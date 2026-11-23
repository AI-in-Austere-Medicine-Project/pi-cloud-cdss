"""W1: Pocket on the web, for outside testers (owner, 2026-11-15).

/pocket runs the real Pocket code, the edgecdss-pocket repo checked out at the
commit pocket_pin.json pins (tools/install_pocket.py), on the Jetson:

    browser audio (16 kHz WAV) -> Vosk with Pocket's committed grammar
      -> Pocket's engine (read-back, "confirm") -> Pocket's spoken templates
      -> Piper -> audio back to the browser, the text shown on screen too.

What it never does:
  - serve any set but the signed EMS one (owner, 2026-11-23: one drug list, the
    EMS set only). The bank is the pinned checkout's own bank/ems directory, loaded as a signed bank (never as a test bank, whatever
    POCKET_TEST says), and refused if it, or any entry in it, names another set.
    No request names a set or a bank: the request models forbid unknown fields.
    CDSS_DRUG_SET does not reach it.
  - write where EdgeCDSS logs or replays read. Turns, doses, timings and feedback
    go to $POCKET_LOG_DIR (default ~/pocket-web/logs), every line product "pocket".
  - talk to two testers at once. One talker holds the engine; anyone else gets
    "busy, try again" until the talker releases or is idle for LEASE_IDLE_S. Each
    new talker gets a fresh Pocket session, so no patient state crosses testers.
"""
import base64
import collections
import dataclasses
import datetime
import io
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid
import wave
from typing import Annotated, Callable, List, Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

_DIR = pathlib.Path(__file__).resolve().parent
PIN = json.loads((_DIR / "pocket_pin.json").read_text())
PAGE = _DIR / "static" / "pocket.html"

SERVED_SET = "EMS"
REFUSED_SETS = ("PFC", "EMS-TEST")
LEASE_IDLE_S = 60.0
MAX_AUDIO_S = 15.0
RATE = 16000
MAX_TURNS_KEPT = 500
FEEDBACK_FILE = "pocket_feedback.jsonl"

# The "How to test" panel: five phrases, said in this order on a fresh session, and
# what the pinned engine answers, as shown on screen (its written form; test_pocket_web
# pins every word).
EXAMPLES = [
    ("fentanyl for pain iv twenty kilos", "Fentanyl, pain or fever, IV, child, twenty kilos. Confirm?"),
    ("confirm", "Fentanyl twenty micrograms. Zero point four mils of fifty micrograms per mil. Use a one mil syringe."),
    ("new patient", "New patient. Weight and age cleared."),
    ("morphine", "No signed dose for morphine."),
    ("acetaminophen for fever po twenty kilos", "Acetaminophen, pain or fever, PO, child, twenty kilos. Confirm?"),
]


class Unavailable(Exception):
    """Pocket cannot serve; the reason is shown on the page."""


class Busy(Exception):
    pass


# ── where things are ────────────────────────────────────────────────────────

def pocket_home() -> pathlib.Path:
    return pathlib.Path(os.getenv("POCKET_HOME", str(pathlib.Path.home() / "pocket-web")))


def checkout_dir() -> pathlib.Path:
    return pocket_home() / f"edgecdss-pocket-{PIN['commit'][:12]}"


def bank_dir() -> pathlib.Path:
    return checkout_dir() / "bank" / "ems"      # Pocket's one drug list (Pocket #36)


def vosk_model_dir() -> pathlib.Path:
    return pocket_home() / "models" / PIN["vosk_model"]["name"]


def piper_voice_path() -> pathlib.Path:
    return pocket_home() / "models" / "piper" / f"{PIN['piper_voice']['name']}.onnx"


def default_log_dir() -> pathlib.Path:
    return pathlib.Path(os.getenv("POCKET_LOG_DIR", str(pocket_home() / "logs")))


LOG_DIR = default_log_dir()


def _write(name: str, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / name, "a", encoding="utf-8") as f:
        f.write(json.dumps({"product": "pocket", **record}, sort_keys=True, default=str) + "\n")


