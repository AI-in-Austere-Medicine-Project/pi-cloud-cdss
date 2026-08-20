# EdgeCDSS — Development Roadmap

Current release: **4.0.0** (see CHANGELOG.md and docs/TECH_NOTES_v4.0.md).
v4.1 is in progress on branch `v4.1-audit` — see CHANGELOG.md [4.1.0].
Completed v3-era roadmap items are preserved in git history and CHANGELOG.md.

---

## v4.1 — audit remediation, carried forward

`AUDIT_v4.1.md` raised more than v4.1 took on. These are the items that were
**knowingly deferred**, each with the residual risk that decision leaves open
(`PLAN_v4.1.md` §0). They are listed so the residue stays a decision rather than
an oversight. Ordered by what v4.1 leaves most exposed.

### Still open in v4.1 itself
- [ ] **SC-1 — patient-boundary reset** (server detection + client control).
      The audit's most serious finding, S-1: a 6-year-old's 34 kg was carried
      into an adult IED casualty and a dose was served. Held 2026-08-20 for
      owner review of the SC-3 diff and the SC-1 approach. Design input is
      settled — `PLAN_v4.1.md` §5.1 option (c): the measured phrase list, with
      the reset surfaced in the response ("Starting a new patient — previous
      weight cleared") so **both** error directions are visible to the medic.
      §5.2 (inactivity-timeout threshold, and whether `ts` may join the client
      history payload) still needs an answer when this resumes.
      **Residual risk until it lands:** S-1 is reproducible on `HEAD`. SC-2 and
      SC-3 mean a stale weight can no longer cross a boundary *invisibly* — the
      issue survives into the log and the medic gets a banner — but it can
      still cross.

### Deferred by owner decision, with residual risk
- [ ] **F-4 / Q-8 — knowledge-base scope.** The corpus is 89 JTS trauma CPGs;
      users bring DKA, angioedema, tropical infectious disease and dysrhythmia
      questions to it. **Residual:** the *"it just denies anything"* complaint —
      the single highest-frequency user complaint, 6 of 63 substantive queries —
      is driven partly by corpus gaps and partly by Q-1. **v4.1 does not
      measurably improve it.** Q-3 improves retrieval *within* the existing
      corpus, which is a different axis.
- [ ] **Q-1 — generator-emitted non-medical refusal.** The #1 user complaint,
      untouched by v4.1. **Residual:** unchanged.
- [ ] **SC-9 — the second `patient_is_known_or_possible_pediatric` copy.**
      Verified still live on `HEAD` (`PLAN_v4.1.md` §1.4). It gates
      `SEIZURE_PEDIATRIC` in `build_allowed_actions()`; SC-2 does not touch it,
      as the two functions are independent copies. **Residual:** an elderly
      seizure patient without a confirmed weight is still pediatric-gated.
- [ ] **SC-7 (full) — `ALLOWED_ACTIONS` bypasses the dose contract.** The
      minimal form shipped in v4.1 (`30c5ad9`): the hard-coded Keppra dose is
      gone. The structural point stands — `ALLOWED_ACTIONS` text reaches the
      prompt without passing the contract. **Residual:** any future action
      string can reintroduce the same class of defect; a meta-test now fails if
      one carries a dose token, which is a guard, not a fix.
- [ ] **Accept or fix the S-3 helpfulness regression** (was `PLAN_v4.1.md` §5.5,
      reopened by the §0.1 correction). Under SC-6 the S-3 status-epilepticus
      query is a **safety hold**, and SC-7-minimal does not change that — the
      hard-coded dose was never in that prompt; the 1500 mg was
      generator-produced. **Residual:** a medic asking about status epilepticus
      with no weight on file gets a block where a weight-free protocol answer
      would serve them better. Fixing it means widening the seizure trigger list
      (`ststus SZ` matches nothing today) — a change with its own false-positive
      surface — or the Q-1 / corpus work above. **Needs an owner decision.**
- [ ] **SC-4 — narrow the tautological overrides.** The dangerous-reassurance
      override still fires on any response containing `monitor`; the fluids
      override on any containing `fluid`. **Residual:** materially reduced by
      SC-3 — these can no longer release an `UNSAFE`, only downgrade to a banner
      with the issue logged. Validator rule #8 remains effectively unenforceable
      as a *block*.
- [ ] **SC-5 — pediatric-weight override must verify weight ownership.**
      Largely dissolved by SC-1 + SC-2: with the context reset at the boundary
      there is no stale weight to satisfy the override. The override's logic
      stays wrong; the input that made it dangerous goes away.
      **Reassess after SC-1 ships** — do not close it before then. Pinned
      meanwhile by `test_pediatric_override_sc5_gap_is_pinned`, which is
      designed to fail the day SC-5 lands.
- [ ] **SC-8 — transcript dose echo.** The generator can still copy a dose out
      of a prior assistant turn. **Residual:** SC-1 removes the cross-patient
      case; within one patient, echo remains possible.
- [ ] **T-4 — validator non-determinism.** Identical input still produces
      opposite verdicts (S-8). **Residual:** this directly bounds what the
      regression suite can assert — no test in the offline suite may pin what
      verdict the validator *produces*, only what the gate does with one
      (`PLAN_v4.1.md` §3.5).

### Measurement not yet done
- [ ] **Validate that Q-3 improved retrieval, not just alias matching**
      (`PLAN_v4.1.md` §5.4). The 143-spurious-match reduction is measured on the
      matcher. Confirming the downstream effect means re-running the 135 logged
      queries against ChromaDB and comparing `source_mode` distribution before
      and after — ~135 embedding queries, no LLM calls. Would also produce the
      first real baseline for F-1's 27.4% `INSUFFICIENT` rate.
- [ ] **Decide the DKA vent card** (`PLAN_v4.1.md` §5.3). Q-2 fixed the routing;
      a vent-settings query now falls through to RAG over 6 relevant protocols.
      Whether the pH-7.1 DKA case warrants a deterministic card is a clinical
      call and needs owner sign-off on card content.

---

## v4.x — Hardening (in progress)

### Clinical parsing fixes (one fix, one commit, one regression test)
- [x] Word-boundary matching for short tokens (kid, roc, epi); parsed age authoritative
- [x] Fever detection: afebrile negation, clause scoping, Fahrenheit/Celsius disambiguation
- [ ] Route capture: bare mid-sentence "im" must not silently select IM route
- [ ] Overdose detector: recognize "succs" alongside "sux"; add lorazepam ceiling
- [x] Pediatric-weight validator override must not discard unrelated issues — `6c7f535` (SC-3). The override now downgrades and preserves the issue list. Note this is *not* SC-5: the branch still fires when unrelated issues co-occur, it just no longer destroys them. See SC-5 above.
- [ ] Hypotension detector: require SBP threshold, not lone DBP / bare "map"
- [ ] Ketamine dose-candidate condition (is_analg or not is_seizure) tautology

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
- [ ] Extended unattended field deployment (solar/battery + satellite)
- [ ] 30-scenario JTS evaluation set as an automated scored runner
- [ ] Feedback review tooling for structured medic reports

## Project 02 — EdgeCDSS Offline
- [ ] Fully offline on-device LLM inference (no cloud dependency)
- [ ] Model evaluation for Jetson-class hardware

## Client
- [ ] cdss_client.py: send X-Access-Token and conversation_history (currently broken against v4 server)
- [ ] Test full cdss_client.py on Android via Termux
