# EdgeCDSS 1.0 → 4.0 — A Version History

**What was tried, what broke, and how it became the current system.**
AI in Austere Medicine Project · July 2026 · Companion to the documents archived in [`v3-era/`](v3/)

This is the reader's guide to the archive. The documents in this folder record three versions of a system that no longer exists in that form — and every major decision in EdgeCDSS 4.0 is a direct response to something that failed in them.

---

## Timeline at a glance

| When (2026) | Version | Defining change | Evidence |
|---|---|---|---|
| Apr 21 | 1.0 | Initial release: FastAPI + ChromaDB on a cloud VM, GPT-4 | 58.6% initial pass rate; 23.7s responses |
| May 3 | 2.2 | GPT-4 → GPT-4o-mini; ZERO MATH rule; dual-domain responses | 23.7s → 2.8s (9× faster) |
| May 3–7 | 2.5 | 34-case automated suite; conversation memory; first web interface | 94.1% (32/34) on suite |
| May 5–6 | 2.5 | **First external field test** — 6 testers, 43 queries | 82% helpful; 1 dangerous flag |
| May–June | 3.0 | Two-pass safety validator (an LLM checking the LLM); voice interface | 3 P1 failures drove the redesign |
| June | 3.3 | Prompt-patching grind against expanded suite | 16/26 → 19/26 → 22/26 plateau |
| Early July | 3.4.x | Deterministic pre-gates begin replacing prompt rules | Transitional rebuild |
| Mid-July | — | **Cloud VM lost** (provider capacity outage); deploy corruption incidents | Forced infrastructure rethink |
| Jul 18 | 4.0 | Deterministic-first rebuild; self-hosted on Jetson Orin Nano | 24/24 on live endpoint |

---

## Versions 1–2: prove the concept, trust the prompt

The original system was a hybrid cloud-edge design: a $35 Radxa Zero voice client in the field, a rented cloud VM ("arcaneone") running FastAPI and ChromaDB, and GPT-4 generating responses grounded in 89 JTS Clinical Practice Guidelines chunked into a vector database. Three ideas from this era survived every subsequent rebuild: the **ZERO MATH rule** (every dose resolved to a final mL draw — no arithmetic for the provider), the **dual-domain design** (JTS-grounded answers clearly distinguished from general evidence-based medicine, with explicit source attribution), and the structured field response format (DO THIS / GIVE / WATCH / DON'T / TLDR / SOURCE).

The era's defining fix was pragmatic: switching from GPT-4 to GPT-4o-mini cut response time from 23.7 seconds to 2.8 — the difference between a demo and a usable field tool. By early May the automated suite read 94.1%, and the Proof of Concept report was written.

That report's own limitations section, in hindsight, named the future: ChromaDB similarity scores were "near zero across all queries" (the retrieval pipeline was miscalibrated and nobody fully trusted its confidence numbers), dose outputs had never been validated against clinical ground truth, and every safety rule in the system was a sentence in a prompt, "stated at multiple locations to reduce hallucination risk." Safety by repetition.

## The field test that changed the trajectory

On May 5–6 the web interface went to external testers for the first time: six testers, 43 queries, 82% of documented feedback rated helpful. But the automated suite — 94.1% green — had said nothing about what the testers found in one day:

- A **6-year-old with WPW syndrome**: the system gave general assessment guidance without the contraindications that matter (adenosine and AV-nodal blockers can precipitate VF). A tester flagged it dangerous — the first P1 safety finding, caught by a human, invisible to the suite.
- A **10-year-old on a ventilator** prescribed a 500 mL tidal volume — the adult formula applied to a child, roughly double the safe value. The tester's feedback: *"Cool."* The error was found only on later expert review.
- The broader v2.5 cycle surfaced a **pediatric ketamine overdose**, a **missing surgical-airway recommendation** in a cannot-intubate scenario, and **high-flow oxygen recommended to a COPD patient**.

The pattern across all of them: automated tests confirm what you thought to check; experts find what you didn't. And prompt rules — however emphatically worded — leak.

## Version 3: an AI to check the AI

v3.0's answer was the **two-pass safety pipeline**: every generated response passed through a second, independent LLM call — a validator prompted to check pediatric ceilings, contraindications, CICO pathways, and route mismatches — before reaching the provider. The version also added a structured patient record, provider scope detection, a full voice interface (wake word: *"HEY MEDIC"*), and the protocols the field test showed missing.

It was a real improvement, and its limits taught the decisive lesson. The v3.3 archive documents a grinding month: failure analyses at 16/26, then 19/26, then 22/26 as prompt rules and validator instructions were patched, repatched, and patched again — each fix nudging the score while new failures appeared elsewhere. One probabilistic system checking another probabilistic system produced both false passes and false blocks, and nobody could prove which side a given day's build would land on. The prompt-only approach had found its ceiling. The v3.4.x transition began moving individual safety decisions — overdose detection, sepsis/DCR differentiation, fixed preparations — out of prompts and into deterministic code, one rule at a time.

Then the infrastructure failed. In mid-July the cloud provider ran out of capacity in the VM's zone and arcaneone could not be restarted — a cloud outage taking down a system whose entire purpose was medicine where infrastructure fails. Deploy-time file corruption (a repository file twice truncated to zero bytes) compounded the lesson: the project controlled neither its runtime nor, reliably, its deployment path.

## Version 4: never ask an AI a question code can answer

4.0 is the generalization of everything above. **Deterministic-first:** thirteen pre-generation gates, dose candidates computed in Python from confirmed weight and handed to the LLM as a fixed ALLOWED_DOSES contract, deterministic post-checks verifying every stated dose against that contract, and a narrow LLM validator behind them — fail-closed, with structured false-positive overrides written in code from observed field reports. The AI writes sentences; it no longer holds safety.

**Self-hosted:** the full stack — re-ingested knowledge base (89 CPGs, now 8,559 cleaner chunks with calibrated retrieval), clinical router, web portal, structured clinical feedback, audit logging — runs on a $249 Jetson Orin Nano reached through an outbound-only tunnel, on any network. No cloud vendor can turn it off.

The continuity is as telling as the change: ZERO MATH, dual-domain attribution, the structured response format, and the open publication of failures all date to version 1. What changed is *where safety lives* — from prompt sentences (v1–2), to a second AI (v3), to inspectable, testable code (4.0). The automated suite now passes 24/24 against the live public endpoint, and the field-feedback loop that caught the WPW gap in May is now built into every response — severity triage, issue categories, protocol-cited corrections — because the single most durable finding of this project's first four versions is that expert human scrutiny finds what nothing else does.

---

*Documents in this archive: the Proof of Concept report (May 2026), the v2.1 Field Evaluation Report (the WPW finding), and the v3.0 Goals & Technology document. Current documentation: [`docs/TECH_NOTES_v4.0.md`](../TECH_NOTES_v4.0.md).*

*Research prototype — not validated for clinical use. AI in Austere Medicine Project.*
