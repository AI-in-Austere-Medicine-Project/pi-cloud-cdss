"""V3 follow-up: Kokoro is loaded and warmed at service start.

Owner, 2026-10-27: "Warm-up: load Kokoro and synthesise a short sentence at
service start, so first listen after a restart isn't 6 s. Test pins
voice_device gpu within 30 s of start."

The first tests use a stand-in engine (no model). The last starts a real
server on the real model and GPU, and runs only with CDSS_TEST_KOKORO_GPU=1
on the Jetson.

    cd server && ./run_unit_tests.sh
"""
import os
import pathlib
import socket
import subprocess
import sys
import time
import types
import urllib.request
import json

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")
from fastapi.testclient import TestClient  # noqa: E402

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
import tts  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
START_LIMIT_S = 30


class _GpuEngine:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def create(self, text, voice, speed=1.0, lang="en-us", **k):
        import numpy as np
        self.calls.append(text)
        if self.fail:
            raise RuntimeError("CUDA exploded")
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def model_files(monkeypatch, tmp_path):
    (tmp_path / tts.MODEL_FILE).write_bytes(b"x")
    (tmp_path / tts.VOICES_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))
    monkeypatch.setattr(tts, "_ENGINE", None)
    monkeypatch.setattr(tts, "_DEVICE", None)
    monkeypatch.setattr(tts, "_DEVICE_NOTE", "")
    monkeypatch.delenv("CDSS_KOKORO_WARMUP", raising=False)


def _on_gpu(monkeypatch, eng):
    def load():
        tts._DEVICE = "gpu"
        return eng
    monkeypatch.setattr(tts, "_load_engine", load)


def _device_after_start(client, limit=START_LIMIT_S):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        dev = client.get("/status", headers=TOKEN).json()["voice_device"]
        if dev["device"] != "not loaded":
            return dev, time.monotonic() - t0
        time.sleep(0.05)
    return client.get("/status", headers=TOKEN).json()["voice_device"], limit


def test_service_start_loads_and_warms_the_voice_on_the_gpu(model_files, monkeypatch):
    eng = _GpuEngine()
    _on_gpu(monkeypatch, eng)
    with TestClient(main.app) as client:
        dev, waited = _device_after_start(client)
        assert dev["device"] == "gpu" and waited < START_LIMIT_S
        t0 = time.monotonic()
        while not eng.calls and time.monotonic() - t0 < START_LIMIT_S:
            time.sleep(0.05)
    assert eng.calls == [tts.WARM_UP_TEXT]


def test_the_service_answers_while_the_voice_warms(model_files, monkeypatch):
    import threading
    gate = threading.Event()
    eng = _GpuEngine()

    def slow_load():
        gate.wait(10)
        tts._DEVICE = "gpu"
        return eng
    monkeypatch.setattr(tts, "_load_engine", slow_load)
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/status", headers=TOKEN).json()["voice_device"]["device"] == "not loaded"
        gate.set()
        dev, _ = _device_after_start(client)
        assert dev["device"] == "gpu"


def test_a_failed_warm_up_ends_on_the_cpu_and_the_service_runs(model_files, monkeypatch):
    # A GPU synthesis failure in the warm-up is the same as in a listen: the
    # model moves to the CPU, with the reason in /status.
    _on_gpu(monkeypatch, _GpuEngine(fail=True))
    monkeypatch.setattr(tts, "_build_engine", lambda providers: (_GpuEngine(), list(providers)))
    with TestClient(main.app) as client:
        t0 = time.monotonic()
        while time.monotonic() - t0 < START_LIMIT_S:
            dev = client.get("/status", headers=TOKEN).json()["voice_device"]
            if dev["device"] == "cpu":
                break
            time.sleep(0.05)
        assert dev["device"] == "cpu" and "synthesis on the GPU failed" in dev["note"]
        assert client.get("/health").status_code == 200


def test_no_warm_up_when_voice_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))      # no model files
    monkeypatch.setattr(tts, "_ENGINE", None)
    monkeypatch.setattr(tts, "_DEVICE", None)
    monkeypatch.setattr(tts, "_load_engine", lambda: pytest.fail("loaded a voice that is not configured"))
    with TestClient(main.app) as client:
        time.sleep(0.3)
        assert client.get("/status", headers=TOKEN).json()["voice_device"]["device"] == "not loaded"


def test_warm_up_can_be_turned_off(model_files, monkeypatch):
    monkeypatch.setenv("CDSS_KOKORO_WARMUP", "0")
    monkeypatch.setattr(tts, "_load_engine", lambda: pytest.fail("warmed with CDSS_KOKORO_WARMUP=0"))
    with TestClient(main.app) as client:
        time.sleep(0.3)
        assert client.get("/status", headers=TOKEN).json()["voice_device"]["device"] == "not loaded"


# ── On the Jetson: the real model, the real GPU ─────────────────────────────

@pytest.mark.skipif(os.getenv("CDSS_TEST_KOKORO_GPU") != "1",
                    reason="set CDSS_TEST_KOKORO_GPU=1 on the Jetson (onnxruntime-gpu, model files, render group)")
def test_a_real_server_has_the_voice_on_the_gpu_within_30_s(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    token = "warmup-test-token"
    env = dict(os.environ, CDSS_ACCESS_TOKEN=token, CDSS_LLM_PROVIDER="local",
               CDSS_LOG_DIR=str(tmp_path))
    env.pop("CDSS_KOKORO_WARMUP", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                             "--port", str(port)], cwd=HERE.parent, env=env,
                            stdout=open(tmp_path / "server.log", "w"), stderr=subprocess.STDOUT)
    t0, dev = time.monotonic(), None
    try:
        while time.monotonic() - t0 < START_LIMIT_S:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/status",
                                             headers={"X-Access-Token": token})
                dev = json.load(urllib.request.urlopen(req, timeout=2))["voice_device"]
                if dev["device"] != "not loaded":
                    break
            except OSError:
                pass
            time.sleep(0.25)
        took = time.monotonic() - t0
    finally:
        proc.terminate()
        proc.wait(15)
    log = (tmp_path / "server.log").read_text()
    assert dev and dev["device"] == "gpu", (dev, log[-2000:])
    assert took < START_LIMIT_S, (took, log[-2000:])
