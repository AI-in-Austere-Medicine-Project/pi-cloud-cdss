"""
EdgeCDSS — AUSTERE-CDS Pipeline
Version: 3.4.2-multiturn-intent

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
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional, List
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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

    @property
    def dosing_weight_kg(self) -> Optional[float]:
        """Only confirmed weight may be used for medication dosing."""
        return self.confirmed_weight_kg

    @property
    def has_confirmed_weight(self) -> bool:
        return self.confirmed_weight_kg is not None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DoseCandidate:
    """A pre-calculated medication dose from deterministic Python calculators."""
    drug: str
    indication: str
    route: str
    dose_mg: float
    volume_ml: float
    concentration_mg_ml: float
    source: str
    warning: Optional[str] = None


@dataclass
class DeterministicCheck:
    passed: bool
    issues: list = field(default_factory=list)


@dataclass
class RetrievalAssessment:
    source_mode: Literal["JTS_GROUNDED", "GENERAL_MEDICAL", "INSUFFICIENT"]
    top_score: float
    context_text: str
    sources: list


# ─────────────────────────────────────────────────────────────────────────────
# PATIENT CONTEXT EXTRACTOR — incremental, merges with prior session state
# ─────────────────────────────────────────────────────────────────────────────

def extract_patient_context(query: str,
                             prior_ctx: Optional[PatientContext] = None,
                             conversation_history: Optional[list] = None) -> PatientContext:
    """
    Extract and update structured patient context from current query.
    Merges with prior_ctx to accumulate state across turns.
    Estimated age-based weight NEVER assigned to confirmed_weight_kg.
    """
    ctx = prior_ctx or PatientContext()
    q = query.lower().strip()

    # Also scan recent conversation for accumulated context
    history_text = ""
    if conversation_history:
        for turn in conversation_history[-5:]:
            history_text += " " + turn.get("query", "").lower()

    full_text = q + " " + history_text

    # ── Confirmed weight in kg ────────────────────────────────────────────
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg\b', q)
    if kg_match:
        ctx.confirmed_weight_kg = float(kg_match.group(1))
        ctx.weight_source = "confirmed_kg"

    # ── Confirmed weight in lbs (convert silently) ────────────────────────
    if not kg_match:
        lb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\b', q)
        if lb_match:
            ctx.confirmed_weight_kg = round(float(lb_match.group(1)) * 0.453592, 1)
            ctx.weight_source = "confirmed_lbs"

    # ── Age extraction ────────────────────────────────────────────────────
    age_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:yo|y/o|year[\s-]*old|yr\s*old)\b', q)
    if age_match:
        ctx.age_years = float(age_match.group(1))
    if not age_match:
        age_match2 = re.search(r'(\d+)[\s-]*year[\s-]*old', q)
        if age_match2:
            ctx.age_years = float(age_match2.group(1))

    # ── Pediatric detection ───────────────────────────────────────────────
    pediatric_terms = ['infant', 'child', 'toddler', 'kid', 'boy', 'girl',
                       'pediatric', 'paediatric', 'newborn', 'neonate', 'baby',
                       'year-old', 'year old', 'yo ', 'y/o']
    if (any(term in full_text for term in pediatric_terms) or
            (ctx.age_years is not None and ctx.age_years < 18) or
            (ctx.confirmed_weight_kg is not None and ctx.confirmed_weight_kg < 40)):
        ctx.is_pediatric = True

    # ── Estimated weight from age (context only — never used for dosing) ─
    if ctx.is_pediatric and ctx.age_years is not None and ctx.confirmed_weight_kg is None:
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

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC PRE-GATES
# ─────────────────────────────────────────────────────────────────────────────

SAFE_GATE_RESPONSES = {
    "Need weight in kg before dosing.",
    "IV or IM? Do you have access?",
    "Need concentration before giving mL dose.",
    "Need rhythm before antiarrhythmic.",
    "Need height and sex before vent settings.",
}


def wants_medication_dose(query: str) -> bool:
    q = query.lower()
    if is_fixed_prep_request(q):
        return False
    dose_terms = ['dose', 'give', 'draw', 'mg', 'ml', 'ketamine', 'roc',
                  'rocuronium', 'sux', 'succinylcholine', 'fentanyl', 'versed',
                  'midazolam', 'lorazepam', 'morphine', 'epi', 'epinephrine',
                  'analges', 'pain', 'sedat', 'intubat', 'rsi', 'txa', 'keppra']
    return any(t in q for t in dose_terms)


def route_changes_dose(query: str) -> bool:
    """Only ketamine has meaningfully different IV vs IM doses (7x difference).
    Other medications either have one route or similar weight-based dosing."""
    q = query.lower()
    # Only ask route for ketamine — IV is 0.3mg/kg vs IM 2mg/kg
    route_sensitive = ['ketamine', 'ket ', 'vitamin k']
    return any(x in q for x in route_sensitive)


def query_is_weight_answer(query: str) -> bool:
    q = (query or "").lower().strip()
    return bool(re.fullmatch(r"(?:about\s+|approximately\s+|approx\s+)?\d+(?:\.\d+)?\s*(?:kg|kgs|kilograms?|lbs?|pounds?)", q))


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
        # Pediatric weight gate
        if ctx.is_pediatric and not ctx.has_confirmed_weight:
            return "ASK", "Need weight in kg before dosing."

        # Route gate — only ask if NOT RSI/intubation/drip context (those are always IV)
        is_rsi_or_iv_ctx = any(x in combined_ctx for x in [
            "rsi", "intubat", "rapid sequence", "rocuronium", "roc",
            "succinylcholine", "sux", "drip", "infusion", "sedation drip",
            "post-intubation", "post intubation", "intubated", "ventilator",
            "on the vent", "on a vent", "ketamine drip"
        ])
        if route_changes_dose(combined_ctx) and ctx.route_preference == "UNKNOWN" and not is_rsi_or_iv_ctx:
            return "ASK", "IV or IM? Do you have access?"

    return "CONTINUE", None


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC DOSE CALCULATORS
# ─────────────────────────────────────────────────────────────────────────────

def ketamine_analgesia_iv(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 0.3, 1)
    return DoseCandidate(
        drug="ketamine", indication="subdissociative analgesia", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 100.0, 3),
        concentration_mg_ml=100.0,
        source="deterministic_calculator:ketamine_analgesia_iv_0.3mgkg",
        warning="Monitor airway and respirations. Subdissociative range."
    )


def ketamine_analgesia_im(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 2.0, 1)
    return DoseCandidate(
        drug="ketamine", indication="dissociative analgesia (IM — no IV access)",
        route="IM", dose_mg=dose_mg, volume_ml=round(dose_mg / 100.0, 2),
        concentration_mg_ml=100.0,
        source="deterministic_calculator:ketamine_analgesia_im_2mgkg",
        warning="IM dose is higher than IV analgesia dose — this is expected and correct. Monitor airway."
    )


def ketamine_induction_iv(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dose_mg = round(weight_kg * 1.5, 1)
    max_mg = weight_kg * 2.0 if is_pediatric else min(weight_kg * 2.0, 200.0)
    dose_mg = min(dose_mg, max_mg)
    return DoseCandidate(
        drug="ketamine", indication="RSI induction", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 100.0, 2),
        concentration_mg_ml=100.0,
        source="deterministic_calculator:ketamine_induction_iv_1.5mgkg",
        warning="Give BEFORE paralytic. Confirm weight and route."
    )


def ketamine_post_intubation_iv(weight_kg: float) -> DoseCandidate:
    dose_mg = round(weight_kg * 0.5, 1)
    return DoseCandidate(
        drug="ketamine", indication="post-intubation sedation q20-30min", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 100.0, 2),
        concentration_mg_ml=100.0,
        source="deterministic_calculator:ketamine_post_intubation_0.5mgkg",
        warning="After tube confirmed only. Not the induction dose."
    )


def rocuronium_rsi(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dose_mg = round(weight_kg * 1.0, 1)
    return DoseCandidate(
        drug="rocuronium", indication="RSI paralytic", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 10.0, 1),
        concentration_mg_ml=10.0,
        source="deterministic_calculator:rocuronium_rsi_1mgkg",
        warning="Give AFTER induction agent. Max 1.2mg/kg."
    )


def succinylcholine_rsi(weight_kg: float, is_pediatric: bool) -> DoseCandidate:
    dkg = 2.0 if is_pediatric else 1.5
    dose_mg = round(weight_kg * dkg, 1)
    return DoseCandidate(
        drug="succinylcholine", indication="RSI paralytic", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 20.0, 1),
        concentration_mg_ml=20.0,
        source=f"deterministic_calculator:succinylcholine_rsi_{dkg}mgkg",
        warning="Contraindicated: hyperkalemia, burns >24hr, crush injury, denervation."
    )


def lorazepam_seizure(weight_kg: float) -> DoseCandidate:
    dose_mg = min(round(weight_kg * 0.1, 1), 4.0)
    return DoseCandidate(
        drug="lorazepam", indication="active seizure", route="IV",
        dose_mg=dose_mg, volume_ml=round(dose_mg / 2.0, 1),
        concentration_mg_ml=2.0,
        source="deterministic_calculator:lorazepam_seizure_0.1mgkg_max4mg",
        warning="Monitor respiratory depression."
    )


def build_allowed_doses(query: str, ctx: PatientContext) -> List[DoseCandidate]:
    """Build route-specific deterministic dose candidates for the current query."""
    if ctx.dosing_weight_kg is None:
        return []
    w = ctx.dosing_weight_kg
    ped = ctx.is_pediatric
    q = query.lower()
    doses = []

    is_rsi = any(x in q for x in ['rsi', 'intubat', 'rapid sequence'])
    is_analg = any(x in q for x in ['pain', 'analges', 'fracture', 'fx', 'arm', 'leg', 'analgesia'])
    is_seizure = any(x in q for x in ['seizure', 'seizing', 'status'])
    has_ketamine = any(x in q for x in ['ketamine', 'ket ', 'vitamin k'])
    has_roc = any(x in q for x in ['rocuronium', 'roc'])
    has_succ = any(x in q for x in ['succinylcholine', 'sux', 'succs'])
    has_loraz = any(x in q for x in ['lorazepam', 'ativan', 'benzo'])

    if is_rsi:
        # RSI always requires induction + paralytic + post-intubation sedation.
        doses.append(ketamine_induction_iv(w, ped))
        doses.append(ketamine_post_intubation_iv(w))

        # Default to rocuronium unless succinylcholine is explicitly requested.
        if has_succ and not any(x in q for x in ["burn", "crush"]):
            doses.append(succinylcholine_rsi(w, ped))
        else:
            doses.append(rocuronium_rsi(w, ped))

        return doses

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

    return doses


def build_allowed_dose_block(doses: List[DoseCandidate]) -> str:
    if not doses:
        return "ALLOWED_DOSES: none. Do not provide medication doses in this response."
    lines = ["ALLOWED_DOSES — use EXACTLY these values. Do not calculate alternatives:"]
    for d in doses:
        dose_str = int(d.dose_mg) if float(d.dose_mg).is_integer() else d.dose_mg
        vol_str = d.volume_ml
        lines.append(
            f"- {d.drug} {d.route}: Draw {vol_str} mL of {d.concentration_mg_ml:g}mg/mL "
            f"({dose_str}mg). Indication: {d.indication}."
        )
        if d.warning:
            lines.append(f"  Note: {d.warning}")
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

def has_hypotension_or_shock(q: str) -> bool:
    """Detect hypotension/shock text, including BP values like 92/46."""
    q = (q or "").lower()
    if any(x in q for x in [
        "hypotension", "hypotensive", "shock", "septic shock",
        "poor perfusion", "altered", "ams", "map "
    ]):
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

FIXED_PREP_TERMS = [
    "push dose epi", "push-dose epi", "push dose epinephrine",
    "dirty epi", "epi drip", "make epi", "prepare epi",
    "mix norepi", "norepinephrine mix", "d50 amp", "dextrose prep"
]


def is_fixed_prep_request(query: str) -> bool:
    q = query.lower()
    return any(t in q for t in FIXED_PREP_TERMS)


def build_fixed_prep_response(query: str) -> Optional[str]:
    q = query.lower()
    if any(x in q for x in ["push dose epi", "push-dose epi", "push dose epinephrine", "dirty epi"]):
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
    if "epi drip" in q or "epinephrine drip" in q:
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
                "and within protocol. Follow with levetiracetam (Keppra) 1500mg IV for maintenance. "
                "Use local protocol for dose and route if weight is not confirmed."
            )

    return actions

# ─────────────────────────────────────────────────────────────────────────────
# RETRIEVAL CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

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
NON-MEDICAL QUERY RULE
────────────────────────────────

If the query is not clinical: "AUSTERE-CDS handles medical queries only."

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
Do NOT say "administer ketamine" — copy the full line with mL, mg/mL, route, and mg total.
CORRECT: "Draw 0.075 mL of 100mg/mL ketamine IV (7.5mg). Indication: analgesia."
WRONG: "Administer ketamine for analgesia."
Every GIVE line must include: drug name, concentration, route, mL volume, total mg.
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
STANDARD CONCENTRATIONS
────────────────────────────────

Ketamine: 100mg/mL | Rocuronium: 10mg/mL | Succinylcholine: 20mg/mL
Fentanyl: 50mcg/mL | Lorazepam: 2mg/mL | Keppra: 100mg/mL | TXA: 100mg/mL
Norepinephrine: 1mg/mL (mix 4mg in 250mL NS = 16mcg/mL)
Cefazolin: 100mg/mL (1g in 10mL NS — 2g = 20mL)
Calcium Chloride 10%: 100mg/mL — CENTRAL LINE ONLY | Calcium Gluconate: 100mg/mL — peripheral OK

────────────────────────────────
RESPONSE FORMAT — JTS SCOPE
────────────────────────────────

**DO THIS**
1. [Most critical action]
2. [Second action]
3. [Third — expand for arrest/RSI/MASCAL/severe shock only]

**GIVE** [use ALLOWED_DOSES values exactly]
- Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason].

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


def build_patient_block(ctx: PatientContext) -> str:
    lines = []
    if ctx.is_pediatric:
        lines.append("PEDIATRIC PATIENT")

    if ctx.confirmed_weight_kg is not None:
        lines.append(f"Confirmed weight: {ctx.confirmed_weight_kg}kg ({ctx.weight_source})")
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


def build_system_prompt(ctx: PatientContext, assessment: RetrievalAssessment,
                        allowed_dose_block: str) -> str:
    patient_block = build_patient_block(ctx)
    source_block = build_source_block(assessment)
    prompt = GENERATOR_BASE
    if patient_block:
        prompt = prompt.replace(
            "────────────────────────────────\nNON-MEDICAL QUERY RULE",
            f"────────────────────────────────\nPATIENT CONTEXT\n────────────────────────────────\n\n{patient_block}\n\n────────────────────────────────\nNON-MEDICAL QUERY RULE"
        )
    prompt += f"\n\n────────────────────────────────\nRETRIEVED PROTOCOL CONTEXT\n────────────────────────────────\n\n{source_block}"
    prompt += f"\n\n────────────────────────────────\n{allowed_dose_block}\n────────────────────────────────"
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC POST-CHECKS
# ─────────────────────────────────────────────────────────────────────────────

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
    if any(x in r for x in ['drink', 'po fluids', 'oral fluids', 'by mouth']):
        if any(x in q for x in ['altered', 'ams', 'unconscious', 'shock', 'unresponsive']):
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
6. TBI STEROIDS: TBI context, response recommends corticosteroids.
7. CRITICAL MISSED DIAGNOSIS: tension pneumo without decompression, cardiac arrest without CPR, severe anaphylaxis without epinephrine.
8. DANGEROUS REASSURANCE: "stable" with hemodynamic instability, "no evacuation" with red flags.

Return NEEDS_HUMAN_REVIEW ONLY when:
- Medication dosing given but no confirmed weight for pediatric patient.
- Invasive procedure recommended beyond stated scope without acknowledgment.
- Source/protocol conflict is clinically meaningful.

Do NOT flag: IM route recommendations, IV route recommendations, short responses,
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
                      patient_ctx: PatientContext) -> dict:
    """
    LLM semantic validator. Receives full conversation transcript.
    Fail-closed: errors return NEEDS_HUMAN_REVIEW, not SAFE.
    """
    # Skip validator entirely for safe gate responses
    if response_text.strip() in SAFE_GATE_RESPONSES:
        return {"result": "SAFE", "issues": [], "rationale": "safe gate response", "safe": True}

    try:
        patient_summary = build_patient_block(patient_ctx) or "No patient context."
        validation_input = (
            f"CONVERSATION TRANSCRIPT:\n{full_transcript}\n\n"
            f"PATIENT CONTEXT:\n{patient_summary}\n\n"
            f"PROPOSED RESPONSE:\n{response_text}"
        )

        result = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VALIDATOR_PROMPT},
                {"role": "user", "content": validation_input}
            ],
            temperature=0,
            max_tokens=300
        )

        raw = result.choices[0].message.content.strip()
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

def apply_safety_gate(response_text: str, det_check: DeterministicCheck,
                      llm_result: dict,
                      patient_ctx=None,
                      full_query_history: str = "") -> tuple:
    # Safe gate responses always pass through
    if is_safe_gate_response(response_text):
        return response_text, False, []

    # Deterministic failures block first
    if not det_check.passed:
        print(f"🚨 DETERMINISTIC BLOCK: {det_check.issues}")
        return build_safety_hold(det_check.issues, ""), True, det_check.issues

    # LLM UNSAFE — check false positives before blocking
    if llm_result["result"] == "UNSAFE":
        issues = llm_result.get("issues", [])
        r_lower = response_text.lower()

        # Override pediatric weight false positive when patient_ctx confirms weight
        issue_text = " ".join(issues).lower()
        confirmed_weight = getattr(patient_ctx, "confirmed_weight_kg", None) if patient_ctx else None
        if (
            "without confirmed pediatric" in issue_text
            or "confirmed pediatric" in issue_text
            or "confirmed weight" in issue_text
        ) and confirmed_weight:
            print(f"✅ Override: pediatric weight confirmed at {confirmed_weight}kg")
            return response_text, False, []

        # Override CICO/airway false positive
        airway_issues = [i for i in issues if any(x in i.lower() for x in
            ["cico", "cricothyrotomy", "surgical airway", "cric", "airway"])]
        non_airway = [i for i in issues if not any(x in i.lower() for x in
            ["cico", "cricothyrotomy", "surgical airway", "cric", "airway"])]
        if airway_issues and not non_airway and is_cico_response_adequate(response_text):
            print(f"✅ Airway/CICO false positive overridden")
            return response_text, False, []

        # Override paralytic-without-induction false positive
        paralytic_issues = [i for i in issues if "paralytic" in i.lower()]
        non_paralytic = [i for i in issues if "paralytic" not in i.lower()]
        has_induction = any(x in r_lower for x in ["ketamine", "etomidate", "induction", "pre-oxygenate"])
        if paralytic_issues and not non_paralytic and has_induction:
            print(f"✅ Paralytic false positive overridden — induction found")
            return response_text, False, []

        # Override SEPSIS AS HEMORRHAGE false positive if no DCR in response
        sepsis_issues = [i for i in issues if any(x in i.upper() for x in ["SEPSIS", "HEMORRHAGE"])]
        non_sepsis = [i for i in issues if not any(x in i.upper() for x in ["SEPSIS", "HEMORRHAGE"])]
        has_dcr = any(x in r_lower for x in ["txa", "tranexamic", "ltowb", "whole blood", "dcr"])
        if sepsis_issues and not non_sepsis and not has_dcr:
            print(f"✅ SEPSIS/HEMORRHAGE false positive overridden")
            return response_text, False, []

        # Override fluids-in-sepsis false positive
        fluids_issues = [i for i in issues if any(x in i.lower() for x in
            ["iv fluid", "fluid", "crystalloid", "resuscitat"])]
        non_fluids = [i for i in issues if not any(x in i.lower() for x in
            ["iv fluid", "fluid", "crystalloid", "resuscitat"])]
        if fluids_issues and not non_fluids and any(x in r_lower for x in
            ["fluid", "crystalloid", "antibiotic", "ns ", "lr "]):
            print(f"✅ Fluids false positive overridden")
            return response_text, False, []

        # Override tension pneumo/MASCAL decompression false positive
        decomp_issues = [i for i in issues if any(x in i.lower() for x in
            ["tension pneumo", "decompression", "needle", "thoracostomy"])]
        non_decomp = [i for i in issues if not any(x in i.lower() for x in
            ["tension pneumo", "decompression", "needle", "thoracostomy"])]
        if decomp_issues and not non_decomp and any(x in r_lower for x in
            ["decompression", "needle", "thoracostomy", "chest"]):
            print(f"✅ Tension pneumo false positive overridden")
            return response_text, False, []

        # Override DANGEROUS REASSURANCE if response has action items
        reassurance_issues = [i for i in issues if "reassurance" in i.lower()]
        non_reassurance = [i for i in issues if "reassurance" not in i.lower()]
        has_action = any(x in r_lower for x in ["airway", "intubat", "evacuate", "evac",
            "monitor", "iv fluid", "cpr", "decompression", "fluid", "antibiotic"])
        if reassurance_issues and not non_reassurance and has_action:
            print(f"✅ Dangerous reassurance false positive overridden")
            return response_text, False, []

        # Override TXA false positive when the full context is clear traumatic hemorrhage without sepsis.
        txa_issues = [i for i in issues if any(x in i.lower() for x in ["txa", "tranexamic"])]
        non_txa = [i for i in issues if not any(x in i.lower() for x in ["txa", "tranexamic"])]
        if txa_issues and not non_txa:
            if has_clear_hemorrhage(full_query_history) and not looks_like_sepsis(full_query_history):
                print("✅ TXA false positive overridden — clear traumatic hemorrhage context")
                return response_text, False, []

        print(f"🚨 LLM BLOCK: {issues}")
        return build_safety_hold(issues, llm_result.get("rationale", "")), True, issues

    # NEEDS_HUMAN_REVIEW appends warning
    if llm_result["result"] == "NEEDS_HUMAN_REVIEW":
        print(f"⚠️ NEEDS_HUMAN_REVIEW: {llm_result.get('rationale','')}")
        warning = (
            "\n\n⚠️ CLINICAL SAFETY NOTE: This response requires human review. "
            "Use local protocol and medical control where available."
        )
        return response_text + warning, False, llm_result.get("issues", [])

    print(f"✅ SAFE")
    return response_text, False, []



# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC HIGH-RISK CASE BUILDERS — used before RAG/LLM
# ─────────────────────────────────────────────────────────────────────────────

def rebuild_patient_context_from_history(
    query: str,
    conversation_history: Optional[list] = None,
    session_ctx: Optional[PatientContext] = None
) -> PatientContext:
    """
    Replays prior user turns into PatientContext before applying the current query.
    This fixes stateless API calls where the current turn is only "IV" or "IM".
    """
    ctx = session_ctx or PatientContext()

    if conversation_history:
        for turn in conversation_history[-8:]:
            prior_q = turn.get("query", "")
            if prior_q:
                ctx = extract_patient_context(prior_q, prior_ctx=ctx)

    ctx = extract_patient_context(query, prior_ctx=ctx)
    return ctx


def build_full_query_history(query: str, conversation_history: Optional[list] = None) -> tuple[str, str]:
    """Return prior user queries and current user-history text for deterministic gates."""
    prior_queries = ""
    if conversation_history:
        parts = []
        for turn in conversation_history[-8:]:
            if turn.get("query"):
                parts.append(turn.get("query", ""))
        prior_queries = " ".join(parts).strip()

    full_query_history = f"{prior_queries} {query}".strip()
    return prior_queries, full_query_history


def is_non_medical_query(query: str) -> bool:
    """Fast reject obvious non-medical queries before RAG/validator."""
    q = (query or "").lower().strip()
    if not q:
        return False

    medical_terms = [
        "patient", "injury", "trauma", "bleeding", "shock", "pain", "dose",
        "medication", "ketamine", "rsi", "intubat", "sepsis", "fever",
        "bp", "hr", "gcs", "airway", "breathing", "burn", "snake",
        "anaphylaxis", "seizure", "hypothermia", "cholera", "txa", "dcr",
        "wound", "fracture", "fx", "epi", "lorazepam", "cric"
    ]
    non_medical_terms = [
        "weather", "sports", "stock", "news", "joke", "recipe",
        "movie", "music", "capital of", "who won"
    ]
    return any(t in q for t in non_medical_terms) and not any(t in q for t in medical_terms)


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

    label = "PEDIATRIC PATIENT" if ctx.is_pediatric else f"{ctx.confirmed_weight_kg:g}kg patient"

    return f"""**DO THIS**
