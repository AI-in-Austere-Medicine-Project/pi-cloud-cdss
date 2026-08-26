"""
EdgeCDSS — patient-boundary regression tests (SC-1).

S-1 is the most serious finding in the v4.1 audit: a 6-year-old's 34 kg was
carried into an adult IED casualty and a dose was served against it. These
tests are the thing that must fail if that ever becomes possible again.

The failure mode is asymmetric in BOTH directions, so the negative tests matter
as much as the positive ones: a missed boundary doses the wrong patient, and a
false boundary destroys a confirmed weight mid-resuscitation.

    cd server && ./run_unit_tests.sh
"""

import datetime
import os
import pathlib
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_client import (  # noqa: E402
    PatientContext, detect_patient_boundary,
    rebuild_patient_context_from_history,
)
from test_fixtures import (  # noqa: E402
    S1_BOUNDARY_LINES, S1_CONTINUATION_LINES, S1_SEQUENCE,
)


def ctx_of(ctx):
    """The three facts S-1 is about."""
    return (ctx.confirmed_weight_kg, ctx.age_years, ctx.is_pediatric)


# The oracle from PLAN_v4.1.md §2 SC-1, keyed by log line in
# data/sessions/cdss_session_2026-07-18.jsonl.
S1_ORACLE = {
    3:  (None, 6.0, True),    # 'I need to intubate a 6 year old'
    4:  (34.0, 6.0, True),    # '34kg'
    5:  (34.0, 6.0, True),    # continuation
    6:  (34.0, 6.0, True),    # continuation
    7:  (34.0, 6.0, True),    # continuation
    8:  (None, None, False),  # NEW PATIENT — the IED marine. No inherited 34kg.
    9:  (None, None, False),  # continuation of the marine
    10: (None, 7.0, True),    # NEW PATIENT — 7 year old; age from this turn only
    11: (None, 7.0, True),    # continuation
    12: (17.0, 7.0, True),    # continuation; weight supplied
    13: (None, None, False),  # 'new session'
    14: (None, None, False),  # NEW PATIENT — pregnant casualty. No inherited 17kg.
}


def test_s1_sticky_weight_scenario():
    """The headline test. Replays the 12 turns of S-1 in order.

    cdss_session_2026-07-18.jsonl lines 3-14, queries verbatim.
    """
    history = []
    for line_no, query in S1_SEQUENCE:
        ctx = rebuild_patient_context_from_history(query, conversation_history=list(history))
        assert ctx_of(ctx) == S1_ORACLE[line_no], (
            f"L{line_no} {query!r}: expected {S1_ORACLE[line_no]}, got {ctx_of(ctx)}")
        history.append({"query": query, "response": ""})


def test_no_inherited_weight_at_the_two_named_turns():
    """PLAN_v4.1.md §6: 'no inherited weight at log lines 8 and 14'.

    Stated separately from the full oracle so the definition-of-done line has a
    test with its own name.
    """
    history = []
    for line_no, query in S1_SEQUENCE:
        ctx = rebuild_patient_context_from_history(query, conversation_history=list(history))
        if line_no in (8, 14):
            assert ctx.confirmed_weight_kg is None, (
                f"L{line_no} inherited {ctx.confirmed_weight_kg}kg from a previous patient")
            assert ctx.is_pediatric is False, f"L{line_no} inherited a pediatric flag"
        history.append({"query": query, "response": ""})


def test_boundary_reset_survives_full_replay():
    """The (b) failure mode: a reset applied to the current turn only.

    The server is stateless and rebuilds context from the whole history on every
    request. If the reset lives outside the replay loop, turn 12's rebuild walks
    turns 1-11 again with no boundary and the 34 kg comes back. That bug passes
    test_s1_sticky_weight_scenario and fails here.
    """
    full_history = [{"query": q, "response": ""} for _, q in S1_SEQUENCE[:-1]]
    last_line, last_query = S1_SEQUENCE[-1]
    ctx = rebuild_patient_context_from_history(last_query, conversation_history=full_history)
    assert ctx_of(ctx) == S1_ORACLE[last_line]
    assert ctx.confirmed_weight_kg is None

    # Every boundary line, rebuilt from scratch against the history preceding it.
    for idx, (line_no, query) in enumerate(S1_SEQUENCE):
        prior = [{"query": q, "response": ""} for _, q in S1_SEQUENCE[:idx]]
        ctx = rebuild_patient_context_from_history(query, conversation_history=prior)
        assert ctx_of(ctx) == S1_ORACLE[line_no], f"L{line_no} on full rebuild"


