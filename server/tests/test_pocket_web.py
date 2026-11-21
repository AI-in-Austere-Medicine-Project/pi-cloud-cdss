"""W1: Pocket on the web, for outside testers (owner, 2026-11-15).

Owner: "A /pocket page on the portal with the same banner (research, simulated
scenarios only, no PHI). Hold-to-talk and a typed box. It runs the real Pocket
code, installed from the edgecdss-pocket repo at a pinned commit: browser audio ->
Vosk with Pocket's grammar on the Jetson -> Pocket engine -> Pocket's spoken
templates -> Piper audio back to the browser, with the text shown on screen too.
Read-back and "confirm" work as on the device. The page shows the Pocket version
and bank version. Drug set: the public page serves the signed PFC set only. EMS and
EMS-TEST are never reachable from the web; pin that with a test. Feedback: the same
"clinically appropriate / flag issue" buttons as the main portal, logged with
product: pocket, the phrase heard, the parse and the answer. Pocket sessions are
kept separate and never enter the EdgeCDSS replay sets. One talker at a time; a
second gets "busy, try again". ... A short "How to test" panel: five example
phrases and what to expect."

The engine tests run the real Pocket code from the pinned checkout
(tools/install_pocket.py); Vosk and Piper are faked except in the two tests marked
for the real models, which run when the models are installed.
"""
import base64
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import types
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

TOKEN = {"X-Access-Token": "pocket-test-token"}
CHECKOUT = pw.checkout_dir()
needs_checkout = pytest.mark.skipif(
    not (CHECKOUT / ".git").exists(),
    reason=f"Pocket is not installed at {CHECKOUT}: run server/tools/install_pocket.py")
import importlib.util  # noqa: E402
needs_models = pytest.mark.skipif(
    not (pw.vosk_model_dir().exists() and pw.piper_voice_path().exists()
         and importlib.util.find_spec("vosk") and importlib.util.find_spec("piper")),
    reason="the Vosk model and Piper voice, or the vosk and piper-tts packages, are not "
           "installed (install_pocket.py --models; requirements-pocket.txt)")

EXAMPLE_PHRASES = ["ketamine for agitation iv eighty kilos", "confirm", "new patient",
                   "magnesium", "acetaminophen for pain po seventy kilos"]


def _gate(x_access_token: str = Header(default="")):
    if x_access_token != TOKEN["X-Access-Token"]:
        raise HTTPException(status_code=401, detail="Invalid access token")


class FakeHearing:
    """Hears whatever the test says it heard."""
    def __init__(self):
        self.next = ""

    def hear(self, pcm: bytes) -> tuple:
        return self.next, self.next, "spelled"


def fake_synth(text: str) -> bytes:
    return b"RIFF-fake-" + text.encode()[:20]


@pytest.fixture
def logs(tmp_path, monkeypatch):
    d = tmp_path / "pocket-logs"
    monkeypatch.setattr(pw, "LOG_DIR", d)
    return d


@pytest.fixture
def runtime(logs):
    return pw.Runtime.load(hearing=FakeHearing(), synth=fake_synth)


@pytest.fixture
def client(runtime):
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=runtime)
    return TestClient(app)


def _say(client, text, sid="tester-a"):
    return client.post("/pocket/say", json={"session_id": sid, "text": text}, headers=TOKEN)


def _wav(seconds=0.5) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def _engine_says(phrases):
    """The pinned Pocket engine itself, on its own bank, phrase by phrase."""
    sys.path.insert(0, str(CHECKOUT))
    from engine.session import boot
    s = boot(CHECKOUT / "bank")
    return [s.handle(p) for p in phrases]


# ── installed from the repo at a pinned commit ──────────────────────────────

