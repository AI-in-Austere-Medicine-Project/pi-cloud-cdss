"""
The provider grid — five providers, one adapter table, no dead menu entries.

Model strings expire. Every id asserted here was verified against the live API
on 2026-08-22 rather than taken from memory, and the check that motivates the
discipline is in this file: `gemini-2.5-pro` now returns 404 "no longer
available", so a config written from memory would have shipped a dead entry.

These tests are OFFLINE. They pin the shape of the config and the adapter's
decisions; the live round-trips are recorded in providers.json's comment block
and in the PR, because a unit test that needs three API keys is a unit test
nobody runs.
"""
import json
import pathlib

import providers


CONFIG = json.loads((pathlib.Path(providers.__file__).parent / "providers.json").read_text())


# ── the grid ────────────────────────────────────────────────────────────────

def test_every_provider_uses_a_real_adapter():
    for pid, p in providers.PROVIDERS.items():
        assert p.get("adapter") in providers._ADAPTERS, f"{pid}: {p.get('adapter')}"


def test_gemini_and_xai_are_openai_compatible():
    """Neither needed new code — that is the point of the adapter split."""
    for pid, base in (("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
                      ("xai", "https://api.x.ai/v1")):
        p = providers.PROVIDERS[pid]
        assert p["adapter"] == "openai_compat"
        assert p["base_url"] == base
        assert p["base_url_env"], f"{pid} needs a base_url override for self-hosted mirrors"


def test_every_model_names_a_registered_provider():
    for spec in providers.MODELS.values():
        assert spec.provider in providers.PROVIDERS, spec.id


def test_the_verified_model_ids_are_registered():
    """Verified live 2026-08-22. Changing one of these is a deploy decision."""
    for model_id, provider in (("gemini-3.7-flash", "gemini"),
                               ("gemini-3.1-pro-preview", "gemini"),
                               ("grok-4", "xai")):
        assert model_id in providers.MODELS, model_id
        assert providers.MODELS[model_id].provider == provider


def test_no_model_id_that_the_api_has_retired():
    """gemini-2.5-pro returns 404 'no longer available' as of 2026-08-22.

    Pinned by name because it is the concrete reason this config was built by
    querying the APIs instead of from memory.
    """
    assert "gemini-2.5-pro" not in providers.MODELS


# ── the opaque-key rule ─────────────────────────────────────────────────────

def test_opaque_keys_are_not_shape_checked():
    """Rejecting a key by shape before any network call is only safe when the
    shape is certain and documented. It is not for Gemini or xAI."""
    for pid in ("gemini", "xai"):
        assert providers.PROVIDERS[pid].get("key_prefix") is None, pid


def test_opaque_key_providers_still_require_a_key(monkeypatch):
    """Opaque does not mean optional. Both ship a public base_url, and without
    requires_key the keyless-self-hosted exemption would let an unconfigured
    provider through to a network auth check on every /status poll."""
    for pid, env in (("gemini", "GEMINI_API_KEY"), ("xai", "XAI_API_KEY")):
        assert providers.PROVIDERS[pid].get("requires_key") is True, pid
        monkeypatch.delenv(env, raising=False)
        problem = providers.config_problem(pid)
        assert problem and env in problem, pid


def test_a_wrong_provider_key_is_still_caught_where_the_shape_is_known():
    """The opaque rule is per provider, not a blanket retreat."""
    assert providers.PROVIDERS["openai"]["key_prefix"] == "sk-"
    assert providers.PROVIDERS["anthropic"]["key_prefix"] == "sk-ant-"


# ── reasoning tiers need room for an answer ─────────────────────────────────

def test_reasoning_tiers_reserve_tokens():
    """The generator caps max_tokens at 700. A model that thinks before it
    speaks can spend all of it and return an empty string, which is why
    reserve_tokens exists."""
    for model_id in ("gemini-3.7-flash", "gemini-3.1-pro-preview", "grok-4"):
        assert providers.MODELS[model_id].reserve_tokens >= 3000, model_id


# ── the anthropic SDK dimension ─────────────────────────────────────────────

def test_temperature_needs_both_the_model_and_the_sdk_to_accept_it():
    """Two independent facts, conflated, broke claude-haiku-4-5 on the
    deployed venv: models[].supports_temperature is about the MODEL, and the
    installed SDK is a separate question.

    anthropic 1.0.0 removed `temperature` from Messages.create with no
    **kwargs, so passing it raised TypeError before any request — measured
    2026-08-22 on claude-haiku-4-5, whose config says supports_temperature:
    true.
    """
    import inspect
    source = inspect.getsource(providers._chat_anthropic)
    assert "_anthropic_accepts_temperature()" in source
    assert "spec.supports_temperature and _anthropic_accepts_temperature()" in source


def test_the_sdk_probe_fails_toward_dropping_the_parameter(monkeypatch):
    """Dropping it costs default sampling. Sending it to an SDK that does not
    take it costs every query."""
    providers._anthropic_accepts_temperature.cache_clear()
    monkeypatch.setitem(__import__("sys").modules, "anthropic", None)
    try:
        assert providers._anthropic_accepts_temperature() is False
    finally:
        providers._anthropic_accepts_temperature.cache_clear()


# ── the menu ────────────────────────────────────────────────────────────────

def test_an_unavailable_provider_contributes_no_models(monkeypatch):
    """xAI had no credits on 2026-08-22, so /status marked it unavailable and
    grok-4 never reached the dropdown. That is the architecture working: a
    model that cannot answer must not be selectable."""
    monkeypatch.setattr(providers, "provider_status",
                        lambda force=False: {p: {"label": p, "available": p != "xai",
                                                 "detail": "no credits" if p == "xai" else ""}
                                             for p in providers.PROVIDERS})
    menu = {m["id"] for m in providers.available_models()}
    assert "grok-4" not in menu
    assert "gemini-3.7-flash" in menu


def test_the_validator_is_not_a_menu_choice():
    """It stays pinned so a generator comparison changes one variable."""
    assert providers.validator_model() == "gpt-4o-mini"
    assert CONFIG["validator_model"] == "gpt-4o-mini"


def test_the_builtin_fallback_knows_every_provider():
    """providers.json going missing must degrade to a working server, not to
    one that has silently lost half its providers."""
    builtin = set(providers._BUILTIN_CONFIG["providers"])
    assert {"openai", "anthropic", "gemini", "xai"} <= builtin
