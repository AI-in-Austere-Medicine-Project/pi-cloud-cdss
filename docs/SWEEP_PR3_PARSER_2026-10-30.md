# Sweep PR 3: parser and withheld (med sweep 2026-10-30)

**Owner (2026-10-30):** "PR 3 (parser and withheld): glucose values never read as temperature; midazolam indication list includes procedural sedation; "intranasal"/"IN" is a route; "fighting us"/"combative"/"kicking our ass" → agitation; atropine nerve-agent escalation within the signed 16 mg; calcium with no salt asks "chloride or gluconate?". Brief tidy: no contradictory "NO VOLUME" beside a volume line, no extra ranges, no "confirm concentration" for tablets."

**Owner (2026-11-03), found in PR 1:** "The infusion finding: yes, fold into PR 3; signed infusion entries enter the allowed list as rates (per-kg/min or per-kg/hr with the signed range), and a correct signed infusion line serves; a bolus for an infusion question still holds. List every row it releases for my sign-off."

The sweep asked live (a7c9043, Offline mode: qwen2.5:3b writes and checks) one question per signed entry. Tests: `tests/test_sweep_pr3_parser.py`, committed failing first (`8c1dc72`).

## 1. dextrose[0][1][2]: a glucose is never read as a temperature

"glucose 2.1" was rejected as "Glucose 2.1 is not a plausible temperature in either unit". The rejection text for every two-unit vital with no stated unit said "temperature" (`vitals._reason`). Height said it too.

**Fix.** A glucose with no unit names the unit it was read in and how to give the other: "Glucose 2.1 with no unit is read as mg/dL, and is outside 10-800mg/dL; if it is mmol/L, say "2.1 mmol/L"". The "say …" part appears only when the number fits the other band, so "sugar 2000" does not suggest 2000 mmol/L. Height says "height". Temperature is unchanged.

**Not changed (for the owner).** The documented convention still reads a unitless glucose as mg/dL (`assumed_unit_when_unstated`), so "glucose 2.1" is still not stored. A number under 10 fits only the mmol/L band. Reading it as mmol/L would be a change to that convention, and that is the owner's decision.

## 2. midazolam[2][7]: procedural sedation is an indication

"procedural sedation for a shoulder reduction, midazolam IV" was asked "Which indication for midazolam — agitation, pacing or cardioversion, sedation (already intubated) or seizure?". The procedural labels fell in the sedation class, whose question word is "already intubated", and the sedation cue deliberately skips "procedural sedation".

**Fix.** Procedural sedation is its own class (`INDICATION_CLASSES`), after pacing / cardioversion:
- Labels: "procedural sedation" (adult IV 1–4 mg) and "procedural / conscious sedation" (peds IN 0.2–0.5 mg/kg).
- Cues: "procedural", "conscious sedation", "sedation for a … reduction / relocation / procedure / repair / debridement".
- Where pacing is stated and the drug has a pacing entry, pacing wins over procedural sedation, as it already won over sedation.

The bare question now offers "procedural sedation". midazolam[2] gets the procedural entry first.

## 3. ketamine[18], midazolam[7]: "intranasal" / "IN" is a route

"ketamine intranasal" was asked "IV or IM? Do you have access?"; the signed IN entries were never offered.

**Fix.** `route_preference` takes "IN" from:
- "intranasal" / "intranasally";
- "nasal spray / route / atomiser / dose";
- "via the nose";
- "MAD";
- a capitalised "IN", but not in a message typed mostly in capitals ("80 KG ADULT IN PAIN").

"Nasal fracture" and "pain in the leg" are not a route. A stated IN is kept when "no IV" is also said: "no IV" no longer switches the route to IM over an IN.

The ketamine analgesia card takes IN the way it takes IM. "Breakthrough pain — IM/IN (prolonged field care)" is the bank's only IN pain entry. ketamine[18] at 80 kg now serves "Draw 0.8 mL of 50mg/mL ketamine IN (40 mg) (kit vial)".

## 4. T1: agitation slang

"this guy's fighting us, 250 lb, ketamine IM" was asked which indication. The agitation cue now also reads:
- "fighting us / me / him / her / them / the crew / the team / the medics / restraints";
- "kicking our / my … ass / butt";
- "swinging at".

"Combative" was already a cue. "Fighting position" is not agitation.

## 5. atropine[3]: the nerve-agent escalation within 16 mg

qwen gave 2 → 4 → 8 → 16 mg. It was held because the check accepted only 2 mg. The signed entry is "nerve agent poisoning — escalating IV/IO bolus":
- 2 mg;
- max single dose 16 mg, rule "the escalation stated reaches 16 mg per bolus";
- its caution: "2 mg then 4, 8, 16 mg … each later bolus doubles" (CBRN ID69 p.28).

**Fix.** `drug_contracts.escalation_steps_mg` gives the doubling steps above the dose, up to the signed maximum single dose. It applies only where the max_single rule names an escalation, which today means this one entry. Those steps (4, 8, 16 mg) pass in the answer's steps and prose. 32 mg holds, and so does 6 mg (not a doubling).

