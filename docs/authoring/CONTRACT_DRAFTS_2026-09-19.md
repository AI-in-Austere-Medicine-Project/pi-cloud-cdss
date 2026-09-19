# Contract drafts for owner review, 2026-09-19

This is follow-up (b) to #70. These are the signed contracts the free-text dose check asks for. **Nothing here is signed.** Every entry is `signoff: false`, `reviewed_by: PENDING_CLINICAL_SIGNOFF`, and invisible to the serving path. The bank still serves 47 entries, as before. You sign.

This page is a reading guide. The canonical text is in `server/drug_contracts.json`: each entry carries its verbatim quotes and page references in `extraction_notes`, and the full entry is rendered in [`DRUG_CONTRACT_WORKSHEET.md`](DRUG_CONTRACT_WORKSHEET.md), which is regenerated from the file.

## How the citations were checked
- **Source documents:** every page is from the local corpus PDFs in `server/data/jts_protocols/`: SMOG CY24 and the JTS CPGs named below.
- **Page numbers:** every cited page was checked to print the same number as its PDF page. The number in a citation is the one you will see on the page.
- **Quotes:** every quoted passage in an entry was matched word by word, in order, against the text of the pages that entry cites. On SMOG's two-column drug pages the columns interleave when extracted, so those quotes (pp.100, 114, 118, 132) were matched against the single column and read against the page by eye.
- **Two SMOG passages must never be cited:**
  - **SMOG p.118, fentanyl, PEDIATRIC column.** It reads "RSI: IV: 0.2-0.4 mg/kg over 30-60 seconds will produce rapid sedation lasting 10-15 minutes. Max dose: 20 mg … adrenal suppression". That is the **etomidate** monograph text, printed under fentanyl. As fentanyl it would be a 200-400× overdose.
  - **SMOG p.57, "Fentanyl 2-10 mcg/kg".** This is the Military Working Dog protocol.

## The drafts

