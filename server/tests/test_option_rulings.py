"""Rulings on the clarifying-question option audit (owner, 2026-11-19).

Owner: "One PR after the two pending ones, a commit per item, failing test first on
each, PFC and EMS replays, every moved row listed."

Each section is one ruling. The questions are driven turn by turn with the model
stubbed out; where a turn reaches the generator, the prompt it was given is captured.
"""
import os
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client as oc  # noqa: E402
import providers  # noqa: E402

dc = oc.drug_contracts


class _NoRetrieval:
    def query(self, *a, **k):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def run(q, history=None):
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=history or [])


@pytest.fixture
def ems(monkeypatch):
    monkeypatch.setattr(dc, "SERVED_SET", "EMS")


@pytest.fixture
def card_only(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("this turn called a model")
    monkeypatch.setattr(providers, "chat", _refuse)


@pytest.fixture
def model(monkeypatch):
    """The generator writes `text` (default: nothing dosed); the validator says SAFE.
    The generator's prompt is kept in `prompts`."""
    state = {"text": "Reassess.", "prompts": []}

    def chat(system, messages, **k):
        if "Clinical Safety Validator" in (system or ""):
            return '{"result":"SAFE","issues":[],"rationale":"stub"}'
        state["prompts"].append(f"{system}\n{messages}")
        return state["text"]
    monkeypatch.setattr(providers, "chat", chat)
    return state


def _offered_block(prompt: str) -> str:
    i = prompt.find("ALLOWED_DOSES — use EXACTLY")
    if i < 0:
        return ""
    end = prompt.find("────", i)
    return prompt[i:end if end > 0 else i + 4000]


# ── 1. A question offers only drugs signed for what is being asked ──────────
# Owner: "the EMS pain question lists aspirin, whose signed entry is cardiac chest
# pain. A question may only offer a drug whose signed indication matches the one being
# asked about." Found: on EMS, "moderate" offered aspirin 324 mg to the generator for a
# femur fracture, and a model line "aspirin PO: 324 mg. Indication: pain from femur
# fracture" passed the deterministic checks.

FEMUR = "80 kg adult, broken femur, pain, what can I give"


def test_ems_pain_question_does_not_offer_aspirin(ems, card_only):
    asked = run(FEMUR)["response"]
    assert asked.startswith(oc.PAIN_SEVERITY_QUESTION_PREFIX), asked[:300]
    assert "aspirin" not in asked.lower(), asked


@pytest.mark.parametrize("level", ["moderate", "severe"])
def test_ems_pain_answer_offers_no_aspirin_to_the_generator(ems, model, level):
    asked = run(FEMUR)["response"]
    run(level, [{"query": FEMUR, "response": asked}])
    block = _offered_block(model["prompts"][-1])
    assert "ketamine" in block and "aspirin" not in block.lower(), block


def test_ems_aspirin_written_for_femur_pain_holds(ems, model):
    asked = run(FEMUR)["response"]
    model["text"] = "**GIVE**\n- aspirin PO: 324 mg. Indication: pain from femur fracture.\n"
    r = run("moderate", [{"query": FEMUR, "response": asked}])
    assert r["validator_result"] == "UNSAFE", r["response"][:300]


def test_ems_aspirin_is_still_offered_for_cardiac_chest_pain(ems, model):
    run("80 kg adult, cardiac chest pain, suspected ACS, aspirin dose")
    assert "aspirin PO: 324 mg" in _offered_block(model["prompts"][-1])


def test_pfc_pain_question_unchanged(card_only):
    asked = run(FEMUR)["response"]
    for drug in ("ketamine", "fentanyl", "morphine", "acetaminophen"):
        assert drug in asked, asked
