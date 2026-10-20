"""A bare "ketamine drip" is not RSI: it is asked which indication.

Owner, 2026-10-20 (#170 review): "ketamine drip 80 kg", with no context at
all, must get the which-indication question (#165), not an answer. On main it
got the RSI bundle: is_rsi_or_post_intubation_context lists "ketamine drip"
as an RSI word, so with a weight the RSI pre-gate served induction ketamine,
rocuronium and post-intubation sedation to a patient nobody said was being
intubated. "ketamine drip for pain" took the same bundle (the #170 harness).

"Intubated" with the drip is read as sedation, and the drip card answers it:
the owner accepted that (2026-10-20). A query with RSI words still gets the
bundle.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
NO_CONTEXT = "ketamine drip 80 kg"


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def generator(monkeypatch):
    seen = {"called": False}

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        seen["called"] = True
        return "STUB"

    monkeypatch.setattr(providers, "chat", chat)
    return seen


def run(query, history=None):
    return oc._query_with_rag_internal(query, _JtsHit(), conversation_history=history or [])


def _until_not_vial(query):
    """The turn after the vial question, if the vial is asked first."""
    r = run(query)
    if r["response"].startswith("Which ketamine do you have"):
        r = run("500", [{"query": query, "response": r["response"]}])
    return r


def test_a_bare_ketamine_drip_is_not_the_rsi_pregate():
    assert oc.should_use_rsi_pregate(NO_CONTEXT) is False


def test_a_bare_ketamine_drip_is_asked_which_indication(generator):
    r = _until_not_vial(NO_CONTEXT)
    assert r["response"].startswith("Which indication for ketamine"), r["response"]
    assert "RSI induction" not in r["response"], r["response"]
    assert generator["called"] is False


def test_an_intubated_patients_ketamine_drip_gets_the_drip_card(generator):
    r = run("ketamine drip, 80 kg, intubated")
    assert r["response"].startswith("**KETAMINE SEDATION DRIP**"), r["response"]


@pytest.mark.parametrize("query", [
    "RSI 80 kg male, ketamine and roc, IV established",
    ("have a 6 year old TBI I need to RSI. Will be giving Ketamine and Rocuronium. Have IV. "
     "Pt weighs 35kg. I will then also need a ketamine drip for him post intubation"),
])
def test_rsi_words_still_take_the_bundle(query):
    assert oc.should_use_rsi_pregate(query) is True
