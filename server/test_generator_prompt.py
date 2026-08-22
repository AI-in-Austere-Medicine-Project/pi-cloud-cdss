"""
F-2 — the generator has no refusal sentence.

Baseline evidence (runs/baseline-gpt4omini): 22 of 160 scenarios, 13.8% of the
bank, were answered "AUSTERE-CDS handles medical queries only." Every one had
already passed is_non_medical_query() and reached the generator, so the
deterministic gate that owns the decision had explicitly declined to refuse.

    G-GEN-01  retrieval 0.423, JTS_GROUNDED  "what should I document on a
              casualty card for a prolonged field care handover"
    G-GEN-05  retrieval 0.418, JTS_GROUNDED  "criteria for terminating
              resuscitation in the field"
    H-IM-12   "reference ranges for serum lactate"   — named in reference scope
    G-ADV-10  "standard dilution for a keppra bag"   — the recipe tier
    H-IM-13   "how many mg of morphine ..."          — should be the referral
    H-SESS-001/003/005  "150lbs" / "17 kg" / "34kg"  — answers to the system's
              own weight question

The sentence was in both system prompts, as a one-line rule with no scoping,
which made it the lowest-energy output for anything the model found awkward.
"""
import inspect

import general_reference as gr
import openai_client as oc

REFUSAL = "AUSTERE-CDS handles medical queries only."


def test_generator_never_emits_the_non_medical_refusal():
    """The bank-wide invariant, asserted where it can be: the sentence is not
    available to either generator prompt.

    Stated as a property of the prompts rather than of any one answer, because
    the failure was a class — six different query shapes reached for the same
    sentence — and a per-case assertion would close six of them.
    """
    assert REFUSAL not in oc.GENERATOR_BASE
    assert REFUSAL not in gr.GENERAL_REFERENCE_PROMPT
    assert REFUSAL not in gr.build_system_prompt(patient_block="ADULT PATIENT")
    ctx = oc.PatientContext()
    assessment = oc.RetrievalAssessment(source_mode="JTS_GROUNDED", top_score=0.5,
                                        context_text="chunk", sources=[])
    assert REFUSAL not in oc.build_system_prompt(ctx, assessment, "")


def test_the_deterministic_gate_still_owns_the_decision():
    """Deleting the prompt rule must not delete the capability.

    is_non_medical_query is the sole owner now, so it has to still work — and
    the pipeline still has to return the sentence when it fires.
    """
    assert oc.is_non_medical_query("what is the weather in Austin today") is True
    assert oc.is_non_medical_query("tell me a joke") is True
    assert oc.is_non_medical_query("what should I document on a casualty card") is False
    assert oc.is_non_medical_query("150lbs") is False
    source = inspect.getsource(oc._run_pipeline)
    assert REFUSAL in source, "the pre-gate must still be able to say it"


def test_both_prompts_say_the_query_was_already_accepted():
    """The replacement is not a deletion — the model is told why it has no
    refusal, so it does not invent a substitute one."""
    for prompt in (oc.GENERATOR_BASE, gr.GENERAL_REFERENCE_PROMPT):
        assert "already been judged clinical" in prompt
        assert "no refusal sentence" in prompt


def test_the_referral_sentence_is_the_only_refusal_on_the_dosing_path():
    prompt = gr.build_system_prompt(patient_block="ADULT PATIENT")
    assert gr.REFERRAL_BASE in prompt
    assert "ONLY refusal available on this path" in gr.GENERAL_REFERENCE_PROMPT
    assert REFUSAL not in prompt


def test_the_patient_block_still_reaches_the_generator_prompt():
    """The block was spliced onto the heading F-2 deleted.

    A rename that missed the splice would drop patient context out of the
    prompt with no error anywhere — the exact silent-failure shape S-1 was.
    """
    ctx = oc.PatientContext(confirmed_weight_kg=80.0)
    assessment = oc.RetrievalAssessment(source_mode="JTS_GROUNDED", top_score=0.5,
                                        context_text="chunk", sources=[])
    prompt = oc.build_system_prompt(ctx, assessment, "")
    assert "PATIENT CONTEXT" in prompt
    assert "80" in prompt
    assert oc.GENERATOR_SCOPE_ANCHOR in oc.GENERATOR_BASE, (
        "the splice anchor must exist in the text it splices into")
    assert prompt.index("PATIENT CONTEXT") < prompt.index("VOICE-FIRST STYLE")
