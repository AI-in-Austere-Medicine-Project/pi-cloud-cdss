"""
EdgeCDSS — paediatric ketamine analgesia serves SMOG's paediatric column.

OWNER RULING 2026-09-18 (#65). SMOG CY24 p.127 states a paediatric IV
analgesia dose (0.1-0.2 mg/kg; the signed value is 0.2 mg/kg), a "<3 mo"
contraindication and "avoid 0.5-0.9 mg/kg IV" for emergence phenomena. A
STATED age under 3 months blocks the dose; an unknown age does not. For a
child that entry serves in place of NASEMSO's all-ages 0.25 mg/kg, which stays
signed, still serves adults, and is named on the paediatric entry as the
general-EBM alternate under the dual-domain rule.

    cd server && ./run_unit_tests.sh
"""
import os

import pytest

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


def _served(q, history=()):
    class _NoRetrieval:
        def query(self, *a, **k):
            raise AssertionError("reached retrieval")
    return oc._query_with_rag_internal(q, _NoRetrieval(), conversation_history=list(history))


def test_a_stated_age_under_3_months_blocks_the_dose():
    """OWNER RULING 2026-09-18: block, not just show. Refused on the first
    turn — asking for a weight and a route would only lead to a refusal."""
    ctx = oc.extract_patient_context("2 month old 5kg needs ketamine IV for pain")
    assert ctx.age_years is not None and ctx.age_years < 0.25 and ctx.is_pediatric

    r = _served("2 month old, ketamine for pain")
    card = r["response"]
    assert r["validator_result"] == "UNSAFE"
    assert "Do not give ketamine: contraindicated under 3 months of age (stated age 2 months)" in card
    assert "Age < 3 months" in _section(card, "CONTRAINDICATIONS")
    assert "SMOG" in card and "p.127" in card
    for dose in ("**GIVE**", " mg.", "mL", "Dilute"):
        assert dose not in card, f"a dose reached a contraindicated infant: {dose!r}"
    assert "Do not give ketamine: contraindicated under 3 months" in r["brief"]
    assert "DON'T" in r["critical_sections"]


@pytest.mark.parametrize("route", ["IV", "IM"])
def test_the_analgesia_card_refuses_on_every_route(route):
    """IM has no contract entry and backfills from the calculator. The block
    must hold there too."""
    ctx = oc.PatientContext(confirmed_weight_kg=5.0, weight_source="stated",
                            route_preference=route, is_pediatric=True,
                            age_years=2 / 12)
    card = oc.build_ketamine_analgesia_response(ctx)
    assert card.startswith("**DON'T**\n- Do not give ketamine")
    assert "**GIVE**" not in card


def test_a_blocked_peds_entry_does_not_hand_back_the_shared_dose():
    """Dropping the peds entry must not leave NASEMSO's adult|peds 0.25 mg/kg
    standing in for it."""
    age = 2 / 12
    assert dc.signed_entries_by_indication(["moderate to severe pain"], True, age) == []
    named = dc.signed_entries_for("ketamine for pain", is_pediatric=True, age_years=age)
    assert not [e for n, e in named if e["indication"] == ANALGESIA]
    ctx = _ctx(5.0, ped=True, age=age)
    assert all(d.indication != ANALGESIA for d in oc.build_allowed_doses("ketamine for pain", ctx))


@pytest.mark.parametrize("age", [0.25, 6.0, None])
def test_three_months_and_up_or_unstated_still_doses(age):
    """The floor is 'under 3 months'. An unknown age blocks nothing: refusing
    every child whose age was not said would take the dose from the patients
    it is signed for. The contraindication is still shown."""
    card = oc.build_ketamine_analgesia_response(_ctx(25.0, ped=True, age=age))
    assert "ketamine IV: 5 mg" in _section(card, "GIVE")
    assert "Age < 3 months" in _section(card, "CONTRAINDICATIONS")


def test_an_age_floor_is_stated_where_the_medic_reads_it():
    """The machine-readable floor and the words agree. A peds-only entry lists
    it as a contraindication; an adult|peds entry records it on the detail
    tier instead, so an adult's card does not carry an infant-only line."""
    for name, entries in dc.servable_entries().items():
        for e in entries:
            floor = e.get("min_age_months")
            if floor is None:
                continue
            if e["population"] == "peds":
                assert f"Age < {floor:g} months" in e["contraindications"], name
            else:
                assert any("AGE FLOOR" in c for c in dc.detail_cautions(e)), name
            assert any(s.get("source_class") == "SMOG" and "p.127" in s["citation"]
                       for s in e["sources"]), f"{name}: the age floor cites nothing"


def test_every_ketamine_entry_a_child_can_be_served_has_the_age_floor():
    """SMOG's "Children <3 mo. age" is a contraindication to the drug, not to
    one indication (owner ruling 2026-09-18)."""
    for e in dc.servable_entries()["ketamine"]:
        if e["population"] != "adult":
            assert e.get("min_age_months") == 3, e["indication"]


def test_nothing_ketamine_reaches_a_stated_infant_by_any_lookup():
    age = 2 / 12
    by_name = dc.signed_entries_for("ketamine", is_pediatric=True, age_years=age)
    assert [n for n, e in by_name if n == "ketamine"] == []
    by_ind = dc.signed_entries_by_indication(
        ["RSI induction", "post-intubation sedation", "ongoing sedation",
         "dissociative sedation", "pain"], True, age)
    assert [n for n, e in by_ind if n == "ketamine"] == []


def test_the_rsi_card_names_the_age_block_for_an_infant():
    ctx = oc.PatientContext(confirmed_weight_kg=5.0, weight_source="stated",
                            route_preference="IV", is_pediatric=True, age_years=2 / 12)
    card = oc.build_rsi_response(ctx, "RSI 2 month old 5kg ketamine and roc")
    give = _section(card, "GIVE")
    assert "ketamine induction: contraindicated under 3 months of age" in give
    assert "before the paralytic" in give
    assert "No signed contract" not in card, "the bank is not silent; the patient is ruled out"
    assert "ketamine post-intubation sedation: contraindicated" in _section(
        card, "POST-INTUBATION SEDATION")
    assert "- Do not give ketamine: contraindicated under 3 months" in card.split("**DON'T**")[1]
    assert not [l for l in card.splitlines() if "ketamine" in l and ("Draw" in l or " mg" in l)], \
        "a ketamine dose was served"


def test_a_3_month_old_still_gets_the_ketamine_rsi_bundle():
    ctx = oc.PatientContext(confirmed_weight_kg=6.0, weight_source="stated",
                            route_preference="IV", is_pediatric=True, age_years=0.25)
    card = oc.build_rsi_response(ctx, "RSI 3 month old 6kg ketamine and roc")
    assert "contraindicated under 3 months" not in card
    assert "ketamine" in _section(card, "GIVE") and "RSI induction" in _section(card, "GIVE")


def test_a_malformed_age_floor_is_refused():
    import copy
    e = copy.deepcopy(next(e for e in dc.servable_entries()["ketamine"]
                           if e.get("min_age_months")))
    e["min_age_months"] = "3"
    ok, why = dc.entry_is_servable(e, dc.DRUGS["ketamine"])
    assert not ok and "min_age_months" in why


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
