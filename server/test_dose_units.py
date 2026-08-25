"""
Dose units — the thousandfold defect, and the guards that close it.

THE BUG
───────
The dose builder did this, for every entry, whatever its units said:

    dose_mg = base * weight if per_kg else base

So dextrose "25 g" became 25 mg, calcium gluconate "1 g" became 1 mg, and
epinephrine "10 mcg" became 10 mg. A thousandfold error in both directions on
a drug where the directions matter: too little sugar, too much adrenaline.

WHY NOTHING CAUGHT IT
─────────────────────
The concentration audit verifies volume x concentration == the STATED
milligrams. A dose whose unit was mis-parsed is internally consistent — 1 mg of
calcium at 100 mg/mL really is 0.01 mL — so it passes every check the volume
path has. The defect was invisible to the layer directly above it, which is why
it needed its own guard rather than a wider tolerance on an existing one.

WHAT REPLACED IT
────────────────
Explicit conversion for every unit family the contracts use, and NO DEFAULT.
Defaulting to milligrams is precisely what caused this, so an unrecognised unit
now refuses to produce a dose at all.
"""
import copy

import pytest

import drug_concentrations as dcn
import drug_contracts as dc
import openai_client as oc
from openai_client import PatientContext


def entry_for(drug, **match):
    for e in dc.DRUGS[drug]["dose_entries"]:
        if all(e.get(k) == v for k, v in match.items()):
            return e
    raise AssertionError(f"no {drug} entry matching {match}")


# ═══════════════════════════════════════════════════════════════════════════
# THE FOUR FAMILIES THAT EXPOSED IT — real entries, real numbers
# ═══════════════════════════════════════════════════════════════════════════

def test_grams_are_not_milligrams_dextrose():
    """NASEMSO Hypoglycemia p.85: 25 g of 10-50% dextrose IV. Was read as
    25 mg — a thousandth of the sugar a hypoglycaemic patient needs."""
    e = entry_for("dextrose", indication="symptomatic hypoglycaemia",
                  population="adult")
    r = dc.resolve_dose(e, 80.0)
    assert r["kind"] == dc.MASS
    assert r["dose_mg"] == 25000.0
    assert (r["display_value"], r["display_units"]) == (25.0, "g")


def test_grams_are_not_milligrams_calcium():
    """NASEMSO Cardiac Arrest p.119: calcium gluconate 10% 1 g IV bolus."""
    e = entry_for("calcium gluconate",
                  indication="hyperkalaemia — membrane stabilisation",
                  population="adult")
    r = dc.resolve_dose(e, 80.0)
    assert r["dose_mg"] == 1000.0
    assert (r["display_value"], r["display_units"]) == (1.0, "g")


def test_micrograms_are_not_milligrams_epinephrine():
    """NASEMSO Bradycardia p.36: 10-20 mcg push dose. Was read as 10 mg —
    a thousandfold overdose of adrenaline."""
    e = entry_for("epinephrine",
                  indication="symptomatic bradycardia — push dose",
                  population="adult")
    r = dc.resolve_dose(e, 80.0)
    assert r["dose_mg"] == pytest.approx(0.01)
    assert (r["display_value"], r["display_units"]) == (10.0, "mcg")


def test_micrograms_per_kg_fentanyl():
    """NASEMSO Pain Management p.94: 1 mcg/kg. At 80 kg that is 80 mcg —
    0.08 mg, not 80 mg."""
    e = entry_for("fentanyl", indication="acute pain / analgesia", route="IN")
    r = dc.resolve_dose(e, 80.0)
    assert r["dose_mg"] == pytest.approx(0.08)
    assert (r["display_value"], r["display_units"]) == (80.0, "mcg")


def test_grams_per_kg_dextrose_paediatric():
    e = entry_for("dextrose", indication="symptomatic hypoglycaemia",
                  population="peds")
    r = dc.resolve_dose(e, 20.0)
    assert r["dose_mg"] == 10000.0                    # 0.5 g/kg x 20 kg
    assert (r["display_value"], r["display_units"]) == (10.0, "g")


def test_milligrams_per_kg_still_work():
    """The family that was always right must stay right."""
    e = entry_for("morphine", indication="acute pain / analgesia",
                  population="adult", route="IV")
    r = dc.resolve_dose(e, 70.0)
    assert r["dose_mg"] == 7.0
    assert (r["display_value"], r["display_units"]) == (7.0, "mg")


