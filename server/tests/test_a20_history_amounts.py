"""A20 (owner, 2026-10-03): an amount the patient already took or was given is
history, not a dose to give.

The free-text dose check could not tell the two apart. In the A18 replay,
"He took calcium channel blocker 240 mg this morning." held as a dose with no
drug named. The owner accepted that hold for A18 (it fails safe) and filed the
general case.

The owner's rule: A9's benzo-given detector is the pattern. A history cue
(took, taken, already given, got, received, ingested, overdosed on, home
dose, ...) within a short window of the amount, in the same clause, marks it
as history. Never loosen a gate: a history amount that is also an instruction
("already given 1 g, give 1 g more") still checks the instruction.
"""
import pytest

import openai_client as oc

ADULT_NO_WEIGHT = oc.PatientContext()
TXA_QUERY = "hx: DVT + thrombosis. TXA still ok in his case?"


def _issues(text, query=None):
    return oc.free_text_dose_issues(text, [], ADULT_NO_WEIGHT, query)


def test_the_calcium_channel_blocker_history_is_not_a_dose():
    # The A18 replay's sentence, verbatim.
    text = "**TREAT**\n- He took calcium channel blocker 240 mg this morning."
    assert _issues(text) == []


@pytest.mark.parametrize("text", [
    "She already received midazolam 10 mg before we arrived.",
    "Took 240 mg of verapamil at 0800.",
    "His home dose is metoprolol 50 mg.",
    "Ingested about 30 g of acetaminophen.",
    "He overdosed on 20 mg of amlodipine.",
    "240 mg verapamil taken this morning.",
    "Got 2 mg of lorazepam from EMS.",
])
def test_an_amount_already_taken_or_given_is_history(text):
    assert _issues(text) == []


@pytest.mark.parametrize("text", [
    # The teacher's line from the A18 replay, verbatim. Its instruction clause
    # ("give 1 g more, not 2 g") is skipped as a limit, so the history clause
    # is the only thing holding the row: it must keep holding.
    "If 1 g already given and <3 hours from injury: give 1 g more, not 2 g.",
    "Already given 1 g, give 1 g more.",
    "Give 1 g if he hasn't already taken it.",
    "Give 1 g unless it was already given.",
])
def test_a_history_amount_beside_an_instruction_still_holds(text):
    issues = _issues(text, TXA_QUERY)
    assert any("tranexamic acid 1 g" in i for i in issues), issues


def test_a_named_drug_given_and_repeated_still_holds():
    issues = _issues("She received midazolam 5 mg, give midazolam 5 mg more.")
    assert any("midazolam 5 mg" in i for i in issues), issues


def test_a_cue_that_is_negated_is_not_history():
    # "hasn't", not "has not": a clause with "not" is skipped as a limit.
    issues = _issues("He hasn't taken his verapamil 240 mg today.")
    assert any("verapamil 240 mg" in i for i in issues), issues