def test_the_pin_names_the_repo_and_a_full_commit():
    pin = json.loads((SERVER / "pocket_pin.json").read_text())
    assert pin["repo"] == "https://github.com/AI-in-Austere-Medicine-Project/edgecdss-pocket"
    assert re.fullmatch(r"[0-9a-f]{40}", pin["commit"])
    assert pw.PIN == pin
    assert re.fullmatch(r"[0-9a-f]{64}", pin["vosk_model"]["zip_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", pin["piper_voice"]["onnx_sha256"])


def test_the_checkout_is_outside_the_repo_and_named_by_its_commit():
    assert pw.PIN["commit"][:12] in CHECKOUT.name
    assert SERVER.parent not in CHECKOUT.parents


@needs_checkout
def test_a_checkout_at_another_commit_is_refused(tmp_path):
    other = tmp_path / "pocket"
    shutil.copytree(CHECKOUT, other, symlinks=True)
    subprocess.run(["git", "-C", str(other), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "moved"], check=True)
    with pytest.raises(pw.Unavailable, match="commit"):
        pw.verify_checkout(other)


def test_no_checkout_is_unavailable_not_a_crash(tmp_path, logs, monkeypatch):
    monkeypatch.setattr(pw, "checkout_dir", lambda: tmp_path / "nothing")
    with pytest.raises(pw.Unavailable):
        pw.Runtime.load(hearing=FakeHearing(), synth=fake_synth)
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=None)
    c = TestClient(app)
    st = c.get("/pocket/status", headers=TOKEN).json()
    assert st["available"] is False and st["why"]
    assert _say(c, "confirm").status_code == 503


# ── the page ────────────────────────────────────────────────────────────────

def _portal_banner_sentences():
    html = (SERVER / "static" / "index.html").read_text()
    disclaimer = re.search(r'<div class="disclaimer">(.*?)</div>', html, re.S).group(1)
    demo = re.search(r"<strong>(Demo &amp; research system.*?)</strong>", html, re.S).group(1)
    return disclaimer, demo


def test_the_page_carries_the_portals_banner_and_needs_no_token():
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=None)
    r = TestClient(app).get("/pocket")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    disclaimer, demo = _portal_banner_sentences()
    assert disclaimer in r.text
    assert demo in r.text


def test_the_page_has_hold_to_talk_a_typed_box_and_the_versions():
    html = pw.PAGE.read_text()
    assert 'id="talk"' in html and "HOLD TO TALK" in html
    assert 'id="typed"' in html
    for slot in ('id="pocket-version"', 'id="bank-version"'):
        assert slot in html
    assert "clinically appropriate" in html and "flag issue" in html


@needs_checkout
def test_the_how_to_test_panel_says_what_the_engine_says():
    """Five phrases, in order on a fresh session, each with the engine's own words."""
    assert [p for p, _ in pw.EXAMPLES] == EXAMPLE_PHRASES
    said = _engine_says(EXAMPLE_PHRASES)
    for (phrase, expect), turn in zip(pw.EXAMPLES, said):
        assert expect == turn.written_text, phrase   # the panel shows the written form
    html = pw.PAGE.read_text()
    for phrase, expect in pw.EXAMPLES:
        assert phrase in html and expect in html


@needs_checkout
def test_status_shows_the_pocket_version_and_the_bank_version(client):
    st = client.get("/pocket/status", headers=TOKEN).json()
    assert st["available"] is True
    assert st["pocket_commit"] == pw.PIN["commit"]
    bank = json.loads((CHECKOUT / "bank" / "manifest.json").read_text())
    assert st["bank_version"] == bank["bank_version"]
    assert st["set"] == "PFC"
    assert st["busy"] is False


# ── the real Pocket engine, read-back and confirm ───────────────────────────

def test_the_api_is_token_gated(client):
    assert client.post("/pocket/say", json={"session_id": "a", "text": "confirm"}).status_code == 401
    assert client.post("/pocket/hear?session_id=a", content=_wav()).status_code == 401
    assert client.post("/pocket/feedback", json={}).status_code == 401
    assert client.get("/pocket/status").status_code == 401


@needs_checkout
def test_read_back_then_confirm_is_the_device_flow(client):
    phrases = ["ketamine for agitation iv eighty kilos", "confirm"]
    engine = _engine_says(phrases)
    for phrase, turn in zip(phrases, engine):
        r = _say(client, phrase).json()
        assert r["kind"] == turn.kind
        assert r["text"] == turn.written_text      # shown: the written form
        assert r["spoken"] == turn.text            # played: the spoken form
        assert base64.b64decode(r["audio_wav_b64"]) == fake_synth(turn.text)
    assert engine[0].kind == "readback" and engine[1].kind == "dose"


@needs_checkout
def test_heard_audio_goes_through_the_same_engine(client, runtime):
    runtime.hearing.next = "ketamine for agitation i v eighty kilos"
    r = client.post("/pocket/hear?session_id=tester-a", content=_wav(),
                    headers={**TOKEN, "Content-Type": "audio/wav"}).json()
    assert r["heard"] == "ketamine for agitation i v eighty kilos"
    assert r["decoder"] == "spelled"
    assert r["kind"] == "readback" and r["text"].endswith("Confirm?")
    assert r["parse"]["drugs"] and r["parse"]["routes"] == ["IV"]


