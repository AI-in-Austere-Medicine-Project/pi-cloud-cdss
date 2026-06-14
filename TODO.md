# EdgeCDSS — Development Roadmap

---

## v3.0 BUILD — IN PROGRESS

### Safety Architecture — P1 (Fix Before Anything Else)
- [x] Secondary validation layer — separate LLM pass checks every response before output reaches provider
- [x] CICO rule — failed ETT + failed supraglottic = surgical airway must be first recommendation
- [x] COPD oxygen rule — SpO2 88-92% target, titrated low-flow only, high-flow NRB prohibited
- [x] Sepsis/DCR hard rule — fever + infection source = sepsis protocol, DCR explicitly blocked
- [x] validator_result and validator_issues fields wired into QueryResponse model
- [ ] Fix validator false positives — over-blocking correct pediatric RSI responses
- [ ] Tune validator math rules — ketamine and rocuronium ceiling calculations
- [ ] Validator returns corrected response on UNSAFE instead of full block where appropriate
- [ ] Morphine restriction — recommend only if explicitly requested or no other analgesic available
- [ ] Height/weight sanity check — flag implausible combinations before generating vent settings

### Patient Context System
- [ ] Structured patient record — weight, age, mechanism, vitals, medications given, time of injury stored per session
- [ ] Medication inventory intake — provider loads available meds at session start, system recommends only from that list
- [ ] Full patient record injection — every query receives complete patient context, not just last 5 exchanges
- [ ] Scope of practice detection — BLS/EMT/Paramedic/CC level stated by provider adjusts recommendation scope accordingly

### Clinical Protocol Gaps
- [ ] Pulmonary embolism protocol — PE missing from knowledge base entirely
- [ ] CICO dedicated section — surgical airway management as standalone protocol
- [ ] Route selection from scene context — combative patient = IM, no IV access = IO
- [ ] BLS pathway — scope-appropriate recommendations for BLS-level providers
- [ ] Strengthen sepsis/DCR differentiation — needs harder rule enforcement

### Voice Interface
- [ ] Dual-interface architecture — voice (ElevenLabs) and text (no TTS) hitting same backend
- [ ] ElevenLabs TTS re-enabled on voice interface
- [ ] Voice commands — stop, repeat, slow down, new patient
- [ ] Wake word detection on Radxa client — HEY MEDIC
- [ ] Voice interface token controls — separate rate limiting for TTS queries
- [ ] ElevenLabs streaming TTS — speak while generating

### Evaluation Infrastructure
- [ ] Automated test suite expansion — add pediatric RSI, CICO, COPD oxygen, PE, BLS scope, route selection cases (target 50+ cases)
- [ ] Structured tester intake — clinical background captured before first query
- [ ] Required feedback — rating required before next query unlocked
- [ ] Post-session survey — 3-question form after 5+ queries
- [ ] Scenario tagging — tester tags clinical domain with each feedback submission
- [ ] Target pass rate: 92%+

### Infrastructure
- [ ] Pre-flight syntax check — python3 -m py_compile before every service restart (add to deployment workflow)
- [ ] Automated ChromaDB backup to GCP Storage
- [ ] fail2ban for repeat scanner IPs
- [ ] WireGuard VPN — edge device to arcaneone tunnel for field deployment

### Documentation
- [ ] v3.0 evaluation report PDF
- [ ] Updated PoC paper incorporating v2.5 and v3.0 findings
- [ ] LinkedIn post — v3.0 launch and AI safety findings
- [ ] Tag v2.5 as closed release on GitHub

---

## BACKLOG — POST v3.0

### Speed Optimization
- [ ] Profile full request cycle — identify biggest latency bottleneck
- [ ] Reduce max_tokens to 150-200 for voice/brief mode
- [ ] Target: ChromaDB <1s, LLM <3s, TTS streaming <1s

### Edge Hardware
- [ ] Validate Pi Zero 2W with wired mic and headphones
- [ ] Build deployable image — flash, boot, auto-connect, auto-update, run
- [ ] Benchmark latency vs Radxa Zero 3W
- [ ] Test wired audio stack (ALSA/PulseAudio) on Pi Zero 2W