# ═══════════════════════════════════════════════════════════════════════════
# FAIL CLOSED — no default, ever
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("units,per_kg", [
    ("IU", False), ("units", False), ("units/kg", True), ("mmol", False),
    ("mEq", False), ("", False), (None, False), ("milligrams", False),
    ("puffs", False), (5, False),
])
def test_an_unknown_unit_refuses_rather_than_assuming_mg(units, per_kg):
    """THE regression. Defaulting to mg is what produced the thousandfold
    error, so there is no default to fall back to."""
    kind, mass, why = dc.classify_units(units, per_kg)
    assert kind == dc.UNKNOWN
    assert why, "a refusal must say why"
    e = {"dose_range": {"min": 1.0, "max": 1.0, "units": units,
                        "per_kg": per_kg}}
    assert dc.resolve_dose(e, 80.0)["dose_mg"] is None


@pytest.mark.parametrize("units,per_kg", [
    ("mg", True),        # flat mass but flagged weight-based
    ("mg/kg", False),    # weight-based but not flagged
    ("mcg/kg", False),
])
def test_units_contradicting_per_kg_refuse(units, per_kg):
    """Half the entry says weight-based and half does not. Picking whichever
    half looks right is the habit that caused the bug."""
    kind, _, why = dc.classify_units(units, per_kg)
    assert kind == dc.UNKNOWN and why


def test_a_rate_never_becomes_a_bolus():
    """0.05 mcg/kg/min is a rate. There is no single volume for it, and
    treating it as a bolus would put an hour of infusion in one syringe."""
    e = entry_for("epinephrine",
                  indication="symptomatic bradycardia — infusion",
                  population="adult")
    r = dc.resolve_dose(e, 80.0)
    assert r["kind"] == dc.RATE
    assert r["dose_mg"] is None
    assert "not a bolus" in r["reason"]


def test_a_weight_based_dose_without_a_weight_refuses():
    e = entry_for("morphine", indication="acute pain / analgesia",
                  population="adult", route="IV")
    assert dc.resolve_dose(e, None)["dose_mg"] is None


def test_an_unusable_max_single_unit_refuses_the_whole_entry():
    """A cap in units we cannot read cannot be applied, and an uncapped dose
    is not the same dose."""
    e = copy.deepcopy(entry_for("fentanyl", indication="acute pain / analgesia",
                                route="IN"))
    e["max_single"] = {"value": 100.0, "units": "IU", "rule": "x"}
    r = dc.resolve_dose(e, 80.0)
    assert r["dose_mg"] is None and "max_single" in r["reason"]


def test_the_builder_serves_nothing_for_an_unusable_unit(monkeypatch):
    d = copy.deepcopy(dc.DRUGS["morphine"])
    for e in d["dose_entries"]:
        if isinstance(e["dose_range"], dict):
            e["dose_range"]["units"] = "IU"
            e.update({"signoff": True, "reviewed_by": "clinician",
                      "review_date": "2026-08-25"})
    monkeypatch.setattr(dc, "DRUGS", {"morphine": d})
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    assert oc._contract_dose_candidates("morphine dose", ctx) == []


# ═══════════════════════════════════════════════════════════════════════════
# THE SOURCE UNIT SURVIVES
# ═══════════════════════════════════════════════════════════════════════════

def test_the_medic_reads_the_guidelines_own_unit():
    """25 g, not 25000 mg. Converting the number a medic checks against the
    guideline makes the check harder, and the check is the point."""
    e = entry_for("dextrose", indication="symptomatic hypoglycaemia",
                  population="adult")
    r = dc.resolve_dose(e, 80.0)
    cand = oc.DoseCandidate(drug="dextrose", indication=e["indication"],
                            route="IV", dose_mg=r["dose_mg"],
                            display_value=r["display_value"],
                            display_units=r["display_units"], source="test")
    line = oc.render_give_line(cand)
    assert "25 g" in line
    assert "25000" not in line


def test_a_served_volume_still_states_its_concentration(monkeypatch):
    """The medic's catch-point survives the unit work."""
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["morphine"]["confirm_required"] = False
    entries["morphine"]["presentations"] = [
        dict(p, signoff=True, reviewed_by="clinician", review_date="2026-08-25")
        for p in entries["morphine"]["presentations"]
        if p["concentration_mg_ml"] == 10.0]
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    cand = oc.resolve_dose_volume(
        oc.DoseCandidate(drug="morphine", indication="pain", route="IV",
                         dose_mg=7.0, display_value=7.0, display_units="mg",
                         source="test"))
    line = oc.render_give_line(cand)
    assert "0.7 mL of 10mg/mL" in line and "7 mg" in line


# ═══════════════════════════════════════════════════════════════════════════
# THE SANITY CHECK THE VOLUME AUDIT CANNOT DO
# ═══════════════════════════════════════════════════════════════════════════

