"""
EdgeCDSS — brief polish: four format rules, no clinical content.

  1. An age-based contraindication reaches the brief only if it could apply.
     A stated age at or over the threshold, or a confirmed weight no child that
     young has (brief.AGE_CLEARED_BY_WEIGHT_KG), clears it: it stays in the
     CONTRAINDICATIONS section, which then folds. No age and no clearing
     weight, it stays in the brief.
  2. Where a push dilution is declared and the undiluted draw is under 0.2 mL,
     the brief gives the diluted instruction alone. The undiluted volume is
     the Vial math chip's answer.
  3. With one signed presentation the TLDR no longer says "Volume not
     computed" — the volume is computed; the card just has not had the vial
     confirmed. Zero signed presentations keep the sentence.
  4. A volume under 1 mL is drawn to three decimals (draw_precision, #64) and
     never printed with a trailing zero: "0.4 mL", not "0.400 mL". A trailing
     zero after a decimal point is on the ISMP and Joint Commission do-not-use
     lists, because "1.0" is misread as "10". The leading zero stays.

Adult output changes only by 3: the ketamine TLDR sentence.

The suite runs against the pinned test kit in conftest.py, where ketamine has
exactly one signed presentation, 50 mg/mL.

    cd server && ./run_unit_tests.sh
"""
import copy
import os
import re

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief  # noqa: E402
import drug_concentrations as dcn  # noqa: E402
import openai_client as oc  # noqa: E402
from test_brief_chips import CHIPS, _NoRetrieval  # noqa: E402

AGE_LINE = "Contraindicated — ketamine: Age < 3 months."
CARD_CONTRA = ("**GIVE**\n- ketamine IV: 5 mg. Indication: analgesia.\n\n"
               "**CONTRAINDICATIONS**\n"
               "- ketamine — analgesia: Hypersensitivity; Age < 3 months\n")


def _ctx(weight, age=None, ped=True):
    return oc.PatientContext(confirmed_weight_kg=weight, weight_source="stated",
                             route_preference="IV", is_pediatric=ped, age_years=age)


def _run(query, history=None):
    return oc._query_with_rag_internal(query, _NoRetrieval(),
                                       conversation_history=history or [])


# ── 1. age-based contraindications ───────────────────────────────────────────

@pytest.mark.parametrize("age,weight,cleared", [
    (6.0, None, True),     # stated age clears it
    (0.25, None, True),    # exactly 3 months is not under 3 months
    (None, 25.0, True),    # 25 kg is not under 3 months
    (None, 10.0, True),    # the weight floor itself
    (None, 9.9, False),    # a heavy young infant could weigh this
    (None, None, False),   # nothing known: it stays
    (0.1, 25.0, False),    # a stated age under it wins over any weight
])
def test_age_cleared(age, weight, cleared):
    assert brief.age_cleared("Age < 3 months", age, weight) is cleared


def test_a_threshold_with_no_weight_floor_is_cleared_by_age_alone():
    assert brief.age_cleared("Age < 2 years", None, 40.0) is False
    assert brief.age_cleared("Age < 2 years", 3.0, None) is True
    assert brief.age_cleared("Age < 2 years", 1.5, 40.0) is False


def test_only_age_contraindications_are_cleared():
    assert brief.age_cleared("Increased intracranial pressure", 30.0, 80.0) is False


def test_a_cleared_age_contraindication_leaves_the_brief_and_folds():
    out = brief.build_brief(CARD_CONTRA, oc.MEDICATION_TERMS, weight_kg=25.0)
    assert AGE_LINE not in out["brief"]
    assert "CONTRAINDICATIONS" not in out["critical_sections"]
    out = brief.build_brief(CARD_CONTRA, oc.MEDICATION_TERMS, weight_kg=5.0, age_years=6.0)
    assert AGE_LINE not in out["brief"]


def test_with_age_unknown_the_age_contraindication_stays():
    for weight in (None, 5.0):
        out = brief.build_brief(CARD_CONTRA, oc.MEDICATION_TERMS, weight_kg=weight)
        assert AGE_LINE in out["brief"], weight
        assert "CONTRAINDICATIONS" in out["critical_sections"]


def test_a_cleared_part_leaves_the_rest_of_the_item():
    text = CARD_CONTRA.replace("Age < 3 months", "Age < 3 months; Globe injury")
    b = brief.build_brief(text, oc.MEDICATION_TERMS, weight_kg=25.0)["brief"]
    assert "Contraindicated — ketamine: Globe injury." in b and "Age" not in b


def test_the_served_card_keeps_the_line_the_brief_drops():
    r = _run("ketamine IV for pain, 6 year old 25kg child, IV access")
    assert r["patient_context"]["age_years"] == 6.0
    assert AGE_LINE not in r["brief"]
    assert "Age < 3 months" in r["response"].split("**CONTRAINDICATIONS**")[1]


# ── 2. the undiluted volume moves to Vial math ───────────────────────────────

