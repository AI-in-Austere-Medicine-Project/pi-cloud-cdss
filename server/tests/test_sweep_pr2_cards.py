"""Med sweep PR 2 (owner, 2026-10-30): cards.

"PR 2, cards (after PR 1): a card answers a question that names a drug only
if the card serves that drug's signed dose, or holds it by name; otherwise
the drug lane answers. Add the signed doses to: anaphylaxis card (epinephrine
IM 0.3 mg adult / 0.15 mg child), paediatric RSI card (atropine pre-dose),
sepsis card (ceftriaxone 2 g), ketamine sedation drip card (0.5-2 mg/kg/hr as
rate). Rows: epinephrine[0][1][4][9], atropine[5], ceftriaxone[0],
propofol[0], T7."

Live (a7c9043, 2026-10-30), each question named a drug and was answered by a
card that gave no dose for it:
- epinephrine[0][1]: the anaphylaxis card, "Give epinephrine IM now", no dose.
- epinephrine[4][9]: the sepsis card, for a push-dose pressor question.
- ceftriaxone[0]: the sepsis card, "Start antibiotics if available".
- atropine[5]: the RSI bundle, "Ask for atropine by name for the dose".
- propofol[0]: the DCR card, TXA and no propofol.
- T7: the ketamine drip card, "document concentration ... and pump rate".

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (
        '{"result":"SAFE","issues":[],"rationale":"stub"}'
        if "Clinical Safety Validator" in (a[0] if a else "") else "STUB"))


@pytest.fixture
def card_only(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("a card row called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


def run(q):
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=[])


def _section(text, head):
    assert f"**{head}**" in text, text
    return text.split(f"**{head}**")[1].split("\n**", 1)[0]


# ── The rule ────────────────────────────────────────────────────────────────

SEPSIS_CARD_ON_MAIN = (
    "**SEPSIS**\n- Treat as suspected sepsis/septic shock.\n\n**TREAT**\n"
    "1. Oxygen, monitor, IV/IO access, reassess BP and mental status.\n"
    "3. Start antibiotics if available and evacuate urgently.\n")


def test_a_card_with_no_dose_for_the_named_drug_does_not_answer():
    q = "80 kg adult, hypotensive, SBP 75, push-dose pressor, epinephrine IV"
    assert oc.card_unanswered_drugs(q, SEPSIS_CARD_ON_MAIN) == ["epinephrine"]


def test_a_card_that_serves_the_named_drug_answers():
    q = "80 kg adult, septic, fever and hypotension, ceftriaxone IV"
    text = ("**GIVE**\n- ceftriaxone IV: 2 g. Indication: sepsis.\n\n"
            "**CAUTIONS**\n- ceftriaxone — sepsis:\n  - Every 24 hours.\n")
    assert oc.card_unanswered_drugs(q, text) == []


def test_a_card_that_holds_the_named_drug_by_name_answers():
    q = "intubated, 30 kg 8 year old, ketamine drip for sedation"
    text = ("**DRIP**\n- No ketamine infusion rate is signed for a child here. "
            "Use local protocol or medical control.\n")
    assert oc.card_unanswered_drugs(q, text) == []


def test_a_caution_naming_the_drug_is_not_a_dose_or_a_hold():
    q = "20 kg 6 year old, about to intubate, pre-dose for RSI, atropine IV"
    text = ("**GIVE**\n- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: RSI induction.\n\n"
            "**CAUTIONS**\n- ketamine — RSI induction:\n  - JTS ID39 paediatric column: pre-dose "
            "atropine IV/IO in all under 1 year. Ask for atropine by name for the dose.\n")
    assert oc.card_unanswered_drugs(q, text) == ["atropine"]


def test_a_question_naming_no_drug_keeps_the_card():
    assert oc.card_unanswered_drugs("80 kg adult, septic, fever and hypotension",
                                    SEPSIS_CARD_ON_MAIN) == []


# ── The rows the card no longer answers: the drug lane does ─────────────────

@pytest.mark.parametrize("q,card", [
    ("80 kg adult, hypotensive, SBP 75, push-dose pressor, epinephrine IV", "**SEPSIS**"),
    ("20 kg 6 year old, shock, push dose, epinephrine IV", "**SEPSIS**"),
    ("80 kg adult, hypotensive trauma patient, need induction, propofol IV",
     "Start damage-control resuscitation"),
])
def test_the_card_yields_to_the_drug_lane(q, card, no_model):
    r = run(q)
    assert card not in r["response"], r["response"][:400]


def test_the_sepsis_card_still_answers_sepsis_with_no_drug_named(card_only):
    r = run("80 kg adult, septic, fever and hypotension")
    assert "**SEPSIS**" in r["response"], r["response"][:300]


# ── epinephrine[0][1]: anaphylaxis card serves the signed IM dose ───────────

def test_anaphylaxis_adult_gets_epinephrine_0_3_mg_im(card_only):
    r = run("80 kg adult, anaphylaxis, throat swelling, epinephrine IM")
    give = _section(r["response"], "GIVE")
    assert "epinephrine IM" in give and "0.3 mg" in give, r["response"]
    assert "Indication: anaphylaxis" in give
    assert "0.15 mg" not in give
    assert "Give in the anterolateral thigh." in r["response"]


def test_anaphylaxis_child_gets_epinephrine_0_15_mg_im(card_only):
    r = run("20 kg 6 year old, anaphylaxis, throat swelling, epinephrine IM")
    give = _section(r["response"], "GIVE")
    assert "epinephrine IM" in give and "0.15 mg" in give, r["response"]
    assert "0.3 mg" not in give


def test_anaphylaxis_with_no_age_or_weight_holds_epinephrine_by_name(card_only):
    r = run("anaphylaxis, throat swelling")
    give = _section(r["response"], "GIVE")
    assert "epinephrine" in give and "mg" not in give, give
    assert "**ANAPHYLAXIS**" in r["response"]


# ── ceftriaxone[0]: sepsis card serves ceftriaxone 2 g ──────────────────────

def test_sepsis_adult_gets_ceftriaxone_2_g(card_only):
    r = run("80 kg adult, septic, fever and hypotension, ceftriaxone IV")
    give = _section(r["response"], "GIVE")
    assert "ceftriaxone IV" in give and "2 g" in give, r["response"]
    assert "Indication: sepsis" in give
    assert "**SEPSIS**" in r["response"]


def test_sepsis_child_gets_no_adult_ceftriaxone(card_only):
    r = run("20 kg 6 year old, septic, fever and hypotension")
    assert "2 g" not in r["response"], r["response"]


# ── atropine[5]: paediatric RSI card serves the atropine pre-dose ───────────

def test_paediatric_rsi_gets_the_atropine_pre_dose(card_only):
    r = run("20 kg 6 year old, about to intubate, pre-dose for RSI, atropine IV")
    give = _section(r["response"], "GIVE")
    # 0.02 mg/kg x 20 kg = 0.4 mg (min 0.1, max 0.5)
    assert "atropine IV" in give and "0.4 mg" in give, r["response"]
    assert "RSI pre-dose — paediatric intubation" in give
    assert give.index("atropine") < give.index("ketamine"), give


def test_adult_rsi_gets_no_atropine():
    ctx = oc.rebuild_patient_context_from_history("RSI an 80kg male trauma patient")
    text = oc.build_rsi_response(ctx, "RSI an 80kg male trauma patient")
    assert "atropine IV" not in text


# ── T7: ketamine drip card serves the signed rate ───────────────────────────

def test_ketamine_drip_card_serves_the_signed_rate(card_only):
    r = run("ketamine drip for sedation, intubated, 90 kg")
    text = r["response"]
    assert "**KETAMINE SEDATION DRIP**" in text, text
    rate = _section(text, "DRIP")
    assert "ketamine IV: 0.5-2 mg/kg/hr" in rate, rate
    assert "45-180 mg/hr for this 90kg patient" in rate, rate
    assert "Indication: prolonged sedation infusion" in rate
    assert "Load 1 mg/kg IV/IO over 60 seconds first" in text


def test_ketamine_drip_card_holds_a_child_by_name(card_only):
    r = run("ketamine drip for sedation, intubated, 20 kg 6 year old")
    text = r["response"]
    rate = _section(text, "DRIP")
    assert "ketamine" in rate and "mg/kg/hr" not in rate, rate


# ── Found in this PR's replay ───────────────────────────────────────────────
# The seizure card named no benzodiazepine in its no-weight line, so "how much
# midaz for the seizure" left the card for the generator. And "no antivenom
# available" counted as naming antivenom.

def test_the_seizure_card_holds_a_named_benzodiazepine_by_name(card_only):
    r = run("how much midaz for the seizure")
    assert "**ACTIVE SEIZURE**" in r["response"], r["response"][:300]
    assert "No signed benzodiazepine (midazolam) dose without a weight" in r["response"]


def test_a_drug_the_question_does_not_have_is_not_asked(card_only):
    r = run("snakebite, no antivenom available, what do I do")
    assert "**SNAKE BITE**" in r["response"], r["response"][:300]


def test_a_benzodiazepine_already_given_is_named_and_the_card_answers(card_only):
    r = run("80kg male still in status after 10 mg of versed")
    assert "A benzodiazepine (midazolam) has already been given" in r["response"], r["response"]