@needs_checkout
def test_audio_that_is_not_16k_mono_pcm_is_refused(client):
    r = client.post("/pocket/hear?session_id=a", content=b"not a wav", headers=TOKEN)
    assert r.status_code == 400


# ── one talker at a time ────────────────────────────────────────────────────

@needs_checkout
def test_a_second_talker_gets_busy_try_again(client):
    assert _say(client, "magnesium", "tester-a").status_code == 200
    r = _say(client, "magnesium", "tester-b")
    assert r.status_code == 409 and r.json()["detail"] == "busy, try again"
    assert client.get("/pocket/status", headers=TOKEN).json()["busy"] is True
    assert client.post("/pocket/release", json={"session_id": "tester-a"}, headers=TOKEN).status_code == 200
    assert _say(client, "magnesium", "tester-b").status_code == 200


@needs_checkout
def test_an_idle_talker_lets_the_next_one_in_with_a_fresh_session(client, runtime, monkeypatch):
    """No state crosses testers: a pending read-back is not the next talker's."""
    clock = [1000.0]
    monkeypatch.setattr(pw.time, "monotonic", lambda: clock[0])
    assert _say(client, "ketamine for agitation iv eighty kilos", "tester-a").json()["kind"] == "readback"
    clock[0] += pw.LEASE_IDLE_S + 1
    r = _say(client, "confirm", "tester-b")
    assert r.status_code == 200
    assert r.json()["text"] == "Nothing to confirm."


# ── PFC only: EMS and EMS-TEST are never reachable from the web ──────────────

def _relabelled(tmp_path, set_name=None, test=False, names=None):
    """Pocket's PFC bank dir, relabelled and rehashed."""
    d = tmp_path / "bank"
    shutil.copytree(CHECKOUT / "bank", d)
    bank = json.loads((d / "bank.json").read_text())
    man = json.loads((d / "manifest.json").read_text())
    if set_name:
        bank["set"] = man["set"] = set_name
        for e in bank["entries"]:
            e["set"] = set_name
    if test:
        bank["test"] = man["test"] = True
        for e in bank["entries"]:
            e.update(status="test", signoff=False, check_failed=[])
    names = names or {"bank": "bank.json", "kit": "kit.json", "manifest": "manifest.json"}
    blob = json.dumps(bank).encode()
    kit = (d / "kit.json").read_bytes()
    for f in ("bank.json", "kit.json", "manifest.json"):
        (d / f).unlink()
    (d / names["bank"]).write_bytes(blob)
    (d / names["kit"]).write_bytes(kit)
    man["sha256"] = {names["bank"]: hashlib.sha256(blob).hexdigest(),
                     names["kit"]: hashlib.sha256(kit).hexdigest()}
    (d / names["manifest"]).write_text(json.dumps(man))
    return d


@needs_checkout
@pytest.mark.parametrize("set_name", ["EMS", "EMS-TEST"])
def test_an_ems_or_ems_test_bank_is_refused(tmp_path, logs, monkeypatch, set_name):
    d = _relabelled(tmp_path, set_name, test=set_name == "EMS-TEST")
    monkeypatch.setattr(pw, "bank_dir", lambda: d)
    with pytest.raises(pw.Unavailable):
        pw.Runtime.load(hearing=FakeHearing(), synth=fake_synth)


@needs_checkout
def test_pocket_test_in_the_environment_never_loads_the_test_bank(tmp_path, logs, monkeypatch):
    test_names = {"bank": "bank-ems-test.json", "kit": "kit-ems-test.json",
                  "manifest": "manifest-ems-test.json"}
    d = _relabelled(tmp_path, "EMS-TEST", test=True, names=test_names)
    monkeypatch.setattr(pw, "bank_dir", lambda: d)
    monkeypatch.setenv("POCKET_TEST", "1")
    with pytest.raises(pw.Unavailable):
        pw.Runtime.load(hearing=FakeHearing(), synth=fake_synth)


