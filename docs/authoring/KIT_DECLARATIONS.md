# Kit declarations

Each declaration that a vial strength is in this kit: what a millilitre is computed from. The kit file itself (`server/drug_concentrations.json`) is deployment state and is not committed. This record is.

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
