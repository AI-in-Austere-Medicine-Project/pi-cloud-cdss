"""Indication-only questions (owner, 2026-10-14; the v1.1 finding from #97).

A question that names an injury or an indication but no drug used to build an
empty ALLOWED_DOSES: the builder looks doses up by drug name. The generator
then wrote a dose of its own and the check held it, although the bank has a
signed entry for exactly that indication. Seen live on 2026-10-14: "80 kg
adult, severe pain from a closed femur fracture, IV access, what can I give"
held three times (qwen2.5:3b twice, edgecdss-v3 once); asked by drug name, the
same question was served.

The fix: with no drug named, the indication the question states selects the
signed entries for that indication, so the model is offered the dose instead
of inventing one. The check is unchanged: a dose that is not the offered one
still holds.
"""
import pytest

import openai_client as oc

FEMUR = "80 kg adult, severe pain from a closed femur fracture, IV access, what can I give"

# The three answers held on the live service, 2026-10-14 (held_response, log schema 16).
HELD_QWEN_GIVE_LINE = """**BRIEF**
- Draw 0.075 mL of 50mg/mL ketamine IV (7.5mg). Indication: analgesia.

**DO THIS**
1. Draw 0.075 mL of 50mg/mL ketamine IV (7.5mg).
2. Administer ketamine for analgesia.
3. Monitor vital signs.

**GIVE**
- Draw 0.075 mL of 50mg/mL ketamine IV (7.5mg). Indication: analgesia.

**WATCH**
- BP, HR, SpO₂
"""

HELD_V3_DISSOCIATIVE = """**BRIEF**
- Analgesia first — treat pain before sedation; no meds at first if the patient is unstable.
- Start with 1–2 mg/kg slow IV push of analgesic (ketamine or ketamine subdissociative).
- Sedation as a second step, once pain is controlled; IM dose for longer duration (300 mg IM or 2–3 mg/kg IM).

**DO THIS**
1. Give 1–2 mg/kg slow IV push of ketamine (ketamine subdissociative) for analgesia; if unstable or no improvement, transition to IM/IV push of the higher dose (300 mg IM or 2–3 mg/kg IM) for prolonged use.
"""

HELD_QWEN_RANGE = """**BRIEF**
- Ketamine 1–2 mg/kg IV (30–60 mg)
- Monitor RASS and CAM.

**GIVE**
- Draw 30–60 mg of ketamine IV (30–60 mg).
"""


def _ctx(q):
    return oc.rebuild_patient_context_from_history(q)


def _doses(q):
    return oc.build_allowed_doses(q, _ctx(q))


def test_the_femur_question_is_offered_the_signed_ketamine_analgesia_dose():
    doses = _doses(FEMUR)
    ket = [d for d in doses if d.drug == "ketamine" and d.route == "IV"
           and d.indication == "moderate to severe pain / analgesia"]
    assert len(ket) == 1, [(d.drug, d.indication, d.route) for d in doses]
    assert ket[0].dose_mg == pytest.approx(20.0)        # 0.25 mg/kg x 80 kg, under the 25 mg cap


def test_only_entries_signed_for_pain_are_offered():
    doses = _doses(FEMUR)
    assert doses
    for d in doses:
        assert "pain" in d.indication, (d.drug, d.indication)
        assert not any(w in d.indication.lower() for w in ("rsi", "sedation", "seizure", "agitated"))


@pytest.mark.parametrize("answer", [HELD_QWEN_GIVE_LINE, HELD_V3_DISSOCIATIVE, HELD_QWEN_RANGE],
                         ids=["qwen-7.5mg", "v3-1-2mg/kg", "qwen-30-60mg"])
def test_the_answers_held_live_still_hold(answer):
    """None of them states the offered dose: offering the right one releases nothing wrong."""
    issues = oc.run_deterministic_checks(FEMUR, answer, _ctx(FEMUR), _doses(FEMUR)).issues
    assert any("ketamine" in i.lower() for i in issues), issues


