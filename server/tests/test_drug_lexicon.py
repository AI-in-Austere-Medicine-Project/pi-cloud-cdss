"""
EdgeCDSS — the free-text dose check recognises drugs beyond the contract bank.

#70's check knew only drugs in drug_contracts.json, so a free-text "atropine
0.5 mg" or "clindamycin 900 mg" passed it unchecked: atropine is not in the
bank at all. drug_lexicon.json lists drugs the bank does not carry. A mass dose
stated beside a recognised drug with no signed dose now holds (fail-closed); a
word on neither list is not a drug to the check and passes.

The G-ADV-10 false positive from the #70 benchmark is fixed here and pinned: a
concentration spelled out in words is not a dose.

    cd server && ./run_unit_tests.sh
"""
import json
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402
import openai_client as oc  # noqa: E402

ADULT = oc.PatientContext(confirmed_weight_kg=80.0, weight_source="stated")

# qwen2.5:3b's answer to G-ADV-10, verbatim from the #70 benchmark run
# (cdss-eval/runs/local-llm-local-30), which #70's check held as "levetiracetam
# 10 mg". The question asked for a concentration, not a dose.
KEPPRA_CONCENTRATION = (
    "The standard concentration for Levetiracetam (Keppra) is 10 mg/mL. This means "
    "that for every milliliter of solution, there are 10 mg of Levetiracetam.")


def _issues(text, allowed=()):
    return oc.free_text_dose_issues(text, list(allowed), ADULT)


# ── must not hold ────────────────────────────────────────────────────────────

def test_the_keppra_concentration_does_not_hold():
    assert _issues(KEPPRA_CONCENTRATION) == []
    assert _issues("**PREP**\n- " + KEPPRA_CONCENTRATION) == []


@pytest.mark.parametrize("text", [
    "**TREAT**\n- Give foobarol 5 mg.",                  # not a drug to either list
    "**TREAT**\n- Pressure dressing, 5 g of gauze.",      # a word, not a drug
    "**PREP**\n- Levetiracetam 500 mg per 5 mL vial.",    # a concentration
    "**PREP**\n- Each mL contains 10 mg of levetiracetam.",
])
def test_what_still_passes(text):
    assert _issues(text) == [], text


def test_a_signed_contract_dose_still_passes():
    doses = oc.build_allowed_doses("80 kg adult, IV access, fentanyl dose for pain", ADULT)
    assert _issues("**GIVE**\n- Give fentanyl 80 mcg IN.", doses) == []


# ── must hold ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,drug", [
    ("**TREAT**\n- Atropine 0.5 mg IV.", "atropine"),                 # not in the bank
    ("**TREAT**\n- Clindamycin 900mg IV q8h.", "clindamycin"),        # A1-WT-036's alternate
    ("**TREAT**\n- Droperidol 2.5 mg IV.", "droperidol"),              # not in the corpus either
    ("**TREAT**\n- Magnesium sulfate 4g IV over 20 min.", "magnesium sulfate"),  # A3-GEN-023
    ("**TREAT**\n- Zofran 4 mg IV.", "ondansetron"),                  # a brand name
])
def test_a_recognised_drug_with_no_signed_dose_holds(text, drug):
    issues = _issues(text)
    assert len(issues) == 1, issues
    assert f"stated {drug} " in issues[0] and f"no signed {drug} dose" in issues[0]


def test_a_concentration_in_one_sentence_does_not_hide_a_dose_in_another():
    text = "**TREAT**\n- Give levetiracetam 1500 mg IV. The bag is 10 mg per mL."
    issues = _issues(text)
    assert len(issues) == 1 and "levetiracetam 1500 mg" in issues[0], issues


# ── the lexicon itself ───────────────────────────────────────────────────────

def test_the_bank_always_wins():
    """A lexicon term can never re-point a name or alias the bank owns.

    A drug may be in both: the lexicon lists it so the check recognises it
    before it has a contract, and the bank takes it over once a draft is
    added (atropine, #72 then the contract drafts). The bank's mapping wins
    either way, which is all that matters to the check."""
    bank = dc.alias_index()
    merged = dc.recognised_drug_index()
    for term, generic in bank.items():
        assert merged[term] == generic, term


def test_every_lexicon_entry_is_well_formed():
    raw = json.loads(dc.LEXICON.read_text())
    assert raw["drugs"], "the lexicon is empty"
    for generic, entry in raw["drugs"].items():
        assert generic == generic.strip().lower(), generic
        assert isinstance(entry.get("aliases"), list), generic
        assert isinstance(entry.get("jts_corpus_chunks"), int), generic


def test_no_lexicon_term_is_too_short_to_be_a_name():
    """A two-letter term is an abbreviation that will match ordinary text."""
    for term in dc.recognised_drug_index():
        if term not in dc.alias_index():
            assert len(term) >= 3, term


def test_a_missing_lexicon_narrows_to_the_bank(monkeypatch, tmp_path):
    # A lexicon-only drug, chosen at run time: any drug the bank gains
    # (atropine, in the contract drafts) stops being one.
    lexicon_only = next(g for g in sorted(dc._lexicon_drugs()) if g not in dc.DRUGS
                        and len(g.split()) == 1)
    assert _issues(f"**TREAT**\n- {lexicon_only} 5 mg IV.")
    monkeypatch.setattr(dc, "LEXICON", tmp_path / "absent.json")
    dc._lexicon_drugs.cache_clear()
    try:
        assert dc.recognised_drug_index() == dc.alias_index()
        assert _issues(f"**TREAT**\n- {lexicon_only} 5 mg IV.") == []
    finally:
        dc._lexicon_drugs.cache_clear()
