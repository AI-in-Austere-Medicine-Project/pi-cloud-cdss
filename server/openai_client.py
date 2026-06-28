"""
EdgeCDSS — AUSTERE-CDS Pipeline
Version: 3.2.0

Architecture:
  1. Patient context extraction (weight, age, pediatric, scope)
  2. ChromaDB RAG + source confidence classification
  3. Deterministic safety checks (Python math — no LLM)
  4. GPT-4o-mini clinical response generator (layered prompt, dynamic context injection)
  5. LLM safety validator (narrow semantic scope — fail-closed)
  6. Safety gate (deterministic failures block first, then LLM result)
  7. Validated response delivery

Validator: FAIL-CLOSED. Validator error = NEEDS_HUMAN_REVIEW appended, not pass-through.
Deterministic calculators own all medication math. LLM validator handles semantic reasoning only.
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import Literal, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PatientContext:
    age_years: Optional[float] = None
    weight_kg: Optional[float] = None
    weight_source: str = "unknown"
    sex: Optional[str] = None
    is_pediatric: bool = False
    provider_scope: str = "UNKNOWN"


@dataclass
class DoseResult:
    drug: str
    dose_mg: float
    max_mg: float
    volume_ml: float
    concentration_mg_ml: float
    route: str
    safe: bool
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
# PATIENT CONTEXT EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

def extract_patient_context(query: str) -> PatientContext:
    ctx = PatientContext()
    q = query.lower()

    # Weight in kg
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*kg', q)
    if kg_match:
        ctx.weight_kg = float(kg_match.group(1))
        ctx.weight_source = "stated_kg"

    # Weight in lbs
    if not ctx.weight_kg:
        lb_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)', q)
        if lb_match:
            ctx.weight_kg = round(float(lb_match.group(1)) * 0.453592, 1)
            ctx.weight_source = "stated_lbs_converted"

    # Age
    age_match = re.search(r'(\d+)[\s-]*year[\s-]*old', q)
    if age_match:
        ctx.age_years = float(age_match.group(1))
        if not ctx.weight_kg and ctx.age_years < 14:
            age_to_weight = {1: 10, 2: 12, 4: 16, 6: 20, 8: 25, 10: 32, 12: 38, 14: 45}
            closest = min(age_to_weight.keys(), key=lambda x: abs(x - ctx.age_years))
            ctx.weight_kg = age_to_weight[closest]
            ctx.weight_source = "estimated_from_age"

    # Pediatric detection
    pediatric_terms = ['infant', 'child', 'toddler', 'kid', 'boy', 'girl',
                       'pediatric', 'paediatric', 'newborn', 'neonate', 'baby',
                       'year-old', 'year old']
    ctx.is_pediatric = (
        any(term in q for term in pediatric_terms) or
        (ctx.age_years is not None and ctx.age_years < 18) or
        (ctx.weight_kg is not None and ctx.weight_kg < 40)
    )

    # Provider scope
    scope_map = {
        'bls': 'BLS', 'basic life support': 'BLS',
        'emt': 'EMT', 'emt-b': 'EMT',
        'paramedic': 'PARAMEDIC', 'medic': 'PARAMEDIC',
        'critical care': 'CRITICAL_CARE', 'flight medic': 'CRITICAL_CARE',
        'ccemtp': 'CRITICAL_CARE',
        'physician': 'PHYSICIAN', 'doctor': 'PHYSICIAN', 'md': 'PHYSICIAN',
    }
    for term, scope in scope_map.items():
        if term in q:
            ctx.provider_scope = scope
            break

    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC DOSE CALCULATORS
# ─────────────────────────────────────────────────────────────────────────────

def calc_ketamine_induction(weight_kg: float, is_pediatric: bool) -> DoseResult:
    dose_mg = weight_kg * 1.5
    max_mg = weight_kg * 2.0 if is_pediatric else min(weight_kg * 2.0, 200.0)
    dose_mg = min(dose_mg, max_mg)
    conc = 100.0
    return DoseResult(drug="ketamine", dose_mg=round(dose_mg, 1), max_mg=round(max_mg, 1),
                      volume_ml=round(dose_mg / conc, 2), concentration_mg_ml=conc,
                      route="IV", safe=True, warning="Confirm weight, route, concentration.")


def calc_ketamine_post_intubation(weight_kg: float) -> DoseResult:
    dose_mg = weight_kg * 0.5
    conc = 100.0
    return DoseResult(drug="ketamine (post-intubation)", dose_mg=round(dose_mg, 1),
                      max_mg=round(weight_kg * 1.0, 1), volume_ml=round(dose_mg / conc, 2),
                      concentration_mg_ml=conc, route="IV", safe=True,
                      warning="After tube confirmed only. Not the induction dose.")


def calc_rocuronium(weight_kg: float, is_pediatric: bool) -> DoseResult:
    dose_mg = weight_kg * 1.0
    max_mg = weight_kg * 1.2
    conc = 10.0
    return DoseResult(drug="rocuronium", dose_mg=round(dose_mg, 1), max_mg=round(max_mg, 1),
                      volume_ml=round(dose_mg / conc, 1), concentration_mg_ml=conc,
                      route="IV", safe=True, warning="Do not give without prior induction agent.")


def calc_succinylcholine(weight_kg: float, is_pediatric: bool) -> DoseResult:
    dkg = 2.0 if is_pediatric else 1.5
    dose_mg = weight_kg * dkg
    conc = 20.0
    return DoseResult(drug="succinylcholine", dose_mg=round(dose_mg, 1),
                      max_mg=round(weight_kg * 2.0, 1), volume_ml=round(dose_mg / conc, 1),
                      concentration_mg_ml=conc, route="IV", safe=True,
                      warning="Contraindicated: hyperkalemia, burns >24hr, crush, denervation.")


def calc_lorazepam(weight_kg: float) -> DoseResult:
    dose_mg = min(weight_kg * 0.1, 4.0)
    conc = 2.0
    return DoseResult(drug="lorazepam", dose_mg=round(dose_mg, 1), max_mg=4.0,
                      volume_ml=round(dose_mg / conc, 1), concentration_mg_ml=conc,
                      route="IV", safe=True, warning="Monitor respiratory depression.")


def calc_cefazolin() -> DoseResult:
    return DoseResult(drug="cefazolin", dose_mg=2000, max_mg=2000, volume_ml=20.0,
                      concentration_mg_ml=100.0, route="IV", safe=True,
                      warning="Reconstitute 1g in 10mL NS = 100mg/mL. 2g = draw 20mL.")


def pediatric_vt(weight_kg: float) -> float:
    return round(weight_kg * 6.0, 0)


def adult_pbw(height_inches: float, sex: str) -> float:
    if sex.lower() in ['m', 'male']:
        return 50 + 2.3 * (height_inches - 60)
    return 45.5 + 2.3 * (height_inches - 60)


# ─────────────────────────────────────────────────────────────────────────────
# DETERMINISTIC SAFETY CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def run_deterministic_checks(query: str, response_text: str,
                              patient_ctx: PatientContext) -> DeterministicCheck:
    """
    Pure Python safety checks — no LLM involved.
    Checks medication math, hard contraindications, and route safety.
    """
    issues = []
    r = response_text.lower()
    q = query.lower()

    # Ketamine induction ceiling
    if patient_ctx.weight_kg:
        ceiling = patient_ctx.weight_kg * 2.0
        ket_doses = re.findall(r'ketamine[^\n]*?\((\d+(?:\.\d+)?)\s*mg\)',
                               response_text, re.IGNORECASE)
        for d in ket_doses:
            dose = float(d)
            if dose > ceiling and dose > (patient_ctx.weight_kg * 0.7):
                issues.append(
                    f"Ketamine {dose}mg exceeds induction ceiling "
                    f"({ceiling}mg = 2mg/kg for {patient_ctx.weight_kg}kg).")

    # Rocuronium ceiling
    if patient_ctx.weight_kg:
        ceiling = patient_ctx.weight_kg * 1.2
        roc_doses = re.findall(r'rocuronium[^\n]*?\((\d+(?:\.\d+)?)\s*mg\)',
                                response_text, re.IGNORECASE)
        for d in roc_doses:
            dose = float(d)
            if dose > ceiling:
                issues.append(
                    f"Rocuronium {dose}mg exceeds ceiling "
                    f"({ceiling}mg = 1.2mg/kg for {patient_ctx.weight_kg}kg).")

    # Paralytic without induction
    has_paralytic = any(x in r for x in ['rocuronium', 'succinylcholine', 'vecuronium', 'cisatracurium'])
    has_induction = any(x in r for x in ['ketamine', 'etomidate', 'propofol', 'midazolam', 'fentanyl'])
    if has_paralytic and not has_induction:
        if any(x in q for x in ['rsi', 'intubat', 'rapid sequence', 'tube']) and \
           'arrest' not in q:
            issues.append("Paralytic without induction agent — awake paralysis risk.")

    # TXA in sepsis/infection context
    if 'txa' in r or 'tranexamic' in r:
        if any(x in q for x in ['fever', 'infection', 'pus', 'sepsis', 'septic', 'abscess']):
            issues.append("TXA in sepsis/infection context. TXA is for hemorrhagic shock only.")
        if any(x in q for x in ['hypothermia', 'frozen', 'cold']) and \
           not any(x in q for x in ['bleeding', 'hemorrhage', 'trauma']):
            issues.append("TXA for hypothermia without hemorrhagic shock. Not indicated.")

    # WPW contraindications
    if 'wpw' in q or 'wolff' in q or 'pre-excitation' in q:
        for drug in ['adenosine', 'metoprolol', 'atenolol', 'diltiazem',
                     'verapamil', 'digoxin', 'beta-block', 'calcium channel']:
            if drug in r:
                issues.append(f"WPW contraindication: {drug} risks VF via accessory pathway.")

    # TBI steroids
    if any(x in q for x in ['tbi', 'traumatic brain', 'head injury', 'head trauma']):
        if any(x in r for x in ['dexamethasone', 'methylprednisolone', 'solu-medrol',
                                  'decadron', 'corticosteroid', 'steroid']):
            issues.append("Steroids in TBI increase mortality (CRASH trial). Contraindicated.")

    # IV potassium push
    if re.search(r'potassium.{0,30}iv\s+push|iv\s+push.{0,30}potassium', r):
        issues.append("IV potassium push is lethal. Never give potassium as a push dose.")

    # Calcium chloride peripheral
    if 'calcium chloride' in r and 'peripheral' in r:
        issues.append("Calcium chloride is central line only. Peripheral: calcium gluconate.")

    # Oral intake in altered mental status or shock
    if any(x in r for x in ['drink', 'po fluids', 'oral fluids', 'by mouth']):
        if any(x in q for x in ['altered', 'ams', 'unconscious', 'shock', 'unresponsive']):
            issues.append("Oral intake recommended in AMS or shock — aspiration risk.")

    return DeterministicCheck(passed=len(issues) == 0, issues=issues)


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
        source_mode=source_mode,
        top_score=round(top_score, 3),
        context_text=context_text,
        sources=sources
    )


# ─────────────────────────────────────────────────────────────────────────────
# GENERATOR SYSTEM PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

GENERATOR_BASE = """
You are AUSTERE-CDS, a voice-first clinical decision-support assistant for austere, prehospital, tactical, and Role 1-3 medical settings.

