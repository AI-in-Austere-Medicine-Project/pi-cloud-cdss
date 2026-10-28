"""
EdgeCDSS — speech in: whisper.cpp on the device (pywhispercpp; GPU, else CPU).

S1 (owner, 2026-10-27): "whisper.cpp on the Jetson (base.en to start, weights
on disk, no network), a push-to-talk button in the portal that records while
held and sends audio to a new /transcribe endpoint; transcript shown verbatim
in the question box before anything acts on it; the medic presses send."

Nothing here opens a connection. The weights are read from CDSS_WHISPER_DIR,
and the model is always handed a file path that exists. pywhispercpp only
downloads when it is given a model *name*, and config_problem refuses before
that can happen. tools/install_whisper.sh builds the package and puts the
weights there; it is the one step that needs the network.

This module only transcribes. The text goes back to the portal, which puts it
in the question box; nothing in the clinical path reads it until the medic
presses send. Like tts, it is importable without the package, numpy or the
weights, and every failure here degrades to "no transcript" with its reason.
"""
import io
import os
import pathlib
import re
import tempfile
import threading
import time
import wave

from openai_client import _env_number

DEFAULT_DIR = pathlib.Path(__file__).resolve().parent / "data" / "whisper"
MODEL_FILE = "ggml-base.en.bin"
SAMPLE_RATE = 16000                 # whisper's rate; the portal resamples to it
DEFAULT_MAX_S = 30                  # a spoken question is far under this
DEFAULT_THREADS = 4

_MODEL = None
_DEVICE = None                      # "gpu" or "cpu" once loaded
_DEVICE_NOTE = ""
_LOCK = threading.Lock()            # one whisper context: one transcription at a time
# A segment that is nothing but a bracketed tag is whisper saying what it heard
# instead of words: "[BLANK_AUDIO]" for silence (seen on base.en), "[MUSIC]".
_NON_SPEECH = re.compile(r"\s*\[[^\]]*\]\s*")


