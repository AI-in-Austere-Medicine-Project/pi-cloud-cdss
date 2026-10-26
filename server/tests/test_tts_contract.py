"""
EdgeCDSS — the voice path: local Kokoro-82M, failing loudly and never silently.

V2 (owner, 2026-10-25): "replace /speak with local Kokoro-82M (kokoro-onnx,
CPU, weights and voices on disk, espeak-ng via apt; no network after install).
Keep the ElevenLabs path deleted, not optional."

What the v4.1 outage taught still holds: a voice failure names its cause (a
missing file, a missing library), /status never claims voice it cannot
produce, and the clinical path cannot fail because voice is misconfigured.

The contract tests are offline and use a stand-in engine: no model, no
network. One test runs the real model when its files are on disk, with every
outbound connection refused.

    cd server && ./run_unit_tests.sh
"""

import asyncio
import io
import os
import pathlib
import re
import socket
import subprocess
import sys
import threading
import wave

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tts  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeEngine:
    """Kokoro's create(): float32 samples at 24 kHz. Records what it was asked."""

    def __init__(self):
        self.calls = []

    def create(self, text, voice, speed=1.0, lang="en-us", **k):
        import numpy as np
        self.calls.append({"text": text, "voice": voice, "speed": speed, "lang": lang,
                           "thread": threading.get_ident()})
        return np.zeros(12000, dtype=np.float32) + 0.25, 24000


@pytest.fixture
def fake_engine(monkeypatch, tmp_path):
    (tmp_path / tts.MODEL_FILE).write_bytes(b"x")
    (tmp_path / tts.VOICES_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))
    eng = _FakeEngine()
    monkeypatch.setattr(tts, "_load_engine", lambda: eng)
    monkeypatch.setattr(tts, "_ENGINE", None)
    return eng


def status_of(text):
    try:
        asyncio.run(tts.synthesize(text))
        return None
    except tts.VoiceUnavailable as e:
        return e.status, e.detail


# --- ElevenLabs is gone --------------------------------------------------------

def test_no_elevenlabs_path_remains():
    for f in ("tts.py", "main.py"):
        src = open(os.path.join(HERE, f)).read()
        assert not re.search(r"elevenlabs|ELEVENLABS|xi-api-key", src), f
        assert "https://" not in open(os.path.join(HERE, "tts.py")).read()


def test_voice_makes_no_network_call(fake_engine, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert asyncio.run(tts.synthesize("Give fentanyl 50 mcg IV.")).startswith(b"RIFF")


# --- the audio ---------------------------------------------------------------

def test_synthesize_returns_wav_16bit_mono_24k(fake_engine):
    audio = asyncio.run(tts.synthesize("Reassess in five minutes."))
    with wave.open(io.BytesIO(audio)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert w.getnframes() == 12000


def test_the_voice_speed_and_language_are_the_configured_ones(fake_engine, monkeypatch):
    asyncio.run(tts.synthesize("hello"))
    call = fake_engine.calls[-1]
    assert (call["voice"], call["speed"], call["lang"]) == (
        tts.DEFAULT_VOICE, tts.DEFAULT_SPEED, tts.DEFAULT_LANG)
    monkeypatch.setenv("CDSS_KOKORO_VOICE", "am_michael")
    monkeypatch.setenv("CDSS_KOKORO_LANG", "en-us")
    monkeypatch.setenv("CDSS_KOKORO_SPEED", "fast")       # a typo keeps the default
    asyncio.run(tts.synthesize("hello"))
    call = fake_engine.calls[-1]
    assert (call["voice"], call["speed"], call["lang"]) == ("am_michael", tts.DEFAULT_SPEED, "en-us")


def test_synthesis_runs_off_the_event_loop(fake_engine):
    """CPU-bound: on the event loop it would stall /health, and the watchdog
    restarts the service at three misses (AE-4)."""
    asyncio.run(tts.synthesize("hello"))
    assert fake_engine.calls[-1]["thread"] != threading.get_ident()


def test_an_engine_failure_is_503_and_says_why(fake_engine, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("phonemizer exploded")
    monkeypatch.setattr(fake_engine, "create", boom)
    status, detail = status_of("hello")
    assert status == 503 and "phonemizer exploded" in detail


def test_empty_text_is_400(fake_engine):
    assert status_of("   ")[0] == 400


def test_overlong_text_is_capped_locally(fake_engine):
    status, detail = status_of("x" * (tts.DEFAULT_MAX_CHARS + 1))
    assert status == 413 and str(tts.DEFAULT_MAX_CHARS) in detail


def test_the_cap_stays_tunable_and_survives_a_typo(fake_engine, monkeypatch):
    monkeypatch.setenv("CDSS_SPEAK_MAX_CHARS", "10")
    assert status_of("x" * 11)[0] == 413
    monkeypatch.setenv("CDSS_SPEAK_MAX_CHARS", "ten thousand")
    assert status_of("x" * 11) is None, "a typo'd cap must not start rejecting text"


# --- configuration: decided before any synthesis -----------------------------

def test_missing_weights_are_named(monkeypatch, tmp_path):
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))
    problem = tts.config_problem()
    assert problem and tts.MODEL_FILE in problem and str(tmp_path) in problem
    assert tts.voice_available() is False
    assert status_of("hello")[0] == 503


def test_missing_espeak_is_named(fake_engine, monkeypatch):
    monkeypatch.setattr(tts, "_espeak_paths", lambda: (None, None))
    problem = tts.config_problem()
    assert problem and "espeak-ng" in problem and "apt" in problem


def test_local_mode_does_not_turn_voice_off(fake_engine, monkeypatch):
    """Voice is on the device now: CDSS_LLM_PROVIDER=local keeps it."""
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    assert tts.config_problem() is None


def test_module_imports_without_kokoro_onnx():
    """/speak is optional; the clinical path must not depend on the voice package."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); "
         "sys.modules['kokoro_onnx'] = None; import tts; print(tts.voice_available())" % HERE],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("False"), proc.stdout


def test_speech_normalisation_survived_the_move():
    spoken = tts.normalize_for_speech("Give **0.24 mL** of 100mg/mL ketamine IV q5min | 34kg")
    assert "0.24 milliliters" in spoken
    assert "100 milligrams per milliliter" in spoken
    assert "I-V" in spoken
    assert "every 5 minutes" in spoken
    assert "34 kilograms" in spoken
    assert "**" not in spoken


def test_voice_support_is_never_hardcoded_true():
    """/status claiming voice_support: true while voice was dead is why nobody
    noticed for a release cycle."""
    source = open(os.path.join(HERE, "main.py")).read()
    assert not re.search(r'"voice_support"\s*:\s*True', source)


def test_speak_answers_wav():
    source = open(os.path.join(HERE, "main.py")).read()
    assert 'media_type="audio/wav"' in source and "audio/mpeg" not in source


# --- the real model, when it is on disk --------------------------------------

_REAL_DIR = pathlib.Path(os.getenv("CDSS_KOKORO_DIR") or tts.DEFAULT_DIR)


@pytest.mark.skipif(not (_REAL_DIR / tts.MODEL_FILE).exists(),
                    reason="Kokoro weights are not on disk (tools/install_kokoro.sh)")
def test_the_real_model_speaks_with_the_network_refused(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network call attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(_REAL_DIR))
    monkeypatch.setattr(tts, "_ENGINE", None)
    audio = asyncio.run(tts.synthesize("Give fentanyl 50 micrograms I-V."))
    with wave.open(io.BytesIO(audio)) as w:
        assert w.getframerate() == 24000 and w.getnframes() / 24000 > 0.5
