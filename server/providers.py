"""
EdgeCDSS — LLM provider registry and dispatch.

One `chat()` call site for the whole clinical pipeline, so the generator and the
validator do not each grow their own idea of what a model call looks like.

Why this module exists
──────────────────────
Two model strings were hard-coded inside openai_client (`model="gpt-4o-mini"` at
the generator and again at the validator). Comparing models meant editing the
clinical core, which is the one file in this repo where an unrelated edit is
most expensive. The model is now config (providers.json) and the transport is
one adapter table.

Import discipline, same as tts.py and openai_client
───────────────────────────────────────────────────
This module must import with no API key, no network, and neither SDK installed.
The offline suite runs on the system interpreter, which has neither `openai` nor
`anthropic`; both are imported lazily inside their adapters. A provider whose
SDK or key is absent is simply absent from the menu — it can never be the reason
the server fails to start.

Adapters
────────
`openai_compat` speaks the OpenAI chat-completions wire format. OpenAI, Ollama,
llama.cpp and vLLM all answer it, so a future on-device model is a providers.json
entry with a base_url and no new code — which is the whole point of the split.

`anthropic` uses the native Anthropic SDK rather than a compatibility shim. The
two wire formats genuinely differ where it matters here: Claude takes `system`
as a top-level parameter rather than a message, and current Claude models reject
`temperature` outright. Those differences are handled once, here, in front of
the ModelSpec flags that describe them.
"""

import json
import os
import pathlib
import threading
import time
from dataclasses import dataclass
from typing import Optional

_CONFIG_PATH = pathlib.Path(__file__).parent / "providers.json"

# Used when providers.json is missing or unparseable. A config typo must degrade
# to a working server with the shipped defaults, loudly — never to a box that
# will not boot. Same rule as _env_number in openai_client.
_BUILTIN_CONFIG = {
    "default_model": "gpt-4o-mini",
    "validator_model": "gpt-4o-mini",
    "providers": {
        "openai": {"label": "OpenAI", "adapter": "openai_compat",
                   "key_env": "OPENAI_API_KEY", "key_prefix": "sk-",
                   "base_url": None, "base_url_env": "CDSS_OPENAI_BASE_URL"},
        "anthropic": {"label": "Anthropic", "adapter": "anthropic",
                      "key_env": "ANTHROPIC_API_KEY", "key_prefix": "sk-ant-",
                      "base_url": None, "base_url_env": "CDSS_ANTHROPIC_BASE_URL"},
    },
    "models": [
        {"id": "gpt-4o-mini", "provider": "openai", "label": "GPT-4o mini",
         "supports_temperature": True, "effort": None, "reserve_tokens": 0},
    ],
}


class ProviderUnavailable(Exception):
    """A model was requested that cannot be called, with the operator-readable why.

    Mirrors tts.VoiceUnavailable: the caller gets a specific reason, not a
    generic failure. The clinical pipeline turns this into a system error the
    medic can act on, never into a silently different answer.
    """


@dataclass(frozen=True)
class ModelSpec:
    id: str
    provider: str
    label: str
    supports_temperature: bool = True
    effort: Optional[str] = None
    reserve_tokens: int = 0


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  {_CONFIG_PATH.name} not found — using built-in provider defaults.")
        return _BUILTIN_CONFIG
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  {_CONFIG_PATH.name} is unreadable ({e}) — using built-in provider defaults.")
        return _BUILTIN_CONFIG

    if not raw.get("providers") or not raw.get("models"):
        print(f"⚠️  {_CONFIG_PATH.name} has no providers/models — using built-in defaults.")
        return _BUILTIN_CONFIG
    return raw


_CONFIG = _load_config()
PROVIDERS = {k: v for k, v in _CONFIG["providers"].items() if not k.startswith("_")}

MODELS = {}
for _m in _CONFIG["models"]:
    if _m.get("provider") not in PROVIDERS:
        print(f"⚠️  model {_m.get('id')!r} names unknown provider "
              f"{_m.get('provider')!r} — skipped.")
        continue
    MODELS[_m["id"]] = ModelSpec(
        id=_m["id"],
        provider=_m["provider"],
        label=_m.get("label", _m["id"]),
        supports_temperature=bool(_m.get("supports_temperature", True)),
        effort=_m.get("effort"),
        reserve_tokens=int(_m.get("reserve_tokens") or 0),
    )

DEFAULT_MODEL = _CONFIG.get("default_model") or next(iter(MODELS), "")
VALIDATOR_MODEL = _CONFIG.get("validator_model") or DEFAULT_MODEL


