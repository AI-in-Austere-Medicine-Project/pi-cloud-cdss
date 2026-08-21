"""
EdgeCDSS — vital signs: capture, supersession, and conflict cautions.

Why this module exists
──────────────────────
The pipeline already reads clinical state out of free text — weight, age, route,
access — and the audit's most serious finding (S-1) was that state going stale
without anyone being able to see it. Vitals are the same kind of state with a
shorter half-life: a blood pressure from twenty minutes ago is not the blood
pressure, and a system that quietly treats it as current is repeating S-1 with a
faster clock.

So three rules shape everything here:

  1. **Every reading carries the timestamp of the turn it was stated in**, and a
     turn with no timestamp yields a reading with `ts=None` — "age unknown", never
     a fabricated "just now". Pre-v4.1 clients send no `ts` at all, and stamping
     those with the current time would claim a stale vital is fresh. Same rule
     detect_patient_boundary already applies to inactivity gaps.
  2. **A vital the medic cannot see is a vital the medic cannot correct.** The
     current state goes back to the client on every response for the context
     strip. That is the S-1 lesson as UI.
  3. **Vitals never compute a dose.** They inform the prompt, the validator and
     the caution table. Dose logic stays in the ALLOWED_DOSES contract, which is
     the only thing in this system permitted to produce a number to give.

Cautions are not blocks
───────────────────────
A conflict between a recommendation and a recorded vital appends a visible line
and downgrades a SAFE verdict to NEEDS_HUMAN_REVIEW. It never blocks a response
and never releases one. Blocking on a vital would put a parser between a medic
and a protocol answer, and this parser reads free text typed one-handed.

The rule table is deliberately narrow (vitals_rules.json). A caution that fires
on most responses stops being read, which is worse than not having it.
"""

import datetime
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Optional

_RULES_PATH = pathlib.Path(__file__).parent / "vitals_rules.json"

# Used when vitals_rules.json is missing or unparseable. Ranges only: without a
# range a vital cannot be validated, so the parser must not fall back to
# accepting anything. An empty caution list degrades to "no cautions", which is
# the safe direction — cautions add warnings, they never release anything.
_BUILTIN_RULES = {
    "ranges": {
        "hr":     {"label": "HR",   "unit": "bpm",  "min": 10, "max": 300},
        "sbp":    {"label": "SBP",  "unit": "mmHg", "min": 40, "max": 300},
        "dbp":    {"label": "DBP",  "unit": "mmHg", "min": 10, "max": 200},
        "spo2":   {"label": "SpO2", "unit": "%",    "min": 50, "max": 100},
        "rr":     {"label": "RR",   "unit": "/min", "min": 2,  "max": 80},
        "gcs":    {"label": "GCS",  "unit": "",     "min": 3,  "max": 15},
        "temp_c": {"label": "Temp", "unit": "C",    "min": 20, "max": 45},
    },
    "cautions": [],
}


def _load_rules() -> dict:
    try:
        with open(_RULES_PATH) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  {_RULES_PATH.name} not found — using built-in vitals ranges.")
        return _BUILTIN_RULES
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  {_RULES_PATH.name} is unreadable ({e}) — using built-in vitals ranges.")
        return _BUILTIN_RULES
    if not raw.get("ranges"):
        print(f"⚠️  {_RULES_PATH.name} has no ranges — using built-in vitals ranges.")
        return _BUILTIN_RULES
    raw.setdefault("cautions", [])
    return raw


_RULES = _load_rules()
RANGES = {k: v for k, v in _RULES["ranges"].items() if not k.startswith("_")}
CAUTIONS = [c for c in _RULES["cautions"] if isinstance(c, dict)]

# Display order for the client strip and the prompt block. Explicit rather than
# dict order so a reordered config file does not reorder what the medic reads.
VITAL_ORDER = ("hr", "sbp", "dbp", "spo2", "rr", "gcs", "temp_c")


@dataclass(frozen=True)
class VitalReading:
    """One measurement, with where and when it came from.

    `ts` is the timestamp of the conversation turn the value was stated in, or
    None when that turn carried no timestamp. None means "age unknown" and is
    rendered that way; it is never treated as recent.
    """
    value: float
    unit: str
    ts: Optional[str] = None
    raw: str = ""

    def to_dict(self) -> dict:
        return {"value": self.value, "unit": self.unit, "ts": self.ts, "raw": self.raw}


