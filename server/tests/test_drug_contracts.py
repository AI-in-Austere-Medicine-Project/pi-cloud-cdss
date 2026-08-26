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
import pathlib
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

def pending_entry(drug="ketamine", **overrides):
    """A shipped entry wound back to the sentinel in every clinical field.

    The state every entry was in before the owner signed anything, and the
    state 49 of them are still in. The fence tests assert against THIS rather
    than against the file, so signing an entry is never what makes them fail —
    the same reason test_vent_module.py installs a pending card instead of
    asserting that no card is live.

    Entries go live one at a time. "How many are signed" is a moving fact and
    no test may depend on it.
    """
    entry = copy.deepcopy(dc.DRUGS[drug]["dose_entries"][0])
    entry.update({
        "indication": "SYNTHETIC TEST INDICATION", "population": "adult",
        "route": "IV",
        "dose_range": {"min": dc.PENDING, "max": dc.PENDING,
                       "units": dc.PENDING, "per_kg": False},
        "sources": [], "cautions": [dc.PENDING], "contraindications": [dc.PENDING],
        "signoff": False, "reviewed_by": dc.PENDING, "review_date": dc.PENDING,
        "version": "0.1.0-draft",
    })
    entry.update(overrides)
    return entry


def test_an_unsigned_entry_is_never_servable():
    """The fence, proven on an entry that is unsigned by construction.

    This replaces test_the_shipped_contract_file_is_entirely_unsigned and
    test_nothing_is_servable_today, which asserted `servable_entries() == {}`
    and were correct until the owner signed 46 entries on 2026-08-25. A test
    that fails the moment the system is used as designed is not a fence test —
    it is a clock. What the fence actually promises is this, and it stays true
    at any number of signatures.
    """
    ok, why = dc.entry_is_servable(pending_entry(), dc.DRUGS["ketamine"])
    assert ok is False
    assert why, "an entry was refused with no reason given"


@pytest.mark.parametrize("field,value", [
    ("signoff", False),
    ("reviewed_by", dc.PENDING),
    ("review_date", dc.PENDING),
    ("sources", []),
    ("cautions", [dc.PENDING]),
])
def test_each_half_authored_field_alone_is_enough_to_refuse(field, value):
    """One sentinel is enough. An entry that is complete except for its
    cautions is still half-authored, and the medic reads the cautions."""
    entry = pending_entry(**{
        "dose_range": {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True},
        "sources": [{"citation": "SYNTHETIC", "tier": 1, "url": "http://example",
                     "retrieved_date": "2026-08-25"}],
        "cautions": [], "contraindications": [],
        "signoff": True, "reviewed_by": dc.SIGNOFF_AUTHORS[0],
        "review_date": "2026-08-25",
    })
    entry[field] = value
    ok, _ = dc.entry_is_servable(entry, dc.DRUGS["ketamine"])
    assert ok is False, f"{field}={value!r} was served"


def test_every_servable_entry_passed_the_fence_it_claims_to_have_passed():
    """The other half of the same promise, over the REAL file: whatever is
    signed today is signed properly. This one scales with the bank instead of
    contradicting it."""
    for name, entries in dc.servable_entries().items():
        for e in entries:
            assert e.get("signoff") is True, f"{name}/{e['indication']}"
            assert e.get("reviewed_by") in dc.SIGNOFF_AUTHORS, \
                f"{name}/{e['indication']} signed by {e.get('reviewed_by')!r}"
            assert e.get("review_date") not in dc.SENTINELS, \
                f"{name}/{e['indication']} has no real review date"
            ok, why = dc.entry_is_servable(e, dc.DRUGS[name])
            assert ok, f"{name}/{e['indication']} is served but fails the fence: {why}"


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




def test_the_legacy_four_are_named_and_only_those_four():
    assert set(dc.LEGACY_CALCULATOR_DRUGS) == \
        {"ketamine", "rocuronium", "succinylcholine", "lorazepam"}
    for name in dc.LEGACY_CALCULATOR_DRUGS:
        assert name in dc.DRUGS, f"{name} was not migrated into the model"




def test_an_ambiguous_sourced_strength_names_no_single_concentration(monkeypatch):
    """A drug whose sources cite two strengths has no single one.

    This used to gate the serving path. It no longer does — the kit decides
    the concentration now, not the contract — but the ambiguity is still a
    fact about the sources and drug_concentrations reads it to decide whether
    a declared vial is corroborated.
    """
    d = synthetic_drug(forms=[
        {"description": "TEST a", "concentration_mg_ml": 1.0, "sources": []},
        {"description": "TEST b", "concentration_mg_ml": 50.0, "sources": []}])
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    assert dc.single_concentration("testosteril") is None
    # The dose still builds; it simply carries no volume.
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    doses = oc._contract_dose_candidates("testosteril dose", ctx)
    assert doses and all(x.volume_ml is None for x in doses)


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
                cls = src.get("source_class")
                assert cls in ("NASEMSO", "JTS"), f"{name}: tier 1 but {cls!r}"
                if cls == "NASEMSO":
                    assert "NASEMSO" in c and "v3.0" in c, c
                else:
                    assert "JTS" in c and "CPG ID" in c, c
                    assert re.search(r"\b\d{2} \w{3} \d{4}\b", c), \
                        f"a JTS citation must carry the CPG's date: {c!r}"
                assert re.search(r"p\.\d+", c), f"{name}: no page in {c!r}"


def test_nothing_became_signed_during_the_extraction():
    """The extraction fills values. It does not sign them. Ever.

    Asserted as "no signature names a script" rather than as "nothing is
    signed": the owner signs entries, and the extraction must never be able to
    produce one. An entry signed by anything other than an authorised human
    role is an entry a tool signed for itself.
    """
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            if e["signoff"] is False:
                assert e["reviewed_by"] == dc.PENDING, \
                    f"{name}/{e['indication']} is unsigned but names a reviewer"
                assert e["review_date"] == dc.PENDING
            else:
                assert e["reviewed_by"] in dc.SIGNOFF_AUTHORS, \
                    f"{name}/{e['indication']} signed by {e['reviewed_by']!r} — " \
                    "a signature must name an authorised role, never a script"


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
    """CONFLICTING doses are never silently resolved — one side dropped at
    extraction time is a silent pick nobody can audit.

    Every conflict raised so far has now been ruled on, so this asserts the
    invariant rather than an instance: whatever is flagged carries a group, and
    a group has at least two sides.
    """
    conflicted = [e for d in dc.DRUGS.values() for e in d["dose_entries"]
                  if "SOURCE_CONFLICT" in (e.get("flags") or [])]
    groups = collections.Counter(e.get("conflict_group") for e in conflicted)
    assert None not in groups, "a SOURCE_CONFLICT entry has no conflict_group"
    for group, n in groups.items():
        assert n >= 2, f"conflict group {group!r} has only {n} side(s)"


def test_a_conflicted_entry_cannot_be_signed_without_adjudicating():
    """Asserted on a synthetic entry, not a real one.

    It used to reach into the file for the live conflict. Ruling 7 settled the
    last of those, and a test that needs an unruled conflict to exist would
    reward leaving one lying around.
    """
    forced = signed_entry(flags=["SOURCE_CONFLICT"],
                          conflict_group="synthetic-group")
    forced.pop("adjudication", None)
    ok, why = dc.entry_is_servable(forced)
    assert not ok and "adjudication" in why

    forced["adjudication"] = "OWNER RULING 2026-08-25: the newer source wins."
    assert dc.entry_is_servable(forced)[0]


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
                joined = " ".join(dc.caution_texts(e))
                assert "no cumulative maximum" in joined or \
                       "states no maximum" in joined, \
                    f"{name}/{e['indication']}: null max with no explanation"


# ═══════════════════════════════════════════════════════════════════════════
# THE JTS EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def test_jts_is_a_tier_1_source_class():
    """JTS sits at tier 1 beside NASEMSO rather than at a tier of its own.

    Tier is a TRUST level, not a document identity — the fence asks "is there
    an approved clinical source", and a JTS CPG is one. What distinguishes the
    documents is source_class, which is why that field exists.
    """
    classes = {s.get("source_class") for d in dc.DRUGS.values()
               for e in d["dose_entries"] for s in e["sources"]}
    assert {"JTS", "NASEMSO", "WHO_EML", "MIGRATION"} <= classes
    jts_tiers = {s["tier"] for d in dc.DRUGS.values() for e in d["dose_entries"]
                 for s in e["sources"] if s.get("source_class") == "JTS"}
    assert jts_tiers == {1}


def test_the_rsi_bundle_is_no_longer_unsourceable():
    """Ranks 1, 3 and 4 — 56 dose queries — had tier-0-only citations and
    could not be signed at any price. JTS covers what NASEMSO does not."""
    for drug in ("rocuronium", "succinylcholine"):
        sourced = [e for e in dc.DRUGS[drug]["dose_entries"]
                   if isinstance(e["dose_range"], dict)
                   and any(s.get("source_class") == "JTS" for s in e["sources"])]
        assert sourced, f"{drug} still has no JTS-sourced dose"






def test_the_succinylcholine_contraindications_are_filled_from_jts():
    """JTS ID40 states them explicitly; they were NEEDS_MANUAL_ENTRY."""
    for e in dc.DRUGS["succinylcholine"]["dose_entries"]:
        if not isinstance(e["dose_range"], dict):
            continue
        ci = " ".join(e["contraindications"]).lower()
        assert dc.NEEDS_MANUAL not in e["contraindications"]
        for term in ("burn", "spinal cord", "hyperkal"):
            assert term in ci, f"{term} missing from {e['indication']}"


def test_the_visual_only_infusion_rate_was_not_guessed():
    """JTS ID61 marks the starting drip rate by HIGHLIGHTING a table row. A
    highlight is not in the text layer, so the rate is not in this file."""
    e = next(x for x in dc.DRUGS["ketamine"]["dose_entries"]
             if x["indication"] == "prolonged sedation infusion")
    assert e["dose_range"] == dc.NEEDS_MANUAL
    assert "NEEDS_VISUAL_CONFIRMATION" in e["flags"]
    assert "highlight" in e["extraction_notes"].lower()


def test_txa_finally_has_a_dose():
    """NASEMSO named TXA in three guidelines and dosed it in none. JTS ID40
    gives 2 g — and the entry is flagged because grams are not milligrams."""
    e = next(x for x in dc.DRUGS["tranexamic acid"]["dose_entries"]
             if "loading" in x["indication"])
    assert e["dose_range"]["min"] == 2.0 and e["dose_range"]["units"] == "g"
    assert "UNIT_NOT_MG" in e["flags"]


def test_nothing_was_signed_by_the_jts_extraction():
    """Same promise as above, scoped to the JTS pass: an extraction may fill a
    dose_range and a citation, and may never fill a signature."""
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            cites_jts = any("JTS" in str(src.get("citation", ""))
                            for src in e.get("sources", []) or [])
            if cites_jts and e["signoff"] is True:
                assert e["reviewed_by"] in dc.SIGNOFF_AUTHORS, \
                    f"{name}/{e['indication']} carries a non-role signature"






