"""
EdgeCDSS — a paediatric answer's doses are each checked against the signed
paediatric entries, and held if they do not match.

Post-signing benchmark run 2 (2026-09-24), G-MTN-03 on the local model: a
6-year-old, 20 kg, asked "ok now what" after an IM ketamine dose, and was
served ketamine 1.0-2.0 mg/kg IV, ketamine IM 80-160 mg, fentanyl 25-100 μg and
midazolam 1-4 mg. The deterministic check passed it with no issues.

Nothing about the patient being a child let it through. The free-text check
did not read any of the four doses:
  - "1.0-2.0mg/kg of ketamine": a per-kg amount was treated as a rate;
  - "For IM administration, ... 80-160mg": the clause names no drug (ketamine
    is in the previous sentence), so the number was not attributed;
  - "**Fentanyl**: Can be added at a dose of 25-100μg": the clause split at
    the colon separated the drug from its dose, and "added" read as a
    preparation ("add 1 mg to the bag");
  - "**Midazolam**: Can be added at a dose of 1-4mg": the same two.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

CHILD = oc.PatientContext(age_years=6.0, is_pediatric=True, confirmed_weight_kg=20.0)

# The local model's answer, verbatim from run 2 (the dose-bearing lines and the
# ones around them).
G_MTN_03 = """Based on the information provided, here's a summary of the key points and steps for procedural sedation using ketamine:

1. **Initial Dose**: Administer a bolus of 1.0-2.0mg/kg of ketamine via IV or IO over 60 seconds. For IM administration, a higher dose of 80-160mg (250-400mg) might be necessary.

2. **Additional Sedation**: Depending on the patient's response and the duration of the procedure:
   - **Fentanyl**: Can be added at a dose of 25-100μg IV/IO.
   - **Midazolam**: Can be added at a dose of 1-4mg IV/IO.

3. **Re-dosing**: If the procedure lasts longer than 10-15 minutes, additional doses of:
   - **Ketamine**: Every 10-15 minutes.
   - **Fentanyl**: Every 15-30 minutes.
   - **Midazolam**: Every 30-60 minutes.

6. **Emergence Delirium**: Consider adding midazolam to prevent emergence delirium in adults with higher doses of ketamine (>0.3mg/kg IV/IO).
"""

NAMED = "ketamine fentanyl midazolam for procedural sedation"


def _issues(text, query, ctx=CHILD):
    allowed = oc.build_allowed_doses(query, ctx)
    det = oc.run_deterministic_checks(query, text, ctx, allowed)
    return det, allowed


def test_the_reported_case_holds_every_dose():
    """As served: "ok now what" names no drug, so no signed dose was built,
    and every stated dose must be held."""
    det, allowed = _issues(G_MTN_03, "ok now what")
    assert allowed == [], "premise: the follow-up names no drug"
    assert det.passed is False
    joined = " | ".join(det.issues)
    for shown in ("ketamine 1.0-2.0mg/kg", "ketamine 80-160mg",
                  "fentanyl 25-100μg", "midazolam 1-4mg"):
        assert shown in joined, f"not held: {shown} — issues: {det.issues}"


def test_each_dose_is_checked_against_the_signed_paediatric_entries():
    """With the drugs named, ALLOWED_DOSES holds the signed paediatric doses
    for this 20 kg child: fentanyl 20 mcg IV/IN, midazolam 4 mg IM, ketamine
    IM 60 mg. None of the answer's numbers for them is one of those."""
    det, allowed = _issues(G_MTN_03, NAMED)
    signed = {(d.drug, d.route, round(d.dose_mg, 4)) for d in allowed}
    assert {("fentanyl", "IV", 0.02), ("midazolam", "IM", 4.0),
            ("ketamine", "IM", 60.0)} <= signed, f"premise: the signed paediatric doses moved: {signed}"
    assert det.passed is False
    joined = " | ".join(det.issues)
    for drug, shown in (("fentanyl", "25-100μg"), ("midazolam", "1-4mg"),
                        ("ketamine", "80-160mg")):
        assert f"The answer stated {drug} {shown}, which is not the signed {drug} dose" in joined, \
            f"{drug} {shown} was not held against the signed entry — issues: {det.issues}"


@pytest.mark.parametrize("line", [
    "- **Fentanyl**: Can be added at a dose of 20 mcg IV/IO.",
    "- **Fentanyl**: Can be added at a dose of 20μg IV.",
    "- **Midazolam**: 4 mg IM for the seizure.",
    "1. **Initial Dose**: Give 2 mg/kg of ketamine IV (40 mg) for induction.",
])
def test_the_signed_paediatric_dose_passes(line):
    """The control: the same shapes carrying the signed paediatric number."""
    det, _ = _issues(line, NAMED)
    assert det.passed, det.issues


@pytest.mark.parametrize("line", [
    "Add 1 mg epinephrine to a 250 mL bag of NS.",
    "Mix 4 mg norepinephrine in 250 mL NS.",
    "Run the ketamine infusion at 0.5 mg/kg/hr.",
    "Fentanyl infusion 1 mcg/kg/hr, titrate to effect.",
    "Ketamine comes as 50 mg/mL.",
])
def test_preparations_rates_and_concentrations_are_still_not_doses(line):
    det, _ = _issues(line, "ok now what")
    assert det.passed, det.issues
