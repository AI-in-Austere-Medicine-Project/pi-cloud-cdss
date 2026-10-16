# Signing batch 2, sedation and antibiotics: draft entries for review (2026-10-16)

The owner asked for (2026-10-16): midazolam sedation, rocuronium redose, ketamine sedation infusion, cefazolin and ceftriaxone. Each entry gives a proposed dose, route, maximum and repeat, with a verbatim quote and the printed page for every figure. Entries are flagged where the sources disagree, or where no JTS/SMOG page states a number. **Nothing here is signed.** Every entry below has `signoff: false` and is invisible to the serving path. Signing is the owner's act, by [`SIGNING.md`](SIGNING.md).

**How the quotes were checked.** `server/tests/test_contracts_batch2_drafts.py` reads each cited PDF page (set `JTS_PDF_DIR`) and checks every quote against it. SMOG is read one column at a time. A quote leaves text out only where it shows `…`. Every page is the printed page. In every document cited here, the printed page and the PDF page are the same; each cited page's footer was checked.

**What was drafted.** These are the eight slots the bank already held open for these drugs, plus five more:
- **Two splits by population.** The sources dose children differently for ketamine's sedation infusion and rocuronium's redose, so each `adult|peds` entry became an adult and a paediatric entry.
- **Three second sides of dose conflicts.** As in batch 1, both sides are kept as entries so neither is dropped silently.

Other well-sourced indications the research found are listed under "Candidates, not drafted" for the owner to place.

## Summary

| # | Drug · indication · population · route | Proposed dose | Max | Repeat | Lead source | Flag |
|---|---|---|---|---|---|---|
| 1 | midazolam · procedural sedation · adult · IV | 1–4 mg (ketamine adjunct) | none stated | every 30–60 min if the procedure runs past 10–15 min | JTS ID61 p.9 | SOURCE_CONFLICT with 2 |
| 2 | midazolam · procedural sedation — SMOG (pacing / cardioversion) · adult · IV | 2.5–5 mg | none stated | every 15–30 min PRN | SMOG p.140 | SOURCE_CONFLICT with 1 |
| 3 | midazolam · sedation infusion, ventilated · adult · IV | 0.05 mg/kg bolus, then 0.05–0.1 mg/kg/hr | none stated | titration step and mix: **not in any source** | SMOG p.140, p.12 | SOURCE_CONFLICT with 4; NEEDS_MANUAL_ENTRY |
| 4 | midazolam · sedation infusion, ventilated — ICU order set (fixed rate) · adult · IV | 1–6 mg/hr | ID12 order set: up to 10 mg/hr | start rate: **not in any source** | JTS ID29 p.25 | SOURCE_CONFLICT with 3; NEEDS_MANUAL_ENTRY |
| 5 | rocuronium · redose interval · adult · IV | 1 mg/kg (range 0.6–1.2; or 8–12 mcg/kg/min) | none stated | every 30–45 min PRN | SMOG p.155 only | SINGLE_SOURCE_UNREFERENCED: SMOG calls it "unlabeled and unreferenced"; **no JTS number** |
| 6 | rocuronium · redose interval · peds · IV | 1 mg/kg (range 0.6–1.2) | none stated | every 30–45 min | SMOG p.155 only | as 5; no paediatric infusion |
| 7 | ketamine · prolonged sedation infusion · adult · IV | start 1.5 mg/kg/h (the highlighted row); band 0.5–2.0 mg/kg/h; step 0.25 | none stated | load 1 mg/kg first | JTS ID61 p.9 | NEEDS_VISUAL_CONFIRMATION; SOURCE_CONFLICT with 8 |
| 8 | ketamine · prolonged sedation infusion — SMOG (en route) · adult · IV | 1–3 mg/kg/hr after a 0.5–2 mg/kg bolus; step 0.25 | none stated | — | SMOG p.127 | SOURCE_CONFLICT with 7 |
| 9 | ketamine · prolonged sedation infusion · peds · IV | 0.5–1 mg/kg/hr; step 0.25 | none stated | start rate and mix: **not in any source** | SMOG p.127 only | STARTING_RATE_NOT_IN_SOURCE; **no JTS number** |
| 10 | cefazolin · open fracture / wound prophylaxis · adult · IV | 2 g | 12 g/day | every 6–8 h; 24 h, open fracture: then with each I&D | JTS ID24 p.11 | WEIGHT_BAND_OPTION_IN_SOURCE (1 / 2 / 3 g by weight) |
| 11 | cefazolin · open fracture / wound prophylaxis · peds · IV | 20–30 mg/kg | 100 mg/kg/day (a caution; see question 7) | every 6–8 h | JTS ID24 p.12 | no per-dose gram cap in any source |
| 12 | ceftriaxone · severe bacterial infection / sepsis · adult · IV | 2 g | none stated | every 24 h | JTS ID91 p.40, ID83 p.8 | ADMINISTRATION_TIME_DIFFERS (10 vs 30 min vs slow push) |
| 13 | ceftriaxone · severe bacterial infection / sepsis · peds · IV | **NEEDS_MANUAL_ENTRY** | — | — | none | DOSE_NOT_IN_SOURCE: **no JTS/SMOG page states a dose** |

## Owner questions

1. **Midazolam procedural sedation (entries 1 and 2): conflict group `midazolam-procedural-sedation-adult`.**
   - JTS ID61 p.9 gives 1–4 mg IV/IO as an adjunct to a ketamine bolus. It is the only page that labels a dose "Procedural Sedation".
   - SMOG p.140 gives 2.5–5 mg every 15–30 min, under "Transcutaneous Pacing / Cardioversion, Anxiety, Agitation". SMOG's own pp.41 and 46 say 2–5 mg.
   - JTS ID91 p.35 gives 0.5–1 mg IV for sedation and anxiolysis; it is recorded, not drafted.

   Sign one entry for adults. Or sign entry 2 under a cardioversion/pacing label of its own, since its heading is different.
2. **Midazolam ventilated infusion (entries 3 and 4): conflict group `midazolam-ventilated-infusion-adult`.**
   - SMOG gives 0.05–0.1 mg/kg/hr, which is 4–8 mg/hr at 80 kg.
   - The JTS ICU order set (ID29) gives a fixed 1–6 mg/hr.
   - The burn order set (ID12) titrates up to 10 mg/hr.

   No source gives a titration step, a mix or (for entry 4) a starting rate, so both entries stay unsignable until those are entered. ID61 p.5 says that in prolonged field care the drip should be ketamine, with midazolam given as pushes. This entry may belong to en-route or ICU care only.
