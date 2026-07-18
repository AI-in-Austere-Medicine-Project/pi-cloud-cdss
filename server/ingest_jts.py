#!/usr/bin/env python3
"""
EdgeCDSS — JTS CPG ingestion v2
Rebuilt 2026-07-18 (original ingestion script was lost with arcaneone).

Ingests JTS Clinical Practice Guideline PDFs into ChromaDB for RAG retrieval.

Improvements over naive ingestion:
  - Sentence-boundary-aware chunking with overlap (no mid-sentence cuts)
  - Repeated header/footer removal (per-document frequency analysis)
  - De-hyphenation of line-wrapped words
  - Page-accurate metadata + CPG ID and date parsed from filenames
  - Deterministic chunk IDs + upsert -> idempotent, re-runnable
  - Batched writes

Compatibility (matches embeddings.py / classify_retrieval expectations):
  - collection: jts_protocols
  - Chroma DEFAULT embedding function (local, same as server)
  - metadata keys: source (title), page (int) — plus extras (file, cpg_id, date)

Usage (on the Jetson, inside the venv):
  cd ~/pi-cloud-cdss/server
  ../.venv/bin/python3 ingest_jts.py --pdf-dir ./data/jts_protocols
  # options: --db ./cache/chromadb   --reset   --dry-run
"""

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

# ── Chunking parameters ──────────────────────────────────────────────────────
CHUNK_TARGET = 900     # chars per chunk (~ fits MiniLM's context)
CHUNK_OVERLAP = 150    # chars of trailing context carried into the next chunk
MIN_CHUNK = 120        # chunks smaller than this get merged into the previous
BATCH_SIZE = 128

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9(])')


def parse_filename(fname: str):
    """Extract a clean title, CPG id, and date from a JTS filename like
    'Acute_Coronary_Syndrome_14_May_2021_ID86.pdf'"""
    stem = Path(fname).stem
    cpg_id = None
    m = re.search(r'ID[_\s]?(\d+)', stem, re.IGNORECASE)
    if m:
        cpg_id = f"ID{m.group(1)}"
    date = None
    m = re.search(r'(\d{1,2})[_\s](Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*[_\s](\d{4})', stem, re.IGNORECASE)
    if m:
        date = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    else:
        m = re.search(r'(Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*[_\s](\d{4})', stem, re.IGNORECASE)
        if m:
            date = f"{m.group(1)} {m.group(2)}"
    # strip date/ID/version suffixes for the title
    title = re.sub(r'[_\s]*\d{0,2}[_\s]*(Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*[_\s]*\d{4}.*$', '', stem, flags=re.IGNORECASE)
    title = re.sub(r'[_\s]*ID[_\s]?\d+.*$', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[_\s]*v\d+(\.\d+)?$', '', title, flags=re.IGNORECASE)
    title = title.replace('_', ' ').strip() or stem.replace('_', ' ')
    return title, cpg_id, date


def clean_page_text(text: str) -> str:
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)      # de-hyphenate line wraps
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


EDGE_LINES = 4  # only lines this close to a page's top/bottom can be header/footer


def find_repeated_lines(pages_text: list) -> set:
    """Lines appearing near the top/bottom of >60% of pages are headers/footers.
    Position-aware: body text that happens to repeat is never stripped."""
    if len(pages_text) < 4:
        return set()
    counts = Counter()
    for t in pages_text:
        lines = [l.strip() for l in t.split('\n')]
        edge = lines[:EDGE_LINES] + lines[-EDGE_LINES:]
        seen = {s for s in edge if 0 < len(s) <= 90}
        counts.update(seen)
    threshold = max(3, int(len(pages_text) * 0.6))
    return {line for line, c in counts.items() if c >= threshold}


def strip_boilerplate(text: str, repeated: set) -> str:
    lines = text.split('\n')
    kept = []
    for idx, line in enumerate(lines):
        s = line.strip()
        near_edge = idx < EDGE_LINES or idx >= len(lines) - EDGE_LINES
        if near_edge and s in repeated:
            continue
        if near_edge and re.fullmatch(r'(Page\s*)?\d{1,3}(\s*of\s*\d{1,3})?', s, re.IGNORECASE):
            continue  # bare page numbers
        kept.append(line)
    return '\n'.join(kept)


