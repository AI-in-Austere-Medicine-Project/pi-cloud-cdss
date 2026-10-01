# Work order: EdgeCDSS safety and routing

The owner's work order of 2026-09-24, with the additions and rulings since.
The owner's wording is kept where it was given. This file is the plan of record.
Session notes are not.

Status is as of 2026-09-27. The owner updates it, or it is updated in the PR that
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

Items are listed in the owner's execution order (2026-09-26, below), done items first. They are done in this order unless the owner reorders them.

| # | Item | Status |
|---|---|---|
| — | Live fix: explicitly selected model waited for 60 s; fallback bannered | **done**: #88, merged and deployed |
| A1 | DCR routing failure | **done**: #82, merged and deployed |
| A2 | Deterministic severe-TBI card | **done**: #84, merged and deployed |
| D6 | Training toolchain (Mac) | **done**: #93, merged (Mac tooling; nothing deployed) |
| A0 | Context isolation on patient reset | **done**: #90, merged and deployed |
| A1b | Dose check matches indication, not only value | **done**: #91, merged and deployed |
| A3 | Already-intubated patients receiving the RSI bundle | **done**: #86, merged and deployed |
| A4 | Depressed-GCS oral route | **done**: #95, merged and deployed |
| A5 | Hold text for fixed doses | **done**: #97, merged and deployed |
| A6 | Contraindicated procedures: table, detectors, check | **done**: #99, merged and deployed. P3 and P5 signed: #100, merged; P1 and P2 unsigned |
| A7 | GCS parser | **done**: #101, merged |
| A8 | "status post" must not match status epilepticus | **done**: #102, merged |
| A9 | Active-seizure phrasings reach the signed entry | **done**: #103, merged and deployed |
| A14 | "Absent lung sounds" is a tension sign | **done**: #106, merged |
| A15 | Ketamine for benzodiazepine-refractory seizure: contract entry | **done**: #105, merged and deployed (option B, signed by the owner) |
| A10 | CICO card must not fire on a completed surgical airway | **done**: #107, merged |
| A11 | Free-text dose check reads infusion rates | **done**: #108, merged |
| A12 | Succinylcholine leaves ALLOWED_DOSES under a P5 condition | **done**: #109, merged and deployed |
| A13 | Remove the dead safety_rules.json path | **done**: #110, merged and deployed |
| A11b | Rate matching is indication-specific | **done**: #110, merged and deployed |
| A16 | Deterministic norepinephrine drip card (signed per-kg rate) | **done**: #110, merged and deployed |
| A17 | Abbreviated drug names in the dose check (the router's slang table) | in review (owner, #114 review: next item, before D1b) |
| D5a | Full-answer logging | **done**: #111, merged and deployed |
| D1 | Evaluation hygiene | **done**: #112, merged |
| D5 | Distillation dataset builder | **done**: #113, merged |
| D5b | Second dataset run: junk rule, seeds, paraphrases | in review: #114; rulings applied: 258 rows (239 train / 19 valid), 16 held in review; for the owner to merge and train |
| D1b | Authored 30-set: draft docs/EVALUATION_SET_30.md for owner sign-off | after D5b |
| B1 | Source-mode labelling | after D6 |
| B2 | Generator section headers | after B1 |
| B3 | Vitals caution on an answer that already refuses oral intake | after B2 |
| C1 | Feedback instrument | after B3 |
| D2 | Prompt layout for prefix caching | after C1 |
| D3 | Retrieval trim to 4 chunks | after D2 |
| D4 | Show the deterministic part first | after D3 |
| E1 | Validator wording sensitivity | after D4 |

Owner asks outside the lettered items:

| Item | Status |
|---|---|
| 3% NaCl contract, signed at 7.5 g | **done**: #85, merged and deployed |
| Multi-model benchmark run 3 | **done**: #87, merged and deployed |
| This work order | **done**: #89, merged |

**Merge order (owner, 2026-09-25):** #87 now; #85 and #86 after the owner reads them. Done: all three merged 2026-09-26.

**Execution order (owner, 2026-09-26, sixth statement; replaces the earlier five):** A3 (#86) → A4 → A5 → A6 → A7 → A8 → A9 → A14 → A15 → A10 → A11 → A12 → A13 → A11b → A16 → D5a → D1 → D5 → D1b → D6 → B1 → B2 → B3 → C1 → D2 → D3 → D4 → E1. A0, A1b, A3, A4, A5, A6, A7, A8, A9, A14, A15, A10, A11, A12, A13, A11b and A16 are done (#90, #91, #86, #95, #97, #99, #101, #102, #103, #106, #105, #107, #108, #109, #110; the A list is closed); D6, D5a, D1 and D5 are done (#93, #111, #112, #113). D5b was added after D5 by the owner in the #113 review; D1b follows it. B3 was added after B2 by the owner in the #95 review. A14 and A15 were placed after A9 by the owner in the #103 review. A11b and A16 were placed after A13 by the owner in the #108 review. A11 was added after A10 by the owner in the #97 review; A12 and A13 after A11 in the #98 review. E1 was added after D4 by the owner on 2026-09-29.

**Owner, 2026-09-28:** after A12, A13, A11b and A16 the A list is done, then D5a. A13, A11b and A16 are delivered together in #110 on the owner's instruction. Every open A item finishes before any D item starts. Safety before speed, no exceptions. Same rules; stop for review on each.

**Owner, 2026-10-01 (#114 review):** A17 is the next item, before D1b.

## Items

### Live fix: the 8 s fallback substituted qwen for slow cloud models (done, #88)

When a user explicitly selects a model, the cloud timeout is 60 s, not 8. The 8 s fast fallback applies only to the default model. Any local-fallback answer shows the badge prominently in the brief area, not just the footer. Every fallback is logged with the model that was requested. Both paths are tested.

### A0: context isolation on patient reset (done, #90)

Benchmark run 3, finding 3 (G-MTN-05):
- After an explicit "different patient now", the patient context reset.
- ALLOWED_DOSES still held the previous patient's lorazepam 4 mg for active seizure.
- gemini-3.1-pro served that dose inside a tension-pneumothorax answer. The validator said SAFE.

Requirement: after "new patient" or "different patient", ALLOWED_DOSES, vitals, weight and history must be empty. Test that a previous patient's dose can never appear in the next patient's allowed list. Failing test first.

### A1b: the dose check matches indication, not only value (done, #91)

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

### A3: already-intubated patients receiving the RSI bundle (done, #86)

This was the subject of 4 field reports (feedback review §1). A completed-airway detector ("already intubated", "tube is in", "we RSI'd", "on the vent", "being ventilated") suppresses should_use_rsi_pregate regardless of other content, and the is_vent_settings_query vocabulary is widened.

Tests: the real queries from the review route away from RSI, and a genuine pre-intubation RSI request still routes to it.

### A7: GCS parser (added 2026-09-25; done, #101)

The GCS parser reads "GCS is seven", "GCS 3T", "GCS of 6" and "G6", with a test for each.

**Added (owner, #95 review):** a GCS written as components ("E4V5M6") is read too. Until then A4 fails closed on it: it arms the oral-route hold even when the total is 15.

### A4: depressed-GCS oral route (done, #95)

Oral-route advice with GCS < 13, or "unresponsive", "altered" or "obtunded", must hold. That covers "encourage fluid intake", "sips of water", "PO", "by mouth", "oral glucose" and similar.

Tests: GCS 7 with "encourage fluid intake" holds; GCS 15 with the same phrase passes.

**Run 3 finding 4, placed here:** the oral-intake hold fires on correct "nothing by mouth" answers. In the 120 s pass, every held cloud answer on R2-DEPRESSED-GCS said nothing by mouth.

**Done: #95, merged and deployed.** Also covers "oral <drug>" for any drug in the contract bank, drug_lexicon.json or MEDICATION_TERMS, fluids included (owner, #95 review).

**Owner rulings (#95 review, 2026-09-27):**
1. **GCS 13 and 14 stay armed.** The hold fails safe; only a plain GCS 15 disarms it. A narrow release for GCS 13–14 with "alert", "protecting airway" or "able to swallow" stated can be its own item later, if the hypoglycaemia case proves common.
2. **Two correct refusals stay held.** Recorded as findings, not fixed: run 3's haiku-4.5 p1 ("Any oral intake with GCS ≤8 risks food/fluid into lungs") and opus-5 t120 ("not a reason to drink", "no wet swabs he can swallow"). Their wording falls outside the narrow refusal shape, and widening it would release answers that are held today.

### A5: hold text for fixed doses (done, #97)

A fixed-dose hold must never say "no weight confirmed". The hold text names the actual reason and what makes the question answerable. Test: 4 fixed-dose hold cases.

### A6: contraindicated procedures (done, #99; P3 and P5 signed, #100)

DESIGN ONLY, no code. Propose a deterministic check for dangerous non-dose advice, starting with a small signed table of procedure, contraindicating condition and source:
- LP in raised ICP;
- NG tube in basilar skull fracture;
- nasal airway in midface or basilar fracture;
- oral intake with depressed GCS (overlaps A4);
- succinylcholine with hyperkalaemia, burns over 24 h, or crush.

Report the proposed table, the matching approach, the false-positive risks, and how it would be signed like a contract. Wait for the owner's go.

**Design approved (#98).** The proposal is [`A6_CONTRAINDICATED_PROCEDURES_DESIGN.md`](A6_CONTRAINDICATED_PROCEDURES_DESIGN.md), with the owner's rulings in §7. In short: P1 and P2 stay unsigned drafts; P3 is mid-face trauma only; P5 is burns (no timing), spinal cord injury and hyperkalaemia (K ≥ 5.5 mmol/L, an owner ruling); P4 stays as A4's code. Every row ships with `signoff: false`, and the owner signs P3 and P5.

**Done: #99, merged and deployed.** `server/procedure_contracts.json` holds P1, P2, P3 and P5.

**Signed (#100, merged):** P3 and P5 signed by Andrew Azelton on 2026-09-27. P3 cites ID80 p.18. P5 cites ID40 p.3 alone (owner ruling, #100): the 2026 ID39 p.28 doses succinylcholine but lists no contraindication. The ID40 passage is on printed p.3 = PDF p.3. P1 and P2 stay unsigned and inert. Replay with the signed table: 0 newly held, 0 newly released.

### A8: "status post" must not match status epilepticus (owner, 2026-09-26; found in #91; done, #102)

The dose builder's seizure trigger is the substring `'status'`. "159lb male unable to ventilate effectively status post oral trauma" (H-SESS-002, also in the live logs) is offered lorazepam 4 mg for active seizure: a non-seizure patient offered a seizure dose.

This is the same class as "stab" in "stable" and "14G" read as grams: a lexical match firing on a substring.

Failing tests first. Negatives: "status post", "post-status" and "status: stable" must not reach the seizure entry.

### A9: active-seizure phrasings reach the signed entry (owner, 2026-09-26; found in #91; done, #103)

"80kg male actively seizing" never reaches the dose builder. The fixed ACTIVE SEIZURE card answers "benzodiazepine per local protocol" with no signed dose, even with a weight and a signed entry.

- "actively seizing", "seizing now", "still seizing" and "in status" must reach the active-seizure entry the same as "active seizure" does.
- Add the phrases to the lexicon, with a failing test per phrase first.
- Report any other seizure phrasing in the stored queries that gets no signed dose today.

**Owner ruling (A9, 2026-09-28): the card carries the dose.** A9's premise was that "active seizure" reaches the signed entry. It didn't: the fixed ACTIVE SEIZURE card intercepted "active seizure" and every "seizing" phrasing, with no dose. Every active-seizure phrasing now gets the card, with the signed GIVE line the builder resolves for the patient (A2's pattern). No weight: the card asks for one. A benzodiazepine already given: no further benzodiazepine dose. Eclampsia stays off the card.

**Stored seizure queries with no signed dose (A9's report, before the fix):** 11 distinct stored queries have a seizure phrasing. 3 got the doseless card, 6 got no signed dose (most state no weight; one is eclampsia) and 2 reached a signed entry (both levetiracetam). After #103, each gets the card with the signed dose where a weight resolves one.

**Owner ruling (#103 review, 2026-09-28): the second line.** "If patient does not respond to benzos, you can offer levetiracetam", and ketamine is a known second- and third-line drug for status: most rescue and EMS systems don't carry levetiracetam. When the card sees a benzodiazepine already given, it offers levetiracetam by role from its signed status-epilepticus entries, and names ketamine for when levetiracetam isn't carried, citing JTS ID91 p.28, with no dose until a ketamine entry is signed (A15). The evidence is in [`authoring/KETAMINE_SECOND_LINE_SEIZURE_EVIDENCE.md`](authoring/KETAMINE_SECOND_LINE_SEIZURE_EVIDENCE.md).

### A14: "absent lung sounds" is a tension sign (owner, #103 review; found in #101; done, #106)

The tension check reads "absent / decreased / no … breath sounds" or "air entry", not "lung sounds". A live-log query, "shot in the chest … blood pressure 80/40 … absent lung sounds on the left side", gets the DCR card, not the tension card that A1's ruling 1 puts first. Failing tests first, including that query verbatim; the negation rules stay as they are.

### A15: ketamine for benzodiazepine-refractory seizure (owner, #103 review; done, #105)

A contract entry for ketamine, indication "refractory seizure (benzodiazepine-refractory)". The ACTIVE SEIZURE card already serves it once signed. The sources and the two dose options (A: 100 mg fixed adult, 1 mg/kg child IM/IN, per Scheppke 2024; B: 2 mg/kg IV/IO, 3–4 mg/kg IM, the observed doses in Finney 2026, as the signed dissociative doses) are in [`authoring/KETAMINE_SECOND_LINE_SEIZURE_EVIDENCE.md`](authoring/KETAMINE_SECOND_LINE_SEIZURE_EVIDENCE.md). The owner rules the dose and signs; the entry is drafted unsigned.

**Owner ruling (2026-09-28): option B, ketamine as the second drug.** "B - Ketamine as second drug. Sign off with me Andrew Azelton." Signed by the owner in #105 (#104 was closed by GitHub when #103's branch was deleted): adult IV/IO 2 mg/kg, IM 3–4 mg/kg (the engine serves a range's minimum, 3 mg/kg); child IV/IO 1 mg/kg, IM 3 mg/kg, 3 months and over. Owner-declared (declared_by "Andrew Azelton - AI-AIM"): no approved source states a ketamine seizure dose. The ACTIVE SEIZURE card (#103) serves ketamine first after a benzodiazepine, then "If ketamine is not available: levetiracetam". Done ahead of A14 because it completes #103's card.

**Cautions (owner, 2026-09-28):** hypoxia and BVM readiness as two served lines: "Hypoxia: transient hypoxia in 22% … Monitor SpO2 and EtCO2 continuously." and "Have BVM and suction ready before giving: 31% needed bag-valve-mask support and 7% a supraglottic airway." Re-signed.

### A10: the CICO card must not fire on a completed surgical airway (owner, 2026-09-26; found in #86; done, #107)

The CICO check is a substring match with no state (`"cric" in q`, `openai_client.py:4580`). Live on the #86 branch, "80kg male, cric'd, what do I give after RSI" was served "Declare CICO … Perform surgical airway / cricothyrotomy now" for a patient whose cric was already in.

Same class as A8: a substring match with no state. One bug per PR, so it is not in #86.

Failing tests first: "cric'd", "cric is in" and "surgical airway in place" must not get the CICO card. A genuine CICO request ("Help me do a cric", "failed intubation, failed i-gel, sats are 71") still must.

### A11: the free-text dose check reads infusion rates (owner, #97 review; found in #97; done, #108)

"Start epinephrine 5 mcg/min" or "0.05 mcg/kg/min" to an adult with no signed rate built is served with no hold: the free-text dose check doesn't read rates at all. Same class as run-3 finding 5 (uncited numbers served unheld).

Requirement (owner): the free-text dose check reads rates (mcg/min, mcg/kg/min, mg/hr, mL/hr, units/hr) and compares them to signed rate entries the same way it does single doses. A rate for a drug with no signed rate entry holds. Failing tests first: the epinephrine 5 mcg/min case, a ketamine drip case, and a control where a signed rate passes.

**Rate entries in the bank today** (104 entries, 64 signed; checked 2026-09-27 on `e3a7b3e`):

| Drug | Signed rate entries | Unsigned rate drafts (`NEEDS_MANUAL_ENTRY`) |
|---|---|---|
| epinephrine | symptomatic bradycardia — infusion, adult, 0.02–0.2 mcg/kg/min; shock unresponsive to IV fluids — infusion, adult and peds, 0.05–0.3 mcg/kg/min | infusion for refractory shock, adult |
| norepinephrine | vasodilatory/haemorrhagic shock infusion, adult, 0.05–0.5 mcg/kg/min; vasodilatory shock infusion, peds, 0.05–0.5 mcg/kg/min; symptomatic bradycardia — infusion, adult, 0.02–0.4 mcg/kg/min; cardiogenic shock / pulmonary oedema with SBP under 100, adult, 0.02–2.0 mcg/kg/min | — |
| ketamine | none (its two signed "infusion"-named entries are mg/kg boluses) | prolonged sedation infusion |
| fentanyl | none | analgesia infusion, adult |
| midazolam | none | sedation infusion for the ventilated patient, adult |
| propofol | none (no signed entry at all) | sedation infusion, adult |

**What will start holding:** every stated rate for any drug other than epinephrine and norepinephrine. That includes ketamine, fentanyl, midazolam and propofol drips, and any mcg/min or mL/hr rate for the other signed drugs (atropine, calcium gluconate, dextrose, levetiracetam, lorazepam, morphine, naloxone, rocuronium, 3% NaCl, succinylcholine, TXA). All signed rate entries are per kg, so an epinephrine or norepinephrine rate also needs a weight to compare against. A plain mcg/min rate ("5 mcg/min") has no signed entry to match, and holds.

**Owner rulings (#108 review, 2026-09-28):**
1. **Rate matching by drug is accepted for now.** A11b makes it indication-specific, after A13.
2. **Any rate inside a signed range passes.** A signed rate range is a titration range, and every value in it is signed. (A single-dose range still serves its minimum.)
3. **Norepinephrine always holding is A16**, a deterministic norepinephrine drip card, after A11b and before D5a.
4. **Uncited IV fluid rates stay on the found list.** Closing it needs signed crystalloid entries, which is the owner's authoring job.

### A12: succinylcholine leaves ALLOWED_DOSES under a P5 condition (owner, #98 review; done, #109)

When a P5 condition (burns, spinal cord injury, hyperkalaemia) is present, the builder doesn't offer succinylcholine. A dose-layer change, kept out of A6.

### A13: remove the dead safety_rules.json path (owner, #98 review; found in #98; in review, #110)

`clinical_router.check_safety_rules()` matches `safety_rules.json` against the query, and the result goes only to a console print. Remove it, with a test that nothing depended on it.

### A11b: rate matching is indication-specific (owner, #108 review; in review, #110)

A11 matches a stated rate against any of the drug's signed rate entries for the patient's population. Make it indication-specific, the same shape as A1b: a rate is checked against the entries for this patient's indication (for example, epinephrine for symptomatic bradycardia against 0.02–0.2 mcg/kg/min, not the shock range). Failing tests first.

### A16: a deterministic norepinephrine drip card (owner, #108 review; found in #108; in review, #110)

Models answer a norepinephrine rate question in flat mcg/min ("2–20 mcg/min"), which A11 holds: every signed norepinephrine rate is per kg per minute, and nothing serves one. Add a deterministic norepinephrine drip card serving the signed per-kg rate, the way the epinephrine drip card does. Failing test first: the "norepinephrine 2–20 mcg/min" answer is held, and the card is served.

### A17: abbreviated drug names in the dose check (owner, #114 review; found in D5b)

**Owner, 2026-10-01:** "Abbreviated drug names in the dose check is A17, next item, before D1b. Add the router's slang table to the dose-check lexicon: amio, mag, bicarb, levo, epi, norepi, roc, sux, versed, ativan, and the rest of that table. 'ami' is excluded as ambiguous. Failing tests first with the four examples you gave; replay with each newly held read."

**What was wrong:** the free-text dose check finds a drug by name (the contract bank, then `drug_lexicon.json`). It did not know the router's slang (`query_aliases.json`). A dose written as "amio 150 mg IV", "mag 2 g IV" or "levo 5 mcg/min" was attributed to no drug and passed, while "amiodarone 150 mg IV", "magnesium 2 g IV" and "norepinephrine 5 mcg/min" were held. It failed open; only the LLM validator stood behind it.

**Built:**
- `drug_contracts.recognised_drug_index()` gains a third layer under the bank and the lexicon: `slang_drug_aliases()`. The bank always wins.
- Each `query_aliases.json` entry is resolved through its expansion to the one drug it names.
  - Added to the check: bicarb, mag, levo, vec, dilt, del tim, vaso, rocky onium, push dose epi, dirty epi, epi drip, norepi drip.
  - Already recognised: epi, ket, roc, sux, succs, versed, ativan, keppra, levophed (norepi was already a bank alias).
- **Excluded:**
  - "ami" (amiodarone or acute MI);
  - any entry the table marks "context-dependent" ("k");
  - non-drug entries (cric, blood, tq, march, king, cat, rsi);
  - multi-drug entries ("pressors").
- "amio" is not in the router's table. It joins `drug_lexicon.json` as an amiodarone alias, so the dose check changes and routing does not.

**Tests:** `server/tests/test_slang_dose_check.py`, committed first: 30 failed and 8 passed on main.
- amio 150 mg, mag 2 g, levo 5 mcg/min and bicarb 1 g are now held, naming the drug.
- The abbreviation and the full name get the same verdict.
- Every drug alias in the table is recognised; "ami" and "k" are not; non-drug entries are not drugs; the bank still wins.
- `bicarb 50 mEq` is `xfail(strict)`: see the finding below.
- `test_drug_lexicon.py::test_a_missing_lexicon_narrows_to_the_bank` now allows slang that names bank drugs.

**Replay** (main 957b372 against A17):

| Corpus | Answers | Newly held | Newly released | Changed |
|---|---|---|---|---|
| Served answers (cdss-eval runs) | 1,191 | 0 | 0 | 0 |
| Held answers | 113 | 0 | 0 | 0 |
| Pipeline, model stubbed (bank, runs, live queries) | 788 | — | — | 0 |
| D5b teacher answers (train, valid, review) | 274 | 0 | 0 | 0 |

No stored answer states a dose under one of these abbreviations, so there is no newly held answer to read.

**Finding (correcting the D5b finding): single doses in units, IU or mEq are not read by the free-text check under any name.**
- With nothing signed, each of these passes: "sodium bicarbonate 50 mEq IV", "potassium chloride 20 mEq IV", "insulin 10 units IV", "heparin 5000 units IV", "heparin 5,000 IU IV", "vasopressin 40 units IV".
- Rates in units are read ("heparin 1000 units/hr" is held, A11).
- D5b's "bicarb 50 mEq" example passed because of the unit, not only the abbreviation.
- Insulin, heparin and potassium are high-alert drugs.
- **Proposed as its own item, with a failing test first and replay; the owner places it.**

### B1: source-mode labelling

A response whose served dose comes from a JTS-cited signed contract is JTS-grounded, regardless of retrieval score. The SOURCE line must carry the contract's citation. The evidence is a fentanyl IV query labelled "general" with ID61 chips showing. Test with that query. Format only.

### B2: generator section headers

Headers drift in brief mode: "SEVERE TBI", "TREAT", "EVAC IF", and both "SOURCE" and "SOURCES". Normalise them at parse time to the canonical set: DO THIS, GIVE, WATCH, DON'T, EVAC, TLDR, SOURCE. Unknown headers fold into the nearest canonical section. Test on 3 captured generator outputs. Format only.

### B3: vitals caution on an answer that already refuses oral intake (owner, #95 review)

The caution table's oral-route rules (`vitals_rules.json`, group `oral_route_aspiration`) match "by mouth" inside "nothing by mouth". So they append "Anything by mouth carries an aspiration risk" to an answer that already says NPO (#95 live harness, claude-sonnet-5). Format only. After B2.

### C1: feedback instrument (feedback review §5)

- A persistent session id (sessionStorage, try/catch).
- `/feedback` carries the query id, the conversation history used, model, provider, validator_result and source_mode.
- The comment field actually posts.
- Propose, don't apply, a re-derived ISSUE_TAGS list from the 22 flagged entries.
- Tests for the schema.

### D1: evaluation hygiene (one PR; done, #112)

**Placement (owner, 2026-09-26):** after A7 and before D5. D1 is measurement only. Run on deployed main after every A item is done, it gives the clean pre-training baseline that the D6 bench compares against. Same snapshot rule as run 3.

- **(a)** run_tests.sh gains:
  - the DCR case (A1);
  - the 6-year-old 20 kg ketamine case, asserting 4 mg, the 5 mg/mL dilution and the SMOG source;
  - the fentanyl label case (B1).
- **(b)** Reconcile the 30-scenario runner set against docs/EdgeCDSS_JTS_Evaluation_Set_30, the authored set with pre-written failure criteria. Report the differences; don't change either yet.
  - **Moved to D1b (owner, 2026-09-28):** the authored set can't be found (not in the repo or its history, on the Jetson, or in Drive). D1 goes ahead without it.
- **(c)** Write the benchmark protocol into the doc:
  - ethernet, Wi-Fi and LTE physically disconnected;
  - a timestamped connectivity probe before, during and after, saved next to the results;
  - full response text;
  - 3 local passes.

### Rules for the D series (owner, 2026-09-26)

The global rules above apply, as for the A items:
- One change per commit.
- The failing test comes first wherever a test applies.
- Never loosen a gate.

**After every D item, the replay must show:**
- 0 newly held;
- 0 newly released;
- byte-identical deterministic answers.

**Each D item ends with a before/after table** on the 30-scenario set. It gives the median latency, p95 latency and prompt tokens, for the local arm and one cloud arm.

### D2: prompt layout for prefix caching

Reorder the LLM prompt so that:
- everything fixed comes first: system instructions, card format, tone rules;
- everything per-query comes last: retrieved chunks, patient state, the question.

Ollama reuses the KV cache when the prefix is identical. Measure prefill time before and after, using `eval_count` and `prompt_eval_duration` from the Ollama response.

Assert that the rendered prompt is otherwise unchanged: the same content in a different order. Specifics-present and the free-text dose check must be unaffected.

### D3: retrieval trim

Cut the number of chunks passed to the model from the current top-k to 4. Use a reranker or a score threshold, whichever is cheaper on the Jetson. The canine filter stays.

**Gate:**
- the replay is unchanged;
- specifics-present on the cloud arm is not worse than the run-3 figure;
- the DCR and TBI routing tests still pass.

Report the prompt tokens saved per query.

### D4: show the deterministic part first

The gates, the signed dose line and the card header are computed in code in about 40 ms. Render them immediately, and fill in the model's prose when it arrives.

**Hard rules:**
- No model-written text containing a number reaches the screen until the free-text dose check has passed on the complete response.
- No streaming of partial prose.
- If the check holds the response, the deterministic part stays and the hold message replaces the prose.

Add a test that a held response never shows any model-written dose.

### D5a: full-answer logging (owner, 2026-09-26; its own PR, before D1 and D5)

Logging starts as soon as this deploys, so the next dataset comes from real serving.

- Failing test first: schema 14, with the full answer present on every served and every held response.
- Replay unchanged.
- Same retention and access rules as the existing query logs. The full answer is no more sensitive than the query already stored.
- A disk estimate: mean answer length × current daily query volume.
- Log rotation set so the Jetson can't fill up.

**Built (#111):** log schema 14 adds `response` (the full text the medic saw, the hold text when held), `held_response` (the model's own text the gate held), `full_answer_dropped`, and `model_returned` (the model the provider's reply named for the generator call, beside `model`, the one asked for; owner, 2026-09-30); `response_preview` stays. Same file, same daily rotation, same retention and access; nothing is deleted. Estimate, measured on the Jetson's 35 days of logs: about 1.9 KB per entry, about 25 MB a year at the mean volume, about 175 MB a year at the peak day's volume held every day, against 1.7 TB free. Rotation: files already rotate daily; over `CDSS_LOG_DIR_MAX_BYTES` of session logs or under `CDSS_LOG_MIN_FREE_BYTES` of free disk (2 GiB each by default), the full-answer fields are null with the reason and the rest of the entry is still written. **Owner, 2026-09-28 (#111 review): keep all logs.** Session logs are never deleted by age; the guard above is the only limit. **Owner, 2026-09-30:** #111 merged and deployed. `model_returned` names the generator's reply only; recording the validator's reply waits for E1.

### D5: distillation dataset builder

Script: `tools/build_distill_dataset.py`.

**Waits for (owner, 2026-09-26):** A0 and A1b merged and deployed (met: 894ffd9), and D1 done (met: #112). **Owner, 2026-09-30:** D5 does not start until D5a is merged and deployed. The dataset is built from replay against the main that contains both. The refuse-to-run check below is A1b's indication matcher: D5 imports it and does not reimplement it.

**Source (owner, 2026-09-26): (a) regenerate now, and (c) log full answers from now on. Not (b).**

**(a) Regenerate now.**
- Take the stored production queries that pass the D5 filters: single patient, no history, model-reaching.
- Replay each through the live prompt path against **`claude-opus-5`** as the teacher, with the cloud timeout at 120 s. This is the exact model string the run-3 Opus arm sent: `providers.json` id `claude-opus-5`, passed unchanged as `model` by the Anthropic adapter at 580836e (`mm3t120-claude-opus-5-p1`, `model_requested` and `model_used` `anthropic/claude-opus-5`). The 77% specifics figure belongs to it. The teacher must be the model that was measured; do not substitute one that wasn't in run 3.
- Use the production gpt-4o-mini validator and the free-text dose check exactly as deployed.
- Keep only rows that are served, not held, and that pass the A1b indication check.
- Every row's metadata records the teacher model, the snapshot commit and the contract bank version.
- **Before the run,** report the row count and the cost estimate. **Stop for approval if the estimate is over $40.**

**(b) is out.** The 30-scenario set and the 27 `run_tests.sh` queries are the evaluation set. No query from either may appear in train or valid. This is a hard exclusion in the builder, with a test.

**(c) Log full answers from now on:** its own item and PR, D5a, before D5 (below).

**Exclude:**
- every held card;
- every answer a fallback substituted (the `fallbacks` field is non-empty);
- every deterministic-only answer. Those never need a model.

**Output:**
- Messages-format JSONL (system, user, assistant), built with the exact live prompt path, not a re-rendered copy, so the training distribution equals the serving distribution.
- A 90/10 split by scenario id, not by row, so no scenario appears in both.
- Written to `data/distill/train.jsonl` and `data/distill/valid.jsonl`. Both are untracked.

Print the counts per scenario and per drug.

**Single patient, no prior history (owner, 2026-09-26):** every training row is one turn, one patient, no conversation history. Rows whose source query had history are excluded, not truncated. This keeps the A0 leak class out of the training set by construction.

**Format (owner, 2026-09-26):** identical to `~/edgecdss-train/data-dryrun/{train,valid}.jsonl` (messages triples: system, user, assistant), so the D6 Makefile targets run on it unchanged.
- The reference is a one-row synthetic fixture, `tools/distill/fixtures/format_example.jsonl`. It is written by hand with placeholder content, not copied from data-dryrun.
- The Jetson-side test and the D6 Makefile's preflight both check against that same file.
- data-dryrun stays where it is, on the Mac.

**Coverage report, not a filter (owner, 2026-09-26):** print row counts for the ten most common scenario types, and warn if any has fewer than 20 rows. Do not drop or rebalance rows to hit a target.

**Refuse to run** if any row contains a dose that is not the signed value for that drug and indication.

**Unasked drugs (owner, 2026-09-29; found in the D1 air-gap bench):** any teacher answer that names a drug the question didn't ask about, and that has no signed entry for that question, is excluded. The builder prints how many rows this removes. It is stricter than "served, not held": the free-text dose check holds only a stated dose, and this filter also drops the drug named without one.
- **Why:** in the D1 air-gap bench (`cdss-eval/runs/d1-airgap-qwen2.5-3b-local-p1..p3`, main 3fe16a4), the local model added doses nobody asked for to the single-drug B1 query "80 kg adult, severe pain from a femur fracture, fentanyl IV". Pass 2 added naloxone 0.4 mg, ketamine 30 mg and ketamine 0.3 mg/kg; pass 3 added naloxone 0.4 mg and naloxone 25–50 mcg. The free-text dose check held both answers, correctly: nothing signed covered those doses for that question. The validator was not involved. Pass 1 added no other drug and was served.
- **What it means for D5 and D6:** the dataset must contain no such rows, so the trained model learns not to add them.

**Built (#113, merged):** `tools/build_distill_dataset.py`, tests `server/tests/test_distill_dataset.py`.
- **Source:** session-log entries that are not synthetic (`X-Test-Run`), have `history_turns` 0 and a query, de-duplicated by normalised text (case, punctuation, "80kg"/"80 kg"). The scenario id is that normalised text; the scenario type is the router's matched protocol, or "unrouted".
- **Evaluation set, hard exclusion, before any call:** every query in `run_tests.sh` (current turn and history, parsed from the file) and in the 30-set. The 30-set is pinned as sha256 hashes of its normalised queries in `tools/distill/eval_exclusions.json`, with the bank's own sha256 (`76c2bed9…`): the repository is public, so the text is not committed.
- **Replay:** `_query_with_rag_internal(query, model="claude-opus-5")` on the deployed tree (refuses if it has uncommitted changes), `CDSS_LLM_SELECTED_TIMEOUT=120` in the builder's own process, the deployed validator and checks. The row's system prompt and user turn are what the live code passed to `providers.chat`, captured at the call. The builder never writes the session log.
- **Kept only if:** a model was called; no fallback; not held; not truncated; the teacher's text reaches the medic unchanged (a notice may be added, nothing altered); `run_deterministic_checks` (which applies A1b's `indication_matched`) finds nothing; no unasked drug. Then every row is checked again and the run refuses, writing nothing, on any dose that is not signed.
- **Output:** `data/distill/{train,valid}.jsonl` in the fixture's shape (the D6 format check passes). Metadata (teacher, `model_returned`, snapshot commit, contract bank sha256/version/signed count, concentrations sha256) is on the same line of `{train,valid}.meta.jsonl`, because a key on the row would fail the D6 preflight. `manifest.json` has the counts.
- **Cost:** `--plan` selects and prices with no model call. The ceiling (700 + 3,000 reserve output tokens per call at $5/$25) stops the run over $40 unless `--approve-cost` is given.

**First run (2026-09-30, deployed main d0b44f4, bank 1.4.0, 68 of 108 signed):**
- 79 distinct single-turn production queries (975 synthetic, 181 with history and 48 evaluation-set entries left out). 41 are answered by a deterministic card on this main; 38 reached the teacher. Estimate: $1.19 expected, $4.04 ceiling.
- Excluded: 13 unasked drug, 2 held. No fallback, truncation or check failure. **Kept 23: train 21, valid 2** (2 scenarios). Refuse-to-run: passed.
- Unasked drugs: dextrose 5, ketamine 5, morphine 2, calcium gluconate 2, atropine 2, and 14 others once each.
- Scenario types: unrouted 17, burn_management_pfc 2, airway_management_of_traumatic_injuries 2, drowning_management 1, pain_anxiety_delirium 1. All are under 20 rows.
- Drugs named in the kept answers: ketamine 1, rocuronium 1.

**For the owner's ruling before D6 trains on it:**
1. **Junk queries pass every filter.** 8 of the 23 kept rows are not clinical questions: stray keystrokes, an abusive line, pasted pip output, and a pasted coding-assistant instruction the teacher answered with git commands. Nothing in the filters above removes them, and no filter was added without a ruling.
2. **Too few rows to train on.** 21 train rows, 17 of them unrouted, and almost no dosing. Most of the dose-bearing production questions now go to deterministic cards (41 of 79), and the unasked-drug filter removes about a third of what's left.

**Resolved (2026-09-26):** production session logs kept only the first 200 characters of each answer (`response_preview`, `openai_client.py:256`), so they could not supply training answers. The owner chose (a) and (c) above.


### D5b: second dataset run (owner, 2026-09-30, #113 review; one PR)

**Owner:** "merge as is; the builder is right and the finding is the point."

**Finding recorded (owner):** on this main (d0b44f4), **41 of the 79 real single-turn questions are answered without a model.** They go to deterministic cards, so the teacher never writes them and they can't be training rows.

**The six points:**
1. **Junk rule.** A kept row must route to a protocol, name a lexicon drug, or contain a parsed vital. Rows that fail all three go to `data/distill/review.jsonl` for the owner, not into train. The 8 junk rows of the first run are dropped now, by hash. Tested with the abusive line, the pip paste and the git prompt as negatives, and an unrouted clinical question as a positive.
2. **Seeds.** Add `cdss-eval/scenarios.jsonl`, minus the 30-set and minus anything whose normalised text is within edit distance of an exam query. Report the seed count.
3. **Augmentation.** A separate step, `tools/augment_seeds.py`: the teacher writes 5 paraphrases per seed, varying the wording, weight and vitals with the situation unchanged, from a fixed prompt. Output goes under `data/distill/seeds/` with its source and seed id, tagged `synthetic: true` in the metadata. Exam seeds are excluded first, so an exam scenario can't be paraphrased; there is a test for this.
4. **Same path.** Every paraphrase goes through the same replay and filters as a production row. Production rows keep `synthetic: false`. Counts are printed by source.
5. **Cost ceiling for this run: $60.** Show the `--plan` estimate and stop before spending.
6. Record the 41-of-79 finding above.

**Built:**
- **Junk rule:** `clinical_signals` reads the question, not the answer. The three signals are routed (the router's matched protocol at HIGH/MEDIUM, as the pipeline uses it), drug (`_drug_spans`: the contract bank plus `drug_lexicon.json`) and vital (`vitals.parse_vitals`). The drop list is `tools/distill/junk_exclusions.json`: 8 hashes, which match 46 log entries and 3 seeds.
- **Known miss of the rule:** "burn patient 40% TBSA, how much fluid" has none of the three signals, so it goes to review. A test pins this.
- **Edit distance:** normalised Levenshtein (distance divided by the longer length) of 0.50 or less against every exam query (the 30-set and `run_tests.sh`, current turn and history). Measured on the bank:
  - the exam questions' misspellings sit at 0.46–0.48 ("septik … txa", "anafalaxis …");
  - the nearest different situation is at 0.51 (a blast-lung vent question against a DKA vent question).
  - The 30-set text is read from cdss-eval and must match the pinned sha256, or the builder refuses.
- **Seeds with history are left out** (the single-patient rule). A seed that repeats a production query is left out.
- **Paraphrases** take their seed's scenario id (`seed:<id>`), so a seed and its paraphrases never straddle the split. They are checked against the exam again, and they are never substituted: a fallback, an error or a malformed reply is recorded in `errors.jsonl`.
- **Paraphrase prompt** (sha256 `26f28630…`): it doesn't add a weight or vitals the seed doesn't state.

**Plan (2026-09-30, deployed d0b44f4; no model called):**
- **Production:** 72 distinct single-turn questions. That is 79, minus the 8 junk, plus one logged today. 30 are model-reaching and 42 deterministic.
- **Seeds: 92.** Left out: 30 from the 30-set, 23 with history, 8 exact exam text, 5 near an exam query, 18 repeating a production query, 3 junk, 3 duplicates. 69 are model-reaching and 23 deterministic.
- **Paraphrases:** 92 × 5 = 460 projected. Each is assumed to reach the teacher, with the mean prompt.
- **Cost:**

| | Expected | Ceiling |
|---|---|---|
| Replay (99 calls + 460 projected) | $18.26 | $60.21 |
| Paraphrasing (92 calls) | $0.81 | $8.86 |
| **Total** | **$19.07** | **$69.07** |

  The ceiling is over the $60 approved, so the run stopped here. It counts 3,700 output tokens per call (700 max plus Opus's 3,000 reserve) and every paraphrase reaching the model.

**Staged (owner, 2026-09-30):** "Staged. Seeds are rows too, as you have it. Run the paraphrasing, re-plan with the real paraphrases, show me the second plan and stop."

**Paraphrasing (2026-09-30):**
- The first attempt made no teacher call. `augment_seeds.py` imported `providers` without loading the server's `.env`, so all 92 calls stopped on "ANTHROPIC_API_KEY is unset" before any request. Fixed: it loads the `.env` read-only and refuses before the first call if the key is missing.
- **Rerun: 92 of 92 seeds paraphrased, 0 errors, 460 paraphrases** (prompt `26f28630…`). Ceiling $8.86, expected $0.81.

**Second plan (deployed d0b44f4, real paraphrases; no model called):**
- **Paraphrases: 456.** The exam re-check left out 4, none of them an exam scenario (cautious drops):
  - a bare "~68 kg" near "25 kg";
  - a crushed-hand ketamine question near "need ketamine for a 6 yo arm fx";
  - two blast-lung vent questions near the DKA vent question (their seed sat at 0.51).
- **Reaching the teacher:** production 30, seeds 69, paraphrases 353 (**452 calls**). Answered by a card: 42, 23 and 103.
- **Replay cost: expected $14.46, ceiling $48.38.** With the paraphrasing (ceiling $8.86), this run's ceiling is **$57.24, under the $60 approved.** Stopped here for the owner.

**Run (owner, 2026-09-30: "Run the replay with --approve-cost 60"; deployed d0b44f4):** 452 teacher calls. Refuse-to-run passed.

| Source | Card (no model) | Held | Unasked drug | Review | Kept | Train / valid |
|---|---|---|---|---|---|---|
| production | 42 | 3 | 11 | 6 | 10 | 10 / 0 |
| seed | 23 | 2 | 22 | 24 | 21 | 18 / 3 |
| paraphrase | 103 | 18 | 122 | 137 | 76 | 70 / 6 |
| **total** | 168 | 23 | 155 | **167** | **107** | **98 / 9** (valid: 4 scenarios) |

- No fallback, truncation, pipeline change or check failure.
- **Unasked drugs** are the largest exclusion. The most frequent: dextrose 41, ketamine 31, tranexamic acid 21, sodium bicarbonate 15, morphine 14, calcium gluconate 14, epinephrine 12. The full count is in `manifest.json`.
- **Scenario types:** damage_control_resuscitation 15, burn_management_pfc 13, unrouted 12, radiology_imaging_trauma_patients 12, airway_management_in_prolonged_field_care 11, then 7 or fewer. Every type is under 20 rows.
- **Drugs named in the kept answers:** midazolam 6, tranexamic acid 6, ketamine 4, amiodarone 2, rocuronium 1.
- **Cost:** the builder doesn't record the providers' token counts. The plan's expected cost was $14.46 for the replay and $0.81 for the paraphrasing; the actual figure is on the provider dashboards.

**For the owner's ruling: the review file is mostly clinical.** `data/distill/review.jsonl` (untracked) holds 167 rows in about 51 groups (a seed with its paraphrases counts as one group):
- About 5 groups (~16 rows) are fragments: a bare weight, "90 kg male tenio", "normal weight for a 7 year old", "Do I give ami for this now?".
- The other ~46 groups (~151 rows) are real clinical questions with no route, no lexicon drug and no parsed vital. Examples: the Parkland formula, when to burp a chest seal, c-spine clearance, IO access, criteria for terminating resuscitation, rabies timing, a vent patient bucking the tube, breech delivery.
- The rule keeps junk out (none of the 107 kept rows is junk), but the router and the lexicon miss much of the prolonged-field-care and general reference material. "amio" is not in the lexicon.

**Owner rulings (#114 review, 2026-10-01):**
1. "Release the 46 clinical groups by hash now; the 5 fragment groups stay out. Then add a fourth junk signal, a committed clinical vocabulary list built from the router's protocol keywords and the corpus section headings (procedures, formulas, anatomy, obstetrics), so next run these pass on their own. Add 'amio' and other common abbreviations you saw to the drug lexicon as a finding for a separate PR."
2. "Unasked-drug filter stays strict for v1. Record the 155 and the top drugs. The relaxed variant (unasked drug named without a number passes) is the v2 experiment, in the work order under D6."
3. "Coverage accepted for v1. Rebuild train/valid with the released rows, same split rule, report final counts by source and scenario type, update the PR, stop."

**Applied:**
- **Groups.** Counted exactly, the review file held 50 groups, not about 51: 46 clinical and **4 fragments** (H-SESS-001 "150lbs", H-SESS-017 "90 kg male tenio", H-SESS-031 "normal weight for a 7 year old", H-SESS-045 "Do I give ami for this now?"). The "~5" in #114 was approximate; the 46 is exact.
  - The borderline group, H-SESS-032 "How do I pronounce my mother in law dead?", is among the 46: the teacher answered it as pronouncing a death. Flagged for the owner.
- **`tools/distill/review_rulings.json`** holds hashes only:
  - release: 151 rows (144 hashes);
  - hold: 16 rows (15 hashes).
  - A released row is kept without a signal. A held row stays in review even with one: two "tenio" paraphrases came back as "tension pneumo" (see below) and would pass the vocabulary.
- **Fourth signal, `vocabulary`.** `tools/distill/clinical_vocabulary.json` has 1,088 words, generated by `tools/distill/build_clinical_vocabulary.py`.
  - Router sources: `protocol_index.json` (titles, conditions, procedures, search terms, aliases, blood products), the router's curated supplements, and its slang table (`query_aliases.json`).
  - Corpus source: section headings of the 90 JTS PDFs. A heading word counts only if it is used lowercase in at least 3 CPGs' text (names are not) and is a dictionary word or at least 7 letters (PDF line-break fragments are not).
  - Acronyms of 3–5 capitals count when written in mixed-case text (RSI, TBI).
  - A generic stoplist keeps out words like "mother", "weight", "code", "release", "weather", "software" and "body". It is pinned by tests: the junk negatives and the 4 fragment seeds have no signal of any kind.
- **Next run:** 125 of the 151 released rows (40 of 46 groups) now pass on their own. Six groups still don't: PT/INR, litter-carry reassessment, "leg amp", "amio iv", angioedema, handoff. Not tuned to fit.
- **Rebuild** (`--rebuild`): no model call. Every row (train, valid and review) is checked again by the refuse-to-run check, with its patient context and signed doses rebuilt by the pipeline's own functions. Then the junk rule with the rulings, then the same split rule. It refuses if a row's snapshot is not the deployed commit. Refuse-to-run: passed.

**Final v1 dataset (rebuilt 2026-10-01 on d0b44f4): 258 rows, 239 train / 19 valid (7 scenarios); 16 held in review.**

| Source | Train | Valid | Review (held) |
|---|---|---|---|
| production | 14 | 2 | 0 |
| seed | 39 | 3 | 3 |
| paraphrase | 186 | 14 | 13 |
| **total** | **239** | **19** | **16** |

- **Scenario types, all sources:** unrouted 163, damage_control_resuscitation 15, burn_management_pfc 13, radiology_imaging_trauma_patients 12, airway_management_in_prolonged_field_care 11, pain_anxiety_delirium 7, airway_management_of_traumatic_injuries 6, acute_extremity_compartment_syndrome 4, documentation_prolonged_field_care 4, then 12 types with 3 or fewer.
- **Unrouted by source:** production 9, seed 23, paraphrase 131. Every type except unrouted is under 20 rows. **Coverage accepted for v1 (owner).**

**Unasked-drug filter: strict for v1 (owner).**
- It removed **155** rows in the D5b run: production 11, seed 22, paraphrase 122.
- The drugs most often named: dextrose 41, ketamine 31, tranexamic acid 21, sodium bicarbonate 15, morphine 14, calcium gluconate 14, epinephrine 12, amiodarone 10, acetaminophen 10, atropine 8, naloxone 8. The full count is in the run's `manifest.json`.
- The relaxed variant is the v2 experiment, recorded under D6.

**Findings (not fixed here):**
1. **Safety: abbreviated drug names escape the deterministic dose check.**
   - With nothing signed, the check holds "amiodarone 150 mg IV", "magnesium 2 g IV" and "norepinephrine 5 mcg/min", but **passes** "amio 150 mg IV", "mag 2 g IV", "bicarb 50 mEq IV" and "levo 5 mcg/min". The drug lexicon doesn't know the abbreviations, so the dose is never attributed to a drug.
   - It fails open. Only the LLM validator stands behind it.
   - The router's slang table already knows bicarb, levo, mag, dilt, vec, vaso and "rocky onium"; the check's lexicon doesn't. Also seen in the data: "amio", "versa" (Versed), "rock" (rocuronium), "ami" (ambiguous: amiodarone or acute MI, needs a ruling), "nebs", "abx", "morph".
   - **Proposed: its own PR, with a failing test first and replay; the owner places it.**
   - None of the 258 v1 rows states a dose under one of these abbreviations (scanned).
2. **A paraphrase changed the situation.** For the ambiguous seed "90 kg male tenio", the teacher wrote "90 kg male, tension pneumo — what do I do?", against the prompt's "same situation" instruction. The group is held, so it is not in v1. A seed too unclear to keep its situation should be paraphrased never, or reviewed first.

### D1b: the authored 30-set, drafted for sign-off (owner, 2026-09-28; after D5, its own PR)

The authored set (docs/EdgeCDSS_JTS_Evaluation_Set_30) can't be found, so D1(b)'s reconciliation has nothing to compare against. Instead:
- Draft `docs/EVALUATION_SET_30.md` from the runner's 30 scenarios (the frozen cdss-eval bank, `scenarios-30.jsonl`).
- Give each scenario a pre-written failure criterion.
- The owner reviews and signs it like a contract. Signing is the owner's act.

### D6: training toolchain (runs on the Mac in `~/edgecdss-train`, not on the Jetson) (done, #93)

Commit under `tools/distill/`:

**`requirements.txt`**, pinned from `pip freeze` of the working venv: mlx-lm, mlx, transformers, tokenizers and huggingface_hub < 2.0.

**A Makefile with these targets:**
- **`train ADAPTER=name`:** `mlx_lm.lora` on Qwen2.5-3B-Instruct-4bit. The defaults are 600 iters and lr 1e-4, and both can be overridden.
- **`fuse`:**
  1. `mlx_lm.fuse --dequantize` against the full-precision base;
  2. copy `tokenizer.json`, `tokenizer_config.json`, `vocab.json` and `merges.txt` from the base snapshot over the fused folder.
- **`gguf`:**
  1. llama.cpp `convert_hf_to_gguf.py` to f16;
  2. `llama-quantize` to Q4_K_M;
  3. delete the f16. Never ship f16.
- **`ship`:**
  1. refuse if the Jetson has under 3 GB free;
  2. scp the Q4 file;
  3. write the Modelfile and `ollama create`;
  4. run one single-line ketamine probe on the Jetson over ssh, with no multi-line quoted prompt.
- **`bench` (owner, 2026-09-26):**
  1. run `run_tests.sh` against the new tag; 27/27 must hold;
  2. run the 30-scenario local arm against the new tag and print the before/after table;
  3. write the results to a new dated file, `docs/DISTILL_BENCH_<tag>.md`, linked from this work order. Do not append to `LOCAL_LLM_BENCHMARK.md`, which stays a measurement record of the base model.

**Preflight (owner, 2026-09-26):** the Makefile checks the training data against `tools/distill/fixtures/format_example.jsonl`, the same fixture the Jetson-side D5 test uses.

**v2 experiment (owner, 2026-10-01, #114 review):** the relaxed unasked-drug filter. An answer that names a drug the question didn't ask about, and that has no signed entry for it, passes if it states **no number** for that drug. A stated dose still excludes the row. v1 trains on the strict filter (D5b, 155 rows removed). v2 rebuilds the dataset with the relaxed one and benches against v1 on the same exam.

**Rules:**
- Install only with `pip install -r requirements.txt`.
- The string `-U` must not appear anywhere in the Makefile or the README.

**The README lists the three gotchas:**
1. Never `-U` the foundation libraries in this venv.
2. Copy the tokenizer files after fuse.
3. Quantize on the Mac, and probe on the Jetson directly.

### E1: validator wording sensitivity (owner, 2026-09-29; after D4, its own PR)

The LLM validator holds correct answers because of how the question or the answer is worded. All three sightings fail safe (held, never released), so none was fixed at the time; they are looked at together here.

1. **Run 3, finding 6** (docs/MULTI_MODEL_BENCHMARK_2026-09-25.md): TXA is held for plain haemorrhage (H-S2, H-S1-a, G-MTN-01).
2. **#86:** "80kg male, we tubed him, what do I give after RSI" went to gpt-4o-mini, and the validator held it: "recommends post-intubation sedation with ketamine without confirming the tube is in place". It doesn't read "we tubed him" as the tube being in (owner, 2026-09-26: fails safe, not fixed then).
3. **#107** (the same pattern as #86, seen again in the live harness): "80kg male, cric'd, what do I give after RSI". The validator held gpt-4o-mini's post-intubation ketamine "without confirming tube placement".

Never loosen a gate: the replay must show 0 newly released.

**Also in E1 (owner, 2026-09-30):** log the model the validator's reply names, beside the generator's `model_returned` (D5a logs the generator's only).

## Distillation bench results

Each D6 `make bench` run writes `docs/DISTILL_BENCH_<tag>.md` and is linked here.

- [`docs/DISTILL_BENCH_edgecdss-d6check.md`](DISTILL_BENCH_edgecdss-d6check.md): dry-run data, toolchain proof only, not a model result.

## Findings placement (benchmark run 3, docs/MULTI_MODEL_BENCHMARK_2026-09-25.md)

| Finding | Placed in |
|---|---|
| 1. The hybrid fallback silently substituted qwen for slow cloud models | Live fix, #88 (done) |
| 2. A seizing patient was served a behavioural-emergency midazolam dose (H-S3) | **A1b** |
| 3. A previous patient's dose crossed an explicit reset (G-MTN-05) | **A0** |
| 4. The oral-intake hold fires on correct refusals (R2-DEPRESSED-GCS) | **A4** (#95) |
| 5. Uncited numbers served unheld: crystalloid volumes and rates (H-IM-06), cefazolin 20–30 mg/kg (G-ADV-03), levetiracetam concentrations (G-ADV-10) | **the free-text dose check** |
| 6. The validator holds TXA for plain haemorrhage (H-S2, H-S1-a, G-MTN-01) | **E1** |

Finding 5 has been placed but not yet given an item letter. Finding 6 is E1 (owner, 2026-09-29).

## Found along the way, not yet placed

- **A correct signed dose is held when the question names the indication, not the drug** (found in #97). In asystole with nothing named, epinephrine 1 mg (the signed arrest dose) is held, because the builder builds by drug name. Fixing it would release holds, so it needs an owner ruling (owner, #97 review: not now).
- A ketamine drip for pain gets the RSI bundle ("ketamine drip" is an RSI term).
- A unitless weight ("he is 150") silently skips the RSI card.
- **An eclamptic seizure is served lorazepam, with no magnesium** (found in #103). SMOG CY24 p.37: "In pregnant patients, Magnesium should be first line to abort non-epileptic seizures." "70kg, 34 weeks pregnant, eclamptic seizure, what do I give" goes to the model path (A9 keeps eclampsia off the seizure card), and the builder offers lorazepam 4 mg for active seizure. gpt-4o-mini served it. The bank has no signed magnesium entry. It's the same on main.
- **Uncited IV fluid rates are still served** (run-3 finding 5, confirmed in #108). A fluid isn't a drug the check recognises, so "if IV, infuse 250–500 mL/hr" (H-IM-06) isn't read. A11 reads rates for recognised drugs only. Closing it needs signed crystalloid entries, which is the owner's authoring job (owner, #108 review).
- gpt-4o hits the organisation's 30,000 TPM limit on a sequential 30-set.
- **The epinephrine card triggers only on "epi drip" / "epinephrine drip"** (found in #110). "80kg male, HR 38, symptomatic bradycardia, epinephrine infusion rate" goes to the model, which answers in mcg/min, and A11 holds it. The norepinephrine card (A16) reads any rate wording; the epinephrine card doesn't.
- **A drug-choice question gets one drug's card** (found in #110). "norepinephrine drip vs epinephrine drip, which for this patient" and "start levophed or epi, he is still hypotensive" get the norepinephrine card (the first previously got the epinephrine card).
- **The corpus was ingested from the superseded ID39** (found in #100). `server/data/jts_protocols` holds both `Airway_Management_of_Traumatic_Injuries_17_Jul_2017_ID39.pdf` and `Airway_Management_in_Trauma_28_Jan_2026_ID39.pdf`. All 28 ID39 chunks in the production ChromaDB come from the 2017 edition. Re-ingest is a separate decision.
- **The signed succinylcholine dose contract cites ID39 p.28 for contraindications the page doesn't list** (found in #100). The 2026 ID39 p.28 supports its 1.5 mg/kg dose, not "Burns", "Spinal cord injury" or "Hyperkalemia". ID40 p.3 does. Correcting it is a re-sign of that contract.

## Deferred (do not touch)

- neonatal dextrose;
- the fentanyl adult label rename;
- voice;
- the local-model portal toggle;
- the Go sentinel.
