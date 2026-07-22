# EdgeCDSS — Clinical Decision Support for Austere Medicine

**AI in Austere Medicine Project (AI-AMP)**
Open source. Edge deployed. Safety findings published.

> ⚠️ **Research prototype** — not validated for clinical use, not for patient care decisions. Simulated and synthetic scenarios only. Do not enter PHI, patient names, or identifying information into any project system.

**Current release: 4.0.0** · [Release notes](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/release-notes-4.0.html) · [Technical notes](docs/TECH_NOTES_v4.0.md) · [Project site](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/)

---

## What this is

EdgeCDSS is a self-hosted clinical decision support system for austere, remote, and resource-limited environments. A provider describes a casualty in plain field language — by text or voice — and receives structured, guideline-cited guidance in seconds, with every medication dose resolved to a final mL draw. Zero math for the field provider.

The entire system — knowledge base, retrieval engine, safety gates, web interface, feedback system, and audit logs — runs on a single **NVIDIA Jetson Orin Nano** at the point of care. Public access flows through an outbound-only Cloudflare Tunnel. The deployment is network agnostic: satellite, broadband, Wi-Fi, Ethernet, or LTE/5G.

**Try it:** the live portal is at **https://cdss.arcanekg.com** (demo access token is pre-filled in the interface).

## Architecture

Pipeline principle: **never ask an AI a question that code can answer.**

```
Query (text or voice)
      ↓
13 deterministic pre-gates ── weight, route, pediatric limits, contraindications
      ↓                       (many queries resolve here in milliseconds, no AI)
Patient context ───────────── rebuilt from the full conversation, deterministic
      ↓
Clinical router ───────────── protocol index aims retrieval at the right CPG
      ↓
On-device RAG ─────────────── 89 JTS CPGs / 8,559 chunks, local embeddings
      ↓
LLM generation ────────────── receives an ALLOWED_DOSES contract computed in
      ↓                       Python; prohibited from doing medication math
Deterministic post-checks ─── every stated dose verified against the contract
      ↓
LLM validator + gate ──────── narrow semantic check; fail-closed on any doubt
      ↓
Provider ──────────────────── cited response, validator status, feedback tools
```

AI is restricted to language generation, retrieval support, and semantic validation. Everything safety-critical is deterministic Python: inspectable, testable, and pinned by regression tests.

## Repository structure

```
pi-cloud-cdss/
├── START-HERE/
│   └── FIRST_TIME_GUIDE.md      ← New here? Start with this
├── server/                      The entire system (runs on the Jetson)
│   ├── main.py                  FastAPI app: /query /speak /feedback + web portal
│   ├── openai_client.py         Deterministic-first pipeline, gates, validator
│   ├── embeddings.py            ChromaDB client (local embeddings)
│   ├── ingest_jts.py            Guideline ingestion (PDF → chunks)
│   ├── clinical_router.py       Query → protocol routing
│   ├── build_protocol_index.py  Builds the router index from the knowledge base
│   ├── static/index.html        Web portal (served at the API root)
│   ├── run_tests.sh             24-case live-endpoint clinical suite
│   └── test_deterministic.py    Offline unit suite for parsers and gates
├── client/
│   ├── cdss_client.py           Voice client for edge devices
│   └── requirements.txt         Voice client dependencies
├── web/                         Project website (GitHub Pages)
├── docs/                        Current documentation + archive of prior versions
├── publications/                Articles and papers written by the project
├── jetson_cdss_setup_v2.sh      One-script Jetson deployment
└── requirements-server.txt      Server dependencies
```

## Quick start

**Just want to use it?** Open https://cdss.arcanekg.com — nothing to install. See the [First-Time Guide](START-HERE/FIRST_TIME_GUIDE.md).

**Run your own server** (Jetson Orin Nano or any Linux/macOS host):

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-server.txt

cp .env.example server/.env        # add OPENAI_API_KEY, CDSS_ACCESS_TOKEN
cd server
uvicorn main:app --host 0.0.0.0 --port 8000
curl localhost:8000/health         # {"status":"healthy", ...}
```

Ingest your guideline library (PDFs → searchable knowledge base):

```bash
python ingest_jts.py --pdf-dir ./data/your_protocols
python build_protocol_index.py     # builds the clinical router index
```

On a Jetson, `jetson_cdss_setup_v2.sh` performs the full deployment (packages, venv, systemd service) in one run.

**Test it:**

```bash
python server/test_deterministic.py   # offline unit suite — free, instant
bash server/run_tests.sh              # 24 clinical cases against the live endpoint
```

## Clinical knowledge base

- **Primary:** Joint Trauma System (JTS) Clinical Practice Guidelines — 89 protocols ingested into 8,559 passages with page-accurate citations
- **Embeddings:** computed on-device (all-MiniLM via ChromaDB) — zero per-query API cost, works with degraded connectivity
- **Ingestion:** sentence-aware chunking, header/footer stripping, idempotent re-runs (`server/ingest_jts.py`) — works with any PDF-based protocol library

## Validation status

- Automated clinical suite: **24/24** against the live public endpoint — pediatric weight gates, P1 safety blocks (sepsis-DCR, WPW, pediatric overdose, TXA-in-sepsis), RSI protocols, grounded scenarios
- Offline deterministic unit suite (`server/test_deterministic.py`) pins every parser and gate fix
- Active field beta with structured clinical feedback: severity triage, issue categories, protocol-cited corrections — reported failures are reproduced from audit logs and fixed with regression tests
- Prior-version evaluation history: [`docs/archive/v3/`](docs/archive/v3/)

## Documentation & publications

| Document | What it is |
|---|---|
| [`docs/TECH_NOTES_v4.0.md`](docs/TECH_NOTES_v4.0.md) | 4.0 technical release notes |
| [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) | Research positioning, design principles, references |
| [`docs/EdgeCDSS_v4_Technology.pdf`](docs/EdgeCDSS_v4_Technology.pdf) | Technology explainer |
| [`publications/`](publications/) | Articles and papers written by the project |
| [Ethics & Governance](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/ethics-governance.html) | Data privacy, responsible AI, governance |

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All contributions welcome — clinical, technical, and hardware.

**Clinical:** protocol review, scenario testing, safety gap identification
**Technical:** Python, FastAPI, RAG, prompt engineering, edge hardware
**Hardware:** off-grid comms, solar power, satellite connectivity, LoRa mesh

## License

MIT — see [`LICENSE`](LICENSE). Copyright (c) 2026 AI in Austere Medicine Project.

Technologies and provider names identify components used by the project and do not imply endorsement, sponsorship, or affiliation.

## Project links

- **Live portal:** https://cdss.arcanekg.com
- **Project site:** https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/
- **Organization:** https://github.com/AI-in-Austere-Medicine-Project
- **Newsletter:** https://aiamp.substack.com
