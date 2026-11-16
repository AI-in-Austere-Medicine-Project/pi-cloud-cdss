"""The owner's vocabulary session for Pocket's hearing (owner, 2026-11-16).

A private teach page at /pocket/teach, gated by the owner token, not linked from any
public page. It shows one word or phrase from the active bank's word list; the owner
holds to talk and says it; the clip is stored with what Vosk heard, and the page
advances. Three takes per word, with skip and redo.

What it never does:
  - answer anyone without the owner token. The token is a file outside the repo
    ($POCKET_OWNER_TOKEN_FILE, default ~/pocket-web/owner-token), read on every
    request; with no file the page and its API are 404. The portal's access token
    does not open it.
  - keep clips anywhere but $POCKET_OWNER_CLIPS (default ~/pocket-web/owner-clips),
    outside every repo. They are never committed.
  - run the engine or take the testers' talker lease. It only decodes, holding the
    decoder lock for the length of one clip.

What Vosk heard, stored for each take:
  - "open": the model with no grammar, and its alternatives. These are the spellings
    Vosk actually produces, the source for new sounds-like spellings.
  - "pocket": Pocket's own two-decoder hearing with its committed grammar, as /pocket
    hears, and whether its parse means the word ("as_itself").
"""
import datetime
import hmac
import json
import os
import pathlib
import re
import threading

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse

_DIR = pathlib.Path(__file__).resolve().parent
PAGE = _DIR / "static" / "pocket_teach.html"
TAKES = 3

# The names medics say (owner, 2026-11-16), as the parser spells them.
MEDIC_NAMES = ("keppra", "narcan", "rocephin", "ancef", "versed", "txa", "roc", "sux", "epi",
               "levophed", "vitamin k")
# Said as letters. Shown in capitals, spoken one letter at a time.
LETTERS = {"txa": "t x a", "rsi": "r s i", "iv": "i v", "io": "i o", "im": "i m",
           "in": "i n", "po": "p o"}
ROUTE_LETTERS = ("iv", "io", "im", "in", "po")
ROUTE_WORDS = ("intravenous", "in the vein", "intramuscular", "intraosseous", "intranasal",
               "by mouth", "oral", "line", "neb")
CONTROL_WORDS = ("confirm", "yes", "correct", "affirmative", "no", "cancel", "negative",
                 "stop", "wrong", "repeat", "why", "new patient")
SAMPLES = ("eighty kilos", "seventy kilos", "sixty five kilos", "ninety kilos",
           "one hundred kilos", "one hundred and ten kilos", "fifty kilos", "forty kilos",
           "twenty five kilos", "twelve kilos", "two hundred pounds",
           "one hundred and fifty pounds", "one hundred eighty pounds", "forty pounds",
           "six years", "two years", "three years", "ten years", "eighteen months",
           "nine months")


def owner_token_file() -> pathlib.Path:
    return pathlib.Path(os.getenv("POCKET_OWNER_TOKEN_FILE",
                                  str(pathlib.Path.home() / "pocket-web" / "owner-token")))


def clips_dir() -> pathlib.Path:
    return pathlib.Path(os.getenv("POCKET_OWNER_CLIPS",
                                  str(pathlib.Path.home() / "pocket-web" / "owner-clips")))


def _owner_token() -> str:
    try:
        return owner_token_file().read_text().strip()
    except OSError:
        return ""


def require_owner(x_owner_token: str = Header(default="")) -> None:
    token = _owner_token()
    if not token:
        raise HTTPException(status_code=404)
    if not hmac.compare_digest(x_owner_token.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="owner token required")


# ── the word list ───────────────────────────────────────────────────────────

def _slug(kind: str, say: str) -> str:
    return f"{kind}-" + re.sub(r"[^a-z0-9]+", "-", say.lower()).strip("-")


def _meaning(kind: str, text: str, vocab) -> object:
    """What the parser reads in the text, for this kind of word; None when it reads
    nothing of that kind."""
    from grammar.parser import parse
    from voice import spoken
    p = parse(spoken.normalise(text), vocab)
    if kind in ("drug", "medic"):
        out = [d.generics for d in p.drugs]
    elif kind == "indication":
        out = list(p.classes)
    elif kind == "route":
        out = list(p.routes)
    elif kind == "control":
        out = list(p.controls)
    else:
        out = [(p.weight.value, p.weight.unit) if p.weight else None,
               (p.age.value, p.age.unit) if p.age else None]
        out = [x for x in out if x]
    return out or None


