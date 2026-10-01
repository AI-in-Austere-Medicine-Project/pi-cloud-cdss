"""A17: abbreviated drug names in the free-text dose check (owner, #114 review).

The router's slang table (query_aliases.json) knew "mag", "bicarb", "levo",
"vec", "dilt", "vaso"; the dose check's lexicon did not, so a dose written
under the abbreviation was never attributed to a drug and passed:

  "GIVE: amiodarone 150 mg IV"  held      "GIVE: amio 150 mg IV"  served
  "GIVE: magnesium 2 g IV"      held      "GIVE: mag 2 g IV"      served

The check now reads the slang table under the bank and the lexicon (a bank
name or alias always wins), resolving each alias through its expansion to the
one drug it names. "ami" is excluded as ambiguous (amiodarone or acute MI);
so is any alias the table itself marks "context-dependent" ("k").
"""
import json
import pathlib

import pytest

import drug_contracts as dc
import openai_client as oc

SERVER = pathlib.Path(__file__).resolve().parents[1]
Q = "80kg male, wide complex tachycardia with a pulse, what do I give"


def _issues(answer, q=Q):
    ctx = oc.rebuild_patient_context_from_history(q)
    return oc.run_deterministic_checks(q, answer, ctx, oc.build_allowed_doses(q, ctx)).issues


# ── the four examples from the D5b finding ─────────────────────────────────
@pytest.mark.parametrize("answer,drug", [
    ("GIVE: amio 150 mg IV over 10 min", "amiodarone"),
    ("GIVE: mag 2 g IV", "magnesium sulfate"),
    ("GIVE: levo 5 mcg/min", "norepinephrine"),
    ("GIVE: bicarb 1 g IV", "sodium bicarbonate"),
])
def test_an_abbreviated_unsigned_dose_is_held_like_the_full_name(answer, drug):
    issues = _issues(answer)
    assert issues, f"{answer!r} passed the dose check"
    assert any(drug in i for i in issues), issues


@pytest.mark.xfail(strict=True, reason="mEq and units single doses are not read by the free-text "
                                       "check under any name (sodium bicarbonate 50 mEq passes too): "
                                       "a separate finding, its own item")
def test_bicarb_in_meq_is_held():
    assert _issues("GIVE: bicarb 50 mEq IV")


@pytest.mark.parametrize("full,short", [
    ("GIVE: amiodarone 150 mg IV over 10 min", "GIVE: amio 150 mg IV over 10 min"),
    ("GIVE: magnesium sulfate 2 g IV", "GIVE: mag 2 g IV"),
    ("GIVE: norepinephrine 5 mcg/min", "GIVE: levo 5 mcg/min"),
    ("GIVE: vecuronium 8 mg IV", "GIVE: vec 8 mg IV"),
    ("GIVE: diltiazem 20 mg IV", "GIVE: dilt 20 mg IV"),
])
def test_the_abbreviation_and_the_full_name_get_the_same_verdict(full, short):
    assert bool(_issues(full)) and bool(_issues(short))


# ── the table, resolved ─────────────────────────────────────────────────────
TABLE = json.loads((SERVER / "query_aliases.json").read_text())


@pytest.mark.parametrize("alias,drug", [
    ("mag", "magnesium sulfate"), ("bicarb", "sodium bicarbonate"), ("levo", "norepinephrine"),
    ("vec", "vecuronium"), ("dilt", "diltiazem"), ("vaso", "vasopressin"),
    ("rocky onium", "rocuronium"), ("epi drip", "epinephrine"), ("norepi drip", "norepinephrine"),
    ("epi", "epinephrine"), ("norepi", "norepinephrine"), ("roc", "rocuronium"),
    ("sux", "succinylcholine"), ("versed", "midazolam"), ("ativan", "lorazepam"),
    ("amio", "amiodarone"),
])
def test_slang_is_recognised_by_the_dose_check(alias, drug):
    assert dc.recognised_drug_index().get(alias) == drug


def test_every_drug_alias_in_the_router_table_is_recognised():
    idx = dc.recognised_drug_index()
    for alias, generic in dc.slang_drug_aliases().items():
        assert idx.get(alias) == generic, alias
    # every table entry that names exactly one drug made it in, bar the exclusions
    assert {"mag", "bicarb", "levo", "vec", "dilt", "vaso"} <= set(dc.slang_drug_aliases())


@pytest.mark.parametrize("alias", ["ami", "k"])
def test_ambiguous_abbreviations_are_excluded(alias):
    assert alias not in dc.recognised_drug_index()
    assert alias not in dc.slang_drug_aliases()


@pytest.mark.parametrize("alias", ["cric", "blood", "pressors", "tq", "march", "king", "cat", "rsi"])
def test_non_drug_and_multi_drug_entries_are_not_drugs(alias):
    assert alias in TABLE
    assert alias not in dc.slang_drug_aliases()


def test_the_bank_still_wins():
    # A slang entry never re-points a term the contract bank owns.
    bank = dc.alias_index()
    idx = dc.recognised_drug_index()
    for term, generic in bank.items():
        assert idx[term] == generic


def test_ami_in_an_answer_is_not_read_as_a_drug():
    assert "amiodarone" not in {g for *_, g in oc._drug_spans("history of AMI last year")}