def chunk_text(text: str):
    """Sentence-aware chunks of ~CHUNK_TARGET chars with CHUNK_OVERLAP carry."""
    sentences = _SENT_SPLIT.split(text)
    chunks, cur = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + len(s) + 1 > CHUNK_TARGET:
            chunks.append(cur.strip())
            cur = (cur[-CHUNK_OVERLAP:] + " " if CHUNK_OVERLAP else "") + s
        else:
            cur = (cur + " " + s).strip()
    if cur.strip():
        if chunks and len(cur.strip()) < MIN_CHUNK:
            chunks[-1] = chunks[-1] + " " + cur.strip()
        else:
            chunks.append(cur.strip())
    return chunks


def ingest_pdf(pdf_path: Path):
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    raw_pages = []
    for pg in reader.pages:
        try:
            raw_pages.append(pg.extract_text() or "")
        except Exception:
            raw_pages.append("")
    repeated = find_repeated_lines(raw_pages)
    title, cpg_id, date = parse_filename(pdf_path.name)

    docs, metas, ids = [], [], []
    for pageno, raw in enumerate(raw_pages, start=1):
        text = clean_page_text(strip_boilerplate(raw, repeated))
        if len(text) < 80:      # blank / image-only pages
            continue
        for ci, chunk in enumerate(chunk_text(text)):
            docs.append(chunk)
            meta = {"source": title, "file": pdf_path.name, "page": pageno}
            if cpg_id:
                meta["cpg_id"] = cpg_id
            if date:
                meta["date"] = date
            metas.append(meta)
            ids.append(f"{pdf_path.stem}_p{pageno}_c{ci}")
    return docs, metas, ids


def main():
    ap = argparse.ArgumentParser(description="Ingest JTS CPG PDFs into ChromaDB")
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--db", default=os.getenv("CHROMADB_PATH", "./cache/chromadb"))
    ap.add_argument("--collection", default="jts_protocols")
    ap.add_argument("--reset", action="store_true", help="delete the collection first")
    ap.add_argument("--dry-run", action="store_true", help="parse and chunk, no DB writes")
    args = ap.parse_args()

    pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {args.pdf_dir}")
    print(f"📄 {len(pdfs)} PDFs in {args.pdf_dir}")

    collection = None
    if not args.dry_run:
        import chromadb
        client = chromadb.PersistentClient(path=args.db)
        if args.reset:
            try:
                client.delete_collection(args.collection)
                print(f"🗑️  Deleted existing collection '{args.collection}'")
            except Exception:
                pass
        collection = client.get_or_create_collection(
            name=args.collection,
            metadata={"description": "Joint Trauma System Clinical Practice Guidelines"}
        )
        print(f"📦 Collection '{args.collection}' at {os.path.abspath(args.db)} "
              f"(currently {collection.count()} chunks)")

    total = 0
    for pdf in pdfs:
        try:
            docs, metas, ids = ingest_pdf(pdf)
        except Exception as e:
            print(f"  ❌ {pdf.name}: {e}")
            continue
        total += len(docs)
        print(f"  {'· (dry) ' if args.dry_run else '✅ '}{pdf.name}: {len(docs)} chunks")
        if collection is not None and docs:
            for i in range(0, len(docs), BATCH_SIZE):
                collection.upsert(
                    documents=docs[i:i+BATCH_SIZE],
                    metadatas=metas[i:i+BATCH_SIZE],
                    ids=ids[i:i+BATCH_SIZE],
                )

    print(f"\n== {total} chunks from {len(pdfs)} PDFs ==")
    if collection is not None:
        print(f"📦 Collection now holds {collection.count()} chunks")
        # smoke-test retrieval
        r = collection.query(query_texts=["tourniquet conversion hemorrhage control"], n_results=2)
        for doc, meta in zip(r["documents"][0], r["metadatas"][0]):
            print(f"   ↳ {meta.get('source')} p.{meta.get('page')}: {doc[:90]}...")


if __name__ == "__main__":
    main()
