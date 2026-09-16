"""
EdgeCDSS — brief-first, at the HTTP boundary.

What the client can rely on: /query carries `brief` and `critical_sections`
on every answer, and they are the pipeline's, passed through untouched.

Requires fastapi and httpx; skipped where they are absent, the same rule as
test_security_patch.py. To run with them:

    PYTHONPATH=../.venv/lib/python3.12/site-packages python3 -m pytest tests/test_brief_first_api.py
"""

import asyncio
import os
import sys
import types

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
httpx = pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
os.environ["CDSS_ACCESS_TOKEN"] = "test-token-not-the-demo-one"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "main" not in sys.modules:
    # main.py builds a ChromaDB client at import. Stubbed exactly as
    # test_security_patch.py stubs it, so either file can import main first.
    _stub = types.ModuleType("embeddings")

    class _StubChroma:
        def get_collection_count(self):
            return 0

        def query(self, *a, **k):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    _stub.ChromaDBClient = _StubChroma
    sys.modules["embeddings"] = _stub

import main  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
QUERY_BODY = {"query": "test", "device_id": "test", "timestamp": "2026-09-16T00:00:00"}


def post_query(body):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.post("/query", json=body, headers=TOKEN)
    return asyncio.run(go())


def test_query_passes_the_brief_through(monkeypatch):
    result = {"response": "**GIVE**\n- x", "brief": "Line one.\nLine two.",
              "critical_sections": ["CONTRAINDICATIONS"], "validator_result": "SAFE"}
    monkeypatch.setattr(main, "query_with_rag", lambda *a, **k: dict(result))
    r = post_query(QUERY_BODY)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["brief"] == "Line one.\nLine two."
    assert d["critical_sections"] == ["CONTRAINDICATIONS"]
    assert d["response"] == "**GIVE**\n- x", "the full response is still served"


def test_a_result_without_a_brief_degrades_to_empty_not_500(monkeypatch):
    monkeypatch.setattr(main, "query_with_rag",
                        lambda *a, **k: {"response": "ok", "validator_result": "SAFE"})
    r = post_query(QUERY_BODY)
    assert r.status_code == 200, r.text
    assert r.json()["brief"] == ""
    assert r.json()["critical_sections"] == []


# ── input_mode ───────────────────────────────────────────────────────────────

def _recording(monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(k)
        return {"response": "ok", "validator_result": "SAFE"}
    monkeypatch.setattr(main, "query_with_rag", fake)
    return calls


def test_the_schema_accepts_chip_and_it_reaches_the_logger(monkeypatch):
    calls = _recording(monkeypatch)
    r = post_query(dict(QUERY_BODY, input_mode="chip"))
    assert r.status_code == 200, r.text
    assert calls[-1]["input_mode"] == "chip"


def test_input_mode_defaults_to_typed(monkeypatch):
    calls = _recording(monkeypatch)
    assert post_query(QUERY_BODY).status_code == 200
    assert calls[-1]["input_mode"] == "typed"


def test_an_unknown_input_mode_is_refused(monkeypatch):
    calls = _recording(monkeypatch)
    r = post_query(dict(QUERY_BODY, input_mode="autopilot"))
    assert r.status_code == 422
    assert not calls