def teach_words(bank, vocab) -> list:
    """Every word for the session, generated from the active bank: each signed drug
    name, the names medics say, each indication, each route as letters and as words,
    the control words, and twenty sample weights and ages."""
    items, seen = [], set()

    def add(kind, say, note=""):
        say = LETTERS.get(say, say)
        if say in seen:
            return
        seen.add(say)
        show = say.replace(" ", "").upper() if say in LETTERS.values() else say
        show = re.sub(r"\b(tbi|cns)\b", lambda m: m.group(1).upper(), show)
        spelled = say in LETTERS.values() or show != say
        items.append({"id": _slug(kind, say), "kind": kind, "say": say, "show": show,
                      "note": note or ("say the letters" if spelled else ""),
                      "expect": _meaning(kind, say, vocab)})

    from grammar.vocabulary import _say_term
    signed = {e["drug"] for e in bank.entries}
    for generic in sorted(signed):
        if _say_term(generic) == generic:     # "sodium chloride 3%" is said by its aliases
            add("drug", generic)
    for name in MEDIC_NAMES:
        add("medic", name)
    for term in sorted(vocab.signed_terms()):
        add("drug", term)
    for term in sorted(vocab.class_terms):
        if "aem" in term and term.replace("aem", "em") in vocab.class_terms:
            continue                          # said the same as its US spelling
        add("indication", term.replace(" ", "") if term == "r s i" else term)
    for r in ROUTE_LETTERS:
        add("route", r)
    for r in ROUTE_WORDS:
        add("route", r)
    for c in CONTROL_WORDS:
        add("control", c)
    for s in SAMPLES:
        add("sample", s)
    return items


# ── a take ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def recorded(word_id: str) -> dict:
    """take number -> its stored record, for one word."""
    d = clips_dir() / word_id
    out = {}
    for f in sorted(d.glob("take*.json")) if d.exists() else ():
        try:
            out[int(f.stem[4:])] = json.loads(f.read_text())
        except (ValueError, OSError):
            continue
    return out


def store_take(word: dict, take: int, wav: bytes, pcm: bytes, hearing, vocab, lock) -> dict:
    with lock:
        open_text, alternatives = hearing.hear_open(pcm)
        heard, text, decoder = hearing.hear(pcm)
    got = _meaning(word["kind"], text, vocab)
    as_itself = (got == word["expect"]) if word["expect"] is not None else (
        text.strip() == word["say"])
    record = {"word_id": word["id"], "kind": word["kind"], "say": word["say"], "take": take,
              "time": _now(), "open": open_text, "open_alternatives": alternatives,
              "pocket": {"heard": heard, "text": text, "decoder": decoder},
              "expect": word["expect"], "got": got, "as_itself": as_itself}
    d = clips_dir() / word["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"take{take}.wav").write_bytes(wav)
    (d / f"take{take}.json").write_text(json.dumps(record, indent=1, default=list))
    with open(clips_dir() / "session.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "take", **record}, default=list) + "\n")
    return record


# ── the routes ──────────────────────────────────────────────────────────────

def mount(app: FastAPI, state: dict, pcm16k) -> None:
    """GET /pocket/teach (the page; 404 with no owner token file) and its owner-gated
    API. state is pocket_web.mount's: the runtime, once loaded."""
    cache = {}

    def runtime():
        rt = state.get("runtime")
        if rt is None:
            raise HTTPException(status_code=503, detail=f"Pocket unavailable: {state.get('why')}")
        return rt

    def words(rt) -> list:
        key = rt.bank.hash
        if key not in cache:
            from grammar.vocabulary import build
            cache.clear()
            cache[key] = (teach_words(rt.bank, build(rt.bank)), build(rt.bank))
        return cache[key]

    def word(rt, word_id: str):
        items, vocab = words(rt)
        for w in items:
            if w["id"] == word_id:
                return w, vocab
        raise HTTPException(status_code=404, detail="no such word")

    page = APIRouter()

    @page.get("/pocket/teach", include_in_schema=False)
    def teach_page():
        if not _owner_token():
            raise HTTPException(status_code=404)
        return FileResponse(PAGE, media_type="text/html",
                            headers={"X-Robots-Tag": "noindex, nofollow",
                                     "Cache-Control": "no-store"})

    api = APIRouter(prefix="/pocket/teach", dependencies=[Depends(require_owner)])

    @api.get("/words")
    def word_list():
        rt = runtime()
        items, _ = words(rt)
        return {"bank_version": rt.bank.version, "pocket_commit": rt.commit, "takes": TAKES,
                "words": [{**w, "recorded": sorted(recorded(w["id"]))} for w in items]}

    @api.post("/clip")
    async def clip(request: Request, word_id: str, take: int):
        rt = runtime()
        w, vocab = word(rt, word_id)
        if not 1 <= take <= TAKES:
            raise HTTPException(status_code=422, detail=f"take is 1 to {TAKES}")
        wav = await request.body()
        try:
            pcm = pcm16k(wav)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        import asyncio
        return await asyncio.to_thread(store_take, w, take, wav, pcm, rt.hearing, vocab, rt._work)

    @api.post("/skip")
    def skip(word_id: str):
        w, _ = word(runtime(), word_id)
        clips_dir().mkdir(parents=True, exist_ok=True)
        with open(clips_dir() / "session.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "skip", "word_id": w["id"], "time": _now()}) + "\n")
        return {"status": "skipped"}

    app.include_router(page)
    app.include_router(api)
