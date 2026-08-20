# EdgeCDSS 4.1 — Technical Notes

AI in Austere Medicine Project — August 2026

- Live portal: https://cdss.arcanekg.com
- Release notes page: https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/release-notes-4.1.html
- Repository: https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss
- Full changelog: [CHANGELOG.md](../CHANGELOG.md) · Deferred findings and residual risk: [TODO.md](../TODO.md)
- Prior release: [TECH_NOTES_v4.0.md](TECH_NOTES_v4.0.md) — superseded by this document
- Project overview & research positioning: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

---

## Overview

EdgeCDSS 4.1 is a hardening release. It adds no clinical capability. The deployment, stack, and cost profile are unchanged from 4.0; what changed is the safety plumbing between the checks 4.0 already had.

4.0 shipped a two-pass safety architecture — deterministic checks before generation, a semantic validator after. 4.1 is the result of auditing what that architecture actually did in the field: 135 logged queries across 14 session days, plus 26 structured feedback entries. The architecture held at detection and leaked at enforcement. The validator identified the problems; the code beneath it discarded the warnings, served responses it had flagged, and recorded verdicts that did not match what the provider saw.

Ten defects were fixed, each with a regression test built from the log line that exposed it.

## Architecture

Pipeline: `Knowledge → Logic → AI → Validation → Human`

Unchanged from 4.0 in shape. Steps 2, 5 and 6 below are corrected — in 4.0's notes they described intended behaviour that the code did not implement.

1. **Pre-generation gates (deterministic).** 13 gates run before any AI call: confirmed-weight requirement, route confirmation, pediatric limits, requested-overdose detection, and absolute contraindications. Many queries resolve here with no AI involvement.
2. **Patient context (deterministic).** Structured state (confirmed vs. estimated weight, age, access, route preference) is re-derived on every request from the conversation history, and **cleared at a detected patient boundary** — an explicit phrase, a presentational opener, a contradicting age or weight, or inactivity past `CDSS_PATIENT_TIMEOUT_MIN` (default 30 minutes). Every reset is announced in the response. Estimated weight is never used for dosing. The pediatric flag is re-derived per turn rather than latched.
3. **Retrieval (on-device).** 89 JTS Clinical Practice Guidelines ingested into 8,559 passages (sentence-aware chunking, header/footer stripping, page-accurate metadata). Embeddings are computed locally; retrieval has zero per-query API cost. A clinical router (LLM-built protocol index) enhances search queries before retrieval, **matching alias terms on word boundaries**.
4. **Generation (AI).** The LLM receives retrieved guideline text plus an ALLOWED_DOSES contract computed in Python. The model is prohibited from performing medication math, and the weight-free protocol block that accompanies the contract carries no numeric doses.
5. **Post-checks (deterministic).** Generated GIVE lines are parsed and every stated dose is verified against the contract. **An empty contract blocks every canonical dosing line** rather than skipping the check: no confirmed weight means no dose was authorised, for adult and pediatric patients alike.
6. **Validation (AI + deterministic gate).** A narrow semantic validator reviews each draft. Failures produce a safety hold (fail-closed). Structured false-positive overrides, held in a named registry, **downgrade a response to human review and preserve the validator's issue list** — an override cannot release a blocked response. The verdict served, the verdict logged, and the verdict the validator reached are one value produced in one place. An unsafe verdict carrying no structured issue fails closed.

## Changes in 4.1

### Safety
- Patient context is cleared at a detected patient boundary, applied per turn during history replay, and the reset is announced to the provider (audit S-1)
- Safety-gate overrides downgrade instead of releasing; the fired override is recorded by name; the validator's issues survive into the audit log (audit S-2)
- The gate fails closed when handed an unsafe verdict with no structured issue, rather than pattern-matching overrides against the validator's free-text rationale
- An empty dose contract hard-blocks canonical dosing lines for adults as well as pediatric patients (audit S-3)
- `is_pediatric` is re-derived each turn instead of latching true for the remainder of a session
- The hard-coded maintenance dose was removed from the weight-free protocol block; a meta-test fails if any protocol string reintroduces a dose token