3. **Rocuronium redose (entries 5 and 6).** SMOG p.155 is the only source, and it prints the dose as "(unlabeled and unreferenced dose)". No JTS page gives a maintenance figure: not ID39 (2026), ID40, ID80, ID91 or ID92. The bank's old note was right about JTS and wrong about SMOG. Is a dose its own source calls unreferenced signable?
4. **Ketamine sedation infusion (entries 7 and 8): conflict group `ketamine-sedation-infusion-rate`, plus the visual start.**
   - **The highlighted start row.** I rendered ID61 p.9: the only shaded row is 1.5 mg/kg/h (25 µg/kg/min; 20/30/40/50 mL/h at 40/60/80/100 kg). ID61's dial-flow rule ("weight in kg divided by 2", at 3 mg/mL) gives the same 1.5 mg/kg/h at every weight. The old note said the rule did not reconcile, and gave the band as 0.5–1.25; both were wrong. The table runs 0.5–2.0 mg/kg/h. **Please look at the page** (`replay-out/batch2/img/id61_p9crop-09.png` in the worktree, or the PDF) before the NEEDS_VISUAL_CONFIRMATION flag is cleared.
   - **The conflict.**
     - ID61's own Appendix D (p.11) gives 1 mg/kg/h non-intubated and 1–2 intubated.
     - SMOG p.127 gives 1–3 mg/kg/hr (entry 8).
     - ID30 p.24 gives 20–100 µg/kg/min (Role 3 neuro-ICU); it is recorded, not drafted.
   - **The mix.** ID61 uses 3 mg/mL and SMOG 1 mg/mL, so mL/h figures differ between the two.
   - **Neither table's arithmetic is clean.** ID61's drip-count tables have several wrong cells, and SMOG's chart has three. Only mg/kg/h is drafted.
5. **Paediatric ketamine infusion (entry 9).** SMOG is the only source (0.5–1 mg/kg/hr), and it states no starting rate or mix. ID61's adult start (1.5) is above SMOG's paediatric ceiling, which is why the entry was split. SMOG prints "Avoid sub-dissociative doses to prevent emergence phenomenon" in the same column; it is served as a caution.
6. **Cefazolin weight bands (entry 10).** ID24 footnote † and SMOG p.103 allow 1 g under 80 kg, 2 g at 81–160 kg and 3 g over 160 kg. ID24's own table, and SMOG's chart, give a flat 2 g. The bands leave 80–81 kg undefined. This is an option within one CPG, not two sources disagreeing, so it is flagged but not a conflict group. The flat 2 g is drafted; should the bands serve instead?
7. **A per-kg daily maximum (entry 11).** Cefazolin's paediatric "maximum, 100 mg/kg/day" is a serve caution. `max_cumulative` holds a mass, and the engine does not compute a per-kg daily cap. Is the caution enough, or should the schema carry per-kg cumulative caps?
8. **Ceftriaxone (entries 12 and 13).**
   - **The dose agrees.** It is 2 g every 24 h. ID83 gives the infusion time as 10 minutes (Better) and 30 minutes (Best), and SMOG says slow push or in 100 cc NS.
   - **The label.** No source says "severe bacterial infection"; they all say sepsis. Relabel?
   - **The paediatric gap.** No JTS or SMOG page states a paediatric sepsis dose, so entry 13 stays incomplete. The only paediatric figure in the corpus is ID24's CNS-injury dose (100 mg/kg/day divided q12–24h, no cap). It is not carried across.
9. **Forms.** No JTS or SMOG page gives a cefazolin vial strength; the bank's form stays NEEDS_MANUAL_ENTRY. With no concentration declared, a signed cefazolin entry would serve a mass dose with no volume, as acetaminophen IV does today.

## Candidates, not drafted (owner to place)

From the research pass. These figures are not yet quote-checked by the test; each would be when drafted.

| Drug · indication · population · route | Dose in source | Source (printed page) | Note |
|---|---|---|---|
| cefazolin · penetrating brain injury · adult · IV | 2 g every 6–8 h; 5 days or until the CSF leak is closed, whichever is longer | JTS ID24 p.11; SMOG p.64; ID30 p.7; ID63 p.8 (every 8 h, 5 days) | the interval and duration differ between ID63 and ID24 |
| cefazolin · penetrating spinal cord injury · adult · IV | 2 g every 6–8 h; no duration printed | JTS ID24 p.12; SMOG p.64; ID15 p.14 (24–72 h, and a 5-day minimum) | duration conflict inside ID15 |
| cefazolin · penetrating chest, maxillofacial · adult · IV | 2 g every 6–8 h; 24 h | JTS ID24 p.11; SMOG p.64 | |
| cefazolin · single pre-surgical dose (Role 1/2 without surgery) · adult · IV | 2 g once | JTS ID24 p.9 | |
| cefazolin · ventriculostomy · adult · IV | 1 g three times daily | JTS ID30 p.13 | a Role 3 neurosurgical indication |
| ceftriaxone · penetrating TBI · adult · IV/IO | 2 g every 24 h; 5 days (ID63) or 5 days / until the CSF leak closes (ID24) | JTS ID63 p.8, p.20; ID24 p.11 | the alternate agent in ID24, "Best" in ID63 |
| ceftriaxone · penetrating TBI · peds · IV | 100 mg/kg/day divided every 12–24 h | JTS ID24 p.12 | no cap printed |
| ceftriaxone · severe pneumonia (COVID-19 co-infection) · adult · IV | 2 g every 24 h | COVID-19 austere CPG p.17 | narrow indication |
| midazolam · procedural sedation · peds · IV | 0.05–0.1 mg/kg every 15–30 min PRN | SMOG p.140, p.47, p.50 | SMOG only; the three pages agree |
| midazolam · procedural sedation · peds · IN | 0.2–0.5 mg/kg; maximum 10 mg total, 5 mg per nostril | SMOG p.140 | SMOG labels the route "unlabeled"; whether the procedural heading covers this line is unclear |
| midazolam · post-intubation bolus · adult · IV | 1–4 mg (ID61 p.12) vs 0.05 mg/kg (SMOG p.12) vs 2–5 mg (ID12 p.24) | as listed | a conflict |
| midazolam · sedation / anxiolysis · adult · IM | 2–4 mg | JTS ID91 p.35 | ID61 p.12: "IM: not recommended" (a conflict) |

## Contradictions found with signed entries (not redrafted; for the owner's awareness)

From the research pass, not quote-checked by the test.

- **midazolam, ongoing sedation (PFC), adult IV, signed at 0.5–2 mg.** ID61 p.12 gives "Nonintubated: 0.5–2mg • Intubated: 1–4mg". The signed range is the non-intubated line.
- **midazolam, active seizure, adult IV, signed at 0.1 mg/kg (max 4 mg; NASEMSO p.102).** Other sources give fixed doses:
  - SMOG p.140: 5 mg IV/IO;
  - SMOG p.37: 5 mg IV/IO/IN or 10 mg IM;
  - JTS ID63 p.9: 5 mg every 5 min;
  - JTS ID30 p.10: 5–10 mg IV.
- **midazolam, behavioural emergency, adult IV, signed at 5 mg (NASEMSO p.60).** SMOG p.32 gives 2.5–5 mg IV/IM every 15–30 min.
- **vancomycin (not in this batch).** The ceftriaxone "Best" sepsis regimen pairs it with vancomycin at 1.5 mg/kg in ID91 p.40, but at 15 mg/kg in ID83 p.8. One of them is likely a printing error.
- **midazolam contraindication vs TBI use.** SMOG p.140 lists "Neurologic Depression (Head Trauma) (unless having active seizure)" as a contraindication. JTS ID63 p.7 recommends midazolam 1–2 mg for anxiety in TBI. The contraindication is on entries 1–4 as SMOG prints it.

