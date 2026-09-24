"""
EdgeCDSS — a fixed dose does not need a weight.

build_allowed_doses returned nothing at all without a confirmed weight, so
"naloxone dose" for an adult built no contract even though naloxone 0.4 mg
IV/IM is signed and weight-independent. The generator was told "ALLOWED_DOSES:
none", and since #70 any naloxone number it stated was held ("give the weight in
kg") for a dose that never depended on one. Replayed case: A1-NOWT-013.

An adult with no weight now gets the signed FIXED-dose entries for the drugs
the query names. Per-kg entries still need a weight, and so does a child, for
whom the pre-gate asks and the post-check holds.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402
import providers  # noqa: E402

ADULT_NO_WEIGHT = oc.PatientContext()
HISTORY = [{"query": "adult male casualty, penetrating chest wound, awake",
            "response": "ok"}]


def _doses(query, ctx):
    return [(d.drug, d.route, d.display_value, d.display_units)
            for d in oc.build_allowed_doses(query, ctx)]


def test_the_signed_naloxone_doses_are_fixed():
    fixed = [e for e in dc.servable_entries()["naloxone"]
             if dc.resolve_dose(e, None)["dose_mg"] is not None]
    assert {(e["route"], e["population"]) for e in fixed} == {("IV", "adult"), ("IM", "adult")}, \
        "the naloxone contract changed; re-derive this regression"


def test_an_adult_with_no_weight_gets_the_fixed_naloxone_dose():
    assert ADULT_NO_WEIGHT.dosing_weight_kg is None
    assert sorted(_doses("naloxone dose", ADULT_NO_WEIGHT)) == [
        ("naloxone", "IM", 0.4, "mg"), ("naloxone", "IV", 0.4, "mg")]
    for d in oc.build_allowed_doses("naloxone dose", ADULT_NO_WEIGHT):
        assert "drug_contracts" in d.source or "contract" in d.source.lower(), d.source


def test_a_child_with_no_weight_still_gets_nothing():
    child = oc.PatientContext(age_years=6.0, is_pediatric=True)
    assert _doses("naloxone dose", child) == []
    assert _doses("epinephrine for anaphylaxis", child) == []


def test_a_per_kg_dose_still_needs_a_weight():
    """Ketamine is per-kg on every entry and in every legacy calculator."""
    assert _doses("ketamine for pain", ADULT_NO_WEIGHT) == []
    assert _doses("RSI ketamine and rocuronium", ADULT_NO_WEIGHT) == []


def test_with_a_weight_nothing_changes():
    ctx = oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    assert sorted(_doses("naloxone dose", ctx)) == [
        ("naloxone", "IM", 0.4, "mg"), ("naloxone", "IV", 0.4, "mg")]


def test_the_replayed_case_now_carries_the_contract_and_holds_the_wrong_number(monkeypatch):
    """A1-NOWT-013: the answer said "naloxone 2–4mg". It is still held, but now
    because it is not the signed dose, and the signed dose reached the model."""
    seen = {}

    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        if system == oc.VALIDATOR_PROMPT:
            return '{"result": "SAFE", "issues": [], "rationale": "ok"}'
        seen["system"] = system
        return "**TREAT**\n- Titrate naloxone 2–4mg escalating doses to respiratory effort.\n"

    monkeypatch.setattr(providers, "chat", fake_chat)

    class Hit:
        def query(self, *a, **k):
            return {"documents": [["Opioid overdose protocol"]],
                    "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}

    r = oc._query_with_rag_internal("naloxone dose", Hit(), conversation_history=HISTORY)
    assert "Draw 1 mL of 0.4mg/mL naloxone IV (0.4 mg)" in seen["system"], \
        "the fixed dose did not reach the generator"
    assert r["validator_result"] == "UNSAFE"
    assert any("not the signed naloxone dose" in i for i in r["validator_issues"]), \
        r["validator_issues"]


def test_the_signed_dose_stated_in_free_text_is_not_held():
    doses = oc.build_allowed_doses("naloxone dose", ADULT_NO_WEIGHT)
    assert oc.free_text_dose_issues("**GIVE**\n- Give naloxone 0.4 mg IV.", doses,
                                    ADULT_NO_WEIGHT) == []


# ── the class phrase that is not a drug ──────────────────────────────────────

def test_a_calcium_channel_blocker_is_not_calcium():
    assert dc.resolve_drugs("patient OD on calcium channel blockers") == []
    assert dc.resolve_drugs("calcium-channel-blocker toxicity") == []
    # The drug itself still resolves, including beside the class phrase.
    assert dc.resolve_drugs("give calcium for hyperkalaemia") == ["calcium gluconate"]
    assert dc.resolve_drugs("calcium channel blocker OD, give calcium") == ["calcium gluconate"]


def test_a_ccb_overdose_with_no_weight_builds_no_calcium_contract():
    assert _doses("patient OD on calcium channel blockers, BP 70/40", ADULT_NO_WEIGHT) == []


def test_the_free_text_check_does_not_pair_a_ccb_dose_with_calcium():
    text = "**TREAT**\n- He took calcium channel blocker 240 mg this morning."
    assert oc.free_text_dose_issues(text, [], ADULT_NO_WEIGHT) == []
