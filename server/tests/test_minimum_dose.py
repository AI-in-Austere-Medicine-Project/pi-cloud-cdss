"""Minimum single dose — a source-stated floor that RAISES the computed dose.

The case throughout is SMOG CY24 p.100, paediatric atropine for symptomatic
bradycardia: 0.02 mg/kg, maximum single 0.5 mg, "Minimum dose is 0.1 mg". Below
5 kg the per-kg arithmetic computes under that floor, and a dose under the
floor can cause the paradoxical bradycardia the drug is treating.

The entry is built here rather than read from drug_contracts.json on purpose.
The atropine drafts are unsigned and an unsigned entry cannot serve, so a test
that read the file would be asserting on nothing; and the floor is an engine
capability, not an atropine fact.
"""
import copy

import drug_contracts as dc


def atropine_peds():
    """SMOG CY24 p.100, paediatric symptomatic bradycardia, signed.

    The same numbers as the unsigned draft, with min_single authored and the
    NEEDS_MINIMUM_DOSE_SUPPORT flag cleared — which is exactly the edit the
    owner makes at signing.
    """
    return {
        "indication": "symptomatic bradycardia",
        "population": "peds",
        "route": "IV",
        "dose_range": {"min": 0.02, "max": 0.02, "units": "mg/kg", "per_kg": True},
        "max_single": {"value": 0.5, "units": "mg",
                       "rule": "maximum single dose 0.5 mg"},
        "min_single": {"value": 0.1, "units": "mg",
                       "rule": "a smaller dose can cause paradoxical bradycardia"},
        "max_cumulative": {"value": 1.0, "units": "mg",
                           "rule": "maximum total dose 1 mg"},
        "contraindications": ["Hypersensitivity to atropine (SMOG CY24 p.100)"],
        "cautions": [{"tier": "serve",
                      "text": "Always reference the Broselow tape (SMOG p.100)."}],
        "sources": [{"citation": "SMOG CY24 — Atropine, Pediatric, p.100",
                     "tier": 1, "source_class": "SMOG",
                     "url": "local:server/data/jts_protocols/SMOG_CY24_REVISION_FINAL.pdf",
                     "retrieved_date": "2026-09-19"}],
        "signoff": True,
        "reviewed_by": sorted(dc.SIGNOFF_AUTHORS)[0],
        "review_date": "2026-09-20",
        "version": "1.0.0",
    }


# ── The floor itself ────────────────────────────────────────────────────────

def test_a_3kg_infant_is_raised_to_the_minimum():
    """0.02 mg/kg x 3 kg = 0.06 mg, which the source forbids. Give 0.1 mg."""
    r = dc.resolve_dose(atropine_peds(), 3.0)
    assert r["dose_mg"] == 0.1
    assert r["display_value"] == 0.1
    assert r["display_units"] == "mg"
    assert r["floor_applied"] is True


def test_the_floor_is_reported_in_the_medics_own_words():
    r = dc.resolve_dose(atropine_peds(), 3.0)
    note = r["floor_note"]
    assert "MINIMUM DOSE 0.1 mg" in note
    assert "paradoxical bradycardia" in note


def test_five_kg_is_the_boundary_and_is_not_raised():
    """0.02 x 5 = 0.1 mg exactly. On the floor is not under it."""
    r = dc.resolve_dose(atropine_peds(), 5.0)
    assert r["dose_mg"] == 0.1
    assert r["floor_applied"] is False


def test_just_under_five_kg_is_raised():
    r = dc.resolve_dose(atropine_peds(), 4.9)
    assert r["floor_applied"] is True
    assert r["dose_mg"] == 0.1


def test_an_ordinary_child_is_untouched():
    r = dc.resolve_dose(atropine_peds(), 10.0)
    assert r["dose_mg"] == 0.2
    assert r["floor_applied"] is False
    assert r["floor_note"] == ""


def test_the_cap_still_wins_at_the_top():
    """0.02 x 40 = 0.8 mg, capped to 0.5. Adding a floor must not lift a cap."""
    r = dc.resolve_dose(atropine_peds(), 40.0)
    assert r["dose_mg"] == 0.5
    assert r["floor_applied"] is False


def test_an_entry_with_no_floor_is_unchanged():
    """The field is optional: every entry authored before it must resolve the
    same way it did, and say so."""
    e = atropine_peds()
    del e["min_single"]
    r = dc.resolve_dose(e, 3.0)
    assert r["dose_mg"] == 0.06
    assert r["floor_applied"] is False


