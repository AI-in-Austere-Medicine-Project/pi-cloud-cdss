# Field feedback review — web client, 2026-07-18 → 2026-08-26

**Source:** `server/feedback.log`, 48 entries, all of them from the web client
(`server/static/index.html`). 26 `appropriate`, 22 `flagged` (17 significant,
5 minor, **0 dangerous**). 40 distinct `device_id` values across 48 entries.
**Nature of this document:** a read of what medics actually reported, grouped
into themes, with the mechanism named where it was verified in code. Nothing
below has been implemented. Themes are ranked by clinical consequence.

Entry numbers are 0-based line indices in `feedback.log`.

---

## 0. What the corpus can and cannot support

Four caveats, because they bound every claim here.

**48 entries is a small n, and the flag rate is not a quality metric.** Flagging
is voluntary and self-selecting; 22/48 flagged says nothing about the flag rate
across all traffic, only that 22 answers were bad enough for someone to stop and
type. Treat each entry as a bug report, not a data point.

**Nine entries cannot be reproduced.** `/feedback` stores the query, a
200-character response preview, and nothing else — no conversation history, no
patient context, no model, no validator result, no sources. Entries 29 (`Ok now
his pressure is getting soft 90/50`) and 43 (`90 kg`) are mid-conversation turns
whose meaning lives entirely in turns that were never captured. See §7.

**The issue-tag UI is barely used.** Only 7 of 22 flagged entries carry any
`issues` tag; the free-text `suggestion` box carries essentially all the signal.
The `comment` field is populated in **0 of 48** — the API accepts it and the
client has no UI for it.

**Nobody has ever used the "dangerous if followed" severity.** Worth stating as
the one clearly good result in the corpus, and worth not over-reading: entry 44
below arguably qualified and was filed as "significant".

---

## 1. The RSI bundle answers questions about patients who are already intubated

**Four reports. The single most repeated complaint in the corpus, and the one
with a verified mechanism.**

> **Entry 38** (08-22) — *"Standard ventilator rate for an RSI patient with a TBI
> he is 54 and 150 pounds"* → RSI induction/paralytic bundle.
> *"I asked for a ventilator rate and it's a mentioned in the comment that I just
> RSI a patient and it focused on the RSI and not the actual need."*

> **Entry 36** (08-22) — *"Patient is being ventilated at a rate of 12. He's
> already intubated"* → RSI bundle. *"Stated patient was already intubated, was
> requesting [vent] protocol... then it gave me RSI stuff."*

> **Entry 26** (08-20) — *"nine-year-old... traumatic brain injury and I have him
> intubated. Give me some further care steps"* → RSI bundle. *"I was wanting more
> like vent management or TBI management after the [intubation]."*

**Mechanism, verified.** `should_use_rsi_pregate()` (`openai_client.py:3838`) is
`is_rsi_or_post_intubation_context(text) and not is_vent_settings_query(text)`.
The S-4 diversion works, but `is_vent_settings_query`'s vocabulary
(`openai_client.py:3819`) does not contain **"ventilator rate"**, **"vent rate"**,
or **"being ventilated"**, while `is_rsi_or_post_intubation_context` matches the
bare substrings `"intubat"` and `"ventilator"`. Replaying the three queries above
through both functions:

| query | `is_vent_settings_query` | routed to RSI pre-gate |
|---|---|---|
| "Standard ventilator **rate** for an RSI patient…" | `False` | **yes** |
| "Patient is **being ventilated** at a rate of 12… already intubated" | `False` | **yes** |
| "…TBI and I **have him intubated**. Give me further care steps" | `False` | **yes** |
| "Ventilator **settings** for 75kg male in DKA" (F-12, fixed) | `True` | no |

**Two fixes, and the second is the real one.**

1. Widen `is_vent_settings_query` — `vent rate`, `ventilator rate`, `rate of \d+`,
   `being ventilated`, `minute ventilation`, `i:e`, `plateau`, `driving pressure`.
   Cheap, and closes entries 38 and 36 today.
2. **The vocabulary chase is the wrong shape of fix.** The medic is not saying a
   vent keyword; they are saying *the tube is already in*. What is missing is a
   past-tense/completed-airway detector — "already intubated", "have him
   intubated", "post RSI", "we RSI'd", "tube is in", "successfully RSI" (entry 0
   uses that phrasing too) — that suppresses the RSI pre-gate **regardless of
   what else the query asks for**, and routes to post-intubation management.
   Serving an induction-and-paralytic bundle for a patient who is already tubed
   is not merely unhelpful; it is a dose bundle for an indication that has passed.

