"""Contract batch 1, analgesia (owner, 2026-10-08): drafted from the unsigned
inventory (docs/UNSIGNED_CONTRACTS_2026-10-08.md), not signed.

Of the 40 unsigned drug entries, one is analgesia: fentanyl, analgesia
infusion, IV, adult. Ketamine analgesia and morphine are already signed. The
owner's rules for the draft:

- every dose line carries a verbatim quote with its CPG ID and page;
- the dose is specific to the indication;
- anything that can't be cited verbatim stays marked incomplete.

Signing is the owner's act: the draft ships with signoff false and is not servable.

The verbatim check reads the PDFs, which are not in the repository
(data/ is gitignored). Point JTS_PDF_DIR at them; without them that test skips.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

import drug_contracts

SERVER = pathlib.Path(__file__).resolve().parents[1]
PDF_DIR = pathlib.Path(os.environ.get("JTS_PDF_DIR", SERVER / "data/jts_protocols"))


def _entry():
    bank = json.loads((SERVER / "drug_contracts.json").read_text())
    drug = next(d for d in bank["drugs"] if d["generic_name"] == "fentanyl")
    return next(e for e in drug["dose_entries"] if e["indication"] == "analgesia infusion"), drug


def test_the_draft_is_a_rate_from_the_jts_icu_order_set():
    e, _ = _entry()
    assert e["dose_range"] == {"min": 25.0, "max": 250.0, "units": "mcg/hr", "per_kg": False}
    assert drug_contracts.classify_units("mcg/hr", False)[0] == drug_contracts.RATE


def test_every_source_carries_a_cpg_id_a_page_and_a_verbatim_quote():
    e, _ = _entry()
    assert e["sources"]
    for s in e["sources"]:
        assert re.search(r"CPG ID\d+", s["citation"]) or "SMOG" in s["citation"], s
        assert isinstance(s.get("page"), int) and s["page"] > 0, s
        assert s.get("quote", "").strip(), s
        assert s.get("supports"), s


def test_every_dose_figure_in_the_entry_is_in_a_quote():
    e, _ = _entry()
    quotes = " ".join(s["quote"] for s in e["sources"])
    assert "25-250 mcg/hr" in quotes and "250 mcg/hr" in quotes
    for c in e["cautions"]:
        text = c["text"] if isinstance(c, dict) else c
        for n in re.findall(r"\d+(?:-\d+)?\s*mcg", text):
            assert n.replace(" ", "") in quotes.replace(" ", ""), (n, text)


def test_what_no_source_states_stays_marked_incomplete():
    e, _ = _entry()
    assert "NEEDS_MANUAL_ENTRY" in json.dumps(e)
    assert "STARTING_RATE_NOT_IN_SOURCE" in e["flags"]


def test_the_draft_is_unsigned_and_not_servable():
    e, drug = _entry()
    assert e["signoff"] is False
    assert e["reviewed_by"] == "PENDING_CLINICAL_SIGNOFF"
    ok, _why = drug_contracts.entry_is_servable(e, drug)
    assert not ok


def test_the_canine_page_is_not_a_source():
    e, _ = _entry()
    text = json.dumps(e)
    assert "MWD" not in [s.get("source_class") for s in e["sources"]]
    assert "2-10 mcg/kg" not in " ".join(s["quote"] for s in e["sources"])
    assert "ID16" not in " ".join(s["citation"] for s in e["sources"]), text


def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


@pytest.mark.skipif(shutil.which("pdftotext") is None or not PDF_DIR.is_dir(),
                    reason="the JTS PDFs (JTS_PDF_DIR) or pdftotext are not available")
def test_every_quote_is_verbatim_on_its_cited_page():
    e, _ = _entry()
    for s in e["sources"]:
        pdf = PDF_DIR / s["url"].split("/")[-1]
        page = subprocess.run(["pdftotext", "-layout", "-f", str(s["pdf_page"]), "-l", str(s["pdf_page"]),
                               str(pdf), "-"], capture_output=True, text=True, check=True).stdout
        for part in s["quote"].split(" … "):
            assert _norm(part) in _norm(page), (s["citation"], part)