## Searched, nothing usable

- **NASEMSO v3.0:**
  - no cefazolin and no ceftriaxone (confirmed);
  - no rocuronium at all;
  - no midazolam dose for procedural, cardioversion or post-intubation sedation, or by infusion;
  - no ketamine infusion dose.
- **Rocuronium, JTS:**
  - ID39 (2026 and 2017), ID40, ID80, ID07 and ID92 give the intubating dose only, or name the drug;
  - ID91 and ID97 give no rocuronium figure;
  - the COVID-19 austere CPG's maintenance dosing is for vecuronium and is not carried across.
- **Ketamine infusion:**
  - ID80, ID39, ID91, ID92, ID57 and the COVID-19 CPG name the drip or defer to ID61;
  - ID29's infusion figures are for low-dose analgesia, a different indication.
- **Ceftriaxone:**
  - SMOG has no ceftriaxone monograph;
  - ID45 (VAP) and ID101 (CBRN) name it without a dose.
- **Cefazolin:**
  - ID07, ID46, ID45, ID56 and ID22 name it, or "1st generation cephalosporin", without a dose;
  - the burn CPGs (ID57, ID12) name it for cellulitis without a dose.
- **Excluded:** the military working dog (canine) documents, including SMOG p.57.

## The drafts

## midazolam

### 1. procedural sedation · adult · IV

- **Dose:** 1–4 mg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** An adjunct to a ketamine procedural-sedation bolus: start low, give more (JTS ID61 p.9). · If the procedure lasts longer than 10-15 minutes, repeat every 30-60 minutes (JTS ID61 p.9). · Have personnel and equipment for standard respiratory resuscitation ready (JTS ID61 p.12). · Respiratory depression, especially when given with any narcotic (JTS ID91 p.35). · No analgesic properties (SMOG p.140).
- **Contraindications:** Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines (SMOG CY24 p.140) · Acute narrow angle glaucoma (SMOG CY24 p.140) · Acute alcohol intoxication (SMOG CY24 p.140) · Respiratory insufficiency/depression, except during mechanical ventilation (SMOG CY24 p.140) · Shock (SMOG CY24 p.140: should not be used in shock) · Neurologic depression (head trauma), unless having an active seizure (SMOG CY24 p.140)
- **Flags:** SOURCE_CONFLICT · conflict group `midazolam-procedural-sedation-adult`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2). The dose is JTS ID61 p.9, the only page that labels a midazolam dose 'Procedural Sedation': 1-4 mg IV/IO, added to a ketamine bolus, repeated every 30-60 minutes for a long procedure. CONFLICT: SMOG CY24 p.140 gives 2.5-5 mg every 15-30 minutes under 'Transcutaneous Pacing / Cardioversion, Anxiety, Agitation'; SMOG p.41 and p.46 give 2-5 mg for sedation before pacing or cardioversion (SMOG disagrees with itself on the lower bound); JTS ID91 p.35 gives 0.5-1 mg IV for sedation and anxiolysis. NASEMSO gives no procedural-sedation dose (confirmed). No source states a maximum. ID61 p.12 also says 'IM: not recommended', so no IM entry is drafted.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix B: Procedural Sedation, p.9 | dose 1-4 mg IV/IO as a ketamine adjunct; repeat every 30-60 minutes | “Procedural Sedation … Step 2: Consider adding (start low, give more): … 1–4mg midazolam IV/IO … Step 3: May need to repeat doses as below if procedure lasts longer than 10–15 minutes. … Midazolam every 30–60 minutes” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Midazolam (Versed), p.12 | resuscitation caution | “Personnel and equipment needed for standard respiratory resuscitation should be available during midazolam administration.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Dose and Administration (ADULT column), p.140 | conflicting: 2.5-5 mg every 15-30 minutes (pacing / cardioversion, anxiety, agitation) | “Transcutaneous Pacing / Cardioversion, Anxiety, Agitation. IV • 2.5-5mg q 15-30 min PRN” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Bradycardia with Pulse, p.41 | conflicting: 2-5 mg for sedation before pacing | “Consider sedation: Midazolam 2-5mg IV / IO” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Tachycardia w/ Pulse, p.46 | conflicting: 2-5 mg for sedation before cardioversion | “Consider Sedation: Midazolam 2-5mg IV / IO” |
| JTS Clinical Practice Guideline — Prolonged Casualty Care Guidelines, CPG ID91, 21 Dec 2021 — Table 10. PCC Role-based Guideline for Pain Management (Analgesia and Sedation), p.35 | conflicting: 0.5-1 mg IV for sedation and anxiolysis; respiratory caution | “For sedation and anxiolysis; … will also cause anterograde … amnesia … 0.5-1mg IV (push slowly over … Respiratory depression ESPECIALLY … when used with any narcotic” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Contraindications, p.140 | contraindications | “Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines … Acute narrow angle glaucoma, Acute Alcohol Intoxication … Respiratory Insufficiency/Depression (except during mechanical ventilation) … Should not be used in shock … Neurologic Depression (Head Trauma) (unless having active seizure)” |

### 2. procedural sedation — SMOG (pacing / cardioversion) · adult · IV

- **Dose:** 2.5–5 mg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Repeat every 15-30 minutes as needed (SMOG p.140). · Do not give without a stable IV line and BVM ready (SMOG p.140). · No analgesic properties (SMOG p.140).
- **Contraindications:** Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines (SMOG CY24 p.140) · Acute narrow angle glaucoma (SMOG CY24 p.140) · Acute alcohol intoxication (SMOG CY24 p.140) · Respiratory insufficiency/depression, except during mechanical ventilation (SMOG CY24 p.140) · Shock (SMOG CY24 p.140: should not be used in shock) · Neurologic depression (head trauma), unless having an active seizure (SMOG CY24 p.140)
- **Flags:** SOURCE_CONFLICT · conflict group `midazolam-procedural-sedation-adult`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2): the other side of the adult procedural-sedation conflict, kept so neither is dropped silently. SMOG CY24 p.140: 2.5-5 mg IV every 15-30 minutes PRN, under 'Transcutaneous Pacing / Cardioversion, Anxiety, Agitation'; SMOG's own algorithm pages (p.41, p.46) print 2-5 mg. CONFLICT with JTS ID61 p.9 (1-4 mg IV/IO as a ketamine adjunct, every 30-60 minutes). The owner rules which serves.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Dose and Administration (ADULT column), p.140 | dose 2.5-5 mg every 15-30 minutes (pacing / cardioversion, anxiety, agitation) | “Transcutaneous Pacing / Cardioversion, Anxiety, Agitation. IV • 2.5-5mg q 15-30 min PRN” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Bradycardia with Pulse, p.41 | corroborates in part: 2-5 mg before pacing (lower bound differs) | “Consider sedation: Midazolam 2-5mg IV / IO” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Tachycardia w/ Pulse, p.46 | corroborates in part: 2-5 mg before cardioversion (lower bound differs) | “Consider Sedation: Midazolam 2-5mg IV / IO” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Adverse Reactions / Precautions, p.140 | cautions | “May Cause Respiratory depression: Do not give without stable IV line and BVM (airway control) ready … No Analgesic properties” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Contraindications, p.140 | contraindications | “Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines … Acute narrow angle glaucoma, Acute Alcohol Intoxication … Respiratory Insufficiency/Depression (except during mechanical ventilation) … Should not be used in shock … Neurologic Depression (Head Trauma) (unless having active seizure)” |