This system is a research prototype. It is not validated for patient-care decisions. Every response must support, not replace, qualified clinical judgment, local protocol, and medical control.

Your priorities, in order:
1. Prevent immediate death or irreversible harm.
2. Ask for missing safety-critical data before unsafe dosing or procedures.
3. Use retrieved JTS/TCCC protocol context when it is relevant.
4. Clearly label when guidance is based on general medical knowledge rather than retrieved protocol.
5. Keep output short enough to be heard through an earpiece during care.

────────────────────────────────
NON-MEDICAL QUERY RULE
────────────────────────────────

If the query is not medical, respond only:
"AUSTERE-CDS handles medical queries only. Ask me a clinical question."

────────────────────────────────
VOICE-FIRST STYLE
────────────────────────────────

Write for spoken delivery through an earpiece during active patient care.

- Short sentences.
- No tables. No long paragraphs.
- No formatting that requires visual reading to understand.
- Max 3 immediate actions unless arrest, RSI, MASCAL, CICO, or severe shock requires more.
- Life-saving action first.
- One critical warning unless more are needed to prevent immediate harm.
- Closed-loop language for high-risk medications: "Confirm weight. Confirm route. Confirm concentration."

────────────────────────────────
FIELD SLANG RECOGNITION
────────────────────────────────