def test_a_per_kg_floor_scales():
    e = atropine_peds()
    e["dose_range"] = {"min": 0.001, "max": 0.001, "units": "mg/kg", "per_kg": True}
    e["min_single"] = {"value": 0.01, "units": "mg/kg", "rule": ""}
    r = dc.resolve_dose(e, 10.0)
    assert r["dose_mg"] == 0.1
    assert r["floor_applied"] is True


def test_a_floor_in_another_unit_converts():
    e = atropine_peds()
    e["min_single"] = {"value": 100.0, "units": "mcg", "rule": ""}
    r = dc.resolve_dose(e, 3.0)
    assert r["dose_mg"] == 0.1


def test_a_fixed_dose_entry_can_carry_a_floor_without_a_weight():
    """A weightless fixed dose must not be refused because a floor sits beside
    it. #71 made this path reachable."""
    e = atropine_peds()
    e["population"] = "adult"
    e["dose_range"] = {"min": 0.05, "max": 0.05, "units": "mg", "per_kg": False}
    r = dc.resolve_dose(e, None)
    assert r["floor_applied"] is True
    assert r["dose_mg"] == 0.1


def test_an_unusable_floor_unit_refuses_the_whole_dose():
    """An unreadable floor is not an absent floor."""
    e = atropine_peds()
    e["min_single"] = {"value": 0.1, "units": "spoonfuls", "rule": ""}
    r = dc.resolve_dose(e, 3.0)
    assert r["dose_mg"] is None
    assert "min_single unit is unusable" in r["reason"]


# ── The signing gate ────────────────────────────────────────────────────────

def test_the_flag_blocks_a_signed_entry():
    """This is the guarantee: atropine peds cannot be signed into service
    while the engine gap it names is still open on it."""
    e = atropine_peds()
    del e["min_single"]
    e["flags"] = [dc.NEEDS_MINIMUM]
    ok, why = dc.entry_is_servable(e)
    assert ok is False
    assert dc.NEEDS_MINIMUM in why


def test_clearing_the_flag_and_authoring_the_floor_makes_it_servable():
    ok, why = dc.entry_is_servable(atropine_peds())
    assert ok is True, why


def test_a_floor_above_its_own_cap_cannot_be_signed():
    e = atropine_peds()
    e["min_single"] = {"value": 2.0, "units": "mg", "rule": ""}
    ok, why = dc.entry_is_servable(e)
    assert ok is False
    assert "above max_single" in why


def test_a_fixed_floor_under_a_per_kg_cap_is_caught_at_low_weight():
    """It holds at 70 kg and fails at 2 kg. Checking one weight would sign it."""
    e = atropine_peds()
    e["max_single"] = {"value": 0.5, "units": "mg/kg", "rule": ""}
    e["min_single"] = {"value": 5.0, "units": "mg", "rule": ""}
    ok, why = dc.entry_is_servable(e)
    assert ok is False
    assert "above max_single at 2 kg" in why


def test_a_non_numeric_floor_cannot_be_signed():
    e = atropine_peds()
    e["min_single"] = {"value": "0.1", "units": "mg"}
    ok, why = dc.entry_is_servable(e)
    assert ok is False
    assert "not a number" in why


def test_an_entry_without_the_flag_or_a_floor_is_unaffected():
    """The gate must not start refusing the 47 entries that were already
    signed without ever hearing of a minimum."""
    e = atropine_peds()
    del e["min_single"]
    ok, why = dc.entry_is_servable(e)
    assert ok is True, why


# ── What the medic is shown ─────────────────────────────────────────────────

def test_the_served_dose_leads_with_the_floor_caution(monkeypatch):
    """A floored dose reaches build_allowed_doses with the floor named first.

    Without this the screen reads 0.1 mg beside a 0.02 mg/kg contract and a
    3 kg weight, which is arithmetic a medic under load will "correct".
    """
    import openai_client as oc

    entry = atropine_peds()
    monkeypatch.setattr(
        dc, "signed_entries_for",
        lambda *a, **k: [("atropine", copy.deepcopy(entry))])

    ctx = oc.extract_patient_context("3 kg infant bradycardic, atropine dose")
    assert ctx.confirmed_weight_kg == 3.0
    doses = oc.build_allowed_doses("atropine dose", ctx)

    atropine = [d for d in doses if d.drug == "atropine"]
    assert atropine, "the contract entry did not reach the serving path"
    d = atropine[0]
    assert d.display_value == 0.1
    assert d.cautions[0].startswith("MINIMUM DOSE 0.1 mg")
    assert "MINIMUM DOSE 0.1 mg" in (d.warning or "")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
