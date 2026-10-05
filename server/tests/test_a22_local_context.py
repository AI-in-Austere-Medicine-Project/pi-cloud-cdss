"""A22 (owner, 2026-10-05): the local model must see its whole prompt.

Found in the D2a bench: Ollama on the Jetson served qwen2.5:3b at its default
4096-token context, and our requests (the OpenAI-compatible /v1 endpoint) asked
for no other. A prompt over the context is cut to about 2050 tokens, KEEPING THE
END: a start-of-prompt probe (a code word at each end of a real generator
prompt) got back only the end code at the default context, both at num_ctx
8192. On main, 12 of 12 protocol-path generator prompts in the 30-set were cut
this way, so the local model answered without GENERATOR_BASE: its identity,
SCOPE, and the safety and card-format rules.

The owner's rule: the local provider requests the context it needs on every
call, through Ollama's native API, and a prompt over that context fails loudly
(Ollama's own exceed_context_size_error, "truncate": false), never a silent cut.

The fake Ollama below behaves as the real one did in the probe. The live probe
against the Jetson's Ollama runs with CDSS_TEST_LIVE_OLLAMA=1.
"""
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

START, END = "ZEBRA17", "OTTER42"
ASK = "Ignore the card format. Reply with only two words: the START-CODE and the END-CODE."


