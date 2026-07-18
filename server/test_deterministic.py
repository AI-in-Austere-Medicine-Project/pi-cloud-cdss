"""
EdgeCDSS — deterministic-layer unit tests.
Runs offline (no API calls, no server). Regression-pins parser fixes.

    cd server && ../.venv/bin/python3 -m pytest test_deterministic.py -q
    (or: ../.venv/bin/python3 test_deterministic.py)
"""

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openai_client import (  # noqa: E402
    extract_patient_context, wants_medication_dose, _has_word,
)


# ── Fix 2026-07-18: word-boundary matching for short tokens ──────────────────

def test_kidney_is_not_pediatric():
    ctx = extract_patient_context("55 year old male with kidney stone pain")
    # 'kidney' must not trip the 'kid' pediatric term (age keeps him adult)
    assert ctx.is_pediatric is False

def test_girlfriend_boyfriend_not_pediatric():
    assert extract_patient_context("my girlfriend has severe wrist pain, 70kg").is_pediatric is False
    assert extract_patient_context("boyfriend fell off a ladder, 90kg").is_pediatric is False

def test_real_pediatric_terms_still_fire():
    assert extract_patient_context("6 year old boy 20kg burn").is_pediatric is True
    assert extract_patient_context("need RSI doses for a kid").is_pediatric is True
    assert extract_patient_context("toddler ingestion").is_pediatric is True

def test_rock_is_not_rocuronium():
    assert _has_word("a rock fell on his leg", "roc") is False
    assert _has_word("give roc now", "roc") is True
    assert _has_word("procedure planned", "roc") is False

def test_epidural_is_not_epi():
    assert _has_word("concern for epidural hematoma", "epi") is False
    assert _has_word("push dose epi please", "epi") is True

def test_wants_dose_word_boundaries():
    assert wants_medication_dose("a rock fell on his leg, splint advice") is False
    assert wants_medication_dose("give roc 1.2mg/kg") is True
    assert wants_medication_dose("ketamine for pain") is True


def test_adult_age_is_authoritative():
    # "55 year old" must not be pediatric-gated by the phrase "year old"
    assert extract_patient_context("55 year old male with kidney stone pain").is_pediatric is False
    assert extract_patient_context("45 year old with a fracture 80kg").is_pediatric is False

def test_child_age_still_authoritative():
    assert extract_patient_context("6 year old with a burn").is_pediatric is True
    assert extract_patient_context("15 yo with wrist fx").is_pediatric is True

def test_low_weight_without_age_is_pediatric():
    assert extract_patient_context("patient 20kg needs analgesia").is_pediatric is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError:
                print(f"FAIL {name}")
                fails += 1
    sys.exit(1 if fails else 0)
