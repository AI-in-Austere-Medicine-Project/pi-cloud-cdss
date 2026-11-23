"""The owner's vocabulary session for Pocket's hearing (owner, 2026-11-16).

A private teach page at /pocket/teach, gated by the owner token, not linked from any
public page. It shows one word or phrase from the active bank's word list; the owner
holds to talk and says it; the clip is stored with what Vosk heard, and the page
advances. Three takes per word, with skip and redo.

What it never does:
  - answer anyone without the owner token or, when the owner has turned contributor
    access on, the contributor password. The token is a file outside the repo
    ($POCKET_OWNER_TOKEN_FILE, default ~/pocket-web/owner-token), read on every
    request; with neither the page and its API are 404. The portal's access token
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

Contributors (owner, 2026-11-17): one shared password, set with
server/tools/pocket_contributors.py and kept hashed in $POCKET_CONTRIBUTORS_FILE
(default ~/pocket-web/contributors.json, mode 600). It opens the teach page and its
API only; the portal's own gate never reads it. Access is off until the owner turns it
on. Each browser is given the next free label (speaker-2, speaker-3, ...; the owner is
speaker-1) and a random key it keeps; only a hash of the key is stored, and no name
is ever asked. Takes are stored per speaker, <clips>/<speaker>/<word_id>/take<n>.json
(the owner's earlier clips move there with pocket_contributors.py migrate).
Contributors are capped in takes per day and in total, per clip length, and in new
labels per day. The owner is not capped.

A contributor's audio is never kept (owner, 2026-11-17): it is decoded in memory and
dropped; only the text the network heard, the word and the speaker label are written.
The owner's own takes (speaker-1) keep the WAV beside the record.
"""
import datetime
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import shutil
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


# ── contributors ────────────────────────────────────────────────────────────

LABEL_PREFIX = "speaker-"
OWNER_LABEL = LABEL_PREFIX + "1"
_LABEL = re.compile(r"^speaker-[1-9][0-9]{0,5}$")
CONSENT = ("Your recording is deleted once it has been processed. Only the text of what the "
           "network heard is kept, and it may be used in this open-source project and future "
           "AI-AMP projects. No name or other information is requested.")
# Contributor limits; the owner changes them with pocket_contributors.py limits k=v.
# Counts of takes: a contributor's audio is not stored, so there is no size to cap.
LIMITS = {"takes_per_day": 450, "takes_total": 1500, "clip_seconds": 6.0,
          "new_speakers_per_day": 20}
_ITERATIONS = 60_000
_files = threading.RLock()          # the config, speakers.json and usage.json


def contributors_file() -> pathlib.Path:
    return pathlib.Path(os.getenv("POCKET_CONTRIBUTORS_FILE",
                                  str(pathlib.Path.home() / "pocket-web" / "contributors.json")))


