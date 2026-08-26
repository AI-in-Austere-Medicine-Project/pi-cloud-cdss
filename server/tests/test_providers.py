"""
EdgeCDSS — provider registry contract.

Runs with ZERO API keys and neither SDK installed. That is not a convenience:
the offline suite runs on the system interpreter, and the whole point of the
provider layer is that a missing key or SDK removes a menu entry rather than
breaking the clinical path.

    cd server && ./run_unit_tests.sh
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import providers  # noqa: E402
from providers import ModelSpec, ProviderUnavailable  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts with no provider configured and nothing cached."""
    for provider in providers.PROVIDERS.values():
        monkeypatch.delenv(provider.get("key_env", ""), raising=False)
        if provider.get("base_url_env"):
            monkeypatch.delenv(provider["base_url_env"], raising=False)
    monkeypatch.delenv("CDSS_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("CDSS_VALIDATOR_MODEL", raising=False)
    providers._reset_status_cache()
    providers._reset_clients()
    yield
    providers._reset_status_cache()
    providers._reset_clients()


# ── config loading ───────────────────────────────────────────────────────────

def test_registry_loaded_from_config():
    assert providers.MODELS, "providers.json produced no models"
    assert "openai" in providers.PROVIDERS
    assert "anthropic" in providers.PROVIDERS
    assert providers.DEFAULT_MODEL in providers.MODELS
    assert providers.VALIDATOR_MODEL in providers.MODELS


def test_every_model_names_a_known_provider():
    for spec in providers.MODELS.values():
        assert spec.provider in providers.PROVIDERS


def test_builtin_config_is_a_working_fallback():
    """A corrupt providers.json must degrade to defaults, not to a dead server.

    _env_number's lesson: this file is edited to change models, so it will
    eventually be edited wrong, and the deploy target is a fanless box behind a
    watchdog that reboots on failed health checks.
    """
    config = providers._BUILTIN_CONFIG
    assert config["default_model"] in {m["id"] for m in config["models"]}
    assert all(m["provider"] in config["providers"] for m in config["models"])


def test_missing_config_file_falls_back(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(providers, "_CONFIG_PATH", tmp_path / "absent.json")
    assert providers._load_config() is providers._BUILTIN_CONFIG
    assert "not found" in capsys.readouterr().out


def test_unparseable_config_file_falls_back(monkeypatch, tmp_path, capsys):
    bad = tmp_path / "providers.json"
    bad.write_text("{not json,,,")
    monkeypatch.setattr(providers, "_CONFIG_PATH", bad)
    assert providers._load_config() is providers._BUILTIN_CONFIG
    assert "unreadable" in capsys.readouterr().out


# ── config_problem: pre-network diagnosis ────────────────────────────────────

def test_unset_key_is_reported_by_env_var_name():
    problem = providers.config_problem("anthropic")
    assert problem and "ANTHROPIC_API_KEY" in problem


def test_wrong_prefix_is_caught_before_the_network(monkeypatch):
    """The tts.py failure, one provider over: an OpenAI key in the Claude slot."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-proj-abcdef")
    problem = providers.config_problem("anthropic")
    assert problem and "sk-ant-" in problem


def test_well_formed_key_passes_the_pre_network_check(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-xxxx")
    assert providers.config_problem("anthropic") is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-xxxx")
    assert providers.config_problem("openai") is None


def test_keyless_self_hosted_provider_is_allowed(monkeypatch):
    """An Ollama or llama.cpp endpoint has no key. That is not a misconfiguration."""
    assert providers.config_problem("local") is not None
    monkeypatch.setenv("CDSS_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    assert providers.config_problem("local") is None


def test_unknown_provider_is_named_not_raised():
    assert "unknown provider" in providers.config_problem("mistral")


def test_config_problem_never_echoes_key_material(monkeypatch):
    """Nothing that reaches /status or a log may contain the key itself."""
    secret = "sk-DO-NOT-LEAK-THIS-VALUE"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    for provider_id in ("anthropic", "openai"):
        problem = providers.config_problem(provider_id) or ""
        assert secret not in problem
        assert "DO-NOT-LEAK" not in problem


def test_status_detail_never_echoes_key_material(monkeypatch):
    secret = "sk-ant-DO-NOT-LEAK-THIS-VALUE"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setattr(providers, "_auth_problem",
                        lambda p: "AuthenticationError: invalid x-api-key")
    for entry in providers.provider_status().values():
        assert secret not in entry["detail"]


# ── provider_status / available_models ───────────────────────────────────────

def test_unconfigured_providers_are_unavailable_with_a_reason():
    status = providers.provider_status()
    for provider_id, entry in status.items():
        assert entry["available"] is False
        assert entry["detail"], f"{provider_id} unavailable with no reason"


def test_auth_failure_makes_a_configured_provider_unavailable(monkeypatch):
    """Key presence is not authentication. A revoked key must not stay on the menu."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-revoked")
    monkeypatch.setattr(providers, "_auth_problem",
                        lambda p: "AuthenticationError: invalid x-api-key")
    entry = providers.provider_status()["anthropic"]
    assert entry["available"] is False
    assert "invalid x-api-key" in entry["detail"]


def test_auth_success_makes_a_provider_available(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")
    monkeypatch.setattr(providers, "_auth_problem", lambda p: None)
    entry = providers.provider_status()["anthropic"]
    assert entry["available"] is True
    assert entry["detail"] == ""


def test_auth_check_is_not_run_when_config_is_already_broken(monkeypatch):
    """No network round trip for a provider we already know cannot work."""
    calls = []
    monkeypatch.setattr(providers, "_auth_problem",
                        lambda p: calls.append(p) or None)
    providers.provider_status()
    assert calls == [], f"auth checked for unconfigured providers: {calls}"


def test_a_hosted_provider_with_a_base_url_still_needs_its_key(monkeypatch):
    """`requires_key` — the keyless exemption is for SELF-hosted endpoints.

    "has a base_url" was the proxy for self-hosted, and it breaks for a hosted
    provider reached through an OpenAI-compatibility endpoint: Gemini ships a
    public base_url and still needs a key. Without the flag it read as
    configured, and /status made a real network round trip for it every five
    minutes on a device that may be offline.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    providers._reset_status_cache()
    problem = providers.config_problem("gemini")
    assert problem and "GEMINI_API_KEY" in problem

    # A genuinely self-hosted provider is unaffected.
    monkeypatch.setenv("CDSS_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.delenv("CDSS_LOCAL_API_KEY", raising=False)
    assert providers.config_problem("local") is None


def test_gemini_models_are_specified_and_activated():
    """Supersedes test_gemini_is_config_only_until_models_are_specified.

    That test held the provider inert while the ids were unknown, because
    guessing one produces a menu entry that 404s at the first clinical query.
    The ids are now specified and were verified against the live API on
    2026-08-22 — see test_provider_grid.py for the grid-level assertions.
    """
    assert "gemini" in providers.PROVIDERS
    gemini_models = [m for m in providers.MODELS.values() if m.provider == "gemini"]
    assert gemini_models, "gemini is registered but contributes no models"
    for spec in gemini_models:
        assert spec.reserve_tokens >= 3000, (
            f"{spec.id} is a reasoning tier and needs room for a visible answer")


def test_status_is_cached_between_calls(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")
    calls = []
    monkeypatch.setattr(providers, "_auth_problem",
                        lambda p: calls.append(p) or None)
    providers.provider_status()
    providers.provider_status()
    assert calls.count("anthropic") == 1
    providers.provider_status(force=True)
    assert calls.count("anthropic") == 2


def test_menu_is_empty_with_no_keys():
    assert providers.available_models() == []


def test_menu_contains_only_available_providers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")
    monkeypatch.setattr(providers, "_auth_problem",
                        lambda p: None if p == "anthropic" else "no key")
    menu = providers.available_models()
    assert menu, "an authenticated provider contributed no models"
    assert {m["provider"] for m in menu} == {"anthropic"}
    assert all(m["id"] in providers.MODELS for m in menu)


# ── model resolution ─────────────────────────────────────────────────────────

def test_resolve_known_model_is_identity():
    for model_id in providers.MODELS:
        assert providers.resolve_model(model_id) == model_id


def test_resolve_unknown_model_falls_back_to_default():
    assert providers.resolve_model("gpt-9-turbo") == providers.default_model()
    assert providers.resolve_model(None) == providers.default_model()
    assert providers.resolve_model("") == providers.default_model()


def test_env_can_override_the_default_model(monkeypatch):
    other = next(m for m in providers.MODELS if m != providers.DEFAULT_MODEL)
    monkeypatch.setenv("CDSS_DEFAULT_MODEL", other)
    assert providers.default_model() == other


def test_garbage_env_override_does_not_break_the_default(monkeypatch):
    monkeypatch.setenv("CDSS_DEFAULT_MODEL", "not-a-model")
    assert providers.default_model() == providers.DEFAULT_MODEL


def test_validator_model_is_independent_of_the_selected_model(monkeypatch):
    """The validator is the control in a cross-model comparison.

    If the dropdown moved both, a change in blocked-response rate could not be
    attributed to the generator or to the validator.
    """
    other = next(m for m in providers.MODELS if m != providers.DEFAULT_MODEL)
    monkeypatch.setenv("CDSS_DEFAULT_MODEL", other)
    assert providers.validator_model() == providers.VALIDATOR_MODEL
    assert providers.validator_model() != providers.default_model()


# ── dispatch ─────────────────────────────────────────────────────────────────

class FakeOpenAI:
    """Records the kwargs the OpenAI-compatible adapter would send."""

    def __init__(self):
        self.seen = {}
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.seen = kwargs
                return type("R", (), {"choices": [type("C", (), {
                    "message": type("M", (), {"content": " answer "})()})()]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


class FakeAnthropic:
    """Records the kwargs the native Anthropic adapter would send."""

    def __init__(self, blocks=None):
        self.seen = {}
        outer = self
        blocks = blocks or [type("B", (), {"type": "text", "text": " answer "})()]

        class _Messages:
            def create(self, **kwargs):
                outer.seen = kwargs
                return type("R", (), {"content": blocks})()

        self.messages = _Messages()


def test_unknown_model_raises_provider_unavailable():
    with pytest.raises(ProviderUnavailable):
        providers.chat("sys", [{"role": "user", "content": "hi"}], model="nope")


def test_openai_compat_puts_system_in_messages(monkeypatch):
    fake = FakeOpenAI()
    monkeypatch.setattr(providers, "_openai_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-oai",
                        ModelSpec(id="test-oai", provider="openai", label="t"))
    out = providers.chat("SYSTEM", [{"role": "user", "content": "hi"}],
                         model="test-oai", temperature=0.2, max_tokens=700)
    assert out == "answer"
    assert fake.seen["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert fake.seen["messages"][1] == {"role": "user", "content": "hi"}
    assert fake.seen["temperature"] == 0.2
    assert fake.seen["max_tokens"] == 700


def test_anthropic_puts_system_in_its_own_parameter(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-claude",
                        ModelSpec(id="test-claude", provider="anthropic", label="t"))
    out = providers.chat("SYSTEM", [{"role": "user", "content": "hi"}],
                         model="test-claude")
    assert out == "answer"
    assert fake.seen["system"] == "SYSTEM"
    assert fake.seen["messages"] == [{"role": "user", "content": "hi"}]
    assert all(m["role"] != "system" for m in fake.seen["messages"])


def test_temperature_is_dropped_for_models_that_reject_it(monkeypatch):
    """Claude Opus 5 and Sonnet 5 return 400 for any sampling parameter."""
    fake = FakeAnthropic()
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-notemp",
                        ModelSpec(id="test-notemp", provider="anthropic", label="t",
                                  supports_temperature=False))
    providers.chat("s", [{"role": "user", "content": "hi"}],
                   model="test-notemp", temperature=0)
    assert "temperature" not in fake.seen


def test_effort_is_sent_only_when_configured(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-effort",
                        ModelSpec(id="test-effort", provider="anthropic", label="t",
                                  effort="low"))
    providers.chat("s", [{"role": "user", "content": "hi"}], model="test-effort")
    assert fake.seen["output_config"] == {"effort": "low"}

    monkeypatch.setitem(providers.MODELS, "test-noeffort",
                        ModelSpec(id="test-noeffort", provider="anthropic", label="t"))
    providers.chat("s", [{"role": "user", "content": "hi"}], model="test-noeffort")
    assert "output_config" not in fake.seen


def test_reserve_tokens_widens_the_output_cap(monkeypatch):
    """A thinking model spends max_tokens on reasoning before it writes anything.

    Without the reserve, the 700-token clinical cap can be consumed entirely by
    reasoning and return an empty answer.
    """
    fake = FakeAnthropic()
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-thinks",
                        ModelSpec(id="test-thinks", provider="anthropic", label="t",
                                  reserve_tokens=3000))
    providers.chat("s", [{"role": "user", "content": "hi"}],
                   model="test-thinks", max_tokens=700)
    assert fake.seen["max_tokens"] == 3700


def test_only_text_blocks_are_returned(monkeypatch):
    """Thinking blocks precede the answer and must not be shown to a medic."""
    blocks = [
        type("B", (), {"type": "thinking", "thinking": "internal reasoning"})(),
        type("B", (), {"type": "text", "text": "Apply a tourniquet."})(),
    ]
    fake = FakeAnthropic(blocks=blocks)
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: fake)
    monkeypatch.setitem(providers.MODELS, "test-thinking-blocks",
                        ModelSpec(id="test-thinking-blocks", provider="anthropic",
                                  label="t"))
    out = providers.chat("s", [{"role": "user", "content": "hi"}],
                         model="test-thinking-blocks")
    assert out == "Apply a tourniquet."
    assert "internal reasoning" not in out


def test_missing_sdk_degrades_to_provider_unavailable(monkeypatch):
    """Neither SDK is installed on the offline interpreter. That is not a crash."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-good")
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def no_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setitem(__builtins__ if isinstance(__builtins__, dict)
                        else __builtins__.__dict__, "__import__", no_anthropic)
    with pytest.raises(ProviderUnavailable) as excinfo:
        providers._anthropic_client("anthropic")
    assert "not installed" in str(excinfo.value)


def test_upstream_errors_are_redacted_before_reaching_status():
    """Providers quote the key back, partially masked. /status is unauthenticated.

    Their masking is not ours to rely on: the same endpoint the web client polls
    without a token would otherwise carry a key prefix and suffix.
    """
    upstream = ("AuthenticationError: Error code: 401 - Incorrect API key "
                "provided: sk-clear*****************-xyz. You can find your key")
    redacted = providers._redact(upstream)
    assert "sk-clear" not in redacted
    assert "[redacted]" in redacted
    assert "AuthenticationError" in redacted, "the useful part must survive"
    assert "401" in redacted


def test_redaction_covers_both_providers_key_shapes():
    for key in ("sk-ant-api03-abcdefgh", "sk-proj-abcdefgh", "sk-abcdefgh"):
        assert key not in providers._redact(f"bad key {key} rejected")
