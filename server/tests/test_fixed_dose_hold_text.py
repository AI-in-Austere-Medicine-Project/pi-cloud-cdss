"""
EdgeCDSS — A5: a fixed-dose hold never says "no weight is confirmed".

Work order A5: the hold text names the actual reason and what makes the
question answerable. Local benchmark run 2, finding 3: where a drug has
signed entries but none was built for the question, the hold read "no weight
is confirmed. Give the weight in kg", even when the signed dose is fixed and
weight is irrelevant (levetiracetam 1500 mg, epinephrine 1 mg). Run 3's hold
lists show the same text on H-S3, G-DIC-01 and G-TYP-07.

For an adult, a fixed entry builds without a weight (build_allowed_doses), so
a weight would not have changed the outcome. The weight IS the reason in two
cases, and those keep the weight text:
  * a child: nothing builds for a child without a weight, fixed or not;
  * an adult drug with a per-kg single-dose entry (midazolam 0.1 mg/kg for a
    seizure). A per-kg infusion rate doesn't count against a stated single
    dose: epinephrine 1 mg in arrest is fixed, whatever its infusions are.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _issues(query, response, ctx=None, allowed=None):
    ctx = ctx if ctx is not None else oc.extract_patient_context(query)
    return oc.run_deterministic_checks(query, response, ctx, allowed or []).issues


# ── The four fixed-dose holds ───────────────────────────────────────────────
# (query, answer, drug, a signed indication the hold must name)
FIXED = [
    # H-S3, run 3 (gpt-4o-mini, as deployed): the query never names levetiracetam.
    ("Have a TBI patient that is having ststus SZ, maxed out on versed",
     "**GIVE**\n- Levetiracetam 1500 mg IV.", "levetiracetam", "status epilepticus"),
    # G-DIC-01, run 3 (haiku): asystole.
    ("in Sicily, he's in asystole, CPR going",
     "**GIVE**\n- Epinephrine 1 mg IV every 3-5 minutes.", "epinephrine", "cardiac arrest"),
    ("hit by an IED, he is bleeding out",
     "**GIVE**\n- TXA 2 g IV.", "tranexamic acid", "traumatic haemorrhage"),
    ("sugar is 32 and he is unresponsive",
     "**GIVE**\n- Dextrose 25 g IV.", "dextrose", "symptomatic hypoglycaemia"),
]


@pytest.mark.parametrize("query,response,drug,indication", FIXED)
def test_a_fixed_dose_hold_does_not_blame_the_weight(query, response, drug, indication):
    issues = _issues(query, response)
    assert len(issues) == 1, issues
    assert "weight" not in issues[0].lower(), issues[0]


@pytest.mark.parametrize("query,response,drug,indication", FIXED)
def test_a_fixed_dose_hold_says_what_makes_it_answerable(query, response, drug, indication):
    text = _issues(query, response)[0]
    assert f"ask for {drug} by name" in text.lower(), text
    assert "fixed" in text, text
    assert indication in text, f"the hold should name what {drug} is signed for: {text}"


def test_what_the_medic_reads_through_the_gate():
    query, response, drug, _ = FIXED[0]
    ctx = oc.extract_patient_context(query)
    det = oc.run_deterministic_checks(query, response, ctx, [])
    out = oc.apply_safety_gate(response, det, {"result": "SAFE", "issues": [],
                                               "rationale": ""}, ctx, query)
    assert out.blocked
    assert "weight" not in out.response.lower(), out.response
    assert "levetiracetam" in out.response
    # No signed number is quoted in a hold (owner ruling 12).
    assert "2000" not in out.response


# ── Where the weight IS the reason, the text stays ──────────────────────────

def test_an_adult_seizure_dose_still_needs_the_weight():
    """midazolam's adult seizure entry is 0.1 mg/kg."""
    text = _issues("80 year old actively seizing, give versed",
                   "**GIVE**\n- Midazolam 5 mg IV.")[0]
    assert "no weight is confirmed" in text, text


def test_a_child_still_needs_the_weight_even_for_a_fixed_entry():
    """Nothing builds for a child without a weight, fixed or not."""
    text = _issues("6 year old, anaphylaxis after a bee sting",
                   "**GIVE**\n- Epinephrine 0.15 mg IM.")[0]
    assert "no weight is confirmed" in text, text


def test_with_a_weight_the_text_is_unchanged():
    ctx = oc.extract_patient_context("80 kg male in asystole")
    assert ctx.has_confirmed_weight
    text = _issues("80 kg male in asystole", "**GIVE**\n- Epinephrine 1 mg IV.", ctx)[0]
    assert text == ("The answer stated epinephrine 1 mg with no signed epinephrine dose "
                    "for this question. Ask for epinephrine by name, with what it is "
                    "for, to get the signed dose.")
