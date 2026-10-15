# EdgeCDSS design principles

## Doctrine (owner, #164 review, 2026-10-15)

> The system warns conservatively at physiological boundaries, defers to the clinician on judgment calls, and always shows its reasoning. **Gates on physiology, advisories on judgment.**

The doctrine decides what a new rule may do.

**A physiological or contextual fact gates.**
- Examples: a recorded vital past a threshold, or an indication the medic stated.
- It holds an answer, or keeps a drug from being volunteered.
- It errs toward the warning.
- It never loosens to make an answer pass.

**A judgment call is the clinician's.**
- Examples: pain severity, or which indication applies to a named drug.
- The system asks rather than infers, and it never infers judgment from sparse vitals.
- It acts on the answer.
- When the vitals grossly contradict the answer, it shows a soft advisory: a visible note that never blocks, never changes the verdict and never changes the dose set.

**Every warning and question shows its reasoning.**
- A caution states the threshold that armed it ("RR < 10").
- A question states what each choice selects ("severe → ketamine dosing").
- A drug kept back says why ("fentanyl, morphine not offered: RR < 10").

## Where it applies today

| Rule | Kind | What it does |
|---|---|---|
| `respiratory_depressant_low_rr` (vitals_rules.json) | gate (physiology) | RR < 10 arms the caution for a respiratory depressant, and it is not volunteered in an indication-only offer. RR ≤ 8 is respiratory depression, inclusive (owner); < 10 already includes it. The sentence states its trigger. |
| Paediatric RR thresholds | gate (physiology) | Must come from an age-banded table, never the adult constant. No such table exists yet, so children keep the RR < 10 rule rather than lose it. |
| Pain severity (#164) | judgment, asked | A drugless pain question that declares no severity is asked mild / moderate / severe. Each choice has its criteria on one line and says what it selects. The choice selects the dose set. |
| Mild pain with RR ≤ 8, adults (#164) | advisory | A visible note. The selection stands and nothing is held. |
| Which indication (#165) | judgment, asked | A drug named with no indication, signed for more than one, is asked which. The answer orders the doses; the formulary removes none. |
| Indication-scoped check (#166) | gate (context) | Planned. After the medic answers, a served dose outside that indication's entries is held. |
