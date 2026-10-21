"""Signing batch 1, analgesia (owner, 2026-10-14): draft every analgesia entry
the bank lacks for ketamine (IV/IM/IN, adult and paediatric), fentanyl (IV,
IN), morphine, acetaminophen and ketorolac. Not signed.

The owner's rules for each draft:

- a verbatim quote, the CPG ID (or the named guideline), the printed page;
- indication, population and route stated;
- anything that can't be quoted verbatim stays marked incomplete.

What was already in the bank and is left alone: ketamine IV analgesia (signed),
fentanyl IV paediatric, IN and the adult JTS fixed dose (signed), the adult
fentanyl IV per-kg entries (retired by the owner, 2026-09-24), morphine adult
IV and IM and paediatric IV (signed).

The verbatim check reads the PDFs, which are not in the repository. Point
JTS_PDF_DIR at the JTS/SMOG corpus and NASEMSO_PDF at the NASEMSO guideline;
without them that test skips.
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
NASEMSO_PDF = pathlib.Path(os.environ.get(
    "NASEMSO_PDF", SERVER.parent / "sources/National_Model_EMS_Clinical_Guidelines_Version_3.pdf"))

KETAMINE_PAIN = "moderate to severe pain / analgesia"
KETAMINE_PFC = "breakthrough pain — IM/IN (prolonged field care)"
APAP_PAIN = "mild to moderate pain / analgesia"
KETOROLAC_PAIN = "moderate to severe acute pain / analgesia"
KETOROLAC_SMOG = "moderate to severe acute pain / analgesia — SMOG weight-based"

# (drug, indication, population, route): every entry this batch drafts.
DRAFTS = [
    ("ketamine", KETAMINE_PAIN, "adult|peds", "IM"),
    ("ketamine", KETAMINE_PFC, "adult", "IM"),
    ("ketamine", KETAMINE_PFC, "adult", "IN"),
    ("ketamine", KETAMINE_PAIN, "peds", "IM"),
    ("ketamine", KETAMINE_PAIN, "peds", "IN"),
    ("morphine", "acute pain / analgesia", "peds", "IM"),
    ("acetaminophen", APAP_PAIN, "adult", "PO"),
    ("acetaminophen", APAP_PAIN, "adult", "IV"),
    ("acetaminophen", APAP_PAIN, "peds", "PO"),
    ("acetaminophen", APAP_PAIN, "peds", "IV"),
    ("ketorolac", KETOROLAC_PAIN, "adult", "IM"),
    ("ketorolac", KETOROLAC_PAIN, "adult", "IV"),
    ("ketorolac", KETOROLAC_PAIN, "peds", "IM"),
    ("ketorolac", KETOROLAC_PAIN, "peds", "IV"),
    ("ketorolac", KETOROLAC_SMOG, "peds", "IM"),
]

# Where the sources disagreed on the dose: both sides were kept as entries and
# the conflict written out. Ruled 2026-10-14: the flag and group are gone and
# each side carries the owner's adjudication.
CONFLICTS = {
    ("ketamine", KETAMINE_PAIN, "adult|peds", "IM"): "ketamine-im-analgesia",
    ("ketamine", KETAMINE_PFC, "adult", "IM"): "ketamine-im-analgesia",
    ("ketamine", KETAMINE_PAIN, "peds", "IM"): "ketamine-im-analgesia",
    ("ketorolac", KETOROLAC_PAIN, "peds", "IM"): "ketorolac-im-analgesia-peds",
    ("ketorolac", KETOROLAC_SMOG, "peds", "IM"): "ketorolac-im-analgesia-peds",
}

# No source states a dose: the entry exists, marked incomplete.
INCOMPLETE = [
    ("ketamine", KETAMINE_PAIN, "peds", "IN"),
]


# Signing batch 3 (owner, 2026-10-21) retired two of these: the NASEMSO
# adult|peds IM side (E03; batch 1's signed adult and paediatric IM entries
# cover it) and paediatric IN (E04; no JTS or SMOG number). The tests below
# cover what batch 1 left in the bank.
RETIRED_IN_BATCH_3 = [
    ("ketamine", KETAMINE_PAIN, "adult|peds", "IM"),
    ("ketamine", KETAMINE_PAIN, "peds", "IN"),
]
LIVE = [k for k in DRAFTS if k not in RETIRED_IN_BATCH_3]


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


# Owner rulings, 2026-10-14: signed as drafted, by AI-AIM for Andrew Azelton.
SIGNED = [
    ("ketamine", KETAMINE_PFC, "adult", "IM"),      # redrafted to 0.5-1.0 mg/kg, read, then signed
    ("ketamine", KETAMINE_PFC, "adult", "IN"),
    ("ketamine", KETAMINE_PAIN, "peds", "IM"),
    ("morphine", "acute pain / analgesia", "peds", "IM"),
    ("acetaminophen", APAP_PAIN, "adult", "PO"),
    ("acetaminophen", APAP_PAIN, "adult", "IV"),
    ("acetaminophen", APAP_PAIN, "peds", "PO"),
    ("acetaminophen", APAP_PAIN, "peds", "IV"),
]


@pytest.mark.parametrize("key", LIVE, ids=lambda k: "-".join(k[::2]) + "-" + k[1][:12])
def test_only_the_ruled_entries_are_signed_and_servable(key):
    e, d = _entry(*key)
    ok, why = drug_contracts.entry_is_servable(e, d)
    if key in SIGNED:
        assert e["signoff"] is True and e["reviewed_by"] == "AI-AIM" and e["review_date"] == "2026-10-14"
        assert ok, why
    else:
        assert e["signoff"] is False
        assert e["reviewed_by"] == "PENDING_CLINICAL_SIGNOFF"
        assert not ok


def test_the_im_ketamine_entry_is_the_ruled_range_with_the_tccc_maximum_checked():
    e, _ = _entry("ketamine", KETAMINE_PFC, "adult", "IM")
    assert e["dose_range"] == {"min": 0.5, "max": 1.0, "units": "mg/kg", "per_kg": True}
    assert e["sources"][0]["source_class"] == "SMOG" and "0.5 - 1.0 mg/kg" in e["sources"][0]["quote"]
    # Owner: add the TCCC maximum if stated. Neither TCCC-derived source states one.
    assert any("CPG ID91" in s["citation"] and "0.5-1 mg/kg" in s["quote"] for s in e["sources"])
    assert "TCCC MAXIMUM CHECKED" in e["extraction_notes"]
    # Owner, 2026-10-14: cap the single dose at 100 mg per ID91's stated 50-100 mg; repeat q20-30 min.
    assert e["max_single"]["value"] == 100.0 and e["max_single"]["units"] == "mg"
    assert any("every 20-30 minutes" in c for c in e["cautions"] if isinstance(c, str))


def test_nasemso_im_stays_unsigned_as_a_documented_alternate():
    """Left unsigned 2026-10-14; retired 2026-10-21 (batch 3, E03), once the
    owner confirmed batch 1's signed IM entries cover adults and children."""
    assert not [e for e in _drug("ketamine")["dose_entries"]
                if (e["indication"], e["population"], e["route"]) == (KETAMINE_PAIN, "adult|peds", "IM")]
    rec = [r for r in _bank()["retired_entries"]
           if (r["generic_name"], r["indication"], r["population"], r["route"])
           == ("ketamine", KETAMINE_PAIN, "adult|peds", "IM")]
    assert len(rec) == 1 and "batch 1" in rec[0]["retired_reason"], rec


