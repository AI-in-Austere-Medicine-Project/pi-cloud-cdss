"""
EdgeCDSS — general medical reference fallback (F-4).

Offline. The generator and validator are stubbed, so nothing here asserts what a
model says — only what the pipeline does with what it says, which is the only
part that is deterministic.

    cd server && ./run_unit_tests.sh
"""

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import general_reference as gr  # noqa: E402
import openai_client as oc  # noqa: E402
from openai_client import PatientContext  # noqa: E402
from test_fixtures import (  # noqa: E402
    GENERAL_LAB_REFERENCE, GENERAL_MODE_GIVE_LINE, GENERAL_PREP_RECIPE,
)


# ── the routing guard ────────────────────────────────────────────────────────

def use(source_mode="INSUFFICIENT", history="what is a normal serum lactate",
        allowed_doses=None, wants_dose=False, patient_known=False):
    return gr.use_general_reference(source_mode, history, allowed_doses or [],
                                    wants_dose, patient_known)


def test_fallback_triggers_on_empty_retrieval():
    assert use() is True


@pytest.mark.parametrize("source_mode", ["JTS_GROUNDED", "GENERAL_MEDICAL"])
def test_fallback_does_not_hijack_retrieved_answers(source_mode):
    """Only INSUFFICIENT falls back.

    The GENERAL_MEDICAL band still has retrieved text in the prompt. It is
    labelled "general" because its own prompt already says it is not JTS, but it
    keeps its existing behaviour and is not this path.
    """
    assert use(source_mode=source_mode) is False


def test_a_populated_dose_contract_keeps_the_query_on_the_dose_path():
    contract = [oc.ketamine_analgesia_iv(80.0)]
    assert use(allowed_doses=contract) is False


def test_wants_medication_dose_disqualifies():
    assert use(wants_dose=True) is False


@pytest.mark.parametrize("query", [
    "how much calcium gluconate for hyperkalemia",
    "what dose of amiodarone",
    "whats the dose for adenosine",
    "how many mg of diphenhydramine",
    "should i give steroids",
    "how much do i give",
])
def test_dosing_questions_never_reach_general_knowledge(query):
    """Recipe yes, prescription no — the first of three independent guards.

    Several of these match none of wants_medication_dose's terms, which is why
    this second check exists rather than leaning on that one.
    """
    assert gr.is_dosing_question(query) is True
    assert use(history=query) is False


@pytest.mark.parametrize("query", [
    "how do i make push dose epi",
    "how do i mix a norepinephrine drip",
    "how much saline do i add to make a 16 mcg/ml bag",
    "what concentration is a 1:10,000 epi syringe",
    "how do you reconstitute tranexamic acid",
])
def test_preparation_questions_are_not_dosing_questions(query):
    """The recipe tier this feature exists to serve.

    "how much saline do I add" contains a dosing-intent phrase and is still a
    recipe question — preparation intent wins, and SC-6 remains the backstop.
    """
    assert gr.is_dosing_question(query) is False
    assert use(history=query) is True


@pytest.mark.parametrize("query", [
    "what is a normal serum potassium",
    "which snakes in west africa are neurotoxic",
    "is oleander toxic",
    "what does an elevated lactate mean",
    "what is the half life of naloxone",
])
def test_reference_questions_reach_general_knowledge(query):
    assert use(history=query) is True


def test_a_dose_request_earlier_in_the_session_still_disqualifies():
    """The guard reads full history, not just the current turn."""
    history = "how much ketamine for a 6 year old  IV"
    assert use(history=history) is False


# ── labelling ────────────────────────────────────────────────────────────────

def test_banner_is_added_and_is_idempotent():
    once = gr.add_banner(GENERAL_LAB_REFERENCE)
    assert gr.has_banner(once)
    assert "not from JTS protocols" in once
    assert gr.add_banner(once) == once


def test_banner_survives_a_round_trip_through_history():
    """The client stores the served text verbatim, so the label persists.

    A medic scrolling back must not find an unlabelled general answer sitting
    among JTS ones.
    """
    served = gr.add_banner(GENERAL_LAB_REFERENCE)
    history = [{"query": "normal potassium", "response": served}]
    assert gr.has_banner(history[0]["response"])


def test_strip_banner_removes_exactly_the_label():
    served = gr.add_banner(GENERAL_LAB_REFERENCE)
    assert gr.strip_banner(served) == GENERAL_LAB_REFERENCE
    assert gr.strip_banner(GENERAL_LAB_REFERENCE) == GENERAL_LAB_REFERENCE


def test_speech_prepends_the_disclosure_and_drops_the_banner():
    served = gr.add_banner(GENERAL_LAB_REFERENCE)
    spoken = gr.for_speech(served, "general")
    assert spoken.startswith(gr.SPOKEN_DISCLOSURE)
    assert "⚠️" not in spoken
    assert "GENERAL MEDICAL REFERENCE" not in spoken
    assert "3.5-5.0 mEq/L" in spoken


