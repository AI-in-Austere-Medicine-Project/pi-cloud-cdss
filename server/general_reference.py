"""
EdgeCDSS — general medical reference fallback.

Closes F-4 (`TODO.md`) as a deliberate general-knowledge fallback rather than a
corpus expansion: the knowledge base is 89 JTS trauma CPGs, and medics bring lab
values, toxicology, envenomation and drug-preparation questions to it. The
measured consequence was the highest-frequency complaint in the feedback corpus
— *"it just denies anything"* — 6 of 63 substantive queries. Curated corpus
expansion is still the right long-term answer; this is the tier below it, the
thing a medic would otherwise look up on a phone.

This is a SECOND KNOWLEDGE SOURCE, NOT A SECOND PIPELINE
────────────────────────────────────────────────────────
Everything downstream of the generator is the same code on both paths:
run_deterministic_checks, validate_response, apply_safety_gate, the
`verdict == "UNSAFE" ⟺ blocked` invariant, the override registry, the session
log. All this module changes is which system prompt the generator receives when
retrieval came back with nothing usable, and how the served answer is labelled.

Recipe yes, prescription no
───────────────────────────
Owner ruling, 2026-08-21. A standardized preparation recipe is reference
knowledge: the concentration you get when you dilute 1 mg of epinephrine into
250 mL of saline is a fixed fact about the syringe, not a decision about a
patient. A dose is not: the moment an answer's correctness depends on this
patient's weight, age, route or access, it belongs to the ALLOWED_DOSES contract,
which either produces a deterministic line or holds.

That line is enforced in three independent places, deliberately:

  1. Routing (`use_general_reference`) — a dosing question never reaches this
     path at all. It stays on the contract path exactly as before.
  2. Prompt (`GENERAL_REFERENCE_PROMPT`) — the generator is told to hand dosing
     back rather than answer it.
  3. SC-6, unchanged — with an empty ALLOWED_DOSES contract, any canonical GIVE
     line in the response is a deterministic block. This is the backstop, and it
     is the reason the first two failing is survivable.

Note what (3) costs, because it is a real limitation and not a hypothetical:
SC-6 is purely syntactic, so it cannot tell a recipe from a prescription. A
legitimate preparation recipe phrased as "Draw 1 mL of 0.1mg/mL epinephrine
(0.1mg)" is blocked. `test_fixed_prep_text_is_not_a_canonical_give_line` pins
that the shipped push-dose epi card does not match that regex, and its docstring
notes it is the *second* of two independent reasons — on this path it is the
only one. The fix is prompt discipline and deterministic FIXED_PREP cards, not a
carve-out in the gate. Fail-closed stays.
"""

import re
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# LABELLING
# ─────────────────────────────────────────────────────────────────────────────

# Prepended AFTER the safety gate, for the same reason BOUNDARY_RESET_NOTICE is:
# the banner must never become text the validator reasons about or a safety
# override matches its keywords against. `dangerous_reassurance_has_action`
# fires on the substring "monitor" anywhere in a response; a banner is not
# clinical content and must not be able to satisfy a condition like that.
GENERAL_REFERENCE_BANNER = (
    "⚠️ GENERAL MEDICAL REFERENCE — not from JTS protocols\n\n"
)

# Voice disclosure. Short because it is heard before every general answer
# through an earpiece during care.
SPOKEN_DISCLOSURE = "From general reference, not JTS:"

_BANNER_RE = re.compile(
    r'^\s*(?:⚠️\s*)?GENERAL MEDICAL REFERENCE\s*—\s*not from JTS protocols\s*',
    re.IGNORECASE)


def add_banner(text: str) -> str:
    """Label a served general-reference answer. Idempotent."""
    return text if has_banner(text) else GENERAL_REFERENCE_BANNER + text


def has_banner(text: str) -> bool:
    return bool(_BANNER_RE.match(text or ""))


