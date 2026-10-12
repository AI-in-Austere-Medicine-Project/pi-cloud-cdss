"""The portal is local-only under CDSS_LLM_PROVIDER=local (owner, 2026-10-12; v1.1).

The live service was switched to local with the API keys removed, and the
portal said "MODEL: no model available": in local mode /models listed nothing,
because the on-device model is registered only on first use and the menu
listed only providers that authenticate. The owner's spec:
- the picker offers exactly qwen2.5:3b and edgecdss-v3 (on device, via Ollama),
  default from CDSS_LLM_MODEL, no cloud entries;
- the validator is CDSS_VALIDATOR_MODEL for both (D7's rule);
- served answers name their model;
- the service starts clean with no API keys;
- a portal request with no cloud keys and provider=local serves, not errors,
  and the portal path makes no outbound HTTP call.

Outbound calls the portal path could make: a cloud provider's auth check in
/status and /models (when a key is left set), and ElevenLabs voice. In local
mode neither is made: cloud providers are reported off without a call, and
voice is off.
"""
import socket
import subprocess
import sys
import pathlib

import pytest

import openai_client as oc
import providers
import tts
from test_local_llm import (GENERATED_QUERY, NATIVE_CALLS, FakeOpenAI,  # noqa: F401
                            _JtsHit, fake_sdk)

SERVER = pathlib.Path(oc.__file__).parent
ON_DEVICE = {"qwen2.5:3b", "edgecdss-v3"}


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setattr(providers, "_ollama_tags", lambda force=False: set(ON_DEVICE) | {"edgecdss-v1"})


@pytest.fixture
def no_network(monkeypatch):
    """Every outbound connection is recorded and refused."""
    attempts = []

    def refuse(self, address, *a, **k):
        attempts.append(address)
        raise ConnectionRefusedError(f"outbound connection to {address!r} in a local-only test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", lambda address, *a, **k: refuse(None, address))
    return attempts


# ── the picker ───────────────────────────────────────────────────────────────

def test_the_picker_offers_exactly_the_two_on_device_models(local):
    menu = providers.available_models(force=True)
    assert {m["id"] for m in menu} == ON_DEVICE, "exactly the two: no cloud entry, and not every Ollama tag (edgecdss-v1 is installed)"
    assert all(m["provider"] == "local" and m["label"].endswith("(on device)") for m in menu)


def test_no_cloud_entry_even_with_a_key_left_set(local, monkeypatch, no_network):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-left-over-0000")
    menu = providers.available_models(force=True)
    assert {m["provider"] for m in menu} == {"local"}
    status = providers.provider_status(force=True)
    assert status["openai"]["available"] is False and "local" in status["openai"]["detail"].lower()
    assert no_network == [], "a cloud provider was checked over the network in local mode"


@pytest.mark.parametrize("setting, expected", [(None, "qwen2.5:3b"), ("edgecdss-v3", "edgecdss-v3")])
def test_the_default_comes_from_cdss_llm_model(local, monkeypatch, setting, expected):
    if setting:
        monkeypatch.setenv("CDSS_LLM_MODEL", setting)
    assert providers.default_model() == expected


@pytest.mark.parametrize("pick", sorted(ON_DEVICE))
def test_the_validator_is_cdss_validator_model_for_both(local, monkeypatch, pick):
    assert providers.validator_model(pick) == "qwen2.5:3b"
    monkeypatch.setenv("CDSS_VALIDATOR_MODEL", "edgecdss-v3")
    assert providers.validator_model(pick) == "edgecdss-v3"


def test_voice_is_off_in_local_mode(local, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_" + "0" * 40)
    assert tts.voice_available() is False
    assert "local" in tts.config_problem().lower()


# ── a request ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pick, writer", [("", "qwen2.5:3b"), ("edgecdss-v3", "edgecdss-v3")])
def test_a_request_serves_on_the_device_with_no_outbound_call(local, monkeypatch, no_network, pick, writer):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    r = oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit(), model=pick or None)
    assert r["validator_result"] not in ("ERROR",), r.get("validator_issues")
    assert r["model"] == f"local/{writer}" and r["provider"] == "local"
    gen = [c["model"] for c in NATIVE_CALLS if c["system"] != oc.VALIDATOR_PROMPT]
    val = [c["model"] for c in NATIVE_CALLS if c["system"] == oc.VALIDATOR_PROMPT]
    assert gen == [writer] and val == ["qwen2.5:3b"]
    assert no_network == [] and FakeOpenAI.instances == []


# ── the service ──────────────────────────────────────────────────────────────

def test_the_service_starts_clean_with_no_keys_and_says_it_is_local(tmp_path):
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "CDSS_LLM_PROVIDER": "local",
           "CHROMADB_PATH": str(tmp_path / "chroma")}
    pytest.importorskip("chromadb")
    pytest.importorskip("fastapi")
    r = subprocess.run([sys.executable, "-c", "import main"], cwd=SERVER, env=env,
                       capture_output=True, text=True, timeout=180)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-2000:]
    assert "Traceback" not in out
    assert "OpenAI clients initialized" not in out, "local mode announced an OpenAI client"
    assert "LLM provider: local" in out, out[-1000:]


def test_the_portal_path_serves_with_no_outbound_call(local, monkeypatch, no_network):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    pytest.importorskip("chromadb")
    from fastapi.testclient import TestClient
    import main
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(main, "chromadb_client", type("Fake", (), {
        "query": lambda self, *a, **k: _JtsHit().query(),
        "get_collection_count": lambda self: 1})())
    token = "local-only-test"
    monkeypatch.setenv("CDSS_ACCESS_TOKEN", token)
    client = TestClient(main.app)
    models = client.get("/models").json()
    assert {m["id"] for m in models["models"]} == ON_DEVICE and models["default_model"] == "qwen2.5:3b"
    assert client.get("/status").status_code == 200
    body = {"query": GENERATED_QUERY, "device_id": "t", "timestamp": "2026-10-12T00:00:00", "model": "edgecdss-v3"}
    d = client.post("/query", json=body, headers={"X-Access-Token": token}).json()
    assert d["validator_result"] != "ERROR" and d["model"] == "local/edgecdss-v3", d
    assert no_network == [], f"outbound connection attempted: {no_network}"
