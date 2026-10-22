"""5.1.0 docs: SAFETY.md, README and REFERENCE state the release as it is.

Owner, 2026-10-22 (v5.1.0 freeze, last item): "SAFETY.md, README and REFERENCE
for 5.1.0 including the cited-in-code non-drug numbers." The counts are read
from the bank, so a doc that drifts from it fails.

    cd server && ./run_unit_tests.sh
"""
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-offline")

import drug_contracts as dc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SAFETY = (ROOT / "SAFETY.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
REFERENCE = (ROOT / "docs" / "REFERENCE.md").read_text(encoding="utf-8")
RAW = json.load(open(Path(dc.__file__).with_name("drug_contracts.json"), encoding="utf-8"))
TOTAL = sum(len(d.get("dose_entries", [])) for d in RAW["drugs"])
LIVE = sum(len(v) for v in dc.servable_entries().values())
RETIRED = len(RAW.get("retired_entries", []))


def test_safety_names_the_release():
    assert "EdgeCDSS 5.1.0" in SAFETY


def test_readme_names_the_release():
    assert "**Current release: 5.1.0**" in README
    assert "## What's new in 5.1" in README


@pytest.mark.parametrize("doc", ["SAFETY", "README"])
def test_the_entry_counts_are_the_banks(doc):
    text = {"SAFETY": SAFETY, "README": README}[doc]
    assert f"{LIVE} of {TOTAL}" in text, (LIVE, TOTAL)
    assert f"{RETIRED} retired" in text, RETIRED
    assert f"{TOTAL - LIVE} contract entries" in text or doc == "README"


@pytest.mark.parametrize("guarantee", [
    "stated indication",          # A32
    "stated route",               # A34
    "names no drug",              # A18 / A33
    "highest signed",             # A36
    "no calculator",              # A35
    "available route",            # A38
    "pacing or cardioversion",    # pacing match
])
def test_safety_states_the_new_guarantees(guarantee):
    assert guarantee in SAFETY, guarantee


@pytest.mark.parametrize("number", [
    # severe TBI card (ID30 / ID63 / SMOG, cited in code)
    "SBP above 110", "SpO2 above 93%", "EtCO2 35-45", "30-45°", "GCS 8 or less",
    "70 + 2 x age", "no more than 20 minutes",
    # ketamine analgesia card; DCR card
    "q5min", "TXA within 3 hours of injury",
    # pain-severity question
    "NRS 1–3",
    # vitals cautions (vitals_rules.json)
    "SBP < 90", "MAP < 65", "RR < 10", "SpO2 < 90", "HR < 50", "glucose < 70",
    # volume limits; IBW constants; vent cards
    "0.05 mL", "60 mL", "Devine", "\"clinician\"",
])
def test_safety_lists_the_cited_in_code_numbers(number):
    section = SAFETY.split("## Numbers in code that no signature covers")[1].split("\n## ")[0]
    assert number in section, number


@pytest.mark.parametrize("row", ["| A35 |", "| A36 |", "| A37 |", "| A38 |",
                                 "Pacing match", "E05 relabel", "Vent card settings",
                                 "Release 5.1.0"])
def test_reference_carries_every_5_1_item(row):
    assert row in REFERENCE, row
