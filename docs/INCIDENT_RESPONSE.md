# EdgeCDSS incident response

Created 2026-10-25 at the owner's request (#181 review). The protocol comes first, then the incident log.

## 1. What an incident is

An incident is a served answer that is clinically wrong: someone acting on it as written would have given the wrong drug, dose, volume or route, or would have done or skipped a procedure wrongly.

- It counts as served when the medic saw it, even with a warning banner. A hold is not served.
- Test sessions count. The record says whether it was a test session or a real patient, and only the owner can say which.
- A wrong answer that was only found in a replay or a bench, and never served live, is a finding, not an incident. It goes to the work order.

## 2. Steps

1. **Contain.** Replay the row on current `main`. If it would still be served, fixing it comes before anything else.
2. **Record.** Add an `INC-nnn` entry to the log below. Fill in every field; write "unknown" where a fact is not known yet.
3. **Test session or real patient.** Ask the owner. If it was a real patient, the owner decides who is told (medical director, agency reporting), and the entry records who was told and when.
4. **Fix.** Follow the standing rules: one PR, the failing test committed first, a replay with the three counts (newly held, newly released, newly doses), and a stop for the owner's review. The fix PR names the incident.
5. **Close.** The entry is closed when the fix is merged and the replay shows every row of the incident held on `main`.

## 3. Record fields

| Field | What it holds |
|---|---|
| Date | When it was served (UTC), the session file and the row |
| Session | Test session or real patient; who confirmed it and when |
| Served | The answer as served, verbatim, with its source mode and validator verdict |
| Correct | What it should have been, and the size of the error |
| Cause | Why the system produced it, with the code at the time (commit) |
| Contributing | Anything that kept it from being caught earlier |
| Fixed by | PR(s), and what each one changed |
| Evidence | The replay rows showing it held now |
| Status | Open or closed |

## 4. Incident log

### INC-001: ketamine mL served for a 100 mg/mL vial when the kit stocks 50 mg/mL (2026-08-11)

- **Date:** 2026-08-11, `server/logs/sessions/cdss_session_2026-08-11.jsonl`, rows 4 and 6.
- **Session:** test session, no patient (owner, 2026-10-25). The session opens with "Test" and moves quickly through unrelated scenarios.
- **Served:**
  - **Row 4, 07:51:38 UTC.** "Have a patient burned 80% of body IV access need large amounts of Ketamine for pain 120 pounds" (75-year-old, 54.4 kg). Source mode `DETERMINISTIC_PRE_GATE`, validator SAFE, so it was served with no warning: "Draw 0.163 mL of 100mg/mL ketamine IV (16.3mg)".
  - **Row 6, 09:12:01 UTC.** "80kg male fx to tib fib, need pain meds IV is established". Source mode `JTS_GROUNDED`, validator NEEDS_HUMAN_REVIEW, so it was served with the human-review note appended. The validator's reason was wrong ("without confirmed weight for pediatric patient"). Served: "Draw 0.2 mL of 100mg/mL ketamine IV (20mg). Indication: pain control."
- **Correct:**
  - The kit stocks ketamine 500 mg / 10 mL (50 mg/mL). The owner signed that presentation on 2026-08-25.
  - Drawn from the real vial, each volume gives half the stated dose. Row 4 gives 8.15 mg instead of 16.3 mg; row 6 gives 10 mg instead of 20 mg.
  - Row 4's milligrams were also wrong: 16.3 mg is 0.3 mg/kg, and the signed dose at 54.4 kg is 0.25 mg/kg, 13.6 mg.
- **Cause:** the code at the time (v4.0, `dc471be`) assumed the kit held 100 mg/mL ketamine.
  - The generator's prompt listed "Ketamine: 100mg/mL" as the kit concentration (`server/openai_client.py:910` at `dc471be`).
  - The ketamine card computed its volume against 100 mg/mL (`:1610`, `:1643`).
  - Nothing in the system knew what was actually in the bag.
- **Contributing:**
  - Row 6 was approved in a replay sign-off. On 2026-10-14 the indication-only doses change released it in replay: its 20 mg matched the signed 0.25 mg/kg at 80 kg, and the owner approved the release (WORK_ORDER, signing batch 1). The sign-off judged the milligrams. The volume and the vial it assumed were not checked.
  - The validator's NEEDS_HUMAN_REVIEW reason on row 6 named the wrong problem, so the note did not point at the vial.
- **Fixed by:**
  - **#36, merged 2026-08-25** (the concentration master list, `server/drug_concentrations.json`). The kit inventory of record: the card gives no volume without a signed presentation. Ketamine is now set to always ask which vial (`confirm_required`), because the two common presentations differ five-fold. This did not stop a volume the model wrote itself: row 6 still passes on main.
  - **#181** (live log 2026-10-24; in review). No mL before the vial is confirmed. The dose check holds any answer stating a ketamine volume while the vial is unconfirmed, including a volume the model wrote itself, which is what row 6 was. The vial gate exists because of this class of error.
- **Evidence (#181, 2026-10-25):**
  - **Replayed** (the recorded answers through today's checks, live-log replay against main `6221981`):
    - Row 4 is held on main (16.3 mg is not the signed 13.6 mg). On #181 it is held on both the mg and the mL.
    - Row 6 passes on main and is held on #181: "The answer gives a ketamine volume in mL before the vial is confirmed." Its 20 mg is the signed dose.
  - **Asked fresh** (offline harness, :8012):
    - Row 4's question serves ketamine IV 13.6 mg with no volume until the vial is confirmed, then "Draw 0.272 mL of 50mg/mL ketamine IV (13.6 mg)". Correct in mg and mL.
    - Row 6's question is asked the pain severity; after "severe" it serves ketamine IV 20 mg with no volume, and still no volume after the vial answer. Correct in mg; no mL served (the analgesia card does not resume on this path, recorded in REFERENCE §9).
- **Status:** open until #181 is merged.