def strip_banner(text: str) -> str:
    """Drop the visual banner before speech.

    The banner is punctuation and an em dash; spoken verbatim it is worse than
    the one-line disclosure that replaces it.
    """
    return _BANNER_RE.sub("", text or "", count=1).lstrip()


def for_speech(text: str, source: str) -> str:
    """What /speak should synthesize. Disclosure is server-side on purpose.

    A client that forgot to prepend it would produce a spoken answer with no
    indication it did not come from JTS, which is the one thing this feature is
    not allowed to do.
    """
    if source != "general":
        return text
    return f"{SPOKEN_DISCLOSURE} {strip_banner(text)}".strip()


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING GUARD — what may and may not reach general knowledge
# ─────────────────────────────────────────────────────────────────────────────

# Phrasings that ask what to give, as opposed to what something is. Matched on
# the full query history, so a dose request two turns back still disqualifies.
_DOSING_INTENT = (
    "how much", "how many mg", "how many ml", "how many mcg",
    "what dose", "whats the dose", "what's the dose", "which dose",
    "dose for", "dosing for", "dose of", "how do i dose",
    "do i give", "should i give", "can i give", "how much do i",
)

# Preparation questions. These legitimately contain "how much" ("how much saline
# do I add") and are the reference tier this feature exists to serve, so they are
# exempted from _DOSING_INTENT — but never from SC-6, which still blocks any
# canonical GIVE line the generator produces from here.
_PREPARATION_INTENT = (
    "how do i make", "how do i mix", "how to make", "how to mix",
    "how do you make", "how do you mix", "make a", "mix a", "mixing",
    "prepare a", "preparation", "prep a", "dilute", "dilution",
    "concentration", "recipe", "reconstitut",
)


def _has_any(text: str, terms) -> bool:
    t = (text or "").lower()
    return any(term in t for term in terms)


def is_preparation_question(text: str) -> bool:
    return _has_any(text, _PREPARATION_INTENT)


def is_dosing_question(text: str) -> bool:
    """True when the query asks what to give rather than what something is.

    Conservative by construction. A reference question that trips this stays on
    the existing path and gets today's behaviour — the cost of a false positive
    here is an unchanged answer, and the cost of a false negative is a dose
    figure from general knowledge read aloud over a patient.

    Note this does NOT require a patient in session context. An empty
    PatientContext means the system knows of no patient, not that there is none
    in front of the medic.
    """
    if is_preparation_question(text):
        return False
    return _has_any(text, _DOSING_INTENT)


def use_general_reference(source_mode: str, full_query_history: str,
                          allowed_doses: list,
                          wants_dose: bool,
                          patient_known: bool = False) -> bool:
    """Whether this query should be answered from general medical knowledge.

    `wants_dose` is openai_client.wants_medication_dose over the full history and
    `patient_known` is whether the session holds any patient facts; both are
    passed in rather than imported, to keep this module free of a circular import
    and testable on its own.

    Only INSUFFICIENT retrieval falls back. The GENERAL_MEDICAL band (0.10–0.35)
    still has retrieved text in the prompt and keeps its existing behaviour; it
    is labelled "general" because its own prompt already says it is not JTS, but
    it is not this path.
    """
    if source_mode != "INSUFFICIENT":
        return False
    if allowed_doses:
        # A contract exists, so the dose path owns this query.
        return False
    if is_dosing_question(full_query_history):
        return False
    if wants_dose:
        # wants_medication_dose fires on a bare drug name, so it also catches
        # "how do I mix a norepinephrine drip" — a recipe question, and exactly
        # the tier this feature exists to serve. Preparation intent releases it,
        # but only while the session holds no patient: "mix a ketamine drip for
        # this child" is a prescription wearing a recipe's phrasing.
        return is_preparation_question(full_query_history) and not patient_known
    return True


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR PROMPT
# ─────────────────────────────────────────────────────────────────────────────

