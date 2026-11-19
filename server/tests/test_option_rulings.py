"""Rulings on the clarifying-question option audit (owner, 2026-11-19).

Owner: "One PR after the two pending ones, a commit per item, failing test first on
each, PFC and EMS replays, every moved row listed."

Each section is one ruling. The questions are driven turn by turn with the model
stubbed out; where a turn reaches the generator, the prompt it was given is captured.
"""
import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

dc = oc.drug_contracts


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def run(q, history=None):
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=history or [])


@pytest.fixture
def ems(monkeypatch):
    monkeypatch.setattr(dc, "SERVED_SET", "EMS")


@pytest.fixture
def card_only(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("this turn called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


@pytest.fixture
def model(monkeypatch):
    """The generator writes `text` (default: nothing dosed); the validator says SAFE.
    The generator's prompt is kept in `prompts`."""
    state = {"text": "Reassess.", "prompts": []}

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return '{"result":"SAFE","issues":[],"rationale":"stub"}'
        state["prompts"].append(f"{system}\n{messages}")
        return state["text"]
    monkeypatch.setattr(providers, "chat", chat)
    return state


def _offered_block(prompt: str) -> str:
    i = prompt.find("ALLOWED_DOSES — use EXACTLY")
    if i < 0:
        return ""
    end = prompt.find("────", i)
    return prompt[i:end if end > 0 else i + 4000]


# ── 1. A question offers only drugs signed for what is being asked ──────────
# Owner: "the EMS pain question lists aspirin, whose signed entry is cardiac chest
# pain. A question may only offer a drug whose signed indication matches the one being
# asked about." Found: on EMS, "moderate" offered aspirin 324 mg to the generator for a
# femur fracture, and a model line "aspirin PO: 324 mg. Indication: pain from femur
# fracture" passed the deterministic checks.

FEMUR = "80 kg adult, broken femur, pain, what can I give"


def test_ems_pain_question_does_not_offer_aspirin(ems, card_only):
    asked = run(FEMUR)["response"]
    assert asked.startswith(oc.PAIN_SEVERITY_QUESTION_PREFIX), asked[:300]
    assert "aspirin" not in asked.lower(), asked


@pytest.mark.parametrize("level", ["moderate", "severe"])
def test_ems_pain_answer_offers_no_aspirin_to_the_generator(ems, model, level):
    asked = run(FEMUR)["response"]
    run(level, [{"query": FEMUR, "response": asked}])
    block = _offered_block(model["prompts"][-1])
    assert "ketamine" in block and "aspirin" not in block.lower(), block


def test_ems_aspirin_written_for_femur_pain_holds(ems, model):
    asked = run(FEMUR)["response"]
    model["text"] = "**GIVE**\n- aspirin PO: 324 mg. Indication: pain from femur fracture.\n"
    r = run("moderate", [{"query": FEMUR, "response": asked}])
    assert r["validator_result"] == "UNSAFE", r["response"][:300]


def test_ems_aspirin_is_still_offered_for_cardiac_chest_pain(ems, model):
    run("80 kg adult, cardiac chest pain, suspected ACS, aspirin dose")
    assert "aspirin PO: 324 mg" in _offered_block(model["prompts"][-1])


def test_pfc_pain_question_unchanged(card_only):
    asked = run(FEMUR)["response"]
    for drug in ("ketamine", "fentanyl", "morphine", "acetaminophen"):
        assert drug in asked, asked


# ── 2. A child, and no child entry for the drug: hold at once ───────────────
# Owner: "Child with no child entry for that drug in the active set: hold at once ("no
# signed dose of X for a child"). Never ask for a weight first. Same for the
# estimated-weight question." Found: "Need weight in kg before dosing." was asked for a
# child whatever the drug, and any weight then offered nothing (PFC artesunate, calcium
# chloride, ertapenem, moxifloxacin, phytomenadione, propofol, sodium chloride 3%; EMS
# acetaminophen, aspirin, atropine, dextrose, norepinephrine, ondansetron).

def _child_hold(r, drug):
    low = r["response"].lower()
    assert r["validator_result"] == "UNSAFE", r["response"][:300]
    assert f"no signed dose of {drug} for a child" in low, r["response"][:300]
    assert "need weight" not in low and oc.WEIGHT_CONFIRM_ASK.lower() not in low


@pytest.mark.parametrize("drug", ["artesunate", "ertapenem", "moxifloxacin", "propofol"])
def test_pfc_child_with_no_child_entry_holds_without_asking_a_weight(drug, card_only):
    _child_hold(run(f"6 year old child, {drug} dose"), drug)


@pytest.mark.parametrize("drug", ["ondansetron", "atropine", "acetaminophen"])
def test_ems_child_with_no_child_entry_holds_without_asking_a_weight(drug, ems, card_only):
    _child_hold(run(f"6 year old child, {drug} dose"), drug)


def test_an_estimated_weight_is_not_asked_to_be_confirmed_either(card_only):
    r = run("child, maybe about 20 kg, artesunate dose")
    _child_hold(r, "artesunate")


def test_a_child_with_a_weight_and_no_child_entry_holds(card_only):
    _child_hold(run("6 year old child 20 kg, ertapenem dose"), "ertapenem")


@pytest.mark.parametrize("q", ["6 year old child, ketamine for pain", "6 year old child, morphine dose"])
def test_a_drug_with_a_child_entry_still_asks_the_weight(q, card_only):
    assert run(q)["response"] == "Need weight in kg before dosing."


def test_the_estimated_weight_question_stays_for_a_drug_with_a_child_entry(card_only):
    assert run("child, maybe about 20 kg, morphine dose")["response"] == oc.WEIGHT_CONFIRM_ASK


# ── 3. The route question offers only signed routes ─────────────────────────
# Owner: "Route question: offer only the routes signed for this drug and this
# patient's population. One signed route: no question, read it back. None: hold."
# Found: "IV or IM? Do you have access?" is asked for ketamine and vitamin K whatever
# is signed. EMS ketamine is signed adult IM only; PFC vitamin K adult IV only.

ROUTE_ASK = "IV or IM? Do you have access?"


def _ketamine_lines(block):
    return [l for l in block.splitlines() if l.startswith("- ") and "ketamine" in l.lower()]


def test_ems_adult_ketamine_is_not_asked_the_route_and_gets_im(ems, model):
    q = "80 kg adult, ketamine for pain, severe"
    r = run(q)
    assert r["response"] != ROUTE_ASK
    if r["response"].startswith("Which ketamine do you have"):    # the vial: a further question
        vial = r["response"].split("—", 1)[1].split("(")[0].strip()
        r = run(vial, [{"query": q, "response": r["response"]}])
    assert model["prompts"], (r["source_mode"], r["response"][:600])
    lines = _ketamine_lines(_offered_block(model["prompts"][-1]))
    assert lines and all(" IM" in l for l in lines), lines


def test_pfc_adult_vitamin_k_is_not_asked_the_route_and_gets_iv(model):
    r = run("80 kg adult, vitamin k dose")
    assert r["response"] != ROUTE_ASK
    assert "phytomenadione IV" in _offered_block(model["prompts"][-1])


def test_pfc_adult_ketamine_still_asks_iv_or_im(card_only):
    assert run("80 kg adult, ketamine for pain")["response"] == ROUTE_ASK


def test_no_signed_iv_or_im_route_holds(card_only, monkeypatch):
    live = dc.servable_entries
    monkeypatch.setattr(dc, "servable_entries", lambda *a, **k: {
        d: ([e for e in es if e.get("route") not in ("IV", "IM", "IO")] if d == "ketamine" else es)
        for d, es in live(*a, **k).items()})
    r = run("80 kg adult, ketamine for pain")
    assert r["validator_result"] == "UNSAFE", r["response"][:300]
    assert "no signed iv or im dose of ketamine" in r["response"].lower(), r["response"][:300]


# ── 4. Ketamine's seizure option names the refractory seizure ───────────────
# Owner: "Ketamine indication question on PFC: the option reads "refractory seizure
# (benzodiazepine already given)" and reaches the signed ketamine entry. Plain
# "seizure" still goes to the seizure card." Found: the option read "seizure", and that
# answer went to the active-seizure card (lorazepam 4 mg), never to ketamine's signed
# refractory-seizure entry.

KETAMINE_Q = "80 kg adult, ketamine dose IV"
REFRACTORY = "refractory seizure (benzodiazepine already given)"


def _ketamine_question():
    """The indication question, after the vial question where the kit asks it."""
    hist, r = [], run(KETAMINE_Q)
    hist.append({"query": KETAMINE_Q, "response": r["response"]})
    if r["response"].startswith("Which ketamine do you have"):
        vial = r["response"].split("—", 1)[1].split("(")[0].strip()
        r = run(vial, hist)
        hist.append({"query": vial, "response": r["response"]})
    return r["response"], hist


def test_the_ketamine_question_offers_refractory_seizure(card_only):
    asked, _ = _ketamine_question()
    assert asked.startswith(oc.INDICATION_QUESTION_PREFIX + "ketamine"), asked
    assert REFRACTORY in asked and ", seizure or" not in asked and "seizure, " not in asked, asked


def test_the_refractory_option_reaches_the_signed_ketamine_entry(card_only):
    _, hist = _ketamine_question()
    r = run(REFRACTORY, hist)
    give = [l for l in r["response"].splitlines() if "ketamine IV" in l and "160 mg" in l]
    assert give, r["response"][:600]
    assert "Indication: refractory seizure (benzodiazepine-refractory)" in r["response"]


def test_plain_seizure_still_goes_to_the_seizure_card(card_only):
    _, hist = _ketamine_question()
    r = run("seizure", hist)
    assert r["response"].startswith("**ACTIVE SEIZURE**") and "lorazepam" in r["response"], r["response"][:300]


# ── 5. The child pain question with a weight known ─────────────────────────
# Owner: "PFC child pain question: fix the label so it does not say "no dose offered,
# need a weight" when a weight is already known." Found: with 20 kg or 12 kg given, each
# level read "no dose offered (... need a weight)", and each still dosed once answered.

@pytest.mark.parametrize("q", ["6 year old child 20 kg, pain, what can I give",
                               "child 12 kg, broken arm, pain, what can I give"])
def test_child_pain_question_with_a_weight_names_what_each_level_offers(q, card_only):
    asked = run(q)["response"]
    assert asked.startswith(oc.PAIN_SEVERITY_QUESTION_PREFIX), asked[:300]
    assert "need a weight" not in asked and "needs a weight" not in asked, asked
    severe = [l for l in asked.splitlines() if l.startswith("- severe")][0]
    assert "dosing" in severe and "no dose offered" not in severe, severe


def test_child_pain_question_with_no_weight_is_still_asked_the_weight_first(card_only):
    assert run("6 year old child, pain, what can I give")["response"] == "Need weight in kg before dosing."