def _write_private(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _read(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_config() -> dict:
    cfg = _read(contributors_file())
    return {"enabled": bool(cfg.get("enabled")), "password": cfg.get("password"),
            "limits": dict(cfg.get("limits") or {})}


def save_config(cfg: dict) -> None:
    with _files:
        _write_private(contributors_file(), cfg)


def limits(cfg: dict = None) -> dict:
    cfg = cfg if cfg is not None else load_config()
    return {**LIMITS, **{k: v for k, v in cfg["limits"].items() if k in LIMITS}}


def _hash(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations).hex()


def set_password(password: str) -> None:
    with _files:
        cfg = load_config()
        salt = secrets.token_bytes(16)
        cfg["password"] = {"salt": salt.hex(), "iterations": _ITERATIONS,
                           "hash": _hash(password, salt, _ITERATIONS)}
        save_config(cfg)


def set_enabled(on: bool) -> None:
    with _files:
        cfg = load_config()
        cfg["enabled"] = bool(on)
        save_config(cfg)


def set_limits(changes: dict) -> None:
    with _files:
        cfg = load_config()
        cfg["limits"].update(changes)
        save_config(cfg)


_checked: dict = {}


def check_password(password: str, cfg: dict) -> bool:
    stored = cfg.get("password")
    if not (password and stored):
        return False
    key = (stored["hash"], hashlib.sha256(password.encode()).hexdigest())
    if key not in _checked:
        if len(_checked) > 64:
            _checked.clear()
        _checked[key] = hmac.compare_digest(
            _hash(password, bytes.fromhex(stored["salt"]), int(stored["iterations"])),
            stored["hash"])
    return _checked[key]


def _speakers_file() -> pathlib.Path:
    return clips_dir() / "speakers.json"


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _today() -> str:
    return datetime.date.today().isoformat()


def speaker_for_key(key: str):
    if not key:
        return None
    s = _read(_speakers_file()).get("speakers", {}).get(_key_hash(key))
    return s["label"] if s else None


def new_speaker(cfg: dict) -> tuple:
    """The next label and a fresh key for a new browser, or HTTPException 429."""
    with _files:
        data = _read(_speakers_file())
        today = data.get("new_per_day", {}).get(_today(), 0)
        if today >= limits(cfg)["new_speakers_per_day"]:
            raise HTTPException(status_code=429, detail=(
                "Thank you for offering to help. Today's places for new speakers are full; "
                "please try again tomorrow."))
        n = max(int(data.get("next", 2)), 2)
        label, key = f"{LABEL_PREFIX}{n}", secrets.token_urlsafe(24)
        data.setdefault("speakers", {})[_key_hash(key)] = {"label": label, "created": _now()}
        data["next"] = n + 1
        data["new_per_day"] = {_today(): today + 1}
        _write_private(_speakers_file(), data)
        return label, key


def speaker_dir(label: str) -> pathlib.Path:
    if not _LABEL.match(label or ""):
        raise ValueError(f"not a speaker label: {label!r}")
    return clips_dir() / label


def delete_speaker(label: str) -> bool:
    """Remove one speaker's clips and their browser key. False if there was neither.
    The label is not given out again."""
    d = speaker_dir(label)
    with _files:
        data = _read(_speakers_file())
        keys = [k for k, s in data.get("speakers", {}).items() if s["label"] == label]
        found = d.exists() or bool(keys)
        for k in keys:
            del data["speakers"][k]
        if keys:
            _write_private(_speakers_file(), data)
        if d.exists():
            shutil.rmtree(d)
    return found


def speakers() -> list:
    """Each speaker folder: label, takes, and the audio kept (the owner's only)."""
    out = []
    root = clips_dir()
    for d in root.glob(LABEL_PREFIX + "*") if root.exists() else ():
        if d.is_dir() and _LABEL.match(d.name):
            wavs = list(d.glob("*/take*.wav"))
            out.append({"label": d.name, "takes": len(list(d.glob("*/take*.json"))),
                        "audio_files": len(wavs),
                        "bytes": sum(w.stat().st_size for w in wavs)})
    return sorted(out, key=lambda s: int(s["label"][len(LABEL_PREFIX):]))


_LEGACY = re.compile(r"^(drug|medic|indication|route|control|sample)-[a-z0-9-]+$")


def migrate_legacy() -> int:
    """The owner's clips from before contributors (<clips>/<word_id>/) move to speaker-1.
    Run by the owner (pocket_contributors.py migrate) once the new code is deployed,
    never by the server or on mount: a process that only mounts the page must not move
    the live service's clips from under it. Idempotent; nothing is overwritten.
    Returns how many entries moved."""
    root, moved = clips_dir(), 0
    if not root.exists():
        return 0
    dest = root / OWNER_LABEL
    with _files:
        for p in sorted(root.iterdir()):
            if (p.is_dir() and _LEGACY.match(p.name)) or p.name == "session.jsonl":
                target = dest / p.name
                if target.exists():
                    continue
                dest.mkdir(parents=True, exist_ok=True, mode=0o700)
                p.rename(target)
                moved += 1
    return moved


def all_takes():
    """Every stored take of every speaker, for the spelling step and the re-run (which
    report per speaker and overall): its record plus speaker, word_id, take and the
    clip's path, or None for a contributor (only the text heard is kept)."""
    for s in speakers():
        for f in sorted((clips_dir() / s["label"]).glob("*/take*.json")):
            try:
                rec, take = json.loads(f.read_text()), int(f.stem[4:])
            except (ValueError, OSError):
                continue
            wav = f.with_suffix(".wav")
            yield {**rec, "speaker": s["label"], "word_id": f.parent.name, "take": take,
                   "wav": str(wav) if wav.exists() else None}


def teach_speaker(x_owner_token: str = Header(default=""),
                  x_teach_password: str = Header(default="")) -> dict:
    """Who is asking: the owner (the owner token, in either header) or, with contributor
    access on, anyone with the contributor password. The portal's access token is not
    read here, and the portal's gate never reads these headers."""
    owner = _owner_token()
    for given in (x_owner_token, x_teach_password):
        if owner and given and hmac.compare_digest(given.encode(), owner.encode()):
            return {"role": "owner", "label": OWNER_LABEL}
    cfg = load_config()
    if not x_teach_password:
        if not owner and not cfg["enabled"]:
            raise HTTPException(status_code=404)
        raise HTTPException(status_code=401, detail="password required")
    if not cfg["enabled"]:
        raise HTTPException(status_code=403, detail=(
            "Contributor recording is off right now. Thank you for offering; please try "
            "again later."))
    if not check_password(x_teach_password, cfg):
        raise HTTPException(status_code=401, detail="That password is not right.")
    return {"role": "contributor", "label": None, "cfg": cfg}


def require_speaker(who: dict = Depends(teach_speaker),
                    x_speaker_key: str = Header(default="")) -> dict:
    if who["role"] == "owner":
        return who
    label = speaker_for_key(x_speaker_key)
    if not label:
        raise HTTPException(status_code=401, detail=(
            "This browser's speaker label is not known (it may have been deleted). "
            "Reload the page to be given a new one."))
    return {**who, "label": label}


def _usage_file(label: str) -> pathlib.Path:
    return speaker_dir(label) / "usage.json"


def check_limits(label: str, cfg: dict, replaces: pathlib.Path) -> None:
    """HTTPException 429, said politely, when this take would pass a contributor's caps."""
    lim = limits(cfg)
    day = _read(_usage_file(label)).get("days", {}).get(_today(), {}).get("takes", 0)
    if day + 1 > lim["takes_per_day"]:
        raise HTTPException(status_code=429, detail=(
            f"Thank you! That is today's limit of {lim['takes_per_day']} recordings for this "
            "browser. Please come back tomorrow to carry on where you left off."))
    have = [s for s in speakers() if s["label"] == label]
    takes = have[0]["takes"] if have else 0
    if replaces.exists():                       # a redo replaces a stored take
        takes -= 1
    if takes + 1 > lim["takes_total"]:
        raise HTTPException(status_code=429, detail=(
            "Thank you! This browser has reached its limit of recordings in all. Your "
            "clips are kept; there is nothing more to do."))


def count_usage(label: str) -> None:
    with _files:
        f = _usage_file(label)
        data = _read(f)
        day = data.get("days", {}).get(_today(), {}).get("takes", 0)
        data["days"] = {_today(): {"takes": day + 1}}
        _write_private(f, data)


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
    signed = {e["drug"] for e in bank.entries} | {x["drug"] for x in getattr(bank, "silent", [])}
    for generic in sorted(signed):
        if _say_term(generic) == generic:     # "sodium chloride 3%" is said by its aliases
            add("drug", generic)
    for name in MEDIC_NAMES:              # only those naming a signed drug of the bank (2026-11-23)
        meant = _meaning("medic", name, vocab)
        if meant and all(set(g) <= signed for g in meant):
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


def recorded(word_id: str, label: str = OWNER_LABEL) -> dict:
    """take number -> its stored record, for one word and one speaker."""
    d = speaker_dir(label) / word_id
    out = {}
    for f in sorted(d.glob("take*.json")) if d.exists() else ():
        try:
            out[int(f.stem[4:])] = json.loads(f.read_text())
        except (ValueError, OSError):
            continue
    return out


def skipped(label: str) -> set:
    """The words this speaker skipped and has not recorded since."""
    out = set()
    try:
        lines = (speaker_dir(label) / "session.jsonl").read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        (out.add if e.get("event") == "skip" else out.discard)(e.get("word_id"))
    return out


def _log(label: str, event: dict) -> None:
    d = speaker_dir(label)
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(d / "session.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=list) + "\n")


def store_take(word: dict, take: int, wav: bytes, pcm: bytes, hearing, vocab, lock,
               label: str = OWNER_LABEL) -> dict:
    """Decode one take and store it. The owner's take keeps its WAV and the full record;
    a contributor's keeps only the text heard, the word and the label. Their audio is
    only ever in memory, and is dropped here. Returns the full result for the page."""
    with lock:
        open_text, alternatives = hearing.hear_open(pcm)
        heard, text, decoder = hearing.hear(pcm)
    got = _meaning(word["kind"], text, vocab)
    as_itself = (got == word["expect"]) if word["expect"] is not None else (
        text.strip() == word["say"])
    record = {"speaker": label, "word_id": word["id"], "kind": word["kind"], "say": word["say"], "take": take,
              "time": _now(), "open": open_text, "open_alternatives": alternatives,
              "pocket": {"heard": heard, "text": text, "decoder": decoder},
              "expect": word["expect"], "got": got, "as_itself": as_itself}
    d = speaker_dir(label) / word["id"]
    d.mkdir(parents=True, exist_ok=True)
    if label == OWNER_LABEL:
        (d / f"take{take}.wav").write_bytes(wav)
        (d / f"take{take}.json").write_text(json.dumps(record, indent=1, default=list))
        _log(label, {"event": "take", **record})
        return record
    kept = {k: record[k] for k in ("speaker", "word_id", "kind", "say", "take", "open",
                                   "open_alternatives", "pocket")}
    (d / f"take{take}.wav").unlink(missing_ok=True)
    (d / f"take{take}.json").write_text(json.dumps(kept, indent=1, default=list))
    _log(label, {"event": "take", "word_id": word["id"], "take": take})
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
        """The served bank's words: the one drug list, the EMS set (owner, 2026-11-23)."""
        key = rt.bank.hash
        if key not in cache:
            from grammar.vocabulary import build
            vocab = build(rt.bank)
            cache.clear()
            cache[key] = (teach_words(rt.bank, vocab), vocab)
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
        if not _owner_token() and not load_config()["enabled"]:
            raise HTTPException(status_code=404)
        return FileResponse(PAGE, media_type="text/html",
                            headers={"X-Robots-Tag": "noindex, nofollow",
                                     "Cache-Control": "no-store"})

    api = APIRouter(prefix="/pocket/teach")

    @api.post("/hello")
    def hello(who: dict = Depends(teach_speaker), x_speaker_key: str = Header(default="")):
        """This browser's speaker label: the owner is speaker-1; a contributor keeps the
        label their key names, or is given the next one. Nothing else is asked."""
        if who["role"] == "owner":
            return {"role": "owner", "speaker": OWNER_LABEL, "consent": CONSENT}
        label, key = speaker_for_key(x_speaker_key), x_speaker_key
        if not label:
            label, key = new_speaker(who["cfg"])
        return {"role": "contributor", "speaker": label, "speaker_key": key,
                "consent": CONSENT, "limits": limits(who["cfg"])}

    @api.get("/words")
    def word_list(who: dict = Depends(require_speaker)):
        rt = runtime()
        items, _ = words(rt)
        skips = skipped(who["label"])
        return {"bank_version": rt.bank.version, "pocket_commit": rt.commit, "takes": TAKES,
                "speaker": who["label"],
                "words": [{**w, "recorded": sorted(recorded(w["id"], who["label"])),
                           "skipped": w["id"] in skips} for w in items]}

    def too_long(seconds: float) -> HTTPException:
        return HTTPException(status_code=413, detail=(
            f"That recording is longer than {seconds:g} seconds. Please say just the word "
            "and let go; then try again."))

    @api.post("/clip")
    async def clip(request: Request, word_id: str, take: int,
                   who: dict = Depends(require_speaker)):
        rt = runtime()
        w, vocab = word(rt, word_id)
        if not 1 <= take <= TAKES:
            raise HTTPException(status_code=422, detail=f"take is 1 to {TAKES}")
        label, cfg = who["label"], who.get("cfg")
        if cfg is not None:                     # a contributor: capped; the owner is not
            seconds = limits(cfg)["clip_seconds"]
            cap, wav = int(seconds * 16000 * 2) + 4096, bytearray()
            async for chunk in request.stream():
                wav += chunk
                if len(wav) > cap:
                    raise too_long(seconds)
            wav = bytes(wav)
        else:
            wav = await request.body()
        try:
            pcm = pcm16k(wav)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        if cfg is not None:
            if len(pcm) > seconds * 16000 * 2:
                raise too_long(seconds)
            with _files:
                check_limits(label, cfg, speaker_dir(label) / w["id"] / f"take{take}.json")
                count_usage(label)
        import asyncio
        return await asyncio.to_thread(store_take, w, take, wav, pcm, rt.hearing, vocab,
                                       rt._work, label)

    @api.post("/skip")
    def skip(word_id: str, who: dict = Depends(require_speaker)):
        w, _ = word(runtime(), word_id)
        event = {"event": "skip", "word_id": w["id"]}
        _log(who["label"], {**event, "time": _now()} if who["label"] == OWNER_LABEL else event)
        return {"status": "skipped"}

    app.include_router(page)
    app.include_router(api)