GENERAL_REFERENCE_PROMPT = """
You are AUSTERE-CDS in GENERAL MEDICAL REFERENCE mode.

No JTS or TCCC protocol was retrieved for this query. You are answering from
general medical knowledge — the tier a medic would otherwise look up on a phone.

This system is a research prototype. Not validated for patient-care decisions.
Support, do not replace, clinical judgment, local protocol, and medical control.

────────────────────────────────
WHAT THIS MODE IS FOR
────────────────────────────────

Reference facts. Laboratory values and reference ranges. Toxicology and
poisoning. Envenomation — snake, spider, scorpion, marine — and identification
support. Toxic plant identification. Standardized drug preparation recipes.
Equipment and device reference. Basic physiology and clinical definitions.

────────────────────────────────
HARD LIMIT — RECIPE YES, PRESCRIPTION NO
────────────────────────────────

You MAY state a standardized preparation: what a fixed dilution yields, the
resulting concentration, the standard mix. That is a fact about the syringe.

You MAY NOT give a dose for a patient. Not weight-based, not "the usual adult
dose", not a range to pick from. If the query asks what to give someone, answer
only with the REFERRAL SENTENCE given below.

Ask only for what the session does not already hold. If PATIENT CONTEXT states a
confirmed weight, that weight is known — do not ask for it, and do not condition
the referral on getting it. Asking a medic for a number printed further down the
same prompt tells them the system has lost their patient.

Never write a line of the form "Draw X mL of Y mg/mL <drug> (Z mg)". That format
is reserved for deterministically calculated doses and will be blocked here.

────────────────────────────────
SCOPE
────────────────────────────────

Every query that reaches you has already been judged clinical, by
is_non_medical_query() before the pipeline ran. You have no refusal sentence
and must never reply that this system handles medical queries only.

The ONLY refusal available on this path is the REFERRAL SENTENCE below, and it
is for dosing questions alone. A reference question you cannot answer gets "I
do not know", not a refusal.

If the query is too broad to answer usefully — a whole specialty, an open-ended
"tell me about", a request for a differential across an unbounded presentation —
say what would narrow it, in one sentence. Do not attempt it.

If you do not know, say you do not know. A wrong reference value is worse than
no reference value.

────────────────────────────────
FORMAT
────────────────────────────────

A reference card, not an essay. 150 words maximum. Short sentences. No tables.
No preamble, no restating the question.

Lead with the answer. Follow with the one caveat that matters, if there is one.

End with: "General reference, not JTS. Confirm against local protocol."
"""

# F-7 (eval baseline). Tier selection is a pure function of the retrieval
# score — use_general_reference fires on source_mode == "INSUFFICIENT" and
# nothing else — so a retrieval MISS silently changes the response format. It
# does so most often on exactly the queries retrieval is worst at, which the
# same run showed are disproportionately the urgent short ones.
#
# Measured: 43 of 132 served answers came through this path, and 45 of 48 had
# no **TLDR** at all. Among them "he's tanking, BP is 78/44 now and he's grey"
# (G-MTN-01), "his sugar came back at 32, he's confused" (G-MTN-08),
# "circumferential burn, fingers are getting dusky" (G-BRN-06) and "hypothermic
# arest, found in the snow, no pulse" (G-TYP-07) — all answered in three
# sentences of prose with no actions, no TLDR and no evacuation trigger.
#
# The content rules above do NOT change: recipe-yes-prescription-no and the
# 150-word cap hold on both registers. Only the shape of an ACUTE answer does.
ACUTE_FORMAT_BLOCK = """

────────────────────────────────
FORMAT OVERRIDE — ACUTE PRESENTATION
────────────────────────────────

This query is about a patient in front of the medic right now, so the
reference-card shape above is replaced by the action shape below. Everything
else on this page still applies: no dose for a patient, the referral sentence
for dosing questions, and the 150-word cap.

**DO THIS**
1. [Most critical action]
2. [Second action]
3. [Third]

**WATCH**
- [One monitoring line]

**TLDR**
- [One sentence. Most critical action or number.]

End with: "General reference, not JTS. Confirm against local protocol."
"""

