# Work order: EdgeCDSS safety and routing

The owner's work order of 2026-09-24, with the additions and rulings since.
The owner's wording is kept where it was given. This file is the plan of record.
Session notes are not.

Status is as of 2026-09-26. The owner updates it, or it is updated in the PR that
closes an item.

## Global rules

- **One work item per PR.** Stop for the owner's review after each. Never merge.
- **Safety items (A-series):**
  - The failing test is committed FIRST, on its own, then the fix.
  - Never loosen a gate.
  - The dose check stays indication-specific.
- **After every safety change, replay the served answers** (537 at the time of the order) and report:
  - newly held, each one read and classified as a true or false positive;
  - newly released, which must be zero;
  - cloud regressions, which must be zero.
- **Every PR reports** the files touched, the suite count, and the live-harness result against a second uvicorn, never against the live service.
- **Never restart the live service or touch its `.env`.**
- **Every benchmark row records** the git commit, the signed-entry count, the Ollama version, the power mode and the kernel.
- **Format and label changes must not change** what is decided, held or dosed.
- **Report format per item:** what changed, why it was wrong, the failing test and what it proves, the replay delta, and anything found that isn't on this list.

Rules the owner added on later items:
- Do not merge an unsigned state; re-sign in the same PR.
- A missing contract must hold; never serve an uncited value.
- Benchmarks: if a key is missing or a model errors, record it and skip. Do not substitute.

## Order

Items are listed by clinical consequence. They are done in this order unless the owner reorders them.

| # | Item | Status |
|---|---|---|
| — | Live fix: explicitly selected model waited for 60 s; fallback bannered | **done**: #88, merged and deployed |
| A0 | Context isolation on patient reset | **next** |
| A1b | Dose check matches indication, not only value | after A0 |
| A1 | DCR routing failure | **done**: #82, merged and deployed |
| A2 | Deterministic severe-TBI card | **done**: #84, merged and deployed |
| A3 | Already-intubated patients receiving the RSI bundle | in review: #86 |
| A7 | GCS parser | after A3 |
| A4 | Depressed-GCS oral route | open |
| A5 | Hold text for fixed doses | open |
| A6 | Contraindicated procedures (design only) | open |
| B1 | Source-mode labelling | open |
| B2 | Generator section headers | open |
| C1 | Feedback instrument | open |
| D1 | Evaluation hygiene | open |
| D2–D6 | not yet specified | owner to supply |

Owner asks outside the lettered items:

| Item | Status |
|---|---|
| 3% NaCl contract, signed at 7.5 g | in review: #85 |
| Multi-model benchmark run 3 | in review: #87 |

**Merge order (owner, 2026-09-25):** #87 now; #85 and #86 after the owner reads them.

## Items

### Live fix: the 8 s fallback substituted qwen for slow cloud models (done, #88)

When a user explicitly selects a model, the cloud timeout is 60 s, not 8. The 8 s fast fallback applies only to the default model. Any local-fallback answer shows the badge prominently in the brief area, not just the footer. Every fallback is logged with the model that was requested. Both paths are tested.

### A0: context isolation on patient reset (added 2026-09-25, ahead of A3)

Benchmark run 3, finding 3 (G-MTN-05):
- After an explicit "different patient now", the patient context reset.
- ALLOWED_DOSES still held the previous patient's lorazepam 4 mg for active seizure.
- gemini-3.1-pro served that dose inside a tension-pneumothorax answer. The validator said SAFE.

Requirement: after "new patient" or "different patient", ALLOWED_DOSES, vitals, weight and history must be empty. Test that a previous patient's dose can never appear in the next patient's allowed list. Failing test first.

### A1b: the dose check matches indication, not only value (added 2026-09-25, ahead of A3)

Benchmark run 3, finding 2 (H-S3):
- The query was "status SZ, maxed out on versed".
- ALLOWED_DOSES held midazolam 5 mg (agitated or violent patient) and 0.5 mg (PFC sedation).
- It did not hold the signed midazolam *active seizure* entry.
- Four arms served "midazolam IV 5 mg … Indication: agitated or violent patient" to a seizing patient. The check passed it because 5 mg is a signed value.

