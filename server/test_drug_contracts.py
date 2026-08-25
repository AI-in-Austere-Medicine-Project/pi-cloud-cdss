"""
Drug dose-contract engine — the fence, the aliases, and the migration.

NOTHING in drug_contracts.json is signed. That is the shipped state and these
tests assert it: the contract layer is structure and refusal until a
credentialed clinician signs an entry, and every drug that had no dose before
this module still has no dose after it.

The serve-path tests build signed entries locally. Those fixtures carry
obviously-synthetic values (drug "TESTOSTERIL", 1 mg/kg of a 1 mg/mL solution)
and no real pharmacology: a fixture that looked like a real dose would be
exactly the thing the fence exists to prevent, sitting in the repo where
somebody could paste it into the contract file.

THE COLLISION THIS CLOSES THE CLASS OF
──────────────────────────────────────
`query_aliases.json` mapped "vitamin k" onto ketamine as a dictation-mangling
alias, and build_allowed_doses() hardcoded `'vitamin k' in q`. So discovery
scenario A1-COL-004, "vitamin K dose for warfarin reversal", built a ketamine
analgesia contract for a warfarin-reversal question. Fifth specimen of the
substring/shadow collision class in this codebase. The fix is word-anchored
matching PLUS a lint that forbids an alias from shadowing a real drug, because
the previous four specimens were each fixed as instances and the class kept
coming back.
"""
import collections
import copy
import json
import re

import pytest

import drug_contracts as dc
import openai_client as oc
from openai_client import PatientContext


# ── fixtures: obviously-synthetic signed entries ────────────────────────────

def _synthetic_source(tier=1):
    return {"citation": "TEST citation", "tier": tier, "url": "test://source",
            "retrieved_date": "2026-08-24"}


def signed_entry(**overrides):
    """A complete, signable entry with nothing real in it."""
    e = {
        "indication": "TEST indication",
        "population": "adult|peds",
        "route": "IV",
        "dose_range": {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True},
        "max_single": None,
        "max_cumulative": None,
        "contraindications": ["TEST contraindication"],
        "cautions": ["TEST caution"],
        "sources": [_synthetic_source()],
        "signoff": True,
        "reviewed_by": "clinician",
        "review_date": "2026-08-24",
        "version": "0.1.0-test",
    }
    e.update(overrides)
    return e


def synthetic_drug(**overrides):
    d = {
        "generic_name": "testosteril",
        "aliases": ["tstl"],
        "drug_class": "TEST class",
        "forms": [{"description": "TEST form", "concentration_mg_ml": 1.0,
                   "sources": [_synthetic_source()]}],
        "routes": ["IV"],
        "tropical_priority": False,
        "discovery_rank": None,
        "discovery_query_count": 0,
        "dose_entries": [signed_entry()],
    }
    d.update(overrides)
    return d


@pytest.fixture
def live(monkeypatch):
    """Install one synthetic signed drug as the whole contract file."""
    d = synthetic_drug()
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    return d


# ═══════════════════════════════════════════════════════════════════════════
# THE SHIPPED STATE
# ═══════════════════════════════════════════════════════════════════════════

def test_the_shipped_contract_file_is_entirely_unsigned():
    """The state this module ships in, asserted rather than assumed.

    If this ever fails, someone signed clinical content in a code change rather
    than in a review, and that is the one thing this layer must make loud.
    """
    signed = [(name, e.get("indication"), e.get("route"))
              for name, d in dc.DRUGS.items()
              for e in d.get("dose_entries", []) if e.get("signoff") is not False]
    assert signed == [], f"entries are signed in the shipped file: {signed}"


def test_nothing_is_servable_today():
    assert dc.servable_entries() == {}


