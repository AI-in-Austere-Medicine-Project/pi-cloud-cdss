"""Signing batch 2, sedation and antibiotics (owner, 2026-10-16): draft the
entries the bank holds open for midazolam sedation, rocuronium redose, ketamine
sedation infusion, cefazolin and ceftriaxone. Not signed.

The owner's rules for each draft, as in batch 1:

- proposed dose, route, maximum and repeat;
- a verbatim quote and the printed page for every figure;
- flagged where the sources disagree (SOURCE_CONFLICT, with a conflict group)
  or where no JTS/SMOG page states the number (incomplete, never guessed).

Two entries are split by population, because the sources dose children
differently: ketamine's sedation infusion (SMOG's paediatric range tops out at
1 mg/kg/hr, below ID61's adult start) and rocuronium's redose (SMOG's
paediatric column has no infusion and no PRN).

The verbatim check reads the PDFs, which are not in the repository. Point
JTS_PDF_DIR at the JTS/SMOG corpus; without it that test skips.
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

MIDAZ_PROC = "procedural sedation"
MIDAZ_VENT = "sedation infusion for the ventilated patient"
ROC_REDOSE = "redose interval"
KET_INFUSION = "prolonged sedation infusion"
CEFAZ = "open fracture / wound prophylaxis"
CEFTRI = "severe bacterial infection / sepsis"

# (drug, indication, population, route): every entry this batch drafts.
DRAFTS = [
    ("midazolam", MIDAZ_PROC, "adult", "IV"),
    ("midazolam", MIDAZ_VENT, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "peds", "IV"),
    ("ketamine", KET_INFUSION, "adult", "IV"),
    ("ketamine", KET_INFUSION, "peds", "IV"),
    ("cefazolin", CEFAZ, "adult", "IV"),
    ("cefazolin", CEFAZ, "peds", "IV"),
    ("ceftriaxone", CEFTRI, "adult", "IV"),
    ("ceftriaxone", CEFTRI, "peds", "IV"),
]

# Where the sources disagree: the conflict is written out, not settled.
CONFLICTS = {
    ("midazolam", MIDAZ_PROC, "adult", "IV"): "midazolam-procedural-sedation-adult",
    ("midazolam", MIDAZ_VENT, "adult", "IV"): "midazolam-ventilated-infusion-adult",
    ("ketamine", KET_INFUSION, "adult", "IV"): "ketamine-sedation-infusion-rate",
    ("cefazolin", CEFAZ, "adult", "IV"): "cefazolin-weight-band",
    ("ceftriaxone", CEFTRI, "adult", "IV"): "ceftriaxone-sepsis-administration",
}

# No JTS/SMOG page states the dose: the entry stays marked incomplete.
INCOMPLETE = [
    ("ceftriaxone", CEFTRI, "peds", "IV"),
]

# A figure some source states only partly: the entry carries the dose, and the
# missing part is a NEEDS_MANUAL_ENTRY caution, so it cannot be signed as is.
PARTLY_STATED = {
    ("midazolam", MIDAZ_VENT, "adult", "IV"): ("titration step", "mix"),
    ("ketamine", KET_INFUSION, "peds", "IV"): ("starting rate", "mix"),
}


def _bank():
    return json.loads((SERVER / "drug_contracts.json").read_text())


def _drug(name):
    return next(d for d in _bank()["drugs"] if d["generic_name"] == name)


def _entry(drug, indication, population, route):
    d = _drug(drug)
    hits = [e for e in d["dose_entries"]
            if (e["indication"], e["population"], e["route"]) == (indication, population, route)]
    assert len(hits) == 1, (drug, indication, population, route, len(hits))
    return hits[0], d


_ids = lambda k: "-".join(k[::2]) + "-" + k[1][:14]


@pytest.mark.parametrize("key", DRAFTS, ids=_ids)
def test_nothing_in_this_batch_is_signed_or_servable(key):
    e, d = _entry(*key)
    assert e["signoff"] is False
    assert e["reviewed_by"] == "PENDING_CLINICAL_SIGNOFF"
    assert not drug_contracts.entry_is_servable(e, d)[0]


@pytest.mark.parametrize("drug,indication", [("ketamine", KET_INFUSION), ("rocuronium", ROC_REDOSE)])
def test_the_split_entries_no_longer_serve_both_populations(drug, indication):
    pops = sorted(e["population"] for e in _drug(drug)["dose_entries"] if e["indication"] == indication)
    assert pops == ["adult", "peds"], pops


@pytest.mark.parametrize("key", DRAFTS, ids=_ids)
def test_every_source_carries_a_guideline_a_printed_page_and_a_quote(key):
    e, _ = _entry(*key)
    assert e["sources"]
    for s in e["sources"]:
        assert re.search(r"CPG ID\d+", s["citation"]) or "SMOG" in s["citation"], s["citation"]
        assert isinstance(s.get("page"), int) and s["page"] > 0, s
        assert isinstance(s.get("pdf_page"), int) and s["pdf_page"] > 0, s
        assert f"p.{s['page']}" in s["citation"], s["citation"]
        assert s.get("quote", "").strip(), s
        assert s.get("supports"), s


def _figures(x):
    vals = (x["min"], x["max"]) if isinstance(x, dict) and "min" in x else \
           ((x["value"],) if isinstance(x, dict) and "value" in x else ())
    return {float(v) for v in vals}


@pytest.mark.parametrize("key", [k for k in DRAFTS if k not in INCOMPLETE], ids=_ids)
def test_every_dose_figure_is_in_a_quote(key):
    e, _ = _entry(*key)
    quotes = " ".join(s["quote"] for s in e["sources"]).replace(",", "")
    numbers = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", quotes)}
    for field in ("dose_range", "max_single", "max_cumulative"):
        for fig in _figures(e.get(field)):
            assert fig in numbers, (field, fig, key)


@pytest.mark.parametrize("key", INCOMPLETE, ids=_ids)
def test_what_no_source_states_stays_marked_incomplete(key):
    e, _ = _entry(*key)
    assert e["dose_range"] == drug_contracts.NEEDS_MANUAL
    assert "DOSE_NOT_IN_SOURCE" in e["flags"]


@pytest.mark.parametrize("key", list(PARTLY_STATED), ids=_ids)
def test_a_figure_no_source_states_is_a_needs_manual_entry_caution(key):
    e, _ = _entry(*key)
    texts = [c if isinstance(c, str) else c["text"] for c in e["cautions"]]
    for what in PARTLY_STATED[key]:
        assert any(drug_contracts.NEEDS_MANUAL in t and what in t for t in texts), (key, what)


@pytest.mark.parametrize("key", list(CONFLICTS), ids=_ids)
def test_a_conflict_is_flagged_grouped_and_written_out(key):
    e, _ = _entry(*key)
    assert "SOURCE_CONFLICT" in e["flags"]
    assert e["conflict_group"] == CONFLICTS[key]
    assert "CONFLICT" in e["extraction_notes"]


def test_the_ketamine_start_rate_is_the_highlighted_row_and_stays_visual():
    """ID61 Appendix B marks the start by shading a row. Rendered, the shaded
    row is 1.5 mg/kg/h, which is also what the dial-flow rule (weight / 2 mL/h
    at 3 mg/mL) gives. The shading is not in the text layer, so the flag stays."""
    e, _ = _entry("ketamine", KET_INFUSION, "adult", "IV")
    assert "NEEDS_VISUAL_CONFIRMATION" in e["flags"]
    texts = " ".join(c if isinstance(c, str) else c["text"] for c in e["cautions"])
    assert "1.5 mg/kg/h" in texts and "highlight" in texts
    assert any("weight in kg divided by 2" in s["quote"] for s in e["sources"])


def test_the_rocuronium_redose_says_smog_calls_it_unreferenced():
    for pop in ("adult", "peds"):
        e, _ = _entry("rocuronium", ROC_REDOSE, pop, "IV")
        assert all(s["source_class"] == "SMOG" for s in e["sources"] if "Dose and Administration" in s["citation"])
        assert any("unlabeled and unreferenced" in s["quote"] for s in e["sources"])
        assert "SINGLE_SOURCE_UNREFERENCED" in e["flags"]


def test_no_caution_states_another_drugs_dose():
    """A caution is served text, and the gate reads served text: another drug's
    dose in it would be a dose with no signed entry behind it."""
    names = {d["generic_name"] for d in _bank()["drugs"]}
    for key in DRAFTS:
        e, _ = _entry(*key)
        for c in e["cautions"]:
            t = (c if isinstance(c, str) else c["text"]).lower()
            for other in names - {key[0]}:
                m = re.search(rf"\b{re.escape(other)}\b[^.;]*?\d\s*(?:mg|g|mcg)\b", t)
                assert not m, (key, other, t)


def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


def _page_texts(pdf, page):
    """The page as text, whole and one half-page column at a time: SMOG prints
    ADULT and PEDIATRIC side by side, and a whole-page extraction interleaves them."""
    run = lambda *a: subprocess.run(["pdftotext", *a, "-f", str(page), "-l", str(page), str(pdf), "-"],
                                    capture_output=True, text=True, check=True).stdout
    width, height = 612, 792
    info = subprocess.run(["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)],
                          capture_output=True, text=True).stdout
    m = re.search(rf"Page\s+{page} size:\s+([\d.]+) x ([\d.]+)", info)
    if m:
        width, height = int(float(m[1])), int(float(m[2]))
    half = width // 2
    texts = [run("-layout"), run()]
    for x in (0, half):
        crop = ["-x", str(x), "-y", "0", "-W", str(half), "-H", str(height)]
        texts += [run(*crop), run("-layout", *crop)]
    return [_norm(t) for t in texts]


@pytest.mark.skipif(shutil.which("pdftotext") is None or not PDF_DIR.is_dir(),
                    reason="the source PDFs (JTS_PDF_DIR) or pdftotext are not available")
@pytest.mark.parametrize("key", DRAFTS, ids=_ids)
def test_every_quote_is_verbatim_on_its_cited_page(key):
    e, _ = _entry(*key)
    for s in e["sources"]:
        texts = _page_texts(PDF_DIR / s["url"].split("/")[-1], s["pdf_page"])
        for part in s["quote"].replace(" [sic]", "").split(" … "):
            assert any(_norm(part) in t for t in texts), (key, s["citation"], part)
