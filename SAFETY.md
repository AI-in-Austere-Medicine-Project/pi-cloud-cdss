# Safety

EdgeCDSS 5.1.0. This is what the system guarantees, what it does not, and how a change to it is made. The order of record is [`docs/WORK_ORDER.md`](docs/WORK_ORDER.md); each item's one-line meaning and status is in [`docs/REFERENCE.md`](docs/REFERENCE.md).

> ⚠️ **Research prototype.** Not validated for clinical use, not for patient care decisions. Simulated and synthetic scenarios only. Do not enter PHI, patient names, or identifying information into any project system.

## How an answer is built

A question first meets a deterministic layer: patient context (weight, age, vitals, access), the pre-gates and the cards. For the presentations below, a card written from signed content answers, and **no model is called**. Otherwise a model writes the answer from retrieved guideline passages and the doses built for this question, and the answer is served only after the deterministic checks and an LLM validator have read it.

## What the system guarantees

These are enforced in code and pinned by tests. A change that weakens one is not merged (see *How a change is made*).

**Doses**
- **A dose is served only from a signed contract entry.**
  - 108 of 118 entries are signed by the program owner, across signing batches 1–3 (2026-10-14 to 2026-10-21; E05 re-signed 2026-10-22).
  - Each has verbatim source quotes and printed page numbers ([`docs/authoring/SIGNING.md`](docs/authoring/SIGNING.md)).
  - 36 retired entries are kept on record and never serve; 26 of them were retired by the owner on 2026-10-21 because no JTS or SMOG page states their number.
  - An unsigned entry serves nothing, and a drug with no signed entry for the question holds. An uncited value is never served.
- **There is no calculator.** Every drug number a deterministic card prints comes from a signed entry or that entry's own caution: dose, rate, volume, concentration or preparation recipe. With no signed entry, the card holds (A35). The legacy calculators are removed, so a bank that fails to load serves nothing rather than falling back.
- **Doses are offered and checked for this question:**
  - **Stated indication:** when the question states one, the check accepts only that indication's signed entries; another indication's dose of the same drug holds, naming both (A32).
  - **Stated route:** only the stated route's doses are offered (IV and IO are one route; IV access reads as IV, no access as IM). A drug with nothing signed on that route is offered nothing, and a dose written for it holds (A34).
- **Every dose the model writes is checked** against the signed value for this patient, wherever it appears:
  - the GIVE line (within 5%), free text and per-kg doses;
  - infusion rates, which are matched to their own indication (A30);
  - abbreviations ("amio", "levo");
  - the unit: a dose in another unit than the signed one holds, even when it converts equal;
  - a line that names no drug: its dose, rate or recipe is read as the question's one named drug and checked as that drug's, and with no drug to attribute it holds (A18, A33).
  - A history amount ("he took 240 mg") is not a dose. A negated dose is exempt only from the check it negates.
- **A requested dose above the highest signed dose for this patient holds** before any model is called. The highest signed dose is read for the patient's population, route and weight, from the signed entries (A36).
- **A millilitre is served only from a confirmed vial concentration.** Until then the dose is in mg.
- **Cautions never state another drug's dose**, so the model is not handed a number for a drug the question did not ask about.

**Cards** (deterministic; no model)
- Haemorrhage with shock physiology: the DCR card; junctional bleeding (groin, axilla, neck) gets its signed lines.
- Severe TBI.
- Tension pneumothorax (two signs, or one with chest trauma; "pneumo" counts): served from the signed needle-decompression procedure, verbatim JTS CPG ID74 (26 Dec 2018). Every number on the card is in the quote it cites; re-signed 2026-10-22 (A37).
- Active seizure, in any recognised phrasing and the common misspellings, with the signed benzodiazepine dose once a weight is given. The dose is chosen for the available route: a child with no IV gets the signed IM midazolam (A38).
- Push-dose epinephrine: the signed entry for the stated indication, with that entry's own preparation. A patient in shock gets the signed shock entry (E05, JTS ID83 p.24), never the bradycardia dose.
- Midazolam for pacing or cardioversion: the signed pacing entry (2.5–5 mg), not the ID61 1 mg add-on. "Cardioversion" is never read as RSI.
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
- **Signed content is as good as its source and its signature.** Signing records who said a number is safe and on what page; it is not an independent clinical validation.
- **Some content is unsigned and holds:**
  - 10 contract entries: ketorolac ×5, excluded; artemether-lumefantrine, ruled SIGN but tablets cannot be signed; and four infusions, deferred or v1.1.
  - Two procedure rows, P1 and P2.
