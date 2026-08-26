"""
EdgeCDSS — the patient context the logs print must be the context the flow uses.

The live case, 2026-08-21 ~09:49-09:53Z, burn scenario testing. The pipeline
printed:

    👤 confirmed_wt=77.1 est_wt=None ped=False route=UNKNOWN access=UNKNOWN
    🛡️ Validator [NEEDS_HUMAN_REVIEW]:
       ['Response recommends fluid resuscitation without confirmed weight for
         pediatric patient.']
       "the patient's weight is confirmed as 77.1 kg, which is not pediatric.
        However, the context does not specify if the patient is pediatric or
        adult, leading to a need for human review."

and three minutes later asked the medic for a weight the session had held all
along.

Two defects, and neither was the obvious one:

  (a) The validator was NOT starved of context. It quoted 77.1 back, so the
      weight reached it. What it did not receive was any statement of AGE BAND:
      build_patient_block asserted "PEDIATRIC PATIENT" when the flag was true
      and said NOTHING when it was false, so "known adult" and "nobody has said"
      were the same silence. Its rationale is a faithful report of an asymmetric
      prompt, not a self-contradiction.

  (b) The re-ask came from the general-reference path. A burn query with
      INSUFFICIENT retrieval lands there, and its HARD LIMIT carried a fixed
      sentence — "ask again with the patient's weight in kg and route" —
      unconditional on a confirmed weight printed further down the same prompt.

These assert on PROMPT CONTENT, offline and with no keys: what the model is
handed is the part this repo controls, and the part that was wrong.

    cd server && ./run_unit_tests.sh
"""

import os
import sys

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import general_reference as gr  # noqa: E402
import openai_client as oc  # noqa: E402

TS = "2026-08-21T09:49:00+00:00"

# The session shape from the log line, rebuilt through the real pipeline:
# a confirmed adult weight, no stated age, then a burn fluid question.
LIVE_HISTORY = [{"query": "burn patient, he weighs 77.1 kg", "ts": TS}]
LIVE_QUERY = "70% TBSA burns, what fluid resuscitation does he need?"


@pytest.fixture
def live_ctx():
    ctx = oc.rebuild_patient_context_from_history(
        LIVE_QUERY, conversation_history=LIVE_HISTORY, now_ts=TS)
    # The fixture is only meaningful if it reproduces the logged state.
    assert ctx.confirmed_weight_kg == 77.1
    assert ctx.is_pediatric is False
    assert ctx.age_years is None
    return ctx


# ── (a) the age band is stated, never implied by silence ────────────────────

def test_the_block_states_the_age_band_in_every_case():
    """is_pediatric False means "adult" OR "nobody said". Both must be legible.

    This is the whole defect: a rule that keys on paediatric status cannot be
    evaluated against a silence.
    """
    def band(**kw):
        return oc.age_band_line(oc.PatientContext(**kw))

    assert band(is_pediatric=True) == "PEDIATRIC PATIENT"
    assert "ADULT PATIENT" in band(age_years=45.0)
    assert "NOT pediatric" in band(confirmed_weight_kg=77.1)
    assert "UNKNOWN" in band(), "no age and no weight is unknown, not adult"


def test_the_live_case_no_longer_leaves_pediatric_status_unstated(live_ctx):
    """The exact sentence the validator complained about is now answered."""
    block = oc.build_patient_block(live_ctx, now_ts=TS)
    assert "NOT pediatric" in block
    assert "77.1" in block
    assert block.splitlines()[0].strip(), "the age band leads the block"


def test_an_unknown_age_band_is_not_reported_as_adult():
    """The same failure pointing the other way.

    Asserting "ADULT" with no age and no weight would be the system claiming
    something nobody told it — which is what this whole block exists not to do.
    """
    block = oc.build_patient_block(oc.PatientContext())
    assert "ADULT" not in block
    assert "UNKNOWN" in block


def test_the_validator_receives_the_block_the_logs_print(live_ctx, monkeypatch):
    """Not "is it serialized" — is it in the bytes the validator model is sent.

    Captured at the provider boundary, which is the last point before the
    network and the only place the answer is not an assumption.
    """
    captured = {}

    def fake_chat(system, messages, **kw):
        captured["system"] = system
        captured["user"] = messages[0]["content"]
        return '{"result":"SAFE","issues":[],"rationale":"ok"}'

    monkeypatch.setattr(oc.providers, "chat", fake_chat)
    monkeypatch.setattr(oc.providers, "validator_model", lambda: "test-model")
    oc.validate_response("CURRENT USER: " + LIVE_QUERY,
                         "Start Parkland at 2 mL/kg/%TBSA.", live_ctx, now_ts=TS)

    assert "PATIENT CONTEXT:" in captured["user"]
    assert "77.1" in captured["user"], "the confirmed weight never reached the validator"
    assert "NOT pediatric" in captured["user"], \
        "the validator cannot rule on a pediatric rule it was told nothing about"


