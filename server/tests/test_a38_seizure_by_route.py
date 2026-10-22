"""A38: the seizure card chooses its benzodiazepine by the available route.

Owner, 2026-10-22 (v5.1.0 freeze, item A38): "seizure card by available route".

Found in the A35 sweep: the seizure role chose ONE benzodiazepine first
(lorazepam, unless midazolam was named) and the route filter (A34) dropped it
when there was no IV access, so a seizing child with no IV got no dose,
though the signed paediatric IM midazolam seizure entry (0.2 mg/kg, NASEMSO)
was there. The choice is now made among the entries on the available route:
lorazepam first where it is on the route, midazolam where named, else the
route's signed entry. Still one benzodiazepine. With nothing signed on the
route (an adult with no IV: no adult IM seizure entry) the card holds, as
before.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _benzos(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    return ctx, [d for d in oc.build_allowed_doses(q, ctx)
                 if d.drug.lower() in oc._BENZODIAZEPINES]


def _give(q):
    ctx = oc.rebuild_patient_context_from_history(q)
    card = oc.build_seizure_response(q, ctx)
    return card.split("**GIVE**")[1].split("\n**")[0]


CHILD_IM = "6 year old child 20 kg, seizing, no IV access"


def test_a_seizing_child_with_no_iv_gets_the_signed_im_midazolam():
    ctx, benzos = _benzos(CHILD_IM)
    assert ctx.route_preference == "IM"
    assert [(d.drug, d.route, d.dose_mg) for d in benzos] == [("midazolam", "IM", 4.0)]


def test_the_card_serves_it():
    give = _give(CHILD_IM)
    assert "midazolam IM" in give and "4 mg" in give, give


@pytest.mark.parametrize("q, drug", [
    ("she is seizing, 60kg, IV access", "lorazepam"),
    ("6 year old child 20 kg, seizing, IV access", "lorazepam"),
    ("she is seizing, 60kg, IV access, give midazolam", "midazolam"),
])
def test_iv_is_unchanged(q, drug):
    _ctx, benzos = _benzos(q)
    assert [(d.drug, d.route) for d in benzos] == [(drug, "IV")]


def test_one_benzodiazepine_only():
    _ctx, benzos = _benzos("6 year old child 20 kg, seizing")  # no route: every route
    assert len(benzos) == 1, benzos


def test_an_adult_with_no_iv_still_holds():
    _ctx, benzos = _benzos("60 kg adult, seizing, no IV access")
    assert benzos == []
    assert "No signed benzodiazepine dose" in _give("60 kg adult, seizing, no IV access")
