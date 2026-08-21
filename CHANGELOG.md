# EdgeCDSS Changelog

## [Unreleased]

### Temperature capture: fever phrasing, and the unit the medic actually used
- **`fever of 104` is a temperature.** `fever` joins `temperature`, `temp` and
  `t` as a label, word-anchored like the rest — a number has to follow it.
  `febrile`, and `fever` with nothing after it, still capture nothing: this
  table stores measurements, and the word alone is the sepsis router's business
  (`has_fever`). The query that prompted this held a fever of 104 and logged no
  temperature at all.
- **The unit comes from the value, and the reading keeps it.** The plausible
  bands do not overlap — 35-43C, 93-110F — so an unlabelled `39` is Celsius and
  an unlabelled `104` is Fahrenheit. A stated `C` or `F` is checked against its
  own band and never reinterpreted: `temp 104 C` is a mistyped reading, not a
  Fahrenheit one, and reading it as F would invent a plausible vital out of an
  implausible one. The strip and the prompt show `Temp 104 F` to the medic who
  typed 104 F; both conversions are stored, and the caution table compares the
  canonical Celsius value the thresholds are written in.
- **A temperature in neither band is rejected visibly**, like `BP 400/300`
  already was, and says which two ranges it missed. Previously the range was
  20-45C and an unlabelled number was split at 45, so `temp 44` was stored as
  44C and `temp 50` as 10C.
- **`temp_c` is now `temp`** — in the caution rules, the response, the log and
  the client — because the value is no longer always Celsius and a name that
  says otherwise is the kind of assumption that costs a render. An older
  `vitals_rules.json` with a `temp_c` key is renamed on load rather than
  ignored: a caution that silently stops arming is the one failure mode that
  table must not have.
- **Log schema 5.** A schema 4 `temp_c` value is Celsius; a schema 5 `temp`
  value is in `unit`, with `value_c` and `value_f` alongside. Analysis tooling
  has to be able to tell them apart without inspecting the number.
- **Known consequence, deliberately shipped:** a `temp.min` of 35 puts Celsius
  hypothermia outside the plausible band, so `temp 33` is rejected and
  `hypothermia_txa` can only arm from a Fahrenheit reading (93-94.9F is
  33.9-34.9C). Pinned by a test that says so out loud, noted in
  `vitals_rules.json`, and raised in TODO.md as an owner decision — lowering
  `temp.min` restores it with no code change.

### Fixed — the context strip could take the answer down with it
- **A clinical answer that had already rendered was being replaced with
  REQUEST FAILED.** `patient_context.confirmed_weight_kg` is a JSON number
  (`75.0`); the new context strip handed it to the client's HTML escaper, which
  called `.replace` on it. The TypeError did not stop at the chip it came from —
  it unwound out of `renderCtx()`, out of `ask()`'s try, and into the catch that
  writes the failure banner, over a SEPSIS card that was already on screen. The
  server had answered correctly; the medic saw an error. Reproduced from the
  session log for *"hypotensive, BP 90/30, fever 104, recent infection, IV
  established, 75 kg"*, which logged `validator_result: SAFE` with both
  pressures captured.
- **The strip converts numbers itself** rather than relying on the escaper to
  cope, and drops any reading it cannot read a value from. A vital that renders
  as `undefined` is a vital sign that is not there.
- **The escape helper coerces** (`String(s ?? '')`), so an absent field renders
  as nothing instead of throwing.
- **The answer outranks the furniture around it.** The strip, the listen button
  and the feedback controls are wired up after the answer is in the DOM and are
  now guarded individually: a failure in any of them is logged and skipped. One
  missing field costs its own element and nothing more. A request that genuinely
  failed still says REQUEST FAILED — the hardening does not swallow real errors.
- **`sources` gained a default** on the response model and is read with `.get`.
  A pipeline path that set no sources would have been a 500 — the same failure
  one layer earlier.
