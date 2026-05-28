# EdgeCDSS Development Roadmap

---

## v3.0 BUILD — IN PROGRESS

### Safety Architecture — P1 (Fix Before Anything Else)
- [ ] Secondary validation layer — separate LLM pass checks every response for dosing safety, contraindications, and route appropriateness before output reaches provider
- [ ] Pediatric hard dosing caps — ketamine ≤2 mg/kg induction, rocuronium ≤1.2 mg/kg, succinylcholine ≤2 mg/kg enforced at validator level
- [ ] CICO rule — failed ETT + failed supraglottic = surgical airway (cric) must be first recommendation
- [ ] Morphine restriction — recommend only if explicitly requested or no other analgesic available
- [ ] Height/weight sanity check — flag implausible combinations before generating vent settings
- [ ] Sepsis/DCR hard rule — fever + infection source = sepsis protocol, DCR explicitly blocked

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
- [ ] Tide pod / household chemical ingestion — EBM-verified care pathway
- [ ] Strengthen sepsis/DCR differentiation — v2.4 fix not holding reliably

### Voice Interface
- [ ] Dual-interface architecture — voice (ElevenLabs) and text (no TTS) hitting same backend
- [ ] ElevenLabs TTS re-enabled on voice interface
- [ ] Voice commands — stop, repeat, slow down, new patient
- [ ] Wake word detection on Radxa client — HEY MEDIC
- [ ] Voice interface token controls — separate rate limiting for TTS queries
- [ ] ElevenLabs streaming TTS — speak while generating
- [ ] TTS medical term expansion tuning (ongoing)

### Evaluation Infrastructure
- [ ] Automated test suite expansion — add pediatric RSI, CICO, COPD oxygen, PE, BLS scope, route selection cases
- [ ] Structured tester intake — clinical background captured before first query
- [ ] Required feedback — rating required before next query unlocked
- [ ] Post-session survey — 3-question form after 5+ queries
- [ ] Scenario tagging — tester tags clinical domain with each feedback submission
- [ ] Query content logging — server-side logging of all queries regardless of feedback submission
- [ ] Target pass rate: 92%+

### Infrastructure
- [ ] Pre-flight syntax check — python3 -m py_compile before every service restart
- [ ] Automated ChromaDB backup to GCP Storage
- [ ] fail2ban for repeat scanner IPs
- [ ] nginx rate limiting on non-/query endpoints
- [ ] GitHub Issues created from all roadmap items

### Documentation
- [ ] v3.0 evaluation report PDF
- [ ] Updated PoC paper incorporating v2.5 and v3.0 findings
- [ ] LinkedIn post — v3.0 launch and AI safety findings
- [ ] Close-out tag on v2.5 release on GitHub

---

## BACKLOG — POST v3.0

### Speed Optimization (Target: <5 second response)
- [ ] Profile full request cycle — identify biggest latency bottleneck
- [ ] Reduce max_tokens to 150-200 for voice/brief mode
- [ ] Target: ChromaDB <1s, LLM <3s, TTS streaming <1s

### Auto-Update Boot System
- [ ] Configure wpa_supplicant for multi-network WiFi auto-connect
- [ ] Implement reverse SSH tunnel for remote device management
- [ ] Test full boot-to-running sequence headless (no keyboard/monitor)

### Lightweight Client Build (Pi Zero 2W)
- [ ] Validate Pi Zero 2W with wired mic and headphones
- [ ] Build deployable image — flash, boot, auto-connect, auto-update, run
- [ ] Document setup process for non-technical users
- [ ] Test wired audio stack (ALSA/PulseAudio) on Pi Zero 2W
- [ ] Benchmark latency vs Radxa Zero 3W

### Network Mesh & VPN
- [ ] Configure WireGuard server to route subnet to VPN clients
- [ ] Add Radxa and edge devices as WireGuard peers with static VPN IPs
- [ ] Test SSH to edge devices through WireGuard from any network
- [ ] Implement split tunneling — local traffic stays local, cloud through VPN

