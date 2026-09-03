# Disaster Recovery — Rebuilding EdgeCDSS From Nothing

How to stand up a working EdgeCDSS 4.0 server on any Linux machine (or WSL2 on Windows)
when the primary device is lost, dead, or unreachable. Written for real conditions:
assume nothing but this repo, an internet connection, and your API keys.

## What lives where

| State | In the repo? | Recovery source |
|---|---|---|
| All code, router index, safety rules, test suites | ✅ yes | `git clone` |
| JTS CPG PDFs (~89 files, `data/jts/`) | ❌ gitignored | `scripts/fetch_jts_cpgs.sh` (public JTS site), or the data pack on the [Releases page](../../releases) |
| ChromaDB vector database (`cache/chromadb/`) | ❌ gitignored | Rebuild with `server/tools/ingest_jts.py`, or the snapshot on the [Releases page](../../releases) |
| API keys (`server/.env`) | ❌ never committed | The backup tarball from `scripts/backup_deployment_state.sh`, else your password manager / provider dashboards |
| Cloudflare tunnel credentials (`~/.cloudflared/`) | ❌ never committed | The backup tarball from `scripts/backup_deployment_state.sh`, else the Cloudflare dashboard — create a new tunnel (see "Restoring the public site") |
| Deployment declarations (`server/drug_concentrations.json` + audit log) | ❌ gitignored | The backup tarball from `scripts/backup_deployment_state.sh`, else re-declare from `server/drug_concentrations.example.json` and re-sign — **requires a signer** |

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
python server/tools/ingest_jts.py
# ...OR restore the certified snapshot from the Releases page:
#   wget <release-url>/chromadb_snapshot.tar.gz && tar xzf chromadb_snapshot.tar.gz

# 5. Secrets — create server/.env (NOT the repo root; the service's WorkingDirectory is server/):
#   OPENAI_API_KEY=...
#   ELEVENLABS_API_KEY=sk_...     (optional — voice degrades gracefully without it;
#                                  must be the key, not the 64-char hex key ID)
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

## Deployment state — the part no rebuild can reconstruct

Everything above this section comes back from a public source or a snapshot. One
category does not, and it is the category worth the most: **what is in this bag,
and who signed for it.**

`server/drug_concentrations.json` is the concentration master list — the vials
this deployment actually carries, and the clinician signatures that let the
system convert a milligram dose into a millilitre volume. It is gitignored
deliberately (`45d5ddd`), and it should stay that way:

> A signed concentration is a claim about **one physical kit**. Committing one
> deployment's signatures would make every clone assert vials it does not have —
> which is the exact failure the signoff gate exists to prevent.

The consequence is that the file, its audit log (`drug_concentrations.log.jsonl`),
`server/.env` and `~/.cloudflared/` exist **on one device and nowhere else**.

**Back them up:**

```bash
bash scripts/backup_deployment_state.sh
# -> ~/edgecdss-deployment-state-<host>-<date>.tar.gz, mode 600
```

The archive **contains secrets** — API keys, the CDSS access token, tunnel
credentials. It belongs on the USB stick or in the password-manager vault, and
never in a GitHub release or the repo. Restore instructions, one block per file,
are in the header of that script.

**If there is no backup**, the system is not broken — it fails closed. With no
concentrations file the loader prints `no concentrations are declared, so no
volumes will be served` and the server answers in milligrams only. To get
volumes back:

```bash
cd server
cp drug_concentrations.example.json drug_concentrations.json
python3 tools/set_concentration.py --list
python3 tools/set_concentration.py --drug ketamine \
        --sign "500 mg / 10 mL vial" --by <signer> --date <YYYY-MM-DD>
```

The template ships every presentation `signoff:false`, so nothing is asserted
until a clinician signs it. **Do not restore another kit's signatures onto a
different bag** — check `kit_id` first. Re-signing needs an authorised signer;
that is the cost of the guarantee, and it is the right cost.

## Notes

- A fresh `fetch_jts_cpgs.sh` download reflects the **current** JTS site, which may
  differ from the KB a release was tested against. The Releases snapshot is the
  certified KB; the script is the always-works fallback.
- `server/protocol_index.json` contains hand-tuned router search terms.
  Do **not** regenerate it with `server/tools/build_protocol_index.py` unless you re-apply the tuning
  (see comments in the file's TBI entries).
- Rebuild order matters: PDFs → ingest → run. The server starts with an empty KB
  but answers will be ungrounded — always verify with the KB check in step 6.
