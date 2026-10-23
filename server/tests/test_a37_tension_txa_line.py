"""A37: the tension card's "TXA within 3 hours" is removed, and the card re-signed.

Owner, 2026-10-22 (v5.1.0 freeze, item A37): "tension card TXA line removed
and re-signed".

Found in the A35 sweep: the signed card's THEN line ("… control bleeding,
blood products, TXA within 3 hours.") cites JTS ID74 p.5, and that quote says
nothing about TXA or 3 hours. The TXA dose and its window are the signed TXA
entry's, served by the DCR card. Every number on the card is now in the quote
it cites.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import re

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

THEN = ("After decompression, then reassess for hemorrhage — DCR (damage-control "
        "resuscitation) if shock persists: control bleeding, blood products.")


def _card():
    return json.load(open(oc._TENSION_CARD_FILE, encoding="utf-8"))


def _lines(card):
    out = []
    for k in ("do_this", "watch", "dont"):
        out += card.get(k, [])
    return out + [card["then_with_dcr"], card["tldr"]]


def test_the_then_line_carries_no_txa():
    assert _card()["then_with_dcr"]["text"] == THEN


def test_every_number_on_the_card_is_in_its_cited_quote():
    for line in _lines(_card()):
        quotes = " ".join(s["quote"] for s in line.get("sources", []))
        for n in re.findall(r"\d+(?:\.\d+)?", line["text"]):
            assert n in quotes, (n, line["text"])


def test_the_card_is_re_signed_by_the_owner():
    card = _card()
    assert card["signoff"] is True
    assert card["reviewed_by"] == "Andrew Azelton"
    assert card["review_date"] == "2026-10-22"


def test_the_served_card_says_no_txa_window():
    text = oc.build_tension_pneumothorax_response(with_dcr=True)
    assert "TXA within 3 hours" not in text, text
    assert THEN in text
