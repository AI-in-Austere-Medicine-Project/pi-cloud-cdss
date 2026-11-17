"""Teach page: one shared contributor password (owner, 2026-11-17).

Owner: "One shared contributor password instead of per-person tokens. A single password
I set in a private file on the Jetson (start with "pocket-voice"). It opens the teach
page only, nothing else on the portal. My owner token still works as before. Each
browser is given its own speaker label automatically (speaker-2, speaker-3, and so on),
remembered in that browser. No names are collected. Contributors can skip freely and
resume where they left off. Limits: a cap on clips and total size per speaker and per
day, and a cap on clip length. Over the limit, the page says so politely. A command to
turn contributor access on and off, to change the password, and to delete one
speaker's clips. A consent line on the page: recordings are kept privately to improve
speech recognition and can be deleted on request. Clips stay in the private folder,
stored per speaker, never committed. The spelling step and the re-run use every
speaker's clips and report per speaker and overall."
"""
import importlib.util
import io
import json
import os
import pathlib
import stat
import sys
import wave

import pytest

pytest.importorskip("fastapi", reason="fastapi is not installed")
pytest.importorskip("httpx", reason="httpx is not installed")
from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
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
CONSENT = ("Your recording is deleted once it has been processed. Only the text of what the "
           "network heard is kept, and it may be used in this open-source project and future "
           "AI-AMP projects. No name or other information is requested.")
OWNER_TOKEN = "owner-secret-for-tests"
PASSWORD = "pocket-voice"


def _gate(x_access_token: str = Header(default="")):
    if x_access_token != ACCESS["X-Access-Token"]:
        raise HTTPException(status_code=401, detail="Invalid access token")


class FakeHearing:
    def __init__(self):
        self.text = "narcan"

    def hear(self, pcm):
        return self.text, self.text, "spelled"

    def hear_open(self, pcm):
        return self.text, [self.text]


