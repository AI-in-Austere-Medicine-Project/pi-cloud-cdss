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

### Found during v4.1 implementation
- [x] **Safety-gate empty-issues fallback could serve what v4.0 would block.**
      Fixed 2026-08-20. `apply_safety_gate` synthesized an issue from the
      validator's rationale when handed an `UNSAFE` with no issues, then fed
      that synthetic text to the override matcher — so a rationale containing an
      override's keywords could downgrade a block into a served response. Now
      the synthesized issue reaches the log but never the matcher: no structured
      issue means fail closed. Genuine issue lists still reach the overrides, so
      SC-3 is intact.
- [ ] **Related, and NOT the same thing:** `is_safe_gate_response()` early-returns
      `SAFE` with `issues=[]`, discarding any validator objection to a
      whitelisted gate question. Strictly better than v4.0, which logged
      `UNSAFE` with `[]` there — an S-2 shape — and the path only carries gate
      questions like "IV or IM? Do you have access?" with no clinical content.
      **Verification note worth keeping:** S-2's second record
      (`cdss_session_2026-07-18.jsonl:11`) does **not** go through this path.
      `is_safe_gate_response("Need exact weight in kg before dosing.")` is
      `False` — that record went through the override path. So this observation
      does not touch either real S-2 record.
- [ ] **The 200-character response preview is itself an observability gap.**
      `log_query()` stores `result["response"][:200]`. Every measured blast
      radius in `AUDIT_v4.1.md` and `PLAN_v4.1.md` that depends on response
      content is therefore a **lower bound** — SC-6's "exactly one record
      affected" was measured this way and cannot see a GIVE line past character
      200. The audit could not have found a dose it could not read.
      **Options:** log the full response text, log a hash plus the preview, or
      raise the cap. Full text has a storage and sensitivity cost worth
      weighing (the system is NO-PHI by policy, but responses quote the query).
      Note SC-1's reset notice now prepends ~120 characters to the response on
      reset turns, which eats into the preview further on exactly the turns
      most worth reading.

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
      **Largely superseded by SC-1** (`18490f6`), which landed 2026-08-20: with
      the context cleared at the patient boundary there is no longer a stale
      weight for the override to be satisfied by. Not closed — the override's
      logic is still wrong, it just no longer has a dangerous input to act on,
      and it still fires when unrelated issues co-occur. Pinned by
      `test_pediatric_override_sc5_gap_is_pinned`, designed to fail the day
      SC-5 proper lands.
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
- [x] /speak input length cap — `CDSS_SPEAK_MAX_CHARS` (default 2500), enforced in `server/tts.py` before the upstream call
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
