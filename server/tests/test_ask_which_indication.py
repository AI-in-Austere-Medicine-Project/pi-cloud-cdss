"""A drug named with no indication is asked about, not offered every entry.

Live portal, 2026-10-15 (session s-mv9htyti-uw34wb80, qwen2.5:3b):

    "Need to give ketamine 89kg IV established"
        -> "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?"
    "500"
        -> "Draw 0.89 mL of 50mg/mL ketamine IV (44.5 mg). Indication:
            post-intubation sedation — repeated bolus (no infusion pump)."
           validator SAFE

The patient was not intubated. ALLOWED_DOSES carried every signed ketamine
entry (12 of them: pain, RSI, post-intubation sedation, agitation, seizure),
and the model picked one. The dose was right for the entry; the entry was the
model's choice. The fix (owner, 2026-10-15): a drug named with no indication,
where more than one signed indication applies, is asked "which indication?" —
the way the vial is asked — and the answer selects the entries offered.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'

TURN_1 = "Need to give ketamine 89kg IV established"
VIAL_ASK = "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?"
TURN_2 = "500"
SERVED_LIVE = ("Draw 0.89 mL of 50mg/mL ketamine IV (44.5 mg). Indication: post-intubation "
               "sedation — repeated bolus (no infusion pump). Contraindications: Hypersensitivity.")
HISTORY_AT_TURN_2 = [{"query": TURN_1, "response": VIAL_ASK}]


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def seen(monkeypatch):
    out = {"allowed": None, "generator": None}
    real = oc.build_allowed_doses

    def build(history, ctx, **kw):
        doses = real(history, ctx, **kw)
        out["allowed"] = [(d.drug, d.indication) for d in doses]
        return doses

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        out["generator"] = messages
        return SERVED_LIVE

    monkeypatch.setattr(oc, "build_allowed_doses", build)
    monkeypatch.setattr(providers, "chat", chat)
    return out


def run(query, history):
    return oc._query_with_rag_internal(query, _JtsHit(), conversation_history=history)


def _ctx(history_text):
    return oc.rebuild_patient_context_from_history(history_text)


# ── the transcript ───────────────────────────────────────────────────────────

def test_turn_1_still_asks_for_the_vial(seen):
    r = run(TURN_1, [])
    assert r["response"] == VIAL_ASK
    assert seen["generator"] is None


def test_turn_2_asks_which_indication_instead_of_serving(seen):
    r = run(TURN_2, HISTORY_AT_TURN_2)
    assert r["source_mode"] == "PRE_GATE", r["response"]
    assert r["response"].startswith("Which indication for ketamine"), r["response"]
    assert seen["generator"] is None, "the model must not be asked to choose the indication"
    for word in ("pain", "RSI", "sedation", "agitation", "seizure"):
        assert word in r["response"], (word, r["response"])


def test_the_question_does_not_name_a_dose(seen):
    r = run(TURN_2, HISTORY_AT_TURN_2)
    assert "mg" not in r["response"].replace("500 mg", "")


ALL_KETAMINE_CLASSES = {"pain", "RSI", "sedation", "agitation", "seizure"}


@pytest.mark.parametrize("answer,kept", [
    ("sedation", "sedation"),
    ("agitation", "agitation"),
    ("seizure", "seizure"),
])
def test_the_answer_puts_that_indications_doses_first_and_removes_none(seen, answer, kept):
    """Owner, 2026-10-15 (#165 review): ask, then surface the stated
    indication's doses; never silently remove a valid dose."""
    history = HISTORY_AT_TURN_2 + [{"query": TURN_2, "response": "Which indication for ketamine — ...?"}]
    run(answer, history)
    assert seen["allowed"], f"premise: '{answer}' reaches the dose builder"
    ket = [oc.indication_class(ind) for drug, ind in seen["allowed"] if drug == "ketamine"]
    n = ket.count(kept)
    assert n and ket[:n] == [kept] * n, (answer, ket)
    assert set(ket) == ALL_KETAMINE_CLASSES, (answer, ket)


@pytest.mark.parametrize("answer", ["pain", "for pain"])
def test_the_pain_answer_is_the_signed_analgesia_card_with_the_ml(seen, answer):
    """Since 2026-10-24 (live harness): "pain" completes a ketamine-for-pain
    request, and the deterministic card answers it: the signed analgesia dose,
    in mL from the confirmed vial, not the model choosing among the offers."""
    history = HISTORY_AT_TURN_2 + [{"query": TURN_2, "response": "Which indication for ketamine — ...?"}]
    r = run(answer, history)
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["response"][:200]
    assert "of 50mg/mL ketamine IV" in r["response"], r["response"]
    assert "Indication: moderate to severe pain / analgesia" in r["response"]


def test_an_answer_that_names_no_indication_is_asked_again(seen):
    history = HISTORY_AT_TURN_2 + [{"query": TURN_2,
                                    "response": "Which indication for ketamine — pain, RSI, ...?"}]
    r = run("yes", history)
    assert r["response"].startswith("Which indication for ketamine"), r["response"]
    assert seen["generator"] is None


def test_for_pain_the_pain_dose_comes_before_the_post_intubation_dose():
    h = f"{TURN_1} {TURN_2} pain"
    offered = [d.indication for d in oc.build_allowed_doses(h, _ctx(h)) if d.drug == "ketamine"]
    assert oc.indication_class(offered[0]) == "pain", offered
    post = [i for i, x in enumerate(offered) if "post-intubation" in x]
    assert post, "the post-intubation entry stays offered"
    assert max(i for i, x in enumerate(offered) if oc.indication_class(x) == "pain") < post[0], offered


@pytest.mark.parametrize("q,drug,kept", [
    ("adult, epi dose for cardiac arrest", "epinephrine",
     {"anaphylaxis", "symptomatic bradycardia — push dose"}),
    ("midazolam dose for sedation", "midazolam",
     {"agitated or violent patient / behavioural emergency"}),
    ("organophosphate poisoning, atropine dose", "atropine", {"symptomatic bradycardia"}),
])
def test_a_stated_indication_removes_no_dose(q, drug, kept):
    """The three the first revision narrowed away, restored by the owner."""
    ctx = _ctx(q)
    if ctx.dosing_weight_kg is None and drug != "epinephrine":
        ctx = oc.PatientContext(confirmed_weight_kg=70.0)
    offered = {d.indication for d in oc.build_allowed_doses(q, ctx) if d.drug == drug}
    assert kept <= offered, offered


# ── where the question must not fire ─────────────────────────────────────────

@pytest.mark.parametrize("q", [
    "89kg, ketamine IV for femur fracture pain",
    "89 kg adult, RSI with ketamine and roc, IV established",
    "89kg intubated patient, ketamine for sedation, IV",
    "89kg agitated combative patient, ketamine IM",
])
def test_a_stated_indication_is_not_asked(q):
    ctx = _ctx(q)
    action, text = oc.pre_gate(q, ctx, "")
    assert not (text or "").startswith("Which indication"), (q, text)


def test_a_drug_with_one_signed_indication_is_not_asked():
    q = "80kg adult, TXA dose"
    action, text = oc.pre_gate(q, _ctx(q), "")
    assert not (text or "").startswith("Which indication"), text


def test_every_signed_indication_has_a_class():
    """A new signature whose label no class reads would be offered with no way to
    ask about it or select it — the bank must stay covered."""
    import drug_contracts
    missing = sorted({(n, e["indication"]) for n, es in drug_contracts.servable_entries().items()
                      for e in es if oc.indication_class(e["indication"]) is None})
    assert not missing, missing


def test_the_batch2_antibiotic_labels_land_in_their_own_classes():
    """Signing batch 2 (2026-10-19) signed cefazolin for "open fracture / wound
    prophylaxis" and ceftriaxone for "sepsis". The TBI class read any label with
    "prophylaxis" in it, so the cefazolin wound entry would have been offered
    as TBI seizure prophylaxis; "sepsis" had no class at all."""
    assert oc.indication_class("open fracture / wound prophylaxis") == "wound infection prophylaxis"
    assert oc.indication_class("sepsis") == "sepsis"
    # The existing labels keep their classes.
    assert oc.indication_class("severe TBI — seizure prophylaxis, loading dose") == "TBI seizure prophylaxis"


def test_the_question_lists_only_classes_the_drug_is_signed_for():
    q = "70kg adult, midazolam IV dose"
    action, text = oc.pre_gate(q, _ctx(q), "")
    assert action == "ASK" and text.startswith("Which indication for midazolam"), text
    assert "pain" not in text and "RSI" not in text, text


# ── Narrowed by the replay (2026-10-15): each of these was asked in the first run ──

@pytest.mark.parametrize("q", [
    # an indication the drug is signed for is stated, though only as an infusion
    "epinephrine infusion rate for refractory shock",
    # the turn names the drug to say it is NOT the one
    "I said norepinephrine not epinephrine, what is the dose",
    # not a dose request
    "what is the standard dilution for a keppra bag, I just want the concentration not a dose",
])
def test_not_asked(q):
    action, text = oc.pre_gate(q, _ctx(q), "")
    assert not (text or "").startswith("Which indication"), (q, text)


def test_a_stated_route_with_one_indication_on_it_is_not_asked():
    q = "epinephrine IM dose and concentration"
    action, text = oc.pre_gate(q, _ctx(q), "")
    assert not (text or "").startswith("Which indication"), text


def test_a_stated_route_with_several_indications_on_it_is_still_asked():
    """The transcript: IV stated, and ketamine is signed IV for five classes."""
    h = f"{TURN_1} {TURN_2}"
    text = oc.which_indication_question(h, _ctx(h))
    assert text and text.startswith("Which indication for ketamine"), text


# ── A ketamine drip with no reason (owner, 2026-10-20, #170 review) ─────────
# With the sedation infusion signed, "ketamine drip 80 kg" must be asked which
# indication, not answered. It got the RSI bundle ("ketamine drip" was an RSI
# word) until A31 (#172). "Intubated" with the drip is read as sedation; the
# owner accepted that.

def test_a_ketamine_drip_with_no_reason_is_asked_which_indication(seen):
    q = "ketamine drip 80 kg"
    r = run(q, [])
    if r["response"] == VIAL_ASK:
        r = run("500", [{"query": q, "response": r["response"]}])
    assert r["response"].startswith("Which indication for ketamine"), r["response"]
    assert seen["generator"] is None
