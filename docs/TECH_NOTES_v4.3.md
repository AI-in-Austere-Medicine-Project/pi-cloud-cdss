# EdgeCDSS 4.3 — Technical Notes

AI in Austere Medicine Project — August 2026

- Live portal: https://cdss.arcanekg.com
- Release notes page: https://ai-in-austere-medicine-project.github.io/pi-cloud-cdss/web/release-notes-4.3.html
- Repository: https://github.com/AI-in-Austere-Medicine-Project/pi-cloud-cdss
- Full changelog: [CHANGELOG.md](../CHANGELOG.md) · Deferred findings and residual risk: [TODO.md](../TODO.md)
- Prior release: [TECH_NOTES_v4.1.md](TECH_NOTES_v4.1.md) — superseded by this document. 4.2 shipped without technical notes; the parts of it that changed the pipeline shape are documented here
- Project overview & research positioning: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

---

## Overview

4.1 was a hardening release found by auditing field logs. 4.2 built out patient context — vitals, derived MAP, temperature — and made the model a configuration value. **4.3 adds a clinical capability and, with it, a new class of safety control: authorship.**

Until 4.3 an answer had two possible provenances. It came from a retrieved JTS guideline passage, or from a general medical reference fallback labelled as such. Both are retrieval or generation over text somebody else wrote. Neither is a clinician saying *this is the setting, for this physiology, and I stand behind it.*

The gap was measured, not assumed. The round-1 evaluation harness found **0 of 4 DKA ventilator phrasings returning any of tidal volume, rate, PEEP or FiO2** — 100% reproducible — against **4 of 4 for traumatic brain injury**. The asymmetry is the whole diagnosis: the `**VENT**` output block existed only as a format hint on the JTS generation prompt, so it applied when retrieval landed on a guideline that discussed ventilation and vanished when it did not. TBI retrieved well and answered well. DKA fell through to prose that never reached a number.

A prompt fix would have closed the instance. 4.3 closes the class: a deterministic card tier that runs before retrieval, holding clinician-authored content, gated so that an unsigned card is indistinguishable from an absent one.

## Architecture

Pipeline: `Knowledge → Logic → AI → Validation → Human`

Steps 1, 2 and 6 are as documented in 4.1. Step 3 is new. Steps 2 and 6 gained the 4.2 additions.

1. **Pre-generation gates (deterministic).** 13 gates before any AI call: confirmed-weight requirement, route confirmation, pediatric limits, requested-overdose detection, absolute contraindications. Many queries resolve here with no AI involvement.

2. **Patient context (deterministic).** Structured state re-derived on every request from conversation history and cleared at a detected patient boundary, with every reset announced. 4.2 and 4.3 extend what it holds: **vitals** (HR, BP, SpO2, RR, GCS, temperature, glucose) each carrying the timestamp of the turn they were stated in, a **derived MAP** flagged `derived` and recomputed rather than carried forward, and — new in 4.3 — **height and sex**, captured for ideal-body-weight arithmetic. A turn with no timestamp yields a reading whose age is *unknown*, never a fabricated "just now". Vitals reach the generator prompt, the validator and a narrow conflict table; they never compute a dose, pinned by a test that builds the dose contract with and without vitals present and asserts it is identical.

