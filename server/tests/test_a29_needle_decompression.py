"""A29 (owner, 2026-10-11): the tension-pneumothorax card is served from a
signed needle-decompression procedure (verbatim JTS CPG ID74 quotes), and
"pneumo" is read as pneumothorax; found in the D7 v3 re-bench, G-TYP-02.

"susected tention pneumo, trachea deviated, what now" went to the model: the
detector needs two tension signs, or one after chest trauma, and only the word
"pneumothorax" counted as chest trauma. edgecdss-v3 served repositioning and
"secure the tube" with no decompression; the base served "Intubate".

The card was hard-coded text citing ID74 with no signed procedure behind it.
Its lines now live in needle_decompression_card.json, each with ID74 quotes.
While that file is unsigned, a tension presentation is held with a line that
names no unsigned content (the junctional precedent, owner #139); signed, the
card is served from the file.
"""
import json

import pytest

import openai_client as oc

BENCH = "susected tention pneumo, trachea deviated, what now"


def _signed_copy(tmp_path, monkeypatch):
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    card.update(signoff=True, reviewed_by="test signer", review_date="2026-10-11")
    p = tmp_path / "needle_decompression_card.json"
    p.write_text(json.dumps(card), encoding="utf-8")
    monkeypatch.setattr(oc, "_TENSION_CARD_FILE", str(p))
    return card


def _run(q, monkeypatch):
    def no_model(*a, **k):
        raise AssertionError("the model was called for a tension pneumothorax")

    class Hit:
        def query(self, *a, **k):
            return {"documents": [["chest"]], "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.4]]}

    monkeypatch.setattr(oc.providers, "chat", no_model)
    return oc._query_with_rag_internal(q, Hit())


# ── "pneumo" ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("q", [
    BENCH,
    "suspected tension pneumo, trachea deviated",
    "pneumo on the left, absent breath sounds",
    "tension pneumo, JVD, hypotensive",
])
def test_pneumo_is_read_as_pneumothorax(q):
    assert oc.looks_like_tension_pneumothorax(q), q


@pytest.mark.parametrize("q", [
    "pneumonia, decreased breath sounds at the base",
    "how do I manage a tension pneumo",
    "simple pneumo on x-ray, breathing comfortably",
])
def test_not_a_tension_presentation(q):
    assert not oc.looks_like_tension_pneumothorax(q), q


# ── the card comes from the signed procedure ─────────────────────────────────

def test_signed_the_card_is_served_from_the_file(tmp_path, monkeypatch):
    card = _signed_copy(tmp_path, monkeypatch)
    r = _run(BENCH, monkeypatch)
    for line in card["do_this"] + card["watch"] + card["dont"]:
        assert line["text"] in r["response"], line["text"]
    assert card["source_line"] in r["response"]


def test_signed_with_shock_the_dcr_line_follows(tmp_path, monkeypatch):
    card = _signed_copy(tmp_path, monkeypatch)
    r = _run("penetrating chest wound, absent breath sounds on the right, JVD, BP 80/50, HR 130", monkeypatch)
    assert card["then_with_dcr"]["text"] in r["response"]


def test_unsigned_a_tension_presentation_holds(monkeypatch):
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    assert card["signoff"] is not True, "this test is for the unsigned draft"
    r = _run(BENCH, monkeypatch)
    assert r["validator_result"] == "UNSAFE"
    assert oc.TENSION_UNSIGNED_ISSUE in r["validator_issues"]
    assert "14 gauge" not in r["response"], "the hold named unsigned content"


# ── the procedure file ───────────────────────────────────────────────────────

def test_every_line_is_cited_to_id74_with_a_quote():
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    lines = card["do_this"] + card["watch"] + card["dont"] + [card["then_with_dcr"], card["tldr"]]
    for line in lines:
        assert line["sources"], line["text"]
        for s in line["sources"]:
            assert "ID74" in s["citation"] and s["page"] in (5, 8) and len(s["quote"]) > 40, s


def test_the_card_states_no_dose():
    text = oc.build_tension_pneumothorax_response(with_dcr=True)
    assert not oc.free_text_dose_issues(text, [])