def test_no_signed_contract_kept_a_sentinel_anywhere():
    """A signed entry must not carry a sentinel in ANY field.

    Not just the fields the schema calls clinical — EVERY field, at every
    depth, including cautions, contraindications, extraction_notes and the
    source records. PENDING_CLINICAL_SIGNOFF and NEEDS_MANUAL_ENTRY are not
    strings a medic should ever read, and a half-authored entry that got signed
    is precisely how one would reach them.

    Vacuously true while nothing is signed. It stops being vacuous on the day
    the owner signs the first entry, which is the day it matters.
    """
    leaked = []
    for name, drug in dc.DRUGS.items():
        for e in drug.get("dose_entries", []):
            if e.get("signoff") is not True:
                continue
            for field, value in e.items():
                if dc.has_sentinel(value):
                    leaked.append(f"{name}/{e.get('indication')}/{field}")
    assert not leaked, f"signed entries still carry a sentinel in: {leaked}"


def test_a_sentinel_bearing_signed_contract_is_refused(live):
    """Signing does not launder an unauthored field."""
    for field, bad in [
            ("indication", dc.PENDING),
            ("route", dc.NEEDS_MANUAL),
            ("dose_range", dc.NEEDS_MANUAL),
            ("cautions", [dc.NEEDS_MANUAL]),
            ("contraindications", [dc.PENDING]),
    ]:
        e = signed_entry(**{field: bad})
        ok, why = dc.entry_is_servable(e)
        assert not ok, f"a signed entry with {field}={bad!r} was accepted"
        assert dc.PENDING in why or dc.NEEDS_MANUAL in why or "sentinel" in why


def test_a_sentinel_in_any_field_at_all_is_refused(live):
    """Including fields the schema does not call clinical."""
    for field in ("extraction_notes", "adjudication", "version"):
        e = signed_entry(**{field: dc.NEEDS_MANUAL})
        ok, why = dc.entry_is_servable(e)
        assert not ok, f"a signed entry with a sentinel in {field} was accepted"


@pytest.mark.parametrize("breakage,reason_fragment", [
    ({"signoff": False}, "signoff is not true"),
    ({"signoff": "true"}, "signoff is not true"),
    ({"reviewed_by": "nobody"}, "authorised signer"),
    ({"reviewed_by": dc.PENDING}, "authorised signer"),
    ({"review_date": ""}, "review_date"),
    ({"review_date": dc.PENDING}, "review_date"),
    ({"sources": []}, "sources"),
    ({"sources": [{"citation": "x"}]}, "missing"),
    ({"dose_range": {"min": 1, "max": 1, "units": "mg/kg"}}, "per_kg"),
    ({"dose_range": {"min": 5, "max": 1, "units": "mg/kg", "per_kg": True}},
     "below"),
    ({"population": "grown-ups"}, "population"),
])
def test_every_way_an_entry_can_be_incomplete_is_refused(breakage, reason_fragment):
    ok, why = dc.entry_is_servable(signed_entry(**breakage))
    assert not ok
    assert reason_fragment in why, f"expected {reason_fragment!r} in {why!r}"


def test_a_missing_field_is_refused_by_name():
    e = signed_entry()
    del e["max_cumulative"]
    ok, why = dc.entry_is_servable(e)
    assert not ok and "max_cumulative" in why


def test_a_null_maximum_is_a_real_answer_not_a_sentinel():
    """`max_single: null` means the cited source states no maximum.

    That is a fact about the source and it must be signable, or every entry
    whose source is silent on a ceiling becomes permanently unservable.
    """
    ok, why = dc.entry_is_servable(signed_entry(max_single=None,
                                                max_cumulative=None))
    assert ok, why


def test_there_is_no_override_that_serves_an_unsigned_entry(monkeypatch):
    """No env var, no debug flag, no anything."""
    for var in ("CDSS_SERVE_PENDING_CARDS", "CDSS_SERVE_PENDING_DOSES",
                "EDGECDSS_DEBUG_WARN_ONLY", "CDSS_DEBUG"):
        monkeypatch.setenv(var, "1")
    d = synthetic_drug(dose_entries=[signed_entry(signoff=False)])
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    assert dc.servable_entries() == {}
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    assert oc._contract_dose_candidates("testosteril dose", ctx) == []