@needs_checkout
def test_the_servers_drug_set_setting_does_not_reach_the_web_bank(logs, monkeypatch):
    monkeypatch.setenv("CDSS_DRUG_SET", "EMS")
    monkeypatch.setenv("POCKET_TEST", "1")
    rt = pw.Runtime.load(hearing=FakeHearing(), synth=fake_synth)
    assert rt.bank.test is False
    assert rt.status()["set"] == "PFC"


def test_the_web_bank_is_the_pinned_checkouts_own_bank_dir():
    assert pw.bank_dir() == CHECKOUT / "bank"
    src = (SERVER / "pocket_web.py").read_text()
    assert "bank-ems" not in src            # no EMS bank file is ever named
    assert pw.SERVED_SET == "PFC"
    assert {"EMS", "EMS-TEST"} <= set(pw.REFUSED_SETS)


@needs_checkout
def test_no_request_can_name_a_set_or_a_bank(client):
    for extra in ({"set": "EMS"}, {"bank": "bank-ems-test"}, {"test": True}):
        r = client.post("/pocket/say", json={"session_id": "a", "text": "magnesium", **extra},
                        headers=TOKEN)
        assert r.status_code == 422, extra
    r = client.post("/pocket/say?set=EMS&bank=bank-ems-test",
                    json={"session_id": "a", "text": "magnesium"}, headers=TOKEN)
    assert r.json()["bank_version"] == client.get("/pocket/status", headers=TOKEN).json()["bank_version"]


# ── logs: product pocket, never in the EdgeCDSS replay sets ─────────────────

REPLAY_SOURCES = ("/home/andrew/pi-cloud-cdss/server/logs/sessions",
                  "/home/andrew/projects/cdss-eval/runs")


def test_the_pocket_log_dir_is_not_where_edgecdss_logs_or_replays_read():
    import openai_client
    d = pathlib.Path(pw.default_log_dir()).resolve()
    for other in (openai_client._LOG_DIR, *REPLAY_SOURCES):
        other = pathlib.Path(other).resolve()
        assert d != other and other not in d.parents and d not in other.parents, other


@needs_checkout
def test_every_turn_is_logged_with_product_pocket_heard_parse_and_answer(client, runtime, logs):
    runtime.hearing.next = "magnesium"
    client.post("/pocket/hear?session_id=tester-a", content=_wav(), headers=TOKEN)
    _say(client, "ketamine for agitation iv eighty kilos")
    _say(client, "confirm")
    files = sorted(logs.glob("*.jsonl"))
    assert files and not any(f.name.startswith("cdss_session_") for f in files)
    lines = [json.loads(l) for f in files for l in f.read_text().splitlines()]
    turns = [l for l in lines if l["event"] == "turn"]
    assert len(turns) == 3
    assert all(l["product"] == "pocket" for l in lines)
    assert turns[0]["heard"] == "magnesium" and turns[0]["input"] == "voice"
    assert turns[1]["heard"] is None and turns[1]["input"] == "typed"
    assert turns[1]["parse"]["drugs"] and turns[2]["answer"]["kind"] == "dose"
    assert all(l["pocket_commit"] == pw.PIN["commit"] and l["bank_version"] for l in turns)
    doses = [l for l in lines if l["event"] == "dose"]
    assert len(doses) == 1 and doses[0]["record"]["drug"] == "ketamine"


@needs_checkout
@pytest.mark.parametrize("verdict", ["appropriate", "flagged"])
def test_feedback_is_logged_with_product_pocket_and_the_turn_it_is_about(client, logs, verdict,
                                                                        tmp_path, monkeypatch):
    main_feedback = tmp_path / "feedback.log"
    monkeypatch.setenv("FEEDBACK_LOG", str(main_feedback))
    turn = _say(client, "ketamine for agitation iv eighty kilos").json()
    r = client.post("/pocket/feedback", headers=TOKEN, json={
        "session_id": "tester-a", "turn_id": turn["turn_id"], "feedback_type": verdict,
        "severity": "minor" if verdict == "flagged" else "", "issues": ["wrong dose"],
        "comment": "test"})
    assert r.status_code == 200
    (line,) = [json.loads(l) for l in (logs / pw.FEEDBACK_FILE).read_text().splitlines()]
    assert line["product"] == "pocket" and line["feedback_type"] == verdict
    assert line["phrase"] == "ketamine for agitation iv eighty kilos"
    assert line["parse"]["drugs"] and line["answer"]["text"] == turn["text"]
    assert line["pocket_commit"] == pw.PIN["commit"]
    assert not main_feedback.exists()