### 3. sedation infusion for the ventilated patient · adult · IV

- **Dose:** 0.05–0.1 mg/kg/hr
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Give a 0.05 mg/kg IV bolus first, then start the infusion (SMOG p.140; SMOG RSI maintenance p.12). · NEEDS_MANUAL_ENTRY: titration step and mix. No source states either; SMOG says only titrate, ID29 titrates to RASS -1 to 0. · A continuous infusion often prolongs the effect (fat storage, active metabolites): use intermittent sedation whenever feasible (JTS ID29 p.11). · Avoid in renal or liver dysfunction (JTS ID29 p.25). · In prolonged field care, use a ketamine drip with midazolam pushes if needed; multiple drips are not recommended (JTS ID61 p.5). · No analgesic properties: intubated trauma patients need narcotic pain control (SMOG p.140).
- **Contraindications:** Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines (SMOG CY24 p.140) · Acute narrow angle glaucoma (SMOG CY24 p.140) · Acute alcohol intoxication (SMOG CY24 p.140) · Respiratory insufficiency/depression, except during mechanical ventilation (SMOG CY24 p.140) · Shock (SMOG CY24 p.140: should not be used in shock) · Neurologic depression (head trauma), unless having an active seizure (SMOG CY24 p.140)
- **Flags:** SOURCE_CONFLICT · conflict group `midazolam-ventilated-infusion-adult`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2). The dose is SMOG CY24 p.140 (repeated on the RSI page, p.12): 0.05 mg/kg IV bolus, then 0.05-0.1 mg/kg/hr. CONFLICT on the form and the ceiling: JTS ID29 p.25 (ICU order set) gives a fixed 1-6 mg/hr, and the Burn Care order set (ID12 p.24) titrates up to 10 mg/hr; at 80 kg SMOG's range is 4-8 mg/hr. SMOG's weight-based figure is drafted because it is the only one stated as a dose rather than an order-set range; the owner rules. No source states a titration step or a mix (NEEDS_MANUAL_ENTRY caution). The Burn Care PDF (file ID12) prints 'ID:20' in its page header; the bank cites ID12, as for the fentanyl infusion.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Dose and Administration (ADULT column), p.140 | dose: 0.05 mg/kg bolus, then 0.05-0.1 mg/kg/hr | “Infusion sedation 0.05 mg/kg bolus IV, then titrate 0.05-0.1mg/kg/hr. IV gtt” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rapid Sequence Intubation, Medications — Maintenance, p.12 | corroborates: same bolus and range | “Midazolam 0.05 mg/kg IVP or 0.05 mg/kg bolus then 0.05-0.1mg/kg/hr.” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Appendix H: Sedation Orders — Continuous Infusion, p.25 | conflicting: fixed 1-6 mg/hr; renal/liver caution; RASS target | “midazolam (aka VERSED) IV infusion (avoid in renal/liver dysfunction) mg/hr (1-6 mg/hr), Intravenous, CONTINUOUS. … Titrate sedation to RASS score of -1 to 0” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Sedation Holiday & Intermittent Medication Dosing, p.11 | caution: prolonged effect; prefer intermittent | “administration as a continuous infusion will often result in a prolonged duration of action and effect due to fat storage an accumulation of active metabolites. It is recommended that intermitted sedation be used whenever feasible.” |
| JTS Clinical Practice Guideline — Burn Care, CPG ID12, 10 Jun 2025 — Appendix A: Physician's Order Set — Analgesia/Sedation/PRN Medications, p.24 | conflicting: titrate up to 10 mg/hr | “Versed gtt at _____ mg/hr, titrate up to 10 mg/hr” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Medications, p.5 | caution: a ketamine drip in prolonged field care | “If a continuous drip is selected, use only a ketamine drip in most situations, augmented by push doses of opioid and/or midazolam if needed.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Adverse Reactions / Precautions, p.140 | caution: no analgesia | “No Analgesic properties” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Contraindications, p.140 | contraindications | “Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines … Acute narrow angle glaucoma, Acute Alcohol Intoxication … Respiratory Insufficiency/Depression (except during mechanical ventilation) … Should not be used in shock … Neurologic Depression (Head Trauma) (unless having active seizure)” |

### 4. sedation infusion for the ventilated patient — ICU order set (fixed rate) · adult · IV

- **Dose:** 1–6 mg/hr
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Titrate sedation to RASS -1 to 0 (JTS ID29 p.25). · Avoid in renal or liver dysfunction (JTS ID29 p.25). · Stop intermittent dosing once the infusion starts (JTS ID29 p.25). · The Burn Care order set titrates up to 10 mg/hr (JTS ID12 p.24). · NEEDS_MANUAL_ENTRY: starting rate. Both order sets leave it blank.
- **Contraindications:** Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines (SMOG CY24 p.140) · Acute narrow angle glaucoma (SMOG CY24 p.140) · Acute alcohol intoxication (SMOG CY24 p.140) · Respiratory insufficiency/depression, except during mechanical ventilation (SMOG CY24 p.140) · Shock (SMOG CY24 p.140: should not be used in shock) · Neurologic depression (head trauma), unless having an active seizure (SMOG CY24 p.140)
- **Flags:** SOURCE_CONFLICT · conflict group `midazolam-ventilated-infusion-adult`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2): the other side of the ventilated-infusion conflict. JTS ID29 p.25 (ICU sedation order set): 1-6 mg/hr, start blank; the Burn Care order set (ID12 p.24) titrates up to 10 mg/hr, start blank. CONFLICT with SMOG CY24 p.140 (0.05 mg/kg bolus, then 0.05-0.1 mg/kg/hr, weight-based). No source states a starting rate for this side (NEEDS_MANUAL_ENTRY caution).

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Appendix H: Sedation Orders — Continuous Infusion, p.25 | dose 1-6 mg/hr; RASS target; renal/liver caution | “midazolam (aka VERSED) IV infusion (avoid in renal/liver dysfunction) mg/hr (1-6 mg/hr), Intravenous, CONTINUOUS. Stop intermittent dosing if continuous infusion initiated and notify Pharmacy. Titrate sedation to RASS score of -1 to 0” |
| JTS Clinical Practice Guideline — Burn Care, CPG ID12, 10 Jun 2025 — Appendix A: Physician's Order Set — Analgesia/Sedation/PRN Medications, p.24 | ceiling 10 mg/hr; start rate blank | “Versed gtt at _____ mg/hr, titrate up to 10 mg/hr” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Midazolam, Contraindications, p.140 | contraindications | “Hypersensitivity to midazolam or any component of the formulation or other benzodiazepines … Acute narrow angle glaucoma, Acute Alcohol Intoxication … Respiratory Insufficiency/Depression (except during mechanical ventilation) … Should not be used in shock … Neurologic Depression (Head Trauma) (unless having active seizure)” |