def test_speech_is_untouched_for_jts_answers():
    assert gr.for_speech("Apply a tourniquet.", "jts") == "Apply a tourniquet."
    assert gr.for_speech("Apply a tourniquet.", "") == "Apply a tourniquet."


def test_the_prompt_forbids_the_canonical_give_format():
    """The second of three guards. Prompt discipline, pinned so it cannot drift."""
    prompt = gr.GENERAL_REFERENCE_PROMPT
    assert "Draw X mL of Y mg/mL" in prompt
    assert "150 words" in prompt
    # F-2 inverts what this line used to assert. The refusal sentence was in
    # this prompt and the model reached for it as a catch-all: 22 of 160 bank
    # scenarios were answered "AUSTERE-CDS handles medical queries only",
    # including a serum-lactate reference question and a keppra dilution — both
    # squarely inside this mode's stated scope. is_non_medical_query() owns
    # that decision and runs first; a second, softer copy here could only
    # disagree with it.
    assert "AUSTERE-CDS handles medical queries only." not in prompt


def test_patient_context_is_marked_not_for_dosing():
    prompt = gr.build_system_prompt("PEDIATRIC PATIENT\nConfirmed weight: 20kg")
    assert "20kg" in prompt
    assert "Do not dose against it" in prompt
    assert "ALLOWED_DOSES" not in prompt


# ── the source field ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("source_mode,expected", [
    ("JTS_GROUNDED", "jts"),
    ("DETERMINISTIC_PRE_GATE", "jts"),
    ("PRE_GATE", "jts"),
    ("NON_MEDICAL_PRE_GATE", "jts"),
    ("ERROR", "jts"),
    ("GENERAL_REFERENCE", "general"),
    ("GENERAL_MEDICAL", "general"),
    ("FIXED_PREP", "general"),
])
def test_knowledge_source_mapping(source_mode, expected):
    """`source` answers one binary question: did general knowledge produce this?

    That is why errors and refusals sit on the "jts" side — they are not
    general-knowledge answers either. FIXED_PREP sits on the "general" side
    because a standardized preparation recipe is reference knowledge; the corpus
    is 89 JTS trauma CPGs and does not contain it.
    """
    assert oc.knowledge_source(source_mode) == expected


# ── end to end through the real pipeline ─────────────────────────────────────

class FakeChroma:
    """Retrieval that returns nothing usable — classify_retrieval -> INSUFFICIENT."""

    def __init__(self, distance=0.99):
        self.distance = distance

    def query(self, text, n_results=5):
        return {"documents": [["unrelated protocol text"]],
                "metadatas": [[{"source": "JTS Burn Care", "page": 3}]],
                "distances": [[self.distance]]}


@pytest.fixture
def stub_llm(monkeypatch):
    """Stub the provider layer. Returns the recorded call so tests can inspect it."""
    calls = {}

    def fake_chat(system, messages, *, model, temperature=0.2, max_tokens=700):
        calls["system"] = system
        calls["model"] = model
        calls["messages"] = messages
        return calls.get("reply", GENERAL_LAB_REFERENCE)

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    monkeypatch.setattr(oc, "validate_response",
                        lambda *a, **k: {"result": "SAFE", "issues": [],
                                         "rationale": "", "safe": True})
    return calls


def run(query, stub_llm, history=None, distance=0.99, **kw):
    return oc._query_with_rag_internal(query, FakeChroma(distance),
                                       conversation_history=history or [], **kw)


def test_end_to_end_fallback_labels_and_serves(stub_llm):
    result = run("what is a normal serum lactate", stub_llm)
    assert result["source_mode"] == "GENERAL_REFERENCE"
    assert gr.has_banner(result["response"])
    assert "3.5-5.0 mEq/L" in result["response"]
    assert oc.knowledge_source(result["source_mode"]) == "general"
    assert "GENERAL MEDICAL REFERENCE mode" in stub_llm["system"]


@pytest.mark.parametrize("query,expected_mode", [
    # Caught by the route pre-gate, which sits above retrieval entirely.
    ("how much ketamine do i give", "PRE_GATE"),
    # Reaches retrieval, comes back INSUFFICIENT, and is still refused the
    # general path by the dosing guard.
    ("how much calcium gluconate for hyperkalemia", "INSUFFICIENT"),
])
def test_end_to_end_dose_question_does_not_fall_back(stub_llm, query, expected_mode):
    """The refusal this feature removes must NOT be removed for dosing."""
    result = run(query, stub_llm)
    assert result["source_mode"] == expected_mode
    assert not gr.has_banner(result["response"])
    assert "GENERAL MEDICAL REFERENCE mode" not in stub_llm.get("system", "")


