"""
EdgeCDSS — safety gate regression tests (SC-3, SC-6, T-13).

Offline: constructs gate inputs directly. No validator is ever called, so no
test here asserts what verdict the LLM produces — only what the gate does with
a verdict. The validator is non-deterministic (S-8) and pinning it is T-4,
which is out of scope for v4.1.

    cd server && ./run_unit_tests.sh
"""

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai_client import (  # noqa: E402
    SAFETY_OVERRIDES, DeterministicCheck, PatientContext,
    apply_safety_gate, find_fired_override,
)
from test_fixtures import S2_GATE_QUESTION_PREVIEW, S2_IED_PREVIEW  # noqa: E402

PASS = DeterministicCheck(passed=True)
FAIL = DeterministicCheck(passed=False, issues=["Deterministic issue for test."])


def unsafe(issues, rationale=""):
    return {"result": "UNSAFE", "issues": list(issues), "rationale": rationale}


def gate(response, issues, ctx=None, history="", det=PASS, verdict="UNSAFE"):
    return apply_safety_gate(
        response, det,
        {"result": verdict, "issues": list(issues), "rationale": ""},
        ctx, history,
    )


# ── The override matrix ─────────────────────────────────────────────────────
# One entry per registry branch. Each supplies a case that MUST fire it and a
# case that MUST NOT — so deleting the branch fails the positive test and
# widening its condition to always-true fails the negative one.

_CLINICAL = "**DO THIS**\n1. Reassess the patient.\n"

OVERRIDE_CASES = {
    "pediatric_weight_confirmed": {
        "issues": ["Medication dose given without confirmed weight for pediatric patient."],
        "response": _CLINICAL,
        "ctx": PatientContext(confirmed_weight_kg=20.0, is_pediatric=True),
        "neg_ctx": PatientContext(is_pediatric=True),          # no confirmed weight
    },
    "cico_airway": {
        "issues": ["Failed airway described without a definitive surgical airway."],
        "response": _CLINICAL + "Perform cricothyrotomy now.\n",
        "neg_response": _CLINICAL + "Reposition and try again.\n",
    },
    "paralytic_with_induction": {
        "issues": ["Paralytic without induction agent — awake paralysis risk."],
        "response": _CLINICAL + "Give ketamine, then rocuronium.\n",
        "neg_response": _CLINICAL + "Give rocuronium.\n",
    },
    "tbi_steroid_absent": {
        "issues": ["Response omits the steroid warning for TBI."],
        "response": _CLINICAL + "Maintain SBP > 110 mmHg.\n",
        "neg_response": _CLINICAL + "Give dexamethasone 4mg.\n",
    },
    "sepsis_hemorrhage_no_dcr": {
        "issues": ["Sepsis presentation managed as hemorrhage."],
        "response": _CLINICAL + "Start antibiotics and source control.\n",
        "neg_response": _CLINICAL + "Initiate DCR with whole blood.\n",
    },
    "fluids_resuscitation": {
        "issues": ["Response recommends resuscitation without a clear endpoint."],
        "response": _CLINICAL + "Give 500 mL crystalloid.\n",
        "neg_response": _CLINICAL + "Elevate the legs.\n",
    },
    "tension_pneumo_decompression": {
        "issues": ["Needle decompression described without confirming tension pneumothorax."],
        "response": _CLINICAL + "Perform needle thoracostomy at the 5th ICS.\n",
        "neg_response": _CLINICAL + "Reassess breath sounds.\n",
    },
    "dangerous_reassurance_has_action": {
        "issues": ["Dangerous reassurance — implies the patient is stable."],
        "response": _CLINICAL + "Monitor vitals and evacuate.\n",
        "neg_response": _CLINICAL,
    },
    "txa_clear_hemorrhage": {
        "issues": ["Tranexamic acid recommended without a documented indication."],
        "response": _CLINICAL + "Give TXA 1g IV.\n",
        "history": "gunshot wound to the thigh with arterial bleed, tourniquet applied",
        "neg_history": "septic patient with fever and pus draining, BP 80/40",
    },
}

