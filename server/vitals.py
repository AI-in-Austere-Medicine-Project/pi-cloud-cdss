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
        # Temperature is stated in two units, so it carries two bands. min/max
        # are the canonical unit the cautions are written in; alt_* is the other
        # one. They do not overlap, which is what lets an unlabelled number be
        # read as whichever band it falls in.
        "temp":   {"label": "Temp", "unit": "C",    "min": 35, "max": 43,
                   "alt_unit": "F", "alt_min": 93, "alt_max": 110},
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
    _rename_legacy_temp(raw)
    return raw


def _rename_legacy_temp(raw: dict) -> None:
    """`temp_c` was the vital's name while a reading was always Celsius.

    It no longer is: a reading keeps the unit it was stated in, so the name
    would be a claim about the value that is not true. This file is meant to be
    edited by a clinician and an edited copy outlives a deploy, so an old key is
    renamed rather than silently ignored — a caution that stops arming is the
    one failure mode this table must not have.
    """
    if "temp_c" in raw.get("ranges", {}):
        raw["ranges"]["temp"] = raw["ranges"].pop("temp_c")
    for rule in raw.get("cautions", []):
        when = rule.get("when") if isinstance(rule, dict) else None
        if isinstance(when, dict) and "temp_c" in when:
            when["temp"] = when.pop("temp_c")
            rule["caution"] = str(rule.get("caution", "")).replace("{temp_c}", "{temp}")


_RULES = _load_rules()
RANGES = {k: v for k, v in _RULES["ranges"].items() if not k.startswith("_")}
CAUTIONS = [c for c in _RULES["cautions"] if isinstance(c, dict)]

# Display order for the client strip and the prompt block. Explicit rather than
# dict order so a reordered config file does not reorder what the medic reads.
VITAL_ORDER = ("hr", "sbp", "dbp", "spo2", "rr", "gcs", "temp")


@dataclass(frozen=True)
class VitalReading:
    """One measurement, with where and when it came from.

    `ts` is the timestamp of the conversation turn the value was stated in, or
    None when that turn carried no timestamp. None means "age unknown" and is
    rendered that way; it is never treated as recent.

    `value` and `unit` are what the medic actually said. Showing 40 C back to
    someone who typed 104 F is a translation they did not ask for, and a value
    they cannot check against the thermometer in their hand. Temperature also
    carries both conversions, and `canonical` is the one the caution table
    compares against — the rules are written in one unit and must stay that way.
    Every other vital has a single unit, so its canonical value is its value.
    """
    value: float
    unit: str
    ts: Optional[str] = None
    raw: str = ""
    value_c: Optional[float] = None
    value_f: Optional[float] = None

    @property
    def canonical(self) -> float:
        """The value in the unit the rules are written in."""
        return self.value_c if self.value_c is not None else self.value

    def to_dict(self) -> dict:
        d = {"value": self.value, "unit": self.unit, "ts": self.ts, "raw": self.raw}
        # Only temperature has a second unit. Emitting value_c: null on a heart
        # rate would invite a reader to wonder what a heart rate in Celsius is.
        if self.value_c is not None:
            d["value_c"] = self.value_c
        if self.value_f is not None:
            d["value_f"] = self.value_f
        return d


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
# "fever" is a temperature label only when a number follows it. "febrile", and
# "fever" with nothing after it, describe a patient without measuring one, and
# this table stores measurements — the sepsis router reads the word itself
# (has_fever) and is where an unmeasured fever belongs.
_TEMP_LABEL = _B + r"(?:temperature|temp|fever|t)"


def _spans_overlap(span, consumed) -> bool:
    return any(not (span[1] <= s or span[0] >= e) for s, e in consumed)


def _in_range(name: str, value: float) -> bool:
    spec = RANGES.get(name)
    if not spec:
        return False
    return spec["min"] <= value <= spec["max"]


def _in_alt_range(name: str, value: float) -> bool:
    """The same test against the vital's second unit, where it has one."""
    spec = RANGES.get(name) or {}
    if spec.get("alt_unit") is None:
        return False
    return spec["alt_min"] <= value <= spec["alt_max"]


def _unit(name: str) -> str:
    return (RANGES.get(name) or {}).get("unit", "")


def _alt_unit(name: str) -> str:
    return (RANGES.get(name) or {}).get("alt_unit", "")


def label(name: str) -> str:
    return (RANGES.get(name) or {}).get("label", name.upper())


