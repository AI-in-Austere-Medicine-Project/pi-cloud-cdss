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
needs_models = pytest.mark.skipif(
    not (pw.vosk_model_dir().exists() and pw.piper_voice_path().exists()),
    reason="the Vosk model and Piper voice are not installed (install_pocket.py --models)")

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
        assert expect == turn.text, phrase
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
        assert r["text"] == turn.text
        assert r["say"] == turn.say and r["after"] == turn.after
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
    assert turn.text == "Ketamine, agitation, IV, eighty kilos. Confirm?"