**Also missing, once routing is fixed:** entries 0, 26 and 38 all wanted the same
thing — **post-intubation TBI management** (BP targets, sedation, vent targets,
EtCO2 goals). There is no card for it. Entry 0 asked for exactly this on 07-18
and got a safety block instead.

---

## 2. A beta-blocker overdose was answered as sepsis

**One report, and clinically the worst answer in the corpus.**

> **Entry 44** (08-23, significant) — *"I have a patient who overdosed on beta
> blockers. Vitals: HR 30, BP 50/20, SpO2 91%… IV access obtained"*
> → **"SEPSIS — Treat as suspected sepsis/septic shock… Give fluid bolus…"**
> *"Told it the patient had a BB OD. Talked about not giving blood and treating
> as sepsis… what?"*

The query names the toxidrome explicitly and carries the textbook vitals for it
(bradycardic, hypotensive). The answer is a different diagnosis with a different
treatment; nothing in it mentions glucagon, calcium, high-dose insulin, atropine
or pacing. **Related — entry 16** (07-22, *"6 year old, fever and altered"*) also
returned the sepsis card and was tagged *Contradicts current CPG*.

Two candidate mechanisms, and they need separating before anything is changed:

- **Retrieval.** Shock vitals + an out-of-corpus presentation may be pulling the
  sepsis chunks on similarity alone. This is F-5 (in-corpus questions served
  general knowledge) inverted — an out-of-corpus question served the nearest
  in-corpus protocol with full confidence.
- **The router.** Check whether `clinical_router` matches sepsis on the vitals
  pattern and appends its search terms, which is the F-6 failure class.

**Recommended:** replay entry 44 verbatim through the eval harness before
touching anything, and add it to the scenario bank either way. A named toxidrome
answered as a different shock state is the kind of failure the bank exists to
hold. Toxicology coverage more broadly — beta-blocker, CCB, TCA, opioid — is
worth a scoping question of its own: if it is out of corpus, the honest answer is
the general-reference banner, not the sepsis card.

---

## 3. The safety gate blocks legitimate field pharmacy

**Three reports, all significant, all the same root confusion: the gate reads a
*container* as a *dose*.**

> **Entry 21** (08-11) — *"Need to make a Ketamine drip at 500 mg of Ketamine and
> a 1 L bag with a 60 drop set"* → blocked: *"provider requested ketamine 500mg,
> which exceeds safety ceiling 108.8mg for 54.4kg patient."*
> *"I gave it the vial of ketamine I had in a bag and it flagged it for safety,
> but I'm obviously not giving 500 at a time. This is an IV drip."*

> **Entry 43** (08-23) — ketamine drip, weight given → held, *"then I asked again
> in a different context and it gave me [the drip], which is fine."*

> **Entry 35** (08-22) — RSI ketamine + rocuronium, 25M closed head injury →
> blocked: *"GIVE line doses 'ketamine' (15mg) with an empty ALLOWED_DOSES
> contract — no deterministic dose was authorised."*

**Three distinct defects behind one symptom.**

1. **No drip/infusion grammar.** "500 mg in a 1 L bag with a 60 gtt set" is a
   *concentration statement*, not a bolus request. `detect_requested_medication_overdose`
   has no concept of a diluted preparation, so every drip order reads as an
   overdose. This is the same detector already flagged as **DP-6** (ceilings from
   hardcoded multipliers, never reads `max_single_dose`) — worth fixing both in
   one pass, since both are that function reasoning about a number it has not
   fully parsed.
2. **A drip is a real austere-medicine need and is not served at all.** Dirty
   drips, drops-per-minute from a 60 gtt set, mg/kg/hr from a bag concentration —
   this is arithmetic the system is well suited to do deterministically, and the
   medic asked for it three times in two weeks.
3. **An empty contract produces a hard block.** Entry 35's failure is not a
   clinical judgement at all — it is a bank gap surfacing to a medic mid-RSI as a
   safety hold. A missing contract should degrade to `SERVE_NO_DOSE` with an
   explicit "no signed dose for this — use local protocol", never a block that
   reads as *your request was dangerous*. Same family as SC-7.

**Cross-cutting:** every hold in this corpus renders as the same opaque
"Clinical safety hold. This response was blocked." Entry 43's medic got a hold,
rephrased, and got a clean answer — which means the hold was noise and they
learned to route around it. **A gate a user learns to bypass is worse than no
gate**, and that is the strongest argument in this corpus for making hold text
say *what would make the request answerable*.

---