### Network
- [ ] Configure WireGuard server to route subnet to VPN clients
- [ ] Add Radxa and edge devices as WireGuard peers with static VPN IPs
- [ ] Test SSH to edge devices through WireGuard from any network
- [ ] Implement split tunneling — local traffic stays local, cloud through VPN

### Austere Environment Deployment
- [ ] Load and process additional national/regional medical protocol sets (WMS, WHO)
- [ ] Optimize ChromaDB chunking for expanded protocol volumes
- [ ] Test on satellite connectivity tiers (broadband and narrowband)
- [ ] Validate tiered degradation: broadband → narrowband → offline
- [ ] Solar/battery power budget validation for full system

### Multi-Provider LLM Support
- [ ] Build provider toggle — switch OpenAI/Claude per request
- [ ] Compare response quality across providers for medical queries
- [ ] Cost-per-query analysis across providers

### Protocol Expansion
- [ ] Pipeline for ingesting new protocol sets (national, regional, specialty)
- [ ] Multi-language protocol support evaluation
- [ ] Version control for protocol knowledge base updates

### Android / Termux Client
- [ ] Resolve pydantic-core ARM64 build failure on Termux
- [ ] Implement Termux TTS fallback (termux-tts-speak)
- [ ] Test full cdss_client.py on Android via Termux

---

## COMPLETED — v2.5 AND PRIOR

- [x] EdgeCDSS-Nano: Raspberry Pi 4 baseline deployment
- [x] FastAPI cloud backend with ChromaDB vector database
- [x] JTS CPG knowledge base — 89 protocols, 7,186 chunks indexed
- [x] Voice interface — ElevenLabs TTS with medical term expansion
- [x] Radxa Zero 3W thin client deployment
- [x] Cloud backend migration — arcaneone (e2-medium, GCP)
- [x] TTS medical term expansion — acronyms, units, concentrations
- [x] lbs to kg auto-conversion for patient safety
- [x] Non-blocking async TTS
- [x] Dual response format — JTS structured vs non-JTS concise
- [x] Zero math rule — all dosing resolved to final mL, no provider math
- [x] TLDR section added to all responses
- [x] Auto-update boot script with network fallback
- [x] Systemd service for auto-launch on boot
- [x] GitHub organization established — AI-in-Austere-Medicine-Project
- [x] HTTPS via Let's Encrypt — arcaneone.duckdns.org
- [x] nginx reverse proxy with SSL termination
- [x] X-Access-Token authentication on all endpoints
- [x] Rate limiting removed — server-controlled access
- [x] Feedback system — helpful / incorrect / dangerous / comment
- [x] Server-side feedback logging
- [x] Web interface — GitHub Pages, voice STT, text response, feedback buttons
- [x] Conversation memory — last 5 exchanges per patient session
- [x] New Patient button + voice command + 30min inactivity timeout
- [x] Custom maintenance/offline page via nginx
- [x] Sepsis vs hemorrhagic shock differentiation
- [x] TXA strict indications — hemorrhagic shock only
- [x] WPW contraindications — adenosine/AV nodal blockers prohibited
- [x] Pediatric detection and dosing rules
- [x] Hypothermia dedicated protocol
- [x] Automated test suite — 34 cases, 9 categories, 85.3% pass rate
- [x] Field evaluation report v1 — 70 feedback entries, 26 testers
- [x] v2.5 summary report with AI safety analysis
- [x] v3.0 goals and technology document
- [x] Project overview PDF
- [x] Two-pass safety pipeline deployed — generator + validator
- [x] Voice-only safety contract added to system prompt
- [x] Medication minimum-data gate
- [x] Pediatric hard stop — absolute dosing ceilings
- [x] Shock fork rule
- [x] MASCAL mode
- [x] Off-grid failure mode
- [x] RAG source discipline
- [x] Norepinephrine safety rules
- [x] After-medication monitoring prompts
- [x] Post-intubation sedation as mandatory response format section
- [x] MIT license — repo cleaned up
- [x] START-HERE folder with first time user guide
- [x] Test results moved to tests/results/
- [x] Client files moved to client/
