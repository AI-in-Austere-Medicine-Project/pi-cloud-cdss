# EdgeCDSS — Clinical Decision Support for Austere Medicine

**AI in Austere Medicine Project (AI-AMP)**
Open source. Edge deployed. Safety findings published.

> ⚠️ **Research prototype** — not validated for clinical use, not for patient care decisions. Simulated and synthetic scenarios only. Do not enter PHI, patient names, or identifying information into any project system.

**Current release: 4.1.0** · [Release notes](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/release-notes-4.1.html) · [Technical notes](docs/TECH_NOTES_v4.1.md) · [Changelog](CHANGELOG.md) · [Project site](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/)

---

## What this is

EdgeCDSS is a self-hosted clinical decision support system for austere, remote, and resource-limited environments. A provider describes a casualty in plain field language — by text or voice — and receives structured, guideline-cited guidance in seconds, with every medication dose resolved to a final mL draw. Zero math for the field provider.

The entire system — knowledge base, retrieval engine, safety gates, web interface, feedback system, and audit logs — runs on a single **NVIDIA Jetson Orin Nano** at the point of care. Public access flows through an outbound-only Cloudflare Tunnel. The deployment is network agnostic: satellite, broadband, Wi-Fi, Ethernet, or LTE/5G.

**Try it:** the live portal is at **https://cdss.arcanekg.com** (demo access token is pre-filled in the interface).

## What's new in 4.1

A hardening release with no new clinical features. Every fix came from auditing 135 real
field queries across 14 session days — not from the test suite, which passed throughout.

- **Patient context resets at the patient boundary, and says so.** Context accumulated
  across a whole conversation with no notion of the patient changing, so one patient's
  weight could reach another patient's dose calculation. Boundaries are now detected and
  the reset is announced in the response. 9 fire across the audited corpus, zero false
  positives.
- **The served verdict and the logged verdict are the same value.** False-positive
  overrides released responses while the log recorded them blocked, discarding the
  validator's objections. Overrides now downgrade to human review and preserve the issue
  list. Pinned by a 216-case invariant: a served response can never be logged unsafe.
- **An empty dose contract blocks dosing lines instead of skipping the check.** No
  confirmed weight means nothing was authorised — previously the state in which the
  check was skipped entirely.
- **Retrieval and routing fixes.** Ventilator-settings queries no longer route into the
  intubation drug bundle; the clinical router matches whole words, removing 143 spurious
  alias matches across 80 of 135 queries.
- **Logs distinguish test traffic from field traffic**, and record latency, boundary
  resets, and which override fired. 48 of the 135 audited entries turned out to be test
  runs indistinguishable from real use.
- **A mistyped tuning value can no longer prevent startup** — previously a config typo
  could put the device into a reboot loop behind an outbound-only tunnel.

Full detail in [`CHANGELOG.md`](CHANGELOG.md); what 4.1 knowingly deferred, and the
residual risk of each deferral, in [`TODO.md`](TODO.md).

## Architecture

Pipeline principle: **never ask an AI a question that code can answer.**

```
Query (text or voice)
      ↓
13 deterministic pre-gates ── weight, route, pediatric limits, contraindications
      ↓                       (many queries resolve here in milliseconds, no AI)
Patient context ───────────── rebuilt deterministically each turn; cleared and
      ↓                       announced at a patient boundary
Clinical router ───────────── protocol index aims retrieval at the right CPG
      ↓
On-device RAG ─────────────── 89 JTS CPGs / 8,559 chunks, local embeddings
      ↓
LLM generation ────────────── receives an ALLOWED_DOSES contract computed in
      ↓                       Python; prohibited from doing medication math
Deterministic post-checks ─── every stated dose verified against the contract
      ↓
LLM validator + gate ──────── narrow semantic check; fail-closed on any doubt.
      ↓                       A false-positive override downgrades to human
      ↓                       review — it can never release a blocked response
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
│   ├── run_unit_tests.sh        Offline regression suite (105 tests, ~2s)
│   └── test_*.py                Offline suites: deterministic parsers/gates,
│                                safety gate, patient boundary, routing and
│                                aliases, log contract, env config
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
cd server && ./run_unit_tests.sh   # 105 offline tests, ~2s — no network, no API key, no ChromaDB
bash server/run_tests.sh           # 24 clinical cases against the live endpoint
```

The offline suite is the gate for every change to the deterministic layer. It needs
no key and no vector database, so it runs on a clean checkout in CI or on a laptop.

## Clinical knowledge base