def _log(record: dict) -> None:
    _write(f"pocket_turns_{datetime.date.today().isoformat()}.jsonl", record)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── the pinned code ─────────────────────────────────────────────────────────

def verify_checkout(path: pathlib.Path) -> str:
    path = pathlib.Path(path)
    if not (path / ".git").exists():
        raise Unavailable(f"Pocket is not installed at {path} (server/tools/install_pocket.py)")

    def git(*a):
        return subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True,
                              check=True).stdout.strip()
    head = git("rev-parse", "HEAD")
    if head != PIN["commit"]:
        raise Unavailable(f"the Pocket checkout is at commit {head[:12]}, "
                          f"not the pinned {PIN['commit'][:12]}")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise Unavailable("the Pocket checkout has local changes")
    return head


def _import_pocket(path: pathlib.Path) -> None:
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)


def load_served_bank(d: pathlib.Path):
    """The signed EMS bank, or Unavailable. Loaded as a signed bank (test=False), so a test
    bank, and the retired PFC bank, are refused by Pocket itself; a bank not labelled the
    EMS set, or labelled another set too, is refused here."""
    from engine.bank import BankRefused, load_bank
    try:
        bank = load_bank(d, test=False)
    except BankRefused as e:
        raise Unavailable(f"bank refused: {e}") from None
    try:
        manifest = json.loads((pathlib.Path(d) / "manifest.json").read_text())
    except (OSError, ValueError):
        raise Unavailable("bank refused: no readable manifest") from None
    sets = {manifest.get("set"), *(e.get("set") for e in bank.entries)} - {None}
    if bank.test or sets != {SERVED_SET} or set(REFUSED_SETS) & sets:
        raise Unavailable(f"bank refused: the web serves the signed {SERVED_SET} set only, "
                          f"this bank is {', '.join(sorted(map(str, sets))) or 'unlabelled'}")
    return bank


def load_served_procedures(d: pathlib.Path, bank) -> dict:
    """The signed procedures (RSI, failed airway; Pocket #22) shipped with the bank, as
    Pocket's own boot() loads them: refused procedures all hold, the doses do not."""
    from engine.procedures import ProceduresRefused, load_procedures
    try:
        return load_procedures(d, bank)
    except ProceduresRefused as e:
        print(f"⚠️  /pocket: procedures refused, none served: {e}")
        return {}


# ── speech in and out ───────────────────────────────────────────────────────

def pcm16k(wav_bytes: bytes) -> bytes:
    """The PCM frames of a 16 kHz mono 16-bit WAV, or ValueError."""
    try:
        with wave.open(io.BytesIO(wav_bytes)) as w:
            if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, RATE):
                raise ValueError("audio must be 16 kHz mono 16-bit WAV")
            if w.getnframes() > MAX_AUDIO_S * RATE:
                raise ValueError(f"audio is over {MAX_AUDIO_S:g} s")
            return w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"not a WAV file: {e}") from None


