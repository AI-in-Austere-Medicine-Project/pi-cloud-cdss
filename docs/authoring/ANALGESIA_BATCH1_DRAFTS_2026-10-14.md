# Signing batch 1, analgesia: draft entries for review (2026-10-14)

The owner asked for (2026-10-14): ketamine (IV/IM/IN analgesia, adult and paediatric), fentanyl (IV, IN), morphine, acetaminophen and ketorolac. For each entry: a verbatim quote, the CPG ID, the printed page, indication, population and route; anything that can't be quoted verbatim stays marked incomplete. **Nothing here is signed.** Every entry below has `signoff: false` and is invisible to the serving path. Signing is the owner's act, by [`SIGNING.md`](SIGNING.md).

Every quote was checked against its cited page: `server/tests/test_contracts_analgesia_batch1b.py` reads the PDFs (with `JTS_PDF_DIR` and `NASEMSO_PDF` set), SMOG one column at a time. A quote leaves text out only where it shows `…`; `[sic]` marks a printed typo kept on purpose. Every page is the printed page; in these four documents the printed page and the PDF page are the same.

## Owner rulings, 2026-10-14

| Entry | Ruling |
|---|---|
| 1. ketamine IM adult\|peds 0.25 mg/kg (NASEMSO) | **Unsigned**: a documented alternate |
| 2. ketamine IM adult | **Redrafted to 0.5–1.0 mg/kg** (SMOG p.127 leads; ID61, TCCC corroborate); signed after the owner reads it |
| 3. ketamine IN adult 0.5–0.75 mg/kg | **Signed** |
| 4. ketamine IM paediatric 0.5 mg/kg | **Signed** (age floor added to contraindications, then re-signed) |
| 5. ketamine IN paediatric | Incomplete: no source |
| 6. morphine IM paediatric 0.1 mg/kg | **Signed** |
| 7–10. acetaminophen PO/IV, adult/paediatric | **Signed** |
| 11–15. ketorolac | **Not signed**: excluded on SMOG p.129, "Not for use as pain management for battlefield trauma patient!" |

Ruling 5's route-aware ceiling (48ef201) is accepted. The tables below show the drafts as first submitted; `drug_contracts.json` holds the current state.

## Entry 2 as redrafted, for the owner's read (2026-10-14)

**breakthrough pain — IM/IN (prolonged field care) · adult · IM: 0.5–1 mg/kg** · max single: none stated · max cumulative: none stated · unsigned

- **Contraindications:** Hypersensitivity
- **Cautions served:** JTS ID61: repeat every 15 minutes until the goal is achieved or nystagmus occurs. · Non-invasive capnography is an earlier predictor of hypoventilation than pulse oximetry.
- **Notes:** Redrafted 2026-10-14 on the owner's ruling: 0.5–1.0 mg/kg IM. The range is SMOG CY24 p.127 (adult "IM/IN • 0.5 - 1.0 mg/kg, repeat q 10-30 prn"); JTS ID61 p.11 (0.5–0.75 mg/kg, 40–60 mg), ID61 p.8 (80 mg IM, 0.4–0.8 mg/kg) and ID29 p.7 (TCCC 50 mg IM) lie inside or at it. Intervals differ: ID61 every 15 minutes (the caution served), SMOG 10-30, TCCC 30. The indication name is still ID61's; the dose is now SMOG-led. Awaiting the owner's read before signing. Ruled CONFLICT (group ketamine-im-analgesia, closed 2026-10-14): NASEMSO p.94 gives 0.25 mg/kg IM, capped at 25 mg initial; left unsigned.
- **Ruling:** OWNER RULING 2026-10-14 (Andrew Azelton): sign the IM ketamine entry at 0.5–1.0 mg/kg (ID61/SMOG/TCCC); NASEMSO's 0.25 mg/kg IM left unsigned. Signed after the owner reads this redraft.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (ADULT column), p.127 | dose range 0.5–1.0 mg/kg IM (adult analgesia, low dose) | “LOW DOSE: Analgesia: IV/IO Push (over 1 min) • 0.1-0.3 mg/kg, repeat q 10-30 prn IM/IN • 0.5 - 1.0 mg/kg, repeat q 10-30 prn” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Ketamine (Ketalar), p.11 | corroborates: IM/IN 40–60 mg (0.5–0.75 mg/kg), every 15 minutes | “Breakthrough pain in hemodynamically stable or unstable … IM/IN: every 15 minutes until goal achieved or nystagmus … 40–60mg (or 0.5–0.75mg/kg)” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Analgesia — footnote 1, ketamine push (for pain), p.8 | corroborates: 80 mg IM (0.4–0.8 mg/kg IM) when no IV/IO | “Ketamine push (for pain): 20mg (range, 0.1–0.2mg/kg) IV/IO every 10–30 minutes PRN. If an IV/IO is not available, quadruple the ketamine dose to give 80mg IM (range, 0.4–0.8mg/kg IM).” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Role 1 Treatment of Pain (TCCC triple analgesia, Option 3), p.7 | corroborates: TCCC 50 mg IM (inside the range at 50–100 kg) | “Option 3, for moderate to severe pain when the casualty is in hemorrhagic shock or respiratory distress or the casualty is at significant risk of developing either condition, should include ketamine 50 mg IM or IN or ketamine 20 mg slow IV or IO. Ketamine doses can be repeated every 30 minutes for IM or IN and every 20 minutes for IV or IO administration.” |

