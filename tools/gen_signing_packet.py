#!/usr/bin/env python3
"""Signing batch 3: build the review packet (Word and PDF) from its items file.

    JTS_PDF_DIR=... NASEMSO_PDF=... python3 tools/gen_signing_packet.py \
        docs/authoring/SIGNING_BATCH3_ITEMS_2026-10-21.json <build_dir>

One page per item: drug, indication, population, route, the proposed dose,
max and repeat, and each source with its verbatim quote, printed page number
and a rendered band of the source page with the quoted line boxed in red. JTS
first, SMOG second, NASEMSO noted only. A SIGN / RETIRE / DEFER line on every
page; RETIRE pre-marked where the items say so. Nothing here signs anything.

Needs poppler (pdftoppm, pdftotext), LibreOffice (soffice) and Pillow; run it
with the system python3, which has Pillow. The page band is rendered from the
PDF and the box comes from pdftotext's word coordinates, so a line the
checker cannot find is reported, not guessed: the page then shows no box and
says so.
"""
import base64
import html
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
PDF_DIR = pathlib.Path(os.environ.get("JTS_PDF_DIR", ROOT / "server/data/jts_protocols"))
NASEMSO_PDF = pathlib.Path(os.environ.get(
    "NASEMSO_PDF", ROOT / "sources/National_Model_EMS_Clinical_Guidelines_Version_3.pdf"))
DPI = 110
STAMP = "2026-10-21"
TITLE = "EdgeCDSS signing batch 3: review packet"
CLASS_LABEL = {"JTS": "JTS", "SMOG": "SMOG", "NASEMSO": "NASEMSO (noted only, not a basis for the dose)"}


def pdf_path(name):
    return NASEMSO_PDF if name == NASEMSO_PDF.name else PDF_DIR / name