Translate automatically — never ask for clarification on these terms:
rocky onium / roc → rocuronium
sux / succs → succinylcholine
vec → vecuronium
vitamin K / ket → ketamine
del tim / dilt → diltiazem (check rhythm first — WPW risk)
dirty epi / epi drip → epinephrine infusion
levo / levophed → norepinephrine
vaso → vasopressin
mag → magnesium sulfate
bicarb → sodium bicarbonate
push dose epi → epinephrine 10mcg/mL bolus prep
cric / front of neck / surgical airway → cricothyrotomy
venting the chest / needle the chest → needle decompression or finger thoracostomy
snake bite / snake bike → snakebite / envenomation
buddy transfusion / donor blood → field whole blood transfusion
bleeding out / hemorrhaging → hemorrhagic shock assessment
infection / pus / septic / infected wound → sepsis protocol — NOT DCR
cold / frozen / hypothermic → hypothermia protocol — NOT DCR
excited delirium / ExDS / agitated and combative → excited delirium protocol

────────────────────────────────
MISSING-DATA GATE
────────────────────────────────

Do not provide a medication dose when required data is missing.

If weight is required and missing, respond only:
"Need weight in kg before dosing."

If concentration is required for an mL dose and missing, respond:
"Need concentration before giving mL dose."

If rhythm is required for treatment selection and missing, respond:
"Need rhythm before antiarrhythmic."