## What was already in the bank (unchanged)

| Drug | Entry | State |
|---|---|---|
| ketamine | moderate to severe pain, adult\|peds, IV, 0.25 mg/kg (NASEMSO p.94) | signed |
| ketamine | moderate to severe pain, peds, IV, 0.2 mg/kg (SMOG p.127) | signed |
| ketamine | background pain, PFC low dose, adult, IV, 0.1–0.2 mg/kg (ID61 p.8, p.11) | signed |
| fentanyl | acute pain, peds, IV, 1 mcg/kg | signed (owner-declared) |
| fentanyl | acute pain, adult\|peds, IN, 1 mcg/kg | signed |
| fentanyl | acute pain, JTS PFC fixed dose, adult, IV, 50 mcg | signed |
| fentanyl | adult IV per-kg (NASEMSO p.94; SMOG p.118) | **retired** by owner ruling 2026-09-24 (the conflict was settled on the 50 mcg fixed dose); not redrafted |
| fentanyl | analgesia infusion, adult, IV, 25–250 mcg/hr | unsigned, starting rate in no source (#148) |
| morphine | acute pain, adult IV, adult IM, peds IV, 0.1 mg/kg | signed |

So fentanyl (IV, IN) has nothing new to draft. Not drafted: TCCC's oral transmucosal fentanyl 800 mcg (ID29 p.7) is neither IV nor IN.

## Owner questions

1. **Ketamine IM dose (conflict group `ketamine-im-analgesia`).** NASEMSO p.94 gives 0.25 mg/kg for IM, IV and IO alike (the IV entry is signed at that dose). Every JTS and SMOG source gives a higher IM dose: ID61 p.11 0.5–0.75 mg/kg (40–60 mg); ID61 p.8 "quadruple the ketamine dose", 80 mg IM (0.4–0.8 mg/kg); SMOG p.127 adult 0.5 - 1.0 mg/kg, paediatric 0.5 mg/kg; ID29 p.7 (TCCC) 50 mg. For 80 kg, NASEMSO gives 20 mg, the JTS sources 40–80 mg. Entries 1, 2 and 4 are the sides; sign one per population.
2. **Ruling 5's tests.** They held every ketamine analgesia entry to 0.25 mg/kg, the IV figure. A separate commit makes the ceiling route-aware: IV/IO 0.25 mg/kg unchanged, IM/IN 1.0 mg/kg (SMOG's "LOW DOSE: Analgesia"). That is still half the retired 2 mg/kg and a quarter of the 4 mg/kg IM dissociative dose. Accept or reject the commit.
3. **Paediatric IN ketamine (entry 5)** is in no source. It is drafted as incomplete so the gap shows.
4. **SMOG's paediatric note** (p.127): "Avoid sub-dissociative doses to prevent emergence phenomenon." It is printed under the infusion lines. Read it against entry 4 before signing.
5. **Paediatric IM morphine (entry 6).** NASEMSO p.94 gives 0.1 mg/kg IM; SMOG p.141 says IM injection is "no longer recommended". The adult IM entry was signed on the same NASEMSO line.
6. **Ketorolac in a trauma tool.** SMOG p.129 lists "Not for use as pain management for battlefield trauma patient!" as a contraindication, with high bleeding risk and volume depletion. It is on every ketorolac draft's contraindication list. Should ketorolac be signed at all, or only under an indication that excludes trauma?
7. **Paediatric IM ketorolac (conflict group `ketorolac-im-analgesia-peds`).** NASEMSO 0.5 mg/kg (maximum 30 mg) against SMOG 1 mg/kg (no cap). Both sides are kept, entries 13 and 14.
8. **No concentration declared** for acetaminophen IV or ketorolac. Signed, they would serve a mass dose with no volume (the engine refuses to pick a form), as fentanyl does today.

## The drafts

## ketamine

### 1. moderate to severe pain / analgesia · adult|peds · IM

