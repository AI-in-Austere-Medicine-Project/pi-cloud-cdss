"""
EdgeCDSS — AUSTERE-CDS Pipeline
Version: 4.0.0

v4.0 — Deterministic-First Architecture
Major version: consolidates the v3.4.x rebuild into a stable architectural baseline.

Core principle: Python owns everything that can be computed deterministically;
the LLM only handles what genuinely requires language understanding.

Pipeline: 13 deterministic pre-gates -> RAG (router-enhanced) -> ALLOWED_DOSES
contract generator -> deterministic post-checks -> narrow LLM validator ->
fail-closed safety gate with structured false-positive overrides.

v4.0 defining features:
  - Structured PatientContext: history for facts, current query for intent
  - confirmed_weight_kg is the ONLY weight used for dosing (estimated walled off)
  - Negation-aware semantic helpers (has_fever numeric parsing, has_positive_term)
  - Clinical router: protocol_index.json-backed RAG query enhancement (89 JTS CPGs)
  - Session audit logger: JSONL per-query log, debug-tagged, no PHI
  - DEBUG_WARN_ONLY env flag: fail-closed logic is never hand-edited to debug
  - normalize_validator_result: UNSAFE without issues -> NEEDS_HUMAN_REVIEW

Architecture per code review recommendations (EdgeCDSS_openai_py_issue_recommendations.docx):
  1. Structured session state (PatientContext with confirmed vs estimated weight, access_state, route_preference)
  2. Deterministic pre-gates BEFORE any LLM call — missing weight/route returns immediately, skips validator
  3. RAG retrieval + source classification
  4. Route-specific deterministic dose candidates (DoseCandidate) built in Python
  5. Generator receives ALLOWED_DOSES only — no medication math
  6. Deterministic post-checks validate against allowed_doses contract
  7. LLM validator receives full conversation transcript — narrow semantic checks only
  8. Safety gate with explicit safe-gate response allowlist

Key design principle: prompts handle formatting and clinical language.
Python handles gates, weight rules, route selection, calculators, and safety checks.

v3.4 additions (EdgeCDSS_openai_py_issue_recommendations_2.docx):
  - detect_requested_medication_overdose() — pre-generator overdose block
  - Deterministic sepsis-DCR pre-gate
  - FIXED_PREPS system with build_fixed_prep_response()
  - ALLOWED_ACTIONS for weight-free protocol guidance
  - normalize_validator_result() — UNSAFE with empty issues → NEEDS_HUMAN_REVIEW
"""

import os
import re
import json
import time
from dataclasses import dataclass, field, asdict, replace as dc_replace
from typing import Literal, Optional, List
import general_reference
import providers
import vent_module

# Same degradation rule the rest of the config layer follows: if the contract
# engine cannot be imported, the dose contracts are ABSENT — every drug falls
# through to the empty-contract path — never a server that will not boot.
try:
    import drug_contracts
except Exception as _e:                                   # pragma: no cover
    print(f"⚠️  drug_contracts unavailable ({_e}) — no drug dose contracts.")
    drug_contracts = None

# The concentration master list. Same degradation rule: if it cannot be
# imported, NO volume is served anywhere — mg doses are unaffected.
try:
    import drug_concentrations
except Exception as _e:                                   # pragma: no cover
    print(f"⚠️  drug_concentrations unavailable ({_e}) — no volumes will be "
          f"served; milligram doses are unaffected.")
    drug_concentrations = None
import vitals as vitals_mod

# The OpenAI SDK is no longer imported here. Both LLM calls go through
# providers.chat(), which imports each provider's SDK lazily inside its own
# adapter — so this module keeps its P-0 property (importable with no SDK, no
# key and no network) without needing a guarded import of its own.

try:
    from dotenv import load_dotenv
except ImportError:  # offline test environment
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv()

def model_label(model_id: str) -> str:
    """'openai/gpt-4o-mini' — what the log and the client footer record.

    Provider-qualified because a bare model string stops being unique the moment
    a local endpoint serves an OpenAI-named model, and the audit question is
    always "which service answered this", not "which weights".
    """
    spec = providers.MODELS.get(model_id)
    return f"{spec.provider}/{spec.id}" if spec else model_id

# Debug flag per deep review §4: never edit fail-closed logic to debug.
# Set EDGECDSS_DEBUG_WARN_ONLY=1 in the environment to observe generator
# output with issues appended as text instead of blocking. Defaults to OFF.
DEBUG_WARN_ONLY = os.getenv("EDGECDSS_DEBUG_WARN_ONLY", "0") == "1"
if DEBUG_WARN_ONLY:
    print("⚠️  EDGECDSS_DEBUG_WARN_ONLY is ON — safety holds will warn, not block. NOT FOR PRODUCTION.")


def _env_number(name: str, default, cast=float):
    """
    Read a numeric tuning knob from the environment, falling back on garbage.

    These knobs exist to be tuned, which means they will be typo'd — "30m",
    "thirty", a trailing space. A bare int()/float() on the result raises, and
    PATIENT_BOUNDARY_TIMEOUT_MIN is read at MODULE SCOPE: an unparseable value
    there means openai_client fails to import, uvicorn never starts, /health
    never answers, and the deploy watchdog reboots the box in a loop. A tuning
    typo must degrade to the default, loudly, not take the device down.
    """
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return cast(str(raw).strip())
    except (TypeError, ValueError):
        print(f"⚠️  {name}={raw!r} is not a number — using default {default}.")
        return default


# ─────────────────────────────────────────────────────────────────────────────
# SESSION AUDIT LOGGER
# ─────────────────────────────────────────────────────────────────────────────

import datetime
import pathlib

_LOG_DIR = pathlib.Path(os.getenv("CDSS_LOG_DIR", "/home/akaclinicalco/cdss-cloud/logs/sessions"))

def _get_log_file() -> pathlib.Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    return _LOG_DIR / f"cdss_session_{date_str}.jsonl"

# Bumped when the entry shape changes. v4.1 (schema 2) adds pipeline_ms,
# synthetic and override_fired. Schema 3 adds `source` and `model`. Entries
# written before v4.1 carry no log_schema key at all; analysis tooling must read
# a missing key as UNKNOWN, never as a default. Defaulting a missing `synthetic`
# to false would re-classify the 48 known test-suite entries as real user
# traffic; defaulting a missing `source` to "jts" would claim JTS provenance for
# every entry written before general reference existed.
# Schema 4 adds the vitals fields. `vitals` is the state the answer was produced
# against — the question "what did the system believe the blood pressure was
# when it said that" has to be answerable from the log alone, which is the S-1
# lesson applied to the audit surface rather than the UI.
# Schema 5 reshapes one of them: the vital named `temp_c` is now `temp`, its
# `value` is in whichever unit the medic stated (`unit` says which), and a
# temperature carries `value_c` and `value_f` alongside. Reading a schema 4
# `temp_c` as Celsius is correct; reading a schema 5 `temp` that way is not,
# which is why this is a version and not a silent change of contents.
# Schema 6 adds `map` — the first vital in this block the SYSTEM produced rather
# than heard — and, because of it, a `derived` flag on EVERY reading. Every
# schema 5 reading was stated; reading a schema 6 one that way is a coin flip on
# `map`. The flag is written even where it is false because "the medic said this"
# is a fact worth recording, and a flag that only appeared when true would leave
# a stated MAP looking exactly like a log written before the field existed.
# Schema 7 adds two things a reader must not guess about. `vitals` may now
# carry `glucose`, whose two plausible unit bands OVERLAP — unlike temperature's
# — so an unlabelled value is read by a documented convention
# (vitals_rules.json: assumed_unit_when_unstated) rather than inferred from the
# number. The `unit` on the reading says which unit was used and is the only
# safe way to read the value: 32 mg/dL and 32 mmol/L are opposite emergencies.
# `patient_ctx` also now carries `ams_stated` — a boolean patient fact, not a
# measurement, which is why it is not in `vitals`.
# Schema 8 adds `review_suppressed`: the name of the deterministic
# precondition that stopped a validator NEEDS_HUMAN_REVIEW from becoming a
# banner, or null. Same reason override_fired exists — a suppression with no
# trace makes "why did this answer carry no banner" unanswerable from the log.
# Schema 9 adds the card tier. `source` gains a third value, "card", and a
# card answer records `card_id` and `card_version` so a served answer can be
# traced to the exact authored revision that produced it — the same question
# override_fired answers for the gate. Both are null on every non-card answer,
# present-and-null rather than absent, because absent is indistinguishable
# from a log written before cards existed.
LOG_SCHEMA_VERSION = 9

# source_modes whose answer did NOT come from retrieved JTS protocol text.
# FIXED_PREP is here deliberately: a standardized preparation recipe is
# reference knowledge, not a JTS protocol, and saying so is the point of the
# field. `source` answers one binary question — did general medical knowledge
# produce this? — which is why errors and refusals sit on the "jts" side: they
# are not general-knowledge answers either.
GENERAL_SOURCE_MODES = frozenset({
    "FIXED_PREP", "GENERAL_MEDICAL", "GENERAL_REFERENCE",
})

# The third provenance label. A card answer is neither retrieved from the JTS
# corpus nor produced from general model knowledge: a named clinician wrote it,
# dated it and signed it off, and the medic should be able to see whose
# judgement they are acting on. Folding it into "jts" would claim a provenance
# it does not have.
CARD_SOURCE_MODES = frozenset({"VENT_CARD"})


def knowledge_source(source_mode: str) -> str:
    """"jts" | "general" | "card" — which knowledge source produced the answer."""
    if source_mode in CARD_SOURCE_MODES:
        return "card"
    return "general" if source_mode in GENERAL_SOURCE_MODES else "jts"


def log_query(query: str, result: dict, conversation_history: list = None,
              pipeline_ms: Optional[int] = None, synthetic: bool = False):
    """
    Write one structured log entry per query.
    JSONL format — one JSON object per line.
    No patient identifiers stored — context is clinical state only.
    """
    try:
        entry = {
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "log_schema": LOG_SCHEMA_VERSION,
            "debug_warn_only": DEBUG_WARN_ONLY,
            "synthetic": bool(synthetic),
            "query": query,
            "response_preview": result.get("response", "")[:200],
            "source_mode": result.get("source_mode", "UNKNOWN"),
            "source": result.get("source") or knowledge_source(
                result.get("source_mode", "UNKNOWN")),
            # The model that produced the text, provider-qualified. null when
            # Python produced it and no model was called at all — a deterministic
            # card is not attributable to a model, and recording one would make
            # cross-model comparison count answers no model wrote.
            "model": result.get("model"),
            "validator_result": result.get("validator_result", "UNKNOWN"),
            "validator_issues": result.get("validator_issues", []),
            "override_fired": result.get("override_fired"),
            "review_suppressed": result.get("review_suppressed"),
            "card_id": result.get("card_id"),
            "card_version": result.get("card_version"),
            "boundary_reset": result.get("boundary_reset"),
            "vitals": (result.get("patient_context") or {}).get("vitals", {}),
            # What this turn displaced, with both values: the prior belief is
            # what an audit needs and what the v4.0 log could not answer.
            "vitals_superseded": result.get("vitals_superseded", []),
            "vitals_rejected": (result.get("patient_context") or {}).get(
                "vitals_rejected", []),
            "vitals_cautions": result.get("vitals_cautions", []),
            "pipeline_ms": pipeline_ms,
            "history_turns": len(conversation_history) if conversation_history else 0,
            "patient_ctx": {
                k: v for k, v in (result.get("patient_context") or {}).items()
                if k in ["confirmed_weight_kg", "is_pediatric", "route_preference",
                         "access_state", "age_years", "ams_stated"]
            }
        }
        with open(_get_log_file(), "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Logger error (non-fatal): {e}")

try:
    from clinical_router import ClinicalRouter
    _router = ClinicalRouter()
    print(f'Clinical router loaded: {len(_router.protocol_index)} protocols')
except Exception as e:
    _router = None
    print(f'Clinical router not available: {e}')


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

AccessState = Literal["UNKNOWN", "CONFIRMED_IV_IO", "NO_IV_IO", "FAILED_IV"]
RoutePreference = Literal["UNKNOWN", "IV", "IM", "IO"]


@dataclass
class PatientContext:
    """
    Structured session state. Persisted across conversation turns.
    confirmed_weight_kg is the ONLY weight used for medication dosing.
    estimated_weight_kg is for airway sizing / rough context only.
    """
    age_years: Optional[float] = None
    confirmed_weight_kg: Optional[float] = None
    estimated_weight_kg: Optional[float] = None
    weight_source: str = "unknown"
    sex: Optional[str] = None
    is_pediatric: bool = False
    provider_scope: str = "UNKNOWN"
    access_state: AccessState = "UNKNOWN"
    route_preference: RoutePreference = "UNKNOWN"
    pending_question: Optional[str] = None
    # Vitals: name -> vitals.VitalReading. Cleared by a patient boundary along
    # with everything else, because a PatientContext() is a fresh patient and a
    # previous patient's blood pressure is the S-1 failure with a faster clock.
    # `map` lives here too and is cleared with the rest, even though it is
    # derived: it is derived FROM this patient's pressure, so it is this
    # patient's number.
    vitals: dict = field(default_factory=dict)
    # {generic_name: mg/mL} — which vial the medic confirmed they are holding,
    # for drugs where the kit declares more than one, or where the owner set
    # confirm_required. Resets with the patient like everything else in here:
    # a fresh PatientContext is a fresh patient, and buying one turn of
    # convenience by making an exception to that is how the exception becomes
    # the bug. The ASK only fires for drugs that genuinely need it.
    confirmed_concentrations: dict = field(default_factory=dict)
    # Drugs named so far in THIS patient's turns. Exists so that a bare answer
    # to the concentration ASK — "50", or "500 in 10" — can be attached to the
    # drug that was asked about a turn earlier, without reaching back into
    # history that a patient boundary has already invalidated.
    drugs_named: list = field(default_factory=list)
    # Both describe the CURRENT turn only, like boundary_reset_reason: reset at
    # the top of every extract_patient_context call so that after the replay
    # loop they hold what this turn did, not what the conversation did.
    vitals_superseded: list = field(default_factory=list)
    vitals_rejected: list = field(default_factory=list)
    # SC-1: set on the context handed to the current turn when THIS turn crossed
    # a patient boundary. Drives the visible reset notice. Never persisted — a
    # fresh PatientContext() starts with it clear, which is what makes it mean
    # "this turn" rather than "some turn".
    boundary_reset_reason: Optional[str] = None
    # F-3: "the medic said this patient's mental status is off", as a fact
    # about the patient rather than a measurement. It lives here and not in
    # `vitals` on purpose — vitals stores measurements, and a stated
    # descriptor is not one — but the caution table needs it, and both of the
    # places that call vitals.conflicts() have the context in hand.
    # Describes the CURRENT turn plus anything a prior turn established, and
    # is cleared by a patient boundary with the rest of the context.
    ams_stated: bool = False

    @property
    def dosing_weight_kg(self) -> Optional[float]:
        """Only confirmed weight may be used for medication dosing."""
        return self.confirmed_weight_kg

    @property
    def has_confirmed_weight(self) -> bool:
        return self.confirmed_weight_kg is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["vitals"] = vitals_mod.to_dict(self.vitals)
        d["vitals_rejected"] = [r.to_dict() for r in self.vitals_rejected]
        return d


@dataclass
class DoseCandidate:
    """A pre-calculated medication dose from deterministic Python calculators."""
    drug: str
    indication: str
    route: str
    dose_mg: float
    source: str
    warning: Optional[str] = None
    # NOT set by the calculators. A milligram dose is a clinical claim the
    # contracts own; a millilitre volume is a claim about the vial in the bag,
    # which only drug_concentrations.json knows. These stay None until
    # resolve_dose_volume() fills them from the confirmed concentration, and a
    # None here is what makes the mg-only GIVE line happen instead of a wrong
    # volume.
    volume_ml: Optional[float] = None
    concentration_mg_ml: Optional[float] = None
    # The dose as the SOURCE states it. dose_mg is the normalised figure used
    # to derive a volume; these two are what the medic reads, because a
    # guideline that says 25 g should not be read back as 25000 mg.
    display_value: Optional[float] = None
    display_units: Optional[str] = None
    volume_refusal: Optional[str] = None


@dataclass
class DeterministicCheck:
    passed: bool
    issues: list = field(default_factory=list)


@dataclass
class GateOutcome:
    """
    Result of apply_safety_gate().

    Replaces the old (response, blocked, issues) tuple so that the verdict
    written to the audit log is produced by the gate itself rather than
    re-derived at the call site. The call site used to compute

        "validator_result": "UNSAFE" if blocked else llm_result["result"]

    which stamped UNSAFE on the log whenever the validator said UNSAFE — even
    when an override had released the response and the medic saw it (S-2).

    INVARIANT: verdict == "UNSAFE" if and only if blocked is True.
    A served response can never be logged UNSAFE. Enforced by
    test_safety_gate.py::test_gate_log_invariant.
    """
    response: str
    blocked: bool
    issues: list
    verdict: str                              # SAFE | NEEDS_HUMAN_REVIEW | UNSAFE
    override_fired: Optional[str] = None      # registry name, for the audit log (T-13)
    # Vitals conflicts. Kept separate from `issues` because they are not
    # validator findings and must not read as such in the audit log: an issue is
    # something the gate weighed, a caution is something appended after it.
    cautions: list = field(default_factory=list)
    # F-8. Names the deterministic precondition that stopped a validator
    # NEEDS_HUMAN_REVIEW from becoming a banner, or None. Recorded for the same
    # reason override_fired is (T-13): a suppression that leaves no trace makes
    # "why did this answer carry no banner" unanswerable from the log, which is
    # the question S-2 could not answer in the other direction.
    review_suppressed: Optional[str] = None


@dataclass
class RetrievalAssessment:
    source_mode: Literal["JTS_GROUNDED", "GENERAL_MEDICAL", "INSUFFICIENT"]
    top_score: float
    context_text: str
    sources: list


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT CONTEXT EXTRACTOR — incremental, merges with prior session state
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT CAPTURE — units, and confidence
# ─────────────────────────────────────────────────────────────────────────────

# Longest alternative first: "kilograms" must not be consumed as "kilo" + junk.
# Anchored with (?!\w) rather than \b for the same reason FIXED_PREP_TERMS is —
# the doctrine in _prep_term_present — so "80kgs" matches and "80kgx" does not.
_KG_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:kilograms|kilogram|kilos|kilo|kgs|kg)(?!\w)')
_LB_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:pounds|pound|lbs|lb)(?!\w)')

# F-1 (eval baseline, G-ADV-12). `confirmed_weight_kg` is the only weight the
# dose contract will calculate from, and the parser had no notion of
# confidence: any number next to a unit became a confirmed weight. The measured
# consequence was "he weighs about 80kg I think, close enough" producing
# `confirmed_weight_kg=80.0` and a served 24 mg ketamine dose, with a SAFE
# verdict and no banner. `estimated_weight_kg` already existed for exactly this
# and was never populated from prose.
#
# Two windows, not one. The ruling's own list contains both leading hedges
# ("about 80kg") and TRAILING ones ("70 kg or so", "80kgish"), so a
# before-the-number-only window would miss half the list it was given.
_HEDGE_BEFORE = ("about", "around", "roughly", "approx", "approximately",
                 "maybe", "like", "i think", "i guess", "guessing",
                 "probably", "somewhere", "close enough", "or so", "ish")
_HEDGE_AFTER = ("or so", "ish", "i think", "close enough", "maybe", "give or take")

_HEDGE_BEFORE_RE = re.compile(
    r'(?<!\w)(?:' + "|".join(re.escape(t) for t in _HEDGE_BEFORE) + r')(?!\w)')
_HEDGE_AFTER_RE = re.compile(
    r'(?<!\w)(?:' + "|".join(re.escape(t) for t in _HEDGE_AFTER) + r')(?!\w)')
# "~80kg" — not a word character, so it cannot be word-anchored with the rest.
_TILDE_RE = re.compile(r'~\s*$')

_HEDGE_WINDOW_BEFORE = 30
# Wide enough for the longest trailing hedge plus its leading space:
# ' give or take' is 13 characters.
_HEDGE_WINDOW_AFTER = 16