If height and sex are needed for vent settings, respond:
"Need height and sex before vent settings."

────────────────────────────────
SOURCE DISCIPLINE
────────────────────────────────

For medication recommendations: prefer doses, routes, and concentrations from retrieved JTS protocol context.
If no relevant JTS protocol was retrieved for a medication: "No JTS protocol retrieved. Use local protocol."
Do not invent medication concentrations. Do not provide mL dose without a stated concentration.

Universal emergency exceptions (recommend without retrieval when clearly indicated):
- Epinephrine 1:10,000: 1mg IV q3-5min — cardiac arrest
- Epinephrine 1:1,000: 0.3mg IM (0.01mg/kg pediatric max 0.3mg) — anaphylaxis
- Naloxone: 0.4mg IV/IM — opioid overdose
- Aspirin: 324mg PO — suspected ACS
- Dextrose 50%: 25g IV — hypoglycemia

MORPHINE RESTRICTION: Never recommend morphine as a first-line analgesic.
Default field analgesic: ketamine subdissociative (0.1-0.3 mg/kg IV or 0.5 mg/kg IM).
Recommend morphine only if provider explicitly requests it or states no alternative exists.

ZERO MATH RULE: The provider does zero calculations.
Show only: final mL, total mg, route, concentration. Never show mg/kg steps.
Medication format: "Draw X mL of Y mg/mL [drug] [route] (Z mg total). Indication: [reason]."
Infusion format: "Mix X mg in Y mL NS (Z mg/mL). Start X mL/hr. Titrate X mL/hr q Y min. Max X mL/hr. Target: [goal]."

────────────────────────────────
SCOPE OF PRACTICE
────────────────────────────────

If provider scope is stated, keep recommendations inside that scope:
- BLS: assessment, positioning, oxygen per protocol, bleeding control, CPR/AED, evacuation.
- EMT: EMT-level interventions.
- Paramedic / Critical care / Physician: advanced interventions as appropriate.

If a recommendation may exceed typical scope: "Only if within your protocol and scope."

────────────────────────────────
HIGH-RISK CLINICAL RULES
────────────────────────────────

Flag these in your reasoning before responding:

SEPSIS vs HEMORRHAGE: Fever + infection source + hypotension = septic shock until proven otherwise.
Do not give TXA or blood product DCR unless hemorrhage is also clearly present.

TXA: Only for traumatic hemorrhagic shock within 3 hours of injury.
Not for: sepsis, medical shock, isolated TBI without hemorrhage, hypothermia alone, burns alone, >3 hours post-injury.

WPW: In WPW/pre-excitation with tachyarrhythmia — never give adenosine, beta-blockers, calcium-channel blockers, or digoxin.

TBI: Avoid hypotension and hypoxia. No routine hyperventilation unless herniation signs are present. No steroids.

PARALYTIC RULES:
1. Never give paralytic alone to a patient with a pulse. Exception: cardiac arrest only.
2. Induction agent MUST precede paralytic.
3. Post-intubation sedation MUST follow tube confirmation — separate lower dose.

SHOCK DIFFERENTIATION:
Hemorrhagic: trauma + active bleeding + no fever → DCR, LTOWB, TXA
Septic: fever + infection source + hypotension → sepsis protocol, antibiotics, fluids, NO TXA
Cardiogenic: JVD + chest pain + no bleeding → pressors, cautious fluids
Obstructive: JVD + tracheal deviation + trauma → decompress
Unclear: "Shock — cause unclear. Assess: bleeding, chest, infection, cardiac, anaphylaxis."

────────────────────────────────
RSI SEQUENCE
────────────────────────────────

For any RSI query, always in this order:
1. Pre-oxygenate — 100% O2, BVM if needed.
2. Prepare — suction, backup airway, tube sized, weight confirmed.
3. Give induction agent first — ketamine or etomidate before paralytic.
4. Give paralytic after induction.
5. Intubate when effect expected — roc ~60 sec, succ ~45 sec.
6. Confirm tube — EtCO2, chest rise, bilateral breath sounds.
7. Secure tube.
8. Give post-intubation sedation after tube confirmed.
9. Set ventilator.
10. Pressor plan if hypotensive.

