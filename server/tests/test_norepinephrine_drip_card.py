"""
EdgeCDSS — A16: a deterministic norepinephrine drip card.

Found in #108; owner, #108 review. Models answer a norepinephrine rate
question in flat mcg/min ("2-20 mcg/min"), which A11 holds: every signed
norepinephrine rate is per kg per minute, and nothing served one. So a
hypotensive patient's "starting norepinephrine, what rate" got a hold and no
answer. The card serves the signed per-kg rate, the way the epinephrine drip
card does: narrowed to the stated indication (A11b), every signed entry when
none is stated, and no mL/hr (no norepinephrine preparation is signed).

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

CARD = "NOREPINEPHRINE INFUSION"
LIVE = "80kg male, still hypotensive after 2 L of crystalloid, starting norepinephrine, what rate"


class _NoRetrieval:
    def query(self, *a, **k):
        raise AssertionError("a deterministic card reached retrieval")


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: "STUB")
    return lambda q: oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=[])


# ── The owner's pair ───────────────────────────────────────────────────────

def test_the_models_flat_rate_answer_is_held():
    """#108's live harness: gpt-4o-mini and claude-sonnet-5 answered in mcg/min."""
    ctx = oc.extract_patient_context(LIVE)
    check = oc.run_deterministic_checks(
        LIVE, "**GIVE**\n- Start norepinephrine at 2–20 mcg/min, titrate to MAP 65.", ctx, [])
    assert any("infusion rate" in i for i in check.issues), check.issues


def test_the_card_is_served_with_the_signed_per_kg_rate(run):
    r = run(LIVE)
    text = r["response"]
    assert CARD in text, text[:200]
    assert "mcg/kg/min" in text and "Indication: vasodilatory/haemorrhagic shock infusion" in text, text
    assert "bradycardia" not in text.split("**RATE**")[1].split("**CONTRAINDICATIONS**")[0], text
    assert "mL/hr" not in text and "mL/h" not in text, "no volume rate from an unsigned preparation"


# ── Narrowed to the indication, as the epinephrine card is ─────────────────

@pytest.mark.parametrize("query,indication", [
    ("80kg male, cardiogenic shock, pulmonary oedema, SBP 85, norepinephrine drip",
     "cardiogenic shock"),
    ("80kg male, HR 38, symptomatic bradycardia, norepinephrine infusion rate",
     "symptomatic bradycardia"),
    ("6 year old, 20kg, septic shock, norepinephrine drip", "vasodilatory shock infusion"),
])
def test_the_card_serves_the_entry_for_the_indication(run, query, indication):
    text = run(query)["response"]
    assert CARD in text and indication in text, text[:400]


def test_with_no_indication_every_signed_entry_is_listed(run):
    rate = run("how do I run a norepi drip")["response"].split("**RATE**")[1]
    assert "shock" in rate and "bradycardia" in rate and "cardiogenic" in rate, rate


def test_mix_norepi_gets_the_card(run):
    assert CARD in run("mix norepi for an 80kg adult in septic shock")["response"]


# ── Controls ────────────────────────────────────────────────────────────────

def test_the_epinephrine_drip_card_is_unchanged(run):
    text = run("how do i make an epi drip for shock")["response"]
    assert "EPINEPHRINE INFUSION PREP" in text and CARD not in text


def test_a_question_about_norepinephrine_is_not_the_card(run):
    text = run("is norepinephrine better than epinephrine in septic shock").get("response") or ""
    assert CARD not in text
