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

Items are listed in the owner's execution order (2026-09-26, below), done items first. They are done in this order unless the owner reorders them.

| # | Item | Status |
|---|---|---|
| — | Live fix: explicitly selected model waited for 60 s; fallback bannered | **done**: #88, merged and deployed |
| A1 | DCR routing failure | **done**: #82, merged and deployed |
| A2 | Deterministic severe-TBI card | **done**: #84, merged and deployed |
| A0 | Context isolation on patient reset | **done**: #90, merged and deployed |
| A1b | Dose check matches indication, not only value | **done**: #91, merged and deployed |
| A3 | Already-intubated patients receiving the RSI bundle | approved 2026-09-26 after the review fix; owner merging #86 |
| A4 | Depressed-GCS oral route | **next**, after A3 |
| A5 | Hold text for fixed doses | after A4 |
| A6 | Contraindicated procedures (design only) | after A5 |
| A7 | GCS parser | after A6 |
| A8 | "status post" must not match status epilepticus | after A7 |
| A9 | Active-seizure phrasings reach the signed entry | after A8 |
| A10 | CICO card must not fire on a completed surgical airway | after A9 |
| D5a | Full-answer logging | after A10 |
| D1 | Evaluation hygiene | after D5a |
| D5 | Distillation dataset builder | after D1 |
| D6 | Training toolchain (Mac) | after D5 |
| B1 | Source-mode labelling | after D6 |
| B2 | Generator section headers | after B1 |
| C1 | Feedback instrument | after B2 |
| D2 | Prompt layout for prefix caching | after C1 |
| D3 | Retrieval trim to 4 chunks | after D2 |
| D4 | Show the deterministic part first | after D3 |

Owner asks outside the lettered items:

| Item | Status |
|---|---|
| 3% NaCl contract, signed at 7.5 g | in review: #85 |
| Multi-model benchmark run 3 | **done**: #87, merged |
| This work order | **done**: #89, merged |

**Merge order (owner, 2026-09-25):** #87 now; #85 and #86 after the owner reads them.

**Execution order (owner, 2026-09-26, sixth statement; replaces the earlier five):** A3 (#86) → A4 → A5 → A6 → A7 → A8 → A9 → A10 → D5a → D1 → D5 → D6 → B1 → B2 → C1 → D2 → D3 → D4. A0 and A1b are done (#90, #91; main at 894ffd9, deployed and restarted on it).

Every open A item finishes before any D item starts. Safety before speed, no exceptions. Same rules; stop for review on each.

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

### A3: already-intubated patients receiving the RSI bundle (in review, #86)

This was the subject of 4 field reports (feedback review §1). A completed-airway detector ("already intubated", "tube is in", "we RSI'd", "on the vent", "being ventilated") suppresses should_use_rsi_pregate regardless of other content, and the is_vent_settings_query vocabulary is widened.

Tests: the real queries from the review route away from RSI, and a genuine pre-intubation RSI request still routes to it.

### A7: GCS parser (added 2026-09-25; a separate PR, after A6 per the 2026-09-26 order)

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

### A8: "status post" must not match status epilepticus (owner, 2026-09-26; found in #91)

The dose builder's seizure trigger is the substring `'status'`. "159lb male unable to ventilate effectively status post oral trauma" (H-SESS-002, also in the live logs) is offered lorazepam 4 mg for active seizure: a non-seizure patient offered a seizure dose.

This is the same class as "stab" in "stable" and "14G" read as grams: a lexical match firing on a substring.

Failing tests first. Negatives: "status post", "post-status" and "status: stable" must not reach the seizure entry.

### A9: active-seizure phrasings reach the signed entry (owner, 2026-09-26; found in #91)

"80kg male actively seizing" never reaches the dose builder. The fixed ACTIVE SEIZURE card answers "benzodiazepine per local protocol" with no signed dose, even with a weight and a signed entry.

- "actively seizing", "seizing now", "still seizing" and "in status" must reach the active-seizure entry the same as "active seizure" does.
- Add the phrases to the lexicon, with a failing test per phrase first.
- Report any other seizure phrasing in the stored queries that gets no signed dose today.

### A10: the CICO card must not fire on a completed surgical airway (owner, 2026-09-26; found in #86)

The CICO check is a substring match with no state (`"cric" in q`, `openai_client.py:4580`). Live on the #86 branch, "80kg male, cric'd, what do I give after RSI" was served "Declare CICO … Perform surgical airway / cricothyrotomy now" for a patient whose cric was already in.

Same class as A8: a substring match with no state. One bug per PR, so it is not in #86.

Failing tests first: "cric'd", "cric is in" and "surgical airway in place" must not get the CICO card. A genuine CICO request ("Help me do a cric", "failed intubation, failed i-gel, sats are 71") still must.

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

**Placement (owner, 2026-09-26):** after A7 and before D5. D1 is measurement only. Run on deployed main after every A item is done, it gives the clean pre-training baseline that the D6 bench compares against. Same snapshot rule as run 3.

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

### D5: distillation dataset builder

Script: `tools/build_distill_dataset.py`.

**Waits for (owner, 2026-09-26):** A0 and A1b merged and deployed (met: 894ffd9), and D1 done. The dataset is built from replay against the main that contains both. The refuse-to-run check below is A1b's indication matcher: D5 imports it and does not reimplement it.

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

**Resolved (2026-09-26):** production session logs kept only the first 200 characters of each answer (`response_preview`, `openai_client.py:256`), so they could not supply training answers. The owner chose (a) and (c) above.

### D6: training toolchain (runs on the Mac in `~/edgecdss-train`, not on the Jetson)

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

**Rules:**
- Install only with `pip install -r requirements.txt`.
- The string `-U` must not appear anywhere in the Makefile or the README.

**The README lists the three gotchas:**
1. Never `-U` the foundation libraries in this venv.
2. Copy the tokenizer files after fuse.
3. Quantize on the Mac, and probe on the Jetson directly.

## Distillation bench results

Each D6 `make bench` run writes `docs/DISTILL_BENCH_<tag>.md` and is linked here.

- None yet.

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

- **The validator holds a correct post-tube sedation answer** (found in #86, live on the branch). "80kg male, we tubed him, what do I give after RSI" went to gpt-4o-mini, and the validator held it: "recommends post-intubation sedation with ketamine without confirming the tube is in place". It doesn't read "we tubed him" as the tube being in. It fails safe, so it isn't fixed now (owner, 2026-09-26). Revisit when the validator wording is looked at as a whole, together with run-3 finding 6 (TXA held for plain haemorrhage).
- A ketamine drip for pain gets the RSI bundle ("ketamine drip" is an RSI term).
- A unitless weight ("he is 150") silently skips the RSI card.
- gpt-4o hits the organisation's 30,000 TPM limit on a sequential 30-set.

## Deferred (do not touch)

- neonatal dextrose;
- the fentanyl adult label rename;
- voice;
- the local-model portal toggle;
- the Go sentinel.