Always include all three in GIVE for any RSI:
1. Induction ketamine
2. Paralytic rocuronium (or succinylcholine)
3. Post-intubation ketamine (after tube confirmed — lower dose)

If failed intubation + failed rescue airway + ongoing hypoxia/cyanosis:
"CICO: perform surgical airway/cricothyrotomy now if within scope and protocol."

────────────────────────────────
STANDARD CONCENTRATIONS
────────────────────────────────

Ketamine: 100mg/mL or 50mg/mL
Rocuronium: 10mg/mL
Succinylcholine: 20mg/mL
Fentanyl: 50mcg/mL
Lorazepam: 2mg/mL or 4mg/mL
Levetiracetam (Keppra): 100mg/mL
TXA: 100mg/mL
Norepinephrine: 1mg/mL (standard mix: 4mg in 250mL NS = 16mcg/mL)
Cefazolin: 100mg/mL (reconstitute 1g in 10mL NS — 2g dose = draw 20mL)
Ertapenem: 100mg/mL
Metronidazole (Flagyl): 5mg/mL premixed
Calcium Chloride 10%: 100mg/mL — CENTRAL LINE ONLY
Calcium Gluconate: 100mg/mL — peripheral OK
Magnesium Sulfate: 500mg/mL
Dextrose 50%: 0.5g/mL

────────────────────────────────
RESPONSE FORMAT — JTS SCOPE
────────────────────────────────

**DO THIS**
1. [Most critical action first]
2. [Second action]
3. [Third action — expand only for arrest, RSI, MASCAL, severe shock, CICO]

**GIVE** [medications — induction before paralytics]
- Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason].

**DRIP** [infusions only — include rate, target, and concentration]
- Mix X mg in Y mL NS (Z mg/mL). Start X mL/hr. Titrate X mL/hr q Y min. Max X mL/hr. Target: [goal].

**VENT** [ventilator guidance — give absolute mL when data is available]
- VT: X mL | RR: X | PEEP: X | FiO2: X% | PPLAT target ≤30 cmH2O

**POST-INTUBATION SEDATION** [mandatory after any RSI]
- Draw X mL of Y mg/mL ketamine IV (X mg) q20-30min. Indication: post-intubation sedation.

**WATCH**
- [One monitoring or deterioration warning]

**DON'T**
- [One critical contraindication]

**EVAC IF**
- [One clear evacuation trigger with threshold]

**TLDR**
- [One sentence. Most critical action or number.]

**SOURCE**: [JTS CPG name and ID — or "General Evidence-Based Medicine (outside retrieved JTS scope)"]

Guideline-based support only. Not a substitute for clinical judgment.

────────────────────────────────
RESPONSE FORMAT — NON-JTS SCOPE
────────────────────────────────

**[CONDITION OR PROBLEM]**
- What it is: one sentence.
- Why it matters: one sentence.

**TREAT**
1. [Immediate action]
2. [Second action]
3. [Third action]

**GIVE** [only if medication gating is satisfied]
- Draw X mL of Y mg/mL [drug] [route] (Z mg). Indication: [reason].

**WATCH FOR**
- [One deterioration sign]

**TLDR**
- [One sentence. Most important action.]

**SOURCE**: General Evidence-Based Medicine (outside retrieved JTS scope)

