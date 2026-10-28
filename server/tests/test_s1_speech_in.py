"""S1: speech in. whisper.cpp on the Jetson, /transcribe, push to talk.

Owner, 2026-10-27: "whisper.cpp on the Jetson (base.en to start, weights on
disk, no network), a push-to-talk button in the portal that records while
held and sends audio to a new /transcribe endpoint; transcript shown verbatim
in the question box before anything acts on it; the medic presses send."

/transcribe takes 16-bit mono 16 kHz PCM WAV (the portal makes exactly that)
and answers {"text", "audio_ms", "transcribe_ms", "device"}. It only
transcribes: nothing is queried, logged as a turn, or sent anywhere. Offline,
with a stand-in model (no whisper, no weights, no GPU).

    cd server && ./run_unit_tests.sh
"""
import asyncio
import io
import os
import pathlib
import struct
import sys
import time
import types
import wave

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed; endpoint tests cannot run")
httpx = pytest.importorskip("httpx", reason="httpx is not installed; endpoint tests cannot run")
np = pytest.importorskip("numpy")

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
import stt  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}
WAV = {"Content-Type": "audio/wav"}


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeWhisper:
    """pywhispercpp's Model.transcribe(np.ndarray) -> segments."""

    def __init__(self, segments=(" Eighty kilo adult,", " cefazolin dose?"), fail=False):
        self.segments, self.fail, self.heard = list(segments), fail, []

    def transcribe(self, audio, **k):
        self.heard.append(audio)
        if self.fail:
            raise RuntimeError("ggml_cuda: out of memory")
        return [_Seg(t) for t in self.segments]


