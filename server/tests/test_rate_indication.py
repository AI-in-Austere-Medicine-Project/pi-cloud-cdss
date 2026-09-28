"""
EdgeCDSS — A11b: rate matching is indication-specific.

Owner, #108 review: A11 matched a stated rate against any of the drug's signed
rate entries for the population. Make it indication-specific, the same shape
as A1b. Epinephrine's bradycardia range (0.02-0.2 mcg/kg/min) and shock range
(0.05-0.3) overlap: on main 0.25 mcg/kg/min passed for a bradycardic patient
(it is inside the SHOCK range) and 0.03 passed for a shocked one (inside the
BRADYCARDIA range). Norepinephrine: vasodilatory shock 0.05-0.5, cardiogenic
0.02-2.0.

The indication comes from the query: bradycardia ("bradycardic", or a stated
HR under 60), cardiogenic ("cardiogenic", pulmonary oedema, heart failure) or
shock (shock or hypotension, when not cardiogenic). With no indication
detected, A11's by-drug matching stands.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

ADULT = oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
BRADY = "80kg male, HR 38, symptomatic bradycardia"
SHOCK = "80kg male, BP 70/40 after 2 L of fluid, still in shock"
SEPTIC = "80kg male in septic shock, BP 72/40"
CARDIOGENIC = "80kg male, cardiogenic shock, pulmonary oedema, SBP 85"


def _rate_issues(query, text):
    check = oc.run_deterministic_checks(query, text, ADULT, [])
    return [i for i in check.issues if "infusion rate" in i]


@pytest.mark.parametrize("query,text", [
    (BRADY, "**GIVE**\n- Epinephrine infusion 0.25 mcg/kg/min."),     # shock range only
    (SHOCK, "**GIVE**\n- Epinephrine infusion 0.03 mcg/kg/min."),     # bradycardia range only
    (SEPTIC, "**GIVE**\n- Norepinephrine 1.5 mcg/kg/min."),           # cardiogenic range only
])
def test_a_rate_signed_for_another_indication_holds(query, text):
    issues = _rate_issues(query, text)
    assert issues, (query, text)


@pytest.mark.parametrize("query,text", [
    (BRADY, "**GIVE**\n- Epinephrine infusion 0.1 mcg/kg/min."),
    (SHOCK, "**GIVE**\n- Epinephrine infusion 0.1 mcg/kg/min."),
    (SEPTIC, "**GIVE**\n- Norepinephrine 0.1 mcg/kg/min."),
    (CARDIOGENIC, "**GIVE**\n- Norepinephrine 1.5 mcg/kg/min."),
])
def test_a_rate_signed_for_this_indication_passes(query, text):
    assert _rate_issues(query, text) == [], (query, text)


def test_with_no_indication_a11s_matching_by_drug_stands():
    assert _rate_issues("80kg male, starting an epi drip",
                        "**GIVE**\n- Epinephrine infusion 0.25 mcg/kg/min.") == []


def test_the_hold_names_the_indication_and_no_signed_number():
    issue = _rate_issues(BRADY, "**GIVE**\n- Epinephrine infusion 0.25 mcg/kg/min.")[0]
    assert "bradycardia" in issue, issue
    for n in ("0.02", "0.05", "0.2", "0.3"):
        assert n not in issue.replace("0.25", ""), issue
