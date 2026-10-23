"""A35 sweep: a drug number a deterministic card emits has a signed entry
behind it, or it is replaced by a hold.

Owner, 2026-10-22: "sweep every deterministic card: list every number a card
can emit and the signed entry it comes from. Any number with no signed entry
behind it is replaced by a hold." Ruled the same day: drug numbers only
(doses, rates, volumes, concentrations, recipes); the overdose ceilings keep
their check and stop printing their unsigned number.

The list is in docs/WORK_ORDER.md (A35). The drug numbers with no signed
entry behind them were:
  - the push-dose epinephrine syringe recipe the prep card printed itself
    (each signed push-dose entry states it in its own cautions);
  - the epinephrine drip bag, 1 mg in 250 mL = 4 mcg/mL (in no entry);
  - the overdose-hold ceilings printed in the hold (ketamine 2 mg/kg,
    rocuronium 1.2 mg/kg, succinylcholine 2 mg/kg);
  - the legacy calculators (RSI induction, post-intubation, rocuronium,
    succinylcholine, lorazepam), unreachable while their drugs are signed
    and back the moment a drug lost its last entry or the bank failed to
    load.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import openai_client as oc  # noqa: E402


def _section(card, name):
    return card.split(f"**{name}**")[1].split("\n**")[0] if f"**{name}**" in card else ""


# ── the legacy calculators ───────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ketamine_induction_iv", "ketamine_post_intubation_iv",
                                  "rocuronium_rsi", "succinylcholine_rsi",
                                  "lorazepam_seizure"])
def test_the_legacy_calculators_are_gone(name):
    assert not hasattr(oc, name)


def _ctx(kg=60.0):
    return oc.PatientContext(confirmed_weight_kg=kg, weight_source="stated",
                             route_preference="IV")


@pytest.mark.parametrize("q", ["60kg RSI now", "she is seizing, 60kg"])
def test_with_no_bank_nothing_is_calculated(monkeypatch, q):
    """drug_contracts failing to load used to bring every calculator back."""
    monkeypatch.setattr(oc, "drug_contracts", None)
    assert oc.build_allowed_doses(q, _ctx()) == []


def test_with_no_bank_the_rsi_card_serves_no_dose(monkeypatch):
    monkeypatch.setattr(oc, "drug_contracts", None)
    assert oc.build_rsi_response(_ctx(), "60kg RSI now") is None


# ── the push-dose prep card ──────────────────────────────────────────────────

PUSH_BRADY = "push dose epi for bradycardia HR 38"


def test_the_push_dose_card_prints_no_recipe_of_its_own():
    card = oc.build_fixed_prep_response(PUSH_BRADY)
    prep = _section(card, "PUSH-DOSE EPINEPHRINE PREP")
    tldr = _section(card, "TLDR")
    for own in ("Make 10 mcg/mL", "into a 10 mL syringe", "Total 10 mL",
                "Final concentration"):
        assert own not in card, card
    assert not any(ch.isdigit() for ch in prep + tldr), (prep, tldr)


def test_the_recipe_still_reaches_the_medic_from_the_signed_entry():
    card = oc.build_fixed_prep_response(PUSH_BRADY)
    assert "adding 1 mL of 0.1 mg/mL epinephrine to 9 mL of normal saline" in \
        _section(card, "CAUTIONS"), card


def test_a_push_dose_request_with_no_signed_entry_gets_no_recipe():
    """A child with bradycardia: the bank has no paediatric bradycardia push
    dose (the adult shock case had none until E05 was relabelled, freeze plan
    item 3). No number in the prep lines."""
    q = "6 year old child 20 kg, bradycardia HR 50, push dose epi"
    card = oc.build_fixed_prep_response(q, oc.rebuild_patient_context_from_history(q))
    prep = _section(card, "PUSH-DOSE EPINEPHRINE PREP")
    assert prep and not any(ch.isdigit() for ch in prep), card
    # Nor does the TLDR point at a signed dose that is not there.
    assert "signed dose" not in _section(card, "TLDR").replace("no signed dose", ""), card


# ── the epinephrine drip card ────────────────────────────────────────────────

def test_the_epi_drip_card_states_no_bag():
    card = oc.build_fixed_prep_response("how do i make an epi drip for shock")
    for unsigned in ("250 mL", "4 mcg/mL", "1 mg epinephrine", "1mg epi"):
        assert unsigned not in card, card
    assert "per local protocol" in card
    assert "2-10 mcg/min" in card, "the signed rate still serves"


def test_no_unsigned_recipe_number_is_registered():
    assert oc.PREP_RECIPE_NUMBERS == {}


# ── the overdose hold ────────────────────────────────────────────────────────

@pytest.mark.parametrize("q, ceiling", [
    ("80 kg adult, give ketamine 500 mg", "160"),
    ("80 kg adult, give rocuronium 200 mg", "96"),
    ("80 kg adult, give succinylcholine 300 mg", "160"),
])
def test_the_overdose_hold_prints_no_unsigned_ceiling(q, ceiling):
    ctx = oc.rebuild_patient_context_from_history(q)
    (issue,) = oc.detect_requested_medication_overdose(q, ctx)
    assert ceiling not in issue, issue
    assert "highest signed" in issue  # it still holds (A36: against the signed maximum)
    assert "a 80" not in issue, issue