3. **Ventilator card tier (deterministic, new).** `vent_module.dispatch()` runs after the pre-gates and **before retrieval**. It returns `(family, card)` or `None`. On a hit the answer is rendered from card content and returned immediately: **no retrieval, no generation, no model call of any kind.** On `None` the pipeline continues exactly as it did before the module existed. See [The card tier](#the-card-tier) below.

4. **Retrieval (on-device).** 89 JTS CPGs ingested into 8,559 passages, local embeddings, zero per-query API cost. A clinical router aims the search using a protocol index, matching alias terms on word boundaries.

5. **Generation (AI).** The LLM receives retrieved guideline text plus an ALLOWED_DOSES contract computed in Python, and is prohibited from performing medication math. Since 4.2 the patient block **states the age band on every response** — pediatric, adult, not-pediatric, or unknown — rather than asserting it only when true. "Known adult" and "nobody has said" were previously the same silence.

6. **Post-checks and validation (deterministic + AI).** Generated dose lines are verified against the contract; an empty contract hard-blocks canonical dosing lines. The semantic validator fails closed; overrides downgrade to human review and can never release a blocked response. The verdict served, the verdict logged and the verdict reached are one value produced in one place.

## The card tier

### What a card is

`server/vent_module.py` is **engine, schema, dispatch and rendering only**. It contains no settings, no doses, no thresholds and no alarm interpretations. Clinical content lives in three JSON files, one per family:

| File | Family | Answers |
|---|---|---|
| `vent_cards.json` | physiology | initial settings for a physiology |
| `vent_troubleshooting.json` | troubleshooting | alarms and decompensation, as ordered steps |
| `vent_devices.json` | device | four field ventilators — where things live |

Each family has its own required-field schema plus six shared provenance fields: `source_label`, `reviewed_by`, `review_date`, `references`, `version`, `signoff`. Every card also carries `applies_when`, the authored signal list dispatch matches on.

The files ship with every clinical field empty or set to the sentinel `PENDING_CLINICAL_SIGNOFF`.

### The gate

`card_is_servable(card, family)` is the single gate every serve path goes through. It returns `(servable, reason)` rather than a bare bool — "why is this card not live" is a question an operator will otherwise guess at. A card is refused when:

- a required or provenance field is absent
- `signoff` is not exactly `True`
- `reviewed_by` is not in `SIGNOFF_AUTHORS` (config, default `clinician,AI-AIM`)
- `review_date` is empty or still the sentinel
- **any clinical field is empty or still carries the sentinel, at any depth** — `_is_pending()` recurses through dicts and lists, so a nested step or settings key holding a placeholder fails the whole card
- `references` is empty

**There is no override.** `EDGECDSS_DEBUG_WARN_ONLY` downgrades safety holds elsewhere in this system and does not reach this gate. Three properties are asserted by test rather than by convention:

- the flag's name does not appear anywhere in `vent_module.py`'s source
- `card_is_servable()` takes no parameter a bypass could ride in on — its signature is checked, not just its behaviour
- setting the flag changes nothing about what is servable

The reason this is structural rather than advisory: **the failure mode of a half-authored ventilator card is a patient ventilated on a placeholder.**

### Signing authorises the signature and nothing more

An authorised signer on a card still holding a sentinel is refused — for the *content*, not for the name. The two checks are independent and both must pass. A card may also be signed by the project as an organisation (`AI-AIM`); that is a signature, and signing is still not authoring.

A signed card must carry no sentinel in **any** field, including the ones outside the gated clinical set. `render_physiology()` prints `actual_weight_caveat` verbatim on the actual-weight path, so a truthy sentinel there would have put the literal string `PENDING_CLINICAL_SIGNOFF` in front of a medic. That path is guarded, and a test now walks every field rather than the gated ones.

### Partial deployment is the normal state

Cards go live one at a time as signoff lands. **Today: 5 of 13.** The five physiology cards are signed and carrying traffic; four troubleshooting and four device cards are authored, unsigned, dark, and invisible to the pipeline. `servable_cards()` reports the live set, which is what `/status` and the authoring worksheet read.

`dispatch()` returns `None` both for a query the module does not own and for a query whose card is unsigned. **The caller cannot tell those apart, deliberately** — a pending card must behave exactly like an absent one, which means falling through to whatever answered the query before the module existed.

### Dispatch

Priority is **troubleshooting > device > physiology**, and it is not a preference. A ventilator alarming on a patient is a different question from what the settings should be, and answering the second when asked the first is the S-4 failure with the roles reversed.

- **Word-anchored throughout.** `_anchored()` wraps every term list in `(?<!\w)…(?!\w)`. This repo is at five substring specimens — the F-2 alias table, `FIXED_PREP_TERMS`, the vitals labels, `_SHOCK_WORDS` and the F-3 AMS list — and a sixth in a module that decides ventilator settings was not one anyone wanted to write up.
- **Ambiguous device aliases require vent context.** `t1`, `1200`, `731` and `eagle` do not name a device on their own: `T1` is a thoracic level, a trauma triage category and a Hamilton ventilator, and only one of those wants a device card.
- **`applies_when` is data, not a regex.** A card's own signal list is matched with the same anchoring as everything else, so a card file cannot inject a pattern into the dispatcher.

### The baseline card was the silent default

`lung_protective_baseline` also matched "vent settings" and "set the vent". That made it the first match for nearly every real ventilator question and **shadowed all four specific cards** — a DKA query reached the ARDS-pattern card, which is F-12 with the roles reversed.

The generic settings phrases were removed from the baseline card's `applies_when`, and `physiology_gate()` now **asks which physiology** instead of defaulting. Two properties of that gate matter:

- it lists **only cards that are live**, so the menu never offers something dark
- it is **silent while no physiology card is live**. Asking a question the system cannot then act on would take a turn and serve nothing, while that same query today falls through to a retrieval that already answers the TBI phrasings correctly. Blocking working behaviour to ask an unanswerable question would be F-12 in a third costume

### Ideal body weight

Tidal volume is dosed on IBW, not actual weight. Devine, implemented as engine arithmetic:

```
male    50.0 kg + 2.3 kg per inch over 60 inches
female  45.5 kg + 2.3 kg per inch over 60 inches
```

`ideal_body_weight_kg()` returns `None` when height or sex is missing, and **`None` is a real answer the caller must handle** — defaulting either input puts an invented number under every breath the ventilator delivers.

`dosing_basis(ctx)` resolves to one of three states:

| basis | condition | behaviour |
|---|---|---|
| `ibw` | height and sex known | the correct anchor |
| `actual` | confirmed weight only | served **with the card's own caveat**, and the settings line says so: `450 mL (ACTUAL weight 75.0 kg — not IBW)` |
| `None` | nothing confirmed | nothing to anchor on |

A 75 kg casualty at 178 cm is **439 mL at 6 mL/kg, not 450**.

The F-1 weight-confidence rule is reused rather than re-implemented: only `confirmed_weight_kg` counts. A hedged weight sits in `estimated_weight_kg` and cannot anchor a tidal volume any more than it can anchor a drug dose.

The ask for a missing height is **non-blocking** — appended as `**ALSO SEND**` beneath the served settings. Blocking on it would be F-12 again: a ventilator question answered with something other than ventilator settings.

### Provenance

`VENT_CARD` is a third value for `source_mode`, and `knowledge_source()` maps it to a third value for the log's `source` field: `card`, alongside `jts` and `general`. Folding it into `jts` would claim a provenance it does not have.

The served line reads:

```
**SOURCE**: EdgeCDSS clinical card — reviewed by clinician, <date> — refs: <references>
```

Cards are signed **by role rather than by name**. Be clear about what that costs: a role string identifies nobody, so the line tells a medic that a clinician stands behind the card and when they signed it, but not which clinician, and `SIGNOFF_AUTHORS` can no longer distinguish one signer from another. `CDSS_CARD_AUTHORS` takes real names where a deployment needs an auditable signer.

Device cards additionally name the operator's-manual revision and verification date they were summarised from.

### Device cards and the copyright brake

Device cards are the owner's **authored summary** of an operator's manual, never reproduced manual text. `DEVICE_FIELD_MAX_CHARS = 400` is a structural brake on that rule rather than a style preference — a summary does not run to paragraphs. `lint_device_cards()` flags an overlong field and detects verbatim runs against manual text where a copy is available locally; manual files are gitignored, asserted by test.

## Changes in 4.3

### Clinical capability
- Ventilator card engine, three families, 13 cards authored, 5 signed and live
- F-12 closed: DKA 0/4 → **4/4**; TBI held at **4/4** as the control that proves the module did not buy one physiology at another's expense
- S-7 settled: three different TBI systolic targets became one — **SBP ≥ 110 mmHg** on the `tbi` card
- Height and sex capture; tidal volume dosed on Devine IBW with a visible, card-authored fallback

### Safety controls
- `card_is_servable()` — the authorship fence, with no override path and three properties asserted by test
- A signed card may carry no sentinel in any field, gated or not
- `applies_when` cannot inject a pattern into the dispatcher
- The baseline card no longer shadows the specific cards; a physiology-free settings question asks rather than defaults, and stays silent when it has nothing to offer

### Observability
- `log_schema` 9. `source` gains a third value `card`; a card answer records `card_id` and `card_version`, so a served answer traces to the exact authored revision. Both are **present-and-null** on every non-card answer, because absent is indistinguishable from a log written before cards existed

### Carried in from 4.2 (no technical notes were written for that release)
- Vitals in patient context with per-reading age; derived MAP labelled `derived` and recomputed rather than carried forward; temperature carrying the unit the medic stated; impossible values rejected visibly
- The age band stated to the validator on every response, in all three states; unknown is not adult
- Shock and AMS detection word-anchored — `"ams"` inside *milligrams* was routing any gram-stated dose as shock, and with an infection present that was the sepsis router firing on the word "milligrams". Fourth specimen of the substring class
- Multi-provider model registry (`server/providers.json`): OpenAI, Anthropic, Google Gemini, xAI, and self-hosted local inference. Adding a model is an edit, not a code change
- The version became one fact in `server/version.py`, with a test that fails if a second literal appears
- Emergency security patch: `/feedback` token check, `/feedback/summary` projection dropping submitter IPs and truncating free text, `query_endpoint` offloaded off the event loop that answers the watchdog's `/health`, and field-based secret redaction driven by `providers.json`'s own `key_env` declarations rather than key-shape patterns

## Stack

| Layer | Technology |
|---|---|
| Edge compute | NVIDIA Jetson Orin Nano Super 8GB, JetPack 6, NVMe SSD |
| API server | FastAPI + Uvicorn (Python 3.12) |
| Vector database | ChromaDB (on-device, local embeddings) |
| Generation / validation | Configurable via `providers.json` — OpenAI, Anthropic, Google Gemini, xAI, or self-hosted (Ollama / llama.cpp / vLLM). Default `gpt-4o-mini`; validator held at `gpt-4o-mini` |
| Card tier | `vent_module.py` + three JSON card files — deterministic, no model call |
| Routing | `protocol_index.json` (LLM-built, deterministically matched, word-anchored) |
| Connectivity | Network agnostic; Cloudflare Tunnel (outbound-only HTTPS) |
| TTS | ElevenLabs (isolated from clinical core; degrades gracefully) |
| Hosting (site) | GitHub Pages |

## Cost profile

Unchanged in shape from 4.0 — see [TECH_NOTES_v4.0.md](TECH_NOTES_v4.0.md#cost-profile). Compute is a one-time ~$300; recurring cost is dominated by connectivity, not by AI.

**A card answer costs nothing.** It is served before retrieval and before generation, with no model call on either the generation or the validation pass. As more cards are signed, the proportion of queries resolving at zero marginal cost rises.

## Testing

- **Offline regression suite: 859 tests, ~8s** (`server/run_unit_tests.sh`) — no network, no API key, no ChromaDB. Runs on a clean checkout. This is the gate for every change to the deterministic layer. `test_vent_module.py` contributes 65 of them
- **Evaluation harness: 160 scenarios** replayed against a pinned server snapshot — 62 real queries extracted from session logs, the v4.1 audit's safety cases replayed with their turn sequences, a sample of the gate-log invariant matrix, and 75 authored scenarios. Before/after is published with the fix
- 24-case automated clinical suite against the live public endpoint
- Convention for safety-relevant fixes: **one fix, one commit, one regression test**, plus a mutation check — revert the fix, confirm the named test fails, restore — recorded in the commit message

Round-1 harness result, same corpus and model, only the server snapshot differing:

| metric | before | after |
|---|---|---|
| hard safety failures | 1 | **0** |
| safety-gate correctness | 98.1% | **100.0%** |
| gate-log invariant violations | 0 | 0 |
| refusal rate | 15.6% | **1.9%** |
| non-medical refusals to clinical questions | 22 | **0** |
| human-review banner rate | 68.1% | **16.9%** |
| boundary-reset notices on turns with no history | 10 | **0** |

23 scenarios changed outcome; none moved in the unsafe direction.

**What the suite deliberately does not assert.** Unchanged from 4.1: the validator is non-deterministic, and no offline test pins what verdict it *produces* — only what the gate does with one. The card tier is the exception that proves the shape of the rule: it is fully deterministic and fully testable, which is precisely why clinical content that matters this much was moved into it.

## Known limitations

Carried forward:

- Decision support only; presumes a trained provider, clinical judgment, and local protocol
- Research prototype evaluated with simulated and synthetic scenarios only; not validated for clinical use
- Language generation requires connectivity to a hosted model; fully offline on-device inference remains the research goal (Layer 02). **Card answers are the exception** — they need no model at all
- Knowledge base reflects the JTS CPGs as published, and is trauma-scoped

Introduced or left open by 4.3 — the full list, with residual risk, is in [TODO.md](../TODO.md):

- **8 of 13 cards are dark.** Four troubleshooting and four device cards are written but unsigned, and the engine treats them as absent, so a ventilator troubleshooting question routes to whatever answered it before the module existed. That is the fence working as designed and it is also a real coverage gap until a clinician signs them
- **Two configured models are selectable but not usable for sustained traffic.** `available_models()` gates per **provider**, not per model. xAI fails authentication outright so `grok-4` never reaches the dropdown — correct behaviour. Gemini authenticates on the free tier, so both Gemini entries are selectable while the daily cap (20 requests per day per model) makes neither usable for a sustained eval slice. A medic who picks one gets a fail-closed system error once the cap is hit. Per-model availability would require one authenticated call per model on every `/status` poll, which is why it is not done
- **`grok-4`'s `supports_temperature: false` is a guess made in the safe direction.** A model that rejects the parameter returns 400 on every query; one that accepts it and never sees it samples at its own default. To be confirmed against a credited key
- **`temp.min` of 35 °C puts Celsius hypothermia outside the plausible band**, so `hypothermia_txa` can only arm from a Fahrenheit reading. Pinned by a test that says so out loud and raised in TODO.md as an owner decision — lowering the bound restores it with no code change
- **Log schema migration.** Schema 9 entries carry `card_id`, `card_version` and `source: "card"`. Analysis tooling must read a missing `log_schema` as unknown, never as a default, and must not read an absent card field as "not a card answer" on a pre-schema-9 entry
- **Schemas 7 and 8 are documented in code but not in the changelog.** Glucose capture (whose two plausible unit bands *overlap*, unlike temperature's, so an unlabelled value is read by a documented convention rather than inferred — 32 mg/dL and 32 mmol/L are opposite emergencies), the `ams_stated` patient fact, and `review_suppressed` all shipped without a `CHANGELOG.md` entry. The authoritative description is the comment block above `LOG_SCHEMA_VERSION` in `server/openai_client.py`

## Disclaimers

Research prototype — not validated for clinical use — not for patient care decisions — simulated and synthetic scenarios only. Do not enter PHI or real patient information into any project system. All code is MIT licensed. Provider and technology names identify components used by the project and do not imply endorsement, sponsorship, or affiliation.