# ═══════════════════════════════════════════════════════════════════════════
# THE OWNER'S RULINGS, 2026-08-25
# ═══════════════════════════════════════════════════════════════════════════
#
# Every SOURCE_CONFLICT the extractions raised has been adjudicated. These
# tests assert the SETTLED state — what the owner decided, and that the
# reasoning survived with it. The tests that asserted the unsettled state were
# removed rather than loosened: an unresolved conflict is no longer a fact
# about this file, and a test insisting it still is would be testing history.


# Ruling 7 (2026-08-25) closed the last one. The set stays here rather than
# being deleted, so a NEW unruled conflict has something to fail against.
STILL_AWAITING_A_RULING = set()


def test_no_source_conflict_is_still_open():
    """All seven are ruled. A new SOURCE_CONFLICT must be adjudicated, not
    parked: the flag exists to stop a silent pick, and an unruled flag sitting
    in the file indefinitely is the same silent pick with extra steps."""
    groups = {e.get("conflict_group") for d in dc.DRUGS.values()
              for e in d["dose_entries"]
              if "SOURCE_CONFLICT" in (e.get("flags") or [])}
    assert groups == STILL_AWAITING_A_RULING, f"unexpected open conflicts: {groups}"


def test_a_retired_entry_keeps_its_reason():
    """Retired, not deleted. A value that was once served has to stay
    traceable — including the 1.5 mg/kg ketamine induction the system has been
    giving all along."""
    raw = json.loads((dc._DIR / "drug_contracts.json").read_text())
    retired = raw.get("retired_entries", [])
    assert len(retired) >= 7
    for r in retired:
        assert r["retired_reason"].startswith("OWNER RULING")
        assert r["retired_on"] and r["dose_range"]


def test_ruling_1_ketamine_induction_is_two_situations_not_two_opinions():
    ind = [e for e in dc.DRUGS["ketamine"]["dose_entries"]
           if "RSI induction" in e["indication"]]
    standard = [e for e in ind if e["indication"] == "RSI induction"]
    reduced = [e for e in ind if "extremis" in e["indication"]]
    assert {e["dose_range"]["min"] for e in standard} == {2.0}
    assert {e["dose_range"]["min"] for e in reduced} == {1.0}
    assert 1.5 not in {e["dose_range"]["min"] for e in ind}, \
        "the unsourced 1.5 mg/kg hardcode is still present"
    for e in ind:
        assert any(s.get("source_class") == "JTS" for s in e["sources"])


def test_ruling_1_the_reduced_dose_says_titrate_first():
    e = next(x for x in dc.DRUGS["ketamine"]["dose_entries"]
             if "extremis" in x["indication"])
    assert dc.caution_texts(e)[0].startswith("TITRATE")
    assert any("no approved source states a reduced PAEDIATRIC" in c.lower()
               or "reduced PAEDIATRIC" in c for c in dc.caution_texts(e))


def test_ruling_2_paediatric_succinylcholine_is_age_banded():
    """The safety ruling: a flat 2 mg/kg is 33% high on a 7-year-old."""
    peds = [e for e in dc.DRUGS["succinylcholine"]["dose_entries"]
            if e["population"] == "peds" and isinstance(e["dose_range"], dict)]
    bands = {e["indication"]: e["dose_range"]["min"] for e in peds}
    assert bands == {"RSI paralytic — under 5 years": 2.0,
                     "RSI paralytic — 5 years and above": 1.5}, bands


def test_ruling_2_an_age_band_is_not_used_without_an_age():
    """Neither band is a safe default, so an unknown age selects neither."""
    live = {"succinylcholine": [e for e in dc.DRUGS["succinylcholine"]["dose_entries"]
                                if e["population"] == "peds"]}
    assert dc._age_band({"indication": "RSI paralytic — under 5 years"}) == (0.0, 5.0)
    assert dc._age_band({"indication": "RSI paralytic — 5 years and above"}) == (5.0, 200.0)
    assert dc._age_band({"indication": "RSI paralytic"}) is None


def test_ruling_3_adult_succinylcholine_is_id39_with_id40_recorded():
    adult = [e for e in dc.DRUGS["succinylcholine"]["dose_entries"]
             if e["population"] == "adult" and isinstance(e["dose_range"], dict)]
    assert len(adult) == 1, "there must be exactly one adult dose"
    assert adult[0]["dose_range"]["min"] == 1.5
    assert any("ALTERNATE" in c and "1 mg/kg" in c
               for c in dc.caution_texts(adult[0])), \
        "ID40's value must survive as a recorded alternate"


def test_ruling_4_rocuronium_is_split_by_age():
    roc = {e["population"]: e["dose_range"]["min"]
           for e in dc.DRUGS["rocuronium"]["dose_entries"]
           if isinstance(e["dose_range"], dict)}
    assert roc == {"adult": 1.2, "peds": 1.0}, roc
    for e in dc.DRUGS["rocuronium"]["dose_entries"]:
        if isinstance(e["dose_range"], dict):
            assert any("CORROBORATING" in c for c in dc.caution_texts(e))


def test_ruling_5_the_mislabelled_im_dose_is_gone():
    """2 mg/kg IM was the IV sedation number on the IM route, called analgesia."""
    for e in dc.DRUGS["ketamine"]["dose_entries"]:
        if "analgesia" in e["indication"] and isinstance(e["dose_range"], dict):
            assert e["dose_range"]["min"] <= 0.25, \
                f"{e['indication']} is not sub-dissociative"


def test_ruling_5_the_two_analgesia_sources_are_no_longer_a_conflict():
    analg = [e for e in dc.DRUGS["ketamine"]["dose_entries"]
             if "analgesia" in e["indication"] and isinstance(e["dose_range"], dict)]
    assert len(analg) == 2
    for e in analg:
        assert "SOURCE_CONFLICT" not in (e.get("flags") or [])
        assert "same clinical range" in e["adjudication"]


def test_ruling_6_ketamine_is_not_contraindicated_in_head_injury():
    """The discovery bank contains "RSI doses, he has a head injury". The
    system must not steer a medic off the induction agent JTS endorses for
    exactly that patient."""
    for e in dc.DRUGS["ketamine"]["dose_entries"]:
        for ci in e.get("contraindications") or []:
            assert "head trauma" not in str(ci).lower(), \
                f"{e['indication']} still lists head trauma as active"
        assert "CONTRAINDICATION_CONFLICT" not in (e.get("flags") or [])


def test_ruling_6_nasemsos_position_survives_as_history():
    """Overturned, not erased — the reasoning has to be auditable."""
    noted = [e for e in dc.DRUGS["ketamine"]["dose_entries"]
             if any("HISTORICAL CAUTION" in c for c in dc.caution_texts(e))]
    assert noted
    for e in noted:
        joined = " ".join(dc.caution_texts(e))
        assert "NASEMSO" in joined and "JTS ID61" in joined


def test_every_ruling_is_recorded_on_the_entry_it_settles():
    for n, d in dc.DRUGS.items():
        for e in d["dose_entries"]:
            if e.get("adjudicated_on"):
                assert e["adjudication"].startswith("OWNER RULING"), \
                    f"{n}/{e['indication']}"


def test_ruling_7_post_intubation_sedation_is_an_equipment_split():
    """The last conflict. The hardcode gives 0.5 mg/kg repeated q20-30min; JTS
    ID61 gives 1 mg/kg over 60 seconds then an infusion. The owner ruled that
    those are two equipment situations rather than two opinions, so both
    entries survive and each says which situation it is for."""
    ket = dc.DRUGS["ketamine"]["dose_entries"]
    bolus = next(e for e in ket if "repeated bolus" in e["indication"])
    pump = next(e for e in ket if "infusion pump available" in e["indication"])
    assert bolus["dose_range"]["min"] == 0.5
    assert pump["dose_range"]["min"] == 1.0
    for e in (bolus, pump):
        assert "SOURCE_CONFLICT" not in (e.get("flags") or [])
        assert "conflict_group" not in e
        assert e["adjudication"].startswith("OWNER RULING 2026-08-25")
        assert "pump" in e["adjudication"]


def test_ruling_7_each_entry_names_the_other():
    """"So the guidance exists when the equipment does" only holds if the medic
    on the entry they matched can find the one they did not."""
    ket = dc.DRUGS["ketamine"]["dose_entries"]
    bolus = next(e for e in ket if "repeated bolus" in e["indication"])
    pump = next(e for e in ket if "infusion pump available" in e["indication"])
    assert any("ongoing sedation" in c and "ID61" in c
               for c in dc.caution_texts(bolus))
    assert any("repeated bolus" in c and "0.5 mg/kg" in c
               for c in dc.caution_texts(pump))


def test_ruling_8_did_not_launder_the_hardcode_into_a_SOURCED_dose():
    """THE POINT OF THE RULING THAT IS EASIEST TO LOSE.

    Ruling 8 made the bolus dose signable. It did NOT make it sourced, and the
    difference is the whole mechanism: the entry serves on a declaration that
    names an owner and a date, not on a citation. If this ever passes while the
    entry also claims a tier 1/2 citation FOR THE VALUE, the declaration has
    quietly turned into evidence.
    """
    bolus = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "repeated bolus" in e["indication"])
    assert dc.OWNER_DECLARED in bolus["flags"]
    assert dc.MIGRATED_UNSOURCED not in bolus["flags"]
    assert dc.is_owner_declared(bolus)

    # The shape doctrine lives in the declaration, NOT in sources[]. Nothing in
    # sources[] may claim to state the number.
    citations = " ".join(s.get("citation", "") for s in bolus["sources"])
    assert "Appendix A" not in citations, \
        "shape doctrine leaked into sources[] where it reads as a dose citation"
    assert any(d["supports"].startswith("SHAPE ONLY")
               for d in bolus["owner_declaration"]["supporting_doctrine"])

    # And the medic is told so, at the top of the cautions they read.
    #
    # This used to assert a hand-written banner IN cautions[], beside the one
    # serve_cautions() generates from the declaration — the same claim written
    # twice, which is how the two come to disagree. Ruling 11 deleted the
    # hand-written copy, so the assertion moved to the mechanism: the label is
    # DERIVED from owner_declaration and cannot be edited apart from it.
    assert dc.serve_cautions(bolus)[0] == dc.provenance_label_short(bolus)
    assert "OWNER-DECLARED dose" in dc.serve_cautions(bolus)[0]
    assert not any("OWNER DECLARATION" in c for c in dc.caution_texts(bolus)), \
        "the hand-copied banner is back — it will drift from the declaration"


