"""A fixed adult dose needs an adult first: the patient's age, "adult", or a weight.

Owner review of #181, 2026-10-25: "Fentanyl IV and naloxone are answered
without a weight because they have a fixed adult dose. How does the system
know the patient is an adult? If age isn't established, a fixed adult dose for
a child is exactly the failure you've been closing. Fixed doses should require
an adult confirmation (or a weight) first, the same way mL requires a vial."

On main a context with no age was an adult (is_pediatric defaults False), so
"naloxone dose" built the signed adult 0.4 mg for a patient nobody had aged.
Now nothing fixed builds until an adult is established: an age of 18 or over,
the word "adult", "yes" to the adult question, or a confirmed weight. The
pre-gate asks the question the way it asks for the vial.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

VALIDATOR_OK = '{"result": "SAFE", "issues": [], "rationale": "ok"}'
WEIGHT_Q = "Need weight in kg before dosing."


class _JtsHit:
    def query(self, *a, **k):
        return {"documents": [["protocol text"]],
                "metadatas": [[{"source": "JTS", "page": 1}]], "distances": [[0.2]]}


@pytest.fixture
def seen(monkeypatch):
    systems = []

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return VALIDATOR_OK
        systems.append(system)
        return "STUB"
    monkeypatch.setattr(providers, "chat", chat)
    return systems


def run_flow(turns):
    hist, out = [], []
    for q in turns:
        r = oc._query_with_rag_internal(q, _JtsHit(), conversation_history=list(hist))
        out.append(r)
        hist.append({"query": q, "response": r["response"]})
    return out


def _drugs(query, ctx):
    return sorted({d.drug for d in oc.build_allowed_doses(query, ctx)})


# ── The builder ─────────────────────────────────────────────────────────────

def test_no_age_and_no_weight_builds_no_fixed_dose():
    ctx = oc.extract_patient_context("naloxone dose")
    assert ctx.age_years is None and not ctx.has_confirmed_weight
    assert _drugs("naloxone dose", ctx) == []
    assert _drugs("fentanyl IV for pain", oc.extract_patient_context("fentanyl IV for pain")) == []


@pytest.mark.parametrize("query", [
    "naloxone dose, adult",
    "naloxone dose, 45 year old",
    "naloxone dose, 80 kg",
])
def test_an_established_adult_gets_the_fixed_dose(query):
    assert _drugs(query, oc.extract_patient_context(query)) == ["naloxone"]


def test_a_stated_minor_age_is_not_an_adult():
    ctx = oc.extract_patient_context("naloxone dose, 16 year old")
    assert not ctx.adult_established
    assert _drugs("naloxone dose", ctx) == []


def test_a_later_minor_age_overrides_adult():
    ctx = oc.extract_patient_context("adult, naloxone dose")
    ctx = oc.extract_patient_context("actually he is 15 year old", prior_ctx=ctx)
    assert not ctx.adult_established


# ── The question ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", ["naloxone dose", "fentanyl IV for pain"])
def test_a_fixed_dose_request_with_no_age_asks_adult(seen, query):
    (r,) = run_flow([query])
    assert r["response"] == oc.ADULT_CONFIRM_ASK, r["response"]
    assert seen == [], "the request reached the model before an adult was established"


@pytest.mark.parametrize("answer", ["adult", "yes", "35 year old", "80 kg"])
def test_the_answer_reaches_the_fixed_dose(seen, answer):
    rs = run_flow(["naloxone dose", answer])
    assert rs[0]["response"] == oc.ADULT_CONFIRM_ASK
    assert rs[1]["response"] != oc.ADULT_CONFIRM_ASK, rs[1]["response"]
    assert seen and "naloxone" in seen[-1] and "0.4 mg" in seen[-1], \
        "the signed fixed dose did not reach the generator"


def test_a_child_answer_is_asked_the_weight(seen):
    rs = run_flow(["naloxone dose", "child"])
    assert rs[1]["response"] == WEIGHT_Q, rs[1]["response"]


@pytest.mark.parametrize("query", [
    "fentanyl IV for pain, adult male",
    "naloxone dose, 40 year old",
    "naloxone dose for an 80 kg patient",
])
def test_an_established_adult_is_not_asked(seen, query):
    (r,) = run_flow([query])
    assert r["response"] != oc.ADULT_CONFIRM_ASK, r["response"]


# ── The hold says what is missing ───────────────────────────────────────────

def test_a_fixed_dose_hold_with_no_age_asks_for_an_adult():
    query = "in Sicily, he's in asystole, CPR going"
    ctx = oc.extract_patient_context(query)
    issues = oc.run_deterministic_checks(
        query, "**GIVE**\n- Epinephrine 1 mg IV every 3-5 minutes.", ctx, []).issues
    assert any("confirm the patient is an adult" in i for i in issues), issues