def resample_wav_16k(wav_bytes: bytes) -> bytes:
    """A mono 16-bit WAV at any rate as 16 kHz (linear interpolation)."""
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, frames = w.getframerate(), w.readframes(w.getnframes())
    x = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    if rate != RATE and len(x):
        n = int(len(x) * RATE / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(RATE)
        w.writeframes(np.clip(x, -32768, 32767).astype("<i2").tobytes())
    return out.getvalue()


class VoskHearing:
    """Pocket's own two-decoder hearing (voice.hear) with its committed grammar, which
    must be the grammar for this model and this bank."""

    def __init__(self, model_dir: pathlib.Path, grammar_path: pathlib.Path, bank):
        import vosk
        from grammar.vocabulary import build
        from voice.grammar import model_id
        from voice.hear import Hearing
        if not pathlib.Path(model_dir).exists():
            raise Unavailable(f"no Vosk model at {model_dir} (install_pocket.py --models)")
        g = json.loads(pathlib.Path(grammar_path).read_text())
        if g.get("bank_hash") != bank.hash:     # Pocket's grammar is the EMS set's (Pocket #36)
            raise Unavailable("Pocket's grammar is for another bank")
        if g.get("model_am_sha256") != model_id(model_dir)["model_am_sha256"]:
            raise Unavailable("Pocket's grammar is for another Vosk model")
        vosk.SetLogLevel(-1)
        self.model_name = pathlib.Path(model_dir).name
        self._vosk, self._model = vosk, vosk.Model(str(model_dir))
        self._hearing = Hearing(self._model, g, build(bank))

    def hear(self, pcm: bytes) -> tuple:
        u = self._hearing.start()
        u.feed(pcm)
        return u.finish()

    def hear_open(self, pcm: bytes) -> tuple:
        """The same model with no grammar: (text, the top alternatives). What Vosk
        itself makes of a word, for the owner's teach page (pocket_teach.py)."""
        r = self._vosk.KaldiRecognizer(self._model, RATE)
        r.SetMaxAlternatives(5)
        r.AcceptWaveform(pcm)
        alts = json.loads(r.FinalResult()).get("alternatives", [])
        texts = list(dict.fromkeys(a.get("text", "") for a in alts))
        return (texts[0] if texts else ""), texts


class PiperSynth:
    def __init__(self, onnx: pathlib.Path):
        from piper import PiperVoice
        if not pathlib.Path(onnx).exists():
            raise Unavailable(f"no Piper voice at {onnx} (install_pocket.py --models)")
        self.voice_name = pathlib.Path(onnx).stem
        self._voice = PiperVoice.load(str(onnx))

    def __call__(self, text: str) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            self._voice.synthesize_wav(text, w)
        return buf.getvalue()


# ── one talker at a time ────────────────────────────────────────────────────

class Runtime:
    def __init__(self, bank, hearing, synth, commit: str, procedures: Optional[dict] = None):
        self.bank, self.hearing, self.synth, self.commit = bank, hearing, synth, commit
        self.procedures = procedures or {}
        # The start-up line the page shows on load (owner, 2026-11-21): Pocket's own, from
        # a session that is never used, so nothing is logged and no tester is holding it.
        from engine.session import Session
        self.start_up = Session(bank, log=lambda record: None, procedures=self.procedures).announce.written_text
        self._lease = threading.Lock()
        self._work = threading.RLock()   # hear() holds it across decoding and turn()
        self._holder: Optional[str] = None
        self._last = 0.0
        self._session = None
        self._turns = collections.OrderedDict()

    @classmethod
    def load(cls, hearing=None, synth=None) -> "Runtime":
        path = checkout_dir()
        commit = verify_checkout(path)
        _import_pocket(path)
        bank = load_served_bank(bank_dir())
        procedures = load_served_procedures(bank_dir(), bank)
        if hearing is None:
            hearing = VoskHearing(vosk_model_dir(), path / "grammar" / "vosk_grammar.json", bank)
        if synth is None:
            synth = PiperSynth(piper_voice_path())
        return cls(bank, hearing, synth, commit, procedures)

    def status(self) -> dict:
        return {"available": True, "why": "", "pocket_commit": self.commit,
                "pocket_repo": PIN["repo"], "bank_version": self.bank.version,
                "bank_hash": self.bank.hash[:8], "set": SERVED_SET,
                "entries": len(self.bank.entries),
                "vosk_model": getattr(self.hearing, "model_name", ""),
                "piper_voice": getattr(self.synth, "voice_name", ""),
                "start_up": self.start_up, "busy": self._busy()}

    def _busy(self) -> bool:
        with self._lease:
            return self._holder is not None and time.monotonic() - self._last <= LEASE_IDLE_S

    def session_for(self, sid: str):
        """The talker's own Pocket session; Busy if another tester holds the engine."""
        from engine.session import Session
        with self._lease:
            now = time.monotonic()
            if self._holder not in (None, sid) and now - self._last <= LEASE_IDLE_S:
                raise Busy()
            if self._holder != sid:
                self._holder = sid
                self._session = Session(self.bank, log=self._dose_log(sid),
                                        procedures=self.procedures)
            self._last = now
            return self._session

    def release(self, sid: str) -> None:
        with self._lease:
            if self._holder == sid:
                self._holder, self._session = None, None

    def _dose_log(self, sid: str) -> Callable:
        def write(record: dict) -> None:
            # Pocket's session logs its start-up line first (set, full version, hash;
            # Pocket #23), then each dose.
            event = "boot" if record.get("event") == "boot" else "dose"
            _log({"event": event, "time": _now(), "session_id": sid,
                  "pocket_commit": self.commit, "bank_version": self.bank.version,
                  "record": record})
        return write

    def turn(self, sid: str, text: str, heard: Optional[str] = None,
             decoder: Optional[str] = None, hear_ms: Optional[float] = None) -> dict:
        session = self.session_for(sid)
        with self._work:
            t0 = time.perf_counter()
            parsed = dataclasses.asdict(session.parse(text))
            # Heard text: a pair the clips or the sound-alike checks confuse asks "X or Y?"
            # first. Typed text cannot be misheard and never asks (owner, 2026-11-15).
            turn = session.handle(text, spoken=heard is not None)
            t1 = time.perf_counter()
            audio = self.synth(turn.text)
            t2 = time.perf_counter()
        turn_id = uuid.uuid4().hex[:16]
        # Two forms (Pocket #10, owner 2026-11-19): "text" is shown (route letters),
        # "spoken" is what Piper says (routes as words).
        answer = {"kind": turn.kind, "text": turn.written_text, "spoken": turn.text}
        timings = {"hear_ms": hear_ms, "engine_ms": round((t1 - t0) * 1000, 1),
                   "synth_ms": round((t2 - t1) * 1000, 1)}
        record = {"event": "turn", "time": _now(), "session_id": sid, "turn_id": turn_id,
                  "input": "typed" if heard is None else "voice", "heard": heard,
                  "decoder": decoder, "text": text, "parse": parsed, "answer": answer,
                  "timings": timings, "pocket_commit": self.commit,
                  "bank_version": self.bank.version}
        _log(record)
        with self._lease:
            self._turns[turn_id] = record
            while len(self._turns) > MAX_TURNS_KEPT:
                self._turns.popitem(last=False)
        return {"turn_id": turn_id, **answer, "heard": heard, "decoder": decoder,
                "parse": parsed, "timings": timings, "bank_version": self.bank.version,
                "pocket_commit": self.commit,
                "audio_wav_b64": base64.b64encode(audio).decode()}

    def recorded(self, sid: str, turn_id: str) -> Optional[dict]:
        with self._lease:
            r = self._turns.get(turn_id)
        return r if r and r["session_id"] == sid else None


# ── requests ────────────────────────────────────────────────────────────────

Sid = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class _Strict(BaseModel):
    # No request may carry a field this file does not define: there is no field
    # that could name a set or a bank, and an unknown one is refused, not ignored.
    model_config = ConfigDict(extra="forbid")


class SayIn(_Strict):
    session_id: Sid
    text: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class ReleaseIn(_Strict):
    session_id: Sid


class FeedbackIn(_Strict):
    session_id: Sid
    turn_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    feedback_type: Literal["appropriate", "flagged"]
    severity: Literal["", "minor", "significant", "dangerous"] = ""
    issues: List[Annotated[str, StringConstraints(max_length=200)]] = Field(default_factory=list,
                                                                             max_length=32)
    suggestion: str = Field("", max_length=4000)
    comment: str = Field("", max_length=4000)


class TimingIn(_Strict):
    session_id: Sid
    turn_id: Annotated[str, StringConstraints(max_length=64)] = ""
    release_to_response_ms: Optional[float] = Field(None, ge=0, le=600_000)
    release_to_first_audio_ms: Optional[float] = Field(None, ge=0, le=600_000)
    input: Literal["voice", "typed"] = "voice"


# ── the routes ──────────────────────────────────────────────────────────────

_AUTO = object()


def mount(app: FastAPI, require_token: Callable, runtime=_AUTO) -> dict:
    """GET /pocket (the page, ungated like /), and the token-gated /pocket/* API.
    runtime: a Runtime, None (unavailable), or loaded at startup in a thread
    (the default), so /health answers while the models load."""
    state = {"runtime": None, "why": "Pocket is starting"}
    if runtime is None:
        state["why"] = "Pocket is not loaded on this server"
    elif runtime is not _AUTO:
        state.update(runtime=runtime, why="")
    else:
        def load():
            try:
                state.update(runtime=Runtime.load(), why="")
                print(f"✅ /pocket: Pocket {PIN['commit'][:12]}, bank {state['runtime'].bank.version}")
            except Exception as e:  # shown on the page; the portal itself is unaffected
                state["why"] = str(e) if isinstance(e, Unavailable) else f"{type(e).__name__}: {e}"
                print(f"⚠️  /pocket unavailable: {state['why']}")

        if os.getenv("POCKET_WEB", "1") == "0":
            state["why"] = "Pocket is switched off on this server (POCKET_WEB=0)"
        else:
            # The same startup hook main.py's voice warm-up uses.
            app.on_event("startup")(lambda: threading.Thread(
                target=load, name="pocket-load", daemon=True).start())

    def rt() -> Runtime:
        if state["runtime"] is None:
            raise HTTPException(status_code=503, detail=f"Pocket unavailable: {state['why']}")
        return state["runtime"]

    def busy(fn, *a, **k):
        try:
            return fn(*a, **k)
        except Busy:
            raise HTTPException(status_code=409, detail="busy, try again") from None

    page = APIRouter()

    @page.get("/pocket", include_in_schema=False)
    def pocket_page():
        return FileResponse(PAGE, media_type="text/html")

    api = APIRouter(prefix="/pocket", dependencies=[Depends(require_token)])

    @api.get("/status")
    def status():
        if state["runtime"] is None:
            return {"available": False, "why": state["why"], "pocket_commit": PIN["commit"],
                    "set": SERVED_SET, "busy": False}
        return state["runtime"].status()

    @api.post("/say")
    def say(body: SayIn):
        return busy(rt().turn, body.session_id, body.text)

    @api.post("/hear")
    async def hear(request: Request, session_id: str):
        if not 0 < len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="session_id")
        runtime = rt()
        try:
            pcm = pcm16k(await request.body())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        def run():
            runtime.session_for(session_id)          # busy before any decoding
            t = time.perf_counter()
            with runtime._work:
                heard, text, decoder = runtime.hearing.hear(pcm)
            hear_ms = round((time.perf_counter() - t) * 1000, 1)
            return runtime.turn(session_id, text, heard=heard, decoder=decoder, hear_ms=hear_ms)
        import asyncio
        return await asyncio.to_thread(busy, run)

    @api.post("/release")
    def release(body: ReleaseIn):
        if state["runtime"] is not None:
            state["runtime"].release(body.session_id)
        return {"status": "released"}

    @api.post("/feedback")
    def feedback(body: FeedbackIn):
        runtime = rt()
        r = runtime.recorded(body.session_id, body.turn_id)
        if r is None:
            raise HTTPException(status_code=404, detail="no such turn on this session")
        _write(FEEDBACK_FILE, {
            "time": _now(), "session_id": body.session_id, "turn_id": body.turn_id,
            "feedback_type": body.feedback_type, "severity": body.severity,
            "issues": body.issues, "suggestion": body.suggestion, "comment": body.comment,
            "input": r["input"], "phrase": r["heard"] if r["heard"] is not None else r["text"],
            "heard": r["heard"], "parse": r["parse"], "answer": r["answer"],
            "pocket_commit": r["pocket_commit"], "bank_version": r["bank_version"]})
        return {"status": "received"}

    @api.post("/timing")
    def timing(body: TimingIn):
        _log({"event": "timing", "time": _now(), **body.model_dump()})
        return {"status": "received"}

    app.include_router(page)
    app.include_router(api)
    # The owner's vocabulary session (owner, 2026-11-16): /pocket/teach, owner token only.
    import pocket_teach
    pocket_teach.mount(app, state, pcm16k)
    return state