def test_an_answer_copying_the_offered_give_line_passes_the_dose_check():
    doses = _doses(FEMUR)
    ket = next(d for d in doses if d.drug == "ketamine" and d.indication == "moderate to severe pain / analgesia")
    answer = ("**BRIEF**\n- Ketamine for severe femur fracture pain.\n\n**GIVE**\n"
              + oc.render_give_line(ket) + "\n\n**WATCH**\n- RR, SpO2, BP\n")
    assert oc.free_text_dose_issues(answer, doses, _ctx(FEMUR), FEMUR) == []
    assert not [i for i in oc.run_deterministic_checks(FEMUR, answer, _ctx(FEMUR), doses).issues
                if "ketamine" in i.lower() or "allowed_doses" in i.lower()]


def test_no_drug_and_no_indication_is_still_offered_nothing():
    assert _doses("80 kg adult, what can I give") == []


def test_a_named_drug_still_goes_by_name():
    q = "80 kg adult, ketamine for severe pain from a femur fracture, IV access"
    named = _doses(q)
    assert {d.drug for d in named} == {"ketamine"}


# ── #97's case: the arrest dose for an arrest named without a drug ─────────────

@pytest.mark.parametrize("q", [
    "70 kg adult in asystole, what do I give",
    "cardiac arrest, 70kg male, what drug",
    "70 kg adult, PEA arrest, CPR in progress, what do I push",
])
def test_an_arrest_named_without_a_drug_is_offered_the_signed_arrest_dose(q):
    doses = _doses(q)
    epi = [d for d in doses if d.drug == "epinephrine" and d.indication == "cardiac arrest"]
    assert len(epi) == 1, [(d.drug, d.indication) for d in doses]
    assert epi[0].dose_mg == pytest.approx(1.0)
    assert all(d.indication == "cardiac arrest" for d in doses)


@pytest.mark.parametrize("q", [
    "70 kg adult, tourniquet on the left leg, no distal pulse, what can I give",
    "70 kg adult, pulseless left foot after a femur fracture, what can I give",
])
def test_a_pulseless_limb_is_not_an_arrest(q):
    assert not [d for d in _doses(q) if d.indication == "cardiac arrest"]


# ── Narrowed by the replay (2026-10-14): an offer is close to an instruction ──
# The generator must copy a GIVE line when ALLOWED_DOSES is present, so a
# drugless question is offered a dose only when THIS turn asks about the
# indication. Each case below was offered a dose in the first replay.

@pytest.mark.parametrize("q", [
    "antibiotic dose for the open femur fracture",
    "open book pelvic fracture from a fall, how do I bind it and what do I watch for",
    "suspected typhoid with abdominal pain, what antibiotic",
    "scratch that, wrong patient, this one is a 70yo with chest pain and a rate of 38",
    "Hey, I just are aside a post cardiac arrest patient blood pressure is 90/70. Heart rate is 110",
    "70 kg adult, ROSC after cardiac arrest, what now",
    "give her keta mean for the pain",
])
def test_no_offer_when_the_turn_is_not_asking_about_that_indication(q):
    assert oc.indication_only_patterns(q) == []


def test_an_earlier_turns_pain_is_not_this_turns_question():
    history = "80 kg adult, severe pain from a closed femur fracture, IV access he is bleeding out from a leg wound, what do I give him"
    current = "he is bleeding out from a leg wound, what do I give him"
    ctx = oc.rebuild_patient_context_from_history(history)
    assert not [d for d in oc.build_allowed_doses(history, ctx, current_query=current)
                if "pain" in d.indication]


def test_an_opioid_is_not_volunteered_against_a_respiratory_caution():
    q = "femur fracture, screaming in pain, RR is 8, what analgesia do I give"
    offered = {d.drug for d in _doses(q)}
    assert not offered & {"fentanyl", "morphine"}, offered