def default_model() -> str:
    """The model used when the client asks for none. Env override for A/B runs."""
    requested = (os.getenv("CDSS_DEFAULT_MODEL") or "").strip()
    return requested if requested in MODELS else DEFAULT_MODEL


def validator_model() -> str:
    """The safety validator's model.

    Deliberately NOT the model the client dropdown selects. The validator is the
    control in every cross-model comparison: if choosing a generator also swapped
    the validator, a difference in blocked-response rate could not be attributed
    to either. Change it here (providers.json 'validator_model') when that is the
    thing being measured.
    """
    requested = (os.getenv("CDSS_VALIDATOR_MODEL") or "").strip()
    return requested if requested in MODELS else VALIDATOR_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION AND AUTH DIAGNOSIS
# ─────────────────────────────────────────────────────────────────────────────

def _api_key(provider_id: str) -> str:
    provider = PROVIDERS.get(provider_id) or {}
    return (os.getenv(provider.get("key_env", "")) or "").strip()


def _base_url(provider_id: str) -> Optional[str]:
    provider = PROVIDERS.get(provider_id) or {}
    env_name = provider.get("base_url_env")
    override = (os.getenv(env_name) or "").strip() if env_name else ""
    return override or provider.get("base_url") or None


def config_problem(provider_id: str) -> Optional[str]:
    """Why this provider cannot work, decided before any network call.

    Conservative in the same way tts.config_problem is: it rejects only values
    that CANNOT be a key. A well-formed but revoked or out-of-quota key still has
    to fail upstream, which is what auth_problem() is for.

    Never includes the key itself — only its declared env var name.
    """
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        return f"unknown provider {provider_id!r}"

    key_env = provider.get("key_env", "")
    key = _api_key(provider_id)
    if not key:
        # A self-hosted endpoint is legitimately keyless. Everything else needs one.
        if _base_url(provider_id):
            return None
        return f"{provider.get('label', provider_id)} is not configured ({key_env} is unset)"

    prefix = provider.get("key_prefix")
    if prefix and not key.startswith(prefix):
        return (f"{key_env} does not look like a {provider.get('label', provider_id)} "
                f"key — those start with '{prefix}'. Check that the right provider's "
                f"key is in the right variable.")
    return None


# Auth checks cost a network round trip, and /status is polled once a minute by
# every open client. Cache the verdict; a key that starts working is picked up
# within the TTL, and _reset_status_cache() exists for the tests.
_STATUS_TTL_S = 300.0
_status_cache: dict = {}
_status_lock = threading.Lock()


def _reset_status_cache():
    with _status_lock:
        _status_cache.clear()


def _auth_problem(provider_id: str) -> Optional[str]:
    """Ask the provider whether the key actually works. None when it does.

    A real authenticated call, not key presence: the failure this is here to
    catch is a well-formed key that is revoked, out of quota, or from the wrong
    account — exactly the class that key-presence checks report as healthy. Uses
    the models listing, the cheapest authenticated endpoint both providers offer.
    """
    adapter = (PROVIDERS.get(provider_id) or {}).get("adapter")
    try:
        if adapter == "anthropic":
            client = _anthropic_client(provider_id)
            client.with_options(timeout=10.0, max_retries=0).models.list(limit=1)
        else:
            client = _openai_client(provider_id)
            client.with_options(timeout=10.0, max_retries=0).models.list()
        return None
    except ProviderUnavailable as e:
        return str(e)
    except Exception as e:
        # Message text only. Provider SDK errors carry the request body, never
        # the key, but the type-and-message form keeps that from ever changing.
        return f"{type(e).__name__}: {str(e)[:200]}"


def provider_status(force: bool = False) -> dict:
    """Per-provider {available, detail} for /status.

    `detail` is empty when the provider is usable and names the specific problem
    when it is not — the voice_detail pattern from tts.py, for the same reason:
    a dead menu entry with no explanation cost this project weeks once already.
    """
    out = {}
    now = time.monotonic()
    for provider_id, provider in PROVIDERS.items():
        with _status_lock:
            cached = _status_cache.get(provider_id)
            fresh = cached and not force and (now - cached[0]) < _STATUS_TTL_S
        if fresh:
            detail = cached[1]
        else:
            detail = config_problem(provider_id)
            if detail is None:
                detail = _auth_problem(provider_id)
            with _status_lock:
                _status_cache[provider_id] = (now, detail)
        out[provider_id] = {
            "label": provider.get("label", provider_id),
            "available": detail is None,
            "detail": detail or "",
        }
    return out


