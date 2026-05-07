# EdgeCDSS Changelog

## [2.5.0] - 2026-05-07

### Clinical Accuracy (System Prompt v2.4.1)
- Sepsis vs hemorrhagic shock differentiation — system now identifies shock etiology before DCR
- TXA strict indications — hemorrhagic shock only, explicit contraindication list
- Hypothermia dedicated protocol — correct rewarming, hypothermic arrest rules, "not dead until warm"
- WPW contraindications — adenosine/AV nodal blockers explicitly prohibited
- Pediatric rules — age/weight-based detection, pediatric VT calculation, weight-based dosing
- Pediatric drowning protocol — 5 rescue breaths before CPR
- Sepsis Hour-1 bundle — antibiotics within 45 min, vasopressors, source control
- Multi-part query rule — system must answer ALL parts of complex queries
- Resource-constrained queries — work within stated provider inventory
- LTOWB explicit — all hemorrhage responses now use LTOWB by name
- Ketamine zero math — mg/kg prohibited in all ketamine responses
- Outside JTS scope attribution — mandatory phrase in all non-JTS responses
- Lorazepam by name — seizure first line always states Lorazepam explicitly
- No-weight strict enforcement — no dosing of any kind without confirmed weight

### Infrastructure
- Rate limiting removed — server on/off manually controlled
- Custom maintenance page — personalized offline message via nginx 502/503
- Conversation memory — last 5 exchanges passed to GPT per patient session
- Memory reset — voice command "new patient", button, 30min inactivity timeout
- New Patient button added to web interface header

### Evaluation
- Automated test suite pass rate: 85.3% (29/34) — up from 61.8%
- Field evaluation report v1.1 published to docs/
- 32 feedback entries analyzed across 6 testers
- Critical gaps identified: WPW dangerous flag, pediatric vent VT, sepsis/DCR confusion

### Web Interface
- Conversation history display — all exchanges shown in scrollable thread
- Context indicator — shows number of active exchanges in memory
- Voice commands — "new patient" / "reset" / "clear" trigger patient context reset
- Feedback buttons on every response — helpful, incorrect, dangerous, comment
- Rate limit display removed from UI (server-controlled)

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

# EdgeCDSS Changelog

## [2.1.0] - 2026-05-05

### Web Interface
- Added voice web interface hosted on GitHub Pages
- Voice-to-text input via Web Speech API
- Text response display with markdown formatting
- Feedback system: helpful, incorrect, dangerous, comment
- Rate limiting: 10 queries per IP per 24 hours (client + server side)
- Disclaimer banner — research prototype, not for clinical use
- Maintenance page via nginx — shown when backend is offline

### Backend (server/main.py)
- Added CORS middleware for GitHub Pages domain
- Added rate limiting — 10 queries per IP per 24 hours
- Added X-Access-Token authentication on all endpoints
- Added /feedback endpoint — logs to feedback.log
- Added /feedback/summary endpoint — token protected
- Added /speak endpoint — server-side ElevenLabs TTS (dormant in web interface)
- Added 502/503 maintenance page fallback via nginx

### Infrastructure
- HTTPS via Let's Encrypt SSL certificate on arcaneone.duckdns.org
- nginx reverse proxy — port 443 → localhost:8000
- DuckDNS dynamic DNS — arcaneone.duckdns.org → static IP
- GCP firewall rules — ports 80 and 443 opened
- httpx installed in venv for async ElevenLabs calls

---

## [2.0.0] - 2026-05-03

### Backend (server/openai_client.py)
- Switched GPT-4 → GPT-4o-mini (9x speed: 23.7s → 2.8s avg)
- Zero math rule — all dosing resolved to final mL, no provider arithmetic
- Dual response format — JTS structured vs non-JTS concise
- TLDR section on all responses
- Knowledge source handling — explicit attribution JTS vs general evidence
- Natural language query mapping — lay terms to clinical protocols
- Mandatory disclaimer enforcement on every response
- P:F ≤100 = SEVERE ARDS explicit rule
- Calcium chloride CENTRAL LINE ONLY enforcement
- TXA >3 hours = DO NOT GIVE absolute rule
- Steroids and albumin in TBI absolute prohibition
- Non-medical query redirect
- Drip rate and ventilator mL calculation rules
- Silent lbs to kg weight conversion

### Test Suite (test_cdss.py v1.3.1)
- 34 automated test cases across 9 categories
- Natural language test cases added
- lbs preprocessing to mirror cdss_client.py behavior
- Fixed dotenv path loading with pathlib
- Pass rate: 94.1% — mean response time: 2,836ms

---

## [1.6.1] - 2026-05-02

### Client (cdss_client.py)
- Restored correct thin client — was overwritten with server code
- SERVER_URL reads from .env only — no hardcoded IP
- lbs to kg auto-conversion for patient safety
- Non-blocking async TTS — prompt returns immediately
- pygame output suppressed — audio timeout prevents hanging
- TTS medical term expansion — 120+ acronyms and units
- Number-attached unit pronunciation (500mg → 500 milligrams)
- Voice speed control (0.85x)

---

## [1.5.0] - 2026-04-28

### Infrastructure
- Migrated from mistral-vm (e2-standard-4, $121/mo) to arcaneone (e2-medium, ~$20/mo)
- 83% monthly cost reduction
- Static external IP configured on arcaneone
- All backend services transferred — FastAPI, ChromaDB, JTS data
- Radxa Zero 3W flashed and deployed as primary edge client
- Auto-update boot.sh with systemd service and network fallback
- Pi-hole DNS, SSH honeypot, Prometheus/Grafana monitoring

---

## [1.0.0] - 2026-04-21

### Initial Release
- FastAPI cloud backend with ChromaDB vector database
- 89 JTS Clinical Practice Guidelines indexed — 7,186 chunks
- Raspberry Pi 4 edge client
- ElevenLabs TTS with wake word detection
- WireGuard VPN integration
- Tiered connectivity architecture designed
- GitHub organization established