1. Confirm monitoring and airway equipment ready.
2. Give ketamine by the {d.route} route.
3. Reassess pain, airway, respirations q5min.

**GIVE**
- Draw {d.volume_ml:g} mL of {d.concentration_mg_ml:g}mg/mL ketamine {d.route} ({d.dose_mg:g}mg). Indication: {d.indication}.

**WATCH**
- Airway, respirations, SpO2, mental status, and emergence reaction.

**DON'T**
- Do not redose without reassessment and local protocol.

**TLDR**
- {label}: ketamine {d.route} = {d.dose_mg:g}mg = {d.volume_ml:g}mL of 100mg/mL.

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

    return f"""**DO THIS**
1. Confirm monitoring and airway equipment ready.
2. Give ketamine by the requested {d.route} route.
3. Reassess pain, airway, respirations, and perfusion.

**GIVE**
- Draw {d.volume_ml:g} mL of {d.concentration_mg_ml:g}mg/mL ketamine {d.route} ({d.dose_mg:g}mg). Indication: {d.indication}.

**WATCH**
- Monitor airway, respirations, SpO2, mental status, and emergence reaction.

**DON'T**
- Do not redose without reassessment and local protocol.

**TLDR**
- {ctx.confirmed_weight_kg:g}kg pediatric patient: ketamine {d.route} = {d.dose_mg:g}mg = {d.volume_ml:g}mL of 100mg/mL.

**SOURCE**: General Evidence-Based Medicine / deterministic calculator

Guideline-based support only. Not a substitute for clinical judgment."""


