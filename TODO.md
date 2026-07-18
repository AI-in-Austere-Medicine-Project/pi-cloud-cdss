# EdgeCDSS — Development Roadmap

Current release: **4.0.0** (see CHANGELOG.md and docs/TECH_NOTES_v4.0.md)
Completed v3-era roadmap items are preserved in git history and CHANGELOG.md.

---

## v4.x — Hardening (in progress)

### Clinical parsing fixes (one fix, one commit, one regression test)
- [ ] Negation handling: "afebrile" must not register as fever
- [ ] Temperature units: disambiguate Fahrenheit vs Celsius by value range
- [ ] Route capture: bare mid-sentence "im" must not silently select IM route
- [ ] Word-boundary matching for short tokens (kid, roc, boy, girl, ket)
- [ ] Overdose detector: recognize "succs" alongside "sux"; add lorazepam ceiling
- [ ] Pediatric-weight validator override must not discard unrelated issues
- [ ] Hypotension detector: require SBP threshold, not isolated DBP / bare "map"

### API hardening
- [ ] Real rate limiting (per token/IP); remove hardcoded rate_limit_remaining
- [ ] /speak input length cap
- [ ] /feedback authentication + field length caps; JSON-format feedback log
- [ ] Separate admin token for /feedback/summary; redact IPs
- [ ] Restrict CORS origins
- [ ] Run LLM calls off the event loop with explicit timeouts
- [ ] Refuse /query (503) when the knowledge base is empty

## v4.x — Research
- [ ] Cross-model comparison: same deterministic harness, OpenAI vs Claude vs Gemini
- [ ] Field deployment: extended unattended operation on solar/battery + Starlink (Tanzania)
- [ ] Feedback review tooling for structured medic reports

## Project 02 — EdgeCDSS Offline
- [ ] Fully offline on-device LLM inference (no cloud dependency)
- [ ] Model evaluation for Jetson-class hardware

## Client
- [ ] cdss_client.py: send X-Access-Token and conversation_history (currently broken against v4 server)
- [ ] Test full cdss_client.py on Android via Termux
