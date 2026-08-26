# Finding identifiers — a legend

Five prefixes are in use across this project's reports, and they come from
different instruments. This file says what each one means, where its canonical
list lives, and what states a finding can be in. It is a legend, not a history:
the findings themselves live in the documents named below.

## States

Every finding is in one of four states, whichever prefix it carries.

| State | Meaning |
|---|---|
| **open** | Recorded, not yet addressed. |
| **fixed** | A change has landed that is intended to close it. |
| **verified** | Closed *and* re-measured by the instrument that raised it — a re-run of the eval harness, a regression test built from the log line that exposed it, or a re-audit. |
| **withdrawn** | The finding was wrong. Withdrawn in place, with the reasoning, rather than deleted. |

**fixed is not verified.** A finding raised by measurement is closed by
measurement; anything else is a claim about a fix rather than a fact about the
system.

---

## `F-` — evaluation harness findings

**What it means.** A finding raised by the standing eval harness, which replays
scenarios against a pinned server snapshot and scores the results. `F-` findings
are behavioural and measured: each one carries a number before and, once fixed,
a number after.

**Canonical list.** `findings.md` in the eval repository (`cdss-eval`), with the
deltas between runs in `DELTA.md`. Closed ones are also written up in
`CHANGELOG.md` under the release that closed them.

**Current set.** F-1 hedged weights promoted to confirmed and dosed on · F-2
clinical questions answered with the non-medical refusal · F-3 oral glucose
recommended in altered mental status · F-4 a newer vital not displacing an older
one · F-5 retrieval delivering general knowledge for in-corpus questions · F-6
the router appending the wrong protocol's search terms on a substring match ·
F-7 the reference-card register used for bedside emergencies · F-8 the
human-review banner firing on most answers · F-9 boundary-reset notices with
nothing to reset · F-10 a dose proposed in the query neither confirmed nor
corrected · F-11 vitals cautions never firing across 160 turns · F-12 no vent
settings returned for DKA.

**Open as of 4.3.0:** F-5, F-10, F-11. The rest are fixed and verified by the
round-1 re-run.

---

## `S-` — safety observations from the v4.1 clinical audit

**Not a one-off.** S-7 (three different TBI SBP targets) is one of **nine**,
S-1 through S-9. The prefix denotes an observation surfaced for the owner's
*clinical* review rather than adjudicated by the audit — the audit states what
the system did and why, mechanically, and the clinical call is the owner's.

**Canonical list.** `AUDIT_v4.1.md` §2, in the private audit repository.

**Three sibling prefixes come from the same audit's remediation plan**
(`PLAN_v4.1.md`), and are work items rather than findings:

| Prefix | Meaning |
|---|---|
| `SC-` | Safety-critical work item (SC-1 … SC-11) |
| `Q-` | Quality work item (Q-1 … Q-11) |
| `T-` | Observability / telemetry work item (T-1, T-2, T-13) |
| `P-` | Prerequisite (P-0, the offline test suite) |

A work item usually cites the finding it answers — `Q-2` closes `S-4`, `Q-3`
closes `F-2` — which is why both kinds of identifier appear in commit messages.

---

## `AE-` / `H-` / `M-` / `L-` — security audit findings

**What they mean.** Severity bands from the v4.2 security audit:

| Prefix | Band |
|---|---|
| `AE-` | Actively exploitable |
| `H-` | High |
| `M-` | Medium |
| `L-` | Low |

**Canonical list.** The security audit document, which lives in the **private
audit repository and is deliberately not in this repository.** It is a live
vulnerability map — evidence, blast radius, and reproduction for each finding —
and publishing it would hand a reader the exploit alongside the fix.

**What may be said publicly:** a finding that is **closed** may be described in
`CHANGELOG.md`, with its mechanism, because the description of a closed hole is
a description of a fix. AE-1, AE-3, AE-4 and H-1 are recorded that way in the
4.3.0 entry. **Findings that are still open are not enumerated in this
repository**, by prefix, number or mechanism. Work on them appears in `TODO.md`
described as the hardening it is, without the finding identifier.

---

## `DP-` — dose provenance findings

**What it means.** Findings about a dose reaching a medic without a traceable
authority behind it — a pre-gate template computing its own number, a supersede
rule that does not cover every path, a source line that claims a provenance the
dose does not have. Raised by reading the serving paths against the contract
bank rather than by a harness.

**Canonical list.** This section, plus the 4.3.0 `CHANGELOG.md` entry. The
structural registry that keeps them closed is
`DOSE_TEMPLATE_CASES` in `server/test_drug_contracts.py`.

These were enumerated in a single report as A1/A2/A3/A4/B1 — labels local to that
report and uncitable outside it. They are numbered here.

| ID | Finding | State |
|---|---|---|
| **DP-1** | `build_ketamine_analgesia_response` served ketamine analgesia from the retired 0.3 mg/kg hardcode — 18 mg at 60 kg against the signed 15 mg — under a source line claiming a deterministic calculator. Returned from a pre-gate ahead of the supersede rule. *(reported as A1)* | fixed, verified |
| **DP-2** | `build_pediatric_ketamine_route_response`: an unreachable fourth copy of the analgesia template, dispatched from nowhere since the v4.0 baseline, bypassing the contract bank by construction. *(reported as A2)* | fixed — deleted |
| **DP-3** | `build_fixed_prep_response` served push-dose epinephrine at 5-20 mcg against a signed 10-20 mcg, and an infusion rate absent from the bank, from the **earliest** pre-gate — ahead of the weight and route gates, so it won over everything downstream. *(reported as A3)* | fixed, verified |
| **DP-4** | `build_rsi_response` assembled the RSI bundle from the retired calculators and asserted a fixed source line. *(reported as A4)* | fixed, verified |
| **DP-5** | `build_allowed_doses`: `if has_loraz or is_seizure` carried the supersede check on the first half only, so a seizure query appended the legacy calculator beside the signed contract entry — two benzodiazepines for one seizure. *(reported as B1)* | fixed, verified |
| **DP-6** | `detect_requested_medication_overdose` computes its refusal ceilings from hardcoded multipliers and never reads `max_single_dose`, so a refusal can quote a ceiling the bank no longer agrees with. | open — `TODO.md` |
| **DP-7** | `safety_rules.json` `dose_limits` still mirrors the retired per-kilogram numbers. Nothing serves them, which is why they will rot unnoticed; the file is generated, so the generator is the fix. | open — `TODO.md` |

**The structural guard protects provenance, not numeric coincidence.** Two doses
with the same number are indistinguishable in rendered text, so a regression that
reintroduces a bypass whose value happens to match the contract is caught by the
provenance assertion or not at all. Stated here because it is the limit of what
the registry can promise.

---

## Citing a finding

Use the prefix and number, and name the instrument if it is not obvious:
"F-12 (eval harness)", "DP-5". A finding that has been fixed should also cite the
commit that fixed it. Labels local to a single report — A1, B1, "the third one" —
are not citations; number them here first.
