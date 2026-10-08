"""E1 (owner, 2026-09-29; rulings 2026-10-08): validator wording sensitivity.

The LLM validator held correct answers because of how the question or the
answer was worded. Owner's ruling: narrow deterministic overrides, one per
sighting class, in the existing SafetyOverride registry. An override fires only
when its issue is the validator's SOLE issue and the deterministic evidence is
there; it DOWNGRADES (served with the human-review banner, NEEDS_HUMAN_REVIEW,
the original issue kept for the log), never SAFE. A deterministic issue still
holds first, whatever the validator said. Each answer an override moves is
listed for the owner's one-by-one sign-off.

  1. Airway (#86, #107): "without confirming the tube is in place" when the
     medic said the airway is done ("we tubed him", "cric'd"): A3's
     already_intubated.
  2. No volume (D2a bench, run_tests B1): "does not confirm concentration to
     compute volume" when the answer uses the dose block's own form, "NO VOLUME
     — confirm concentration to compute volume".
  3. TXA (run 3 finding 6): "TXA … without confirmed (traumatic) hemorrhage"
     when the medic's words state active traumatic bleeding (A23's phrases);
     not for a pregnant patient, not with an infection picture.

Also in E1: the session log records the model the validator's reply names
(validator_model_returned), beside the generator's model_returned (schema 16).
"""
import json
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

PASSED = oc.DeterministicCheck(passed=True, issues=[])


def _gate(history, response, issues):
    ctx = oc.rebuild_patient_context_from_history(history)
    return oc.apply_safety_gate(response, PASSED, {"result": "UNSAFE", "issues": issues, "rationale": ""},
                                ctx, history)


def _downgraded(out, name):
    assert out.verdict == "NEEDS_HUMAN_REVIEW", out.verdict
    assert not out.blocked and out.override_fired == name
    assert out.response.endswith(oc.HUMAN_REVIEW_BANNER)


POST_RSI = "**POST-INTUBATION SEDATION**\n- Ketamine 40 mg IV q20-30min.\n\n**SOURCE**: JTS"
AIRWAY_ISSUES = [
    "Response recommends post-intubation sedation with ketamine without confirming the tube is in place.",  # #86
    "Response recommends post-intubation ketamine without confirming tube placement.",                     # #107
]


@pytest.mark.parametrize("history", ["80kg male, we tubed him, what do I give after RSI",
                                     "80kg male, cric'd, what do I give after RSI"])
@pytest.mark.parametrize("issue", AIRWAY_ISSUES)
def test_a_done_airway_downgrades_the_tube_confirmation_hold(history, issue):
    _downgraded(_gate(history, POST_RSI, [issue]), "airway_secured_post_rsi")


def test_no_done_airway_stays_held():
    out = _gate("RSI an 80kg male trauma patient, what do I give after", POST_RSI, [AIRWAY_ISSUES[0]])
    assert out.verdict == "UNSAFE" and out.blocked


NO_VOLUME = ("**GIVE**\n- Fentanyl IV: 50 mcg. NO VOLUME — confirm concentration to compute volume. "
             "Indication: acute pain / analgesia.")
VOLUME_ISSUE = "Response recommends 50 mcg fentanyl IV but does not confirm concentration to compute volume."  # D2a bench, verbatim


def test_the_no_volume_form_downgrades_the_concentration_hold():
    _downgraded(_gate("80 kg adult, severe pain from a femur fracture, fentanyl IV", NO_VOLUME, [VOLUME_ISSUE]),
                "no_volume_form")


def test_a_volume_line_without_the_form_stays_held():
    out = _gate("80 kg adult, severe pain, fentanyl IV",
                "**GIVE**\n- Draw 1 mL of 0.05mg/mL fentanyl IV (0.05mg).", [VOLUME_ISSUE])
    assert out.verdict == "UNSAFE"


TXA_ANSWER = "**GIVE**\n- TXA 2 g IV over 10 minutes. Indication: traumatic haemorrhage.\n\n**DO THIS**\n1. Apply a tourniquet."


@pytest.mark.parametrize("history, issue", [
    ("have a marine that was hit by an IED - he is bleeding out",
     "Response recommends TXA for a patient with active bleeding from an IED blast without confirmed traumatic hemorrhage."),
    ("he is bleeding out from a leg wound, what do I give him",
     "Response recommends TXA for bleeding without confirmed traumatic hemorrhage."),
    ("GSW to the pelvis with massive bleeding, 40 minutes since injury, should I give TXA",
     "Response recommends TXA for hemorrhage without confirming active bleeding or trauma context."),
])
def test_stated_traumatic_bleeding_downgrades_the_txa_hold(history, issue):
    _downgraded(_gate(history, TXA_ANSWER, [issue]), "txa_stated_traumatic_haemorrhage")


@pytest.mark.parametrize("history, issue", [
    ("BP 80/40, confused, what now", "Response recommends TXA for hypotension without confirmed hemorrhage."),
    ("34 weeks pregnant, she is bleeding heavily", "Response recommends TXA for bleeding in a pregnant patient without confirmed hemorrhage."),
    ("fever 39, pus from the wound, he is bleeding out", "Response recommends TXA for bleeding without confirmed traumatic hemorrhage."),
])
def test_txa_without_stated_traumatic_bleeding_stays_held(history, issue):
    assert _gate(history, TXA_ANSWER, [issue]).verdict == "UNSAFE"


def test_an_override_needs_its_issue_to_be_the_only_one():
    out = _gate("have a marine that was hit by an IED - he is bleeding out", TXA_ANSWER,
                ["Response recommends TXA for bleeding without confirmed traumatic hemorrhage.",
                 "Response omits airway assessment."])
    assert out.verdict == "UNSAFE"


def test_a_deterministic_issue_still_holds_first():
    ctx = oc.rebuild_patient_context_from_history("80kg male, we tubed him")
    det = oc.DeterministicCheck(passed=False, issues=["GIVE line doses 'ketamine' (500mg) …"])
    out = oc.apply_safety_gate(POST_RSI, det, {"result": "UNSAFE", "issues": [AIRWAY_ISSUES[0]]}, ctx,
                               "80kg male, we tubed him")
    assert out.verdict == "UNSAFE" and out.blocked


# ── the validator's model in the log ─────────────────────────────────────────

def test_the_log_records_the_validators_returned_model(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)

    def chat(system, messages, *, model, **k):
        providers._RETURNED.set(f"{model}-as-named-by-the-provider")
        if system == oc.VALIDATOR_PROMPT:
            return '{"result":"SAFE","issues":[],"rationale":"ok"}'
        return "**DO THIS**\n1. Splint the femur.\n\n**SOURCE**: General Evidence-Based Medicine"
    monkeypatch.setattr(providers, "chat", chat)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    class _R:
        def query(self, *a, **k):
            return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.5]]}
    r = oc.query_with_rag("80 kg adult, femur fracture, what do I do", _R())
    entry = json.loads(next(tmp_path.glob("*.jsonl")).read_text().splitlines()[-1])
    assert entry["log_schema"] == 16
    assert entry["validator_model_returned"] == f"{providers.validator_model()}-as-named-by-the-provider"
    assert entry["model_returned"] != entry["validator_model_returned"] or entry["model_returned"].endswith("-as-named-by-the-provider")
    assert r.get("validator_model_returned")
