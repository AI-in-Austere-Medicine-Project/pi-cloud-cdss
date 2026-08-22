"""
F-7 — an acute question gets the action format, whichever tier answers it.

Baseline evidence (runs/baseline-gpt4omini): 43 of 132 served answers came
through GENERAL_REFERENCE, and 45 of 48 had no **TLDR** at all.

    band                has TLDR   no TLDR
    JTS_GROUNDED           17         2
    GENERAL_MEDICAL        42         7
    GENERAL_REFERENCE       3        45
    deterministic card     16         0

That shape is correct for the tier it was designed for — lab values,
toxicology, envenomation, drug preps. It was being applied to:

    G-MTN-01  "he's tanking, BP is 78/44 now and he's grey"
    G-MTN-08  "his sugar came back at 32, he's confused"
    G-BRN-06  "circumferential burn, fingers are getting dusky, what now"
    G-TYP-07  "hypothermic arest, found in the snow, no pulse"

all answered in three sentences of prose with no actions, no TLDR and no
evacuation trigger — because use_general_reference fires on
source_mode == "INSUFFICIENT" and nothing else, so a RETRIEVAL MISS silently
changed the response format.
"""
import pytest

import general_reference as gr
from openai_client import PatientContext, extract_patient_context

ACUTE_MARKERS = ("**DO THIS**", "**WATCH**", "**TLDR**")


def prompt(acute):
    return gr.build_system_prompt(patient_block="ADULT PATIENT", acute=acute)


# ── the selector ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,vitals,expected", [
    ("he's tanking, BP is 78/44 now and he's grey", True, True),
    ("his sugar came back at 32, he's confused", True, True),
    ("circumferential burn to the forearm, fingers are getting dusky, what now",
     False, True),
    ("hypothermic arest, found in the snow, no pulse", False, True),
    ("susected tention pneumo, trachea deviated, what now", False, True),
    ("what do I do first", False, True),
    # Reference questions. No patient, no imperative.
    ("what are the normal reference ranges for serum lactate", False, False),
    ("what does dengue warning-signs criteria actually mean at the bedside",
     False, False),
    ("how do I mix a norepinephrine drip", False, False),
    ("typhoid versus typhus, how do I tell them apart with no lab", False, False),
    ("what is the diagnostic approach to acute jaundice in a returning traveller",
     False, False),
])
def test_is_acute_presentation(query, vitals, expected):
    assert gr.is_acute_presentation(query, vitals_present=vitals) is expected


def test_any_recorded_vital_makes_it_acute():
    """A vital in the session means a patient in front of the medic. The
    cheapest possible signal, and stated by the medic rather than inferred."""
    ctx = extract_patient_context("he's tanking, BP is 78/44 now and he's grey")
    assert ctx.vitals
    assert gr.is_acute_presentation("what now", vitals_present=bool(ctx.vitals))
    assert gr.is_acute_presentation("anything at all",
                                    vitals_present=bool(PatientContext().vitals)) is False


# ── the prompt ──────────────────────────────────────────────────────────────

def test_general_reference_uses_action_format_when_vitals_present():
    """G-MTN-01's tier, with the format it should have had."""
    p = prompt(acute=True)
    for marker in ACUTE_MARKERS:
        assert marker in p, marker
    assert "FORMAT OVERRIDE — ACUTE PRESENTATION" in p


def test_reference_questions_keep_the_reference_register():
    """H-IM-12's tier, unchanged. The negative that stops this becoming a
    blanket format change."""
    p = prompt(acute=False)
    assert "**DO THIS**" not in p
    assert "FORMAT OVERRIDE" not in p
    assert "A reference card, not an essay" in p


def test_the_content_rules_hold_on_both_registers():
    """The ruling changes the SHAPE of an acute answer and nothing else.

    Recipe-yes-prescription-no, the referral sentence and the 150-word cap are
    what keep this tier safe; a format override that relaxed any of them would
    be a different change wearing this one's clothes.
    """
    for acute in (True, False):
        p = prompt(acute)
        assert "Draw X mL of Y mg/mL" in p
        assert "150 words" in p
        assert gr.REFERRAL_BASE in p
        assert "You MAY NOT give a dose for a patient" in p
        assert "AUSTERE-CDS handles medical queries only." not in p


def test_the_acute_block_says_the_other_rules_still_apply():
    """A format override that reads as a fresh start is one the model will
    treat as a fresh start."""
    assert "Everything" in gr.ACUTE_FORMAT_BLOCK
    assert "no dose for a patient" in gr.ACUTE_FORMAT_BLOCK
    assert "150-word cap" in gr.ACUTE_FORMAT_BLOCK


def test_acuteness_does_not_read_the_retrieval_score():
    """The whole point. Tier SHAPE must stop being a side-effect of a miss."""
    import inspect
    source = inspect.getsource(gr.is_acute_presentation)
    for forbidden in ("source_mode", "top_score", "INSUFFICIENT", "retrieval"):
        assert forbidden not in source, forbidden


def test_the_default_is_unchanged_behaviour():
    """build_system_prompt's new argument defaults to the old register, so a
    caller that has not been updated cannot silently change format."""
    assert gr.build_system_prompt() == gr.build_system_prompt(acute=False)
    assert "FORMAT OVERRIDE" not in gr.build_system_prompt()