- **Dose:** 0.25 mg/kg
- **Max single:** 25 mg — maximum initial dose 25 mg
- **Max cumulative:** 100 mg — maximum cumulative dose 100 mg
- **Age floor:** 3 months
- **Flags:** SOURCE_CONFLICT · conflict group `ketamine-im-analgesia`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). The dose is NASEMSO p.94, which states one dose for IM, IV and IO: the IV entry is already signed at the same 0.25 mg/kg. CONFLICT: every other source gives a higher IM dose. SMOG CY24 p.127: adult IM/IN 0.5 - 1.0 mg/kg, paediatric IM 0.5 mg/kg. JTS ID61 p.11: IM/IN 40–60 mg (0.5–0.75 mg/kg). JTS ID61 p.8: when there is no IV/IO, quadruple the IV dose, 80 mg IM (0.4–0.8 mg/kg IM). JTS ID29 p.7 (TCCC): 50 mg IM or IN. For 80 kg, NASEMSO gives 20 mg (capped at 25 mg), the JTS sources 40–80 mg. The owner rules which IM dose serves; signing this entry and the PFC IM entry together would put two IM analgesia doses in front of one question.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | dose (0.25 mg/kg), route IM, maximum initial 25 mg, cumulative 100 mg | “d. Ketamine: i. 0.25 mg/kg IM, IV or IO (maximum initial dose 25 mg; maximum cumulative dose 100 mg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (ADULT column), p.127 | adult IM/IN analgesia 0.5–1.0 mg/kg | “LOW DOSE: Analgesia: IV/IO Push (over 1 min) • 0.1-0.3 mg/kg, repeat q 10-30 prn IM/IN • 0.5 - 1.0 mg/kg, repeat q 10-30 prn” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (PEDIATRIC column), p.127 | paediatric IM analgesia 0.5 mg/kg; the column gives IM and IV only, no IN | “Analgesia: IM: • 0.5 mg/kg, repeat q 10-30 prn IV: • 0.1 – 0.2 mg/kg, repeat q 10-30 prn” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Ketamine (Ketalar), p.11 | dose 40–60 mg (0.5–0.75 mg/kg) by IM or IN for breakthrough pain; interval | “Breakthrough pain in hemodynamically stable or unstable … IM/IN: every 15 minutes until goal achieved or nystagmus … 40–60mg (or 0.5–0.75mg/kg)” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Analgesia — footnote 1, ketamine push (for pain), p.8 | IM when no IV/IO: 80 mg (0.4–0.8 mg/kg IM), quadruple the IV dose | “Ketamine push (for pain): 20mg (range, 0.1–0.2mg/kg) IV/IO every 10–30 minutes PRN. If an IV/IO is not available, quadruple the ketamine dose to give 80mg IM (range, 0.4–0.8mg/kg IM).” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Role 1 Treatment of Pain (TCCC triple analgesia, Option 3), p.7 | TCCC fixed dose 50 mg IM or IN; repeat every 30 minutes | “Option 3, for moderate to severe pain when the casualty is in hemorrhagic shock or respiratory distress or the casualty is at significant risk of developing either condition, should include ketamine 50 mg IM or IN or ketamine 20 mg slow IV or IO. Ketamine doses can be repeated every 30 minutes for IM or IN and every 20 minutes for IV or IO administration.” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Contraindications, p.127 | age floor (under 3 months) | “Children <3 mo. age” |

### 2. breakthrough pain — IM/IN (prolonged field care) · adult · IM

- **Dose:** 0.5–0.75 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Flags:** SOURCE_CONFLICT · conflict group `ketamine-im-analgesia`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). JTS ID61 p.11: IM/IN 40–60 mg (or 0.5–0.75 mg/kg) every 15 minutes for breakthrough pain. ID61 p.8 gives a slightly wider IM range in the same CPG: quadruple the IV dose, 80 mg IM (range 0.4–0.8 mg/kg IM). CONFLICT with NASEMSO p.94, 0.25 mg/kg IM capped at 25 mg initial and 100 mg cumulative (the unsigned IM twin of the signed IV entry). ID61 is a prolonged-field-care CPG for adult casualties; population drafted adult.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Ketamine (Ketalar), p.11 | dose 40–60 mg (0.5–0.75 mg/kg) by IM or IN for breakthrough pain; interval | “Breakthrough pain in hemodynamically stable or unstable … IM/IN: every 15 minutes until goal achieved or nystagmus … 40–60mg (or 0.5–0.75mg/kg)” |
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Analgesia — footnote 1, ketamine push (for pain), p.8 | IM when no IV/IO: 80 mg (0.4–0.8 mg/kg IM), quadruple the IV dose | “Ketamine push (for pain): 20mg (range, 0.1–0.2mg/kg) IV/IO every 10–30 minutes PRN. If an IV/IO is not available, quadruple the ketamine dose to give 80mg IM (range, 0.4–0.8mg/kg IM).” |

### 3. breakthrough pain — IM/IN (prolonged field care) · adult · IN