- **The five vent cards are signed by a role, not a name** ("clinician", 2026-08-22). Their settings are printed for the owner's ruling in [`docs/authoring/VENT_CARD_SETTINGS_2026-10-22.md`](docs/authoring/VENT_CARD_SETTINGS_2026-10-22.md).
- **Some numbers that are not drug doses are in code, not in a signature:** targets, thresholds, times and limits. They are listed below.
- **The guideline corpus is a snapshot.** The editions are the ones in the knowledge base when it was built; a newer guideline is not used until it is ingested and its citations rechecked.
- **Benchmark counts are advisory.** A model is adopted only when the owner has read every answer it served and found none clinically wrong. No distilled model has passed; `qwen2.5:3b` is the offline model.
- **The portal can offer a model the owner did not adopt.** The picker lists the on-device models Ollama has, including `edgecdss-v3` (owner ruling, 2026-10-12): a medic who selects it gets that model's answer, validated on the device by `qwen2.5:3b`, under every deterministic check. The default model is unchanged.

The open items are in the v1.1 section of the work order.

## Numbers in code that no signature covers

The A35 sweep (2026-10-22) listed every number a deterministic card can print. The drug numbers trace to signed entries. The numbers below are not drug doses; they are written in code, most with a guideline citation beside them, and **no signature covers them**. They are the owner's to rule on ([`docs/authoring/A35_CARD_NUMBERS_2026-10-22.md`](docs/authoring/A35_CARD_NUMBERS_2026-10-22.md), section 3).

| Where | Number | Cited in code |
|---|---|---|
| Severe TBI card | "with GCS 8 or less" (airway) | JTS ID63 p.6 |
| | "Keep SBP above 110 mmHg; SpO2 above 93%" | ID30 p.7, ID63 p.20 |
| | child: SMOG's lower limit, "70 + 2 x age in years for 1-10 years; 90 mmHg over 10" | SMOG CY24 pp.49–50 |
| | "Ventilate to EtCO2 35-45 mmHg" | ID30 p.7 |
| | "Head of bed 30-45°" | ID30 pp.10–11 |
| | "EtCO2 35 mmHg for no more than 20 minutes" (impending herniation only) | ID63 p.7 |
| Ketamine analgesia card | "Reassess pain, airway, respirations q5min" | none |
| Haemorrhagic-shock (DCR) card | TLDR "TXA within 3 hours of injury" | The signed TXA caution beside it cites ID18 p.9; the card's SOURCE line does not. |
| Pain-severity question | NRS 1–3 / 4–6 / 7–10 | Owner note (#164); no clinical citation |
| Vitals cautions, on every non-gated card (`vitals_rules.json`, no signoff field) | SBP < 90, MAP < 65, RR < 10, SpO2 < 90, HR < 50 (AV-nodal blockers), temperature < 35 °C (TXA), GCS ≤ 8 (nothing by mouth), glucose < 70; plausibility ranges | none |
| Volumes | a volume below 0.05 mL or above 60 mL is not served; the brief's undiluted floor is 0.2 mL | none ("physical facts") |
| Vent cards | tidal volume on the Devine ideal body weight (50 / 45.5 kg + 2.3 kg per inch over 60 in) | none |
| Vent cards | every setting (VT 6 mL/kg, RR, PEEP, FiO2, SpO2, plateau, EtCO2), signed by the role "clinician" | the card's references |

## How a change is made

The global rules of [`docs/WORK_ORDER.md`](docs/WORK_ORDER.md) apply to every change:
- One bug per pull request. The failing test is committed first, on its own, then the fix.
- Never loosen a gate. After every safety change the stored answers are replayed (served answers, held answers, live session logs, the full pipeline): **newly released must be 0**, every newly held answer is read and classified, and every movement is listed for the owner's sign-off.
- Signing is the owner's act. A changed signed line fails its test until it is re-signed; an unsigned state is not merged.
- Every pull request reports the files touched, the suite count, and the live-harness result against a second server, never against the live service. The live service and its `.env` are never touched.
- The owner reviews every item before the next starts. Nothing is merged without the owner.

## Offline operation

The offline model is `qwen2.5:3b`, under the Qwen RESEARCH LICENSE AGREEMENT (non-commercial use only; see the README). Every local call asks for an 8192-token context and refuses to truncate. The deterministic layer, every check and every hold work the same offline; the validator is the on-device model (`CDSS_VALIDATOR_MODEL`, default `qwen2.5:3b`).

**The portal is local-only in local mode:** the picker offers only the on-device models Ollama has, no cloud provider is contacted, voice is off, and the portal path makes no outbound call. The startup log line names the mode; check it after any change to `.env`.

**An `edgecdss-v3` pick is slow on an 8 GB Jetson:** with `qwen2.5:3b` validating, both models stay loaded, v3 runs partly on the CPU, and an answer took 113–174 s (16 s for `qwen2.5:3b`).

## Reporting a problem

- **A clinically wrong answer:** use the portal's feedback (it records the session and the full answer), or open a GitHub Issue with the query, the response received and what the correct response should be. Do not include patient information.
- **A security vulnerability:** open a private Issue (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

Every reported failure is reproduced from the logs and fixed with a test built from it.
