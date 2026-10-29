# K3: a kit-vial volume under 0.5 mL is drawn from the signed dilution (2026-10-28)

**Owner, 2026-10-28:** "After the ketamine --single declaration on the live kit, run_tests.sh is 27/29: "Ped IV ketamine correct dose" and "Ped 20kg IV ketamine: 4 mg, SMOG, dilution after the vial" fail on missing keyword 'IV: 5 mg' / 'IV: 4 mg'. Paste the full answer for both. If the mg is right and only the format moved, update the harness keywords. If a 0.1 mL / 0.08 mL volume is shown with no dilution instruction, the paediatric-dilution item comes off v1.1 and is fixed now, failing test first: for a kit-vial volume under 0.5 mL, the answer gives the signed dilution (ketamine 5 mg/mL: 1 mL of 50 mg/mL in 9 mL NS) and the volume from the diluted strength. PR, do not merge."

The number K3 is assigned here; the owner to confirm. This was v1.1 #5 (owner, 2026-10-25).

## 1. The two live answers (live service, live kit after the K1 declaration)

Both mg doses are right: 0.2 mg/kg × 25 kg = 5 mg and × 20 kg = 4 mg. The harness keyword moved because the vial now resolves: the line became a draw line. But the draw is 0.1 mL and 0.08 mL of undiluted 50 mg/mL. The 5 mg/mL recipe is only a caution; no line gives a volume of it. So both branches of the instruction applied: the keywords are updated and the dilution is fixed.

"Ped IV ketamine correct dose" (history: "need ketamine for a 6yo arm fx", "25kg"; question "ketamine IV for pain"):

```
**DO THIS**
1. Confirm monitoring and airway equipment ready.
2. Give ketamine by the IV route.
3. Reassess pain, airway, respirations q5min.

**GIVE**
- Draw 0.1 mL of 50mg/mL ketamine IV (5 mg) (kit vial). Indication: moderate to severe pain / analgesia.

**CONTRAINDICATIONS**
- ketamine — moderate to severe pain / analgesia: Hypersensitivity; Age < 3 months

**CAUTIONS**
- ketamine — moderate to severe pain / analgesia:
  - OWNER-DECLARED dilution for IV push (no guideline states one): 5 mg/mL — 1 mL of ketamine 50 mg/mL in 9 mL of normal saline.
  - 0.2 mg/kg equals 0.04 mL/kg of that dilution.
  - Avoid 0.5-0.9 mg/kg IV — emergence phenomena (SMOG: "feeling of unreality leading to agitation").
  - General-EBM alternate (dual-domain): NASEMSO gives 0.25 mg/kg IV/IO for all ages, max 25 mg initial / 100 mg cumulative (Pain Management, p.94).
- Ask **"why this dose?"** for the citations, the maxima, and anything held back from this list.

**WATCH**
- Airway, respirations, SpO2, mental status, and emergence reaction.

**DON'T**
- Do not redose without reassessment and local protocol.

**TLDR**
- PEDIATRIC PATIENT: ketamine IV = 5mg = 0.1mL of 50mg/mL (kit vial).

**SOURCE**: Signed dose contracts — each dose carries its own citation or owner declaration under CAUTIONS

Guideline-based support only. Not a substitute for clinical judgment.
```

Spoken: "Give ketamine, five milligrams, intravenously. Draw zero point one millilitres of ketamine, fifty milligrams per millilitre, from your kit. Watch: airway, respirations, oxygen saturation, mental status, and emergence reaction."

"Ped 20kg IV ketamine" ("6 year old, 20kg, arm fracture, ketamine IV for pain"): the same card, with

```
- Draw 0.08 mL of 50mg/mL ketamine IV (4 mg) (kit vial). Indication: moderate to severe pain / analgesia.
...
- PEDIATRIC PATIENT: ketamine IV = 4mg = 0.08mL of 50mg/mL (kit vial).
```

Spoken: "Give ketamine, four milligrams, intravenously. Draw zero point zero eight millilitres of ketamine, fifty milligrams per millilitre, from your kit. ..."

## 2. The fix

**Where it applies:** a volume from the kit's single vial (K1's "(kit vial)") under 0.5 mL, when the dose's own signed entry declares a `push_dilution` made from that vial. One signed entry declares one today: paediatric ketamine IV analgesia, 5 mg/mL = 1 mL of 50 mg/mL + 9 mL normal saline (AI-AIM, 2026-09-18). The volume is then the dose at 5 mg/mL.

The 20 kg child now gets:

