"""
EdgeCDSS — a generated answer cut off at its token limit is flagged.

The generator runs under max_tokens=700. A model that runs out of tokens just
stops, and what the format puts LAST is what goes: DON'T, EVAC IF, TLDR,
SOURCE, the disclaimer. Nothing noticed, so a cut-off answer was served as if
it were whole. Owner decision 2026-09-17: flag it, do not hold it.

Pinned here:
  - each adapter reports a token-limit stop, a normal stop, and silence apart;
  - the pipeline reads the GENERATOR's stop, not the validator's, which runs
    straight after it through the same chat();
  - a cut-off served answer carries the notice, the issue, and a review
    verdict; a hold carries no notice; both log the flag;
  - the notice is a notice: the brief does not read it as the answer.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402
from providers import ModelSpec  # noqa: E402
from test_log_contract import log_and_read  # noqa: E402

MSG = [{"role": "user", "content": "hi"}]


# ── the adapters ─────────────────────────────────────────────────────────────

def _openai(finish):
    class Client:
        # The cloud attempt is bounded with with_options(); both SDKs have it.
        def with_options(self, **kw):
            return self

        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    choice = type("C", (), {"message": type("M", (), {"content": "x"})()})()
                    if finish is not None:
                        choice.finish_reason = finish
                    return type("R", (), {"choices": [choice]})()
    return Client()


def _anthropic(stop):
    class Client:
        def with_options(self, **kw):
            return self

        class messages:
            @staticmethod
            def create(**kw):
                r = type("R", (), {"content": [type("B", (), {"type": "text", "text": "x"})()]})()
                if stop is not None:
                    r.stop_reason = stop
                return r
    return Client()


@pytest.mark.parametrize("finish,expected", [("length", True), ("stop", False), (None, None)])
def test_openai_compat_reports_a_length_stop(monkeypatch, finish, expected):
    monkeypatch.setattr(providers, "_openai_client", lambda p: _openai(finish))
    monkeypatch.setitem(providers.MODELS, "t-oai", ModelSpec(id="t-oai", provider="openai", label="t"))
    providers.chat("s", MSG, model="t-oai")
    assert providers.last_chat_truncated() is expected


@pytest.mark.parametrize("stop,expected", [("max_tokens", True), ("end_turn", False), (None, None)])
def test_anthropic_reports_a_max_tokens_stop(monkeypatch, stop, expected):
    monkeypatch.setattr(providers, "_anthropic_client", lambda p: _anthropic(stop))
    monkeypatch.setitem(providers.MODELS, "t-cl", ModelSpec(id="t-cl", provider="anthropic", label="t"))
    providers.chat("s", MSG, model="t-cl")
    assert providers.last_chat_truncated() is expected


def test_a_failed_call_does_not_inherit_the_last_ones_stop(monkeypatch):
    monkeypatch.setattr(providers, "_openai_client", lambda p: _openai("length"))
    monkeypatch.setitem(providers.MODELS, "t-oai", ModelSpec(id="t-oai", provider="openai", label="t"))
    providers.chat("s", MSG, model="t-oai")
    assert providers.last_chat_truncated() is True
    with pytest.raises(providers.ProviderUnavailable):
        providers.chat("s", MSG, model="no-such-model")
    assert providers.last_chat_truncated() is None


# ── the pipeline ─────────────────────────────────────────────────────────────

CUT_OFF = """**DO THIS**
1. Needle decompression, 2nd ICS MCL.
2. Reassess breathing.

**WATCH**
- Recurrence of"""


class JtsHit:
    def query(self, *a, **k):
        return {"documents": [["tension pneumothorax protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]],
                "distances": [[0.2]]}


def _run(monkeypatch, generator_truncated, verdict="SAFE"):
    """Real validate_response, stubbed transport. The validator reports a clean
    stop AFTER the generator's cut, which is the overwrite this must survive."""
    def fake_chat(system, messages, **kw):
        if "Clinical Safety Validator" in (system or ""):
            providers._TRUNCATED.set(False)
            issues = '[]' if verdict == "SAFE" else '["Test issue that blocks."]'
            return '{"result":"%s","issues":%s,"rationale":"ok"}' % (verdict, issues)
        providers._TRUNCATED.set(generator_truncated)
        return CUT_OFF

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    return oc._query_with_rag_internal("tension pneumothorax, trachea deviated, what now",
                                       JtsHit())


def test_a_cut_off_answer_is_served_flagged(monkeypatch):
    r = _run(monkeypatch, True)
    assert r["source_mode"] == "JTS_GROUNDED", "the test no longer reaches the generator"
    assert r["generation_truncated"] is True, "the validator's clean stop overwrote the generator's"
    assert r["response"].startswith(oc.TRUNCATED_NOTICE)
    assert "Needle decompression" in r["response"], "flagged, not held"
    assert oc.TRUNCATED_ISSUE in r["validator_issues"]
    assert r["validator_result"] == "NEEDS_HUMAN_REVIEW"


def test_the_notice_is_not_the_brief(monkeypatch):
    r = _run(monkeypatch, True)
    assert "cut off" not in r["brief"]
    assert r["brief"].startswith("Needle decompression")


def test_a_whole_answer_is_untouched(monkeypatch):
    r = _run(monkeypatch, False)
    assert r["generation_truncated"] is False
    assert oc.TRUNCATED_NOTICE not in r["response"]
    assert oc.TRUNCATED_ISSUE not in r["validator_issues"]
    assert r["validator_result"] == "SAFE"


def test_a_hold_is_not_flagged_but_the_cut_is_logged(monkeypatch):
    r = _run(monkeypatch, True, verdict="UNSAFE")
    assert r["validator_result"] == "UNSAFE"
    assert brief.HOLD_OPENER in r["response"]
    assert oc.TRUNCATED_NOTICE not in r["response"]
    assert r["generation_truncated"] is True


def test_the_flag_is_logged(monkeypatch):
    r = _run(monkeypatch, True)
    entry = log_and_read(r)
    assert entry["generation_truncated"] is True
    assert entry["log_schema"] >= 11


def test_a_card_logs_null_not_false():
    """No model wrote a deterministic card, so it was neither cut off nor whole."""
    r = oc._query_with_rag_internal("need to make push dose epi", JtsHit())
    assert r["source_mode"] == "FIXED_PREP"
    assert log_and_read(r)["generation_truncated"] is None
