# Sweep PR 2 (SW2): a card answers a named drug only with its dose or a hold by name

**Owner (2026-10-30):** "PR 2, cards (after PR 1): a card answers a question that names a drug only if the card serves that drug's signed dose, or holds it by name; otherwise the drug lane answers. Add the signed doses to: anaphylaxis card (epinephrine IM 0.3 mg adult / 0.15 mg child), paediatric RSI card (atropine pre-dose), sepsis card (ceftriaxone 2 g), ketamine sedation drip card (0.5–2 mg/kg/hr as rate). Rows: epinephrine[0][1][4][9], atropine[5], ceftriaxone[0], propofol[0], T7."

Tests: `tests/test_sweep_pr2_cards.py`, committed failing first (`f604b28`).

## 1. The rows

Live (a7c9043, 2026-10-30), each question named a drug and a card answered it with no dose for that drug:

| Row | Question | Card served | Now |
|---|---|---|---|
| epinephrine[0] | "80 kg adult, anaphylaxis, throat swelling, epinephrine IM" | anaphylaxis: "Give epinephrine IM now", no dose | anaphylaxis card, **epinephrine IM 0.3 mg** |
| epinephrine[1] | "20 kg 6 year old, anaphylaxis, throat swelling, epinephrine IM" | the same | anaphylaxis card, **epinephrine IM 0.15 mg** |
| epinephrine[4] | "80 kg adult, hypotensive, SBP 75, push-dose pressor, epinephrine IV" | sepsis card | drug lane |
| epinephrine[9] | "20 kg 6 year old, shock, push dose, epinephrine IV" | sepsis card | drug lane |
| atropine[5] | "20 kg 6 year old, about to intubate, pre-dose for RSI, atropine IV" | RSI bundle, "Ask for atropine by name for the dose" | RSI bundle, **atropine IV 0.4 mg** first |
| ceftriaxone[0] | "80 kg adult, septic, fever and hypotension, ceftriaxone IV" | sepsis card, "Start antibiotics if available" | sepsis card, **ceftriaxone IV 2 g** |
| propofol[0] | "80 kg adult, hypotensive trauma patient, need induction, propofol IV" | DCR card: TXA, no propofol | drug lane |
| T7 | "ketamine drip for sedation, intubated, 90 kg" | drip card: "document concentration … and pump rate" | drip card, **ketamine IV 0.5-2 mg/kg/hr (45-180 mg/hr for this 90kg patient)** |

## 2. The rule (`card_unanswered_drugs`, `card_yields`)

The drugs a question names are PR 1's `asked_drugs` (generic names, aliases included). A card answers only if, for each of them, it has:

- **a dose:** a line outside CAUTIONS, CONTRAINDICATIONS, WATCH, DON'T, TLDR, EVAC and SOURCE that names the drug and states an amount; or
- **a hold by name:** such a line saying no signed dose or rate is given ("no signed …", "no … dose … here").

A caution naming the drug ("Ask for atropine by name for the dose") is neither. Otherwise the card yields and the pipeline carries on to the drug lane, exactly as if no card had matched.

A drug the question says it does not have is not asked for ("no antivenom available" keeps the snake bite card).

Applied to every treatment card: sepsis, the common cards (anaphylaxis, seizure, hypothermic arrest, VT, MASCAL, ketamine drip, cholera, snake bite), tension pneumothorax, severe TBI, ketamine analgesia, the RSI bundle, the vent cards and DCR. **Never to a hold or a refusal:** the TXA blocks, the sepsis-DCR refusal, the overdose pre-gate, the unsigned junctional and tension holds and the RSI access check stay as they are, so no gate loosens.

Three cards hold a drug they deliberately do not give, and now say so by name:

- **seizure (A9):** "A benzodiazepine (midazolam) has already been given: no further benzodiazepine dose here." Without the name, "still in status after 10 mg of versed" would have left the card for the drug lane.
- **seizure, no weight:** "No signed benzodiazepine (midazolam) dose without a weight."
- **RSI bundle:** one paralytic per intubation. A question naming both gets "rocuronium: no dose here: one paralytic per intubation, and this bundle's is succinylcholine."

## 3. The doses

