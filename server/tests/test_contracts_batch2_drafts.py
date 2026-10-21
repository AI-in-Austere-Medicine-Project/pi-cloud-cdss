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

Ruled 2026-10-19 (owner, Andrew Azelton, signer). Signed by AI-AIM for him:
midazolam 1-4 mg as a ketamine add-on (ID61 p.9); ketamine sedation infusion,
adult, start 1.5 mg/kg/h in 0.5-2.0 (ID61 p.9, the shaded row confirmed by the
owner on the page); cefazolin adult flat 2 g, max 12 g/day (ID24 p.11), not the
weight bands; cefazolin paediatric 20-30 mg/kg (ID24 p.12), 100 mg/kg/day as a
WATCH warning; ceftriaxone adult 2 g q24h (ID91 p.40, ID83 p.8 noted), the
infusion speed in WATCH only, relabelled "sepsis". Not signed: the SMOG sides of
the two closed conflicts, the midazolam ventilated infusion (v1.1), the
rocuronium redose (the source calls it unreferenced), the paediatric ketamine
infusion (v1.1) and paediatric ceftriaxone (no dose in any source).

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
CEFTRI = "sepsis"  # relabelled from "severe bacterial infection / sepsis" (owner, 2026-10-19)
MIDAZ_PROC_SMOG = "procedural sedation — SMOG (pacing / cardioversion)"
MIDAZ_VENT_FIXED = "sedation infusion for the ventilated patient — ICU order set (fixed rate)"
KET_INFUSION_SMOG = "prolonged sedation infusion — SMOG (en route)"

# (drug, indication, population, route): every entry this batch drafts.
DRAFTS = [
    ("midazolam", MIDAZ_PROC, "adult", "IV"),
    ("midazolam", MIDAZ_PROC_SMOG, "adult", "IV"),
    ("midazolam", MIDAZ_VENT, "adult", "IV"),
    ("midazolam", MIDAZ_VENT_FIXED, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "peds", "IV"),
    ("ketamine", KET_INFUSION, "adult", "IV"),
    ("ketamine", KET_INFUSION_SMOG, "adult", "IV"),
    ("ketamine", KET_INFUSION, "peds", "IV"),
    ("cefazolin", CEFAZ, "adult", "IV"),
    ("cefazolin", CEFAZ, "peds", "IV"),
    ("ceftriaxone", CEFTRI, "adult", "IV"),
    ("ceftriaxone", CEFTRI, "peds", "IV"),
]

RULING = "OWNER RULING 2026-10-19 (Andrew Azelton)"

# Owner rulings, 2026-10-19: signed as ruled, by AI-AIM for Andrew Azelton.
SIGNED = [
    ("midazolam", MIDAZ_PROC, "adult", "IV"),
    ("ketamine", KET_INFUSION, "adult", "IV"),
    ("cefazolin", CEFAZ, "adult", "IV"),
    ("cefazolin", CEFAZ, "peds", "IV"),
    ("ceftriaxone", CEFTRI, "adult", "IV"),
]

# Where the sources disagreed on the dose: both sides were kept as entries, as
# in batch 1. Two groups are ruled and closed: the flag and group are gone and
# each side carries the owner's adjudication.
CLOSED_CONFLICTS = {
    ("midazolam", MIDAZ_PROC, "adult", "IV"): "midazolam-procedural-sedation-adult",
    ("midazolam", MIDAZ_PROC_SMOG, "adult", "IV"): "midazolam-procedural-sedation-adult",
    ("ketamine", KET_INFUSION, "adult", "IV"): "ketamine-sedation-infusion-rate",
    ("ketamine", KET_INFUSION_SMOG, "adult", "IV"): "ketamine-sedation-infusion-rate",
}
# Neither side signed (v1.1: no source gives a start rate or titration), so
# the group stays open.
OPEN_CONFLICTS = {
    ("midazolam", MIDAZ_VENT, "adult", "IV"): "midazolam-ventilated-infusion-adult",
    ("midazolam", MIDAZ_VENT_FIXED, "adult", "IV"): "midazolam-ventilated-infusion-adult",
}

