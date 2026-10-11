"""A caution never states another drug's dose (owner, 2026-10-11).

A served caution is in the ALLOWED_DOSES block the generator reads, and the
generator copies it. Only the asked drug's doses are built for a question, so
a copied dose of another drug is held, even where that drug has a signed
entry: edgecdss-v3's B1 answer copied fentanyl's "Naloxone (0.4 mg IV or IM)"
and was held for it (found in A25).

The edits that bring the bank to the rule are drafted for the owner to sign in
docs/authoring/CAUTION_DOSE_EDITS_2026-10-11.md. Until they are signed and
applied, the rule is an expected failure, and the list of breaking cautions is
pinned so no new one is added meanwhile.
"""
import json
import pathlib

import pytest

import openai_client as oc

CONTRACTS = pathlib.Path(oc.__file__).parent / "drug_contracts.json"

# The eight caution texts the draft edits, by their first words.
DRAFTED = {
    "Naloxone (0.4 mg IV or IM) should be available",                     # 1 fentanyl PFC IV
    "High-risk medication (ID29 p.24). Naloxone (0.4 mg IV or IM)",       # 2 fentanyl infusion
    "The cited guideline states no cumulative maximum",                    # 3 39 entries
    "Ketamine is JTS ID39's FIRST-LINE induction agent; etomidate 0.3",    # 4 ketamine RSI adult
    "JTS ID39 paediatric column: pre-dose atropine IV/IO 0.02",           # 5 ketamine RSI peds
    "Pre-dose atropine IV/IO 0.02",                                        # 6 succinylcholine peds
    "JTS ID39 adult RSI pathway. Alternatives listed alongside: vecuronium 0.1",  # 7 rocuronium
    "JTS ID39 does not list propofol as an RSI induction agent",           # 8 propofol
}


def _breaking_cautions():
    """(owner drug, caution text) for every caution that states a dose of
    another drug: a drug name followed, within the clause, by a dose."""
    bank = json.loads(CONTRACTS.read_text())
    found = set()
    for drug in bank["drugs"]:
        owner = drug["generic_name"]
        for entry in drug["dose_entries"]:
            for c in entry.get("cautions") or []:
                text = c.get("text", "") if isinstance(c, dict) else c
                for start, end, name in oc._drug_spans(text):
                    if name == owner:
                        continue
                    tail = text[end:end + 40]
                    if oc._FREE_DOSE_AMOUNT_RE.search(tail) or oc._FREE_DOSE_PER_KG_RE.search(tail):
                        found.add((owner, text))
    return found


def test_no_caution_breaks_the_rule_beyond_the_draft():
    texts = {t for _, t in _breaking_cautions()}
    undrafted = {t for t in texts if not any(t.startswith(p) for p in DRAFTED)}
    assert not undrafted, f"a caution states another drug's dose and is not in the draft: {undrafted}"


@pytest.mark.xfail(strict=True, reason="the drafted caution edits await the owner's signature "
                                       "(docs/authoring/CAUTION_DOSE_EDITS_2026-10-11.md)")
def test_no_caution_states_another_drugs_dose():
    assert not _breaking_cautions()