@dataclass(frozen=True)
class VitalRejection:
    """A vital-shaped token whose value cannot be real.

    Surfaced to the medic rather than dropped. A silently ignored "BP 400/300"
    leaves them believing the system has a blood pressure it does not have.
    """
    name: str
    raw: str
    reason: str

    def to_dict(self) -> dict:
        return {"name": self.name, "raw": self.raw, "reason": self.reason}


# ─────────────────────────────────────────────────────────────────────────────
# PARSING
# ─────────────────────────────────────────────────────────────────────────────
#
# Patterns are tried in order and each one CONSUMES the span it matched, so a
# later pattern cannot re-read digits an earlier one already claimed. That is
# what lets the bare "82/40" blood-pressure form exist at the end of the list
# without swallowing the numbers out of "GCS 3-4-5" or a dose ratio.

_NUM = r"(\d{1,3}(?:\.\d+)?)"
_SEP = r"\s*(?:of|is|was|at|=|:)?\s*"

# Label alternations. Ordered longest-first within each group so "resp rate"
# wins over "resp". The 'sp02' spellings are not typos to be tolerated later —
# a zero for the letter O is the single most common way this gets typed.
#
# Every label is anchored with (?<!\w). Without it these are substrings of
# ordinary clinical prose and they fire inside it: bare 't' matched the t in
# "pt is 82/40" and read a temperature of 82F, and 'hr' is a substring of
# "thrombosis". Same failure the alias table hit in F-2 and FIXED_PREP_TERMS hit
# with "norepinephrine drip" — short medical tokens are substrings of longer
# medical words, and this parser reads free text typed one-handed.
_B = r"(?<!\w)"
_HR_LABEL = _B + r"(?:heart\s*rate|pulse\s*rate|pulse|hr)"
_BP_LABEL = _B + r"(?:blood\s*pressure|bp)"
_SPO2_LABEL = _B + r"(?:pulse\s*ox(?:imetry)?|o2\s*sats?|sp[o0]2|sa[o0]2|sats|sat)"
_RR_LABEL = _B + r"(?:respiratory\s*rate|resp\s*rate|resps|resp|rr)"
_GCS_LABEL = _B + r"(?:gcs)"
_TEMP_LABEL = _B + r"(?:temperature|temp|t)"


def _spans_overlap(span, consumed) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in consumed)


def _in_range(name: str, value: float) -> bool:
    spec = RANGES.get(name)
    if not spec:
        return False
    return spec["min"] <= value <= spec["max"]


def _unit(name: str) -> str:
    return (RANGES.get(name) or {}).get("unit", "")


def label(name: str) -> str:
    return (RANGES.get(name) or {}).get("label", name.upper())


def _reason(name: str, value: float) -> str:
    spec = RANGES.get(name) or {}
    return (f"{label(name)} {value:g} is outside the plausible range "
            f"{spec.get('min')}-{spec.get('max')}{_unit(name)}")