- **The client render path is now tested by running it.** `test_client_render.py`
  drives the real `<script>` from `static/index.html` in a stubbed DOM against
  canned `/query` payloads, including the one the server actually served for the
  query above. The grep-based contract tests all passed while this bug was live;
  eight of the new assertions fail against the shipped client.
- **`test_vitals.py`'s fixture timestamps are anchored to the clock**, not to a
  calendar date. `T0 = 2026-08-21T10:00Z` fed a conversation history against a
  current turn stamped from `utcnow`, so once real time passed it by more than
  the patient-boundary timeout the fixture started firing an
  `inactivity_timeout` and the test failed on the clock rather than on a change.

### Vital signs in patient context
- **Vitals are parsed from free text and held in session context** — HR, BP,
  SpO2, RR, GCS and temperature, in the phrasings a medic actually types
  (`HR 128`, `BP 82/40`, `sats 91`, `sp02 88`, `GCS 3-4-5`, `temp 101.2 F`).
  Fahrenheit is normalised to Celsius. **Every reading carries the timestamp of
  the turn it was stated in**, and a turn with no timestamp yields a reading
  whose age is *unknown* — never a fabricated "just now". Pre-v4.1 clients send
  no timestamp at all, and stamping those "now" would present a stale vital as
  fresh, which is S-1 with a faster clock.
- **Newer supersedes older, and the prior value is kept in the log.** The
  question "what did the system believe the blood pressure was when it said
  that" is answerable from the log alone.
- **The client shows a context strip** — weight, age, access, and each vital
  with the age of its reading. Readings older than 15 minutes, or whose age
  cannot be established, are marked. This is the S-1 lesson as UI: the v4.1 fix
  cleared stale context at a boundary, and this is the other half — showing the
  medic what the system believes the rest of the time, so a wrong value is
  corrected before it is dosed against rather than after.
- **A patient boundary clears every vital**, and the reset notice now says so:
  *"previous weight, age, access and vitals cleared"*.
- **Impossible values are rejected visibly, not silently.** `BP 400/300` is not
  stored and the medic is told it was dropped. A pressure passes or fails as one
  measurement — storing the diastolic from `400/300` because 300 sits inside the
  diastolic range would leave the system holding half a vital it had just said
  it could not read.
- **Vitals never compute a dose.** They reach the generator prompt, the
  validator, and a narrow conflict table. Dose logic stays in the ALLOWED_DOSES
  contract, which remains the only thing permitted to produce a number to give.
  Pinned by a test that builds the contract with and without vitals present and
  asserts it is identical.
- **Conflicts produce a visible caution, never a block.** A drug with a
  hypotension risk at a low SBP, a respiratory depressant at a low RR or SpO2,
  an AV-nodal blocker at a low HR, TXA at a low temperature, anything by mouth
  at a low GCS. The caution appends a line and downgrades a SAFE verdict to
  NEEDS_HUMAN_REVIEW — served-but-flagged, which is what that verdict means.
  It cannot block a response and, the direction that would actually be
  dangerous, it cannot release one.
  - Both a deterministic table (`server/vitals_rules.json`, editable clinical
    content) and the validator, which gains a conservative vitals rule and is
    told to flag rather than rewrite.
  - Ketamine is deliberately absent from the haemodynamic and respiratory
    lists — it is the favourable agent on both axes and cautioning it would push
    a medic toward the drug the caution exists to warn about. Pinned so a future
    config edit cannot add it quietly.
  - Cautions are applied at the gate's single exit point, after every override
    has been evaluated against the original text. The
    `dangerous_reassurance_has_action` branch fires on the substring "monitor"
    anywhere in a response, and a caution is commentary about the answer, not
    part of it — the same ordering rule `BOUNDARY_RESET_NOTICE` and the
    general-reference banner follow.
- The gate invariant matrix is now **648 cases**, with and without cautions in
  every cell.
- `log_schema` 3 → 4, adding `vitals`, `vitals_superseded`, `vitals_rejected`
  and `vitals_cautions`.

