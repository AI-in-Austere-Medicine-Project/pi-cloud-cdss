# Kit declarations

Each declaration that a vial strength is in this kit: what a millilitre is computed from. The kit file itself (`server/drug_concentrations.json`) is deployment state and is not committed. This record is.

Each drug set has its own kit (owner, 2026-11-12). Rows whose reason says **EMS kit** are the EMS set's (`server/drug_concentrations_ems.json`, also deployment state); every other row is the PFC kit's.

`tools/set_concentration.py` appends a row on every `--sign` and `--single`. It does not append a row it already holds. Revocations are in the kit's change log (`drug_concentrations.log.jsonl`), not here.

Signer is the person, then the role the serving fence honours (`clinician` or `AI-AIM`).

## Signed before this record began

From the live kit file, read 2026-10-28. Each was signed by role `AI-AIM` on 2026-08-25; the change log on the device holds the detail.

| Drug | Strength | Vial | Signed by | Date |
|---|---|---|---|---|
| ketamine | 50 mg/mL | 500 mg / 10 mL vial | AI-AIM | 2026-08-25 |
| succinylcholine | 50 mg/mL | 100 mg / 2 mL ampoule | AI-AIM | 2026-08-25 |
| rocuronium | 10 mg/mL | 100 mg / 10 mL vial | AI-AIM | 2026-08-25 |
| lorazepam | 2 mg/mL | 4 mg / 2 mL ampoule | AI-AIM | 2026-08-25 |
| tranexamic acid | 100 mg/mL | 1000 mg / 10 mL ampoule | AI-AIM | 2026-08-25 |
| naloxone | 0.4 mg/mL | 0.4 mg / 1 mL ampoule | AI-AIM | 2026-08-25 |

## Declarations

| Date | Drug | Strength | Vial | Declaration | Signer | Reason |
|---|---|---|---|---|---|---|
| 2026-10-28 | ketamine | 50 mg/mL | 500 mg / 10 mL vial | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-10-28: ketamine 500 mg / 10 mL (50 mg/mL) is the kit's single ketamine vial (K1) |
| 2026-10-28 | ketamine | 5 mg/mL | 1 mL of 50 mg/mL in 9 mL normal saline | push dilution, adult IV analgesia only (any kit-vial volume under 0.5 mL is drawn from it); in `drug_contracts.json`, not the kit file | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-10-28 (#195 ruling 1): adult IV ketamine dilution, 1 mL of 50 mg/mL in 9 mL NS = 5 mg/mL, for IV analgesia only; 75 kg gives 3.75 mL of 5 mg/mL (K3) |
| 2026-11-12 | acetaminophen | 10 mg/mL | 1 g / 100 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Acetaminophen, MD 26-01) |
| 2026-11-12 | albuterol | 0.833333 mg/mL | 2.5 mg / 3 mL nebule | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Albuterol, MD 24-15) |
| 2026-11-12 | amiodarone | 50 mg/mL | 50 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Amiodarone, MD 24-15) |
| 2026-11-12 | atropine | 0.4 mg/mL | 0.4 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Atropine, MD 24-15) |
| 2026-11-12 | dexamethasone | 10 mg/mL | 10 mg / 1 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Dexamethasone, MD 24-15) |
| 2026-11-12 | dextrose | 100 mg/mL | D10W 25 g / 250 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Dextrose (D10W), MD 24-15) |
| 2026-11-12 | diltiazem | 5 mg/mL | 5 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Diltiazem, MD 24-15) |
| 2026-11-12 | droperidol | 2.5 mg/mL | 2.5 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Droperidol, MD 26-01) |
| 2026-11-12 | epinephrine | 1 mg/mL | 1 mg / 1 mL (1:1,000) | signed | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Epinephrine, MD 26-01) |
| 2026-11-12 | fentanyl | 0.05 mg/mL | 50 mcg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Fentanyl, MD 24-15) |
| 2026-11-12 | glucagon | 1 mg/mL | 1 mg / 1 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Glucagon, MD 24-15) |
| 2026-11-12 | hydroxocobalamin | 25 mg/mL | 5 g / 200 mL (reconstituted) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Hydroxocobalamin, MD 24-15) |
| 2026-11-12 | ketamine | 100 mg/mL | 100 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Ketamine, MD 25-02) |
| 2026-11-12 | lidocaine | 20 mg/mL | 20 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Lidocaine, MD 24-15) |
| 2026-11-12 | midazolam | 5 mg/mL | 5 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Midazolam, MD 24-15) |
| 2026-11-12 | norepinephrine | 1 mg/mL | 4 mg / 4 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Norepinephrine, MD 26-01) |
| 2026-11-12 | ondansetron | 2 mg/mL | 2 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Ondansetron, MD 24-15) |
| 2026-11-12 | rocuronium | 10 mg/mL | 10 mg/mL (vial size not stated) | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Rocuronium Bromide, MD 24-15) |
| 2026-11-12 | tranexamic acid | 100 mg/mL | 1 g / 10 mL | single vial (no vial question) | Andrew Azelton (clinician) | Owner declaration, Andrew Azelton, 2026-11-12 (signing batch 4, ruling 4): EMS kit vial, as the formulary card states it (Tranexamic Acid, MD 24-15) |