def test_the_validator_prompt_says_a_confirmed_weight_satisfies_the_rule(live_ctx):
    """The rule fired WITH a confirmed weight present, so the rule text had to
    say what a confirmed weight does. It now does, and says not to ask for one."""
    p = oc.VALIDATOR_PROMPT
    assert "SATISFIES this rule" in p
    assert "never ask for" in p.lower() or "do not ask for" in p.lower()
    assert "NEVER FROM WHAT IT OMITS" in p


# ── (b) the flow must not ask for a weight it holds ─────────────────────────

def test_a_burn_fluid_query_with_a_confirmed_weight_falls_to_general_reference(live_ctx):
    """Pins the route, so the assertions below are about the path that ran.

    If retrieval or the fallback rule changes so this no longer lands on the
    general-reference path, this test should fail loudly rather than keep
    asserting about a prompt nobody builds any more.
    """
    assert gr.use_general_reference(
        "INSUFFICIENT", LIVE_QUERY, [], oc.wants_medication_dose(LIVE_QUERY),
        patient_known=True) is True


def test_the_referral_sentence_asks_only_for_what_the_session_lacks():
    assert "weight in kg" in gr.dosing_referral(False, False)
    assert "weight" not in gr.dosing_referral(True, False)
    assert "route" in gr.dosing_referral(True, False)
    both = gr.dosing_referral(True, True)
    assert "ask again with" not in both
    assert "already has the weight and route" in both


def test_the_general_reference_prompt_does_not_re_ask_for_a_confirmed_weight(live_ctx):
    """The served defect, at the only place it can be pinned offline.

    The prompt used to carry "ask again with the patient's weight in kg" and
    "Confirmed weight: 77.1kg" at the same time.
    """
    prompt = gr.build_system_prompt(
        oc.build_patient_block(live_ctx, now_ts=TS),
        weight_confirmed=live_ctx.has_confirmed_weight,
        route_known=live_ctx.route_preference != "UNKNOWN")
    assert "77.1" in prompt, "the fixture no longer carries a confirmed weight"
    assert "weight in kg" not in prompt, \
        "the prompt asks for a weight it is printing thirty lines below"
    assert "Do not ask for a weight the context already states." in prompt


def test_a_session_with_no_weight_is_still_asked_for_one():
    """The fix must not cost the ask where the ask is correct."""
    prompt = gr.build_system_prompt(oc.build_patient_block(oc.PatientContext()),
                                    weight_confirmed=False, route_known=False)
    assert "weight in kg" in prompt


def test_general_reference_still_refuses_to_dose(live_ctx):
    """Knowing the weight is not permission to use it. There is no ALLOWED_DOSES
    contract on this path by construction, and that has not changed."""
    prompt = gr.build_system_prompt(
        oc.build_patient_block(live_ctx, now_ts=TS), weight_confirmed=True)
    assert "You MAY NOT give a dose for a patient." in prompt
    assert "Dosing goes through the protocol path" in prompt
    assert "Do not dose against it." in prompt
    assert "ALLOWED_DOSES" not in prompt


# ── the whole session shape, through the real pipeline ──────────────────────

def test_the_live_session_produces_no_pediatric_claim_and_no_weight_re_ask(live_ctx):
    """The fixture the report asked for: confirmed adult weight + burn fluid
    query, pinning that nothing downstream calls this patient paediatric and
    nothing asks for the weight again."""
    generator = oc.build_system_prompt(
        live_ctx,
        oc.RetrievalAssessment(source_mode="INSUFFICIENT", top_score=0.055,
                               context_text="", sources=[]),
        allowed_dose_block="", now_ts=TS)
    reference = gr.build_system_prompt(
        oc.build_patient_block(live_ctx, now_ts=TS), weight_confirmed=True)

    for name, prompt in (("generator", generator), ("general reference", reference)):
        assert "PEDIATRIC PATIENT" not in prompt, f"{name} calls an adult paediatric"
        assert "NOT pediatric" in prompt, f"{name} leaves the age band unstated"
        assert "77.1" in prompt, f"{name} lost the confirmed weight"
        assert "Need weight in kg before dosing." not in prompt, \
            f"{name} asks for a weight the session holds"


def test_the_pre_gate_does_not_ask_an_adult_for_a_weight_it_has(live_ctx):
    """The deterministic half. A confirmed weight satisfies the weight gate,
    and a patient who is not paediatric never reaches it."""
    action, response = oc.pre_gate("how much fluid does he need?", live_ctx,
                                   prior_queries=LIVE_HISTORY[0]["query"])
    assert action == "CONTINUE", f"pre-gate asked: {response!r}"
