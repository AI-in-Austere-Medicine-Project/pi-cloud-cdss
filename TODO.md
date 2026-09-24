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
- [x] **The Celsius band excluded hypothermia.** Fixed 2026-09-17 by owner
      decision: `temp` now spans 25-43C and 77-110F (was 35-43C / 93-110F),
      config only. `temp 33` is stored and arms `hypothermia_txa`. Replaying
      the 250 distinct logged and feedback queries, none parses a
      temperature differently.
      **Carried forward:** the bare `t` label now stores `t 30` as 30C where
      it used to reject it visibly — no logged query has that shape. The
      built-in fallback in `vitals.py` still carries 35C / 93F, which only
      applies if the config fails to load and fails in the rejecting direction.
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

### Dose provenance — the class fixed 2026-08-25, and what it left behind

The pre-contract templates that computed a dose without consulting
`drug_contracts` were enumerated and routed as a class (RSI in `1d9eaee`; the
analgesia card, the push-dose/infusion prep cards, the dead paediatric route
card and the seizure bypass in the commit after it). The registry in
`test_drug_contracts.py` — `DOSE_TEMPLATE_CASES`, `DOSELESS_CARDS`,
`NOT_A_DOSE_CARD` — now fails the suite if a served number traces to neither a
signed contract nor a declared backfill, and fails it again if a new response
builder is added without being classified. These two are what that work
deliberately did NOT touch.

- [ ] **`detect_requested_medication_overdose` ceilings never read
      `max_single_dose`.** The ceilings are hardcoded (`wt * 2.0` ketamine,
      `wt * 1.2` rocuronium, `wt * 2.0` succinylcholine) and the refusal text
      QUOTES them at the medic: "exceeds safety ceiling 120.0mg for 60kg
      patient". So a refusal can cite a number the bank no longer agrees with —
      a small lie, but one told at the moment the system is claiming to be the
      authority on the dose. Owner: fix eventually, deliberately deferred from
      the 2026-08-25 change to keep that diff to the serving path. Note the
      ceilings are also drug-level where the contracts are indication-level,
      so this is not a one-line substitution: ketamine's ceiling has to admit
      4 mg/kg IM dissociative sedation without admitting 4 mg/kg as analgesia.
- [ ] **`safety_rules.json` `dose_limits` is a stale mirror of the dose bank.**
      It still carries the retired numbers (ketamine 0.3/2.0/1.5/0.5 mg/kg,
      rocuronium 1.0, succinylcholine 1.5/2.0). Nothing serves them —
      `clinical_router.check_safety_rules()` reads only `condition`,
      `never_give` and `contraindications`, so `dose_limits` reaches no medic
      and no prompt — which is exactly why it will rot unnoticed. It is
      regenerated by `server/tools/build_protocol_index.py`, so deleting the key by hand is
      not the fix; the generator has to stop emitting doses, or the file has to
      start reading them from `drug_contracts.json`.

