"""A caution never states another drug's dose (owner, 2026-10-11).

A served caution is in the ALLOWED_DOSES block the generator reads, and the
generator copies it. Only the asked drug's doses are built for a question, so
a copied dose of another drug is held, even where that drug has a signed
entry: edgecdss-v3's B1 answer copied fentanyl's "Naloxone (0.4 mg IV or IM)"
and was held for it (found in A25).

The edits that bring the bank to the rule are in
docs/authoring/CAUTION_DOSE_EDITS_2026-10-11.md. The owner signed 1, 2, 3, 4,
7 and 8 (applied 2026-10-11); 5 and 6 are signed with an atropine RSI
pre-dose entry. Until then the rule is an expected failure, and the two
remaining cautions are pinned so no new one is added meanwhile.
"""
import json
import pathlib

import pytest

import openai_client as oc

CONTRACTS = pathlib.Path(oc.__file__).parent / "drug_contracts.json"

# Edits 1, 2, 3, 4, 7 and 8 were signed by the owner and applied on
# 2026-10-11. Edits 5 and 6 (the paediatric RSI atropine pre-dose) stay
# unsigned until an atropine RSI pre-dose entry is signed with them.
DRAFTED = {
    "JTS ID39 paediatric column: pre-dose atropine IV/IO 0.02",           # 5 ketamine RSI peds
    "Pre-dose atropine IV/IO 0.02",                                        # 6 succinylcholine peds
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


@pytest.mark.xfail(strict=True, reason="edits 5 and 6 await an atropine RSI pre-dose entry and the owner's "
                                       "signature (docs/authoring/CAUTION_DOSE_EDITS_2026-10-11.md)")
def test_no_caution_states_another_drugs_dose():
    assert not _breaking_cautions()
