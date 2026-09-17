"""
EdgeCDSS — the validator's invented equipment preconditions.

See TODO.md, "Safety gate": "Validator invents equipment preconditions and
blocks contract-signed doses." Field report: server/feedback.log line 49
(entry 48), "500mg / 10ml", held for "without confirming the presence of an
infusion pump".

Offline. Runs the real contract bank (build_allowed_doses), the real
deterministic check and the real gate; only the validator's verdict is
supplied, in the words the validator used.

Two kinds of test:

- FALSE BLOCKS, xfail(strict=True). A dose the contract signs for exactly this
  situation, held for a missing pump. These are the bug. strict means the fix
  turns them XPASS and the run goes red until the marker comes off.

- HOLES, plain tests that pass today. Each is a case the discarded override
  (wip/equipment-precondition-override) served: it matched drug + milligrams
  only, ignoring indication, route and non-canonical dose lines. The
  deterministic check passes every one of these on main, so the validator's
  verdict is the only thing holding them. Any fix must keep them blocked.

    cd server && ./run_unit_tests.sh
"""

import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402

FALSE_BLOCK = pytest.mark.xfail(strict=True, reason=(
    "TODO.md Safety gate: validator invents an equipment precondition and the "
    "gate blocks a contract-signed dose"))


def pump_issue(mg, purpose="sedation"):
    return (f"Response recommends {mg} mg ketamine IV for {purpose} without "
            "confirming the presence of an infusion pump.")


def run_gate(history, response, issues):
    ctx = oc.rebuild_patient_context_from_history(history, conversation_history=[])
    allowed = oc.build_allowed_doses(history, ctx)
    det = oc.run_deterministic_checks(history, response, ctx, allowed)
    outcome = oc.apply_safety_gate(
        response, det, {"result": "UNSAFE", "issues": list(issues), "rationale": ""},
        ctx, history)
    return allowed, det, outcome


def signed(allowed, drug="ketamine"):
    return {(d.indication, d.route, d.dose_mg) for d in allowed if d.drug == drug}


# ── False blocks: the bug ────────────────────────────────────────────────────

@FALSE_BLOCK
def test_signed_no_pump_bolus_is_blocked_for_no_pump():
    """100 kg: the bank signs 50 mg IV as the repeated bolus for sedation with
    NO infusion pump. Blocking it for a missing pump inverts the contract."""
    history = "100kg male, intubated, need ongoing sedation with ketamine"
    response = ("**GIVE**\n- Draw 1 mL of 50mg/mL ketamine IV (50 mg). "
                "Indication: post-intubation sedation.\n")
    allowed, det, outcome = run_gate(history, response, [pump_issue(50)])
    assert ("post-intubation sedation — repeated bolus (no infusion pump)",
            "IV", 50.0) in signed(allowed)
    assert det.passed
    assert not outcome.blocked, "the signed no-pump dose was held for no pump"


@FALSE_BLOCK
def test_pump_dependent_dose_blocked_when_history_states_the_pump():
    """100 kg, "infusion pump available" in the history: the bank signs 100 mg
    IV as the loading dose for exactly that. The precondition is met."""
    history = ("100kg male, intubated, infusion pump available, need ongoing "
               "sedation with ketamine")
    response = ("**GIVE**\n- Draw 2 mL of 50mg/mL ketamine IV (100 mg). "
                "Indication: ongoing sedation loading dose.\n")
    allowed, det, outcome = run_gate(history, response, [pump_issue(100)])
    assert ("ongoing sedation — loading dose (infusion pump available)",
            "IV", 100.0) in signed(allowed)
    assert det.passed
    assert not outcome.blocked, "a pump-dependent dose was held with the pump stated"


# ── Holes: must stay blocked under any fix ───────────────────────────────────

def test_pump_dependent_dose_with_no_pump_stated_stays_blocked():
    """Entry 48's complaint at a weight where it is TRUE. 100 kg: 100 mg is
    signed only as the pump-available loading dose; the no-pump bolus is 50 mg.
    Nothing establishes a pump, so the finding selects between signed entries."""
    history = "100kg male, intubated, need ongoing sedation with ketamine"
    response = ("**GIVE**\n- Draw 2 mL of 50mg/mL ketamine IV (100 mg). "
                "Indication: post-intubation sedation.\n")
    allowed, det, outcome = run_gate(history, response, [pump_issue(100)])
    s = signed(allowed)
    assert ("ongoing sedation — loading dose (infusion pump available)", "IV", 100.0) in s
    assert ("post-intubation sedation — repeated bolus (no infusion pump)", "IV", 50.0) in s
    assert det.passed, "fixture drifted: the deterministic check now catches this"
    assert outcome.blocked


def test_route_no_entry_signs_stays_blocked():
    """50 kg, ketamine 100 mg IM. No IM entry signs 100 mg (IM dissociative is
    200 mg); only the IV induction entry has 100 mg. Route must be compared."""
    history = "RSI a 50kg female ketamine and rocuronium, now intubated, sedation"
    response = ("**GIVE**\n- Draw 2 mL of 50mg/mL ketamine IM (100 mg). "
                "Indication: post-intubation sedation.\n")
    allowed, det, outcome = run_gate(history, response, [pump_issue(100)])
    s = signed(allowed)
    assert ("RSI induction", "IV", 100.0) in s
    assert not any(route == "IM" and mg == 100.0 for _, route, mg in s)
    assert det.passed, "fixture drifted: the deterministic check now catches this"
    assert outcome.blocked


def test_induction_dose_relabelled_as_sedation_stays_blocked():
    """50 kg: the signed repeated-bolus sedation dose is 25 mg; 100 mg is the
    signed INDUCTION dose. Served for sedation it is four times the signed
    dose. Indication must be compared, not milligrams alone."""
    history = "RSI a 50kg female ketamine and rocuronium, now intubated, sedation"
    response = ("**GIVE**\n- Draw 2 mL of 50mg/mL ketamine IV (100 mg). "
                "Indication: post-intubation sedation.\n")
    allowed, det, outcome = run_gate(history, response, [pump_issue(100)])
    s = signed(allowed)
    assert ("RSI induction", "IV", 100.0) in s
    assert [mg for ind, route, mg in s
            if "sedation — repeated bolus" in ind] == [25.0]
    assert det.passed, "fixture drifted: the deterministic check now catches this"
    assert outcome.blocked


def test_uncontracted_dose_outside_canonical_form_stays_blocked():
    """80 kg: one canonical ketamine line that matches a signed dose, plus
    midazolam 5 mg in a non-canonical line and in no contract here. A fix that
    checks only canonical lines lets the second dose ride along."""
    history = "80kg male, intubated, need ongoing sedation with ketamine"
    response = ("**GIVE**\n- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). "
                "Indication: post-intubation sedation.\n"
                "- midazolam IV: 5 mg. Indication: adjunct sedation.\n")
    allowed, det, outcome = run_gate(history, response, [
        "Response recommends a sedation infusion without confirming the "
        "presence of an infusion pump."])
    assert ("post-intubation sedation — repeated bolus (no infusion pump)",
            "IV", 40.0) in signed(allowed)
    assert not any(d.drug == "midazolam" for d in allowed)
    assert det.passed, "fixture drifted: the deterministic check now catches this"
    assert outcome.blocked