def parse_vitals(text: str, ts: Optional[str] = None):
    """Read vitals out of free text.

    Returns (readings, rejections). A vital-shaped token with an impossible
    value lands in `rejections`, never in `readings` — and the caller is
    expected to show the medic that it was rejected.

    Text that simply contains no vitals produces neither. Only a LABELLED vital
    can be rejected; an arbitrary number is not a failed vital, it is not a
    vital.
    """
    if not text:
        return {}, []

    q = text.lower()
    readings: dict = {}
    rejections: list = []
    consumed: list = []

    def take(name: str, value: float, span, raw: str):
        if _spans_overlap(span, consumed):
            return
        consumed.append(span)
        if _in_range(name, value):
            readings[name] = VitalReading(value=value, unit=_unit(name),
                                          ts=ts, raw=raw.strip())
        else:
            rejections.append(VitalRejection(name=name, raw=raw.strip(),
                                             reason=_reason(name, value)))

    # ── GCS, component form: "GCS 3-4-5" / "GCS E3 V4 M5" ───────────────────
    # Before the numeric form so the three components are not read as a total,
    # and before bare BP so "3-4-5" cannot be mistaken for anything else.
    for m in re.finditer(_GCS_LABEL + r"\s*e?\s*([1-4])\s*[-/ ]\s*v?\s*([1-5])\s*[-/ ]\s*m?\s*([1-6])\b", q):
        total = sum(int(g) for g in m.groups())
        take("gcs", float(total), m.span(), m.group(0))

    # ── Blood pressure, labelled: "BP 82/40" ────────────────────────────────
    # Both halves share one timestamp: they were measured together and must
    # never be superseded independently.
    for m in re.finditer(_BP_LABEL + _SEP + r"(\d{1,3})\s*/\s*(\d{1,3})", q):
        _take_bp(float(m.group(1)), float(m.group(2)), m, consumed,
                 readings, rejections, ts)

    # ── Labelled single values ──────────────────────────────────────────────
    for name, pattern in (
        ("hr",   _HR_LABEL + _SEP + _NUM),
        ("spo2", _SPO2_LABEL + _SEP + _NUM + r"\s*%?"),
        ("rr",   _RR_LABEL + _SEP + _NUM),
        ("gcs",  _GCS_LABEL + _SEP + _NUM),
    ):
        for m in re.finditer(pattern + r"\b", q):
            take(name, float(m.group(1)), m.span(), m.group(0))

    # ── Temperature, normalised to Celsius ──────────────────────────────────
    for m in re.finditer(_TEMP_LABEL + _SEP + r"(\d{2,3}(?:\.\d+)?)\s*(c|f|°c|°f)?\b", q):
        value, unit = float(m.group(1)), (m.group(2) or "").strip("°")
        if unit == "f":
            value = (value - 32) * 5.0 / 9.0
        elif not unit:
            # No unit given. 45C is already incompatible with life, so anything
            # at or above it can only be Fahrenheit. Same split has_fever uses.
            if value >= 45:
                value = (value - 32) * 5.0 / 9.0
        take("temp_c", round(value, 1), m.span(), m.group(0))

    # ── Bare blood pressure: "82/40" ────────────────────────────────────────
    # Last, and only over spans nothing else claimed. Guarded by plausibility on
    # BOTH halves plus sbp > dbp, which is what stops a dose ratio or a date
    # from being read as a pressure.
    for m in re.finditer(r"(?<![\w./])(\d{2,3})\s*/\s*(\d{2,3})(?![\w./])", q):
        sbp, dbp = float(m.group(1)), float(m.group(2))
        if _in_range("sbp", sbp) and _in_range("dbp", dbp) and sbp > dbp:
            take("sbp", sbp, m.span(), m.group(0))
            readings.setdefault("dbp", VitalReading(
                value=dbp, unit=_unit("dbp"), ts=ts, raw=m.group(0).strip()))

    return readings, rejections


def _take_bp(sbp: float, dbp: float, m, consumed, readings, rejections, ts):
    """Both halves of a labelled BP, or neither.

    A pressure is one measurement, so it passes or fails as one. Storing the
    diastolic from "BP 400/300" because 300 happens to sit inside the diastolic
    range, while rejecting the systolic, would leave the system holding half a
    vital it had just told the medic it could not read.

    `sbp > dbp` is part of the plausibility test, not a formatting preference:
    a reversed pair means the reading was mistyped, whatever the two numbers are.
    """
    if _spans_overlap(m.span(), consumed):
        return
    consumed.append(m.span())
    raw = m.group(0).strip()

    if _in_range("sbp", sbp) and _in_range("dbp", dbp) and sbp > dbp:
        readings["sbp"] = VitalReading(sbp, _unit("sbp"), ts, raw)
        readings["dbp"] = VitalReading(dbp, _unit("dbp"), ts, raw)
        return

    if not _in_range("sbp", sbp):
        reason = _reason("sbp", sbp)
    elif not _in_range("dbp", dbp):
        reason = _reason("dbp", dbp)
    else:
        reason = (f"systolic {sbp:g} is not above diastolic {dbp:g}")
    rejections.append(VitalRejection(name="bp", raw=raw, reason=reason))


# ─────────────────────────────────────────────────────────────────────────────
# SUPERSESSION
# ─────────────────────────────────────────────────────────────────────────────

def merge(existing: dict, incoming: dict):
    """Fold new readings over old. Returns (merged, superseded).

    Newer wins. `superseded` records what was displaced, with both values, so
    the log can answer "what did the system believe before this turn" — the
    question the v4.0 log could not answer about S-1.

    Called once per replayed turn, so ordering comes from the conversation
    rather than from comparing timestamps: a turn with no `ts` still supersedes
    the turn before it, which is the ordering the medic actually typed.
    """
    merged = dict(existing or {})
    superseded = []
    for name, reading in (incoming or {}).items():
        prior = merged.get(name)
        if prior is not None and prior.value != reading.value:
            superseded.append({
                "name": name,
                "from": {"value": prior.value, "ts": prior.ts},
                "to": {"value": reading.value, "ts": reading.ts},
            })
        merged[name] = reading
    return merged, superseded


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY AND PROMPT RENDERING
# ─────────────────────────────────────────────────────────────────────────────

