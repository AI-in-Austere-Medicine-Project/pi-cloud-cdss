"""C1 (owner, work order; feedback review §0 and §7): the feedback instrument.

What the review found: /feedback stored the query and a 200-character preview
and nothing else, so mid-conversation reports ("90 kg", "Ok now his pressure
is getting soft 90/50") could not be reproduced; device_id was minted per page
load, so nothing grouped a medic's reports; the `comment` field had no UI and
was empty in 48 of 48 reports.

The work order:
  - a persistent session id (sessionStorage, try/catch);
  - /feedback carries the query id, the conversation history used, model,
    provider, validator_result and source_mode;
  - the comment field actually posts;
  - tests for the schema.
"""
import asyncio
import json
import os
import pathlib
import re
import sys
import tempfile
import types

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
httpx = pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
os.environ.setdefault("CDSS_ACCESS_TOKEN", "test-token-not-the-demo-one")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "embeddings" not in sys.modules:
    _stub = types.ModuleType("embeddings")

    class _StubChroma:
        def get_collection_count(self):
            return 0

        def query(self, *a, **k):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    _stub.ChromaDBClient = _StubChroma
    sys.modules["embeddings"] = _stub

import main  # noqa: E402
import openai_client as oc  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
CLIENT = (pathlib.Path(__file__).parent.parent / "static" / "index.html").read_text()

HISTORY = [{"query": "head injury from a fall, GCS 7, BP 118/76",
            "response": "Recorded. Reassess.", "ts": "2026-10-05T10:00:00Z"}]
FULL_REPORT = {
    "query": "90 kg", "response": "R" * 600, "feedback_type": "flagged",
    "severity": "significant", "issues": ["Held or refused something safe"],
    "suggestion": "should have given the drip rate", "comment": "voice was fine",
    "device_id": "web-abc", "session_id": "s-1234", "query_id": "q-5678",
    "conversation_history": HISTORY, "model": "openai/gpt-4o-mini",
    "provider": "openai", "validator_result": "UNSAFE", "source_mode": "GENERAL_MEDICAL",
}


def call(method, path, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


@pytest.fixture
def feedback_log(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "feedback.log")
        monkeypatch.setattr(main, "FEEDBACK_LOG", path)
        yield path


def _records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# ── /feedback: the schema ────────────────────────────────────────────────────

def test_feedback_stores_the_full_context(feedback_log):
    r = call("POST", "/feedback", json=FULL_REPORT, headers=TOKEN)
    assert r.status_code == 200, r.text
    rec = _records(feedback_log)[0]
    for k in ("session_id", "query_id", "conversation_history", "model", "provider",
              "validator_result", "source_mode", "comment", "suggestion"):
        assert rec[k] == FULL_REPORT[k], k


def test_feedback_stores_the_whole_response_not_only_a_preview(feedback_log):
    call("POST", "/feedback", json=FULL_REPORT, headers=TOKEN)
    rec = _records(feedback_log)[0]
    assert rec["response"] == FULL_REPORT["response"]
    assert rec["response_preview"] == FULL_REPORT["response"][:200]   # tooling reads it


def test_an_old_client_payload_is_still_accepted(feedback_log):
    body = {"query": "q", "response": "r", "feedback_type": "appropriate"}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 200
    rec = _records(feedback_log)[0]
    assert rec["session_id"] == "" and rec["query_id"] == "" and rec["conversation_history"] == []


@pytest.mark.parametrize("field, value", [
    ("session_id", "s" * 65), ("query_id", "q" * 65), ("model", "m" * 129),
    ("provider", "p" * 65), ("validator_result", "v" * 65), ("source_mode", "x" * 65),
    ("conversation_history", [{"query": "q"}] * (main.MAX_HISTORY_TURNS + 1)),
])
def test_the_new_fields_are_bounded(feedback_log, field, value):
    body = {**FULL_REPORT, field: value}
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 422


def test_the_history_is_bounded_in_bytes_too(feedback_log):
    big = [{"query": "x" * 4000, "response": "y" * 4000}] * 40
    body = {**FULL_REPORT, "conversation_history": big}
    assert len(json.dumps(big)) > main.MAX_HISTORY_BYTES
    assert call("POST", "/feedback", json=body, headers=TOKEN).status_code == 422


def test_the_summary_carries_the_answer_metadata_but_not_the_history(feedback_log):
    call("POST", "/feedback", json=FULL_REPORT, headers=TOKEN)
    e = call("GET", "/feedback/summary", headers=TOKEN).json()["entries"][0]
    for k in ("session_id", "query_id", "model", "provider", "validator_result", "source_mode"):
        assert e[k] == FULL_REPORT[k], k
    assert "conversation_history" not in e and "ip" not in e


# ── /query: the ids the report refers to ─────────────────────────────────────

def test_query_response_and_request_declare_the_new_fields():
    assert "query_id" in main.QueryResponse.model_fields
    assert "source_mode" in main.QueryResponse.model_fields
    assert "session_id" in main.QueryRequest.model_fields


def test_each_query_gets_an_id_that_the_log_line_carries(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    r1 = oc.query_with_rag("what is the weather in Austin today", sys.modules["embeddings"].ChromaDBClient(),
                           session_id="s-1234")
    r2 = oc.query_with_rag("what is the weather in Austin today", sys.modules["embeddings"].ChromaDBClient(),
                           session_id="s-1234")
    assert r1["query_id"] and r2["query_id"] and r1["query_id"] != r2["query_id"]
    lines = [json.loads(l) for f in tmp_path.glob("*.jsonl") for l in f.read_text().splitlines()]
    assert [l["query_id"] for l in lines] == [r1["query_id"], r2["query_id"]]
    assert all(l["session_id"] == "s-1234" for l in lines)
    assert all(l["log_schema"] == 16 for l in lines)


# ── the client ───────────────────────────────────────────────────────────────

def test_the_client_keeps_a_session_id_in_session_storage_with_a_fallback():
    m = re.search(r"function sessionIdOf\(\)\s*\{(.*?)\n\}", CLIENT, re.S)
    assert m, "no sessionIdOf()"
    body = m.group(1)
    assert "sessionStorage" in body and "try" in body and "catch" in body


def test_the_client_sends_the_session_id_with_every_query():
    query_call = CLIENT[CLIENT.index("fetch('/query'"):][:900]
    assert "session_id: sessionId" in query_call


def test_the_report_carries_the_answer_context():
    for k in ("query_id", "session_id", "conversation_history", "model", "provider",
              "validator_result", "source_mode", "comment"):
        assert re.search(r"\b" + k + r"\b", CLIENT[CLIENT.index("function feedbackContext"):][:1200]) \
            or re.search(r"\b" + k + r":", CLIENT[CLIENT.index("function openFlagPanel"):][:2600]), k


def test_the_flag_panel_has_a_comment_box_that_posts():
    panel = CLIENT[CLIENT.index("function openFlagPanel"):][:2600]
    assert "comment" in panel and panel.count("<textarea") == 2


def test_a_refused_report_is_not_shown_as_recorded():
    post = CLIENT[CLIENT.index("async function postFeedback"):][:700]
    assert "r.ok" in post or "res.ok" in post
