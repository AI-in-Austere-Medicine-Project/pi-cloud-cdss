"""V1: voice latency baseline, the instrumentation (no behaviour change).

Owner, 2026-10-25: "Instrument the pipeline with timestamps at: request
received, pre-gate done, retrieval done, doses built, LLM first token, LLM
last token, validator done, response sent. Log them per turn in the session
log (schema bump, migration, test). Add TTS timing on the portal's 'listen'
path: text sent, first audio, audio end. ... Do not optimise anything."

    cd server && ./run_unit_tests.sh
"""
import asyncio
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import types

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
httpx = pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
os.environ.setdefault("CDSS_ACCESS_TOKEN", "test-token-not-the-demo-one")
HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

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
import providers  # noqa: E402

sys.path.insert(0, str(HERE.parent / "tools"))
import migrate_session_log as mig  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
STAGES = ["request_received", "pre_gate_done", "retrieval_done", "doses_built",
          "llm_first_token", "llm_last_token", "validator_done", "response_sent"]
VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
CARD_QUERY = "failed intubation failed igel patient desaturating"     # the CICO card
MODEL_QUERY = "how do I reassess a splinted forearm fracture"


class _JtsHit:
    def get_collection_count(self):
        return 1

    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def call(method, path, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


@pytest.fixture
def logdir(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(main, "chromadb_client", _JtsHit(), raising=False)

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        # As Ollama reports it: the model's own generation time.
        providers._TIMING.set({"eval_s": 0.0001, "first_token_source": "ollama_eval_duration"})
        return "**DO THIS**\n1. Reassess distal pulses and capillary refill."
    monkeypatch.setattr(providers, "chat", chat)
    return tmp_path


def _q(query):
    return {"query": query, "device_id": "test", "timestamp": "2026-10-25T00:00:00"}


def _lines(path):
    return [json.loads(l) for f in sorted(path.glob("cdss_session_*.jsonl"))
            for l in f.read_text().splitlines() if l.strip()]


# ── Schema 17 ───────────────────────────────────────────────────────────────

def test_the_schema_is_17():
    assert oc.LOG_SCHEMA_VERSION == 17


def test_a_model_answer_logs_every_stage_in_order(logdir):
    r = call("POST", "/query", json=_q(MODEL_QUERY), headers=TOKEN)
    assert r.status_code == 200, r.text
    (line,) = _lines(logdir)
    assert line["log_schema"] == 17
    t = line["timings"]
    assert list(t)[:8] == STAGES
    assert t["request_received"] == 0.0
    got = [t[s] for s in STAGES]
    assert all(v is not None for v in got), t
    assert got == sorted(got), t
    assert t["origin"] == "http"


def test_a_card_answer_logs_no_retrieval_doses_model_or_validator(logdir):
    r = call("POST", "/query", json=_q(CARD_QUERY), headers=TOKEN)
    assert r.json()["source_mode"] == "DETERMINISTIC_PRE_GATE"
    (line,) = _lines(logdir)
    t = line["timings"]
    for s in ("retrieval_done", "doses_built", "llm_first_token", "llm_last_token",
              "validator_done"):
        assert s in t and t[s] is None, (s, t)
    assert t["pre_gate_done"] is not None and t["response_sent"] >= t["pre_gate_done"]


def test_the_event_stream_path_logs_response_sent_too(logdir):
    r = call("POST", "/query", json=_q(MODEL_QUERY),
             headers={**TOKEN, "Accept": "text/event-stream"})
    assert r.status_code == 200 and "event: final" in r.text
    (line,) = _lines(logdir)
    assert line["timings"]["response_sent"] is not None
    assert line["timings"]["response_sent"] >= line["timings"]["validator_done"]


def test_a_direct_caller_still_logs_at_return_with_no_response_sent(logdir):
    oc.query_with_rag(MODEL_QUERY, _JtsHit())
    (line,) = _lines(logdir)
    t = line["timings"]
    assert t["origin"] == "direct" and t["response_sent"] is None
    assert t["validator_done"] is not None


def test_the_timer_changes_nothing_in_the_answer(logdir):
    """No behaviour change: the same question, timed and untimed, gives the
    same response and verdict."""
    direct = oc.query_with_rag(MODEL_QUERY, _JtsHit())
    http = call("POST", "/query", json=_q(MODEL_QUERY), headers=TOKEN).json()
    assert http["response"] == direct["response"]
    assert http["validator_result"] == direct["validator_result"]
    assert http["source_mode"] == direct["source_mode"]


# ── LLM first token, from Ollama's own eval time ────────────────────────────

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_local_model_first_token_comes_from_its_eval_duration(monkeypatch):
    body = {"model": "qwen2.5:3b", "message": {"content": "ok"}, "done": True,
            "done_reason": "stop", "eval_count": 40, "eval_duration": 2_000_000_000,
            "prompt_eval_duration": 500_000_000, "load_duration": 1_000_000}
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: _Resp(json.dumps(body).encode()))
    spec = providers.local_model_spec("qwen2.5:3b")
    providers._chat_local_native(spec, "sys", [{"role": "user", "content": "q"}], 0.2, 50)
    timing = providers.last_chat_timing()
    assert timing["first_token_source"] == "ollama_eval_duration"
    assert timing["eval_s"] == pytest.approx(2.0)


def test_a_reply_with_no_eval_time_has_no_first_token(monkeypatch):
    body = {"model": "qwen2.5:3b", "message": {"content": "ok"}, "done": True}
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: _Resp(json.dumps(body).encode()))
    spec = providers.local_model_spec("qwen2.5:3b")
    providers._chat_local_native(spec, "sys", [{"role": "user", "content": "q"}], 0.2, 50)
    assert providers.last_chat_timing()["first_token_source"] is None