@needs_checkout
def test_feedback_names_a_turn_the_server_gave(client):
    r = client.post("/pocket/feedback", headers=TOKEN, json={
        "session_id": "tester-a", "turn_id": "made-up", "feedback_type": "appropriate"})
    assert r.status_code == 404
    turn = _say(client, "magnesium").json()
    r = client.post("/pocket/feedback", headers=TOKEN, json={
        "session_id": "tester-a", "turn_id": turn["turn_id"], "feedback_type": "positive"})
    assert r.status_code == 422


# ── the portal mounts it ────────────────────────────────────────────────────

def test_the_portal_mounts_the_page_and_gates_the_api():
    src = (SERVER / "main.py").read_text()
    assert "pocket_web.mount(app, require_token=require_token" in src


# ── the real models (when installed) ────────────────────────────────────────

@needs_checkout
@needs_models
def test_the_committed_grammar_is_for_this_model_and_this_bank(logs):
    rt = pw.Runtime.load(synth=fake_synth)  # real Vosk hearing
    g = json.loads((CHECKOUT / "grammar" / "vosk_grammar.json").read_text())
    assert g["bank_hash"] == rt.bank.hash
    assert rt.status()["vosk_model"] == pw.PIN["vosk_model"]["name"]


@needs_checkout
@needs_models
def test_piper_said_it_and_vosk_heard_it(logs):
    """Loopback: Piper says the device prompt for a phrase, Vosk with Pocket's grammar
    hears it, and the engine reads it back."""
    rt = pw.Runtime.load()
    sys.path.insert(0, str(CHECKOUT))
    from voice import spoken
    wav = rt.synth(spoken.prompt("ketamine for agitation iv eighty kilos"))
    heard, text, _ = rt.hearing.hear(pw.pcm16k(pw.resample_wav_16k(wav)))
    turn = rt.session_for("loop").handle(text)
    assert turn.kind == "readback", (heard, turn.text)
    assert turn.text == "Ketamine, agitation, eye vee, eighty kilos. Confirm?"   # spoken


# ── W1 pin bump: Pocket's hearing fixes (Pocket #5, owner 2026-11-15) ───────
# Owner: "Typed input stays as it is; no pair asks for typed text." A pair the clips or
# the sound-alike checks confuse asks "X or Y?" before the read-back when it is heard.

HEARING_FIXES = "f8f7aa5fe80766891175be05d3c6e81b6c9397c3"   # Pocket #5, merged


def test_the_pin_is_after_pockets_hearing_fixes():
    """Superseded by the voice pin below; the hearing fixes are in its history."""
    assert pw.PIN["commit"] != HEARING_FIXES


def _hear(client, runtime, heard, sid="tester-a"):
    runtime.hearing.next = heard
    return client.post(f"/pocket/hear?session_id={sid}", content=_wav(),
                       headers={**TOKEN, "Content-Type": "audio/wav"}).json()


@needs_checkout
def test_a_heard_confused_drug_pair_asks_x_or_y_first(client, runtime):
    r = _hear(client, runtime, "epinephrine for anaphylaxis intramuscular eighty kilos")
    assert r["kind"] == "ask" and r["text"] == "Epinephrine or norepinephrine?"
    r = _hear(client, runtime, "epinephrine")
    assert r["kind"] == "readback" and r["text"].startswith("Epinephrine, anaphylaxis, IM")


@needs_checkout
def test_a_heard_letter_spelled_im_or_in_asks_first(client, runtime):
    r = _hear(client, runtime, "fentanyl for pain i n eighty kilos")
    assert r["text"] == "IM or IN?"
    r = _hear(client, runtime, "intranasal")
    assert r["kind"] == "readback" and ", IN," in r["text"]


@needs_checkout
@pytest.mark.parametrize("typed", ["epinephrine for anaphylaxis im eighty kilos",
                                   "fentanyl for pain in eighty kilos"])
def test_the_typed_box_never_asks_a_pair(client, typed):
    r = _say(client, typed).json()
    assert r["kind"] == "readback", r["text"]


@needs_checkout
@pytest.mark.parametrize("heard, route", [("i v", "IV"), ("intravenous", "IV"), ("in the vein", "IV"),
                                          ("intramuscular", "IM"), ("i o", "IO"), ("by mouth", "PO")])