# Left unsigned by the ruling, and why. v1.1 entries say so.
HELD = {
    ("midazolam", MIDAZ_PROC_SMOG, "adult", "IV"): "not signed",
    ("midazolam", MIDAZ_VENT, "adult", "IV"): "v1.1",
    ("midazolam", MIDAZ_VENT_FIXED, "adult", "IV"): "v1.1",
    ("rocuronium", ROC_REDOSE, "adult", "IV"): "unreferenced",
    ("rocuronium", ROC_REDOSE, "peds", "IV"): "unreferenced",
    ("ketamine", KET_INFUSION_SMOG, "adult", "IV"): "not signed",
    ("ketamine", KET_INFUSION, "peds", "IV"): "v1.1",
    ("ceftriaxone", CEFTRI, "peds", "IV"): "cannot be signed",
}

# No JTS/SMOG page states the dose: the entry stays marked incomplete.
INCOMPLETE = [
    ("ceftriaxone", CEFTRI, "peds", "IV"),
]

# A figure some source states only partly: the entry carries the dose, and the
# missing part is a NEEDS_MANUAL_ENTRY caution, so it cannot be signed as is.
PARTLY_STATED = {
    ("midazolam", MIDAZ_VENT, "adult", "IV"): ("titration step", "mix"),
    ("midazolam", MIDAZ_VENT_FIXED, "adult", "IV"): ("starting rate",),
    ("ketamine", KET_INFUSION, "peds", "IV"): ("starting rate", "mix"),
}


# Signing batch 3 (owner, 2026-10-21) moved five of these on. Retired: the
# SMOG ketamine infusion (E01), the rocuronium redose in both populations (E07,
# E08) and paediatric ceftriaxone (E12). Relabelled and signed: the SMOG
# midazolam procedural sedation (E13), now "procedural sedation for pacing /
# cardioversion", pinned in test_signing_batch3_rulings.py. The tests below
# cover what batch 2 left in the bank.
RETIRED_IN_BATCH_3 = [
    ("ketamine", KET_INFUSION_SMOG, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "adult", "IV"),
    ("rocuronium", ROC_REDOSE, "peds", "IV"),
    ("ceftriaxone", CEFTRI, "peds", "IV"),
]
MOVED_ON = RETIRED_IN_BATCH_3 + [("midazolam", MIDAZ_PROC_SMOG, "adult", "IV")]
LIVE = [k for k in DRAFTS if k not in MOVED_ON]


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


def _texts(e, tier=None):
    out = []
    for c in e["cautions"]:
        t, ct = (c, "serve") if isinstance(c, str) else (c["text"], c.get("tier", "serve"))
        if tier is None or ct == tier:
            out.append(t)
    return out


@pytest.mark.parametrize("key", LIVE, ids=_ids)
def test_only_the_ruled_entries_are_signed_and_servable(key):
    e, d = _entry(*key)
    ok, why = drug_contracts.entry_is_servable(e, d)
    if key in SIGNED:
        assert e["signoff"] is True and e["reviewed_by"] == "AI-AIM" and e["review_date"] == "2026-10-19"
        assert not e["version"].endswith("-draft")
        assert ok, why
    else:
        assert e["signoff"] is False
        assert e["reviewed_by"] == "PENDING_CLINICAL_SIGNOFF"
        assert not ok


@pytest.mark.parametrize("key", LIVE, ids=_ids)
def test_every_entry_carries_the_owners_ruling(key):
    e, _ = _entry(*key)
    assert e["adjudication"].startswith(RULING), e.get("adjudication")
    assert e["adjudicated_on"] == "2026-10-19"
    if key in HELD:
        assert HELD[key] in e["adjudication"], (key, e["adjudication"])