def test_the_ollama_request_is_unchanged(monkeypatch):
    """Measured from the reply, not by streaming: the request body is as before."""
    sent = {}

    def urlopen(req, timeout=None):
        sent.update(json.loads(req.data))
        return _Resp(json.dumps({"message": {"content": "ok"}, "done": True}).encode())
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    providers._chat_local_native(providers.local_model_spec("qwen2.5:3b"), "s",
                                 [{"role": "user", "content": "q"}], 0.2, 50)
    assert sent["stream"] is False and set(sent) == {"model", "messages", "stream",
                                                     "truncate", "options"}


# ── Migration ───────────────────────────────────────────────────────────────

def test_migration_adds_null_timings_and_keeps_the_original_schema(tmp_path):
    src = tmp_path / "in.jsonl"
    rows = [{"ts": "a", "query": "pre-v4.1, no schema"},
            {"ts": "b", "log_schema": 16, "query": "q16"},
            {"ts": "c", "log_schema": 17, "query": "q17",
             "timings": {s: 1.0 for s in STAGES}}]
    src.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    out = tmp_path / "out.jsonl"
    stats = mig.migrate(src, out)
    got = [json.loads(l) for l in out.read_text().splitlines()[:3]]
    assert out.read_text().splitlines()[3] == "not json"
    assert [g["log_schema"] for g in got] == [17, 17, 17]
    assert got[0]["timings"] is None and got[0]["migrated_from_schema"] is None
    assert got[1]["timings"] is None and got[1]["migrated_from_schema"] == 16
    assert got[2] == rows[2]
    assert stats == {"migrated": 2, "already_current": 1, "unparsed": 1}


def test_migration_never_writes_in_place(tmp_path):
    src = tmp_path / "in.jsonl"
    src.write_text(json.dumps({"log_schema": 16}) + "\n")
    with pytest.raises(ValueError):
        mig.migrate(src, src)


# ── TTS timing on the listen path ───────────────────────────────────────────

@pytest.fixture
def tts_log(monkeypatch, tmp_path):
    monkeypatch.setattr(oc, "_LOG_DIR", tmp_path)
    return tmp_path


def test_speak_timing_is_logged_beside_the_session_log(tts_log):
    rec = {"query_id": "q-1", "session_id": "s-1", "text_chars": 120, "synth_ms": 180,
           "text_sent_to_response_ms": 250.0, "first_audio_ms": 300.0,
           "audio_end_ms": 1200.0, "outcome": "ended"}
    r = call("POST", "/speak/timing", json=rec, headers=TOKEN)
    assert r.status_code == 200, r.text
    (f,) = list(tts_log.glob("cdss_tts_timing_*.jsonl"))
    (line,) = [json.loads(l) for l in f.read_text().splitlines()]
    assert line["tts_log_schema"] == 1
    assert {k: line[k] for k in rec} == rec
    assert not list(tts_log.glob("cdss_session_*.jsonl")), "not mixed into the query log"


def test_speak_timing_needs_the_token(tts_log):
    assert call("POST", "/speak/timing", json={"outcome": "ended"}).status_code in (401, 403)


def test_speak_returns_its_synthesis_time(monkeypatch):
    async def synth(text):
        return b"ID3"
    monkeypatch.setattr(main.tts, "synthesize", synth)
    r = call("POST", "/speak", json={"text": "hello"}, headers=TOKEN)
    assert r.status_code == 200
    assert float(r.headers["X-Synth-Ms"]) >= 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_portal_times_text_sent_first_audio_and_audio_end():
    proc = subprocess.run(["node", str(HERE / "tts_timing_harness.js"),
                           str(HERE.parent / "static" / "index.html")],
                          capture_output=True, text=True, timeout=60)
    calls = json.loads(proc.stdout)
    assert not isinstance(calls, dict), calls
    assert [c["url"] for c in calls] == ["/speak", "/speak/timing"]
    t = calls[1]["body"]
    # The stub clock: /speak answers 250 ms after it is sent, the blob 10 ms
    # later, audio starts 40 ms after play() and ends 900 ms after that.
    assert t["query_id"] == "q-42" and t["session_id"]
    assert t["text_sent_to_response_ms"] == 250
    assert t["first_audio_ms"] == 300
    assert t["audio_end_ms"] == 1200
    assert t["synth_ms"] == 180 and t["outcome"] == "ended"
    assert t["text_chars"] == len("fentanyl 50 mcg IV")