Each dose comes from the signed entry, rendered as the TBI card renders levetiracetam (`_served_from_pairs`, `render_range_line`, with its contraindications and cautions). Population follows the drug lane's gate (`_card_signed_entries`): a child needs a weight, and an adult fixed dose needs an adult confirmed or a weight (#181). Where the gate is not met, or nothing is signed for the patient, the card holds the drug by name:

- **anaphylaxis:** epinephrine IM, "anaphylaxis": adult 0.3 mg, child 0.15 mg (NASEMSO p.67). With no age or weight: "epinephrine IM: no signed dose until you confirm the patient is an adult, or give the age or the weight in kg."
- **sepsis:** ceftriaxone IV, "sepsis", adult 2 g (JTS ID91 p.40; ID83 p.8). There is no paediatric sepsis entry, so a child gets "no signed ceftriaxone dose for sepsis for a child here". The SOURCE line now reads "JTS CPG ID83, Sepsis Management in Prolonged Field Care (28 Oct 2020) · doses: …".
- **paediatric RSI:** atropine IV, "RSI pre-dose — paediatric intubation", 0.02 mg/kg (min 0.1, max 0.5 mg; ID39 p.28), as a new bundle role (`_contract_rsi_entries`, children only), first under GIVE, and DO THIS step 2 reads "Atropine pre-dose first (see its cautions), then induction, then paralytic." Who gets it is the entry's own caution, printed with it. No atropine vial is in the kit, so the line says NO VOLUME, like any drug with no confirmed vial.
- **ketamine drip:** ketamine IV, "prolonged sedation infusion", adult 0.5-2 mg/kg/hr, under DRIP (a brief dose section), with the same range in mg/hr at a confirmed weight. No pump rate in mL: the ID61 mix and its mL/h rule are the entry's cautions, printed beneath. The paediatric infusion is not servable (its start and mix are NEEDS_MANUAL_ENTRY), so a child gets "no signed ketamine infusion rate for a child here".

## 4. For the owner

- **The ketamine RSI induction entry's signed caution** still ends "Ask for atropine by name for the dose." On a child's card it now prints beneath the atropine line. It is signed text and is not changed here.
- **Epinephrine anaphylaxis population:** the entries define adult and child by weight (25 kg). The card follows the system's paediatric flag, as the drug lane does, so a heavy child (e.g. 13 years, 50 kg) gets 0.15 mg with a caution saying adult is 25 kg or more. Not changed here.
- **Hypothermic arrest:** "… cardiac arrest in the snow, epinephrine?" now goes to the drug lane, whose dose check decides. No replay row asks this.

## 5. Tests changed

- `test_drug_contracts.py`: the anaphylaxis, sepsis and ketamine drip cards move from DOSELESS_CARDS to the dose cards, with four DOSE_TEMPLATE_CASES (anaphylaxis adult and child, sepsis adult, drip adult), so every number they print is traced to its contract.
- `test_ped_ketamine_analgesia.py`: the infant RSI brief's line 2 carries the atropine item after the paralytic. The test now checks that the paralytic item ends with its qualifier, not the whole line.
- `test_sweep_pr2_cards.py`: the drip rate's section is DRIP, not RATE as first written, because DRIP is a brief dose section and was already the card's heading.

## 6. Checked

**Replay** vs main abea861 (live kit), the five sets:

| Set | Rows | Changed | Newly held | Newly released | Newly doses |
|---|---|---|---|---|---|
| served | 1,738 | 0 (byte-identical) | 0 | 0 | 0 |
| held | 308 | 0 (byte-identical) | 0 | 0 | 0 |
| gate | 1,408 | 0 (byte-identical) | 0 | 0 | 0 |
| log | 4,938 | 0 (byte-identical) | 0 | 0 | 0 |
| pipe | 847 | 31 | 0 | 0 | **6** |

Only the pipe set runs the pipeline, so only it can reach a card. Every changed row is listed below. Rows marked **sign-off** serve a dose main did not.

**Newly doses, 6 (sign-off):**

- ceftriaxone IV 2 g on the sepsis card, 5 live rows:
  - "80kg male HR 106 BP 92/46 temp 38.2C pus draining from wound";
  - "Currently managing a 70-year-old with hypotension …";
  - "I have a patient who is hypotensive his blood pressure is 90/30. He has a fever of 104 …", three rows (one prefixed "MEDIC").
