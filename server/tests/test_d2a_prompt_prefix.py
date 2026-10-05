"""D2a (owner, work order D2; split 2026-10-05): prompt layout for prefix caching.

Everything fixed first, everything per-query last, so Ollama (and any provider
with prefix caching) reuses the KV cache across queries. The generator spliced
the patient block into the MIDDLE of its fixed text (ahead of SCOPE), so the
shared prefix ended at the first patient. Same content, different order: the
rendered prompt must hold exactly the lines it held before.

The general-reference prompt (fixed text, then the acute block, the referral
sentence, the patient) and the validator (fixed system prompt; everything
per-query in the user turn) are already in prefix order; they are pinned here
so they stay that way.
"""
import collections
import os

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import general_reference  # noqa: E402
import openai_client as oc  # noqa: E402

ASSESS = oc.RetrievalAssessment(source_mode="JTS_GROUNDED", top_score=0.5,
                                context_text="RETRIEVED CHUNK TEXT", sources=[])
DOSES = "ALLOWED_DOSES:\n- fentanyl IV 0.05 mg"


def _ctx(weight, age=None):
    return oc.PatientContext(confirmed_weight_kg=weight, age_years=age, weight_source="stated")


def _main_layout(ctx, assessment, dose_block):
    """The layout on main before D2a, kept here to compare content against."""
    patient_block = oc.build_patient_block(ctx)
    source_block = oc.build_source_block(assessment)
    prompt = oc.GENERATOR_BASE
    if patient_block:
        prompt = prompt.replace(
            oc.GENERATOR_SCOPE_ANCHOR,
            f"────────────────────────────────\nPATIENT CONTEXT\n────────────────────────────────\n\n{patient_block}\n\n{oc.GENERATOR_SCOPE_ANCHOR}")
    prompt += f"\n\n────────────────────────────────\nRETRIEVED PROTOCOL CONTEXT\n────────────────────────────────\n\n{source_block}"
    prompt += f"\n\n────────────────────────────────\n{dose_block}\n────────────────────────────────"
    return prompt


def test_the_fixed_text_is_the_whole_prefix():
    a = oc.build_system_prompt(_ctx(80.0), ASSESS, DOSES)
    b = oc.build_system_prompt(_ctx(20.0, 6), ASSESS, DOSES)
    assert a.startswith(oc.GENERATOR_BASE) and b.startswith(oc.GENERATOR_BASE)


def test_same_content_different_order():
    for ctx in (_ctx(80.0), _ctx(20.0, 6), oc.PatientContext()):
        new = oc.build_system_prompt(ctx, ASSESS, DOSES)
        old = _main_layout(ctx, ASSESS, DOSES)
        assert collections.Counter(l for l in new.splitlines() if l.strip()) == \
            collections.Counter(l for l in old.splitlines() if l.strip())


def test_per_query_blocks_come_after_the_fixed_text_in_order():
    p = oc.build_system_prompt(_ctx(80.0), ASSESS, DOSES)
    fixed_end = len(oc.GENERATOR_BASE)
    i_ret = p.index("RETRIEVED PROTOCOL CONTEXT")
    i_pat = p.index("PATIENT CONTEXT", fixed_end)
    i_dose = p.index("ALLOWED_DOSES:\n- fentanyl")
    assert fixed_end <= i_ret < i_pat < i_dose


def test_no_patient_no_patient_section():
    p = oc.build_system_prompt(oc.PatientContext(), ASSESS, DOSES)
    assert "\nPATIENT CONTEXT\n" not in p[len(oc.GENERATOR_BASE):]


def test_the_general_reference_prompt_is_already_fixed_first():
    p = general_reference.build_system_prompt("Weight: 80 kg (confirmed)",
                                              weight_confirmed=True, acute=True)
    assert p.startswith(general_reference.GENERAL_REFERENCE_PROMPT)
    assert p.index("REFERRAL SENTENCE") < p.index("PATIENT CONTEXT")


def test_the_validator_sends_the_same_system_prompt_for_every_patient(monkeypatch):
    import providers
    systems = []
    monkeypatch.setattr(providers, "chat", lambda system, messages, **k:
                        systems.append(system) or '{"result":"SAFE","issues":[],"rationale":"ok"}')
    for ctx in (_ctx(80.0), _ctx(20.0, 6)):
        oc.validate_response("Q: pain", "Give fentanyl.", ctx, DOSES)
    assert systems == [oc.VALIDATOR_PROMPT, oc.VALIDATOR_PROMPT]