def words(pdf, page):
    """[(xMin, yMin, xMax, yMax, text)] in points, page size (w, h)."""
    out = subprocess.run(["pdftotext", "-bbox", "-f", str(page), "-l", str(page), str(pdf), "-"],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', out)
    size = (float(m[1]), float(m[2]))
    ws = [(float(a), float(b), float(c), float(d), html.unescape(t)) for a, b, c, d, t in re.findall(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', out)]
    return ws, size


def _tok(t):
    return re.sub(r"[^0-9a-z]", "", t.lower())


def locate(ws, box):
    """The rectangle around the words of `box`: the longest run of its tokens
    in the page's words (punctuation ignored, so "(Consider" is "Consider"),
    widened to the box's other tokens on the same line. A run may cross a
    line break: a flowchart cell wraps its text."""
    toks = [t for t in (_tok(x) for x in box.split()) if t]
    page = [_tok(w[4]) for w in ws]
    best, at = 0, None
    for i in range(len(ws)):
        n = j = 0
        while n < len(toks) and i + j < len(ws):
            if not page[i + j]:
                j += 1
                continue
            if page[i + j] != toks[n]:
                break
            n += 1
            j += 1
        if n > best:
            best, at, span = n, i, j
    if at is None or best < min(3, len(toks)):
        return locate_by_line(ws, toks)
    hit = ws[at:at + span]
    y0 = hit[0][1]
    rest = set(toks[best:])
    hit += [w for w in ws if abs(w[1] - y0) < 2.5 and _tok(w[4]) in rest and w not in hit]
    return (min(w[0] for w in hit), min(w[1] for w in hit),
            max(w[2] for w in hit), max(w[3] for w in hit))


def locate_by_line(ws, toks):
    """Fallback for a table or a merged-column line, where reading order
    breaks the run: the physical line (words sharing a baseline) holding the
    most of the box's tokens, with the next line when the box wraps. Only the
    box's own words are boxed."""
    lines = {}
    for w in ws:
        key = round(w[3] / 3)
        lines.setdefault(key, []).append(w)
    want = set(toks)
    if not want:
        return None
    scored = []
    for key, line in lines.items():
        got = [w for w in line if _tok(w[4]) in want]
        scored.append((len({_tok(w[4]) for w in got}), key, got))
    scored.sort(key=lambda x: -x[0])
    n, key, got = scored[0]
    if n < max(2, int(0.6 * len(want))):
        nxt = lines.get(key + 4, []) + lines.get(key + 5, []) + lines.get(key + 6, [])
        more = [w for w in nxt if _tok(w[4]) in want]
        if n + len({_tok(w[4]) for w in more}) < max(2, int(0.6 * len(want))):
            return None
        got += more
    return (min(w[0] for w in got), min(w[1] for w in got),
            max(w[2] for w in got), max(w[3] for w in got))


def band_png(pdf, page, rect, size, band_pt):
    """A band of the rendered page around rect, rect boxed in red, as PNG bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-f", str(page), "-l", str(page),
                        "-png", "-singlefile", str(pdf), f"{tmp}/p"], capture_output=True, check=True)
        im = Image.open(f"{tmp}/p.png").convert("RGB")
    k = im.width / size[0]
    if rect:
        x0, y0, x1, y1 = (v * k for v in rect)
        d = ImageDraw.Draw(im)
        for g in range(3):
            d.rectangle([x0 - 4 - g, y0 - 3 - g, x1 + 4 + g, y1 + 3 + g], outline=(220, 0, 0))
        mid = (y0 + y1) / 2
    else:
        mid = im.height * 0.5
    half = band_pt * k / 2
    top = int(max(0, min(mid - half, im.height - 2 * half)))
    im = im.crop((0, top, im.width, int(min(im.height, top + 2 * half))))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue(), im.width / im.height


def esc(t):
    return html.escape(t or "")


def page_html(item, build):
    n = max(1, len(item["sources"]))
    # The page is 10 in of usable height. The header table and the decision
    # line take about 4 in with spacing; the text is estimated at 140 characters a line
    # in the 7.5-8 pt type used for it, 0.13 in a line; the bands share what
    # is left, never less than 0.38 in (the boxed line and a line either side).
    lines = lambda t, w=118: max(1, -(-len(t or "") // w))
    text_in = 0.15 * (lines(item.get("conflict")) + lines(item.get("note"))
                      + sum(lines(s["quote"]) + 2 for s in item["sources"]))
    img_h = max(0.38, min(2.6, (10.0 - 4.0 - text_in) / n))
    width_in = 7.2
    rows = []
    misses = []
    for s in item["sources"]:
        pdf = pdf_path(s["pdf"])
        ws, size = words(pdf, s["pdf_page"])
        rect = locate(ws, s["box"])
        if rect is None:
            misses.append((item["id"], s["pdf"], s["pdf_page"], s["box"]))
        band_pt = img_h / width_in * size[0]
        png, _ = band_png(pdf, s["pdf_page"], rect, size, band_pt)
        (build / f"{item['id']}_{s['pdf_page']}_{len(rows)}.png").write_bytes(png)
        b64 = base64.b64encode(png).decode()
        printed = s.get("printed_page") or "none printed"
        where = (f"{esc(s.get('cpg') or s['pdf'])}: printed page <b>{esc(printed)}</b> "
                 f"(PDF page {s['pdf_page']})")
        boxed = "" if rect else " <i>(the line could not be located for a box; read the quote)</i>"
        rows.append(f"""
<p style="margin:4pt 0 1pt 0; font-size:8pt"><b>{esc(CLASS_LABEL[s['class']])}</b> · {where} · states: {esc(s['states'])}{boxed}</p>
<p style="margin:0 0 2pt 12pt; font-family:'DejaVu Serif',serif; font-size:7.5pt">“{esc(s['quote'])}”</p>
<p style="margin:0"><img src="data:image/png;base64,{b64}" style="width:{width_in}in; height:{img_h:.2f}in; border:1px solid #999"></p>""")
    p = item["proposed"]
    retire = item.get("premark") == "RETIRE"
    decision = ("☐ SIGN&nbsp;&nbsp;&nbsp;&nbsp;☒ RETIRE (pre-marked: no JTS or SMOG page states a number)"
                "&nbsp;&nbsp;&nbsp;&nbsp;☐ DEFER" if retire else
                "☐ SIGN&nbsp;&nbsp;&nbsp;&nbsp;☐ RETIRE&nbsp;&nbsp;&nbsp;&nbsp;☐ DEFER")
    kind = {"entry": "Unsigned contract entry", "undrafted": "Undrafted indication (v1.1 list)",
            "procedure": "Procedure row"}[item["kind"]]
    conflict = (f'<p style="margin:3pt 0; color:#a00000; font-size:8pt"><b>Sources disagree:</b> {esc(item["conflict"])}</p>'
                if item.get("conflict") else "")
    note = f'<p style="margin:3pt 0; font-size:7.5pt"><b>Note:</b> {esc(item["note"])}</p>' if item.get("note") else ""
    cell = 'style="border:1px solid #888; padding:2pt 4pt; font-size:9.5pt"'
    head = 'style="border:1px solid #888; padding:2pt 4pt; font-size:9.5pt; background:#eee; width:1.1in"'
    return f"""
<p style="page-break-before:always; margin:0; font-size:8pt; color:#555">{esc(TITLE)} · {esc(kind)} · {esc(item['id'])}</p>
<h2 style="margin:2pt 0 4pt 0; font-size:14pt">{esc(item['id'])}. {esc(item['drug'] or 'Procedure')}: {esc(item['indication'])}</h2>
<table style="border-collapse:collapse; width:7.2in"><col width="80"><col width="250"><col width="80"><col width="110">
<tr><td {head}>Drug</td><td {cell}>{esc(item['drug'] or '(procedure)')}</td><td {head}>Population</td><td {cell}>{esc(item['population'])}</td></tr>
<tr><td {head}>Indication</td><td {cell}>{esc(item['indication'])}</td><td {head}>Route</td><td {cell}>{esc(item['route'] or '—')}</td></tr>
<tr><td {head}>Proposed dose</td><td {cell} colspan="3"><b>{esc(p.get('dose'))}</b></td></tr>
<tr><td {head}>Max</td><td {cell} colspan="3">{esc(p.get('max') or 'not stated')}</td></tr>
<tr><td {head}>Repeat</td><td {cell} colspan="3">{esc(p.get('repeat') or 'not stated')}</td></tr>
</table>
{conflict}{note}
{''.join(rows) if rows else '<p><i>No JTS, SMOG or NASEMSO page found.</i></p>'}
<p style="margin:8pt 0 0 0; font-size:11pt; border-top:1px solid #000; padding-top:4pt">
<b>Decision:</b>&nbsp;&nbsp;{decision}&nbsp;&nbsp;&nbsp;&nbsp;Initials ______ Date ________</p>
""", misses


def cover(items):
    count = lambda k: sum(1 for i in items if i["kind"] == k)
    retire = sum(1 for i in items if i.get("premark") == "RETIRE")
    conflicts = sum(1 for i in items if i.get("conflict"))
    toc = "".join(f"<tr><td style='padding:1pt 4pt'>{esc(i['id'])}</td><td style='padding:1pt 4pt'>{esc(i['drug'] or 'Procedure')}</td>"
                  f"<td style='padding:1pt 4pt'>{esc(i['indication'])}</td><td style='padding:1pt 4pt'>{esc(i['population'])} {esc(i['route'])}</td>"
                  f"<td style='padding:1pt 4pt'>{'RETIRE' if i.get('premark') == 'RETIRE' else ''}{' · conflict' if i.get('conflict') else ''}</td></tr>"
                  for i in items)
    return f"""
<h1 style="font-size:18pt">{esc(TITLE)}</h1>
<p>Prepared {STAMP} for the owner's review. <b>Nothing in this packet is signed.</b> Signing is the owner's act: mark SIGN, RETIRE or DEFER on each page.</p>
<p>{len(items)} pages: {count('entry')} unsigned contract entries (the five ketorolac entries the owner excluded on 2026-10-14 are not included), {count('procedure')} procedure rows (P1, P2) and {count('undrafted')} undrafted indications from the v1.1 list. {retire} are pre-marked RETIRE because no JTS or SMOG page states a number; {conflicts} show sources that disagree.</p>
<p><b>How to read a page.</b> Sources are in order: JTS first, SMOG second, NASEMSO noted only (never the basis for a dose). Each source shows its verbatim quote, the page number printed on the page (with the PDF page index), and a band of the rendered page with the quoted line boxed in red. The proposed dose, max and repeat are as the first JTS (or, failing JTS, SMOG) source states them; "not stated" means the source does not say.</p>
<table style="border-collapse:collapse; font-size:8.5pt">{toc}</table>
"""


def main():
    items = json.loads(pathlib.Path(sys.argv[1]).read_text())
    build = pathlib.Path(sys.argv[2])
    build.mkdir(parents=True, exist_ok=True)
    parts, misses = [cover(items)], []
    for it in items:
        h, m = page_html(it, build)
        parts.append(h)
        misses += m
    doc = f"""<html><head><meta charset="utf-8"><title>{esc(TITLE)}</title>
<style>@page {{ size: 8.5in 11in; margin: 0.5in 0.6in; }} body {{ font-family: 'DejaVu Sans', sans-serif; font-size: 10pt; }}</style>
</head><body>{''.join(parts)}</body></html>"""
    src = build / "SIGNING_BATCH3_PACKET_2026-10-21.html"
    src.write_text(doc)
    subprocess.run(["soffice", "--headless", "--infilter=HTML (StarWriter)",
                    "--convert-to", "docx:MS Word 2007 XML", "--outdir", str(build), str(src)],
                   check=True, capture_output=True)
    docx = build / "SIGNING_BATCH3_PACKET_2026-10-21.docx"
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(build), str(docx)],
                   check=True, capture_output=True)
    for m in misses:
        print("NO BOX:", m)
    print("items", len(items), "misses", len(misses))


if __name__ == "__main__":
    main()