### Austere Environment Deployment
- [ ] Load and process additional national/regional medical protocol sets
- [ ] Migrate to higher-performance edge hardware for larger knowledge bases
- [ ] Optimize ChromaDB chunking for expanded protocol volumes
- [ ] Test on satellite connectivity tiers (broadband and narrowband)
- [ ] Validate tiered degradation: broadband → narrowband → offline
- [ ] Solar/battery power budget validation for full system

### Multi-Provider LLM Support
- [ ] Build provider toggle — switch OpenAI/Claude per request
- [ ] Compare response quality across providers for medical queries
- [ ] Cost-per-query analysis across providers

### Android / Termux Client
- [ ] Resolve pydantic-core ARM64 build failure on Termux
- [ ] Implement Termux TTS fallback (termux-tts-speak)
- [ ] Test full cdss_client.py on Android via Termux

### Security Hardening
- [ ] Generate device-specific API tokens per edge deployment
- [ ] Automated backup of ChromaDB index to cloud storage
- [ ] Configure billing alerts and cost monitoring

### Protocol Expansion
- [ ] Pipeline for ingesting new protocol sets (national, regional, specialty)
- [ ] Chunking strategy optimization for non-JTS formatted documents
- [ ] Multi-language protocol support evaluation
- [ ] Version control for protocol knowledge base updates

---

## COMPLETED — v2.5 AND PRIOR

- [x] EdgeCDSS-Nano: Raspberry Pi 4 baseline deployment
- [x] FastAPI cloud backend with ChromaDB vector database
- [x] JTS CPG knowledge base — 89 protocols, 7,186 chunks indexed
- [x] Voice interface — ElevenLabs TTS with medical term expansion
- [x] Radxa Zero 3W thin client deployment
- [x] Cloud backend migration from mistral-vm to arcaneone (e2-medium, 83% cost reduction)
- [x] cdss_client.py — thin client routing queries to arcaneone backend
- [x] TTS medical term expansion — acronyms, units, concentrations
- [x] lbs to kg auto-conversion for patient safety
- [x] Non-blocking async TTS — prompt returns immediately after response
- [x] Dual response format — JTS structured vs non-JTS concise
- [x] Zero math rule — all dosing resolved to final mL, no provider math
- [x] TLDR section added to all responses
- [x] Auto-update boot script with network fallback
- [x] Systemd service for auto-launch on boot
- [x] GitHub organization established — AI-in-Austere-Medicine-Project
- [x] HTTPS via Let's Encrypt — arcaneone.duckdns.org
- [x] nginx reverse proxy with SSL termination
- [x] X-Access-Token authentication on all endpoints
- [x] Rate limiting — server-side per-IP (removed v2.5, server-controlled)
- [x] Feedback system — helpful / incorrect / dangerous / comment
- [x] Server-side feedback logging to feedback.log
- [x] Web interface — GitHub Pages, voice STT, text response, feedback buttons
- [x] Conversation memory — last 5 exchanges per patient session
- [x] New Patient button + voice command + 30min inactivity timeout
- [x] Custom maintenance/offline page via nginx
- [x] Sepsis vs hemorrhagic shock differentiation (v2.4)
- [x] TXA strict indications — hemorrhagic shock only (v2.4)
- [x] WPW contraindications — adenosine/AV nodal blockers prohibited (v2.3)
- [x] Pediatric detection and dosing rules (v2.4)
- [x] Hypothermia dedicated protocol (v2.4)
- [x] Automated test suite — 34 cases, 9 categories, 85.3% pass rate (v2.5)
- [x] Field evaluation report v1.1 — 43 queries, 6 testers, 24hr analysis
- [x] v2.5 summary report with AI safety analysis
- [x] Project overview PDF
- [x] Tiered connectivity architecture documented (Starlink/BGAN/Iridium/Offline)
- [x] Single repo structure — client + server + web + tests + docs