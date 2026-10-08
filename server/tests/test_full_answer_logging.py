"""
EdgeCDSS — D5a: full-answer logging (log schema 14).

Owner, 2026-09-26: log the full answer from now on, so the next dataset comes
from real serving (D5). On main the session log kept only the first 200
characters of what the medic saw (`response_preview`), and nothing at all of
a held answer's model text: #101's held haiku answer could not be read back.

Schema 14 adds:
  response             the full text the medic saw (the hold text when held)
  held_response        the model's own text that the gate held; null when the
                       answer was served or no model wrote it
  full_answer_dropped  null, or why the two fields above were left out: the
                       log directory is over its size cap, or free disk is
                       under its floor. Nothing is deleted; the rest of the
                       entry, preview included, is still written.
Same file, same retention and access rules as the existing query log.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import pathlib
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402


def _log(result, query="q"):
    with tempfile.TemporaryDirectory() as tmp:
        original = oc._LOG_DIR
        oc._LOG_DIR = pathlib.Path(tmp)
        try:
            oc.log_query(query, result)
            (f,) = pathlib.Path(tmp).glob("*.jsonl")
            return json.loads(f.read_text().strip().splitlines()[-1])
        finally:
            oc._LOG_DIR = original


LONG = "**DO THIS**\n" + "\n".join(f"{i}. Step number {i} of a long answer." for i in range(1, 40))


def test_schema_is_16():
    assert oc.LOG_SCHEMA_VERSION == 16  # E1 (schema 16): validator_model_returned; C1 (15): query_id, session_id
    assert _log({"response": "x"})["log_schema"] == 16


def test_a_served_answer_is_logged_in_full():
    entry = _log({"response": LONG, "source_mode": "GENERAL_MEDICAL",
                  "validator_result": "SAFE"})
    assert len(LONG) > 200
    assert entry["response"] == LONG
    assert entry["response_preview"] == LONG[:200], "the preview stays for old tooling"
    assert entry["held_response"] is None
    assert entry["full_answer_dropped"] is None


class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


HELD_MODEL_TEXT = ("**GIVE**\n- Give ketamine 999 mg IV now for the pain.\n\n"
                   "**TLDR**\n- Ketamine 999 mg IV.")


def test_a_held_answer_logs_the_hold_text_and_the_model_text(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda system, messages, **k: (
        '{"result":"SAFE","issues":[],"rationale":"stub"}'
        if "Clinical Safety Validator" in (system or "") else HELD_MODEL_TEXT))
    q = "80kg male, femur fracture, what do I give for pain"
    result = oc._query_with_rag_internal(q, _Retrieval(), conversation_history=[])
    assert result["response"].startswith("Clinical safety hold."), result["response"][:120]
    entry = _log(result, q)
    assert entry["response"] == result["response"]
    assert entry["held_response"] == HELD_MODEL_TEXT


def test_the_held_model_text_never_reaches_the_client(monkeypatch):
    """QueryResponse lists its fields; held_response is a log field only."""
    import main
    assert "held_response" not in main.QueryResponse.model_fields


def test_a_deterministic_card_has_no_model_text():
    entry = _log({"response": LONG, "source_mode": "DETERMINISTIC_PRE_GATE",
                  "validator_result": "DETERMINISTIC_CHECKED"})
    assert entry["response"] == LONG and entry["held_response"] is None


# ── Rotation: the log can't fill the disk ──────────────────────────────────

def test_over_the_directory_cap_the_full_answer_is_dropped_not_the_entry(monkeypatch):
    monkeypatch.setattr(oc, "LOG_DIR_MAX_BYTES", 1)
    entry = _log({"response": LONG})
    assert entry["response"] is None and entry["held_response"] is None
    assert "cap" in entry["full_answer_dropped"]
    assert entry["response_preview"] == LONG[:200]


def test_under_the_free_disk_floor_the_full_answer_is_dropped(monkeypatch):
    import shutil
    monkeypatch.setattr(oc.shutil, "disk_usage",
                        lambda p: shutil._ntuple_diskusage(100, 99, 1))
    entry = _log({"response": LONG})
    assert entry["response"] is None
    assert "disk" in entry["full_answer_dropped"]


def test_nothing_is_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        old = pathlib.Path(tmp) / "cdss_session_2020-01-01.jsonl"
        old.write_text('{"old": true}\n')
        original = oc._LOG_DIR
        oc._LOG_DIR = pathlib.Path(tmp)
        try:
            oc.log_query("q", {"response": LONG})
        finally:
            oc._LOG_DIR = original
        assert old.exists() and old.read_text() == '{"old": true}\n'