- **Primary:** Joint Trauma System (JTS) Clinical Practice Guidelines — 89 protocols ingested into 8,559 passages with page-accurate citations
- **Embeddings:** computed on-device (all-MiniLM via ChromaDB) — zero per-query API cost, works with degraded connectivity
- **Ingestion:** sentence-aware chunking, header/footer stripping, idempotent re-runs (`server/ingest_jts.py`) — works with any PDF-based protocol library

### Answer sources

Every answer says where it came from, on screen and in the session log.

| Source | When | Label |
|---|---|---|
| **JTS** | A JTS protocol was retrieved, or a deterministic protocol card fired | none — this is the default |
| **General reference** | Retrieval found nothing usable, and the query is not a dosing question | `GENERAL MEDICAL REFERENCE — not from JTS protocols`, plus a spoken disclosure |

General reference covers lab values, toxicology, envenomation and plant/snake
identification, preparation recipes, and basic clinical reference — the tier a
medic would otherwise look up on a phone. It is a second knowledge source, not a
second pipeline: general answers pass through the same deterministic checks,
validator and safety gate as every JTS answer.

**Recipe yes, prescription no.** A standardized preparation ("1 mg in 250 mL NS
= 4 mcg/mL") is reference knowledge. A patient dose is not, and never comes from
general knowledge — dosing questions stay on the ALLOWED_DOSES contract path,
which either produces a deterministic line or holds.

## Choosing a model

Models are configuration, not code. `server/providers.json` holds the registry;
edit it and restart. Nothing in `openai_client.py` names a model.

```jsonc
{
  "default_model":   "gpt-4o-mini",   // what the client gets unless it asks otherwise
  "validator_model": "gpt-4o-mini",   // the safety validator — see below
  "models": [
    { "id": "claude-sonnet-5", "provider": "anthropic", "label": "Claude Sonnet 5",
      "supports_temperature": false,  // Opus 5 / Sonnet 5 reject sampling params
      "effort": "low",                // Anthropic output_config.effort
      "reserve_tokens": 3000 }        // headroom so reasoning cannot starve the answer
  ]
}
```

Set keys in `server/.env` — `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. A provider
with no key, the wrong provider's key, or a key that fails a real auth check is
absent from the dropdown, and `/status` and `/models` carry a `provider_detail`
field saying which of those it was. Keys are never logged or echoed.

`CDSS_DEFAULT_MODEL` and `CDSS_VALIDATOR_MODEL` override the config from the
environment, for A/B runs without editing the file.

**Adding a local model** is a config entry and no code. Point a provider at an
OpenAI-compatible endpoint:

```bash
CDSS_LOCAL_BASE_URL=http://127.0.0.1:11434/v1     # Ollama, llama.cpp, vLLM
```

then add a `models` entry with `"provider": "local"`.

**The validator does not follow the dropdown.** It stays on `validator_model` so
that a cross-model comparison changes one variable. If the generator and the
validator both moved, a shift in blocked-response rate could not be attributed
to either. Change `validator_model` when the validator is the thing being
measured.

## Validation status

- Offline regression suite: **105 tests, ~2s** (`server/run_unit_tests.sh`) — no network, no API key, no ChromaDB. Every v4.1 fix is pinned by a test built from the log line that exposed it
- Automated clinical suite: **24 cases** against the live public endpoint — pediatric weight gates, P1 safety blocks (sepsis-DCR, WPW, pediatric overdose, TXA-in-sepsis), RSI protocols, grounded scenarios
- Convention for safety-relevant fixes: **one fix, one commit, one regression test**, plus a mutation check — revert the fix, confirm the named test fails, restore — recorded in the commit message
- Active field beta with structured clinical feedback: severity triage, issue categories, protocol-cited corrections — reported failures are reproduced from audit logs and fixed with regression tests
- Prior-version evaluation history: [`docs/archive/v3/`](docs/archive/v3/)

## Documentation & publications

| Document | What it is |
|---|---|
| [`CHANGELOG.md`](CHANGELOG.md) | Full release history, including the complete 4.1 entry |
| [`TODO.md`](TODO.md) | Roadmap, and every audit finding 4.1 knowingly deferred with its residual risk |
| [`docs/TECH_NOTES_v4.1.md`](docs/TECH_NOTES_v4.1.md) | **Current** technical notes — architecture, changes in 4.1, testing, known limitations |
| [`docs/TECH_NOTES_v4.0.md`](docs/TECH_NOTES_v4.0.md) | 4.0 technical notes (superseded; kept as the record of what 4.0 claimed) |
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