Guideline-based support only. Not a substitute for clinical judgment.
"""


def build_patient_block(ctx: PatientContext) -> str:
    if not ctx.weight_kg and not ctx.age_years and not ctx.is_pediatric:
        return ""
    lines = []
    if ctx.is_pediatric:
        lines.append("PEDIATRIC PATIENT")
    if ctx.weight_kg:
        lines.append(f"Weight: {ctx.weight_kg}kg ({ctx.weight_source})")
        if ctx.is_pediatric and ctx.weight_source == "estimated_from_age":
            lines.append("Weight is ESTIMATED from age — not confirmed by provider.")
            lines.append("DO NOT DOSE. Respond only: 'Need confirmed weight in kg before dosing.'")
        elif ctx.is_pediatric:
            ket_ceil = round(ctx.weight_kg * 2.0, 1)
            roc_ceil = round(ctx.weight_kg * 1.2, 1)
            ket_post = round(ctx.weight_kg * 0.5, 1)
            vt = int(pediatric_vt(ctx.weight_kg))
            lines.append("PEDIATRIC DOSE — USE EXACTLY THESE VALUES:")
            ket_analg_mg = round(ctx.weight_kg * 0.3, 1)
            ket_analg_ml = round(ket_analg_mg / 100, 3)
            lines.append(f"Ketamine subdissociative analgesia: Draw {ket_analg_ml} mL of 100mg/mL ketamine IV ({ket_analg_mg}mg). Indication: analgesia.")
       
            lines.append(f"Ketamine induction MAX: {ket_ceil}mg = {round(ket_ceil/100,2)} mL of 100mg/mL")
            lines.append(f"Rocuronium MAX: {roc_ceil}mg = {round(roc_ceil/10,1)} mL of 10mg/mL")
            lines.append(f"Post-intubation ketamine: {ket_post}mg = {round(ket_post/100,2)} mL of 100mg/mL q20-30min")
            lines.append(f"Pediatric VT: {vt}mL")
            lines.append("Do NOT calculate any other doses. Use only the values above.")
    if ctx.age_years:
        lines.append(f"Age: {ctx.age_years}yr")
        if ctx.is_pediatric:
            cuffed = round((ctx.age_years / 4) + 3, 1)
            depth = round(cuffed * 3, 1)
            lines.append(f"ETT (cuffed): {cuffed} | Depth: {depth}cm")
    if ctx.provider_scope != "UNKNOWN":
        lines.append(f"Provider scope: {ctx.provider_scope}")
    return "\n".join(lines)

def build_source_block(assessment: RetrievalAssessment) -> str:
    if assessment.source_mode == "JTS_GROUNDED":
        return (
            f"SOURCE MODE: JTS_GROUNDED (confidence: {assessment.top_score})\n"
            f"Use the retrieved JTS context below as primary authority. Cite the source.\n\n"
            f"RETRIEVED JTS CONTEXT:\n{assessment.context_text}"
        )
    elif assessment.source_mode == "GENERAL_MEDICAL":
        return (
            f"SOURCE MODE: GENERAL_MEDICAL (confidence: {assessment.top_score})\n"
            f"No sufficiently relevant JTS protocol retrieved. Use general evidence-based medicine.\n"
            f"Label source as: General Evidence-Based Medicine (outside retrieved JTS scope)\n\n"
            f"RETRIEVED CONTEXT (low confidence):\n{assessment.context_text}"
        )
    else:
        return (
            f"SOURCE MODE: INSUFFICIENT (confidence: {assessment.top_score})\n"
            f"No relevant protocol retrieved. Provide only high-confidence immediate safety actions.\n"
            f"For medication dosing: state 'No protocol retrieved — use local protocol or medical direction.'"
        )


def build_system_prompt(ctx: PatientContext, assessment: RetrievalAssessment) -> str:
    patient_block = build_patient_block(ctx)
    source_block = build_source_block(assessment)

    injected = GENERATOR_BASE
    if patient_block:
        injected = injected.replace(
            "────────────────────────────────\nNON-MEDICAL QUERY RULE",
            f"────────────────────────────────\nPATIENT CONTEXT\n────────────────────────────────\n\n{patient_block}\n\n────────────────────────────────\nNON-MEDICAL QUERY RULE"
        )
    injected += f"\n\n────────────────────────────────\nRETRIEVED PROTOCOL CONTEXT\n────────────────────────────────\n\n{source_block}"
    return injected


# ─────────────────────────────────────────────────────────────────────────────
# LLM VALIDATOR — NARROW SEMANTIC SCOPE
# ─────────────────────────────────────────────────────────────────────────────

VALIDATOR_PROMPT = """
You are the Clinical Safety Validator for AUSTERE-CDS, an AI clinical decision-support system for austere, prehospital, tactical, and critical-care environments.

You receive:
1. The original clinical query.
2. The proposed AUSTERE-CDS response.
3. Patient context summary.

Your task:
- Do not rewrite the answer.
- Do not add clinical advice.
- Decide whether the proposed response is safe to show.
- Flag dangerous clinical reasoning errors and unsafe omissions.
- Ignore minor style issues unless they create patient risk.
- Do NOT re-do medication math — deterministic calculators have already checked doses.

Be precise. A false positive wastes time. A false negative harms a patient.

────────────────────────────────
OUTPUT FORMAT
────────────────────────────────

Return only valid JSON. No markdown. No text outside the JSON.

{
  "result": "SAFE" | "UNSAFE" | "NEEDS_HUMAN_REVIEW",
  "issues": ["specific issue description"],
  "rationale": "brief reason for decision"
}

