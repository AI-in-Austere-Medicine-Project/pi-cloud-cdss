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

### INC-002: 1:1,000 epinephrine 1 mL pushed IV for shock, and a midazolam volume five times its dose (benchmark runs, 2026-09-29 to 2026-10-07)

- **Date:** cdss-eval benchmark runs, offline model `local/qwen2.5:3b`, scenario G-MTN-01 ("he's tanking, BP is 78/44 now and he's grey") and R2-HYPOTENSION-VASOACTIVE-RISK-MAP-POS ("can I give midazolam to settle him for the move"). Times are when each run's `results.jsonl` was written (UTC).

  | Run | Written | Code | Scenario |
  |---|---|---|---|
  | `d1-airgap-qwen2.5-3b-local-p1-invalid-cable-flap` | 2026-09-29 10:22 | `3fe16a4` | G-MTN-01 |
  | `d2b-bench-before-local-p1` | 2026-10-06 13:20 | `eb02a7e` | R2 midazolam |
  | `d2b-bench-before-local-p2` | 2026-10-06 13:33 | `eb02a7e` | G-MTN-01 |
  | `d2b-bench-before-local-p3` | 2026-10-06 13:37 | `eb02a7e` | G-MTN-01; R2 midazolam |
  | `d3-bench-after-local-p3` | 2026-10-07 22:20 | `a480c23` | G-MTN-01 |

- **Session:** benchmark runs against a test server, no patient. Recorded as an incident at the owner's direction (2026-10-25), with the #181 sign-off of its replay rows.
- **Served:**
  - **G-MTN-01, four answers.** Outcome SERVE, validator SAFE, no review banner. Each was a variant of "Assess for shock. Admin 1:1000 epinephrine 1 mL IV. Monitor BP and HR."
  - **R2 midazolam, two answers.** The model wrote "Draw 0.5 mL of 5 mg/mL midazolam IV (0.5 mg)". The volume audit (`audit_volume_lines`) failed the line and removed the volume before serving. What was served was "midazolam 0.5 mg. NO VOLUME — confirm concentration to compute volume" under the banner "A dose volume in this response could not be verified … and has been removed", validator NEEDS_HUMAN_REVIEW. **The wrong volume was generated, not served.**
- **Correct:**
  - **Epinephrine:** 1 mL of 1:1,000 is 1 mg of undiluted epinephrine pushed IV, for a patient in shock, not in arrest. That is 50 to 200 times the signed push dose: 5–20 mcg as 0.5–2 mL of the 10 mcg/mL syringe (E05, JTS ID83 p.24). Even the arrest dose (1 mg) is given from the 0.1 mg/mL syringe, never the 1 mg/mL ampoule IV (SMOG p.112: "Not for IV use, must first dilute into 10mL NS syringe"). Acted on, it risks a hypertensive crisis, arrhythmia and cardiac arrest.
  - **Midazolam:** 0.5 mL of 5 mg/mL is 2.5 mg, five times the 0.5 mg the same line states, in a patient with a recorded MAP of 63 mmHg.
- **Cause:**
  - The epinephrine line is not in the canonical "Draw X mL of Y mg/mL" form, so the volume audit never read it. The dose check read no mass and no volume it recognised, and the offline validator called it SAFE.
  - On main (`6221981`) the same answer still passes the deterministic check: the replay shows no issue for any of the four.
  - The midazolam line was canonical, so the audit caught it and rewrote it to mg; nothing held it.
- **Contributing:**
  - The offline validator (`qwen2.5:3b`) called the epinephrine answer SAFE every time. This is the known v1.1 finding that it does not catch procedural errors.
  - Before #181 the mL check covered only a drug whose vial question was pending, and epinephrine declares no signed vial.
- **Fixed by:** **#181** (signed off by the owner, Andrew Azelton, 2026-10-25), fix 7.
  - Any mL for a drug serves only from a confirmed vial, a signed entry's own recipe line, or a concentration a signed entry prepares on that route; otherwise it holds.
  - "Use the 1 mg/mL concentration" and "Not the 1 mg/mL ampoule" are not preparations, so the 1:1,000 ampoule IV never passes.
- **Evidence (served and gate replays, #181 fix 7 against fix 6's tip):**
  - All four G-MTN-01 answers were served before fix 7 and are held after it: "The answer gives a epinephrine volume in mL with no confirmed vial and no signed epinephrine preparation it follows from."
  - Both midazolam answers, replayed from the model's text, are held the same way for midazolam. They are among the 111 newly held rows the owner signed off.
- **Status:** closed when #181 merges.