```
**GIVE**
- Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg). Dilute first: 1 mL of 50mg/mL ketamine (kit vial) in 9 mL normal saline. Indication: moderate to severe pain / analgesia.
...
**TLDR**
- PEDIATRIC PATIENT: ketamine IV = 4mg = 0.8mL of 5mg/mL dilution (kit vial).
```

- **Brief:** "Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg) (0.2 mg/kg × 20 kg). Dilute first: 1 mL of 50mg/mL ketamine (kit vial) in 9 mL normal saline."
- **Spoken** (fixed templates): "Give ketamine, four milligrams, intravenously. Dilute one millilitre of ketamine, fifty milligrams per millilitre, from your kit, in nine millilitres of normal saline. Draw zero point eight millilitres of the dilution." A dilution line in any other shape is spoken "The dilution is on the screen.", never as the vial's strength.
- The 25 kg child: "Draw 1 mL of 5mg/mL ketamine dilution IV (5 mg)", the same recipe.

**What is unchanged:**
- **A dose with no signed dilution.** The adult 75 kg ketamine, 18.75 mg = 0.375 mL of 50 mg/mL (kit vial), is under 0.5 mL and keeps its vial volume: no adult dilution is signed. See section 5.
- **A vial the medic states.** The instruction says "kit-vial volume", so a stated vial keeps its vial volume. See section 5.
- **A kit that asks which vial.** No volume and no dilution until the vial is answered (owner, 2026-10-24).
- **0.5 mL and over** keeps the vial volume (24.5 mg diluted, 25 mg not).

**The checks** (no gate loosened; each is a test):
- **The volume audit** (`audit_volume_lines`) accepts a strength that is not a signed vial only when every one of these holds:
  - the line names the dilution;
  - a signed entry for that drug on that route declares a dilution at that strength;
  - the dilution is made from the vial the kit resolves to (none while the kit asks which vial);
  - the volume × strength = mg, exactly as for any line.

  "Draw 0.8 mL of 5mg/mL ketamine IV" (not named a dilution), the wrong volume, 10 mg/mL, and an IM dilution are each removed to mg.
- **The unconfirmed-volume check** accepts the signed recipe's own two volumes (1 mL and 9 mL) where the sentence states the vial strength it starts from. The card is code-made and is not read by this check, but the generator is offered the same line; repeated verbatim, it would otherwise hold on "9 mL". Your #181 rule covers it: "An mL serves when it comes from a confirmed vial OR from a signed entry's own recipe line". Any other recipe (2 mL in 8 mL, a 100 mg/mL start) or a volume that follows from nothing still holds, and so does any recipe while the kit asks which vial.

**Harness** (`run_tests.sh`): the two cases now look for the dilution draw line and the recipe.

## 3. Tests

`server/tests/test_k3_ped_ketamine_dilution.py`. The failing tests were committed first, in two commits: the card, TLDR, spoken brief, threshold and audit; then the recipe volumes. Two tests were added with the change: the brief keeps its per-kg basis, and a dilution line in another shape is never spoken as the vial.

**Suite:** 3,798 passed, 0 failed.

**Harness** against this branch on :8013, with the live kit (after the K1 declaration) and the local model: 29/29.

## 4. Replay

Main `979565b` (K1 merged) against this branch, both with the live kit after the K1 declaration (`replay-out/run_k3.sh`):

| Set | Rows | Changed | Newly held | Newly released | Newly dosing |
|---|---|---|---|---|---|
| served | 1,738 | 0 (byte-identical) | 0 | 0 | 0 |
| held | 308 | 0 (byte-identical) | 0 | 0 | 0 |
| gate | 1,408 | 0 (byte-identical) | 0 | 0 | 0 |
| log | 4,449 | 0 (byte-identical) | 0 | 0 | 0 |
| pipe | 838 | 3 | 0 | 0 | 0 |

The three changed pipe rows: each is a live paediatric ketamine IV analgesia question. The mg is unchanged, the vial volume becomes the dilution's, and nothing else in the row changes (verdict, boundary, allowed and source mode are the same):

| Question | Main | This branch |
|---|---|---|
| "25 kg child, broken femur, ketamine IV for pain" | 0.1 mL of 50 mg/mL (5 mg) | 1 mL of 5 mg/mL dilution (5 mg) + the recipe |
| "6 year old, 20 kg, femur fracture, ketamine IV for pain" | 0.08 mL of 50 mg/mL (4 mg) | 0.8 mL of 5 mg/mL dilution (4 mg) + the recipe |
| "have a 6 year old in pain. need to give ketamine iV established weight is 45kg" | 0.18 mL of 50 mg/mL (9 mg) | 1.8 mL of 5 mg/mL dilution (9 mg) + the recipe |

