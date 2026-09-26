"""
EdgeCDSS — an explicitly selected model is waited for; only the default falls back fast.

Multi-model benchmark run 3 (docs/MULTI_MODEL_BENCHMARK_2026-09-25.md): at the
8 s CDSS_LLM_CLOUD_TIMEOUT, 20 of 25 Opus turns and 24 of 25 gemini-3.1-pro
turns were answered by the on-device qwen2.5:3b through the hybrid fallback,
and nothing but a footer badge said so. A medic who picks a model from the menu
asked for THAT model.

The rule pinned here:
  - a model the medic selected, other than the default, gets 60 s
    (CDSS_LLM_SELECTED_TIMEOUT) before the fallback fires;
  - the default model — nothing selected, or the default selected — keeps the
    8 s fast fallback (CDSS_LLM_CLOUD_TIMEOUT);
  - the validator is the control, not the medic's choice: it keeps 8 s;
  - every fallback is logged with the model that was requested;
  - a fallback answer says so above the brief, not only in the footer.

    cd server && ./run_unit_tests.sh
"""
import ast
import pathlib

import pytest

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
from test_local_llm import (  # noqa: E402,F401  (fake_sdk is an autouse fixture)
    APITimeoutError, FakeOpenAI, GENERATED_QUERY, _JtsHit, _clients,
    _cloud_fails_with, fake_sdk)
from test_log_contract import log_and_read  # noqa: E402

SELECTED = "gpt-4o"          # on the menu, same provider as the default, not the default


@pytest.fixture(autouse=True)
def no_timeout_env(monkeypatch):
    for name in ("CDSS_LLM_CLOUD_TIMEOUT", "CDSS_LLM_SELECTED_TIMEOUT"):
        monkeypatch.delenv(name, raising=False)


def run(model=None):
    return oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit(), model=model)


def _timeouts():
    """The timeout of each cloud call, in order: generator first, then validator."""
    (cloud,), _local = _clients()
    return [o["timeout"] for o in cloud.options]


def test_premise_the_default_is_not_the_selected_model():
    assert providers.default_model() == "gpt-4o-mini" != SELECTED
    assert SELECTED in providers.MODELS


# ── the timeout follows the medic's choice ───────────────────────────────────

@pytest.mark.parametrize("model", [None, "", "gpt-4o-mini"])
def test_the_default_model_keeps_the_8s_fast_fallback(model):
    r = run(model)
    assert r["source_mode"] == "JTS_GROUNDED"
    assert _timeouts() == [8.0, 8.0]


def test_an_explicitly_selected_model_is_given_60s():
    run(SELECTED)
    generator, validator = _timeouts()
    assert generator == 60.0
    assert validator == 8.0, "the validator is the control, not the medic's choice"


def test_the_selected_timeout_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_SELECTED_TIMEOUT", "45")
    monkeypatch.setenv("CDSS_LLM_CLOUD_TIMEOUT", "5")
    run(SELECTED)
    assert _timeouts() == [45.0, 5.0]
    monkeypatch.setenv("CDSS_LLM_SELECTED_TIMEOUT", "soon")
    assert providers.selected_model_timeout_s() == 60.0


def test_an_unknown_model_is_the_default_and_falls_back_fast():
    run("not-a-model")
    assert _timeouts() == [8.0, 8.0]


def test_a_selected_model_that_still_times_out_falls_back_and_says_what_was_asked(monkeypatch):
    _cloud_fails_with(monkeypatch, APITimeoutError("Request timed out."))
    r = run(SELECTED)
    assert r["provider"] == "local-fallback"
    assert r["model"] == "local/qwen2.5:3b"
    assert r["fallback_from"] == "openai/gpt-4o"
    gen = next(f for f in r["fallbacks"] if f["role"] == "generator")
    assert gen == {"role": "generator", "requested": "openai/gpt-4o",
                   "served": "local/qwen2.5:3b", "error": "APITimeoutError",
                   "timeout_s": 60.0}


# ── every fallback is logged, with what was requested ────────────────────────

def test_every_fallback_is_logged_with_the_requested_model(monkeypatch):
    _cloud_fails_with(monkeypatch, APITimeoutError("Request timed out."))
    entry = log_and_read(run())
    assert entry["log_schema"] == oc.LOG_SCHEMA_VERSION == 13
    roles = {f["role"]: f for f in entry["fallbacks"]}
    assert roles["generator"]["requested"] == "openai/gpt-4o-mini"
    assert roles["generator"]["timeout_s"] == 8.0
    assert roles["validator"]["requested"] == "openai/gpt-4o-mini"
    assert all(f["served"] == "local/qwen2.5:3b" for f in entry["fallbacks"])


def test_no_fallback_logs_an_empty_list():
    entry = log_and_read(run(SELECTED))
    assert entry["fallbacks"] == []


def test_a_card_logs_no_fallback():
    r = oc._query_with_rag_internal("need to make push dose epi", _JtsHit())
    assert r["fallbacks"] == [] and r["fallback_from"] is None
    assert FakeOpenAI.instances == []


def test_the_http_response_declares_and_passes_fallback_from():
    main = ast.parse((pathlib.Path(oc.__file__).parent / "main.py").read_text())
    cls = next(n for n in main.body if isinstance(n, ast.ClassDef) and n.name == "QueryResponse")
    assert "fallback_from" in {s.target.id for s in cls.body if isinstance(s, ast.AnnAssign)}
    call = next(n for n in ast.walk(main) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "QueryResponse")
    assert "fallback_from" in {k.arg for k in call.keywords}
