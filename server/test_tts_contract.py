"""
EdgeCDSS — the voice path must fail loudly, locally, and never silently.

The v4.1 voice outage was a config error with no signal: ELEVENLABS_API_KEY held
the 64-character hex key *ID* from the dashboard instead of the `sk_` key, the
API answered 400 api_key_id_used_as_api_key on every request, /speak reported
`500 ElevenLabs error` for it, /status reported `voice_support: true` regardless,
and the web client printed "audio unavailable" with no reason. Four layers, none
of which named the cause.

These tests are offline: no key, no network, no httpx, no ChromaDB.

    cd server && ./run_unit_tests.sh
"""

import asyncio
import os
import re
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tts  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

KEY_ID = "4a" + "0" * 62          # shape of the value that caused the outage
GOOD_KEY = "sk_" + "0" * 48


class _NoNetwork:
    """Any attempt to reach the network during these tests is a test failure."""

    def __init__(self, *a, **kw):
        raise AssertionError("network call attempted")


def with_key(value):
    if value is None:
        os.environ.pop("ELEVENLABS_API_KEY", None)
    else:
        os.environ["ELEVENLABS_API_KEY"] = value


def speak(text, key):
    """synthesize() outcome as (status, detail), never reaching the network."""
    with_key(key)
    try:
        import httpx
        original, httpx.AsyncClient = httpx.AsyncClient, _NoNetwork
    except ImportError:
        original = None
    try:
        asyncio.run(tts.synthesize(text))
        raise AssertionError("expected VoiceUnavailable")
    except tts.VoiceUnavailable as e:
        return e.status, e.detail
    finally:
        if original is not None:
            import httpx
            httpx.AsyncClient = original
        with_key(None)


# --- the outage itself -------------------------------------------------------

def test_a_key_id_is_rejected_before_the_network():
    """THE ONE THAT MATTERS. A pasted key ID cost every request a 400 upstream."""
    with_key(KEY_ID)
    try:
        problem = tts.config_problem()
    finally:
        with_key(None)
    assert problem, "a 64-char hex key ID was accepted as an API key"
    assert "sk_" in problem, problem


def test_the_key_id_message_says_what_to_do():
    """A reason the operator cannot act on is barely better than the old 500."""
    with_key(KEY_ID)
    try:
        problem = tts.config_problem()
    finally:
        with_key(None)
    assert "ELEVENLABS_API_KEY" in problem
    assert "key ID" in problem


def test_a_wellformed_key_is_not_rejected_locally():
    """The guard must not become a second outage: only impossible values fail here."""
    with_key(GOOD_KEY)
    try:
        assert tts.config_problem() is None
        assert tts.voice_available() is True
    finally:
        with_key(None)


# --- every failure names itself ---------------------------------------------

def test_missing_key_is_503_and_says_so():
    status, detail = speak("give TXA", None)
    assert status == 503, status
    assert "ELEVENLABS_API_KEY" in detail


def test_key_id_through_synthesize_is_503_not_500():
    status, detail = speak("give TXA", KEY_ID)
    assert status == 503, status
    assert "sk_" in detail


def test_empty_text_is_400():
    status, _ = speak("   ", GOOD_KEY)
    assert status == 400, status


def test_overlong_text_is_capped_locally():
    status, detail = speak("x" * (tts.DEFAULT_MAX_CHARS + 1), GOOD_KEY)
    assert status == 413, status
    assert str(tts.DEFAULT_MAX_CHARS) in detail


def test_the_cap_stays_tunable_and_survives_a_typo():
    os.environ["CDSS_SPEAK_MAX_CHARS"] = "10"
    try:
        assert speak("x" * 11, GOOD_KEY)[0] == 413
    finally:
        del os.environ["CDSS_SPEAK_MAX_CHARS"]
    os.environ["CDSS_SPEAK_MAX_CHARS"] = "ten thousand"
    try:
        assert speak("x" * 11, GOOD_KEY)[0] != 413, "a typo'd cap must not start rejecting text"
    finally:
        del os.environ["CDSS_SPEAK_MAX_CHARS"]


def test_upstream_reason_is_extracted_not_swallowed():
    class Resp:
        def json(self):
            return {"detail": {"status": "api_key_id_used_as_api_key",
                               "message": "API key ID used as API key"}}
        text = ""
    assert "API key ID used as API key" in tts._upstream_reason(Resp())

    class Plain:
        def json(self):
            raise ValueError
        text = "quota_exceeded"
    assert "quota_exceeded" in tts._upstream_reason(Plain())


# --- isolation from the clinical core ---------------------------------------

def test_module_imports_without_httpx_or_a_key():
    """/speak is optional; the clinical path must not depend on voice config."""
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); "
         "sys.modules['httpx'] = None; import tts; print(tts.voice_available())" % HERE],
        env={k: v for k, v in os.environ.items() if k != "ELEVENLABS_API_KEY"},
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("False"), proc.stdout


def test_speech_normalisation_survived_the_move():
    spoken = tts.normalize_for_speech("Give **0.24 mL** of 100mg/mL ketamine IV q5min | 34kg")
    assert "0.24 milliliters" in spoken
    assert "100 milligrams per milliliter" in spoken
    assert "I-V" in spoken
    assert "every 5 minutes" in spoken
    assert "34 kilograms" in spoken
    assert "**" not in spoken


# --- meta-tests: the shapes that hid this ------------------------------------

def test_speak_does_not_inline_the_elevenlabs_call_again():
    source = open(os.path.join(HERE, "main.py")).read()
    assert "api.elevenlabs.io" not in source, "the TTS call belongs in tts.py"
    assert "ElevenLabs error" not in source, "a generic upstream error hides the cause"


def test_voice_support_is_never_hardcoded_true():
    """/status claiming voice_support: true while voice was dead is why nobody
    noticed for a release cycle."""
    source = open(os.path.join(HERE, "main.py")).read()
    assert not re.search(r'"voice_support"\s*:\s*True', source)
