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


def test_unsigned_a_tension_presentation_holds(tmp_path, monkeypatch):
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    card.update(signoff=False, reviewed_by=None, review_date=None)
    p = tmp_path / "needle_decompression_card.json"
    p.write_text(json.dumps(card), encoding="utf-8")
    monkeypatch.setattr(oc, "_TENSION_CARD_FILE", str(p))
    r = _run(BENCH, monkeypatch)
    assert r["validator_result"] == "UNSAFE"
    assert oc.TENSION_UNSIGNED_ISSUE in r["validator_issues"]
    assert "14 gauge" not in r["response"], "the hold named unsigned content"


# ── the procedure file ───────────────────────────────────────────────────────

def test_every_line_is_cited_with_a_verbatim_quote():
    """ID74 p.5 and p.8; the WATCH reassessment line also SMOG CY24 p.22 (owner, 2026-10-11)."""
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    lines = card["do_this"] + card["watch"] + card["dont"] + [card["then_with_dcr"], card["tldr"]]
    allowed = {("ID74", 5), ("ID74", 8), ("SMOG", 22)}
    for line in lines:
        assert any("ID74" in s["citation"] for s in line["sources"]), line["text"]
        for s in line["sources"]:
            doc = "ID74" if "ID74" in s["citation"] else "SMOG" if "SMOG" in s["citation"] else None
            assert (doc, s["page"]) in allowed and len(s["quote"]) > 40, s


def test_the_card_is_the_card_served_before_word_for_word():
    """Owner, 2026-10-11: the WATCH line keeps post-decompression reassessment."""
    text = oc.build_tension_pneumothorax_response(with_dcr=False)
    assert "- Breathing, SpO2, BP and breath sounds after decompression; recurrence." in text


def test_the_card_states_no_dose():
    text = oc.build_tension_pneumothorax_response(with_dcr=True)
    assert not oc.free_text_dose_issues(text, [])


# ── the signed text (owner, 2026-10-12) ──────────────────────────────────────

SIGNED = {
    "do_this": [
        "Needle decompression now, on the affected side: large bore (14 gauge or larger) 3.25in/8cm catheter in the 4th or 5th intercostal space, anterior axillary line.",
        "Alternate site: 2nd intercostal space, mid-clavicular line (the primary site in children).",
        "Follow with tube thoracostomy as soon as feasible and safe. If it is delayed, be ready to repeat needle decompression."
    ],
    "watch": [
        "Breathing, SpO2, BP and breath sounds after decompression; recurrence.",
        "No improvement after two needle decompressions most likely means another diagnosis."
    ],
    "dont": [
        "Do not use short (5 cm) venous-access catheters: they rarely reach the chest cavity.",
        "Do not wait for imaging: absent or markedly decreased breath sounds after chest trauma indicate intervention without further testing."
    ],
    "then_with_dcr": "After decompression, then reassess for hemorrhage — DCR (damage-control resuscitation) if shock persists: control bleeding, blood products, TXA within 3 hours.",
    "tldr": "Suspected tension pneumothorax: needle decompress, 14 gauge 8cm catheter, 4th/5th ICS anterior axillary line, then tube thoracostomy.",
    "source_line": "JTS CPG ID74, Wartime Thoracic Injury (26 Dec 2018), p.5 (recognition), p.8 (needle decompression)"
}


def test_the_procedure_is_signed_by_the_owner():
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    assert card["signoff"] is True
    assert card["reviewed_by"] == "Andrew Azelton" and card["review_date"] == "2026-10-12"


def test_the_signed_text_is_pinned_word_for_word():
    """A changed line needs a new signature: this test fails until the owner re-signs."""
    card = json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))
    assert [l["text"] for l in card["do_this"]] == SIGNED["do_this"]
    assert [l["text"] for l in card["watch"]] == SIGNED["watch"]
    assert [l["text"] for l in card["dont"]] == SIGNED["dont"]
    assert card["then_with_dcr"]["text"] == SIGNED["then_with_dcr"]
    assert card["tldr"]["text"] == SIGNED["tldr"]
    assert card["source_line"] == SIGNED["source_line"]


def test_the_bench_question_gets_the_signed_card(monkeypatch):
    r = _run(BENCH, monkeypatch)
    assert r["validator_result"] == "DETERMINISTIC_CHECKED"
    assert SIGNED["do_this"][0] in r["response"]
