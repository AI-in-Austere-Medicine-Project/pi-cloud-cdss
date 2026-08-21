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
- [x] **F-4 / Q-8 — knowledge-base scope.** Resolved 2026-08-21 as *deliberate
      general-knowledge fallback now, curated corpus expansion later* (owner
      decision). A query whose retrieval comes back `INSUFFICIENT` is answered
      from the model's general medical knowledge, banner-labelled and logged
      `source: "general"`, instead of refused. **The corpus is unchanged** — it
      is still 89 JTS trauma CPGs, and the DKA / angioedema / tropical
      infectious disease / dysrhythmia gaps are still gaps; they are now
      answered from a labelled second source rather than not at all.
      **Carried forward:**
      - [ ] Curated corpus expansion — the actual fix for the gaps above.
      - [ ] Measure whether the fallback moves the *"it just denies anything"*
            complaint rate. The `source` field in the schema-3 log makes this
            countable for the first time; nothing has been measured yet.
      - [ ] Q-1 is untouched and is the other half of that complaint.
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

## Vitals — carried forward

- [ ] **The caution table is narrow on purpose and is not clinically signed
      off.** `server/vitals_rules.json` ships six rules chosen to be
      uncontroversial (hypotension-risk drugs at low SBP, respiratory
      depressants at low RR/SpO2, AV-nodal blockers at low HR, TXA at low temp,
      oral route at low GCS). **Needs an owner decision** on whether that set is
      right and what else belongs in it. A caution that fires on most responses
      stops being read, which is why it starts small rather than complete.
- [ ] **Measure the caution rate before widening the table.** `vitals_cautions`
      in the schema-4 log makes this countable. If cautions attach to a large
      fraction of answers, NEEDS_HUMAN_REVIEW stops meaning anything — the
      verdict is now reachable two ways and the log cannot yet distinguish a
      validator-driven review from a caution-driven one without reading the
      field.
- [ ] **Staleness is displayed but not enforced.** A 40-minute-old blood
      pressure is marked in the strip and its age reaches the prompt, but
      nothing refuses to reason about it. Whether an old vital should stop
      arming a caution — and at what age — is a clinical call.
- [ ] **The Celsius band excludes hypothermia. Needs an owner decision.**
      `temp` ships with a plausible range of 35-43C and 93-110F. The Fahrenheit
      band reaches 33.9C, the Celsius band stops at 35, so `temp 33` is rejected
      as unreadable while `temp 93 F` — the same patient — is stored. It also
      means `hypothermia_txa` can only arm from a Fahrenheit reading. Lowering
      `temp.min` in `server/vitals_rules.json` fixes it with no code change; the
      question is what the floor should be for a trauma population where
      hypothermia is a real presentation, not a typo.
- [ ] **No structured vitals entry.** Capture is free-text only, which is what
      was asked for. A dedicated input would remove the parser from the path for
      medics who prefer fields.

## v4.x — Hardening (in progress)