## rocuronium

### 5. redose interval · adult · IV

- **Dose:** 1 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Repeat every 30-45 minutes as needed (SMOG p.155). · SMOG prints a range of 0.6-1.2 mg/kg, and an infusion of 8-12 mcg/kg/min as the alternative (SMOG p.155). · SMOG labels this maintenance dose 'unlabeled and unreferenced' (SMOG p.155). · Provides no analgesia or sedation: give sedation and analgesia before paralysis and throughout maintenance (SMOG p.155; JTS ID92 p.6; ID91 p.37). · Neuromuscular blockade is recommended only for those trained and practiced in its use (JTS ID39 p.12). · Resistance may occur in burns over 30% of the body, for 5-70 days after injury (SMOG p.155).
- **Contraindications:** Hypersensitivity (e.g., anaphylaxis) to rocuronium, other neuromuscular-blocking agents, or any component of the formulation (SMOG CY24 p.155)
- **Flags:** SINGLE_SOURCE_UNREFERENCED
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2). The old note ('neither JTS ID39 nor ID40 states a redose interval') holds for every JTS document, the 2026 ID39 included, but SMOG CY24 p.155 prints a maintenance dose: adult 1 mg/kg IV/IO every 30-45 minutes PRN, or 8-12 mcg/kg/min, range 0.6-1.2 mg/kg. It is the only source, and SMOG itself labels it '(unlabeled and unreferenced dose)'. No JTS page gives a maintenance figure; the COVID-19 austere CPG's maintenance dosing is for vecuronium and is not carried across. Split from the adult|peds entry: the paediatric column differs (no infusion, no PRN). No maximum stated.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Dose and Administration (ADULT column), p.155 | dose 1 mg/kg; every 30-45 minutes PRN; range; infusion | “Maintenance dosing: (unlabeled and unreferenced dose) IV Push: • 1 mg/kg IV/IO q30-45min PRN or 8-12 mcg/kg/min IV/IO (Dosing ranges from 0.6-1.2 mg/kg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Adverse Reactions / Precautions, p.155 | caution: no sedation or analgesia | “Provides NO analgesia or sedation! … Must provide appropriate sedation and analgesia prior to paralytic use and throughout maintenance.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Contraindications, p.155 | contraindication | “Hypersensitivity (e.g., anaphylaxis) to rocuronium, other neuromuscular-blocking agents, or any component of the formulation” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Adverse Reactions / Precautions, p.155 | caution: burn resistance | “Resistance may occur in burn patients (>30% of body) for period of 5-70 days after injury” |
| JTS Clinical Practice Guideline — Airway Management in Trauma, CPG ID39, 28 Jan 2026 — Neuromuscular blockade, p.12 | caution: trained users only | “Neuromuscular blockade (succinylcholine, rocuronium, vecuronium, etc.) is only recommended for use by those trained and practiced in its use.” |
| JTS Clinical Practice Guideline — Mechanical Ventilation Basics, CPG ID92, 09 Apr 2025 — WARNING, p.6 | caution: never paralyse without sedation | “Never paralyze a patient who has not received sedation” |
| JTS Clinical Practice Guideline — Prolonged Casualty Care Guidelines, CPG ID91, 21 Dec 2021 — Special Considerations, Patient Monitoring During Sedation, p.37 | caution: never paralyse without sedation | “Under no circumstances should paralytics be used without analgesia/sedation” |

### 6. redose interval · peds · IV