def test_end_to_end_good_retrieval_is_untouched(stub_llm):
    result = run("massive hemorrhage management", stub_llm, distance=0.2)
    assert result["source_mode"] == "JTS_GROUNDED"
    assert not gr.has_banner(result["response"])


def test_a_dose_line_in_general_mode_is_blocked_and_unbannered(stub_llm):
    """The third guard, end to end: SC-6 holds and the hold is not mislabelled.

    A safety hold is text Python wrote. Labelling it "GENERAL MEDICAL REFERENCE"
    would be a false claim about where it came from — the log still records
    source=general, which is where the attempt came from.
    """
    stub_llm["reply"] = GENERAL_MODE_GIVE_LINE
    result = run("what is a normal serum lactate", stub_llm)
    assert result["source_mode"] == "GENERAL_REFERENCE"
    assert result["validator_result"] == "UNSAFE"
    assert "Clinical safety hold" in result["response"]
    assert not gr.has_banner(result["response"])
    assert oc.knowledge_source(result["source_mode"]) == "general"


def test_a_recipe_in_general_mode_is_served(stub_llm):
    stub_llm["reply"] = GENERAL_PREP_RECIPE
    result = run("how do i mix a norepinephrine drip", stub_llm)
    assert result["source_mode"] == "GENERAL_REFERENCE"
    assert result["validator_result"] == "SAFE"
    assert gr.has_banner(result["response"])
    assert "16 mcg/mL" in result["response"]


def test_non_medical_refusal_is_unchanged(stub_llm):
    """"Too broad / non-medical: keep current refusal behaviour."" """
    result = run("what is the weather in kandahar", stub_llm)
    assert result["source_mode"] == "NON_MEDICAL_PRE_GATE"
    assert result["response"] == "AUSTERE-CDS handles medical queries only."


def test_deterministic_pre_gates_still_win(stub_llm):
    """General mode sits after every pre-gate, so none of them can be bypassed."""
    result = run("failed intubation failed igel patient desaturating", stub_llm)
    assert result["source_mode"] == "DETERMINISTIC_PRE_GATE"
    assert not gr.has_banner(result["response"])


def test_the_selected_model_is_reported_and_used(stub_llm):
    other = next(m for m in oc.providers.MODELS if m != oc.providers.default_model())
    result = run("what is a normal serum lactate", stub_llm, model=other)
    assert stub_llm["model"] == other
    assert result["model"] == oc.model_label(other)


def test_an_unknown_model_falls_back_rather_than_failing(stub_llm):
    """The medic asked a clinical question, not for a particular model."""
    result = run("what is a normal serum lactate", stub_llm, model="gpt-9-turbo")
    assert stub_llm["model"] == oc.providers.default_model()
    assert result["model"] == oc.model_label(oc.providers.default_model())


def test_deterministic_responses_are_attributed_to_no_model(stub_llm):
    """A card Python wrote must not be counted as a model's answer."""
    result = run("failed intubation failed igel patient desaturating", stub_llm)
    assert result.get("model") is None


def test_a_missing_provider_degrades_to_a_system_error_not_a_wrong_answer():
    """With no key, the pipeline fails closed and says so.

    ProviderUnavailable propagates into the pipeline's exception handler, which
    already returns the "use local protocol" system error. What must NOT happen
    is a served clinical answer produced some other way, or a silent SAFE.
    """
    import providers

    def unavailable(*a, **k):
        raise providers.ProviderUnavailable(
            "Anthropic is not configured (ANTHROPIC_API_KEY is unset)")

    original = providers.chat
    providers.chat = unavailable
    try:
        result = oc._query_with_rag_internal(
            "what is a normal serum lactate", FakeChroma(), conversation_history=[])
    finally:
        providers.chat = original

    assert result["source_mode"] == "ERROR"
    assert result["validator_result"] == "ERROR"
    assert "local protocol" in result["response"]
    assert not gr.has_banner(result["response"])


def test_the_validator_model_is_not_the_selected_model(monkeypatch):
    """Pinned end to end: selecting a generator must not move the validator.

    Otherwise a cross-model comparison changes two variables at once and a shift
    in blocked-response rate cannot be attributed to either.
    """
    seen = []

    def record(system, messages, *, model, temperature=0.2, max_tokens=700):
        seen.append(model)
        return "Normal serum potassium is 3.5-5.0 mEq/L." if len(seen) == 1 else \
            '{"result": "SAFE", "issues": [], "rationale": ""}'

    monkeypatch.setattr(oc.providers, "chat", record)
    other = next(m for m in oc.providers.MODELS if m != oc.providers.validator_model())
    oc._query_with_rag_internal("what is a normal serum lactate", FakeChroma(),
                                conversation_history=[], model=other)
    assert seen[0] == other, "the generator must use the selected model"
    assert seen[1] == oc.providers.validator_model(), "the validator must not move"
