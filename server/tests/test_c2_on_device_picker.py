"""C2 (owner, 2026-10-12): the portal's model picker lists the on-device Ollama
models alongside the cloud models, labelled "(on device)". Selecting one routes
that request to the local provider, validated on the device by D7's rule
(CDSS_VALIDATOR_MODEL if it names an on-device model, else qwen2.5:3b), with no
cloud call. The served answer names the model that wrote it. The default is
unchanged.

The listed models are providers.json's on-device entries: qwen2.5:3b and
edgecdss-v3 (owner ruling: the v3 verdict does not bar it from the picker). An
entry is on the menu only when Ollama reports that tag installed, so a host
without Ollama, or without the tag, lists nothing it cannot serve. This
un-defers "the local-model portal toggle" (work order, Deferred).
"""
import pathlib

import pytest

import openai_client as oc
import providers
from test_local_llm import (GENERATED_QUERY, NATIVE_CALLS, FakeOpenAI,  # noqa: F401
                            _JtsHit, fake_sdk)

ON_DEVICE = {"qwen2.5:3b", "edgecdss-v3"}


@pytest.fixture
def ollama(monkeypatch):
    """Ollama's installed tags, as /api/tags would report them."""
    tags = set(ON_DEVICE)
    monkeypatch.setattr(providers, "_ollama_tags", lambda force=False: set(tags))
    return tags


def _menu():
    return {m["id"]: m for m in providers.available_models(force=True)}


def _calls():
    gen = [c["model"] for c in NATIVE_CALLS if c["system"] != oc.VALIDATOR_PROMPT]
    val = [c["model"] for c in NATIVE_CALLS if c["system"] == oc.VALIDATOR_PROMPT]
    return gen, val


# ── the menu ─────────────────────────────────────────────────────────────────

def test_the_menu_lists_the_on_device_models_labelled(ollama, monkeypatch):
    monkeypatch.setattr(providers, "_auth_problem", lambda pid: None)
    menu = _menu()
    for mid in ON_DEVICE:
        assert mid in menu, mid
        assert menu[mid]["provider"] == "local"
        assert menu[mid]["label"].endswith("(on device)"), menu[mid]["label"]
    assert "gpt-4o-mini" in menu, "the cloud models are still listed"


def test_a_tag_ollama_does_not_have_is_not_listed(ollama, monkeypatch):
    monkeypatch.setattr(providers, "_auth_problem", lambda pid: None)
    ollama.discard("edgecdss-v3")
    menu = _menu()
    assert "qwen2.5:3b" in menu and "edgecdss-v3" not in menu


def test_without_ollama_the_menu_is_what_it_was(monkeypatch):
    monkeypatch.setattr(providers, "_ollama_tags", lambda force=False: None)
    monkeypatch.setattr(providers, "_auth_problem", lambda pid: None)
    assert not any(m["provider"] == "local" for m in providers.available_models(force=True))


# ── routing and the validator ────────────────────────────────────────────────

def test_selecting_an_on_device_model_resolves_to_it(ollama):
    assert providers.resolve_model("edgecdss-v3") == "edgecdss-v3"
    assert providers.resolve_model(None) == providers.DEFAULT_MODEL == "gpt-4o-mini"


@pytest.mark.parametrize("setting, expected", [
    (None, "qwen2.5:3b"),            # the live service: no local validator set
    ("gpt-4o", "qwen2.5:3b"),        # a cloud name is never the on-device validator
    ("qwen2.5:3b", "qwen2.5:3b"),
])
def test_an_on_device_generator_gets_an_on_device_validator(ollama, monkeypatch, setting, expected):
    if setting:
        monkeypatch.setenv("CDSS_VALIDATOR_MODEL", setting)
    assert providers.validator_model("edgecdss-v3") == expected


def test_the_cloud_validator_is_unchanged(ollama):
    assert providers.validator_model() == providers.validator_model("gpt-4o") == "gpt-4o-mini"


def test_an_on_device_request_makes_no_cloud_call(ollama):
    r = oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit(), model="edgecdss-v3")
    gen, val = _calls()
    assert gen == ["edgecdss-v3"] and val == ["qwen2.5:3b"]
    assert FakeOpenAI.instances == [], "an on-device request reached the cloud"
    assert r["model"] == "local/edgecdss-v3" and r["provider"] == "local"


def test_the_default_request_is_unchanged(ollama):
    oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit())
    assert NATIVE_CALLS == [], "the default request reached the device"
    (client,) = FakeOpenAI.instances
    assert [c["model"] for c in client.calls] == ["gpt-4o-mini", "gpt-4o-mini"]


def test_offline_an_on_device_selection_is_honoured(ollama, monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    assert providers.resolve_model("edgecdss-v3") == "edgecdss-v3"
    assert providers.resolve_model("gpt-4o") == "qwen2.5:3b", "a cloud pick still answers on the device"
    assert providers.resolve_model(None) == "qwen2.5:3b"


# ── the portal ───────────────────────────────────────────────────────────────

PORTAL = (pathlib.Path(oc.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


def test_the_portal_does_not_call_an_on_device_answer_offline():
    badge = PORTAL[PORTAL.index("function providerBadge"):PORTAL.index("function fallbackBanner")]
    assert ">on-device model</span>" in badge, "the badge text for a chosen on-device answer"
    assert ">local model · offline</span>" in badge, "a cloud-unreachable fallback keeps its wording"


def test_the_picker_says_where_an_on_device_pick_is_validated():
    menu = PORTAL[PORTAL.index("async function refreshModels"):PORTAL.index("refreshModels();")]
    assert "on_device_validator_model" in menu
