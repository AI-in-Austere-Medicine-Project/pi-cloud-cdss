"""Signing batch 4: the EMS set's rulings (owner, Andrew Azelton, 2026-11-12).

Owner: "Sign every drug entry in the EMS set as transcribed, with these
conditions: 1. Before signing, run two checks and list every failure instead of
signing it: (a) re-read each entry's dose, unit, max and route from the PDF's
text layer and compare with the packet entry; (b) for every paediatric entry
with a weight table, check that dose per kg x weight / concentration matches
the printed mL for each weight band within rounding. 2. Entries you flagged in
the packet [...] are not signed by this message. 3. The 9 non-drug rows [...]
stay unsigned unless the engine can express them. 4. Kit: each formulary
concentration is declared as the EMS kit vial (owner declaration, recorded in
KIT_DECLARATIONS). Where a drug has more than one concentration, an entry uses
the concentration its own row states; otherwise the vial question stays. 5. A
line becomes a hold only if the formulary lists it under Contraindications.
Adverse effects are cautions, spoken under "why"."

The formulary stays outside the repo; these tests pin what entered it: which
entries are signed (the 22 that passed every condition), their shape, the set
they serve in, the kit vial each uses, and the kit file per set.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import pathlib
import sys

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import drug_concentrations as cc  # noqa: E402
import drug_contracts as dc  # noqa: E402

ROOT = pathlib.Path(dc.__file__).resolve().parents[1]
DECLARATIONS = ROOT / "docs" / "authoring" / "KIT_DECLARATIONS.md"

# The entries signed by the 2026-11-12 rulings: every other packet entry failed
# a condition and is listed in the work order for its own ruling.
SIGNED = {
    "EMS-001": ("acetaminophen", "adult", "PO", 650, 650, "mg", "none"),
    "EMS-002": ("acetaminophen", "adult", "IV", 1, 1, "g", 10.0),
    "EMS-016": ("aspirin", "adult", "PO", 324, 324, "mg", "none"),
    "EMS-018": ("atropine", "adult", "IV", 2, 2, "mg", 0.4),
    "EMS-019": ("atropine", "adult", "IM", 2, 2, "mg", 0.4),
    "EMS-020": ("atropine", "adult", "IV", 0.8, 0.8, "mg", 0.4),
    "EMS-076": ("epinephrine", "adult", "IM", 0.3, 0.3, "mg", 1.0),
    "EMS-077": ("epinephrine", "adult", "NEB", 2, 2, "mg", 1.0),
    "EMS-080": ("epinephrine", "adult", "NEB", 1, 1, "mg", 1.0),
    "EMS-089": ("epinephrine", "peds", "NEB", 0.5, 0.5, "mg", None),
    "EMS-126": ("ketamine", "adult", "IM", 25, 50, "mg", 100.0),
    "EMS-138": ("lidocaine", "adult", "IV", 100, 100, "mg", 20.0),
    "EMS-139": ("lidocaine", "adult", "IV", 100, 100, "mg", 20.0),
    "EMS-142": ("lidocaine", "peds", "IV", 1, 1, "mg/kg", 20.0),
    "EMS-181": ("norepinephrine", "adult", "IV", 2, 20, "mcg/min", "none"),
    "EMS-182": ("norepinephrine", "adult", "IV", 24, 32, "mcg", "none"),
    "EMS-187": ("ondansetron", "adult", "IM", 4, 4, "mg", 2.0),
    "EMS-188": ("ondansetron", "adult", "IV", 4, 4, "mg", 2.0),
    "EMS-192": ("dextrose", "adult", "PO", 15, 15, "g", "none"),
    "EMS-210": ("tranexamic acid", "adult", "IN", 1, 1, "g", 100.0),
    "EMS-214": ("tranexamic acid", "peds", "IN", 15, 15, "mg/kg", 100.0),
    "EMS-216": ("tranexamic acid", "peds", "IV", 15, 15, "mg/kg", 100.0),
}


def _ems_entries():
    raw = json.loads((ROOT / "server" / "drug_contracts.json").read_text())
    return [(d["generic_name"], d, e) for d in raw["drugs"] for e in d["dose_entries"]
            if e.get("set") == "EMS"]


# ── which entries, and as transcribed ───────────────────────────────────────

def test_exactly_the_entries_that_passed_every_condition_are_in_the_ems_set():
    got = {e["ems_item"]: n for n, _, e in _ems_entries()}
    assert sorted(got) == sorted(SIGNED)
    for item, name in got.items():
        assert name == SIGNED[item][0], item


@pytest.mark.parametrize("item", sorted(SIGNED))
def test_each_signed_entry_is_the_transcribed_dose(item):
    name, pop, route, lo, hi, units, _ = SIGNED[item]
    (e,) = [e for _, _, e in _ems_entries() if e["ems_item"] == item]
    assert (e["population"], e["route"]) == (pop, route)
    dr = e["dose_range"]
    assert (dr["min"], dr["max"], dr["units"]) == (lo, hi, units)
    assert dr["per_kg"] == ("/kg" in units)


def test_every_ems_entry_is_signed_by_the_owners_ruling():
    for _, _, e in _ems_entries():
        assert e["signoff"] is True and e["reviewed_by"] == "clinician"
        assert e["review_date"] == "2026-11-12"
        assert "Andrew Azelton" in e["adjudication"]


def test_every_ems_source_gives_the_card_page_and_a_short_quote():
    for _, _, e in _ems_entries():
        (s,) = e["sources"]
        assert s["source_class"] == "EMS" and s["tier"] == 1
        assert isinstance(s["page"], int) and 1 <= s["page"] <= 61
        assert 0 < len(s["quote"]) <= 160
        assert "MD " in s["citation"] and "updated" in s["citation"]
        assert "formulary" in s["url"].lower() and "repository" in s["url"].lower()


# ── ruling 5: contraindications hold, adverse effects are "why" ─────────────

def test_adverse_effects_are_detail_cautions_and_never_contraindications():
    for _, _, e in _ems_entries():
        adverse = [c for c in e["cautions"] if dc.caution_text(c).startswith("Adverse/side effects")]
        assert len(adverse) == 1 and dc.caution_tier(adverse[0]) == dc.CAUTION_DETAIL
        assert not any("adverse" in c.lower() for c in e["contraindications"])


def test_none_under_contraindications_is_no_contraindication():
    for _, _, e in _ems_entries():
        assert not any(c.strip().lower().startswith("none") for c in e["contraindications"])


# ── served in EMS only ──────────────────────────────────────────────────────

def test_every_ems_entry_serves_under_ems_and_never_under_pfc():
    for n, d, e in _ems_entries():
        live = dc.DRUGS[n]
        ok, why = dc.entry_is_servable(e, live, served_set="EMS")
        assert ok, (e["ems_item"], why)
        assert not dc.entry_is_servable(e, live, served_set="PFC")[0]


def test_the_pfc_bank_is_untouched_by_the_ems_fields():
    raw = json.loads((ROOT / "server" / "drug_contracts.json").read_text())
    for d in raw["drugs"]:
        for e in d["dose_entries"]:
            if e.get("set") == "PFC":
                assert "kit_vial" not in e and "indication_class" not in e and "ems_item" not in e


# ── the EMS entry's own fields ──────────────────────────────────────────────

def test_an_ems_entry_must_name_its_class_and_its_kit_vial_choice():
    _, d, e = _ems_entries()[0]
    for field in ("indication_class", "kit_vial"):
        bare = {k: v for k, v in e.items() if k != field}
        if field == "kit_vial" and e["ems_item"] == "EMS-089":
            continue
        ok, why = dc.entry_is_servable(bare, d, served_set="EMS")
        assert not ok and field in why, why


@pytest.mark.parametrize("bad", [0, -1, "0.4", "None", True, [1.0]])
def test_a_kit_vial_is_a_positive_strength_or_none(bad):
    _, d, e = [x for x in _ems_entries() if x[2]["ems_item"] == "EMS-018"][0]
    ok, why = dc.entry_is_servable(dict(e, kit_vial=bad), d, served_set="EMS")
    assert not ok and "kit_vial" in why, why


def test_the_vial_question_entry_says_so():
    """EMS-089 states both 1:1,000 and 1:10,000: no kit_vial, so the vial question stays."""
    (e,) = [e for _, _, e in _ems_entries() if e["ems_item"] == "EMS-089"]
    assert e.get("kit_vial", "ABSENT") is None


# ── ruling 4: the kit, per set ──────────────────────────────────────────────

def test_each_set_has_its_own_kit_file():
    assert cc._config_for(None).name == "drug_concentrations.json"
    assert cc._config_for("PFC").name == "drug_concentrations.json"
    assert cc._config_for("EMS").name == "drug_concentrations_ems.json"


def _two_vials(monkeypatch):
    pres = lambda mg, ml: {"label_text": f"{mg:g} mg / {ml:g} mL", "mass_mg": mg, "volume_ml": ml,  # noqa: E731
                           "concentration_mg_ml": mg / ml, "signoff": True, "reviewed_by": "clinician",
                           "review_date": "2026-11-12"}
    monkeypatch.setitem(cc.ENTRIES, "testosteril", {"generic_name": "testosteril", "confirm_required": True,
                                                    "presentations": [pres(1, 1), pres(1, 10)]})


def test_a_pinned_kit_vial_resolves_without_the_question(monkeypatch):
    _two_vials(monkeypatch)
    assert cc.resolve("testosteril")[0] == cc.NEEDS_CONFIRMATION
    status, conc, _ = cc.resolve("testosteril", pinned=1.0)
    assert (status, conc) == (cc.RESOLVED, 1.0)
    assert cc.resolve("testosteril", pinned=0.1)[1] == 0.1


def test_a_pinned_strength_the_kit_does_not_hold_is_still_the_question(monkeypatch):
    _two_vials(monkeypatch)
    assert cc.resolve("testosteril", pinned=5.0)[0] == cc.NEEDS_CONFIRMATION


def test_a_strength_the_medic_confirmed_wins_over_the_pin(monkeypatch):
    _two_vials(monkeypatch)
    assert cc.resolve("testosteril", {"testosteril": 0.1}, pinned=1.0)[1] == 0.1


def test_kit_vial_none_never_gives_a_volume(monkeypatch):
    import openai_client as oc
    _two_vials(monkeypatch)
    monkeypatch.setitem(cc.ENTRIES, "testosteril", dict(cc.ENTRIES["testosteril"], confirm_required=False,
                                                        presentations=cc.ENTRIES["testosteril"]["presentations"][:1]))
    d = oc.DoseCandidate(drug="testosteril", indication="t", route="PO", dose_mg=1.0, source="t")
    assert oc.resolve_dose_volume(d).volume_ml == 1.0
    d = oc.DoseCandidate(drug="testosteril", indication="t", route="PO", dose_mg=1.0, source="t", kit_vial="none")
    assert oc.resolve_dose_volume(d).volume_ml is None


def test_a_pinned_candidate_takes_its_volume_from_the_pinned_vial(monkeypatch):
    import openai_client as oc
    _two_vials(monkeypatch)
    d = oc.DoseCandidate(drug="testosteril", indication="t", route="IM", dose_mg=0.3, source="t")
    assert oc.resolve_dose_volume(d).volume_ml is None
    d = oc.DoseCandidate(drug="testosteril", indication="t", route="IM", dose_mg=0.3, source="t", kit_vial=1.0)
    assert oc.resolve_dose_volume(d).volume_ml == pytest.approx(0.3)


def test_the_ems_kit_declarations_are_recorded():
    text = DECLARATIONS.read_text()
    assert "EMS kit" in text
    for drug, strength in [("acetaminophen", "10 mg/mL"), ("atropine", "0.4 mg/mL"), ("epinephrine", "1 mg/mL"),
                           ("epinephrine", "0.1 mg/mL"), ("ketamine", "100 mg/mL"), ("lidocaine", "20 mg/mL"),
                           ("ondansetron", "2 mg/mL"), ("tranexamic acid", "100 mg/mL")]:
        assert any(drug in line and strength in line and "EMS kit" in line for line in text.splitlines()), (drug, strength)


def test_conflicting_card_strengths_are_not_declared():
    text = DECLARATIONS.read_text()
    for drug in ("adenosine", "calcium chloride", "magnesium sulfate", "pralidoxime"):
        assert not any(f"| {drug} |" in line and "EMS kit" in line for line in text.splitlines()), drug


# ── the export ──────────────────────────────────────────────────────────────

def test_the_ems_export_names_its_files_for_the_set():
    import export_pocket_bank as ex
    assert ex.file_names("PFC") == {"bank": "bank.json", "kit": "kit.json", "manifest": "manifest.json"}
    assert ex.file_names("EMS") == {"bank": "bank-ems.json", "kit": "kit-ems.json", "manifest": "manifest-ems.json"}


def test_the_ems_bank_carries_the_class_and_kit_vial_of_each_entry():
    import export_pocket_bank as ex
    bank = ex.build_bank(dc.DRUGS, "t", classify=lambda label: None, set_name="EMS")
    assert len(bank["entries"]) == len(SIGNED)
    for e in bank["entries"]:
        assert e["set"] == "EMS" and e["indication_class"]
        assert "kit_vial" in e