def test_ketorolac_is_excluded_with_the_smog_quote():
    for e in _drug("ketorolac")["dose_entries"]:
        assert e["signoff"] is False
        assert "OWNER_EXCLUDED" in e["flags"]
        assert "Not for use as pain management for battlefield trauma patient!" in e["adjudication"]


@pytest.mark.parametrize("key", LIVE, ids=lambda k: "-".join(k[::2]) + "-" + k[1][:12])
def test_every_source_carries_a_guideline_a_printed_page_and_a_quote(key):
    e, _ = _entry(*key)
    assert e["sources"]
    for s in e["sources"]:
        assert (re.search(r"CPG ID\d+", s["citation"]) or "SMOG" in s["citation"]
                or "NASEMSO" in s["citation"]), s["citation"]
        assert isinstance(s.get("page"), int) and s["page"] > 0, s
        assert isinstance(s.get("pdf_page"), int) and s["pdf_page"] > 0, s
        assert f"p.{s['page']}" in s["citation"], s["citation"]
        assert s.get("quote", "").strip(), s
        assert s.get("supports"), s


def _figures(x):
    return {f"{v:g}" for v in (x["min"], x["max"])} if isinstance(x, dict) and "min" in x else \
           ({f"{x['value']:g}"} if isinstance(x, dict) and "value" in x else set())