def test_boundary_lines_reset_and_continuations_do_not():
    """The fixture's own classification, asserted against the detector."""
    history = []
    for line_no, query in S1_SEQUENCE:
        ctx_before = rebuild_patient_context_from_history(
            history[-1]["query"] if history else "", conversation_history=history[:-1] or None
        ) if history else PatientContext()
        fired = bool(detect_patient_boundary(query, ctx_before))
        if line_no in S1_BOUNDARY_LINES:
            assert fired, f"L{line_no} {query!r} must reset"
        if line_no in S1_CONTINUATION_LINES:
            assert not fired, f"L{line_no} {query!r} must NOT reset"
        history.append({"query": query, "response": ""})


# ── Negative cases — the direction that destroys a confirmed weight ─────────

POPULATED = PatientContext(age_years=34.0, confirmed_weight_kg=80.0)


def test_continuation_turns_never_reset():
    """Turns that carry no contradicting fact must never reset, whatever the
    context holds."""
    for query in ("IV", "IM", "TBI mgmt", "now what", "burn care",
                  "tbi mgmt on vent", "what about the airway", "next steps",
                  "give the versed", "vent settings"):
        assert detect_patient_boundary(query, POPULATED) is None, query


def test_restating_the_known_age_does_not_reset():
    """S-1 L11: 'he is a normal weight for a 7 year old' follows a turn that
    established age 7. Restating it is a continuation, not a new patient."""
    assert detect_patient_boundary("he is a normal weight for a 7 year old",
                                   PatientContext(age_years=7.0, is_pediatric=True)) is None


def test_bare_weight_after_a_reset_is_not_a_contradiction():
    """S-1 L12: '17 kg' arrives with no weight on file (L10 cleared it), so it
    is this patient's first weight, not a contradiction."""
    assert detect_patient_boundary("17 kg", PatientContext(age_years=7.0)) is None


def test_a_weight_correction_resets_and_that_is_the_accepted_trade():
    """DELIBERATE, and the sharpest edge of SC-1. PLAN_v4.1.md §5.1.

    A medic correcting a weight on the SAME patient ("actually he's 90kg")
    trips the weight-contradiction trigger and clears the context. The trigger
    cannot distinguish a correction from a new patient — both are "the weight I
    have is not the weight you just said".

    This is accepted because of option (c): the reset is announced in the
    response, so the medic sees it and restates. The alternative — trusting the
    older weight — is S-1. If this fires in the field often enough to matter,
    the fix is a correction phrase list ("actually", "sorry, make that"), not
    dropping the trigger.
    """
    assert detect_patient_boundary("actually he is 90kg", POPULATED) == "weight_contradiction"


def test_confirmed_weight_survives_continuations():
    """The asymmetric failure: a false reset mid-resuscitation."""
    history = [{"query": "80kg male, blast injury, IV access", "response": ""}]
    for query in ("TBI mgmt", "now what", "what about TXA", "vent settings"):
        ctx = rebuild_patient_context_from_history(query, conversation_history=list(history))
        assert ctx.confirmed_weight_kg == 80.0, f"{query!r} destroyed the weight"
        history.append({"query": query, "response": ""})


def test_clinical_prose_does_not_fire():
    """Near-misses. Widening the trigger to a bare 'have' fails this."""
    for query in ("patient has a fever", "have a look at this", "if you have a tourniquet",
                  "I have a question about TXA", "does he have a pulse",
                  "have a second to check the airway", "the patient has an open fracture",
                  "we have a protocol for this", "have a quick question"):
        assert detect_patient_boundary(query, POPULATED) is None, query


def test_new_patient_phrases_fire():
    for query in ("new patient", "new session", "next patient", "another patient",
                  "new casualty", "different patient",
                  "have a marine that was hit by an IED - he is bleeding out",
                  "got a kid with a burn", "Have a 75-year-old male fall on blood thinners"):
        assert detect_patient_boundary(query, POPULATED) is not None, query


# ── Contradiction triggers ─────────────────────────────────────────────────

def test_age_contradiction_resets():
    assert detect_patient_boundary("45 year old chest pain",
                                   PatientContext(age_years=6.0)) == "age_contradiction"