The TLDR of each changes the same way ("= 4mg = 0.8mL of 5mg/mL dilution (kit vial).").

## 5. For the owner (answered: #195 rulings, section 6)

1. **The adult 0.375 mL.** *(Ruling 1.)* "ketamine for pain, 75 kg IV" draws 0.375 mL of 50 mg/mL from the kit vial, under 0.5 mL. No adult dilution is signed, so it is unchanged. Declaring one (or extending the paediatric 5 mg/mL to adults) is a signing act.
2. **A stated vial.** *(Ruling 2.)* A medic who says "I have 500 mg / 10 mL" for the 20 kg child gets 0.08 mL of 50 mg/mL, as before: the instruction names kit-vial volumes. The same rule could apply to any resolved vial the dilution is made from.

## 6. #195 rulings (owner, 2026-10-28)

**Owner:** "K3 numbering confirmed. 1. Adult: same rule, any kit-vial volume under 0.5 mL gets the signed dilution. Sign the adult IV ketamine dilution as an owner declaration (Andrew Azelton, today): 1 mL of 50 mg/mL in 9 mL NS = 5 mg/mL, for IV analgesia only; so 75 kg gives 3.75 mL of 5 mg/mL. Failing test first; record in KIT_DECLARATIONS. 2. Medic-stated vial: the dilution applies whenever the volume is under 0.5 mL and the vial (kit or stated) is the one the signed dilution is made from; a stated 500 mg/10 mL for the 20 kg child gets 0.8 mL of 5 mg/mL. Failing test first. 3. The 08:50 process on :8012: identify it (ps -fp $(lsof -t -i :8012)) and stop it if it's yours; report what it was. Replay, suite, harness. Report."

**Ruling 1, the adult IV analgesia dilution** (failing tests first):
- **The declaration is recorded in `drug_contracts.json`.** Both adult IV analgesia entries now carry `push_dilution`: NASEMSO 0.25 mg/kg (adult|peds) and JTS ID61 0.1–0.2 mg/kg (adult, "background pain — low-dose analgesia"). The recipe is 5 mg/mL = 1 mL of 50 mg/mL + 9 mL normal saline. The fields are `declared_by` clinician, `declared_name` Andrew Azelton, `declared_on` 2026-10-28, plus the declaration text. No other ketamine entry or route has one; that is pinned by a test.
- **A row in `docs/authoring/KIT_DECLARATIONS.md`.** The dilution lives in the dose contract, not the kit file, so `set_concentration.py` does not write it; the row was added by hand.
- **Each adult entry's serve cautions** state the recipe and its mL/kg, as the paediatric entry does. This is required by the existing invariant that a declared dilution is stated in the words the medic reads:
  - "OWNER-DECLARED dilution for IV push (Andrew Azelton, 2026-10-28): 5 mg/mL — 1 mL of ketamine 50 mg/mL in 9 mL of normal saline."
  - "0.25 mg/kg equals 0.05 mL/kg of that dilution." (or "0.1 mg/kg … 0.02 mL/kg")

  Both fit the serve-tier budget (5 cautions, 500 characters). The first version was 514 characters on the 0.1–0.2 mg/kg entry, so I shortened my own lines rather than change the budget.