def test_the_new_route_words_are_heard_through_the_web(client, runtime, heard, route):
    drug = "acetaminophen for pain" if route == "PO" else "ketamine for agitation"
    r = _hear(client, runtime, f"{drug} {heard} eighty kilos")
    assert r["parse"]["routes"] == [route], r["text"]


# ── W1 pin bump: Pocket's voice work (Pocket #9 and #10, owner 2026-11-19) ──
# Owner: "Route spelling choices: IV = "eye vee"; IM = "eye em"; IO = "eye oh"; IN =
# "intranasal"; PO = "pee oh"; NEB = "nebuliser". Apply them to every spoken line ..."
# Owner: "Pocket should return two forms of each answer: the spoken form for the voice,
# and a written form for display that uses IV, IM, IO, IN, PO and NEB. The page shows
# the written form and plays the spoken form. Failing test first: no on-screen answer
# contains "eye vee" or "pee oh", and the audio text still does." "Make one pin bump,
# not two: point the pin at #10's merge commit."

VOICE = "844cdfe46becabe5899331f384a27ea5efe68c77"   # Pocket main after #10 (and #9)
SPOKEN_ROUTE = re.compile(r"(?i)\b(eye vee|eye em|eye oh|pee oh|nebuliser)\b")
BARE_ROUTE = re.compile(r"(?<![A-Za-z])(IV|IM|IO|IN|PO|NEB)(?![A-Za-z])")
ROUTE_PHRASES = ["ketamine for agitation iv eighty kilos", "ketamine for agitation io eighty kilos",
                 "fentanyl for pain in eighty kilos", "epinephrine for anaphylaxis im eighty kilos",
                 "acetaminophen for pain po seventy kilos"]


def test_the_pin_is_after_pockets_voice_work():
    """Superseded by the pin after Pocket #25 below; #9 and #10 are in its history."""
    assert pw.PIN["commit"] != VOICE


@needs_checkout
@pytest.mark.parametrize("phrase", ROUTE_PHRASES)
def test_the_screen_shows_letters_and_the_voice_says_words(client, phrase):
    for said in (phrase, "why", "repeat", "confirm"):
        r = _say(client, said).json()
        assert not SPOKEN_ROUTE.search(r["text"]), r["text"]          # on screen
        assert not BARE_ROUTE.search(r["spoken"]), r["spoken"]        # in the audio
        assert base64.b64decode(r["audio_wav_b64"]) == fake_synth(r["spoken"])
    _say(client, "new patient")
    first = _say(client, phrase).json()
    assert BARE_ROUTE.search(first["text"]), first
    assert SPOKEN_ROUTE.search(first["spoken"]) or "intranasal" in first["spoken"], first


@needs_checkout
def test_the_read_back_on_screen_and_in_the_audio(client):
    r = _say(client, "acetaminophen for pain po seventy kilos").json()
    assert r["text"] == "Acetaminophen, pain, PO, seventy kilos. Confirm?"
    assert r["spoken"] == "Acetaminophen, pain, pee oh, seventy kilos. Confirm?"


@needs_checkout
def test_a_heard_pair_question_on_screen_and_in_the_audio(client, runtime):
    r = _hear(client, runtime, "fentanyl for pain i n eighty kilos")
    assert (r["text"], r["spoken"]) == ("IM or IN?", "Eye em or intranasal?")


def test_the_page_shows_the_written_form_and_plays_the_audio():
    html = pw.PAGE.read_text()
    assert "esc(d.text)" in html and "d.spoken" not in html
    for _, expect in pw.EXAMPLES:
        assert not SPOKEN_ROUTE.search(expect), expect


@needs_checkout
@pytest.mark.parametrize("word", ["confirm", "yes", "correct", "affirmative"])
def test_a_confirm_word_gives_the_dose_through_the_web(client, word):
    assert _say(client, "ketamine for agitation iv eighty kilos").json()["kind"] == "readback"
    assert _say(client, word).json()["kind"] == "dose"


@needs_checkout
@pytest.mark.parametrize("word", ["no", "cancel", "negative", "stop", "wrong"])
def test_a_cancel_word_cancels_through_the_web_and_no_dose_follows(client, word):
    _say(client, "ketamine for agitation iv eighty kilos")
    assert _say(client, word).json()["text"] == "Cancelled."
    assert _say(client, "yes").json()["kind"] != "dose"


