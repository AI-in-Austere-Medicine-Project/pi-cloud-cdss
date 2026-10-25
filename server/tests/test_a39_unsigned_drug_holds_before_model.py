"""A39: a question naming a drug with no signed entry holds before the model runs.

Owner, 2026-10-25 (after #181 merged): "a question that names a drug with no
signed entry at all is held deterministically before the model runs, with the
hold naming the drug and 'no signed dose'; the model is not called. Fixture:
"don't want ketamine, I need magnesium", 75 kg. Magnesium itself goes on the
v1.1 signing list."

On main the fixture reaches the generator and the validator, and only the dose
check holds what the model wrote ("The answer stated magnesium sulfate 2 g, but
EdgeCDSS has no signed magnesium sulfate dose"). A model answer with no number
in it would have been served.

A drug the turn names only as history (the patient takes it, took it, is
allergic to it) or refuses is not asked for, and does not hold here: those
turns go on as before, and any dose the model writes is still checked.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

FIXTURE = "don't want ketamine, I need magnesium"


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


def _run(monkeypatch, turns):
    calls = []

    def chat(system, messages, **k):
        calls.append(system)
        if "Clinical Safety Validator" in (system or ""):
            return '{"result": "SAFE", "issues": [], "rationale": "ok"}'
        return "Magnesium is used for this. Consider it per local protocol."
    monkeypatch.setattr(providers, "chat", chat)
    hist, r = [], None
    for q in turns:
        calls.clear()
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        hist.append({"query": q, "response": r["response"]})
    return r, calls


def _assert_held_for_magnesium(r, calls):
    assert calls == [], "the model was called"
    assert r["source_mode"] == "DETERMINISTIC_PRE_GATE", r["source_mode"]
    assert r["validator_result"] == "UNSAFE"
    assert "magnesium" in r["response"].lower() and "no signed dose" in r["response"], r["response"]
    assert "ketamine" not in r["response"].lower(), r["response"]


# ── The fixture ─────────────────────────────────────────────────────────────

def test_the_fixture_holds_before_the_model(monkeypatch):
    _assert_held_for_magnesium(*_run(monkeypatch, [f"{FIXTURE}, 75 kg"]))


def test_the_fixture_after_a_weight_holds_before_the_model(monkeypatch):
    _assert_held_for_magnesium(*_run(monkeypatch, ["75 kg adult", FIXTURE]))


def test_the_fixture_after_the_ketamine_vial_question_holds(monkeypatch):
    """The live shape (2026-10-24): a ketamine card asked for the vial, then
    the medic turned it down for magnesium."""
    _assert_held_for_magnesium(*_run(monkeypatch, ["need ketamine 75kg adult IV", FIXTURE]))


# ── What counts as naming the drug ──────────────────────────────────────────

@pytest.mark.parametrize("query,drug", [
    (FIXTURE, "magnesium sulfate"),
    ("can I give mag for eclampsia", "magnesium sulfate"),
    ("how much amiodarone for VT, 80 kg", "amiodarone"),
    ("fentanyl or ketorolac for this pain, 75 kg adult", "ketorolac"),
    ("start him on magnesium", "magnesium sulfate"),
])
def test_an_unsigned_drug_asked_for_is_named(query, drug):
    assert oc.unsigned_drugs_named(query) == [drug]


@pytest.mark.parametrize("query", [
    "75 kg adult, fentanyl for pain",
    "need to give ketamine 80kg adult IV",
    "how much calcium for hyperkalemia",          # its signed forms are calcium chloride / gluconate
    "not amiodarone, what else for VT",
    "pt on metoprolol, HR 38, BP 70/40",
    "overdosed on oxycodone, RR 6, pinpoint pupils",
    "allergic to penicillin, open fracture, 80 kg",
    "took 240 mg of diltiazem this morning, HR 40",
    "history of warfarin and aspirin use, fell and hit head",
    "oxycodone overdose, RR 6",
])
def test_history_negation_and_signed_drugs_are_not_named(query):
    assert oc.unsigned_drugs_named(query) == []


def test_the_hold_names_every_unsigned_drug():
    issue = oc.unsigned_drug_hold_issue(["amiodarone", "magnesium sulfate"])
    assert "amiodarone" in issue and "magnesium sulfate" in issue and "no signed dose" in issue


def test_a_history_mention_still_goes_to_the_model(monkeypatch):
    r, calls = _run(monkeypatch, ["overdosed on oxycodone, RR 6, pinpoint pupils, adult"])
    assert calls, "a history mention is not a request: the turn goes on as before"