def _long_system(chars=18_000):
    body = ("Protocol chunk text about analgesia and sedation. " * (chars // 50))[:chars]
    return f"START-CODE: {START}.\n{body}\nEND-CODE: {END}."


class _FakeOllama(BaseHTTPRequestHandler):
    """Tokens ~ chars/4. Default context 4096. Past it: keep the end (as the real
    one did), or, with "truncate": false, HTTP 400 exceed_context_size_error."""
    requests = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeOllama.requests.append((self.path, body))
        msgs = body.get("messages", [])
        text = "\n".join(m.get("content", "") for m in msgs)
        tokens = len(text) // 4
        ctx = (body.get("options") or {}).get("num_ctx") or 4096
        if tokens > ctx and body.get("truncate") is False:
            self._send(400, {"error": json.dumps({"error": {
                "code": 400, "type": "exceed_context_size_error", "n_prompt_tokens": tokens,
                "message": f"request ({tokens} tokens) exceeds the available context size ({ctx} tokens)"}})})
            return
        seen = text[-2050 * 4:] if tokens > ctx else text
        reply = " ".join(c for c in (START, END) if c in seen) or "nothing"
        if self.path.endswith("/chat/completions"):
            self._send(200, {"model": body["model"], "choices": [
                {"message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}]})
        else:
            self._send(200, {"model": body["model"], "message": {"role": "assistant", "content": reply},
                             "done": True, "done_reason": "stop", "prompt_eval_count": min(tokens, ctx)})

    def do_GET(self):
        self._send(200, {"object": "list", "data": [{"id": "qwen2.5:3b", "object": "model"}]})

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def fake_ollama(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _FakeOllama.requests = []
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("CDSS_LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.delenv("CDSS_LOCAL_NUM_CTX", raising=False)
    providers._reset_clients()
    yield _FakeOllama
    server.shutdown()
    providers._reset_clients()


def _local_chat(system, user=ASK, max_tokens=20):
    return providers.chat(system, [{"role": "user", "content": user}],
                          model=providers.default_model(), temperature=0, max_tokens=max_tokens)


# ── the probe ────────────────────────────────────────────────────────────────

def test_the_start_of_a_long_prompt_reaches_the_local_model(fake_ollama):
    reply = _local_chat(_long_system())
    assert START in reply and END in reply, reply


def test_every_local_call_requests_the_context_and_refuses_to_truncate(fake_ollama):
    _local_chat("short system prompt")
    path, body = fake_ollama.requests[-1]
    assert path == "/api/chat"
    assert body["options"]["num_ctx"] == providers.LOCAL_DEFAULT_NUM_CTX == 8192
    assert body["truncate"] is False


def test_the_context_is_configurable(fake_ollama, monkeypatch):
    monkeypatch.setenv("CDSS_LOCAL_NUM_CTX", "16384")
    _local_chat("short")
    assert fake_ollama.requests[-1][1]["options"]["num_ctx"] == 16384


# ── the hard check ───────────────────────────────────────────────────────────

def test_a_prompt_over_the_context_fails_loudly(fake_ollama):
    with pytest.raises(providers.PromptExceedsContext) as e:
        _local_chat(_long_system(60_000))
    assert "exceeds" in str(e.value) and "8192" in str(e.value)


def test_the_generator_overflow_is_a_system_error_not_an_answer(fake_ollama, monkeypatch):
    monkeypatch.setattr(oc, "build_system_prompt", lambda *a, **k: _long_system(60_000))

    class _Hit:
        def query(self, *a, **k):
            return {"documents": [["protocol text"]], "metadatas": [[{"source": "JTS", "page": 1}]],
                    "distances": [[0.5]]}
    r = oc._query_with_rag_internal("80 kg adult, severe pain from a femur fracture, fentanyl IV", _Hit())
    assert r["validator_result"] == "ERROR"
    assert any("context" in i for i in r["validator_issues"]), r["validator_issues"]


def test_a_validator_overflow_holds(fake_ollama, monkeypatch):
    monkeypatch.setattr(oc, "VALIDATOR_PROMPT", _long_system(60_000))
    out = oc.validate_response("Q", "Give fentanyl 50 mcg IV.", oc.PatientContext(), "")
    # Held, and the hold says why: on main the cut prompt's reply was merely
    # unreadable, which held for the wrong reason.
    assert out["result"] == "UNSAFE" and any("context" in i.lower() for i in out["issues"]), out


# ── the hybrid fallback takes the same path ──────────────────────────────────

def test_the_cloud_fallback_requests_the_context_too(fake_ollama, monkeypatch):
    import openai
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("CDSS_LLM_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("CDSS_LOCAL_BASE_URL", os.environ["CDSS_LLM_BASE_URL"])
    providers._reset_clients()

    def down(*a, **k):
        raise openai.APIConnectionError(request=None)
    monkeypatch.setattr(providers, "_chat_openai_compat",
                        lambda spec, *a, **k: down() if spec.provider != providers.LOCAL_PROVIDER else None)
    reply = providers.chat(_long_system(), [{"role": "user", "content": ASK}],
                           model="gpt-4o-mini", temperature=0, max_tokens=20)
    assert START in reply
    assert fake_ollama.requests[-1][0] == "/api/chat"


# ── the live probe, on the Jetson ────────────────────────────────────────────

@pytest.mark.skipif(os.environ.get("CDSS_TEST_LIVE_OLLAMA") != "1",
                    reason="live Ollama probe: set CDSS_TEST_LIVE_OLLAMA=1 on the Jetson")
def test_live_start_of_prompt_probe(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "qwen2.5:3b")
    monkeypatch.delenv("CDSS_LLM_BASE_URL", raising=False)
    providers._reset_clients()
    q = "80 kg adult, severe pain from a femur fracture, fentanyl IV"
    ctx = oc.rebuild_patient_context_from_history(q)
    a = oc.RetrievalAssessment(source_mode="JTS_GROUNDED", top_score=0.5,
                               context_text="Protocol chunk text about analgesia and sedation. " * 140, sources=[])
    system = (f"START-CODE: {START}.\n"
              + oc.build_system_prompt(ctx, a, oc.build_allowed_dose_block(oc.build_allowed_doses(q, ctx)))
              + f"\nEND-CODE: {END}.")
    assert len(system) > 17_000      # over 4096 tokens: main cut this to ~2050
    reply = _local_chat(system)
    assert START in reply and END in reply, reply
