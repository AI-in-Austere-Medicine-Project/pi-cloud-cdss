"""The replay comparison's third count: newly doses.

Owner, 2026-10-24 (#179 review): "Add a third count, 'newly doses': any row
whose after-state serves a dose that its before-state did not (question ->
dose, no-dose card -> dose, hold -> dose). Listed by row like the others; my
sign-off required."

Found in the #170-#178 re-run (#179): "versed dose IM" (#174) went from the
which-indication question to the generator with midazolam doses offered, and
the push-dose card for "push dose epi, BP 70/40 shocky" (#177) went from "No
signed entry for shock" to E05's 5-20 mcg. Both are serve-to-serve, so neither
newly held nor newly released counted them.

A pipeline row doses when its response states a dose (a number with a mass or
unit: mg, mcg, g, units, mEq, mmol, including rates), with concentration
phrases (50 mg/mL, 500 mg / 10 mL) removed, or when it reached the stubbed
generator with doses offered. A hold never doses. The served, held and gate
replays read the answer text in the row key; the log replay has no text, so a
log row that serves is counted as dosing (it can only newly dose by being
released).

    cd server && ./run_unit_tests.sh
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import replay_compare as rc  # noqa: E402

ROWS = json.load(open(os.path.join(HERE, "fixtures", "replay_newly_doses_rows.json")))
ROWS_178 = json.load(open(os.path.join(HERE, "fixtures", "replay_178_rows.json")))
VERSED = '["versed dose IM", "run"]'
E05 = '["push dose epi, BP 70/40 shocky", "live"]'
Q178 = '["Need to give ketamine. 75kg IV established and we have a 500mg/10ml vial", "live"]'
CARD178 = ('["need to give ketamine for pain i have a 500mg/50ml vial. Iv established '
           'Patient is 75kg", "live"]')


def _cmp(rows):
    return rc.compare({k: v["before"] for k, v in rows.items()},
                      {k: v["after"] for k, v in rows.items()})


def test_premise_question_then_generator_and_no_dose_card_then_e05():
    v, e = ROWS[VERSED], ROWS[E05]
    assert v["before"]["response"].startswith("Which indication for midazolam")
    assert v["after"]["response"] == "STUB" and v["after"]["allowed"]
    assert "No signed entry for shock" in e["before"]["response"]
    assert "epinephrine IV: 5-20 mcg" in e["after"]["response"]


def test_versed_im_and_the_e05_shock_card_newly_dose():
    r = _cmp(ROWS)
    assert sorted(r["newly_doses"]) == sorted([VERSED, E05]), r
    assert r["newly_released"] == [] and r["newly_held"] == []


def test_hold_to_dose_newly_doses_and_hold_to_question_does_not():
    r = _cmp(ROWS_178)
    assert r["newly_doses"] == [CARD178], r
    assert sorted(r["newly_released"]) == sorted([Q178, CARD178])


@pytest.mark.parametrize("response", [
    "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?",
    "Which indication for ketamine — agitation, RSI, sedation (already intubated), seizure or pain?",
    "Need weight in kg before dosing.",
    "Pain severity? Choose one; it selects the dose: mild (1-3), moderate (4-6), severe (7-10).",
    "**LUNG-PROTECTIVE BASELINE**\n- VT 6 mL/kg ideal body weight\n- PEEP 5",
])
def test_a_question_or_a_card_with_no_dose_does_not_dose(response):
    row = {"verdict": "SKIPPED_SAFE_GATE", "source_mode": "PRE_GATE", "boundary": None,
           "allowed": [["ketamine", "RSI induction", 150.0]], "response": response}
    assert rc.is_dosing(row) is False


def test_the_old_push_dose_recipe_card_does_not_dose():
    assert rc.is_dosing(ROWS[E05]["before"]) is False


@pytest.mark.parametrize("response", [
    "**GIVE**\n- epinephrine IV: 5-20 mcg. Indication: ...",
    "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg).",
    "- epinephrine IV: 0.05-0.3 mcg/kg/min.",
    "- 3% NaCl 7.5 g (= 250 mL)",
    "- TXA 2 g IV",
])
def test_a_stated_dose_doses(response):
    row = {"verdict": "DETERMINISTIC_CHECKED", "boundary": None, "allowed": None, "response": response}
    assert rc.is_dosing(row) is True


def test_the_generator_doses_only_when_doses_were_offered():
    base = {"verdict": "SAFE", "source_mode": "JTS_GROUNDED", "boundary": None, "response": "STUB"}
    assert rc.is_dosing({**base, "allowed": [["midazolam", "procedural sedation", 1.0]]}) is True
    assert rc.is_dosing({**base, "allowed": []}) is False
    assert rc.is_dosing({**base, "response": "🔄 **Starting a new patient**\n\nSTUB",
                         "allowed": [["midazolam", "procedural sedation", 1.0]]}) is True


def test_a_hold_never_doses():
    row = {"verdict": "UNSAFE", "boundary": None, "allowed": [["ketamine", "x", 1.0]],
           "response": rc.HOLD_HEADER + "\n\n- Provider requested ketamine 500mg"}
    assert rc.is_dosing(row) is False


def test_dose_to_dose_and_dose_to_question_are_not_newly_dosing():
    dose = {"verdict": "DETERMINISTIC_CHECKED", "boundary": None, "response": "- ketamine IV: 20 mg"}
    dose2 = {"verdict": "DETERMINISTIC_CHECKED", "boundary": None, "response": "- ketamine IV: 40 mg"}
    q = {"verdict": "SKIPPED_SAFE_GATE", "boundary": None, "response": "IV or IM? Do you have access?"}
    r = rc.compare({"a": dose, "b": dose}, {"a": dose2, "b": q})
    assert r["newly_doses"] == []


def test_a_released_model_answer_newly_doses_when_its_text_states_a_dose():
    key_dose = json.dumps(["S", "q", "Give ketamine 20 mg IV."])
    key_none = json.dumps(["S", "q", "Apply direct pressure."])
    held = {"run": "r", "scenario": "S", "model": "m", "issues": ["x"]}
    served = {"run": "r", "scenario": "S", "model": "m", "issues": []}
    r = rc.compare({key_dose: held, key_none: held}, {key_dose: served, key_none: served})
    assert r["newly_doses"] == [key_dose]
    assert sorted(r["newly_released"]) == sorted([key_dose, key_none])


def test_a_released_log_row_counts_as_newly_dosing():
    key = "cdss_session_2026-10-01.jsonl:3:response"
    r = rc.compare({key: {"source_mode": "JTS_GROUNDED", "issues": ["x"]}},
                   {key: {"source_mode": "JTS_GROUNDED", "issues": []}})
    assert r["newly_doses"] == [key]


def test_the_report_lists_newly_doses_by_row(tmp_path, capsys):
    for side in ("before", "after"):
        json.dump({k: v[side] for k, v in ROWS.items()}, open(tmp_path / f"pipe_{side}.json", "w"))
    rc.main([str(tmp_path), "--before", "before", "--after", "after"])
    out = capsys.readouterr().out
    assert "newly doses 2" in out
    assert f"[newly_doses] {VERSED}" in out and f"[newly_doses] {E05}" in out
