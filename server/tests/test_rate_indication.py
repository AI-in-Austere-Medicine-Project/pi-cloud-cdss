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


# ── Beyond the pressors: a rate is for its indication too ───────────────────
# Found signing batch 2 (#170): the adult ketamine prolonged-sedation infusion
# (0.5-2.0 mg/kg/hr) is the first signed rate outside bradycardia, cardiogenic
# and shock. The query's indication was only read for those three, so any
# other rate entry matched by drug: a ketamine drip written for PAIN at
# 1.5 mg/kg/hr passed on the sedation range. Owner, #170 review: the rate
# check must be indication-specific like the dose check. An entry outside the
# three is matched only when the query states its class (INDICATION_CLASSES,
# #165); with no class stated, matching by drug stands, as above.
#
# The entry is the one #170 signs. It is added here so the test does not wait
# on that signature.
KETAMINE_SEDATION_INFUSION = {
    "indication": "prolonged sedation infusion", "population": "adult", "route": "IV",
    "dose_range": {"min": 0.5, "max": 2.0, "units": "mg/kg/hr", "per_kg": True},
    "signoff": True, "reviewed_by": "AI-AIM", "version": "0.4.0",
}
KETAMINE_PAIN = "80kg male, open femur fracture, start a ketamine drip for pain"
KETAMINE_SEDATION = "80kg male, intubated on the vent, ketamine drip for sedation"
KETAMINE_RATE = "**GIVE**\n- Ketamine infusion at 1.5 mg/kg/hr."


@pytest.fixture
def ketamine_rate_signed(monkeypatch):
    real = oc.drug_contracts.servable_entries

    def with_infusion():
        out = {k: list(v) for k, v in real().items()}
        out["ketamine"] = out.get("ketamine", []) + [KETAMINE_SEDATION_INFUSION]
        return out
    monkeypatch.setattr(oc.drug_contracts, "servable_entries", with_infusion)


def test_a_ketamine_drip_for_pain_holds_on_the_sedation_rate(ketamine_rate_signed):
    issues = _rate_issues(KETAMINE_PAIN, KETAMINE_RATE)
    assert issues, issues
    assert "pain" in issues[0], issues
    for n in ("0.5", "2.0"):
        assert n not in issues[0], issues


def test_the_signed_sedation_infusion_still_serves(ketamine_rate_signed):
    assert _rate_issues(KETAMINE_SEDATION, KETAMINE_RATE) == []


def test_a_ketamine_drip_with_no_indication_matches_by_drug(ketamine_rate_signed):
    assert _rate_issues("80kg male, starting a ketamine drip", KETAMINE_RATE) == []


def test_the_pressor_indications_are_unchanged(ketamine_rate_signed):
    """A query with no pressor indication but another class stated: the
    pressor entries are still matched by drug, as before."""
    assert _rate_issues("80kg male, anaphylaxis, epi drip",
                        "**GIVE**\n- Epinephrine infusion 0.1 mcg/kg/min.") == []