def test_ruling_8_left_the_bolus_entry_signable():
    """The ruling is inert unless the fence actually accepts it."""
    bolus = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "repeated bolus" in e["indication"])
    ok, why = dc.entry_is_servable(
        dict(bolus, signoff=True, reviewed_by=dc.SIGNOFF_AUTHORS[0],
             review_date="2026-08-25", version="0.3.0"))
    assert ok, why


def test_ruling_7_left_the_only_cited_shape_signable():
    """The bolus cannot be served. If the ID61 entry had been retired into a
    caution on it — the ruling-3 shape — the cited guidance would have gone
    with it and post-intubation sedation would serve nothing at all."""
    pump = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                if "infusion pump available" in e["indication"])
    assert any(s.get("source_class") == "JTS" for s in pump["sources"])
    assert dc.entry_is_servable(
        dict(pump, signoff=True, reviewed_by=dc.SIGNOFF_AUTHORS[0],
             review_date="2026-08-25"))[0]


# ─────────────────────────────────────────────────────────────────────────────
# OWNER DECLARATION — the anti-smuggling suite
#
# OWNER_DECLARED is the one place where a number with no citation may be
# served. That makes it the one place worth attacking, so every test below is
# written as an attack: each one is a way somebody could get an unsourced value
# onto a screen without meaning to declare it, and each one must be refused.
# ─────────────────────────────────────────────────────────────────────────────

def _declared_fixture(**over):
    """A minimal, well-formed owner-declared entry. Synthetic drug, synthetic
    number, for the same reason the rest of this file's fixtures are."""
    dr = {"min": 1.0, "max": 1.0, "units": "mg/kg", "per_kg": True}
    e = {
        "indication": "synthetic indication",
        "population": "adult",
        "route": "IV",
        "dose_range": dict(dr),
        "max_single": None,
        "max_cumulative": None,
        "contraindications": ["Hypersensitivity"],
        "cautions": ["The cited guideline states no maximum single dose for "
                     "this drug and indication.",
                     "The cited guideline states no cumulative maximum for "
                     "this drug and indication."],
        "sources": [{"citation": "TESTOSTERIL migration carrier",
                     "tier": 0, "url": "internal:test",
                     "retrieved_date": "2026-08-25"}],
        "signoff": True,
        "reviewed_by": dc.SIGNOFF_AUTHORS[0],
        "review_date": "2026-08-25",
        "version": "0.0.1",
        "flags": [dc.OWNER_DECLARED],
        "owner_declaration": {
            "basis": "owner clinical declaration",
            "declared_by": "Test Owner - AI-AIM",
            "declared_on": "2026-08-25",
            "justification": ("A synthetic justification long enough to be a "
                              "real one: doctrine supports the shape of this "
                              "intervention and no guideline states a number "
                              "for it, so the value is declared."),
            "declared_value": dict(dr),
            "supporting_doctrine": [
                {"citation": "SYNTHETIC CPG — shape only", "tier": 1,
                 "supports": "SHAPE ONLY — states the approach, not the dose"},
            ],
        },
    }
    e.update(over)
    return e


def test_the_declaration_fixture_is_actually_servable():
    """Every refusal below is only meaningful if the baseline passes."""
    ok, why = dc.entry_is_servable(_declared_fixture())
    assert ok, why
    assert dc.is_owner_declared(_declared_fixture())


def test_the_flag_alone_declares_nothing():
    """The flag is a claim that a declaration exists. It is not the
    declaration."""
    e = _declared_fixture()
    del e["owner_declaration"]
    ok, why = dc.entry_is_servable(e)
    assert not ok and "no owner_declaration object" in why
    assert not dc.is_owner_declared(e)


def test_a_declaration_without_the_flag_is_refused():
    """THE QUIET PATH, CLOSED.

    Someone drops an owner_declaration into an entry, does not flag it, and
    the entry serves on whatever it had before while carrying a document that
    reads like authority. Refused: a declaration that is not declared is the
    smuggle this whole mechanism is built against.
    """
    e = _declared_fixture(flags=[])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "not flagged" in why
    assert not dc.is_owner_declared(e)


def test_a_declaration_must_carry_a_justification():
    e = _declared_fixture()
    e["owner_declaration"] = dict(e["owner_declaration"], justification="ok")
    ok, why = dc.entry_is_servable(e)
    assert not ok and "justification" in why


def test_a_declaration_must_say_what_doctrine_supports_the_shape():
    """A bare assertion is not a declaration. If nothing at all supports even
    the SHAPE of the intervention, the answer is not to declare a dose."""
    e = _declared_fixture()
    e["owner_declaration"] = dict(e["owner_declaration"],
                                  supporting_doctrine=[])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "supporting_doctrine" in why


def test_editing_the_dose_after_declaring_it_takes_the_entry_OFF_THE_WIRE():
    """THE ONE THAT MATTERS MOST.

    The declaration names the number it authorises. Change dose_range and
    leave the declaration alone — a plausible edit, and the one that would
    otherwise let a NEW unsourced value inherit an OLD signature — and the
    entry stops serving until somebody re-declares it deliberately.
    """
    e = _declared_fixture()
    e["dose_range"] = dict(e["dose_range"], min=2.0, max=2.0)
    ok, why = dc.entry_is_servable(e)
    assert not ok
    assert "declared_value" in why and "does not name the dose" in why
    assert not dc.is_owner_declared(e)

    # And re-declaring it deliberately is what puts it back.
    e["owner_declaration"] = dict(e["owner_declaration"],
                                  declared_value=dict(e["dose_range"]))
    assert dc.entry_is_servable(e)[0]


def test_a_declaration_may_not_ride_on_top_of_the_migration_flag():
    """Declaring a value is a change of BASIS, and a change of basis has to be
    a visible edit. Leaving MIGRATED_UNSOURCED in place while adding
    OWNER_DECLARED would make the entry serve while still claiming, in its own
    flags, that its dose is an uncorroborated hardcode."""
    e = _declared_fixture(flags=[dc.OWNER_DECLARED, dc.MIGRATED_UNSOURCED])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "cannot be both" in why


def test_a_declaration_does_not_source_the_entry_NEXT_DOOR():
    """PER-ENTRY, AND THERE IS NO GLOBAL 'THE OWNER HAS DECLARED' STATE.

    An undeclared entry with nothing but tier 0 sources is refused whether or
    not it sits beside a declared one, and whether or not it is in the same
    drug. If this ever passes, OWNER_DECLARED has become a property of the
    file rather than of an entry.
    """
    declared = _declared_fixture()
    assert dc.entry_is_servable(declared)[0]

    neighbour = _declared_fixture(flags=[], indication="undeclared neighbour")
    del neighbour["owner_declaration"]
    ok, why = dc.entry_is_servable(neighbour)
    assert not ok
    assert "tier 1 or tier 2" in why


def test_a_declaration_does_not_excuse_any_OTHER_refusal():
    """It substitutes for the citation and for nothing else. A sentinel, a bad
    signer, an unresolved conflict — all still refuse."""
    assert not dc.entry_is_servable(
        _declared_fixture(cautions=[dc.NEEDS_MANUAL]))[0]
    assert not dc.entry_is_servable(
        _declared_fixture(reviewed_by="andrew"))[0]
    assert not dc.entry_is_servable(
        _declared_fixture(flags=[dc.OWNER_DECLARED, "SOURCE_CONFLICT"]))[0]


def test_a_declared_dose_is_visibly_declared_wherever_it_is_served():
    """The label rides in the CAUTIONS, first, because that is the text that
    reaches a medic at the moment of giving the drug. A provenance that only
    exists in the JSON is a provenance nobody reads."""
    e = _declared_fixture(cautions=["TEST serve-tier caution"])
    served = dc.serve_cautions(e)
    assert served[0].startswith("OWNER-DECLARED dose")
    assert served[1:] == ["TEST serve-tier caution"], \
        "serve_cautions dropped or reordered the entry's own cautions"


def test_ruling_11_the_serve_label_carries_the_fact_and_not_the_signature():
    """OWNER RULING 11, 2026-08-26. Two forms of one claim.

    What changes what a medic does is that the number is a declaration. WHO
    declared it and WHEN changes nothing at the bedside and cost four lines of
    a screen read mid-airway — so the short form serves and the full banner is
    kept by the record. Both are generated from the declaration, so neither can
    drift from it.
    """
    e = _declared_fixture()
    short = dc.provenance_label_short(e)
    full = dc.provenance_label(e)

    assert "OWNER-DECLARED dose" in short and "not a guideline value" in short
    assert "Test Owner - AI-AIM" not in short, \
        "the signature is back on the serve tier"
    assert "2026" not in short, "the declaration date is back on the serve tier"
    assert len(short) < 80, "the serve label has grown back into a paragraph"

    # The record keeps what the screen drops.
    assert "Test Owner - AI-AIM" in full and e["owner_declaration"]["declared_on"] in full

    # And the serve path takes the short one.
    assert dc.serve_cautions(e)[0] == short


def test_ruling_11_neither_form_labels_a_cited_dose():
    e = _declared_fixture(flags=[])
    del e["owner_declaration"]
    assert dc.provenance_label(e) == ""
    assert dc.provenance_label_short(e) == ""


def test_an_ordinary_entry_is_not_labelled_declared():
    """The label has to mean something, which means it has to be absent from
    every cited dose."""
    e = _declared_fixture(flags=[])
    del e["owner_declaration"]
    e["sources"] = [{"citation": "SYNTHETIC CPG", "tier": 1,
                     "url": "internal:test", "retrieved_date": "2026-08-25"}]
    assert dc.entry_is_servable(e)[0]
    assert not dc.is_owner_declared(e)
    assert dc.provenance_label(e) == ""
    assert dc.serve_cautions(e) == dc.caution_texts(e)


def test_every_declared_entry_in_the_shipped_file_is_well_formed():
    """A malformed declaration fails closed — the entry just stops serving —
    which is safe and silent. This is the loud half."""
    for name, drug in dc.DRUGS.items():
        for e in drug["dose_entries"]:
            if dc.OWNER_DECLARED not in (e.get("flags") or []):
                continue
            ok, why = dc._declaration_ok(e)
            assert ok, f"{name} / {e['indication']}: {why}"


def test_the_declared_list_is_short_and_named():
    """Not a correctness property — a review property. Every entry on this
    list is a number the project is answerable for itself, so the set is
    pinned: adding one has to be a deliberate edit to this test.
    """
    declared = {(n, e["indication"]) for n, d in dc.DRUGS.items()
                for e in d["dose_entries"]
                if dc.OWNER_DECLARED in (e.get("flags") or [])}
    assert declared == {
        ("ketamine",
         "post-intubation sedation — repeated bolus (no infusion pump)"),
    }


