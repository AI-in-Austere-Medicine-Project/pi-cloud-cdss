# A35: every number a deterministic card can emit, and the signed entry behind it

Owner, 2026-10-22: "Sweep every deterministic card: list every number a card can emit and the signed entry it comes from. Any number with no signed entry behind it is replaced by a hold, with the list in the PR for me to read."

**Scope, ruled 2026-10-22:**
- **Drug numbers only:** doses, rates, volumes, concentrations and preparation recipes.
- **Non-drug numbers are listed (section 3), not changed.** These are targets, thresholds, times and device settings.
- **The overdose ceilings keep their check** and stop printing their number.

"Deterministic card" means every response the pipeline returns without the generator. That is the pre-gates in `_query_with_rag_internal`, the cards `build_general_case_response` dispatches to, the prep cards, the vent cards, and the clarifying questions.

Cards that emit no number:
- CICO, WPW and TXA-in-sepsis blocks; the TXA-in-hypothermia hold; the sepsis-DCR refusal; sepsis management.
- Anaphylaxis ("epinephrine IM now", no dose); hypothermic arrest; MASCAL; cholera; snake bite; VT; the ketamine drip card.
- The unsigned tension and junctional holds; the notices.

## 1. Drug numbers with no signed entry behind them: replaced by a hold or removed

| Card | What it emitted | Now |
|---|---|---|
| Ketamine analgesia, IM | The legacy calculator, 2 mg/kg: "ketamine IM: 160 mg … dissociative analgesia (IM — no IV access)" at 80 kg. | The signed adult IM entry, ketamine · breakthrough pain — IM/IN (prolonged field care) · IM (JTS ID91 p.33, 0.5–1.0 mg/kg, max single 100 mg): 40 mg at 80 kg. With no signed entry on the route, the card holds. |
| Ketamine analgesia, IV | The legacy 0.3 mg/kg backfill (unreachable: the signed IV entry serves). | Removed. |
| Push-dose epinephrine prep | Its own recipe: "Make 10 mcg/mL", "Draw 1 mL of 1:10,000 (0.1 mg/mL) into a 10 mL syringe", "Add 9 mL NS. Total 10 mL", "Final concentration 10 mcg/mL", and the same in the TLDR. | Removed. The recipe reaches the medic only from the signed entry's own caution, printed under CAUTIONS: the NASEMSO bradycardia push dose, the NASEMSO p.109 paediatric shock push dose, or E05 ID83 p.24. With no entry served, the card says "No signed push-dose preparation". |
| Epinephrine drip | "Mix 1 mg epinephrine (1:10,000, 10 mL) in 250 mL NS = 4 mcg/mL", and the same in the TLDR. No entry states it. | "Concentration: prepare per local protocol … no pump rate in mL is computed", as on the norepinephrine card. `PREP_RECIPE_NUMBERS` is empty. |
| Requested-overdose hold | "exceeds safety ceiling 160.0mg for 80kg" (ketamine 2 mg/kg, rocuronium 1.2 mg/kg, succinylcholine 2 mg/kg; no citation). | The check is unchanged. The hold no longer prints the ceiling. |
| RSI bundle, seizure card, builder | The legacy calculators: ketamine induction 1.5 mg/kg (cap 2 mg/kg / 200 mg), post-intubation 0.5 mg/kg, rocuronium 1.0 mg/kg, succinylcholine 1.5 / 2.0 mg/kg, lorazepam 0.1 mg/kg (max 4). They were unreachable while their drugs had signed entries, and came back if a drug lost its last entry or the bank failed to import. | Removed. A role with no signed entry holds: "No signed dose for the {role} here". With no bank, nothing is calculated. |

## 2. Drug numbers kept, each with its signed entry

Each entry is written as drug · indication · route (population).

| Card | Number | Signed entry |
|---|---|---|
| Ketamine analgesia | adult IV 20 mg (80 kg) | ketamine · moderate to severe pain / analgesia · IV (adult) |
| | adult IM 40 mg (80 kg); max 100 mg | ketamine · breakthrough pain — IM/IN · IM (adult), JTS ID91 p.33 |
| | child IV and IM (e.g. 4 mg IV, 10 mg IM at 20 kg) | ketamine · moderate to severe pain / analgesia · IV and IM (peds) |
| | child 5 mg/mL dilution | that entry's `push_dilution` (owner-declared) |
| Ketamine age block | under 3 months | the entry's `min_age_months` (SMOG p.127) |
| RSI | ketamine induction (160 mg at 80 kg) | ketamine · RSI induction · IV |
| | rocuronium (96 mg at 80 kg) | rocuronium · RSI paralytic · IV |
| | succinylcholine (adult; child "5 years and above" or "under 5 years") | succinylcholine · RSI paralytic · IV |
| | post-intubation ketamine (40 mg at 80 kg), q20–30 min | ketamine · post-intubation sedation — repeated bolus · IV (owner-declared) |
| Seizure | lorazepam 4 mg (80 kg) | lorazepam · active seizure · IV |
| | midazolam 4 mg (when named) | midazolam · active seizure · IV |
| | second line, ketamine IV / IM | ketamine · refractory seizure · IV, IM (owner-declared) |
| | second line, levetiracetam | levetiracetam · status epilepticus · IV |
| Severe TBI | levetiracetam 1500 mg | levetiracetam · severe TBI seizure prophylaxis loading · IV |
| | 3% NaCl 7.5 g (= 250 mL) | sodium chloride 3% · severe TBI herniation bolus · IV |
| Haemorrhagic shock (DCR) | TXA 2 g; child 15 mg/kg | tranexamic acid · traumatic haemorrhage loading · IV (adult, peds) |
| Push-dose prep | 10–20 mcg | epinephrine · symptomatic bradycardia — push dose · IV (adult), NASEMSO p.36 |
| | 0.01 mg/kg, capped at 10 mcg | epinephrine · shock — push dose · IV (peds), NASEMSO p.109 |
| Epinephrine drip | 2–10 mcg/min, start 4 mcg/min | epinephrine · infusion for refractory shock · IV (adult), E06, JTS ID83 p.24 / ID91 p.40 |
| | 0.02–0.2 mcg/kg/min | epinephrine · symptomatic bradycardia — infusion · IV (adult) |
| | 0.05–0.3 mcg/kg/min | epinephrine · shock unresponsive to IV fluids — infusion · IV (adult\|peds) |
| Norepinephrine drip | 0.05–0.5, 0.02–0.4 and 0.02–2 mcg/kg/min | norepinephrine · shock, bradycardia and cardiogenic infusion entries |
| Why-this-dose | every range, cap and caution it prints | the named drug's signed entries, verbatim |