class SpeechInUnavailable(Exception):
    """No transcript. `status` is what /transcribe returns, `detail` why."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _model_dir() -> pathlib.Path:
    return pathlib.Path((os.getenv("CDSS_WHISPER_DIR") or "").strip() or DEFAULT_DIR)


def _installed() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("pywhispercpp") is not None
    except Exception:
        return False


def config_problem():
    """Why speech in cannot work, decided before any audio. None if it can."""
    path = _model_dir() / MODEL_FILE
    if not path.is_file():
        return (f"speech in needs the whisper weights {MODEL_FILE} in {_model_dir()} "
                f"(tools/install_whisper.sh, or set CDSS_WHISPER_DIR)")
    if not _installed():
        return "speech in needs pywhispercpp built for this device (tools/install_whisper.sh)"
    return None


def status() -> dict:
    """For /status."""
    problem = config_problem()
    return {"available": problem is None, "detail": problem or _DEVICE_NOTE,
            "device": _DEVICE or "not loaded", "model": MODEL_FILE}


def _build_model():
    """(the model, "gpu" or "cpu"). whisper.cpp says which backend it took only
    in its own log, so the load's log is read back for it. The log is caught at
    file descriptor 2 here, not by pywhispercpp's redirect, which falls back to
    a Python-level one (that C never writes to) when sys.stderr has no fd."""
    from pywhispercpp.model import Model
    use_gpu = (os.getenv("CDSS_WHISPER_DEVICE") or "auto").strip().lower() != "cpu"
    threads = _env_number("CDSS_WHISPER_THREADS", DEFAULT_THREADS, int)
    with tempfile.TemporaryFile("w+") as log:
        saved = os.dup(2)
        try:
            os.dup2(log.fileno(), 2)
            model = Model(str(_model_dir() / MODEL_FILE), redirect_whispercpp_logs_to=False,
                          context_params={"use_gpu": use_gpu},
                          n_threads=threads, language="en", no_context=True,
                          print_progress=False, print_realtime=False, print_timestamps=False)
        finally:
            os.dup2(saved, 2)
            os.close(saved)
        log.seek(0)
        text = log.read()
    return model, ("gpu" if use_gpu and "using CUDA" in text else "cpu")


def _model():
    global _MODEL, _DEVICE, _DEVICE_NOTE
    with _LOCK:
        if _MODEL is None:
            _MODEL, _DEVICE = _build_model()
            _DEVICE_NOTE = "" if _DEVICE == "gpu" else "whisper.cpp did not start on the GPU"
            print(f"🎙  speech in: whisper {MODEL_FILE} on the {_DEVICE.upper()}")
        return _MODEL


def samples_from_wav(body: bytes):
    """float32 samples in [-1, 1] from 16-bit mono 16 kHz PCM WAV, or
    SpeechInUnavailable(400/413) saying what is wrong with it."""
    import numpy as np
    try:
        with wave.open(io.BytesIO(body)) as w:
            channels, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            pcm = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise SpeechInUnavailable(400, f"the audio is not a WAV file ({e})")
    if channels != 1:
        raise SpeechInUnavailable(400, f"the audio must be mono, not {channels} channels")
    if width != 2:
        raise SpeechInUnavailable(400, f"the audio must be 16-bit PCM, not {8 * width}-bit")
    if rate != SAMPLE_RATE:
        raise SpeechInUnavailable(400, f"the audio must be {SAMPLE_RATE} Hz, not {rate} Hz")
    if n == 0:
        raise SpeechInUnavailable(400, "no audio was recorded")
    max_s = _env_number("CDSS_TRANSCRIBE_MAX_S", DEFAULT_MAX_S, float)
    if n / rate > max_s:
        raise SpeechInUnavailable(
            413, f"the recording is {n / rate:.1f} s; speech in takes up to {max_s:g} s")
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0


def _transcribe_blocking(samples) -> str:
    model = _model()
    with _LOCK:
        segments = model.transcribe(samples)
    # Verbatim: whisper's segments joined as it wrote them. No rewriting of
    # numbers, units or words; the medic reads and edits it before sending.
    # Only whole-segment non-speech tags are dropped (silence comes back "").
    return "".join(s.text for s in segments if not _NON_SPEECH.fullmatch(s.text)).strip()


async def transcribe(body: bytes) -> dict:
    """{"text", "audio_ms", "transcribe_ms", "device"} for a WAV body."""
    import asyncio
    problem = config_problem()
    if problem:
        raise SpeechInUnavailable(503, problem)
    samples = samples_from_wav(body)
    t0 = time.perf_counter()
    try:
        text = await asyncio.to_thread(_transcribe_blocking, samples)
    except SpeechInUnavailable:
        raise
    except Exception as e:
        raise SpeechInUnavailable(
            503, f"speech-in failed ({type(e).__name__}: {str(e)[:200]})") from e
    return {"text": text, "audio_ms": round(len(samples) / SAMPLE_RATE * 1000, 1),
            "transcribe_ms": round((time.perf_counter() - t0) * 1000, 1), "device": _DEVICE}


def warm_up():
    """Load the model and transcribe one second of silence, at service start
    (in a thread, as tts.warm_up). Never raises. CDSS_WHISPER_WARMUP=0 turns
    it off."""
    if (os.getenv("CDSS_WHISPER_WARMUP") or "1").strip() == "0" or config_problem():
        return
    t0 = time.perf_counter()
    try:
        import numpy as np
        _transcribe_blocking(np.zeros(SAMPLE_RATE, dtype=np.float32))
    except Exception as e:
        print(f"⚠️  speech-in warm-up failed ({type(e).__name__}: {str(e)[:200]}); "
              "whisper loads on the first recording")
        return
    print(f"🎙  speech in warmed on the {(_DEVICE or '?').upper()} in {time.perf_counter() - t0:.1f} s")