def test_an_unsigned_drug_serves_no_dose_and_falls_through(monkeypatch):
    """The whole point: unsigned drug -> empty contract -> existing fallback."""
    d = synthetic_drug(dose_entries=[signed_entry(signoff=False)])
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    assert oc.build_allowed_doses("how much testosteril", ctx) == []


def test_a_signed_entry_actually_reaches_the_serving_path(live):
    """The fence must be a gate, not a wall — control for the refusal tests."""
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    doses = oc._contract_dose_candidates("testosteril dose", ctx)
    assert len(doses) == 1
    d = doses[0]
    assert (d.drug, d.route, d.dose_mg, d.volume_ml) == \
           ("testosteril", "IV", 80.0, 80.0)
    assert d.source.startswith("drug_contract:testosteril")


# ═══════════════════════════════════════════════════════════════════════════
# POPULATE ONLY FROM THE TWO APPROVED SOURCES
# ═══════════════════════════════════════════════════════════════════════════

def test_an_entry_sourced_only_to_the_migration_cannot_be_signed():
    """Tier 0 carries the four pre-contract hardcodes into the model.

    It is not clinical evidence, and an entry that cites nothing else must not
    become servable just because someone signed it — otherwise the migration
    launders four unsourced numbers into served doses.
    """
    e = signed_entry(sources=[_synthetic_source(tier=0)])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "approved source" in why


@pytest.mark.parametrize("tier", [1, 2])
def test_either_approved_tier_is_enough(tier):
    ok, why = dc.entry_is_servable(signed_entry(sources=[_synthetic_source(tier)]))
    assert ok, why


# Migrated drugs whose value NO approved source corroborates. Lorazepam left
# this set when the NASEMSO extraction landed: Seizures p.102 gives exactly the
# hardcoded rule, so it is corroborated rather than unsourced. Expected to keep
# shrinking as sources are found — that is the point of the migration.
UNSOURCED_MIGRATED = ("ketamine", "rocuronium", "succinylcholine")


@pytest.mark.parametrize("name", UNSOURCED_MIGRATED)
def test_an_unsourced_migrated_entry_cannot_be_signed(name):
    """A migrated value no approved source corroborates stays unsignable.

    Not "is unsigned" — UNSIGNABLE. Forcing signoff true on it must still be
    refused, because the only citation is tier 0 and tier 0 is the migration
    carrier, not evidence.
    """
    drug = dc.DRUGS[name]
    migrated = [e for e in drug["dose_entries"]
                if "MIGRATED_UNSOURCED" in (e.get("flags") or [])]
    assert migrated, f"{name} has no migrated entry"
    for e in migrated:
        assert {s["tier"] for s in e["sources"]} == {0}
        forced = copy.deepcopy(e)
        forced.update({"signoff": True, "reviewed_by": "clinician",
                       "review_date": "2026-08-24"})
        ok, why = dc.entry_is_servable(forced)
        assert not ok, f"{name} migrated entry became servable: {e}"


def test_the_corroborated_migration_became_signable():
    """Lorazepam's migrated value is the one NASEMSO confirmed exactly.

    NASEMSO Seizures p.102: lorazepam 0.1 mg/kg IV or IO, maximum 4 mg —
    identical to lorazepam_seizure_0.1mgkg_max4mg. So this entry carries a
    tier 1 citation alongside the tier 0 one, and the tier rule no longer
    blocks it. It is still UNSIGNED; what changed is that it is now signable.
    """
    entry = next(e for e in dc.DRUGS["lorazepam"]["dose_entries"]
                 if e["indication"] == "active seizure")
    assert entry["signoff"] is False, "nothing may ship signed"
    assert "MIGRATION_CORROBORATED" in entry["flags"]
    tiers = {s["tier"] for s in entry["sources"]}
    assert 1 in tiers and 0 in tiers, tiers

    forced = copy.deepcopy(entry)
    forced.update({"signoff": True, "reviewed_by": "clinician",
                   "review_date": "2026-08-24"})
    ok, why = dc.entry_is_servable(forced)
    assert ok, f"the corroborated migration is still unsignable: {why}"