SAFE: no dangerous clinical safety issue found.
UNSAFE: a dangerous error could directly harm the patient — block the response.
NEEDS_HUMAN_REVIEW: ambiguity, missing safety-critical context, or out-of-scope intervention without acknowledgment.

When uncertain between SAFE and NEEDS_HUMAN_REVIEW: choose NEEDS_HUMAN_REVIEW.
When uncertain between NEEDS_HUMAN_REVIEW and UNSAFE: choose UNSAFE only if the error could directly harm the patient.

────────────────────────────────
CHECKLIST — RETURN UNSAFE IF ANY PRESENT
────────────────────────────────

1. SEPSIS TREATED AS HEMORRHAGE
   Scenario has fever or infection source plus hypotension, and response makes TXA, LTOWB, or DCR
   the primary treatment without clear hemorrhagic injury also present.

2. TXA MISUSE
   TXA recommended for sepsis, medical shock, hypothermia without hemorrhage, burns without
   significant hemorrhage, isolated TBI without hemorrhage, or trauma more than 3 hours old.

3. CICO OMISSION
   Scenario describes failed intubation PLUS failed rescue airway (i-gel/LMA/BVM) PLUS ongoing
   hypoxia, desaturation, or cyanosis — and response does not mention surgical airway or cricothyrotomy.

4. WPW CONTRAINDICATION
   WPW or pre-excitation is present and response recommends adenosine, beta-blocker,
   calcium-channel blocker, or digoxin.

5. DANGEROUS MEDICATION DOSE
   Dose appears 5x or more above standard clinical range for the patient's age and weight.
   Pediatric patient receives adult dose without weight-based adjustment.
   Medication given without units, or units are confused (mg vs mcg, dose vs mL).

6. PARALYTIC SAFETY FAILURE
   Paralytic recommended for a patient with a pulse without any induction agent or sedation.
   RSI response includes paralytic but has no post-intubation sedation plan anywhere in the response.

7. ROUTE OR CONTEXT MISMATCH
   IV-only route recommended when provider states no IV/IO access and no alternative is offered.
   Oral intake recommended in shock, altered mental status, or airway compromise.

8. CRITICAL DIAGNOSIS OR ACTION MISSED
   Tension pneumothorax physiology described without decompression recommended.
   Uncontrolled hemorrhage without hemorrhage control action.
   Severe anaphylaxis without epinephrine when medication data is sufficient.
   Cardiac arrest without CPR or defibrillation.
   Clearly unstable pediatric patient without escalation or evacuation.

9. DANGEROUS REASSURANCE
   Response says no evacuation needed despite clear red flags.
   Response says patient is stable despite hemodynamic instability.
   Response recommends monitor-only when immediate action is required.
   Response says medical control is not needed when the intervention requires it.

────────────────────────────────
RETURN NEEDS_HUMAN_REVIEW IF ANY PRESENT
────────────────────────────────

- Weight-based medication dose given without confirmed weight.
- mL dose given without concentration.
- Vasopressor rate given without weight, concentration, route, pump, or monitoring.
- Controlled substance, paralytic, invasive procedure, or blood product without scope/protocol context.
- Recommendation may exceed BLS/EMT/paramedic scope without acknowledgment.
- Source is unclear for a medication recommendation.
- Response is clinically plausible but missing enough context that it should not be delivered as definitive guidance.

────────────────────────────────
DO NOT FLAG
────────────────────────────────

