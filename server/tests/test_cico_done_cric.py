"""
EdgeCDSS — A10: the CICO card must not fire on a completed surgical airway.

Found in #86. is_cico_query() fired on any "cric" or "surgical airway"
substring, with no state. Live on the #86 branch, "80kg male, cric'd, what
do I give after RSI" was served "Declare CICO ... Perform surgical airway /
cricothyrotomy now" for a patient whose cric was already in. Same class as A8:
a substring match with no state.

A completed surgical airway is not a CICO request. A failed one still is.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

CICO_MARK = "Declare CICO"


class _Retrieval:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (
        '{"result":"SAFE","issues":[],"rationale":"stub"}'
        if "Clinical Safety Validator" in (a[0] if a else "") else "STUB"))


def run(q):
    return oc._query_with_rag_internal(q, _Retrieval(), conversation_history=[])


DONE = [
    # the #86 live query, verbatim
    "80kg male, cric'd, what do I give after RSI",
    "cric is in, what vent settings for an 80kg male",
    "surgical airway in place, sats 95, what next",
    "we did a cric, now what for sedation, 80kg",
    "post-cric patient, 80kg, pain control",
    "cric done and secured, sats coming up, what now",
    "cricothyrotomy performed, tube secured, 80kg male sedation",
]


@pytest.mark.parametrize("query", DONE)
def test_a_completed_surgical_airway_is_not_cico(query):
    assert not oc.is_cico_query(query), query
    assert CICO_MARK not in (run(query).get("response") or ""), query


CICO = [
    "Help me do a cric",
    "failed intubation, failed i-gel, sats are 71",
    "can't intubate, failed igel, sats 70, cric kit ready",
    "failed cric, can't oxygenate, sats 60",
    "need a surgical airway now",
]


@pytest.mark.parametrize("query", CICO)
def test_a_cico_request_still_gets_the_card(query):
    assert oc.is_cico_query(query), query
    assert CICO_MARK in run(query)["response"], query
