"""
EdgeCDSS — safety gate regression tests (SC-3, SC-6, T-13).

Offline: constructs gate inputs directly. No validator is ever called, so no
test here asserts what verdict the LLM produces — only what the gate does with
a verdict. The validator is non-deterministic (S-8) and pinning it is T-4,
which is out of scope for v4.1.

    cd server && ./run_unit_tests.sh
"""

import os
import re
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai_client import (  # noqa: E402
    CANONICAL_GIVE_RE, SAFETY_OVERRIDES, DeterministicCheck, DoseCandidate,
    PatientContext, apply_safety_gate, find_fired_override,
    run_deterministic_checks,
)
from test_fixtures import (  # noqa: E402
    FIXED_PREP_PUSH_DOSE_EPI, S2_GATE_QUESTION_PREVIEW, S2_IED_PREVIEW,
    S3_GIVE_LINE, S6_POPULATED_CONTRACT_ISSUES, S6_POPULATED_CONTRACT_RESPONSE,
)

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


# ── SC-6: the dose contract must be enforced when the contract is EMPTY ─────
# v4.0 guarded the whole canonical-GIVE parse behind `if allowed_doses:`, so
# "no contract" read as "nothing to check" rather than "nothing authorised".
# That is the S-3 gap: an adult with no confirmed weight, an empty contract,
# and a served 1500mg dose. The pediatric net below it never covered adults.

ADULT_NO_WEIGHT = PatientContext()
ADULT_WITH_WEIGHT = PatientContext(age_years=44.0, confirmed_weight_kg=72.1)
PEDS_NO_WEIGHT = PatientContext(age_years=6.0, is_pediatric=True)

LORAZEPAM_4MG_IV = DoseCandidate(
    drug="lorazepam", indication="status epilepticus", route="IV",
    dose_mg=4.0, volume_ml=2.0, concentration_mg_ml=2.0, source="test",
)


def checks(response, ctx, allowed_doses=None, query="status seizure"):
    return run_deterministic_checks(query, response, ctx, allowed_doses)


def test_empty_contract_blocks_canonical_give_line():
    """S-3, verbatim: cdss_session_2026-07-21.jsonl:2."""
    result = checks(S3_GIVE_LINE, ADULT_NO_WEIGHT, [])
    assert result.passed is False
    joined = " ".join(result.issues)
    assert "levetiracetam" in joined
    assert "1500" in joined
    assert "empty" in joined.lower() and "ALLOWED_DOSES" in joined


def test_empty_contract_blocks_for_adults_specifically():
    """The exact gap S-3 describes — the pediatric net only covered pediatrics.

    Same response, same empty contract, adult context. If the empty-contract
    branch were made pediatric-only this would pass and the gap would reopen.
    """
    adult = checks(S3_GIVE_LINE, ADULT_NO_WEIGHT, [])
    peds = checks(S3_GIVE_LINE, PEDS_NO_WEIGHT, [])
    assert adult.passed is False, "an adult with no contract must be blocked"
    assert peds.passed is False
    assert any("empty" in i.lower() for i in adult.issues), (
        f"adult block must come from the contract check, not another net: {adult.issues}")


def test_empty_contract_passes_none_and_empty_list_alike():
    """allowed_doses=None is 'no contract built', not 'check skipped'."""
    assert checks(S3_GIVE_LINE, ADULT_NO_WEIGHT, None).passed is False


def test_empty_contract_allows_response_without_give_line():
    """Guards against over-blocking: numbers outside a canonical GIVE line."""
    narrative = (
        "**DO THIS**\n1. Protect the airway; suction ready.\n"
        "2. Benzodiazepine per local protocol.\n\n"
        "**WATCH**\n- Recheck glucose; treat below 70 mg/dL.\n"
        "- Seizures beyond 5 minutes are status.\n\n"
        "**DON'T**\n- Do not give 1500mg of anything without a confirmed weight.\n"
    )
    result = checks(narrative, ADULT_NO_WEIGHT, [])
    assert result.passed is True, result.issues


def test_fixed_prep_text_is_not_a_canonical_give_line():
    """07-18.jsonl:40 and :67 — push-dose epi prep must stay unblocked.

    Two independent reasons in production (FIXED_PREP returns at the pre-gate,
    and the text does not match the canonical regex). This pins the second, so
    a future loosening of CANONICAL_GIVE_RE cannot silently start blocking
    preparation recipes.
    """
    assert re.findall(CANONICAL_GIVE_RE, FIXED_PREP_PUSH_DOSE_EPI.lower()) == []
    assert checks(FIXED_PREP_PUSH_DOSE_EPI, ADULT_NO_WEIGHT, [],
                  query="need to make push dose epi").passed is True