def test_the_corroborated_value_still_equals_the_calculator():
    """The whole point of corroboration: the number NASEMSO gives and the
    number the code has produced all along are the same number."""
    entry = next(e for e in dc.DRUGS["lorazepam"]["dose_entries"]
                 if e["indication"] == "active seizure")
    for w in (20.0, 45.0, 80.0):
        expected = min(entry["dose_range"]["min"] * w,
                       entry["max_single"]["value"])
        assert round(expected, 1) == oc.lorazepam_seizure(w).dose_mg


def test_every_source_record_is_shaped_like_a_citation():
    for name, drug in dc.DRUGS.items():
        for e in drug.get("dose_entries", []):
            for s in e.get("sources", []):
                assert set(dc._SOURCE_KEYS) <= set(s), f"{name}: {s}"
                assert s["tier"] in (0, 1, 2), f"{name}: bad tier {s['tier']}"


def test_a_signed_source_conflict_must_record_its_adjudication():
    """Two sources disagreeing is kept as BOTH entries, never silently
    resolved. Signing one of them IS the adjudication; saying so is what stops
    the next reader re-opening the question."""
    e = signed_entry(flags=["SOURCE_CONFLICT"])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "adjudication" in why
    ok, why = dc.entry_is_servable(
        signed_entry(flags=["SOURCE_CONFLICT"],
                     adjudication="TEST: took the tier 1 value"))
    assert ok, why


# ═══════════════════════════════════════════════════════════════════════════
# THE COLLISION CLASS
# ═══════════════════════════════════════════════════════════════════════════

def test_vitamin_k_does_not_build_a_ketamine_contract():
    """A1-COL-004, the specimen. THE regression test for this build.

    "vitamin K dose for warfarin reversal" used to return a ketamine analgesia
    contract, because 'vitamin k' was a hardcoded ketamine alias.
    """
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated",
                         route_preference="IV")
    doses = oc.build_allowed_doses("vitamin K dose for warfarin reversal", ctx)
    assert [d.drug for d in doses] == [], \
        f"vitamin K built a contract for: {[d.drug for d in doses]}"


@pytest.mark.parametrize("query", [
    "vitamin K dose for warfarin reversal",
    "does he need vitamin K here",
    "vitamin-k for the INR",
])
def test_vitamin_k_resolves_to_vitamin_k(query):
    assert dc.resolve_drugs(query) == ["phytomenadione"]


@pytest.mark.parametrize("query,expected", [
    ("ket dose for pain", ["ketamine"]),
    ("roc dose now", ["rocuronium"]),
    ("rocephin dose for this infection", ["ceftriaxone"]),
    ("sux or roc for this airway", ["rocuronium", "succinylcholine"]),
    ("start levophed", ["norepinephrine"]),
    ("narcan dose IM", ["naloxone"]),
    ("keppra loading dose", ["levetiracetam"]),
])
def test_established_aliases_still_resolve(query, expected):
    assert sorted(dc.resolve_drugs(query)) == sorted(expected)


@pytest.mark.parametrize("query", [
    "she is on the rocks",            # roc
    "follow the procedure",           # roc
    "check the socket",               # sux-adjacent noise
    "the patient is in Sicily",       # A1-COL-012, epi-adjacent dictation noise
    "market analysis",                # ket
])
def test_no_alias_fires_inside_a_longer_word(query):
    assert dc.resolve_drugs(query) == [], \
        f"{query!r} resolved to {dc.resolve_drugs(query)}"