# What makes a query acute. Two signals, both cheap and both stated by the
# medic rather than inferred: the session holds a vital sign, or the query
# asks what to do now. Neither reads the retrieval score, which is the whole
# point — the tier's SHAPE stops being a side-effect of a retrieval miss.
_ACUTE_IMPERATIVES = (
    "what do i do", "what do we do", "what now", "what next", "now what",
    "what should i do", "how do i manage", "how should i manage",
    "do i give", "should i give", "can i give", "what do i give",
    "he's tanking", "hes tanking", "she's tanking", "shes tanking",
    "is crashing", "is dying", "no pulse", "not breathing", "unresponsive",
    "right now", "immediately", "first thing", "priority",
)


def is_acute_presentation(query: str, vitals_present: bool = False) -> bool:
    """Whether a general-reference answer should use the action format.

    Deliberately biased toward the action shape: a reference question answered
    in DO THIS / WATCH / TLDR is mildly over-structured, and an acute question
    answered as a paragraph of prose is the failure this exists to close.
    """
    if vitals_present:
        return True
    return _has_any(query, _ACUTE_IMPERATIVES)


REFERRAL_BASE = "Dosing goes through the protocol path"


def dosing_referral(weight_confirmed: bool = False,
                    route_known: bool = False) -> str:
    """The one sentence this mode may answer a dosing question with.

    It names ONLY what the session does not already hold. The fixed wording used
    to be "ask again with the patient's weight in kg and route" whatever the
    context said, so on 2026-08-21 a medic who had already given 77.1 kg was
    asked for the weight again — by a prompt that was carrying "Confirmed
    weight: 77.1kg" thirty lines below the sentence telling the model to ask.

    Refusing to dose here is the point and does not change. Re-asking for a
    fact the system is holding is the bug: it reads as the system having lost
    the patient, and it is the thing that makes a medic stop trusting the
    context strip.
    """
    missing = []
    if not weight_confirmed:
        missing.append("the patient's weight in kg")
    if not route_known:
        missing.append("route")
    if not missing:
        return (f"{REFERRAL_BASE} — this session already has the weight and route, "
                f"so ask there and it will be calculated.")
    return f"{REFERRAL_BASE} — ask again with {' and '.join(missing)}."


def build_system_prompt(patient_block: str = "",
                        weight_confirmed: bool = False,
                        route_known: bool = False,
                        acute: bool = False) -> str:
    """Reference prompt, plus patient context when the session has any.

    Patient context is included so the model can decline coherently — knowing a
    child is in the session is what makes "dosing goes through the protocol
    path" the obvious answer rather than a surprising one. It is NOT there to be
    dosed against, and ALLOWED_DOSES is deliberately absent from this prompt:
    there is no contract on this path, by construction.

    `weight_confirmed` and `route_known` shape the referral sentence so it does
    not ask for what the block already states. They are passed as flags rather
    than parsed back out of `patient_block`, because a prompt that reads its own
    text to decide what it knows is one rewording away from being wrong.
    """
    prompt = GENERAL_REFERENCE_PROMPT
    if acute:
        prompt += ACUTE_FORMAT_BLOCK
    prompt += ("\n\n────────────────────────────────\nREFERRAL SENTENCE\n"
               "────────────────────────────────\n\n"
               "Answer a dosing question with exactly this sentence:\n\n"
               f"\"{dosing_referral(weight_confirmed, route_known)}\"")
    if patient_block:
        prompt += ("\n\n────────────────────────────────\nPATIENT CONTEXT\n"
                   "────────────────────────────────\n\n" + patient_block +
                   "\n\nThis context is for coherence only. Do not dose against it.")
    return prompt