@pytest.mark.parametrize("drug,indication", [("ketamine", KET_INFUSION), ("rocuronium", ROC_REDOSE)])
def test_the_split_entries_no_longer_serve_both_populations(drug, indication):
    pops = sorted(e["population"] for e in _drug(drug)["dose_entries"] if e["indication"] == indication)
    retired = sorted(r["population"] for r in _bank()["retired_entries"]
                     if (r["generic_name"], r["indication"]) == (drug, indication))
    # The rocuronium redose was retired in both populations (batch 3).
    assert sorted(pops + retired) == ["adult", "peds"], (pops, retired)


@pytest.mark.parametrize("key", LIVE, ids=_ids)
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


@pytest.mark.parametrize("key", [k for k in LIVE if k not in INCOMPLETE], ids=_ids)
def test_every_dose_figure_is_in_a_quote(key):
    e, _ = _entry(*key)
    quotes = " ".join(s["quote"] for s in e["sources"]).replace(",", "")
    numbers = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", quotes)}
    for field in ("dose_range", "max_single", "max_cumulative"):
        for fig in _figures(e.get(field)):
            assert fig in numbers, (field, fig, key)


@pytest.mark.parametrize("key", [k for k in INCOMPLETE if k in LIVE], ids=_ids)
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


@pytest.mark.parametrize("key", [k for k in CLOSED_CONFLICTS if k in LIVE], ids=_ids)
def test_a_ruled_conflict_is_closed_with_the_owners_adjudication(key):
    e, _ = _entry(*key)
    assert "SOURCE_CONFLICT" not in e["flags"] and "conflict_group" not in e
    assert CLOSED_CONFLICTS[key] in e["extraction_notes"] and "closed 2026-10-19" in e["extraction_notes"]
    assert "CONFLICT" in e["extraction_notes"]


@pytest.mark.parametrize("key", list(OPEN_CONFLICTS), ids=_ids)
def test_the_unsigned_conflict_stays_flagged_and_grouped(key):
    e, _ = _entry(*key)
    assert "SOURCE_CONFLICT" in e["flags"]
    assert e["conflict_group"] == OPEN_CONFLICTS[key]
    assert "CONFLICT" in e["extraction_notes"]


def test_the_ketamine_start_rate_is_the_shaded_row_the_owner_confirmed():
    """ID61 Appendix B marks the start by shading a row. Rendered, the shaded
    row is 1.5 mg/kg/h, which is also what the dial-flow rule (weight / 2 mL/h
    at 3 mg/mL) gives. The owner looked at the page (2026-10-19): the flag is
    cleared, and the start is served with the signed 0.5-2.0 band."""
    e, _ = _entry("ketamine", KET_INFUSION, "adult", "IV")
    assert "NEEDS_VISUAL_CONFIRMATION" not in e["flags"]
    assert e["dose_range"] == {"min": 0.5, "max": 2.0, "units": "mg/kg/hr", "per_kg": True}
    assert any("1.5 mg/kg/h" in t for t in _texts(e, "serve"))
    assert "owner confirmed the shaded row" in e["extraction_notes"]
    assert any("weight in kg divided by 2" in s["quote"] for s in e["sources"])


def test_cefazolin_adult_is_the_flat_2_g_not_the_weight_bands():
    e, _ = _entry("cefazolin", CEFAZ, "adult", "IV")
    assert e["dose_range"] == {"min": 2.0, "max": 2.0, "units": "g", "per_kg": False}
    assert e["max_cumulative"]["value"] == 12.0 and e["max_cumulative"]["units"] == "g"
    assert e["sources"][0]["page"] == 11 and "CPG ID24" in e["sources"][0]["citation"]
    assert "WEIGHT_BAND_OPTION_IN_SOURCE" not in e["flags"]
    # The bands are kept for the record, never served: 1 g and 3 g would be
    # cefazolin doses the medic is shown beside the signed one.
    assert not any("160 kg" in t for t in _texts(e, "serve"))
    assert any("160 kg" in t for t in _texts(e, "detail"))