def test_the_alias_lint_refuses_an_alias_that_shadows_a_real_drug(monkeypatch):
    """THE CLASS FIX, asserted directly.

    Re-introduce exactly the mapping that caused this bug and prove the lint
    catches it. This is what stops specimen six.
    """
    drugs = {
        "ketamine": {"generic_name": "ketamine", "aliases": ["ket", "vitamin k"],
                     "dose_entries": []},
        "vitamin k": {"generic_name": "vitamin k", "aliases": [],
                      "dose_entries": []},
    }
    monkeypatch.setattr(dc, "DRUGS", drugs)
    problems = dc.lint_alias_collisions()
    assert problems, "the lint accepted vitamin k -> ketamine"
    assert any("shadow" in p for p in problems)


def test_the_alias_lint_refuses_two_drugs_claiming_one_alias(monkeypatch):
    drugs = {
        "epinephrine": {"generic_name": "epinephrine", "aliases": ["epi"],
                        "dose_entries": []},
        "norepinephrine": {"generic_name": "norepinephrine", "aliases": ["epi"],
                           "dose_entries": []},
    }
    monkeypatch.setattr(dc, "DRUGS", drugs)
    assert any("claimed by both" in p for p in dc.lint_alias_collisions())


def test_the_shipped_contract_file_passes_the_alias_lint():
    assert dc.lint_alias_collisions() == []


def test_a_combination_product_is_not_shadowed_by_its_components():
    """"artemether + lumefantrine" contains "artemether". Longest match wins,
    so asking for the combination does not also resolve the component."""
    assert dc.resolve_drugs("artemether lumefantrine dose") == \
        ["artemether + lumefantrine"]
    assert dc.resolve_drugs("artemether-lumefantrine") == \
        ["artemether + lumefantrine"]
    assert dc.resolve_drugs("artemether IM for severe malaria") == ["artemether"]


def test_component_overlaps_are_reported_separately_from_collisions():
    """A combination product legitimately contains its components' names.
    Conflating that with a real shadow would either fail the build on a legal
    combination or teach the team to ignore the lint that catches real ones."""
    overlaps = dc.lint_generic_name_overlaps()
    assert any("artemether" in o for o in overlaps)
    assert dc.lint_alias_collisions() == []


def test_proposed_aliases_are_not_live(monkeypatch):
    """Dictation manglings the discovery run observed are held back for owner
    approval: promoting one makes the system answer a query it used to refuse,
    which is a routing change the owner signs off, not one a migration makes."""
    assert "keta mean" in dc.DRUGS["ketamine"].get("proposed_aliases", [])
    assert "keta mean" not in dc.DRUGS["ketamine"]["aliases"]
    assert dc.resolve_drugs("give her keta mean for the pain") == []


# ═══════════════════════════════════════════════════════════════════════════
# THE MIGRATED FOUR — BEHAVIOUR IS UNCHANGED
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("query,weight,route,expected", [
    ("ketamine dose for analgesia IV", 80.0, "IV",
     [("ketamine", "IV", 24.0, 0.24)]),
    ("what is the ketamine dose, no IV yet", 80.0, "IM",
     [("ketamine", "IM", 160.0, 1.6)]),
    ("rocuronium dose for intubation", 80.0, "IV",
     [("ketamine", "IV", 120.0, 1.2), ("ketamine", "IV", 40.0, 0.4),
      ("rocuronium", "IV", 80.0, 8.0)]),
    ("succinylcholine dose for RSI", 80.0, "IV",
     [("ketamine", "IV", 120.0, 1.2), ("ketamine", "IV", 40.0, 0.4),
      ("succinylcholine", "IV", 120.0, 6.0)]),
    ("lorazepam for the seizure", 80.0, "IV",
     [("lorazepam", "IV", 4.0, 2.0)]),
])
def test_the_migrated_four_serve_exactly_what_they_served_before(
        query, weight, route, expected):
    """Migration preserves behaviour byte for byte.

    These four still come from the hardcoded calculators; the contract file
    carries an unsigned migrated draft of each for cross-check. The calculator
    for a drug is deleted only when the owner signs its migrated entry.
    """
    ctx = PatientContext(confirmed_weight_kg=weight, weight_source="stated",
                         route_preference=route)
    got = [(d.drug, d.route, d.dose_mg, d.volume_ml)
           for d in oc.build_allowed_doses(query, ctx)]
    assert got == expected


