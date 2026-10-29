"""
EdgeCDSS P1 — two portal findings (owner, live, 2026-10-29).

1. Hold to talk "does nothing" from the owner's Mac. Every failure is shown on
   the screen, in red, and named once in the browser console ("[talk] <case>"):
   no microphone because the page is not a secure context (http by IP), the
   microphone permission denied, no microphone found, let go before the
   microphone opened, no audio captured, /transcribe unreachable or answering
   an error status, and an empty transcript. While held, the note says it is
   recording; the transcript goes into the box a word at a time.
2. The MODE brief/detailed control is gone: voice_mode was carried from the
   portal to _run_pipeline and never read there. The portal stops sending it,
   /query neither takes nor returns it, and a client that still sends it is
   answered as before (an unknown field is ignored).

The portal's script runs in stt_ptt_harness.js (stubbed DOM and microphone).

    cd server && ./run_unit_tests.sh
"""
import inspect
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
PORTAL = (HERE.parent / "static" / "index.html").read_text(encoding="utf-8")
TRANSCRIPT = "Eighty kilo adult, cefazolin dose?"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _ptt(scenario):
    proc = subprocess.run(["node", str(HERE / "stt_ptt_harness.js"),
                           str(HERE.parent / "static" / "index.html"), scenario],
                          capture_output=True, text=True, timeout=60)
    out = json.loads(proc.stdout)
    assert "error" not in out, out
    return out


def _case(out):
    """The one [talk] case the console names."""
    cases = [w.split()[1] for w in out["warned"] if w.startswith("[talk] ")]
    assert len(cases) == 1, out["warned"]
    return cases[0]


# ── 1. hold to talk: every failure is visible ────────────────────────────────

@needs_node
def test_while_held_the_note_says_it_is_recording():
    out = _ptt("ok")
    assert out["heldRec"], "the button is not marked as recording while held"
    assert out["heldNote"].startswith("● Recording"), out["heldNote"]


@needs_node
@pytest.mark.parametrize("scenario,start", [("ok", ""), ("append", "80 kg adult, ")])
def test_the_transcript_appears_word_by_word(scenario, start):
    out = _ptt(scenario)
    words = TRANSCRIPT.split()
    assert out["boxSteps"] == [start + " ".join(words[:i]) for i in range(1, len(words) + 1)]
    assert out["box"] == start + TRANSCRIPT
    assert out["note"] == "Check the words, then press SEND." and not out["noteErr"]
    assert out["warned"] == []


@needs_node
def test_http_by_ip_says_voice_needs_https_or_localhost():
    out = _ptt("insecure")
    assert out["calls"] == [] and out["noteErr"]
    assert "https or localhost" in out["note"] and "http://192.168.1.126:8000" in out["note"]
    assert _case(out) == "insecure-origin"
    assert out["disabled"] is False and out["button"] == "HOLD TO TALK"


@needs_node
def test_permission_denied_says_so():
    out = _ptt("denied")
    assert out["calls"] == [] and out["noteErr"]
    assert "Microphone permission denied" in out["note"]
    assert _case(out) == "permission-denied"


@needs_node
def test_no_microphone_found_says_so():
    out = _ptt("nomic")
    assert out["calls"] == [] and out["noteErr"]
    assert "No microphone found" in out["note"]
    assert _case(out) == "no-microphone"


@needs_node
def test_letting_go_before_the_microphone_opened_is_not_silent():
    """The first press on a new site: the browser asks for the microphone, the
    medic lets go to answer it, and the press used to end with nothing shown."""
    out = _ptt("early")
    assert out["calls"] == [] and out["tracksStopped"] == 1
    assert "hold the button again" in out["note"].lower()
    assert _case(out) == "released-before-microphone"


@needs_node
@pytest.mark.parametrize("scenario", ["silent", "noaudio"])
def test_no_audio_captured_says_so_and_sends_nothing(scenario):
    out = _ptt(scenario)
    assert out["calls"] == [] and out["noteErr"]
    assert "No audio captured" in out["note"]
    assert _case(out) == "no-audio"


@needs_node
def test_a_tap_still_asks_to_hold():
    out = _ptt("short")
    assert out["calls"] == [] and "Hold the button while you speak." in out["note"]
    assert _case(out) == "too-short"


@needs_node
def test_a_transcribe_error_shows_its_status_and_reason():
    out = _ptt("error")
    assert out["box"] == "" and out["noteErr"]
    assert "/transcribe 503" in out["note"] and "out of memory" in out["note"]
    assert _case(out) == "transcribe-error"
    assert any("503" in w for w in out["warned"])


@needs_node
def test_transcribe_unreachable_says_so():
    out = _ptt("neterr")
    assert out["box"] == "" and out["noteErr"]
    assert "could not reach /transcribe" in out["note"]
    assert _case(out) == "transcribe-unreachable"


@needs_node
def test_an_empty_transcript_says_nothing_was_heard():
    out = _ptt("empty")
    assert out["box"] == "" and out["noteErr"] and "Nothing was heard" in out["note"]
    assert _case(out) == "empty-transcript"


def test_the_note_is_announced_and_an_error_is_red():
    assert '<div id="talknote" role="status" aria-live="polite">' in PORTAL
    assert "#talknote.err" in PORTAL


# ── 2. no MODE control ───────────────────────────────────────────────────────

def test_the_portal_has_no_mode_control():
    assert 'name="mode"' not in PORTAL and "MODE:" not in PORTAL
    assert "voice_mode" not in PORTAL


@needs_node
def test_send_does_not_send_voice_mode():
    out = _ptt("send")
    (query,) = [c for c in out["calls"] if c["url"] == "/query"]
    assert "voice_mode" not in query["body"]


def test_the_pipeline_takes_no_voice_mode():
    import os
    os.environ.setdefault("OPENAI_API_KEY", "test-offline")
    import openai_client as oc
    for fn in (oc.query_with_rag, oc._query_with_rag_internal, oc._run_pipeline):
        assert "voice_mode" not in inspect.signature(fn).parameters, fn.__name__


def test_no_client_sends_voice_mode():
    root = HERE.parent.parent
    for rel in ("server/run_tests.sh", "server/tools/latency_run.py",
                "server/tools/tts_latency_run.py", "client/cdss_client.py",
                "server/tests/client_render_harness.js"):
        assert "voice_mode" not in (root / rel).read_text(encoding="utf-8"), rel
