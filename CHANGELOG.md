# EdgeCDSS Changelog

## [4.1.0] - 2026-08-20

Hardening release driven by `AUDIT_v4.1.md` — a review of 135 logged queries and
26 feedback entries from the v4.0 field period. Convention: one fix, one commit,
one regression test. Every fix below has a mutation check recorded in its commit
message: revert the fix, watch the named test fail, restore.

### Safety
- **Patient-boundary reset.** Patient context accumulated across every turn of a
  conversation with no notion of the patient changing, so a 6-year-old's 34 kg
  was carried into an adult casualty and a dose was served against it. The
  server now detects a boundary — explicit phrases, a presentational opener, a
  contradicting age or weight, or 30 minutes of inactivity
  (`CDSS_PATIENT_TIMEOUT_MIN`) — and clears the context, **announcing every
  reset in the response** so a wrong reset is as visible to the medic as a
  missed one. The web client gains a NEW PATIENT button that clears the history
  the server replays. (audit S-1)
- Safety-gate overrides now **downgrade instead of releasing**. The nine
  hand-rolled false-positive branches became a named `SAFETY_OVERRIDES` registry;
  a fired override serves the response with the human-review banner and
  **preserves the validator's issue list** instead of discarding it. Invariant,
  pinned over a 216-case matrix: a served response can never be logged `UNSAFE`.
  (audit S-2)
- **Dose contract enforced when the contract is empty.** Canonical GIVE lines
  were only checked when Python had computed dose candidates — that is, the check
  was skipped in exactly the state where the generator is most likely to invent a
  dose. An empty contract now hard-blocks any canonical GIVE line, for adults as
  well as pediatrics. (audit S-3)
- `is_pediatric` is **re-derived every turn** rather than latched True and never
  cleared, so a stated adult age clears a pediatric flag set earlier in the
  conversation. (audit S-1)
- The safety gate **fails closed when the validator returns no structured
  issue.** It synthesizes an issue from the validator's free-text rationale so
  the audit log is not left blank, but that synthesized text is no longer passed
  to the false-positive override matcher — a rationale mentioning "fluid" or
  "airway" could otherwise satisfy an override's keywords and downgrade a block
  into a served response. Found while reviewing the override-registry change.
- The hard-coded `levetiracetam (Keppra) 1500mg` was removed from
  `ALLOWED_ACTIONS`. That block carries weight-free protocol guidance only; every
  number with a dose unit belongs in `ALLOWED_DOSES`, which requires a confirmed
  weight.

### Quality
- Ventilator-settings queries no longer route into the RSI paralytic bundle. A
  bare `"ventilator"` substring match dispatched them before vent settings were
  ever considered. (audit S-4)
- The clinical router's alias table matches on **word boundaries**. Plain
  substring matching against single- and double-letter keys meant any query
  containing *patient* had "physician assistant" appended to its RAG search, and
  *dka* pulled in "ketamine". 143 spurious matches removed across the logged
  corpus. (audit F-2)

### Observability
- Session JSONL gains `override_fired`, `boundary_reset`, `pipeline_ms` and
  `synthetic`, stamped `log_schema: 2`. Pre-v4.1 entries carry none of these and no schema key;
  analysis tooling must read a missing key as **unknown**, never as a default —
  defaulting an absent `synthetic` to false would re-classify 48 known
  test-suite entries as real user traffic.
- `run_tests.sh` tags its requests `X-Test-Run: 1`. The suite fires at the live
  public endpoint by design, so the flag is self-declared and spoofable: it is
  log hygiene, **not** a security control, and nothing in the pipeline branches
  on it (pinned by test).

### Deployment safety
- **A typo'd tuning value can no longer prevent startup.** `_env_number()`
  replaces the raw `int()`/`float()` around `os.getenv` at all three numeric
  knobs (`CDSS_PATIENT_TIMEOUT_MIN`, `CDSS_EVENT_TURNS`, `CDSS_RAG_TOP_K`): an
  unparseable value now falls back to the default and says so, instead of
  raising. The timeout knob is read at module scope, so a typo there meant
  `openai_client` failed to import, uvicorn never started, `/health` never
  answered, and the deploy watchdog rebooted the device in a loop — remotely,
  with no way back in. The knobs stay tunable; only the failure mode changed.

### Testing
- Offline regression suite: 105 tests, ~2 s, no network, no API key, no
  ChromaDB. `cd server && ./run_unit_tests.sh`. `openai_client` is now importable
  without the OpenAI SDK or a key, which is what made the suite possible.

### Corrections to earlier changelog entries
- **[2.5.0] "Memory reset — voice command \"new patient\", button, 30min
  inactivity timeout" and "New Patient button added to web interface header" are
  inaccurate as they stand.** No patient-boundary reset exists in the shipped
  server: no inactivity timeout, and no server-side handling of a "new patient"
  utterance. The S-1 sequence was replayed against shipped `HEAD`
  (`PLAN_v4.1.md` §1.1): `new session` at `cdss_session_2026-07-18.jsonl:13`
  parses as an ordinary query and clears nothing — the 17 kg carries straight
  through to the next patient. Whatever shipped in 2.5 did not survive into
  the v4 client/server split. **SC-1 in this release is what finally makes the
  claim true** — a real button, a real 30-minute timeout, and server-side
  boundary detection, none of which existed before. The 2.5.0 entry is left as written — it is a
  historical record — and corrected here rather than edited.


## [4.0.0] - 2026-07-18

### Architecture (Deterministic-First)
- ALLOWED_DOSES contract: all doses computed in Python; generator prohibited from medication math
- Deterministic post-check parses GIVE lines and blocks any dose not matching the contract
- 13 deterministic pre-generation safety gates (weight, route, pediatric, overdose, contraindications)
- Structured PatientContext — confirmed vs estimated weight separation; facts replayed over full conversation
- Clinical router: LLM-built protocol_index.json enhances retrieval queries (89 protocols)
- Narrow LLM validator receives dose contract; fail-closed gate with structured false-positive overrides
- Session audit logger — JSONL per query, no PHI
- EDGECDSS_DEBUG_WARN_ONLY env flag for observation-mode debugging

### Deployment (Cloud → Edge)
- Migrated entire stack from GCP VM to NVIDIA Jetson Orin Nano (JetPack 6, aarch64)
- Public access via outbound-only Cloudflare Tunnel (cdss.arcanekg.com); no open ports
- systemd-managed services with Restart=always; health watchdog with escalating recovery
- Knowledge base re-ingested on device: 89 JTS CPGs → 8,559 chunks (sentence-aware chunking, header/footer stripping, page-accurate metadata, idempotent upserts)
- Server files added to repo: embeddings.py, ingest_jts.py, clinical_router.py + index files, jetson_cdss_setup_v2.sh

### Interface & Evaluation
- Web portal served from the device at the API root: conversation memory (50-turn window), source citations, validator status
- Structured clinical feedback: severity triage, issue categories, protocol-cited corrections
- TTS pronunciation normalization for clinical notation (units, concentrations, routes, acronyms)
- Fixed TBI-steroid validator false positive (from beta field report, same-day fix + regression test)
- Severe TBI routed through RAG instead of fixed card (clinical decision)
- Automated suite: 24/24 passing against the live public endpoint


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