def test_the_migrated_values_match_the_calculators_they_came_from():
    """The draft in the file is the calculator's value, not a re-derivation.

    If these drift apart, the owner is cross-checking the migration against
    something that is no longer what the system does.
    """
    w = 70.0
    checks = [
        ("ketamine", "subdissociative analgesia", oc.ketamine_analgesia_iv(w)),
        ("ketamine", "dissociative analgesia (IM — no IV access)",
         oc.ketamine_analgesia_im(w)),
        ("ketamine", "post-intubation sedation q20-30min",
         oc.ketamine_post_intubation_iv(w)),
        ("rocuronium", "RSI paralytic", oc.rocuronium_rsi(w, False)),
        ("lorazepam", "active seizure", oc.lorazepam_seizure(w)),
    ]
    for drug_name, indication, candidate in checks:
        entry = next(e for e in dc.DRUGS[drug_name]["dose_entries"]
                     if e["indication"] == indication
                     and isinstance(e["dose_range"], dict))
        rng = entry["dose_range"]
        assert rng["per_kg"] is True and rng["units"] == "mg/kg"
        expected_mg = rng["min"] * w
        cap = entry.get("max_single")
        if isinstance(cap, dict) and cap.get("units") == "mg" and cap.get("value"):
            expected_mg = min(expected_mg, cap["value"])
        assert round(expected_mg, 1) == candidate.dose_mg, \
            f"{drug_name}/{indication}: file says {expected_mg}, code says " \
            f"{candidate.dose_mg}"


def test_the_legacy_four_are_named_and_only_those_four():
    assert set(dc.LEGACY_CALCULATOR_DRUGS) == \
        {"ketamine", "rocuronium", "succinylcholine", "lorazepam"}
    for name in dc.LEGACY_CALCULATOR_DRUGS:
        assert name in dc.DRUGS, f"{name} was not migrated into the model"


def test_the_concentration_mismatches_the_migration_found_are_recorded():
    """WHO lists ketamine at 10/50 mg/mL and suxamethonium at 50 mg/mL; the
    calculators assume 100 mg/mL and 20 mg/mL. That is a volume error at the
    syringe if the wrong one is real, and it is the migration's job to surface
    it rather than pick a side."""
    for name in ("ketamine", "succinylcholine"):
        flagged = [e for e in dc.DRUGS[name]["dose_entries"]
                   if "CONCENTRATION_MISMATCH" in (e.get("flags") or [])]
        assert flagged, f"{name} concentration mismatch is not flagged"


def test_an_ambiguous_concentration_refuses_to_build_a_volume(monkeypatch):
    """A drug carrying two different concentrations cannot be turned into a
    syringe volume, and the engine must refuse rather than pick one."""
    d = synthetic_drug(forms=[
        {"description": "TEST a", "concentration_mg_ml": 1.0, "sources": []},
        {"description": "TEST b", "concentration_mg_ml": 50.0, "sources": []}])
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    assert dc.single_concentration("testosteril") is None
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    assert oc._contract_dose_candidates("testosteril dose", ctx) == []


# ═══════════════════════════════════════════════════════════════════════════
# SCHEMA / STRUCTURE OF THE SHIPPED FILE
# ═══════════════════════════════════════════════════════════════════════════

def test_every_drug_carries_the_required_fields():
    for name, drug in dc.DRUGS.items():
        missing = [f for f in dc._DRUG_REQUIRED if f not in drug]
        assert not missing, f"{name} is missing {missing}"


def test_every_entry_carries_the_required_fields():
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            missing = [f for f in dc._ENTRY_REQUIRED if f not in e]
            assert not missing, f"{name}/{e.get('indication')} missing {missing}"


