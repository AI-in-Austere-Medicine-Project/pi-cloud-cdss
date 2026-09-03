"""
EdgeCDSS — the sepsis pre-gate's entry conditions.

Both failures this file pins come from the 2026-09-03 web-client feedback
review, and both ended at the same card:

  entry 44 — "overdosed on beta blockers. HR 30, BP 50/20" -> the SEPSIS card.
  entry 16 — "6 year old, fever and altered"               -> the SEPSIS card.

Offline: no API key, no network, no ChromaDB.
"""

import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402


# ── has_fever: a number is not a temperature until it has a scale ───────────

@pytest.mark.parametrize("query,expected", [
    # Fahrenheit, bare. The measured entry-16 defect: `\d{2}` captured "98".
    ("temp 98.6", False),
    ("temp 96.8", False),
    # The same defect's other sign: `\d{2}` captured "10" out of "101".
    ("temp 101", True),
    ("temp 100.4", True),           # the threshold itself is a fever
    # Celsius, bare — below the 50 split.
    ("temp 37", False),
    ("temp 38.5", True),
    ("temp 37.9", False),           # just under, on the Celsius scale
    # An explicit unit wins over the magnitude heuristic.
    ("39 C", True),
    ("101 F", True),
    ("99 F", False),
    ("38 C", True),
    # Other phrasings of the label.
    ("temp of 98.6", False),
    ("T 98.6", False),
    ("temperature of 101.5", True),
    ("temp: 39c", True),
    # Negation.
    ("afebrile, temp 98.6", False),
    ("afebrile, temp 101", False),
    ("no fever, temp 39", False),
    # Text terms still work, and "afebrile" no longer reads as "febrile".
    ("patient is febrile", True),
    ("patient is afebrile", False),
    ("fever and pus from the wound", True),
    ("no fever", False),
])
def test_has_fever_reads_the_scale(query, expected):
    assert oc.has_fever(query) is expected, query


def test_a_temperature_beside_an_unrelated_negative_is_still_a_fever():
    """The fever negation window is fever-specific on purpose: the general
    window contains "no ", and "no chest pain, temp 101" is a febrile
    patient."""
    assert oc.has_fever("no chest pain, no vomiting, temp 101") is True


@pytest.mark.parametrize("query", [
    "give 100 mcg fentanyl",        # "100 mc" is not 100 C
    "20 fr chest tube",             # "20 f" is not 20 F
    "wound is 10 cm across",
    "patient is 98 kg",             # no label, no unit, no temperature
    "peaked T waves, K is 6.8",     # a bare "t" that is not a temperature
    "hr 30 bp 50/20 spo2 91%",      # entry 44's vitals carry no temperature
])
def test_numbers_that_are_not_temperatures(query):
    assert oc.has_fever(query) is False, query


# ── The poisoning guard: a toxidrome is not a shock card ────────────────────

import clinical_router as cr  # noqa: E402
import general_reference as gr  # noqa: E402


class _FakeChroma:
    """Retrieval that comes back with nothing usable — an out-of-corpus
    question's actual experience. Same shape as test_general_reference's."""

    def __init__(self, distance=0.99):
        self.distance = distance

    def query(self, text, n_results=5):
        return {"documents": [["unrelated protocol text"]],
                "metadatas": [[{"source": "JTS Burn Care", "page": 3}]],
                "distances": [[self.distance]]}


@pytest.fixture
def stub_llm(monkeypatch):
    """Stub the provider layer and the validator. Nothing here needs a model:
    every assertion is about which path the query took, not what was said."""
    calls = {}

    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        calls["system"] = system
        calls["model"] = model
        return calls.get("reply", "Supportive care and urgent evacuation.")

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    monkeypatch.setattr(oc, "validate_response",
                        lambda *a, **k: {"result": "SAFE", "issues": [],
                                         "rationale": "", "safe": True})
    return calls


def _run(query, stub_llm, distance=0.99):
    return oc._query_with_rag_internal(query, _FakeChroma(distance),
                                       conversation_history=[])


