"""D4 (owner, work order; rulings 2026-10-08): show the deterministic part first.

One request, two events. A client that asks for text/event-stream gets an
"early" event as soon as the pipeline is about to call the model — the header
(the matched protocol, the knowledge source) and the patient strip, nothing
else — and a "final" event with the whole, checked response. Owner's rulings:
the early part is the header and the patient strip only; no dose appears until
the checked final answer. Hard rules (work order): no model-written text with a
number reaches the screen until the free-text dose check has passed on the
complete response; no streaming of partial prose; a held response keeps the
deterministic part and the hold replaces the prose.

A client that does not ask for the stream gets the JSON response as before
(run_tests.sh, the cdss-eval harness, older clients).
"""
import asyncio
import json
import os
import sys
import types

import pytest

pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
os.environ.setdefault("CDSS_ACCESS_TOKEN", "test-token-not-the-demo-one")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if "embeddings" not in sys.modules:
    _stub = types.ModuleType("embeddings")

    class _Chroma:
        def get_collection_count(self):
            return 0

        def query(self, *a, **k):
            return {"documents": [["protocol text about analgesia"]],
                    "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.5]]}
    _stub.ChromaDBClient = _Chroma
    sys.modules["embeddings"] = _stub

import main  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
SSE = dict(TOKEN, Accept="text/event-stream")
GENERATED_Q = "80 kg adult, severe pain from a femur fracture, what should I do"
SAFE = '{"result":"SAFE","issues":[],"rationale":"ok"}'
HELD_DOSE = "**DO THIS**\n1. Give fentanyl 1 mg IV now.\n\n**SOURCE**: General Evidence-Based Medicine"
SERVED_TEXT = "**DO THIS**\n1. Splint the femur and reassess pain.\n\n**SOURCE**: General Evidence-Based Medicine"


class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text about analgesia"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.5]]}


@pytest.fixture
def model(monkeypatch, tmp_path):
    """providers.chat stand-in; records whether the early event had gone out."""
    calls = {"text": SERVED_TEXT, "early_seen_before_generator": None}
    monkeypatch.setattr(main, "chromadb_client", _Retrieval())
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)

    def chat(system, messages, **k):
        if system == oc.VALIDATOR_PROMPT:
            return SAFE
        calls["early_seen_before_generator"] = bool(calls.get("early"))
        return calls["text"]
    monkeypatch.setattr(providers, "chat", chat)
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_MODEL", "CDSS_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return calls


def _post(query, headers):
    body = {"query": query, "device_id": "t", "timestamp": "2026-10-08T00:00:00Z"}

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.post("/query", json=body, headers=headers)
    return asyncio.run(go())


def _events(resp):
    out = []
    for block in resp.text.split("\n\n"):
        if not block.strip():
            continue
        ev = {l.split(":", 1)[0]: l.split(":", 1)[1].strip() for l in block.splitlines() if ":" in l}
        out.append((ev.get("event"), json.loads(ev["data"])))
    return out


def test_a_model_answer_streams_early_then_final(model):
    r = _post(GENERATED_Q, SSE)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r)
    assert [e for e, _ in events] == ["early", "final"]
    early, final = events[0][1], events[1][1]
    assert set(early) == {"query_id", "header", "patient_context"}
    assert early["query_id"] == final["query_id"]
    assert early["patient_context"].get("confirmed_weight_kg") == 80.0
    assert final["response"].startswith("**DO THIS**") or "Splint the femur" in final["response"]


def test_the_early_event_goes_out_before_the_model_is_called(model, monkeypatch):
    real = main._sse_event

    def spy(name, payload):
        if name == "early":
            model["early"] = True
        return real(name, payload)
    monkeypatch.setattr(main, "_sse_event", spy)
    _post(GENERATED_Q, SSE)
    assert model["early_seen_before_generator"] is True


def test_the_early_event_carries_no_dose_and_no_model_text(model):
    early = _events(_post(GENERATED_Q, SSE))[0][1]
    raw = json.dumps(early)
    assert "Splint" not in raw and "fentanyl" not in raw.lower()
    assert "allowed" not in raw.lower() and " mg" not in raw and "mcg" not in raw


def test_a_held_response_never_shows_a_model_written_dose(model):
    model["text"] = HELD_DOSE
    r = _post(GENERATED_Q, SSE)
    events = _events(r)
    assert [e for e, _ in events] == ["early", "final"]
    final = events[1][1]
    assert final["validator_result"] == "UNSAFE"
    for _name, payload in events:
        assert "1 mg IV now" not in payload.get("response", "")
        assert "Give fentanyl 1 mg" not in json.dumps(payload)
    # The deterministic part stays: the patient strip is in the final event.
    assert final["patient_context"].get("confirmed_weight_kg") == 80.0


def test_a_deterministic_card_sends_only_the_final_event(model):
    events = _events(_post("RSI an 80kg male trauma patient ketamine and rocuronium", SSE))
    assert [e for e, _ in events] == ["final"]
    assert events[0][1]["validator_result"] == "DETERMINISTIC_CHECKED"


def test_without_the_stream_header_the_response_is_json_as_before(model):
    r = _post(GENERATED_Q, TOKEN)
    assert r.headers["content-type"].startswith("application/json")
    d = r.json()
    assert "Splint the femur" in d["response"] and d["query_id"]


# ── the client ───────────────────────────────────────────────────────────────

CLIENT = (os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html"))


def test_the_client_asks_for_the_stream_and_keeps_json_working():
    src = open(CLIENT).read()
    q = src[src.index("fetch('/query'"):][:900]
    assert "text/event-stream" in q
    assert "function readQueryResponse" in src
    body = src[src.index("async function readQueryResponse"):][:1800]
    assert "application/json" in body or "r.json()" in body          # older servers
    assert "early" in body and "final" in body


def test_the_client_early_render_shows_no_answer_text():
    src = open(CLIENT).read()
    fn = src[src.index("function earlyHtml"):][:900]
    assert "response" not in fn and "brief" not in fn