- **Dose:** 0.5–0.75 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). JTS ID61 p.11: IM/IN 40–60 mg (or 0.5–0.75 mg/kg) every 15 minutes for breakthrough pain. Corroborating, not identical: SMOG CY24 p.127 adult IM/IN 0.5 - 1.0 mg/kg repeat q 10-30 prn; JTS ID29 p.7 (TCCC) 50 mg IN, repeat every 30 minutes. Not flagged as a conflict: ID61's range lies inside SMOG's (whose upper bound, 1.0 mg/kg, is higher), and TCCC's 50 mg is inside ID61's range at 67-100 kg. The intervals differ (ID61 15 minutes, SMOG 10-30, TCCC 30). NASEMSO gives no IN ketamine. No source states an IN volume limit per nostril.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Ketamine (Ketalar), p.11 | dose 40–60 mg (0.5–0.75 mg/kg) by IM or IN for breakthrough pain; interval | “Breakthrough pain in hemodynamically stable or unstable … IM/IN: every 15 minutes until goal achieved or nystagmus … 40–60mg (or 0.5–0.75mg/kg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (ADULT column), p.127 | adult IM/IN analgesia 0.5–1.0 mg/kg | “LOW DOSE: Analgesia: IV/IO Push (over 1 min) • 0.1-0.3 mg/kg, repeat q 10-30 prn IM/IN • 0.5 - 1.0 mg/kg, repeat q 10-30 prn” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Role 1 Treatment of Pain (TCCC triple analgesia, Option 3), p.7 | TCCC fixed dose 50 mg IM or IN; repeat every 30 minutes | “Option 3, for moderate to severe pain when the casualty is in hemorrhagic shock or respiratory distress or the casualty is at significant risk of developing either condition, should include ketamine 50 mg IM or IN or ketamine 20 mg slow IV or IO. Ketamine doses can be repeated every 30 minutes for IM or IN and every 20 minutes for IV or IO administration.” |

### 4. moderate to severe pain / analgesia · peds · IM

- **Dose:** 0.5 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Age floor:** 3 months
- **Flags:** SOURCE_CONFLICT · conflict group `ketamine-im-analgesia`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). SMOG CY24 p.127 PEDIATRIC column: IM 0.5 mg/kg, repeat q 10-30 prn. CONFLICT with NASEMSO p.94, 0.25 mg/kg IM (maximum initial 25 mg, cumulative 100 mg) for adults and children alike, which is the unsigned adult|peds IM entry. Both serve a paediatric IM question if both are signed; the owner picks one. Age floor 3 months from SMOG's contraindication, as on the signed IV entries. OWNER QUESTION: SMOG CY24 p.127, PEDIATRIC column, under the infusion lines: "**NOTE** Avoid sub-dissociative doses to prevent emergence phenomenon." Read it against this sub-dissociative analgesic dose before signing.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (PEDIATRIC column), p.127 | paediatric IM analgesia 0.5 mg/kg; the column gives IM and IV only, no IN | “Analgesia: IM: • 0.5 mg/kg, repeat q 10-30 prn IV: • 0.1 – 0.2 mg/kg, repeat q 10-30 prn” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Contraindications, p.127 | age floor (under 3 months) | “Children <3 mo. age” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | dose (0.25 mg/kg), route IM, maximum initial 25 mg, cumulative 100 mg | “d. Ketamine: i. 0.25 mg/kg IM, IV or IO (maximum initial dose 25 mg; maximum cumulative dose 100 mg)” |

### 5. moderate to severe pain / analgesia · peds · IN

- **Dose:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Max single:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Max cumulative:** **NEEDS_MANUAL_ENTRY** (incomplete)
- **Age floor:** 3 months
- **Flags:** DOSE_NOT_IN_SOURCE
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** INCOMPLETE: no source in the corpus states a paediatric intranasal ketamine dose. SMOG CY24 p.127 (paediatric: IM, IV), NASEMSO p.94 (IM, IV, IO) and JTS ID29 p.7 (adult casualty, 50 mg IN) were read. ID61 p.11's IM/IN 0.5–0.75 mg/kg is in an adult PFC CPG and is not carried across to children. The entry exists so the gap is visible; it refuses even if signed.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketamine, Dose and Administration (PEDIATRIC column), p.127 | checked: the paediatric column gives IM and IV analgesia, no IN | “Analgesia: IM: • 0.5 mg/kg, repeat q 10-30 prn IV: • 0.1 – 0.2 mg/kg, repeat q 10-30 prn” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | checked: ketamine IM, IV or IO only, no IN | “d. Ketamine: i. 0.25 mg/kg IM, IV or IO (maximum initial dose 25 mg; maximum cumulative dose 100 mg)” |
| JTS Clinical Practice Guideline — Pain, Anxiety and Delirium, CPG ID29, 26 Apr 2021 — Role 1 Treatment of Pain (TCCC triple analgesia, Option 3), p.7 | checked: TCCC 50 mg IN is a casualty (adult) fixed dose, no paediatric dose | “Option 3, for moderate to severe pain when the casualty is in hemorrhagic shock or respiratory distress or the casualty is at significant risk of developing either condition, should include ketamine 50 mg IM or IN or ketamine 20 mg slow IV or IO. Ketamine doses can be repeated every 30 minutes for IM or IN and every 20 minutes for IV or IO administration.” |