# The five presentations from the toxidrome review, each with the vitals a
# medic would actually type. The antidote each one needs — glucagon, calcium /
# high-dose insulin, bicarbonate, naloxone, atropine — is in none of the 89
# JTS CPGs, which is the whole reason these must reach general reference and
# not the nearest in-corpus shock card.
TOXIDROMES = [
    # entry 44, verbatim shape.
    "I have a patient who overdosed on beta blockers. Vitals: HR 30, "
    "BP 50/20, SpO2 91%, IV access obtained",
    "patient OD on calcium channel blockers, BP 70/40, HR 40, IV access obtained",
    "TCA overdose, wide QRS, hypotensive BP 80/50, altered",
    "opioid overdose, RR 4, pinpoint pupils, unresponsive",
    "organophosphate poisoning, salivating, lacrimating, bradycardic, miosis",
]


@pytest.mark.parametrize("query", TOXIDROMES)
def test_every_toxidrome_is_detected(query):
    assert cr.looks_like_poisoning(query) is True


@pytest.mark.parametrize("query", TOXIDROMES)
def test_no_diagnosis_asserting_pre_gate_claims_a_toxidrome(query):
    """2e, 2g and 2h are the gates that assert a diagnosis from a shock
    pattern. None of them may answer a named poisoning."""
    assert not (oc.looks_like_sepsis(query)
                and oc.asks_for_dcr_or_hemostatic_resus(query)
                and not oc.has_clear_hemorrhage(query)
                and not cr.looks_like_poisoning(query)), "2e would fire"
    assert not (oc.looks_like_hemorrhagic_shock(query)
                and not oc.looks_like_sepsis(query)
                and not cr.looks_like_poisoning(query)), "2g would fire"
    assert not (oc.looks_like_sepsis(query)
                and not oc.has_clear_hemorrhage(query)
                and not cr.looks_like_poisoning(query)), "2h would fire"


@pytest.mark.parametrize("query", TOXIDROMES)
def test_every_toxidrome_reaches_general_reference(query, stub_llm):
    """End to end, with retrieval returning nothing usable — which is what an
    out-of-corpus question gets. The banner is the deliverable: the answer must
    say it is not from JTS rather than arrive dressed as a protocol."""
    result = _run(query, stub_llm)
    assert result["source_mode"] == "GENERAL_REFERENCE", result["response"][:200]
    assert gr.has_banner(result["response"])
    assert "not from JTS protocols" in result["response"]


def test_a_genuine_sepsis_presentation_still_gets_the_sepsis_card(stub_llm):
    """The guard is additive. A septic patient with no tox terms is unchanged."""
    query = "80kg male temp 38.2C pus draining from wound, BP 85/50, altered"
    assert cr.looks_like_poisoning(query) is False
    assert oc.looks_like_sepsis(query) is True
    result = _run(query, stub_llm)
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "**SEPSIS**" in result["response"]


def test_a_dose_safety_question_that_mentions_overdose_is_not_a_poisoning_case(stub_llm):
    """"max ketamine dose to avoid overdose" contains the word and is still a
    dosing question. The guard is scoped to the three diagnosis-asserting
    gates, so a query that never reaches them is untouched by it — which is
    why the detector does not need to parse intent to get this right."""
    query = "what is the max ketamine dose to avoid overdose"
    result = _run(query, stub_llm)
    assert result["source_mode"] == "PRE_GATE"
    assert not gr.has_banner(result["response"])


def test_the_seizure_card_still_owns_a_seizing_patient(stub_llm):
    """Scope boundary, pinned so it is visible rather than discovered.

    Step 2i (the common-case bank) is NOT guarded by looks_like_poisoning —
    this commit guards 2e, 2g and 2h, the three gates that assert a shock
    DIAGNOSIS. So "organophosphate poisoning, salivating, seizing" still
    reaches the ACTIVE SEIZURE card.

    That is defensible and it is not complete: a benzodiazepine IS the
    treatment for organophosphate-induced seizures, so the card is not wrong,
    but it names no atropine and no pralidoxime, and an unguarded 2i is how a
    partial answer gets served with a protocol's confidence. Flagged for owner
    review as a content question rather than widened here — 2i is a bank of
    twelve cards and guarding it is a separate decision.
    """
    result = _run("organophosphate poisoning, salivating, seizing, bradycardic",
                  stub_llm)
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert "**ACTIVE SEIZURE**" in result["response"]