## 4. Content that exists but will not come out; content that does not exist

> **Entry 46** (08-25) — *"Give me the fio2 table"* → *"I cannot provide the FiO2
> table. Please refer to your local protocol."*

The ARDSNet PEEP/FiO2 ladder is referenced in `vent_cards.json` — but only as
English prose inside card fields (*"climb PEEP/FiO2 ladder together"*), never as
a servable table. The system is describing a table it cannot render.
`is_vent_settings_query("give me the fio2 table")` returns `True`, so routing is
fine; the object is missing. **Either author the ladder as a card and serve it,
or make the refusal honest** ("the ladder is not in the on-device corpus").

> **Entry 41** (08-23) — *"need adenosine dose"* → SVT card, vagal manoeuvres,
> no dose. *"wont give adenosine dose"*

**Verified:** adenosine appears in `drug_contracts.json` **zero** times. It exists
in the codebase only in never-give/contraindication lists
(`openai_client.py:1921`, `:2808`, `:4009`) and in the WPW warning. So the system
knows when adenosine is dangerous and does not know what it is. For a card that
already names vagal manoeuvres as step 1, the 6/12 mg sequence is the obvious
next step and is absent. **Adenosine belongs in the contract bank.**

> **Entry 22** (08-11) — *"amiorderone"* → *"No protocol retrieved — use local
> protocol."*

A misspelled drug name — under stress, on a phone keyboard, one-handed — returns
nothing. `query_aliases.json` exists; it needs fuzzy/edit-distance matching on
drug names, not just exact aliases. This class will recur constantly in the field
and is cheap to close.

> **Entry 1** (07-18) — *"I need ventilator settings for a DKA patient"* →
> *"AUSTERE-CDS handles medical queries only."*

The known F-2 / **Q-1** failure — the non-medical refusal fired at a clinical
question. Still the #1 complaint class by the v4.1 audit's own count, and still
open. This entry is now covered by the F-12 fix; **Q-1 is not closed** and the
generator can still emit this refusal.

---

## 5. Patient context: captured wrong, held too tightly, re-asked anyway

> **Entry 30** (08-21) — *"Help with the calculation to start norepi"* → *"What is
> the confirmed weight of the patient?"*
> *"It keeps asking me to confirm the weight, even when it shows the weight on
> there."*

The weight is displayed in the patient-context strip and the dose gate asks for
it anyway. Either the gate is not reading `confirmed_weight_kg`, or the weight is
held at a lower confidence than the UI implies (the F-1 hedged-weight fix
correctly demotes hedged weights — but then **the strip must show that demotion**,
or the UI is lying about state the medic is being asked to re-supply). Check
which before fixing: this could be F-1 working as designed with an honest-UI bug
sitting on top of it.

> **Entry 36** (08-22) — *"gave the wrong weight and it saved it, so might need to
> be able to redo weight… maybe reconfirm if it's over a certain amount."*

**There is no correction path for a captured vital.** A mis-parsed weight is
sticky for the rest of the session. The medic proposed the fix themselves:
re-confirm implausible values. Related to the open vitals items (staleness
displayed but not enforced; no structured vitals entry).

> **Entry 32** (08-22) — *"his saturation on pulse ox is about 91%"* → *"Couldn't
> read that vital: 'pulse ox is about 91'."* *"Are you [allergic to] slang for
> the pulse ox at 91%?"*

"Pulse ox" is not slang; it is what the device is called. The parser wants "SpO2".
This entry is a good specimen for the vitals-phrasing bank generally — the same
turn also carried "cap is rising about 80" (EtCO2), and the answer additionally
fell to the general-reference banner for a COPD patient in extremis.

---

## 6. Register: right facts, wrong altitude

Three entries where the content was defensible and the *shape* was not — the F-7
family (reference-card register used for a bedside emergency).

> **Entry 47** (08-26, *Missing critical step*) — *"Help me do a cric"* → *"1.
> Declare CICO. 2. Perform surgical airway / cricothyrotomy now."*
> *"This just tells a user to do a cric… it should be the classic scalpel, finger,
> bougie, tube."*

The sharpest example in the corpus. "Help me do a cric" is a request for a
**procedure walkthrough**; the answer restated the indication and then said to do
the thing. Procedural queries ("help me do", "walk me through", "how do I") need
a distinct register: numbered physical steps, landmarks, equipment, failure
points. Worth checking how many other procedures have the same hole.