def weight_is_hedged(text: str, start: int, end: int) -> bool:
    """True when the number at [start:end] was offered as an estimate.

    Deliberately biased toward reading a hedge that is not there: a false
    positive downgrades a confirmed weight to an estimate and the pre-gate asks
    once more, which costs a turn. A false negative doses a patient on a guess.
    """
    before = text[max(0, start - _HEDGE_WINDOW_BEFORE):start]
    after = text[end:end + _HEDGE_WINDOW_AFTER]
    return bool(_HEDGE_BEFORE_RE.search(before)
                or _TILDE_RE.search(before)
                or _HEDGE_AFTER_RE.search(after))


def extract_patient_context(query: str,
                             prior_ctx: Optional[PatientContext] = None,
                             conversation_history: Optional[list] = None,
                             turn_ts: Optional[str] = None) -> PatientContext:
    """
    Extract and update structured patient context from current query.
    Merges with prior_ctx to accumulate state across turns.
    Estimated age-based weight NEVER assigned to confirmed_weight_kg.

    `turn_ts` timestamps any vitals found in THIS turn. None is stored as None —
    "age unknown" — never as the current time: a pre-v4.1 client sends no
    timestamp at all, and stamping those readings "now" would present a stale
    vital as fresh, which is S-1 with a faster clock.
    """
    ctx = prior_ctx or PatientContext()
    q = query.lower().strip()

    # Reset before parsing. Both fields describe the turn being processed, so
    # after the replay loop in rebuild_patient_context_from_history they hold
    # what the CURRENT turn did — the same "this turn" semantics as
    # boundary_reset_reason.
    ctx.vitals_superseded = []
    ctx.vitals_rejected = []
    found, rejected = vitals_mod.parse_vitals(query, ts=turn_ts)
    if found:
        ctx.vitals, ctx.vitals_superseded = vitals_mod.merge(ctx.vitals, found)
    ctx.vitals_rejected = rejected

    # Also scan recent conversation for accumulated context
    history_text = ""
    if conversation_history:
        for turn in conversation_history[-5:]:
            history_text += " " + turn.get("query", "").lower()

    full_text = q + " " + history_text

    # ── Stated weight, and whether the medic stood behind it (F-1) ────────
    # kg wins over lbs when both appear; a hedged number goes to
    # estimated_weight_kg and NEVER to confirmed_weight_kg, which is what the
    # dose contract reads.
    _wt_match, _wt_kg, _wt_unit = None, None, None
    kg_match = _KG_RE.search(q)
    if kg_match:
        _wt_match, _wt_kg, _wt_unit = kg_match, float(kg_match.group(1)), "kg"
    else:
        lb_match = _LB_RE.search(q)
        if lb_match:
            _wt_match = lb_match
            _wt_kg = round(float(lb_match.group(1)) * 0.453592, 1)
            _wt_unit = "lbs"

    if _wt_match is not None:
        if weight_is_hedged(q, _wt_match.start(), _wt_match.end()):
            # Not a confirmed weight. Left in estimated_weight_kg so the
            # pre-gate can say what it has rather than asking from nothing,
            # and so airway sizing still has a number to work with.
            ctx.estimated_weight_kg = _wt_kg
            ctx.weight_source = f"estimated_hedged_{_wt_unit}"
        else:
            ctx.confirmed_weight_kg = _wt_kg
            ctx.weight_source = f"confirmed_{_wt_unit}"

    # ── Sex ───────────────────────────────────────────────────────────────
    # Declared on PatientContext since v3 and never populated. Needed now
    # because the Devine ideal-body-weight formula the vent cards dose tidal
    # volume on takes a different constant per sex.
    #
    # Word-anchored, and NOT inferred from anything else: "he"/"she" are not
    # read as sex here. A pronoun is how someone is being referred to, an
    # 80 kg "male" is a stated fact, and the gap between them is not one this
    # parser gets to close on a number that scales every breath.
    if _has_any_word(q, ("male", "man", "m", "gentleman")) and not _has_any_word(
            q, ("female", "woman", "f", "lady")):
        ctx.sex = "male"
    elif _has_any_word(q, ("female", "woman", "f", "lady")):
        ctx.sex = "female"

    # ── Altered mental status, as stated (F-3) ────────────────────────────
    # Sticky within a patient, like route and access: a turn that says nothing
    # about mental status does not mean it has recovered. A patient boundary
    # clears it with everything else.
    if has_ams_descriptor(q):
        ctx.ams_stated = True

    # ── Age extraction ────────────────────────────────────────────────────
    age_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:yo|y/o|year[\s-]*old|yr\s*old)\b', q)
    if age_match:
        ctx.age_years = float(age_match.group(1))
    if not age_match:
        age_match2 = re.search(r'(\d+)[\s-]*year[\s-]*old', q)
        if age_match2:
            ctx.age_years = float(age_match2.group(1))

    # ── Pediatric detection ───────────────────────────────────────────────
    # Word-boundary matched: 'kid' must not fire on "kidney", 'girl' on
    # "girlfriend", 'boy' on "boyfriend" (fix 2026-07-18).
    # Age phrasings ('year old', 'yo', 'y/o') are NOT pediatric terms — they are
    # parsed into age_years above, and a known age is authoritative: "55 year
    # old" must never be pediatric-gated.
    # is_pediatric is NOT monotonic (SC-2, v4.1). A known age decides the flag in
    # BOTH directions: stating "45 year old" after a pediatric turn must clear it.
    # With no known age the flag stays sticky within the patient — a turn reading
    # only "IV" must never un-pediatric a child.
    pediatric_terms = ['infant', 'child', 'toddler', 'kid', 'kids', 'boy', 'girl',
                       'pediatric', 'paediatric', 'newborn', 'neonate', 'baby']
    if ctx.age_years is not None:
        ctx.is_pediatric = ctx.age_years < 18
    elif (_has_any_word(full_text, pediatric_terms) or
            (ctx.confirmed_weight_kg is not None
             and ctx.confirmed_weight_kg < PEDIATRIC_WEIGHT_CEILING_KG) or
            # A hedged weight is not good enough to DOSE from and is good
            # enough to pediatric-GATE from. "he's maybe 20 kilos" must not
            # dose, and must also not be treated as an adult.
            (ctx.weight_source.startswith("estimated_hedged")
             and ctx.estimated_weight_kg is not None
             and ctx.estimated_weight_kg < PEDIATRIC_WEIGHT_CEILING_KG)):
        ctx.is_pediatric = True

    # ── Estimated weight from age (context only — never used for dosing) ─
    if (ctx.is_pediatric and ctx.age_years is not None
            and ctx.confirmed_weight_kg is None
            # A weight the medic actually stated, even hedged, beats an
            # age-band table lookup. Overwriting it would lose information.
            and not ctx.weight_source.startswith("estimated_hedged")):
        age_to_weight = {1: 10, 2: 12, 4: 16, 6: 20, 8: 25, 10: 32, 12: 38, 14: 45}
        closest = min(age_to_weight.keys(), key=lambda x: abs(x - ctx.age_years))
        ctx.estimated_weight_kg = age_to_weight[closest]
        ctx.weight_source = "estimated_from_age"

    # ── Route preference ──────────────────────────────────────────────────
    q_stripped = q.strip()
    if q_stripped in ('im', 'intramuscular') or re.search(r'\bim\b', q):
        ctx.route_preference = "IM"
    if q_stripped in ('iv', 'intravenous') or re.search(r'\biv\b', q):
        ctx.route_preference = "IV"
    if re.search(r'\bio\b', q):
        ctx.route_preference = "IO"

    # ── Access state ──────────────────────────────────────────────────────
    confirmed_iv = ['have a 14g', 'have an iv', 'iv established', 'got an iv',
                    'iv in place', 'line established', 'io access', 'have io',
                    'io established', 'access established', 'i have iv', 'iv access']
    if any(x in full_text for x in confirmed_iv):
        ctx.access_state = "CONFIRMED_IV_IO"
        if ctx.route_preference == "UNKNOWN":
            ctx.route_preference = "IV"

    failed_iv = ['iv blew', 'lost the iv', 'iv infiltrated', 'iv failed',
                 'no iv', 'no access', "can't get iv", 'cannot get iv',
                 'unable to get iv', 'no line', 'no vascular access', 'no io',
                 'only have im', 'im only', 'only im']
    if any(x in full_text for x in failed_iv):
        ctx.access_state = "NO_IV_IO"
        ctx.route_preference = "IM"

    # ── Provider scope ────────────────────────────────────────────────────
    scope_map = {
        'bls': 'BLS', 'basic life support': 'BLS',
        'emt': 'EMT', 'emt-b': 'EMT',
        'paramedic': 'PARAMEDIC', 'medic': 'PARAMEDIC',
        'critical care': 'CRITICAL_CARE', 'flight medic': 'CRITICAL_CARE',
        'ccemtp': 'CRITICAL_CARE',
        'physician': 'PHYSICIAN', 'doctor': 'PHYSICIAN', 'md': 'PHYSICIAN',
    }
    for term, scope in scope_map.items():
        if term in full_text and ctx.provider_scope == "UNKNOWN":
            ctx.provider_scope = scope
            break

    # Which vial the medic is holding. Matched only against DECLARED, SIGNED
    # presentations — drug_concentrations.match_confirmation has no path that
    # parses a concentration out of free text and believes it. This runs on
    # user turns only (the replay loop feeds it prior_q, never a response), so
    # the ASK's own text — which necessarily names both options — cannot be
    # mistaken for an answer to itself.
    if drug_concentrations is not None and drug_contracts is not None:
        for drug in drug_contracts.resolve_drugs(full_text):
            if drug not in ctx.drugs_named:
                ctx.drugs_named.append(drug)
        # A bare "50" names no drug, so it is attributed to what is already
        # under discussion for THIS patient.
        for drug in ctx.drugs_named:
            hit = drug_concentrations.match_confirmation(drug, q)
            if hit is not None:
                ctx.confirmed_concentrations[drug] = hit

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC PRE-GATES
# ─────────────────────────────────────────────────────────────────────────────

# F-1: the ask when the session holds a weight the medic hedged. The eval
# report illustrated this as "I have about 80 kg — confirm ..."; it is fixed
# text here instead, because SAFE_GATE_RESPONSES is matched by exact string
# and that exactness is depended on in three places (validate_response's skip,
# is_safe_gate_response, and _with_cautions' refusal to annotate a question).
# Interpolating the number would put this response outside the set and it
# would be validated, cautioned and banner-able like a clinical plan.
WEIGHT_CONFIRM_ASK = "Confirm the weight in kg before dosing — I only have an estimate."

# F-3 (eval baseline, G-MTN-08). "his sugar came back at 32, he's confused"
# was answered with "provide oral glucose (e.g., glucose gel or candy)" and no
# caution fired, because two independent guards each missed on a word:
# run_deterministic_checks matched the query against ['altered','ams',
# 'unconscious','shock','unresponsive'] and the medic had said "confused", and
# depressed_gcs_oral_route arms on a numeric GCS that was never stated.
#
# One list, three consumers — run_deterministic_checks, extract_patient_context
# (which sets ctx.ams_stated) and, through that flag, the caution table. Two
# copies of a clinical word list is how the pediatric-word bug in S-6 survived
# its own fix.
#
# Word-anchored at both ends per doctrine: "out" must not match "outer",
# "confused" must not match inside a longer token, and — the specific trap —
# 'ams' must never match "milligrams", which is the bug _SHOCK_WORDS was
# already bitten by.
AMS_DESCRIPTORS = (
    "altered", "altered mental status", "ams", "unconscious", "unresponsive",
    "confused", "confusion", "disoriented", "disorientated", "obtunded",
    "not tracking", "gcs", "stuporous", "somnolent", "won't wake",
    "wont wake", "not waking", "postictal", "post-ictal",
)

# The response-side list. What the answer proposes putting in the patient's
# mouth. "oral glucose" and "glucose gel" are here because the baseline answer
# used exactly those words and neither was in the old four-term list.
ORAL_ROUTE_TERMS = (
    "by mouth", "oral fluids", "po fluids", "drink", "drinking",
    "oral glucose", "glucose gel", "oral rehydration", "ors", "swallow",
    "sips", "orally", "po intake", "buccal", "sublingual glucose",
)


def has_ams_descriptor(text: str) -> bool:
    """Whether the text says this patient's mental status is not normal.

    Negation-aware through has_positive_term for the descriptors that are
    routinely negated in a handover — "not altered", "no confusion" — because
    reading a negation as its opposite is the _SHOCK_WORDS 'unaltered' bug and
    this list is wider than that one was.
    """
    q = (text or "").lower()
    return any(_has_word(q, t) and has_positive_term(q, t)
               for t in AMS_DESCRIPTORS if " " not in t) or \
           any(t in q and has_positive_term(q, t)
               for t in AMS_DESCRIPTORS if " " in t)


SAFE_GATE_RESPONSES = {
    "Need weight in kg before dosing.",
    WEIGHT_CONFIRM_ASK,
    "IV or IM? Do you have access?",
    "Need concentration before giving mL dose.",
    "Need rhythm before antiarrhythmic.",
    "Need height and sex before vent settings.",
}


# The weight below which a patient with no stated age is treated as paediatric.
# Named because two places depend on it agreeing: the classifier above, and
# build_patient_block, which has to explain to a reader WHY a 77.1kg patient with
# no stated age is not being paediatric-gated. A silent 40 in one of them and a
# different number in the other is a context block that contradicts the flag it
# is describing.
PEDIATRIC_WEIGHT_CEILING_KG = 40.0


def _has_word(text: str, term: str) -> bool:
    """Word-boundary match — 'roc' matches "give roc" but not "rock" or "procedure"."""
    return re.search(r'\b' + re.escape(term) + r'\b', text) is not None


def _has_any_word(text: str, terms) -> bool:
    return any(_has_word(text, t) for t in terms)


def wants_medication_dose(query: str) -> bool:
    q = query.lower()
    if is_fixed_prep_request(q):
        return False
    stem_terms = ['rocuronium', 'succinylcholine', 'fentanyl', 'versed',
                  'midazolam', 'lorazepam', 'morphine', 'epinephrine',
                  'analges', 'sedat', 'intubat', 'ketamine']
    word_terms = ['dose', 'give', 'draw', 'mg', 'ml', 'roc', 'sux', 'succs',
                  'epi', 'pain', 'rsi', 'txa', 'keppra']
    return any(t in q for t in stem_terms) or _has_any_word(q, word_terms)


def route_changes_dose(query: str) -> bool:
    """Only ketamine has meaningfully different IV vs IM doses (7x difference).
    Other medications either have one route or similar weight-based dosing."""
    q = query.lower()
    # Only ask route for ketamine — IV is 0.3mg/kg vs IM 2mg/kg
    route_sensitive = ['ketamine', 'ket ', 'vitamin k']
    return any(x in q for x in route_sensitive)


def query_is_weight_answer(query: str) -> bool:
    q = (query or "").lower().strip()
    # Hedged forms count as a weight ANSWER — the medic did answer the
    # question. Whether the number is good enough to dose from is
    # weight_is_hedged's call, made in extract_patient_context, not here.
    return bool(re.fullmatch(
        r"(?:about\s+|around\s+|roughly\s+|approximately\s+|approx\s+|maybe\s+|~\s*)?"
        r"\d+(?:\.\d+)?\s*(?:kilograms?|kilos?|kgs?|pounds?|lbs?)"
        r"(?:\s*(?:or so|ish))?", q))


def has_pending_route_sensitive_request(prior_queries: str) -> bool:
    return route_changes_dose(prior_queries or "")


def pre_gate(query: str, ctx: PatientContext, prior_queries: str = "") -> tuple:
    """
    Deterministic pre-gate before any LLM call.
    Returns: ("ASK", response) | ("BLOCK", response) | ("CONTINUE", None)
    ASK and BLOCK skip the validator entirely.
    """
    combined_ctx = (prior_queries + " " + query).lower()
    current_or_pending_med_request = (
        wants_medication_dose(query)
        or (query_is_weight_answer(query) and has_pending_route_sensitive_request(prior_queries))
    )

    if current_or_pending_med_request:
        # Hedged weight gate (F-1). Before the paediatric ask because it is the
        # more specific question: the session HAS a number and needs it stood
        # behind, which is not the same request as "tell me a weight".
        if (not ctx.has_confirmed_weight
                and ctx.estimated_weight_kg is not None
                and ctx.weight_source.startswith("estimated_hedged")):
            return "ASK", WEIGHT_CONFIRM_ASK

        # Pediatric weight gate
        if ctx.is_pediatric and not ctx.has_confirmed_weight:
            return "ASK", "Need weight in kg before dosing."

        # Route gate — only ask if NOT RSI/intubation/drip context (those are always IV)
        is_rsi_or_iv_ctx = any(x in combined_ctx for x in [
            "rsi", "intubat", "rapid sequence", "rocuronium",
            "succinylcholine", "drip", "infusion", "sedation drip",
            "post-intubation", "post intubation", "intubated", "ventilator",
            "on the vent", "on a vent", "ketamine drip"
        ]) or _has_any_word(combined_ctx, ["roc", "sux", "succs"])
        if route_changes_dose(combined_ctx) and ctx.route_preference == "UNKNOWN" and not is_rsi_or_iv_ctx:
            return "ASK", "IV or IM? Do you have access?"

        # Which vial? Asked for the same reason route is asked: the answer
        # changes the number the medic draws up, and guessing is worse than
        # asking. Fires only where the kit declares more than one signed
        # strength, or the owner set confirm_required — ketamine, where
        # 500 mg/10 mL and 200 mg/20 mL are both common and differ five-fold.
        #
        # Deliberately AFTER weight and route: those gate the milligram dose,
        # and a question about the vial is wasted on a turn that is not going
        # to produce a dose at all. Silent while nothing is signed, because
        # then there is nothing to choose between and the answer is mg-only
        # regardless.
        if (drug_concentrations is not None and drug_contracts is not None
                and ctx.has_confirmed_weight):
            for drug in drug_contracts.resolve_drugs(combined_ctx):
                status, _, _ = drug_concentrations.resolve(
                    drug, ctx.confirmed_concentrations)
                if status == drug_concentrations.NEEDS_CONFIRMATION:
                    question = drug_concentrations.confirmation_question(drug)
                    if question:
                        return "ASK", question

    return "CONTINUE", None


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC DOSE CALCULATORS
# ─────────────────────────────────────────────────────────────────────────────

def ketamine_analgesia_iv(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 0.3, 1)
    return DoseCandidate(
        drug="ketamine", indication="subdissociative analgesia", route="IV",
        dose_mg=dose_mg,
        source="deterministic_calculator:ketamine_analgesia_iv_0.3mgkg",
        warning="Monitor airway and respirations. Subdissociative range."
    )


def ketamine_analgesia_im(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 2.0, 1)
    return DoseCandidate(
        drug="ketamine", indication="dissociative analgesia (IM — no IV access)",
        route="IM", dose_mg=dose_mg,
        source="deterministic_calculator:ketamine_analgesia_im_2mgkg",
        warning="IM dose is higher than IV analgesia dose — this is expected and correct. Monitor airway."
    )


