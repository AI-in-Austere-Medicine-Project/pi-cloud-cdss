"""
EdgeCDSS — the on-device model: provider switch, provenance.

CDSS_LLM_PROVIDER=local sends the generator and the validator to an
OpenAI-compatible endpoint on the device (Ollama, qwen2.5:3b) through the same
openai SDK with a base_url — no new dependency. openai (the default) must be
the request it always was.

The offline suite runs on the system interpreter, which has no openai package,
so these tests install a stand-in `openai` module that records what the real SDK
would have been asked to do: the client's constructor arguments and every
chat.completions.create() call.

    cd server && ./run_unit_tests.sh
"""
import os
import pathlib
import sys
import types

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402
from test_log_contract import log_and_read  # noqa: E402

KEY = "sk-test-local-llm-0000"
VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
GENERATED = "**TLDR**\n- stub answer\n\n**SOURCE**: stub"


class _Choice:
    def __init__(self, text):
        self.message = types.SimpleNamespace(content=text)
        self.finish_reason = "stop"


class FakeOpenAI:
    """Records what the real client would have been constructed with and sent."""
    instances = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls = []
        self.options = []
        FakeOpenAI.instances.append(self)
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))
        self.models = types.SimpleNamespace(list=lambda **k: [])

    def with_options(self, **kwargs):
        self.options.append(kwargs)
        return self

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        first = kwargs["messages"][0]["content"] if kwargs["messages"] else ""
        text = VALIDATOR_OK if first == oc.VALIDATOR_PROMPT else GENERATED
        return types.SimpleNamespace(choices=[_Choice(text)])


