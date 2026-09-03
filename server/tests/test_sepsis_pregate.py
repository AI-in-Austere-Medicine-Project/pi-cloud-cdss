"""
EdgeCDSS — the sepsis pre-gate's entry conditions.

Both failures this file pins come from the 2026-09-03 web-client feedback
review, and both ended at the same card:

  entry 44 — "overdosed on beta blockers. HR 30, BP 50/20" -> the SEPSIS card.
  entry 16 — "6 year old, fever and altered"               -> the SEPSIS card.

Offline: no API key, no network, no ChromaDB.
"""

import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402


# ── has_fever: a number is not a temperature until it has a scale ───────────

@pytest.mark.parametrize("query,expected", [
    # Fahrenheit, bare. The measured entry-16 defect: `\d{2}` captured "98".
    ("temp 98.6", False),
    ("temp 96.8", False),
    # The same defect's other sign: `\d{2}` captured "10" out of "101".
    ("temp 101", True),
    ("temp 100.4", True),           # the threshold itself is a fever
    # Celsius, bare — below the 50 split.
    ("temp 37", False),
    ("temp 38.5", True),
    ("temp 37.9", False),           # just under, on the Celsius scale
    # An explicit unit wins over the magnitude heuristic.
    ("39 C", True),
    ("101 F", True),
    ("99 F", False),
    ("38 C", True),
    # Other phrasings of the label.
    ("temp of 98.6", False),
    ("T 98.6", False),
    ("temperature of 101.5", True),
    ("temp: 39c", True),
    # Negation.
    ("afebrile, temp 98.6", False),
    ("afebrile, temp 101", False),
    ("no fever, temp 39", False),
    # Text terms still work, and "afebrile" no longer reads as "febrile".
    ("patient is febrile", True),
    ("patient is afebrile", False),
    ("fever and pus from the wound", True),
    ("no fever", False),
])
def test_has_fever_reads_the_scale(query, expected):
    assert oc.has_fever(query) is expected, query


def test_a_temperature_beside_an_unrelated_negative_is_still_a_fever():
    """The fever negation window is fever-specific on purpose: the general
    window contains "no ", and "no chest pain, temp 101" is a febrile
    patient."""
    assert oc.has_fever("no chest pain, no vomiting, temp 101") is True


@pytest.mark.parametrize("query", [
    "give 100 mcg fentanyl",        # "100 mc" is not 100 C
    "20 fr chest tube",             # "20 f" is not 20 F
    "wound is 10 cm across",
    "patient is 98 kg",             # no label, no unit, no temperature
    "peaked T waves, K is 6.8",     # a bare "t" that is not a temperature
    "hr 30 bp 50/20 spo2 91%",      # entry 44's vitals carry no temperature
])
def test_numbers_that_are_not_temperatures(query):
    assert oc.has_fever(query) is False, query