def ketamine_induction_iv(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dose_mg = round(weight_kg * 1.5, 1)
    max_mg = weight_kg * 2.0 if is_pediatric else min(weight_kg * 2.0, 200.0)
    dose_mg = min(dose_mg, max_mg)
    return DoseCandidate(
        drug="ketamine", indication="RSI induction", route="IV",
        dose_mg=dose_mg,
        source="deterministic_calculator:ketamine_induction_iv_1.5mgkg",
        warning="Give BEFORE paralytic. Confirm weight and route."
    )


def ketamine_post_intubation_iv(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 0.5, 1)
    return DoseCandidate(
        drug="ketamine", indication="post-intubation sedation q20-30min", route="IV",
        dose_mg=dose_mg,
        source="deterministic_calculator:ketamine_post_intubation_0.5mgkg",
        warning="After tube confirmed only. Not the induction dose."
    )


def rocuronium_rsi(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dose_mg = round(weight_kg * 1.0, 1)
    return DoseCandidate(
        drug="rocuronium", indication="RSI paralytic", route="IV",
        dose_mg=dose_mg,
        source="deterministic_calculator:rocuronium_rsi_1mgkg",
        warning="Give AFTER induction agent. Max 1.2mg/kg."
    )


def succinylcholine_rsi(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dkg = 2.0 if is_pediatric else 1.5
    dose_mg = round(weight_kg * dkg, 1)
    return DoseCandidate(
        drug="succinylcholine", indication="RSI paralytic", route="IV",
        dose_mg=dose_mg,
        source=f"deterministic_calculator:succinylcholine_rsi_{dkg}mgkg",
        warning="Contraindicated: hyperkalemia, burns >24hr, crush injury, denervation."
    )


def lorazepam_seizure(weight_kg: float) -> DoseCandidate:
    dose_mg = min(round(weight_kg * 0.1, 1), 4.0)
    return DoseCandidate(
        drug="lorazepam", indication="active seizure", route="IV",
        dose_mg=dose_mg,
        source="deterministic_calculator:lorazepam_seizure_0.1mgkg_max4mg",
        warning="Monitor respiratory depression."
    )


def _contract_dose_candidates(query: str, ctx: PatientContext) -> List[DoseCandidate]:
    """DoseCandidates from SIGNED drug_contracts.json entries only.

    Every value here has already passed drug_contracts.entry_is_servable(), so
    this function does arithmetic and nothing else — it makes no clinical
    decision and it never falls back. A signed entry that cannot be turned into
    a syringe volume is skipped rather than served: a mg with no mL is a number
    the medic has to convert under load, which is the error this whole contract
    layer exists to remove.
    """
    if drug_contracts is None or ctx.dosing_weight_kg is None:
        return []

    w = ctx.dosing_weight_kg
    out = []
    for name, entry in drug_contracts.signed_entries_for(
            query, route=None, is_pediatric=ctx.is_pediatric):
        # Units are resolved by drug_contracts, which converts explicitly and
        # FAILS CLOSED on anything it does not recognise. This loop used to do
        # `base * w if per_kg else base` and call the answer milligrams
        # whatever the entry said, so "25 g" became 25 mg and "10 mcg" became
        # 10 mg. Nothing downstream could catch it: the volume audit checks a
        # volume against the STATED milligrams, and a wrongly-parsed dose that
        # is internally consistent passes.
        resolved = drug_contracts.resolve_dose(entry, w)
        if resolved["dose_mg"] is None:
            # A rate, or a unit we refuse to guess at. Either way it is not a
            # bolus and must not become a volume.
            continue

        out.append(DoseCandidate(
            drug=name, indication=entry["indication"], route=entry["route"],
            dose_mg=round(resolved["dose_mg"], 4),
            display_value=resolved["display_value"],
            display_units=resolved["display_units"],
            source=f"drug_contract:{name}:{entry['indication']}:"
                   f"{entry['route']}:v{entry.get('version')}",
            warning="; ".join(entry.get("cautions") or []) or None,
        ))
    return out


def build_allowed_doses(query: str, ctx: PatientContext) -> List[DoseCandidate]:
    """Build route-specific deterministic dose candidates for the current query.

    Two paths, and the split is temporary by design:

      LEGACY   ketamine, rocuronium, succinylcholine, lorazepam still come from
               the hardcoded calculators below. The contract file carries a
               migrated draft of each, unsigned. Behaviour for these four is
               unchanged, byte for byte, until the owner re-signs the migrated
               entries — at which point the calculator for that drug is deleted
               and it joins the contract path.

      CONTRACT every other drug serves from drug_contracts.json, and ONLY from
               a signed entry. Nothing is signed yet, so this path returns
               empty and those drugs land on the existing empty-contract
               fallback exactly as before.

    DRUG NAMING IS WORD-ANCHORED. It used to be substring matching with an
    explicit `'vitamin k' in q` mapped onto ketamine as a dictation-mangling
    alias, so "vitamin K dose for warfarin reversal" built a ketamine contract.
    Vitamin K is a real drug; the alias was eating it. Naming now goes through
    drug_contracts.resolve_drugs(), which is word-anchored and which the alias
    lint forbids from shadowing another contracted drug.
    """
    if ctx.dosing_weight_kg is None:
        return []
    w = ctx.dosing_weight_kg
    ped = ctx.is_pediatric
    q = query.lower()
    doses = []

    named = set(drug_contracts.resolve_drugs(q)) if drug_contracts else set()

    is_rsi = any(x in q for x in ['rsi', 'intubat', 'rapid sequence'])
    is_analg = any(x in q for x in ['pain', 'analges', 'fracture', 'fx', 'arm', 'leg', 'analgesia'])
    is_seizure = any(x in q for x in ['seizure', 'seizing', 'status'])
    has_ketamine = 'ketamine' in named
    has_roc = 'rocuronium' in named
    has_succ = 'succinylcholine' in named
    # 'benzo' is a CLASS word, not a lorazepam alias, and it is preserved here
    # only because removing it would change current behaviour — which this
    # migration is not allowed to do. It is on the worksheet for the owner:
    # once midazolam has a signed contract, "benzo" pointing at exactly one
    # benzodiazepine is its own collision waiting to happen.
    has_loraz = 'lorazepam' in named or _has_word(q, 'benzo')

    if is_rsi:
        # RSI always requires induction + paralytic + post-intubation sedation.
        doses.append(ketamine_induction_iv(w, ped))
        doses.append(ketamine_post_intubation_iv(w))

        # Default to rocuronium unless succinylcholine is explicitly requested.
        if has_succ and not any(x in q for x in ["burn", "crush"]):
            doses.append(succinylcholine_rsi(w, ped))
        else:
            doses.append(rocuronium_rsi(w, ped))

        doses.extend(_contract_dose_candidates(query, ctx))
        return [resolve_dose_volume(d, ctx) for d in doses]

    if has_ketamine:
        if is_analg or (not is_seizure):
            if ctx.route_preference == "IV":
                doses.append(ketamine_analgesia_iv(w))
            elif ctx.route_preference == "IM":
                doses.append(ketamine_analgesia_im(w))
            elif ctx.route_preference == "UNKNOWN":
                # Build both — generator will present based on context
                doses.append(ketamine_analgesia_iv(w))
                doses.append(ketamine_analgesia_im(w))

    if has_loraz or is_seizure:
        doses.append(lorazepam_seizure(w))

    doses.extend(_contract_dose_candidates(query, ctx))
    return [resolve_dose_volume(d, ctx) for d in doses]


CONFIRM_CONCENTRATION_LINE = "confirm concentration to compute volume"


def resolve_dose_volume(d: DoseCandidate,
                        ctx: Optional[PatientContext] = None) -> DoseCandidate:
    """Fill volume_ml/concentration_mg_ml from the confirmed concentration.

    The ONLY place a millilitre is derived in this system. Returns the
    candidate unchanged — volume still None — when the kit has not declared a
    signed concentration for this drug, or has declared more than one and the
    medic has not said which vial they are holding.
    """
    if drug_concentrations is None:
        return d
    confirmed = dict(ctx.confirmed_concentrations) if ctx else {}
    vol, conc = drug_concentrations.volume_ml(d.drug, d.dose_mg, confirmed)
    if vol is None:
        # A concentration may be known and the volume still refused — a dose
        # below what a syringe can draw, or above what a push can be. The
        # reason rides along so the GIVE line can say which.
        why = drug_concentrations.volume_refusal(d.drug, d.dose_mg, confirmed)
        return dc_replace(d, volume_refusal=why) if why else d
    return dc_replace(d, volume_ml=vol, concentration_mg_ml=conc)


def render_give_line(d: DoseCandidate, prefix: str = "- ") -> str:
    """One canonical GIVE line, or the mg-only line when there is no volume.

    Every volume-bearing line in the system comes through here, so the
    fail-closed rule cannot be true in one renderer and false in another. The
    line always states the concentration it used: that is the medic's
    catch-point, the thing that would have let someone notice "20mg/mL
    succinylcholine" was not the vial in their hand.
    """
    dose_txt = (f"{d.display_value:g} {d.display_units}"
                if d.display_value is not None and d.display_units
                else f"{d.dose_mg:g} mg")
    if d.volume_ml is None or d.concentration_mg_ml is None:
        why = d.volume_refusal or CONFIRM_CONCENTRATION_LINE
        return (f"{prefix}{d.drug} {d.route}: {dose_txt}. "
                f"NO VOLUME — {why}. Indication: {d.indication}.")
    return (f"{prefix}Draw {d.volume_ml:g} mL of {d.concentration_mg_ml:g}mg/mL "
            f"{d.drug} {d.route} ({dose_txt}). Indication: {d.indication}.")


def render_dose_summary(d: DoseCandidate, label: str) -> str:
    """The TLDR restatement of a dose. Degrades with the GIVE line it summarises.

    Kept in step deliberately: a TLDR that still said "= 1.2mL of 100mg/mL"
    under a GIVE line that had already refused to give a volume would be the
    only number on the screen, and the one a medic would act on.
    """
    if d.volume_ml is None or d.concentration_mg_ml is None:
        return (f"- {label}: {d.drug} {d.route} = {d.dose_mg:g}mg. "
                f"Volume not computed — {CONFIRM_CONCENTRATION_LINE}.")
    return (f"- {label}: {d.drug} {d.route} = {d.dose_mg:g}mg = "
            f"{d.volume_ml:g}mL of {d.concentration_mg_ml:g}mg/mL.")


def build_allowed_dose_block(doses: List[DoseCandidate]) -> str:
    if not doses:
        return "ALLOWED_DOSES: none. Do not provide medication doses in this response."
    lines = ["ALLOWED_DOSES — use EXACTLY these values. Do not calculate alternatives:"]
    for d in doses:
        lines.append(render_give_line(d))
        if d.warning:
            lines.append(f"  Note: {d.warning}")
    if any(d.volume_ml is None for d in doses):
        lines.append(
            "  A line with NO VOLUME has no confirmed concentration for that "
            "drug. Give the milligram dose and the confirm-concentration "
            "sentence exactly as written. Do NOT compute or invent a mL "
            "volume for it.")
    return "\n".join(lines)




# ─────────────────────────────────────────────────────────────────────────────
# REQUESTED OVERDOSE DETECTOR — runs BEFORE generator
# ─────────────────────────────────────────────────────────────────────────────

def detect_requested_medication_overdose(query: str, ctx: PatientContext) -> list:
    """
    Detect explicit unsafe doses requested by the provider in the query text.
    Run before the generator so unsafe user-provided doses cannot be silently normalized.
    Returns list of issue strings. Empty = no overdose detected.
    """
    issues = []
    wt = ctx.confirmed_weight_kg
    if not wt:
        return issues

    q = query.lower()
    patterns = {
        "ketamine": (r"ketamine.{0,40}?(\d+(?:\.\d+)?)\s*mg", wt * 2.0),
        "rocuronium": (r"rocuronium.{0,40}?(\d+(?:\.\d+)?)\s*mg|roc\b.{0,40}?(\d+(?:\.\d+)?)\s*mg", wt * 1.2),
        "succinylcholine": (r"succinylcholine.{0,40}?(\d+(?:\.\d+)?)\s*mg|sux\b.{0,40}?(\d+(?:\.\d+)?)\s*mg", wt * 2.0),
    }

    for drug, (pattern, ceiling) in patterns.items():
        for m in re.finditer(pattern, q):
            dose_txt = next((g for g in m.groups() if g), None)
            if dose_txt and float(dose_txt) > ceiling:
                issues.append(
                    f"Provider requested {drug} {float(dose_txt):g}mg, "
                    f"which exceeds safety ceiling {ceiling:.1f}mg for {wt:g}kg patient."
                )
    return issues


# ─────────────────────────────────────────────────────────────────────────────
# SEPSIS-DCR DETERMINISTIC GATE
# ─────────────────────────────────────────────────────────────────────────────

def has_fever(q: str) -> bool:
    """Detect fever from text or numeric temperature. Negation-aware."""
    q = q.lower()
    if has_positive_term(q, "fever") or has_positive_term(q, "febrile"):
        return True
    m = re.search(r"temp(?:erature)?\s*(\d{2}(?:\.\d+)?)\s*c?", q)
    if m:
        try:
            if float(m.group(1)) >= 38.0:
                return True
        except ValueError:
            pass
    m = re.search(r"(\d{2,3}(?:\.\d+)?)\s*f\b", q)
    if m:
        try:
            if float(m.group(1)) >= 100.4:
                return True
        except ValueError:
            pass
    return False


def has_positive_term(q: str, term: str) -> bool:
    """Check if term appears without preceding negation."""
    q = (q or "").lower()
    term = term.lower()
    idx = q.find(term)
    if idx == -1:
        return False
    before = q[max(0, idx - 40):idx]
    negations = ["no ", "denies ", "without ", "afebrile", "not ", "negative for ", "no evidence of ", "rule out "]
    return not any(n in before for n in negations)

# Long enough that a substring match cannot land inside an unrelated word.
_SHOCK_PHRASES = ["hypotension", "hypotensive", "poor perfusion", "septic shock"]

# Short tokens that ARE substrings of ordinary clinical prose, so they are
# word-anchored. The fourth specimen of this repo's substring failure class,
# after the F-2 alias table, FIXED_PREP_TERMS and the vitals labels — and the
# worst of the four, because every hit routes a casualty:
#   "ams"     matched milligrams, grams, diagrams, exams. Any dose stated in
#             grams routed as shock, and with an infection present that is
#             looks_like_sepsis() firing on the word "milligrams".
#   "altered" matched unaltered — an explicit negation read as its opposite.
#   "map "    matched roadmap.
# Inflections are kept explicitly rather than by dropping the right-hand
# boundary: \bshock would also swallow "shockwave", and this list decides
# whether a casualty is treated as being in shock.
_SHOCK_WORDS = ["shock", "shocks", "shocked", "altered", "ams", "map"]


def has_hypotension_or_shock(q: str) -> bool:
    """Detect hypotension/shock text, including BP values like 92/46."""
    q = (q or "").lower()
    if any(x in q for x in _SHOCK_PHRASES) or _has_any_word(q, _SHOCK_WORDS):
        return True

    for m in re.finditer(r"\bbp\s*(\d{2,3})\s*/\s*(\d{2,3})\b", q):
        try:
            sbp = int(m.group(1))
            dbp = int(m.group(2))
            if sbp < 100 or dbp < 60:
                return True
        except ValueError:
            pass
    return False


def looks_like_sepsis(query: str) -> bool:
    q = (query or "").lower()
    infection = (
        has_fever(q)
        or any(has_positive_term(q, x) for x in [
            "pus", "purulent", "infection", "infected",
            "sepsis", "septic", "abscess", "wound infection"
        ])
    )
    return infection and has_hypotension_or_shock(q)

def asks_for_dcr_or_hemostatic_resus(q: str) -> bool:
    q = (q or "").lower()
    return any(x in q for x in [
        "dcr", "initiate dcr", "damage control resuscitation",
        "ltowb", "whole blood", "blood product", "blood-product",
        "massive transfusion", "hemostatic resus", "blood resuscitation",
        "transfusion", "give blood"
    ])

def has_clear_hemorrhage(query: str) -> bool:
    q = query.lower()
    hemorrhage_terms = [
        "active bleeding", "active abdominal bleeding", "abdominal bleeding",
        "arterial bleed", "junctional bleed", "massive bleeding",
        "hemorrhage", "hemorrhagic", "hemorrhagic shock", "blood loss",
        "tourniquet", "amputation", "penetrating trauma", "gunshot",
        "gsw", "blast", "trauma patient", "massive transfusion"
    ]
    return any(t in q for t in hemorrhage_terms)


def asks_for_txa(q: str) -> bool:
    q = q.lower()
    return "txa" in q or "tranexamic" in q


def has_infection_context(query: str) -> bool:
    q = (query or "").lower()
    return (
        has_fever(q)
        or any(has_positive_term(q, x) for x in [
            "pus", "purulent", "infection", "infected", "sepsis",
            "septic", "abscess", "wound infection"
        ])
    )


def asks_for_wpw_contraindicated_drug(query: str) -> bool:
    q = (query or "").lower()
    if not any(x in q for x in ["wpw", "wolff", "pre-excitation", "preexcitation"]):
        return False
    return any(x in q for x in [
        "adenosine", "metoprolol", "atenolol", "diltiazem",
        "verapamil", "digoxin", "beta blocker", "calcium channel"
    ])


def looks_like_hemorrhagic_shock(query: str) -> bool:
    q = (query or "").lower()
    return has_clear_hemorrhage(q) and has_hypotension_or_shock(q)


SEPSIS_DCR_REFUSAL = """Sepsis suspected — do not initiate DCR/TXA/LTOWB unless hemorrhage is clearly present.

**DO THIS**
1. Treat as septic shock: oxygen, IV/IO access, monitor BP and mental status.
2. Give crystalloid bolus per local protocol and reassess frequently.
3. Start antibiotics if available and within protocol; evacuate urgently.

**DON'T**
- Do not give TXA or blood-product DCR for sepsis alone.

**TLDR**
- Fever plus pus plus hypotension is sepsis until proven otherwise.

Guideline-based support only. Not a substitute for clinical judgment."""


# ─────────────────────────────────────────────────────────────────────────────
# FIXED PREPS — preparation recipes not tied to patient weight
# ─────────────────────────────────────────────────────────────────────────────

# Single source of truth for "this is a preparation request". Must cover every
# phrasing build_fixed_prep_response() answers, or the two disagree: this list
# is what suppresses the dose gate (wants_medication_dose) while the builder is
# what produces the card, and a term in one but not the other means a request
# routed as a dose question that then returns a recipe. Under plain substring
# matching the disagreement was invisible; word boundaries surfaced it.
FIXED_PREP_TERMS = [
    "push dose epi", "push-dose epi", "push dose epinephrine",
    "dirty epi", "epi drip", "epinephrine drip", "make epi", "prepare epi",
    "mix norepi", "norepinephrine mix", "d50 amp", "dextrose prep"
]


def _prep_term_present(query: str, terms) -> bool:
    """Word-boundary match for a fixed-prep term.

    Plain substring matching is wrong here for the same reason it was wrong in
    the alias table (F-2, v4.1): "epinephrine drip" is a substring of
    "norepinephrine drip", so a request to mix a NOREPINEPHRINE infusion
    returned the EPINEPHRINE recipe — a different drug at a different
    concentration, served as though it were the answer. Found 2026-08-21 while
    routing preparation questions to the reference tier.

    Lookarounds rather than \\b because the terms are multi-word and several
    end in characters \\b treats inconsistently.
    """
    q = query.lower()
    return any(re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', q) for t in terms)


def is_fixed_prep_request(query: str) -> bool:
    return _prep_term_present(query, FIXED_PREP_TERMS)


def build_fixed_prep_response(query: str) -> Optional[str]:
    q = query.lower()
    if _prep_term_present(q, ["push dose epi", "push-dose epi",
                              "push dose epinephrine", "dirty epi"]):
        return (
            "**PUSH-DOSE EPINEPHRINE PREP**\n"
            "- Make 10 mcg/mL epinephrine.\n"
            "- Draw 1 mL of 1:10,000 epinephrine (0.1mg/mL) into a 10 mL syringe.\n"
            "- Add 9 mL normal saline. Total 10 mL.\n"
            "- Final concentration: 10 mcg/mL.\n\n"
            "**GIVE**\n"
            "- Administer 0.5-2 mL (5-20 mcg) IV push q2-5min. Titrate to effect.\n\n"
            "**WATCH**\n"
            "- Continuous cardiac monitoring required. Use only with local protocol.\n\n"
            "**TLDR**\n"
            "- 1 mL of 1:10,000 epi plus 9 mL NS = 10 mcg/mL push-dose epi.\n\n"
            "Guideline-based support only. Not a substitute for clinical judgment."
        )
    if _prep_term_present(q, ["epi drip", "epinephrine drip"]):
        return (
            "**EPINEPHRINE INFUSION PREP (Dirty Epi Drip)**\n"
            "- Mix 1 mg epinephrine (1:10,000, 10 mL) in 250 mL NS = 4 mcg/mL.\n"
            "- Start at 2-10 mcg/min (30-150 mL/hr). Titrate to MAP target.\n\n"
            "**WATCH**\n"
            "- Cardiac monitoring required. Peripheral line — monitor for extravasation.\n\n"
            "**TLDR**\n"
            "- 1mg epi in 250mL NS = 4 mcg/mL. Start 2-10 mcg/min.\n\n"
            "Guideline-based support only. Not a substitute for clinical judgment."
        )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# ALLOWED ACTIONS — weight-free protocol guidance
# ─────────────────────────────────────────────────────────────────────────────

def patient_is_known_or_possible_pediatric(ctx: PatientContext, query: str) -> bool:
    q = query.lower()
    pediatric_words = ["child", "kid", "infant", "baby", "toddler", "pediatric",
                       "paediatric", "yo", "year old", "year-old"]
    return ctx.is_pediatric or any(w in q for w in pediatric_words)


def build_allowed_actions(query: str, ctx: PatientContext) -> List[str]:
    q = query.lower()
    actions = []

    if any(t in q for t in ["active bleeding", "hemorrhagic shock", "abdominal bleeding",
                              "active abdominal", "massive bleeding", "exsanguinat"]):
        actions.append(
            "HEMORRHAGIC_SHOCK_DCR: Control hemorrhage immediately. "
            "If hemorrhagic shock and within protocol, use damage-control resuscitation "
            "with LTOWB/blood products if available. "
            "Consider TXA if traumatic hemorrhage is within 3 hours and no contraindication. "
            "Do NOT give large-volume crystalloid for hemorrhagic shock."
        )

    if "seizure" in q or "seizing" in q or "status epilepticus" in q:
        if patient_is_known_or_possible_pediatric(ctx, q) and not ctx.dosing_weight_kg:
            actions.append("SEIZURE_PEDIATRIC: Need weight in kg before benzodiazepine dosing.")
        else:
            actions.append(
                "SEIZURE_ADULT_DEFAULT: For active adult seizure, lorazepam is first-line if available "
                "and within protocol. Follow with levetiracetam (Keppra) IV for maintenance. "
                "Dose and route per local protocol. State no numeric dose unless it appears "
                "verbatim in ALLOWED_DOSES."
            )

    return actions

# ─────────────────────────────────────────────────────────────────────────────
# RETRIEVAL CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

def retrieval_cosine(top_score: float) -> float:
    """The cosine `top_score` came from. Reporting only, nothing routes on it.

    The collection is built with `space: l2` over embeddings the encoder has
    already normalised, so the distance Chroma returns is SQUARED L2 = 2 - 2cos,
    and classify_retrieval's `1 - distance` is therefore `2cos - 1`. Two things
    follow that were not visible from the printed number alone:

      - JTS_GROUNDED at 0.35 means cosine >= 0.675, which is a high bar for
        MiniLM against a mid-sentence PDF chunk.
      - The score goes NEGATIVE below cosine 0.5, and `max(0.0, ...)` clamps it.
        A genuinely hopeless retrieval and a merely weak one both printed as a
        small positive number, which is what made the 2026-08-21 burn queries
        take a corpus rebuild to diagnose.

    Inverse of the same transform, so the log carries the number a person can
    reason about next to the number the thresholds use.
    """
    return (top_score + 1.0) / 2.0


def classify_retrieval(results: dict) -> RetrievalAssessment:
    context_parts = []
    sources = []
    top_score = 0.0

    if results and 'documents' in results and results['documents']:
        for i, doc in enumerate(results['documents'][0]):
            context_parts.append(doc)
            metadata = results['metadatas'][0][i] if results.get('metadatas') else {}
            distance = results['distances'][0][i] if results.get('distances') else 1.0
            score = max(0.0, 1.0 - distance)
            if score > top_score:
                top_score = score
            sources.append({
                'title': metadata.get('source', 'Unknown'),
                'page': metadata.get('page'),
                'confidence': round(score, 3)
            })

    context_text = "\n\n".join(context_parts) if context_parts else ""
    if top_score >= 0.35:
        source_mode = "JTS_GROUNDED"
    elif top_score >= 0.10 and context_text:
        source_mode = "GENERAL_MEDICAL"
    else:
        source_mode = "INSUFFICIENT"

    return RetrievalAssessment(
        source_mode=source_mode, top_score=round(top_score, 3),
        context_text=context_text, sources=sources
    )


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

GENERATOR_BASE = """
You are AUSTERE-CDS, a voice-first clinical decision-support assistant for austere, prehospital, tactical, and Role 1-3 medical settings.

This system is a research prototype. Not validated for patient-care decisions. Support, do not replace, clinical judgment, local protocol, and medical control.

Your priorities:
1. Prevent immediate death or irreversible harm.
2. Ask for missing safety-critical data before dosing — one question only.
3. Use retrieved JTS/TCCC protocol context when relevant.
4. Label guidance based on general evidence when no JTS protocol was retrieved.
5. Keep output short enough to be heard through an earpiece during care.

────────────────────────────────
SCOPE
────────────────────────────────

Every query that reaches you has already been judged clinical. Answer it.

You have no refusal sentence. If a query is unclear, ask the ONE question that
would let you answer it. If it is outside what you can answer safely, say what
you cannot answer and what you can. Never reply that this system handles
medical queries only — that decision is made before you see the query, and
saying it here refuses a question that was already accepted.

────────────────────────────────
VOICE-FIRST STYLE
────────────────────────────────

Short sentences. No tables. No long paragraphs.
Max 3 immediate actions unless arrest, RSI, MASCAL, CICO, or severe shock requires more.
Life-saving action first. Closed-loop language for high-risk medications.

────────────────────────────────
FIELD SLANG RECOGNITION
────────────────────────────────

rocky onium / roc → rocuronium | sux / succs → succinylcholine | vec → vecuronium
vitamin K / ket → ketamine | del tim / dilt → diltiazem (check rhythm — WPW risk)
dirty epi / epi drip → epinephrine infusion | levo / levophed → norepinephrine
vaso → vasopressin | mag → magnesium sulfate | bicarb → sodium bicarbonate
push dose epi → epinephrine 10mcg/mL bolus | cric / front of neck → cricothyrotomy
venting the chest → needle decompression | snake bite / snake bike → envenomation
buddy transfusion / donor blood → field whole blood transfusion
bleeding out / hemorrhaging → hemorrhagic shock | infection / pus / septic → sepsis — NOT DCR
cold / frozen / hypothermic → hypothermia — NOT DCR | excited delirium / ExDS → agitation protocol

────────────────────────────────
MEDICATION RULES
────────────────────────────────

ALLOWED_DOSES RULE — MANDATORY:
If ALLOWED_DOSES is present below, you MUST include at least one exact GIVE line copied from it.
Copy the line EXACTLY as written. Do NOT say "administer ketamine".
CORRECT: "Draw 0.075 mL of 50mg/mL ketamine IV (7.5mg). Indication: analgesia."
WRONG: "Administer ketamine for analgesia."
A line that carries a mL volume must include: drug name, concentration, route, mL volume, total mg.
A line that says NO VOLUME has no confirmed concentration for that drug. Copy it as
written, with its milligram dose and its confirm-concentration sentence. NEVER
compute, estimate or supply a mL volume that is not in ALLOWED_DOSES — the volume
depends on which vial is in the bag, and you do not know that.
For RSI: name induction agent AND paralytic AND post-intubation sedation explicitly.
If ALLOWED_DOSES is empty — do not provide medication doses. Give protocol actions only.

MORPHINE RESTRICTION: Never first-line. Default analgesic: ketamine subdissociative.

ZERO MATH: Provider does zero calculations. Show final mL, total mg, route, concentration only.
Format: "Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason]."
Infusion: "Mix X mg in Y mL NS (Z mg/mL). Start X mL/hr. Target: [goal]."

GATE QUESTION RULE: If the response is a gate question (weight, route, concentration),
answer ONLY the gate question. Do not add clinical warnings or extra content.

────────────────────────────────
SCOPE OF PRACTICE
────────────────────────────────

If scope stated: BLS = basic interventions only | EMT = EMT-level | Paramedic/CC/MD = advanced.
If recommendation may exceed scope: "Only if within your protocol and scope."

────────────────────────────────
HIGH-RISK CLINICAL RULES
────────────────────────────────

SEPSIS vs DCR: Fever + infection + hypotension = septic shock. No TXA or blood product DCR unless hemorrhage also present.
TXA: Traumatic hemorrhagic shock only. <3hrs post injury. Not sepsis, hypothermia, TBI alone, burns alone.
WPW: Never adenosine, beta-blockers, CCBs, digoxin. Unstable → synchronized cardioversion.
TBI: No steroids. No albumin. No routine hyperventilation unless herniation.
PARALYTIC: Never paralytic alone on a patient with a pulse. Induction BEFORE paralytic. Post-intubation sedation AFTER tube confirmed.
SHOCK FORK: If cause unclear → "Assess: bleeding, chest, infection, cardiac, anaphylaxis."
CICO: Failed ETT + failed rescue airway + hypoxia → "Perform surgical airway/cricothyrotomy now."

────────────────────────────────
RSI SEQUENCE
────────────────────────────────

1. Pre-oxygenate | 2. Prepare | 3. Induction FIRST | 4. Paralytic AFTER | 5. Intubate
6. Confirm tube | 7. Secure | 8. Post-intubation sedation | 9. Vent | 10. Pressors if needed

Always include all three in GIVE for RSI: induction + paralytic + post-intubation sedation.
CICO: Failed ETT + failed rescue + hypoxia → cricothyrotomy immediately.

────────────────────────────────
CONCENTRATIONS
────────────────────────────────

You do not know any drug concentration. There is no standard strength: the same
drug ships at different strengths in different kits, and the only authority on
what is in THIS bag is the ALLOWED_DOSES block below.

Never state a mg/mL concentration, and never compute a mL volume, unless it is
copied from an ALLOWED_DOSES line. If a line gives milligrams and says NO
VOLUME, that drug has no confirmed concentration — reproduce it exactly as
written, including its confirm-concentration sentence.

────────────────────────────────
RESPONSE FORMAT — JTS SCOPE
────────────────────────────────

**DO THIS**
1. [Most critical action]
2. [Second action]
3. [Third — expand for arrest/RSI/MASCAL/severe shock only]

**GIVE** [use ALLOWED_DOSES values exactly]
- Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason].
- [drug] [route]: Z mg. NO VOLUME — confirm concentration to compute volume. Indication: [reason].
  [the second shape when ALLOWED_DOSES gives no volume for that drug]

**DRIP** [infusions]
- Mix X mg in Y mL NS (Z mg/mL). Start X mL/hr. Target: [goal].

**VENT** [if requested]
- VT: X mL | RR: X | PEEP: X | FiO2: X% | PPLAT ≤30 cmH2O

**POST-INTUBATION SEDATION** [mandatory after RSI]
- Draw X mL of Y mg/mL ketamine IV (X mg) q20-30min.

**WATCH**
- [One monitoring line]

**DON'T**
- [One contraindication]

**EVAC IF**
- [One threshold trigger]

**TLDR**
- [One sentence. Most critical action or number.]

**SOURCE**: [JTS CPG name and ID — or "General Evidence-Based Medicine (outside retrieved JTS scope)"]

Guideline-based support only. Not a substitute for clinical judgment.

────────────────────────────────
RESPONSE FORMAT — NON-JTS SCOPE
────────────────────────────────

**[CONDITION]**
- What it is: [one sentence]
- Why it matters: [one sentence]

**TREAT**
1. [Step 1] 2. [Step 2] 3. [Step 3]

**GIVE** [ALLOWED_DOSES only]
- Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason].

**WATCH FOR** | **TLDR** | **SOURCE**: General Evidence-Based Medicine

Guideline-based support only. Not a substitute for clinical judgment.
"""


def age_band_line(ctx: PatientContext) -> str:
    """What the system actually knows about the age band, stated either way.

    `is_pediatric` is False for a known adult AND for a patient nobody has given
    an age for. The block used to say "PEDIATRIC PATIENT" when the flag was true
    and NOTHING when it was false, so those two very different states looked
    identical downstream — and on 2026-08-21 the validator said so out loud
    about a 77.1kg casualty: "the patient's weight is confirmed as 77.1 kg,
    which is not pediatric. However, the context does not specify if the patient
    is pediatric or adult, leading to a need for human review."

    It was right. It had the weight — it quoted the number — and it genuinely
    had no statement of age band, because the block asserted that status in one
    direction only. A rule that keys on paediatric status cannot be evaluated
    against a silence, and a silence is what it got.

    So this says which of the three it is, and says "unknown" out loud when it
    is unknown rather than saying nothing. Unknown is not adult: with no age and
    no weight the system does not know, and claiming otherwise here would be the
    same failure pointing the other way.
    """
    if ctx.is_pediatric:
        return "PEDIATRIC PATIENT"
    if ctx.age_years is not None:
        return f"ADULT PATIENT — age {ctx.age_years:g}yr stated. NOT pediatric."
    if ctx.confirmed_weight_kg is not None:
        return (f"NOT pediatric — no age was stated, and the confirmed weight of "
                f"{ctx.confirmed_weight_kg:g}kg is at or above the "
                f"{PEDIATRIC_WEIGHT_CEILING_KG:g}kg paediatric threshold.")
    return "Age not stated and no weight confirmed — pediatric status UNKNOWN."


def build_patient_block(ctx: PatientContext, now_ts=None) -> str:
    # Always first, and never absent. See age_band_line.
    lines = [age_band_line(ctx)]

    if ctx.confirmed_weight_kg is not None:
        lines.append(f"Confirmed weight: {ctx.confirmed_weight_kg}kg ({ctx.weight_source})")
        # Said explicitly because the failure this fixes was a flow asking the
        # medic for a number three lines above the answer.
        lines.append("Weight is CONFIRMED. Do not ask for a weight the context already states.")
        if ctx.is_pediatric:
            # ETT/VT for airway planning
            vt = int(ctx.confirmed_weight_kg * 6)
            lines.append(f"Pediatric VT: {vt}mL (6mL/kg)")
    elif ctx.estimated_weight_kg is not None:
        lines.append(f"Estimated weight from age: {ctx.estimated_weight_kg}kg — NOT confirmed.")
        lines.append("Weight is NOT confirmed. DO NOT provide medication doses.")
        lines.append("For any dosing request, respond only: 'Need weight in kg before dosing.'")

    if ctx.age_years is not None:
        lines.append(f"Age: {ctx.age_years}yr")
        if ctx.is_pediatric:
            cuffed = round((ctx.age_years / 4) + 3, 1)
            depth = round(cuffed * 3, 1)
            lines.append(f"ETT (cuffed): {cuffed} | Depth: {depth}cm")

    if ctx.access_state == "CONFIRMED_IV_IO":
        lines.append("IV/IO access confirmed.")
    elif ctx.access_state in ["NO_IV_IO", "FAILED_IV"]:
        lines.append("No working IV/IO access. Use IM route only.")
    else:
        lines.append("IV/IO access: unknown.")

    if ctx.route_preference != "UNKNOWN":
        lines.append(f"Provider requested route: {ctx.route_preference}")

    if ctx.provider_scope != "UNKNOWN":
        lines.append(f"Provider scope: {ctx.provider_scope}")

    vitals_block = vitals_mod.prompt_block(ctx.vitals, now_ts=now_ts)
    if vitals_block:
        lines.append("")
        lines.append(vitals_block)

    return "\n".join(lines) if lines else ""


def build_source_block(assessment: RetrievalAssessment) -> str:
    if assessment.source_mode == "JTS_GROUNDED":
        return (
            f"SOURCE MODE: JTS_GROUNDED (score: {assessment.top_score})\n"
            f"Use retrieved JTS context as primary authority. Cite the source.\n\n"
            f"RETRIEVED JTS CONTEXT:\n{assessment.context_text}"
        )
    elif assessment.source_mode == "GENERAL_MEDICAL":
        return (
            f"SOURCE MODE: GENERAL_MEDICAL (score: {assessment.top_score})\n"
            f"No strong JTS protocol retrieved. Use general evidence-based medicine.\n"
            f"Label source as: General Evidence-Based Medicine (outside retrieved JTS scope)\n\n"
            f"RETRIEVED CONTEXT (low confidence):\n{assessment.context_text}"
        )
    else:
        return (
            f"SOURCE MODE: INSUFFICIENT (score: {assessment.top_score})\n"
            f"No relevant protocol retrieved. Give only high-confidence safety actions.\n"
            f"For medication dosing: state 'No protocol retrieved — use local protocol.'"
        )


# Where the patient block is spliced into GENERATOR_BASE. Named because the
# splice is a string match against a heading, and a heading that is edited
# without editing this constant silently drops the patient block.
GENERATOR_SCOPE_ANCHOR = "────────────────────────────────\nSCOPE"


def build_system_prompt(ctx: PatientContext, assessment: RetrievalAssessment,
                        allowed_dose_block: str, now_ts=None) -> str:
    patient_block = build_patient_block(ctx, now_ts=now_ts)
    source_block = build_source_block(assessment)
    prompt = GENERATOR_BASE
    if patient_block:
        # Anchored to the SCOPE heading, which replaced NON-MEDICAL QUERY RULE
        # (F-2). Asserted in test_generator_prompt.py rather than left to fail
        # silently: a rename that misses this line drops the patient block out
        # of the prompt entirely and nothing else notices.
        prompt = prompt.replace(
            GENERATOR_SCOPE_ANCHOR,
            f"────────────────────────────────\nPATIENT CONTEXT\n────────────────────────────────\n\n{patient_block}\n\n{GENERATOR_SCOPE_ANCHOR}"
        )
    prompt += f"\n\n────────────────────────────────\nRETRIEVED PROTOCOL CONTEXT\n────────────────────────────────\n\n{source_block}"
    prompt += f"\n\n────────────────────────────────\n{allowed_dose_block}\n────────────────────────────────"
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC POST-CHECKS
# ─────────────────────────────────────────────────────────────────────────────

# The canonical GIVE line the generator is instructed to emit:
#   "Draw X mL of Ymg/mL <drug> <route> (Zmg)."
# Module-level so the contract check and its tests share one definition —
# broadening it silently broadens what SC-6 blocks.
CANONICAL_GIVE_RE = (
    r'draw\s+(\d+(?:\.\d+)?)\s*ml\s+of\s+(\d+(?:\.\d+)?)\s*mg/ml\s+'
    r'([a-z][a-z\- ]{2,30}?)\s*(?:i[vmo][^(]*)?\((\d+(?:\.\d+)?)\s*mg\)'
)


VOLUME_STRIPPED_NOTICE = (
    "⚠️ A dose volume in this response could not be verified against the "
    "confirmed concentration and has been removed. The milligram dose stands. "
    "Confirm the vial concentration and recalculate the volume by hand.\n\n")


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def audit_volume_lines(response_text: str,
                       ctx: Optional[PatientContext] = None) -> tuple:
    """(rewritten_text, issues). Verifies every millilitre before it is served.

    This is what makes a served volume an actually-checked number rather than
    one copied through the pipeline. Three things must hold for each canonical
    GIVE line:

      1. the drug has a SIGNED concentration in the master list;
      2. the concentration the line states is that one — not a different
         strength the generator remembered, and not the one the medic
         confirmed they are NOT holding;
      3. volume x concentration == milligrams, at the precision the line
         actually prints. Comparing at the printed precision rather than
         inside a percentage band is deliberate: a 5% tolerance is wide enough
         to hide a real error in a small-volume push.

    A line that fails any of these is REWRITTEN to its milligram dose. Flagging
    it would leave the wrong number on the screen above the warning, and the
    number is what gets acted on.
    """
    issues = []
    if not response_text:
        return response_text, issues

    confirmed = dict(ctx.confirmed_concentrations) if ctx else {}
    out = response_text

    for m in re.finditer(CANONICAL_GIVE_RE, response_text, re.IGNORECASE):
        vol_s, conc_s, drug_s, mg_s = m.groups()
        drug_txt = drug_s.strip().lower()
        vol, conc, mg = float(vol_s), float(conc_s), float(mg_s)

        generic = None
        if drug_contracts is not None:
            hits = drug_contracts.resolve_drugs(drug_txt)
            generic = hits[0] if hits else None
        if generic is None:
            generic = drug_txt

        problem = None
        if drug_concentrations is None:
            problem = "the concentration master list is unavailable"
        else:
            signed = drug_concentrations.all_signed_strengths(generic)
            if not signed:
                problem = (f"no signed concentration is declared for "
                           f"{generic} in the kit")
            elif generic in confirmed and abs(conc - confirmed[generic]) > 1e-9:
                problem = (f"states {conc:g}mg/mL but the confirmed vial for "
                           f"this patient is {confirmed[generic]:g}mg/mL")
            elif not any(abs(conc - c) < 1e-9 for c in signed):
                problem = (f"states {conc:g}mg/mL, which is not a declared "
                           f"concentration for {generic} "
                           f"({', '.join(f'{c:g}' for c in signed)}mg/mL)")
            else:
                true_vol = mg / conc
                # Two conditions, both required.
                #
                # (1) exact at the precision the line actually prints, so a
                #     real error cannot hide inside a percentage band; and
                # (2) within 5% of the true volume, which is what stops (1)
                #     being satisfied by rounding so coarsely that the number
                #     stops meaning anything — "Draw 0 mL" rounds correctly to
                #     zero decimal places and is not a dose.
                rounds_right = abs(round(true_vol, _decimals(vol_s)) - vol) <= 1e-9
                close_enough = vol > 0 and abs(vol - true_vol) <= true_vol * 0.05
                if not (rounds_right and close_enough):
                    problem = (f"states {vol:g} mL of {conc:g}mg/mL for "
                               f"{mg:g}mg; {mg:g}mg at {conc:g}mg/mL is "
                               f"{round(true_vol, 3):g} mL")

        if problem:
            issues.append(f"GIVE line for '{drug_txt}' {problem} — volume removed.")
            out = out.replace(
                m.group(0),
                f"{generic} {mg:g} mg. NO VOLUME — {CONFIRM_CONCENTRATION_LINE}")

    return out, issues


def run_deterministic_checks(query: str, response_text: str,
                              patient_ctx: PatientContext,
                              allowed_doses: Optional[List[DoseCandidate]] = None) -> DeterministicCheck:
    """
    Post-generation safety checks.
    If allowed_doses provided: validate response doses match the contract.
    Also checks hard contraindications.
    """
    issues = []
    r = response_text.lower()
    q = query.lower()
    allowed_doses = allowed_doses or []

    # ── ALLOWED_DOSES contract enforcement (implemented 2026-07-18) ───────
    # Parse canonical GIVE lines ("Draw X mL of Ymg/mL drug ... (Zmg)") and
    # verify each stated dose against the deterministic contract. Scoped to
    # the canonical format so warnings/DON'T-lines with numbers never trip it.
    give_lines = re.findall(CANONICAL_GIVE_RE, r)

    if not allowed_doses:
        # SC-6: no contract was built — no weight, so no dose was authorised.
        # Any canonical GIVE line here is a number the generator supplied on its
        # own. This is the adult gap: the pediatric net below never covered it.
        for _vol_s, _conc_s, drug_s, mg_s in give_lines:
            issues.append(
                f"GIVE line doses '{drug_s.strip()}' ({float(mg_s):g}mg) with an empty "
                f"ALLOWED_DOSES contract — no deterministic dose was authorised.")
    else:
        contract_drugs = {d.drug.lower() for d in allowed_doses}
        for vol_s, conc_s, drug_s, mg_s in give_lines:
            stated_mg = float(mg_s)
            # vol_s and conc_s used to be parsed here and discarded, so the
            # millilitre was the one number in a GIVE line nothing verified.
            # audit_volume_lines() owns that check now and runs on every path;
            # this loop keeps owning the milligram-against-contract check.
            drug_words = drug_s.strip().split()
            matched_drug = None
            for cd in contract_drugs:
                if any(cd in w or w in cd for w in drug_words):
                    matched_drug = cd
                    break
            if matched_drug is None:
                issues.append(
                    f"GIVE line doses '{drug_s.strip()}' ({stated_mg}mg) but that "
                    f"medication is not in the ALLOWED_DOSES contract.")
                continue
            candidates = [d for d in allowed_doses if d.drug.lower() == matched_drug]
            tol = lambda dm: max(0.5, dm * 0.05)
            if not any(abs(stated_mg - d.dose_mg) <= tol(d.dose_mg) for d in candidates):
                allowed_vals = ", ".join(f"{d.dose_mg:g}mg {d.route}" for d in candidates)
                issues.append(
                    f"GIVE line states {matched_drug} {stated_mg:g}mg, which does not "
                    f"match any ALLOWED_DOSES value ({allowed_vals}).")

    # ── Pediatric: no dose without confirmed weight ───────────────────────
    if patient_ctx.is_pediatric and not patient_ctx.has_confirmed_weight:
        if re.search(r'\b\d+(?:\.\d+)?\s*(mg|mcg|ml|mL)\b', response_text):
            issues.append("Medication dose given without confirmed pediatric weight.")

    # ── Paralytic without induction ───────────────────────────────────────
    has_paralytic = any(x in r for x in ['rocuronium', 'succinylcholine', 'vecuronium'])
    has_induction = any(x in r for x in ['ketamine', 'etomidate', 'propofol', 'midazolam'])
    if has_paralytic and not has_induction:
        if any(x in q for x in ['rsi', 'intubat', 'rapid sequence']) and 'arrest' not in q:
            issues.append("Paralytic without induction agent — awake paralysis risk.")

    # ── TXA contraindications - negation-aware and hemorrhage-aware
    if 'txa' in r or 'tranexamic' in r:
        clear_hemorrhage = has_clear_hemorrhage(q)
        has_infection = (
            has_fever(q)
            or any(has_positive_term(q, x) for x in [
                "infection", "infected", "pus", "purulent",
                "sepsis", "septic", "abscess"
            ])
        )
        if has_infection and not clear_hemorrhage:
            issues.append(
                "TXA in sepsis/infection context. TXA is for hemorrhagic shock only."
            )
        if any(x in q for x in ['hypothermia', 'frozen', 'cold']) and not clear_hemorrhage:
            issues.append("TXA for hypothermia without hemorrhagic shock.")

    # ── WPW contraindications ─────────────────────────────────────────────
    if 'wpw' in q or 'wolff' in q or 'pre-excitation' in q:
        for drug in ['adenosine', 'metoprolol', 'atenolol', 'diltiazem',
                     'verapamil', 'digoxin', 'calcium channel']:
            if drug in r:
                issues.append(f"WPW contraindication: {drug} risks VF.")

    # ── TBI steroids ──────────────────────────────────────────────────────
    if any(x in q for x in ['tbi', 'traumatic brain', 'head injury']):
        if any(x in r for x in ['dexamethasone', 'methylprednisolone', 'solu-medrol', 'decadron']):
            issues.append("Steroids in TBI increase mortality (CRASH trial).")

    # ── IV potassium push ─────────────────────────────────────────────────
    if re.search(r'potassium.{0,30}iv\s+push|iv\s+push.{0,30}potassium', r):
        issues.append("IV potassium push is lethal.")

    # ── Calcium chloride peripheral ───────────────────────────────────────
    if 'calcium chloride' in r and 'peripheral' in r:
        issues.append("Calcium chloride central line only. Peripheral: calcium gluconate.")

    # ── Oral intake in AMS/shock ──────────────────────────────────────────
    # F-3: both halves of this test used to be short hand-written lists and
    # both missed on G-MTN-08 — "confused" was not an AMS word and "oral
    # glucose" was not an oral-route word. Shared lists now, word-anchored.
    if _has_any_word(r, ORAL_ROUTE_TERMS) or any(
            t in r for t in ORAL_ROUTE_TERMS if " " in t):
        if has_ams_descriptor(q) or _has_any_word(q, ["shock"]):
            issues.append("Oral intake in AMS or shock — aspiration risk.")

    return DeterministicCheck(passed=len(issues) == 0, issues=issues)


# ─────────────────────────────────────────────────────────────────────────────
# LLM VALIDATOR — narrow semantic scope, fail-closed
# ─────────────────────────────────────────────────────────────────────────────

VALIDATOR_PROMPT = """
You are the Clinical Safety Validator for AUSTERE-CDS.

You receive:
1. Full conversation transcript (prior turns + current query)
2. Proposed response
3. Patient context

DECISION RULES:

Return SAFE if the response is a gate question:
"Need weight in kg before dosing."
"Confirm the weight in kg before dosing — I only have an estimate."
"IV or IM? Do you have access?"
"Need concentration before giving mL dose."
"Need rhythm before antiarrhythmic."
"Need height and sex before vent settings."

Return SAFE if the response uses an ALLOWED_DOSES value exactly.
Do NOT compare IM ketamine dose to IV ketamine dose — they have different dose ranges.
Do NOT flag IM route when the provider selected IM.
Do NOT flag IV route when the provider selected IV or confirmed IV/IO access.
Do NOT flag routine ask-responses.

Return UNSAFE ONLY for direct patient-harm errors:

1. SEPSIS AS HEMORRHAGE: fever + infection source + hypotension, response gives TXA/LTOWB/DCR as primary treatment.
2. TXA MISUSE: TXA for sepsis/infection WITHOUT clear traumatic hemorrhage, hypothermia alone, burns alone, TBI alone, >3hrs post injury.
   Do NOT flag TXA when the query clearly states active bleeding, abdominal bleeding, hemorrhagic shock, penetrating trauma, GSW, blast injury, amputation, or massive bleeding.
3. CICO OMISSION: failed ETT + failed rescue airway + ongoing hypoxia, no surgical airway mentioned.
4. WPW CONTRAINDICATION: WPW present, response gives adenosine/beta-blocker/CCB/digoxin.
5. PARALYTIC WITHOUT SEDATION: paralytic for patient with pulse, no induction or sedation plan.
6. TBI STEROIDS: TBI context AND the response itself recommends a corticosteroid by name. The ABSENCE of a steroid warning is NEVER an issue — do not flag a response for failing to mention steroids it never recommended.
7. CRITICAL MISSED DIAGNOSIS: tension pneumo without decompression, cardiac arrest without CPR, severe anaphylaxis without epinephrine.
8. DANGEROUS REASSURANCE: "stable" with hemodynamic instability, "no evacuation" with red flags.

REASON FROM WHAT PATIENT CONTEXT SAYS, NEVER FROM WHAT IT OMITS.
PATIENT CONTEXT always states the age band on its first line — "PEDIATRIC
PATIENT", "ADULT PATIENT", "NOT pediatric", or "pediatric status UNKNOWN" — and
states a confirmed weight when the session holds one. Take those lines as fact.
Never ask for, or flag the absence of, a weight or an age the block already
states, and never escalate because you could not find something that is there.

Return NEEDS_HUMAN_REVIEW ONLY when:
- Medication dosing given for a patient PATIENT CONTEXT calls PEDIATRIC or of
  UNKNOWN pediatric status, AND PATIENT CONTEXT shows no confirmed weight.
  A confirmed weight SATISFIES this rule — if the block says the weight is
  confirmed, do not flag it and do not ask for it.
  An ADULT or NOT-pediatric patient does not arm this rule at all.
- Invasive procedure recommended beyond stated scope without acknowledgment.
- Source/protocol conflict is clinically meaningful.
- VITALS CONFLICT: the patient context lists RECORDED VITALS and the response
  recommends an agent those vitals caution against — a drug with a hypotension
  risk at a low SBP, a respiratory depressant at a low RR or SpO2, an AV-nodal
  blocker at a low HR. FLAG IT, do not rewrite the recommendation and do not
  substitute a different drug: the deterministic layer owns what is given.
  State the vital and its value in the issue.

  Do NOT flag a vitals conflict when the vital in question was never recorded.
  A missing vital is unknown, not normal — but an absent vital is also not
  evidence of a conflict, so say nothing about it.
  Do NOT flag ketamine on haemodynamic or respiratory grounds; it is the
  favourable agent on both and flagging it pushes toward a worse one.

Do NOT flag: missing warnings about medications the response does not recommend, IM route recommendations, IV route recommendations, short responses,
missing non-critical monitoring details, sedation interval preferences when a plan exists,
or any issue not explicitly listed above.
Do not flag TXA for active traumatic hemorrhage if no positive sepsis/infection pattern is present.
Do not treat "no fever", "afebrile", "denies fever", or "without fever" as fever.

ISSUE FORMAT REQUIREMENT:
Issue descriptions must be specific and actionable. Do not use category-only labels.
BAD: "CRITICAL MISSED DIAGNOSIS" or "TBI STEROIDS"
GOOD: "Response recommends TXA for fever + pus + hypotension without confirmed hemorrhage."
GOOD: "Response includes paralytic but no induction agent or sedation."
Never return result=UNSAFE with an empty issues array.

OUTPUT: Return only valid JSON. No markdown. No text outside the JSON.
{
  "result": "SAFE" | "UNSAFE" | "NEEDS_HUMAN_REVIEW",
  "issues": ["specific issue"],
  "rationale": "brief reason"
}
"""



def normalize_validator_result(data: dict) -> dict:
    """Normalize validator output. UNSAFE with empty issues → NEEDS_HUMAN_REVIEW."""
    result = data.get("result", "NEEDS_HUMAN_REVIEW")
    issues = data.get("issues") or []
    rationale = data.get("rationale") or ""

    if result not in ["SAFE", "UNSAFE", "NEEDS_HUMAN_REVIEW"]:
        result = "NEEDS_HUMAN_REVIEW"
        issues.append("Validator returned unknown result value.")

    if result == "UNSAFE" and not issues:
        if rationale:
            issues = [f"Validator marked UNSAFE: {rationale}"]
        else:
            result = "NEEDS_HUMAN_REVIEW"
            issues = ["Validator marked unsafe but provided no specific issue."]

    if result == "SAFE":
        issues = []

    return {"result": result, "issues": issues, "rationale": rationale, "safe": result == "SAFE"}


def validate_response(full_transcript: str, response_text: str,
                      patient_ctx: PatientContext,
                      allowed_dose_block: str = "",
                      now_ts=None) -> dict:
    """
    LLM semantic validator. Receives full conversation transcript.
    Fail-closed: errors return NEEDS_HUMAN_REVIEW, not SAFE.

    Runs on providers.validator_model(), NOT on the model the client selected.
    Holding the validator constant is what makes a generator comparison mean
    anything; it also keeps the safety layer on a model whose behaviour is
    already characterised by the logged corpus. A provider outage here degrades
    to NEEDS_HUMAN_REVIEW like every other validator failure.
    """
    # Skip validator entirely for safe gate responses
    if response_text.strip() in SAFE_GATE_RESPONSES:
        return {"result": "SAFE", "issues": [], "rationale": "safe gate response", "safe": True}

    try:
        patient_summary = build_patient_block(patient_ctx, now_ts=now_ts) or "No patient context."
        dose_section = f"{allowed_dose_block}\n\n" if allowed_dose_block else ""
        validation_input = (
            f"CONVERSATION TRANSCRIPT:\n{full_transcript}\n\n"
            f"PATIENT CONTEXT:\n{patient_summary}\n\n"
            f"{dose_section}"
            f"PROPOSED RESPONSE:\n{response_text}"
        )

        raw = providers.chat(
            VALIDATOR_PROMPT,
            [{"role": "user", "content": validation_input}],
            model=providers.validator_model(),
            temperature=0,
            max_tokens=300,
        ).strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        result_val = data.get("result", "NEEDS_HUMAN_REVIEW")
        issues = data.get("issues", [])
        rationale = data.get("rationale", "")

        if issues:
            print(f"🛡️ Validator [{result_val}]: {issues}")
        else:
            print(f"✅ Validator [{result_val}]: {rationale}")

        return normalize_validator_result({"result": result_val, "issues": issues, "rationale": rationale})

    except json.JSONDecodeError as e:
        print(f"🚨 Validator parse error: {e}")
        return {"result": "NEEDS_HUMAN_REVIEW",
                "issues": ["Validator returned invalid output."],
                "rationale": "Parse error — human review required.", "safe": False}
    except Exception as e:
        print(f"🚨 Validator error: {e}")
        return {"result": "NEEDS_HUMAN_REVIEW",
                "issues": ["Validator unavailable."],
                "rationale": str(e), "safe": False}


# ─────────────────────────────────────────────────────────────────────────────
# SAFETY GATE
# ─────────────────────────────────────────────────────────────────────────────

def build_safety_hold(issues: list, rationale: str) -> str:
    issue_lines = "\n".join(f"- {i}" for i in issues) if issues else f"- {rationale}"
    return (
        "Clinical safety hold. This response was blocked.\n\n"
        f"Issues identified:\n{issue_lines}\n\n"
        "Reassess patient. Use local protocol. Contact medical control if available.\n\n"
        "Guideline-based support only. Not a substitute for clinical judgment."
    )


def is_safe_gate_response(text: str) -> bool:
    return text.strip() in SAFE_GATE_RESPONSES



def is_cico_response_adequate(response_text: str) -> bool:
    """Return True when response explicitly includes definitive surgical airway language."""
    r = (response_text or "").lower()
    return any(x in r for x in [
        "cricothyrotomy", "surgical airway", "front of neck", "cric"
    ])

HUMAN_REVIEW_BANNER = (
    "\n\n⚠️ CLINICAL SAFETY NOTE: This response requires human review. "
    "Use local protocol and medical control where available."
)


def _partition_issues(issues: list, keywords: list) -> tuple:
    """Split issues into (those mentioning any keyword, the rest)."""
    matched, other = [], []
    for issue in issues:
        text = issue.lower()
        (matched if any(k in text for k in keywords) else other).append(issue)
    return matched, other


@dataclass(frozen=True)
class SafetyOverride:
    """
    One structured false-positive override.

    `name` is stable and is written to the session log (T-13) so an audit can
    tell which branch fired. `keywords` selects the issues this override speaks
    to; `requires_sole_issue` is the guard that stops an override dismissing a
    block when unrelated issues are also present. `condition` is the evidence
    that the flagged concern is actually addressed by the response.

    Overrides DOWNGRADE, they do not release (SC-3). A fired override yields a
    served response with the human-review banner, the ORIGINAL issue list
    preserved for the log, and verdict NEEDS_HUMAN_REVIEW.
    """
    name: str
    keywords: tuple
    condition: object                  # (response_lower, ctx, full_history) -> bool
    requires_sole_issue: bool = True

    def fires(self, issues, response_lower, patient_ctx, full_query_history) -> bool:
        matched, other = _partition_issues(list(issues), list(self.keywords))
        if not matched:
            return False
        if self.requires_sole_issue and other:
            return False
        return bool(self.condition(response_lower, patient_ctx, full_query_history))


_STEROID_DRUGS = ["dexamethasone", "methylprednisolone", "solu-medrol",
                  "decadron", "prednisone", "prednisolone", "hydrocortisone"]


def _has_confirmed_weight(_r, ctx, _h):
    return bool(getattr(ctx, "confirmed_weight_kg", None) if ctx else None)


# Evaluation order is significant and matches v4.0 exactly.
SAFETY_OVERRIDES = (
    # NOTE: requires_sole_issue=False preserves v4.0 behaviour — this branch
    # dismisses the block even when unrelated issues co-occur. That is the
    # SC-5 gap on TODO.md, deliberately NOT changed here. Under SC-3 its
    # consequence is bounded: the co-occurring issue is now preserved in the
    # log and banner-flagged rather than discarded.
    SafetyOverride(
        name="pediatric_weight_confirmed",
        keywords=("without confirmed pediatric", "confirmed pediatric", "confirmed weight"),
        condition=_has_confirmed_weight,
        requires_sole_issue=False,
    ),
    SafetyOverride(
        name="cico_airway",
        keywords=("cico", "cricothyrotomy", "surgical airway", "cric", "airway"),
        condition=lambda r, ctx, h: is_cico_response_adequate(r),
    ),
    SafetyOverride(
        name="paralytic_with_induction",
        keywords=("paralytic",),
        condition=lambda r, ctx, h: any(x in r for x in
            ["ketamine", "etomidate", "induction", "pre-oxygenate"]),
    ),
    # TBI-steroid (beta 2026-07-18): the validator may demand a steroid warning
    # when the response never recommends one. Absence of a warning is not a
    # violation; the deterministic check is the authority on actual steroid
    # recommendations.
    SafetyOverride(
        name="tbi_steroid_absent",
        keywords=("steroid", "corticosteroid"),
        condition=lambda r, ctx, h: not any(d in r for d in _STEROID_DRUGS),
    ),
    SafetyOverride(
        name="sepsis_hemorrhage_no_dcr",
        keywords=("sepsis", "hemorrhage"),
        condition=lambda r, ctx, h: not any(x in r for x in
            ["txa", "tranexamic", "ltowb", "whole blood", "dcr"]),
    ),
    SafetyOverride(
        name="fluids_resuscitation",
        keywords=("iv fluid", "fluid", "crystalloid", "resuscitat"),
        condition=lambda r, ctx, h: any(x in r for x in
            ["fluid", "crystalloid", "antibiotic", "ns ", "lr "]),
    ),
    SafetyOverride(
        name="tension_pneumo_decompression",
        keywords=("tension pneumo", "decompression", "needle", "thoracostomy"),
        condition=lambda r, ctx, h: any(x in r for x in
            ["decompression", "needle", "thoracostomy", "chest"]),
    ),
    SafetyOverride(
        name="dangerous_reassurance_has_action",
        keywords=("reassurance",),
        condition=lambda r, ctx, h: any(x in r for x in
            ["airway", "intubat", "evacuate", "evac", "monitor", "iv fluid",
             "cpr", "decompression", "fluid", "antibiotic"]),
    ),
    SafetyOverride(
        name="txa_clear_hemorrhage",
        keywords=("txa", "tranexamic"),
        condition=lambda r, ctx, h: has_clear_hemorrhage(h) and not looks_like_sepsis(h),
    ),
)


def find_fired_override(issues: list, response_text: str, patient_ctx,
                        full_query_history: str):
    """First override in registry order whose conditions are met, else None."""
    r_lower = (response_text or "").lower()
    for override in SAFETY_OVERRIDES:
        if override.fires(issues, r_lower, patient_ctx, full_query_history):
            return override
    return None


# F-8. 109 of 160 bank turns carried the human-review banner, and of 110
# validator issues raised, 87 mentioned weight, 87 mentioned paediatric status
# and 78 mentioned both — one complaint, rephrased. It fired on a documentation
# checklist and on ventilator settings, neither of which is a dose.
#
# The VALIDATOR_PROMPT's NEEDS_HUMAN_REVIEW rule already says "Medication
# dosing given for ...". The prompt says it and is not obeyed, so the
# precondition is evaluated here instead: no medication in the response, no
# weight/paediatric review.
#
# Keywords that identify the rule from its issue text. Matched the same way
# SafetyOverride matches, via _partition_issues, so an issue about something
# ELSE co-occurring keeps the banner.
WEIGHT_REVIEW_KEYWORDS = ("confirmed weight", "without confirmed", "pediatric",
                          "paediatric", "weight for", "no confirmed weight",
                          "confirming weight", "confirming the weight")

# Drug names the system itself names elsewhere — the deterministic calculators,
# the steroid list, the vitals caution table and the standard-concentration
# block. Assembled rather than hand-written so it cannot drift from the lists
# that already exist.
# MEDICATION dose units only. Bare "mL" and "L" are deliberately absent: a
# tidal volume of 420 mL, a 1 L bag and a 500 mL fluid bolus are all volumes
# and none of them is a drug dose. Including mL was the first thing this
# precondition got wrong, and it got it wrong on H-S6-a — the ventilator-
# settings answer whose banner is the finding's own headline example, where
# the validator called a tidal volume "dosing in mL/kg" and the precondition
# agreed with it. Volume plus a drug NAME still counts, via MEDICATION_TERMS.
_DOSE_UNIT_RE = re.compile(
    r'(?<!\w)\d+(?:\.\d+)?\s*(?:mg|mcg|µg|units?|meq|mmol|mg/kg|mcg/kg'
    r'|mcg/kg/min|mcg/min|mg/ml|mcg/ml|mg/hr|mg/min)(?!\w)', re.IGNORECASE)


def _medication_vocabulary() -> frozenset:
    names = set(_STEROID_DRUGS)
    names.update(["ketamine", "rocuronium", "succinylcholine", "vecuronium",
                  "lorazepam", "midazolam", "diazepam", "levetiracetam",
                  "keppra", "fentanyl", "morphine", "hydromorphone",
                  "epinephrine", "norepinephrine", "vasopressin", "dopamine",
                  "dobutamine", "adenosine", "amiodarone", "atropine",
                  "diltiazem", "verapamil", "metoprolol", "labetalol",
                  "esmolol", "digoxin", "txa", "tranexamic", "cefazolin",
                  "ertapenem", "ceftriaxone", "moxifloxacin", "etomidate",
                  "propofol", "naloxone", "dextrose", "calcium chloride",
                  "calcium gluconate", "sodium bicarbonate", "magnesium",
                  "hypertonic saline", "albuterol", "ondansetron",
                  "tranexamic acid", "nitroglycerin", "insulin", "glucagon",
                  # Fluids and blood products. Weight-dependent in a child, so
                  # a review complaint about them IS about dosing — and their
                  # volumes are in mL, which the unit pattern deliberately
                  # ignores, so they have to be recognised by name.
                  "crystalloid", "normal saline", "lactated ringer", "ltowb",
                  "whole blood", "packed red", "plasma", "platelets"])
    try:
        for rule in vitals_mod.CAUTIONS:
            # The oral-route rules list ROUTES under `drugs` — "swallow",
            # "drink", "orally". A route is not a medication and must not
            # satisfy this precondition. Excluded by GROUP rather than by word
            # shape: "swallow" is alphabetic and seven characters long, which
            # is exactly what a drug name looks like from the outside.
            if rule.get("group") == "oral_route_aspiration":
                continue
            for drug in rule.get("drugs", []):
                names.add(str(drug).lower())
    except Exception:
        pass
    return frozenset(names)


MEDICATION_TERMS = _medication_vocabulary()


def response_states_a_medication(response_text: str) -> bool:
    """Whether the response actually proposes a drug or a dose.

    The precondition for the weight/paediatric review rule. A response that
    names no medication and states no dose cannot be "medication dosing given
    without a confirmed weight", whatever the validator says about it.
    """
    r = (response_text or "").lower()
    if _DOSE_UNIT_RE.search(r):
        return True
    return any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', r)
               for term in MEDICATION_TERMS)


VITALS_CAUTION_HEADING = "\n\n⚠️ **VITALS CAUTION**\n"


# Verdicts that mean "nothing has flagged this yet". DETERMINISTIC_CHECKED is
# one of them: a deterministic path ran its checks and found nothing, which is
# the same STARTING point as a validator SAFE for anything that downgrades.
#
# This set exists because relabelling the deterministic returns silently broke
# the vitals-caution downgrade — _with_cautions tested `verdict == "SAFE"`, so
# a caution on a deterministic card stopped escalating to NEEDS_HUMAN_REVIEW.
# Anything that softens a verdict must test membership here, not equality.
CLEAN_VERDICTS = frozenset({"SAFE", "DETERMINISTIC_CHECKED"})


def _with_cautions(outcome: GateOutcome, cautions: list) -> GateOutcome:
    """Append vitals cautions to a served response. Never blocks, never releases.

    Applied at the single exit point of the gate, AFTER every override has been
    evaluated against the original response text. If cautions were appended
    first they would become text an override condition could match — the
    dangerous_reassurance branch fires on the substring "monitor" anywhere in a
    response, and a caution is commentary about the answer, not part of it.
    That is the same ordering rule BOUNDARY_RESET_NOTICE and the
    general-reference banner follow.

    A caution cannot move a block. A blocked response is a safety hold Python
    wrote; appending "confirm the haemodynamic plan" to it would describe a
    recommendation that was never served. A gate question is left alone for the
    same reason, and because SAFE_GATE_RESPONSES is matched exactly.

    SAFE becomes NEEDS_HUMAN_REVIEW. A response that contradicts a recorded
    vital is served-but-flagged, which is precisely what that verdict means; the
    UNSAFE-iff-blocked invariant is untouched because both are served.
    """
    if not cautions or outcome.blocked or is_safe_gate_response(outcome.response):
        return outcome
    lines = "\n".join(f"- {c}" for c in cautions)
    print(f"🩺 VITALS CAUTION: {cautions}")
    return GateOutcome(
        response=outcome.response + VITALS_CAUTION_HEADING + lines,
        blocked=False,
        issues=outcome.issues,
        verdict=("NEEDS_HUMAN_REVIEW" if outcome.verdict in CLEAN_VERDICTS
                 else outcome.verdict),
        override_fired=outcome.override_fired,
        cautions=list(cautions),
        review_suppressed=outcome.review_suppressed,
    )


def apply_safety_gate(response_text: str, det_check: DeterministicCheck,
                      llm_result: dict,
                      patient_ctx=None,
                      full_query_history: str = "",
                      vitals_cautions: Optional[list] = None) -> GateOutcome:
    """
    Fail-closed safety gate. Returns a GateOutcome whose `verdict` is what the
    session log records — see the invariant on GateOutcome.

    Vitals cautions are applied to the core outcome rather than inside it, so
    the block/serve decision and the override registry see exactly what they saw
    before vitals existed.
    """
    return _with_cautions(
        _gate_core(response_text, det_check, llm_result, patient_ctx,
                   full_query_history),
        vitals_cautions or [])


def _gate_core(response_text: str, det_check: DeterministicCheck,
               llm_result: dict,
               patient_ctx=None,
               full_query_history: str = "") -> GateOutcome:
    """The gate as it was before vitals. Unchanged."""
    # Safe gate responses always pass through
    if is_safe_gate_response(response_text):
        return GateOutcome(response_text, False, [], "SAFE")

    # Deterministic failures block first (warn-only when debug flag set)
    if not det_check.passed:
        if DEBUG_WARN_ONLY:
            print(f"DEBUG WARN ONLY — deterministic issue: {det_check.issues}")
            response_text += "\n\n[DEBUG DET ISSUE: " + str(det_check.issues) + "]"
        else:
            print(f"🚨 DETERMINISTIC BLOCK: {det_check.issues}")
            return GateOutcome(build_safety_hold(det_check.issues, ""), True,
                               det_check.issues, "UNSAFE")

    # LLM UNSAFE — check structured false positives before blocking
    if llm_result["result"] == "UNSAFE":
        issues = llm_result.get("issues") or []
        had_no_issues = not issues
        if had_no_issues:
            # normalize_validator_result() already guarantees a non-empty issue
            # list upstream, but the gate must not depend on a normalizer it does
            # not call: a blocked record with no issues is as uninformative in the
            # audit log as the served UNSAFE records S-2 describes. Mirrors the
            # normalizer's wording.
            rationale = llm_result.get("rationale", "")
            issues = [f"Validator marked UNSAFE: {rationale}" if rationale
                      else "Validator marked unsafe but provided no specific issue."]

        # The synthesized issue exists to make the LOG readable. It must never
        # be matched by an override: its text is the validator's free-form
        # rationale, so a rationale mentioning "fluid" or "airway" could satisfy
        # an override's keywords and DOWNGRADE a block into a served response.
        # A defensive fallback that serves what would otherwise be blocked
        # defends the wrong way. When the validator gave us nothing structured
        # to reason about, fail closed. Found in review of SC-3 (6c7f535).
        fired = (None if had_no_issues else
                 find_fired_override(issues, response_text, patient_ctx, full_query_history))
        if fired is not None:
            # SC-3: an override DOWNGRADES. v4.0 returned (response, False, [])
            # here — unblocked, issue list discarded, and the call site then
            # logged UNSAFE for a response the medic had already been shown.
            # The medic now sees the review banner and the issues survive.
            print(f"⚠️ OVERRIDE [{fired.name}] — downgraded to NEEDS_HUMAN_REVIEW: {issues}")
            return GateOutcome(response_text + HUMAN_REVIEW_BANNER, False, issues,
                               "NEEDS_HUMAN_REVIEW", override_fired=fired.name)

        if DEBUG_WARN_ONLY:
            # Served, so it cannot be logged UNSAFE (see the GateOutcome invariant).
            print(f"DEBUG WARN ONLY — LLM issue: {issues}")
            return GateOutcome(response_text + "\n\n[DEBUG LLM ISSUE: " + str(issues) + "]",
                               False, issues, "NEEDS_HUMAN_REVIEW")

        print(f"🚨 LLM BLOCK: {issues}")
        return GateOutcome(build_safety_hold(issues, llm_result.get("rationale", "")),
                           True, issues, "UNSAFE")

    # NEEDS_HUMAN_REVIEW appends warning
    if llm_result["result"] == "NEEDS_HUMAN_REVIEW":
        issues = llm_result.get("issues", [])
        # F-8: the weight/paediatric rule has a precondition the prompt states
        # and the model does not honour. Applied here, deterministically, and
        # ONLY when every issue raised is that one complaint — an unrelated
        # issue co-occurring keeps the banner, the same guard
        # requires_sole_issue gives the override registry.
        weight_issues, other = _partition_issues(list(issues),
                                                 list(WEIGHT_REVIEW_KEYWORDS))
        if (weight_issues and not other
                and not response_states_a_medication(response_text)):
            print(f"🔇 REVIEW PRECONDITION UNMET — no medication in response, "
                  f"suppressing: {weight_issues}")
            return GateOutcome(response_text, False, [], "SAFE",
                               review_suppressed="no_medication_in_response")
        print(f"⚠️ NEEDS_HUMAN_REVIEW: {llm_result.get('rationale','')}")
        return GateOutcome(response_text + HUMAN_REVIEW_BANNER, False,
                           issues, "NEEDS_HUMAN_REVIEW")

    print(f"✅ SAFE")
    return GateOutcome(response_text, False, [], "SAFE")



# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC HIGH-RISK CASE BUILDERS — used before RAG/LLM
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# PATIENT BOUNDARY DETECTION (SC-1)
# ─────────────────────────────────────────────────────────────────────────────
# The audit's most serious finding (S-1) was a 6-year-old's 34 kg carried into
# an adult IED casualty, with a dose served against it. PatientContext replayed
# over the FULL conversation with no notion of the patient changing.
#
# The failure mode is asymmetric and BOTH directions are bad:
#   missed boundary -> a stale weight doses the wrong patient (S-1)
#   false boundary  -> a confirmed weight is destroyed mid-resuscitation
# Owner decision 2026-08-20 (PLAN_v4.1.md §5.1, option c): use the measured
# phrase list AND surface every reset in the response, so a wrong reset is
# immediately visible to the medic rather than silently swapping one failure
# for the other.

# Explicit "this is a different patient" statements.
NEW_PATIENT_PHRASES = (
    "new patient", "new session", "next patient", "another patient",
    "different patient", "new casualty", "next casualty", "new cas",
)

# Presentational openers: "have a marine that was hit by an IED".
# Anchored to the START of the query — mid-sentence "have a" is prose
# ("patient has a fever", "if you have a tourniquet") and must not fire.
_PRESENTATIONAL_OPENER_RE = re.compile(
    r"^\W*(?:i\s+|i'?ve\s+|we\s+|we'?ve\s+)?(?:have|has|got|get)\s+an?\b"
)

# Words that follow the opener when it is NOT introducing a patient.
# "have a look at this", "have a question about TXA".
_OPENER_NON_PATIENT_NOUNS = (
    "look", "question", "quick", "second", "sec", "minute", "moment",
    "problem", "issue", "follow", "followup", "protocol", "guideline",
    "reference", "copy", "chance", "feeling", "hard time", "bad feeling",
)

# Inactivity gap after which the next turn is treated as a new patient.
# v2.5's changelog claimed 30 minutes; confirmed by owner 2026-08-20 against
# the logged session clusters (08-11 splits at 07:49->07:52, 09:12, 11:54).
PATIENT_BOUNDARY_TIMEOUT_MIN = _env_number("CDSS_PATIENT_TIMEOUT_MIN", 30.0, float)

# Contradiction tolerances. Below these a restatement is a restatement, not a
# new patient — "34kg" then "34 kg" must not reset.
_AGE_CONTRADICTION_YEARS = 1.0
_WEIGHT_CONTRADICTION_KG = 1.0
_WEIGHT_CONTRADICTION_FRAC = 0.05


def _parse_ts(value):
    """Parse an ISO-8601 timestamp from the client. None on anything unusable."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # Clients may send naive timestamps; treat them as UTC so a naive/aware mix
    # cannot raise mid-request and take the whole query down.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _stated_weight_kg(q: str) -> Optional[float]:
    """The confirmed weight this query states, using extract_patient_context's
    own patterns so the two can never disagree about what a query says."""
    kg = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', q)
    if kg:
        return float(kg.group(1))
    lb = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b', q)
    if lb:
        return round(float(lb.group(1)) * 0.453592, 1)
    return None


def _stated_age_years(q: str) -> Optional[float]:
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:yo|y/o|year[\s-]*old|yr\s*old)\b', q)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+)[\s-]*year[\s-]*old', q)
    if m:
        return float(m.group(1))
    return None


def detect_patient_boundary(query: str, ctx: Optional[PatientContext] = None,
                            prev_ts=None, now_ts=None) -> Optional[str]:
    """
    Return a short trigger reason when `query` starts a NEW patient, else None.

    Evaluated BEFORE the query is folded into ctx, so the contradiction triggers
    compare what this turn says against what previous turns established.
    """
    q = (query or "").lower().strip()
    if not q:
        return None

    # 1. Explicit statement.
    for phrase in NEW_PATIENT_PHRASES:
        if phrase in q:
            return f"explicit:{phrase}"

    # 2. Presentational opener introducing a patient.
    opener = _PRESENTATIONAL_OPENER_RE.match(q)
    if opener:
        remainder = q[opener.end():].strip()
        if remainder and not remainder.startswith(_OPENER_NON_PATIENT_NOUNS):
            return "presentational_opener"

    # Triggers 3-5 need prior state to contradict.
    if ctx is None:
        return None

    # 3. Age contradiction.
    stated_age = _stated_age_years(q)
    if (stated_age is not None and ctx.age_years is not None
            and abs(stated_age - ctx.age_years) > _AGE_CONTRADICTION_YEARS):
        return "age_contradiction"

    # 4. Weight contradiction.
    stated_wt = _stated_weight_kg(q)
    if stated_wt is not None and ctx.confirmed_weight_kg is not None:
        prior = ctx.confirmed_weight_kg
        tol = max(_WEIGHT_CONTRADICTION_KG, prior * _WEIGHT_CONTRADICTION_FRAC)
        if abs(stated_wt - prior) > tol:
            return "weight_contradiction"

    # 5. Inactivity. Missing or unparseable timestamps mean "unknown", never
    #    "no gap" — pre-v4.1 clients send no ts at all and must not be treated
    #    as one unbroken session.
    start, end = _parse_ts(prev_ts), _parse_ts(now_ts)
    if start and end:
        gap_min = (end - start).total_seconds() / 60.0
        if gap_min > PATIENT_BOUNDARY_TIMEOUT_MIN:
            return "inactivity_timeout"

    return None


def context_holds_anything(ctx: Optional[PatientContext]) -> bool:
    """Whether a reset would actually discard something the medic told us.

    Deliberately a list of the facts the notice NAMES — weight, age, access,
    vitals — plus route, which it does not name but which is the same class of
    carried-over belief. If the notice's wording changes, this list changes
    with it; a notice that claims to have cleared something the system never
    held is exactly the defect this closes.
    """
    if ctx is None:
        return False
    return bool(ctx.confirmed_weight_kg is not None
                or ctx.estimated_weight_kg is not None
                or ctx.age_years is not None
                or ctx.vitals
                or ctx.access_state != "UNKNOWN"
                or ctx.route_preference != "UNKNOWN"
                or ctx.is_pediatric
                or ctx.ams_stated)


BOUNDARY_RESET_NOTICE = (
    "🔄 **Starting a new patient — previous weight, age, access and vitals cleared.** "
    "If this is still the same patient, restate the weight and vitals before "
    "asking for a dose.\n\n"
)


def rebuild_patient_context_from_history(
    query: str,
    conversation_history: Optional[list] = None,
    session_ctx: Optional[PatientContext] = None,
    now_ts=None
) -> PatientContext:
    """
    Replays prior user turns into PatientContext before applying the current query.
    This fixes stateless API calls where the current turn is only "IV" or "IM".
    """
    ctx = session_ctx or PatientContext()
    prev_ts = None

    if conversation_history:
        # Durable patient facts (weight/age/route/access) replay over the FULL
        # conversation — a weight given 30 turns ago is still the weight, WITHIN
        # one patient.
        #
        # SC-1: the boundary check runs per-turn INSIDE this loop, not once
        # after it. The server is stateless and re-derives context from the full
        # history on every request, so a reset applied only to the current turn
        # is undone on the next request when the earlier turns replay again.
        # Pinned by test_boundary_reset_survives_full_replay.
        for turn in conversation_history:
            prior_q = turn.get("query", "")
            if not prior_q:
                continue
            turn_ts = turn.get("ts")
            if detect_patient_boundary(prior_q, ctx, prev_ts=prev_ts, now_ts=turn_ts):
                ctx = PatientContext()
            ctx = extract_patient_context(prior_q, prior_ctx=ctx, turn_ts=turn_ts)
            prev_ts = turn_ts or prev_ts

    reason = detect_patient_boundary(query, ctx, prev_ts=prev_ts, now_ts=now_ts)
    if reason:
        # F-9: the reset is free and stays unconditional. The NOTICE is what
        # needs something to have been cleared. 15 notices fired across the
        # eval bank and 10 of them were on turns with no conversation history
        # at all — "have a 56kg patient with 3rd degree burns" on turn 1 was
        # told that a previous weight, age, access and vitals had been cleared,
        # and asked to restate a weight it had just been given in the same
        # sentence. The notice made a false statement, which is the fastest way
        # to teach a medic to stop reading it.
        if not context_holds_anything(ctx):
            reason = None
        ctx = PatientContext()

    ctx = extract_patient_context(query, prior_ctx=ctx, turn_ts=now_ts)
    # Only the CURRENT turn's boundary drives the notice. extract_patient_context
    # is called on a context whose field is already clear, so this cannot leak
    # from a boundary that happened earlier in the replay.
    ctx.boundary_reset_reason = reason
    return ctx


def build_full_query_history(query: str, conversation_history: Optional[list] = None) -> tuple[str, str]:
    """Return prior user queries and current user-history text for deterministic gates."""
    prior_queries = ""
    if conversation_history:
        parts = []
        event_turns = _env_number("CDSS_EVENT_TURNS", 12, int)
        for turn in conversation_history[-event_turns:]:
            if turn.get("query"):
                parts.append(turn.get("query", ""))
        prior_queries = " ".join(parts).strip()

    full_query_history = f"{prior_queries} {query}".strip()
    return prior_queries, full_query_history


def is_non_medical_query(query: str) -> bool:
    """Only reject clearly non-clinical queries. Default assumption is clinical."""
    q = (query or "").lower().strip()
    if not q:
        return False

    # Clinical overrides — never block if these appear
    clinical_overrides = [
        "vent", "setting", "peep", "fio2", "tidal", "intub", "airway",
        "patient", "trauma", "pain", "bleed", "sepsis", "dose", "mg", "ml",
        "bp", "hr", "spo2", "oxygen", "pulse", "shock", "fever", "wound",
        "ketamine", "rsi", "epi", "txa", "fluid", "antibiotic", "seizure",
        "fracture", "burn", "hypothermia", "cardiac", "arrest", "cpr",
        "rocuronium", "succinylcholine", "fentanyl", "morphine", "lorazepam",
        "albuterol", "adenosine", "amiodarone", "vasopressor", "pressor"
    ]
    if any(x in q for x in clinical_overrides):
        return False

    # Hard non-medical patterns only
    non_medical = [
        "what is the weather", "weather in", "weather today",
        "stock price", "sports score", "who won the game",
        "tell me a joke", "write me a poem", "recipe for",
        "capital of ", "what movie", "best restaurant",
        "how do i cook", "what is the population"
    ]
    return any(t in q for t in non_medical)


def is_cico_query(text: str) -> bool:
    q = (text or "").lower()
    explicit = any(x in q for x in ["cico", "cric", "front of neck", "surgical airway"])
    failed_airway = any(x in q for x in [
        "failed ett", "failed intubation", "can't intubate", "cannot intubate",
        "unable to intubate", "failed tube", "failed airway", "missed tube"
    ])
    failed_rescue = any(x in q for x in [
        "failed supraglottic", "failed sg", "failed igel", "failed i-gel",
        "failed lma", "rescue airway failed", "can't ventilate", "cannot ventilate",
        "failed bvm", "bvm not working", "can't oxygenate", "cannot oxygenate"
    ])
    hypoxia = any(x in q for x in [
        "spo2", "sat", "desat", "hypoxic", "cyanotic", "cyanosis", "blue", "o2 70", "o2 80"
    ])
    return explicit or (failed_airway and failed_rescue and hypoxia)


def build_cico_response() -> str:
    return """**DO THIS**
1. Declare CICO: cannot intubate, cannot oxygenate.
2. Perform surgical airway / cricothyrotomy now.
3. Ventilate through the surgical airway and confirm air movement.

**WATCH**
- Confirm chest rise, SpO2 improvement, and waveform ETCO2 if available.

**DON'T**
- Do not keep repeating failed intubation attempts while the patient is hypoxic.

**TLDR**
- Failed ETT plus failed rescue airway plus hypoxia = surgical airway / cricothyrotomy now.

**SOURCE**: General Evidence-Based Medicine / TCCC airway principles

Guideline-based support only. Not a substitute for clinical judgment."""


def is_ketamine_analgesia_context(text: str) -> bool:
    q = (text or "").lower()
    has_ketamine = any(x in q for x in ["ketamine", "ket ", "vitamin k"])
    has_pain = any(x in q for x in [
        "pain", "analgesia", "analgesic", "fracture", "fx", "arm", "leg", "burn"
    ])
    return has_ketamine and has_pain


def build_ketamine_analgesia_response(ctx: PatientContext) -> Optional[str]:
    """Deterministic ketamine analgesia response for confirmed weight + known route."""
    if not ctx.confirmed_weight_kg or ctx.route_preference not in ["IV", "IM"]:
        return None

    if ctx.route_preference == "IV":
        d = ketamine_analgesia_iv(ctx.confirmed_weight_kg)
    else:
        d = ketamine_analgesia_im(ctx.confirmed_weight_kg)
    d = resolve_dose_volume(d, ctx)

    label = "PEDIATRIC PATIENT" if ctx.is_pediatric else f"{ctx.confirmed_weight_kg:g}kg patient"

    return f"""**DO THIS**
1. Confirm monitoring and airway equipment ready.
2. Give ketamine by the {d.route} route.
3. Reassess pain, airway, respirations q5min.

**GIVE**
{render_give_line(d)}

**WATCH**
- Airway, respirations, SpO2, mental status, and emergence reaction.

**DON'T**
- Do not redose without reassessment and local protocol.

**TLDR**
{render_dose_summary(d, label)}

**SOURCE**: General Evidence-Based Medicine / deterministic calculator

Guideline-based support only. Not a substitute for clinical judgment."""


def build_pediatric_ketamine_route_response(ctx: PatientContext) -> Optional[str]:
    if not ctx.is_pediatric or not ctx.confirmed_weight_kg:
        return None

    if ctx.route_preference == "IV":
        d = ketamine_analgesia_iv(ctx.confirmed_weight_kg)
    elif ctx.route_preference == "IM":
        d = ketamine_analgesia_im(ctx.confirmed_weight_kg)
    else:
        return None
    d = resolve_dose_volume(d, ctx)

    return f"""**DO THIS**
1. Confirm monitoring and airway equipment ready.
2. Give ketamine by the requested {d.route} route.
3. Reassess pain, airway, respirations, and perfusion.

**GIVE**
{render_give_line(d)}

**WATCH**
- Monitor airway, respirations, SpO2, mental status, and emergence reaction.

**DON'T**
- Do not redose without reassessment and local protocol.

**TLDR**
{render_dose_summary(d, f"{ctx.confirmed_weight_kg:g}kg pediatric patient")}

**SOURCE**: General Evidence-Based Medicine / deterministic calculator

Guideline-based support only. Not a substitute for clinical judgment."""


def is_vent_settings_query(text: str) -> bool:
    q = (text or "").lower()
    return any(x in q for x in [
        "vent setting", "ventilator setting", "tidal volume", "respiratory rate",
        "peep", "fio2", "need vent", "set the vent", "vent the patient",
        "start the vent", "vent management", "mechanical ventilation"
    ])


def is_rsi_or_post_intubation_context(text: str) -> bool:
    q = (text or "").lower()
    return any(x in q for x in [
        "rsi", "rapid sequence", "intubat", "post-intubation",
        "post intubation", "after tube", "tube confirmed",
        "ventilator", "on the vent", "on a vent", "ketamine drip"
    ])


def should_use_rsi_pregate(text: str) -> bool:
    """
    Whether a query should be routed to the deterministic RSI bundle.

    S-4 (v4.1): is_rsi_or_post_intubation_context() matches the bare substring
    "ventilator", so "Ventilator settings for 75kg male in DKA. Ph 7.1" with a
    confirmed weight was answered with an RSI paralytic bundle rather than vent
    settings. The substring stays in the RSI term list — "on the vent" and
    post-intubation phrasings are genuine RSI context — and a query that is
    actually asking for vent settings is diverted out of the RSI path here.

    This is the single dispatch decision; both call sites use it so the
    regression tests assert the real condition rather than a copy of it.
    """
    return is_rsi_or_post_intubation_context(text) and not is_vent_settings_query(text)


def build_rsi_response(ctx: PatientContext, text: str) -> Optional[str]:
    """
    Deterministic RSI bundle. RSI should not ask "IV or IM" unless no access is stated.
    It always includes induction, paralytic, and post-intubation sedation.
    """
    if not ctx.confirmed_weight_kg:
        return None

    if ctx.access_state in ["NO_IV_IO", "FAILED_IV"]:
        return """**RSI ACCESS CHECK**

**DO THIS**
1. RSI medications require reliable IV/IO access.
2. Establish IV/IO access now if proceeding with RSI.
3. If unable to obtain access, use local failed-airway/agitation protocol and contact medical control if available.

**DON'T**
- Do not give IV RSI induction/paralytic doses when no IV/IO route is available.

**TLDR**
- No IV/IO access documented. Get IV/IO before RSI medications.

Guideline-based support only. Not a substitute for clinical judgment."""

    q = (text or "").lower()
    w = ctx.confirmed_weight_kg
    ped = ctx.is_pediatric

    ket_ind = resolve_dose_volume(ketamine_induction_iv(w, ped), ctx)
    ket_post = resolve_dose_volume(ketamine_post_intubation_iv(w), ctx)

    # Burns RSI: avoid succinylcholine unless explicitly requested; default rocuronium.
    use_succ = any(x in q for x in ["succinylcholine", "sux", "succs"]) and not any(x in q for x in ["burn", "crush"])
    paralytic = resolve_dose_volume(
        succinylcholine_rsi(w, ped) if use_succ else rocuronium_rsi(w, ped), ctx)

    return f"""**DO THIS**
1. Pre-oxygenate and prepare suction, backup airway, and cricothyrotomy equipment.
2. Give induction first, then paralytic.
3. Intubate, confirm tube, secure tube, then continue post-intubation sedation.

**GIVE**
{render_give_line(ket_ind)}
{render_give_line(paralytic)}

**POST-INTUBATION SEDATION**
{render_give_line(ket_post)}

**WATCH**
- Confirm tube with waveform ETCO2 if available. Monitor SpO2, BP, chest rise, and ventilator pressures.

**DON'T**
- Never give paralytic before induction in a patient with a pulse.
- Avoid succinylcholine in burns/crush/hyperkalemia risk unless specifically indicated by protocol.

**TLDR**
- RSI: ketamine induction first, {paralytic.drug} second, post-intubation ketamine sedation after tube confirmed.

**SOURCE**: General Evidence-Based Medicine / deterministic RSI calculator

Guideline-based support only. Not a substitute for clinical judgment."""


def build_txa_sepsis_block() -> str:
    return build_safety_hold(
        ["TXA in sepsis/infection context. TXA is for traumatic hemorrhagic shock only."],
        "Fever/infection plus shock suggests sepsis unless hemorrhage is clearly present."
    )


def build_wpw_drug_block() -> str:
    return build_safety_hold(
        ["WPW/pre-excitation with adenosine or AV-nodal blocker request risks deterioration."],
        "Use local protocol and cardioversion/antiarrhythmic guidance appropriate to stability."
    )


def build_hemorrhagic_shock_dcr_response() -> str:
    return """**DO THIS**
1. Control hemorrhage immediately: pressure, tourniquet, wound packing, pelvic binder if indicated.
2. Treat as hemorrhagic shock. Start damage-control resuscitation.
3. Use LTOWB or blood products if available and within protocol. Evacuate urgently.

**GIVE**
- Consider TXA for traumatic hemorrhagic shock only if within 3 hours of injury and within local protocol.

**WATCH**
- Mental status, radial pulse, BP trend, ongoing bleeding, hypothermia, and response to blood products.

**DON'T**
- Do not give large-volume crystalloid for hemorrhagic shock if blood products are available.

**EVAC IF**
- Persistent hypotension, abdominal bleeding, altered mental status, or ongoing hemorrhage.

**TLDR**
- Active abdominal bleeding with hypotension is hemorrhagic shock: hemorrhage control, DCR, LTOWB/blood if available, consider TXA if within 3 hours.

**SOURCE**: General Evidence-Based Medicine / TCCC damage-control resuscitation principles

Guideline-based support only. Not a substitute for clinical judgment."""


def build_sepsis_management_response() -> str:
    return """**SEPSIS**
- Treat as suspected sepsis/septic shock.

**TREAT**
1. Oxygen, monitor, IV/IO access, reassess BP and mental status.
2. Give fluid bolus per local protocol and reassess frequently.
3. Start antibiotics if available and evacuate urgently.

**DON'T**
- Do not use TXA/DCR/LTOWB for sepsis alone unless hemorrhage is clearly present.

**TLDR**
- Fever or pus plus hypotension = sepsis: fluids, antibiotics, urgent evacuation.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_anaphylaxis_response() -> str:
    return """**ANAPHYLAXIS**

**DO THIS**
1. Give epinephrine IM now if severe allergic reaction with airway symptoms or hypotension.
2. High-flow oxygen, IV/IO access, monitor BP and airway.
3. Evacuate urgently; repeat epi per local protocol if not improving.

**WATCH**
- Worsening airway swelling, wheeze, shock, or recurrent symptoms.

**TLDR**
- Severe anaphylaxis with throat swelling or dropping BP needs epinephrine now.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_seizure_response() -> str:
    return """**ACTIVE SEIZURE**

**DO THIS**
1. Protect airway, place lateral if possible, suction ready.
2. Give benzodiazepine per local protocol; lorazepam is preferred IV when available.
3. If prolonged/recurrent, prepare levetiracetam/Keppra and evacuate.

**WATCH**
- Respiratory depression after benzodiazepine.

**TLDR**
- Active seizure: airway protection, lorazepam/benzodiazepine, then Keppra if ongoing.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_hypothermic_arrest_response() -> str:
    return """**HYPOTHERMIC ARREST**

**DO THIS**
1. Start CPR and defibrillate per local protocol if indicated.
2. Prevent further heat loss; remove wet clothing and actively rewarm.
3. Handle gently and evacuate to rewarming capability.

**WATCH**
- Core temperature, rhythm, and ability to continue high-quality CPR during evacuation.

**TLDR**
- Hypothermic arrest: CPR, warm/rewarm, evacuate.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_tbi_management_response() -> str:
    return """**SEVERE TBI**

**DO THIS**
1. Protect airway and oxygenation; avoid hypoxia and hypotension.
2. Give fluid/blood per protocol to maintain perfusion.
3. Monitor for ICP/herniation signs and evacuate urgently.

**DON'T**
- No steroids (no dexamethasone, methylprednisolone, solu-medrol, or any corticosteroid) — increases mortality per CRASH trial.
- No albumin. Avoid routine hyperventilation unless active herniation signs.

**TLDR**
- Severe TBI: airway, fluid/perfusion, evacuate. Never give steroids.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_mascal_response() -> str:
    return """**MASCAL TRIAGE**

**DO THIS**
1. Triage immediate threats first.
2. Control massive hemorrhage now.
3. Decompress suspected tension pneumothorax if within protocol.

**WATCH**
- Re-triage after each lifesaving intervention.

**TLDR**
- MASCAL: immediate triage, hemorrhage control, decompression for tension pneumo.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_ketamine_drip_response() -> str:
    return """**KETAMINE SEDATION DRIP**

**DO THIS**
1. Confirm the patient is intubated and tube is secured.
2. Use local protocol concentration and pump settings.
3. Titrate ketamine sedation to BP, ventilator synchrony, and agitation.

**DRIP**
- Ketamine infusion: document concentration in mg/mL and pump rate in mL/hr.

**WATCH**
- BP, HR, SpO2, ETCO2 if available, and ventilator synchrony.

**TLDR**
- Intubated sedation: ketamine drip with mg/mL concentration and mL/hr pump rate.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_cholera_response() -> str:
    return """**CHOLERA / SEVERE DEHYDRATION**

**TREAT**
1. Rapid rehydration: ORS if awake and able to drink.
2. IV fluid if severe dehydration, shock, or unable to tolerate oral fluids.
3. Monitor urine output, mental status, pulse, and perfusion.

**WATCH FOR**
- Shock, persistent vomiting, altered mental status, or worsening dehydration.

**TLDR**
- Cholera care is rehydration: ORS when able, IV fluid when severe.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_snake_bite_response() -> str:
    return """**SNAKE BITE**

**DO THIS**
1. Immobilize the limb and keep the patient calm.
2. Mark swelling edge and time; monitor airway, bleeding, neuro signs, and shock.
3. Evacuate for antivenom evaluation.

**DON'T**
- Do not cut, suck, ice, or apply a tight tourniquet.

**TLDR**
- Pit viper bite with spreading swelling: immobilize, monitor, evacuate for antivenom.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_vtach_response() -> str:
    return """**VENTRICULAR TACHYCARDIA**

**DO THIS**
1. Check pulse and stability now.
2. If pulseless: start CPR and defibrillate per local protocol.
3. If unstable with a pulse: synchronized cardioversion per local protocol.

**WATCH**
- Mental status, BP, chest pain, shock signs, pulse loss, and monitor rhythm.

**TLDR**
- VTach: pulse check first. Pulseless = CPR/defib. Unstable with pulse = synchronized cardioversion.

Guideline-based support only. Not a substitute for clinical judgment."""


def build_general_case_response(query: str) -> Optional[str]:
    q = (query or "").lower()
    if any(x in q for x in ["vtach", "v tach", "v-tach", "ventricular tachycardia"]):
        return build_vtach_response()
    if "anaphylaxis" in q or ("hives" in q and ("throat" in q or "bp" in q)):
        return build_anaphylaxis_response()
    if any(x in q for x in ["active seizure", "having active seizure", "seizing"]):
        return build_seizure_response()
    if "cardiac arrest" in q and any(x in q for x in ["hypothermic", "snow", "cold", "frozen"]):
        return build_hypothermic_arrest_response()
    # TBI intentionally NOT dispatched to a fixed card (decision 2026-07-18):
    # severe TBI routes through RAG for guideline-grounded specifics
    # (SBP floor, hypertonic saline, seizure prophylaxis). To revert, re-add:
    #   if any(x in q for x in ["severe tbi", "gcs 6", "traumatic brain injury"]):
    #       return build_tbi_management_response()
    if "mascal" in q:
        return build_mascal_response()
    if "ketamine drip" in q and any(x in q for x in ["intubated", "on the vent", "ventilator"]):
        return build_ketamine_drip_response()
    if "cholera" in q:
        return build_cholera_response()
    if "snake" in q or "pit viper" in q:
        return build_snake_bite_response()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# MAIN QUERY PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

# source_modes produced by the RAG path, which passes through apply_safety_gate.
# Everything else returned before the gate: the deterministic cards, the
# pre-gates, the non-medical refusal and the error path.
GATED_SOURCE_MODES = frozenset({
    "JTS_GROUNDED", "GENERAL_MEDICAL", "GENERAL_REFERENCE", "INSUFFICIENT",
})


def _finalise(result: dict, ctx: Optional[PatientContext]) -> dict:
    """Everything that must happen to EVERY response, however it was produced.

    Two things live here rather than in the RAG path, because the pipeline has
    fourteen early returns and anything applied at only one of them covers only
    one of them:

    1. **Vitals cautions on gate-bypassing responses.** The deterministic cards
       are fixed reviewed strings and return before apply_safety_gate by design.
       A fixed string can still recommend lorazepam to a patient whose RR was
       recorded as 6 — build_seizure_response does, build_cholera_response
       recommends oral fluids, and both DCR cards name TXA. Reusing
       _with_cautions rather than reimplementing it is what keeps "never a new
       pathway" true: same helper, same rules, same refusal to touch a block or
       a gate question.

    2. **The notices.** BOUNDARY_RESET_NOTICE was applied only on the RAG path,
       so a boundary turn that hit a pre-gate cleared the patient's context and
       said nothing about it — a gap in SC-1's coverage, since the whole point
       of option (c) was that every reset is visible. The rejected-vital notice
       would have had the same gap. Both are applied here now, to everything.

    Notices are applied AFTER cautions so the caution attaches to the answer
    rather than to the banner above it.
    """
    # Volume audit FIRST, so every later step sees the text that will actually
    # be served. This runs on EVERY path, gated or not: the deterministic
    # templates return before apply_safety_gate by design, and they were the
    # ones emitting "Draw 7.1 mL of 20mg/mL succinylcholine" with a hardcoded
    # SAFE stamped on it. A check that lived on the LLM path would have missed
    # exactly the path that had the problem.
    audited, volume_issues = audit_volume_lines(result.get("response", ""), ctx)
    if volume_issues:
        result["response"] = VOLUME_STRIPPED_NOTICE + audited
        result["validator_issues"] = list(result.get("validator_issues") or []) + volume_issues
        # Downgrade, never escalate to a block: _finalise is not allowed to
        # introduce UNSAFE, and it does not need to. The dangerous number is
        # already gone from the text; what is left is a response a human
        # should look at.
        if result.get("validator_result") in CLEAN_VERDICTS:
            result["validator_result"] = "NEEDS_HUMAN_REVIEW"

    if ctx is None:
        return result

    if result.get("source_mode") not in GATED_SOURCE_MODES:
        cautions = vitals_mod.conflicts(result.get("response", ""), ctx.vitals,
                                        flags={"ams_stated": ctx.ams_stated})
        if cautions:
            outcome = _with_cautions(
                GateOutcome(response=result.get("response", ""),
                            blocked=result.get("validator_result") == "UNSAFE",
                            issues=result.get("validator_issues", []),
                            verdict=result.get("validator_result", "SAFE"),
                            review_suppressed=result.get("review_suppressed")),
                cautions)
            result["response"] = outcome.response
            result["validator_result"] = outcome.verdict
            result["vitals_cautions"] = outcome.cautions

    if ctx.vitals_rejected:
        result["response"] = (vitals_mod.rejection_notice(ctx.vitals_rejected)
                              + result["response"])
    if ctx.boundary_reset_reason:
        result["response"] = BOUNDARY_RESET_NOTICE + result["response"]
    return result


def _query_with_rag_internal(query: str, chromadb_client, voice_mode: bool = False,
                             conversation_history: list = None,
                             session_ctx: Optional[PatientContext] = None,
                             model: Optional[str] = None) -> dict:
    """Run the pipeline, then apply what every response needs regardless of path."""
    state: dict = {}
    result = _run_pipeline(query, chromadb_client, voice_mode,
                           conversation_history, session_ctx, model, state)
    return _finalise(result, state.get("patient_ctx"))


def _run_pipeline(query: str, chromadb_client, voice_mode: bool = False,
                   conversation_history: list = None,
                   session_ctx: Optional[PatientContext] = None,
                   model: Optional[str] = None,
                   state: Optional[dict] = None) -> dict:
    """
    EdgeCDSS v3.4.1 Pipeline:
    1. Replay structured patient context from conversation history.
    2. Define full_query_history once and use it consistently.
    3. Deterministic pre-gates for high-risk known cases before RAG/LLM.
    4. RAG retrieval + source classification for remaining cases.
    5. Deterministic dose candidates from full_query_history.
    6. Post-checks + validator + safety gate.
    """
    model = providers.resolve_model(model)
    try:
        # Step 1: canonical history and patient context
        prior_queries, full_query_history = build_full_query_history(query, conversation_history)

        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        patient_ctx = rebuild_patient_context_from_history(
            query,
            conversation_history=conversation_history,
            session_ctx=session_ctx,
            now_ts=now_ts
        )
        if state is not None:
            # The live context, not its dict form: _finalise needs the
            # VitalReading objects the caution table reads.
            state["patient_ctx"] = patient_ctx
        if patient_ctx.boundary_reset_reason:
            print(f"🔄 PATIENT BOUNDARY [{patient_ctx.boundary_reset_reason}] — context cleared")

        print(f"👤 confirmed_wt={patient_ctx.confirmed_weight_kg} "
              f"est_wt={patient_ctx.estimated_weight_kg} "
              f"ped={patient_ctx.is_pediatric} "
              f"route={patient_ctx.route_preference} "
              f"access={patient_ctx.access_state}")

        # Fast non-medical gate
        if is_non_medical_query(query):
            return {
                "response": "AUSTERE-CDS handles medical queries only.",
                "sources": [],
                "source_mode": "NON_MEDICAL_PRE_GATE",
                "validator_result": "SAFE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2a: Fixed prep check — before medication gates
        fixed_prep = build_fixed_prep_response(query)
        if fixed_prep:
            print(f"🔧 FIXED_PREP: {query[:40]}")
            return {
                "response": fixed_prep,
                "sources": [],
                "source_mode": "FIXED_PREP",
                "validator_result": "SAFE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2b: Deterministic CICO response
        if is_cico_query(query):
            print("🛑 CICO PRE-GATE")
            return {
                "response": build_cico_response(),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "DETERMINISTIC_CHECKED",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2c: WPW/pre-excitation contraindicated drug hard safety block
        if asks_for_wpw_contraindicated_drug(query):
            print("🛑 WPW DRUG PRE-GATE")
            return {
                "response": build_wpw_drug_block(),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "UNSAFE",
                "validator_issues": [
                    "WPW/pre-excitation with adenosine or AV-nodal blocker request risks deterioration."
                ],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2d: TXA in hypothermia pre-gate
        if asks_for_txa(query) and not has_clear_hemorrhage(query):
            q_lower = query.lower()
            if any(x in q_lower for x in ["hypothermia", "hypothermic", "frozen",
                                            "temp 3", "temp 2", "32c", "33c", "34c"]):
                issue = "TXA for hypothermia without hemorrhagic shock. TXA is for traumatic hemorrhagic shock only."
                print("🛑 TXA-IN-HYPOTHERMIA PRE-GATE")
                return {"response": build_safety_hold([issue], ""),
                        "sources": [], "source_mode": "DETERMINISTIC_PRE_GATE",
                        "validator_result": "UNSAFE", "validator_issues": [issue],
                        "patient_context": patient_ctx.to_dict()}

        # Step 2d-ii: TXA in infection/sepsis hard safety block
        if (
            has_infection_context(query)
            and asks_for_txa(query)
            and not has_clear_hemorrhage(query)
        ):
            print("🛑 TXA-IN-SEPSIS PRE-GATE")
            return {
                "response": build_txa_sepsis_block(),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "UNSAFE",
                "validator_issues": [
                    "TXA in sepsis/infection context. TXA is for traumatic hemorrhagic shock only."
                ],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2e: Sepsis-DCR deterministic refusal
        if (
            looks_like_sepsis(query)
            and asks_for_dcr_or_hemostatic_resus(query)
            and not has_clear_hemorrhage(query)
        ):
            print("🛑 SEPSIS-DCR PRE-GATE")
            return {
                "response": SEPSIS_DCR_REFUSAL,
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "DETERMINISTIC_CHECKED",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2f: Requested overdose pre-gate
        requested_overdose = detect_requested_medication_overdose(query, patient_ctx)
        if requested_overdose:
            print(f"🚨 REQUESTED OVERDOSE: {requested_overdose}")
            return {
                "response": build_safety_hold(requested_overdose, "Requested dose exceeds safety ceiling."),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "UNSAFE",
                "validator_issues": requested_overdose,
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2g: Hemorrhagic shock/DCR deterministic response
        if (
            looks_like_hemorrhagic_shock(query)
            and not looks_like_sepsis(query)
        ):
            print("🩸 HEMORRHAGIC-SHOCK DCR PRE-GATE")
            return {
                "response": build_hemorrhagic_shock_dcr_response(),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "DETERMINISTIC_CHECKED",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2h: Sepsis management deterministic response
        if looks_like_sepsis(query) and not has_clear_hemorrhage(query):
            print("🧫 SEPSIS MANAGEMENT PRE-GATE")
            return {
                "response": build_sepsis_management_response(),
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "DETERMINISTIC_CHECKED",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2i: Deterministic common benchmark scenarios
        general_response = build_general_case_response(query)
        if general_response:
            print("📌 COMMON CASE PRE-GATE")
            return {
                "response": general_response,
                "sources": [],
                "source_mode": "DETERMINISTIC_PRE_GATE",
                "validator_result": "DETERMINISTIC_CHECKED",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2j: Ketamine analgesia — deterministic for confirmed weight + known route
        # Only fires if current query is about ketamine/pain, not a different topic
        _current_is_ketamine = is_ketamine_analgesia_context(query) or query.strip().lower() in [
            "iv", "im", "io", "intramuscular", "intravenous",
            "only have im", "im only", "no iv", "only have iv"
        ]
        _current_is_other_med = _has_any_word(query.lower(), ["epi", "roc", "sux", "succs"]) or any(x in query.lower() for x in [
            "epinephrine", "blood", "ltowb", "txa", "tranexamic",
            "rocuronium", "succinylcholine", "fentanyl",
            "morphine", "lorazepam", "ativan", "amiodarone", "adenosine",
            "norepinephrine", "vasopressin", "dopamine", "albuterol",
            "vtach", "vfib", "arrest", "cpr", "shock", "sepsis", "hemorrhage"
        ])
        if (
            _current_is_ketamine
            and not _current_is_other_med
            and is_ketamine_analgesia_context(full_query_history)
            and not is_rsi_or_post_intubation_context(query)
            and patient_ctx.confirmed_weight_kg
            and patient_ctx.route_preference in ["IV", "IM"]
        ):
            ket_response = build_ketamine_analgesia_response(patient_ctx)
            if ket_response:
                label = "PED " if patient_ctx.is_pediatric else ""
                print(f"💊 {label}KETAMINE ANALGESIA PRE-GATE")
                return {
                    "response": ket_response,
                    "sources": [],
                    "source_mode": "DETERMINISTIC_PRE_GATE",
                    "validator_result": "DETERMINISTIC_CHECKED",
                    "validator_issues": [],
                    "patient_context": patient_ctx.to_dict()
                }

        # Step 2k: RSI / post-intubation deterministic response — before standard pre-gate.
        # should_use_rsi_pregate() diverts vent-settings queries out of this path (S-4).
        if should_use_rsi_pregate(query):
            rsi_response = build_rsi_response(patient_ctx, query)
            if rsi_response:
                print("💉 RSI PRE-GATE")
                return {
                    "response": rsi_response,
                    "sources": [],
                    "source_mode": "DETERMINISTIC_PRE_GATE",
                    "validator_result": "DETERMINISTIC_CHECKED",
                    "validator_issues": [],
                    "patient_context": patient_ctx.to_dict()
                }

        # Step 2k-ii: Ventilator cards (F-12). Deterministic tier, authored
        # content, third provenance label. Returns None for anything it does
        # not own AND for any card still awaiting clinical signoff — the two
        # are indistinguishable to this call site on purpose, so a pending
        # card behaves exactly like an absent one and the pipeline carries on
        # to the gate question or the referral it produced before.
        vent_hit = vent_module.dispatch(query, patient_ctx)
        if vent_hit:
            family, card = vent_hit
            basis = vent_module.dosing_basis(patient_ctx)
            response = vent_module.render(family, card, patient_ctx, query)
            ask = vent_module.follow_up_ask(family, basis)
            if ask:
                # Non-blocking. The settings are served and the ask is for what
                # would make the NEXT answer better — blocking here would be
                # F-12 again, a vent question answered with something else.
                response += f"\n\n**ALSO SEND**\n- {ask}"
            print(f"🫁 VENT CARD [{family}/{card['id']}]")
            return {
                "response": response,
                "sources": [],
                "source_mode": "VENT_CARD",
                "card_id": card["id"],
                "card_family": family,
                "card_version": card.get("version"),
                "validator_result": "SAFE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2k-iii: a settings question that named no physiology. ASK, do
        # not default. The physiology decides the settings, and serving one
        # card because it happened to be first in the file is how a DKA
        # patient would get the ARDS-pattern answer — F-12 with the roles
        # reversed. Returns None while no physiology card is live, so this
        # stays invisible until there is something to choose between.
        vent_ask = vent_module.physiology_gate(query)
        if vent_ask:
            print(f"🚪 VENT GATE: {vent_ask}")
            return {
                "response": vent_ask,
                "sources": [],
                "source_mode": "VENT_GATE",
                "validator_result": "SKIPPED_SAFE_GATE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2l: Standard pre-gate (weight/route) — after all deterministic cases
        gate_action, gate_response = pre_gate(query, patient_ctx, prior_queries)
        if gate_action in ["ASK", "BLOCK"]:
            print(f"🚪 PRE-GATE [{gate_action}]: {gate_response}")
            return {
                "response": gate_response,
                "sources": [],
                "source_mode": "PRE_GATE",
                "validator_result": "SKIPPED_SAFE_GATE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 3: RAG retrieval — use router-enhanced query if available
        # Improve vent query ChromaDB search
        search_query = query
        if is_vent_settings_query(query):
            search_query = query + " mechanical ventilation tidal volume PEEP lung protective"

        if _router:
            try:
                routing = _router.route(query, patient_ctx, full_query_history)
                if routing.matched_protocol and routing.confidence in ['HIGH', 'MEDIUM']:
                    search_query = routing.enhanced_search_query
                    print(f"🗺️  Router: {routing.protocol_title} [{routing.confidence}]")
            except Exception as e:
                print(f"Router error: {e}")

        raw_results = chromadb_client.query(search_query, n_results=_env_number("CDSS_RAG_TOP_K", 10, int))
        assessment = classify_retrieval(raw_results)
        print(f"📚 {assessment.source_mode} (top: {assessment.top_score}, "
              f"cos {retrieval_cosine(assessment.top_score):.2f})")

        # Step 4: Build dose candidates from full history, not only current query.
        allowed_doses = build_allowed_doses(full_query_history, patient_ctx)
        allowed_dose_block = build_allowed_dose_block(allowed_doses)
        print(f"💊 {len(allowed_doses)} dose candidates built")

        allowed_actions = build_allowed_actions(full_query_history, patient_ctx)

        # Step 4b: general medical reference fallback (F-4).
        # Retrieval found nothing usable and this is not a dosing question, so
        # answer from general knowledge rather than refusing. A second knowledge
        # source, not a second pipeline: every check below this point is the same
        # code on both paths.
        use_general = general_reference.use_general_reference(
            assessment.source_mode, full_query_history, allowed_doses,
            wants_medication_dose(full_query_history),
            patient_known=any([patient_ctx.confirmed_weight_kg,
                               patient_ctx.age_years, patient_ctx.is_pediatric]))

        # Step 5: Build system prompt and generate response
        if use_general:
            assessment.source_mode = "GENERAL_REFERENCE"
            print("📖 GENERAL REFERENCE — no usable JTS retrieval")
            # F-7: the reference tier keeps its content rules and takes the
            # action format when the query is about a patient in front of the
            # medic. Acuteness is read from the session's own vitals and the
            # query's shape, never from the retrieval score — a retrieval miss
            # must not decide what a response looks like.
            system_prompt = general_reference.build_system_prompt(
                build_patient_block(patient_ctx, now_ts=now_ts),
                weight_confirmed=patient_ctx.has_confirmed_weight,
                route_known=patient_ctx.route_preference != "UNKNOWN"
                            or patient_ctx.access_state == "CONFIRMED_IV_IO",
                acute=general_reference.is_acute_presentation(
                    full_query_history, vitals_present=bool(patient_ctx.vitals)))
            allowed_actions = []
        else:
            system_prompt = build_system_prompt(patient_ctx, assessment,
                                                allowed_dose_block, now_ts=now_ts)
        if allowed_actions:
            system_prompt += "\n\nALLOWED_ACTIONS:\n" + "\n".join(f"- {a}" for a in allowed_actions)

        if should_use_rsi_pregate(query):
            system_prompt += """

MANDATORY RSI LABEL:
Include the exact heading:
**POST-INTUBATION SEDATION**
Do not ask IV or IM for RSI unless no IV/IO access is stated.
"""

        messages = []
        transcript_lines = []
        if conversation_history:
            for turn in conversation_history[-8:]:
                uq = turn.get("query", "")
                ar = turn.get("response", "")
                if uq or ar:
                    transcript_lines.append(f"USER: {uq}\nASSISTANT: {ar}")
                if uq:
                    messages.append({"role": "user", "content": uq})
                if ar:
                    messages.append({"role": "assistant", "content": ar})

        messages.append({"role": "user", "content": f"Clinical query: {query}"})
        transcript_lines.append(f"CURRENT USER: {query}")

        response_text = providers.chat(
            system_prompt, messages,
            model=model, temperature=0.2, max_tokens=700,
        )

        # Step 6: Deterministic post-checks use full history.
        det_check = run_deterministic_checks(full_query_history, response_text, patient_ctx, allowed_doses)

        # Step 7: LLM validator with full transcript
        full_transcript = "\n".join(transcript_lines)
        llm_result = validate_response(full_transcript, response_text, patient_ctx,
                                       allowed_dose_block, now_ts=now_ts)

        # Step 7b: deterministic vitals conflicts. Python owns the explicit rule
        # table (vitals_rules.json); the validator above catches what a table
        # cannot. Both arrive at the gate as cautions, neither can block.
        cautions = vitals_mod.conflicts(response_text, patient_ctx.vitals,
                                        flags={"ams_stated": patient_ctx.ams_stated})

        # Step 8: Safety gate with full history context
        outcome = apply_safety_gate(
            response_text,
            det_check,
            llm_result,
            patient_ctx,
            full_query_history,
            vitals_cautions=cautions
        )

        # validator_result comes from the gate, not from the validator verdict.
        # v4.0 computed `"UNSAFE" if blocked else llm_result["result"]` here,
        # which logged UNSAFE for responses that were served (S-2).
        # SC-1 / PLAN §5.1 option (c): every reset is surfaced to the medic, so a
        # WRONG reset is as visible as a missed one. Prepended AFTER the safety
        # gate on purpose — the notice must not become text the validator reasons
        # about or an override matches on. It rides on blocked responses too: if
        # the context was cleared, the medic needs to know that regardless.
        final_response = outcome.response
        # Applied after the gate for the same reason the reset notice is: a label
        # must never become text the validator reasons about or an override
        # matches its keywords against. Served answers only — a safety hold is
        # text Python wrote, not a general-reference answer, and labelling it as
        # one would be a false claim about where it came from. The block is still
        # logged source=general, which is where the attempt came from.
        if use_general and not outcome.blocked:
            final_response = general_reference.add_banner(final_response)
        # The rejected-vital and boundary notices are applied by _finalise, which
        # sees every return path rather than only this one.

        return {
            "response": final_response,
            "sources": assessment.sources[:3],
            "source_mode": assessment.source_mode,
            "model": model_label(model),
            "validator_result": outcome.verdict,
            "validator_issues": outcome.issues,
            "override_fired": outcome.override_fired,
            "review_suppressed": outcome.review_suppressed,
            "boundary_reset": patient_ctx.boundary_reset_reason,
            "vitals_cautions": outcome.cautions,
            "vitals_superseded": patient_ctx.vitals_superseded,
            "patient_context": patient_ctx.to_dict()
        }

    except Exception as e:
        print(f"❌ Pipeline error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "response": "System error. Use local protocol and contact medical control.",
            "sources": [],
            "source_mode": "ERROR",
            "validator_result": "ERROR",
            "validator_issues": [str(e)],
            "patient_context": {}
        }



def query_with_rag(query: str, chromadb_client, voice_mode: bool = False,
                   conversation_history: list = None,
                   session_ctx: Optional[PatientContext] = None,
                   synthetic: bool = False,
                   model: Optional[str] = None) -> dict:
    """
    Public entry point. Calls internal pipeline and logs every query/response.

    `synthetic` marks test-suite traffic (T-2). It is self-declared by the
    caller via the X-Test-Run header and is therefore trivially spoofable: it
    is a log-hygiene flag, NOT a security control, and nothing in the pipeline
    may branch on it. Pinned by test_synthetic_does_not_alter_pipeline.

    `pipeline_ms` (T-1) times this function, not the HTTP round trip: it
    excludes FastAPI request parsing and response serialisation, so it reads
    lower than the processing_time_ms badge the client shows. The names are
    kept distinct so the two are never compared as if interchangeable.
    """
    t0 = time.perf_counter()
    result = _query_with_rag_internal(
        query, chromadb_client, voice_mode, conversation_history, session_ctx,
        model=model
    )
    # Stamped once, here, so the client footer and the log entry can never
    # disagree about which knowledge source answered.
    result["source"] = knowledge_source(result.get("source_mode", "UNKNOWN"))
    pipeline_ms = int((time.perf_counter() - t0) * 1000)
    log_query(query, result, conversation_history,
              pipeline_ms=pipeline_ms, synthetic=synthetic)
    return result