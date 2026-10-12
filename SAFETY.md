# Safety

EdgeCDSS 5.0.0. This is what the system guarantees, what it does not, and how a change to it is made. The order of record is [`docs/WORK_ORDER.md`](docs/WORK_ORDER.md); each item's one-line meaning and status is in [`docs/REFERENCE.md`](docs/REFERENCE.md).

> ⚠️ **Research prototype.** Not validated for clinical use, not for patient care decisions. Simulated and synthetic scenarios only. Do not enter PHI, patient names, or identifying information into any project system.

## How an answer is built

A question first meets a deterministic layer: patient context (weight, age, vitals, access), the pre-gates and the cards. For the presentations below, a card written from signed content answers, and **no model is called**. Otherwise a model writes the answer from retrieved guideline passages and the doses built for this question, and the answer is served only after the deterministic checks and an LLM validator have read it.

## What the system guarantees

These are enforced in code and pinned by tests. A change that weakens one is not merged (see *How a change is made*).

**Doses**
- **A dose is served only from a signed contract entry.** 69 of 109 entries are signed by the program owner, each with verbatim source quotes and printed page numbers ([`docs/authoring/SIGNING.md`](docs/authoring/SIGNING.md)). An unsigned entry serves nothing; a drug with no signed entry for the question holds. An uncited value is never served.
- **Every dose the model writes is checked** against the signed value for this patient and indication, wherever it appears: the GIVE line (within 5%), free text, per-kg doses, infusion rates, a line that names no drug, abbreviations ("amio", "levo"), and the unit (a dose in another unit than the signed one holds, even when it converts equal). A history amount ("he took 240 mg") is not a dose. A negated dose is exempt only from the check it negates.
- **A millilitre is served only from a confirmed vial concentration.** Until then the dose is in mg.
- **Cautions never state another drug's dose**, so the model is not handed a number for a drug the question did not ask about.

**Cards** (deterministic; no model)
- Haemorrhage with shock physiology: the DCR card; junctional bleeding (groin, axilla, neck) gets its signed lines.
- Severe TBI.
- Tension pneumothorax (two signs, or one with chest trauma; "pneumo" counts): served from the signed needle-decompression procedure, verbatim JTS CPG ID74 (26 Dec 2018).
- Active seizure, in any recognised phrasing and the common misspellings, with the signed benzodiazepine dose once a weight is given.
- Hypothermic arrest: "cardiac arrest", or a patient's "no pulse" or "pulseless", with hypothermia.
- A completed airway never gets the RSI bundle; a completed surgical airway never gets the CICO card.
- A card served from a signed file holds while the file is unsigned.

**Holds for harmful advice that states no dose**
- Oral intake with depressed consciousness.
- A contraindicated procedure under its condition (signed rows: a nasal airway with mid-face trauma; succinylcholine with burns, spinal cord injury or hyperkalaemia).
- An answer to an actively bleeding patient with no step that controls the bleeding.

**The validator**
- An unreadable validator reply fails closed: the answer is held.
- Offline, the validator is its own setting (`CDSS_VALIDATOR_MODEL`, default `qwen2.5:3b`), never the generator's model by accident.

**Patient context**
- After a patient boundary ("new patient"), only the new patient is read, and the reset is shown.

## What it does not guarantee

Read these before relying on any served answer.

- **Advice a check does not read can be wrong.** The checks read doses, units, rates, a few procedures and the bleeding-control step. They do not read the order of steps, a missing step in most presentations, or a wrong procedure. In the 2026-10-10 bench, model-written answers that passed every check and were served included a low-and-loose tourniquet for an arterial bleed, no rewarming in a hypothermic arrest and no decompression for a tension pneumothorax (all called SAFE by the validator), and CPR for a seizing patient (served with the review banner) ([`docs/DISTILL_BENCH_edgecdss-v3-d7.md`](docs/DISTILL_BENCH_edgecdss-v3-d7.md)). The cards added since close those four presentations, not the class.
- **The offline validator is a 3B model and misses procedural errors.** It called several of those answers SAFE. Online, the validator is `gpt-4o-mini`.
- **"Needs human review" serves.** An answer the validator flags for review is served with a banner, not held.
- **A card fires only on the phrasings it recognises.** Misspellings beyond the listed ones, and presentations described without the words a trigger reads, reach the model. An active arterial bleed without shock physiology gets no card (v1.1).
- **Signed content is as good as its source and its signature.** Signing records who said a number is safe and on what page; it is not an independent clinical validation. 40 contract entries and two procedure rows (P1, P2) are unsigned and hold.
- **The guideline corpus is a snapshot.** The editions are the ones in the knowledge base when it was built; a newer guideline is not used until it is ingested and its citations rechecked.
- **Benchmark counts are advisory.** A model is adopted only when the owner has read every answer it served and found none clinically wrong. No distilled model has passed; `qwen2.5:3b` is the offline model.

The open items are in the v1.1 section of the work order.

## How a change is made

The global rules of [`docs/WORK_ORDER.md`](docs/WORK_ORDER.md) apply to every change:
- One bug per pull request. The failing test is committed first, on its own, then the fix.
- Never loosen a gate. After every safety change the stored answers are replayed (served answers, held answers, live session logs, the full pipeline): **newly released must be 0**, every newly held answer is read and classified, and every movement is listed for the owner's sign-off.
- Signing is the owner's act. A changed signed line fails its test until it is re-signed; an unsigned state is not merged.
- Every pull request reports the files touched, the suite count, and the live-harness result against a second server, never against the live service. The live service and its `.env` are never touched.
- The owner reviews every item before the next starts. Nothing is merged without the owner.

## Offline operation

The offline model is `qwen2.5:3b`, under the Qwen RESEARCH LICENSE AGREEMENT (non-commercial use only; see the README). Every local call asks for an 8192-token context and refuses to truncate. The deterministic layer, every check and every hold work the same offline; the validator is the on-device model.

## Reporting a problem

- **A clinically wrong answer:** use the portal's feedback (it records the session and the full answer), or open a GitHub Issue with the query, the response received and what the correct response should be. Do not include patient information.
- **A security vulnerability:** open a private Issue (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

Every reported failure is reproduced from the logs and fixed with a test built from it.