## morphine

### 6. acute pain / analgesia · peds · IM

- **Dose:** 0.1 mg/kg
- **Max single:** 10 mg — maximum initial dose 10 mg
- **Max cumulative:** none stated
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). NASEMSO p.94 gives 0.1 mg/kg IM, IV or IO (maximum initial dose 10 mg) without splitting adult from paediatric; the paediatric IV and adult IM entries are signed from the same line. SMOG CY24 p.141 (both columns) says IM/SubQ injection is no longer recommended, especially for repeated doses: painful, variable absorption, slow to peak. That is advice against the route, not a different dose; the owner rules whether a paediatric IM morphine dose should serve at all.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | dose 0.1 mg/kg, route IM, maximum initial 10 mg | “a. Morphine sulfate: i. 0.1 mg/kg IM, IV or IO (maximum initial dose is 10 mg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Morphine, Dose and Administration (PEDIATRIC column), p.141 | advice against the IM route (no dose) | “IM, SubQ: The use of IM/ SubQ injections is no longer recommended especially for repeated administration due to painful administration, variable absorption and lag time to peak effect.” |

## acetaminophen

### 7. mild to moderate pain / analgesia · adult · PO

- **Dose:** 500–1000 mg
- **Max single:** 1000 mg — maximum single dose 1000 mg
- **Max cumulative:** 4000 mg — maximum 4,000 mg in 24 hours, all acetaminophen-containing products
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). JTS ID61 p.13: IV/PO 500–1000 mg every 6 hours, daily limit 4,000 mg. SMOG CY24 p.92 agrees in range (325-500 mg every 4-6 hours, or 1000 mg 3-4 times daily, maximum 4 g/day). NASEMSO p.93 gives 15 mg/kg with a 1 g maximum single dose: the same ceiling. Interval every 6 hours (ID61).

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Acetaminophen (Tylenol), p.13 | adult IV/PO 500–1000 mg every 6 hours; daily limit 4,000 mg | “For mild to moderate pain: IV/PO: 500–1000mg every 6 hours … limit daily dose of acetaminophen and acetaminophen-containing products (e.g., Percocet) to 4,000mg” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Dose and Administration (ADULT column), p.92 | adult PO 325-500 mg every 4-6 hours or 1000 mg 3-4 times daily, maximum 4 g/day | “Pain or fever: (Limit total daily dose to <4 g/day) PO: • Regular release: 325-500 mg every 4-6 hours or 1000 mg 3-4 times daily (maximum: 4 g/day)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Contraindications, p.92 | contraindications | “Hypersensitivity to acetaminophen or any component of the formulation … Hepatic impairment or liver disease” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.93 | 15 mg/kg PO or IV, maximum dose 1 g, adults and children alike | “a. Acetaminophen 15 mg/kg PO or IV (maximum dose 1 g)” |

### 8. mild to moderate pain / analgesia · adult · IV

- **Dose:** 500–1000 mg
- **Max single:** 1000 mg — maximum single dose 1000 mg
- **Max cumulative:** 4000 mg — maximum 4,000 mg in 24 hours, all acetaminophen-containing products
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). JTS ID61 p.13 and SMOG CY24 p.92 agree: IV 500-1000 mg every 6 hours; daily limit 4,000 mg (ID61) / under 4 g (SMOG). NASEMSO p.93: maximum single dose 1 g.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix D: Recommended Pain and Sedation Medication — Acetaminophen (Tylenol), p.13 | adult IV/PO 500–1000 mg every 6 hours; daily limit 4,000 mg | “For mild to moderate pain: IV/PO: 500–1000mg every 6 hours … limit daily dose of acetaminophen and acetaminophen-containing products (e.g., Percocet) to 4,000mg” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Dose and Administration (ADULT column), p.92 | adult IV 500-1000 mg every 6 hours; daily limit under 4 g | “Pain or fever: (Limit total daily dose to <4 g/day) … IV: • 500-1000 mg every 6 hours” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Contraindications, p.92 | contraindications | “Hypersensitivity to acetaminophen or any component of the formulation … Hepatic impairment or liver disease” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.93 | 15 mg/kg PO or IV, maximum dose 1 g, adults and children alike | “a. Acetaminophen 15 mg/kg PO or IV (maximum dose 1 g)” |

### 9. mild to moderate pain / analgesia · peds · PO

