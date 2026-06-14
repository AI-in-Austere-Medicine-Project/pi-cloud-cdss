# EdgeCDSS — AI-Powered Clinical Decision Support for Austere Medicine

**AI in Austere Medicine Project (AI-AMP)**
Open source. Built in the field. Safety shared.

> ⚠️ **Research Prototype** — Not validated for clinical use. Not for patient care decisions. Do not enter patient names, dates of birth, or identifying information into this system.

---

## What This Is

EdgeCDSS is a hybrid cloud-edge clinical decision support system designed for austere, resource-limited, and remote medical environments. It delivers voice-accessible, protocol-driven clinical guidance with all medication dosing resolved to final mL volumes — zero math for the field provider.

**Current version: v3.0.0** — Two-pass safety architecture  
**Live demo online status :** https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/  


---

## Architecture

```
Voice/Text Query
      ↓
Edge Device (Radxa Zero 3W / Raspberry Pi 4)
      ↓
ChromaDB RAG — 89 JTS CPGs, 7,186 semantic chunks
      ↓
Pass 1 — GPT-4o-mini (AUSTERE-CDS generator)
      ↓
Pass 2 — GPT-4o-mini (Clinical Safety Validator, temp=0)
      ↓
Gate: SAFE → deliver | UNSAFE → block | NEEDS_HUMAN_REVIEW → append warning
      ↓
ElevenLabs TTS → provider earpiece
```

---

## Repository Structure

```
pi-cloud-cdss/
├── START-HERE/                  ← New here? Start with this
│   └── FIRST_TIME_GUIDE.md
├── server/
│   ├── main.py                  FastAPI backend
│   ├── openai_client.py         Two-pass LLM pipeline
│   └── embeddings.py            ChromaDB client
├── web/
│   └── index.html               Web testing interface (GitHub Pages)
├── client/
│   ├── cdss_client.py           Edge device voice client
│   └── client.py                Thin client
├── tests/
│   ├── test_cdss.py             34-case automated test suite
│   └── results/                 Test run outputs
├── docs/
│   ├── EdgeCDSS_v25_Summary.pdf
│   ├── EdgeCDSS_v30_Goals.pdf
│   ├── EdgeCDSS_FieldEvaluationReport_v1.pdf
│   ├── EdgeCDSS_ProjectOverview.pdf
│   └── AILM_Resources_Reference.pdf
├── README.md
├── TODO.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                      MIT
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Quick Start

**Prerequisites:** Python 3.10+, OpenAI API key, GCP VM (or local FastAPI server)

```bash
# Clone
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss

# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your OPENAI_API_KEY and CDSS_ACCESS_TOKEN to .env

# Run the server
cd server
uvicorn main:app --host 0.0.0.0 --port 8000

# Test
python3 tests/test_cdss.py
```

See `START-HERE/FIRST_TIME_GUIDE.md` for full setup instructions.

---

## Safety Architecture (v3.0)

v3.0 introduced a two-pass safety pipeline. Every LLM-generated response passes through an independent safety validator before reaching the provider.

**Validator checks:**
- Pediatric dosing ceiling violations (ketamine >2mg/kg, rocuronium >1.2mg/kg)
- Contraindicated drugs (adenosine in WPW, high-flow O2 in COPD)
- CICO pathway — failed ETT + failed supraglottic = surgical airway required
- Sepsis/DCR misclassification — fever + infection ≠ hemorrhagic shock
- Route mismatch, missing post-intubation sedation, paralytic without sedation

**Gate logic:**
- `SAFE` — response delivered
- `UNSAFE` — response blocked, safety hold message delivered
- `NEEDS_HUMAN_REVIEW` — warning appended to response

---

## Clinical Knowledge Base

- **Primary:** Joint Trauma System (JTS) Clinical Practice Guidelines — 89 protocols, 7,186 indexed chunks
- **Secondary:** Evidence-based guidance for non-JTS presentations (sepsis, tropical disease, envenomation, obstetrics, environmental emergencies)
- **Embeddings:** OpenAI text-embedding-ada-002 via ChromaDB

---

## v2.5 Evaluation Summary

| Metric | Result |
|---|---|
| Automated test pass rate | 85.3% (29/34 cases) |
| External testers | 26 unique devices |
| Feedback entries | 70 |
| Helpful rate | 61% |
| P1 safety gaps identified | 3 (all fixed in v3.0) |
| Mean response time | 2,836ms |

Full evaluation report: `docs/EdgeCDSS_FieldEvaluationReport_v1.pdf`

---

## Infrastructure

| Component | Technology |
|---|---|
| Cloud VM | GCP e2-medium (arcaneone) |
| API framework | FastAPI + Python |
| Vector database | ChromaDB |
| LLM | GPT-4o-mini (two-pass) |
| TTS | ElevenLabs API |
| Edge hardware | Radxa Zero 3W / Raspberry Pi 4 |
| Connectivity | Starlink primary / T-Mobile 5G failover |
| Hosting | GCP + GitHub Pages |
| DNS | DuckDNS + Let's Encrypt SSL |

---

## Contributing

See `CONTRIBUTING.md`. All contributions welcome — clinical, technical, and hardware.

**Clinical:** Protocol review, scenario testing, safety gap identification  
**Technical:** Python, FastAPI, prompt engineering, ChromaDB, edge hardware  
**Hardware:** Off-grid comms, solar power, Iridium satellite, LoRa mesh  

---

## License

MIT — see `LICENSE`

Copyright (c) 2026  AI in Austere Medicine Project

---

## Project Links

- **Organization:** https://github.com/AI-in-Austere-Medicine-Project
- **Web demo:** https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/
- **Research docs:** `/docs`
- **Newsletter:** https://aiamp.substack.com
