"""Route filter: the offered doses are the stated route's, and only those.

Owner, 2026-10-21 (freeze plan to v5.1.0, item 1): "Route filter (finding 3):
offered doses filtered by the stated route; 'versed IM' is never offered the
IV entry. Failing test first."

Found in signing batch 2's replay (2026-10-19): "versed dose IM" was offered
the IV procedural bolus. Batch 3 signed adult IM midazolam (U12, sedation /
anxiolysis), and the question was then answered rather than asked which
indication, because the which-indication question counts the stated route's
entries; but every IV midazolam entry was still offered, and a model that
wrote one of them passed the dose check.

IV and IO are one route for dosing (the which-indication question and the
seizure second line already read them so). A drug with nothing signed on the
stated route is offered nothing, so a dose written for it holds.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _offers(history):
    ctx = oc.rebuild_patient_context_from_history(history)
    return ctx, oc.build_allowed_doses(history, ctx)


def _issues(history, text):
    ctx, doses = _offers(history)
    return oc.run_deterministic_checks(history, text, ctx, doses).issues


@pytest.mark.parametrize("q", [
    "adult, versed dose IM",
    "80 kg adult, midazolam IM for agitation",
    "80 kg adult, no IV access, midazolam dose",
])
def test_versed_im_is_never_offered_an_iv_entry(q):
    ctx, doses = _offers(q)
    assert ctx.route_preference == "IM"
    mid = [d for d in doses if d.drug == "midazolam"]
    assert mid, "the signed IM entry (U12) is still offered"
    assert {d.route for d in mid} == {"IM"}, [(d.indication, d.route) for d in mid]


def test_a_stated_im_route_offers_only_im_for_every_drug():
    _ctx, doses = _offers("80 kg adult, femur fracture, ketamine for pain IM")
    assert doses
    assert {d.route for d in doses} == {"IM"}, [(d.drug, d.indication, d.route) for d in doses]


@pytest.mark.parametrize("q", [
    "80 kg adult, midazolam IV",
    "80 kg adult, IO access, midazolam dose",
])
def test_a_stated_iv_or_io_route_offers_iv_and_io_only(q):
    _ctx, doses = _offers(q)
    mid = [d for d in doses if d.drug == "midazolam"]
    assert mid
    assert {d.route for d in mid} <= {"IV", "IO"}, [(d.indication, d.route) for d in mid]


def test_the_iv_dose_written_for_versed_im_holds():
    text = "**GIVE**\n- Midazolam 1 mg IV, slow push, for procedural sedation."
    issues = _issues("versed dose IM", text)
    assert any("midazolam" in i.lower() for i in issues), issues


def test_the_signed_im_dose_for_versed_im_still_passes():
    _ctx, doses = _offers("adult, versed dose IM")
    (im,) = [d for d in doses if d.drug == "midazolam"]
    text = f"**GIVE**\n- Midazolam {im.dose_mg:g} mg IM for sedation / anxiolysis."
    assert _issues("adult, versed dose IM", text) == []


def test_a_drug_with_nothing_on_the_stated_route_is_offered_nothing():
    """Ertapenem is signed IV only (E10). Asked for IM, it is offered nothing,
    and the IV gram written for it holds."""
    q = "80 kg adult, penetrating abdominal injury, ertapenem IM"
    _ctx, doses = _offers(q)
    assert [d for d in doses if d.drug == "ertapenem"] == []
    issues = _issues(q, "**GIVE**\n- Ertapenem 1 g IV.")
    assert any("ertapenem" in i.lower() for i in issues), issues


def test_naloxone_im_keeps_its_im_entry_only():
    _ctx, doses = _offers("adult, opioid overdose, naloxone IM")
    assert {d.route for d in doses if d.drug == "naloxone"} == {"IM"}


def test_no_stated_route_offers_every_route():
    _ctx, doses = _offers("adult, versed dose")
    assert {"IV", "IM"} <= {d.route for d in doses if d.drug == "midazolam"}
