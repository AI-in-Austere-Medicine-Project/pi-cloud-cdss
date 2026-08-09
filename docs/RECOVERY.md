# Disaster Recovery — Rebuilding EdgeCDSS From Nothing

How to stand up a working EdgeCDSS 4.0 server on any Linux machine (or WSL2 on Windows)
when the primary device is lost, dead, or unreachable. Written for real conditions:
assume nothing but this repo, an internet connection, and your API keys.

## What lives where

| State | In the repo? | Recovery source |
|---|---|---|
| All code, router index, safety rules, test suites | ✅ yes | `git clone` |
| JTS CPG PDFs (~89 files, `data/jts/`) | ❌ gitignored | `scripts/fetch_jts_cpgs.sh` (public JTS site), or the data pack on the [Releases page](../../releases) |
| ChromaDB vector database (`cache/chromadb/`) | ❌ gitignored | Rebuild with `server/ingest_jts.py`, or the snapshot on the [Releases page](../../releases) |
| API keys (`.env`) | ❌ never committed | Your password manager / provider dashboards |
| Cloudflare tunnel credentials | ❌ never committed | Cloudflare dashboard — create a new tunnel (step 6) |

## Full rebuild

```bash
# 1. Code
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss

# 2. Knowledge base — EITHER re-download from the source...
bash scripts/fetch_jts_cpgs.sh
# ...OR pull the tested data pack from the Releases page:
#   wget <release-url>/jts_cpgs.tar.gz && tar xzf jts_cpgs.tar.gz

# 3. Python environment
pip install -r requirements-server.txt

# 4. Vector DB — EITHER rebuild (~20 min on CPU)...
python server/ingest_jts.py
# ...OR restore the certified snapshot from the Releases page:
#   wget <release-url>/chromadb_snapshot.tar.gz && tar xzf chromadb_snapshot.tar.gz

# 5. Secrets — create .env in the repo root:
#   OPENAI_API_KEY=...
#   ELEVENLABS_API_KEY=...        (optional — voice degrades gracefully without it)
#   CDSS_LOG_DIR=./logs

# 6. Run
uvicorn server.main:app --host 0.0.0.0 --port 8000
# verify: curl localhost:8000/health
# verify KB: curl -X POST localhost:8000/query -H 'Content-Type: application/json' \
#   -d '{"query":"ketamine dose for a 80kg adult with a broken femur"}'
```

## Restoring the public site (cdss.arcanekg.com)

The tunnel is outbound-only, so the replacement machine can be behind any NAT/CGNAT.
On the new machine:

```bash
# install cloudflared, then:
cloudflared tunnel login
cloudflared tunnel create edgecdss-recovery
cloudflared tunnel route dns edgecdss-recovery cdss.arcanekg.com
cloudflared tunnel run --url http://localhost:8000 edgecdss-recovery
```

`route dns` repoints the hostname at the new tunnel — the old (dead) machine's
tunnel is simply abandoned. Public site is back with no DNS wait.

## Notes

- A fresh `fetch_jts_cpgs.sh` download reflects the **current** JTS site, which may
  differ from the KB a release was tested against. The Releases snapshot is the
  certified KB; the script is the always-works fallback.
- `server/protocol_index.json` contains hand-tuned router search terms.
  Do **not** regenerate it with `build_protocol_index.py` unless you re-apply the tuning
  (see comments in the file's TBI entries).
- Rebuild order matters: PDFs → ingest → run. The server starts with an empty KB
  but answers will be ungrounded — always verify with the KB check in step 6.
