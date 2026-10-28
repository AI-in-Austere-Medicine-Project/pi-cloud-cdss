# K1: ketamine 500 mg / 10 mL as the kit's single vial (2026-10-28)

**Owner (2026-10-28):** "K1: sign ketamine 500 mg/10 mL (50 mg/mL) as the kit's single ketamine vial, owner declaration Andrew Azelton, dated. Failing test first: "ketamine for pain, 75 kg IV" with no vial stated serves mg and mL ("0.375 mL of 50 mg/mL, kit") without the vial question; a different concentration stated in the question still overrides it. Replay; list every row that newly serves an mL. PR, do not merge."

## 1. Where the signature lives

- `drug_concentrations.json` is deployment state. It is gitignored because it is a claim about one bag, so no PR can carry the signature.
- This PR carries the tool that makes the declaration, the override and the tests.
- The declaration was applied to this worktree's copy for the replay. **The live file is unchanged.** The owner runs, on the Jetson, after merging:

```
cd /home/andrew/pi-cloud-cdss/server
python3 tools/set_concentration.py --drug ketamine --single "500 mg / 10 mL vial" \
    --by clinician --date 2026-10-28 \
    --reason "Owner declaration, Andrew Azelton, 2026-10-28: ketamine 500 mg / 10 mL (50 mg/mL) is the kit's single ketamine vial (K1)"
sudo systemctl restart edgecdss.service
```

- `--by clinician` is the role the serving fence honours (`SIGNOFF_AUTHORS`). The name rides in `--reason`, which the change log keeps, as for every other signature.

## 2. What changed

**`set_concentration.py --single LABEL`** declares the kit's only vial for a drug:
- signs it;
- removes the drug's other presentations (ketamine's 200 mg / 20 mL, 10 mg/mL, which was declared and never signed);
- sets `confirm_required` false and drops the old `confirm_reason`;
- records `single_vial` {label_text, declaration, by, date} on the entry;
- logs `SINGLE_VIAL` with what it removed, the config hash and the snapshot.

It needs an authorised `--by`, a `--date` and the declaration in `--reason`, and it refuses a vial the kit does not declare.

**A different strength stated in the question overrides the kit vial.** `drug_concentrations.stated_strengths` reads the strengths a question states: "100 mg/mL", "10 mg per mL", "200 mg / 20 mL", "500 mg in 5 mL". As in `match_confirmation`, a separator is required, so "500 mg over 10 minutes" is not a vial.
- A stated strength that is no signed vial for the drugs that turn names (else the drugs under discussion) is recorded as that patient's vial.
- `resolve()` then finds it matches nothing signed and asks again. The answer is mg only, with the vial question, in that turn and later ones.
- The stated number is never used to compute a volume.
- This holds for every single-vial drug, not only ketamine. Rocuronium's 100 mg / 10 mL is the test case.

**Live evidence:** two live questions stated "500mg/50ml" (10 mg/mL).
- With K1 and without the override, they would have been served 0.375 mL of the kit's 50 mg/mL vial.
- The correct volume of that vial is 1.875 mL, so that would have been a fifth of the dose.
- With the override they get mg and the vial question.

**Not changed:**
- **The GIVE line:** it is the same as for the other single-vial kit drugs: "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg)". It states the concentration it used, which is the medic's catch-point. It does not add the word "kit"; the owner can ask for a label on every kit-vial line.
- **The mg doses.**
- **The other vials and the gates.**

## 3. Tests

`tests/test_k1_ketamine_single_vial.py`, committed failing first (12 failed).
- **With the K1 kit:**
  - "ketamine for pain, 75 kg IV" serves "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg)", with no vial question and no NO VOLUME.
  - Stating the kit vial serves the same volume.
  - "100 mg/mL", "10 mg/mL vial", "200 mg / 20 mL" and "500 mg / 5 mL" each withhold every mL, in the turn and in a later turn. The 0.1875 mL a 100 mg/mL vial would give never appears.
  - Rocuronium follows the same rule.
- **The tool:** declares, logs what it removed, and refuses without a signer, a date or the declaration, or for an undeclared vial.
- Suite: 3,761 passed, 0 failed.

## 4. Replay, main `058136a` against K1 (tree and kit)

| Set | Rows | Changed | Newly held | Newly released | Newly doses |
|---|---|---|---|---|---|
| served | 1,738 | 9 | 0 | 0 | 0 |
| held | 308 | 29 | 0 | 0 | 0 |
| gate | 1,408 | 0 (byte-identical) | 0 | 0 | 0 |
| log | 4,385 | 118 | 0 | **1** | 1 |
| pipe | 838 | 43 | 0 | 0 | 2 |

