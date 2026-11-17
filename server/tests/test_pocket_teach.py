"""The owner's vocabulary session for Pocket's hearing (owner, 2026-11-16).

Owner: "A private teach page on the portal (owner token only, not linked from the
public page). It shows one word or phrase, I hold to talk and say it, it stores the
clip and what Vosk heard, then advances. Three takes each, with skip and redo. Clips
stay private in ~/pocket-web/owner-clips, never committed. Word list, generated from
the active bank: every signed drug name and the names medics say (keppra, narcan,
rocephin, ancef, versed, TXA, roc, sux, epi, levophed, vitamin K), every indication
word, every route as letters and as words, control words (confirm, yes, correct,
affirmative, no, cancel, negative, stop, wrong, repeat, why, new patient), and 20
sample weights and ages ("eighty kilos", "two hundred pounds", "six years")."
"""
import io
import json
import os
import pathlib
import re
import sys
import wave

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed")
pytest.importorskip("httpx", reason="httpx is not installed")
from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SERVER = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import pocket_web as pw  # noqa: E402

CHECKOUT = pw.checkout_dir()
pytestmark = pytest.mark.skipif(
    not (CHECKOUT / ".git").exists(),
    reason=f"Pocket is not installed at {CHECKOUT}: run server/tools/install_pocket.py")

ACCESS = {"X-Access-Token": "pocket-test-token"}
OWNER_TOKEN = "owner-secret-for-tests"
OWNER = {"X-Owner-Token": OWNER_TOKEN}


def _gate(x_access_token: str = Header(default="")):
    if x_access_token != ACCESS["X-Access-Token"]:
        raise HTTPException(status_code=401, detail="Invalid access token")


class FakeHearing:
    """Hears whatever the test says, on both decoders."""
    def __init__(self):
        self.next, self.open = "", ""

    def hear(self, pcm):
        return self.next, self.next, "spelled"

    def hear_open(self, pcm):
        return self.open, [self.open]


def _wav(seconds=0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


@pytest.fixture
def owner(tmp_path, monkeypatch):
    f = tmp_path / "owner-token"
    f.write_text(OWNER_TOKEN + "\n")
    monkeypatch.setenv("POCKET_OWNER_TOKEN_FILE", str(f))
    monkeypatch.setenv("POCKET_OWNER_CLIPS", str(tmp_path / "owner-clips"))
    monkeypatch.setenv("POCKET_CONTRIBUTORS_FILE", str(tmp_path / "contributors.json"))
    monkeypatch.setattr(pw, "LOG_DIR", tmp_path / "pocket-logs")
    return tmp_path / "owner-clips"


@pytest.fixture
def hearing():
    return FakeHearing()


@pytest.fixture
def runtime(owner, hearing):
    return pw.Runtime.load(hearing=hearing, synth=lambda t: b"RIFF")


@pytest.fixture
def client(runtime):
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=runtime)
    return TestClient(app)


def _words(client):
    return client.get("/pocket/teach/words", headers=OWNER).json()["words"]


def _clip(client, word_id, take=1):
    return client.post(f"/pocket/teach/clip?word_id={word_id}&take={take}", content=_wav(),
                       headers={**OWNER, "Content-Type": "audio/wav"})


# ── private ─────────────────────────────────────────────────────────────────

def test_with_no_owner_token_file_the_page_and_its_api_do_not_exist(tmp_path, monkeypatch, runtime):
    monkeypatch.setenv("POCKET_OWNER_TOKEN_FILE", str(tmp_path / "absent"))
    monkeypatch.setenv("POCKET_CONTRIBUTORS_FILE", str(tmp_path / "absent-contributors.json"))
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=runtime)
    c = TestClient(app)
    assert c.get("/pocket/teach").status_code == 404
    assert c.get("/pocket/teach/words", headers={**ACCESS, "X-Owner-Token": ""}).status_code == 404


def test_the_api_answers_the_owner_token_only(client):
    assert client.get("/pocket/teach/words").status_code == 401
    assert client.get("/pocket/teach/words", headers=ACCESS).status_code == 401
    assert client.get("/pocket/teach/words", headers={"X-Owner-Token": "edgecdss-demo-2026"}).status_code == 401
    assert client.get("/pocket/teach/words", headers=OWNER).status_code == 200
    assert client.post("/pocket/teach/clip?word_id=medic-narcan&take=1", content=_wav(),
                       headers=ACCESS).status_code == 401


def test_the_page_is_served_unindexed_and_no_public_page_links_it(client):
    r = client.get("/pocket/teach")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "noindex" in r.headers.get("x-robots-tag", "")
    for public in ("pocket.html", "index.html"):
        assert "/pocket/teach" not in (SERVER / "static" / public).read_text(), public
    for page in (SERVER.parent / "web").glob("*.html"):
        assert "/pocket/teach" not in page.read_text(), page.name


def test_the_page_has_hold_to_talk_three_takes_skip_and_redo():
    import pocket_teach
    html = pocket_teach.PAGE.read_text()
    for slot in ('id="talk"', 'id="skip"', 'id="redo"', 'id="word"', 'id="password"'):
        assert slot in html, slot
    assert "/pocket/teach/clip" in html and "X-Teach-Password" in html
    assert 'name="robots" content="noindex' in html
    assert pocket_teach.TAKES == 3


def test_clips_are_kept_outside_every_repo():
    import pocket_teach
    os.environ.pop("POCKET_OWNER_CLIPS", None)
    d = pocket_teach.clips_dir()
    assert d == pathlib.Path.home() / "pocket-web" / "owner-clips"
    assert SERVER.parent not in d.parents and CHECKOUT not in d.parents