def to_dict(readings: dict) -> dict:
    return {name: readings[name].to_dict()
            for name in VITAL_ORDER if name in (readings or {})}


def format_pair(readings: dict, name: str) -> Optional[str]:
    r = (readings or {}).get(name)
    if r is None:
        return None
    unit = r.unit
    value = f"{r.value:g}"
    if name == "sbp" and "dbp" in readings:
        return f"BP {value}/{readings['dbp'].value:g} {unit}"
    return f"{label(name)} {value}{(' ' + unit) if unit and unit != '%' else unit}"


def summary_line(readings: dict) -> str:
    """One line of vitals for the prompt and the log. Empty when there are none."""
    if not readings:
        return ""
    parts = []
    for name in VITAL_ORDER:
        if name == "dbp":
            continue                      # rendered with sbp
        if name in readings:
            parts.append(format_pair(readings, name))
    return " | ".join(p for p in parts if p)


def _parse_ts(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def age_minutes(reading: VitalReading, now_ts=None) -> Optional[float]:
    """How old this reading is, or None when either timestamp is unknown.

    None is rendered "age unknown" and must never be shown as 0. A vital whose
    age cannot be established is exactly the one a medic needs to look at.
    """
    start, end = _parse_ts(getattr(reading, "ts", None)), _parse_ts(now_ts)
    if not start or not end:
        return None
    return (end - start).total_seconds() / 60.0


def _age_suffix(reading: VitalReading, now_ts) -> str:
    age = age_minutes(reading, now_ts)
    if age is None:
        return " (age unknown)"
    if age < 1:
        return " (just now)"
    return f" ({int(age)}m ago)"


def prompt_block(readings: dict, now_ts=None) -> str:
    """The VITALS section of the generator and validator prompts.

    Ages are included because a model reasoning about a blood pressure needs to
    know whether it is from this minute or from before the last intervention.
    """
    if not readings:
        return ""
    lines = ["RECORDED VITALS (stated by the provider, not measured by this system):"]
    for name in VITAL_ORDER:
        if name == "dbp" or name not in readings:
            continue
        lines.append(f"- {format_pair(readings, name)}"
                     f"{_age_suffix(readings[name], now_ts)}")
    lines.append("Vitals inform cautions and context only. They never authorise a dose.")
    return "\n".join(lines)


def rejection_notice(rejections: list) -> str:
    """The visible "couldn't read that" note. Empty when nothing was rejected."""
    if not rejections:
        return ""
    items = "; ".join(f"{r.raw!r} ({r.reason})" for r in rejections)
    return (f"⚠️ **Couldn't read that vital: {items}.** "
            f"It was not stored — restate it if it matters.\n\n")


# ─────────────────────────────────────────────────────────────────────────────
# CONFLICT CAUTIONS
# ─────────────────────────────────────────────────────────────────────────────

_COMPARATORS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
}


def _rule_armed(rule: dict, readings: dict):
    """The readings that arm this rule, or None if it is not armed.

    A rule whose vital was never recorded is not armed. Absence of a vital is
    not a normal vital — the system does not know the blood pressure, and must
    not reason as though it were fine.
    """
    armed = {}
    for name, test in (rule.get("when") or {}).items():
        reading = (readings or {}).get(name)
        if reading is None:
            return None
        for comparator, threshold in test.items():
            fn = _COMPARATORS.get(comparator)
            if fn is None or not fn(reading.value, threshold):
                return None
        armed[name] = reading
    return armed


def _drug_present(response_lower: str, drug: str) -> bool:
    return re.search(r'(?<!\w)' + re.escape(drug.lower()) + r'(?!\w)',
                     response_lower) is not None


def conflicts(response_text: str, readings: dict) -> list:
    """Cautions where the response and the recorded vitals disagree.

    Returns caution strings, not issues. These never block: apply_safety_gate
    appends them to a served response and downgrades SAFE to
    NEEDS_HUMAN_REVIEW. A parser reading one-handed free text does not get to
    stand between a medic and a protocol answer.
    """
    if not response_text or not readings:
        return []
    response_lower = response_text.lower()
    out = []
    for rule in CAUTIONS:
        armed = _rule_armed(rule, readings)
        if armed is None:
            continue
        for drug in rule.get("drugs", []):
            if not _drug_present(response_lower, drug):
                continue
            values = {name: f"{r.value:g}" for name, r in armed.items()}
            out.append(rule.get("caution", "").format(drug=drug, **values))
            break            # one caution per rule, named for the first agent found
    return out