### Fixed
- **A boundary reset on a pre-gate turn was never announced.** SC-1 chose option
  (c) — surface every reset, so a wrong reset is as visible as a missed one —
  but `BOUNDARY_RESET_NOTICE` was applied only on the RAG path. A turn that
  crossed a patient boundary and then hit a deterministic pre-gate cleared the
  weight, age and access and said nothing about it. Notices are now applied on
  every return path.
- **Deterministic cards bypass the safety gate by design and so were invisible
  to vitals cautions.** They are fixed reviewed strings, but a fixed string can
  still recommend lorazepam to a patient whose RR was recorded as 6 —
  `build_seizure_response` does, `build_cholera_response` recommends oral
  fluids, and both DCR cards name TXA. Cautions now reach them through the same
  helper the gate uses, not a second implementation.

### General medical reference fallback (F-4)
- **When JTS retrieval returns nothing usable, the system now answers from
  general medical knowledge instead of refusing.** Lab values, toxicology,
  envenomation and plant/snake identification support, preparation recipes,
  basic clinical reference. This resolves **F-4** as *a deliberate
  general-knowledge fallback now, curated corpus expansion later* — the corpus
  is still 89 JTS trauma CPGs and this does not close the gaps in it.
- **A second knowledge source, not a second pipeline.** General answers pass
  through the same `run_deterministic_checks`, the same validator, the same
  `apply_safety_gate`, the same `GateOutcome`, the same UNSAFE-iff-blocked
  invariant, the same override registry and the same log. The gate has no
  notion of source and was not given one. The 216-case invariant matrix is now
  324 cases, with general-mode text in every cell.
- **Recipe yes, prescription no** (owner ruling). A standardized preparation
  recipe is reference knowledge; a patient dose is not. Enforced three times
  over: the routing guard keeps dosing questions off this path entirely, the
  prompt forbids the canonical GIVE format by name, and SC-6 blocks any GIVE
  line that appears anyway — general mode never builds a contract, so the
  empty-contract rule applies to all of it.
  - *Known limitation:* SC-6 is syntactic and cannot tell a recipe from a
    prescription. A legitimate recipe phrased as a GIVE line is held. That is
    the fail-closed answer and it stays.
- **Labelled everywhere it is served.** An on-screen banner
  (`GENERAL MEDICAL REFERENCE — not from JTS protocols`) that persists in
  conversation history, a spoken disclosure applied by `/speak` rather than by
  the client, and `source: "general"` in the session log. The banner is applied
  **after** the safety gate, like `BOUNDARY_RESET_NOTICE` and for the same
  reason: a label must never be text the validator reasons about or an override
  matches keywords against.
- `FIXED_PREP` responses are now classified `source: "general"`. A preparation
  recipe is not in the JTS corpus and claiming otherwise in the audit log is the
  exact thing the field exists to prevent.

### Multi-provider model selection
- **Model choice is now config, not code.** `server/providers.json` holds the
  model strings, per-model capability flags, and the default and validator
  models. The two hard-coded `model="gpt-4o-mini"` strings inside
  `openai_client.py` are gone. **Default behaviour is unchanged:** the shipped
  config is `gpt-4o-mini` for both calls, which is what was hard-coded.
- **Anthropic (Claude) and OpenAI (GPT), keyed from `server/.env`.** Two
  adapters: `openai_compat` covers OpenAI and any OpenAI-compatible endpoint
  (Ollama, llama.cpp, vLLM) via `base_url`, so a future on-device model is a
  config entry and no new code. `anthropic` uses the native SDK, because Claude
  takes `system` as a top-level parameter and Opus 5 / Sonnet 5 reject
  `temperature` outright.
- **A provider that cannot work is absent from the menu and says why.**
  `/status` and `/models` carry `provider_detail` — the same self-diagnosing
  contract as `voice_detail`. Key presence is not authentication, so the check
  is a real authenticated call (cached five minutes, off the event loop). Keys
  are never logged or echoed; anything key-shaped is redacted before it can
  reach `/status`, which is unauthenticated.