def test_the_serve_path_labels_a_declared_dose_in_BOTH_channels(monkeypatch):
    """END TO END, THROUGH THE REAL SERVE PATH.

    The unit tests above check serve_cautions() in isolation, which proves the
    helper works and proves nothing about whether anything calls it. This goes
    through _contract_dose_candidates(), because the failure that matters is a
    serve path that reads entry["cautions"] directly and hands a medic an
    owner-declared number dressed as a cited one.
    """
    e = _declared_fixture(indication="TEST declared indication",
                          population="adult|peds")
    d = synthetic_drug(dose_entries=[e])
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})

    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    doses = oc._contract_dose_candidates("testosteril dose", ctx)
    assert doses, "the declared entry did not serve at all"
    c = doses[0]
    # Channel 1: prose a medic reads, first, before the clinical cautions —
    # the SHORT form, per ruling 11. The signature is in the record, and
    # build_why_this_dose_response() is how a medic gets to it.
    assert c.warning.startswith("OWNER-DECLARED dose")
    assert "Test Owner - AI-AIM" not in c.warning
    # Channel 2: a machine-matchable marker for the log and the transcript.
    assert c.source.endswith(":owner_declared")


def test_the_serve_path_does_not_label_a_CITED_dose(monkeypatch):
    """The other half: the marker must be absent from an ordinary dose, or it
    stops distinguishing anything."""
    d = synthetic_drug()
    monkeypatch.setattr(dc, "DRUGS", {d["generic_name"]: d})
    ctx = PatientContext(confirmed_weight_kg=80.0, weight_source="stated")
    c = oc._contract_dose_candidates("testosteril dose", ctx)[0]
    assert "owner_declared" not in c.source
    assert "OWNER-DECLARED" not in (c.warning or "")


# ─────────────────────────────────────────────────────────────────────────────
# THE RSI PRE-GATE SERVES CONTRACTS
#
# The bug these exist for: build_rsi_response() was a second, older
# implementation of the RSI bundle that called the retired calculators
# directly, and the pre-gate returned it before build_allowed_doses() — where
# the supersede rule lives — was ever reached. Signing the contracts changed
# nothing on that path. Every assertion here is about the two paths not being
# allowed to drift apart again.
# ─────────────────────────────────────────────────────────────────────────────

import openai_client as _oc
from openai_client import PatientContext as _PC


def _rsi_ctx(weight=80.0):
    return _PC(confirmed_weight_kg=weight, weight_source="stated",
               route_preference="IV")


def test_rsi_pregate_serves_contract_doses_not_the_retired_calculators():
    """The exact failure reported: 46 contracts signed, service restarted, and
    the RSI query still answered 120 mg / 80 mg from the 1.5 and 1.0 mg/kg
    hardcodes with a 'deterministic RSI calculator' source line."""
    text = _oc.build_rsi_response(_rsi_ctx(),
                                  "need to RSI with ketamine and roc, 80kg IV")
    assert text is not None
    give = text.split("**GIVE**")[1].split("**POST-INTUBATION")[0]

    assert "160 mg" in give, f"ketamine is not the signed 2 mg/kg dose: {give}"
    assert "96 mg" in give, f"rocuronium is not the signed 1.2 mg/kg dose: {give}"
    assert "120 mg" not in give, "the retired 1.5 mg/kg ketamine hardcode is back"
    assert "80 mg" not in give, "the retired 1.0 mg/kg rocuronium hardcode is back"

    assert "deterministic RSI calculator" not in text, \
        "the hardcoded calculator SOURCE line survived the migration"
    assert "deterministic_calculator:" not in text
    assert "Signed dose contracts" in text.split("**SOURCE**")[1]


def test_rsi_pregate_gives_exactly_one_dose_per_role():
    """signed_entries_by_indication() matches on substring, so 'RSI induction'
    also returns the in-extremis entry and 'ongoing sedation' returns
    midazolam's. Serving them all is two induction doses in one intubation —
    the same class of failure as the two-paralytics bug this replaced."""
    for query in ("need to RSI with ketamine and roc, 80kg IV", "rsi now",
                  "RSI now, BP 78/40, shocky", "rsi now sux",
                  "rapid sequence intubation, we have an infusion pump"):
        text = _oc.build_rsi_response(_rsi_ctx(), query)
        give = text.split("**GIVE**")[1].split("**POST-INTUBATION")[0]
        # Split on the NEXT heading, whatever it is: CONFIRM VIAL sits between
        # this block and CAUTIONS whenever a vial is still unconfirmed.
        post = text.split("**POST-INTUBATION SEDATION**")[1].split("\n**")[0]

        give_doses = [l for l in give.splitlines() if l.startswith("- ")]
        post_doses = [l for l in post.splitlines() if l.startswith("- ")]
        assert len(give_doses) == 2, f"{query!r}: expected induction+paralytic, got {give_doses}"
        assert len(post_doses) == 1, f"{query!r}: expected one sedative, got {post_doses}"

        # One paralytic, never both.
        assert sum(p in give for p in ("rocuronium", "succinylcholine")) == 1, give
        # Owner ruling 2026-08-25: the sedation slot is ketamine.
        assert "ketamine" in post_doses[0], post_doses
        assert "midazolam" not in post, f"{query!r}: midazolam in the sedation slot"


def test_rsi_pregate_and_build_allowed_doses_agree():
    """The structural guard. Two code paths that both answer 'what dose' will
    drift; this asserts they cannot, by making the pre-gate's numbers a
    function of the same contract lookup build_allowed_doses uses."""
    for query in ("need to RSI with ketamine and roc, 80kg IV",
                  "RSI now, BP 78/40, shocky", "rsi now sux"):
        ctx = _rsi_ctx()
        text = _oc.build_rsi_response(ctx, query)
        give = text.split("**GIVE**")[1].split("**WATCH**")[0]

        for d in _oc._contract_rsi_candidates(query, ctx):
            role = _oc._rsi_role(d.indication)
            assert f"{d.dose_mg:g} mg" in give, \
                f"{query!r}: contract {role} {d.drug} {d.dose_mg:g} mg missing from the bundle"
            assert d.drug in give, f"{query!r}: {d.drug} missing from the bundle"


def test_rsi_pregate_keeps_the_owner_declared_banner():
    """The sedation entry serves on a declaration, not a citation. A bundle
    that dropped its banner would present the owner's number as the
    guideline's — exactly what ruling 8 forbids."""
    text = _oc.build_rsi_response(_rsi_ctx(), "rsi now")
    assert "OWNER-DECLARED dose — not a guideline value." in text
    # Ruling 11: the full banner is NOT on this screen, and the way to it is.
    assert "clinical judgement of" not in text
    assert 'why this dose?' in text


def test_no_signature_is_silently_unhonoured():
    """A signed entry whose signer the allowlist will not honour serves
    nothing, and used to do so silently — the tool said SIGNED and the dose
    simply was not there. If this list is non-empty, --list says so."""
    assert dc.unhonoured_signatures() == [], (
        "signed entries whose signer is not in SIGNOFF_AUTHORS: "
        f"{dc.unhonoured_signatures()}")


def test_signoff_authors_is_not_shell_widenable(monkeypatch):
    """The fence that broke the concentration list: SIGNOFF_AUTHORS read
    CDSS_CARD_AUTHORS, a signing shell widened it, and the service — which had
    no such export — refused what was written."""
    import importlib
    monkeypatch.setenv("CDSS_CARD_AUTHORS", "clinician,AI-AIM,anyone at all")
    importlib.reload(dc)
    assert "anyone at all" not in dc.SIGNOFF_AUTHORS
    assert dc.SIGNOFF_AUTHORS == ("clinician", "AI-AIM")
    monkeypatch.delenv("CDSS_CARD_AUTHORS")
    importlib.reload(dc)


# ─────────────────────────────────────────────────────────────────────────────
# THE VIAL ASK REACHES THE RSI BUNDLE
#
# pre_gate() has asked "which vial?" since the concentration list shipped, but
# it runs at step 2l and the RSI dispatch returns at step 2k — so the one
# bundle most likely to need the question could never be asked it. The medic
# got "NO VOLUME — confirm concentration to compute volume" with nothing
# naming what to confirm.
# ─────────────────────────────────────────────────────────────────────────────

import drug_concentrations as _dcn


def _needs_vial_confirmation(drug):
    return _dcn.resolve(drug, {})[0] == _dcn.NEEDS_CONFIRMATION


def test_the_rsi_bundle_names_the_vial_options_it_needs():
    """Not the generic refusal line — the actual presentations, so the medic
    can answer without knowing the question was about ketamine."""
    if not _needs_vial_confirmation("ketamine"):
        pytest.skip("ketamine no longer needs confirmation in the shipped list")
    ctx = _oc.extract_patient_context("need to RSI with ketamine and roc, 80kg IV")
    text = _oc.build_rsi_response(ctx, "need to RSI with ketamine and roc, 80kg IV")

    assert "**CONFIRM VIAL**" in text
    ask = text.split("**CONFIRM VIAL**")[1].split("**CAUTIONS**")[0]
    assert "ketamine" in ask
    # The options themselves, phrased in what is printed on the vial.
    for p in _dcn.signed_presentations("ketamine"):
        assert p["label_text"] in ask, f"{p['label_text']} not offered: {ask}"
    # The doses are still served — the ask does not withhold the bundle.
    give = text.split("**GIVE**")[1].split("**POST-INTUBATION")[0]
    assert "160 mg" in give


def test_confirming_the_vial_computes_the_volume_and_drops_the_ask():
    if not _needs_vial_confirmation("ketamine"):
        pytest.skip("ketamine no longer needs confirmation in the shipped list")
    conc = _dcn.signed_presentations("ketamine")[0]["concentration_mg_ml"]
    q = "need to RSI with ketamine and roc, 80kg IV"
    ctx = _oc.extract_patient_context(q)
    ctx.confirmed_concentrations["ketamine"] = conc

    text = _oc.build_rsi_response(ctx, q)
    give = text.split("**GIVE**")[1].split("**POST-INTUBATION")[0]
    assert "**CONFIRM VIAL**" not in text, "still asking after the answer"
    assert f"{160.0 / conc:g} mL of {conc:g}mg/mL ketamine" in give, give


def test_a_vial_answer_caches_on_the_patient_and_survives_later_turns():
    """Asked once, not again mid-airway. The cache is per-PATIENT: a patient
    boundary clears it with everything else, which is the point."""
    c1 = _oc.extract_patient_context("need to RSI with ketamine and roc, 80kg IV")
    assert "ketamine" in c1.drugs_named
    c2 = _oc.extract_patient_context("500 in 10", prior_ctx=c1)
    assert c2.confirmed_concentrations.get("ketamine") == 50.0
    c3 = _oc.extract_patient_context("what about the sedation dose", prior_ctx=c2)
    assert c3.confirmed_concentrations.get("ketamine") == 50.0, \
        "the confirmation was lost on a later turn"


