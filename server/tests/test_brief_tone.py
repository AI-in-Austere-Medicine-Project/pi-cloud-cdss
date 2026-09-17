"""
EdgeCDSS — the brief's tone: three slots, computed volume, specific contraindications.

Format only. Every sentence in a brief traces to text the card already carries
or to a value computed from what the card was computed from. Pinned here:

  - a dosing brief has three slots, in order: (a) the dose line verbatim, with
    its per-kg basis when it was weight-computed; (b) the card's first real
    next action, not equipment preamble; (c) a contraindication only when it is
    specific to this indication;
  - with exactly one signed presentation, a no-volume dose line carries the
    volume conditionally ("At 50 mg/mL that's 0.12 mL — confirm vial"); with
    zero or several, the card's own reason stays, in sentence case;
  - hypersensitivity / allergy boilerplate never reaches a brief, while a
    patient-specific contraindication (steroids in TBI) still does;
  - no brief says "NO VOLUME", or shouts at all; acronyms stay acronyms.

The suite runs against the pinned test kit in conftest.py, where ketamine has
exactly one signed presentation, 500 mg / 10 mL (50 mg/mL).

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
from test_brief import CARDS, GENERATED, _NoRetrieval  # noqa: E402


@pytest.fixture(scope="module")
def served():
    return {name: oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=h)
            for name, (q, h) in CARDS.items()}


def _all_briefs(served):
    out = dict((k, v["brief"]) for k, v in served.items())
    out["generated"] = brief.build_brief(GENERATED, oc.MEDICATION_TERMS)["brief"]
    return out


# ── (a)(b)(c): the pediatric ketamine brief ──────────────────────────────────

def test_the_ketamine_brief_is_three_slots(served):
    """25 kg child, ketamine IV for pain. The card's only contraindication is
    Hypersensitivity, so slot (c) is empty and the brief is two lines."""
    r = served["ped_ketamine_iv"]
    assert r["brief"].splitlines() == [
        # (a) the GIVE line verbatim, its per-kg basis, the conditional volume
        "ketamine IV: 6.25 mg (0.25 mg/kg × 25 kg). At 50 mg/mL that's 0.12 mL — confirm vial.",
        # (b) DO THIS step 3: step 1 is equipment preamble, step 2 restates the dose
        "Reassess pain, airway, respirations q5min.",
    ]
    # The card underneath is untouched: still no volume, still asks the vial.
    assert "ketamine IV: 6.25 mg. NO VOLUME" in r["response"]
    assert "**CONFIRM VIAL**" in r["response"]
    assert "Confirm monitoring and airway equipment ready." in r["response"]


def test_every_line_of_the_ketamine_brief_traces_to_the_card_or_a_computation(served):
    r = served["ped_ketamine_iv"]
    line_a, line_b = r["brief"].splitlines()
    assert "ketamine IV: 6.25 mg" in r["response"]
    assert line_b in r["response"]
    # 0.25 mg/kg is the signed contract's rate for this indication; 25 kg the
    # confirmed weight; their product is the printed dose.
    entry = next(e for e in oc.drug_contracts.servable_entries()["ketamine"]
                 if e["indication"] == "moderate to severe pain / analgesia" and e["route"] == "IV")
    assert entry["dose_range"]["min"] == 0.25 and entry["dose_range"]["units"] == "mg/kg"
    assert r["patient_context"]["confirmed_weight_kg"] == 25
    # The volume is the one the card serves once the medic confirms the vial:
    # resolve_dose_volume goes through drug_concentrations.volume_ml, and with
    # the vial confirmed that returns the same number.
    assert oc.drug_concentrations.volume_ml("ketamine", 6.25, {"ketamine": 50.0}) == (0.12, 50.0), \
        "the conditional volume disagrees with the volume the card serves once confirmed"
    assert "At 50 mg/mL that's 0.12 mL" in line_a


def test_the_dose_line_is_verbatim(served):
    for name in ("ped_ketamine_iv", "adult_rsi", "push_dose_epi"):
        r = served[name]
        _, sections = brief.parse_sections(r["response"])
        for item in brief._section(sections, brief.DOSE_SECTIONS):
            if not brief._DOSE_RE.search(item):
                continue
            head = item.split(" Indication:")[0].split(" NO VOLUME")[0].rstrip().rstrip(".")
            assert head in r["brief"], f"{name}: {head!r} not verbatim in\n{r['brief']}"


def test_preamble_is_not_the_next_action():
    text = ("**DO THIS**\n1. Confirm monitoring and airway equipment ready.\n"
            "2. Ensure suction is available.\n3. Splint the limb.\n\n"
            "**GIVE**\n- ketamine IV: 15 mg. Indication: analgesia.\n\n"
            "**WATCH**\n- Respirations.\n")
    assert brief.build_brief(text, oc.MEDICATION_TERMS)["brief"].splitlines()[1] == \
        "Splint the limb."


def test_watch_is_the_fallback_next_action():
    text = ("**DO THIS**\n1. Confirm monitoring equipment ready.\n2. Give ketamine IV.\n\n"
            "**GIVE**\n- ketamine IV: 15 mg. Indication: analgesia.\n\n"
            "**WATCH**\n- Respirations and emergence reaction.\n")
    assert brief.build_brief(text, oc.MEDICATION_TERMS)["brief"].splitlines()[1] == \
        "Respirations and emergence reaction."


# ── the per-kg basis ─────────────────────────────────────────────────────────

def test_no_basis_without_a_confirmed_weight():
    text = "**GIVE**\n- ketamine IV: 6.25 mg. Indication: moderate to severe pain / analgesia.\n"
    assert "mg/kg" not in brief.build_brief(text, oc.MEDICATION_TERMS)["brief"]
    assert "(0.25 mg/kg × 25 kg)" in brief.build_brief(text, oc.MEDICATION_TERMS, weight_kg=25)["brief"]


def test_no_basis_when_the_printed_dose_is_not_that_product():
    """A capped dose, or a line that is not what the entry computes, gets no
    basis rather than one it does not follow."""
    text = "**GIVE**\n- ketamine IV: 10 mg. Indication: moderate to severe pain / analgesia.\n"
    assert "mg/kg" not in brief.build_brief(text, oc.MEDICATION_TERMS, weight_kg=25)["brief"]


def test_no_basis_for_a_reworded_indication():
    text = "**GIVE**\n- ketamine IV: 6.25 mg. Indication: pain.\n"
    assert "mg/kg" not in brief.build_brief(text, oc.MEDICATION_TERMS, weight_kg=25)["brief"]


# ── volume ───────────────────────────────────────────────────────────────────

NO_VOL = ("**GIVE**\n- ketamine IV: 6.25 mg. NO VOLUME — confirm concentration to "
          "compute volume. Indication: moderate to severe pain / analgesia.\n")


def test_one_signed_presentation_gives_a_conditional_volume():
    assert [p["label_text"] for p in dcn.signed_presentations("ketamine")] == \
        ["500 mg / 10 mL vial"], "the pinned test kit changed"
    b = brief.build_brief(NO_VOL, oc.MEDICATION_TERMS)["brief"]
    assert "At 50 mg/mL that's 0.12 mL — confirm vial." in b
    assert "No volume" not in b


def test_several_signed_presentations_keep_the_cards_reason(monkeypatch):
    entries = copy.deepcopy(dcn.ENTRIES)
    for p in entries["ketamine"]["presentations"]:
        p.update(signoff=True, reviewed_by="clinician", review_date="2026-08-25")
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    b = brief.build_brief(NO_VOL, oc.MEDICATION_TERMS)["brief"]
    assert "At " not in b and "mL —" not in b
    assert b.startswith("ketamine IV: 6.25 mg. No volume — confirm concentration to compute volume.")


def test_no_signed_presentation_keeps_the_cards_reason(monkeypatch):
    entries = copy.deepcopy(dcn.ENTRIES)
    for p in entries["ketamine"]["presentations"]:
        p.update(signoff=False)
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    b = brief.build_brief(NO_VOL, oc.MEDICATION_TERMS)["brief"]
    assert "At " not in b
    assert "No volume — confirm concentration to compute volume." in b


def test_an_undrawable_volume_is_not_stated():
    """0.5 mg at 50 mg/mL is 0.01 mL, below what a syringe draws. No volume."""
    text = ("**GIVE**\n- ketamine IV: 0.5 mg. NO VOLUME — confirm concentration to "
            "compute volume. Indication: test.\n")
    b = brief.build_brief(text, oc.MEDICATION_TERMS)["brief"]
    assert "At " not in b and "No volume" in b


def test_no_brief_says_no_volume_in_capitals(served):
    for name, b in _all_briefs(served).items():
        assert "NO VOLUME" not in b, name


# ── contraindications ────────────────────────────────────────────────────────

def test_hypersensitivity_is_in_no_brief(served):
    for name, b in _all_briefs(served).items():
        assert not re.search(r"hypersensitiv|allerg", b, re.IGNORECASE), f"{name}: {b}"
    # ...and it is still on the card, in the section that folds.
    r = served["ped_ketamine_iv"]
    assert "Hypersensitivity" in r["response"]
    assert "CONTRAINDICATIONS" not in r["critical_sections"]


def test_allergy_boilerplate_in_dont_stays_out_of_the_brief():
    text = ("**GIVE**\n- ketamine IV: 15 mg. Indication: analgesia.\n\n"
            "**DON'T**\n- Never give ketamine with a known allergy to it.\n")
    assert "allergy" not in brief.build_brief(text, oc.MEDICATION_TERMS)["brief"]


TBI = ("**DO THIS**\n1. Keep SBP above 110.\n\n"
       "**GIVE**\n- levetiracetam IV: 1500 mg. Indication: seizure prophylaxis in TBI.\n\n"
       "**CONTRAINDICATIONS**\n- methylprednisolone — spinal cord injury: Hypersensitivity; "
       "Traumatic brain injury (CRASH: increased mortality)\n\n"
       "**DON'T**\n- Never give steroids in TBI.\n")


def test_a_patient_specific_contraindication_still_reaches_the_brief():
    out = brief.build_brief(TBI, oc.MEDICATION_TERMS)
    lines = out["brief"].splitlines()
    assert lines[2] == ("Contraindicated — methylprednisolone: Traumatic brain injury "
                        "(CRASH: increased mortality). · Never give steroids in TBI.")
    assert "Hypersensitivity" not in out["brief"]
    assert "CONTRAINDICATIONS" in out["critical_sections"]


# ── sentence case ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("NO VOLUME — confirm vial.", "No volume — confirm vial."),
    ("FENTANYL DOSING: titrate to pain.", "Fentanyl dosing: titrate to pain."),
    ("Use the VENT settings above.", "Use the vent settings above."),
    ("[POST-INTUBATION SEDATION] ketamine IV: 40 mg.", "[Post-intubation sedation] ketamine IV: 40 mg."),
    ("Declare CICO: cannot intubate, cannot oxygenate.", "Declare CICO: cannot intubate, cannot oxygenate."),
    ("TXA IV/IO within 3 h; PEEP 5; ETCO2 35-45; TBI, GCS, RSI.",
     "TXA IV/IO within 3 h; PEEP 5; ETCO2 35-45; TBI, GCS, RSI."),
    ("ketamine IV: 6.25 mg.", "ketamine IV: 6.25 mg."),
])
def test_sentence_case(line, expected):
    assert brief._sentence_case(line) == expected


def test_a_shouted_card_line_arrives_in_sentence_case():
    """End to end, not just the helper: the card shouts, the brief does not."""
    text = ("**GIVE**\n- ketamine IV: 15 mg. Indication: analgesia.\n\n"
            "**WATCH**\n- MONITOR AIRWAY CONTINUOUSLY. Check ETCO2 and SpO2.\n\n"
            "**DON'T**\n- NEVER redose without reassessment.\n")
    b = brief.build_brief(text, oc.MEDICATION_TERMS)["brief"].splitlines()
    assert b[1] == "Monitor airway continuously. Check ETCO2 and SpO2."
    assert b[2] == "Never redose without reassessment."


def test_no_brief_shouts(served):
    for name, b in _all_briefs(served).items():
        for word in re.findall(r"\b[A-Z][A-Z'’-]{3,}\b", b):
            assert word in brief.ACRONYMS, f"{name}: shouted {word!r} in\n{b}"