### Quality
- Ventilator-settings queries no longer dispatch into the RSI paralytic pre-gate; genuine post-intubation phrasings still route to RSI (audit S-4)
- The clinical router's alias table matches on word boundaries — 143 spurious matches removed across 80 of 135 audited queries, with no aliases deleted (audit F-2)

### Observability
- Session JSONL gains `pipeline_ms`, `synthetic`, `override_fired`, and `boundary_reset`, stamped `log_schema: 2`
- The live clinical suite tags its requests, making test traffic distinguishable from field traffic — 48 of the 135 audited entries were test runs previously indistinguishable from real use
- The synthetic tag is self-declared and deliberately load-bearing on nothing; a test asserts the pipeline behaves identically with and without it

### Deployment safety
- Numeric environment knobs fall back to their defaults on unparseable values and announce the rejection, instead of raising. One knob is read at module scope, where a typo previously prevented import, left `/health` unanswered, and put the device into a watchdog reboot loop

### Test infrastructure
- `openai_client` imports without the OpenAI SDK or an API key, which is what makes an offline suite possible
- Offline regression suite added: `server/run_unit_tests.sh`

## Stack

Unchanged from 4.0.

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

Unchanged from 4.0 — see [TECH_NOTES_v4.0.md](TECH_NOTES_v4.0.md#cost-profile). Compute is a one-time ~$300; recurring cost is dominated by connectivity, not by AI.

## Testing

- **Offline regression suite: 105 tests, ~2s** (`server/run_unit_tests.sh`) — no network, no API key, no ChromaDB. Runs on a clean checkout. This is the gate for every change to the deterministic layer
- 24-case automated clinical suite run against the live public endpoint: pediatric weight gates, P1 safety blocks (sepsis-DCR, WPW, pediatric overdose, TXA-in-sepsis), RSI protocols, grounded clinical scenarios
- Convention for safety-relevant fixes: **one fix, one commit, one regression test**, plus a mutation check — revert the fix, confirm the named test fails, restore — recorded in the commit message
- Structured field feedback and session audit logs make reported failures reproducible

**What the suite deliberately does not assert.** The validator is non-deterministic: identical input can produce opposite verdicts. No offline test pins what verdict the validator *produces* — only what the gate does with one. This bounds what the suite can prove and is a known limitation, not an oversight.

## Known limitations

Carried from 4.0:

- Decision support only; presumes a trained provider, clinical judgment, and local protocol
- Research prototype evaluated with simulated and synthetic scenarios only; not validated for clinical use
- Language generation requires connectivity to a cloud model; fully offline on-device inference is a research goal (Project 02)
- Knowledge base reflects the JTS CPGs as published

Introduced or left open by 4.1 — the full list, with the residual risk of each, is in [TODO.md](../TODO.md):

- **Helpfulness regression.** A provider asking about status epilepticus with no weight on file now receives a safety hold where a weight-free protocol answer would serve them better. Fail-closed is the intended trade; this is a real cost of it and is being watched in post-release feedback
- **Weight corrections trip the boundary detector.** Correcting a weight on the same patient clears the context. The detector cannot distinguish a correction from a new patient. Accepted because the reset is announced; the alternative is trusting the older weight, which is the S-1 defect
- **The knowledge base is trauma-scoped.** Providers bring DKA, angioedema, tropical infectious disease and dysrhythmia questions to a corpus of 89 JTS trauma CPGs. The most frequent provider complaint — that the system declines questions — is driven partly by this and partly by generator-side refusal behaviour, and **4.1 does not measurably improve it**
- **Audit log response previews are truncated at 200 characters.** Every content-based measurement in the v4.1 audit is therefore a lower bound; a dosing line past that offset is invisible to analysis
- **Log schema migration.** Pre-4.1 entries carry no `log_schema` key and none of the new fields. Analysis tooling must treat a missing key as unknown, never as a default — defaulting an absent `synthetic` to false would reclassify 48 known test entries as field traffic

## Disclaimers

Research prototype — not validated for clinical use — not for patient care decisions — simulated and synthetic scenarios only. Do not enter PHI or real patient information into any project system. All code is MIT licensed. Provider and technology names identify components used by the project and do not imply endorsement, sponsorship, or affiliation.
