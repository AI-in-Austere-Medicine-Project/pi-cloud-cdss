# Unsigned contracts: inventory for the owner (2026-10-08)

Owner's ask (2026-10-08): list every unsigned contract with its citations; sign the clean ones; leave the uncertain ones unsigned and list them. **Signing is the owner's act** (CLAUDE.md, the work order's global rules), so nothing here is signed: this lists what a signature would and would not make servable. `drug_contracts.SIGNOFF_AUTHORS` accepts `clinician` or `AI-AIM` as `reviewed_by`.

**Result: no contract is clean to sign.** 41 are unsigned: 40 drug-contract dose entries (of 108; 68 are signed and servable) and procedure rows P1 and P2.

How each was checked: the entry was signed in memory (signoff true, reviewed_by AI-AIM, today's date) and run through `entry_is_servable`, the one gate every serve path uses. A signature alone would make 1 of 40 servable; the other 39 are incomplete drafts.

## The one entry a signature would make servable — uncertain

| Drug | Indication | Route | Population | Dose | Why it is not clean |
|---|---|---|---|---|---|
| dextrose | neonatal hypoglycaemia | IV | peds | 0.5–0.5 g/kg | Deferred by the owner ("neonatal dextrose", work order deferred list, 2026-09-25). Its sources are citation strings with no verbatim quote. It carries a 25 g single-dose maximum (an adult figure) on a neonatal entry. Citations: U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Dextrose, Dose and Administration: Pediatric, Hypoglycemia, IV — Newborns, p.105; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Hypoglycemia, p.85; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Hypoglycemia, p.86; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Appendix III. Medications, p.380 (NASEMSO states this appendix's class/contraindication content derives from medscape.com, accessed 2021-10-23); U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Newborn Care and Distress guideline, p.53 |

## 39 incomplete drafts — not signable

**Update 2026-10-08 (contract batch 1, analgesia):** fentanyl, analgesia infusion, IV, adult, is now drafted with cited values (25-250 mcg/hr, JTS ID29 p.24 and ID12 p.24, verbatim quotes). It stays unsigned and still refuses as signed: its starting rate is in no source and is left incomplete.

**Update 2026-10-14 (signing batch 1, analgesia):** 15 new unsigned entries outside this inventory's count: ketamine IM/IN (5, one incomplete), morphine paediatric IM, acetaminophen (4) and ketorolac (5), each cited verbatim. Ruled the same day: 8 signed (adult IM ketamine redrafted to 0.5–1.0 mg/kg, then signed); ketorolac excluded. See [`authoring/ANALGESIA_BATCH1_DRAFTS_2026-10-14.md`](authoring/ANALGESIA_BATCH1_DRAFTS_2026-10-14.md).

**Update 2026-10-19 (signing batch 2, sedation and antibiotics):** 13 entries drafted 2026-10-16, each cited verbatim. Ruled by the owner (Andrew Azelton) 2026-10-19: 5 signed (midazolam 1–4 mg as a ketamine add-on; ketamine sedation infusion, adult; cefazolin adult and paediatric; ceftriaxone adult, relabelled "sepsis"). 8 stay unsigned: the SMOG sides of the two closed conflicts, the midazolam ventilated infusion (both sides; v1.1), the rocuronium redose (adult and paediatric; the source calls it unreferenced), the paediatric ketamine infusion (v1.1) and paediatric ceftriaxone (no dose in any source). The rows above for rocuronium, cefazolin, ceftriaxone, midazolam and the ketamine infusion are the 2026-10-08 state. See [`authoring/SEDATION_ANTIBIOTIC_BATCH2_DRAFTS_2026-10-16.md`](authoring/SEDATION_ANTIBIOTIC_BATCH2_DRAFTS_2026-10-16.md) and the v1.1 items below.

A signature would not make these servable: `entry_is_servable` still refuses them. 38 have no dose (`dose_range` empty), 14 of those have no source either, and propofol induction has a sentinel in its contraindications. They need authoring — values with page citations — before they can be reviewed.

| Drug | Indication | Route | Population | Dose | Sources | Refused because |
|---|---|---|---|---|---|---|
| ketamine | prolonged sedation infusion | IV | adult|peds | empty | JTS Clinical Practice Guideline — Analgesia and Sedation Management during Prolonged Field Care, CPG ID61, 11 May 2017 — Appendix B: Ketamine Drip Dosing Tables, p.9 | clinical field(s) still empty or sentinel: dose_range |
| epinephrine | push-dose vasopressor for hypotension | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| epinephrine | infusion for refractory shock | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| rocuronium | redose interval | IV | adult|peds | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| fentanyl | analgesia infusion | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| cefazolin | open fracture / wound prophylaxis | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| cefazolin | open fracture / wound prophylaxis | IV | peds | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| ertapenem | penetrating abdominal injury | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| moxifloxacin | combat wound prophylaxis (oral) | PO | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| ceftriaxone | severe bacterial infection / sepsis | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| ceftriaxone | severe bacterial infection / sepsis | IV | peds | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| midazolam | procedural sedation | IV | adult | empty | NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Appendix III. Medications, p.387 (NASEMSO states this appendix's class/contraindication content derives from medscape.com, accessed 2021-10-23) | clinical field(s) still empty or sentinel: dose_range |
| midazolam | sedation infusion for the ventilated patient | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| propofol | induction of anaesthesia | IV | adult | 0.5–1.0 mg/kg | JTS Clinical Practice Guideline — Anesthesia for Trauma Patients, CPG ID40, 05 Apr 2021 — Induction of Anesthesia, item 4, p.3 | a sentinel survives in: contraindications |
| propofol | sedation infusion | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| calcium gluconate | hypocalcaemia after massive transfusion | IV | adult | empty | NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Appendix III. Medications, p.380 (NASEMSO states this appendix's class/contraindication content derives from medscape.com, accessed 2021-10-23) | clinical field(s) still empty or sentinel: dose_range |
| naloxone | opioid-induced respiratory depression | IN | adult|peds | empty | NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Opioid Poisoning/Overdose, p.304; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Appendix III. Medications, p.388 (NASEMSO states this appendix's class/contraindication content derives from medscape.com, accessed 2021-10-23) | clinical field(s) still empty or sentinel: dose_range |
| phytomenadione | warfarin reversal | IV | adult | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| phytomenadione | haemorrhagic disease of the newborn — prophylaxis | IM | peds | empty | **none** | clinical field(s) still empty or sentinel: dose_range, sources |
| artesunate | severe malaria | IV | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| artesunate | severe malaria | IV | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| artesunate | severe malaria — pre-referral only | PR | adult|peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| artemether | severe malaria | IM | adult|peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| artemether + lumefantrine | uncomplicated P. falciparum malaria | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| artemether + lumefantrine | uncomplicated P. falciparum malaria | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.24 (PDF p.29) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| quinine | severe malaria | IV | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.25 (PDF p.30) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| quinine | severe malaria | IV | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.25 (PDF p.30) (6.5.3.1 Antimalarial medicines) | clinical field(s) still empty or sentinel: dose_range |
| antivenom immunoglobulin | envenoming | IV | adult|peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.50 (PDF p.55) (19.2 Sera, immunoglobulins) | clinical field(s) still empty or sentinel: dose_range |
| oral rehydration salts | cholera / acute watery diarrhoea — rehydration | PO | adult|peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.48 (PDF p.53) (17.5.1 Oral rehydration) | clinical field(s) still empty or sentinel: dose_range |
| zinc sulfate | acute diarrhoea — adjunct to ORS | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.48 (PDF p.53) (17.5.2 Medicines for diarrhoea) | clinical field(s) still empty or sentinel: dose_range |
| isoniazid | drug-susceptible tuberculosis — first-line | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| isoniazid | drug-susceptible tuberculosis — first-line | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| rifampicin | drug-susceptible tuberculosis — first-line | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| rifampicin | drug-susceptible tuberculosis — first-line | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| pyrazinamide | drug-susceptible tuberculosis — first-line | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.19 (PDF p.24) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| pyrazinamide | drug-susceptible tuberculosis — first-line | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.19 (PDF p.24) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| ethambutol | drug-susceptible tuberculosis — first-line | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| ethambutol | drug-susceptible tuberculosis — first-line | PO | peds | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |
| ethambutol + isoniazid + pyrazinamide + rifampicin | drug-susceptible tuberculosis — intensive phase | PO | adult | empty | WHO Model List of Essential Medicines, 24th list (2025), in: The selection and use of essential medicines 2025 — p.18 (PDF p.23) (6.2.5 Antituberculosis medicines) | clinical field(s) still empty or sentinel: dose_range |

## v1.1 items from signing batch 2

Owner, 2026-10-19: these go to v1.1. None is drafted as an entry. The figures come from batch 2's research pass and are not yet quote-checked by a test; each is checked when it is drafted.

**Indications found but not drafted (12):**

| Item | Dose in source | Source (printed page) | Note |
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
| midazolam · procedural sedation · peds · IN | 0.2–0.5 mg/kg; maximum 10 mg total, 5 mg per nostril | SMOG p.140 | SMOG labels the route "unlabeled" |
| midazolam · post-intubation bolus · adult · IV | 1–4 mg (ID61 p.12) vs 0.05 mg/kg (SMOG p.12) vs 2–5 mg (ID12 p.24) | as listed | a conflict |
| midazolam · sedation / anxiolysis · adult · IM | 2–4 mg | JTS ID91 p.35 | ID61 p.12: "IM: not recommended" (a conflict) |

**Discrepancies with what is signed or sourced (2):**

| Item | What differs | Source (printed page) |
|---|---|---|
| midazolam · active seizure · adult · IV, signed at 0.1 mg/kg (max 4 mg; NASEMSO p.102) | other sources give fixed doses: SMOG p.140 5 mg IV/IO; SMOG p.37 5 mg IV/IO/IN or 10 mg IM; JTS ID63 p.9 5 mg every 5 min; JTS ID30 p.10 5–10 mg IV | as listed |
| vancomycin, in the ceftriaxone "Best" sepsis regimen | 1.5 mg/kg in ID91 p.40 against 15 mg/kg in ID83 p.8; one is likely a printing error. No vancomycin entry is drafted | JTS ID91 p.40; ID83 p.8 |

## Procedure rows P1, P2 — uncertain

| Row | Advice held | Condition | Sources | Why it is not clean |
|---|---|---|---|---|
| P1 | lumbar puncture | raised or suspected raised ICP | none | No corpus passage states the contraindication. The criterion is sourced (JTS TBI Management in PFC p.6, "Suspect high ICP in any head injury patient with GCS score <=8 …"). The only corpus mention of lumbar puncture is a myelography technique (Cervical Thoracolumbar Spine Injury p.24). Owner ruling (#98): unsigned draft, inert. |
| P2 | an NG tube | a basilar skull fracture, or its signs | none | No corpus passage links an NG tube to a skull fracture (searched 2026-10-08). The signs are sourced (JTS Use of TBI WB Biomarkers p.6). Owner ruling (#98): unsigned draft, inert; the owner to look in NASEMSO or SMOG. |

## Signing batch 3 rulings (2026-10-21)

Owner's rulings (Andrew Azelton, signer, 2026-10-21) on the batch 3 review packet ([`authoring/SIGNING_BATCH3_PACKET_2026-10-21.pdf`](authoring/SIGNING_BATCH3_PACKET_2026-10-21.pdf), items in [`authoring/SIGNING_BATCH3_ITEMS_2026-10-21.json`](authoring/SIGNING_BATCH3_ITEMS_2026-10-21.json)). "Apply exactly; sign nothing not listed." The rows above are the state before these rulings.

**Signed, 26 entries from 24 rulings** (by AI-AIM for the owner, `set_contract.py`; 2026-10-21):

| Item | Entry | Dose | Sources |
|---|---|---|---|
| E05 | epinephrine · push-dose vasopressor for hypotension · adult · IV | 5–20 mcg every 2–5 min | JTS ID83 p.24; SMOG p.12 noted |
| E06 | epinephrine · infusion for refractory shock · adult · IV | start 4 mcg/min; rate-check range 2–10 mcg/min | JTS ID83 p.24, ID91 p.40; SMOG p.114 |
| E10 | ertapenem · penetrating abdominal injury · adult · IV | 1 g once | JTS ID24 p.11, p.12 |
| E11 | moxifloxacin · combat wound prophylaxis (oral) · adult · PO | 400 mg once | JTS ID24 p.12, ID62 p.24; SMOG p.64 |
| E13 | midazolam · procedural sedation for pacing / cardioversion (relabelled) · adult · IV | 2.5–5 mg every 15–30 min | SMOG p.140 |
| E16 | dextrose · neonatal hypoglycaemia · peds · IV | 5 mL/kg D10 (0.5 g/kg), max 25 g | SMOG p.105 |
| E17 | propofol · induction of anaesthesia, hypotensive trauma patient (reduced dose) (relabelled) · adult · IV | 0.5–1 mg/kg | JTS ID40 p.3 |
| E18 | propofol · sedation infusion · adult · IV | 10–75 mcg/kg/min, max 100 | SMOG p.12, p.153; ID30 p.22 noted |
| E19 | calcium chloride · hypocalcaemia after massive transfusion · adult · IV (new drug) | 1 g after the 1st unit, then every 4 | JTS ID18 p.9, ID73 p.8; SMOG p.16 |
| E19 | calcium gluconate · hypocalcaemia after massive transfusion · adult · IV | 3 g, same timing | SMOG p.16, p.102 |
| E20 | naloxone · opioid-induced respiratory depression · adult · IN (adult half) | 0.4–2 mg every 2–3 min, max 10 mg | JTS ID61 p.13 |
| E21 | phytomenadione · warfarin reversal · adult · IV | 10 mg with 4-factor PCC | JTS Stroke CPG (03 Jul 2024) p.12 |
| E23 | artesunate · severe malaria · adult · IV | 2.4 mg/kg at 0, 12, 24, 48 h | JTS ID83 p.8 |
| U01 | cefazolin · penetrating brain injury · adult · IV | 2 g every 6–8 h | JTS ID24 p.11, ID30 p.7; SMOG p.64 |
| U02 | cefazolin · penetrating spinal cord injury · adult · IV | 2 g every 6–8 h | JTS ID24 p.12; SMOG p.64 |
| U03 | cefazolin · penetrating chest injury without esophageal disruption · adult · IV | 2 g every 6–8 h for 24 h | JTS ID24 p.11; SMOG p.64 |
| U03 | cefazolin · open maxillofacial fracture · adult · IV | 2 g every 6–8 h for 24 h | JTS ID24 p.11; SMOG p.64 |
| U04 | cefazolin · single pre-surgical dose for open wounds · adult · IV | 2 g once | JTS ID24 p.9 |
| U05 | cefazolin · ventriculostomy in place · adult · IV | 1 g three times daily | JTS ID30 p.13, p.23 |
| U06 | ceftriaxone · open or penetrating TBI · adult · IV | 2 g every 24 h | JTS ID63 p.8, p.20; ID24 p.11 noted |
| U07 | ceftriaxone · penetrating TBI / CNS injury · peds · IV | 100 mg/kg/day, served once daily, capped at 2 g | JTS ID24 p.12; ID63 p.8 (ceiling) |
| U08 | ceftriaxone · severe COVID-19 with bacterial pneumonia · adult · IV | 2 g every 24 h | JTS ID85 p.17 |
| U09 | midazolam · procedural sedation · peds · IV | 0.05–0.1 mg/kg every 15–30 min | SMOG p.140, p.47, p.50 |
| U10 | midazolam · procedural / conscious sedation · peds · IN | 0.2–0.5 mg/kg, max 10 mg (5 mg per nostril) | SMOG p.140 |
| U11 | midazolam · post-intubation sedation bolus · adult · IV | 1–4 mg every 5 min | JTS ID61 p.12 |
| U12 | midazolam · sedation / anxiolysis · adult · IM | 2–4 mg | JTS ID91 p.35 |

**Ruled SIGN, not signed: E27** (artemether + lumefantrine · uncomplicated P. falciparum malaria · adult · PO; 4 tablets, 4 at 8 h, then 4 twice daily for 2 days). The bank has no tablet unit: `drug_contracts.classify_units` fails closed on any dose unit that is not a mass, and no source states the tablet strength. It stays unsigned with the ruling written on it, for the owner to rule how a tablet count is served (a tablet unit in the engine, its own PR; or the dose in mg of the WHO tablet, 20 mg + 120 mg).

**Retired, 26** (out of the bank, into `retired_entries` with the reason): E01 (ketamine SMOG infusion), E03 (ketamine IM analgesia adult|peds: batch 1 signed adult 0.5–1.0 mg/kg and paediatric 0.5 mg/kg IM, checked first), E04, E07, E08 (rocuronium redose, unreferenced), E12, E22, E24, E25, E26, E28, E29, E30, E31 (antivenom), E32–E42, and the paediatric half of E20 (naloxone IN). A drug whose every entry is retired stays in the bank with no entries, so its name is still recognised and a dose stated for it holds.

**Deferred, 4: stay unsigned, holding.** E02 (ketamine infusion, peds), E09 (fentanyl infusion), E14 and E15 (midazolam ventilated infusion, both sides).

**P1, P2: stay unsigned hold rows**, not retired.

**v1.1 items from batch 3:** antivenom product entries (E31: antivenom is dosed per product); E27's tablet unit.

**The bare word "calcium"** was calcium gluconate's alias. With calcium chloride a drug of its own, the alias lint refuses it (it word-matches inside "calcium chloride"), and the two salts are signed at different doses. The bare word now names no salt: it is recognised (`drug_lexicon.json`), and a dose stated for it holds.