- **75 kg:** "Draw 3.75 mL of 5mg/mL ketamine dilution IV (18.75 mg). Dilute first: 1 mL of 50mg/mL ketamine (kit vial) in 9 mL normal saline."
- **100 kg and over:** 25 mg (NASEMSO's cap) is 0.5 mL, not under 0.5, and is drawn from the vial.

**Ruling 2, a stated vial** (failing tests first):
- **The rule:** the dilution applies to the resolved vial it is made from, the kit's or one the medic states. "(kit vial)" appears on the recipe only for the kit's vial.
- **The 20 kg child with "I have 500 mg / 10 mL":** "Draw 0.8 mL of 5mg/mL ketamine dilution IV (4 mg). Dilute first: 1 mL of 50mg/mL ketamine in 9 mL normal saline." Spoken: "… Dilute one millilitre of ketamine, fifty milligrams per millilitre, in nine millilitres of normal saline. Draw zero point eight millilitres of the dilution."
- **The same on a kit that asks which vial,** when the question answers it.
- **A stated vial the dilution is not made from keeps its volume:** a signed 10 mg/mL vial gives 0.4 mL.
- **The volume audit:** its confirmed-vial check now takes a signed dilution made from the confirmed vial at the dilution's strength. With a confirmed 10 mg/mL vial, a 5 mg/mL dilution line is still removed.

**Tests that pinned the old volumes**, updated to the rulings in their own commit:
- 20 mg (0.4 mL), 4 mg (0.08 mL), 18.75 mg (0.375 mL) and 22.25 mg (0.445 mL) at the vial are now the dilution's 4, 0.8, 3.75 and 4.45 mL.
- Two tests about arithmetic and the leading zero moved to 100–120 kg (25 mg = 0.5 mL at the vial), so they still test the vial line.
- "An adult is never told to dilute" (2026-09-18) is now "told only once the vial is confirmed".
- The adult 80 kg card baseline, with the kit asking which vial, gains "Volumes and any dilution: given once the vial is confirmed.": the new recipe waits for the vial, as the paediatric one does.

**Ruling 3, the :8012 process:**
- **What it was:** PID 2213160, `/home/andrew/pi-cloud-cdss/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8012`, started 2026-10-28 08:50 local (13:50 UTC), parent 1. It was mine: the S2 test server (`replay-out/s2/serve.sh`, this worktree's `s2-speech-drug-names` code, whisper on, local model, the demo token, logs under `replay-out/s2/logs`). `replay-out/s2/uvicorn.log` reads "Started server process [2213160]". I restarted it at 13:50 UTC for the S2 commit-2 Kokoro timing run and did not stop it afterwards.
- **Identifying it:** `lsof -t -i :8012` printed nothing here, and its `/proc` entries could not be read, so `ps -fp $(lsof …)` had no PID. `ss` showed the listener and `ps` the PID.
- **Stopped** with `kill 2213160`; :8012 is free.
- The K3 test servers on :8013 are stopped too.

**Suite:** 3,811 passed, 0 failed.

**Harness** against this branch on :8013, with the live kit and qwen2.5:3b: 29/29.

**Replay** (main 979565b's results from section 4, the same main tree and live kit, against this branch):

| Set | Rows | Changed | Newly held | Newly released | Newly dosing |
|---|---|---|---|---|---|
| served | 1,738 | 0 (byte-identical) | 0 | 0 | 0 |
| held | 308 | 0 (byte-identical) | 0 | 0 | 0 |
| gate | 1,408 | 0 (byte-identical) | 0 | 0 | 0 |
| log | 4,449 | 0 (byte-identical) | 0 | 0 | 0 |
| pipe | 839 (main 838) | 14 | 0 | 0 | 1 |

- **The extra pipe row is not a change made by this branch.** The pipe set reads the live session logs. "ketamine for pain, 75 kg IV" was asked live on 2026-10-28, after main's replay ran, so main's results don't have it. It is counted as newly dosing because it has no before. Here it serves 3.75 mL of the 5 mg/mL dilution (ruling 1); live main serves 0.375 mL of 50 mg/mL.
- **The other 13 changed rows** are all ketamine IV analgesia. In none does the mg change, and none changes verdict, boundary, allowed or source mode.

| Question | Main (at the vial) | This branch |
|---|---|---|
| "80kg patient ketamine for pain. IV" | 0.4 mL (20 mg) | 4 mL of the dilution |
| "80kg male IV pain with ketamine" | 0.4 mL (20 mg) | 4 mL |
| "Patient’s weight is 90 kg IV is established looking for Ketamine for pain control" | 0.45 mL (22.5 mg) | 4.5 mL |
| "ketamine for pain 60kg IV" | 0.3 mL (15 mg) | 3 mL |
| "Need to give ketamine for pain IV 60kg" | 0.3 mL (15 mg) | 3 mL |
| "… burned 80% … Ketamine for pain 120 pounds" (live, bank H-SESS-029, its run) | 0.272 mL (13.6 mg) | 2.72 mL (3 rows) |
| "ketamine for pain, 75 kg IV, 500mg/10ml vial" (a stated vial, ruling 2) | 0.375 mL (18.75 mg) | 3.75 mL, recipe without "(kit vial)" |
| "25 kg child, broken femur, ketamine IV for pain" | 0.1 mL (5 mg) | 1 mL (as in section 4) |
| "6 year old, 20 kg, femur fracture, ketamine IV for pain" | 0.08 mL (4 mg) | 0.8 mL (as in section 4) |
| "have a 6 year old in pain … weight is 45kg" | 0.18 mL (9 mg) | 1.8 mL (as in section 4) |
| "need to give ketamine for pain i have a 500mg/50ml vial. Iv established Patient is 75kg" | mg only (the unsigned 10 mg/mL withholds the volume, K1) | still mg only; its cautions add "Volumes and any dilution: given once the vial is confirmed." |

Each adult row also gains the two dilution caution lines. The list is in `replay-out/k3r_changed_rows.txt`.