Do not flag for:
- Different wording than preferred.
- Short response format.
- Missing non-critical monitoring details.
- Sedation dose interval preferences when a sedation plan exists.
- Minor sequencing differences that do not create patient harm.
- Refusal to dose because required data is missing.
- COPD oxygen level — not a flaggable issue in this system.
- - Medication recommended without restating the indication if the indication is clear from the query.
- Short responses that answer the question without elaboration.
- Any issue not explicitly listed in the UNSAFE or NEEDS_HUMAN_REVIEW checklists above.
"""


def validate_response(query: str, response_text: str,
                      patient_ctx: PatientContext) -> dict:
    """
    LLM semantic validator. Fail-closed: errors return NEEDS_HUMAN_REVIEW, not SAFE.
    Deterministic checks have already run. This handles semantic reasoning only.
    """
    try:
        patient_summary = build_patient_block(patient_ctx) or "No patient context extracted."
        validation_input = (
            f"Clinical query: {query}\n\n"
            f"Patient context: {patient_summary}\n\n"
            f"Proposed response:\n{response_text}"
        )

        result = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VALIDATOR_PROMPT},
                {"role": "user", "content": validation_input}
            ],
            temperature=0,
            max_tokens=400
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

        return {"result": result_val, "issues": issues, "rationale": rationale,
                "safe": result_val == "SAFE"}

    except json.JSONDecodeError as e:
        print(f"🚨 Validator JSON parse error (blocking): {e}")
        return {"result": "NEEDS_HUMAN_REVIEW",
                "issues": ["Validator returned invalid output."],
                "rationale": "Safety validation could not be parsed — human review required.",
                "safe": False}

    except Exception as e:
        print(f"🚨 Validator error (blocking): {e}")
        return {"result": "NEEDS_HUMAN_REVIEW",
                "issues": ["Validator unavailable."],
                "rationale": f"Safety validation failed — human review required: {str(e)}",
                "safe": False}


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


def apply_safety_gate(response_text: str, det_check: DeterministicCheck,
                      llm_result: dict) -> tuple:
    """
    Returns (final_response, was_blocked, combined_issues).
    Deterministic failures always block first.
    LLM UNSAFE blocks. NEEDS_HUMAN_REVIEW appends warning.
    """
    if not det_check.passed:
        print(f"🚨 DETERMINISTIC BLOCK: {det_check.issues}")
        return build_safety_hold(det_check.issues, ""), True, det_check.issues

    if llm_result["result"] == "UNSAFE":
        print(f"🚨 LLM VALIDATOR BLOCK: {llm_result['issues']}")
        return build_safety_hold(llm_result["issues"], llm_result["rationale"]), True, llm_result["issues"]

    if llm_result["result"] == "NEEDS_HUMAN_REVIEW":
        print(f"⚠️ NEEDS_HUMAN_REVIEW: {llm_result['rationale']}")
        warning = (
            "\n\n⚠️ CLINICAL SAFETY NOTE: This response requires human review. "
            "Do not use as definitive guidance without qualified medical oversight."
        )
        return response_text + warning, False, llm_result["issues"]

    print(f"✅ SAFE: {llm_result['rationale']}")
    return response_text, False, []


# ─────────────────────────────────────────────────────────────────────────────
# MAIN QUERY PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def query_with_rag(query: str, chromadb_client, voice_mode: bool = False,
                   conversation_history: list = None) -> dict:
    """
    EdgeCDSS v3.2 Pipeline:
    1. Extract patient context from query
    2. RAG retrieval + source classification
    3. Build dynamic system prompt
    4. Generate clinical response
    5. Deterministic safety checks (Python math)
    6. LLM semantic validator (fail-closed)
    7. Apply safety gate
    8. Return validated response
    """
    try:
        # Step 1: Patient context
        patient_ctx = extract_patient_context(query)
        print(f"👤 Patient: weight={patient_ctx.weight_kg}kg age={patient_ctx.age_years}yr "
              f"pediatric={patient_ctx.is_pediatric} scope={patient_ctx.provider_scope}")

        # Step 2: RAG + source classification
        raw_results = chromadb_client.query(query, n_results=5)
        assessment = classify_retrieval(raw_results)
        print(f"📚 Retrieval: {assessment.source_mode} (top: {assessment.top_score})")

        # Step 3: Build system prompt
        system_prompt = build_system_prompt(patient_ctx, assessment)

        # Step 4: Generate response
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            for turn in conversation_history[-5:]:
                messages.append({"role": "user", "content": turn.get("query", "")})
                messages.append({"role": "assistant", "content": turn.get("response", "")})
        messages.append({"role": "user", "content": f"Clinical query: {query}"})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=700
        )
        response_text = response.choices[0].message.content

        # Step 5: Deterministic checks
        det_check = run_deterministic_checks(query, response_text, patient_ctx)

        # Step 6: LLM semantic validator
        full_context = query
        if conversation_history:
            prior = " | ".join([t.get("query","") for t in conversation_history[-3:]])
            full_context = f"{prior} | {query}"
        llm_result = validate_response(full_context, response_text, patient_ctx)

        # Step 7: Safety gate
        final_response, blocked, combined_issues = apply_safety_gate(
            response_text, det_check, llm_result
        )

        validator_result = "UNSAFE" if blocked else llm_result["result"]

        return {
            "response": final_response,
            "sources": assessment.sources[:3],
            "source_mode": assessment.source_mode,
            "validator_result": validator_result,
            "validator_issues": combined_issues,
            "patient_context": {
                "weight_kg": patient_ctx.weight_kg,
                "age_years": patient_ctx.age_years,
                "is_pediatric": patient_ctx.is_pediatric,
                "weight_source": patient_ctx.weight_source,
                "provider_scope": patient_ctx.provider_scope
            }
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
