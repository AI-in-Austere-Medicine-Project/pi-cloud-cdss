"""A24 (owner, 2026-10-06; found in the D2b bench): junctional bleeding goes to
the DCR card, with junctional-specific content the owner signs.

"new casualty, adult male, blast injury, he's bleeding from the groin"
(G-MTN-04) went to the model, not the haemorrhage card: the DCR gate's
junctional pattern read the site BEFORE the bleeding ("groin wound bleeding")
and not after it ("bleeding from the groin"). JTS CPG ID82 p.13: "junctional
includes axilla/inguinal/cervical".

The junctional content (packing with a hemostatic dressing, pressure, a
junctional tourniquet) lives in junctional_card.json, drafted from the JTS
corpus with page citations, and ships with signoff false. Unsigned, the DCR
card is served exactly as before; it is the owner's act to sign it.
"""
import json
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

G_MTN_04 = "new casualty, adult male, blast injury, he's bleeding from the groin"


@pytest.mark.parametrize("query", [
    G_MTN_04,
    "bleeding from his left armpit after a frag wound",
    "she's bleeding heavily from the axilla",
    "bleeding from the neck, shrapnel",
    "he is bleeding from the inguinal area",
])
def test_junctional_bleeding_routes_to_the_dcr_card(query):
    assert oc.looks_like_hemorrhagic_shock(query), query


@pytest.mark.parametrize("query", [
    "bleeding from the nose for an hour",
    "bleeding from his gums",
    "neck pain after a fall, no bleeding",
])
def test_other_bleeds_are_not_junctional(query):
    assert not oc.is_junctional_bleeding(query), query


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_the_g_mtn_04_question_gets_the_dcr_card():
    r = oc._query_with_rag_internal(G_MTN_04, _NoRetrieval())
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["source_mode"]
    assert "Control hemorrhage immediately" in r["response"]


def test_the_draft_ships_unsigned_and_the_card_is_unchanged():
    card = oc.junctional_card()
    assert card["signoff"] is False
    assert oc.build_hemorrhagic_shock_dcr_response(None, G_MTN_04) == \
        oc.build_hemorrhagic_shock_dcr_response(None, "")
    assert "junctional tourniquet" not in oc.build_hemorrhagic_shock_dcr_response(None, G_MTN_04).lower()


def test_every_draft_line_cites_a_page():
    card = oc.junctional_card()
    assert card["do_this"]
    for line in card["do_this"]:
        assert line["text"] and line["sources"], line
        assert all(s.get("citation") and s.get("page") and s.get("quote") for s in line["sources"]), line


def test_signed_the_card_serves_the_junctional_steps(monkeypatch):
    signed = dict(oc.junctional_card(), signoff=True, reviewed_by="owner", review_date="2026-10-06")
    monkeypatch.setattr(oc, "junctional_card", lambda: signed)
    out = oc.build_hemorrhagic_shock_dcr_response(None, G_MTN_04)
    for line in signed["do_this"]:
        assert line["text"] in out
    assert "ID18" in out and "p.8" in out
    # Not junctional: the card is unchanged even when signed.
    assert oc.build_hemorrhagic_shock_dcr_response(None, "GSW left thigh, BP 80/40") == \
        oc.build_hemorrhagic_shock_dcr_response(None, "")