- **The safety validator does not move when the dropdown does.** It runs on
  `validator_model` from config. Holding it constant is what makes a generator
  comparison attributable.
- Client: a MODEL dropdown, and every answer carries
  `Answered by <model> · source: <JTS|general>`. A deterministic card is
  attributed to no model, because Python wrote it.
- `log_schema` 2 → 3, adding `source` and `model`. As with `synthetic`, a
  missing key must read as UNKNOWN — defaulting an absent `source` to `"jts"`
  would claim JTS provenance for every entry written before this existed.

### Fixed
- **A request to mix a NOREPINEPHRINE drip returned the EPINEPHRINE recipe.**
  `"epinephrine drip"` is a substring of `"norepinephrine drip"`, and
  `build_fixed_prep_response` matched on substrings — a different drug at a
  different concentration, served as though it were the answer, with nothing
  marking the substitution. Fixed with word-boundary matching, the same
  technique F-2 applied to the alias table in v4.1. Found while routing
  preparation questions to the reference tier.
- `FIXED_PREP_TERMS` and `build_fixed_prep_response` disagreed about which
  phrasings are preparation requests (`"make epinephrine drip"` was in one and
  not the other), so a request could be routed as a dose question and then
  answered with a recipe. The list is now the single source of truth. The
  disagreement was invisible under substring matching.

### Voice output (fixed)
- **The 🔊 listen button has been dead since v4.1.** `ELEVENLABS_API_KEY` held
  the 64-character hex key *ID* shown beside the key in the ElevenLabs
  dashboard, not the `sk_` key, so every request came back
  `400 api_key_id_used_as_api_key`. **Operator action: paste the real `sk_` key
  into `server/.env` and restart the service** — the code fixes below make the
  failure visible, they cannot supply a credential.
- Four layers each hid the cause, and all four are fixed:
  - `/speak` inlined the ElevenLabs call and turned every upstream failure into
    `500 ElevenLabs error`. The call now lives in `server/tts.py` and the
    endpoint returns the reason: **503** not configured / key ID pasted /
    upstream unreachable, **502** upstream refused (with its status and
    message), **413** text over the cap, **400** empty text.
  - `/status` and `/health` reported `voice_support: true` unconditionally, so a
    dead voice path looked healthy. Both now report what the config actually
    supports, and `/status` carries a `voice_detail` reason. Pinned by a
    meta-test: the hard-coded `True` cannot come back.
  - A malformed key is caught **before** the network, naming the key-ID mistake
    specifically. A missing key raised `TypeError` inside httpx (`None` header
    value) and surfaced as the same generic 500 as everything else.
  - The web client discarded the server's reason, and its unawaited
    `audio.play()` reported success when a browser autoplay block had rejected
    it. It now shows the reason on the button and in a status line, awaits
    playback, and revokes the object URL it used to leak per click.
- `server/tts.py` imports with no key, no network and no httpx — the voice path
  cannot affect the clinical path, and the contract is testable offline.
- Network and timeout failures degrade to `503 ElevenLabs unreachable` instead
  of an unhandled exception. Relevant on Starlink: voice needs connectivity, the
  clinical answer already on screen does not.
- `/speak` input length cap (`CDSS_SPEAK_MAX_CHARS`, default 2500) — closes the
  open API-hardening item.
- The thin client (`client/cdss_client.py`) carries the same key guard and
  prints the same actionable reason.

### Testing
- `server/test_tts_contract.py` — 13 offline tests, no key, no network, no
  httpx. Mutation checks: drop the `sk_` guard → 3 fail, incl. the key-ID test;
  re-hardcode `voice_support: True` → the meta-test fails; collapse the upstream
  reason back to a generic 500 → the inlining meta-test fails. Suite: 117 tests.

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