@pytest.fixture(autouse=True)
def fake_sdk(monkeypatch):
    FakeOpenAI.instances = []
    monkeypatch.setitem(sys.modules, "openai",
                        types.SimpleNamespace(OpenAI=FakeOpenAI))
    for name in ("CDSS_LLM_PROVIDER", "CDSS_LLM_BASE_URL", "CDSS_LLM_MODEL",
                 "CDSS_LOCAL_BASE_URL", "CDSS_LOCAL_API_KEY",
                 "CDSS_DEFAULT_MODEL", "CDSS_VALIDATOR_MODEL", "CDSS_OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    providers._reset_clients()
    providers._reset_status_cache()
    yield
    providers._reset_clients()
    providers._reset_status_cache()


def _one_call(model):
    providers.chat("SYSTEM", [{"role": "user", "content": "Q"}],
                   model=model, temperature=0.2, max_tokens=700)
    (client,) = FakeOpenAI.instances
    (call,) = client.calls
    return client, call


# ── provider=local ───────────────────────────────────────────────────────────

def test_local_constructs_a_client_on_the_local_endpoint_and_model(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    assert providers.default_model() == "qwen2.5:3b"
    assert providers.validator_model() == "qwen2.5:3b", \
        "offline, a cloud validator would fail every query closed"
    client, call = _one_call(providers.default_model())
    assert client.init_kwargs == {"api_key": "not-required",
                                  "base_url": "http://localhost:11434/v1"}
    assert call["model"] == "qwen2.5:3b"
    assert providers.last_chat_served() == ("local", "qwen2.5:3b")


def test_local_base_url_and_model_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    monkeypatch.setenv("CDSS_LLM_BASE_URL", "http://127.0.0.1:18080/v1")
    monkeypatch.setenv("CDSS_LLM_MODEL", "llama3.2:3b")
    client, call = _one_call(providers.default_model())
    assert client.init_kwargs["base_url"] == "http://127.0.0.1:18080/v1"
    assert call["model"] == "llama3.2:3b"
    assert oc.model_label("llama3.2:3b") == "local/llama3.2:3b"


def test_local_answers_whatever_model_was_requested(monkeypatch):
    """A cloud model picked from a menu cached before the link dropped."""
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    assert providers.resolve_model("gpt-4o") == "qwen2.5:3b"
    assert providers.resolve_model(None) == "qwen2.5:3b"


def test_an_unknown_provider_is_the_default_not_a_crash(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "ollama")
    assert providers.llm_provider() == "openai"
    assert providers.default_model() == providers.DEFAULT_MODEL


# ── provider=openai is the request it always was ─────────────────────────────

@pytest.mark.parametrize("setting", [None, "openai", "OpenAI"])
def test_openai_is_byte_identical_to_today(monkeypatch, setting):
    if setting is not None:
        monkeypatch.setenv("CDSS_LLM_PROVIDER", setting)
    assert providers.default_model() == providers.DEFAULT_MODEL == "gpt-4o-mini"
    assert providers.validator_model() == providers.VALIDATOR_MODEL
    assert providers.resolve_model("gpt-4o") == "gpt-4o"
    client, call = _one_call(providers.default_model())
    # The constructor and the request, exactly as providers.chat built them
    # before the switch existed: no base_url, no extra parameter.
    assert client.init_kwargs == {"api_key": KEY}
    assert call == {"model": "gpt-4o-mini",
                    "messages": [{"role": "system", "content": "SYSTEM"},
                                 {"role": "user", "content": "Q"}],
                    "max_tokens": 700, "temperature": 0.2}
    assert providers.last_chat_served() == ("openai", "gpt-4o-mini")


def test_openai_takes_its_model_from_cdss_llm_model(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_MODEL", "gpt-4o")
    assert providers.default_model() == "gpt-4o"
    assert providers.validator_model() == providers.VALIDATOR_MODEL, \
        "the validator stays the control on the cloud path"


def test_openai_does_not_put_the_local_model_on_the_menu():
    assert providers.config_problem("local") is not None
    assert "qwen2.5:3b" not in providers.MODELS


# ── every response says what answered it ─────────────────────────────────────

class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


GENERATED_QUERY = "how do I manage a tension pneumothorax in the field"


def _generated(monkeypatch):
    r = oc._query_with_rag_internal(GENERATED_QUERY, _JtsHit())
    assert r["source_mode"] == "JTS_GROUNDED", r["source_mode"]
    return r


def test_a_local_answer_is_stamped_local(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    r = _generated(monkeypatch)
    assert r["provider"] == "local" and r["validator_provider"] == "local"
    assert r["model"] == "local/qwen2.5:3b"
    entry = log_and_read(r)
    assert entry["provider"] == "local" and entry["model"] == "local/qwen2.5:3b"
    assert entry["validator_provider"] == "local"


def test_a_cloud_answer_is_stamped_openai(monkeypatch):
    r = _generated(monkeypatch)
    assert r["provider"] == "openai" and r["validator_provider"] == "openai"
    assert r["model"] == "openai/gpt-4o-mini"
    assert log_and_read(r)["provider"] == "openai"


def test_a_card_carries_both_fields_as_null(monkeypatch):
    monkeypatch.setenv("CDSS_LLM_PROVIDER", "local")
    r = oc._query_with_rag_internal("need to make push dose epi", _JtsHit())
    assert r["source_mode"] == "FIXED_PREP"
    assert "model" in r and r["model"] is None
    assert "provider" in r and r["provider"] is None
    assert FakeOpenAI.instances == [], "a card called a model"


def test_the_http_response_declares_and_passes_provider():
    """The pipeline's field is only half of it: /query builds its response from
    an explicit field list, and a field left off it never reaches the portal."""
    import ast
    import pathlib
    main = ast.parse((pathlib.Path(oc.__file__).parent / "main.py").read_text())
    cls = next(n for n in main.body if isinstance(n, ast.ClassDef) and n.name == "QueryResponse")
    assert "provider" in {s.target.id for s in cls.body if isinstance(s, ast.AnnAssign)}
    call = next(n for n in ast.walk(main) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "QueryResponse")
    assert "provider" in {k.arg for k in call.keywords}
