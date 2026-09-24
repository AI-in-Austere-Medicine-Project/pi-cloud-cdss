"""
EdgeCDSS — A1: haemorrhage with shock physiology reaches the DCR card.

Field report, 2026-09-24: "80 kg male, GSW left thigh, tourniquet on 20 min,
HR 118, BP 104/68" was answered from GENERAL MEDICAL REFERENCE — no TXA, no
blood-product priority, validator SAFE. Three separate misses (A1 step 1):

  1. the hemorrhagic-shock pre-gate was suppressed by the stated BP: 104/68 is
     not below 100/60, so "not shock", and HR 118 was never read;
  2. the router had no term for the medic's words (GSW, gunshot, tourniquet,
     TQ, bleeding, amputation) in the DCR entry, so it matched nothing;
  3. retrieval scored 0.000 and the query fell to general knowledge.

A related P1 found on the way: for "massive hemorrhage, tourniquet applied" the
top two retrieval hits were the Military Working Dog CPG. Canine pages must not
answer a human query.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

ORIGINAL = "80 kg male, GSW left thigh, tourniquet on 20 min, HR 118, BP 104/68"
DCR_QUERIES = [
    ORIGINAL,
    "blast injury, bilateral leg amputations, TQs on",
    "massive hemorrhage, tourniquet applied",
    "penetrating trauma, hemorrhagic shock",          # already reached it
]
STABLE = "small laceration on the forearm, bleeding controlled with pressure, HR 78, BP 124/80"


class _NoRetrieval:
    """The DCR card is a pre-gate: it answers before retrieval and any model."""
    def query(self, *a, **k):
        raise AssertionError("a DCR case reached retrieval")


class _RecordingRetrieval:
    def __init__(self):
        self.calls = []

    def query(self, text, n_results=10, **kw):
        self.calls.append(kw)
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")


@pytest.mark.parametrize("query", DCR_QUERIES)
def test_haemorrhage_with_shock_physiology_reaches_the_dcr_card(query):
    r = oc._query_with_rag_internal(query, _NoRetrieval())
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["source_mode"]
    assert "Start damage-control resuscitation" in r["response"], r["response"][:200]
    assert "TXA" in r["response"]


def test_a_stable_controlled_laceration_does_not(no_model):
    assert not oc.looks_like_hemorrhagic_shock(STABLE)
    r = oc._query_with_rag_internal(STABLE, _RecordingRetrieval())
    assert "damage-control resuscitation" not in r["response"].lower()


# ── the shock criteria, one at a time ────────────────────────────────────────

@pytest.mark.parametrize("query,why", [
    ("GSW to the leg, casualty is in shock", "a stated shock word"),
    ("stab wound to the thigh, BP 92/70", "SBP < 100"),
    (ORIGINAL, "HR > 100 with a bleeding term; a normal-looking BP must not suppress it"),
    ("tourniquet on the arm, HR 104, BP 132/84", "HR > 100 with a tourniquet"),
    ("gunshot wound to the calf, HR 96, BP 100/70", "shock index 0.96 >= 0.9"),
    ("bilateral above-knee amputations after an IED", "ID18 injury pattern: multiple amputation"),
    ("penetrating wound to the abdomen, HR 88, BP 128/82", "ID18 injury pattern: penetrating torso, BP normal"),
    ("junctional bleed in the left groin, packed", "ID18 injury pattern: junctional wound"),
])
def test_each_shock_criterion_triggers_the_gate(query, why):
    assert oc.looks_like_hemorrhagic_shock(query), why


@pytest.mark.parametrize("query,why", [
    (STABLE, "no shock physiology, no ID18 pattern"),
    ("HR 110 after the run, BP 130/80, no injuries", "tachycardia without a bleeding term"),
    ("GSW to the forearm, bleeding controlled, HR 84, BP 126/80, SI 0.67", "bleeding term, normal physiology"),
    ("single below-knee amputation stump, well healed, routine check", "one old amputation is not the pattern"),
    # Found in the A1 replay: "stab" matched inside "stable".
    ("21 year-old male with stable vitals, fractured femur, HR 120, BP 130/100, ketamine drip for pain",
     "'stable' is not a stab wound"),
])
def test_what_does_not_trigger_the_gate(query, why):
    assert not oc.looks_like_hemorrhagic_shock(query), why


# ── (b) router terms ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "gunshot wound thigh bleeding controlled with TQ",
    "GSW left thigh, tourniquet on",
    "exsanguination from a leg wound",
])
def test_medic_phrasing_routes_to_dcr(query):
    r = oc._router.route(query, oc.PatientContext(), query)
    assert r.matched_protocol == "damage_control_resuscitation", (r.matched_protocol, r.confidence)


# ── (c) canine pages are not retrieved for a human query ─────────────────────

@pytest.mark.parametrize("query", [
    # A human query that reaches retrieval. ("massive hemorrhage, tourniquet
    # applied" was the case that surfaced this, but it now takes the DCR card.)
    "how long can a tourniquet stay on before conversion",
    "GSW thigh, how do I manage the bleeding",
])
def test_a_human_query_excludes_the_canine_documents(no_model, query):
    rec = _RecordingRetrieval()
    oc._query_with_rag_internal(query, rec)
    assert rec.calls, "retrieval was not reached"
    where = rec.calls[0].get("where")
    assert where == oc.HUMAN_ONLY_WHERE, where


@pytest.mark.parametrize("query", [
    "my MWD was hit, massive bleeding from the leg",
    "K9 heat injury, temp 42",
    "the dog has a tourniquet on its hind leg",
])
def test_a_query_naming_a_dog_keeps_the_canine_documents(no_model, query):
    rec = _RecordingRetrieval()
    oc._query_with_rag_internal(query, rec)
    if rec.calls:
        assert rec.calls[0].get("where") is None, rec.calls[0]


def test_the_canine_filter_names_every_mwd_document_and_the_smog_canine_pages():
    files = set(oc.CANINE_FILES)
    assert files == {
        "Arachnid_Snake_Envenomation_MWD_CPG_c11_29_Mar_2025_v1.1.pdf",
        "Heat_Injury_MWD_CPG_c9_29_Mar_2025.pdf",
        "K9_Euthanasia_MWD_CPG_c21_03_Apr_2025.pdf",
        "MWD_CPG_12_Dec_2018_ID16_v1.3.pdf",
        "Normal_Clinical_Parameters_MWD_c2_05_May_2025_v1.1.pdf",
        "Transfusion_in_Military_Working_Dog_10_Dec_2019_ID77.pdf",
    }
    assert oc.SMOG_CANINE_PAGES == (56, 63)
