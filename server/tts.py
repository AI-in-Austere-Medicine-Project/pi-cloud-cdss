"""
EdgeCDSS — voice output: Kokoro-82M on the device (kokoro-onnx; GPU, else CPU).

V2 (owner, 2026-10-25): "replace /speak with local Kokoro-82M (kokoro-onnx,
CPU, weights and voices on disk, espeak-ng via apt; no network after install).
Keep the ElevenLabs path deleted, not optional." There is no cloud voice and
no switch back to one. Nothing here opens a connection: the weights and voices
are read from CDSS_KOKORO_DIR, and phonemes come from apt's libespeak-ng.
tools/install_kokoro.sh puts the files there, the one step that needs the
network.

Isolated from the clinical core by design: every failure in here degrades to
"no audio", never to a missing, delayed or altered clinical answer.
Importable without kokoro_onnx, numpy or the weights — the offline suite pins
the contract in this module, and the clinical path must not be able to fail
because the voice path is missing a file. (Same reason openai_client is
importable without the OpenAI SDK; see P-0.)

What the v4.1 outage taught still holds: a failure names its cause (which
file, which library) and /status reports voice only when it can be produced.
"""

import asyncio
import ctypes.util
import io
import os
import pathlib
import re as _re
import struct
import threading
import time
import wave

# One numeric-env parser for the repo: a typo'd knob degrades to the default
# and says so, it never raises. See openai_client._env_number.
from openai_client import _env_number

DEFAULT_DIR = pathlib.Path(__file__).resolve().parent / "data" / "kokoro"
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

# British male, the nearest to the ElevenLabs "George" the portal spoke with,
# at the same 0.85 speed it used for intelligibility.
DEFAULT_VOICE = "bm_george"
DEFAULT_LANG = "en-gb"
DEFAULT_SPEED = 0.85

# A brief-mode answer is far under this; the cap keeps a runaway detailed
# answer from holding the CPU for minutes.
DEFAULT_MAX_CHARS = 2500

_ENGINE = None
_ENGINE_LOCK = threading.Lock()


class VoiceUnavailable(Exception):
    """Voice could not be produced.

    `status` is the HTTP status /speak should return, `detail` the operator- and
    medic-readable reason. Both are deliberately specific: this feature failed
    for weeks behind a generic 500.
    """

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _model_dir() -> pathlib.Path:
    return pathlib.Path((os.getenv("CDSS_KOKORO_DIR") or "").strip() or DEFAULT_DIR)


def _espeak_paths():
    """(library, data directory) of apt's espeak-ng, or (None, None).
    CDSS_ESPEAK_LIB / CDSS_ESPEAK_DATA override the search."""
    lib = (os.getenv("CDSS_ESPEAK_LIB") or "").strip()
    if not lib:
        name = ctypes.util.find_library("espeak-ng")
        for d in ("/usr/lib/aarch64-linux-gnu", "/usr/lib/x86_64-linux-gnu", "/usr/lib"):
            if name and os.path.exists(os.path.join(d, name)):
                lib = os.path.join(d, name)
                break
    data = (os.getenv("CDSS_ESPEAK_DATA") or "").strip()
    if lib and not data:
        data = os.path.join(os.path.dirname(lib), "espeak-ng-data")
    if not lib or not os.path.exists(lib) or not os.path.isdir(data):
        return None, None
    return lib, data


def _kokoro_importable() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except Exception:
        return False


def config_problem():
    """Why voice cannot work, decided before any synthesis. None if it can."""
    d = _model_dir()
    missing = [f for f in (MODEL_FILE, VOICES_FILE) if not (d / f).is_file()]
    if missing:
        return (f"voice output needs the Kokoro files {', '.join(missing)} in {d} "
                f"(tools/install_kokoro.sh, or set CDSS_KOKORO_DIR)")
    if _espeak_paths() == (None, None):
        return ("voice output needs espeak-ng's library and data "
                "(sudo apt install espeak-ng)")
    if not _kokoro_importable():
        return "voice output needs the kokoro-onnx package (pip install kokoro-onnx)"
    return None