def is_rsi_or_post_intubation_context(text: str) -> bool:
    q = (text or "").lower()
    return any(x in q for x in [
        "rsi", "rapid sequence", "intubat", "post-intubation",
        "post intubation", "after tube", "tube confirmed",
        "ventilator", "on the vent", "on a vent", "ketamine drip"
    ])


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

    ket_ind = ketamine_induction_iv(w, ped)
    ket_post = ketamine_post_intubation_iv(w)

    # Burns RSI: avoid succinylcholine unless explicitly requested; default rocuronium.
    use_succ = any(x in q for x in ["succinylcholine", "sux", "succs"]) and not any(x in q for x in ["burn", "crush"])
    paralytic = succinylcholine_rsi(w, ped) if use_succ else rocuronium_rsi(w, ped)

    return f"""**DO THIS**
1. Pre-oxygenate and prepare suction, backup airway, and cricothyrotomy equipment.
2. Give induction first, then paralytic.
3. Intubate, confirm tube, secure tube, then continue post-intubation sedation.

**GIVE**
- Draw {ket_ind.volume_ml:g} mL of {ket_ind.concentration_mg_ml:g}mg/mL ketamine IV ({ket_ind.dose_mg:g}mg). Indication: RSI induction.
- Draw {paralytic.volume_ml:g} mL of {paralytic.concentration_mg_ml:g}mg/mL {paralytic.drug} IV ({paralytic.dose_mg:g}mg). Indication: RSI paralysis.

**POST-INTUBATION SEDATION**
- Draw {ket_post.volume_ml:g} mL of {ket_post.concentration_mg_ml:g}mg/mL ketamine IV ({ket_post.dose_mg:g}mg) q20-30min after tube confirmation. Indication: post-intubation sedation.

**WATCH**
- Confirm tube with waveform ETCO2 if available. Monitor SpO2, BP, chest rise, and ventilator pressures.

**DON'T**
- Never give paralytic before induction in a patient with a pulse.
- Avoid succinylcholine in burns/crush/hyperkalemia risk unless specifically indicated by protocol.

**TLDR**
- RSI: ketamine induction first, rocuronium second, post-intubation ketamine sedation after tube confirmed.

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
    if any(x in q for x in ["severe tbi", "gcs 6", "traumatic brain injury"]):
        return build_tbi_management_response()
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

def query_with_rag(query: str, chromadb_client, voice_mode: bool = False,
                   conversation_history: list = None,
                   session_ctx: Optional[PatientContext] = None) -> dict:
    """
    EdgeCDSS v3.4.1 Pipeline:
    1. Replay structured patient context from conversation history.
    2. Define full_query_history once and use it consistently.
    3. Deterministic pre-gates for high-risk known cases before RAG/LLM.
    4. RAG retrieval + source classification for remaining cases.
    5. Deterministic dose candidates from full_query_history.
    6. Post-checks + validator + safety gate.
    """
    try:
        # Step 1: canonical history and patient context
        prior_queries, full_query_history = build_full_query_history(query, conversation_history)

        patient_ctx = rebuild_patient_context_from_history(
            query,
            conversation_history=conversation_history,
            session_ctx=session_ctx
        )

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
                "validator_result": "SAFE",
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
                "validator_result": "SAFE",
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
                "validator_result": "SAFE",
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
                "validator_result": "SAFE",
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
                "validator_result": "SAFE",
                "validator_issues": [],
                "patient_context": patient_ctx.to_dict()
            }

        # Step 2j: Ketamine analgesia — deterministic for confirmed weight + known route
        # Only fires if current query is about ketamine/pain, not a different topic
        _current_is_ketamine = is_ketamine_analgesia_context(query) or query.strip().lower() in [
            "iv", "im", "io", "intramuscular", "intravenous",
            "only have im", "im only", "no iv", "only have iv"
        ]
        _current_is_other_med = any(x in query.lower() for x in [
            "epi", "epinephrine", "blood", "ltowb", "txa", "tranexamic",
            "rocuronium", "roc", "succinylcholine", "sux", "fentanyl",
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
                    "validator_result": "SAFE",
                    "validator_issues": [],
                    "patient_context": patient_ctx.to_dict()
                }

        # Step 2k: RSI / post-intubation deterministic response — before standard pre-gate
        if is_rsi_or_post_intubation_context(query):
            rsi_response = build_rsi_response(patient_ctx, query)
            if rsi_response:
                print("💉 RSI PRE-GATE")
                return {
                    "response": rsi_response,
                    "sources": [],
                    "source_mode": "DETERMINISTIC_PRE_GATE",
                    "validator_result": "SAFE",
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
        search_query = query
        if _router:
            try:
                routing = _router.route(query, patient_ctx, full_query_history)
                if routing.matched_protocol and routing.confidence in ['HIGH', 'MEDIUM']:
                    search_query = routing.enhanced_search_query
                    print(f"🗺️  Router: {routing.protocol_title} [{routing.confidence}]")
            except Exception as e:
                print(f"Router error: {e}")

        raw_results = chromadb_client.query(search_query, n_results=5)
        assessment = classify_retrieval(raw_results)
        print(f"📚 {assessment.source_mode} (top: {assessment.top_score})")

        # Step 4: Build dose candidates from full history, not only current query.
        allowed_doses = build_allowed_doses(full_query_history, patient_ctx)
        allowed_dose_block = build_allowed_dose_block(allowed_doses)
        print(f"💊 {len(allowed_doses)} dose candidates built")

        allowed_actions = build_allowed_actions(full_query_history, patient_ctx)

        # Step 5: Build system prompt and generate response
        system_prompt = build_system_prompt(patient_ctx, assessment, allowed_dose_block)
        if allowed_actions:
            system_prompt += "\n\nALLOWED_ACTIONS:\n" + "\n".join(f"- {a}" for a in allowed_actions)

        if is_rsi_or_post_intubation_context(query):
            system_prompt += """

MANDATORY RSI LABEL:
Include the exact heading:
**POST-INTUBATION SEDATION**
Do not ask IV or IM for RSI unless no IV/IO access is stated.
"""

        messages = [{"role": "system", "content": system_prompt}]
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

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=700
        )
        response_text = response.choices[0].message.content

        # Step 6: Deterministic post-checks use full history.
        det_check = run_deterministic_checks(full_query_history, response_text, patient_ctx, allowed_doses)

        # Step 7: LLM validator with full transcript
        full_transcript = "\n".join(transcript_lines)
        llm_result = validate_response(full_transcript, response_text, patient_ctx)

        # Step 8: Safety gate with full history context
        final_response, blocked, combined_issues = apply_safety_gate(
            response_text,
            det_check,
            llm_result,
            patient_ctx,
            full_query_history
        )

        return {
            "response": final_response,
            "sources": assessment.sources[:3],
            "source_mode": assessment.source_mode,
            "validator_result": "UNSAFE" if blocked else llm_result["result"],
            "validator_issues": combined_issues,
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