# ── the word list ───────────────────────────────────────────────────────────

def test_the_word_list_is_generated_from_the_active_bank(client, runtime):
    words = _words(client)
    said = {w["say"] for w in words}
    by_kind = lambda k: {w["say"] for w in words if w["kind"] == k}  # noqa: E731
    # Every signed drug, by its own name where that can be said ("sodium chloride 3%"
    # cannot; "hypertonic saline" is said for it).
    named = {g for w in words if w["kind"] in ("drug", "medic") for g in (w["expect"] or [[]])[0]}
    assert {e["drug"] for e in runtime.bank.entries} <= named
    assert {"keppra", "narcan", "rocephin", "ancef", "versed", "t x a", "roc", "sux", "epi",
            "levophed", "vitamin k"} <= said
    from grammar.vocabulary import build
    v = build(runtime.bank)
    assert set(v.signed_terms()) - {"txa"} <= said                       # every signed name
    classes = {c for c in v.class_terms if not ("aem" in c and c.replace("aem", "em") in v.class_terms)}
    assert classes - {"r s i", "rsi"} <= by_kind("indication") and "r s i" in by_kind("indication")
    assert {"i v", "i o", "i m", "i n", "p o"} <= by_kind("route")
    assert {"intravenous", "intramuscular", "intraosseous", "intranasal", "by mouth",
            "oral", "in the vein"} <= by_kind("route")
    assert by_kind("control") == {"confirm", "yes", "correct", "affirmative", "no", "cancel",
                                  "negative", "stop", "wrong", "repeat", "why", "new patient"}
    samples = by_kind("sample")
    assert len(samples) == 20 and {"eighty kilos", "two hundred pounds", "six years"} <= samples


def test_each_word_has_one_safe_id_and_letters_are_shown_as_letters(client):
    words = _words(client)
    ids = [w["id"] for w in words]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z]+-[a-z0-9-]+", i) for i in ids)
    shown = {w["say"]: w["show"] for w in words}
    assert shown["t x a"] == "TXA" and shown["i v"] == "IV" and shown["r s i"] == "RSI"


def test_every_word_but_the_new_control_words_means_something_to_pocket(client):
    """Each drug, indication, route and sample parses, typed, as itself; its meaning is
    what a take is checked against."""
    for w in _words(client):
        if w["kind"] != "control":
            assert w["expect"], w["say"]


# ── a take ──────────────────────────────────────────────────────────────────

def test_a_take_stores_the_clip_and_what_vosk_heard(client, hearing, owner):
    hearing.open, hearing.next = "keep her", "keppra"
    r = _clip(client, "medic-keppra")
    assert r.status_code == 200
    d = r.json()
    assert d["open"] == "keep her" and d["open_alternatives"] == ["keep her"]
    assert d["pocket"] == {"heard": "keppra", "text": "keppra", "decoder": "spelled"}
    assert d["as_itself"] is True
    assert (owner / "speaker-1" / "medic-keppra" / "take1.wav").read_bytes() == _wav()
    assert json.loads((owner / "speaker-1" / "medic-keppra" / "take1.json").read_text())["open"] == "keep her"


def test_a_take_heard_as_another_word_is_not_as_itself(client, hearing):
    hearing.open = hearing.next = "ketamine"
    assert _clip(client, "medic-narcan").json()["as_itself"] is False


def test_three_takes_redo_overwrites_and_a_fourth_is_refused(client, hearing, owner):
    for take in (1, 2, 3):
        hearing.open = hearing.next = "narcan"
        assert _clip(client, "medic-narcan", take).status_code == 200
    hearing.open = "nar can"
    _clip(client, "medic-narcan", 2)                                      # redo take 2
    assert json.loads((owner / "speaker-1" / "medic-narcan" / "take2.json").read_text())["open"] == "nar can"
    assert _clip(client, "medic-narcan", 4).status_code == 422
    assert _clip(client, "medic-narcan", 0).status_code == 422
    w = next(w for w in _words(client) if w["id"] == "medic-narcan")
    assert w["recorded"] == [1, 2, 3]


def test_skip_is_recorded_and_an_unknown_word_is_refused(client, owner):
    assert client.post("/pocket/teach/skip?word_id=medic-sux", headers=OWNER).status_code == 200
    lines = [json.loads(x) for x in (owner / "speaker-1" / "session.jsonl").read_text().splitlines()]
    assert lines[-1]["event"] == "skip" and lines[-1]["word_id"] == "medic-sux"
    assert _clip(client, "../../etc").status_code == 404
    assert client.post("/pocket/teach/skip?word_id=nope", headers=OWNER).status_code == 404


def test_a_take_does_not_hold_the_testers_lease_or_write_their_logs(client, runtime, hearing):
    runtime.session_for("tester-a")                       # a tester is talking
    hearing.open = hearing.next = "epi"
    assert _clip(client, "medic-epi").status_code == 200
    assert runtime._holder == "tester-a"
    assert not pw.LOG_DIR.exists() or not any(pw.LOG_DIR.iterdir())


def test_the_real_hearing_decodes_open_and_with_pockets_grammar():
    import importlib.util
    if not (pw.vosk_model_dir().exists() and importlib.util.find_spec("vosk")):
        pytest.skip("the Vosk model is not installed")
    pw._import_pocket(CHECKOUT)
    bank = pw.load_pfc_bank(pw.bank_dir())
    h = pw.VoskHearing(pw.vosk_model_dir(), CHECKOUT / "grammar" / "vosk_grammar.json", bank)
    text, alternatives = h.hear_open(b"\x00\x00" * 8000)
    assert text == "" and isinstance(alternatives, list)
