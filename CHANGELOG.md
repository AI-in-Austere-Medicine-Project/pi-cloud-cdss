# EdgeCDSS Changelog

## [1.6.1] - 2026-05-03
### Client (cdss_client.py)
- Fixed: Correct thin client restored — was accidentally overwritten with server code
- Fixed: SERVER_URL reads from .env only — no hardcoded IP
- Added: lbs to kg auto-conversion for patient safety
- Added: Non-blocking async TTS — prompt returns immediately
- Added: pygame output suppressed, audio timeout prevents hanging
- Added: TTS medical term expansion — acronyms, units, concentrations
- Added: Number-attached unit pronunciation (500mg → 500 milligrams)
- Added: Voice speed control (0.85x)

## [2.2.0] - 2026-05-03
### Backend (server/openai_client.py)
- Switched: GPT-4 → GPT-4o-mini (9x speed improvement: 23s → 2.8s avg)
- Added: ZERO MATH RULE — all dosing resolved to final mL, no provider math
- Added: Dual response format — JTS structured vs non-JTS concise
- Added: TLDR section on all responses
- Added: Knowledge source handling — flags when outside JTS scope
- Added: Non-medical query redirect
- Added: Natural language recognition — lay terms mapped to protocols
- Added: Mandatory disclaimer enforcement
- Added: P:F ≤100 = SEVERE ARDS explicit rule
- Added: Calcium chloride CENTRAL LINE ONLY enforcement
- Added: TXA >3 hours = DO NOT GIVE absolute rule
- Added: Steroids/albumin in TBI absolute prohibition
- Added: Drip rate and ventilator mL calculation rules
- Added: Weight conversion silent rule (lbs → kg)

## [1.3.1] - 2026-05-03
### Test Suite (test_cdss.py)
- Added: Automated test suite v1.3.1 — 34 test cases
- Added: Natural language test cases (NL-001 through NL-005)
- Added: lbs preprocessing to mirror cdss_client.py behavior
- Fixed: dotenv path loading with pathlib
- Fixed: Test strings to match actual response language
- Result: 94.1% pass rate, 2,836ms avg response time

## [1.0.0] - 2026-04-21
### Initial Release
- FastAPI cloud backend with ChromaDB vector database
- JTS CPG knowledge base — 89 protocols, 7,186 chunks indexed
- Radxa Zero 3W thin client deployment
- ElevenLabs TTS with wake word detection
- WireGuard VPN integration
- Tiered connectivity architecture (Starlink/BGAN/Iridium/Offline)
- Auto-update boot script with network fallback
- Systemd service for auto-launch on boot