def voice_available() -> bool:
    """What /status and /health must report instead of a hard-coded True.
    Checks the files and libraries; does not load the model."""
    return config_problem() is None


# V3 (owner, 2026-10-26): "Run Kokoro on the GPU ... fall back to CPU if it
# fails." CDSS_KOKORO_DEVICE is auto (the default: the GPU when onnxruntime can
# start its CUDA provider, else the CPU), gpu (the same, said explicitly) or
# cpu. Voice is never lost for want of a GPU: every GPU failure, at load or in
# synthesis, ends on the CPU with the reason logged and in /status.
CUDA = "CUDAExecutionProvider"
CPU = "CPUExecutionProvider"
_DEVICE = None           # "gpu" or "cpu" once the model is loaded
_DEVICE_NOTE = ""        # why it is on the CPU, when it is


def _ort_providers() -> list:
    import onnxruntime
    return onnxruntime.get_available_providers()


def _build_engine(providers: list):
    """(the model on a session asking for `providers`, the providers the
    session actually got: onnxruntime falls back to the CPU on its own when
    the CUDA provider cannot start, and says so only in its log)."""
    import onnxruntime as rt
    from kokoro_onnx import EspeakConfig, Kokoro
    lib, data = _espeak_paths()
    d = _model_dir()
    opts = rt.SessionOptions()
    opts.log_severity_level = 3
    sess = rt.InferenceSession(str(d / MODEL_FILE), opts, providers=providers)
    eng = Kokoro.from_session(sess, str(d / VOICES_FILE),
                              espeak_config=EspeakConfig(lib_path=lib, data_path=data))
    return eng, list(sess.get_providers())


def _load_engine():
    global _DEVICE, _DEVICE_NOTE
    wanted = (os.getenv("CDSS_KOKORO_DEVICE") or "auto").strip().lower()
    if wanted == "cpu":
        note = "CDSS_KOKORO_DEVICE=cpu"
    elif CUDA not in _ort_providers():
        note = "onnxruntime here has no CUDA provider (onnxruntime-gpu is not installed)"
    else:
        try:
            eng, got = _build_engine([CUDA, CPU])
        except Exception as e:
            note = f"the CUDA provider failed to load ({type(e).__name__}: {str(e)[:160]})"
        else:
            if got and got[0] == CUDA:
                _DEVICE, _DEVICE_NOTE = "gpu", ""
                print("🔊 voice: Kokoro on the GPU (CUDA)")
                return eng
            # onnxruntime fell back by itself: this session is already a CPU one.
            _DEVICE = "cpu"
            _DEVICE_NOTE = ("the CUDA provider did not start, so onnxruntime fell back to "
                            "the CPU (no GPU access for this user?)")
            print(f"⚠️  voice: Kokoro on the CPU: {_DEVICE_NOTE}")
            return eng
    eng, _ = _build_engine([CPU])
    _DEVICE, _DEVICE_NOTE = "cpu", note
    print(f"🔊 voice: Kokoro on the CPU: {note}")
    return eng