def test_age_restatement_does_not_reset():
    assert detect_patient_boundary("the 6 yo needs a dose",
                                   PatientContext(age_years=6.0)) is None


def test_weight_contradiction_resets():
    assert detect_patient_boundary("80 kg", PatientContext(confirmed_weight_kg=34.0)) \
        == "weight_contradiction"


def test_weight_restatement_within_tolerance_does_not_reset():
    """34kg then '34 kg' is a restatement. Rounding must not reset a patient."""
    for query in ("34 kg", "34.0 kg", "he is 35kg"):
        assert detect_patient_boundary(query, PatientContext(confirmed_weight_kg=34.0)) is None, query


def test_first_weight_is_not_a_contradiction():
    """'34kg' after 'I need to intubate a 6 year old' must NOT reset — S-1 L4."""
    assert detect_patient_boundary("34kg", PatientContext(age_years=6.0)) is None


# ── Inactivity (trigger 4) ─────────────────────────────────────────────────

def ts(minutes):
    base = datetime.datetime(2026, 8, 11, 7, 0, 0, tzinfo=datetime.timezone.utc)
    return (base + datetime.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def test_inactivity_timeout_resets():
    assert detect_patient_boundary("TBI mgmt", POPULATED, prev_ts=ts(0), now_ts=ts(31)) \
        == "inactivity_timeout"


def test_activity_within_the_window_does_not_reset():
    assert detect_patient_boundary("TBI mgmt", POPULATED, prev_ts=ts(0), now_ts=ts(29)) is None


def test_missing_timestamps_never_reset():
    """Pre-v4.1 clients send no ts. Unknown must not read as 'a long gap'."""
    for prev, now in ((None, None), (ts(0), None), (None, ts(99)), ("garbage", ts(99))):
        assert detect_patient_boundary("TBI mgmt", POPULATED, prev_ts=prev, now_ts=now) is None


def test_naive_timestamps_do_not_raise():
    """A client sending a naive ISO string must not take the request down."""
    naive = "2026-08-11T07:00:00"
    assert detect_patient_boundary("TBI mgmt", POPULATED, prev_ts=naive, now_ts=ts(31)) \
        == "inactivity_timeout"


def test_inactivity_applies_inside_the_replay():
    history = [
        {"query": "80kg male, blast injury", "response": "", "ts": ts(0)},
        {"query": "TBI mgmt", "response": "", "ts": ts(2)},
    ]
    ctx = rebuild_patient_context_from_history("what about TXA", conversation_history=history,
                                               now_ts=ts(45))
    assert ctx.confirmed_weight_kg is None
    assert ctx.boundary_reset_reason == "inactivity_timeout"


# ── The visible notice (PLAN §5.1 option c) ────────────────────────────────

def test_reset_reason_is_reported_for_the_current_turn_only():
    history = [{"query": "have a marine hit by an IED", "response": ""},
               {"query": "80kg", "response": ""}]
    ctx = rebuild_patient_context_from_history("TXA dose", conversation_history=history)
    assert ctx.boundary_reset_reason is None, "an earlier boundary must not flag this turn"
    assert ctx.confirmed_weight_kg == 80.0

    ctx = rebuild_patient_context_from_history("new patient", conversation_history=history)
    assert ctx.boundary_reset_reason == "explicit:new patient"


def test_notice_text_names_what_was_cleared():
    from openai_client import BOUNDARY_RESET_NOTICE
    lowered = BOUNDARY_RESET_NOTICE.lower()
    assert "new patient" in lowered
    assert "weight" in lowered, "the medic must be told the weight is gone"


# ── The client half (SC-1 part c) ──────────────────────────────────────────

def client_source():
    return (pathlib.Path(__file__).parent.parent / "static" / "index.html").read_text()


def test_client_new_patient_button_exists():
    """The only thing standing between v4.1 and v2.5's claim of a button that
    was not there. See the CHANGELOG correction under [4.1.0]."""
    src = client_source()
    assert 'id="newpatient"' in src
    assert "function newPatient" in src
    assert "getElementById('newpatient').onclick" in src


def test_client_new_patient_clears_the_replayed_history():
    """Clearing the transcript without clearing `history` would leave the server
    replaying the previous patient — the button would look like it worked."""
    src = client_source()
    body = src[src.index("function newPatient"):]
    body = body[:body.index("\n}")]
    assert "history.length = 0" in body


def test_client_sends_timestamps():
    assert "ts: new Date().toISOString()" in client_source()