# Declared by hand. test_every_override_has_coverage compares this against the
# registry, so a tenth override cannot be added without writing its pair.
TESTED_OVERRIDES = {
    "pediatric_weight_confirmed", "cico_airway", "paralytic_with_induction",
    "tbi_steroid_absent", "sepsis_hemorrhage_no_dcr", "fluids_resuscitation",
    "tension_pneumo_decompression", "dangerous_reassurance_has_action",
    "txa_clear_hemorrhage",
}


def _positive(name):
    c = OVERRIDE_CASES[name]
    return gate(c["response"], c["issues"], c.get("ctx"), c.get("history", ""))


def _negative(name):
    c = OVERRIDE_CASES[name]
    return gate(c.get("neg_response", c["response"]), c["issues"],
                c.get("neg_ctx", c.get("ctx")), c.get("neg_history", c.get("history", "")))


def test_every_override_has_coverage():
    """Anti-silent-pass: a new override branch must arrive with its tests."""
    registry = {o.name for o in SAFETY_OVERRIDES}
    assert registry == TESTED_OVERRIDES, (
        f"untested overrides: {registry - TESTED_OVERRIDES}; "
        f"stale test entries: {TESTED_OVERRIDES - registry}"
    )
    assert set(OVERRIDE_CASES) == registry


def test_each_override_fires_on_its_case():
    for name in OVERRIDE_CASES:
        outcome = _positive(name)
        assert outcome.override_fired == name, f"{name}: fired {outcome.override_fired!r}"


def test_each_override_does_not_fire_when_its_condition_fails():
    for name in OVERRIDE_CASES:
        outcome = _negative(name)
        assert outcome.override_fired is None, f"{name} fired when it should not have"
        assert outcome.blocked is True, f"{name}: gate must block when no override applies"
        assert outcome.verdict == "UNSAFE"


def test_override_never_empties_issues():
    """SC-3: a fired override preserves the issue list and downgrades."""
    for name in OVERRIDE_CASES:
        outcome = _positive(name)
        assert outcome.issues == OVERRIDE_CASES[name]["issues"], name
        assert outcome.verdict == "NEEDS_HUMAN_REVIEW", name
        assert outcome.blocked is False, name
        assert "requires human review" in outcome.response, name


def test_unrelated_co_occurring_issue_defeats_the_override():
    """The requires_sole_issue guard: 8 of 9 branches must not dismiss a block
    when an unrelated issue is also present."""
    unrelated = "GIVE line doses 'amiodarone' (300mg) but that medication is not in the ALLOWED_DOSES contract."
    for name in OVERRIDE_CASES:
        if name == "pediatric_weight_confirmed":
            continue          # see test_pediatric_override_sc5_gap_is_pinned
        c = OVERRIDE_CASES[name]
        outcome = gate(c["response"], c["issues"] + [unrelated],
                       c.get("ctx"), c.get("history", ""))
        assert outcome.override_fired is None, f"{name} fired despite an unrelated issue"
        assert outcome.blocked is True, name


def test_pediatric_override_sc5_gap_is_pinned():
    """The pediatric-weight override still fires with unrelated issues present.

    This is the SC-5 item on TODO.md, deliberately NOT fixed in v4.1. Pinned so
    the behaviour is a recorded decision rather than an accident, and so the day
    SC-5 lands this test fails and has to be updated on purpose.

    Under SC-3 the consequence is bounded: the unrelated issue is preserved in
    the log and the medic sees the review banner. In v4.0 it was discarded and
    the response was served clean.
    """
    c = OVERRIDE_CASES["pediatric_weight_confirmed"]
    unrelated = "Paralytic without induction agent — awake paralysis risk."
    outcome = gate(c["response"], c["issues"] + [unrelated], c["ctx"])
    assert outcome.override_fired == "pediatric_weight_confirmed"
    assert unrelated in outcome.issues, "the unrelated issue must survive into the log"
    assert outcome.verdict == "NEEDS_HUMAN_REVIEW"


# ── SC-3: the gate log invariant ────────────────────────────────────────────

