# Unsigned contracts: inventory for the owner (2026-10-08)

Owner's ask (2026-10-08): list every unsigned contract with its citations; sign the clean ones; leave the uncertain ones unsigned and list them. **Signing is the owner's act** (CLAUDE.md, the work order's global rules), so nothing here is signed: this lists what a signature would and would not make servable. `drug_contracts.SIGNOFF_AUTHORS` accepts `clinician` or `AI-AIM` as `reviewed_by`.

**Result: no contract is clean to sign.** 41 are unsigned: 40 drug-contract dose entries (of 108; 68 are signed and servable) and procedure rows P1 and P2.

How each was checked: the entry was signed in memory (signoff true, reviewed_by AI-AIM, today's date) and run through `entry_is_servable`, the one gate every serve path uses. A signature alone would make 1 of 40 servable; the other 39 are incomplete drafts.

## The one entry a signature would make servable — uncertain

| Drug | Indication | Route | Population | Dose | Why it is not clean |
|---|---|---|---|---|---|
| dextrose | neonatal hypoglycaemia | IV | peds | 0.5–0.5 g/kg | Deferred by the owner ("neonatal dextrose", work order deferred list, 2026-09-25). Its sources are citation strings with no verbatim quote. It carries a 25 g single-dose maximum (an adult figure) on a neonatal entry. Citations: U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Dextrose, Dose and Administration: Pediatric, Hypoglycemia, IV — Newborns, p.105; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Hypoglycemia, p.85; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Hypoglycemia, p.86; NASEMSO National Model EMS Clinical Guidelines v3.0 (March 2022) — Appendix III. Medications, p.380 (NASEMSO states this appendix's class/contraindication content derives from medscape.com, accessed 2021-10-23); U.S. Army Aeromedical Evacuation Standard Medical Operating Guidelines (SMOG) CY24 — Newborn Care and Distress guideline, p.53 |

## 39 incomplete drafts — not signable

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

## Procedure rows P1, P2 — uncertain

| Row | Advice held | Condition | Sources | Why it is not clean |
|---|---|---|---|---|
| P1 | lumbar puncture | raised or suspected raised ICP | none | No corpus passage states the contraindication. The criterion is sourced (JTS TBI Management in PFC p.6, "Suspect high ICP in any head injury patient with GCS score <=8 …"). The only corpus mention of lumbar puncture is a myelography technique (Cervical Thoracolumbar Spine Injury p.24). Owner ruling (#98): unsigned draft, inert. |
| P2 | an NG tube | a basilar skull fracture, or its signs | none | No corpus passage links an NG tube to a skull fracture (searched 2026-10-08). The signs are sourced (JTS Use of TBI WB Biomarkers p.6). Owner ruling (#98): unsigned draft, inert; the owner to look in NASEMSO or SMOG. |
