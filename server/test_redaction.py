"""
EdgeCDSS — _redact is field-based, not shape-based (SECURITY_AUDIT.md H-1).

/status needs no token. Its provider `detail` strings quote whatever the
upstream said, and what upstream says about a bad key routinely includes the
key. The redactor was a denylist of two SHAPES — /\bsk-.../ and nothing else —
which covered OpenAI and Anthropic and silently missed xAI, Gemini and
ElevenLabs. ElevenLabs is the instructive one: its keys begin "sk_" with an
underscore, so the pattern looked like it covered them and did not.

Coverage now comes from the FIELD list — providers.json's own key_env
declarations plus the two secrets no provider owns — so it does not depend on
anyone predicting what a credential looks like.

    cd server && ./run_unit_tests.sh

Stdlib only: providers.py imports its SDKs lazily, so this runs in the gate.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import providers  # noqa: E402


# One real-world shape per credential this deployment holds.
REAL_SHAPES = {
    "OPENAI_API_KEY": "sk-proj-" + "A" * 60,
    "ANTHROPIC_API_KEY": "sk-ant-api03-" + "B" * 60,
    "GEMINI_API_KEY": "AQ.Ab8RN6" + "C" * 40,
    "XAI_API_KEY": "xai-" + "D" * 60,
    "ELEVENLABS_API_KEY": "sk_" + "e" * 48,
}


@pytest.fixture
def keys_in_env(monkeypatch):
    for name, value in REAL_SHAPES.items():
        monkeypatch.setenv(name, value)
    providers._reset_status_cache()
    return REAL_SHAPES


@pytest.mark.parametrize("name", sorted(REAL_SHAPES))
def test_every_credential_format_is_redacted(keys_in_env, name):
    """The finding itself, one credential format per case."""
    key = keys_in_env[name]
    out = providers._redact(f"AuthenticationError: incorrect api key: {key}")
    assert key not in out, f"{name} survived redaction"
    assert "[redacted]" in out


def test_the_three_formats_the_old_denylist_missed(keys_in_env):
    """Pinned as a group because they shipped uncovered together."""
    for name in ("GEMINI_API_KEY", "XAI_API_KEY", "ELEVENLABS_API_KEY"):
        key = keys_in_env[name]
        assert key not in providers._redact(f"upstream rejected {key}"), name


def test_redaction_is_field_based_not_shape_based(monkeypatch):
    """A credential of a shape no pattern anticipates is still redacted.

    This is the whole point of the rewrite. Shape rules only fail closed for
    the shapes someone remembered.
    """
    weird = "totally-unlike-any-known-key-format-9f3a2b7c"
    monkeypatch.setenv("XAI_API_KEY", weird)
    providers._reset_status_cache()
    assert weird not in providers._redact(f"error: key {weird} rejected")


def test_every_declared_provider_key_env_is_covered(monkeypatch):
    """Regression guard for providers added later.

    The field list is read from providers.json's key_env declarations, so a new
    provider is covered the moment it is declared. If one is ever added that
    this does not reach, it fails here instead of shipping a quiet gap onto an
    unauthenticated endpoint.
    """
    declared = [p.get("key_env") for p in providers.PROVIDERS.values()
                if p.get("key_env")]
    assert declared, "no provider declares a key_env — the source list is wrong"
    for name in declared:
        secret = f"secret-value-for-{name}-0123456789"
        monkeypatch.setenv(name, secret)
        providers._reset_status_cache()
        assert secret not in providers._redact(f"upstream said: {secret}"), name


def test_the_secrets_no_provider_owns_are_covered(monkeypatch):
    """ELEVENLABS_API_KEY lives in tts.py and the access token in main.py.

    Neither is a provider in providers.json, and both would otherwise reach
    /status through an error string like any other value.
    """
    for name in providers._EXTRA_SECRET_ENV:
        secret = f"value-of-{name}-abcdefghij"
        monkeypatch.setenv(name, secret)
        providers._reset_status_cache()
        assert secret not in providers._redact(f"detail: {secret}"), name


def test_a_provider_console_url_is_stripped(keys_in_env):
    """The xAI team-URL echo.

    The console URL of the account that failed names the account. /status needs
    no token, and a diagnostic does not need to carry that.
    """
    detail = ("Your credit balance is too low. Visit "
              "https://console.x.ai/team/3f9c1e88-team-identifier/billing "
              "to top up.")
    out = providers._redact(detail)
    assert "console.x.ai" not in out
    assert "3f9c1e88-team-identifier" not in out
    assert "credit balance is too low" in out, "the useful half was thrown away"


def test_a_partially_masked_key_is_still_caught(monkeypatch):
    """The shape backstop earns its place.

    Providers quote keys back masked, so the value this process holds does not
    appear literally and only a shape rule can catch it.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-" + "A" * 60)
    providers._reset_status_cache()
    assert "sk-clear" not in providers._redact("rejected key sk-clear*****-xyz")


def test_an_ordinary_diagnostic_stays_readable(monkeypatch):
    """Over-redaction is its own outage — a dead menu entry with no reason."""
    monkeypatch.setenv("XAI_API_KEY", "xai-" + "D" * 60)
    providers._reset_status_cache()
    plain = "APIConnectionError: Connection error."
    assert providers._redact(plain) == plain


def test_the_unset_provider_message_survives(monkeypatch):
    """config_problem names the env var, never its value. It must stay legible."""
    monkeypatch.delenv("CDSS_LOCAL_API_KEY", raising=False)
    providers._reset_status_cache()
    msg = "Local is not configured (CDSS_LOCAL_API_KEY is unset)"
    assert providers._redact(msg) == msg


def test_a_short_env_value_is_not_treated_as_a_secret(monkeypatch):
    """A one-character value must not blank every matching character elsewhere."""
    monkeypatch.setenv("XAI_API_KEY", "0")
    providers._reset_status_cache()
    assert providers._redact("timeout after 30 seconds") == "timeout after 30 seconds"


def test_redact_handles_empty_and_none():
    assert providers._redact("") == ""
    assert providers._redact(None) == ""


def test_the_longest_secret_is_redacted_first(monkeypatch):
    """Where one secret is a prefix of another, order decides correctness.

    Replacing the short one first leaves the tail of the long one in the
    string — a partial key is still a key.
    """
    short = "shared-prefix-value"
    long = short + "-with-a-longer-tail"
    monkeypatch.setenv("XAI_API_KEY", short)
    monkeypatch.setenv("GEMINI_API_KEY", long)
    providers._reset_status_cache()
    out = providers._redact(f"failed for {long}")
    assert "with-a-longer-tail" not in out
    assert long not in out