### Clinical parsing fixes (one fix, one commit, one regression test)
- [x] Word-boundary matching for short tokens (kid, roc, epi); parsed age authoritative
- [x] Fever detection: afebrile negation, clause scoping, Fahrenheit/Celsius disambiguation
- [ ] Route capture: bare mid-sentence "im" must not silently select IM route
- [ ] Overdose detector: recognize "succs" alongside "sux"; add lorazepam ceiling
- [x] Pediatric-weight validator override must not discard unrelated issues — `6c7f535` (SC-3). The override now downgrades and preserves the issue list. Note this is *not* SC-5: the branch still fires when unrelated issues co-occur, it just no longer destroys them. See SC-5 above.
- [x] Hypotension detector (`has_hypotension_or_shock`): word-anchored. `"ams"`
      matched *milligrams*/*grams*/*diagrams*/*exams*, `"altered"` matched
      *unaltered*, `"map "` matched *roadmap*. **Carried forward:**
      - [ ] It still routes on the WORD "map", not the value, so "MAP 90" reads
            as shock. The vitals table now derives a real MAP per turn; this
            detector takes only a string and would need the context passed in.
            Do it with the eval harness, where the routing change can be scored.
- [ ] Substring failure class, specimens 5 and 6 — found by audit, NOT fixed
      here because each changes clinical routing and deserves its own review:
      - [ ] `is_cico_query`: `"cric"` matches **cricoid**. "apply cricoid
            pressure during intubation" classifies as can't-intubate-can't-
            oxygenate. Fails safe (an extra surgical-airway check, never a
            missed one), so it is noise rather than danger — but it is noise on
            the loudest check in the system.
      - [ ] `is_ketamine_analgesia_context`: `"ket "` matches **blanket **.
            "put a warming blanket on him, he has a leg fracture" reads as a
            ketamine analgesia context. Hypothermia prose and pain prose
            co-occur constantly in trauma, so this is not a rare shape.
      - [ ] `build_allowed_doses` `is_analg`: `"arm"` matches *warm*, *harm*,
            *alarm*. Latent — downstream gates masked it in every probe — but
            the flag itself is wrong.
- [ ] Ketamine dose-candidate condition (is_analg or not is_seizure) tautology

### API hardening
- [ ] Real rate limiting (per token/IP); remove hardcoded rate_limit_remaining
- [x] /speak input length cap — `CDSS_SPEAK_MAX_CHARS` (default 2500), enforced in `server/tts.py` before the upstream call
- [ ] /feedback authentication + field length caps; JSON-format feedback log
- [ ] Separate admin token for /feedback/summary; redact IPs
- [ ] Restrict CORS origins
- [ ] Run LLM calls off the event loop with explicit timeouts
- [ ] Refuse /query (503) when the knowledge base is empty

### Docs owed for 4.2.0
- [ ] `docs/TECH_NOTES_v4.2.md` and `web/release-notes-4.2.html`. README links
      still point at the 4.1 documents and say so; CHANGELOG carries the full
      4.2.0 section in the meantime.

### Retrieval (scoped for the eval-harness phase — do not tune thresholds ad hoc)
Measured 2026-08-21 against the live 8,559-chunk corpus, re-embedded with the
same all-MiniLM-L6-v2 the server uses. Numbers and method in `docs/RETRIEVAL_DIAGNOSIS_2026-08-21.md`.
- [ ] **Narrative dilution is the real failure.** Clean burn queries retrieve
      burn CPG chunks at 0.40–0.51 (well inside JTS_GROUNDED). The live queries
      were conversational and multi-topic — *"his Tesla rear ended a semi and
      he's got broken bones and estimated 70% burns"* — and mean-pooled MiniLM
      averages the burn clause away: −0.023 on the medic's own words. The fix is
      query construction (clause splitting, multi-query retrieval, or reranking),
      not a threshold. Needs the harness to score.
- [ ] **The router is the mitigation, not the cause.** Its enhanced query lifted
      those live cases by +0.12 to +0.18 and was the only reason burn chunks
      surfaced at all. It costs ~0.04 on short clean queries. Worth measuring
      properly before anyone "simplifies" it away.
- [ ] **A HIGH-confidence router match should be able to reach its document.**
      The router named "Burn Wound Management in Prolonged Field Care" with HIGH
      confidence, the corpus held 233 burn chunks, and the answer still came
      from general reference. Source-filtered or source-boosted retrieval on a
      confident route is the obvious lever; it is a real behaviour change and
      belongs behind the harness.
- [ ] **PDF ligature corruption.** 53% of burn-CPG chunks contain `ﬁ`/`ﬂ`
      ligatures against 9% corpus-wide — "ﬂuid" appears in 50 burn chunks,
      ASCII "fluid" in only 26. The tokenizer splits `ﬂuid` into two rare
      tokens; cosine("fluid", "ﬂuid") is 0.37 in this model. Secondary to
      dilution, but it is a corpus defect and re-ingesting with NFKC
      normalisation is cheap. Requires a DB rebuild, so it is a deploy, not a
      patch.
- [ ] **`classify_retrieval` clamps at zero.** `score = 2·cos − 1`, so anything
      below cosine 0.5 is negative and prints as 0.0-ish. The log now shows the
      cosine alongside; consider whether `confidence` on the wire should stop
      being clamped too.

## v4.x — Research
- [x] Cross-model comparison harness: model is config (`server/providers.json`),
      Anthropic and OpenAI both wired, and `log_schema` 3 records which model
      answered. Gemini would be a config entry against its OpenAI-compatible
      endpoint. **Carried forward:**
      - [ ] Build the comparison set and a scored runner. Most of the 24-case
            suite returns at a deterministic pre-gate **before any model call**,
            so swapping models changes nothing on those cases — a real
            comparison has to be built from queries that reach the generator.
            The schema-3 `model` field plus the 135 logged queries are the
            inputs for selecting that subset.
      - [ ] Decide whether cross-model runs should also vary `validator_model`.
            It is deliberately pinned today so a generator comparison changes
            one variable; measuring the validator itself is a separate run.
- [ ] Extended unattended field deployment (solar/battery + satellite)
- [ ] 30-scenario JTS evaluation set as an automated scored runner
- [ ] Feedback review tooling for structured medic reports

## Project 02 — EdgeCDSS Offline
- [ ] Fully offline on-device LLM inference (no cloud dependency)
- [ ] Model evaluation for Jetson-class hardware

## Client
- [ ] cdss_client.py: send X-Access-Token and conversation_history (currently broken against v4 server)
- [ ] Test full cdss_client.py on Android via Termux
