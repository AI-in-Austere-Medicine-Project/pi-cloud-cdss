"""The replay comparison counts a release by what the medic gets.

Owner, 2026-10-23 (#178 review): "the replay comparison counts a row as newly
released when its before-state was a hold and its after-state serves anything
(card, dose, question), regardless of verdict label."

Found in #178: two live rows went from the safety hold to the which-indication
question and to the signed ketamine analgesia card. The comparison judged the
pipeline replay by verdict label, and SKIPPED_SAFE_GATE (a question) and
DETERMINISTIC_CHECKED (a card) are not "SAFE", so both were counted as still
held and the replay reported 0 newly released.

A pipeline row is a hold when its response is the safety hold
(build_safety_hold); a gate row when the gate blocked it; the served, held and
log replays when the deterministic check returns issues.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import replay_compare as rc  # noqa: E402

ROWS_178 = json.load(open(os.path.join(HERE, "fixtures", "replay_178_rows.json")))
QUESTION = '["Need to give ketamine. 75kg IV established and we have a 500mg/10ml vial", "live"]'
CARD = ('["need to give ketamine for pain i have a 500mg/50ml vial. Iv established '
        'Patient is 75kg", "live"]')


def _sides():
    return ({k: v["before"] for k, v in ROWS_178.items()},
            {k: v["after"] for k, v in ROWS_178.items()})


def test_premise_the_178_rows_are_a_hold_then_a_question_and_a_card():
    assert set(ROWS_178) == {QUESTION, CARD}
    for row in ROWS_178.values():
        assert row["before"]["response"].startswith("Clinical safety hold.")
    assert ROWS_178[QUESTION]["after"]["response"].startswith("Which indication for ketamine")
    assert ROWS_178[CARD]["after"]["response"].startswith("**DO THIS**")
    assert "ketamine IV: 18.75 mg" in ROWS_178[CARD]["after"]["response"]


def test_the_two_178_rows_are_newly_released():
    before, after = _sides()
    r = rc.compare(before, after)
    assert sorted(r["newly_released"]) == sorted([QUESTION, CARD]), r
    assert r["newly_held"] == []


@pytest.mark.parametrize("verdict, source_mode, response", [
    ("SKIPPED_SAFE_GATE", "PRE_GATE", "Need weight in kg before dosing."),
    ("DETERMINISTIC_CHECKED", "DETERMINISTIC_PRE_GATE", "**ACTIVE SEIZURE**\n\n**DO THIS** ..."),
    ("SAFE", "JTS_GROUNDED", "STUB"),
    ("NEEDS_HUMAN_REVIEW", "JTS_GROUNDED", "⚠️ review banner\n\nketamine 20 mg IV"),
    ("SAFE", "VENT_CARD", "**TRAUMATIC BRAIN INJURY**"),
])
def test_a_pipeline_row_that_serves_anything_is_not_a_hold(verdict, source_mode, response):
    row = {"verdict": verdict, "source_mode": source_mode, "boundary": None, "response": response}
    assert rc.is_hold(row) is False


@pytest.mark.parametrize("prefix", ["", "🔄 **Starting a new patient — previous weight, ...**\n\n"])
def test_a_pipeline_row_whose_response_is_the_safety_hold_is_a_hold(prefix):
    import openai_client as oc
    hold = oc.build_safety_hold(["x"], "")
    for verdict in ("UNSAFE", "SAFE", "DETERMINISTIC_CHECKED"):
        row = {"verdict": verdict, "source_mode": "DETERMINISTIC_PRE_GATE",
               "boundary": None, "response": prefix + hold}
        assert rc.is_hold(row) is True, verdict


def test_the_hold_header_is_the_one_build_safety_hold_writes():
    import openai_client as oc
    assert oc.build_safety_hold(["x"], "").startswith(rc.HOLD_HEADER)


def test_a_boundary_reset_alone_is_not_a_hold():
    row = {"verdict": "SAFE", "boundary": "new patient", "response": "🔄 **Starting a new patient**\n\nSTUB"}
    assert rc.is_hold(row) is False


def test_a_hold_to_a_hold_is_not_released_and_a_serve_to_a_hold_is_newly_held():
    hold = {"verdict": "UNSAFE", "boundary": None, "response": rc.HOLD_HEADER + "\n\n- a"}
    hold2 = {"verdict": "UNSAFE", "boundary": None, "response": rc.HOLD_HEADER + "\n\n- b"}
    card = {"verdict": "DETERMINISTIC_CHECKED", "boundary": None, "response": "**DO THIS**"}
    r = rc.compare({"a": hold, "b": card}, {"a": hold2, "b": hold})
    assert r["newly_released"] == [] and r["newly_held"] == ["b"]


@pytest.mark.parametrize("before, after, released", [
    (True, False, True),
    (False, True, False),
])
def test_a_gate_row_is_judged_by_blocked_not_by_the_recorded_issues(before, after, released):
    def row(blocked, verdict):
        return {"verdict": verdict, "blocked": blocked, "validator": "UNSAFE",
                "issues": ["recorded validator issue"], "override": None}
    r = rc.compare({"k": row(before, "UNSAFE" if before else "NEEDS_HUMAN_REVIEW")},
                   {"k": row(after, "UNSAFE" if after else "NEEDS_HUMAN_REVIEW")})
    assert (r["newly_released"] == ["k"]) is released
    assert (r["newly_held"] == ["k"]) is (not released)


def test_a_served_held_or_log_row_is_judged_by_its_issues():
    assert rc.is_hold({"run": "r", "scenario": "s", "model": "m", "issues": ["x"]}) is True
    assert rc.is_hold({"run": "r", "scenario": "s", "model": "m", "issues": []}) is False
    assert rc.is_hold({"source_mode": "JTS_GROUNDED", "issues": []}) is False
