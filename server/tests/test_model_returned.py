"""
EdgeCDSS — D5a: the log records the model the provider says answered.

`model` is the model EdgeCDSS asked for (the id sent in the request). The
provider's reply names its own model, often a dated snapshot of that id
("gpt-4o-mini-2024-07-18"), and until now nothing kept it. D5 builds training
rows from logged answers and must be able to show exactly which model wrote
each one (owner, 2026-09-30).

Pinned here:
  - both adapters read the reply's model; a reply without one reads None;
  - a failed call does not inherit the last call's model;
  - a fallback records what the local endpoint returned;
  - the pipeline keeps the GENERATOR's, not the validator's, which runs straight
    after it through the same chat();
  - the log has `model_returned` beside `model`; null for a deterministic card;
  - it is a log field only, not sent to the client.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
from providers import ModelSpec  # noqa: E402
from test_log_contract import log_and_read  # noqa: E402

MSG = [{"role": "user", "content": "hi"}]


# ── the adapters ─────────────────────────────────────────────────────────────

def _openai(returned, raises=None):
    class Client:
        def with_options(self, **kw):
            return self

        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    if raises is not None:
                        raise raises
                    choice = type("C", (), {"message": type("M", (), {"content": "x"})(),
                                            "finish_reason": "stop"})()
                    r = type("R", (), {"choices": [choice]})()
                    if returned is not None:
                        r.model = returned
                    return r
    return Client()


def _anthropic(returned):
    class Client:
        def with_options(self, **kw):
            return self

        class messages:
            @staticmethod
            def create(**kw):
                r = type("R", (), {"content": [type("B", (), {"type": "text", "text": "x"})()],
                                   "stop_reason": "end_turn"})()
                if returned is not None:
                    r.model = returned
                return r
    return Client()


@pytest.mark.parametrize("returned", ["gpt-4o-mini-2024-07-18", None])
def test_openai_compat_records_the_returned_model(monkeypatch, returned):
    monkeypatch.setattr(providers, "_openai_client", lambda p: _openai(returned))
    monkeypatch.setitem(providers.MODELS, "t-oai", ModelSpec(id="t-oai", provider="openai", label="t"))
    providers.chat("s", MSG, model="t-oai")
    assert providers.last_chat_returned_model() == returned


@pytest.mark.parametrize("returned", ["claude-opus-5-20260801", None])
def test_anthropic_records_the_returned_model(monkeypatch, returned):
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: _anthropic(returned))
    monkeypatch.setitem(providers.MODELS, "t-cl", ModelSpec(id="t-cl", provider="anthropic", label="t"))
    providers.chat("s", MSG, model="t-cl")
    assert providers.last_chat_returned_model() == returned


def test_a_failed_call_does_not_inherit_the_last_ones_model(monkeypatch):
    monkeypatch.setattr(providers, "_openai_client", lambda p: _openai("gpt-4o-mini-2024-07-18"))
    monkeypatch.setitem(providers.MODELS, "t-oai", ModelSpec(id="t-oai", provider="openai", label="t"))
    providers.chat("s", MSG, model="t-oai")
    with pytest.raises(providers.ProviderUnavailable):
        providers.chat("s", MSG, model="no-such-model")
    assert providers.last_chat_returned_model() is None


class APIConnectionError(Exception):
    """Named like the SDK's; is_connectivity_error matches on the name."""


def test_a_fallback_records_what_the_local_endpoint_returned(monkeypatch):
    monkeypatch.setattr(providers, "llm_provider", lambda: "openai")
    monkeypatch.setattr(providers, "_openai_client",
                        lambda p: _openai("never", raises=APIConnectionError("down")))
    monkeypatch.setattr(providers, "_local_client", lambda: _openai("qwen2.5:3b"))
    monkeypatch.setitem(providers.MODELS, "t-oai", ModelSpec(id="t-oai", provider="openai", label="t"))
    providers.chat("s", MSG, model="t-oai")
    assert providers.last_chat_served()[0] == providers.FALLBACK_PROVIDER
    assert providers.last_chat_returned_model() == "qwen2.5:3b"


# ── the pipeline and the log ─────────────────────────────────────────────────

class JtsHit:
    def query(self, *a, **k):
        return {"documents": [["tension pneumothorax protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.2]]}


ANSWER = "**DO THIS**\n1. Needle decompression, 2nd ICS MCL.\n2. Reassess breathing."


def _run(monkeypatch):
    """The validator reports its own model AFTER the generator's, which is the
    overwrite this must survive."""
    def fake_chat(system, messages, **kw):
        if "Clinical Safety Validator" in (system or ""):
            providers._RETURNED.set("validator-snapshot")
            return '{"result":"SAFE","issues":[],"rationale":"ok"}'
        providers._RETURNED.set("gpt-4o-mini-2024-07-18")
        return ANSWER

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    return oc._query_with_rag_internal("how do I manage a tension pneumothorax in the field",
                                       JtsHit())


def test_the_pipeline_keeps_the_generators_returned_model(monkeypatch):
    r = _run(monkeypatch)
    assert r["source_mode"] == "JTS_GROUNDED", "the test no longer reaches the generator"
    assert r["model_returned"] == "gpt-4o-mini-2024-07-18", \
        "the validator's reply overwrote the generator's"


def test_the_log_has_the_returned_model_beside_the_requested_one(monkeypatch):
    r = _run(monkeypatch)
    entry = log_and_read(r)
    assert entry["model_returned"] == "gpt-4o-mini-2024-07-18"
    assert entry["model"] == r["model"] and entry["model"], "the requested model is still logged"


def test_a_card_logs_null():
    """No model wrote a deterministic card, so no provider returned a model."""
    r = oc._query_with_rag_internal("need to make push dose epi", JtsHit())
    assert r["source_mode"] == "FIXED_PREP"
    assert log_and_read(r)["model_returned"] is None


def test_it_is_a_log_field_only():
    import main
    assert "model_returned" not in main.QueryResponse.model_fields