- ketamine IV 0.5-2 mg/kg/hr (40-160 mg/hr at 80 kg) on the drip card, 1 live row: "patient intubated need a ketamine drip for sedation 80kg male".

**An atropine line added to a bundle that already dosed, 5 (sign-off;** the replay counts these as changed, not newly dosing):

- "have a 6 year old TBI I need to RSI … 35kg" (live): atropine IV 0.5 mg (0.7 mg capped at the 0.5 mg maximum). Under the entry's "who gets it" caution, a 6-year-old receiving rocuronium is not in the listed groups; the line serves with that caution, as asked.
- "Need to rsi a 75lb patient. IV established" (live): 0.5 mg. No age is given; the system already treats 34 kg as paediatric, and main's bundle served the paediatric entries.
- H-SESS-014 (bank, run and live, 3 rows): five questions pasted as one message ("… RSI meds for a 100kg male … 22kg child, femur fracture …"). The patient context was already paediatric with an 80 kg weight on main (the "22kg child" question), and the bundle served paediatric doses there. The atropine line follows the same flag. It is an existing mixed-patient artefact, not new here.

**The card now holds the named drug by name, no dose, 17 rows:**

- anaphylaxis, no age or weight, 8 rows: "epinephrine IM: no signed dose until you confirm the patient is an adult, or give the age or the weight in kg".
  - G-TYP-05 (bank, run), G-DIC-03 (bank, run), A1-WT-023, and one live row, "patient with severe anaphylaxis hives throat swelling BP dropping".
  - A1-PED-008 "epinephrine dose for pediatric anaphylaxis": "… until you give the child's weight in kg".
- sepsis, no age or weight, 3 rows: "ceftriaxone IV: no signed dose until you confirm …".
  - G-ADV-07 (bank, run), and one live row, "hypotensive approximately 80/30 heart rate of 150 …".
- seizure, no weight, 4 rows: "No signed benzodiazepine (midazolam) dose without a weight": A1-WT-012, A1-NOWT-004, A1-PED-004, and the live "versed for pedi sz".
- seizure, after versed (A9), 3 rows: "A benzodiazepine (midazolam) has already been given …": H-S3 (bank, run, live).

**Left a card for the drug lane, 3 rows:**

- "levetiracetam dose for seizure" (A1-WT-033): the seizure card named levetiracetam with no dose. The drug lane now asks "Adult patient?".
- "Need Ketamine dose for status seizure" (live): the seizure card had no ketamine. The drug lane now asks "IV or IM?".
- "OK, let's try this again … seven years old. He is 75 pounds having status seizure need Ketamine dose cause we've already maxed out our pencils … 500 in 10 mL for Ketamine" (live). On main the seizure card served **lorazepam 3.4 mg** to a child whose benzodiazepines were maxed out ("pencils" is a dictation slip) and whose medic asked for ketamine. It now goes to the generator and the dose check (the replay stubs the generator, so no text is judged).

**Found by the first replay and fixed:** two seizure rows ("how much midaz for the seizure", and "Have a TBI patient … maxed out on versed") left the card because its lines named no benzodiazepine; they now name it. "snakebite, no antivenom available" left the snake bite card; a drug the question says it lacks is no longer counted as asked. Each is now a test.

**Suite:** 3,890 passed, 47 skipped, 3 xfailed.

**Harness:** 29/29 against the branch on :8014 (Offline mode, qwen2.5:3b).

**The eight rows on the branch (:8014):**
- epinephrine[0] 0.3 mg and epinephrine[1] 0.15 mg IM on the anaphylaxis card.
- atropine[5] 0.4 mg first on the RSI bundle.
- ceftriaxone[0] 2 g on the sepsis card.
- T7 0.5-2 mg/kg/hr (45-180 mg/hr) on the drip card; each brief leads with the dose.
- In the drug lane:
  - epinephrine[4] and [9]: qwen's answers hold (an mL volume with no vial; 0.1 mg for a child against the signed 0.01 mg/kg).
  - propofol[0]: serves the signed 40 mg induction dose, but the line reads "Draw 40 mg of propofol IV (40 mg)", a malformed template line. That belongs to PR 3's brief tidy.
