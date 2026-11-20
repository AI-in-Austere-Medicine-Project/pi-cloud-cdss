"""Scope rulings PR 0 (owner, 2026-11-20): the dose-trace check, report only.

Every dose number a served answer states must come from code's own rendering
of the signed entries offered for that question (the GIVE line of each dose
candidate, the range line of each rate). A number with a dose unit that is not
there is "untraced". Vital-sign and lab units are not dose units.
"""
import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import openai_client as oc  # noqa: E402
from dose_trace import dose_numbers, untraced  # noqa: E402

KET = oc.DoseCandidate(drug="ketamine", indication="analgesia", route="IM", dose_mg=25,
                       source="test", volume_ml=0.5, concentration_mg_ml=50)


def test_dose_numbers_are_read_with_their_units():
    text = "Draw 0.5 mL of 50mg/mL ketamine IM (25 mg). Then 1.5 g, 100 mcg, 2 units, 5 mEq."
    assert dose_numbers(text) == [("0.5", "ml"), ("50", "mg/ml"), ("25", "mg"),
                                  ("1.5", "g"), ("100", "mcg"), ("2", "units"), ("5", "meq")]


def test_vital_and_lab_units_are_not_doses():
    assert dose_numbers("BP 78/44 mmHg, glucose 70 mg/dL, 70 kg, PEEP 5 cmH2O, SpO2 94%") == []


def test_the_code_rendered_line_traces():
    assert untraced(oc.render_give_line(KET), [KET], []) == []


def test_a_number_not_offered_is_untraced():
    assert untraced("Give ketamine 62.5 mg IM.", [KET], []) == [("62.5", "mg")]


def test_with_nothing_offered_every_dose_number_is_untraced():
    assert untraced("Give 2 g ceftriaxone.", [], []) == [("2", "g")]


def test_an_answer_with_no_dose_numbers_traces():
    assert untraced("Splint the arm. Reassess distal pulses.", [], []) == []