**Found in this PR's replay and closed.** The live answer's GIVE line was "Atropine IV: 16 mg … Indication: nerve agent poisoning — escalating IV/IO bolus": the ceiling given as the dose. A labelled dose line ("Indication:") must state the first bolus. That row stays held.

## 6. T9: calcium with no salt

"calcium after 4 units of blood" was held: "EdgeCDSS has no signed calcium dose". Two salts are signed for hypocalcaemia after massive transfusion: calcium chloride 1 g and calcium gluconate 3 g.

**Fix.** A turn that asks for calcium and names no salt is asked "Calcium chloride or calcium gluconate?" (step 2l-00), before the model.
- A calcium level is not a request: "ionized calcium is low", "check a calcium level" and "calcium 0.9" are not asked.
- The answer "chloride" or "gluconate" is read as "calcium chloride" or "calcium gluconate", in the history too, so later turns keep it.
- With no age, the next question is #181's "Adult patient?". After "adult", calcium chloride 1 g is built.

## 7. Brief tidy (ketamine[6], naloxone[2], moxifloxacin[0], propofol[0])

The tidy runs after the gate, on served answers only (`tidy_dose_lines`). Lines change shape or are dropped; no number is added that the check did not pass. In BRIEF and the dose sections:
- **A dose line that states a signed dose in another shape is replaced by that dose's own line.** "Shape" means one of three things:
  - a "Draw <mass>" line with no volume ("Draw 40 mg of propofol IV (40 mg)", "Draw 400 mg of moxifloxacin PO");
  - a NO VOLUME line beside a dose that has a volume (ketamine[6]);
  - a tablet asked for its concentration.

  Duplicate lines in a section collapse to one.
- **A BRIEF line with a dose range that is no signed rate goes.**

In other sections, a step's "Draw <mass>" becomes "Give <mass>".

**Tablets.** An oral dose of a drug with no signed liquid presentation renders "moxifloxacin PO: 400 mg. Indication: …". It has no NO VOLUME and no "confirm concentration", in the card and in what the generator is offered.

**naloxone[2]'s extra range now holds.** Live, qwen moved "0.001-0.015 mg/kg/dose" (another indication's range) from BRIEF to DO THIS on this branch's harness. The dose check read "mg/kg/dose" as neither a dose nor a rate. "/dose" and "per dose" are now doses, so the range holds as an unsigned naloxone dose. This adds holds only.

## 8. The infusion ruling: signed rates are allowed doses