def test_the_brief_gives_the_diluted_instruction_alone_under_0_2_ml():
    card = oc.build_ketamine_analgesia_response(_ctx(25.0, 6.0))
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=25.0, age_years=6.0)["brief"]
    assert b.splitlines()[0] == (
        "ketamine IV: 5 mg (0.2 mg/kg × 25 kg). Dilute first — 5 mg/mL "
        "(1 mL of 50 mg/mL + 9 mL normal saline): 1 mL — confirm vial.")


def test_the_vial_math_chip_carries_the_undiluted_volume():
    q = "ketamine IV for pain, 6 year old 25kg child, IV access"
    first = _run(q)
    chip = _run(CHIPS["Vial math"], [{"query": q, "response": first["response"]}])
    assert chip["source_mode"] == "PRE_GATE"
    assert chip["response"] == (
        "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)? "
        "Vial math — ketamine IV 5 mg: 0.1 mL of 50 mg/mL undiluted — confirm vial.")
    # It is on the chip's first screen too, not only in the response.
    assert "0.1 mL of 50 mg/mL undiluted" in chip["brief"]


def test_the_vial_math_chip_adds_nothing_for_an_adult():
    q = "ketamine IV for pain 80kg adult, IV access"
    first = _run(q)
    chip = _run(CHIPS["Vial math"], [{"query": q, "response": first["response"]}])
    assert chip["response"] == "Which ketamine do you have — 500 mg / 10 mL vial (50 mg/mL)?"


def test_no_dilution_no_withheld_volume():
    assert dcn.vial_math_line("ketamine", 5.0, None) == ""
    assert dcn.conditional_volume_line("ketamine", 5.0, None) == \
        "At 50 mg/mL that's 0.1 mL — confirm vial."


# ── 3. the stale TLDR sentence ───────────────────────────────────────────────

def test_one_signed_vial_the_tldr_states_the_mg_alone():
    card = oc.build_ketamine_analgesia_response(_ctx(25.0, 6.0))
    tldr = card.split("**TLDR**")[1].split("**")[0]
    assert tldr.strip() == "- PEDIATRIC PATIENT: ketamine IV = 5mg."
    # The GIVE line's fail-closed marker and CONFIRM VIAL are untouched.
    assert "ketamine IV: 5 mg. NO VOLUME" in card and "**CONFIRM VIAL**" in card


def test_nothing_signed_the_tldr_still_says_volume_not_computed(monkeypatch):
    entries = copy.deepcopy(dcn.ENTRIES)
    for p in entries["ketamine"]["presentations"]:
        p["signoff"] = False
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    assert dcn.signed_presentations("ketamine") == []
    card = oc.build_ketamine_analgesia_response(_ctx(80.0, ped=False))
    assert "Volume not computed — " in card.split("**TLDR**")[1]


# ── 4. three decimals, no trailing zero ──────────────────────────────────────

_TRAILING_ZERO_RE = re.compile(r"\b\d+\.\d*0 ?mL\b")


@pytest.mark.parametrize("query", [
    "ketamine IV for pain, 6 year old 25kg child, IV access",
    "ketamine IV for pain, 50kg 12 year old child, IV access",
    "ketamine IV for pain 80kg adult, IV access",
    "RSI an 80kg male trauma patient ketamine and rocuronium",
])
def test_no_volume_is_printed_with_a_trailing_zero(query):
    r = _run(query)
    confirmed = _run("500 mg / 10 mL vial (50 mg/mL)",
                     [{"query": query, "response": r["response"]}])
    for text in (r["response"], r["brief"], confirmed["response"], confirmed["brief"]):
        assert not _TRAILING_ZERO_RE.search(text), _TRAILING_ZERO_RE.search(text).group(0)


def test_a_sub_millilitre_draw_keeps_three_decimals_and_its_leading_zero():
    ctx = _ctx(25.0, 6.0)
    assert dcn.single_signed_volume("ketamine", 6.25) == (0.125, 50.0)
    assert dcn.conditional_volume_line("ketamine", 6.25) == \
        "At 50 mg/mL that's 0.125 mL — confirm vial."
    ctx = _ctx(80.0, ped=False)
    ctx.confirmed_concentrations = {"ketamine": 50.0}
    card = oc.build_ketamine_analgesia_response(ctx)
    assert "Draw 0.4 mL of 50mg/mL ketamine IV (20 mg)" in card
    audited, issues = oc.audit_volume_lines(card, ctx)
    assert issues == [] and audited == card


# ── adults ───────────────────────────────────────────────────────────────────

def test_the_adult_rsi_brief_is_unchanged():
    b = _run("RSI an 80kg male trauma patient ketamine and rocuronium")["brief"]
    assert b.splitlines()[0] == (
        "[RSI induction] ketamine IV: 160 mg (2 mg/kg × 80 kg). At 50 mg/mL that's "
        "3.2 mL — confirm vial. · [RSI paralytic] Draw 9.6 mL of 10mg/mL rocuronium IV "
        "(96 mg) (1.2 mg/kg × 80 kg). · [post-intubation sedation — repeated bolus "
        "(no infusion pump)] ketamine IV: 40 mg (0.5 mg/kg × 80 kg). At 50 mg/mL "
        "that's 0.8 mL — confirm vial.")
    assert "Dilute" not in b and "Age <" not in b