- **Dose:** 10–15 mg/kg
- **Max single:** 1 g — maximum single dose 1 g (NASEMSO p.93)
- **Max cumulative:** 4 g — do not exceed 5 doses (4 g/day) in 24 hours (SMOG p.92)
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). SMOG CY24 p.92 PEDIATRIC: infants and children under 12 years, 10-15 mg/kg every 4-6 hours, at most 5 doses (4 g/day) in 24 hours; 12 and over take the adult dose. NASEMSO p.93: 15 mg/kg, maximum dose 1 g. The 1 g single cap is NASEMSO's; SMOG states none for PO. No source gives a neonatal dose or a lower age limit for PO.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Dose and Administration (PEDIATRIC column), p.92 | paediatric PO 10-15 mg/kg every 4-6 hours, under 12 years; at most 5 doses (4 g/day) in 24 hours | “PO: • Infants and Children <12 years: 10-15 mg/kg/dose every 4-6 hours as needed; do not exceed 5 doses (4 g/day) in 24 hours” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.93 | 15 mg/kg PO or IV, maximum dose 1 g, adults and children alike | “a. Acetaminophen 15 mg/kg PO or IV (maximum dose 1 g)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Contraindications, p.92 | contraindications | “Hypersensitivity to acetaminophen or any component of the formulation … Hepatic impairment or liver disease” |

### 10. mild to moderate pain / analgesia · peds · IV

- **Dose:** 15 mg/kg
- **Max single:** 750 mg — maximum single dose 750 mg (SMOG p.92, 2-12 years)
- **Max cumulative:** 3.75 g — maximum 75 mg/kg/day, not over 3.75 g daily (SMOG p.92, 2-12 years)
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). SMOG CY24 p.92 PEDIATRIC IV: 15 mg/kg every 6 hours for children under 2 and 2-12 years; for 2-12 years, maximum single dose 750 mg and daily 75 mg/kg (3.75 g). The printed line for 2-12 years ends in a stray "s" (kept as [sic]). SMOG states the caps for 2-12 years only; whether they apply under 2 is not stated. NASEMSO p.93: 15 mg/kg, maximum 1 g, which is above SMOG's 750 mg; the lower cap is drafted. No neonatal dose.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Dose and Administration (PEDIATRIC column), p.92 | paediatric IV 15 mg/kg every 6 hours; max single 750 mg, max daily 75 mg/kg (3.75 g), 2-12 years | “Infants and children <2 years 15 mg/kg every 6 hours … Children 2-12 years: 15 mg/kg every 6 hours s [sic] … Max single dose: 15 mg/kg/dose (≤750 mg/dose) … Max daily dose: 75 mg/kg/day (≤3.75 g daily) … Note: Children ≥12 years & Adolescents: Refer to adult dosing” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.93 | 15 mg/kg PO or IV, maximum dose 1 g, adults and children alike | “a. Acetaminophen 15 mg/kg PO or IV (maximum dose 1 g)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Acetaminophen, Contraindications, p.92 | contraindications | “Hypersensitivity to acetaminophen or any component of the formulation … Hepatic impairment or liver disease” |

## ketorolac

### 11. moderate to severe acute pain / analgesia · adult · IM

- **Dose:** 15–30 mg
- **Max single:** 30 mg — maximum single dose 30 mg
- **Max cumulative:** 120 mg — maximum 120 mg daily; 60 mg daily if over 65 years or under 50 kg (SMOG p.129)
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). SMOG CY24 p.129: IM 15-30 mg every 6 hours, daily maximum 120 mg (60 mg over 65 years or under 50 kg). NASEMSO p.94: 30 mg IM, inside SMOG's range. OWNER QUESTION: SMOG lists "battlefield trauma patient" as a contraindication, and the contraindication list includes high bleeding risk and volume depletion. This bank serves trauma care; the owner rules whether a ketorolac entry should be signed at all, or only with an indication that excludes trauma.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | adult 30 mg IM or 15 mg IV; age 2-16 0.5 mg/kg, maximum 30 mg IM or 15 mg IV | “ii. Ketorolac 1. Adult: 30 mg IM or 15 mg IV 2. Pediatric age 2–16 years old: 0.5 mg/kg (maximum dose of 30 mg IM or 15 mg IV)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Dose and Administration (ADULT column), p.129 | adult IM 15-30 mg / IV 15 mg every 6 hours; daily maximum 120 mg (60 mg over 65 years or under 50 kg) | “Patients ≥50 kg IM: • 15-30 mg every 6 hours (maximum daily dose: 120 mg) IV: • 15 mg every 6 hours (maximum daily dose: 120 mg) Adults >65 years and/or adults <50 kg IM: • 15-30 mg every 6 hours (maximum daily dose: 60 mg) IV: • 15 mg every 6 hours (maximum daily dose: 60 mg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Contraindications, p.129 | contraindications, including battlefield trauma | “Hypersensitivity to ketorolac, aspirin, other NSAIDs, or any component of the formulation. … High risk of bleeding, recent history of GI bleeding or perforation, known history of peptic ulcer disease. … Not for use as pain management for battlefield trauma patient! … Suspected cerebrovascular bleeding … Risk of renal failure secondary to volume depletion … Concurrent use with other NSAIDs” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management — Patient Safety Considerations, p.94 | contraindications | “4. Avoid non-steroidal anti-inflammatory medications such as ibuprofen and ketorolac in patients with NSAID allergy, aspirin-sensitive asthma, renal insufficiency, pregnancy, or known peptic ulcer disease 5. Ketorolac should not be used in patients with hypotension (due to renal toxicity)” |