def test_the_bundle_resumes_on_a_vial_answer_and_not_on_anything_else():
    """The answer turn carries no RSI words. Without the resume the medic
    answers the question and the volumes arrive nowhere."""
    rsi = "need to RSI with ketamine and roc, 80kg IV"
    ctx = _oc.extract_patient_context(rsi)

    assert _oc.rsi_bundle_should_resume("500 in 10", rsi, ctx) is True
    # A fresh RSI request is the normal path's job, not the resume's.
    assert _oc.rsi_bundle_should_resume(rsi, rsi, ctx) is False
    # An ordinary follow-up must not be hijacked into re-serving the bundle.
    for other in ("what about the sedation dose", "how long does roc last",
                  "he is bradycardic now"):
        assert _oc.rsi_bundle_should_resume(other, rsi, ctx) is False, other
    # No RSI in flight at all.
    assert _oc.rsi_bundle_should_resume("500 in 10", "tylenol dose", ctx) is False


# ═══════════════════════════════════════════════════════════════════════════
# THE STRUCTURAL GUARD — NO DOSE WITHOUT A PROVENANCE
#
# The individual routings in this file are today's instances. This section is
# the actual fix.
#
# Three implementations of "what dose" had been found by 2026-08-25:
# build_rsi_response, build_ketamine_analgesia_response, and
# build_fixed_prep_response — each computing a number without consulting the
# bank, each returning from a pre-gate before build_allowed_doses (where the
# supersede rule lives) was ever reached, and each asserting a SOURCE line that
# was true when it was written and false the moment a contract was signed
# underneath it. A fourth was sitting in the file unreferenced.
#
# Fixing them one at a time does not stop the fifth. What stops the fifth is
# this: every number a deterministic path puts in front of a medic must be
# traceable to a signed contract entry, or to a calculator this registry
# explicitly declares as a backfill, or to the preparation-recipe registry. A
# number that is none of those fails the suite, and a new card that is in
# neither list fails the suite for not being classified at all.
# ═══════════════════════════════════════════════════════════════════════════

# A number followed by a MASS or RATE unit. Deliberately NOT mL and NOT
# anything ending /mL: a millilitre is a claim about a vial, guarded by
# resolve_dose_volume and audit_volume_lines, and a concentration is the
# product of a recipe rather than a quantity given to a patient. This regex is
# about the quantity that goes INTO the patient, which is the thing contracts
# own.
_DOSE_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mcg/kg/min|mg/kg/min|mcg/kg|mg/kg|mcg/min|mg/min|"
    r"mcg|mg|g|units)(?![\w/])",
    re.IGNORECASE)


# A PRESENTATION — "500 mg / 10 mL vial", "0.1mg/mL", "1:10,000" — is a
# statement about what is in the ampoule, which is drug_concentrations' job and
# not a quantity given to anybody. Removed before tokenising rather than
# excluded afterwards, so the milligrams in "500 mg / 10 mL" cannot be read as
# a 500 mg dose.
_PRESENTATION = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mcg|g)\s*/\s*\d+(?:\.\d+)?\s*m[lL]"
    r"|\d+(?:\.\d+)?\s*(?:mg|mcg)\s*/\s*m[lL]"
    r"|1:\d[\d,]*")


def _tokens(text: str) -> list:
    """(value, units, line) for every dose-shaped number in a response."""
    out = []
    for line in text.splitlines():
        scannable = _PRESENTATION.sub(" ", line)
        for m in _DOSE_TOKEN.finditer(scannable):
            out.append((float(m.group(1)), m.group(2).lower(), line.strip()))
    return out


def _is_contract_text(line: str, cautions: list) -> bool:
    """Whether this line is text a CONTRACT wrote.

    Cautions carry their own numbers — "10-20 mcg equals 1-2 mL of that
    dilution", the cumulative maxima quoted from the guideline, the second-line
    agent a JTS note names — and quoting them faithfully is the opposite of the
    failure this guards. Matched after stripping the renderers' furniture,
    because the ALLOWED_DOSES block prints the cautions joined behind a "Note:"
    and the cards print them one to a bullet.
    """
    stripped = line.strip().lstrip("-").strip()
    if stripped.lower().startswith("note:"):
        stripped = stripped[5:].strip()
    if not stripped:
        return False
    return any(stripped in c or c in stripped for c in cautions)


def _values_of(served) -> set:
    """Every number a served object legitimately authorises.

    A DoseCandidate authorises the milligrams it resolved to and the figure it
    displays in the source's own unit. A ServedEntry authorises the endpoints
    of the range it prints, plus whatever its per-patient note worked out to —
    all of which came out of drug_contracts, which is the point.
    """
    vals = set()
    for s in served:
        for attr in ("dose_mg", "display_value"):
            v = getattr(s, attr, None)
            if isinstance(v, (int, float)):
                vals.add(round(float(v), 4))
        for field_text in (getattr(s, "range_text", None),
                           getattr(s, "resolved_note", None)):
            if field_text:
                vals |= {round(float(v), 4) for v, _, _ in _tokens(field_text)}
    return vals


def _caution_lines(served) -> list:
    out = []
    for s in served:
        out += [c.strip() for c in (getattr(s, "cautions", None) or []) if c]
        if getattr(s, "warning", None):
            out.append(str(s.warning).strip())
    return out


def _rsi_case_ctx():
    return _PC(confirmed_weight_kg=80.0, weight_source="stated", route_preference="IV")


def _analgesia_ctx(route="IV", weight=60.0, ped=False):
    return _PC(confirmed_weight_kg=weight, weight_source="stated",
               route_preference=route, is_pediatric=ped,
               age_years=6.0 if ped else None)


def _render_allowed_doses(query, ctx):
    """The ALLOWED_DOSES block is a served surface too — it is the only dose
    text the generator is allowed to copy, so a wrong number there is a wrong
    number on screen one step later."""
    return _oc.build_allowed_dose_block(_oc.build_allowed_doses(query, ctx))


# Each case: how to render the card, what the contract engine authorises for
# it, and which legacy calculators it is ALLOWED to fall back to. That last
# list is the "explicitly-flagged backfill" — adding to it is a deliberate,
# reviewable act, and every entry in it is a drug/route the bank does not yet
# cover.
DOSE_TEMPLATE_CASES = [
    {
        "name": "rsi_bundle",
        "render": lambda: _oc.build_rsi_response(
            _rsi_case_ctx(), "need to RSI with ketamine and roc, 80kg IV"),
        "contract": lambda: _oc._contract_rsi_candidates(
            "need to RSI with ketamine and roc, 80kg IV", _rsi_case_ctx()),
        "backfill": [lambda w: _oc.ketamine_induction_iv(w, False),
                     lambda w: _oc.ketamine_post_intubation_iv(w),
                     lambda w: _oc.rocuronium_rsi(w, False),
                     lambda w: _oc.succinylcholine_rsi(w, False)],
        "weight": 80.0,
    },
    {
        "name": "rsi_bundle_shock",
        "render": lambda: _oc.build_rsi_response(
            _rsi_case_ctx(), "RSI now, BP 78/40, shocky"),
        "contract": lambda: _oc._contract_rsi_candidates(
            "RSI now, BP 78/40, shocky", _rsi_case_ctx()),
        "backfill": [lambda w: _oc.ketamine_induction_iv(w, False),
                     lambda w: _oc.ketamine_post_intubation_iv(w),
                     lambda w: _oc.rocuronium_rsi(w, False)],
        "weight": 80.0,
    },
    {
        "name": "ketamine_analgesia_iv",
        "render": lambda: _oc.build_ketamine_analgesia_response(_analgesia_ctx("IV")),
        "contract": lambda: [c for c in
                             [_oc._contract_analgesia_candidate(_analgesia_ctx("IV"))]
                             if c],
        "backfill": [lambda w: _oc.ketamine_analgesia_iv(w)],
        "weight": 60.0,
    },
    {
        # The bank has no IM analgesia entry. This case exists to pin that the
        # backfill is ALLOWED here and that the card says so — and that the
        # signed IM dissociative-sedation entry never leaks in to fill it.
        "name": "ketamine_analgesia_im_backfill",
        "render": lambda: _oc.build_ketamine_analgesia_response(_analgesia_ctx("IM")),
        "contract": lambda: [c for c in
                             [_oc._contract_analgesia_candidate(_analgesia_ctx("IM"))]
                             if c],
        "backfill": [lambda w: _oc.ketamine_analgesia_im(w)],
        "weight": 60.0,
    },
    {
        "name": "push_dose_epi_unstated_indication",
        "render": lambda: _oc.build_fixed_prep_response("how do I mix push dose epi"),
        "contract": lambda: _oc._epi_entries(
            _oc.EPI_PUSH_DOSE_INDICATIONS, "how do I mix push dose epi", None)[0],
        "backfill": [],
        "weight": None,
    },
    {
        "name": "push_dose_epi_bradycardia",
        "render": lambda: _oc.build_fixed_prep_response("push dose epi for bradycardia HR 38"),
        "contract": lambda: _oc._epi_entries(
            _oc.EPI_PUSH_DOSE_INDICATIONS, "push dose epi for bradycardia HR 38", None)[0],
        "backfill": [],
        "weight": None,
    },
    {
        "name": "push_dose_epi_peds_shock",
        "render": lambda: _oc.build_fixed_prep_response(
            "push dose epi for the kid, shocky", _analgesia_ctx("IV", 20.0, True)),
        "contract": lambda: _oc._epi_entries(
            _oc.EPI_PUSH_DOSE_INDICATIONS, "push dose epi for the kid, shocky",
            _analgesia_ctx("IV", 20.0, True))[0],
        "backfill": [],
        "weight": 20.0,
    },
    {
        "name": "epi_infusion_shock",
        "render": lambda: _oc.build_fixed_prep_response("how do i make an epi drip for shock"),
        "contract": lambda: _oc._epi_entries(
            _oc.EPI_INFUSION_INDICATIONS, "how do i make an epi drip for shock", None)[0],
        "backfill": [],
        "weight": None,
    },
    {
        "name": "allowed_doses_seizure",
        "render": lambda: _render_allowed_doses("she is seizing, 60kg",
                                                _analgesia_ctx("IV")),
        "contract": lambda: _oc.build_allowed_doses("she is seizing, 60kg",
                                                    _analgesia_ctx("IV")),
        "backfill": [lambda w: _oc.lorazepam_seizure(w)],
        "weight": 60.0,
    },
    {
        "name": "allowed_doses_rsi",
        "render": lambda: _render_allowed_doses("60kg RSI now", _analgesia_ctx("IV")),
        "contract": lambda: _oc.build_allowed_doses("60kg RSI now", _analgesia_ctx("IV")),
        "backfill": [lambda w: _oc.ketamine_induction_iv(w, False),
                     lambda w: _oc.ketamine_post_intubation_iv(w),
                     lambda w: _oc.rocuronium_rsi(w, False)],
        "weight": 60.0,
    },
]


