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

import contextvars
import json
import os
import re
import pathlib
import threading
import time
from functools import lru_cache
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
        "gemini": {"label": "Google Gemini", "adapter": "openai_compat",
                   "key_env": "GEMINI_API_KEY", "key_prefix": None,
                   "requires_key": True,
                   "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                   "base_url_env": "CDSS_GEMINI_BASE_URL"},
        "xai": {"label": "xAI", "adapter": "openai_compat",
                "key_env": "XAI_API_KEY", "key_prefix": None,
                "requires_key": True,
                "base_url": "https://api.x.ai/v1",
                "base_url_env": "CDSS_XAI_BASE_URL"},
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

_CONFIGURED_MODELS = frozenset(MODELS)
DEFAULT_MODEL = _CONFIG.get("default_model") or next(iter(MODELS), "")
VALIDATOR_MODEL = _CONFIG.get("validator_model") or DEFAULT_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# THE LLM PROVIDER SWITCH — cloud or on-device
#
# CDSS_LLM_PROVIDER   openai (default) | local
# CDSS_LLM_BASE_URL   the local OpenAI-compatible endpoint; default
#                     http://localhost:11434/v1 (Ollama on the Jetson)
# CDSS_LLM_MODEL      the model: default gpt-4o-mini for openai (providers.json's
#                     default_model), qwen2.5:3b for local
#
# `local` sends the generator AND the validator to the on-device model: the
# point is answering with no internet, and a validator left on the cloud would
# fail every query closed. `openai` is the registry exactly as it was — nothing
# here changes a request while these variables are unset. Read live from the
# environment, like CDSS_DEFAULT_MODEL, so a test or an A/B run can flip it.
# ─────────────────────────────────────────────────────────────────────────────
LLM_PROVIDERS = ("openai", "local")
LOCAL_PROVIDER = "local"
LOCAL_DEFAULT_BASE_URL = "http://localhost:11434/v1"
LOCAL_DEFAULT_MODEL = "qwen2.5:3b"


def llm_provider() -> str:
    """"openai" or "local". Anything else is a typo: say so, serve the default."""
    value = (os.getenv("CDSS_LLM_PROVIDER") or "").strip().lower()
    if not value:
        return "openai"
    if value not in LLM_PROVIDERS:
        print(f"⚠️  CDSS_LLM_PROVIDER={value!r} is not one of {LLM_PROVIDERS} — using openai.")
        return "openai"
    return value


def local_base_url() -> str:
    """The on-device endpoint. CDSS_LOCAL_BASE_URL is the older name for it."""
    return ((os.getenv("CDSS_LLM_BASE_URL") or "").strip()
            or (os.getenv("CDSS_LOCAL_BASE_URL") or "").strip()
            or LOCAL_DEFAULT_BASE_URL)


def local_model_spec(model_id: Optional[str] = None) -> ModelSpec:
    """The on-device model, registered on the `local` provider on first use.

    A local model is whatever `ollama pull` fetched, so it is named by the
    environment rather than listed in providers.json. Registering it in MODELS
    is what lets model_label() and resolve_model() treat it like any other.
    """
    mid = (model_id or (os.getenv("CDSS_LLM_MODEL") or "").strip()
           or LOCAL_DEFAULT_MODEL)
    spec = MODELS.get(mid)
    if spec is None or spec.provider != LOCAL_PROVIDER:
        spec = ModelSpec(id=mid, provider=LOCAL_PROVIDER, label=f"{mid} (local)")
        MODELS[mid] = spec
    return spec


# The hybrid fallback. With CDSS_LLM_PROVIDER=openai, a cloud call that cannot
# CONNECT — a timeout, a refused or dropped connection, no route — is retried
# once against the local model, and the answer is stamped "local-fallback". A
# call that connected and was REFUSED (401, 403, 404, 429, 400, 5xx) is not: the
# network is fine and something is misconfigured, and serving the local model
# would hide that until the next outage. Those surface as they always did.
FALLBACK_PROVIDER = "local-fallback"
CLOUD_TIMEOUT_DEFAULT_S = 8.0
# Both SDKs name their transport failures the same way, and APITimeoutError
# subclasses APIConnectionError in both. Matched by name so neither SDK has to
# be importable for the check — the offline suite has neither.
_CONNECTIVITY_ERRORS = frozenset({"APIConnectionError", "APITimeoutError"})


def cloud_timeout_s() -> float:
    """CDSS_LLM_CLOUD_TIMEOUT: seconds before a cloud call counts as unreachable."""
    raw = (os.getenv("CDSS_LLM_CLOUD_TIMEOUT") or "").strip()
    if not raw:
        return CLOUD_TIMEOUT_DEFAULT_S
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    print(f"⚠️  CDSS_LLM_CLOUD_TIMEOUT={raw!r} is not a positive number of seconds "
          f"— using {CLOUD_TIMEOUT_DEFAULT_S:g}.")
    return CLOUD_TIMEOUT_DEFAULT_S


def is_connectivity_error(exc: BaseException) -> bool:
    """A timeout or connection failure — not an error the provider answered with."""
    return any(cls.__name__ in _CONNECTIVITY_ERRORS for cls in type(exc).__mro__)


def fallback_model_id() -> str:
    """The local model a failed cloud call is retried on.

    CDSS_LLM_MODEL names the CLOUD model while the provider is openai, so the
    fallback has its own override.
    """
    return (os.getenv("CDSS_LLM_FALLBACK_MODEL") or "").strip() or LOCAL_DEFAULT_MODEL


def default_model() -> str:
    """The model used when the client asks for none. Env override for A/B runs."""
    if llm_provider() == "local":
        return local_model_spec().id
    requested = (os.getenv("CDSS_LLM_MODEL") or "").strip()
    if requested in MODELS:
        return requested
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
    if llm_provider() == "local":
        return local_model_spec().id
    requested = (os.getenv("CDSS_VALIDATOR_MODEL") or "").strip()
    return requested if requested in MODELS else VALIDATOR_MODEL


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION AND AUTH DIAGNOSIS
# ─────────────────────────────────────────────────────────────────────────────

def _api_key(provider_id: str) -> str:
    provider = PROVIDERS.get(provider_id) or {}
    return (os.getenv(provider.get("key_env", "")) or "").strip()


def _base_url(provider_id: str) -> Optional[str]:
    if provider_id == LOCAL_PROVIDER and llm_provider() == "local":
        return local_base_url()
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
        # A self-hosted endpoint is legitimately keyless, and "has a base_url"
        # was the proxy for self-hosted. That proxy breaks for a hosted
        # provider reached through an OpenAI-compatibility endpoint: Gemini
        # ships a PUBLIC base_url in providers.json and still requires a key,
        # so without `requires_key` it looked configured, and /status made a
        # real network round trip for it every five minutes — on a device that
        # may have no network at all.
        if _base_url(provider_id) and not provider.get("requires_key"):
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


# Providers quote the offending key back in their own error bodies, partially
# masked ("sk-clear*****-xyz"). Their masking is not ours to rely on, and
# /status is unauthenticated — the same endpoint the web client polls once a
# minute without a token.
#
# This was a SHAPE denylist matching /\bsk-.../ and nothing else, which covered
# OpenAI and Anthropic and silently missed every other credential this process
# holds: xAI (xai-), Gemini (AQ.), and ElevenLabs — whose keys begin "sk_" with
# an underscore, so it looked covered and was not. A denylist of shapes fails
# closed only for the shapes someone remembered.
#
# It is now FIELD-based. The field list is read from providers.json's own
# key_env declarations, so a provider added there is redacted from the moment
# it is added rather than the moment someone remembers to add a pattern here.
_EXTRA_SECRET_ENV = ("ELEVENLABS_API_KEY", "CDSS_ACCESS_TOKEN")

# Below this a value is not a credential — it is "", "0" or a test stub — and
# blanking it would eat ordinary words out of a diagnostic.
_MIN_SECRET_LEN = 8

# Shape backstop, still needed: the value pass cannot match what this process
# does not hold — a key quoted back partially masked, or one rotated upstream
# but not here.
_KEY_SHAPED_RE = re.compile(
    r'\b(?:sk[-_][A-Za-z0-9_*\-]{4,}'
    r'|xai-[A-Za-z0-9_*\-]{4,}'
    r'|AIza[A-Za-z0-9_*\-]{10,}'
    r'|AQ\.[A-Za-z0-9_*\-]{10,})', re.IGNORECASE)

# Provider error bodies quote the console URL of the account that failed — the
# xAI team URL is one of these. An account identifier is not something a
# diagnostic needs to carry onto an unauthenticated endpoint.
_URL_RE = re.compile(r'https?://\S+')


def _secret_values() -> list:
    """Every secret this process holds, by field, read live from the environment.

    Live rather than cached at import: a key rotated into the environment and
    the process reloaded must not leave the old value unredacted, and provider
    status is cached for five minutes anyway so the cost is nothing.
    """
    names = [(p.get("key_env") or "") for p in PROVIDERS.values()]
    names += list(_EXTRA_SECRET_ENV)
    values = {v for v in ((os.getenv(n) or "").strip() if n else "" for n in names)
              if len(v) >= _MIN_SECRET_LEN}
    # Longest first: where one secret contains another as a prefix, replacing
    # the shorter first would leave the tail of the longer one behind.
    return sorted(values, key=len, reverse=True)


def _redact(text: str) -> str:
    """Strip anything secret from a string bound for /status, a log or a caller."""
    out = text or ""
    for secret in _secret_values():
        out = out.replace(secret, "[redacted]")
    out = _KEY_SHAPED_RE.sub("[redacted]", out)
    return _URL_RE.sub("[url removed]", out)


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
            client = (_local_client() if provider_id == LOCAL_PROVIDER
                      else _openai_client(provider_id))
            client.with_options(timeout=10.0, max_retries=0).models.list()
        return None
    except ProviderUnavailable as e:
        return _redact(str(e))
    except Exception as e:
        # Type and message only, with key-shaped substrings removed. Provider
        # errors quote the key back partially masked; that masking is theirs,
        # not ours, and this reaches an unauthenticated endpoint.
        return _redact(f"{type(e).__name__}: {str(e)[:200]}")


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

    With CDSS_LLM_PROVIDER=local the on-device model answers whatever was
    requested: the operator chose local, and a cloud model picked from a menu
    cached before the link dropped would fail every query.
    """
    if llm_provider() == "local":
        return local_model_spec().id
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


def _local_client():
    """The on-device endpoint's client. Keyless; no config check to fail.

    Separate from _openai_client("local") because it must exist whether or not
    the `local` provider is configured for the menu — the hybrid fallback
    reaches it while CDSS_LLM_PROVIDER is openai.
    """
    url = local_base_url()
    key = ("__local__", url)
    with _client_lock:
        if key in _clients:
            return _clients[key]
    try:
        from openai import OpenAI
    except ImportError:
        raise ProviderUnavailable(
            "the openai package is not installed — see requirements-server.txt")
    client = OpenAI(api_key=_api_key(LOCAL_PROVIDER) or "not-required", base_url=url)
    with _client_lock:
        _clients[key] = client
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


# Whether the most recent chat() in this context stopped at its token limit:
# True, False, or None when the provider did not say or no call has been made.
# A context variable, not a return value, so chat() still returns the text and
# every caller and stand-in that treats it as a string keeps working — the eval
# harness wraps chat() and passes its result straight through. A ContextVar
# rather than a global so two requests in two threads cannot read each other's.
_TRUNCATED = contextvars.ContextVar("edgecdss_chat_truncated", default=None)


# Which provider and model actually served the last chat() in this context —
# (provider, model_id), or None. Same ContextVar reasoning as _TRUNCATED: chat()
# keeps returning plain text, and a caller that needs the provenance reads it
# straight after the call.
_SERVED = contextvars.ContextVar("edgecdss_chat_served", default=None)


def last_chat_served() -> Optional[tuple]:
    """(provider, model_id) of the last chat() here, or None if none completed.

    provider is the registry id ("openai", "anthropic", "local"), or
    "local-fallback" when a cloud call could not connect and the local model
    answered instead. Read it immediately after the call it describes; the next
    chat() overwrites it.
    """
    return _SERVED.get()


def reset_served() -> None:
    """Forget which provider served the last call, before one that may not run."""
    _SERVED.set(None)


def last_chat_truncated() -> Optional[bool]:
    """Did the last chat() here stop because it ran out of tokens?

    A truncated answer is served silently otherwise: the text simply ends, and
    whatever the format put last — DON'T, EVAC IF, TLDR, SOURCE, the
    disclaimer — is not there. Read it immediately after the call it describes;
    the next chat() overwrites it.
    """
    return _TRUNCATED.get()


def reset_truncation() -> None:
    """Forget the last call. For callers that read last_chat_truncated() after
    a chat() that may be a stand-in, so a real call's answer cannot leak into
    a later one that never reported."""
    _TRUNCATED.set(None)


def _reset_clients():
    """Drop cached clients so a changed key or base_url is picked up. Tests only."""
    with _client_lock:
        _clients.clear()
    # A local model registered by an earlier test's CDSS_LLM_MODEL.
    for mid in [m for m, spec in MODELS.items()
                if spec.provider == LOCAL_PROVIDER and m not in _CONFIGURED_MODELS]:
        del MODELS[mid]


def _chat_openai_compat(spec: ModelSpec, system: str, messages: list,
                        temperature: float, max_tokens: int,
                        timeout: Optional[float] = None) -> str:
    client = (_local_client() if spec.provider == LOCAL_PROVIDER
              else _openai_client(spec.provider))
    if timeout is not None:
        client = client.with_options(timeout=timeout, max_retries=0)
    wire = ([{"role": "system", "content": system}] if system else []) + list(messages)
    kwargs = {"model": spec.id, "messages": wire,
              "max_tokens": max_tokens + spec.reserve_tokens}
    if spec.supports_temperature:
        kwargs["temperature"] = temperature
    result = client.chat.completions.create(**kwargs)
    choice = result.choices[0]
    finish = getattr(choice, "finish_reason", None)
    _TRUNCATED.set(None if finish is None else finish == "length")
    return (choice.message.content or "").strip()


@lru_cache(maxsize=1)
def _anthropic_accepts_temperature() -> bool:
    """Whether the INSTALLED anthropic SDK still takes a temperature.

    Two independent things decide whether temperature is sent, and conflating
    them is what broke the menu: models[].supports_temperature says whether the
    MODEL accepts it, and this says whether the SDK exposes it at all.

    anthropic 1.0.0 removed `temperature` from Messages.create and the method
    takes no **kwargs, so passing it raises TypeError before any request is
    made. Measured on the deployed venv 2026-08-22: claude-haiku-4-5, whose
    config says supports_temperature: true, failed every call with
    "Messages.create() got an unexpected keyword argument 'temperature'" while
    claude-sonnet-5 worked — because its config already said false.

    Inspected rather than version-compared: a version table is another thing to
    keep in step with reality, and the signature IS the reality. Fails toward
    dropping the parameter, which costs default sampling; the other direction
    costs every query.
    """
    try:
        import inspect
        import anthropic
        sig = inspect.signature(anthropic.Anthropic(api_key="probe").messages.create)
        if any(prm.kind is inspect.Parameter.VAR_KEYWORD
               for prm in sig.parameters.values()):
            return True
        return "temperature" in sig.parameters
    except Exception:
        return False


def _chat_anthropic(spec: ModelSpec, system: str, messages: list,
                    temperature: float, max_tokens: int,
                    timeout: Optional[float] = None) -> str:
    client = _anthropic_client(spec.provider)
    if timeout is not None:
        client = client.with_options(timeout=timeout, max_retries=0)
    kwargs = {"model": spec.id, "messages": list(messages),
              "max_tokens": max_tokens + spec.reserve_tokens}
    if system:
        kwargs["system"] = system
    # Both must agree: the model accepts it AND the installed SDK exposes it.
    if spec.supports_temperature and _anthropic_accepts_temperature():
        kwargs["temperature"] = temperature
    if spec.effort:
        kwargs["output_config"] = {"effort": spec.effort}
    result = client.messages.create(**kwargs)
    stop = getattr(result, "stop_reason", None)
    _TRUNCATED.set(None if stop is None else stop == "max_tokens")
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
    _TRUNCATED.set(None)
    _SERVED.set(None)
    spec = MODELS.get(model)
    if spec is None:
        raise ProviderUnavailable(f"unknown model {model!r}")
    adapter = _ADAPTERS.get(PROVIDERS[spec.provider].get("adapter", "openai_compat"))
    if adapter is None:
        raise ProviderUnavailable(
            f"provider {spec.provider!r} names an unknown adapter")
    if spec.provider == LOCAL_PROVIDER or llm_provider() != "openai":
        text = adapter(spec, system, messages, temperature, max_tokens)
        _SERVED.set((spec.provider, spec.id))
        return text

    # A cloud model: bounded, and retried on the local model if unreachable.
    # max_retries=0 because the SDK's own retries would triple the wait before
    # the medic gets any answer at all.
    try:
        text = adapter(spec, system, messages, temperature, max_tokens,
                       timeout=cloud_timeout_s())
    except Exception as cloud_error:
        if not is_connectivity_error(cloud_error):
            raise
        local = local_model_spec(fallback_model_id())
        print(f"🛰️  {spec.provider}/{spec.id} unreachable "
              f"({type(cloud_error).__name__}) — retrying on local/{local.id}")
        _TRUNCATED.set(None)
        try:
            text = _chat_openai_compat(local, system, messages, temperature, max_tokens)
        except Exception as local_error:
            raise ProviderUnavailable(
                f"{spec.provider} unreachable ({type(cloud_error).__name__}) and the "
                f"local fallback failed ({type(local_error).__name__}: "
                f"{_redact(str(local_error))[:160]})") from local_error
        _SERVED.set((FALLBACK_PROVIDER, local.id))
        return text
    _SERVED.set((spec.provider, spec.id))
    return text