@pytest.mark.parametrize("key", [k for k in LIVE if k not in INCOMPLETE],
                         ids=lambda k: "-".join(k[::2]) + "-" + k[1][:12])
def test_every_dose_figure_is_in_a_quote(key):
    e, _ = _entry(*key)
    quotes = " ".join(s["quote"] for s in e["sources"]).replace(",", "")
    numbers = set(re.findall(r"\d+(?:\.\d+)?", quotes))
    for field in ("dose_range", "max_single", "max_cumulative"):
        for fig in _figures(e.get(field)):
            assert fig in numbers, (field, fig, key)


@pytest.mark.parametrize("key", [k for k in INCOMPLETE if k in LIVE], ids=lambda k: "-".join(k[::2]))
def test_what_no_source_states_stays_marked_incomplete(key):
    e, _ = _entry(*key)
    assert e["dose_range"] == "NEEDS_MANUAL_ENTRY"
    assert "DOSE_NOT_IN_SOURCE" in e["flags"]


@pytest.mark.parametrize("key", [k for k in CONFLICTS if k in LIVE], ids=lambda k: "-".join(k[::2]) + "-" + k[1][:12])
def test_a_ruled_conflict_carries_the_owners_adjudication(key):
    e, _ = _entry(*key)
    assert "SOURCE_CONFLICT" not in e["flags"] and "conflict_group" not in e
    assert e["adjudication"].startswith("OWNER RULING 2026-10-14 (Andrew Azelton)")
    assert "CONFLICT" in e["extraction_notes"]


def test_ketorolac_carries_smogs_battlefield_trauma_contraindication():
    for key in [k for k in DRAFTS if k[0] == "ketorolac"]:
        e, _ = _entry(*key)
        assert any("battlefield trauma" in c for c in e["contraindications"]), key
        assert any("hypotension" in c.lower() for c in e["contraindications"]), key


def test_the_retired_adult_fentanyl_iv_per_kg_entries_stay_retired():
    for e in _drug("fentanyl")["dose_entries"]:
        if e["population"] == "adult" and e["route"] == "IV" and "infusion" not in e["indication"]:
            assert e["dose_range"]["per_kg"] is False, e["indication"]


def test_the_new_drugs_carry_the_lexicon_aliases():
    lexicon = json.loads((SERVER / "drug_lexicon.json").read_text())
    for name in ("acetaminophen", "ketorolac"):
        d = _drug(name)
        lex = lexicon["drugs"][name]
        aliases = lex["aliases"] if isinstance(lex, dict) else lex
        assert set(aliases) <= set(d["aliases"]), name


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


def _pdf_for(source):
    if source.get("source_class") == "NASEMSO":
        return NASEMSO_PDF
    return PDF_DIR / source["url"].split("/")[-1]


@pytest.mark.skipif(shutil.which("pdftotext") is None or not PDF_DIR.is_dir() or not NASEMSO_PDF.is_file(),
                    reason="the source PDFs (JTS_PDF_DIR, NASEMSO_PDF) or pdftotext are not available")
def test_every_quote_is_verbatim_on_its_cited_page():
    for key in LIVE:
        e, _ = _entry(*key)
        for s in e["sources"]:
            texts = _page_texts(_pdf_for(s), s["pdf_page"])
            for part in s["quote"].replace(" [sic]", "").split(" … "):
                assert any(_norm(part) in t for t in texts), (key, s["citation"], part)