def _reason(name: str, value: float, unit: str = "") -> str:
    """Why a reading was not stored, in the unit the medic used.

    A vital with two bands says both, because "outside 35-43C" is not an
    explanation to someone who typed a Fahrenheit number.
    """
    spec = RANGES.get(name) or {}
    stated = f" {unit}" if unit else ""
    if unit and unit == _alt_unit(name):
        return (f"{label(name)} {value:g}{stated} is outside the plausible range "
                f"{spec.get('alt_min')}-{spec.get('alt_max')}{_alt_unit(name)}")
    if not unit and spec.get("alt_unit"):
        return (f"{label(name)} {value:g} is not a plausible temperature in either "
                f"unit ({spec.get('min')}-{spec.get('max')}{_unit(name)} or "
                f"{spec.get('alt_min')}-{spec.get('alt_max')}{_alt_unit(name)})")
    return (f"{label(name)} {value:g}{stated} is outside the plausible range "
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

    # ── Temperature, in whichever unit it was stated ────────────────────────
    for m in re.finditer(_TEMP_LABEL + _SEP + r"(\d{2,3}(?:\.\d+)?)\s*(c|f|°c|°f)?\b", q):
        _take_temp(float(m.group(1)), (m.group(2) or "").strip("°"),
                   m, consumed, readings, rejections, ts)

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


def _f_to_c(value: float) -> float:
    return (value - 32) * 5.0 / 9.0


def _c_to_f(value: float) -> float:
    return value * 9.0 / 5.0 + 32


def _take_temp(value: float, stated_unit: str, m, consumed, readings, rejections, ts):
    """A temperature in the unit it was stated in, or a visible rejection.

    Which unit is decided by range, not by a threshold: the two plausible bands
    (35-43C, 93-110F) do not overlap, so an unlabelled number belongs to at most
    one of them. A number in neither is not a temperature this parser can read,
    and the medic is told so — guessing between two units on an implausible
    value is how a system ends up holding 50C.

    A stated unit is checked against its own band and never reinterpreted. "temp
    104 C" is a mistyped reading, not a Fahrenheit one: silently reading it as F
    would invent a plausible vital out of an implausible one, which is the
    failure the whole rejection path exists to prevent.
    """
    if _spans_overlap(m.span(), consumed):
        return
    consumed.append(m.span())
    raw = m.group(0).strip()

    canonical_unit, alt_unit = _unit("temp"), _alt_unit("temp")
    if stated_unit == canonical_unit.lower():
        unit = canonical_unit if _in_range("temp", value) else None
    elif stated_unit == alt_unit.lower():
        unit = alt_unit if _in_alt_range("temp", value) else None
    elif _in_range("temp", value):
        unit = canonical_unit
    elif _in_alt_range("temp", value):
        unit = alt_unit
    else:
        unit = None

    if unit is None:
        rejections.append(VitalRejection(
            name="temp", raw=raw,
            reason=_reason("temp", value, stated_unit.upper())))
        return

    in_canonical = unit == canonical_unit
    readings["temp"] = VitalReading(
        value=value, unit=unit, ts=ts, raw=raw,
        value_c=round(value if in_canonical else _f_to_c(value), 1),
        value_f=round(_c_to_f(value) if in_canonical else value, 1))


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
        line = f"- {format_pair(readings, name)}"
        # A model reasoning about a fever should not have to convert, and should
        # not have to guess which unit an unlabelled number was in.
        r = readings[name]
        if r.value_c is not None and r.unit != _unit(name):
            line += f" ({r.value_c:g}{_unit(name)})"
        lines.append(line + _age_suffix(r, now_ts))
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
            # canonical, not value: the thresholds in the table are written in
            # one unit, and a reading kept in the unit the medic stated it in
            # would otherwise compare 104 against a rule meaning 40.
            if fn is None or not fn(reading.canonical, threshold):
                return None
        armed[name] = reading
    return armed


def _caution_value(reading: VitalReading) -> str:
    """A reading as it appears inside a caution line, with its unit if it has
    a second one. Single-unit vitals name their unit in the caution template."""
    if reading.value_c is None:
        return f"{reading.value:g}"
    return f"{reading.value:g} {reading.unit}"


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
            # Quoted back in the unit the medic used. The comparison was
            # canonical; the sentence they read should be the number they typed.
            values = {name: _caution_value(r) for name, r in armed.items()}
            out.append(rule.get("caution", "").format(drug=drug, **values))
            break            # one caution per rule, named for the first agent found
    return out