- **Changed rows that stay held:** the hold's wording changed, from "a ketamine volume in mL with no confirmed vial" to "a ketamine volume in mL that does not follow from the confirmed 50 mg/mL vial and the dose it states". Each is still held.
- **Newly released, for the owner's sign-off:** one row, `cdss_session_2026-10-25.jsonl:33`, live.
  - The question was "ketamine for pain, 75 kg IV, 500mg/10ml vial".
  - The logged answer was "Draw 0.375 mL of 50mg/mL ketamine IV (18.75 mg)" and "TLDR: 75kg patient: ketamine IV = 18.75mg = 0.375mL of 50mg/mL".
  - Main held it ("no confirmed vial"). With the kit's single 50 mg/mL vial it is right and is served. It is K1's own target answer, with the vial stated.
- **Newly serving an mL:** 38 pipe rows, listed below; plus the log row above.
  - All ketamine.
  - Every volume line checked: 103 draw and TLDR lines, each equal to the dose ÷ 50 at the syringe's precision.
  - The mg dose is unchanged from main in every row. No other drug's volume changed, and no row lost an mL.
  - In the stored sets (served, held, gate) a row can newly serve an mL only by being newly released, and none was.

| Origin | Question | Ketamine volume served (new) |
|---|---|---|
| bank:H-SESS-014 | 80kg male, blast injury to the leg, severe pain, IV access — what can I give? / Need RSI meds for a 100kg male with facial burns. Give me do… | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| bank:H-SESS-023 | have a 56kg patient with 3rd degree burns. I need to RSI. IV is established | Draw 2.24 mL of 50mg/mL ketamine IV (112 mg). Indication: RSI induction.; Draw 0.56 mL of 50mg/mL ketamine IV (28 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| bank:H-SESS-029 | Have a patient burned 80% of body IV access need large amounts of Ketamine for pain 120 pounds | Draw 0.272 mL of 50mg/mL ketamine IV (13.6 mg). Indication: moderate to severe pain / analgesia. |
| bank:H-IM-03 | RSI an 85kg male with a facial gunshot wound, walk me through the sequence | Draw 3.4 mL of 50mg/mL ketamine IV (170 mg). Indication: RSI induction.; Draw 0.85 mL of 50mg/mL ketamine IV (42.5 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| bank:G-TYP-03 | need to do an RSI, pt is a 90kg male, rocuronim and ketamin | Draw 3.6 mL of 50mg/mL ketamine IV (180 mg). Indication: RSI induction.; Draw 0.9 mL of 50mg/mL ketamine IV (45 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| run:H-SESS-014 | 80kg male, blast injury to the leg, severe pain, IV access — what can I give? / Need RSI meds for a 100kg male with facial burns. Give me do… | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| run:H-SESS-023 | have a 56kg patient with 3rd degree burns. I need to RSI. IV is established | Draw 2.24 mL of 50mg/mL ketamine IV (112 mg). Indication: RSI induction.; Draw 0.56 mL of 50mg/mL ketamine IV (28 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| run:H-SESS-029 | Have a patient burned 80% of body IV access need large amounts of Ketamine for pain 120 pounds | Draw 0.272 mL of 50mg/mL ketamine IV (13.6 mg). Indication: moderate to severe pain / analgesia. |
| run:H-IM-03 | RSI an 85kg male with a facial gunshot wound, walk me through the sequence | Draw 3.4 mL of 50mg/mL ketamine IV (170 mg). Indication: RSI induction.; Draw 0.85 mL of 50mg/mL ketamine IV (42.5 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| run:G-TYP-03 | need to do an RSI, pt is a 90kg male, rocuronim and ketamin | Draw 3.6 mL of 50mg/mL ketamine IV (180 mg). Indication: RSI induction.; Draw 0.9 mL of 50mg/mL ketamine IV (45 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | need to RSI a 50kg patient Iv established. Vitals: 80/40,HR 140, SpO2 89% | Draw 2 mL of 50mg/mL ketamine IV (100 mg). Indication: RSI induction.; Draw 0.5 mL of 50mg/mL ketamine IV (25 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | RSI an 80kg male trauma patient ketamine and rocuronium | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | RSI 70kg male ketamine rocuronium | Draw 2.8 mL of 50mg/mL ketamine IV (140 mg). Indication: RSI induction.; Draw 0.7 mL of 50mg/mL ketamine IV (35 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | RSI a TBI patient 80kg male | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | need to RSI a badly burned 70kg male | Draw 2.8 mL of 50mg/mL ketamine IV (140 mg). Indication: RSI induction.; Draw 0.7 mL of 50mg/mL ketamine IV (35 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | ketamine for pain 60kg IV | Draw 0.3 mL of 50mg/mL ketamine IV (15 mg). Indication: moderate to severe pain / analgesia. |
| live | have a 6 year old TBI I need to RSI. Will be giving Ketamine and Rocuronium. Have IV. Pt weighs 35kg. I will then also need a ketamine drip … | Draw 1.4 mL of 50mg/mL ketamine IV (70 mg). Indication: RSI induction.; Draw 0.35 mL of 50mg/mL ketamine IV (17.5 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | Need to RSI. Need ketamine and roc dosing 89kg IV | Draw 3.56 mL of 50mg/mL ketamine IV (178 mg). Indication: RSI induction.; Draw 0.89 mL of 50mg/mL ketamine IV (44.5 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | Patient’s weight is 90 kg IV is established looking for Ketamine for pain control | Draw 0.45 mL of 50mg/mL ketamine IV (22.5 mg). Indication: moderate to severe pain / analgesia. |
| live | Need to rsi a 75lb patient. IV established | Draw 1.36 mL of 50mg/mL ketamine IV (68 mg). Indication: RSI induction.; Draw 0.34 mL of 50mg/mL ketamine IV (17 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | 25 kg child, broken femur, ketamine IV for pain | Draw 0.1 mL of 50mg/mL ketamine IV (5 mg). Indication: moderate to severe pain / analgesia. |
| live | Have a patient burned 80% of body IV access need large amounts of Ketamine for pain 120 pounds | Draw 0.272 mL of 50mg/mL ketamine IV (13.6 mg). Indication: moderate to severe pain / analgesia. |
| live | 80kg RSI, succinylcholine dose | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | 80kg RSI, succinylcholine and ketamine | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | 80kg Sux RSI with ketamine IV | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | "80kg RSI, succinylcholine and ketamine" | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | need to RSI with ketamine and roc, 80kg IV | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | 80kg male, blast injury to the leg, severe pain, IV access — what can I give? / Need RSI meds for a 100kg male with facial burns. Give me do… | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | have a 56kg patient with 3rd degree burns. I need to RSI. IV is established | Draw 2.24 mL of 50mg/mL ketamine IV (112 mg). Indication: RSI induction.; Draw 0.56 mL of 50mg/mL ketamine IV (28 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | Need to give ketamine for pain IV 60kg | Draw 0.3 mL of 50mg/mL ketamine IV (15 mg). Indication: moderate to severe pain / analgesia. |
| live | need to RSI, 80kg, ketamine and roc | Draw 3.2 mL of 50mg/mL ketamine IV (160 mg). Indication: RSI induction.; Draw 0.8 mL of 50mg/mL ketamine IV (40 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | Need to rsi 60kg make IV established | Draw 2.4 mL of 50mg/mL ketamine IV (120 mg). Indication: RSI induction.; Draw 0.6 mL of 50mg/mL ketamine IV (30 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | Need to rsi a 45kg patient. have ketamine and roc, iv and IO established | Draw 1.8 mL of 50mg/mL ketamine IV (90 mg). Indication: RSI induction.; Draw 0.45 mL of 50mg/mL ketamine IV (22.5 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | need to RSI a 70kg male | Draw 2.8 mL of 50mg/mL ketamine IV (140 mg). Indication: RSI induction.; Draw 0.7 mL of 50mg/mL ketamine IV (35 mg). Indication: post-intubation sedation — repeated bolus (no infusion pump). |
| live | 6 year old, 20 kg, femur fracture, ketamine IV for pain | Draw 0.08 mL of 50mg/mL ketamine IV (4 mg). Indication: moderate to severe pain / analgesia. |
| live | 80kg patient ketamine for pain. IV | Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). Indication: moderate to severe pain / analgesia. |
| live | 80kg male IV pain with ketamine | Draw 0.4 mL of 50mg/mL ketamine IV (20 mg). Indication: moderate to severe pain / analgesia. |
| live | have a 6 year old in pain. need to give ketamine iV established weight is 45kg | Draw 0.18 mL of 50mg/mL ketamine IV (9 mg). Indication: moderate to severe pain / analgesia. |

The H-SESS-014 rows are one bank row that runs five questions together. Their mg (160 mg for "RSI meds for a 100kg male", from the first line's 80 kg) is main's, unchanged here.
