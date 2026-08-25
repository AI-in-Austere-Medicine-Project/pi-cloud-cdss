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
                joined = " ".join(e.get("cautions") or [])
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
    assert dc.servable_entries() == {}






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
    assert e["cautions"][0].startswith("TITRATE")
    assert any("no approved source states a reduced PAEDIATRIC" in c.lower()
               or "reduced PAEDIATRIC" in c for c in e["cautions"])


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
    assert any("ALTERNATE" in c and "1 mg/kg" in c for c in adult[0]["cautions"]), \
        "ID40's value must survive as a recorded alternate"


def test_ruling_4_rocuronium_is_split_by_age():
    roc = {e["population"]: e["dose_range"]["min"]
           for e in dc.DRUGS["rocuronium"]["dose_entries"]
           if isinstance(e["dose_range"], dict)}
    assert roc == {"adult": 1.2, "peds": 1.0}, roc
    for e in dc.DRUGS["rocuronium"]["dose_entries"]:
        if isinstance(e["dose_range"], dict):
            assert any("CORROBORATING" in c for c in e["cautions"])


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
             if any("HISTORICAL CAUTION" in c for c in e["cautions"])]
    assert noted
    for e in noted:
        joined = " ".join(e["cautions"])
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
    assert any("ongoing sedation" in c and "ID61" in c for c in bolus["cautions"])
    assert any("repeated bolus" in c and "0.5 mg/kg" in c for c in pump["cautions"])


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

    # And the entry says so in its own cautions, which is what a medic reads.
    assert any("OWNER DECLARATION" in c and "NOT A GUIDELINE VALUE" in c
               for c in bolus["cautions"])


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
    """The banner rides in the CAUTIONS, first, because that is the text that
    reaches a medic at the moment of giving the drug. A provenance that only
    exists in the JSON is a provenance nobody reads."""
    e = _declared_fixture()
    served = dc.serve_cautions(e)
    assert served[0].startswith("OWNER-DECLARED DOSE")
    assert "Test Owner - AI-AIM" in served[0]
    assert served[1:] == e["cautions"], \
        "serve_cautions dropped or reordered the entry's own cautions"


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
    assert dc.serve_cautions(e) == e["cautions"]


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
    # Channel 1: prose a medic reads, first, before the clinical cautions.
    assert c.warning.startswith("OWNER-DECLARED DOSE")
    assert "Test Owner - AI-AIM" in c.warning
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
    assert "OWNER-DECLARED DOSE" in text
    assert "not a value any CPG states" in text


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
