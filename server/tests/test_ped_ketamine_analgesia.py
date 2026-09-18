"""
EdgeCDSS — paediatric ketamine analgesia serves SMOG's paediatric column.

OWNER RULING 2026-09-18 (#65). SMOG CY24 p.127 states a paediatric IV
analgesia dose (0.1-0.2 mg/kg; the signed value is 0.2 mg/kg), a "<3 mo"
contraindication and "avoid 0.5-0.9 mg/kg IV" for emergence phenomena. For a
child that entry serves in place of NASEMSO's all-ages 0.25 mg/kg, which stays
signed, still serves adults, and is named on the paediatric entry as the
general-EBM alternate under the dual-domain rule.

    cd server && ./run_unit_tests.sh
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402

ANALGESIA = "moderate to severe pain / analgesia"


def _ctx(weight, ped, age=None):
    return oc.PatientContext(confirmed_weight_kg=weight, weight_source="stated",
                             route_preference="IV", is_pediatric=ped,
                             age_years=age)


def _section(card, name):
    return card.split(f"**{name}**")[1].split("**", 1)[0]


def test_a_25kg_child_is_served_the_smog_paediatric_dose():
    ctx = _ctx(25.0, ped=True, age=6.0)
    d = oc._contract_analgesia_candidate(ctx)
    assert d is not None and d.dose_mg == 5.0, "0.2 mg/kg x 25 kg"
    assert d.source.startswith(f"drug_contract:ketamine:{ANALGESIA}:IV:")

    card = oc.build_ketamine_analgesia_response(ctx)
    assert "ketamine IV: 5 mg" in _section(card, "GIVE")
    assert "6.25 mg" not in _section(card, "GIVE"), "the NASEMSO all-ages dose served a child"
    cautions = _section(card, "CAUTIONS")
    assert "Avoid 0.5-0.9 mg/kg IV" in cautions
    assert "NASEMSO gives 0.25 mg/kg" in cautions, "the general-EBM alternate is not named"

    # The card's SOURCE line names no guideline by design (ruling 8); the
    # citation is one question away, and it is SMOG's paediatric column.
    why = oc.build_why_this_dose_response(
        "why this dose?", "ketamine IV for pain 25kg child", ctx)
    assert "SMOG" in why and "p.127" in why
    assert "0.2 mg/kg (peds)" in why


def test_a_named_ketamine_lookup_for_a_child_does_not_serve_both_analgesia_doses():
    """signed_entries_for() is the name-lookup path the generator's
    ALLOWED_DOSES is built from. Two analgesia entries there would be two
    doses for one pain."""
    pairs = dc.signed_entries_for("ketamine for pain", is_pediatric=True)
    analg = [e for n, e in pairs if e["indication"] == ANALGESIA and e["route"] == "IV"]
    assert [e["population"] for e in analg] == ["peds"]


def test_a_2_month_old_is_shown_the_under_3_months_contraindication():
    ctx = oc.extract_patient_context("2 month old 5kg needs ketamine IV for pain")
    assert ctx.age_years is not None and ctx.age_years < 0.25
    assert ctx.is_pediatric

    card = oc.build_ketamine_analgesia_response(ctx)
    assert "Age < 3 months" in _section(card, "CONTRAINDICATIONS")


def test_an_80kg_adult_is_unchanged():
    ctx = _ctx(80.0, ped=False)
    d = oc._contract_analgesia_candidate(ctx)
    assert d.dose_mg == 20.0, "NASEMSO 0.25 mg/kg x 80 kg"

    card = oc.build_ketamine_analgesia_response(ctx)
    assert "ketamine IV: 20 mg" in _section(card, "GIVE")
    for peds_only in ("Age < 3 months", "Avoid 0.5-0.9 mg/kg IV", "general-EBM alternate"):
        assert peds_only not in card, f"the paediatric entry leaked to an adult: {peds_only}"

    entry = next(e for e in dc.servable_entries()["ketamine"]
                 if e["indication"] == ANALGESIA and e["route"] == "IV"
                 and e["population"] == "adult|peds")
    assert entry["dose_range"]["min"] == 0.25


def test_a_population_specific_entry_supersedes_a_shared_one_only_on_the_same_route():
    """The rule, on synthetic entries so it holds whatever the bank signs."""
    shared_iv = {"indication": "x", "route": "IV", "population": "adult|peds"}
    shared_im = {"indication": "x", "route": "IM", "population": "adult|peds"}
    peds_iv = {"indication": "x", "route": "IV", "population": "peds"}
    other = {"indication": "y", "route": "IV", "population": "adult|peds"}
    pairs = [("d", shared_iv), ("d", shared_im), ("d", peds_iv), ("d", other),
             ("e", shared_iv)]
    assert dc._prefer_population_specific(pairs) == [
        ("d", shared_im), ("d", peds_iv), ("d", other), ("e", shared_iv)]
