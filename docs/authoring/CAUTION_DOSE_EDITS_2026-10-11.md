# Caution edits for signing: no other drug's dose in a caution (2026-10-11)

**Status (2026-10-11): edits 1, 2, 3, 4, 7 and 8 signed by Andrew Azelton (owner) as drafted, and applied.** Each of the 42 signed entries they touch was unsigned, edited and re-signed with `server/tools/set_contract.py` (`--by AI-AIM --date 2026-10-11`, the owner's name and the edit number in `--reason`); 68 entries are signed before and after, and only `cautions` and `review_date` changed. Edits 2 and 8 are in unsigned drafts: their text changed, the entries stay unsigned. **Edits 5 and 6 are not signed** (owner, 2026-10-11): they are signed in the same pull request as an atropine paediatric RSI pre-dose entry, drafted from JTS ID39 for the owner to sign first.

Every edit is to caution text only; no dose, route, population, contraindication or source changes.

Replay (main `e96e6ab` against the applied edits): served answers (1,738), gate (1,408), live session logs (2,218) and held answers (308) byte-identical; the full pipeline (800 stored queries, model stubbed) differs on 22, in served text only: every added line is a signed edit's new wording, and the route, verdict and built doses are unchanged on every row. **0 newly held, 0 newly released.** Suite: 2,666 passed, 54 skipped, 4 xfailed (the adult RSI card's pinned cautions updated to edits 4 and 7).

## The rule (owner, 2026-10-11)

**A caution never states another drug's dose.** It may name the drug. First stated as "cautions name the drug, never a dose, unless the drug has its own signed entry"; tightened the same day after naloxone was found to have signed entries of its own (IV and IM adult, 0.4–2 mg), so the exception would have kept the dose that caused the finding.

**Why:** a served caution goes into the ALLOWED_DOSES block the generator reads, and the generator copies it. Only the asked drug's doses are built for a question, so a copied dose of another drug is held by the free-text dose check, even where that drug has a signed entry. Found in A25: `edgecdss-v3`'s B1 answer copied fentanyl's caution as "Naloxone (0.4 mg IV or IM) available", and the answer was held for it ("no signed naloxone dose for this question").

**Tier:** a caution with no tier, or `serve`, is shown with the dose and is in the generator's block. A `detail` caution is kept for the record and for "why this dose?".

## The edits