@needs_checkout
def test_two_misses_cancel_through_the_web(client):
    _say(client, "ketamine for agitation iv eighty kilos")
    assert _say(client, "ok").json()["text"] == "Say confirm or cancel."
    assert _say(client, "ok").json()["text"] == "Cancelled."
    assert _say(client, "yes").json()["kind"] != "dose"


# ── W1 pin bump: Pocket main after #25 (owner, 2026-11-21) ──────────────────
# Owner: "Update the Pocket page on the portal to current edgecdss-pocket main
# (includes #21, #22, #23, #25). Pin bump only in pi-cloud-cdss; no EdgeCDSS code
# changes and no replays. Check that RSI works on the page: "rsi 80kg", "next",
# "repeat", "failed airway", yes/no. If the page needs a change to handle
# procedures, include it."

POCKET_MAIN_25 = "e63248c8ae665f5fc7f876195537b56518564f03"   # Pocket main after #25


def test_the_pin_is_after_pocket_main_after_25():
    """Superseded by the home menu pin below; #21 to #25 are in its history."""
    assert pw.PIN["commit"] != POCKET_MAIN_25


@needs_checkout
def test_rsi_on_the_page_steps_and_repeats(client):
    one = _say(client, "rsi 80kg").json()
    assert one["kind"] == "step"
    assert one["text"].startswith("Rapid sequence intubation, adult, eighty kilos. Step one of eleven.")
    two = _say(client, "next").json()
    assert two["kind"] == "step" and two["text"].startswith("Step two of eleven.")
    again = _say(client, "repeat").json()
    assert again["text"] == two["text"] and again["spoken"] == two["spoken"]
    assert base64.b64decode(again["audio_wav_b64"]) == fake_synth(two["spoken"])


@needs_checkout
@pytest.mark.parametrize("answer, branch", [
    ("yes", "Step three of three. YES → Surgical airway"),
    ("no", "Step three of three. NO → Emergency pathway."),
])
def test_failed_airway_on_the_page_asks_and_reads_the_answer(client, answer, branch):
    first = _say(client, "failed airway").json()
    assert first["text"].startswith("Failed airway. Step one of three."), first["text"]
    _say(client, "next")
    ask = _say(client, "next").json()
    assert (ask["kind"], ask["text"]) == ("ask", "Can you mask ventilate? Say yes or no.")
    r = _say(client, answer).json()
    assert r["kind"] == "step" and r["text"].startswith(branch), r["text"]
    assert _say(client, "log").json()["text"] == "Zero doses logged."     # no dose came of it


@needs_checkout
def test_rsi_by_voice_on_the_page(client, runtime):
    r = _hear(client, runtime, "r s i eighty kilos")
    assert r["kind"] == "step" and "Step one of eleven." in r["text"]


@needs_checkout
def test_the_page_steps_are_the_engines_own(client):
    phrases = ["rsi 80kg", "next", "repeat", "start over", "failed airway", "next", "next", "no"]
    for phrase, turn in zip(phrases, _engine_says(phrases)):
        r = _say(client, phrase).json()
        assert (r["kind"], r["text"], r["spoken"]) == (turn.kind, turn.written_text, turn.text), phrase


@needs_checkout
def test_the_start_up_record_is_logged_as_boot_not_as_a_dose(client, logs):
    _say(client, "rsi 80kg")
    lines = [json.loads(x) for f in logs.glob("pocket_turns_*.jsonl") for x in f.read_text().splitlines()]
    boots = [x for x in lines if x["event"] == "boot"]
    assert len(boots) == 1 and boots[0]["record"]["set"] == "PFC set"
    assert not [x for x in lines if x["event"] == "dose"]



# ── W1 pin bump: Pocket #26, home menu, help and command lists (owner, 2026-11-21) ──
# Owner: "The Pocket page shows the same home menu, the drug and procedure lists, and the
# help text as text on screen. The lists come from the signed bank, not a hand-written
# copy." "Pin bump only, no EdgeCDSS code changes, no replays. Check on the page: "rsi
# 80kg", "next", "repeat", "failed airway", yes/no, "help", "drugs"."

HOME_MENU = "1242a63f0ed0c0d3787a0e9efc8554ff96b72dd2"   # Pocket #26 (home menu), on main after #25
_DOSE_WORDS = re.compile(r"(?i)\b(milligrams?|micrograms?|grams?|mg|mcg|mils?|ml|units?)\b|\d")