### 12. moderate to severe acute pain / analgesia · adult · IV

- **Dose:** 15 mg
- **Max single:** 15 mg — maximum single dose 15 mg
- **Max cumulative:** 120 mg — maximum 120 mg daily; 60 mg daily if over 65 years or under 50 kg (SMOG p.129)
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). NASEMSO p.94 and SMOG CY24 p.129 agree: 15 mg IV; SMOG every 6 hours, daily maximum 120 mg (60 mg over 65 years or under 50 kg). OWNER QUESTION: SMOG lists "battlefield trauma patient" as a contraindication, and the contraindication list includes high bleeding risk and volume depletion. This bank serves trauma care; the owner rules whether a ketorolac entry should be signed at all, or only with an indication that excludes trauma.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | adult 30 mg IM or 15 mg IV; age 2-16 0.5 mg/kg, maximum 30 mg IM or 15 mg IV | “ii. Ketorolac 1. Adult: 30 mg IM or 15 mg IV 2. Pediatric age 2–16 years old: 0.5 mg/kg (maximum dose of 30 mg IM or 15 mg IV)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Dose and Administration (ADULT column), p.129 | adult IM 15-30 mg / IV 15 mg every 6 hours; daily maximum 120 mg (60 mg over 65 years or under 50 kg) | “Patients ≥50 kg IM: • 15-30 mg every 6 hours (maximum daily dose: 120 mg) IV: • 15 mg every 6 hours (maximum daily dose: 120 mg) Adults >65 years and/or adults <50 kg IM: • 15-30 mg every 6 hours (maximum daily dose: 60 mg) IV: • 15 mg every 6 hours (maximum daily dose: 60 mg)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Contraindications, p.129 | contraindications, including battlefield trauma | “Hypersensitivity to ketorolac, aspirin, other NSAIDs, or any component of the formulation. … High risk of bleeding, recent history of GI bleeding or perforation, known history of peptic ulcer disease. … Not for use as pain management for battlefield trauma patient! … Suspected cerebrovascular bleeding … Risk of renal failure secondary to volume depletion … Concurrent use with other NSAIDs” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management — Patient Safety Considerations, p.94 | contraindications | “4. Avoid non-steroidal anti-inflammatory medications such as ibuprofen and ketorolac in patients with NSAID allergy, aspirin-sensitive asthma, renal insufficiency, pregnancy, or known peptic ulcer disease 5. Ketorolac should not be used in patients with hypotension (due to renal toxicity)” |

### 13. moderate to severe acute pain / analgesia · peds · IM

- **Dose:** 0.5 mg/kg
- **Max single:** 30 mg — maximum dose 30 mg IM (NASEMSO p.94)
- **Max cumulative:** none stated
- **Age floor:** 24 months
- **Flags:** SOURCE_CONFLICT · conflict group `ketorolac-im-analgesia-peds`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). NASEMSO p.94: age 2-16, 0.5 mg/kg, maximum 30 mg IM. CONFLICT: SMOG CY24 p.129 gives 1 mg/kg IM for moderate discomfort in children 2-16, twice NASEMSO's dose, with no cap stated. The lower dose is drafted; the owner rules. No cumulative maximum stated for children. OWNER QUESTION: SMOG lists "battlefield trauma patient" as a contraindication, and the contraindication list includes high bleeding risk and volume depletion. This bank serves trauma care; the owner rules whether a ketorolac entry should be signed at all, or only with an indication that excludes trauma.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | adult 30 mg IM or 15 mg IV; age 2-16 0.5 mg/kg, maximum 30 mg IM or 15 mg IV | “ii. Ketorolac 1. Adult: 30 mg IM or 15 mg IV 2. Pediatric age 2–16 years old: 0.5 mg/kg (maximum dose of 30 mg IM or 15 mg IV)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Dose and Administration (PEDIATRIC column), p.129 | paediatric 2-16 years: 1 mg/kg IM (moderate), 0.5 mg/kg IV (severe) | “Children 2-16 y/o: • Moderate discomfort: 1 mg/kg IM • Severe discomfort: 0.5 mg/kg IV” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Contraindications, p.129 | contraindications, including battlefield trauma | “Hypersensitivity to ketorolac, aspirin, other NSAIDs, or any component of the formulation. … High risk of bleeding, recent history of GI bleeding or perforation, known history of peptic ulcer disease. … Not for use as pain management for battlefield trauma patient! … Suspected cerebrovascular bleeding … Risk of renal failure secondary to volume depletion … Concurrent use with other NSAIDs” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management — Patient Safety Considerations, p.94 | contraindications | “4. Avoid non-steroidal anti-inflammatory medications such as ibuprofen and ketorolac in patients with NSAID allergy, aspirin-sensitive asthma, renal insufficiency, pregnancy, or known peptic ulcer disease 5. Ketorolac should not be used in patients with hypotension (due to renal toxicity)” |