> **Entry 12** (07-20, *Too vague*) — Tanzania, explosive diarrhoea + fever +
> fatigue → a definitional card. The medic wanted *"a very brief overview of the
> big overarching things of what it could be, and what to look out for — body
> substance isolation, etc."* Two gaps: **no differential-shaped answer**, and
> **no geographic/epidemiological awareness** despite the query naming the
> country. Cholera and typhoid are the point of that question.

> **Entry 29** (08-21) — *"his pressure is getting soft 90/50"* → fluids, control
> bleeding, "consider starting a pressor". *"Should it suggest push-dose
> pressors? Not sure if it's in the protocols."*
> Push-dose epinephrine **is** in the bank (DP-3 fixed it at a signed 10–20 mcg).
> The answer said "consider a pressor" without naming the one it can dose. When a
> signed contract exists for the drug the answer is gesturing at, name it.

---

## 7. What the feedback instrument itself needs

The corpus is thinner than it should be because of how it is collected. All of
this is in `server/main.py:214` and `server/static/index.html`.

- **`device_id` is not a device id.** `const deviceId = 'web-' + Math.random()…`
  (`static/index.html:238`) runs once per page load, so it identifies a tab, not
  a device or a session — hence 40 ids for 48 reports. Nothing groups a medic's
  reports together.
- **No session/turn linkage.** `/query` sends `conversation_history`; `/feedback`
  does not. Entries 29 and 43 are unusable as a result. Send a conversation id and
  turn index at minimum; the server already has the history.
- **The 200-char preview truncates mid-word** and is the only record of what was
  said. Already logged in `TODO.md`; every entry in §1–§3 above would have been
  faster to diagnose with the full text.
- **No answer metadata on the report.** Model, `validator_result`, `source_mode`,
  sources, latency are all known to the client at feedback time and none are sent.
  A flag saying "this was wrong" without recording whether it came from a
  deterministic pre-gate or the generator throws away the most useful bit.
- **Python `repr` on disk, not JSON.** `str(entry)` produces `'...'`-quoted lines
  that need `ast.literal_eval` and break on any unicode oddity. Already in
  `TODO.md`; do it with the linkage change.
- **Two free-text fields, one used.** Drop `comment` or give it a UI.
- **The tag list does not match what medics report.** 15 of 22 flagged entries
  skipped tags entirely. Every theme above would be better served by tags like
  *answered a different question*, *blocked something safe*, *dose missing*,
  *wrong register*. Consider deriving the next tag list from this corpus.
- **Entry 25 — "voice not working"**, filed as a clinical flag with query "test",
  because there is nowhere else to put it. A separate "something's broken"
  channel would keep the clinical log clinical.
- **Entry 19 — "Give better feedback on message — prompt user to change question
  style?"** The non-medical refusal is a dead end; it should say what a good
  query looks like.

---

## 8. Suggested ordering

Ranked by clinical consequence per unit of work, not by effort.

| # | Work | Why here |
|---|---|---|
| 1 | **Already-intubated detector** suppressing the RSI pre-gate (§1) | 4 reports; verified mechanism; serves a dose bundle for a passed indication |
| 2 | **Replay entry 44** (BB overdose → sepsis) through the harness, add to bank (§2) | Worst clinical answer in the corpus; mechanism unknown, so measure first |
| 3 | **Empty contract → `SERVE_NO_DOSE`, never a block** (§3.3) | A bank gap must not reach a medic as a safety accusation mid-RSI |
| 4 | **Hold text says what would make it answerable** (§3) | Entry 43 shows medics already route around opaque holds |
| 5 | **Drip/infusion grammar + DP-6 in one pass** (§3.1) | 3 reports; the detector is already open work |
| 6 | **Adenosine into the contract bank** (§4) | Verified absent; the SVT card already sets up the dose it won't give |
| 7 | **Feedback linkage: conversation id, full response, answer metadata, JSON** (§7) | Every future review depends on it; 9 entries already unusable |
| 8 | **Widen `is_vent_settings_query` vocabulary** (§1.1) | Trivial, closes 2 entries today, but do not mistake it for #1 |
| 9 | **Post-intubation TBI management card** (§1) | Asked for 3 times; does not exist |
| 10 | **Fuzzy drug-name matching** (§4) | "amiorderone" will recur every shift |
| 11 | **Procedural register for "help me do X"** (§6) | The cric answer is a real gap, breadth unknown |
| 12 | **Weight: correction path + re-confirm implausible values** (§5) | Medic-proposed; sticky bad state is worse than no state |

Items 1, 5, 6, 8 and 10 want regression tests built from the exact query strings
in this file — one fix, one commit, one test, per the existing convention.