- [ ] **Signed dose contracts owed: the drugs the free-text dose check now
      holds. Needs an owner decision on content, not format.** Since #70 a dose
      a model states in free text is held unless it is a signed contract value
      for that patient. Measured 2026-09-19 on 568 replayed cloud answers
      (17 held) and on the local-model benchmark (4 real holds). Every hold
      below is a correct refusal under the rule. Each item is the content that
      would turn one into an answer.
      - **Drafted 2026-09-19, awaiting signature:** TXA, fentanyl IV,
        epinephrine (cardiac arrest), dextrose (oral, neonatal IV), atropine
        and levetiracetam have `signoff: false` entries with JTS/SMOG
        citations and verified page numbers. See
        `docs/authoring/CONTRACT_DRAFTS_2026-09-19.md`. The rest of this item
        stands until they are signed.
      - **No signed dose at all.** Any number for these is held.
        - `tranexamic acid` (bank entry, 0 servable): TXA 1-2 g stated four times
          (A1-WT-030, A1-WT-031, A1-NOWT-020, A1-DRIP-004). Needs the
          trauma-haemorrhage regimen: 2 g IV/IO bolus per current JTS, or
          1 g + 1 g over 8 h. The owner picks one.
        - `levetiracetam` (0 servable): 1500 mg load / 1000 mg q12h, four times
          (A1-WT-034, A1-WT-035, H-SESS-030, H-S3). Needs the TBI and status
          load, fixed or per-kg.
        - `cefazolin` (0 servable): 2 g IV for open fracture (A1-WT-036).
        - `moxifloxacin` (0 servable): 400 mg PO, combat wound pack
          (A1-WT-039).
        - `atropine`: **not in the bank at all.** The local model gave 0.25 mg
          for "tacky cardia" (G-DIC-04), held only because it wrote a canonical
          Draw line (SC-6).
        - `clindamycin`: **not in the bank at all.** A cloud answer gave 900 mg
          IV as the cefazolin alternative (A1-WT-036).
      - **Signed, but not for the route or indication asked.**
        - `epinephrine`: 9 servable entries (anaphylaxis, bradycardia, shock),
          **none for cardiac arrest**. The local model said 1 mg for a
          hypothermic arrest (G-TYP-07). Needs an arrest entry: 1 mg IV/IO
          q3-5 min, and the owner's hypothermia modification.
        - `dextrose`: IV only. **No oral glucose entry**, and "awake enough to
          swallow, oral glucose?" drew 20-25 g twice from the local model
          (R2-HYPOGLYCAEMIA-ORAL-ROUTE-POS/-UNLABELLED). Needs a PO entry, with
          the AMS/airway precondition the oral-route cautions already carry.
        - `fentanyl`: **IN only** (1 mcg/kg). Cloud answers gave IV 25-100 mcg
          three times (A1-WT-001, A1-WT-002, A1-WT-003). Needs an IV entry, or
          a decision that IN is the only fentanyl route served.
      - **Signed, but not built for that question.** No new content needed;
        the behaviour needs deciding.
        - [x] `naloxone` (3 servable, 2 fixed-dose): "naloxone dose" with no
          weight built nothing (A1-NOWT-013), because the dose builder built
          nothing without a confirmed weight, even for a fixed dose. **Fixed:**
          signed fixed-dose entries now build for an adult with no weight. A
          child and per-kg entries still need one.
        - `lorazepam` (2 servable): given as a substitute when midazolam was
          asked for (A1-WT-012).
        - `ketamine` (12 servable): a range for "pain meds" with no drug named
          (H-SESS-013), and 24 mg against a contract list (A1-DRIP-001).
          Freelanced numbers, not missing content.
      - [x] **Coverage limit of the check itself.** It knew only drugs in the
        contract bank, so free-text "atropine 0.5 mg" or "clindamycin 900 mg"
        passed it. **Fixed:** `drug_lexicon.json` lists 167 drugs the bank
        does not carry, and a stated dose of any of them now holds. A word on
        neither list still passes.
      - [x] **Known false positive.** A concentration restated in words ("for
        every milliliter ... there are 10 mg of levetiracetam", G-ADV-10) was
        read as a dose. **Fixed**, with that answer verbatim as a must-not-hold
        test.

### Safety gate

- [ ] **Validator invents equipment preconditions and blocks contract-signed doses.**
      An override attempt (branch `wip/equipment-precondition-override`,
      discarded 2026-09-17) keyed on drug+route and could pass doses the
      contract never signed for the situation. A correct fix must key on the
      signed indication and fail closed when the indication is not signed.
      Reproduce cases:
      - `server/feedback.log` line 49 (entry 48, 2026-09-03, device
        `web-0wfzq4`): query "500mg / 10ml", held with "Response recommends
        100 mg ketamine IV for sedation without confirming the presence of an
        infusion pump." Medic: "Strange it held on this - its a safe dose to
        give." Not in `docs/FEEDBACK_REVIEW_2026-09-03.md` (covers 0–47); the
        earlier turns were never captured, so the 100 mg came from the
        generated path and can't be replayed exactly.
      - Holes the override opened (each must stay blocked under any fix):
        100 kg, ketamine 100 mg IV "sedation" with no pump established — the
        bank signs 100 mg only as the pump-available loading dose (ruling 7);
        50 kg, ketamine 100 mg **IM** — no IM entry signs 100 mg at 50 kg, but
        the IV induction entry vouched for it because route wasn't compared;
        50 kg, ketamine 100 mg IV labelled sedation — the signed repeated-bolus
        sedation dose is 25 mg, the 100 mg is induction; a second dose line
        outside the canonical "Draw X mL" form (midazolam IV 5 mg, no contract)
        rode along unchecked.
      - Tests: `server/tests/test_equipment_precondition.py`. Two xfail
        (strict) false blocks — the signed no-pump 50 mg bolus at 100 kg held
        for "no pump", and the 100 mg loading dose held with "infusion pump
        available" in the history. The four holes above are plain tests that
        pass today and must keep passing. Note the deterministic check passes
        all four holes on main; the validator's verdict is the only thing
        holding them, so the fix cannot lean on `run_deterministic_checks` as
        it stands.

### Deterministic cards owed

- [x] **Pediatric IV ketamine needs dilution guidance before it serves a volume.
      Needs an owner decision — content, not format.** **Decided 2026-09-18
      (#65):** 5 mg/mL (1 mL + 9 mL NS) as an owner-declared `push_dilution` on
      the SMOG paediatric analgesia entry (0.2 mg/kg = 0.04 mL/kg), in CAUTIONS,
      the brief and the refusal; not in `drug_concentrations.json`. Not applied
      to NASEMSO 0.25 mg/kg (no longer served to children) or to the adult|peds
      0.5 mg/kg post-intubation sedation entry. At the signed 50 mg/mL
      vial, the analgesia dose (0.25 mg/kg) is a fraction of a millilitre at
      every paediatric weight: 10 kg is 2.5 mg = **0.05 mL**, 25 kg is 6.25 mg =
      **0.125 mL**, 40 kg is 10 mg = 0.2 mL. Below 10 kg it is refused outright
      — 5 kg computes 0.025 mL, under the 0.05 mL floor
      `drug_concentrations.drawable()` enforces — and the medic is told the dose
      "likely needs a dilution the kit has not declared" without being told
      which. The brief now states the volume conditionally ("At 50 mg/mL that's
      0.125 mL — confirm vial"), so the small number is on the first screen.

      **What the corpus states, checked 2026-09-18** (133 ketamine chunks,
      quotes verified against the source PDFs):
      - Every ketamine concentration any guideline in the corpus prepares is an
        **INFUSION** mix: "MIX: 750mg (1.5 vials of 500mg/5mL) in 250mL of
        normal saline (3mg/mL solution)" (JTS ID61, Appendix B, p.9); "250 mg
        of Ketamine in 250 ml of normal saline" (Pain Anxiety Delirium, p.8);
        "MIX 500 mg/500 mL CONCENTRATION 1 mg/mL" (SMOG CY24, p.128).
      - **No guideline in the corpus states a ketamine PUSH dilution, a
        paediatric preparation, or a target concentration for push.** The push
        guidance is a RATE, not a concentration: "IV/IO Push (over 1 min)"
        (SMOG CY24, p.127), and "Rapid IV administration may cause hypotension,
        apnea, or laryngospasm" (same page).
      - The corpus does carry a **drug-agnostic dilution table** whose 50 mg row
        gives exactly the recipe below: 50 mg into 10 cc = **5 mg/mL**, with
        "1ml drug + 9ml fluid = 10ml solution" (SMOG CY24, p.71). It names no
        drug, so it sources the ARITHMETIC, not the choice to apply it to
        ketamine.
      - Dilution recipes for other drugs ARE stated and are the precedent for
        the shape: naloxone "Dilute 0.4mg (1mL) with 9mL normal saline" (JTS
        ID61, Appendix C, p.10), and push-dose epinephrine, which is already
        signed and serving.

      So the concentration itself is an OWNER DECLARATION, not a citation — the
      `owner_declaration` block, the way ketamine's no-pump sedation entry
      already is.

      **Recommended shape — mirror push-dose epinephrine exactly.** That entry
      carries its dilution as CAUTIONS on the dose entry, not as card prose:
      "DILUTED preparation: prepare 10 mcg/mL by diluting 1 mL of epinephrine
      0.1 mg/mL in 9 mL of normal saline" and "0.01 mg/kg equals 0.1 mL/kg of
      that dilution". Two properties worth copying: the card renders it with no
      new template code, and the **mL/kg** form states the volume without
      deriving a millilitre from a concentration nobody signed.

      **Recommended concentration: 5 mg/mL** (1 mL of the 50 mg/mL vial + 9 mL
      NS = 10 mL — the same "1 mL + 9 mL" shape as the epi card). At
      0.25 mg/kg that is **0.05 mL/kg**: 0.25 mL at 5 kg, 0.5 mL at 10 kg,
      1.25 mL at 25 kg, 2 mL at 40 kg. Nothing is refused, nothing is a
      hundredths-of-a-mL read, and the biggest paediatric analgesia draw stays
      under 3 mL.
      - **1 mg/mL** is the alternative with the strongest anchor — it is the
        concentration the two guidelines above actually prepare — but at
        0.25 mL/kg it is 6.25 mL at 25 kg and 12.5 mL at 50 kg, and the
        citation is for an infusion, so using it for a push is still an
        extrapolation the owner declares.
      - **Do NOT use 10 mg/mL.** WHO lists ketamine as a stocked vial strength
        at both 10 and 50 mg/mL (`drug_contracts.json`, ketamine forms), so a
        10 mg/mL syringe is indistinguishable from a stocked vial — the exact
        confusion the concentration fence exists to prevent.

      **Scope it to the low-mg/kg indications.** 0.25 mg/kg analgesia, and
      optionally 0.5 mg/kg post-intubation sedation (0.1 mL/kg at 5 mg/mL). NOT
      1-2 mg/kg — paediatric dissociative sedation and RSI induction already
      draw 0.2-1.6 mL from the 50 mg/mL vial, and diluting those turns a 1 mL
      push into a 10 mL one.

      **Do NOT declare the dilution in `drug_concentrations.json`.** It is a
      prepared syringe, not a vial, and declaring it would (a) make ketamine's
      signed presentations two, which silently switches off the brief's
      conditional volume line, and (b) let `audit_volume_lines` accept a
      "5mg/mL ketamine" GIVE line as a stocked strength.

      **Related content question, same sign-off (the DOSE, not the volume).**
      The served paediatric analgesia dose is NASEMSO's 0.25 mg/kg, which that
      guideline applies to all ages. SMOG CY24's ketamine monograph (p.127)
      states a separate PAEDIATRIC column: analgesia **IV 0.1-0.2 mg/kg**,
      IM 0.5 mg/kg — lower than what is served — plus "Children <3 mo. age" as
      a contraindication and "Dosing between 0.5-0.9 mg/kg IV ... should be
      avoided" (emergence phenomenon). None of that is in the contract entry.
      Decide whether the paediatric analgesia dose stays at 0.25 mg/kg with
      NASEMSO's all-ages scope, or gets its own peds entry.
      - [x] **Decided 2026-09-18 (#65): its own peds entry.** SMOG CY24 p.127,
            IV **0.2 mg/kg** (the top of its 0.1-0.2 range), "Age < 3 months"
            contraindication — a STATED age under 3 months blocks the dose on
            every route (`min_age_months`), and on every ketamine entry a
            child can be served (RSI induction, post-intubation and loading
            sedation, dissociative sedation); an unknown age does not — and
            "avoid 0.5-0.9 mg/kg IV" caution. For a child it
            supersedes NASEMSO's 0.25 mg/kg, which stays signed for adults and
            is named on the peds entry as the general-EBM alternate. SMOG's
            paediatric IM 0.5 mg/kg is NOT entered. At 0.2 mg/kg the vial draw
            is 0.004 mL/kg, refused below 12.5 kg — which is what the dilution
            above now has to cover, on the peds entry rather than on NASEMSO's.

      **Follow-ons once the entry carries a dilution caution:**
      - [x] The brief's conditional volume should say the dilution's volume, or
            say "dilute first" — otherwise the brief quotes 0.125 mL of the
            vial while the card underneath says to dilute, which is the
            contradiction the 2026-09-18 cleanup removed. **Done:** both, from
            the entry's `push_dilution` record.
      - [x] `drawable()`'s refusal text names no dilution ("a dilution the kit
            has not declared"). Once one is declared for a drug, it should name
            it. **Done:** named when the entry declares one for that vial.

- [ ] **Weight-only infant guard for ketamine.** Owner decision 2026-09-19
      (#66). The under-3-months age floor (`min_age_months`) blocks only a
      STATED age; with no age, a 4 kg infant is dosed and shown "Age < 3
      months" as a contraindication. Wanted: when the confirmed weight is
      **< 5 kg and the age is unknown**, hold the peds-only ketamine entries
      and ask ONE question — the age — before serving; a stated age then
      either clears the floor or triggers the existing block. Scope: peds-only
      entries (analgesia, RSI induction, dissociative sedation); the adult|peds
      entries are enforced by the same floor once the age is known.
      - Open: where the question lives (a pre-gate beside 2j-0, like the
        weight and route asks), and whether the < 5 kg threshold should come
        from a signed source rather than a fixed number.
      - Tests: 4 kg, no age → one age question, no ketamine dose; then
        "2 months" → block; then "4 months" → dose. 5 kg, no age → dose as
        today.

- [ ] **Post-intubation TBI management card.** `docs/FEEDBACK_REVIEW_2026-09-03.md`
      §1, priority entry 9 — "asked for 3 times; does not exist". Entries 0, 26
      and 38 all wanted the same thing: BP targets, sedation, vent targets,
      EtCO2 goals for a patient whose tube is already in. Entry 0 asked for it
      on 07-18 and got a safety block instead.
      - Severe-TBI generation surfaces SBP target / 3% saline / levetiracetam
        in ~1 of 5 runs despite correct JTS_GROUNDED retrieval (cos 0.71). The
        specifics belong in a deterministic TBI management card with SOURCE
        ID30 — same card as post-intubation TBI. Until then the harness row is
        a known coin flip.
      - Measured 2026-09-03 on `severe TBI patient GCS 6 BP 90/60 needs
        management`, in-process, 5 runs at `c751fab`: 1 emitted "3% hypertonic
        saline 250-500 mL", 4 did not. Routing is stable and correct every run
        (`tbi_neurosurgery_deployed_environment`, HIGH), and the router's
        enhanced query already carries "hypertonic saline / levetiracetam /
        SBP" — so this is a generation gap, not a retrieval or routing one, and
        no threshold should be tuned for it. Identical at `dd2ec14`: not
        introduced by #53.
      - Citation to confirm when the card is authored: the corpus stores
        titles, not CPG ids, so ID30 could not be verified from the repo. Note
        it holds two distinct adult TBI CPGs — "TBI Neurosurgery Deployed
        Environment" (what the router matches) and "Traumatic Brain Injury
        PFC". The card should cite whichever actually carries the SBP target,
        3% saline and levetiracetam text.

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

## Brief first — follow-ups

- [ ] **Voice branch reads the brief.** The voice work (its "actions" mode) is
      not on origin at the time of writing. When it lands, the actions mode must
      speak `brief` and nothing else. `/speak` already prefers a `brief` in the
      body over `text` (`server/main.py`, pinned by
      `test_speak_says_the_brief_and_nothing_else`), so the voice branch should
      send `brief` rather than build its own short form. A second summariser would
      reintroduce the reworded-dose risk the brief is built to exclude. Voice
      input should also send `input_mode: "voice"`, which `/query` already
      accepts.
- [ ] Owner review of the "critical" rule in `server/brief.py`: recorded
      contraindications that are SPECIFIC to the indication (hypersensitivity /
      allergy boilerplate is excluded since 2026-09-17), plus DON'T lines saying
      "never"/"contraindicated" or naming a dosed drug. It decides which lines
      are required in the brief.
      It no longer decides folding for DON'T, which never folds (owner decision
      2026-09-17). Headings like "SUCCINYLCHOLINE — CONTRAINDICATED" on a
      generated answer still fold; decide whether they should.
- [ ] New portal screenshots for the release notes. The 4.3 set predates brief-first
      (see the README screenshot note).
- [ ] Measure whether the generator's `**BRIEF**` section pushes long RSI-shaped
      answers into `max_tokens=700` truncation. A truncated tail loses SOURCE first.
      Measured 2026-09-17 from the eval harness: gpt-4o-mini (the default, no
      reserve) peaked at 311 output tokens including the validator, so no risk
      there. Sonnet/Opus/Gemini/Grok carry reserve_tokens 3000. Unmeasured:
      claude-haiku-4-5 and gpt-4o (reserve 0) — at Sonnet-length (~650-700
      tokens) plus a brief, the disclaimer/SOURCE/TLDR tail could be cut; DON'T
      has 180-300 tokens behind it and would survive.
      **Flagged since 2026-09-17** (owner decision: flag, not hold): a
      generator stop at the token limit now prepends a visible notice, logs
      the issue, downgrades a clean verdict to NEEDS_HUMAN_REVIEW, and logs
      `generation_truncated` (schema 11). **Still open:** the validator's own
      max_tokens=300 stop is not flagged; /speak says the brief, so the notice
      is not spoken; and the rate on haiku-4-5 / gpt-4o is still unmeasured —
      the schema-11 field makes it countable.
- [ ] Consider logging `brief` (log schema 12). It is now the first thing a
      medic reads, and `response_preview` (200 chars) cannot reconstruct it.

## Client
- [ ] cdss_client.py: send X-Access-Token and conversation_history (currently broken against v4 server)
- [ ] Test full cdss_client.py on Android via Termux