def test_populated_contract_behaviour_unchanged():
    """cdss_session_2026-07-19.jsonl:6 — the three real issues, unchanged.

    SC-6 moved this path into an else branch; it must produce byte-identical
    issues.
    """
    result = checks(S6_POPULATED_CONTRACT_RESPONSE, ADULT_WITH_WEIGHT,
                    [LORAZEPAM_4MG_IV],
                    query="159lb male unable to ventilate effectively status post oral trauma")
    assert result.passed is False
    assert sorted(result.issues) == sorted(S6_POPULATED_CONTRACT_ISSUES)


def test_matching_dose_under_a_populated_contract_still_passes():
    """The contract's own value must not be blocked by the new branch."""
    response = "**GIVE**\n- Draw 2 mL of 2mg/mL lorazepam IV (4mg). Indication: status.\n"
    assert checks(response, ADULT_WITH_WEIGHT, [LORAZEPAM_4MG_IV]).passed is True


def test_empty_contract_block_reaches_the_gate_as_a_hard_block():
    """SC-6 issues must block, not downgrade — no SC-3 override may release one.

    The S-3 case is the whole point: a served dose with nothing authorising it.
    """
    det = checks(S3_GIVE_LINE, ADULT_NO_WEIGHT, [])
    outcome = apply_safety_gate(S3_GIVE_LINE, det,
                                {"result": "SAFE", "issues": [], "rationale": ""},
                                ADULT_NO_WEIGHT, "")
    assert outcome.blocked is True
    assert outcome.verdict == "UNSAFE"
    assert outcome.issues == det.issues


# ── The synthesized issue must not feed the override matcher ───────────────
# Found reviewing SC-3 (6c7f535). The gate synthesizes an issue from the
# validator's rationale when handed an UNSAFE with no issues, so the audit log
# is not left blank. That synthetic text was then passed to the override
# matcher — and it is the validator's free-form prose, so a rationale that
# happens to contain an override's keywords could satisfy one and DOWNGRADE the
# block into a served response. v4.0 blocked these: with issues=[], every
# override's matched-issue list was empty and none could fire.
#
# Unreachable through the current call site (validate_response always returns
# SAFE, a normalized result, or NEEDS_HUMAN_REVIEW with a non-empty issue), so
# this is defence-in-depth. It must defend in the right direction.

def unsafe_no_issues(rationale):
    return {"result": "UNSAFE", "issues": [], "rationale": rationale}


def test_empty_issue_unsafe_blocks_even_when_the_rationale_matches_an_override():
    """The exact case: fluids rationale, fluids response, fluids override."""
    response = "**DO THIS**\n1. Start IV fluid resuscitation with crystalloid.\n"
    outcome = apply_safety_gate(
        response, PASS,
        unsafe_no_issues("Recommends aggressive fluid resuscitation without a defined endpoint."),
        PatientContext(), "")
    assert outcome.blocked is True
    assert outcome.verdict == "UNSAFE"
    assert outcome.override_fired is None, "no override may fire on synthesized text"


def test_empty_issue_unsafe_blocks_across_every_override_keyword():
    """Not just fluids. Every registry branch, driven from the registry itself,
    so a tenth override cannot reopen this."""
    for override in SAFETY_OVERRIDES:
        for keyword in override.keywords:
            rationale = f"Concern regarding {keyword} handling in this response."
            response = (_CLINICAL + "Perform cricothyrotomy, decompression, "
                        "ketamine induction, fluid, monitor, antibiotic.\n")
            outcome = apply_safety_gate(response, PASS, unsafe_no_issues(rationale),
                                        PatientContext(confirmed_weight_kg=20.0,
                                                       is_pediatric=True),
                                        "blast injury hemorrhage")
            assert outcome.blocked is True, (
                f"{override.name}/{keyword!r}: synthesized issue released a block")
            assert outcome.override_fired is None


def test_the_synthesized_issue_still_reaches_the_log():
    """Failing closed must not go back to blocking with an empty issue list —
    that is the other half of S-2."""
    outcome = apply_safety_gate(_CLINICAL, PASS,
                                unsafe_no_issues("Dose exceeds the safe ceiling."),
                                PatientContext(), "")
    assert outcome.blocked is True
    assert outcome.issues == ["Validator marked UNSAFE: Dose exceeds the safe ceiling."]


def test_empty_issue_and_empty_rationale_still_blocks_with_a_readable_issue():
    outcome = apply_safety_gate(_CLINICAL, PASS, unsafe_no_issues(""), PatientContext(), "")
    assert outcome.blocked is True
    assert outcome.issues == ["Validator marked unsafe but provided no specific issue."]


def test_real_structured_issues_still_reach_the_overrides():
    """The fix must be scoped to the synthesized case only. A genuine issue list
    must still be able to fire an override — otherwise SC-3 is undone."""
    outcome = gate(_CLINICAL, ["Medication dose given without confirmed weight for pediatric patient."],
                   PatientContext(confirmed_weight_kg=20.0, is_pediatric=True))
    assert outcome.blocked is False
    assert outcome.override_fired == "pediatric_weight_confirmed"
