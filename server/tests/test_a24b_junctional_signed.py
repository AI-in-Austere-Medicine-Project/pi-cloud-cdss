"""A24b (owner, 2026-10-08): the junctional card, signed by Andrew Azelton.

The owner's decisions at signing: cite the DCR in Prolonged Field Care CPG as
the corpus prints it (CPG ID73, 01 Oct 2018, rapid updates to 01 Sep 2023)
and the CCATT NPWT CPG likewise (CPG ID49, rev. 26 Feb 2025); keep line 3
(manual pressure) as cited; leave TCCC's 3 minutes of pressure out; the
2-hour conversion is junctional in the source (ID73 p.5, "Tourniquets (limb
and junctional) …"). The card's text is unchanged from the reviewed draft.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

# The reviewed draft's text (#139), word for word.
TEXTS = [
    "Junctional bleeding (groin, axilla, neck): pack the wound tightly with a hemostatic dressing (Combat Gauze, Celox Gauze, ChitoGauze; XStat for a deep wound) and put a pressure dressing over it.",
    "Groin or axilla: apply a junctional tourniquet if one is carried (Combat Ready Clamp, SAM Junctional Tourniquet, Junctional Emergency Treatment Tool).",
    "Until it is on, or if none is carried, hold firm manual pressure on the packed wound.",
    "Junctional tourniquet on: transition to a pressure dressing within 2 hours when the criteria for conversion are met."
]


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_the_card_is_signed_by_the_owner():
    card = oc.junctional_card()
    assert card["signoff"] is True
    assert card["reviewed_by"] == "Andrew Azelton"
    assert card["review_date"] == "2026-10-08"


def test_the_text_is_the_reviewed_draft_word_for_word():
    card = oc.junctional_card()
    assert [l["text"] for l in card["do_this"]] + [w["text"] for w in card["watch"]] == TEXTS


def test_the_citations_are_as_the_corpus_prints_them():
    cites = {s["citation"] for l in oc.junctional_card()["do_this"] + oc.junctional_card()["watch"] for s in l["sources"]}
    assert any("CPG ID73" in c and "01 Oct 2018" in c for c in cites), cites
    assert any("CPG ID49" in c and "26 Feb 2025" in c for c in cites), cites
    assert not any("to confirm" in c or "owner to" in c.lower() for c in cites), cites


@pytest.mark.parametrize("query", [
    "new casualty, adult male, blast injury, he's bleeding from the groin",
    "groin wound bleeding heavily",
    "bleeding from the left axilla after a frag wound",
])
def test_junctional_bleeding_gets_the_signed_card(query):
    r = oc._query_with_rag_internal(query, _NoRetrieval())
    assert r["validator_result"] == "DETERMINISTIC_CHECKED", r["validator_result"]
    for text in TEXTS[:3]:
        assert text in r["response"]
    assert "CPG ID73" in r["response"] and "p.8" in r["response"]


def test_the_card_names_its_signer_nowhere_in_the_answer():
    # Provenance lives in the file and the log, not in the medic's card text.
    r = oc._query_with_rag_internal("he's bleeding from the groin", _NoRetrieval())
    assert "Azelton" not in r["response"]
