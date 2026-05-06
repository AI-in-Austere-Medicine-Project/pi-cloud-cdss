# EdgeCDSS — Hybrid Cloud-Edge Clinical Decision Support System

> AI-powered clinical decision support for austere, resource-limited, and remote medical environments.
> Open source. Built for the field, not the hospital.

[![Research Prototype](https://img.shields.io/badge/status-research%20prototype-red)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![GitHub Pages](https://img.shields.io/badge/demo-live-green)](https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/)

---

## ⚠️ Important Disclaimer

**EdgeCDSS is an active research project. It has not been validated for clinical use and must not be used to make patient care decisions.** All responses are AI-generated and should be treated as reference material only. Always follow your training, institutional protocols, and the judgment of qualified medical personnel.

---

## Overview

Low-income countries, conflict zones, and austere environments carry the highest burden of preventable medical mortality — and the least access to the technology being built to address it.

EdgeCDSS is the first project under the **AI in Austere Medicine** research initiative. It delivers voice-accessible, protocol-driven clinical decision support on a $35 edge device, with responses in under 3 seconds. The system resolves all medication dosing to final mL volumes — the provider does zero arithmetic.

The system operates across two knowledge domains:

- **JTS Clinical Practice Guidelines** — 89 indexed protocols, 7,186 semantic chunks, retrieved via vector search
- **General Evidence-Based Medicine** — LLM parametric knowledge for out-of-scope presentations (tropical disease, envenomation, infectious illness), clearly attributed as outside JTS scope

---

## Live Demo

**Web interface:** - optional 

- Voice input via Web Speech API (Chrome recommended)
- Text response display
- Feedback and flagging system
- 10 queries per 24 hours per device

---

## Architecture
┌─────────────────────────────────────────────────────────────┐
│                     EDGE CLIENT                              │
│  Radxa Zero 3W / Raspberry Pi 4                             │
│  cdss_client.py — voice I/O, lbs→kg conversion, TTS        │
└─────────────────┬───────────────────────────────────────────┘
│ HTTPS / REST
┌─────────────────▼───────────────────────────────────────────┐
│                  CLOUD BACKEND (arcaneone)                   │
│  GCP e2-medium — nginx reverse proxy — FastAPI              │
│  ChromaDB vector search — GPT-4o-mini inference             │
│  Rate limiting — feedback logging — ElevenLabs TTS          │
└─────────────────┬───────────────────────────────────────────┘
│
┌─────────────────▼───────────────────────────────────────────┐
│                  KNOWLEDGE BASE                              │
│  89 JTS Clinical Practice Guidelines                        │
│  7,186 semantic chunks — OpenAI embeddings                  │
└─────────────────────────────────────────────────────────────┘
**Connectivity tiers (graceful degradation):**
1. Broadband satellite (Starlink) — full cloud inference + voice TTS
2. Narrowband satellite (BGAN/Iridium Certus) — cloud inference
3. SMS/data-limited — abbreviated text protocol lookups
4. Fully offline — local edge LLM via Jetson Orin Nano *(planned)*

---

## Repository 
pi-cloud-cdss/
├── cdss_client.py          # Radxa/Pi thin client — voice I/O, TTS
├── boot.sh                 # Auto-update boot script with offline fallback
├── edgecdss.service        # systemd service unit
├── test_cdss.py            # Automated evaluation suite (34 test cases)
├── requirements.txt        # Client dependencies
├── server/
│   ├── main.py             # FastAPI backend — rate limiting, CORS, feedback
│   └── openai_client.py    # GPT-4o-mini system prompt + RAG pipeline
├── web/
│   └── index.html          # Voice web interface — GitHub Pages hosted
├── docs/
│   ├── EdgeCDSS_ProofOfConcept.pdf
│   └── EdgeCDSS_Architecture.pdf
├── CHANGELOG.md
├── TODO.md
└── README.md
---

## Evaluation Results

Automated test suite (test_cdss.py) — 34 cases across 9 categories:

| Category | Pass Rate |
|---|---|
| Damage Control Resuscitation | 100% |
| ARDS / Ventilation | 100% |
| Traumatic Brain Injury | 100% |
| Sedation / Analgesia | 100% |
| Weight Conversion | 100% |
| Non-JTS Clinical Queries | 100% |
| Edge Cases | 100% |
| Format Compliance | 100% |
| Natural Language | 60% |
| **Overall** | **94.1%** |

**Mean response time: 2,836ms** — suitable for real-time field use.

---

## Getting Started

### Cloud Backend

Requires: GCP VM, OpenAI API key, ElevenLabs API key

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
pip install -r requirements.txt
cp .env.example .env  # add your API keys
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### Edge Client (Radxa Zero 3W / Raspberry Pi)

```bash
git clone https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss.git
cd pi-cloud-cdss
pip install -r requirements.txt
cp .env.example .env  # add CDSS_SERVER_URL and ELEVENLABS_API_KEY
python3 cdss_client.py
```

### Environment Variables
OPENAI_API_KEY=your-key
ELEVENLABS_API_KEY=your-key
CDSS_ACCESS_TOKEN=your-token
CDSS_SERVER_URL=https://your-server-url
DEVICE_ID=your-device-id
---

## Running the Evaluation Suite

```bash
export CDSS_SERVER_URL=https://your-server-url
export CDSS_ACCESS_TOKEN=your-token
python test_cdss.py

# Soak test — 3 cycles
python test_cdss.py 3 1
```

---

## Contributing

This is an open research project. Contributions are welcome.

- **Clinical accuracy** — flag incorrect protocol responses via the web interface or open an issue
- **Protocol expansion** — help ingest additional clinical guideline sets
- **Edge hardware** — test on new hardware platforms and document results
- **Offline inference** — Jetson Orin Nano local LLM integration
- **Code** — see open issues for current priorities

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting a pull request.

---

## Documentation

- [Proof of Concept Report](docs/EdgeCDSS_ProofOfConcept.pdf)
- [System Architecture](docs/EdgeCDSS_Architecture.pdf)
- [Development Roadmap](TODO.md)
- [Changelog](CHANGELOG.md)

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Project

**AI in Austere Medicine Project**
github.com/AI-in-Austere-Medicine-Project

*Guideline-based support only. Not a substitute for clinical judgment.*