def test_cefazolin_peds_daily_maximum_is_a_watch_warning():
    e, _ = _entry("cefazolin", CEFAZ, "peds", "IV")
    assert e["dose_range"] == {"min": 20.0, "max": 30.0, "units": "mg/kg", "per_kg": True}
    assert e["max_cumulative"] is None
    assert any("100 mg/kg/day" in t for t in _texts(e, "serve"))
    assert e["sources"][0]["page"] == 12 and "CPG ID24" in e["sources"][0]["citation"]


def test_ceftriaxone_adult_is_sepsis_2_g_q24h_with_the_speed_in_watch_only():
    e, _ = _entry("ceftriaxone", CEFTRI, "adult", "IV")
    assert e["dose_range"] == {"min": 2.0, "max": 2.0, "units": "g", "per_kg": False}
    assert "CPG ID91" in e["sources"][0]["citation"] and e["sources"][0]["page"] == 40
    assert any("CPG ID83" in s["citation"] and s["page"] == 8 for s in e["sources"])
    assert "ADMINISTRATION_TIME_DIFFERS" not in e["flags"]
    serve = _texts(e, "serve")
    assert any("24 hours" in t for t in serve)
    assert any("10 minutes" in t and "30 minutes" in t for t in serve)
    assert not any(e2["indication"] == "severe bacterial infection / sepsis"
                   for e2 in _drug("ceftriaxone")["dose_entries"])


V11_ITEMS = [
    "cefazolin · penetrating brain injury",
    "cefazolin · penetrating spinal cord injury",
    "cefazolin · penetrating chest, maxillofacial",
    "cefazolin · single pre-surgical dose",
    "cefazolin · ventriculostomy",
    "ceftriaxone · penetrating TBI · adult",
    "ceftriaxone · penetrating TBI · peds",
    "ceftriaxone · severe pneumonia",
    "midazolam · procedural sedation · peds · IV",
    "midazolam · procedural sedation · peds · IN",
    "midazolam · post-intubation bolus",
    "midazolam · sedation / anxiolysis · adult · IM",
    "midazolam · active seizure",
    "vancomycin",
]


def test_the_undrafted_indications_and_discrepancies_are_v1_1_items():
    doc = (SERVER.parent / "docs/UNSIGNED_CONTRACTS_2026-10-08.md").read_text()
    assert "## v1.1 items from signing batch 2" in doc
    section = doc.split("## v1.1 items from signing batch 2", 1)[1]
    for item in V11_ITEMS:
        assert item in section, item


def test_the_rocuronium_redose_says_smog_calls_it_unreferenced():
    """Retired in batch 3 (owner, 2026-10-21) for the reason batch 2 held it."""
    for pop in ("adult", "peds"):
        rec = [r for r in _bank()["retired_entries"]
               if (r["generic_name"], r["indication"], r["population"]) == ("rocuronium", ROC_REDOSE, pop)]
        assert len(rec) == 1 and "unreferenced" in rec[0]["retired_reason"], rec


def test_no_caution_states_another_drugs_dose():
    """A caution is served text, and the gate reads served text: another drug's
    dose in it would be a dose with no signed entry behind it."""
    names = {d["generic_name"] for d in _bank()["drugs"]}
    for key in LIVE:
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
@pytest.mark.parametrize("key", LIVE, ids=_ids)
def test_every_quote_is_verbatim_on_its_cited_page(key):
    e, _ = _entry(*key)
    for s in e["sources"]:
        texts = _page_texts(PDF_DIR / s["url"].split("/")[-1], s["pdf_page"])
        for part in s["quote"].replace(" [sic]", "").split(" … "):
            assert any(_norm(part) in t for t in texts), (key, s["citation"], part)