def _wav(seconds=0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def _tool():
    spec = importlib.util.spec_from_file_location(
        "pocket_contributors", SERVER / "tools" / "pocket_contributors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def clips(tmp_path, monkeypatch):
    (tmp_path / "owner-token").write_text(OWNER_TOKEN + "\n")
    monkeypatch.setenv("POCKET_OWNER_TOKEN_FILE", str(tmp_path / "owner-token"))
    monkeypatch.setenv("POCKET_OWNER_CLIPS", str(tmp_path / "owner-clips"))
    monkeypatch.setenv("POCKET_CONTRIBUTORS_FILE", str(tmp_path / "contributors.json"))
    monkeypatch.setattr(pw, "LOG_DIR", tmp_path / "pocket-logs")
    return tmp_path / "owner-clips"


@pytest.fixture
def tool(clips):
    t = _tool()
    return lambda *argv, stdin="": t.main(list(argv), stdin=io.StringIO(stdin))


@pytest.fixture
def on(tool):
    assert tool("password", stdin=PASSWORD + "\n" + PASSWORD + "\n") == 0
    assert tool("on") == 0


@pytest.fixture
def client(clips):
    runtime = pw.Runtime.load(hearing=FakeHearing(), synth=lambda t: b"RIFF")
    app = FastAPI()

    @app.get("/api/portal-thing", dependencies=[Depends(_gate)])
    def portal_thing():
        return {"ok": True}

    pw.mount(app, require_token=_gate, runtime=runtime)
    return TestClient(app)


def _hello(client, key="", password=PASSWORD):
    h = {"X-Teach-Password": password}
    if key:
        h["X-Speaker-Key"] = key
    return client.post("/pocket/teach/hello", headers=h)


def _browser(client):
    """A new browser: its label and the headers it sends from then on."""
    d = _hello(client).json()
    return d["speaker"], {"X-Teach-Password": PASSWORD, "X-Speaker-Key": d["speaker_key"]}


def _clip(client, headers, word_id="medic-narcan", take=1, seconds=0.5):
    return client.post(f"/pocket/teach/clip?word_id={word_id}&take={take}",
                       content=_wav(seconds), headers={**headers, "Content-Type": "audio/wav"})


# ── the password opens the teach page only ──────────────────────────────────

def test_the_contributor_password_opens_the_teach_page_and_nothing_else(client, on):
    label, h = _browser(client)
    assert client.get("/pocket/teach/words", headers=h).status_code == 200
    for header in ("X-Access-Token", "X-Teach-Password", "X-Owner-Token"):
        assert client.get("/api/portal-thing", headers={header: PASSWORD}).status_code == 401
        assert client.get("/pocket/status", headers={header: PASSWORD}).status_code == 401
    # Nor is it the owner: as an owner token it opens nothing.
    assert client.get("/pocket/teach/words", headers={"X-Owner-Token": PASSWORD}).status_code == 401


def test_the_owner_token_still_works_as_before_and_is_speaker_1(client, on):
    owner = {"X-Owner-Token": OWNER_TOKEN}
    assert client.get("/pocket/teach/words", headers=owner).status_code == 200
    assert _clip(client, owner).status_code == 200
    d = _hello(client, password=OWNER_TOKEN).json()
    assert d["speaker"] == "speaker-1" and d["role"] == "owner" and not d.get("speaker_key")
    assert client.get("/pocket/teach/words",
                      headers={"X-Teach-Password": OWNER_TOKEN}).status_code == 200


def test_a_wrong_password_is_refused(client, on):
    assert _hello(client, password="pocket-voice2").status_code == 401
    assert _hello(client, password="").status_code == 401


def test_with_contributor_access_off_the_password_is_refused_politely(client, on, tool):
    assert tool("off") == 0
    r = _hello(client)
    assert r.status_code == 403 and "off" in r.json()["detail"].lower()
    assert client.get("/pocket/teach/words", headers={"X-Owner-Token": OWNER_TOKEN}).status_code == 200


def test_the_page_exists_for_contributors_without_an_owner_token_file(client, on, clips, monkeypatch):
    monkeypatch.setenv("POCKET_OWNER_TOKEN_FILE", str(clips.parent / "absent"))
    assert client.get("/pocket/teach").status_code == 200
    assert _hello(client).status_code == 200


def test_the_password_is_kept_private_and_never_in_clear(clips, on):
    f = clips.parent / "contributors.json"
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    assert PASSWORD not in f.read_text()


# ── each browser its own label; no names ────────────────────────────────────

def test_each_browser_gets_the_next_label_and_keeps_it(client, on):
    a, ha = _browser(client)
    b, hb = _browser(client)
    assert (a, b) == ("speaker-2", "speaker-3")
    again = _hello(client, key=ha["X-Speaker-Key"]).json()
    assert again["speaker"] == "speaker-2" and again["speaker_key"] == ha["X-Speaker-Key"]


def test_no_names_are_collected_and_keys_are_stored_hashed(client, on, clips):
    import pocket_teach
    r = client.post("/pocket/teach/hello", headers={"X-Teach-Password": PASSWORD},
                    json={"name": "Jane Medic", "email": "jane@example.org"})
    h = {"X-Speaker-Key": r.json()["speaker_key"]}
    _clip(client, {"X-Teach-Password": PASSWORD, **h})
    for f in clips.rglob("*"):
        if f.is_file() and f.suffix != ".wav":
            assert "Jane" not in f.read_text() and "example.org" not in f.read_text(), f
    text = (clips / "speakers.json").read_text()
    assert h["X-Speaker-Key"] not in text
    for s in json.loads(text)["speakers"].values():
        assert set(s) <= {"label", "created"}
    assert pocket_teach.LABEL_PREFIX == "speaker-"


def test_a_contributor_needs_their_browsers_key(client, on):
    assert client.get("/pocket/teach/words", headers={"X-Teach-Password": PASSWORD}).status_code == 401
    assert client.get("/pocket/teach/words", headers={"X-Teach-Password": PASSWORD,
                                                      "X-Speaker-Key": "made-up"}).status_code == 401


# ── stored per speaker; resume where they left off ──────────────────────────

def test_clips_are_stored_per_speaker(client, on, clips):
    a, ha = _browser(client)
    b, hb = _browser(client)
    assert _clip(client, ha).status_code == 200
    assert _clip(client, hb).status_code == 200
    assert _clip(client, {"X-Owner-Token": OWNER_TOKEN}).status_code == 200
    for label in ("speaker-1", a, b):
        assert json.loads((clips / label / "medic-narcan" / "take1.json").read_text())["speaker"] == label
    assert (clips / "speaker-1" / "medic-narcan" / "take1.wav").read_bytes() == _wav()
    for label in (a, b):                                  # a contributor's audio is not kept
        assert not (clips / label / "medic-narcan" / "take1.wav").exists()


def test_each_speaker_resumes_from_their_own_takes_and_skips(client, on):
    a, ha = _browser(client)
    b, hb = _browser(client)
    for take in (1, 2, 3):
        _clip(client, ha, take=take)
    client.post("/pocket/teach/skip?word_id=medic-sux", headers=ha)
    words = {w["id"]: w for w in client.get("/pocket/teach/words", headers=ha).json()["words"]}
    assert words["medic-narcan"]["recorded"] == [1, 2, 3] and words["medic-sux"]["skipped"]
    other = {w["id"]: w for w in client.get("/pocket/teach/words", headers=hb).json()["words"]}
    assert other["medic-narcan"]["recorded"] == [] and not other["medic-sux"]["skipped"]


def test_mounting_never_moves_clips_the_migrate_command_does(clips, tool):
    """The owner's clips from #210 (<clips>/<word_id>/) move into speaker-1 only when the
    owner runs the command: a server or a test mounting the page must never move the
    live service's clips from under it (2026-11-17: a test run did)."""
    (clips / "medic-narcan").mkdir(parents=True)
    (clips / "medic-narcan" / "take1.wav").write_bytes(_wav())
    (clips / "medic-narcan" / "take1.json").write_text(json.dumps({"word_id": "medic-narcan", "take": 1}))
    (clips / "session.jsonl").write_text('{"event": "skip", "word_id": "medic-sux"}\n')
    runtime = pw.Runtime.load(hearing=FakeHearing(), synth=lambda t: b"RIFF")
    pw.mount(FastAPI(), require_token=_gate, runtime=runtime)
    assert (clips / "medic-narcan" / "take1.wav").exists() and not (clips / "speaker-1").exists()
    assert tool("migrate") == 0
    assert (clips / "speaker-1" / "medic-narcan" / "take1.wav").read_bytes() == _wav()
    assert (clips / "speaker-1" / "session.jsonl").exists()
    assert not (clips / "medic-narcan").exists() and not (clips / "session.jsonl").exists()
    assert tool("migrate") == 0                          # again: nothing to move


def test_no_test_reaches_the_real_private_files():
    import pocket_teach
    real = pathlib.Path.home() / "pocket-web"
    for f in (pocket_teach.clips_dir(), pocket_teach.contributors_file(),
              pocket_teach.owner_token_file()):
        assert real not in f.parents and f != real, f


# ── limits ──────────────────────────────────────────────────────────────────

def test_over_the_daily_take_cap_the_page_is_told_politely(client, on, tool):
    assert tool("limits", "takes_per_day=2") == 0
    _, h = _browser(client)
    assert _clip(client, h, take=1).status_code == 200
    assert _clip(client, h, take=2).status_code == 200
    r = _clip(client, h, take=3)
    assert r.status_code == 429
    msg = r.json()["detail"].lower()
    assert "thank you" in msg and "today" in msg
    _, h2 = _browser(client)                         # per speaker, not shared
    assert _clip(client, h2).status_code == 200


def test_over_the_total_take_cap_per_speaker_the_page_is_told_politely(client, on, tool):
    assert tool("limits", "takes_total=1") == 0
    _, h = _browser(client)
    assert _clip(client, h).status_code == 200
    r = _clip(client, h, word_id="medic-sux")
    assert r.status_code == 429 and "thank you" in r.json()["detail"].lower()


def test_limits_are_counts_of_takes_not_sizes(tool, capsys):
    import pocket_teach
    assert not any("mb" in k for k in pocket_teach.LIMITS)
    assert {"takes_per_day", "takes_total", "clip_seconds", "new_speakers_per_day"} == set(pocket_teach.LIMITS)
    assert tool("limits", "mb_per_day=5") != 0
    assert tool("limits", "clips_per_day=5") != 0


def test_a_clip_over_the_length_cap_is_refused_politely(client, on, tool, clips):
    assert tool("limits", "clip_seconds=2") == 0
    _, h = _browser(client)
    r = _clip(client, h, seconds=2.5)
    assert r.status_code == 413 and "2 seconds" in r.json()["detail"]
    assert not list((clips / "speaker-2").glob("*/take*")) if (clips / "speaker-2").exists() else True


def test_new_labels_per_day_are_capped(client, on, tool):
    assert tool("limits", "new_speakers_per_day=2") == 0
    _browser(client), _browser(client)
    r = _hello(client)
    assert r.status_code == 429 and "thank you" in r.json()["detail"].lower()


def test_the_owner_is_not_capped(client, on, tool):
    assert tool("limits", "takes_per_day=1") == 0
    owner = {"X-Owner-Token": OWNER_TOKEN}
    for take in (1, 2, 3):
        assert _clip(client, owner, take=take).status_code == 200


# ── the command ─────────────────────────────────────────────────────────────

def test_the_command_turns_access_on_and_off_and_changes_the_password(client, tool, capsys):
    assert _hello(client).status_code == 403               # off until turned on
    assert tool("password", stdin="first-pass\nfirst-pass\n") == 0
    assert tool("on") == 0
    assert _hello(client, password="first-pass").status_code == 200
    assert tool("password", stdin="second-pass\nsecond-pass\n") == 0
    assert _hello(client, password="first-pass").status_code == 401
    assert _hello(client, password="second-pass").status_code == 200
    assert tool("password", stdin="a\nb\n") != 0            # mismatch: unchanged
    assert _hello(client, password="second-pass").status_code == 200
    assert tool("off") == 0
    assert _hello(client, password="second-pass").status_code == 403
    assert tool("status") == 0
    assert "off" in capsys.readouterr().out.lower()


def test_the_command_deletes_one_speakers_clips_and_label(client, on, tool, clips):
    a, ha = _browser(client)
    b, hb = _browser(client)
    _clip(client, ha), _clip(client, hb)
    assert tool("delete", a) == 0
    assert not (clips / a).exists() and (clips / b / "medic-narcan" / "take1.json").exists()
    r = client.get("/pocket/teach/words", headers=ha)
    assert r.status_code == 401                            # that browser's key is gone
    c, _ = _browser(client)
    assert c == "speaker-4"                                # a deleted label is never reused
    assert tool("delete", "../etc") != 0 and tool("delete", "speaker-99") != 0


# ── the page ────────────────────────────────────────────────────────────────

def test_the_page_has_the_consent_line_a_password_field_and_the_speaker_label():
    import pocket_teach
    html = pocket_teach.PAGE.read_text()
    assert CONSENT in html and pocket_teach.CONSENT == CONSENT
    assert "kept privately" not in html
    for slot in ('id="password"', 'id="speaker"', "/pocket/teach/hello", "X-Speaker-Key",
                 "X-Teach-Password"):
        assert slot in html, slot
    assert "owner-clips" not in html                       # no server paths shown to contributors


# ── every speaker's clips feed the spelling step ────────────────────────────

def test_every_speakers_takes_are_listed_for_the_spelling_step(client, on):
    import pocket_teach
    a, ha = _browser(client)
    _clip(client, ha)
    _clip(client, {"X-Owner-Token": OWNER_TOKEN})
    takes = {t["speaker"]: t for t in pocket_teach.all_takes()}
    assert {(t["speaker"], t["word_id"], t["take"]) for t in takes.values()} == {
        ("speaker-1", "medic-narcan", 1), (a, "medic-narcan", 1)}
    assert pathlib.Path(takes["speaker-1"]["wav"]).exists()       # the owner's recording
    assert takes[a]["wav"] is None and takes[a]["open"] == "narcan"  # a contributor's text only


# ── contributor audio is not kept (owner, 2026-11-17) ───────────────────────
# "For a contributor, the audio is deleted as soon as the take has been decoded. Keep
# only the text the network heard, the word and the speaker label. A test checks that
# no contributor audio remains on disk after a take. My own owner recordings
# (speaker-1) are still kept."

def _noise_wav(seconds=0.5) -> tuple:
    """A WAV of random samples, so its audio can be searched for byte for byte."""
    pcm = os.urandom(int(16000 * seconds) * 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(pcm)
    return buf.getvalue(), pcm


def _files_holding(root: pathlib.Path, needle: bytes) -> list:
    return [f for f in root.rglob("*") if f.is_file() and needle in f.read_bytes()]


def test_no_contributor_audio_remains_on_disk_after_a_take(client, on, clips):
    import tempfile
    _, h = _browser(client)
    wav, pcm = _noise_wav()
    tmp = pathlib.Path(tempfile.gettempdir())
    before = {f for f in tmp.iterdir()} if tmp.exists() else set()
    for take in (1, 2, 3, 2):                                 # three takes and a redo
        r = client.post(f"/pocket/teach/clip?word_id=medic-narcan&take={take}", content=wav,
                        headers={**h, "Content-Type": "audio/wav"})
        assert r.status_code == 200
    assert not list(clips.rglob("*.wav"))
    # Not under another name either: no file anywhere in this test's private files, or
    # new in the temp folder, holds any of the audio.
    needle = pcm[8000:8064]
    assert _files_holding(clips.parent, needle) == []
    new = {f for f in tmp.iterdir()} - before if tmp.exists() else set()
    assert [f for f in new if f.is_file() and needle in f.read_bytes()] == []


def test_a_contributor_take_keeps_only_the_text_heard_the_word_and_the_label(client, on, clips):
    label, h = _browser(client)
    r = _clip(client, h)
    assert r.status_code == 200 and r.json()["as_itself"] is True   # the page is still told
    rec = json.loads((clips / label / "medic-narcan" / "take1.json").read_text())
    assert set(rec) == {"speaker", "word_id", "kind", "say", "take", "open",
                        "open_alternatives", "pocket"}
    assert rec["speaker"] == label and rec["say"] == "narcan" and rec["open"] == "narcan"
    assert set(rec["pocket"]) == {"heard", "text", "decoder"}
    for line in (clips / label / "session.jsonl").read_text().splitlines():
        assert set(json.loads(line)) <= {"event", "word_id", "take"}


def test_a_contributor_take_that_fails_to_decode_leaves_no_audio(client, on, clips, monkeypatch):
    _, h = _browser(client)

    def boom(self, pcm):
        raise RuntimeError("decoder failed")
    monkeypatch.setattr(FakeHearing, "hear_open", boom)
    with pytest.raises(RuntimeError):
        _clip(client, h)
    assert not list(clips.rglob("*.wav"))


def test_the_owners_recordings_are_still_kept_in_full(client, on, clips):
    owner = {"X-Owner-Token": OWNER_TOKEN}
    wav, _ = _noise_wav()
    r = client.post("/pocket/teach/clip?word_id=medic-narcan&take=1", content=wav,
                    headers={**owner, "Content-Type": "audio/wav"})
    assert r.status_code == 200
    assert (clips / "speaker-1" / "medic-narcan" / "take1.wav").read_bytes() == wav
    rec = json.loads((clips / "speaker-1" / "medic-narcan" / "take1.json").read_text())
    assert {"time", "as_itself", "expect", "got"} <= set(rec)


def test_a_contributor_resumes_from_the_text_records(client, on):
    _, h = _browser(client)
    for take in (1, 2, 3):
        _clip(client, h, take=take)
    words = {w["id"]: w for w in client.get("/pocket/teach/words", headers=h).json()["words"]}
    assert words["medic-narcan"]["recorded"] == [1, 2, 3]


def test_status_counts_takes_and_says_whose_audio_is_kept(client, on, tool, capsys):
    _, h = _browser(client)
    _clip(client, h, take=1), _clip(client, h, take=2)
    _clip(client, {"X-Owner-Token": OWNER_TOKEN})
    capsys.readouterr()
    assert tool("status") == 0
    out = capsys.readouterr().out
    assert "speaker-1 (owner): 1 take, audio kept" in out
    assert "speaker-2: 2 takes, text only" in out
    assert "takes_per_day = " in out and "MB" not in out.split("Speakers")[0]