- **Dose:** 1 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Repeat every 30-45 minutes (SMOG p.155). · SMOG prints a range of 0.6-1.2 mg/kg and no paediatric infusion (SMOG p.155). · SMOG labels this maintenance dose 'unlabeled and unreferenced' (SMOG p.155). · Always reference the Broselow tape (SMOG p.155). · Provides no analgesia or sedation: give sedation and analgesia before paralysis and throughout maintenance (SMOG p.155; JTS ID92 p.6; ID91 p.37). · Neuromuscular blockade is recommended only for those trained and practiced in its use (JTS ID39 p.12). · Resistance may occur in burns over 30% of the body, for 5-70 days after injury (SMOG p.155).
- **Contraindications:** Hypersensitivity (e.g., anaphylaxis) to rocuronium, other neuromuscular-blocking agents, or any component of the formulation (SMOG CY24 p.155)
- **Flags:** SINGLE_SOURCE_UNREFERENCED
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2), split from the adult|peds entry. SMOG CY24 p.155 PEDIATRIC column: maintenance bolus 1 mg/kg every 30-45 minutes, range 0.6-1.2 mg/kg; no infusion and no PRN (the adult column's infusion is not carried across). SMOG labels it '(unlabeled and unreferenced dose)'. No JTS page gives a paediatric maintenance figure (ID39 2026 p.28 gives the intubating dose only). No maximum stated.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Dose and Administration (PEDIATRIC column), p.155 | dose 1 mg/kg; every 30-45 minutes; range | “Maintenance bolus dosing: (unlabeled and unreferenced dose) IV Push: • 1 mg/kg every 30-45 minutes (Dosing ranges from 0.6 - 1.2 mg/kg.)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Dose and Administration header, p.155 | caution: Broselow tape | “PEDIATRIC Always Reference BROSELOW Tape” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Adverse Reactions / Precautions, p.155 | caution: no sedation or analgesia | “Provides NO analgesia or sedation! … Must provide appropriate sedation and analgesia prior to paralytic use and throughout maintenance.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Contraindications, p.155 | contraindication | “Hypersensitivity (e.g., anaphylaxis) to rocuronium, other neuromuscular-blocking agents, or any component of the formulation” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Rocuronium, Adverse Reactions / Precautions, p.155 | caution: burn resistance | “Resistance may occur in burn patients (>30% of body) for period of 5-70 days after injury” |
| JTS Clinical Practice Guideline — Airway Management in Trauma, CPG ID39, 28 Jan 2026 — Neuromuscular blockade, p.12 | caution: trained users only | “Neuromuscular blockade (succinylcholine, rocuronium, vecuronium, etc.) is only recommended for use by those trained and practiced in its use.” |
| JTS Clinical Practice Guideline — Mechanical Ventilation Basics, CPG ID92, 09 Apr 2025 — WARNING, p.6 | caution: never paralyse without sedation | “Never paralyze a patient who has not received sedation” |
| JTS Clinical Practice Guideline — Prolonged Casualty Care Guidelines, CPG ID91, 21 Dec 2021 — Special Considerations, Patient Monitoring During Sedation, p.37 | caution: never paralyse without sedation | “Under no circumstances should paralytics be used without analgesia/sedation” |

## ketamine

### 7. prolonged sedation infusion · adult · IV

- **Dose:** 0.5–2 mg/kg/hr
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Give the 1 mg/kg IV/IO loading dose over 60 seconds first (JTS ID61 p.9). · Start at 1.5 mg/kg/h (25 mcg/kg/min): the row JTS ID61 Appendix B highlights (p.9). With a dial-flow adaptor and ID61's mix (750 mg in 250 mL normal saline, 3 mg/mL), that is the casualty’s weight in kg divided by 2, in mL/h. The highlight is visual only (NEEDS_VISUAL_CONFIRMATION). · Adjust by 0.25 mg/kg/h, one table row, at a time (JTS ID61 p.9; SMOG p.127). · A continuous drip may take an hour to take full effect or wear off; increase or decrease it gradually (JTS ID61 p.8). · Respiratory depression at higher doses (over 1 mg/kg), especially with fast IV/IO administration (JTS ID61 p.11). · Use with caution in cardiovascular disease; monitor cardiac function continuously (SMOG p.127). · The mL/h figures hold only for ID61's 3 mg/mL mix; SMOG's chart uses 1 mg/mL (SMOG p.128).
- **Contraindications:** Hypersensitivity to ketamine or any component of the formulation (SMOG CY24 p.127) · Conditions that cannot tolerate sustained increases in blood pressure: non-traumatic intracerebral hemorrhage, hypertension associated with acute coronary syndrome; NOT contraindicated in TBI (SMOG CY24 p.127)
- **Flags:** NEEDS_VISUAL_CONFIRMATION · SOURCE_CONFLICT · conflict group `ketamine-sedation-infusion-rate`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Redrafted 2026-10-16 (signing batch 2); was adult|peds with no dose. JTS ID61 p.9: the start is marked by shading a row; rendered, the shaded row is 1.5 mg/kg/h (25 mcg/kg/min), shaded in all three tables. ID61's dial-flow rule (weight / 2 mL/h at 3 mg/mL) gives 3 x (W/2) / W = 1.5 mg/kg/h at every weight, and the printed 1.5 row reads 20/30/40/50 mL/h at 40/60/80/100 kg, so the rule and the highlight agree (the old note said they did not reconcile, and gave the band as 0.5-1.25; the table runs 0.5-2.0 mg/kg/h). The dose range drafted is the table's printed band; no source states a maximum. CONFLICT on the rate: ID61's own Appendix D (p.11) gives 1 mg/kg/h non-intubated and 1-2 mg/kg/h intubated; SMOG p.127 gives 1-3 mg/kg/hr; ID30 p.24 (Role 3 neuro-ICU) 20-100 mcg/kg/min. CONFLICT on the mix: ID61 3 mg/mL, SMOG 1 mg/mL. ID61's drip-count tables have several arithmetic errors (100 kg at 0.5 mg/kg/h printed 1/9, calculated about 1/14); only mg/kg/h is drafted. Split from adult|peds: SMOG's paediatric range tops out at 1 mg/kg/hr, below the adult start.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix B: Ketamine Drip Dosing Tables, p.9 | loading dose; mix 3 mg/mL; dial-flow start (weight / 2 mL/h); step 0.25 mg/kg/h | “Sedation loading dose first (1mg/kg IV/IO over 60 seconds). MIX: 750mg (1.5 vials of 500mg/5mL) in 250mL of normal saline (3mg/mL solution). … initial drip rate in mL/h equals the casualty’s weight in kg divided by 2 (see mL/h table). … Drip adjustments: Increase or decrease drip by 0.25mg/kg/h (1 row).” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix B: Ketamine Drip Dosing Tables — mL/h table, p.9 | start 1.5 mg/kg/h (the row is highlighted in the rendered page, not in the text); table band 0.5-2.0 mg/kg/h | “starting dose highlighted … 0.5 8 7* 10 13 17 … 1.5 25 20 30 40 50 … 2.0 33 27 40 53 67” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix A, footnote 4, p.8 | caution: onset and offset take an hour | “A continuous ketamine drip may take an hour to take full effect or wear off. Always start with a loading dose and augment with an effective dose of opioid and/or midazolam if additional sedation is needed. Increase or decrease drip gradually.” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Ketamine (Ketalar), p.11 | conflicting: 1 mg/kg/h non-intubated, 1-2 mg/kg/h intubated; respiratory caution | “Nonintubated: 1mg/kg/h … Intubated 1–2mg/kg/h … Respiratory depression at higher doses (>1mg/kg), especially with fast administration IV/IO” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (ADULT column), p.127 | conflicting: 1-3 mg/kg/hr; step 0.25 mg/kg/hr | “IV Continuous Infusion • 0.5-2mg/kg bolus then 1-3 mg/kg/hr. Titrate levels by 0.25mg/kg/hr.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine (Ketalar) infusion chart, p.128 | conflicting: mix 1 mg/mL | “MIX 500 mg/500 mL CONCENTRATION 1 mg/mL” |
| JTS Clinical Practice Guideline — TBI Management and Basic Neurosurgery in the Deployed Environment, CPG ID30, 15 Sep 2023 — Sedation, p.24 | conflicting (Role 3 neuro-ICU): 20-100 mcg/kg/min | “Ketamine infusion dosage ranges are from 20mcg/kg/min up to 100mcg/kg/min” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Contraindications / Precautions, p.127 | contraindications; cardiovascular caution | “Hypersensitivity to ketamine or any component of the formulation … Conditions that cannot tolerate sustained increases in blood pressure (non-traumatic intracerebral hemorrhage, hypertension associated with acute coronary syndrome; NOT contraindicated in TBI) … Children <3 mo. age … Use with caution in patients with cardiovascular disease. Continuously monitor cardiac function” |

### 8. prolonged sedation infusion — SMOG (en route) · adult · IV

- **Dose:** 1–3 mg/kg/hr
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Bolus 0.5-2 mg/kg, then the infusion; adjust by 0.25 mg/kg/hr to appropriate sedation (SMOG p.127). · SMOG's chart mixes 500 mg in 500 mL (1 mg/mL); its mL/h figures hold only for that mix (SMOG p.128). · Use with caution in cardiovascular disease; monitor cardiac function continuously (SMOG p.127).
- **Contraindications:** Hypersensitivity to ketamine or any component of the formulation (SMOG CY24 p.127) · Conditions that cannot tolerate sustained increases in blood pressure: non-traumatic intracerebral hemorrhage, hypertension associated with acute coronary syndrome; NOT contraindicated in TBI (SMOG CY24 p.127)
- **Flags:** SOURCE_CONFLICT · conflict group `ketamine-sedation-infusion-rate`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2): the other side of the sedation-infusion rate conflict. SMOG CY24 p.127 adult: 0.5-2 mg/kg bolus, then 1-3 mg/kg/hr, titrated by 0.25; its chart (p.128) mixes 1 mg/mL. CONFLICT with JTS ID61 Appendix B (start 1.5 mg/kg/h, table 0.5-2.0 mg/kg/h, 3 mg/mL). Also recorded, not drafted: ID61's own Appendix D (1 mg/kg/h non-intubated, 1-2 intubated) and ID30 p.24 (Role 3 neuro-ICU, 20-100 mcg/kg/min). SMOG's chart has three arithmetic errors and runs 15-60 mcg/kg/min against its own 17-50 header; only mg/kg/hr is drafted.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (ADULT column), p.127 | dose 1-3 mg/kg/hr after a 0.5-2 mg/kg bolus; step 0.25 mg/kg/hr | “IV Continuous Infusion • 0.5-2mg/kg bolus then 1-3 mg/kg/hr. Titrate levels by 0.25mg/kg/hr.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine (Ketalar) infusion chart, p.128 | mix 1 mg/mL | “MIX 500 mg/500 mL CONCENTRATION 1 mg/mL” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Contraindications / Precautions, p.127 | contraindications; cardiovascular caution | “Hypersensitivity to ketamine or any component of the formulation … Conditions that cannot tolerate sustained increases in blood pressure (non-traumatic intracerebral hemorrhage, hypertension associated with acute coronary syndrome; NOT contraindicated in TBI) … Children <3 mo. age … Use with caution in patients with cardiovascular disease. Continuously monitor cardiac function” |

