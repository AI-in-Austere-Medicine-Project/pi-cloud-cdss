"""
EdgeCDSS — voice output (ElevenLabs).

Isolated from the clinical core by design: every failure in here degrades to
"no audio", never to a missing, delayed or altered clinical answer.

Importable with no key, no network and no httpx — the offline suite pins the
contract in this module, and the clinical path must not be able to fail because
the voice path is misconfigured. (Same reason openai_client is importable
without the OpenAI SDK; see P-0.)

Why this module exists: /speak inlined the ElevenLabs call and collapsed every
upstream failure into `500 ElevenLabs error`. The v4.1 outage was a 400
`api_key_id_used_as_api_key` — the key *ID* from the dashboard had been pasted
into ELEVENLABS_API_KEY instead of the key — and the endpoint reported exactly
as much about that as it would about a dead network: nothing.
"""

import os
import re as _re

# One numeric-env parser for the repo: a typo'd knob degrades to the default
# and says so, it never raises. See openai_client._env_number.
from openai_client import _env_number

API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"

# ElevenLabs API keys are secrets and start with 'sk_'. The dashboard shows a
# 64-character hex key *ID* beside each key; that ID is an identifier, not a
# credential. Pasting it is a silent, plausible-looking config error that costs
# a 400 on every single request, so it is caught here before the network.
KEY_PREFIX = "sk_"

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"        # George
DEFAULT_MODEL_ID = "eleven_multilingual_v2"

# Long inputs are rejected upstream. A brief-mode answer is far under this; a
# detailed-mode answer plus expansion can approach it, and a clear local 413
# beats a 400 that has already cost a round trip and a character quota.
DEFAULT_MAX_CHARS = 2500
DEFAULT_TIMEOUT_S = 30.0


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


def config_problem():
    """Why voice cannot work, decided before any network call. None if it looks usable.

    Deliberately conservative: this only rejects values that CANNOT be a key.
    A well-formed but revoked or out-of-quota key still has to fail upstream.
    """
    key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        return ("voice output is not configured on this server "
                "(ELEVENLABS_API_KEY is unset)")
    if not key.startswith(KEY_PREFIX):
        return ("ELEVENLABS_API_KEY is not an ElevenLabs API key — keys start "
                f"with '{KEY_PREFIX}'. A 64-character hex value is the key ID "
                "shown beside the key in the dashboard, not the key itself; "
                "the API rejects it with api_key_id_used_as_api_key.")
    return None


def voice_available() -> bool:
    """What /status and /health must report instead of a hard-coded True."""
    return config_problem() is None


def _upstream_reason(response) -> str:
    """Human-readable cause from an ElevenLabs error body.

    ElevenLabs answers `{"detail": {"status": ..., "message": ...}}` or
    `{"detail": "..."}`. Error bodies never carry the key, and /speak is reached
    with a token that is printed in the web client, so echoing the upstream
    reason surfaces nothing that was private — and it is the whole difference
    between a five-minute fix and an unexplained dead button.
    """
    try:
        detail = response.json().get("detail", "")
    except Exception:
        detail = (response.text or "")
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status") or str(detail)
    detail = str(detail).strip()
    return detail[:300] if detail else "(no error body)"


async def synthesize(text: str) -> bytes:
    """MP3 bytes for `text`, or VoiceUnavailable carrying the status and reason."""
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

    try:
        import httpx                      # lazy: this module must import without it
    except ImportError:
        raise VoiceUnavailable(503, "voice output needs httpx, which is not installed")

    voice_id = (os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID).strip()
    model_id = (os.getenv("ELEVENLABS_MODEL_ID") or DEFAULT_MODEL_ID).strip()
    timeout = _env_number("CDSS_SPEAK_TIMEOUT_S", DEFAULT_TIMEOUT_S, float)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE}/{voice_id}",
                headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY").strip(),
                         "Content-Type": "application/json"},
                json={"text": text,
                      "model_id": model_id,
                      "voice_settings": {"stability": 0.5,
                                         "similarity_boost": 0.75,
                                         "speed": 0.85}},
                timeout=timeout)
    except Exception as e:
        # Starlink drops and tunnel flaps are the normal condition here. Voice
        # needs the network; the clinical answer already on screen does not.
        raise VoiceUnavailable(
            503, f"ElevenLabs unreachable ({type(e).__name__}) — voice needs connectivity.")

    if response.status_code != 200:
        raise VoiceUnavailable(
            502, f"ElevenLabs returned {response.status_code}: {_upstream_reason(response)}")
    if not response.content:
        raise VoiceUnavailable(502, "ElevenLabs returned an empty audio body.")
    return response.content


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
