"""
EdgeCDSS — D7: the offline validator is its own setting.

Under CDSS_LLM_PROVIDER=local the validator was whatever CDSS_LLM_MODEL named,
so a bench of a distilled generator also swapped the validator. edgecdss-v1 and
edgecdss-v3 answered the validator prompt with a field card (20 and 19 of 23
calls on main b8902c1), every one held as unreadable since A19, and the bench
measured nothing about the generator (docs/DISTILL_BENCH_edgecdss-v3.md).

Owner, 2026-10-10: CDSS_VALIDATOR_MODEL names the offline validator, default
qwen2.5:3b; the generator and the validator are configured independently. With
the generator on its default (qwen2.5:3b) nothing changes.

    cd server && ./run_unit_tests.sh
"""
import openai_client as oc
import providers
from test_local_llm import (GENERATED_QUERY, NATIVE_CALLS, FakeOpenAI,  # noqa: F401
                            _JtsHit, fake_sdk)


def _calls_by_role():
    gen = [c["model"] for c in NATIVE_CALLS if c["system"] != oc.VALIDATOR_PROMPT]
    val = [c["model"] for c in NATIVE_CALLS if c["system"] == oc.VALIDATOR_PROMPT]
    return gen, val


# ── the setting ──────────────────────────────────────────────────────────────

def test_offline_validator_defaults_to_qwen_not_the_generator(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "edgecdss-v3")
    assert providers.default_model() == "edgecdss-v3"
    assert providers.validator_model() == "qwen2.5:3b", \
        "a distilled generator must not become its own validator"


def test_offline_validator_comes_from_cdss_validator_model(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "edgecdss-v3")
    monkeypatch.setenv("CDSS_VALIDATOR_MODEL", "llama3.2:3b")
    assert providers.default_model() == "edgecdss-v3"
    assert providers.validator_model() == "llama3.2:3b"
    assert providers.MODELS["llama3.2:3b"].provider == "local"


def test_offline_generator_is_unaffected_by_the_validator_setting(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_VALIDATOR_MODEL", "edgecdss-v3")
    assert providers.default_model() == "qwen2.5:3b"
    assert providers.validator_model() == "edgecdss-v3"


def test_offline_a_cloud_validator_name_is_not_used(monkeypatch):
    """The same .env line serves the cloud path, where it names a cloud model.
    Offline, a cloud validator would fail every query closed, and registering
    the name as local would put a cloud model on the local provider."""
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "edgecdss-v3")
    monkeypatch.setenv("CDSS_VALIDATOR_MODEL", "gpt-4o-mini")
    assert providers.validator_model() == "qwen2.5:3b"
    assert providers.MODELS["gpt-4o-mini"].provider == "openai"


# ── production unchanged ─────────────────────────────────────────────────────

def test_offline_default_is_qwen_for_both(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    assert providers.default_model() == "qwen2.5:3b"
    assert providers.validator_model() == "qwen2.5:3b"


def test_cloud_validator_is_unchanged(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_MODEL", "gpt-4o")
    assert providers.validator_model() == providers.VALIDATOR_MODEL == "gpt-4o-mini"


# ── end to end: the calls go where the settings say ─────────────────────────

def test_pipeline_sends_generator_and_validator_to_their_own_models(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "edgecdss-v3")
    r = oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit())
    assert r["source_mode"] == "JTS_GROUNDED", r["source_mode"]
    gen, val = _calls_by_role()
    assert gen == ["edgecdss-v3"]
    assert val == ["qwen2.5:3b"]
    assert r["model"] == "local/edgecdss-v3"
    assert r["validator_provider"] == "local"
    assert FakeOpenAI.instances == [], "offline, nothing reached the cloud"


def test_pipeline_default_offline_calls_are_unchanged(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit())
    gen, val = _calls_by_role()
    assert gen == ["qwen2.5:3b"] and val == ["qwen2.5:3b"]