@pytest.mark.parametrize("case", DOSE_TEMPLATE_CASES, ids=lambda c: c["name"])
def test_every_served_dose_traces_to_a_contract_or_a_declared_backfill(case):
    """No number reaches a medic that nobody signed and nobody declared.

    This is the test that makes a fourth implementation impossible to land
    quietly: write a new card that multiplies a weight by a number of its own,
    register it here, and it fails on the first number it invents. Do not
    register it, and the coverage test below fails instead.
    """
    text = case["render"]()
    assert text, f"{case['name']}: rendered nothing"

    served = case["contract"]()
    authorised = _values_of(served)
    cautions = _caution_lines(served)

    # Declared backfills are authorised too — and named, so the reader of a
    # failure can see exactly which unsourced calculator is still in play.
    backfilled = set()
    if case["weight"] is not None:
        for f in case["backfill"]:
            d = f(case["weight"])
            backfilled |= {round(float(v), 4) for v in
                           (d.dose_mg, d.display_value) if isinstance(v, (int, float))}

    prep_numbers = {round(float(v), 4)
                    for group in _oc.PREP_RECIPE_NUMBERS.values()
                    for entry in group
                    for v, _, _ in _tokens(entry)}

    # The inline vial question names presentations, which _tokens already
    # strips; what remains of that block is a question, not a dose.
    for value, units, line in _tokens(text):
        # Text the CONTRACT wrote is contract-sourced by definition — the
        # cautions carry their own numbers ("10-20 mcg equals 1-2 mL of that
        # dilution", cumulative maxima quoted from the guideline) and quoting
        # them faithfully is the opposite of the failure this guards.
        if _is_contract_text(line, cautions):
            continue
        v = round(value, 4)
        assert v in authorised or v in backfilled or v in prep_numbers, (
            f"{case['name']}: served '{value:g} {units}' with no provenance.\n"
            f"  line: {line}\n"
            f"  contract authorises: {sorted(authorised)}\n"
            f"  declared backfills:  {sorted(backfilled)}\n"
            f"  prep recipe numbers: {sorted(prep_numbers)}\n"
            "A dose must come from a signed contract entry, from a calculator "
            "this case declares as a backfill, or from PREP_RECIPE_NUMBERS.")


@pytest.mark.parametrize("case", DOSE_TEMPLATE_CASES, ids=lambda c: c["name"])
def test_the_source_line_follows_what_was_actually_served(case):
    """The SOURCE line is a claim about provenance, and a false one is worse
    than none: it is what told the owner the RSI bundle was contract-served
    while it was serving 1.5 mg/kg from a hardcode."""
    text = case["render"]()
    if "**SOURCE**" not in text:
        pytest.skip("no SOURCE line on this surface")
    source = text.split("**SOURCE**:")[1].strip().splitlines()[0]

    served = case["contract"]()
    from_contract = [_oc.dose_is_from_contract(s) for s in served]

    if served and all(from_contract):
        assert source == _oc.SOURCE_ALL_CONTRACT, (
            f"{case['name']}: every dose came from a contract, and the SOURCE "
            f"line says something else: {source!r}")
    elif any(from_contract):
        assert source == _oc.SOURCE_MIXED, (
            f"{case['name']}: contracts and calculators both served, and the "
            f"SOURCE line does not say so: {source!r}")
    else:
        assert source not in (_oc.SOURCE_ALL_CONTRACT, _oc.SOURCE_MIXED), (
            f"{case['name']}: nothing came from a contract and the SOURCE line "
            f"claims one did: {source!r}")
        assert "calculator" in source.lower() or "preparation" in source.lower(), (
            f"{case['name']}: an unsourced number must SAY it is unsourced: "
            f"{source!r}")


def test_a_signed_indication_is_never_substituted_for_a_different_one():
    """The IM analgesia case, pinned as its own assertion because it is the one
    the owner called out: ketamine's signed IM entries are dissociative
    sedation at 3-4 mg/kg, twelve to sixteen times the IV analgesia dose. A
    pain request on the IM route must reach the calculator, never them."""
    ctx = _analgesia_ctx("IM")
    assert _oc._contract_analgesia_candidate(ctx) is None, \
        "an IM entry matched an analgesia request — check the route/indication scoping"

    text = _oc.build_ketamine_analgesia_response(ctx)
    give = text.split("**GIVE**")[1].split("**CAUTIONS**")[0]
    assert "dissociative sedation" not in give, \
        "an agitation indication is being served as analgesia"
    assert "120 mg" in text, "the declared IM backfill is not what got served"
    # 3 and 4 mg/kg on a 60 kg patient.
    for smuggled in ("180 mg", "240 mg"):
        assert smuggled not in text, f"an agitation dose reached a pain card: {smuggled}"


def test_the_push_dose_card_refuses_rather_than_reaching_for_the_wrong_entry():
    """An adult shock push-dose request has no signed entry. The card must say
    so — not answer with the bradycardia window, and not fall back to the
    unsourced 5 mcg floor it used to print."""
    text = _oc.build_fixed_prep_response("need push dose epi, BP 70/40 shocky")
    give = text.split("**GIVE**")[1].split("**CAUTIONS**")[0]
    assert "No signed entry for shock" in give
    assert "10-20 mcg" not in give, "the bradycardia window was substituted"
    assert "5-20 mcg" not in give, "the retired unsourced floor is back"


def test_the_retired_analgesia_hardcode_is_gone_from_the_iv_path():
    """The reported bug, pinned: 0.3 mg/kg served 18 mg at 60 kg while the
    signed NASEMSO entry says 0.25 mg/kg = 15 mg."""
    text = _oc.build_ketamine_analgesia_response(_analgesia_ctx("IV"))
    assert "15 mg" in text
    assert "18 mg" not in text, "the retired 0.3 mg/kg hardcode is back"
    assert "deterministic calculator" not in text.split("**SOURCE**:")[1]


# ─────────────────────────────────────────────────────────────────────────────
# COVERAGE — a new card cannot avoid the guard by not being in the registry.
# ─────────────────────────────────────────────────────────────────────────────

# Cards that state NO dose. Listed by name rather than detected, because
# "this card has no numbers in it" is a claim worth making explicitly: several
# of these name a drug whose dose IS signed and deliberately leave the number
# to the protocol.
DOSELESS_CARDS = {
    "build_cico_response", "build_hemorrhagic_shock_dcr_response",
    "build_sepsis_management_response", "build_anaphylaxis_response",
    "build_seizure_response", "build_hypothermic_arrest_response",
    "build_tbi_management_response", "build_mascal_response",
    "build_ketamine_drip_response", "build_cholera_response",
    "build_snake_bite_response", "build_vtach_response",
    "build_txa_sepsis_block", "build_wpw_drug_block",
}

# Plumbing: prompt blocks, gate text and the dose machinery itself. These do
# not author doses — they carry or format what the machinery produced.
NOT_A_DOSE_CARD = {
    "build_allowed_doses", "build_allowed_dose_block", "build_allowed_actions",
    "build_patient_block", "build_source_block", "build_system_prompt",
    "build_safety_hold", "build_full_query_history", "build_general_case_response",
    "build_fixed_prep_response", "build_ketamine_analgesia_response",
    "build_rsi_response",
}

# Cards that render the RECORD behind a dose already served. They print
# numbers — the range as the source writes it, the figures quoted inside a
# citation or a justification — and every one of those numbers is text read
# out of a signed entry rather than a value the card computed. That is a
# different property from the one DOSE_TEMPLATE_CASES pins, so it gets its own
# guard: test_a_provenance_card_invents_no_number below.
PROVENANCE_CARDS = {
    "build_why_this_dose_response",
}

# The three above are in NOT_A_DOSE_CARD because they are covered by name in
# DOSE_TEMPLATE_CASES instead; this set exists so the classification is total.
_REGISTERED_BUILDERS = {"build_fixed_prep_response",
                        "build_ketamine_analgesia_response",
                        "build_rsi_response"}


def test_every_response_builder_is_classified():
    """Add a build_*_response to openai_client and this test tells you to say
    which kind it is. That is the whole point: the registry cannot silently
    fall behind the code, because the code cannot grow a new card without the
    registry noticing."""
    builders = {n for n in dir(_oc)
                if n.startswith("build_") and callable(getattr(_oc, n))}
    unclassified = builders - DOSELESS_CARDS - NOT_A_DOSE_CARD - PROVENANCE_CARDS
    assert not unclassified, (
        f"unclassified response builders: {sorted(unclassified)}. Add each to "
        "DOSE_TEMPLATE_CASES (with the contract lookup it serves from and any "
        "calculator it is allowed to backfill from), or to DOSELESS_CARDS if it "
        "states no dose, to PROVENANCE_CARDS if it renders the record behind a "
        "dose already served, or to NOT_A_DOSE_CARD if it is plumbing.")


def test_a_provenance_card_invents_no_number():
    """The guard PROVENANCE_CARDS gets instead of DOSE_TEMPLATE_CASES.

    "Where did this number come from" is the one question where a made-up
    answer does specific harm: it would launder an owner declaration into a
    citation, which is the failure the declaration mechanism exists to
    prevent. So every dose-shaped number this card prints has to be a number
    the entries it is describing actually contain.
    """
    ctx = _rsi_ctx()
    history = "RSI now 80kg. why this dose?"
    pairs = _oc.why_this_dose_entries("why this dose?", history, ctx)
    assert pairs, "the provenance card found no entries to describe"

    text = _oc.build_why_this_dose_response("why this dose?", history, ctx)
    source_text = json.dumps(
        [e for _, e in pairs], ensure_ascii=False)

    for value, units, line in _tokens(text):
        assert f"{value:g}" in source_text, (
            f"the provenance card printed '{value:g} {units}' and no entry it "
            f"describes contains that number.\n  line: {line}")


def test_the_registered_cards_are_actually_registered():
    """DOSE_TEMPLATE_CASES must cover every card claimed to be covered by it."""
    covered = " ".join(c["name"] for c in DOSE_TEMPLATE_CASES)
    for name, token in (("build_rsi_response", "rsi_bundle"),
                        ("build_ketamine_analgesia_response", "ketamine_analgesia"),
                        ("build_fixed_prep_response", "epi")):
        assert name in _REGISTERED_BUILDERS
        assert token in covered, f"{name} has no case in DOSE_TEMPLATE_CASES"


@pytest.mark.parametrize("name", sorted(DOSELESS_CARDS))
def test_a_doseless_card_states_no_dose(name):
    """If one of these ever grows a number, it becomes a dose surface and has
    to be registered like the rest."""
    text = getattr(_oc, name)()
    offenders = [(v, u, l) for v, u, l in _tokens(text)]
    assert not offenders, (
        f"{name} now states a dose: {offenders}. Either take the number out, or "
        "move it into DOSE_TEMPLATE_CASES with a contract lookup behind it.")


