"""
EdgeCDSS — a missing contract holds. It never serves an uncited value.

The push-dose and infusion epinephrine cards kept the numbers they printed
before the contract engine existed — 5-20 mcg push, 2-10 mcg/min drip — for
the case where no signed entry applied. Neither number has a citation in the
bank. Unsigning the push-dose entries to correct a citation (#78) would have
served the 5 mcg floor with no contraindications, and the card fires ahead of
every gate that could have caught it.

Unsigning an epinephrine entry now makes the card a safety hold, through the
whole pipeline, with no dose in it.

    cd server && ./run_unit_tests.sh
"""
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402


class _NoRetrieval:
    """A prep card answers at step 2a, before retrieval and before any model."""
    def query(self, *a, **k):
        raise AssertionError("a preparation question reached retrieval")


# A dose or rate: a number with a mass unit, optionally per kg and per minute.
# The recipe's own numbers (1 mL, 9 mL, 10 mcg/mL, 250 mL) are volumes or
# concentrations and do not match; a hold carries no recipe anyway.
DOSE = re.compile(r"\d+(?:\.\d+)?\s*(?:-\s*\d+(?:\.\d+)?\s*)?(?:mcg|mg|g)"
                  r"(?:/kg)?(?:/min|/hr)?\b(?!/mL)", re.I)

PUSH = "how do I mix push dose epi"
DRIP = "how do I make an epi drip"


def _unsign(monkeypatch, indication_words=None):
    """Unsign the signed epinephrine entries whose indication contains any of
    indication_words (all of them when None). Restored after the test."""
    n = 0
    for e in dc.DRUGS["epinephrine"]["dose_entries"]:
        if indication_words is None or any(w in e["indication"] for w in indication_words):
            if e.get("signoff") is True:
                monkeypatch.setitem(e, "signoff", False)
                n += 1
    assert n, "no signed epinephrine entry matched — the premise is stale"


def _run(query):
    return oc._query_with_rag_internal(query, _NoRetrieval())


def _assert_hold(r, what):
    assert r["validator_result"] == "UNSAFE", r["validator_result"]
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["source_mode"]
    assert r["response"].startswith("Clinical safety hold"), r["response"][:120]
    assert any(f"no signed {what}" in i for i in r["validator_issues"]), r["validator_issues"]
    served = DOSE.findall(r["response"])
    assert not served, f"a hold served a dose: {served}"
    for retired in ("5-20 mcg", "2-10 mcg/min"):
        assert retired not in r["response"], f"the uncited fallback is back: {retired}"


def test_the_signed_cards_still_serve():
    """The premise: with the bank as signed, both cards answer."""
    for q in (PUSH, DRIP):
        r = _run(q)
        assert r["source_mode"] == "FIXED_PREP" and r["validator_result"] == "SAFE", (q, r["source_mode"])
    assert "10-20 mcg" in _run(PUSH)["response"], "the signed push-dose window is not what served"


@pytest.mark.parametrize("query,words,what", [
    (PUSH, ["push dose"], "push-dose epinephrine"),
    (DRIP, ["infusion"], "epinephrine infusion"),
])
def test_unsigning_the_entries_a_card_uses_yields_a_hold(monkeypatch, query, words, what):
    _unsign(monkeypatch, words)
    _assert_hold(_run(query), what)


@pytest.mark.parametrize("query,what", [
    (PUSH, "push-dose epinephrine"), (DRIP, "epinephrine infusion"),
])
def test_unsigning_every_epinephrine_entry_yields_a_hold(monkeypatch, query, what):
    _unsign(monkeypatch)
    _assert_hold(_run(query), what)


def test_a_paediatric_push_dose_with_its_entry_unsigned_yields_a_hold(monkeypatch):
    """The paediatric shock push dose is its own entry at its own number."""
    _unsign(monkeypatch, ["push dose"])
    ctx = oc.PatientContext(age_years=6.0, is_pediatric=True)
    text, issues = oc.fixed_prep_outcome("push dose epi for the kid, shocky", ctx)
    assert issues and text.startswith("Clinical safety hold")
    assert not DOSE.findall(text)


@pytest.mark.parametrize("query,what", [
    (PUSH, "push-dose epinephrine"), (DRIP, "epinephrine infusion"),
])
def test_a_failed_contract_import_yields_a_hold(monkeypatch, query, what):
    """drug_contracts failing to import is the other case the fallback covered."""
    monkeypatch.setattr(oc, "drug_contracts", None)
    text, issues = oc.fixed_prep_outcome(query)
    assert issues and any(f"no signed {what}" in i for i in issues)
    assert not DOSE.findall(text)
