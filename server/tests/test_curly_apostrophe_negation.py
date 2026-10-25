"""A refusal typed with a curly apostrophe is a refusal.

Found in A39's replay (#182): live 2026-10-25 row 34, "I don’t want ketamine,
I need magnesium", typed on a phone (U+2019). negated_drugs read "don’t" as
no negation, so the pending-question rule (#181 fix 1) kept ketamine in
scope; with no history, main asked "IV or IM? Do you have access?" for the
refused ketamine. Owner, 2026-10-25: its own small PR.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402


@pytest.mark.parametrize("apostrophe", ["'", "’", "‘", "ʼ"])
def test_dont_with_any_apostrophe_refuses_the_drug(apostrophe):
    q = f"I don{apostrophe}t want ketamine, I need magnesium"
    assert oc.negated_drugs(q) == {"ketamine"}
    _prior, request, _answered = oc.scope_request(q, "", "")
    assert "ketamine" not in request


def test_the_scoped_text_keeps_its_offsets():
    q = "I don’t want ketamine, give fentanyl"
    _prior, request, _ = oc.scope_request(q, "", "")
    assert len(request) == len(q) and "fentanyl" in request and "’" in request


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def test_a_curly_refusal_is_not_asked_about_the_refused_drug(monkeypatch):
    """Before: "IV or IM? Do you have access?" for the refused ketamine."""
    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return '{"result": "SAFE", "issues": [], "rationale": "ok"}'
        return "Give fentanyl 50 mcg IV."
    monkeypatch.setattr(providers, "chat", chat)
    r = oc._query_with_rag_internal("I don’t want ketamine, fentanyl for pain, 80 kg adult",
                                    _JtsHit(), conversation_history=[])
    assert not r["response"].startswith("IV or IM?"), r["response"]
    assert "Which ketamine" not in r["response"]
