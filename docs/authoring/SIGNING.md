# Reviewing and signing a drug dose contract

This is the procedure for turning a draft dose entry into a signed one that EdgeCDSS serves. It is written for a signer who has not worked on this codebase before, including a signer from another program.

**What a signature means.** A signed entry is a dose the system gives to a medic as a number. Until an entry is signed, the system does not state a dose for that drug, indication, population and route: it holds the answer or refers the medic to local protocol. Signing makes you the person who said this number is safe to give.

**One entry at a time.** Every dose entry is signed on its own. You can sign one entry, leave the entry beside it unsigned, and ship. Nothing here requires signing a batch.

## Before you start

1. **Be on the signer list.** `SIGNOFF_AUTHORS` in `server/drug_contracts.py` lists the roles whose signatures the engine honours (today `clinician` and `AI-AIM`).
   - `--by` takes one of those roles. Your own name goes in `--reason`.
   - A new program adds its signer role with a reviewed pull request to that tuple. The program owner decides who is on it.
   - An entry signed by a role that is not on the list serves nothing. `set_contract.py --list` reports such signatures.
2. **Get the exact source editions.** Each source record in an entry has a `citation` (document, edition date, section, page) and a `url`.
   - `local:server/data/jts_protocols/...` files are the program's corpus. `server/data/` is not in git. Get the data pack from the Releases page (see [`docs/RECOVERY.md`](../RECOVERY.md)).
   - `scripts/fetch_jts_cpgs.sh` downloads the **current** JTS guidelines, which may be newer than the edition cited. Check that the file's date matches the date in the citation before you rely on it.
   - NASEMSO and WHO sources are fetched from the `url` in the source record.
3. **Tools.** The repo's Python environment, and `pdftotext` (poppler) for reading a page's text layer. Use a PDF viewer as well, to see the page as printed.

## 1. Read the entry

Every entry lives in `server/drug_contracts.json` under its drug. An entry is selected by drug, `indication`, `population` and `route`.

```bash
cd server
python3 tools/set_contract.py --list --drug atropine    # every entry, and whether it is signed, ready or blocked
```

[`DRUG_CONTRACT_WORKSHEET.md`](DRUG_CONTRACT_WORKSHEET.md) renders each entry with every field. It is generated from the JSON file, so it always matches it.

Your review packet for one entry has three parts:

| Part | Where it is |
|---|---|
| **The entry as drafted:** dose (`dose_range`, and `min_single`, `max_single`, `max_cumulative` where set), population and any age limits, route, contraindications, cautions, flags | the entry's fields |
| **The cited passages:** each quoted verbatim, with the document and page | `sources[]` for the document and page; the quotes in `extraction_notes` |
| **Every known conflict:** each with its source and page | `extraction_notes`, in lines headed `CONFLICT`; conflicting sources are also listed in `sources[]` |

Notes marked `CORRECTED <date>` record a citation that was wrong and has been fixed. Read them: they tell you which checks have already failed once.

## Citation convention

Every page reference, in a `sources[]` citation and in `extraction_notes`, follows one rule:

- **Cite the page number printed on the page.** That is the number a reader holding the document will look for.
- **When the PDF's own page index differs, add it in parentheses:** `p.37 (PDF p.42)`. When the two are the same, give the printed page alone: `p.105`.
- **A page that prints no number** is cited by its PDF page, marked as such: `PDF p.12`.
- **A range** follows the same rule at both ends: `p.85-86`.

Why: PDF viewers jump to the PDF index, while a printed copy or a colleague's reference uses the printed number. Giving both where they differ is how a reader gets to the same page either way. The WHO EML is the case in this corpus: its printed page is 5 lower than its PDF page throughout.

A citation that gives only the PDF page where the two differ is an error. Correct it, with a `CORRECTED <date>:` line in the notes, before you sign.

## 2. Check every citation yourself

Do not sign on the strength of the notes. For **each** source record:

1. **Open the cited page.** Following the [citation convention](#citation-convention), the page in a citation is the number **printed on the page**, with the PDF page in parentheses where it differs. Confirm the page prints the number cited.
2. **Read the quote against the page, word by word.**
   - A quote may leave text out only where it shows `…`.
   - `[sic]` marks a typo that is printed in the source and kept on purpose.
   - Any other difference is an error. Stop, and correct it before you sign (see step 3).
3. **On two-column pages, read the right column.** SMOG drug pages print ADULT and PEDIATRIC side by side. Text extraction interleaves them, so read the page as printed, or extract one column at a time.
4. **Confirm the passage supports the field it is cited for.** A page that names the drug but states no dose does not source a dose. Check the population (adult or paediatric), the route, the units and any maximum.

To read one page's text:

```bash
pdftotext -f 118 -l 118 -layout server/data/jts_protocols/SMOG_CY24_REVISION_FINAL.pdf -
```

**Known traps in the current corpus. Never cite these as a dose:**
- **SMOG CY24 p.118, fentanyl, PEDIATRIC column:** this is the etomidate monograph, printed under fentanyl. As fentanyl it would be a 200-400× overdose.
- **SMOG CY24 pp.57-63:** the Military Working Dog (canine) protocols.
- **SMOG CY24 p.53, newborn dextrose:** "D12.5 1/0ml/kg" is misprinted, so the volume cannot be read.
- **SMOG CY24 p.39, paediatric organophosphate atropine:** "0.02mg/" has its unit cut off.
- **NASEMSO v3.0 p.121, paediatric epinephrine:** "0.1 mg/kg" is 10 times the conventional arrest dose.

## 3. Look for conflicts the notes do not record

The notes list the conflicts the author found. Look for more before you sign:

- Search the corpus for the drug's name beside a dose unit (mg, mcg, g, mL, mg/kg). Include pages the entry does not cite: SMOG's treatment algorithms repeat doses from its drug pages, and JTS guidelines repeat each other.
- **A conflict** is a different dose, maximum, interval or rate for the **same indication, population and route**, or a version of any of these that is narrower.
- A dose for another indication is not a conflict. Note it if it could be confused with this one.
- Leave out the canine protocols.

**Record what you find before signing,** in its own pull request:
- Add a line to the entry's `extraction_notes` in this form: `CONFLICT (found <date>): <source> p.<n>: "<verbatim quote>". <what differs, and what needs ruling>.`
- Add the source to `sources[]` with its citation (page numbers per the [citation convention](#citation-convention)), tier, `source_class`, `url` and `retrieved_date`.
- Fix any citation error the same way, with a `CORRECTED <date>:` line that says what was wrong.
- Then regenerate the worksheet (step 6). Leave `signoff` false.

## 4. Rule

For each entry, decide one of these:
- **Sign as drafted.**
- **Change the value**, then sign it in a later pass once the change has been reviewed.
- **Leave it unsigned.**
- **Retire it.**

Rules that decide what you may sign:

- **Ranges.** When `dose_range` is a range, the engine serves its **minimum**. To serve a different value, set `min` and `max` to that value and say why in the notes.
- **Conflict groups.** Entries flagged `SOURCE_CONFLICT` share a `conflict_group`. Sign **one** of them.
  - First write an `adjudication` field on it: which source wins, and why.
  - The tool refuses to sign a `SOURCE_CONFLICT` entry without an adjudication.
- **Flags that block signing.** The engine refuses to serve an entry carrying any of these, and the tool refuses to sign it:
  - **`NEEDS_MINIMUM_DOSE_SUPPORT`:** the source states a minimum dose the entry does not carry. Add `min_single` (`{"value": …, "units": …}`) with the source's value, then remove the flag.
  - **`MIGRATED_UNSOURCED`:** the dose came from an older hardcoded value and no approved source states it. Find a tier 1 or tier 2 source for the number, or have it declared (see below).
  - **`SOURCE_CONFLICT`** without an `adjudication`.
  - A `NEEDS_MANUAL_ENTRY` or `PENDING_CLINICAL_SIGNOFF` value **anywhere** in the entry, including cautions, notes and source records.
- **Flags that inform** (for example `SUSPECTED_SOURCE_ERROR`) do not block. Read them: they say which source figure was deliberately not used.
- **No source states the dose.** Only the program owner can make the dose servable. They do it with an owner declaration: the `OWNER_DECLARED` flag plus an `owner_declaration` block (`basis`, `declared_by`, `declared_on`, `justification`, `declared_value`, `supporting_doctrine`). If the dose is later edited without re-declaring it, the entry stops serving.
- **Cautions.** Serve-tier cautions are shown to the medic with the dose; detail-tier ones are kept for the record. Keep serve-tier lines to what a medic must act on. The test `test_the_serve_tier_stays_within_budget` fails if a signed entry's serve-tier cautions are too many or too long.

## 5. Sign

```bash
cd server
python3 tools/set_contract.py --drug atropine --indication "symptomatic bradycardia" \
    --population adult --route IV \
    --sign --by clinician --date 2026-09-24 --reason "Jane Doe, MD: packet checked 2026-09-24"
```

What the tool does:
- **Refuses** (and writes nothing) if any rule in step 4 fails. The refusal says what to fix.
- Then checks the entry **as it would be written** against the engine's own serving gate. It can never sign something the engine would not serve.
- Sets `signoff`, `reviewed_by` and `review_date`, and drops the `-draft` suffix from the entry's `version`.
- Appends a line to `server/drug_contracts.log.jsonl` (or `$CDSS_CONTRACT_LOG`) with the dose, the citations, the signer and a hash of the file. **That log is not in git.** Copy the `SIGN` line into your pull request so the record travels with the change.

Signing by hand-editing the JSON also works. It skips the tool's refusals and its log line, though the engine still refuses to serve what step 4 forbids. Use the tool.

## 6. Check, and ship

```bash
cd server
python3 tools/gen_drug_worksheet.py      # regenerate the worksheet; the entry now reads ✅ LIVE
bash run_unit_tests.sh                   # the full suite must pass
```

Open a pull request containing `drug_contracts.json` and the regenerated worksheet. In the description, give:
- The entry's selector (drug, indication, population, route).
- Your role and name.
- The review packet, or a link to it.
- Your ruling, and the adjudication if there was a conflict.
- The `SIGN` log line.

The program owner merges.

**A signature does nothing until the server restarts.** The contract file is read once, at startup. The deploy (`deploy.sh` on the production host) pulls `main` and restarts the service. Afterwards, on the deployed checkout, `python3 tools/set_contract.py --list --drug <drug>` should show the entry signed.

## Withdrawing a signature

```bash
python3 tools/set_contract.py --drug atropine --indication "symptomatic bradycardia" \
    --population adult --route IV --unsign --reason "why"
```

`--unsign` needs no signer. Anyone who finds a dose wrong can pull it at once. The system then stops stating a dose for that drug and indication, which is safer than stating a wrong one. Ship it the same way: pull request, merge, deploy.

## Concentrations are signed separately

A dose in mg becomes a volume in mL only through a signed concentration. Concentrations are signed with `tools/set_concentration.py` in `server/drug_concentrations.json`, which is a per-deployment file and not in git. Each deployment signs the concentrations of the stock it actually carries.