def test_every_population_is_one_the_engine_understands():
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            assert e["population"] in dc.VALID_POPULATIONS, \
                f"{name}: {e['population']!r}"


def test_no_dose_was_guessed():
    """Every entry either carries a real dose_range or says NEEDS_MANUAL_ENTRY
    with a reason. There is no third state, and in particular no entry with a
    number and no source."""
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            dr = e["dose_range"]
            if dr == dc.NEEDS_MANUAL:
                assert e.get("extraction_notes"), \
                    f"{name}/{e['indication']}: refused without saying why"
            else:
                assert isinstance(dr, dict) and e["sources"], \
                    f"{name}/{e['indication']}: has a number and no source"


def test_the_tropical_subset_is_present_and_distinct():
    tropical = dc.tropical_priority_drugs()
    for expected in ("artesunate", "artemether", "artemether + lumefantrine",
                     "quinine", "antivenom immunoglobulin",
                     "oral rehydration salts", "isoniazid", "rifampicin",
                     "pyrazinamide", "ethambutol"):
        assert expected in tropical, f"{expected} is not in the tropical subset"
    assert "ketamine" not in tropical


def test_the_discovery_ranking_is_recorded_for_the_ranked_drugs():
    """The build order is a measurement, and it has to stay auditable."""
    ranked = {d["generic_name"]: d["discovery_rank"] for d in dc.DRUGS.values()
              if d.get("discovery_rank")}
    assert ranked["ketamine"] == 1
    assert ranked["epinephrine"] == 2
    assert ranked["phytomenadione"] == 16
    for name, rank in ranked.items():
        assert dc.DRUGS[name]["discovery_query_count"] > 0, \
            f"{name} is ranked {rank} but recorded no queries"


def test_the_contract_file_is_valid_json_and_reloads():
    raw = json.loads((dc._DIR / "drug_contracts.json").read_text())
    assert raw["schema_version"]
    assert len(raw["drugs"]) == len(dc.DRUGS)


# ═══════════════════════════════════════════════════════════════════════════
# THE NASEMSO EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def test_tier_1_actually_landed():
    """Before the NASEMSO extraction no entry had an approved-source dose.
    This asserts the extraction is real, not that a file was touched."""
    with_t1 = [(n, e["indication"]) for n, d in dc.DRUGS.items()
               for e in d["dose_entries"]
               if isinstance(e["dose_range"], dict)
               and any(s["tier"] == 1 for s in e["sources"])]
    assert len(with_t1) >= 25, f"only {len(with_t1)} tier-1 dosed entries"


def test_every_tier_1_citation_names_a_guideline_and_page():
    """A citation that cannot be checked is not a citation.

    NASEMSO's printed page number equals its PDF page number and every page
    footer carries its guideline name, so there is no excuse for a vague cite.
    """
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            for src in e["sources"]:
                if src["tier"] != 1:
                    continue
                c = src["citation"]
                assert "NASEMSO" in c and "v3.0" in c, c
                assert re.search(r"p\.\d+", c), f"{name}: no page in {c!r}"


def test_nothing_became_signed_during_the_extraction():
    """The extraction fills values. It does not sign them. Ever."""
    assert dc.servable_entries() == {}
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            assert e["signoff"] is False, f"{name}/{e['indication']}"
            assert e["reviewed_by"] == dc.PENDING
            assert e["review_date"] == dc.PENDING


def test_the_extraction_made_entries_signABLE():
    """The fence must have moved from 'nothing can be signed' to 'these can'.

    Otherwise the extraction achieved nothing the owner can act on.
    """
    signable = 0
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            forced = copy.deepcopy(e)
            forced.update({"signoff": True, "reviewed_by": "clinician",
                           "review_date": "2026-08-24"})
            if dc.entry_is_servable(forced)[0]:
                signable += 1
    assert signable >= 25, f"only {signable} entries are signable"