def test_the_pin_is_pockets_home_menu():
    assert pw.PIN["commit"] == HOME_MENU


@needs_checkout
@pytest.mark.parametrize("said", ["home", "drugs", "list drugs", "procedures", "list procedures",
                                  "help", "what can i say"])
def test_the_page_shows_the_menu_lists_and_help_as_the_engine_says_them(client, said):
    r = _say(client, said).json()
    turn = _engine_says([said])[0]
    assert (r["kind"], r["text"], r["spoken"]) == ("menu", turn.written_text, turn.text)
    assert base64.b64decode(r["audio_wav_b64"]) == fake_synth(turn.text)
    assert not _DOSE_WORDS.search(r["text"]) and not _DOSE_WORDS.search(r["spoken"]), r["text"]


@needs_checkout
def test_the_page_lists_come_from_the_signed_bank(client, runtime):
    from grammar.vocabulary import build
    vocab = build(runtime.bank)
    text = _say(client, "drugs").json()["text"]
    names = sorted({vocab.listed_name(d) for d in runtime.bank.signed_drugs})
    assert text == f"Signed drugs: {', '.join(names)}. Say a drug name to begin."
    assert len(names) == len(runtime.bank.signed_drugs) == 25
    titles = [p.title for p in runtime.procedures.values()]
    assert _say(client, "procedures").json()["text"] == (
        f"Signed procedures: {', '.join(titles)}. Say a procedure name to begin.")


@needs_checkout
def test_the_page_help_shows_letters_and_says_words(client):
    r = _say(client, "help").json()
    assert "ketamine for pain, IV, eighty kilos" in r["text"] and "RSI, eighty kilos" in r["text"]
    assert "ketamine for pain, eye vee, eighty kilos" in r["spoken"] and "R S I, eighty kilos" in r["spoken"]


@needs_checkout
def test_the_owners_checks_on_the_page_in_one_session(client):
    said = ["rsi 80kg", "next", "repeat", "failed airway", "next", "next", "yes",
            "failed airway", "next", "next", "no", "help", "drugs", "home", "what can i say"]
    kinds = [_say(client, p).json()["kind"] for p in said]
    assert kinds == ["step", "step", "repeat", "step", "step", "ask", "step",
                     "step", "step", "ask", "step", "menu", "menu", "menu", "menu"]
    assert _say(client, "log").json()["text"] == "Zero doses logged."


@needs_checkout
def test_home_on_the_page_ends_a_procedure_and_drops_a_read_back(client):
    _say(client, "rsi 80kg")
    assert _say(client, "home").json()["text"] == "Pocket ready. Say drugs, procedures, or help."
    assert _say(client, "next").json()["text"] == "No steps running."
    _say(client, "ketamine for agitation iv eighty kilos")
    _say(client, "home")
    assert _say(client, "yes").json()["kind"] != "dose"



# Owner: "do the small page change so the start-up menu line shows when the Pocket page
# loads. Put it with #227."

@needs_checkout
def test_status_carries_the_engines_own_start_up_line(client, logs):
    st = client.get("/pocket/status", headers=TOKEN).json()
    sys.path.insert(0, str(CHECKOUT))
    from engine.session import boot
    assert st["start_up"] == boot(CHECKOUT / "bank").announce.written_text
    assert st["start_up"] == ("Pocket ready. Research prototype, not for patient care. "
                              "Say drugs, procedures, or help.")
    assert not logs.exists() or not any(logs.iterdir())    # no tester session, no log line
    assert client.get("/pocket/status", headers=TOKEN).json()["busy"] is False


def test_the_page_shows_the_start_up_line_once_when_it_loads():
    html = pw.PAGE.read_text()
    js = html[html.index("async function status()"):]
    assert "s.start_up" in js and "startUpShown" in js
    assert "esc(s.start_up)" in js                       # escaped, as every answer is
    assert re.search(r"if \(s\.available && s\.start_up && !startUpShown\)", js)
    start = js[js.index("function showStartUp"):js.index("}", js.index("function showStartUp"))]
    assert "play" not in start.lower() and "Audio" not in start   # text only: no autoplay


def test_with_pocket_unavailable_status_has_no_start_up_line():
    app = FastAPI()
    pw.mount(app, require_token=_gate, runtime=None)
    st = TestClient(app).get("/pocket/status", headers=TOKEN).json()
    assert st["available"] is False and "start_up" not in st
