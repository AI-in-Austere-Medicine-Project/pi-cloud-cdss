"""V3: first audio sooner.

Owner, 2026-10-26: "Sentence-chunked synthesis: split at sentence boundaries,
synthesise and stream each chunk as it's ready, so first audio waits only for
the first sentence."

Offline, with a stand-in engine (as test_tts_contract.py): no model, no
network.

    cd server && ./run_unit_tests.sh
"""
import asyncio
import io
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import types
import wave

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
import tts  # noqa: E402

TOKEN = {"X-Access-Token": main.ACCESS_TOKEN}


class _FakeEngine:
    """Kokoro's create(): 0.1 s of samples per character, so each sentence's
    WAV says which sentence it was."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def create(self, text, voice, speed=1.0, lang="en-us", **k):
        import numpy as np
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("phonemizer exploded")
        return np.zeros(2400 * len(text), dtype=np.float32), 24000


@pytest.fixture
def engine(monkeypatch, tmp_path):
    (tmp_path / tts.MODEL_FILE).write_bytes(b"x")
    (tmp_path / tts.VOICES_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))
    eng = _FakeEngine()
    monkeypatch.setattr(tts, "_load_engine", lambda: eng)
    monkeypatch.setattr(tts, "_ENGINE", None)
    return eng


def call(method, path, **kw):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://testserver") as c:
            return await c.request(method, path, **kw)
    return asyncio.run(go())


def frames_of(body: bytes):
    out, at = [], 0
    while at < len(body):
        kind, (n,) = body[at:at + 1], struct.unpack(">I", body[at + 1:at + 5])
        out.append((kind, body[at + 5:at + 5 + n]))
        at += 5 + n
    assert at == len(body), "a frame was cut short"
    return out


def seconds(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return round(w.getnframes() / w.getframerate(), 2)


# ── Sentence boundaries ─────────────────────────────────────────────────────

@pytest.mark.parametrize("text, want", [
    ("Held. No signed dose for magnesium. Use local protocol.",
     ["Held.", "No signed dose for magnesium.", "Use local protocol."]),
    # A decimal point is not a full stop.
    ("Draw 0.18 mL of 1 mg/mL epinephrine. Reassess.",
     ["Draw 0.18 mL of 1 mg/mL epinephrine.", "Reassess."]),
    # A line break ends a sentence; a list number joins its line.
    ("Issues identified:\n1. Reassess.\n2. Repeat!", ["Issues identified:", "1. Reassess.", "2. Repeat!"]),
    ("Which ketamine do you have? 500 mg vial", ["Which ketamine do you have?", "500 mg vial"]),
    ("e.g. this one. Then that.", ["e.g. this one.", "Then that."]),
    ("No full stop at all", ["No full stop at all"]),
    ("  ", []),
])
def test_split_sentences(text, want):
    assert tts.split_sentences(text) == want


# ── The stream ──────────────────────────────────────────────────────────────

def test_the_stream_is_one_wav_per_sentence_in_order(engine):
    r = call("POST", "/speak", json={"text": "Held. No signed dose. Use local protocol.",
                                     "stream": True}, headers=TOKEN)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == tts.STREAM_MEDIA_TYPE
    assert r.headers["X-Speak-Sentences"] == "3" and float(r.headers["X-Synth-Ms"]) >= 0
    got = frames_of(r.content)
    assert [k for k, _ in got] == [b"A", b"A", b"A"]
    assert [seconds(w) for _, w in got] == [0.5, 1.5, 1.9]
    assert engine.calls == ["Held.", "No signed dose.", "Use local protocol."]


def test_first_audio_waits_for_the_first_sentence_only(engine):
    """The first frame is ready while later sentences are not yet synthesised."""
    async def go():
        count, first_ms, frames = await tts.open_stream("One. Two. Three.")
        assert engine.calls == ["One."]
        first = await frames.__anext__()
        assert first[:1] == tts.FRAME_AUDIO and engine.calls == ["One."]
        rest = [f async for f in frames]
        return count, rest
    count, rest = asyncio.run(go())
    assert count == 3 and len(rest) == 2 and engine.calls == ["One.", "Two.", "Three."]


def test_the_streamed_text_is_normalised_as_the_whole_was(engine):
    call("POST", "/speak", json={"text": "Give 50 mcg IV. Reassess q5min.", "stream": True},
         headers=TOKEN)
    assert engine.calls == ["Give 50 micrograms I-V.", "Reassess every 5 minutes."]


def test_the_brief_is_still_what_is_spoken(engine):
    call("POST", "/speak", json={"text": "The whole card. Long.", "brief": "Brief only.",
                                 "stream": True}, headers=TOKEN)
    assert engine.calls == ["Brief only."]


def test_the_general_disclosure_is_still_spoken_first(engine):
    call("POST", "/speak", json={"text": "Rest.", "source": "general", "stream": True},
         headers=TOKEN)
    # Owner, 2026-10-26: the disclosure is its own sentence, spoken first.
    assert engine.calls[:2] == ["General reference, not guideline.", "Rest."]


def test_no_disclosure_before_a_general_hold(engine):
    call("POST", "/speak", json={"text": "x", "source": "general", "stream": True,
                                 "brief": "Held. The cefazolin dose in the answer is not the "
                                          "signed dose. Use local protocol."}, headers=TOKEN)
    assert engine.calls[0] == "Held."
    assert not any("general reference" in c.lower() for c in engine.calls)


def test_no_jts_in_any_spoken_disclosure():
    import general_reference as gr
    for text in ("Rest.", "Held. Use local protocol.", gr.GENERAL_REFERENCE_BANNER + "Rest."):
        assert "JTS" not in gr.for_speech(text, "general")


def test_a_failure_before_audio_is_its_status_not_a_200(engine, monkeypatch):
    engine.fail_on = "One"
    r = call("POST", "/speak", json={"text": "One. Two.", "stream": True}, headers=TOKEN)
    assert r.status_code == 503 and "phonemizer exploded" in r.json()["detail"]
    assert call("POST", "/speak", json={"text": " ", "stream": True},
                headers=TOKEN).status_code == 400
    monkeypatch.setenv("CDSS_SPEAK_MAX_CHARS", "5")
    assert call("POST", "/speak", json={"text": "Too long. Really.", "stream": True},
                headers=TOKEN).status_code == 413


def test_a_failure_after_audio_ends_the_stream_with_its_reason(engine):
    engine.fail_on = "Two"
    r = call("POST", "/speak", json={"text": "One. Two. Three.", "stream": True}, headers=TOKEN)
    assert r.status_code == 200
    got = frames_of(r.content)
    assert [k for k, _ in got] == [b"A", b"E"]
    assert "phonemizer exploded" in got[1][1].decode()
    assert "Three." not in engine.calls


def test_without_stream_speak_still_answers_one_wav(engine):
    r = call("POST", "/speak", json={"text": "One. Two."}, headers=TOKEN)
    assert r.headers["content-type"] == "audio/wav"
    assert engine.calls == ["One. Two."]


def test_the_stream_needs_the_token(engine):
    assert call("POST", "/speak", json={"text": "One.", "stream": True}).status_code in (401, 403)


# ── The portal ──────────────────────────────────────────────────────────────

def _harness(*args):
    proc = subprocess.run(["node", str(HERE / "tts_stream_harness.js"),
                           str(HERE.parent / "static" / "index.html"), *args],
                          capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout)
    assert "error" not in out, out
    return out


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_portal_plays_each_sentence_as_it_lands_back_to_back():
    out = _harness()
    speak, timing = out["calls"][0], out["calls"][1]
    assert speak["url"] == "/speak" and speak["body"]["stream"] is True
    s = out["started"]
    assert [x["duration"] for x in s] == [2, 3]
    # The second sentence is queued after the first, with the breath between.
    assert s[1]["at"] == pytest.approx(s[0]["at"] + 2 + 0.15)
    t = timing["body"]
    assert timing["url"] == "/speak/timing" and t["outcome"] == "ended"
    assert t["query_id"] == "q-7" and t["synth_ms"] == 110
    # First audio is the first frame, not the whole stream: the stub stream
    # takes 10 ms per 4-byte read, and the first frame is in the first 8 bytes.
    assert t["text_sent_to_response_ms"] == 120
    assert t["first_audio_ms"] < 160
    assert t["audio_end_ms"] > t["first_audio_ms"]
    assert out["button"] == "🔊 listen"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_portal_names_a_failure_after_audio_started():
    out = _harness("error")
    assert len(out["started"]) == 2, "what was spoken stands"
    assert out["calls"][1]["body"]["outcome"] == "error"
    assert out["button"] == "audio unavailable" and "boom" in out["title"]


# ── V3.2: the GPU, else the CPU ─────────────────────────────────────────────
# Owner, 2026-10-26: "Run Kokoro on the GPU (onnxruntime with the CUDA
# provider on JetPack ...); fall back to CPU if it fails."

class _Builds:
    """Stands in for tts._build_engine: records what was asked for, and
    answers with the providers a session on this machine would get."""

    def __init__(self, gets=None, raises_on_cuda=False, gpu_create_fails=False):
        self.asked = []
        self.gets = gets
        self.raises_on_cuda = raises_on_cuda
        self.gpu_create_fails = gpu_create_fails

    def __call__(self, providers):
        self.asked.append(list(providers))
        if tts.CUDA in providers and self.raises_on_cuda:
            raise RuntimeError("CUDA failure 801: operation not supported")
        got = self.gets if (self.gets and tts.CUDA in providers) else providers
        eng = _FakeEngine()
        if got[0] == tts.CUDA and self.gpu_create_fails:
            eng.fail_on = " "          # every real sentence has a space
        eng.on = got[0]
        return eng, list(got)


@pytest.fixture
def device_env(monkeypatch, tmp_path):
    (tmp_path / tts.MODEL_FILE).write_bytes(b"x")
    (tmp_path / tts.VOICES_FILE).write_bytes(b"x")
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(tmp_path))
    monkeypatch.delenv("CDSS_KOKORO_DEVICE", raising=False)
    monkeypatch.setattr(tts, "_ENGINE", None)
    monkeypatch.setattr(tts, "_DEVICE", None)
    monkeypatch.setattr(tts, "_DEVICE_NOTE", "")

    def setup(providers, builds):
        monkeypatch.setattr(tts, "_ort_providers", lambda: providers)
        monkeypatch.setattr(tts, "_build_engine", builds)
        return builds
    return setup


def test_the_gpu_is_used_when_cuda_starts(device_env):
    b = device_env([tts.CUDA, tts.CPU], _Builds())
    asyncio.run(tts.synthesize("Give fentanyl."))
    assert b.asked == [[tts.CUDA, tts.CPU]]
    assert tts.device() == {"device": "gpu", "note": ""}


def test_no_cuda_provider_is_the_cpu_and_says_why(device_env):
    b = device_env([tts.CPU], _Builds())
    asyncio.run(tts.synthesize("Give fentanyl."))
    assert b.asked == [[tts.CPU]]
    d = tts.device()
    assert d["device"] == "cpu" and "onnxruntime-gpu" in d["note"]


def test_cuda_that_onnxruntime_quietly_dropped_is_the_cpu_loaded_once(device_env):
    """What this Jetson does today: the CUDA provider is listed, cannot open
    the GPU, and onnxruntime retries on the CPU by itself."""
    b = device_env([tts.CUDA, tts.CPU], _Builds(gets=[tts.CPU]))
    asyncio.run(tts.synthesize("Give fentanyl."))
    assert b.asked == [[tts.CUDA, tts.CPU]], "the fallen-back session is kept, not rebuilt"
    d = tts.device()
    assert d["device"] == "cpu" and "CUDA provider did not start" in d["note"]


def test_a_cuda_load_failure_is_the_cpu(device_env):
    b = device_env([tts.CUDA, tts.CPU], _Builds(raises_on_cuda=True))
    asyncio.run(tts.synthesize("Give fentanyl."))
    assert b.asked == [[tts.CUDA, tts.CPU], [tts.CPU]]
    d = tts.device()
    assert d["device"] == "cpu" and "801" in d["note"]


def test_a_gpu_synthesis_failure_moves_to_the_cpu_and_still_speaks(device_env):
    b = device_env([tts.CUDA, tts.CPU], _Builds(gpu_create_fails=True))
    audio = asyncio.run(tts.synthesize("Give fentanyl."))
    assert audio.startswith(b"RIFF")
    assert b.asked == [[tts.CUDA, tts.CPU], [tts.CPU]]
    d = tts.device()
    assert d["device"] == "cpu" and "synthesis on the GPU failed" in d["note"]
    asyncio.run(tts.synthesize("Again, please."))
    assert len(b.asked) == 2, "it stays on the CPU"


def test_cdss_kokoro_device_cpu_never_tries_the_gpu(device_env, monkeypatch):
    monkeypatch.setenv("CDSS_KOKORO_DEVICE", "cpu")
    b = device_env([tts.CUDA, tts.CPU], _Builds())
    asyncio.run(tts.synthesize("Give fentanyl."))
    assert b.asked == [[tts.CPU]] and tts.device()["device"] == "cpu"


def test_status_says_where_the_voice_runs(device_env, monkeypatch):
    device_env([tts.CPU], _Builds())
    monkeypatch.setattr(main.providers, "provider_status", lambda: {})
    monkeypatch.setattr(main.providers, "available_models", lambda: [])
    before = call("GET", "/status", headers=TOKEN).json()["voice_device"]
    assert before["device"] == "not loaded"
    asyncio.run(tts.synthesize("Give fentanyl."))
    after = call("GET", "/status", headers=TOKEN).json()["voice_device"]
    assert after["device"] == "cpu" and after["note"]


_REAL_DIR = pathlib.Path(os.getenv("CDSS_KOKORO_DIR") or tts.DEFAULT_DIR)


@pytest.mark.skipif(not (_REAL_DIR / tts.MODEL_FILE).exists(),
                    reason="Kokoro weights are not on disk (tools/install_kokoro.sh)")
def test_the_real_model_speaks_on_whichever_device_it_got(monkeypatch):
    monkeypatch.setenv("CDSS_KOKORO_DIR", str(_REAL_DIR))
    monkeypatch.setattr(tts, "_ENGINE", None)
    monkeypatch.setattr(tts, "_DEVICE", None)
    audio = asyncio.run(tts.synthesize("Reassess in five minutes."))
    assert audio.startswith(b"RIFF") and tts.device()["device"] in ("gpu", "cpu")


# ── Owner, 2026-10-26: a long first sentence splits at a clause mark ─────────

def test_short_first_sentence_is_not_split():
    assert tts.speech_chunks("Held. No signed dose for magnesium sulfate.") == [
        "Held.", "No signed dose for magnesium sulfate."]


def test_long_first_sentence_splits_at_the_last_mark_within_80():
    s = ("Which ketamine do you have, five hundred milligrams in ten millilitres vial, "
         "fifty milligrams per millilitre? Then the dose.")
    got = tts.speech_chunks(s)
    assert got == ["Which ketamine do you have, five hundred milligrams in ten millilitres vial,",
                   "fifty milligrams per millilitre?", "Then the dose."]
    assert len(got[0]) <= tts.FIRST_CHUNK_MAX


def test_only_the_first_sentence_splits():
    long = "Watch: " + "pulse, " * 15 + "pressure."
    assert tts.speech_chunks("Give it. " + long) == ["Give it.", long]


def test_first_mark_after_80_when_none_within():
    s = "A" * 90 + ", then the rest; and more."
    assert tts.speech_chunks(s) == ["A" * 90 + ",", "then the rest; and more."]


def test_a_number_comma_is_not_a_clause_mark():
    s = "Give " + "x " * 40 + "2,000 units now."
    assert tts.speech_chunks(s) == [s]


def test_the_stream_speaks_the_chunks(engine):
    s = "Which ketamine do you have, five hundred milligrams in ten millilitres vial, fifty milligrams per millilitre?"
    r = call("POST", "/speak", json={"text": s, "stream": True}, headers=TOKEN)
    assert r.headers["X-Speak-Sentences"] == "2"
    assert engine.calls[0].endswith("vial,")