def test_gate_log_invariant():
    """verdict == "UNSAFE" if and only if blocked. S-2 is the violation of this.

    Driven across the full matrix of deterministic pass/fail x validator verdict
    x override firing/not, so it closes the class rather than the two logged
    instances.
    """
    responses = [_CLINICAL, _CLINICAL + "Perform cricothyrotomy now.\n",
                 S2_IED_PREVIEW, S2_GATE_QUESTION_PREVIEW]
    verdicts = ["SAFE", "NEEDS_HUMAN_REVIEW", "UNSAFE"]
    issue_sets = [[], ["Failed airway described without a definitive surgical airway."],
                  ["Medication dose given without confirmed weight for pediatric patient."]]
    contexts = [None, PatientContext(), PatientContext(confirmed_weight_kg=20.0, is_pediatric=True)]

    checked = 0
    for det in (PASS, FAIL):
        for response in responses:
            for verdict in verdicts:
                for issues in issue_sets:
                    for ctx in contexts:
                        outcome = gate(response, issues, ctx, "", det=det, verdict=verdict)
                        assert (outcome.verdict == "UNSAFE") == outcome.blocked, (
                            f"invariant broken: verdict={outcome.verdict} blocked={outcome.blocked} "
                            f"det_passed={det.passed} llm={verdict} issues={issues}"
                        )
                        if outcome.blocked:
                            assert outcome.issues, "a block must carry its issues"
                        checked += 1
    assert checked == 2 * 4 * 3 * 3 * 3


def test_no_served_response_logs_unsafe():
    """The two real S-2 records: served, so they must never log UNSAFE.

    cdss_session_2026-07-18.jsonl:8  — the IED casualty, issues emptied
    cdss_session_2026-07-18.jsonl:11 — a gate question, issues emptied
    """
    ctx = PatientContext(age_years=6.0, confirmed_weight_kg=34.0, is_pediatric=True)
    issues = ["Medication dose given without confirmed weight for pediatric patient."]

    outcome = gate(S2_IED_PREVIEW, issues, ctx)
    assert outcome.blocked is False
    assert outcome.verdict == "NEEDS_HUMAN_REVIEW"
    assert outcome.issues == issues, "v4.0 returned [] here"
    assert outcome.override_fired == "pediatric_weight_confirmed"

    # The gate question is in SAFE_GATE_RESPONSES-adjacent territory; whichever
    # path it takes, a served response may not be logged UNSAFE.
    outcome = gate(S2_GATE_QUESTION_PREVIEW, issues, ctx)
    assert (outcome.verdict == "UNSAFE") == outcome.blocked


def test_deterministic_block_still_blocks():
    """SC-3 must not soften the deterministic path."""
    outcome = gate(_CLINICAL, [], None, det=FAIL, verdict="SAFE")
    assert outcome.blocked is True
    assert outcome.verdict == "UNSAFE"
    assert outcome.issues == FAIL.issues
    assert "Clinical safety hold" in outcome.response


def test_safe_gate_responses_bypass_unchanged():
    outcome = gate("Need weight in kg before dosing.", ["anything"], None, verdict="UNSAFE")
    assert outcome.blocked is False
    assert outcome.verdict == "SAFE"
    assert outcome.override_fired is None


def test_plain_safe_and_needs_review_paths():
    outcome = gate(_CLINICAL, [], None, verdict="SAFE")
    assert (outcome.verdict, outcome.blocked, outcome.override_fired) == ("SAFE", False, None)

    outcome = gate(_CLINICAL, ["something to review"], None, verdict="NEEDS_HUMAN_REVIEW")
    assert outcome.verdict == "NEEDS_HUMAN_REVIEW"
    assert outcome.blocked is False
    assert outcome.issues == ["something to review"]
    assert "requires human review" in outcome.response


def test_find_fired_override_returns_registry_members():
    for name in OVERRIDE_CASES:
        c = OVERRIDE_CASES[name]
        fired = find_fired_override(c["issues"], c["response"], c.get("ctx"),
                                    c.get("history", ""))
        assert fired in SAFETY_OVERRIDES