### 9. prolonged sedation infusion · peds · IV

- **Dose:** 0.5–1 mg/kg/hr
- **Max single:** none stated
- **Max cumulative:** none stated
- **Age floor:** 3 months
- **Repeat, administration and cautions served:** NEEDS_MANUAL_ENTRY: starting rate and mix. SMOG gives the paediatric range only; ID61's adult start (1.5 mg/kg/h) is above it. · Adjust by 0.25 mg/kg/hr (SMOG p.127). · Always reference the Broselow tape (SMOG p.127). · SMOG's paediatric note: avoid sub-dissociative doses to prevent emergence phenomenon (SMOG p.127).
- **Contraindications:** Hypersensitivity to ketamine or any component of the formulation (SMOG CY24 p.127) · Age < 3 months (SMOG CY24 p.127)
- **Flags:** STARTING_RATE_NOT_IN_SOURCE
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2), split from the adult|peds entry. SMOG CY24 p.127 PEDIATRIC column is the only source with a paediatric infusion figure: 0.5-1 mg/kg/hr, titrated by 0.25. No source states a paediatric starting rate or mix (NEEDS_MANUAL_ENTRY caution); ID61's tables start at 40 kg and its highlighted start (1.5 mg/kg/h) is above SMOG's paediatric ceiling. The SMOG note 'Avoid sub-dissociative doses' sits in the same column; recorded verbatim. Age floor 3 months as on the signed paediatric ketamine entries.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (PEDIATRIC column), p.127 | range 0.5-1 mg/kg/hr; step 0.25 mg/kg/hr; emergence note | “PEDIATRIC Always Reference BROSELOW Tape … IV Continuous Infusion: • 0.5-1 mg/kg/hr. Titrate levels by 0.25mg/kg/hr PRN to achieve appropriate sedation. … Avoid sub-dissociative doses to prevent emergence phenomenon.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Contraindications, p.127 | contraindications; age floor | “Hypersensitivity to ketamine or any component of the formulation … Conditions that cannot tolerate sustained increases in blood pressure (non-traumatic intracerebral hemorrhage, hypertension associated with acute coronary syndrome; NOT contraindicated in TBI) … Children <3 mo. age” |

## cefazolin

### 10. open fracture / wound prophylaxis · adult · IV

- **Dose:** 2 g
- **Max single:** none stated
- **Max cumulative:** 12 g — maximum 12 g per day
- **Repeat, administration and cautions served:** Every 6-8 hours (JTS ID24 p.11; SMOG p.64). · Duration: skin and soft tissue without open fracture, 24 hours; open fracture, exposed bone or open joint, 24 hours, then again with each subsequent I&D until soft tissue coverage (JTS ID24 p.11). · Give within 3 hours of injury (JTS ID24 p.9). · Some cross-reactions occur in penicillin allergy; use with caution (SMOG p.103). · ID24 and SMOG also allow dosing by body mass: 1 g under 80 kg, 2 g at 81-160 kg, 3 g over 160 kg (JTS ID24 p.12; SMOG p.103).
- **Contraindications:** Hypersensitivity to cefazolin, other cephalosporin antibiotics, other beta-lactams, or any component of the formulation (SMOG CY24 p.103)
- **Flags:** WEIGHT_BAND_OPTION_IN_SOURCE
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2); was NOT_IN_SOURCE from the NASEMSO search alone. JTS ID24 Appendix B Table 1 p.11 and the SMOG antibiotic chart p.64: cefazolin 2 g IV every 6-8 hours; 24 hours for skin and soft tissue, and for open fractures 24 hours then with each subsequent I&D until soft tissue coverage. Maximum 12 g/day (ID24 footnote †; SMOG p.103). WEIGHT BANDS (an option in the same CPG, not a conflict between sources; owner question): ID24 footnote † and SMOG p.103 allow weight bands (1 g under 80 kg, 2 g 81-160 kg, 3 g over 160 kg) against the tables' flat 2 g; the bands leave 80-81 kg undefined, and SMOG's adult column also says '1-2g every 6-8hrs'. The flat 2 g is drafted; the owner rules. Not drafted, for the owner to place: the other ID24 rows (penetrating brain, spine, chest, maxillofacial, abdominal with metronidazole), the single pre-surgical dose (ID24 p.9), and the ventriculostomy regimen (ID30 p.13). No timed intra-operative re-dose and no IM/IO dose is printed. ID91 Table 12 (p.38) ranks cefazolin 'Better' behind the TCCC agents (ertapenem, moxifloxacin) when TCCC supplies are limited; at a surgical role ID24 makes it the preferred agent.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix B, Table 1. Post-Injury Antimicrobial Agent Selection and Duration (Extremity Wounds), p.11 | dose 2 g IV every 6-8 hours; duration (24 hours; open fracture: then with each I&D until soft tissue coverage) | “Skin, soft tissue, no open fractures … Skin, soft tissue, with open fractures, exposed bone, or open joints … Cefazolin, 2 gm IV q6-8h†‡ … 24 hours initially and repeat with each subsequent I&D until soft tissue coverage.” |
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix B, Table 1, footnote †, p.12 | conflicting: weight bands (1 g under 80 kg; 2 g 81-160 kg; 3 g over 160 kg); 12 g daily | “†Cefazolin may be dosed based on body mass: 1 gram if weight < 80 kg (176 lbs), 2 grams if weight 81-160 kg (177-352 lbs), 3 grams if weight > 160 kg (>352 lbs); doses up to 12 grams daily are supported by FDA-approved package insert.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Antibiotic Therapy Chart (Extremity Wounds), p.64 | corroborates: 2 g every 6-8 hours; durations | “Cefazolin 2g q 6-8hrs 24 hours … Cefazolin 2g q 6-8hrs 24 hours, then with each subsequent I&D until soft tissue coverage” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Cefazolin, Dose and Administration (ADULT column), p.103 | conflicting: weight bands; 1-2 g every 6-8 hours; maximum 12 g/day | “Routine dosing may be based on body mass: 1g if weight <80kg 2g if weight 81-160 kg (177-352 lbs), 3g if weight > 160 kg (>352 lbs) Max dose is 12g per day … 1-2g every 6-8hrs” |
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix A, Table 1 — Role 1 and Role 2 without surgical support, p.9 | timing: within 3 hours of injury | “Provide intravenous antimicrobials for open wounds (Appendix B) within 3 hours of injury.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Cefazolin, Contraindications, p.103 | contraindications; penicillin cross-reaction caution | “Hypersensitivity to cefazolin, other cephalosporin antibiotics, other beta-lactams, or any component of the formulation … Some cross reactions occur in those with penicillin allergies. Use with caution.” |

