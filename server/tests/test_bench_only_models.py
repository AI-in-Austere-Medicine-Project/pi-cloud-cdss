"""edgecdss-v3 is bench only: off the live picker, by config.

Owner, 2026-10-27: "Take edgecdss-v3 off the live picker (bench only; config,
with a test) so qwen + Kokoro + whisper share the GPU." Live at 17:31 UTC an
edgecdss-v3 answer with qwen2.5:3b loaded as its validator left no GPU memory
for Kokoro (docs/VOICE_WARMUP_GPU_2026-10-27.md, memory budget).

providers.json marks the entry "bench_only": it is not on the menu, and a
request that names it (a portal menu cached before this change) is answered
by the default model. A bench server still runs it by naming it in
CDSS_LLM_MODEL.
"""
import json
import pathlib

import pytest

import providers

CONFIG = json.loads((pathlib.Path(providers.__file__).parent / "providers.json").read_text())


@pytest.fixture
def ollama_has_both(monkeypatch):
    monkeypatch.setattr(providers, "_ollama_tags", lambda force=False: {"qwen2.5:3b", "edgecdss-v3"})
    monkeypatch.setattr(providers, "_auth_problem", lambda pid: None)


def test_the_config_marks_edgecdss_v3_bench_only():
    entry = next(m for m in CONFIG["on_device_models"] if m["id"] == "edgecdss-v3")
    assert entry.get("bench_only") is True
    qwen = next(m for m in CONFIG["on_device_models"] if m["id"] == "qwen2.5:3b")
    assert not qwen.get("bench_only")


@pytest.mark.parametrize("provider", ["local", "openai"])
def test_the_live_picker_does_not_list_it(ollama_has_both, monkeypatch, provider):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", provider)
    monkeypatch.delenv("CDSS_LLM_MODEL", raising=False)
    menu = {m["id"] for m in providers.available_models(force=True)}
    assert "qwen2.5:3b" in menu
    assert "edgecdss-v3" not in menu


@pytest.mark.parametrize("provider", ["local", "openai"])
def test_a_request_naming_it_is_answered_by_the_default(ollama_has_both, monkeypatch, provider):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", provider)
    monkeypatch.delenv("CDSS_LLM_MODEL", raising=False)
    assert providers.resolve_model("edgecdss-v3") == providers.default_model()
    assert providers.resolve_model("edgecdss-v3") != "edgecdss-v3"


def test_a_bench_server_still_runs_it_by_name(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_MODEL", "edgecdss-v3")
    assert providers.default_model() == "edgecdss-v3"
    assert providers.resolve_model(None) == "edgecdss-v3"