**Fix.** `build_allowed_rates(query, ctx)` returns the signed rate entries for the drugs the question names. It narrows them the way the check narrows a bolus:
- population;
- stated route (rates are IV/IO);
- the stated indication (A32's accepted labels);
- A11b's rate categories;
- a child needs a weight, and an adult entry an adult (#181).

Three things use it:
- **The generator** is offered them under "ALLOWED_RATES — signed infusion rates. Give the rate EXACTLY as written; never as a bolus, and no mL/hr".
- **The validator** reads the same block.
- **The label check** (A1b) counts them as built, so "Indication: symptomatic bradycardia — infusion" is no longer held as a label for an indication that was not built.

The rate value check (A11/A11b) is unchanged. A32's form rule still holds a bolus for an infusion question.

Correct signed lines now serve, for example:
- "epinephrine IV: 0.02-0.2 mcg/kg/min. Indication: symptomatic bradycardia — infusion";
- propofol 10-75 mcg/kg/min sedation infusion;
- ketamine 0.5-2 mg/kg/hr;
- epinephrine 2-10 mcg/min refractory shock.

Three still hold:
- shock's 0.05-0.3 for a bradycardic patient;
- 0.5 mcg/kg/min;
- the 10 mcg push dose.

**Found in this PR's replay and closed: an unfilled dose template.** A logged answer (2026-10-27) read "Draw X mL of Y mg/mL propofol IV (Z mg). Indication: sedation.". That is the prompt's format line, copied unfilled. It had been held only by the label check, because propofol's sedation infusion was not built. With rates built, nothing held it. A dose line with the template's letters where its numbers go now holds: "The answer has an unfilled dose template (…), not a dose."

**Rows it releases: none.** In every replay row that asks for an infusion, the answer gives a bolus or a wrong rate, so they still hold. On the branch harness, qwen still wrote a bolus for all five infusion rows (epinephrine[5][6][8], propofol[1], ketamine[1]), and all five held. The ruling lets a correct signed line serve; qwen has not yet written one. Every unit test of a correct line passes.

## 9. Tests changed

- `test_pacing_match.py::test_e13_is_its_own_class` and `test_signing_batch3_rulings.py` (two pins): "procedural sedation" and "procedural / conscious sedation" are now the class "procedural sedation", not "sedation" (section 2).
- `test_sweep_pr1_wrong_numbers.py::test_the_2026_10_27_propofol_template_line_stays_held`: still held, now by the unfilled-template hold; the label check passes "sedation" once the sedation infusion is built (section 8).
- `test_b1_source_mode_labelling.py`: "only the SOURCE line may change" now compares against the tidied text. Its logged answer has "Draw 50 mcg fentanyl IV", which the tidy rewrites (section 7).
- `test_deterministic.py`: the pre-gate count word list takes 25 (the calcium ask is a new early return; docstrings say 25).
- `test_drug_contracts.py`: `build_allowed_rates` is classified as plumbing (`NOT_A_DOSE_CARD`).

No test that holds a dose was loosened.

## 10. Checked

**Suite:** 3,942 passed, 47 skipped, 3 xfailed.

**Replay** vs main b881d38 (#198 merged), the five sets:

| Set | Rows | Changed | Newly held | Newly released | Newly doses |
|---|---|---|---|---|---|
| served | 1,738 | 1 | 1 | 0 | 0 |
| held | 308 | 0 | 0 | 0 | 0 |
| gate | 1,408 | 0 | 0 | 0 | 0 |
| log | 4,996 | 10 | 2 | 2 | 2 |
| pipe | 847 | 3 | 0 | 0 | 0 |

The log set's two "newly released" rows are the `response` and `response_preview` fields of one log line (2026-10-30 line 14, atropine[3]). Both hold the text of the hold message, which quotes "atropine 4 mg … 8 mg … 16 mg". The replay re-checks that text, and the steps now pass. The model answer the hold replaced (`held_response`, with GIVE "Atropine IV: 16 mg") is still held. **No answer is released.**

Every moved row:

- served, newly held: H-IM-11, "femur fracture, screaming in pain, RR is 8, what analgesia do I give" (gpt-4o-mini, determinism run). Its GIVE line was "Draw X mL of Y mg/mL ketamine IV (Z mg). Indication: analgesia for femur fracture.", the unfilled template.
- log, newly held: 2026-10-30 line 105 (`response`, `response_preview`), naloxone[2]. The served answer's BRIEF had "0.001-0.015 mg/kg/dose" (section 7).
- log, still held, reason changed:
  - 2026-10-27 line 135: the "is for" list adds the refractory-shock infusion.
  - 2026-10-27 line 145: the propofol template line, now held as a template.
  - 2026-10-30 line 14 `held_response`: atropine, now held only for its GIVE 16 mg.
  - 2026-10-30 lines 23 and 30 (cefazolin, ceftriaxone): each adds an unfilled-template issue ("Draw X mL of 2 g/mL cefazolin", "Draw X mL of 2000 mg ceftriaxone").
  - 2026-10-30 line 42 (epinephrine, bradycardia): the "is for" list adds the refractory-shock infusion.
- pipe:
  - "calcium dose after 4 units" and "calcium dose after the transfusion" now ask the salt; before, they reached the generator with nothing offered.
  - "can I give intranasal fentanyl, what dose" now asks for a weight (the IN entry is 1 mcg/kg). Before, it asked "Adult patient?" with fentanyl IV 50 mcg queued, the wrong route.

**Newly dosing, for owner sign-off.** These are not in the replay (they asked before), but they serve once this merges:
- ketamine[18]: ketamine IN 40 mg (0.5 mg/kg, the low end of 0.5–0.75), 0.8 mL of the 50 mg/mL kit vial, deterministic card.
- midazolam[2]: the procedural-sedation entry reaches the generator. qwen served 1 mg IV (signed 1–4 mg).
- midazolam[7]: the peds IN procedural entry reaches the generator. qwen served 4 mg IN at 20 kg (0.2 mg/kg, signed 0.2–0.5 mg/kg).
- atropine[3]: the 2-4-8-16 mg escalation serves when the GIVE line gives 2 mg. qwen did so on the second harness run.
- T9 after the salt: calcium chloride 1 g or calcium gluconate 3 g, through the generator.

**Harness** on :8014, this branch, Offline mode: 29/29. The 16 PR 3 rows on qwen are in `replay-out/harness/sweep_rows.txt`:
- served: the procedural rows, ketamine IN, moxifloxacin (tidied, no concentration line) and atropine;
- held on qwen's own wrong numbers: T1 (340 mg for 453.6 mg), dextrose[0] (250 mg), ketamine[6] (40 mg), propofol[0] (an unfilled "(Z mg)") and the five infusion rows (boluses);
- naloxone[2] holds on the range;
- T9 asks the salt.

## 11. Found, not changed (for the owner)

- **A post-intubation dose passes for an agitated patient.** On this branch's harness, ketamine[6] ("20 kg 6 year old, combative, need dissociative sedation, ketamine IV") was once served SAFE with a BRIEF line "Post-intubation sedation: Draw 0.2 mL of 50mg/mL ketamine IV (10 mg)". The child was not intubated. "Dissociative sedation" states the sedation class through `sedat\w*`, so A32 accepts the post-intubation entries. Main b881d38 passes the same text, so this is not caused by PR 3. A fix would make "dissociative sedation" yield to agitation, like A32's generic words. It is its own item, for the owner to order.
- **qwen does not yet copy the signed rate.** On all five infusion rows the generator was offered ALLOWED_RATES and still wrote a bolus. It held, correctly. The builder still offers every bolus entry beside the rate (owner, #165 review: nothing is removed from the offer).
- **A unitless glucose under 10** is still read as mg/dL and not stored (section 1).
