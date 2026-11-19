"""A clarifying question only when an answer can dose (owner, 2026-11-19).

Owner: "a clarifying question is asked only if at least one of its answers leads to a
signed dose in the active set. Otherwise hold at once, naming what is not signed.
Fixtures: the two EMS calcium rows hold immediately; the PFC calcium question still
asks chloride or gluconate."

The EMS set signs neither calcium salt, so asking "Calcium chloride or calcium
gluconate?" there can only lead to "no signed dose" a turn later (SW3 replay, rows
signed off by the owner 2026-11-19 as no dose served).
"""
import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

dc = oc.drug_contracts
SALTS = ("calcium chloride", "calcium gluconate")
EMS_ROWS = ["calcium dose after 4 units", "calcium dose after the transfusion"]


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


@pytest.fixture
def card_only(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("this row called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


def run(q, history=None):
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=history or [])


def _without(monkeypatch, *drugs):
    live = dc.servable_entries
    monkeypatch.setattr(dc, "servable_entries",
                        lambda *a, **k: {d: es for d, es in live(*a, **k).items() if d not in drugs})


def _names_both_salts_unsigned(text):
    low = text.lower()
    return "no signed" in low and all(s in low for s in SALTS)


@pytest.mark.parametrize("q", EMS_ROWS)
def test_ems_calcium_rows_hold_at_once_naming_what_is_not_signed(q, card_only, monkeypatch):
    monkeypatch.setattr(dc, "SERVED_SET", "EMS")
    assert not any(dc.servable_entries().get(s) for s in SALTS), "EMS signs a calcium salt now"
    r = run(q)
    assert r["response"] != oc.CALCIUM_SALT_ASK
    assert r["validator_result"] == "UNSAFE", r["response"][:300]
    assert _names_both_salts_unsigned(r["response"]), r["response"][:300]


@pytest.mark.parametrize("q", ["calcium after 4 units of blood"] + EMS_ROWS)
def test_pfc_calcium_still_asks_chloride_or_gluconate(q, card_only):
    assert all(dc.servable_entries().get(s) for s in SALTS)
    assert run(q)["response"] == oc.CALCIUM_SALT_ASK


@pytest.mark.parametrize("unsigned", SALTS)
def test_one_signed_salt_is_enough_to_ask(unsigned, card_only, monkeypatch):
    _without(monkeypatch, unsigned)
    assert run("calcium after 4 units of blood")["response"] == oc.CALCIUM_SALT_ASK


def test_no_signed_salt_holds_on_any_set(card_only, monkeypatch):
    _without(monkeypatch, *SALTS)
    r = run("calcium after 4 units of blood")
    assert r["response"] != oc.CALCIUM_SALT_ASK
    assert _names_both_salts_unsigned(r["response"]), r["response"][:300]


def test_the_rule_as_a_function(monkeypatch):
    assert oc.an_answer_can_dose(SALTS)
    _without(monkeypatch, *SALTS)
    assert not oc.an_answer_can_dose(SALTS)
    assert oc.unsigned_answers(SALTS) == list(SALTS)