@pytest.mark.parametrize("case", DOSE_TEMPLATE_CASES, ids=lambda c: c["name"])
def test_no_surface_states_the_same_dose_twice(case):
    """One drug, one indication, one line.

    The trace test above cannot catch a duplicate: both copies have honest
    provenance. But two identical GIVE lines read as two doses under load, and
    the way duplicates arrive is exactly the way the seizure bypass arrived —
    a second lookup added beside the first, both correct, neither aware of the
    other. This is the assertion that would have failed on `or is_seizure`
    even though the calculator and the contract agree on 4 mg today.
    """
    served = case["contract"]()
    keys = [(getattr(s, "drug", None), getattr(s, "indication", None),
             getattr(s, "route", None)) for s in served]
    dupes = [k for k in set(keys) if keys.count(k) > 1]
    assert not dupes, f"{case['name']}: served twice: {dupes}"

    # And no two benzodiazepines for one seizure, no two paralytics for one
    # intubation: the role-collision shape, asserted on the roles that have
    # actually collided.
    drugs = {getattr(s, "drug", None) for s in served}
    assert len({"lorazepam", "midazolam"} & drugs) <= 1, \
        f"{case['name']}: two benzodiazepines served together: {sorted(drugs)}"
    assert len({"rocuronium", "succinylcholine"} & drugs) <= 1, \
        f"{case['name']}: two paralytics served together: {sorted(drugs)}"


@pytest.mark.parametrize("case", DOSE_TEMPLATE_CASES, ids=lambda c: c["name"])
def test_a_calculator_never_serves_what_a_contract_covers(case):
    """The supersede rule, asserted on the OUTPUT instead of trusted to the one
    function that implements it.

    Worth being precise about what this catches and what it cannot. Two doses
    with the SAME NUMBER are indistinguishable in rendered text — the seizure
    bypass survived unseen for exactly that reason, because the retired
    calculator and the signed entry both say 4 mg at 60 kg. No test that reads
    numbers off a screen can see that.

    Provenance is not invisible. If the bank covers this drug for this
    indication, the thing that got served has to be the contract's — not a
    calculator that happens to agree with it today, and not a calculator that
    won because it was appended first and the dedupe keeps the first. That is
    the regression this pins: correctness here currently depends on append
    order, and append order is not a thing anyone remembers.
    """
    for s in case["contract"]():
        indication = (getattr(s, "indication", "") or "").lower()
        drug = getattr(s, "drug", None)
        covered = [e for e in dc.servable_entries().get(drug, [])
                   if (e.get("indication") or "").lower() == indication]
        if not covered:
            continue
        assert _oc.dose_is_from_contract(s), (
            f"{case['name']}: {drug} '{indication}' is covered by a signed "
            f"contract, but what got served came from {s.source!r}. A "
            "calculator backfills only where the bank is silent.")


# ─────────────────────────────────────────────────────────────────────────────
# THE LINTS ACTUALLY RUN
# ─────────────────────────────────────────────────────────────────────────────

def test_the_generic_name_overlap_lint_runs_at_import():
    """It was defined and never called, from the day it was written until
    2026-08-26.

    That is the vitamin-K class waiting to recur: a substring alias quietly
    eating a real drug, in a file that reads as though the class were covered.
    Asserting the RESULT exists at module level is what makes "wired up"
    testable — a lint whose output nothing holds is a lint nobody ran.
    """
    assert hasattr(dc, "GENERIC_NAME_OVERLAPS")
    assert dc.GENERIC_NAME_OVERLAPS == dc.lint_generic_name_overlaps()


def test_every_reported_overlap_is_a_combination_product():
    """The lint is informational because a combination product legitimately
    contains its components' names. If an overlap ever appears that is NOT one,
    resolve_drugs() has two names that could match the same span and the
    longest-match rule is deciding a clinical question silently."""
    unexpected = [p for p in dc.GENERIC_NAME_OVERLAPS
                  if " + " not in p.split(" contains ")[0]]
    assert unexpected == [], (
        f"generic names shadow each other without being combinations: {unexpected}")


def test_the_alias_lint_still_refuses_rather_than_reports():
    """The two lints are deliberately different: an alias collision is a
    refusal, a generic-name overlap is a note. Conflating them would either
    fail the build on a legal combination or teach the team to ignore the one
    that catches real shadows."""
    assert dc.ALIAS_COLLISIONS == [], f"alias collisions present: {dc.ALIAS_COLLISIONS}"


# ═══════════════════════════════════════════════════════════════════════════
# CAUTION TIERS, CONTRAINDICATIONS AT SERVE — owner rulings 9-12, 2026-08-26
#
# The RSI bundle served eighteen caution bullets, several of them paragraphs
# about what a guideline does NOT state, to a medic holding a laryngoscope —
# and served the contraindications field to nobody at all, because nothing
# rendered it. These tests pin the four rulings that answered that:
#
#   9   the no-pump entry's one overloaded caution becomes two, re-signed
#  10   one sedate-before-paralyse line survives, and it is the sourced one
#  11   the short owner-declared label serves; the full banner is the record
#  12   contraindications render, and their thinness is linted rather than hidden
# ═══════════════════════════════════════════════════════════════════════════

def test_default_is_serve_because_the_alternative_hides_things_silently():
    """The whole safety argument for the mechanism, in one assertion.

    A bare string has never been tiered by anyone. It SERVES. Any other default
    would mean one forgotten annotation puts a caution nowhere a medic looks,
    and the entries most likely to be edited in a hurry are the ones where that
    matters most.
    """
    e = signed_entry(cautions=["never been tiered by anybody"])
    assert dc.caution_tier("never been tiered by anybody") == dc.CAUTION_SERVE
    assert dc.serve_cautions(e) == ["never been tiered by anybody"]
    assert dc.detail_cautions(e) == []


def test_only_the_exact_word_detail_takes_a_line_off_the_screen():
    """Every ambiguous state resolves towards the medic seeing the text."""
    for tier in (None, "", "serve", "SERVE"):
        c = {"text": "x", "tier": tier} if tier is not None else {"text": "x"}
        assert dc.caution_tier(c) == dc.CAUTION_SERVE, tier
    assert dc.caution_tier({"text": "x", "tier": "detail"}) == dc.CAUTION_DETAIL
    assert dc.caution_tier({"text": "x", "tier": "DETAIL"}) == dc.CAUTION_DETAIL


def test_a_tier_the_schema_does_not_know_refuses_the_entry():
    """caution_tier() serves it — harmless — and the fence says so out loud.

    Both halves matter. The permissive read means a typo cannot hide a line;
    the refusal means nobody has to notice the typo by reading the file. Same
    doctrine as classify_units(), which refuses an unrecognised unit rather
    than assuming milligrams.
    """
    e = signed_entry(cautions=[{"text": "x", "tier": "detials"}])
    ok, why = dc.entry_is_servable(e)
    assert not ok and "tier" in why
    assert dc.caution_tier({"text": "x", "tier": "detials"}) == dc.CAUTION_SERVE


def test_a_caution_that_would_render_as_junk_refuses_the_entry():
    for bad in ([{"tier": "serve"}], [{"text": "   "}], [""], "not a list"):
        assert not dc.entry_is_servable(signed_entry(cautions=bad))[0], bad


def test_the_detail_tier_is_kept_not_deleted():
    """"Detail" has to mean one question away. A tier that dropped text would
    be worse than the wall it replaced."""
    e = signed_entry(cautions=["serve me",
                               {"text": "keep me", "tier": "detail"}])
    assert dc.serve_cautions(e) == ["serve me"]
    assert dc.detail_cautions(e) == ["keep me"]
    assert dc.caution_texts(e) == ["serve me", "keep me"]


def test_the_serve_tier_stays_within_budget():
    """THE BUDGET. A screen, not a document.

    Both ceilings, because they fail differently: six short bullets and one
    long paragraph are both unreadable at the moment of giving a drug, and a
    count on its own would pass the paragraph. Pinned as a test rather than
    enforced at serve — a dose withheld because its cautions are long would be
    a worse failure than a long screen.
    """
    over = dc.serve_caution_overruns()
    assert over == [], (
        f"{len(over)} servable entr(y/ies) exceed "
        f"{dc.SERVE_CAUTION_BUDGET} serve-tier cautions or "
        f"{dc.SERVE_CAUTION_CHAR_BUDGET} characters of them: {over}. Tier the "
        "provenance commentary to 'detail' — do not delete it.")


def test_the_untiered_caution_lint_is_a_backlog_and_says_so():
    """Default-is-serve means an untiered caution is SAFE, not finished. The
    lint is how the difference stays visible instead of being declared done."""
    rows = dc.lint_unclassified_cautions()
    assert rows, "every caution is tiered — update this test, the backlog is closed"
    for name, ind, route, pop, text, servable in rows:
        assert isinstance(text, str) and text
        # Everything it reports is on screen right now, by definition.
        entry = next(e for e in dc.DRUGS[name]["dose_entries"]
                     if e.get("indication") == ind and e.get("route") == route
                     and e.get("population") == pop)
        assert text in dc.serve_cautions(entry)


def test_the_detail_tier_hides_only_these_families():
    """THE REGISTRY OF WHAT IS NOT ON THE DOSE SCREEN.

    Hiding a line from a medic is a clinical decision, so it cannot be a side
    effect of an edit somewhere else. Every family below is either boilerplate
    about what a source does NOT say, or commentary on provenance — plus the
    one cross-reference owner ruling 9 placed here by name. Tier a new string
    to detail and this test asks you to say so on purpose.
    """
    families = {c[:44] for n, d in dc.DRUGS.items()
                for e in d["dose_entries"] for c in dc.detail_cautions(e)}
    assert families == {
        "The cited guideline states no cumulative max",
        "The cited guideline states no maximum single",
        "HISTORICAL CAUTION, NOT AN ACTIVE CONTRAINDI",
        "CORROBORATING: JTS ID40 (05 Apr 2021) p.3 gi",
        "ALTERNATE, recorded not served: JTS ID40 (05",
        "ALTERNATE SHAPE, AND THE ONLY ONE WITH A CIT",
        "Neither JTS CPG states a contraindication fo",
        "No approved source states a reduced PAEDIATR",
        "If an infusion pump IS available, see ketami",
    }


def test_ruling_9_the_overloaded_caution_became_two():
    """OWNER RULING 9, 2026-08-26. One caution carried the repeat interval AND
    a cross-reference to the pump-available entry AND a citation of it. The
    interval is what a medic acts on; the cross-reference is what they read
    afterwards. Two claims in one bullet means the second one buries the first.
    """
    bolus = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "repeated bolus" in e["indication"])
    served = dc.serve_cautions(bolus)
    assert "Repeat q20-30min. Preferred where there is no pump." in served
    assert not any("infusion pump IS available" in c for c in served), \
        "the cross-reference is back on the dose screen"
    assert any("infusion pump IS available" in c
               for c in dc.detail_cautions(bolus)), \
        "the cross-reference was deleted rather than tiered"


