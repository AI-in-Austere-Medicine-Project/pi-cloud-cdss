#!/usr/bin/env python3
"""K2: the kit packet (Word and PDF). One page per bank drug with a signed dose.

    python3 tools/gen_kit_packet.py <kit.json> <smog_strengths.json> <build_dir>

Owner, 2026-10-28: "kit packet: one page per drug in the bank with a signed
dose, listing the concentrations the kit file or SMOG shows, a SIGN line per
concentration, and a "two strengths stocked" option. Word and PDF under
docs/authoring. Sign nothing."

Each page: the drug's signed doses (what a strength turns into a volume), the
kit file's presentations (label, mg/mL, signed or not), the strengths SMOG
CY24 shows (verbatim, with the printed page; checked against the PDF's text
here, and a quote not found is reported, not printed as found), a SIGN line
per vial strength, a blank line for a strength neither shows, and the
choice: one strength stocked (no vial question) or two (asked every time).
Infusion mixes SMOG shows are listed for reference with no SIGN line: a bag
is not a vial. Nothing here signs anything: a signature is entered with
tools/set_concentration.py (--sign, or --single for the kit's one vial).

Needs poppler (pdftotext) and LibreOffice (soffice). Run it with the
service venv's python from the repo root (it imports server/drug_contracts).
"""
import html
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import drug_contracts  # noqa: E402

SMOG_PDF = pathlib.Path(os.environ.get(
    "SMOG_PDF", ROOT / "server/data/jts_protocols/SMOG_CY24_REVISION_FINAL.pdf"))
STAMP = "2026-10-28"
TITLE = "EdgeCDSS kit packet: vial strengths to sign"
NAME = f"KIT_PACKET_{STAMP}"
BOX = "&#9744;"


def esc(s):
    return html.escape(str(s))


def smog_pages():
    """Each page's text twice over: as laid out, and in reading order. SMOG is
    two columns, so a line can be whole in one and interleaved in the other."""
    modes = []
    for args in (["-layout"], []):
        out = subprocess.run(["pdftotext", *args, str(SMOG_PDF), "-"],
                             capture_output=True, text=True, check=True).stdout
        modes.append([re.sub(r"\s+", " ", p) for p in out.split("\f")])
    return list(zip(*modes))


def quote_found(pages, page, quote):
    """Every '...'-separated part of the quote is on that page (spacing aside),
    in either text mode."""
    texts = pages[page - 1] if 0 < page <= len(pages) else ()
    return all(any(re.sub(r"\s+", " ", part).strip() in t for t in texts)
               for part in quote.split("..."))


def strength(mg_ml):
    if mg_ml < 0.1:
        return f"{mg_ml * 1000:g} mcg/mL"
    return f"{mg_ml:g} mg/mL"


def dose_rows(drug):
    rows = []
    for e in drug_contracts.servable_entries().get(drug, []):
        dr = e.get("dose_range") or {}
        lo, hi, units = dr.get("min"), dr.get("max"), dr.get("units", "")
        dose = f"{lo:g} {units}" if lo == hi else f"{lo:g}–{hi:g} {units}"
        rows.append((e.get("indication", ""), e.get("population", ""), e.get("route", ""), dose))
    return rows


def sign_line(what):
    return (f'<tr><td style="width:46%">{what}</td>'
            f'<td>{BOX} SIGN as stocked &nbsp; {BOX} not stocked</td>'
            f'<td style="width:28%">Signed ____________ Date ________</td></tr>')


