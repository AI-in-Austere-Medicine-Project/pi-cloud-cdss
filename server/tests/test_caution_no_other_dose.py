"""A caution never states another drug's dose (owner, 2026-10-11).

A served caution is in the ALLOWED_DOSES block the generator reads, and the
generator copies it. Only the asked drug's doses are built for a question, so
a copied dose of another drug is held, even where that drug has a signed
entry: edgecdss-v3's B1 answer copied fentanyl's "Naloxone (0.4 mg IV or IM)"
and was held for it (found in A25).

The edits that brought the bank to the rule are in
docs/authoring/CAUTION_DOSE_EDITS_2026-10-11.md: 1, 2, 3, 4, 7 and 8 signed
and applied on 2026-10-11 (#155); 5 and 6 signed the same day with the atropine
paediatric RSI pre-dose entry (JTS ID39 p.28), which now carries that dose.
"""
import json
import pathlib

import openai_client as oc

CONTRACTS = pathlib.Path(oc.__file__).parent / "drug_contracts.json"

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


def test_no_caution_states_another_drugs_dose():
    assert not _breaking_cautions(), _breaking_cautions()