### 11. open fracture / wound prophylaxis · peds · IV

- **Dose:** 20–30 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Every 6-8 hours (JTS ID24 p.12; SMOG p.103). · Maximum 100 mg/kg/day (JTS ID24 p.12; SMOG p.103). · Duration as for the adult indication (JTS ID24 Table 1, p.11). · Some cross-reactions occur in penicillin allergy; use with caution (SMOG p.103).
- **Contraindications:** Hypersensitivity to cefazolin, other cephalosporin antibiotics, other beta-lactams, or any component of the formulation (SMOG CY24 p.103)
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2). JTS ID24 Table 1 footnote ‡ and SMOG CY24 p.103 PEDIATRIC column agree: 20-30 mg/kg IV every 6-8 hours, maximum 100 mg/kg/day. The daily maximum is a serve caution: max_cumulative holds a mass, and a per-kg daily cap is not a unit the engine computes (owner question). No per-dose gram cap is printed, and none is derived from the mg/kg figure.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix B, Table 1, footnote ‡ (Pediatric dosing), p.12 | dose 20-30 mg/kg IV every 6-8 hours; maximum 100 mg/kg/day | “‡Pediatric dosing: cefazolin, 20-30 mg/kg IV q6-8h (maximum, 100 mg/kg/day)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Cefazolin, Dose and Administration (PEDIATRIC column), p.103 | corroborates: same dose and maximum | “20-30 mg/kg IV q 6-8h (maximum, 100 mg/kg/day)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Cefazolin, Contraindications, p.103 | contraindications; penicillin cross-reaction caution | “Hypersensitivity to cefazolin, other cephalosporin antibiotics, other beta-lactams, or any component of the formulation … Some cross reactions occur in those with penicillin allergies. Use with caution.” |

## ceftriaxone

### 12. severe bacterial infection / sepsis · adult · IV

- **Dose:** 2 g
- **Max single:** none stated
- **Max cumulative:** none stated
- **Repeat, administration and cautions served:** Every 24 hours (JTS ID91 p.40; ID83 p.8). · Give IV/IO over 10 minutes (ID83, Better) or over 30 minutes (ID83, Best); SMOG gives slow IV push or in 100 cc NS by gravity (SMOG p.38). · SMOG's sepsis protocol gives ceftriaxone for the immunocompetent patient (SMOG p.38). · No source states a duration for sepsis; PCC antibiotics are generally given daily for seven to 10 days (JTS ID91 p.38).
- **Contraindications:** History of anaphylaxis or allergy to cephalosporins (JTS ID24 p.11: use the non-cephalosporin regimen)
- **Flags:** ADMINISTRATION_TIME_DIFFERS
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-16 (signing batch 2); was NOT_IN_SOURCE from the NASEMSO search alone. JTS ID91 p.40, ID83 p.8 and SMOG p.38 agree on 2 g; ID91 and ID83 give every 24 hours, SMOG no interval. SOURCES DISAGREE on administration only (the dose agrees; owner question): ID83 gives 'over 10 minutes' (Better tier) and 'over 30 minutes' (Best tier) for the same dose; SMOG gives slow IV push or in 100 cc NS. No source states a duration or maximum for sepsis. LABEL: no source says 'severe bacterial infection'; they say sepsis (owner question: relabel). In ID91 and ID83 ceftriaxone alone is 'Better' and ceftriaxone plus vancomycin plus metronidazole is 'Best'; the vancomycin figure differs between them (ID91 1.5 mg/kg, ID83 15 mg/kg), a finding for the vancomycin entry, not this one. Not drafted, for the owner to place: penetrating TBI (ID63 p.8, p.20; ID24 p.11, 2 g every 24 hours, duration differs) and severe pneumonia co-infection (COVID-19 austere CPG p.17).

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Prolonged Casualty Care Guidelines, CPG ID91, 21 Dec 2021 — Sepsis Treatment, Table 14. Sepsis Treatments/Interventions, p.40 | dose 2 g IV/IO every 24 hours | “ceftriaxone 2 grams IV/IO every 24 hrs” |
| JTS Clinical Practice Guideline — Sepsis Management in Prolonged Field Care, CPG ID83, 28 Oct 2020 — Treatment, Antimicrobial Therapy, p.8 | corroborates 2 g IV/IO every 24 hours; conflicting administration time (10 vs 30 minutes) | “ceftriaxone (Rocephin) 2 grams IV/IO given over 10 minutes q24hrs. … Ceftriaxone (Rocephin) 2 gm IV/IO q24 hrs given over 30 minutes” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Sepsis/Fever protocol, Treatment, p.38 | corroborates 2 g; conflicting administration (slow push or 100 cc NS); immunocompetent | “Ceftriaxone 2 g slow IV push or in 100 cc NS flow to gravity (immunocompetent)” |
| JTS Clinical Practice Guideline — Prolonged Casualty Care Guidelines, CPG ID91, 21 Dec 2021 — Antibiotics, Sepsis, and Other Drugs - PCC, Background, p.38 | general PCC duration (not ceftriaxone-specific) | “Antibiotics should be given daily for seven to 10 days, depending on the type of antibiotic given” |
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix B, Table 1 (Central Nervous System Wounds), p.11 | contraindication: cephalosporin allergy | “For patients with a history of anaphylaxis or allergies to cephalosporins” |

### 13. severe bacterial infection / sepsis · peds · IV

- **Dose:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Max single:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Max cumulative:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Repeat, administration and cautions served:** Neonates: do not give with IV calcium gluconate (risk of calcium-ceftriaxone precipitation) (SMOG p.102).
- **Contraindications:** History of anaphylaxis or allergy to cephalosporins (JTS ID24 p.11)
- **Flags:** DOSE_NOT_IN_SOURCE
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** INCOMPLETE (signing batch 2, 2026-10-16): no JTS or SMOG page states a paediatric ceftriaxone dose for sepsis. SMOG's sepsis protocol (p.38) is adult and has no paediatric column; SMOG has no ceftriaxone monograph. The only paediatric figure in the corpus is ID24's CNS-injury dose (100 mg/kg/day divided q12-24h, no cap printed), which is not carried across to sepsis. NASEMSO has no ceftriaxone. The entry exists so the gap shows; it refuses even if signed.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Sepsis/Fever protocol, Treatment, p.38 | checked: an adult protocol, no paediatric dose | “Ceftriaxone 2 g slow IV push or in 100 cc NS flow to gravity (immunocompetent)” |
| JTS Clinical Practice Guideline — Infection Prevention in Combat-related Injuries, CPG ID24, 27 Jan 2021 — Appendix B, Table 1, footnote ‡ (Pediatric dosing), p.12 | checked: the only paediatric ceftriaxone dose is for CNS injury, not sepsis | “ceftriaxone, 100 mg/kg/day IV divided q12-24h (dosing for CNS injury)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Calcium Gluconate, Contraindications, p.102 | caution: neonatal calcium co-administration | “Concomitant use of IV calcium gluconate and ceftriaxone in neonates (risk of precipitation of calcium- ceftriaxone)” |
