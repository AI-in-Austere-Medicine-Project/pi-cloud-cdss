"""
EdgeCDSS — A11: the free-text dose check reads infusion rates.

Found in #97; owner, #97 review: the free-text dose check must read rates
(mcg/min, mcg/kg/min, mg/hr, mL/hr, units/hr) and compare them to signed rate
entries the same way it does single doses; a rate for a drug with no signed
rate entry holds. On main "Start epinephrine 5 mcg/min" to an adult with no
signed rate built was served with no hold: the amount pattern skips any unit
followed by "/" or "per", so no rate was ever read.

Signed rate entries today (all per kg): epinephrine (symptomatic bradycardia
0.02-0.2, shock 0.05-0.3 mcg/kg/min) and norepinephrine (0.05-0.5, 0.02-0.4,
0.02-2.0 mcg/kg/min, one paediatric 0.05-0.5). A stated per-kg rate inside a
signed range for the drug and the patient's population passes; a flat rate
("5 mcg/min", "10 mL/hr") has no signed flat rate to match, and holds.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

ADULT = oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
CHILD = oc.PatientContext(confirmed_weight_kg=20.0, weight_source="stated",
                          is_pediatric=True, age_years=6.0)


def _rate_issues(text, ctx=ADULT):
    return [i for i in oc.free_text_dose_issues(text, [], ctx) if "rate" in i.lower()]


# ── Holds ───────────────────────────────────────────────────────────────────

HOLD = [
    # the #97 case: a flat rate, no signed flat rate exists
    "**GIVE**\n- Start epinephrine 5 mcg/min IV.",
    "**GIVE**\n- Epinephrine infusion at 2 micrograms per minute.",
    # a ketamine drip: no signed ketamine rate
    "**GIVE**\n- Ketamine infusion at 1 mg/kg/hr.",
    "**GIVE**\n- Run the ketamine drip at 10 mL/hr.",
    # a signed drug, a per-kg rate outside every signed range
    "**GIVE**\n- Epinephrine infusion 1 mcg/kg/min.",
    # a drug with no signed rate at all
    "**GIVE**\n- Insulin 0.1 units/kg/hr.",
    "**GIVE**\n- Fentanyl drip 50 mcg/hr.",
]


@pytest.mark.parametrize("text", HOLD)
def test_an_unsigned_rate_holds(text):
    assert _rate_issues(text), text


def test_the_hold_names_the_drug_and_rate_and_no_signed_number():
    issue = _rate_issues("**GIVE**\n- Start epinephrine 5 mcg/min IV.")[0]
    assert "epinephrine" in issue and "5 mcg/min" in issue, issue
    assert "infusion rate" in issue, issue
    for signed in ("0.02", "0.05", "0.2", "0.3"):
        assert signed not in issue, issue


# ── Passes: a signed rate ───────────────────────────────────────────────────

PASS = [
    ("**GIVE**\n- Epinephrine infusion 0.05 mcg/kg/min, titrate to MAP 65.", ADULT),
    ("**GIVE**\n- Epinephrine infusion at 0.1 mcg/kg/min.", ADULT),
    ("**GIVE**\n- Norepinephrine 0.1 mcg/kg/min IV.", ADULT),
    ("**GIVE**\n- Norepinephrine 0.1 mcg/kg/min IV.", CHILD),
]


@pytest.mark.parametrize("text,ctx", PASS)
def test_a_signed_rate_passes(text, ctx):
    assert _rate_issues(text, ctx) == [], text


# ── Not a drug rate: untouched ──────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "**GIVE**\n- Lactated Ringer's at 500 mL/hr.",
    "**WATCH**\n- Heart rate above 120 per minute.",
    "**DON'T**\n- Don't run epinephrine faster than 0.3 mcg/kg/min.",
    "**GIVE**\n- Epinephrine: titrate up to 0.3 mcg/kg/min.",
])
def test_not_a_stated_drug_rate(text):
    assert _rate_issues(text) == [], text


def test_single_doses_are_read_as_before():
    """A rate is not also read as a bolus, and a bolus not as a rate."""
    issues = oc.free_text_dose_issues("**GIVE**\n- Epinephrine infusion 0.05 mcg/kg/min.",
                                      [], ADULT)
    assert issues == [], issues
