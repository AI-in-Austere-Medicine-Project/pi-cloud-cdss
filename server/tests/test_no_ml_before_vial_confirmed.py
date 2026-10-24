"""No millilitre is served from a vial the medic has not confirmed.

Owner, 2026-10-24 (live log, finding 2): "ketamine IV 9 mg … 1.8 mL — confirm
vial" and "0.18 mL of 50 mg/mL undiluted — confirm vial" were served before the
vial was confirmed. SAFETY.md: a millilitre is served only from a confirmed
concentration. "Until confirmed, mg only, with the vial question; no mL
anywhere in the answer, including vial-math sections."

Where the mL came from, for a drug with a pending vial question (ketamine,
confirm_required):
- the brief's computed line ("At 50 mg/mL that's 0.4 mL — confirm vial",
  "Dilute first — …: 1.8 mL — confirm vial");
- the "Vial math" add-on on the which-vial question;
- the entry's dilution cautions on the card and in the offered doses
  ("1 mL of ketamine 50 mg/mL in 9 mL", "0.04 mL/kg of that dilution");
- the dose check, which passed a model answer stating ketamine mL ("Draw 0.4
  mL of 50mg/mL ketamine IV (20 mg)") with the vial unconfirmed.
A drug whose one signed vial the kit declares (rocuronium, 10 mg/mL) is
confirmed by the kit and keeps its mL.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
LIVE = "have a 6 year old in pain. need to give ketamine iV established weight is 45kg"
ADULT = "80 kg adult, femur fracture, severe pain, IV access, ketamine for pain"
VIAL_Q = "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?"
CHIP = "Show the vial math for that dose."

# The vial's own label and a concentration are not a volume to draw.
_LABEL_RE = re.compile(r"\d+(?:\.\d+)?\s*mg\s*/\s*\d+(?:\.\d+)?\s*mL\s*(?:vial|ampoule|amp)\b"
                       r"|\d+(?:\.\d+)?\s*(?:mg|mcg)\s*/\s*mL", re.IGNORECASE)
_ML_RE = re.compile(r"\d(?:\.\d+)?\s*mL\b", re.IGNORECASE)


def ml_volumes(text):
    return _ML_RE.findall(_LABEL_RE.sub(" ", text or ""))


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def gen(monkeypatch):
    out = {"answer": "STUB", "allowed": None}
    real = oc.build_allowed_doses

    def build(history, ctx, **kw):
        doses = real(history, ctx, **kw)
        out["allowed"] = doses
        return doses

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        return out["answer"]

    monkeypatch.setattr(oc, "build_allowed_doses", build)
    monkeypatch.setattr(providers, "chat", chat)
    return out


def run_flow(turns):
    hist, out = [], []
    for q in turns:
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        out.append(r)
        hist.append({"query": q, "response": r["response"]})
    return out


@pytest.mark.parametrize("q", [LIVE, ADULT])
def test_the_card_serves_mg_and_the_vial_question_and_no_ml(gen, q):
    (r,) = run_flow([q])
    assert "ketamine IV:" in r["response"] and "mg" in r["response"]
    assert VIAL_Q in r["response"]
    assert ml_volumes(r["response"]) == [], ml_volumes(r["response"])
    assert ml_volumes(r["brief"]) == [], r["brief"]


def test_the_vial_math_chip_is_the_vial_question_and_no_ml(gen):
    first, chip = run_flow([LIVE, CHIP])
    assert chip["response"] == VIAL_Q, chip["response"]
    assert ml_volumes(chip.get("brief", "")) == []


def test_the_offered_doses_carry_no_ml_before_the_vial_is_confirmed():
    ctx = oc.rebuild_patient_context_from_history(LIVE)
    for d in oc.build_allowed_doses(LIVE, ctx):
        if d.drug == "ketamine":
            assert d.volume_ml is None
            for c in d.cautions:
                assert ml_volumes(c) == [], c
            assert ml_volumes(d.warning or "") == [], d.warning


@pytest.mark.parametrize("answer", [
    "**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). Indication: moderate to severe pain / analgesia.",
    "Give ketamine 20 mg IV (0.4 mL of the 50 mg/mL vial).",
    "Give 0.4 mL of ketamine IV.",
    "Dilute 1 mL of ketamine 50 mg/mL in 9 mL of normal saline and give 4 mL.",
])
def test_a_model_answer_with_ketamine_ml_before_the_vial_is_confirmed_holds(answer):
    ctx = oc.rebuild_patient_context_from_history(ADULT)
    allowed = oc.build_allowed_doses(ADULT, ctx)
    issues = oc.run_deterministic_checks(ADULT, answer, ctx, allowed).issues
    assert any("vial" in i.lower() and "ketamine" in i.lower() for i in issues), issues


def test_a_model_answer_in_mg_before_the_vial_is_confirmed_passes():
    ctx = oc.rebuild_patient_context_from_history(ADULT)
    allowed = oc.build_allowed_doses(ADULT, ctx)
    answer = ("**GIVE**\n- ketamine IV: 20 mg. Indication: moderate to severe pain / analgesia.\n"
              "Confirm the vial: 500 mg / 10 mL (50 mg/mL)?")
    assert oc.run_deterministic_checks(ADULT, answer, ctx, allowed).issues == []


# ── once confirmed: a straight answer in mL ──────────────────────────────────

CONFIRMED = ADULT + " 500 mg / 10 mL vial"


def test_after_the_vial_is_confirmed_the_card_serves_the_ml():
    ctx = oc.rebuild_patient_context_from_history(CONFIRMED)
    assert ctx.confirmed_concentrations == {"ketamine": 50.0}
    card = oc.build_ketamine_analgesia_response(ctx)
    assert "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)" in card, card


def test_after_the_vial_is_confirmed_a_model_answer_in_ml_passes():
    ctx = oc.rebuild_patient_context_from_history(CONFIRMED)
    allowed = oc.build_allowed_doses(CONFIRMED, ctx)
    answer = ("**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). "
              "Indication: moderate to severe pain / analgesia.")
    assert oc.run_deterministic_checks(CONFIRMED, answer, ctx, allowed).issues == []


def test_after_the_vial_is_confirmed_the_dilution_cautions_come_back():
    q = LIVE + " 500 mg / 10 mL vial"
    ctx = oc.rebuild_patient_context_from_history(q)
    ket = [d for d in oc.build_allowed_doses(q, ctx) if d.drug == "ketamine"
           and d.indication.startswith("moderate")]
    assert ket and any("9 mL of normal saline" in c for c in ket[0].cautions), ket


def test_a_kit_declared_vial_keeps_its_ml():
    q = "RSI 80 kg adult, IV established, rocuronium"
    ctx = oc.rebuild_patient_context_from_history(q)
    card = oc.build_rsi_response(ctx, q)
    assert "Draw 9.6 mL of 10mg/mL rocuronium IV (96 mg)" in card, card