def test_ruling_9_re_authoring_the_entry_re_signed_and_re_declared_it():
    """Editing what a signed entry says is a change to what was signed."""
    bolus = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "repeated bolus" in e["indication"])
    assert bolus["review_date"] == "2026-08-26"
    assert bolus["owner_declaration"]["declared_on"] == "2026-08-26"
    assert bolus["reviewed_by"] in dc.SIGNOFF_AUTHORS
    assert dc.entry_is_servable(bolus)[0]
    # The declaration still names the dose it serves — the anti-smuggling check
    # is exactly what a re-declaration must not break.
    assert bolus["owner_declaration"]["declared_value"] == bolus["dose_range"]
    # And the entry the cross-reference points at agrees about the date.
    pump = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                if "infusion pump available" in e["indication"])
    assert not any("2026-08-25" in c and "AI-AIM" in c
                   for c in dc.caution_texts(pump)), \
        "the mirror entry still quotes the superseded declaration date"


def test_ruling_10_the_surviving_line_is_the_sourced_one():
    """OWNER RULING 10, 2026-08-26. "Give AFTER the induction agent" and "JTS
    ID39: ALWAYS SEDATE PRIOR TO PARALYZING" are one instruction written twice.
    The JTS line carries the instruction AND the guideline's emphasis, and it
    is sourced — so it is the one that stays, on every paralytic entry."""
    for e in dc.DRUGS["rocuronium"]["dose_entries"]:
        if not dc.entry_is_servable(e)[0]:
            continue
        served = dc.serve_cautions(e)
        assert "JTS ID39: ALWAYS SEDATE PRIOR TO PARALYZING." in served
        assert not any("Give AFTER the induction agent" in c for c in served)
        assert any("ID39" in s.get("citation", "") for s in e["sources"]), \
            "the surviving line cites a guideline this entry does not"


def test_ruling_10_the_bundle_says_it_once():
    """The other half of collapsing a duplicate: the bundle serves an induction
    agent and a paralytic, and both entries carry the same JTS line. A caution
    printed twice teaches the reader that this screen repeats itself."""
    text = _oc.build_rsi_response(_rsi_ctx(), "rsi now")
    assert text.count("ALWAYS SEDATE PRIOR TO PARALYZING") == 1


def test_ruling_12_contraindications_reach_the_medic():
    """OWNER RULING 12, 2026-08-26. The field had been authored, reviewed,
    signed — and rendered nowhere. A do-not-give list nothing displays is not a
    safety feature, it is a comment."""
    text = _oc.build_rsi_response(_rsi_ctx(), "rsi now with sux")
    assert "**CONTRAINDICATIONS**" in text
    block = text.split("**CONTRAINDICATIONS**")[1].split("**CAUTIONS**")[0]
    for ci in ("Burns", "Hyperkalemia", "Spinal cord injury"):
        assert ci in block, f"succinylcholine's {ci!r} never reached the screen"


def test_ruling_12_contraindications_reach_the_generator_too():
    """Both channels. A query answered by the generator instead of a card used
    to get the dose with the do-not-give list stripped off it."""
    ctx = _analgesia_ctx("IV")
    block = _oc.build_allowed_dose_block(
        _oc.build_allowed_doses("ketamine dose for pain, 60kg", ctx))
    assert "Contraindications:" in block


def test_ruling_12_an_empty_contraindication_list_says_what_it_means():
    """"None recorded" alone reads as a clearance. It is a gap in the record."""
    d = _oc.DoseCandidate(drug="testosteril", indication="TEST", route="IV",
                          dose_mg=1.0, source="drug_contract:x")
    block = _oc.served_contraindications_block([d])
    assert "gap in the record" in block and "not a clearance" in block


def test_ruling_12_a_contraindication_is_never_deduped_across_drugs():
    """Cautions dedup bundle-wide; contraindications dedup only within a drug.
    Shortening drug B's do-not-give list because drug A said it first is how a
    medic reads "nothing recorded" off a drug that has three."""
    shared = ["Hyperkalemia"]
    a = _oc.DoseCandidate(drug="drug-a", indication="i", route="IV", dose_mg=1.0,
                          source="drug_contract:a", contraindications=list(shared))
    b = _oc.DoseCandidate(drug="drug-b", indication="i", route="IV", dose_mg=1.0,
                          source="drug_contract:b", contraindications=list(shared))
    block = _oc.served_contraindications_block([a, b])
    assert block.count("Hyperkalemia") == 2
    # Same drug, two entries: once is right.
    b2 = _oc.DoseCandidate(drug="drug-a", indication="j", route="IV", dose_mg=1.0,
                           source="drug_contract:a", contraindications=list(shared))
    assert _oc.served_contraindications_block([a, b2]).count("Hyperkalemia") == 1


def test_the_thin_contraindication_lint_makes_the_thinness_visible():
    """Ruling 12 rendered the field KNOWING parts of it are weak. Weakness is a
    content problem; invisibility was the safety problem. This is what keeps
    the content problem from being forgotten now that it looks answered."""
    rows = dc.lint_thin_contraindications()
    live = [r for r in rows if r[-1]]
    assert live, "no thin contraindications — update this test, the work is done"
    assert {r[0] for r in live} == {"fentanyl", "ketamine", "naloxone",
                                    "rocuronium"}, \
        f"the thin set moved: {sorted({r[0] for r in live})}"
    assert {r[4] for r in live} == {"no contraindications recorded",
                                    "only trivial: Hypersensitivity"}
    # And it reports what a medic is being shown, not what the file hides.
    for name, ind, route, pop, reason, servable in live:
        entry = next(e for e in dc.DRUGS[name]["dose_entries"]
                     if e.get("indication") == ind and e.get("route") == route
                     and e.get("population") == pop)
        assert len(dc.serve_contraindications(entry)) <= 1


def test_the_detail_hint_rides_with_every_contract_dose():
    """A held-back tier that nobody is told about is a deleted tier."""
    for text in (_oc.build_rsi_response(_rsi_ctx(), "rsi now"),
                 _oc.build_ketamine_analgesia_response(_analgesia_ctx("IV"))):
        assert "why this dose?" in text


# ── "why this dose?" — the detail tier, on request ──────────────────────────

def test_why_this_dose_does_not_eat_a_dose_request():
    """This gate returns provenance INSTEAD of a dose, so a false positive
    costs a medic the thing they actually asked for."""
    for q in ("how much ketamine and why", "what dose of ketamine, and why",
              "give me the ketamine dose", "why is he hypotensive",
              "why", "rsi now"):
        assert not _oc.is_why_this_dose_query(q), q
    for q in ("why this dose?", "why that dose", "where did that dose come from",
              "what's the source for the number"):
        assert _oc.is_why_this_dose_query(q), q


def test_why_this_dose_describes_the_bundle_that_was_actually_served():
    """Not every entry that matched the indication — the ones the role rulings
    picked. A provenance answer listing both paralytics describes a bundle
    nobody was given."""
    ctx = _rsi_ctx()
    served = {(d.drug, d.indication)
              for d in _oc._contract_rsi_candidates("rsi now", ctx)}
    described = {(n, e["indication"])
                 for n, e in _oc.why_this_dose_entries("why this dose?",
                                                       "rsi now. why this dose?",
                                                       ctx)}
    assert described == served


def test_why_this_dose_never_calls_a_declaration_a_citation():
    """The one question where an invented answer does specific harm: it would
    launder the owner's number into the guideline's."""
    ctx = _rsi_ctx()
    text = _oc.build_why_this_dose_response(
        "why this dose?", "rsi now 80kg. why this dose?", ctx)
    assert "OWNER-DECLARED DOSE — NOT FROM A PUBLISHED GUIDELINE" in text
    assert "Andrew Azelton - AI-AIM" in text, "the record dropped the signature"
    assert "SHAPE ONLY" in text, "the shape doctrine is not marked as shape-only"
    assert "Doctrine supporting the SHAPE — not the number" in text


def test_why_this_dose_returns_before_retrieval_ever_runs():
    """END TO END, THROUGH THE PIPELINE, with no retrieval client at all.

    Two things at once: the gate is wired in (a builder nothing calls is the
    defect this repo has already had twice), and it returns at step 2a-i —
    passing None for chromadb would raise anywhere downstream of it.
    """
    out = _oc._run_pipeline(
        "why this dose?", None,
        conversation_history=[{"query": "RSI now, 80kg, IV", "response": "..."}])
    assert out["source_mode"] == "DOSE_PROVENANCE"
    assert out["response"].startswith("**WHY THIS DOSE**")
    assert "ketamine" in out["response"]


def test_why_this_dose_says_nothing_when_it_knows_nothing():
    """None, not an apology: a question this gate cannot match is a question
    the rest of the pipeline should get a turn at."""
    assert _oc.build_why_this_dose_response(
        "why this dose?", "why this dose?", _PC()) is None


def test_the_files_note_about_itself_is_derived_from_itself():
    """`generated_note` sits at the top of drug_contracts.json and is the first
    thing a reader is told about the bank. It said "Nothing in this file is
    signed and nothing in it is served" through 46 signatures.

    A prose claim about a file, stored inside that file, drifts the moment the
    file changes and nothing notices. So it is computed from the file's own
    contents, refreshed by every write through tools/set_contract.py, and
    checked here — with the correct string in the failure message, because a
    test that only says "stale" leaves the reader to write the sentence.
    """
    raw = json.loads((pathlib.Path(dc.__file__).parent
                      / "drug_contracts.json").read_text())
    assert raw["generated_note"] == dc.state_note(raw), (
        "drug_contracts.json's generated_note no longer describes the file. "
        f"Replace it with:\n\n{dc.state_note(raw)}")


def test_the_note_counts_servable_rather_than_merely_signed():
    """A signature the allowlist will not honour carries no traffic, and a
    reader asking "how much of this bank is live" would be told it does."""
    doc = {"drugs": [synthetic_drug(dose_entries=[
        signed_entry(),
        signed_entry(indication="TEST unhonoured", reviewed_by="somebody else"),
    ])]}
    assert dc.state_note(doc).startswith("1 of 2 dose entries across 1 of 1 drugs")


def test_ruling_10_reaches_a_paralytic_served_on_its_own():
    """The gap the bundle hid. A paediatric succinylcholine query serves that
    entry with no induction agent beside it to carry the instruction, so the
    line has to be on the paralytic entry itself — on every one of them."""
    for e in dc.DRUGS["succinylcholine"]["dose_entries"]:
        if not dc.entry_is_servable(e)[0]:
            continue
        assert "JTS ID39: ALWAYS SEDATE PRIOR TO PARALYZING." in dc.serve_cautions(e), \
            f"{e['indication']} / {e['population']} serves a paralytic with no "
        assert any("ID39" in s.get("citation", "") for s in e["sources"])


def test_ruling_10_the_paediatric_bundle_also_says_it_once():
    ctx = _PC(confirmed_weight_kg=20.0, weight_source="stated",
              is_pediatric=True, age_years=6.0, route_preference="IV")
    text = _oc.build_rsi_response(ctx, "paeds rsi with sux")
    assert text.count("ALWAYS SEDATE PRIOR TO PARALYZING") == 1