Requirement: a signed seizure entry must be offered for a seizure query, and a 5 mg "agitated patient" midazolam must hold when the indication is seizure. Failing tests first.

### A1: DCR routing failure (P1) (done, #82)

"80 kg male, GSW left thigh, tourniquet on 20 min, HR 118, BP 104/68" returned GENERAL MEDICAL REFERENCE, not DCR ID18. It had no TXA, no blood-product priority and generic first aid, and the validator said SAFE.

- **Step 1 (diagnose only):** report the router match and score, the top-5 retrieval hits and distances, the classify_retrieval result, and the exact reason DCR was not selected. Run these variants and report the routing for each:
  - "gunshot wound thigh bleeding controlled with TQ";
  - "penetrating trauma, hemorrhagic shock";
  - "massive hemorrhage, tourniquet applied";
  - "blast injury, bilateral leg amputations, TQs on".
- **Step 2 (after the owner's go):** the smallest fix. Do NOT regenerate protocol_index.json. Add the original query and 2 variants to run_tests.sh, asserting DCR and TXA in the output.

**Rulings on the false positives (2026-09-24):**
1. **Tension pneumothorax signs** (absent or decreased breath sounds, JVD, tracheal deviation, hyperresonance) route to needle decompression and thoracic injury (ID74), never to the DCR card. If both shock physiology and tension signs are present, the tension card fires first and carries "then reassess for hemorrhage — DCR". Test both orders.
2. **Injury pattern alone does not fire DCR** when the query asks something else specific: another drug, a vent setup or a procedure. The DCR check moves after the vent card and the dose paths.
3. **No HR > 100 rule under age 16.** Use age-appropriate tachycardia only if a paediatric threshold is cited (SMOG, PALS).
4. **"Bleeding controlled", "hemorrhage controlled" and "TQ effective"** are not bleeding terms for the HR and shock-index rules.
- Also: the DCR card's SOURCE line is ID18 with its printed page, and the TXA line serves the signed 2 g dose verbatim. Keep the canine filter. The heat-stroke corpus gap is a TODO content item.

### A2: deterministic severe-TBI card (done, #84)

A card for GCS ≤ 8 with a head injury:
- the SBP target (ID30);
- the levetiracetam 1500 mg load from the signed contract;
- 3% hypertonic saline for herniation signs from the signed entry, held if unsigned;
- EtCO2 35–45;
- head of bed raised;
- DON'T hyperventilate;
- evacuation criteria;
- SOURCE lines to ID30 and ID63 with printed pages.

An already-intubated patient gets the same card with the airway lines suppressed. The brief follows the 3-slot rule. A child routes to the card with the levetiracetam line held unless a paediatric entry is signed.

### A3: already-intubated patients receiving the RSI bundle (in review, #86)

This was the subject of 4 field reports (feedback review §1). A completed-airway detector ("already intubated", "tube is in", "we RSI'd", "on the vent", "being ventilated") suppresses should_use_rsi_pregate regardless of other content, and the is_vent_settings_query vocabulary is widened.

Tests: the real queries from the review route away from RSI, and a genuine pre-intubation RSI request still routes to it.

### A7: GCS parser (added 2026-09-25, a separate PR after A3)

The GCS parser reads "GCS is seven", "GCS 3T", "GCS of 6" and "G6", with a test for each.

### A4: depressed-GCS oral route

Oral-route advice with GCS < 13, or "unresponsive", "altered" or "obtunded", must hold. That covers "encourage fluid intake", "sips of water", "PO", "by mouth", "oral glucose" and similar.

Tests: GCS 7 with "encourage fluid intake" holds; GCS 15 with the same phrase passes.

**Run 3 finding 4, placed here:** the oral-intake hold fires on correct "nothing by mouth" answers. In the 120 s pass, every held cloud answer on R2-DEPRESSED-GCS said nothing by mouth.

### A5: hold text for fixed doses

A fixed-dose hold must never say "no weight confirmed". The hold text names the actual reason and what makes the question answerable. Test: 4 fixed-dose hold cases.

### A6: contraindicated procedures (design only)

DESIGN ONLY, no code. Propose a deterministic check for dangerous non-dose advice, starting with a small signed table of procedure, contraindicating condition and source:
- LP in raised ICP;
- NG tube in basilar skull fracture;
- nasal airway in midface or basilar fracture;
- oral intake with depressed GCS (overlaps A4);
- succinylcholine with hyperkalaemia, burns over 24 h, or crush.

Report the proposed table, the matching approach, the false-positive risks, and how it would be signed like a contract. Wait for the owner's go.

### B1: source-mode labelling

A response whose served dose comes from a JTS-cited signed contract is JTS-grounded, regardless of retrieval score. The SOURCE line must carry the contract's citation. The evidence is a fentanyl IV query labelled "general" with ID61 chips showing. Test with that query. Format only.

### B2: generator section headers

Headers drift in brief mode: "SEVERE TBI", "TREAT", "EVAC IF", and both "SOURCE" and "SOURCES". Normalise them at parse time to the canonical set: DO THIS, GIVE, WATCH, DON'T, EVAC, TLDR, SOURCE. Unknown headers fold into the nearest canonical section. Test on 3 captured generator outputs. Format only.

### C1: feedback instrument (feedback review §5)

- A persistent session id (sessionStorage, try/catch).
- `/feedback` carries the query id, the conversation history used, model, provider, validator_result and source_mode.
- The comment field actually posts.
- Propose, don't apply, a re-derived ISSUE_TAGS list from the 22 flagged entries.
- Tests for the schema.

### D1: evaluation hygiene (one PR)

- **(a)** run_tests.sh gains:
  - the DCR case (A1);
  - the 6-year-old 20 kg ketamine case, asserting 4 mg, the 5 mg/mL dilution and the SMOG source;
  - the fentanyl label case (B1).
- **(b)** Reconcile the 30-scenario runner set against docs/EdgeCDSS_JTS_Evaluation_Set_30, the authored set with pre-written failure criteria. Report the differences; don't change either yet.
- **(c)** Write the benchmark protocol into the doc:
  - ethernet, Wi-Fi and LTE physically disconnected;
  - a timestamped connectivity probe before, during and after, saved next to the results;
  - full response text;
  - 3 local passes.

### D2–D6: not yet specified

These were named in the owner's instruction of 2026-09-26 but aren't defined in any order received so far. They are left for the owner to supply. Nothing is inferred here.

## Findings placement (benchmark run 3, docs/MULTI_MODEL_BENCHMARK_2026-09-25.md)

| Finding | Placed in |
|---|---|
| 1. The hybrid fallback silently substituted qwen for slow cloud models | Live fix, #88 (done) |
| 2. A seizing patient was served a behavioural-emergency midazolam dose (H-S3) | **A1b** |
| 3. A previous patient's dose crossed an explicit reset (G-MTN-05) | **A0** |
| 4. The oral-intake hold fires on correct refusals (R2-DEPRESSED-GCS) | **A4** |
| 5. Uncited numbers served unheld: crystalloid volumes and rates (H-IM-06), cefazolin 20–30 mg/kg (G-ADV-03), levetiracetam concentrations (G-ADV-10) | **the free-text dose check** |
| 6. The validator holds TXA for plain haemorrhage (H-S2, H-S1-a, G-MTN-01) | **the TXA validator hold** |

Findings 5 and 6 have been placed but not yet given an item letter.

## Found along the way, not yet placed

- A ketamine drip for pain gets the RSI bundle ("ketamine drip" is an RSI term).
- A unitless weight ("he is 150") silently skips the RSI card.
- gpt-4o hits the organisation's 30,000 TPM limit on a sequential 30-set.

## Deferred (do not touch)

- neonatal dextrose;
- the fentanyl adult label rename;
- voice;
- the local-model portal toggle;
- the Go sentinel.