def test_both_sides_of_a_source_conflict_are_kept():
    """CONFLICTING doses are never silently resolved.

    NASEMSO gives ketamine 0.25 mg/kg for analgesia capped at 25 mg; the
    migrated hardcode gives 0.3 mg/kg IV and 2.0 mg/kg IM uncapped. Both stay,
    tied by conflict_group, for the owner to adjudicate.
    """
    conflicted = [e for d in dc.DRUGS.values() for e in d["dose_entries"]
                  if "SOURCE_CONFLICT" in (e.get("flags") or [])]
    assert len(conflicted) >= 2, "a conflict needs at least two sides"
    groups = collections.Counter(e.get("conflict_group") for e in conflicted)
    assert None not in groups, "a SOURCE_CONFLICT entry has no conflict_group"
    for group, n in groups.items():
        assert n >= 2, f"conflict group {group!r} has only {n} side(s)"


def test_a_conflicted_entry_cannot_be_signed_without_adjudicating():
    """Already covered generically; asserted here on the REAL conflict."""
    # the NASEMSO side — the migrated side is refused earlier, for tier 0
    entry = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "SOURCE_CONFLICT" in (e.get("flags") or [])
                 and any(src["tier"] in (1, 2) for src in e["sources"]))
    forced = copy.deepcopy(entry)
    forced.update({"signoff": True, "reviewed_by": "clinician",
                   "review_date": "2026-08-24"})
    forced.pop("adjudication", None)
    ok, why = dc.entry_is_servable(forced)
    assert not ok and "adjudication" in why


def test_the_suspected_source_error_was_not_transcribed():
    """NASEMSO p.121 says paediatric arrest epinephrine 0.1 mg/kg — ten times
    the conventional 0.01 mg/kg. Copying a source faithfully is not the job
    when copying it authors a 10x overdose."""
    entry = next(e for e in dc.DRUGS["epinephrine"]["dose_entries"]
                 if e["indication"] == "cardiac arrest"
                 and e["population"] == "peds")
    assert entry["dose_range"] == dc.NEEDS_MANUAL
    assert "SUSPECTED_SOURCE_ERROR" in entry["flags"]
    assert "0.1 mg/kg" in entry["extraction_notes"]


def test_drugs_absent_from_both_sources_say_so():
    """A refusal must name which source was searched and came up empty."""
    for name in ("rocuronium", "succinylcholine", "propofol", "levetiracetam"):
        for e in dc.DRUGS[name]["dose_entries"]:
            if e["dose_range"] != dc.NEEDS_MANUAL:
                continue
            notes = e.get("extraction_notes", "")
            assert "NASEMSO" in notes, f"{name}: {notes!r}"


def test_no_dose_was_invented_for_a_drug_neither_source_covers():
    """The strongest form of 'never guess a dose'."""
    for name in ("rocuronium", "succinylcholine", "artesunate", "quinine",
                 "antivenom immunoglobulin"):
        for e in dc.DRUGS[name]["dose_entries"]:
            if not isinstance(e["dose_range"], dict):
                continue
            # A MIGRATED value is a number with no approved source by
            # definition — that is what makes it migrated, and the tier rule
            # already makes it unsignable. Anything else with a number and no
            # approved source would be invented.
            if "MIGRATED_UNSOURCED" in (e.get("flags") or []):
                continue
            assert any(s["tier"] in (1, 2) for s in e["sources"]), \
                f"{name}/{e['indication']} has a number with no approved source"


def test_a_meaningful_null_maximum_carries_the_sentence_that_says_so():
    """null max means 'the source states none'. An entry that just dropped the
    sentinel without saying why would be indistinguishable from a value nobody
    looked for."""
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            if not isinstance(e["dose_range"], dict):
                continue
            if e["max_cumulative"] is None:
                joined = " ".join(e.get("cautions") or [])
                assert "no cumulative maximum" in joined or \
                       "states no maximum" in joined, \
                    f"{name}/{e['indication']}: null max with no explanation"