| # | Drug, indication | Pop. | Route | Draft dose | Sources (page) | Your decision |
|---|---|---|---|---|---|---|
| 1 | Tranexamic acid, traumatic haemorrhage — loading dose | adult | IV | **2 g** single bolus | DCR ID18 p.9, p.2; SMOG p.158; TBI ID30 p.7; PCC ID91 p.28; ID40 p.2 | Sign as drafted. The sources agree. |
| 2 | Tranexamic acid, traumatic haemorrhage — maintenance infusion | adult | IV | (none) | DCR ID18 p.2; DCR-PFC ID73 p.2; PCC ID91 p.28 | **Retire it.** Current JTS favours the single 2 g bolus over 1 g + 1 g/8 h. It stays unsigned until you rule. |
| 3 | Tranexamic acid, traumatic haemorrhage | peds | IV | **15 mg/kg**, max 1 g | DCR-PFC ID73 p.12; SMOG p.158 | Rule the administration: over 10 min (ID73) or bolus within 1 min (SMOG). The dose agrees. |
| 4 | Fentanyl, acute pain — **JTS PFC fixed dose** | adult | IV | **50 mcg** (range 25-100) q30 min-2 h | PFC Analgesia ID61 p.8, p.10; Burn ID12 p.24 | **Conflict group `fentanyl-iv-adult-analgesia`: sign one of #4, #5, #6**, with an adjudication note. |
| 5 | Fentanyl, acute pain — **SMOG weight-based** | adult | IV | **0.5-1 mcg/kg** slow IV q30-60 min | SMOG p.118 | Same group. The engine serves the minimum of a range unless you rule the value. |
| 6 | Fentanyl, acute pain (existing NASEMSO draft) | adult | IV | **1 mcg/kg**, max 100 mcg initial | NASEMSO p.94 | Same group. It is the basis of the fentanyl IN entry you already signed. |
| 7 | Fentanyl, acute pain (existing NASEMSO draft) | peds | IV | 1 mcg/kg, max 100 mcg | NASEMSO p.94 | **No JTS source exists** for a paediatric IV dose, and SMOG's column is the misprint. Proposed basis: an owner declaration on this NASEMSO value. |
| 8 | Epinephrine, cardiac arrest | adult | IV | **1 mg** (10 mL of 0.1 mg/mL) q3-5 min | SMOG p.114, p.42; Drowning ID64 p.8; NASEMSO p.118 | Sign. Also rule on the hypothermia caution (below). |
| 9 | Epinephrine, cardiac arrest | peds | IV | **0.01 mg/kg**, max 1 mg, q3-5 min | SMOG p.114; Drowning ID64 p.8; NASEMSO p.121 | Sign. NASEMSO's 0.1 mg/kg (10×) stays recorded as `SUSPECTED_SOURCE_ERROR` and is not the dose. |
| 10 | Dextrose, symptomatic hypoglycaemia — alert patient | adult | **PO** (new) | **4-20 g** single dose | SMOG p.105, p.34 | **Rule the value.** The engine serves the minimum, 4 g, which is small for symptomatic hypoglycaemia. Alert, swallowing patients only (serve caution). |
| 11 | Dextrose, same | peds | **PO** (new) | 4-20 g | SMOG p.105, p.34 | Same. SMOG gives the same oral dose for children. |
| 12 | Dextrose, neonatal hypoglycaemia | peds | IV | **0.5 g/kg** (5 mL/kg D10), max 25 g | SMOG p.105; NASEMSO p.85-86 | **Conflict:** SMOG 5 mL/kg D10 (0.5 g/kg) vs NASEMSO 2 mL/kg (0.2 g/kg). |
| 13 | Atropine, symptomatic bradycardia | adult | IV | **1 mg** q3-5 min, max total 3 mg | SMOG p.100, p.41 | Sign. **Atropine is new to the bank.** |
| 14 | Atropine, symptomatic bradycardia | peds | IV | **0.02 mg/kg**, max single 0.5 mg, max total 1 mg | SMOG p.100 | **Engine gap:** SMOG's 0.1 mg *minimum* dose is only a serve caution. Below 5 kg the computed dose is under it (`NEEDS_MINIMUM_DOSE_SUPPORT`). |
| 15 | Atropine, nerve agent or organophosphate — autoinjector | adult | IM | **2 mg** (AtroPen); severe: three in rapid succession | SMOG p.100; CBRN Part 2 ID69 p.10 | Sign. |
| 16 | Atropine, nerve agent — escalating IV/IO bolus | adult | IV | **2 mg** first bolus, then 4, 8, 16 mg q3-5 min | CBRN Part 2 ID69 p.28; SMOG p.100 | The engine serves one number, the first bolus. The card says each later bolus doubles. |
| 17 | Atropine, organophosphate or carbamate | peds | IV | **0.05-0.1 mg/kg**, double if no atropinization | SMOG p.100 | Rule the value within the range. |
| 18 | Levetiracetam, severe TBI — seizure prophylaxis, loading dose | adult | IV | **1500 mg** over 15 min, then 1000 mg q12h | TBI ID30 p.10, p.7; TBI-PFC ID63 p.21, p.1; SMOG p.132, p.26; PCC ID91 p.29 | Sign. Four sources agree. PCC (2021, the oldest) says 1 g; ID63's Apr 2024 rapid update moved it to 1500. |
| 19 | Levetiracetam, status epilepticus | adult | IV | **2000 mg** over 15 min | SMOG p.132, p.37 | **Conflict within SMOG:** p.132 gives 2000 mg, the seizure algorithm on p.37 gives 1500 mg. No JTS CPG doses status. |
| 20 | Levetiracetam, status epilepticus, refractory | peds | IV | **60 mg/kg**, max 4500 mg, single dose | SMOG p.132, p.37 | Sign. "Limited data available" is a serve caution. |

Already signed and unchanged: dextrose IV adult 25 g and peds 0.5-1 g/kg (NASEMSO). SMOG p.105 corroborates both (adult 10-25 g; children 2 mL/kg D25 = 0.5 g/kg, max 25 g).

## Rulings needed beyond the doses
- **Hypothermic arrest (#8, #9).**
  - JTS Drowning ID64 p.8: "Withhold ACLS medications until temperature >30°C (86°F)." It is written for drowning.
  - The drafts carry it as a serve caution marked "owner to rule". Decide whether it applies to every hypothermic arrest; the #70 local benchmark's G-TYP-07 was one.
- **Indication names (#4, #5).** The source suffix exists only so the signing tool's selector is unique across the conflict group. After you sign one, rename it back to `acute pain / analgesia` and retire the other two.
- **Tiering.** Every provenance and conflict note is in `extraction_notes`, so the worksheet shows it and a medic does not. Every caution on an entry is serve-tier, except the standard "states no maximum" sentences. Check the serve budget on each entry you sign: `test_the_serve_tier_stays_within_budget` runs on servable entries only.

## How to sign
Conflict entries (#4-#6) need an `adjudication` note written into the entry first. The fence refuses to serve a `SOURCE_CONFLICT` entry without one. Then:

```bash
cd server
python3 tools/set_contract.py --drug "tranexamic acid" \
    --indication "traumatic haemorrhage — loading dose" --population adult --route IV \
    --sign --by <signer> --date <YYYY-MM-DD>
python3 tools/gen_drug_worksheet.py   # the worksheet follows the file
```

`python3 tools/set_contract.py --list --drug atropine` prints every selector for a drug.