def test_the_volume_audit_provably_cannot_catch_a_unit_error():
    """Stated rather than assumed, because it is the reason this file exists.

    1 mg of calcium gluconate at 100 mg/mL really is 0.01 mL. The audit
    verifies volume against the STATED mg and finds nothing wrong.
    """
    text = ("- Draw 0.01 mL of 100mg/mL calcium gluconate IV (1mg). "
            "Indication: hyperkalaemia.")
    _out, issues = oc.audit_volume_lines(text)
    arithmetic = [i for i in issues if "mL of" in i and "is" in i]
    assert not arithmetic, "the arithmetic is consistent; that is the problem"


def test_a_thousandfold_outlier_is_refused_visibly(monkeypatch):
    d = copy.deepcopy(dc.DRUGS["morphine"])
    bad = next(e for e in d["dose_entries"] if isinstance(e["dose_range"], dict))
    bad["dose_range"] = {"min": 100.0, "max": 100.0, "units": "mg/kg",
                         "per_kg": True}                    # 7000 mg at 70 kg
    # max_single would otherwise clamp this back to 10 mg and hide it — which
    # is the cap doing its job, and worth knowing: a capped entry is already
    # protected from a magnitude error, so this lint matters most where the
    # source states no maximum.
    bad["max_single"] = None
    monkeypatch.setattr(dc, "DRUGS", {"morphine": d})
    problems = dc.lint_dose_magnitude()
    assert problems and "unit error" in problems[0]
    assert bad.get("_unit_error")
    forced = copy.deepcopy(bad)
    forced.update({"signoff": True, "reviewed_by": "clinician",
                   "review_date": "2026-08-25"})
    ok, why = dc.entry_is_servable(forced)
    assert not ok and "magnitude" in why


def test_the_shipped_file_has_no_magnitude_outliers():
    assert dc.refresh_dose_magnitude_lint() == []


def test_the_threshold_clears_the_widest_real_spread():
    """Epinephrine legitimately spans 500x — 10 mcg push against 5 mg
    nebulised. The threshold is 1000x, so the margin is two. Asserted so that
    a future entry narrowing it fails here rather than in the field."""
    doses = [dc.resolve_dose(e, 70.0)["dose_mg"]
             for e in dc.DRUGS["epinephrine"]["dose_entries"]]
    doses = [x for x in doses if x]
    spread = max(doses) / min(doses)
    assert spread < dc.DOSE_MAGNITUDE_FACTOR
    assert spread > 100, "if epinephrine's real spread shrank, re-derive this"


@pytest.mark.parametrize("vol,ok", [
    (0.001, False), (0.049, False), (0.05, True), (2.4, True),
    (60.0, True), (61.0, False), (250.0, False),
])
def test_only_a_drawable_volume_is_served(vol, ok):
    assert dcn.drawable(vol)[0] is ok


def test_the_epinephrine_push_dose_refuses_rather_than_printing_001_ml(monkeypatch):
    """10 mcg is 0.01 mL of the 1 mg/mL ampoule and 1 mL of the 10 mcg/mL
    dilution NASEMSO actually specifies. The kit declares the ampoule, so the
    honest answer is a refusal naming the reason — not a volume nobody can draw.
    """
    entries = copy.deepcopy(dcn.ENTRIES)
    entries["epinephrine"]["presentations"] = [
        dict(p, signoff=True, reviewed_by="clinician", review_date="2026-08-25")
        for p in entries["epinephrine"]["presentations"]]
    monkeypatch.setattr(dcn, "ENTRIES", entries)
    cand = oc.resolve_dose_volume(
        oc.DoseCandidate(drug="epinephrine", indication="push dose", route="IV",
                         dose_mg=0.01, display_value=10.0, display_units="mcg",
                         source="test"))
    assert cand.volume_ml is None
    assert "dilution" in (cand.volume_refusal or "")
    line = oc.render_give_line(cand)
    assert "10 mcg" in line and "NO VOLUME" in line


def test_a_max_single_cap_already_absorbs_a_magnitude_error():
    """Found while writing the test above: morphine's 10 mg cap clamped a
    synthetic 7000 mg dose straight back to 10 mg.

    So the magnitude lint is not the only guard — it is the guard for entries
    whose source states no maximum, which is most of them.
    """
    e = copy.deepcopy(entry_for("morphine", indication="acute pain / analgesia",
                                population="adult", route="IV"))
    e["dose_range"] = {"min": 100.0, "max": 100.0, "units": "mg/kg",
                       "per_kg": True}
    assert dc.resolve_dose(e, 70.0)["dose_mg"] == 10.0
