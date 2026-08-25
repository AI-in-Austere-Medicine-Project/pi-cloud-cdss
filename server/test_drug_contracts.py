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


def test_ruling_7_did_not_launder_the_hardcode_into_a_sourced_dose():
    """THE POINT OF THE RULING THAT IS EASIEST TO LOSE.

    Ruling for the bolus SHAPE settles which answer the owner wants. It does
    not put a citation under 0.5 mg/kg, which is still the pre-contract
    hardcode. The flag stays, the fence still refuses, and the entry says so in
    its own cautions rather than only in a note nobody serves.
    """
    bolus = next(e for e in dc.DRUGS["ketamine"]["dose_entries"]
                 if "repeated bolus" in e["indication"])
    assert "MIGRATED_UNSOURCED" in bolus["flags"]
    ok, why = dc.entry_is_servable(
        dict(bolus, signoff=True, reviewed_by=dc.SIGNOFF_AUTHORS[0],
             review_date="2026-08-25"))
    assert not ok and "MIGRATED_UNSOURCED" in why
    assert any("NOT IN ANY APPROVED SOURCE" in c for c in bolus["cautions"])


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