Found by scanning every caution in the bank for a drug name followed by a dose (`openai_client._drug_spans` and the free-text check's dose patterns), then reading each hit.

### 1. Fentanyl, acute pain / analgesia — JTS PFC fixed dose, adult, IV (signed; serve)

- Current: "Naloxone (0.4 mg IV or IM) should be available when using opioid analgesics (Pain, Anxiety and Delirium ID29 p.7)."
- **Proposed:** "Naloxone should be available when using opioid analgesics (Pain, Anxiety and Delirium ID29 p.7)."
- Changes: the served fentanyl IV card and the block no longer state a naloxone dose. Naloxone's own signed entries are unchanged; asking for naloxone still gets 0.4 mg.

### 2. Fentanyl, analgesia infusion, adult, IV (unsigned draft, #148; serve)

- Current: "High-risk medication (ID29 p.24). Naloxone (0.4 mg IV or IM) should be available when using opioid analgesics (ID29 p.7)."
- **Proposed:** "High-risk medication (ID29 p.24). Naloxone should be available when using opioid analgesics (ID29 p.7)."
- Changes: nothing served today (the entry is unsigned). Applied with the others so the draft does not carry the dose into a later signature.

### 3. The cumulative-maximum note, in 39 signed entries (detail)

- Current: "The cited guideline states no cumulative maximum for this drug and indication. That is meaningful silence, not a gap in extraction: the same guideline DOES state cumulative maxima where it means to (ketamine 100 mg, hydromorphone 4 mg, Pain Management p.94)."
- **Proposed:** "The cited guideline states no cumulative maximum for this drug and indication. That is meaningful silence, not a gap in extraction: the same guideline DOES state cumulative maxima where it means to (for ketamine and for hydromorphone, Pain Management p.94)."
- Changes: record text only (detail tier: not served with the dose). Hydromorphone has no signed entry; ketamine's 100 mg is a cumulative maximum, not a dose.

| Drug | Indication | Population | Route |
|---|---|---|---|
| ketamine | post-intubation sedation — repeated bolus (no infusion pump) | adult|peds | IV |
| ketamine | agitated or violent patient — dissociative sedation | adult | IV |
| ketamine | agitated or violent patient — dissociative sedation | adult | IM |
| ketamine | agitated or violent patient — dissociative sedation | peds | IV |
| ketamine | agitated or violent patient — dissociative sedation | peds | IM |
| ketamine | refractory seizure (benzodiazepine-refractory) | adult | IV |
| ketamine | refractory seizure (benzodiazepine-refractory) | adult | IM |
| ketamine | refractory seizure (benzodiazepine-refractory) | peds | IV |
| ketamine | refractory seizure (benzodiazepine-refractory) | peds | IM |
| epinephrine | anaphylaxis | adult | IM |
| epinephrine | anaphylaxis | peds | IM |
| epinephrine | symptomatic bradycardia — infusion | adult | IV |
| epinephrine | symptomatic bradycardia — push dose | adult | IV |
| epinephrine | shock unresponsive to IV fluids — infusion | adult|peds | IV |
| epinephrine | shock — push dose | peds | IV |
| epinephrine | neonatal resuscitation — HR below 60 despite ventilation | peds | IV |
| epinephrine | croup with stridor at rest — nebulised | peds | NEB |
| epinephrine | bronchiolitis with severe respiratory distress — nebulised | peds | NEB |
| fentanyl | acute pain / analgesia | peds | IV |
| fentanyl | acute pain / analgesia | adult|peds | IN |
| norepinephrine | vasodilatory/haemorrhagic shock infusion | adult | IV |
| norepinephrine | vasodilatory shock infusion | peds | IV |
| norepinephrine | symptomatic bradycardia — infusion | adult | IV |
| norepinephrine | cardiogenic shock / pulmonary oedema with SBP under 100 | adult | IV |
| midazolam | active seizure | adult | IV |
| midazolam | active seizure | peds | IM |
| midazolam | agitated or violent patient / behavioural emergency | adult | IV |
| morphine | acute pain / analgesia | adult | IV |
| morphine | acute pain / analgesia | adult | IM |
| morphine | acute pain / analgesia | peds | IV |
| dextrose | symptomatic hypoglycaemia | adult | IV |
| dextrose | symptomatic hypoglycaemia | peds | IV |
| calcium gluconate | hyperkalaemia — membrane stabilisation | adult | IV |
| calcium gluconate | hyperkalaemia — membrane stabilisation | peds | IV |
| naloxone | opioid-induced respiratory depression | adult | IV |
| naloxone | opioid-induced respiratory depression | adult | IM |
| naloxone | opioid-induced respiratory depression | peds | IV |
| lorazepam | active seizure | adult|peds | IV |
| lorazepam | agitated or violent patient / behavioural emergency | adult | IV |

### 4. Ketamine, RSI induction, adult, IV (signed; untiered, so served)

- Current: "Ketamine is JTS ID39's FIRST-LINE induction agent; etomidate 0.3 mg/kg IV/IO is listed second line."
- **Proposed:** "Ketamine is JTS ID39's FIRST-LINE induction agent; etomidate is listed second line."
- Changes: the served RSI card no longer states an etomidate dose (no etomidate entry is signed).

### 5. Ketamine, RSI induction, peds, IV (signed; untiered, so served) — **clinical note below**

- Current: "JTS ID39 paediatric column: pre-dose atropine IV/IO 0.02 mg/kg (minimum 0.1 mg, maximum 0.5 mg) in all under 1 year, those under 5 receiving succinylcholine, and all who receive a 2nd dose of succinylcholine."
- **Proposed:** "JTS ID39 paediatric column: pre-dose atropine IV/IO in all under 1 year, those under 5 receiving succinylcholine, and all who receive a 2nd dose of succinylcholine. Ask for atropine by name for the dose."

### 6. Succinylcholine, RSI paralytic — under 5 years, peds, IV (signed; untiered, so served) — **clinical note below**

- Current: "Pre-dose atropine IV/IO 0.02 mg/kg (min 0.1 mg, max 0.5 mg)."
- **Proposed:** "Pre-dose atropine IV/IO. Ask for atropine by name for the dose."

**Clinical note on 5 and 6:** no signed atropine entry covers the RSI pre-dose. Atropine's signed entries are symptomatic bradycardia (adult 1 mg, peds 0.02 mg/kg), nerve agent and organophosphate poisoning. Today these two cautions are the only place the pre-dose figure, with its minimum and maximum, reaches the medic. After the edit, asking for atropine on a paediatric RSI question builds the entries it has, each labelled with its own indication. Checked on main e96e6ab, for a 15 kg child, "RSI with succinylcholine, atropine pre-dose": symptomatic bradycardia IV 0.3 mg (0.02 mg/kg) and organophosphate or carbamate poisoning IV 0.75 mg (0.05 mg/kg). Neither is the RSI pre-dose, and neither carries its minimum of 0.1 mg or maximum of 0.5 mg. **Options:** sign 5 and 6 as drafted; or first author and sign an atropine "RSI pre-dose" peds entry from ID39 (0.02 mg/kg, minimum 0.1 mg, maximum 0.5 mg), then sign 5 and 6; or leave 5 and 6 unsigned for now.

### 7. Rocuronium, RSI paralytic, adult, IV (signed; untiered, so served)

- Current: "JTS ID39 adult RSI pathway. Alternatives listed alongside: vecuronium 0.1 mg/kg IV/IO or succinylcholine 1.5 mg/kg IV/IO."
- **Proposed:** "JTS ID39 adult RSI pathway. Alternatives listed alongside: vecuronium or succinylcholine."
- Changes: no vecuronium dose (no entry signed) and no succinylcholine dose (its own signed entries are unchanged).

### 8. Propofol, induction of anaesthesia, adult, IV (unsigned draft; untiered)

- Current: "JTS ID39 does not list propofol as an RSI induction agent at all — ketamine first line, etomidate 0.3 mg/kg second."
- **Proposed:** "JTS ID39 does not list propofol as an RSI induction agent at all — ketamine first line, etomidate second."

## Signing

Sign, or rule otherwise, on each numbered edit (1–8). On signature the edits are applied to `server/drug_contracts.json`, each changed signed entry's `review_date` and `reviewed_by` are set to the signature, the worksheet is regenerated, and `server/tests/test_caution_no_other_dose.py` stops being an expected failure. The usual replay runs on the applied change: a caution edit changes what the generator reads, so newly held and newly released answers are both reported.