### 14. moderate to severe acute pain / analgesia — SMOG weight-based · peds · IM

- **Dose:** 1 mg/kg
- **Max single:** none stated
- **Max cumulative:** none stated
- **Age floor:** 24 months
- **Flags:** SOURCE_CONFLICT · conflict group `ketorolac-im-analgesia-peds`
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1): the other side of the paediatric IM conflict, kept so neither is dropped silently. SMOG CY24 p.129: children 2-16, moderate discomfort 1 mg/kg IM; no cap stated. CONFLICT: NASEMSO p.94 gives 0.5 mg/kg, maximum 30 mg IM. OWNER QUESTION: SMOG lists "battlefield trauma patient" as a contraindication, and the contraindication list includes high bleeding risk and volume depletion. This bank serves trauma care; the owner rules whether a ketorolac entry should be signed at all, or only with an indication that excludes trauma.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Dose and Administration (PEDIATRIC column), p.129 | paediatric 2-16 years: 1 mg/kg IM (moderate), 0.5 mg/kg IV (severe) | “Children 2-16 y/o: • Moderate discomfort: 1 mg/kg IM • Severe discomfort: 0.5 mg/kg IV” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Contraindications, p.129 | contraindications, including battlefield trauma | “Hypersensitivity to ketorolac, aspirin, other NSAIDs, or any component of the formulation. … High risk of bleeding, recent history of GI bleeding or perforation, known history of peptic ulcer disease. … Not for use as pain management for battlefield trauma patient! … Suspected cerebrovascular bleeding … Risk of renal failure secondary to volume depletion … Concurrent use with other NSAIDs” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | adult 30 mg IM or 15 mg IV; age 2-16 0.5 mg/kg, maximum 30 mg IM or 15 mg IV | “ii. Ketorolac 1. Adult: 30 mg IM or 15 mg IV 2. Pediatric age 2–16 years old: 0.5 mg/kg (maximum dose of 30 mg IM or 15 mg IV)” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management — Patient Safety Considerations, p.94 | contraindications | “4. Avoid non-steroidal anti-inflammatory medications such as ibuprofen and ketorolac in patients with NSAID allergy, aspirin-sensitive asthma, renal insufficiency, pregnancy, or known peptic ulcer disease 5. Ketorolac should not be used in patients with hypotension (due to renal toxicity)” |

### 15. moderate to severe acute pain / analgesia · peds · IV

- **Dose:** 0.5 mg/kg
- **Max single:** 15 mg — maximum dose 15 mg IV (NASEMSO p.94)
- **Max cumulative:** none stated
- **Age floor:** 24 months
- **Status:** unsigned (PENDING_CLINICAL_SIGNOFF)
- **Notes:** Drafted 2026-10-14 (signing batch 1). NASEMSO p.94 and SMOG CY24 p.129 agree: 0.5 mg/kg IV, ages 2-16; NASEMSO caps it at 15 mg. No cumulative maximum stated for children. OWNER QUESTION: SMOG lists "battlefield trauma patient" as a contraindication, and the contraindication list includes high bleeding risk and volume depletion. This bank serves trauma care; the owner rules whether a ketorolac entry should be signed at all, or only with an indication that excludes trauma.

| Source (printed page) | Supports | Verbatim quote |
|---|---|---|
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management, p.94 | adult 30 mg IM or 15 mg IV; age 2-16 0.5 mg/kg, maximum 30 mg IM or 15 mg IV | “ii. Ketorolac 1. Adult: 30 mg IM or 15 mg IV 2. Pediatric age 2–16 years old: 0.5 mg/kg (maximum dose of 30 mg IM or 15 mg IV)” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Dose and Administration (PEDIATRIC column), p.129 | paediatric 2-16 years: 1 mg/kg IM (moderate), 0.5 mg/kg IV (severe) | “Children 2-16 y/o: • Moderate discomfort: 1 mg/kg IM • Severe discomfort: 0.5 mg/kg IV” |
| U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Ketorolac, Contraindications, p.129 | contraindications, including battlefield trauma | “Hypersensitivity to ketorolac, aspirin, other NSAIDs, or any component of the formulation. … High risk of bleeding, recent history of GI bleeding or perforation, known history of peptic ulcer disease. … Not for use as pain management for battlefield trauma patient! … Suspected cerebrovascular bleeding … Risk of renal failure secondary to volume depletion … Concurrent use with other NSAIDs” |
| NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Pain Management — Patient Safety Considerations, p.94 | contraindications | “4. Avoid non-steroidal anti-inflammatory medications such as ibuprofen and ketorolac in patients with NSAID allergy, aspirin-sensitive asthma, renal insufficiency, pregnancy, or known peptic ulcer disease 5. Ketorolac should not be used in patients with hypotension (due to renal toxicity)” |

