"""Signing batch 3, the last: the review packet (owner, 2026-10-21).

"Build a review packet in Word and PDF under docs/authoring/: one page per
entry for every unsigned contract entry (42), P1/P2, and the 12 undrafted
indications. Each page: drug, indication, population, route, proposed
dose/max/repeat, verbatim source quote, printed page number, and a rendered
image of the source page with the line boxed. JTS first, SMOG second, NASEMSO
noted only. Where sources disagree, show both on the same page. Where no JTS
or SMOG page states a number, pre-mark RETIRE. Leave a SIGN / RETIRE / DEFER
line on each page. Sign nothing."

The 42 are the unsigned entries less the five ketorolac entries the owner
excluded (OWNER_EXCLUDED, 2026-10-14). The packet's pages are generated from
ITEMS by tools/gen_signing_packet.py; these tests pin what the items say.
The quote test needs JTS_PDF_DIR (and NASEMSO_PDF) and pdftotext; without
them it skips.

    cd server && ./run_unit_tests.sh
"""
import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1]
DOCS = SERVER.parent / "docs" / "authoring"
ITEMS = DOCS / "SIGNING_BATCH3_ITEMS_2026-10-21.json"
DOCX = DOCS / "SIGNING_BATCH3_PACKET_2026-10-21.docx"
PDF = DOCS / "SIGNING_BATCH3_PACKET_2026-10-21.pdf"
PDF_DIR = pathlib.Path(os.environ.get("JTS_PDF_DIR", SERVER / "data/jts_protocols"))
NASEMSO_PDF = pathlib.Path(os.environ.get(
    "NASEMSO_PDF", SERVER.parent / "sources/National_Model_EMS_Clinical_Guidelines_Version_3.pdf"))
CLASS_ORDER = {"JTS": 0, "SMOG": 1, "NASEMSO": 2}
NO_NUMBER = ("no number", "condition only")


def _no_number(s):
    """A source listed for context: what it states begins "no number" (with
    the reason), or "no contraindication" for a procedure row, or is
    "condition only"."""
    return (s["states"].startswith(("no number", "no contraindication"))
            or s["states"] == "condition only")


def _bank():
    """{generic_name: drug} from the bank file."""
    return {d["generic_name"]: d
            for d in json.loads((SERVER / "drug_contracts.json").read_text())["drugs"]}


def _items():
    return json.loads(ITEMS.read_text())


def test_the_packet_files_exist():
    for p in (ITEMS, DOCX, PDF):
        assert p.is_file(), p


# The owner's rulings on the packet (2026-10-21), by item. The bank no longer
# holds the 42 unsigned entries the packet was built from: what was ruled is
# pinned in test_signing_batch3_rulings.py; here, that every page got one.
RULED = {
    "SIGN": ["E05", "E06", "E10", "E11", "E13", "E16", "E17", "E18", "E19", "E20", "E21", "E23", "E27",
             "U01", "U02", "U03", "U04", "U05", "U06", "U07", "U08", "U09", "U10", "U11", "U12"],
    "RETIRE": ["E01", "E03", "E04", "E07", "E08", "E12", "E22", "E24", "E25", "E26", "E28", "E29", "E30",
               "E31", "E32", "E33", "E34", "E35", "E36", "E37", "E38", "E39", "E40", "E41", "E42"],
    "DEFER": ["E02", "E09", "E14", "E15"],
    "HOLD": ["P1", "P2"],
}


def test_one_page_for_every_entry_that_was_unsigned_and_every_page_ruled():
    """42 entry pages, as built (2026-10-21), and a ruling for every page. E20
    is SIGN for its adult half and RETIRE for its paediatric half; it is listed
    once, under SIGN."""
    items = _items()
    entries = [i["id"] for i in items if i["kind"] == "entry"]
    assert len(entries) == 42 and len(set(entries)) == 42
    ruled = [x for ids in RULED.values() for x in ids]
    assert len(ruled) == len(set(ruled))
    assert sorted(ruled) == sorted(i["id"] for i in items)


def test_a_drug_named_on_a_page_is_still_in_the_bank():
    """Retired entries leave the bank; their drugs do not."""
    bank = _bank()
    for i in _items():
        if i["kind"] == "entry":
            assert i["drug"] in bank, i["id"]


def test_p1_p2_and_the_12_undrafted_indications_have_pages():
    items = _items()
    assert sorted(i["id"] for i in items if i["kind"] == "procedure") == ["P1", "P2"]
    assert len([i for i in items if i["kind"] == "undrafted"]) == 12


def test_jts_first_smog_second_nasemso_noted_only():
    for i in _items():
        order = [CLASS_ORDER[s["class"]] for s in i["sources"]]
        assert order == sorted(order), i["id"]
        numbered = [s for s in i["sources"] if not _no_number(s)]
        if numbered and not i["premark"]:
            assert numbered[0]["class"] in ("JTS", "SMOG"), i["id"]


def test_retire_is_premarked_exactly_where_no_jts_or_smog_page_states_a_number():
    for i in _items():
        stated = [s for s in i["sources"]
                  if s["class"] in ("JTS", "SMOG") and not _no_number(s)]
        assert (i["premark"] == "RETIRE") == (not stated), i["id"]


def test_every_source_has_a_printed_page_a_quote_and_a_boxed_line():
    for i in _items():
        for s in i["sources"]:
            assert s["quote"] and s["box"], (i["id"], s["pdf"])
            assert re.sub(r"\s+", " ", s["box"]) in re.sub(r"\s+", " ", s["quote"]), (i["id"], s["pdf"])
            assert "printed_page" in s, (i["id"], s["pdf"])


def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


def _page_texts(pdf, page):
    run = lambda *a: subprocess.run(["pdftotext", *a, "-f", str(page), "-l", str(page), str(pdf), "-"],
                                    capture_output=True, text=True, check=True).stdout
    return [_norm(run("-layout")), _norm(run())]


def _pdf(name):
    return NASEMSO_PDF if name == NASEMSO_PDF.name else PDF_DIR / name


@pytest.mark.skipif(shutil.which("pdftotext") is None or not PDF_DIR.is_dir(),
                    reason="the source PDFs (JTS_PDF_DIR) or pdftotext are not available")
def test_every_quote_is_verbatim_on_its_page():
    for i in _items():
        for s in i["sources"]:
            path = _pdf(s["pdf"])
            if not path.is_file():
                pytest.skip(f"{path} not available")
            texts = _page_texts(path, s["pdf_page"])
            assert any(_norm(s["quote"]) in t for t in texts), (i["id"], s["pdf"], s["pdf_page"])
