"""
EdgeCDSS — A7: the GCS parser.

Work order A7: the GCS parser reads "GCS is seven", "GCS 3T", "GCS of 6" and
"G6", with a test for each; the #95 review added "E4V5M6".

On main there were two GCS readers and they disagreed:
  * vitals.parse_vitals (the recorded vital: the patient block, the caution
    table) read "GCS of 6" but not "GCS is seven", "GCS 3T" or "11T";
  * openai_client._GCS_RE (the severe-TBI card, A4's oral-route hold) read
    those but not "G6" or a component score without separators.
Neither read "G6", "E4V5M6" or "E2 V1 M4". So a "G6" head injury did not get
the severe-TBI card, and a "G6" patient did not arm A4's oral-route hold.

One parser now, in vitals.py, and every reader goes through it.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import vitals as v  # noqa: E402


def _vital(text):
    readings, _ = v.parse_vitals(text.lower(), ts=None)
    return readings["gcs"].value if "gcs" in readings else None


# ── Each form A7 names, and its neighbours ─────────────────────────────────

FORMS = [
    ("GCS is seven", 7),
    ("GCS 3T", 3),
    ("GCS of 6", 6),
    ("G6", 6),
    ("E4V5M6", 15),
    # neighbours
    ("GCS seven", 7),
    ("gcs 8t", 8),
    ("GCS 11T", 11),
    ("G15", 15),
    ("GCS E4V5M6", 15),
    ("E2 V1 M4", 7),
    ("e3 v4 m5", 12),
    ("GCS was twelve", 12),
    # already read on main, and must stay
    ("GCS 15", 15),
    ("GCS: 7", 7),
    ("GCS 3-4-5", 12),
    ("GCS 10 (E3V2M5)", 10),
]


@pytest.mark.parametrize("text,total", FORMS)
def test_the_vital_is_recorded(text, total):
    assert _vital(text) == total, text


@pytest.mark.parametrize("text,total", FORMS)
def test_every_reader_gets_the_same_number(text, total):
    """_stated_gcs is what the severe-TBI card reads."""
    assert oc._stated_gcs(text) == total, text


@pytest.mark.parametrize("text,total", FORMS)
def test_the_patient_context_records_it(text, total):
    ctx = oc.extract_patient_context("fall from a vehicle, " + text)
    assert ctx.vitals["gcs"].value == total, text


# ── What each reading drives ────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["head injury, G6", "head injury, E2V1M4",
                                  "head injury, GCS 3T", "head injury, GCS is seven"])
def test_a_severe_tbi_is_seen_in_every_form(text):
    assert oc.looks_like_severe_tbi(text), text


@pytest.mark.parametrize("text", ["head injury, E4V5M6", "head injury, G15"])
def test_a_gcs_of_15_is_not_a_severe_tbi(text):
    assert not oc.looks_like_severe_tbi(text), text


@pytest.mark.parametrize("text", ["G6", "E2V1M4", "E3 V4 M5", "GCS 11T"])
def test_a_depressed_gcs_arms_the_oral_route_hold_in_every_form(text):
    assert oc.has_ams_descriptor(text), text


@pytest.mark.parametrize("text", ["G15", "E4V5M6", "E4 V5 M6"])
def test_a_gcs_of_15_does_not_arm_it(text):
    assert not oc.has_ams_descriptor(text), text


def test_an_intubated_verbal_score_fails_closed():
    """E3 VT M5: the verbal score is not a number. No total is recorded, and
    the oral-route hold is armed, as for any GCS the parser cannot read."""
    assert _vital("E3 VT M5") is None
    assert oc.has_ams_descriptor("E3 VT M5")


# ── Words that only look like a GCS ─────────────────────────────────────────

NOT_A_GCS = [
    "G6PD deficiency, needs primaquine",
    "G2P1 at 32 weeks",
    "14G IV in the left AC",
    "18g needle decompression",
    "no 5G signal out here",
    "V5 lead shows ST elevation",
    # Added with the fix: "G3" is gravida 3 in an obstetric history.
    "G3 at 30 weeks, abdominal pain",
    "she is pregnant, G4 P3",
]


@pytest.mark.parametrize("text", NOT_A_GCS)
def test_a_look_alike_is_not_a_gcs(text):
    assert _vital(text) is None, text
    assert oc._stated_gcs(text) is None, text
    assert not oc.has_ams_descriptor(text), text
