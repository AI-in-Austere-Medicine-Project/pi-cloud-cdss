# EdgeCDSS 4.0 — Technical Notes

AI in Austere Medicine Project — July 2026

- Live portal: https://cdss.arcanekg.com
- Release notes page: https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/release-notes-4.0.html
- Repository: https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss

---

## Overview

EdgeCDSS 4.0 is a self-hosted clinical decision support system for austere and prolonged field care. The full stack — knowledge base, retrieval engine, safety gates, web interface, feedback system, and audit logs — runs on a single NVIDIA Jetson Orin Nano. External access is provided by an outbound-only Cloudflare Tunnel. The deployment is network agnostic (Starlink, broadband, Wi-Fi, Ethernet, LTE/5G).

AI is restricted to language generation, retrieval support, and semantic validation. All medication calculations, contraindication checks, routing, patient-context handling, and safety gating are performed by deterministic Python code.

## Architecture

Pipeline: `Knowledge → Logic → AI → Validation → Human`

1. **Pre-generation gates (deterministic).** 13 gates run before any AI call: confirmed-weight requirement, route confirmation, pediatric limits, requested-overdose detection, and absolute contraindications. Many queries resolve here with no AI involvement.
2. **Patient context (deterministic).** Structured state (confirmed vs. estimated weight, age, access, route preference) is rebuilt from the full conversation on every request. Estimated weight is never used for dosing.
3. **Retrieval (on-device).** 89 JTS Clinical Practice Guidelines ingested into 8,559 passages (sentence-aware chunking, header/footer stripping, page-accurate metadata). Embeddings are computed locally; retrieval has zero per-query API cost. A clinical router (LLM-built protocol index) enhances search queries before retrieval.
4. **Generation (AI).** The LLM receives retrieved guideline text plus an ALLOWED_DOSES contract computed in Python. The model is prohibited from performing medication math.
5. **Post-checks (deterministic).** Generated GIVE lines are parsed and every stated dose is verified against the contract. Non-matching doses are blocked.
6. **Validation (AI + deterministic gate).** A narrow semantic validator reviews each draft. Failures produce a safety hold (fail-closed). Structured false-positive overrides are implemented in code from observed field reports.

## Changes in 4.0

### Architecture
- Deterministic-first rebuild: dose math, gates, and safety decisions moved from prompts into code
- ALLOWED_DOSES contract generation and deterministic post-check enforcement
- Structured PatientContext with confirmed/estimated weight separation
- Clinical router (protocol_index.json) for query-to-protocol matching
- Fail-closed safety gate with structured false-positive overrides
- Session audit logger (JSONL per query, no PHI)
- `EDGECDSS_DEBUG_WARN_ONLY` env flag: fail-closed logic is never hand-edited for debugging

### Deployment
- Full migration from cloud VM (GCP) to NVIDIA Jetson Orin Nano (JetPack 6 / Ubuntu, aarch64)
- Public access via Cloudflare Tunnel (outbound-only; no open ports, no exposed IP)
- Services systemd-managed with automatic restart; health watchdog with escalating recovery
- Knowledge base re-ingested on device: 89 CPGs → 8,559 chunks (previous: 7,186)

### Interface and evaluation
- Web portal served from the device: conversation memory, source citations, validator status
- Structured clinical feedback on every response: severity triage (minor / significant / dangerous-if-followed), issue categories, protocol-cited corrections
- Patient facts persist across the full conversation; clinical events windowed to recent turns
- TTS pronunciation normalization for clinical notation (units, concentrations, routes, acronyms)
- Automated regression suite: 24/24 passing against the live endpoint

## Stack

| Layer | Technology |
|---|---|
| Edge compute | NVIDIA Jetson Orin Nano Super 8GB, JetPack 6, NVMe SSD |
| API server | FastAPI + Uvicorn (Python 3.12) |
| Vector database | ChromaDB (on-device, local embeddings) |
| Generation / validation | OpenAI gpt-4o-mini (swappable; cross-model comparison planned) |
| Routing | protocol_index.json (LLM-built, deterministically matched) |
| Connectivity | Network agnostic; Cloudflare Tunnel (outbound-only HTTPS) |
| TTS | ElevenLabs (isolated from clinical core; degrades gracefully) |
| Hosting (site) | GitHub Pages |

## Cost profile

| Item | Cost |
|---|---|
| Jetson Orin Nano Super dev kit | $249 one-time |
| NVMe SSD | ~$50 one-time |
| Satellite connectivity (where used) | $120–150 / month |
| LLM API at evaluation volume | < $5 / month |
| TTS | $0–6 / month |
| Tunnel / DNS | $0 (+ ~$10/yr domain) |

## Testing

- 24-case automated clinical suite run against the live public endpoint: pediatric weight gates, P1 safety blocks (sepsis-DCR, WPW, pediatric overdose, TXA-in-sepsis), RSI protocols, grounded clinical scenarios
- Structured field feedback and session audit logs make reported failures reproducible; fixes ship with regression tests

## Known limitations

- Decision support only; presumes a trained provider, clinical judgment, and local protocol
- Research prototype evaluated with simulated and synthetic scenarios only; not validated for clinical use
- Language generation requires connectivity to a cloud model; fully offline on-device inference is a research goal (Project 02)
- Knowledge base reflects the JTS CPGs as published

## Disclaimers

Research prototype — not validated for clinical use — not for patient care decisions — simulated and synthetic scenarios only. Do not enter PHI or real patient information into any project system. All code is MIT licensed. Provider and technology names identify components used by the project and do not imply endorsement, sponsorship, or affiliation.