def available_models(force: bool = False) -> list:
    """Menu contents: every model whose provider authenticates, in config order.

    A provider with no key or a dead key contributes nothing here, so an
    unusable model can never be selected in the first place.
    """
    status = provider_status(force=force)
    return [
        {"id": spec.id, "label": spec.label,
         "provider": spec.provider,
         "provider_label": status.get(spec.provider, {}).get("label", spec.provider)}
        for spec in MODELS.values()
        if status.get(spec.provider, {}).get("available")
    ]


def resolve_model(requested: Optional[str]) -> str:
    """The model to actually use for a request.

    An unknown or unconfigured model falls back to the default rather than
    failing the query: the medic asked a clinical question, not for a particular
    model, and the answer is labelled with what actually served it.
    """
    if requested and requested in MODELS:
        return requested
    return default_model()


# ─────────────────────────────────────────────────────────────────────────────
# ADAPTERS
# ─────────────────────────────────────────────────────────────────────────────

_clients: dict = {}
_client_lock = threading.Lock()


def _openai_client(provider_id: str):
    with _client_lock:
        if provider_id in _clients:
            return _clients[provider_id]
    try:
        from openai import OpenAI
    except ImportError:
        raise ProviderUnavailable(
            "the openai package is not installed — see requirements-server.txt")
    problem = config_problem(provider_id)
    if problem:
        raise ProviderUnavailable(problem)
    kwargs = {"api_key": _api_key(provider_id) or "not-required"}
    base_url = _base_url(provider_id)
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    with _client_lock:
        _clients[provider_id] = client
    return client


def _anthropic_client(provider_id: str):
    with _client_lock:
        if provider_id in _clients:
            return _clients[provider_id]
    try:
        import anthropic
    except ImportError:
        raise ProviderUnavailable(
            "the anthropic package is not installed — see requirements-server.txt")
    problem = config_problem(provider_id)
    if problem:
        raise ProviderUnavailable(problem)
    kwargs = {"api_key": _api_key(provider_id)}
    base_url = _base_url(provider_id)
    if base_url:
        kwargs["base_url"] = base_url
    client = anthropic.Anthropic(**kwargs)
    with _client_lock:
        _clients[provider_id] = client
    return client


def _reset_clients():
    """Drop cached clients so a changed key or base_url is picked up. Tests only."""
    with _client_lock:
        _clients.clear()


def _chat_openai_compat(spec: ModelSpec, system: str, messages: list,
                        temperature: float, max_tokens: int) -> str:
    client = _openai_client(spec.provider)
    wire = ([{"role": "system", "content": system}] if system else []) + list(messages)
    kwargs = {"model": spec.id, "messages": wire,
              "max_tokens": max_tokens + spec.reserve_tokens}
    if spec.supports_temperature:
        kwargs["temperature"] = temperature
    result = client.chat.completions.create(**kwargs)
    return (result.choices[0].message.content or "").strip()


def _chat_anthropic(spec: ModelSpec, system: str, messages: list,
                    temperature: float, max_tokens: int) -> str:
    client = _anthropic_client(spec.provider)
    kwargs = {"model": spec.id, "messages": list(messages),
              "max_tokens": max_tokens + spec.reserve_tokens}
    if system:
        kwargs["system"] = system
    if spec.supports_temperature:
        kwargs["temperature"] = temperature
    if spec.effort:
        kwargs["output_config"] = {"effort": spec.effort}
    result = client.messages.create(**kwargs)
    # content is a list of blocks — thinking blocks come first on models that
    # think, and only text blocks carry the answer.
    return "".join(b.text for b in result.content if getattr(b, "type", "") == "text").strip()


_ADAPTERS = {
    "openai_compat": _chat_openai_compat,
    "anthropic": _chat_anthropic,
}


def chat(system: str, messages: list, *, model: str,
         temperature: float = 0.2, max_tokens: int = 700) -> str:
    """One chat completion. `system` is separate from `messages` on purpose.

    Claude takes the system prompt as a top-level parameter and the OpenAI wire
    format takes it as messages[0]; keeping them separate at this boundary means
    neither call site has to know which. `messages` carries user/assistant turns
    only.

    `temperature` is a request, not a guarantee: models that reject sampling
    parameters (Claude Opus 5, Sonnet 5) drop it. See models[].supports_temperature.
    """
    spec = MODELS.get(model)
    if spec is None:
        raise ProviderUnavailable(f"unknown model {model!r}")
    adapter = _ADAPTERS.get(PROVIDERS[spec.provider].get("adapter", "openai_compat"))
    if adapter is None:
        raise ProviderUnavailable(
            f"provider {spec.provider!r} names an unknown adapter")
    return adapter(spec, system, messages, temperature, max_tokens)
