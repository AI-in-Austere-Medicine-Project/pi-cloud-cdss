"""
EdgeCDSS — the paediatric ketamine push dilution is a prepared syringe.

OWNER RULING 2026-09-18 (#65). No guideline in the corpus states a ketamine
push dilution, so it is an owner declaration: 5 mg/mL, 1 mL of the 50 mg/mL
vial in 9 mL of normal saline, on the paediatric analgesia entry only. It
reaches the medic three ways — CAUTIONS (recipe and mL/kg, the push-dose
epinephrine shape), the brief's conditional volume, and drawable()'s refusal —
and is NOT a presentation in drug_concentrations.json, so the single-vial
brief line stays on and the volume audit never accepts 5 mg/mL as stocked.

The suite runs against the pinned test kit in conftest.py, where ketamine has
exactly one signed presentation, 50 mg/mL.

    cd server && ./run_unit_tests.sh
"""
import copy
import json
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import brief  # noqa: E402
import drug_concentrations as dcn  # noqa: E402
import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402

ANALGESIA = "moderate to severe pain / analgesia"


def _ctx(weight, ped=True):
    return oc.PatientContext(confirmed_weight_kg=weight, weight_source="stated",
                             route_preference="IV", is_pediatric=ped,
                             age_years=6.0 if ped else None)


def _section(card, name):
    return card.split(f"**{name}**")[1].split("**", 1)[0]


def _peds_entry():
    return next(e for e in dc.servable_entries()["ketamine"]
                if e["indication"] == ANALGESIA and e["route"] == "IV"
                and e["population"] == "peds")


# ── what the medic reads ─────────────────────────────────────────────────────

def test_25kg_cautions_carry_the_dilution_and_the_brief_its_volume():
    card = oc.build_ketamine_analgesia_response(_ctx(25.0))
    cautions = _section(card, "CAUTIONS")
    assert "5 mg/mL" in cautions and "1 mL of ketamine 50 mg/mL in 9 mL" in cautions
    assert "0.04 mL/kg" in cautions, "the mL/kg equivalence is missing"
    assert "OWNER-DECLARED dilution" in cautions

    # CAUTIONS are fixed text; the weight's own volume is the brief's:
    # 0.2 mg/kg x 25 kg = 5 mg, at 5 mg/mL = 1 mL.
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=25.0)["brief"]
    assert "Dilute first — 5 mg/mL (1 mL of 50 mg/mL + 9 mL normal saline): 1 mL — confirm vial." in b


def test_the_single_vial_volume_moves_to_vial_math_under_0_2_ml():
    """25 kg: 5 mg is 0.100 mL of the vial — drawable, but under the brief's
    0.2 mL floor where a dilution is declared. The brief gives the diluted
    instruction alone; the undiluted volume is the Vial math chip's."""
    card = oc.build_ketamine_analgesia_response(_ctx(25.0))
    assert "ketamine IV: 5 mg. NO VOLUME" in card, "the card now draws from somewhere"
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=25.0)["brief"]
    assert "At 50 mg/mL" not in b and "0.100" not in b and "Diluted to" not in b
    assert brief.vial_math_lines(card, 25.0) == [
        "ketamine IV 5 mg: 0.100 mL of 50 mg/mL undiluted — confirm vial."]
    assert dcn.signed_presentations("ketamine") and \
        [p["concentration_mg_ml"] for p in dcn.signed_presentations("ketamine")] == [50.0]


def test_at_0_2_ml_and_over_the_brief_keeps_both_volumes():
    """50 kg: 10 mg is 0.200 mL of the vial — not under the floor, so the brief
    still says it, then the dilution; Vial math has nothing to add."""
    card = oc.build_ketamine_analgesia_response(_ctx(50.0))
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=50.0)["brief"]
    assert ("At 50 mg/mL that's 0.200 mL — confirm vial. Diluted to 5 mg/mL "
            "(1 mL of 50 mg/mL + 9 mL normal saline): 2 mL.") in b
    assert brief.vial_math_lines(card, 50.0) == []


def test_below_the_vial_floor_the_refusal_names_the_dilution():
    """10 kg: 2 mg is 0.04 mL of the vial, under the 0.05 mL floor."""
    ctx = _ctx(10.0)
    ctx.confirmed_concentrations = {"ketamine": 50.0}
    card = oc.build_ketamine_analgesia_response(ctx)
    give = _section(card, "GIVE")
    assert "NO VOLUME" in give and "Draw" not in give
    assert "dilute first: 5 mg/mL (1 mL of 50 mg/mL + 9 mL normal saline)" in give
    assert "a dilution the kit has not declared" not in give

    # Unconfirmed vial, same child: the brief gives the diluted volume alone.
    card = oc.build_ketamine_analgesia_response(_ctx(10.0))
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=10.0)["brief"]
    assert b.startswith("ketamine IV: 2 mg (0.2 mg/kg × 10 kg). Dilute first — "
                        "5 mg/mL (1 mL of 50 mg/mL + 9 mL normal saline): 0.400 mL — confirm vial.")


