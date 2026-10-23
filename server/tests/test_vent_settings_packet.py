"""The vent card settings, printed for the owner's signature ruling.

Owner, 2026-10-22 (v5.1.0 freeze): "vent card settings printed for my
signature ruling". Found in the A35 sweep: the five vent cards serve with
signoff true, reviewed_by "clinician" (a role, not a name), 2026-08-22; their
settings are numbers no named signer has signed. The packet prints every line
each card can render, verbatim, with its reference, for the owner to rule
SIGN / CHANGE / REMOVE per card. Nothing is signed or changed by it.

    cd server && ./run_unit_tests.sh
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import vent_module  # noqa: E402

PACKET = Path(__file__).resolve().parents[2] / "docs" / "authoring" / "VENT_CARD_SETTINGS_2026-10-22.md"
CARDS = json.load(open(Path(vent_module.__file__).with_name("vent_cards.json"),
                       encoding="utf-8"))["cards"]


def _rendered(card):
    s = card.get("initial_settings") or {}
    out = [f"{v}" for v in s.values()]
    for k in ("titrate_on", "watch_for", "evac_if"):
        out += list(card.get(k) or [])
    for k in ("actual_weight_caveat", "escape_hatch", "tldr"):
        if card.get(k):
            out.append(card[k])
    return out + list(card.get("references") or [])


def _packet():
    return PACKET.read_text(encoding="utf-8")


@pytest.mark.parametrize("card", CARDS, ids=[c["id"] for c in CARDS])
def test_every_rendered_line_is_in_the_packet_verbatim(card):
    text = _packet()
    assert f"`{card['id']}`" in text
    for line in _rendered(card):
        assert line in text, (card["id"], line)


def test_the_packet_carries_the_ibw_constants():
    text = _packet()
    for v in (vent_module._DEVINE_BASE["male"], vent_module._DEVINE_BASE["female"],
              vent_module._DEVINE_PER_INCH, vent_module._DEVINE_BASE_INCHES):
        assert f"{v:g}" in text


def test_the_packet_asks_for_a_ruling_and_signs_nothing():
    text = _packet()
    assert text.count("Ruling (owner):") == len(CARDS) + 1  # + the IBW constants
    for card in CARDS:
        assert card["reviewed_by"] == "clinician"  # unchanged until the owner rules