def page_html(drug, kit_entry, smog, pages, misses):
    parts = [f'<p style="page-break-before:always; margin:0; font-size:7pt; color:#555">{esc(TITLE)} · {esc(drug)}</p>',
             f'<h2 style="margin:4pt 0">{esc(drug)}</h2>']
    rows = dose_rows(drug)
    parts.append(f'<p style="margin:2pt 0"><b>Signed doses in the bank</b> ({len(rows)}): a signed strength turns these into millilitres.</p>')
    parts.append('<table border="1" cellspacing="0" cellpadding="2" style="border-collapse:collapse; font-size:7pt; width:100%">'
                 '<tr><th>Indication</th><th>Population</th><th>Route</th><th>Dose</th></tr>'
                 + "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>"
                           for a, b, c, d in rows) + "</table>")

    sign_rows = []
    pres = (kit_entry or {}).get("presentations", [])
    parts.append('<p style="margin:6pt 0 2pt"><b>The kit file</b> (drug_concentrations.json)</p>')
    if pres:
        state = []
        for p in pres:
            signed = bool(p.get("signoff")) and p.get("reviewed_by") not in (None, "PENDING_CLINICAL_SIGNOFF")
            state.append(f"<li>{esc(p['label_text'])} = {esc(strength(p['concentration_mg_ml']))}: "
                         f"{'signed ' + esc(p.get('reviewed_by')) + ' ' + esc(p.get('review_date')) if signed else 'declared, unsigned'}</li>")
            sign_rows.append(sign_line(f"Kit: {esc(p['label_text'])} ({esc(strength(p['concentration_mg_ml']))})"))
        cr = "asks which vial every time (confirm_required)" if kit_entry.get("confirm_required") else "does not ask which vial"
        parts.append(f'<ul style="margin:0">{"".join(state)}</ul><p style="margin:0; font-size:8pt">The kit {cr}.</p>')
    else:
        parts.append('<p style="margin:0">No presentation declared.</p>')

    parts.append('<p style="margin:6pt 0 2pt"><b>SMOG CY24</b></p>')
    vials = [s for s in smog if s["kind"] == "vial"]
    mixes = [s for s in smog if s["kind"] == "infusion"]
    if not smog:
        parts.append('<p style="margin:0">SMOG states doses for this drug in mg and no strength, or has no monograph for it.</p>')
    for s in vials + mixes:
        found = quote_found(pages, s["page"], s["quote"])
        if not found:
            misses.append(f'{drug} p.{s["page"]}: {s["quote"]}')
        tag = "" if found else ' <span style="color:#b00">(quote not found on that page: check)</span>'
        kind = "vial strength" if s["kind"] == "vial" else "infusion mix, not a vial: reference only"
        parts.append(f'<p style="margin:0 0 2pt 10pt; font-size:8.5pt">{esc(strength(s["mg_ml"]))}, {kind}. '
                     f'p.{s["page"]}: &ldquo;{esc(s["quote"])}&rdquo;{tag}</p>')
    for s in vials:
        kit_has = any(abs(p["concentration_mg_ml"] - s["mg_ml"]) < 1e-9 for p in pres)
        if not kit_has:
            sign_rows.append(sign_line(f"SMOG p.{s['page']}: {esc(strength(s['mg_ml']))}, not in the kit file "
                                       f"(declare: ____ mg in ____ mL)"))

    sign_rows.append(sign_line("Another strength on the vial: ______ mg in ______ mL"))
    parts.append('<p style="margin:8pt 0 2pt"><b>Sign</b>: one line per strength. Sign only what you have read off the vial.</p>')
    parts.append('<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse; font-size:8.5pt; width:100%">'
                 + "".join(sign_rows) + "</table>")
    parts.append('<p style="margin:8pt 0 2pt"><b>Stocked</b> (tick one)</p>'
                 f'<p style="margin:0 0 2pt 10pt">{BOX} <b>One strength stocked</b>: ____________. '
                 'Doses serve mg and mL from it with no vial question; a different strength the medic states still withholds the volume.</p>'
                 f'<p style="margin:0 0 2pt 10pt">{BOX} <b>Two strengths stocked</b>: ____________ and ____________. '
                 'The medic is asked which vial every time before any mL.</p>'
                 f'<p style="margin:0 0 2pt 10pt">{BOX} <b>Not stocked</b>: doses serve mg only.</p>'
                 '<p style="margin:6pt 0 0; font-size:8pt">Declared by ______________________ Date __________ '
                 '(entered with tools/set_concentration.py; nothing on this page is signed until then)</p>')
    return "".join(parts)


def cover(drugs, kit_path, misses_note):
    return (f"<h1>{esc(TITLE)}</h1>"
            f"<p>{esc(STAMP)}. One page per drug with a signed dose in the bank: {len(drugs)} drugs. "
            "Each lists the strengths the kit file and SMOG CY24 show, a SIGN line per strength, "
            "and whether one strength or two is stocked. <b>Nothing in this packet is signed.</b></p>"
            "<p>Why it matters: a millilitre is served only from a signed strength. One strength stocked: "
            "the volume is served without asking. Two: the medic is asked which vial first. "
            "None signed: mg only.</p>"
            f"<p>Kit file: {esc(kit_path)}. SMOG: {esc(SMOG_PDF.name)} (printed page = PDF page); "
            "quotes are checked against the PDF's text when the packet is built"
            f"{esc(misses_note)}.</p>"
            "<p>Drugs: " + esc(", ".join(drugs)) + "</p>")


def main():
    kit_path, smog_path, build = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    build.mkdir(parents=True, exist_ok=True)
    kit = {e["generic_name"]: e for e in json.loads(pathlib.Path(kit_path).read_text())["entries"]}
    smog = json.loads(pathlib.Path(smog_path).read_text())["drugs"]
    pages = smog_pages()
    served = drug_contracts.servable_entries()
    drugs = [d for d in drug_contracts.DRUGS if served.get(d)]
    misses, body = [], []
    for d in drugs:
        body.append(page_html(d, kit.get(d), smog.get(d, []), pages, misses))
    note = "; every quote was found" if not misses else f"; {len(misses)} not found, marked on their pages"
    doc = (f'<html><head><meta charset="utf-8"><title>{esc(TITLE)}</title>'
           "<style>@page { size: 8.5in 11in; margin: 0.45in 0.55in; } "
           "body { font-family: 'DejaVu Sans', sans-serif; font-size: 9.5pt; }</style>"
           f"</head><body>{cover(drugs, kit_path, note)}{''.join(body)}</body></html>")
    src = build / f"{NAME}.html"
    src.write_text(doc)
    subprocess.run(["soffice", "--headless", "--infilter=HTML (StarWriter)",
                    "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(build), str(src)],
                   check=True, capture_output=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(build),
                    str(build / f"{NAME}.docx")], check=True, capture_output=True)
    for m in misses:
        print("QUOTE NOT FOUND:", m)
    print("drugs", len(drugs), "quotes not found", len(misses))


if __name__ == "__main__":
    main()
