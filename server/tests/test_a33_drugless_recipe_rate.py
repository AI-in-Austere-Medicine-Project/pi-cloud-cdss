"""A33: a recipe or rate that names no drug is the question's drug, or it holds.

Owner, 2026-10-21 (#173 review): "a mix/recipe or mL/hr line that names no
drug is attributed to the drug the question asks about and checked as that
drug's rate; if no drug can be attributed, the line holds."

Found in the A32 live harness: "80 kg adult, BP 70/40 after 2 L of fluid,
still in shock, epinephrine infusion rate" was served, SAFE,

    **GIVE**
    - Mix 10 mg in 10 mL NS (10 mg/mL). Start 10 mL/hr. Target: MAP > 65 mmHg.

naming no drug (vasopressin, from its BRIEF). The recipe clause is exempt as a
preparation, and a rate with no drug in its clause was not read at all.

A line that names only a fluid and no drug amount ("Lactated Ringer's at
500 mL/hr", "oral rehydration solution; if IV, infuse 250-500 mL/hr") is a
fluid rate, not a drug's, and is untouched.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

SHOCK_EPI = "80 kg adult, BP 70/40 after 2 L of fluid, still in shock, epinephrine infusion rate"
SHOCK_NO_DRUG = "80 kg adult, BP 70/40 after 2 L of fluid, still in shock, what pressor and what rate"
DRUGLESS_DRIP = ("**GIVE**\n- Mix 10 mg in 10 mL NS (10 mg/mL). Start 10 mL/hr. "
                 "Target: MAP > 65 mmHg.")


def _issues(history, text):
    ctx = oc.rebuild_patient_context_from_history(history)
    doses = oc.build_allowed_doses(history, ctx)
    return oc.run_deterministic_checks(history, text, ctx, doses).issues


def test_the_shock_patients_drugless_drip_holds_as_epinephrine():
    issues = _issues(SHOCK_EPI, DRUGLESS_DRIP)
    assert issues, issues
    assert any("epinephrine" in i and "10 mL/hr" in i for i in issues), issues


def test_with_no_drug_to_attribute_the_drugless_drip_holds():
    issues = _issues(SHOCK_NO_DRUG, DRUGLESS_DRIP)
    assert issues, issues
    assert any("no drug named" in i for i in issues), issues


def test_a_drugless_recipe_alone_holds_with_no_drug_to_attribute():
    issues = _issues(SHOCK_NO_DRUG, "**GIVE**\n- Mix 10 mg in 10 mL NS (10 mg/mL).")
    assert any("no drug named" in i for i in issues), issues


def test_the_a18_recipe_now_holds():
    """Pinned as not a drugless dose by A18; under A33 a drugless recipe with
    no drug in the question to attribute it to holds."""
    ctx = oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    issues = oc.free_text_dose_issues(
        "- 500 mg in 1 L = 0.5 mg/mL — half the standard 1 mg/mL mix, so rate must double.\n",
        [], ctx, "80kg male, tension pneumo on the left, what now")
    assert any("no drug named" in i for i in issues), issues


def test_a_drugless_mass_rate_is_the_questions_drug():
    issues = _issues(SHOCK_EPI, "**GIVE**\n- Start the drip. Run it at 5 mcg/min.")
    assert any("epinephrine" in i and "5 mcg/min" in i for i in issues), issues


# ── Untouched ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "**GIVE**\n- Lactated Ringer's at 500 mL/hr.",
    "**BRIEF**\n- If stable and conscious: Use oral rehydration solution; if IV, infuse 250–500 mL/hr.",
    "**GIVE**\n- Normal saline 1 L bolus, then 125 mL/hr.",
])
def test_a_fluid_rate_is_not_a_drugs(text):
    """The question names epinephrine, so a drug could be attributed; a fluid
    line is still not epinephrine's. (Not the shock question: oral intake in
    shock holds on its own check.)"""
    q = "80 kg adult, HR 38, symptomatic bradycardia, epinephrine infusion rate"
    assert _issues(q, text) == [], text


def test_a_named_recipe_with_a_signed_rate_still_passes():
    text = ("**GIVE**\n- Mix 4 mg norepinephrine in 250 mL NS (16 mcg/mL). "
            "Start 0.1 mcg/kg/min, titrate to MAP 65.")
    q = "80 kg adult in septic shock, BP 72/40, norepinephrine infusion"
    assert _issues(q, text) == []


# ── Found in the A33 replay: not a drug's rate ──────────────────────────────
# 38 of the first pass's 44 newly held rows were these: H-IM-06 ("dehydrated
# casualty after two days without water, how much crystalloid and how fast")
# answered with crystalloid rates and urine-output targets in lines that name
# no fluid, and A1-RX-008's clarifying question, which says "mix".
CRYSTALLOID = "dehydrated casualty after two days without water, how much crystalloid and how fast"


@pytest.mark.parametrize("text", [
    "**GIVE**\n- Initial rate: 500 mL/h.",
    "**DO THIS**\n2. Start at 500 mL/h",
    "**WATCH**\n- Urine output goal: >30-50 mL/hour in adults, >0.5-1 mL/kg/hr in children.",
    "**DO THIS**\n- **Urine Output:** Aim for at least 0.5 mL/kg/hr.",
])
def test_the_crystalloid_questions_rates_are_the_fluids(text):
    assert _issues(CRYSTALLOID, text) == [], text


def test_a_urine_output_target_is_not_an_infusion_even_with_a_drug_asked():
    q = "80 kg adult, HR 38, symptomatic bradycardia, epinephrine infusion rate"
    assert _issues(q, "**WATCH**\n- UOP: >0.5 mL/kg/hr") == []


def test_a_question_back_that_says_mix_is_not_a_recipe():
    text = "Which medication/mix are you asking about — and what concentration do you have available?"
    assert _issues("how much of that mix do I push for him", text) == []


def test_a_drug_amount_in_the_crystalloid_answer_still_holds():
    issues = _issues(CRYSTALLOID, "**GIVE**\n- Mix 10 mg in 10 mL NS (10 mg/mL). Start 10 mL/hr.")
    assert any("no drug named" in i for i in issues), issues