def _engine():
    """The model, loaded once (about 2 s on the Jetson) and kept."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = _load_engine()
        return _ENGINE


def _fall_back_to_cpu(failed, why: str):
    """A synthesis failed on the GPU: the model moves to the CPU for good.
    `failed` is the engine that failed, so two threads failing together load
    the CPU model once."""
    global _ENGINE, _DEVICE, _DEVICE_NOTE
    with _ENGINE_LOCK:
        if _ENGINE is failed:
            _ENGINE, _ = _build_engine([CPU])
            _DEVICE, _DEVICE_NOTE = "cpu", why
            print(f"⚠️  voice: Kokoro moved to the CPU: {why}")
        return _ENGINE


def device() -> dict:
    """For /status: where the voice runs, and why the CPU when it is.
    "not loaded" until the first synthesis."""
    return {"device": _DEVICE or "not loaded", "note": _DEVICE_NOTE}


def _wav(samples, sample_rate: int) -> bytes:
    """16-bit mono PCM WAV: the browser plays it with no decoder to install."""
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _synthesize_blocking(text: str) -> bytes:
    voice = (os.getenv("CDSS_KOKORO_VOICE") or "").strip() or DEFAULT_VOICE
    lang = (os.getenv("CDSS_KOKORO_LANG") or "").strip() or DEFAULT_LANG
    speed = _env_number("CDSS_KOKORO_SPEED", DEFAULT_SPEED, float)
    eng = _engine()
    try:
        samples, sample_rate = eng.create(text, voice=voice, speed=speed, lang=lang)
    except Exception as e:
        if _DEVICE != "gpu":
            raise
        eng = _fall_back_to_cpu(eng, f"synthesis on the GPU failed ({type(e).__name__}: {str(e)[:160]})")
        samples, sample_rate = eng.create(text, voice=voice, speed=speed, lang=lang)
    return _wav(samples, sample_rate)


def _checked(text: str) -> str:
    """The text to speak, or VoiceUnavailable: 400 empty, 413 over the cap,
    503 not configured. Decided before any synthesis."""
    text = (text or "").strip()
    if not text:
        raise VoiceUnavailable(400, "No text provided")

    max_chars = _env_number("CDSS_SPEAK_MAX_CHARS", DEFAULT_MAX_CHARS, int)
    if len(text) > max_chars:
        raise VoiceUnavailable(
            413, f"Text is {len(text)} characters; the voice limit is {max_chars}.")

    problem = config_problem()
    if problem:
        raise VoiceUnavailable(503, problem)
    return text


async def _synthesize_off_loop(text: str) -> bytes:
    # CPU-bound for seconds: off the event loop, or /health stalls behind it
    # and the watchdog restarts the service (AE-4).
    try:
        return await asyncio.to_thread(_synthesize_blocking, text)
    except Exception as e:
        raise VoiceUnavailable(
            503, f"local voice failed ({type(e).__name__}: {str(e)[:200]})") from e


async def synthesize(text: str) -> bytes:
    """WAV bytes for `text`, or VoiceUnavailable carrying the status and reason."""
    return await _synthesize_off_loop(_checked(text))


# ── V3: sentence by sentence ─────────────────────────────────────────────────
# Owner, 2026-10-26: "split at sentence boundaries, synthesise and stream each
# chunk as it's ready, so first audio waits only for the first sentence."
#
# A sentence ends at . ! or ? followed by white space, or at a line break. A
# decimal point is followed by a digit, so "0.18" never splits. A piece with
# no letter in it ("1.", "-") is not a sentence: it joins the next one, and
# so does one that ends in an abbreviation ("e.g.").
_SENTENCE_END_RE = _re.compile(r"(?<=[.!?])\s+|\s*\n\s*")
_HAS_LETTER_RE = _re.compile(r"[A-Za-z]")
_ABBREV_END_RE = _re.compile(r"\b(?:e\.g|i\.e|etc|approx|vs|Dr|No)\.$", _re.IGNORECASE)


def split_sentences(text: str) -> list:
    out, carry = [], ""
    for piece in _SENTENCE_END_RE.split(text or ""):
        piece = piece.strip()
        if not piece:
            continue
        piece = f"{carry} {piece}".strip() if carry else piece
        if _HAS_LETTER_RE.search(piece) and not _ABBREV_END_RE.search(piece):
            out.append(piece)
            carry = ""
        else:
            carry = piece
    if carry:
        if out:
            out[-1] = f"{out[-1]} {carry}"
        else:
            out.append(carry)
    return out


# Owner, 2026-10-26: "First chunk may split at a comma, colon or semicolon if
# the first sentence exceeds 80 characters." Only the first, and only once:
# first audio waits for that chunk alone. The split is the last such mark that
# leaves the chunk within 80 characters, else the first mark after; the mark
# must be followed by white space, so "2,000" never splits. With no mark the
# sentence is spoken whole.
FIRST_CHUNK_MAX = 80
_CLAUSE_END_RE = _re.compile(r"[,:;](?=\s)")


def speech_chunks(text: str) -> list:
    """The pieces /speak streams: split_sentences, with a long first sentence
    split once at a clause mark."""
    out = split_sentences(text)
    if not out or len(out[0]) <= FIRST_CHUNK_MAX:
        return out
    first = out[0]
    marks = [m.end() for m in _CLAUSE_END_RE.finditer(first)
             if _HAS_LETTER_RE.search(first[:m.end()]) and first[m.end():].strip()]
    if not marks:
        return out
    within = [i for i in marks if i <= FIRST_CHUNK_MAX]
    cut = within[-1] if within else marks[0]
    return [first[:cut].strip(), first[cut:].strip()] + out[1:]


# The stream is a run of frames: one type byte, a 4-byte big-endian length,
# then the payload. b"A" is a complete WAV of one sentence, played in order;
# b"E" is a failure after audio has started, UTF-8 text naming it. A WAV per
# frame lets the portal decode each with decodeAudioData as it lands.
FRAME_AUDIO = b"A"
FRAME_ERROR = b"E"
STREAM_MEDIA_TYPE = "application/vnd.edgecdss.audio-frames"


def frame(kind: bytes, payload: bytes) -> bytes:
    return kind + struct.pack(">I", len(payload)) + payload


async def open_stream(text: str):
    """(sentence count, the first sentence's synthesis ms, an async iterator of
    frames). Every failure before audio exists is raised here, with its status:
    the first sentence is synthesised before this returns, so /speak can still
    answer 503 rather than a 200 that carries no audio. A failure on a later
    sentence ends the stream with an error frame; what was spoken stands."""
    sentences = speech_chunks(_checked(text))
    t0 = time.perf_counter()
    first = await _synthesize_off_loop(sentences[0])
    first_ms = round((time.perf_counter() - t0) * 1000, 1)

    async def frames():
        yield frame(FRAME_AUDIO, first)
        for s in sentences[1:]:
            try:
                audio = await _synthesize_off_loop(s)
            except VoiceUnavailable as e:
                print(f"⚠️  /speak stream stopped: {e.detail}")
                yield frame(FRAME_ERROR, e.detail.encode("utf-8"))
                return
            yield frame(FRAME_AUDIO, audio)

    return len(sentences), first_ms, frames()


def normalize_for_speech(text: str) -> str:
    """Rewrite clinical shorthand so TTS speaks doses intelligibly.
    '0.24 mL of 100mg/mL ketamine IV' -> '0.24 milliliters of 100 milligrams per milliliter ketamine I-V'"""
    t = text
    t = _re.sub(r'\*\*', '', t)                    # markdown bold
    t = _re.sub(r'\s*\|\s*', '. ', t)             # section pipes
    # compound units FIRST (order matters)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mcg/kg/min\b', r'\1 micrograms per kilogram per minute', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mg/kg\b', r'\1 milligrams per kilogram', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mcg/kg\b', r'\1 micrograms per kilogram', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mg/mL\b', r'\1 milligrams per milliliter', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mcg/mL\b', r'\1 micrograms per milliliter', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mL/hr\b', r'\1 milliliters per hour', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mg/hr\b', r'\1 milligrams per hour', t, flags=_re.I)
    # simple units
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mL\b', r'\1 milliliters', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mcg\b', r'\1 micrograms', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*mg\b', r'\1 milligrams', t, flags=_re.I)
    t = _re.sub(r'(\d+(?:\.\d+)?)\s*kg\b', r'\1 kilograms', t, flags=_re.I)
    # frequency shorthand: q5min, q 15 min
    t = _re.sub(r'\bq\s*(\d+)\s*min\b', r'every \1 minutes', t, flags=_re.I)
    t = _re.sub(r'\bq\s*(\d+)\s*(?:hr|h)\b', r'every \1 hours', t, flags=_re.I)
    # routes and initialisms spoken letter-by-letter
    for abbr, spoken in [('IV', 'I-V'), ('IO', 'I-O'), ('IM', 'I-M'),
                         ('RSI', 'R-S-I'), ('TXA', 'T-X-A'), ('GCS', 'G-C-S'),
                         ('SpO2', 'S-P-O-2'), ('ICP', 'I-C-P'), ('TBI', 'T-B-I'),
                         ('DCR', 'D-C-R'), ('CPR', 'C-P-R'), ('PO', 'by mouth')]:
        t = _re.sub(r'\b' + abbr + r'\b', spoken, t)
    return t