@pytest.fixture
def whisper(monkeypatch, tmp_path):
    (tmp_path / stt.MODEL_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_WHISPER_DIR", str(tmp_path))
    monkeypatch.delenv("CDSS_TRANSCRIBE_MAX_S", raising=False)
    monkeypatch.setattr(stt, "_installed", lambda: True)
    monkeypatch.setattr(stt, "_MODEL", None)
    monkeypatch.setattr(stt, "_DEVICE", None)
    fake = _FakeWhisper()
    monkeypatch.setattr(stt, "_build_model", lambda: (fake, "gpu"))
    return fake


def wav(seconds=1.0, rate=16000, channels=1, width=2, value=16384):
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        if width == 2:
            w.writeframes(struct.pack(f"<{n * channels}h", *([value] * n * channels)))
        else:
            w.writeframes(bytes([128]) * n * channels)
    return buf.getvalue()


def call(method, path, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


def post(body, headers=None):
    return call("POST", "/transcribe", content=body, headers={**TOKEN, **WAV, **(headers or {})})


# ── the transcript ──────────────────────────────────────────────────────────

def test_the_transcript_is_whispers_text_verbatim(whisper):
    r = post(wav())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["text"] == "Eighty kilo adult, cefazolin dose?"
    assert d["device"] == "gpu" and d["audio_ms"] == 1000.0 and d["transcribe_ms"] >= 0


def test_numbers_and_units_are_not_rewritten(whisper):
    whisper.segments = [" Give 50 mcg fentanyl IV,", " q5 min."]
    assert post(wav()).json()["text"] == "Give 50 mcg fentanyl IV, q5 min."


def test_whisper_hears_16k_float_samples_from_the_pcm(whisper):
    post(wav(seconds=0.5, value=16384))
    (audio,) = whisper.heard
    assert audio.dtype == np.float32 and audio.shape == (8000,)
    assert np.allclose(audio, 0.5)


def test_silence_is_an_empty_transcript_not_an_error(whisper):
    whisper.segments = []
    r = post(wav())
    assert r.status_code == 200 and r.json()["text"] == ""


def test_whispers_silence_marker_is_not_a_transcript(whisper):
    # Real whisper.cpp base.en, on 1 s of zeros, wrote "[BLANK_AUDIO]". That is
    # whisper saying it heard nothing, not words; it must not land in the box.
    whisper.segments = [" [BLANK_AUDIO]"]
    r = post(wav())
    assert r.status_code == 200 and r.json()["text"] == ""


def test_a_non_speech_segment_is_dropped_and_the_words_kept_verbatim(whisper):
    whisper.segments = [" [MUSIC]", " 80 kg adult,", " cefazolin dose?"]
    assert post(wav()).json()["text"] == "80 kg adult, cefazolin dose?"


def test_brackets_inside_spoken_words_are_left_alone(whisper):
    whisper.segments = [" Cefazolin [two grams] dose?"]
    assert post(wav()).json()["text"] == "Cefazolin [two grams] dose?"


# ── what it takes, and what it refuses ──────────────────────────────────────

def test_a_token_is_required(whisper):
    r = call("POST", "/transcribe", content=wav(), headers=WAV)
    assert r.status_code == 401
    assert whisper.heard == []


@pytest.mark.parametrize("body, why", [
    (b"not a wav at all", "WAV"),
    (wav(rate=44100), "16000"),
    (wav(channels=2), "mono"),
    (wav(width=1), "16-bit"),
    (wav(seconds=0), "no audio"),
])
def test_anything_but_16k_mono_pcm16_is_refused_with_the_reason(whisper, body, why):
    r = post(body)
    assert r.status_code == 400, r.text
    assert why in r.json()["detail"]
    assert whisper.heard == []


def test_audio_over_the_limit_is_refused_not_cut(whisper, monkeypatch):
    monkeypatch.setenv("CDSS_TRANSCRIBE_MAX_S", "2")
    r = post(wav(seconds=3))
    assert r.status_code == 413 and "2 s" in r.json()["detail"]
    assert whisper.heard == []


def test_the_default_limit_is_30_s(whisper):
    assert post(wav(seconds=29.5)).status_code == 200
    assert post(wav(seconds=31)).status_code == 413


# ── not configured, and failing ─────────────────────────────────────────────

def test_no_weights_is_503_with_the_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("CDSS_WHISPER_DIR", str(tmp_path))      # empty
    monkeypatch.setattr(stt, "_installed", lambda: True)
    monkeypatch.setattr(stt, "_MODEL", None)
    monkeypatch.setattr(stt, "_build_model", lambda: pytest.fail("loaded with no weights"))
    r = post(wav())
    assert r.status_code == 503 and stt.MODEL_FILE in r.json()["detail"]


def test_no_whisper_package_is_503_with_the_reason(monkeypatch, tmp_path):
    (tmp_path / stt.MODEL_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_WHISPER_DIR", str(tmp_path))
    monkeypatch.setattr(stt, "_installed", lambda: False)
    monkeypatch.setattr(stt, "_MODEL", None)
    r = post(wav())
    assert r.status_code == 503 and "install_whisper.sh" in r.json()["detail"]


def test_a_failed_transcription_is_503_with_the_reason(whisper):
    whisper.fail = True
    r = post(wav())
    assert r.status_code == 503 and "out of memory" in r.json()["detail"]


def test_status_reports_speech_in(whisper, monkeypatch):
    monkeypatch.setattr(main.providers, "provider_status", lambda: {})
    monkeypatch.setattr(main.providers, "available_models", lambda: [])
    before = call("GET", "/status", headers=TOKEN).json()["speech_in"]
    assert before["available"] is True and before["device"] == "not loaded"
    assert before["model"] == stt.MODEL_FILE
    post(wav())
    after = call("GET", "/status", headers=TOKEN).json()["speech_in"]
    assert after["device"] == "gpu" and after["detail"] == ""


# ── nothing acts on the transcript ──────────────────────────────────────────

def test_transcribing_asks_nothing_and_logs_no_turn(whisper, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "query_with_rag", lambda *a, **k: pytest.fail("a transcript was queried"))
    monkeypatch.setattr(main.openai_client, "_LOG_DIR", tmp_path / "logs")
    assert post(wav()).status_code == 200
    logs = tmp_path / "logs"
    assert not logs.exists() or not any(logs.glob("cdss_session_*.jsonl"))


# ── loaded at service start, with the voice ─────────────────────────────────

def test_service_start_loads_whisper(whisper, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("CDSS_KOKORO_WARMUP", "0")
    monkeypatch.delenv("CDSS_WHISPER_WARMUP", raising=False)
    with TestClient(main.app) as client:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 30:
            if client.get("/status", headers=TOKEN).json()["speech_in"]["device"] == "gpu":
                break
            time.sleep(0.05)
        assert client.get("/status", headers=TOKEN).json()["speech_in"]["device"] == "gpu"
    assert len(whisper.heard) == 1, "one warm-up transcription"


# ── the portal: push to talk ────────────────────────────────────────────────

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
PORTAL = (HERE.parent / "static" / "index.html").read_text(encoding="utf-8")


def _ptt(scenario):
    proc = subprocess.run(["node", str(HERE / "stt_ptt_harness.js"),
                           str(HERE.parent / "static" / "index.html"), scenario],
                          capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout)
    assert "error" not in out, out
    return out


def _wav_header(byte_list):
    h = bytes(byte_list)
    assert h[:4] == b"RIFF" and h[8:12] == b"WAVE"
    channels, rate = struct.unpack("<HI", h[22:28])
    bits = struct.unpack("<H", h[34:36])[0]
    data_len = struct.unpack("<I", h[40:44])[0]
    return channels, rate, bits, data_len


def test_the_portal_has_a_push_to_talk_button_beside_send():
    row = PORTAL[PORTAL.index('<div id="inputrow">'):PORTAL.index('<div id="opts">')]
    assert 'id="talk"' in row and 'id="send"' in row


@needs_node
def test_holding_records_and_releasing_sends_16k_mono_wav_to_transcribe():
    out = _ptt("ok")
    assert out["recording"] != out["button"], "the button shows it is recording while held"
    (t,) = [c for c in out["calls"] if c["url"] == "/transcribe"]
    assert t["headers"]["Content-Type"] == "audio/wav" and "X-Access-Token" in t["headers"]
    channels, rate, bits, data_len = _wav_header(t["body"])
    assert (channels, rate, bits) == (1, 16000, 16)
    # 12 blocks of 4096 at 48 kHz = 49,152 samples -> 16,384 at 16 kHz.
    assert data_len == 16384 * 2 and t["bytes"] == 44 + data_len
    assert out["tracksStopped"] == 1, "the microphone is released"


@needs_node
def test_the_transcript_lands_in_the_question_box_and_nothing_is_sent():
    out = _ptt("ok")
    assert out["box"] == "Eighty kilo adult, cefazolin dose?"
    assert [c["url"] for c in out["calls"]] == ["/transcribe"], "the medic presses send, not the portal"
    assert out["focused"] >= 1 and out["disabled"] is False


@needs_node
def test_a_transcript_is_added_after_what_is_already_typed():
    out = _ptt("append")
    assert out["box"] == "80 kg adult, Eighty kilo adult, cefazolin dose?"


@needs_node
def test_send_asks_the_box_as_it_stands_marked_voice():
    out = _ptt("send")
    (query,) = [c for c in out["calls"] if c["url"] == "/query"]
    assert query["body"]["query"] == "Eighty kilo adult, cefazolin dose?"
    assert query["body"]["input_mode"] == "voice"


@needs_node
def test_a_tap_is_not_a_recording():
    out = _ptt("short")
    assert out["calls"] == [] and out["box"] == ""
    assert "hold" in out["note"].lower()


@needs_node
def test_no_microphone_says_so_and_sends_nothing():
    out = _ptt("denied")
    assert out["calls"] == [] and "microphone" in out["note"].lower()
    assert out["disabled"] is False


@needs_node
def test_a_failed_transcription_says_why_and_leaves_the_box_alone():
    out = _ptt("error")
    assert out["box"] == "" and "out of memory" in out["note"]
    assert [c["url"] for c in out["calls"]] == ["/transcribe"]


# ── On the Jetson: the real whisper.cpp, the real GPU ───────────────────────

@pytest.mark.skipif(os.getenv("CDSS_TEST_WHISPER_GPU") != "1",
                    reason="set CDSS_TEST_WHISPER_GPU=1 on the Jetson (pywhispercpp installed, "
                           "weights in CDSS_WHISPER_DIR, render group)")
def test_the_real_whisper_loads_from_its_own_directory_and_runs_on_the_gpu(monkeypatch):
    import importlib.util
    import subprocess
    site = pathlib.Path(importlib.util.find_spec("_pywhispercpp").origin).parent
    libs = sorted(site.glob("_pywhispercpp*.so")) + sorted(site.glob("libwhisper.so*")) + sorted(site.glob("libggml*.so*"))
    assert libs
    for lib in libs:
        dyn = subprocess.run(["readelf", "-d", str(lib)], capture_output=True, text=True).stdout
        paths = [l.split("[", 1)[1].rstrip("]") for l in dyn.splitlines() if "RUNPATH" in l or "RPATH" in l]
        assert paths == ["$ORIGIN"], f"{lib.name} looks for libraries in {paths} (install_whisper.sh sets $ORIGIN)"
    import numpy as np
    monkeypatch.setattr(stt, "_MODEL", None)
    monkeypatch.setattr(stt, "_DEVICE", None)
    assert stt.config_problem() is None
    assert stt._transcribe_blocking(np.zeros(stt.SAMPLE_RATE, dtype=np.float32)) == ""
    assert stt._DEVICE == "gpu"
