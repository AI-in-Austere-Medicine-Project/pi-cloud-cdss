"""Pacing match: "midazolam for pacing" or "cardioversion" is E13, not the
ketamine add-on.

Owner, 2026-10-21 (freeze plan to v5.1.0, item 2): "'midazolam for pacing' or
'cardioversion' matches E13 (2.5-5 mg), not the ketamine add-on entry.
Failing test first."

Found in the signing batch 3 live harness: "80 kg adult, symptomatic
bradycardia, about to pace, midazolam for sedation" was served the JTS ID61
1 mg ("procedural sedation", the ketamine add-on), SAFE. E13 ("procedural
sedation for pacing / cardioversion", 2.5-5 mg IV) was in the same class,
"sedation", so the check accepted either; and "midazolam for pacing" with no
other word was asked which indication.

Pacing / cardioversion is now its own class, ahead of sedation: E13 (and the
paediatric "procedural sedation (incl. cardioversion, transcutaneous pacing)")
are in it. A question that states it accepts, for a drug signed for it, only
those entries; "sedation" stated beside it does not reopen the add-on. A drug
with no pacing entry keeps the sedation reading it had (no gate loosens).

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

E13 = "procedural sedation for pacing / cardioversion"
QUESTIONS = [
    "80 kg adult, midazolam for pacing",
    "80 kg adult, midazolam for cardioversion",
    "80 kg adult, IV, midazolam for synchronized cardioversion",
    "80 kg adult, symptomatic bradycardia, about to pace, midazolam for sedation",
    "80 kg adult, transcutaneous pacing, versed dose",
]


def _offers(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    return ctx, oc.build_allowed_doses(q, ctx)


def _issues(q, text):
    ctx, doses = _offers(q)
    return oc.run_deterministic_checks(q, text, ctx, doses).issues


def test_e13_is_its_own_class():
    pacing = oc.indication_class(E13)
    assert pacing not in (None, "sedation")
    assert oc.indication_class("procedural sedation") == "sedation"
    assert oc.indication_class(
        "procedural sedation (incl. cardioversion, transcutaneous pacing)") == pacing


@pytest.mark.parametrize("q", QUESTIONS)
def test_the_question_is_not_asked_which_indication(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    assert oc.which_indication_question(q, ctx) is None


@pytest.mark.parametrize("q", QUESTIONS)
def test_e13_is_offered_first(q):
    _ctx, doses = _offers(q)
    mid = [d for d in doses if d.drug == "midazolam"]
    assert mid and mid[0].indication == E13, [(d.indication, d.dose_mg) for d in mid]


@pytest.mark.parametrize("q", QUESTIONS)
def test_the_add_on_holds_and_e13_passes(q):
    held = _issues(q, "**GIVE**\n- Midazolam 1 mg IV slow push.")
    assert any("midazolam" in i.lower() for i in held), held
    assert _issues(q, "**GIVE**\n- Midazolam 2.5 mg IV slow push.") == []


def test_a_drug_with_no_pacing_entry_keeps_its_sedation_reading():
    """Ketamine has no pacing entry: "about to pace … ketamine for sedation"
    still accepts only its sedation entries, as before. The RSI dose holds."""
    q = "80 kg adult, symptomatic bradycardia, about to pace, ketamine for sedation"
    issues = _issues(q, "**GIVE**\n- Ketamine 160 mg IV.")
    assert any("ketamine" in i.lower() for i in issues), issues


def test_a_pacemaker_is_not_pacing():
    stated = oc.stated_indication_classes("patient with a pacemaker, chest pain")
    assert oc.indication_class(E13) not in stated
