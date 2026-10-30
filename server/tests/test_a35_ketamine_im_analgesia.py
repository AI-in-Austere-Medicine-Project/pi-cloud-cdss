"""A35: "ketamine for pain IM" serves the signed adult IM entry, or holds.

Owner, 2026-10-22 (#176 review): "'Ketamine for pain IM, 80 kg' serves the
signed adult IM entry (40-80 mg, cap 100) or holds; the legacy 2 mg/kg
calculator is removed."

Found in the A34 live harness: the ketamine analgesia card looked the signed
entry up by "moderate to severe pain" only. The adult bank's IM pain entry is
"breakthrough pain — IM/IN (prolonged field care)" (0.5-1.0 mg/kg, max single
100 mg, JTS ID91 p.33), so the card found nothing and backfilled the legacy
calculator: "ketamine IM: 160 mg … dissociative analgesia (IM — no IV
access)", 2 mg/kg, with no signed entry behind it.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

QUERY = "80 kg adult, femur fracture, ketamine for pain IM"


def _card(q=QUERY):
    ctx = oc.rebuild_patient_context_from_history(q)
    return ctx, oc.build_ketamine_analgesia_response(ctx)


def _give(card):
    return card.split("**GIVE**")[1].split("**")[0]


def test_the_card_serves_the_signed_adult_im_pain_entry():
    ctx, card = _card()
    assert ctx.route_preference == "IM" and ctx.confirmed_weight_kg == 80.0
    assert card is not None
    give = _give(card)
    assert "ketamine IM: 40 mg" in give, give
    assert "breakthrough pain" in give, give
    assert "Signed dose contract" in card and "ID91" in card, card


def test_the_served_dose_is_inside_the_signed_range_and_cap():
    for kg in (50, 80, 120, 250):
        q = f"{kg} kg adult, femur fracture, ketamine for pain IM"
        _ctx, card = _card(q)
        give = _give(card)
        # "ketamine IM: 60 mg" or, with a declared vial, "… ketamine IM (25 mg)".
        mg = float(re.search(r"ketamine IM(?::| \()\s*([\d.]+) ?mg", give).group(1))
        # 0.5-1.0 mg/kg, never above the 100 mg single maximum.
        assert min(0.5 * kg, 100.0) <= mg <= min(1.0 * kg, 100.0), (kg, give)


@pytest.mark.parametrize("bad", ["160 mg", "2 mg/kg", "dissociative analgesia",
                                 "Deterministic calculator"])
def test_the_legacy_im_calculator_never_reaches_the_card(bad):
    _ctx, card = _card()
    assert bad not in card, card


def test_the_legacy_calculators_are_gone():
    assert not hasattr(oc, "ketamine_analgesia_im")
    assert not hasattr(oc, "LEGACY_ANALGESIA_SOURCE")


def test_with_nothing_signed_on_the_route_the_card_holds(monkeypatch):
    """No signed IM pain entry for this patient: the card holds rather than
    computing a dose of its own."""
    monkeypatch.setattr(oc, "_contract_analgesia_candidate", lambda ctx, **k: None)
    _ctx, card = _card()
    assert card is not None
    assert "**GIVE**" not in card, card
    assert "mg" not in card.split("**SOURCE**")[0].replace("mg/mL", ""), card
    assert card.startswith(oc.build_safety_hold([], "").split("\n")[0]), card


def test_the_pipeline_serves_it():
    class _R:
        def query(self, *a, **k):
            return {"documents": [["t"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.2]]}
    r = oc._query_with_rag_internal(QUERY, _R())
    assert "ketamine IM: 40 mg" in r["response"], r["response"]
    assert "160 mg" not in r["response"]
