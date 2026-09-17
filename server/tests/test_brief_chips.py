"""
EdgeCDSS — follow-up chips.

The portal's chips send fixed phrasings through /query with the conversation
history, tagged input_mode "chip". The phrasings are read out of the client
itself, so these tests pin the words that ship, not a copy of them.

Two things are pinned:

  1. **A chip cannot move the patient.** A chip is one tap, and its words are
     replayed as history on every later turn. "Pediatric dosing?" would set
     is_pediatric on an adult whose age was never stated — the extractor's
     paediatric word list contains "pediatric" — and a chip carrying a number
     could read as a weight or age contradiction, which is a new patient. So
     every phrasing must leave the context, the boundary detector and the
     non-medical gate exactly where they were.

  2. **Two phrasings reach the path they are for.** "Why that dose?" reaches the
     deterministic provenance gate; "Show the vial math for that dose." reaches
     the which-vial question. The rest go to the generator with the history,
     which is also pinned for one of them.

    cd server && ./run_unit_tests.sh
"""

import os
import pathlib
import re
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402

CLIENT = pathlib.Path(__file__).parent.parent / "static" / "index.html"


def shipped_chips():
    """[(label, phrasing)] exactly as FOLLOW_UP_CHIPS declares them."""
    html = CLIENT.read_text()
    block = html.split("const FOLLOW_UP_CHIPS = [", 1)[1].split("];", 1)[0]
    return re.findall(r"\['([^']+)',\s*'([^']+)'\]", block)


CHIPS = dict(shipped_chips())

RSI_QUERY = "RSI an 80kg male trauma patient ketamine and rocuronium"
RSI_HISTORY = [{"query": RSI_QUERY, "response": "(the RSI card)"}]
# An adult with no stated age: the case where a paediatric word would flip the
# flag, because there is no age to overrule it.
CONTEXT_FIELDS = ("is_pediatric", "age_years", "confirmed_weight_kg",
                  "estimated_weight_kg", "weight_source", "route_preference",
                  "access_state", "boundary_reset_reason")


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def test_the_client_ships_the_six_chips():
    assert list(CHIPS) == ["Why?", "Contraindications", "Vial math", "Pediatric",
                           "What to watch", "Full protocol"]


@pytest.mark.parametrize("label", list(CHIPS))
def test_a_chip_cannot_move_the_patient(label):
    phrasing = CHIPS[label]
    before = oc.rebuild_patient_context_from_history("ok", conversation_history=RSI_HISTORY)
    after = oc.rebuild_patient_context_from_history(phrasing, conversation_history=RSI_HISTORY)
    for f in CONTEXT_FIELDS:
        assert getattr(after, f) == getattr(before, f), \
            f"chip {label!r} changed {f}: {getattr(before, f)!r} -> {getattr(after, f)!r}"
    assert oc.detect_patient_boundary(phrasing, before) is None
    assert oc.is_non_medical_query(phrasing) is False


def test_why_reaches_the_provenance_gate():
    r = oc._query_with_rag_internal(CHIPS["Why?"], _NoRetrieval(),
                                    conversation_history=RSI_HISTORY)
    assert r["source_mode"] == "DOSE_PROVENANCE"
    assert r["response"].startswith("**WHY THIS DOSE**")


def test_vial_math_reaches_the_vial_question():
    r = oc._query_with_rag_internal(CHIPS["Vial math"], _NoRetrieval(),
                                    conversation_history=RSI_HISTORY)
    assert r["source_mode"] == "PRE_GATE"
    assert "vial" in r["response"].lower()


def test_full_protocol_reaches_the_generator_with_the_history(monkeypatch):
    seen = {}

    def fake_chat(system, messages, **kw):
        seen["messages"] = messages
        return "**TLDR**\n- stub"

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    monkeypatch.setattr(oc, "validate_response",
                        lambda *a, **k: {"result": "SAFE", "issues": [], "rationale": "", "safe": True})

    class JtsHit:
        def query(self, *a, **k):
            return {"documents": [["protocol"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.2]]}

    r = oc._query_with_rag_internal(CHIPS["Full protocol"], JtsHit(),
                                    conversation_history=RSI_HISTORY)
    assert r["source_mode"] == "JTS_GROUNDED"
    contents = [m["content"] for m in seen["messages"]]
    assert contents[0] == RSI_QUERY, "the prior turn did not reach the generator"
    assert contents[-1].endswith(CHIPS["Full protocol"])


def test_input_mode_values_are_closed():
    assert oc.INPUT_MODES == ("typed", "voice", "chip")
