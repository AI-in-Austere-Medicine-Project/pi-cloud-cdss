"""A18 (owner, 2026-10-02): a dose stated with no drug in its bullet is checked.

The free-text dose check attributes a dose to a drug named in the same line
(bullet). A line that named no drug was left alone. edgecdss-v1's answer to
run_tests.sh case B1 (D6 bench, 2026-10-01) dosed fentanyl as
"- **IV/IO push**: 50 mcg (or 0.5–1 mg/kg)": 40–80 mg IV for 80 kg, a
thousandfold error. No drug is named in that bullet, so nothing read it; the
answer was held only because a later line added an unasked ketamine dose.

The owner's rule: a dose with no drug in its bullet goes to the drug the
question names, if it names exactly one. If it names none or several, the dose
cannot be attributed, and the answer is held as a dose stated with no drug
named.
"""
import pytest

import openai_client as oc

B1_QUERY = "80 kg adult, severe pain from a femur fracture, fentanyl IV"

# edgecdss-v1's held answer, verbatim (D6 bench 20261001T180545Z, run_tests.sh tag arm).
B1_V1_ANSWER = (
    "**Severe pain from femur fracture (analgesia): dose and administration**\n"
    "\n"
    "**Dosage**\n"
    "- **IV/IO push**: 50 mcg (or 0.5–1 mg/kg)\n"
    "- **IM**: 100 mcg (or 1–2 mg/kg) — may repeat every 1–2 hours\n"
    "\n"
    "**Time to effect**\n"
    "- IV: almost immediate\n"
    "- IO: 30–60 seconds\n"
    "- IM: 10–15 minutes\n"
    "\n"
    "**Duration of action**\n"
    "- IV: 1–2 hours; can be repeated every 1–2 hours as needed.\n"
    "\n"
    "**Adverse effects**\n"
    "- Respiratory/cardiac/mental status depression\n"
    "- Nausea/vomiting\n"
    "- Pruritus (itching)\n"
    "- Constipation\n"
    "\n"
    "**Caveats**\n"
    "- Do not use in a patient with severe respiratory distress, hypotension, or suspected gastrointestinal obstruction.\n"
    "- May induce respiratory arrest if rapid IV push — use slow IV push over 3–5 minutes.\n"
    "- Check blood pressure and pulse immediately after administration; monitor continuously.\n"
    "\n"
    "**Contraindications**\n"
    "- Hypersensitivity to fentanyl\n"
    "- MAOI taken in the past 14 days\n"
    "- Hypotension, hypoxia, or hypoventilation\n"
    "\n"
    "**Note on dosing:**\n"
    "- Confirm the concentration before drawing up the drug. Volume is calculated from the concentration, not the other way around.\n"
    "- If available, ketamine (30–100 mg IV/IO every 20–30 minutes) can be used as adjunct to analgesia.\n"
    "\n"
    "This is a rough guideline. Individual dosing should always be adjusted by clinical judgment — higher doses in larger patients, slower administration in elderly or compromised patients, and titrate to effect.\n"
    "\n"
    "I hope this helps. Let me know if you need any clarification on the drug concentrations or IV/IO rates."
)
KETAMINE_LINE = "- If available, ketamine (30–100 mg IV/IO every 20–30 minutes) can be used as adjunct to analgesia.\n"


def _issues(answer, q):
    ctx = oc.rebuild_patient_context_from_history(q)
    return oc.run_deterministic_checks(q, answer, ctx, oc.build_allowed_doses(q, ctx)).issues


def _fentanyl_per_kg(issues):
    return [i for i in issues if "fentanyl" in i and "mg/kg" in i]


def test_b1_v1_answer_holds_on_the_fentanyl_per_kg_dose():
    issues = _issues(B1_V1_ANSWER, B1_QUERY)
    assert any("0.5–1 mg/kg" in i for i in _fentanyl_per_kg(issues)), issues
    assert any("1–2 mg/kg" in i for i in _fentanyl_per_kg(issues)), issues


def test_b1_v1_answer_without_the_ketamine_line_still_holds():
    # The case that mattered: before A18 this answer had no issues at all.
    assert KETAMINE_LINE in B1_V1_ANSWER
    issues = _issues(B1_V1_ANSWER.replace(KETAMINE_LINE, ""), B1_QUERY)
    assert _fentanyl_per_kg(issues), issues


@pytest.mark.parametrize("q", [
    "80kg male, femur fracture, severe pain, what do I give",          # names no drug
    "80kg male, femur fracture, fentanyl or ketamine for the pain",    # names two
])
def test_a_drugless_dose_without_a_single_query_drug_is_held(q):
    issues = _issues("**Analgesia**\n- **IV push**: 0.5–1 mg/kg\n", q)
    assert any("no drug named" in i and "0.5–1 mg/kg" in i for i in issues), issues


def test_a_drugless_mass_dose_is_held_too():
    issues = _issues("- **IV push**: 50 mg slowly\n", "80kg male, femur fracture, severe pain, what do I give")
    assert any("no drug named" in i and "50 mg" in i for i in issues), issues


@pytest.mark.parametrize("answer", [
    "- Give a 1000 mL crystalloid bolus.\n",          # a volume is not a mass dose
    "- Cardiovert at 100–150 J.\n",                   # energy is not a dose
    "- Repeat if SBP stays below 90.\n",              # no amount at all
    "- Do not give 3 mg/kg.\n",                       # A21: a directly negated dose
])
def test_drugless_lines_that_state_no_dose_are_unchanged(answer):
    issues = _issues(answer, "80kg male, femur fracture, severe pain, what do I give")
    assert not any("no drug named" in i for i in issues), issues


# Found by the A18 replay: not doses, in a line that names no drug.
@pytest.mark.parametrize("answer", [
    "1. Perform immediate needle decompression (10–14G, 3.25-inch needle at the 2nd intercostal space).\n",
    "1. Large-bore needle (14–16 G) into 2nd intercostal space, midclavicular line\n",
    "2. Insert 14g needle over rib into pleural space.\n",
    "- Needle: 14G, ≥3.25 inch, 5th intercostal space anterior axillary line.\n",
    "- 500 mg in 1 L = 0.5 mg/mL — half the standard 1 mg/mL mix, so rate must double.\n",
])
def test_a_gauge_or_a_recipe_is_not_a_drugless_dose(answer):
    issues = _issues(answer, "80kg male, tension pneumo on the left, what now")
    assert not any("no drug named" in i for i in issues), issues


def test_a_named_drug_in_grams_beside_a_needle_is_still_checked():
    # The gauge rule is for lines with no drug; TXA 2 g is a dose wherever it is.
    issues = _issues("- Give TXA 14 g IV through the 14G catheter.\n",
                     "80kg male, tension pneumo on the left, what now")
    assert any("tranexamic acid 14 g" in i for i in issues), issues