**Every caution line** on these cards is the entry's own serve caution: repeat intervals, maxima, mL equivalents and infusion times.

**Every volume** is the signed dose divided by the declared vial (`drug_concentrations.json`, signed): ketamine 50, rocuronium 10, succinylcholine 50, lorazepam 2 and TXA 100 mg/mL. The vial question lists only the signed presentations.

## 3. Non-drug numbers, not changed (for the owner's ruling)

| Card | Number | Where it comes from |
|---|---|---|
| Severe TBI | GCS 8 or less | Hardcoded; JTS ID63 p.6 cited in the code and SOURCE |
| | SBP above 110 (and TLDR "SBP > 110"); SpO2 above 93% | Hardcoded; ID30 p.7, ID63 p.20 |
| | child SBP 70 + 2 × age (1–10 years), 90 over 10, and the computed value | Hardcoded; SMOG pp.49–50 |
| | EtCO2 35–45 mmHg (twice) | Hardcoded; ID30 p.7 |
| | head of bed 30–45° (three times) | Hardcoded; ID30 pp.10–11 |
| | "EtCO2 35 mmHg for no more than 20 minutes" | Hardcoded; ID63 p.7 |
| Ketamine analgesia | "Reassess … q5min" | Hardcoded; **no citation** |
| Haemorrhagic shock (DCR) | TLDR "TXA within 3 hours of injury" | Hardcoded. The signed TXA caution served on the same card says it (ID18 p.9), but the card's SOURCE cites ID18 pp.3/4/10/11, not p.9. |
| Tension pneumothorax (signed, Andrew Azelton, 2026-10-12) | 14 gauge or larger; 3.25 in / 8 cm; 4th/5th ICS; 2nd ICS; after two decompressions; 5 cm catheters | needle_decompression_card.json, signed (ID74 p.8) |
| | "TXA within 3 hours" (with DCR) | Signed, but **the quote it cites (ID74 p.5) does not contain it** |
| Junctional bleeding (signed, Andrew Azelton, 2026-10-08) | "within 2 hours" | junctional_card.json, signed (ID73 p.5) |
| Vent cards | VT 6 mL/kg (toward 4); RR 16–20 / 20–30 / 8–12; PEEP 5–8, 5, 0–5; FiO2 100%; SpO2 ≥ 94% / < 90%; plateau < 30; driving pressure > 15; pH ≥ 7.20; I:E 1:4; EtCO2 35–40 / 30–35 / < 35; PaCO2 35–45; SBP ≥ 110; 24–48 h | vent_cards.json, signoff true, **reviewed_by "clinician" (a role, not a name)**, 2026-08-22 |
| | Devine IBW: 50 / 45.5 kg, 2.3 kg per inch over 60 in | Hardcoded in vent_module.py; **no citation** |
| | vent_devices.json, vent_troubleshooting.json | Unsigned; nothing renders |
| Pain-severity question | NRS 1–3 / 4–6 / 7–10 | Hardcoded; owner note (#164), no clinical citation |
| Vitals cautions (on every non-gated card) | SBP < 90, MAP < 65, RR < 10, SpO2 < 90, HR < 50, temperature < 35, GCS ≤ 8, glucose < 70; plausibility ranges (e.g. HR 10–300) | vitals_rules.json, **no signoff field** |
| Volumes | refused below 0.05 mL and above 60 mL; brief "undiluted" floor 0.2 mL | Hardcoded in drug_concentrations.py ("physical facts") |

## 4. Found in the sweep, not changed

- **The overdose ceiling holds signed doses.** Ketamine's 2 mg/kg ceiling is below the signed IM entries: agitation 4 mg/kg, refractory seizure 3–4 mg/kg, paediatric IM 3 mg/kg. "ketamine 320 mg IM" for an agitated 80 kg patient holds as an overdose. Raising the ceiling to the signed maximum would release those requests: owner to rule.
- **The push-dose prep card never serves E05.** `EPI_PUSH_DOSE_INDICATIONS = ("push dose",)` does not match "push-dose vasopressor", and the shock narrowing needs "shock" in the label. This is freeze-plan item 3.
- **A seizing patient with no IV access gets no benzodiazepine dose.** Lorazepam (IV only) is chosen first and the route filter (A34) then drops it, so the card holds. The signed paediatric IM midazolam seizure entry is never chosen. Nothing wrong is served.
- **Why-this-dose lists every signed entry of the drug.** It is not filtered by route or indication.
- **"d50 amp" and "dextrose prep" are prep terms with no card.** `fixed_prep_outcome` returns nothing for them.