def test_an_adult_is_never_told_to_dilute():
    card = oc.build_ketamine_analgesia_response(_ctx(80.0, ped=False))
    assert "dilution" not in card.lower() and "5 mg/mL" not in card
    b = brief.build_brief(card, oc.MEDICATION_TERMS, weight_kg=80.0)["brief"]
    assert "Dilute" not in b and "Diluted" not in b


def test_an_entry_without_a_dilution_keeps_the_old_refusal():
    assert "a dilution the kit has not declared" in dcn.drawable(0.01)[1]


# ── the fence ────────────────────────────────────────────────────────────────

def test_the_volume_audit_does_not_accept_the_dilution_as_a_stocked_strength():
    text = "- Draw 1 mL of 5mg/mL ketamine IV (5mg). Indication: analgesia."
    out, issues = oc.audit_volume_lines(text)
    assert issues and "not a declared concentration" in issues[0]
    assert "1 mL of 5mg/mL" not in out


def test_no_declared_dilution_is_a_presentation_in_any_concentration_file():
    """The deployment file and the example it is copied from. A prepared
    syringe listed as a presentation would switch off the single-vial brief
    line and let the audit accept it as stocked."""
    dilutions = {(n, e["push_dilution"]["concentration_mg_ml"])
                 for n, es in dc.servable_entries().items() for e in es
                 if e.get("push_dilution")}
    assert dilutions, "no entry declares a push dilution — this test guards nothing"
    for fname in ("drug_concentrations.json", "drug_concentrations.example.json"):
        with open(os.path.join(os.path.dirname(dc.__file__), fname)) as f:
            entries = json.load(f)["entries"]
        for entry in entries:
            for p in entry.get("presentations", []):
                assert (entry["generic_name"], p.get("concentration_mg_ml")) not in dilutions, \
                    f"{fname}: the {entry['generic_name']} push dilution is declared as a presentation"


def test_a_recipe_is_quoted_only_against_the_vial_it_was_written_for():
    dil = dc.push_dilution(_peds_entry())
    assert dcn._dilution_for(dil, 50.0) is dil
    assert dcn._dilution_for(dil, 10.0) is None, \
        "1 mL of a 10 mg/mL vial in 9 mL is 1 mg/mL, not 5"
    assert "dilute first" not in dcn.volume_refusal(
        "ketamine", 0.1, {"ketamine": 50.0}, dilution={**dil, "from_concentration_mg_ml": 10.0})


def _drug_with(dilution):
    drug = copy.deepcopy(dc.DRUGS["ketamine"])
    entry = copy.deepcopy(_peds_entry())
    entry["push_dilution"] = dilution
    return drug, entry


def test_a_dilution_that_does_not_add_up_is_refused():
    drug, entry = _drug_with({**_peds_entry()["push_dilution"], "diluent_ml": 4.0})
    ok, why = dc.entry_is_servable(entry, drug)
    assert not ok and "does not add up" in why


def test_a_dilution_at_a_stocked_strength_is_refused():
    """WHO lists ketamine at 10 mg/mL: a 10 mg/mL syringe reads as a vial."""
    drug, entry = _drug_with({**_peds_entry()["push_dilution"],
                              "concentration_mg_ml": 10.0, "diluent_ml": 4.0})
    ok, why = dc.entry_is_servable(entry, drug)
    assert not ok and "stocked strength" in why


def test_an_unsigned_dilution_is_refused():
    drug, entry = _drug_with({**_peds_entry()["push_dilution"], "declared_by": "script"})
    ok, why = dc.entry_is_servable(entry, drug)
    assert not ok and "authorised signer" in why


@pytest.mark.parametrize("name,entry", [
    (n, e) for n, es in dc.servable_entries().items() for e in es
    if e.get("push_dilution")])
def test_every_declared_dilution_is_stated_in_the_serve_cautions(name, entry):
    """The record and the words the medic reads must say the same thing."""
    dil = entry["push_dilution"]
    served = " ".join(dc.serve_cautions(entry))
    assert f"{dil['concentration_mg_ml']:g} mg/mL" in served
    per_kg = entry["dose_range"]["min"] / dil["concentration_mg_ml"]
    assert f"{per_kg:g} mL/kg" in served, f"{name}: no mL/kg equivalence"
