"""A32: a stated indication restricts what the dose check accepts.

Owner, 2026-10-20: "when the question states an indication, the dose check
accepts only signed entries for that indication; a dose from another
indication of the same drug holds, with the hold naming both indications. No
stated indication keeps today's behaviour (which-indication question or
by-drug)."

Found twice:
- A31 live harness: "80 kg adult, femur fracture, IV access, ketamine drip for
  pain, what rate", then "500". qwen2.5:3b served "ketamine IV (40 mg).
  Indication: post-intubation sedation — repeated bolus", SAFE. #165 puts the
  stated indication's doses first but removes none, and the check accepted
  every offered entry.
- A30 live harness: "BP 70/40 after 2 L of fluid, still in shock, epinephrine
  infusion rate" was served the 10 mcg push dose labelled "symptomatic
  bradycardia", SAFE.

The builder still offers every entry (owner, #165 review: nothing is removed
from the offer). Only the check narrows. A drug with no signed entry in a
stated class is left alone, as A1b leaves a drug with no seizure entry.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402

FEMUR_PAIN = "80 kg adult, femur fracture, IV access, ketamine drip for pain, what rate 500"
SHOCK = "80 kg adult, BP 70/40 after 2 L of fluid, still in shock, epinephrine infusion rate"
BRADY = "80 kg adult, HR 38, symptomatic bradycardia, epinephrine infusion rate"
NO_INDICATION = "Need to give ketamine 89kg IV established 500"

KETAMINE_SEDATION_40 = ("**GIVE**\n- Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: "
                        "post-intubation sedation — repeated bolus (no infusion pump).")
KETAMINE_ANALGESIA_20 = ("**GIVE**\n- Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). Indication: "
                         "moderate to severe pain / analgesia.")
EPI_PUSH = ("**GIVE**\n- Draw 10 mcg of 10 mcg/mL epinephrine IV (10 mcg). "
            "Indication: symptomatic bradycardia.")


def _issues(history, text):
    ctx = oc.rebuild_patient_context_from_history(history)
    doses = oc.build_allowed_doses(history, ctx)
    return oc.run_deterministic_checks(history, text, ctx, doses).issues


# ── Holds, naming both indications ──────────────────────────────────────────

def test_the_femur_fracture_sedation_dose_holds():
    issues = _issues(FEMUR_PAIN, KETAMINE_SEDATION_40)
    assert issues, issues
    both = [i for i in issues if "post-intubation sedation" in i and "pain" in i]
    assert both, issues


def test_the_epinephrine_push_dose_holds_in_shock():
    issues = _issues(SHOCK, EPI_PUSH)
    assert issues, issues
    both = [i for i in issues if "bradycardia" in i and "shock" in i]
    assert both, issues


# ── The stated indication's own signed dose still serves ────────────────────

def test_the_signed_analgesia_dose_still_serves():
    assert _issues(FEMUR_PAIN, KETAMINE_ANALGESIA_20) == []


def test_the_bradycardia_push_dose_still_serves_for_bradycardia():
    assert _issues(BRADY, EPI_PUSH) == []


# ── No stated indication: today's behaviour ─────────────────────────────────

def test_with_no_stated_indication_any_signed_entry_still_passes():
    text = ("**GIVE**\n- Draw 0.89 mL of 50mg/mL ketamine IV (44.5 mg). Indication: "
            "post-intubation sedation — repeated bolus (no infusion pump).")
    assert _issues(NO_INDICATION, text) == []


def test_the_builder_still_offers_every_entry():
    """Owner, #165 review: nothing is removed from the offer; only the check narrows."""
    ctx = oc.rebuild_patient_context_from_history(FEMUR_PAIN)
    offered = {d.indication for d in oc.build_allowed_doses(FEMUR_PAIN, ctx)}
    assert any("post-intubation sedation" in i for i in offered), offered


# ── RSI covers the sedation that follows the tube ───────────────────────────
# Found in the A32 replay: 43 live-log rows of the deterministic RSI bundle
# ("RSI an 80kg male trauma patient ketamine and rocuronium") held on the
# bundle's own post-intubation sedation line, because an RSI question states
# RSI and not sedation. The bundle serves that line by design (A3, #86).

def test_the_rsi_bundles_post_intubation_sedation_line_passes():
    history = "RSI an 80kg male trauma patient ketamine and rocuronium"
    text = ("**GIVE**\n- ketamine IV: 160 mg. NO VOLUME — confirm concentration to compute volume. "
            "Indication: RSI induction.\n"
            "- Draw 9.6 mL of 10mg/mL rocuronium IV (96 mg). Indication: RSI paralytic.\n"
            "**POST-INTUBATION SEDATION**\n- ketamine IV: 40 mg. NO VOLUME — confirm concentration "
            "to compute volume. Indication: post-intubation sedation — repeated bolus (no infusion pump).")
    assert _issues(history, text) == []
