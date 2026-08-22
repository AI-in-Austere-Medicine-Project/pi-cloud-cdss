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

MAP is the one value here the system computes rather than hears
──────────────────────────────────────────────────────────────
Every other reading is something a medic said. A mean arterial pressure is
usually not — it is arithmetic on a pressure they did say — and a computed
number that looks like a measured one is its own small S-1. So a derived MAP is
flagged `derived` everywhere it appears, it is recomputed rather than carried
forward whenever either pressure moves, and it inherits the age of the OLDER of
its two inputs: a derived value must never look fresher than the data behind it.

A MAP the medic states directly is a measurement like any other — they may have
an arterial line — and it supersedes the derived one until a newer pressure
arrives.

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
        # MAP is derived from sbp/dbp, so this band only ever validates a MAP
        # the medic STATED. It spans everything derivable from the two pressure
        # bands above — (40+2*10)/3 up to (300+2*200)/3 — so a derived value
        # cannot fall outside a range its own inputs passed.
        "map":    {"label": "MAP",  "unit": "mmHg", "min": 20, "max": 240},
        # Temperature is stated in two units, so it carries two bands. min/max
        # are the canonical unit the cautions are written in; alt_* is the other
        # one. They do not overlap, which is what lets an unlabelled number be
        # read as whichever band it falls in.
        "temp":   {"label": "Temp", "unit": "C",    "min": 35, "max": 43,
                   "alt_unit": "F", "alt_min": 93, "alt_max": 110},
        # Bands OVERLAP, unlike temperature's — see vitals_rules.json.
        "glucose": {"label": "Glucose", "unit": "mg/dL", "min": 10, "max": 800,
                    "alt_unit": "mmol/L", "alt_min": 0.6, "alt_max": 44.4,
                    "assumed_unit_when_unstated": "mg/dL"},
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
VITAL_ORDER = ("hr", "sbp", "dbp", "map", "spo2", "rr", "gcs", "temp", "glucose")


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

    `derived` says whether the system computed this reading or the medic stated
    it. It is written on EVERY reading, including the false ones, because
    "stated" is a fact about a value and not the absence of one — a flag that
    only appeared on derived readings would make a stated MAP indistinguishable
    from a log written before this field existed.
    """
    value: float
    unit: str
    ts: Optional[str] = None
    raw: str = ""
    value_c: Optional[float] = None
    value_f: Optional[float] = None
    derived: bool = False
    # Set only when a vital has a second unit that is NOT a temperature —
    # glucose is the first. `value_c` cannot carry it: that field means
    # Celsius, is emitted under that name, and a glucose in Celsius is not a
    # thing. Not emitted in to_dict, so the log shape is unchanged.
    canonical_value: Optional[float] = None

    @property
    def canonical(self) -> float:
        """The value in the unit the rules are written in."""
        if self.canonical_value is not None:
            return self.canonical_value
        return self.value_c if self.value_c is not None else self.value

    def to_dict(self) -> dict:
        d = {"value": self.value, "unit": self.unit, "ts": self.ts,
             "raw": self.raw, "derived": self.derived}
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
# "are" joins the rest: "sats are 91" is as ordinary as "sats of 91". Trend
# phrasings ("dropped to 88", "down to 84") are deliberately NOT here — they
# are surfaced by the unparsed-number sweep instead, so how often medics use
# them is measured rather than guessed at before widening the parser.
_SEP = r"\s*(?:of|is|was|are|at|=|:)?\s*"

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
# "he's satting 84 on room air now" — the verb form is what a medic says out
# loud and what speech-to-text produces. Before "sats|sat" in the alternation
# or it matches the stem and leaves "ting" where a number should be.
_SPO2_LABEL = _B + (r"(?:pulse\s*ox(?:imetry)?|o2\s*sats?|sp[o0]2|sa[o0]2"
                    r"|satt?ing|sat'?ing|sats|sat)")
_RR_LABEL = _B + r"(?:respiratory\s*rate|resp\s*rate|resps|resp|rr)"
_GCS_LABEL = _B + r"(?:gcs)"
# "map" is an ordinary English word, so this label is the one that most needs
# its anchors. (?<!\w) keeps it out of "roadmap", and a number has to follow:
# "map" on its own is a map, and this table stores measurements.
_MAP_LABEL = _B + r"(?:mean\s*arterial\s*(?:pressure|bp)?|map)"
# "fever" is a temperature label only when a number follows it. "febrile", and
# "fever" with nothing after it, describe a patient without measuring one, and
# this table stores measurements — the sepsis router reads the word itself
# (has_fever) and is where an unmeasured fever belongs.
_TEMP_LABEL = _B + r"(?:temperature|temp|fever|t)"
# "sugar" and "glucose" are what medics say; "bg"/"cbg"/"bgl"/"dstick"/
# "accucheck" are what they write. Anchored like every other label: "bg" must
# not fire inside "bgcolor" and "t" is already the narrowest label here.
_GLUCOSE_LABEL = _B + (r"(?:blood\s*sugar|blood\s*glucose|glucose|sugar"
                       r"|cbg|bgl|bg|dstick|d-stick|accucheck|accu-chek|fingerstick)")
# "his sugar CAME BACK AT 32" — a lab value gets reported, not just stated, and
# _SEP alone only spans a single connective. An explicit verb list rather than
# a wildcard filler: "\w+{0,3}" would read "sugar was fine, bp 118" as a
# glucose of 118. Each alternative here is a word that introduces a result.
_REPORTED = r"(?:\s*(?:came\s*back|comes\s*back|came\s*in|came\s*out"
_REPORTED += r"|reads?|showed|shows|returned|resulted|measured))?"


# Every label this file knows, for the unparsed-number sweep below. Built from
# the same strings the real patterns use, so a label added above is swept for
# automatically rather than needing to be remembered here.
# NOT _TEMP_LABEL: it carries a bare "t", which is correct for the parser
# (it is followed there by a two-to-three digit number in a plausible
# temperature band) and far too loose for a sweep that only has to find a
# number nearby. Measured over the 186 bank queries, the bare "t" produced
# every single false positive — "the next 4", "to 1", "tidal co2", "tbi 5" —
# and nothing else did.
_TEMP_LABEL_SWEEP = _B + r"(?:temperature|temp|fever)"

_ALL_VITAL_LABELS = (_HR_LABEL, _BP_LABEL, _SPO2_LABEL, _RR_LABEL, _GCS_LABEL,
                     _MAP_LABEL, _TEMP_LABEL_SWEEP, _GLUCOSE_LABEL)

# Numbers that follow a vital stem but are plainly not that vital. Without
# this, "fever for 2 days" reports a vital it could not read, and a notice that
# fires on ordinary prose is a notice nobody reads — the same failure mode the
# caution table's narrowness exists to avoid.
_NOT_A_VITAL_AFTER = (
    r"(?!\s*(?:days?|hours?|hrs?|mins?|minutes?|weeks?|months?|years?|yo\b|y/o"
    r"|mg|mcg|ml|g\b|kg|kgs|lbs?|pounds?|kilos?|kilograms?|%\s*tbsa|units?"
    r"|french|fr\b|ga\b|gauge|joules?|j\b|litres?|liters?|l\b))")


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
        # A STATED mean arterial pressure. Derivation happens in merge(), over
        # the accumulated state — this turn's text is not where a MAP whose
        # systolic arrived three turns ago can be computed.
        ("map",  _MAP_LABEL + _SEP + _NUM),
    ):
        for m in re.finditer(pattern + r"\b", q):
            take(name, float(m.group(1)), m.span(), m.group(0))

    # ── Glucose, in whichever unit it was stated ────────────────────────────
    # Before temperature on purpose: _TEMP_LABEL includes a bare "t", and
    # _spans_overlap only defends spans that have ALREADY been consumed.
    # (?!\d) is load-bearing. Every other label in this file is followed by a
    # trailing \b, which is what stops "hr 1288" being read as a heart rate of
    # 128; this pattern ends in an OPTIONAL unit group, so \b would sit after
    # something that may not be there and "glucose 2000" silently became 200 —
    # a rejectable value turned into a plausible one.
    for m in re.finditer(
            _GLUCOSE_LABEL + _REPORTED + _SEP + r"(\d{1,4}(?:\.\d+)?)(?!\d)\s*"
            r"(mg/dl|mg\s*per\s*dl|mmol/l|mmol)?", q):
        _take_glucose(float(m.group(1)), (m.group(2) or "").strip(),
                      m, consumed, readings, rejections, ts)

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
        # The overlap test up front, not inside take(): the diastolic used to be
        # stored whether or not the systolic survived it, so "HR 90/50" — where
        # the 90 already belongs to the heart rate — left a diastolic of 50 with
        # no systolic behind it. Half a pressure is not a pressure, and it is
        # not something to derive a MAP from either.
        if _spans_overlap(m.span(), consumed):
            continue
        if _in_range("sbp", sbp) and _in_range("dbp", dbp) and sbp > dbp:
            take("sbp", sbp, m.span(), m.group(0))
            readings.setdefault("dbp", VitalReading(
                value=dbp, unit=_unit("dbp"), ts=ts, raw=m.group(0).strip()))

    # ── A number beside a vital label that nothing above could read ─────────
    # F-4. "he's satting 84 on room air now" left the PREVIOUS SpO2 of 96 in
    # place, recorded no supersession and said nothing — so the answer was
    # produced against a saturation twelve points too high and nothing in the
    # response, the context or the log showed that the newer number had been
    # dropped. Silence must never be indistinguishable from agreement.
    #
    # This is the backstop, not the fix: the label table above is where a
    # phrasing should be read correctly. What this guarantees is that failing
    # to read one is VISIBLE.
    for label in _ALL_VITAL_LABELS:
        for m in re.finditer(
                label + r"[^\d\n]{0,12}?(\d{1,4}(?:\.\d+)?)" + _NOT_A_VITAL_AFTER, q):
            if _spans_overlap(m.span(), consumed):
                continue
            consumed.append(m.span())
            rejections.append(VitalRejection(
                name="unreadable", raw=m.group(0).strip(),
                reason="could not be read as a vital in that phrasing"))

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


def _take_glucose(value: float, stated_unit: str, m, consumed, readings,
                  rejections, ts):
    """A blood glucose, in the unit it was stated in — or the assumed one.

    Temperature can disambiguate an unlabelled number because its two bands do
    not overlap. Glucose's DO: 32 is a critical low in mg/dL and a high in
    mmol/L, which are opposite emergencies with opposite treatments. There is
    no reading of the number that resolves that, so this does not guess from
    the value — it applies the documented convention in
    `assumed_unit_when_unstated`, records which unit it assumed, and lets the
    caution quote it back. Visible assumption, not a silent one.

    A STATED unit is always honoured and never reinterpreted.
    """
    if _spans_overlap(m.span(), consumed):
        return
    spec = RANGES.get("glucose") or {}
    canonical_unit = _unit("glucose")
    alt_unit = _alt_unit("glucose")
    stated = stated_unit.lower().replace(" ", "").replace("per", "/")

    if stated in ("mg/dl", "mg/dl"):
        unit = canonical_unit if _in_range("glucose", value) else None
    elif stated in ("mmol/l", "mmol"):
        unit = alt_unit if _in_alt_range("glucose", value) else None
    else:
        # Unlabelled. Convention, not inference.
        assumed = spec.get("assumed_unit_when_unstated") or canonical_unit
        if assumed == alt_unit:
            unit = alt_unit if _in_alt_range("glucose", value) else None
        else:
            unit = canonical_unit if _in_range("glucose", value) else None

    if unit is None:
        consumed.append(m.span())
        rejections.append(VitalRejection(
            name="glucose", raw=m.group(0),
            reason=_reason("glucose", value, stated_unit.upper())))
        return

    # Canonical is mg/dL, which is what the caution thresholds are written in.
    canonical = value if unit == canonical_unit else round(value * 18.0182, 1)
    consumed.append(m.span())
    readings["glucose"] = VitalReading(
        value=value, unit=unit, ts=ts, raw=m.group(0),
        canonical_value=canonical, derived=False)


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
# DERIVATION — mean arterial pressure
# ─────────────────────────────────────────────────────────────────────────────
#
# The only value in this module the system produces rather than hears. Kept
# here, next to merge(), because it is a property of the ACCUMULATED state: a
# systolic stated three turns ago and a diastolic stated in this one still make
# a MAP, and parse_vitals only ever sees one turn.

MAP_FORMULA = "(SBP + 2*DBP)/3"


def _older_ts(a: VitalReading, b: VitalReading) -> Optional[str]:
    """The timestamp of whichever input is older, or None if either is unknown.

    A derived value is only as fresh as the stalest thing it was derived from.
    An input with no timestamp makes the result's age unknown rather than equal
    to the other one: "age unknown" is potentially any age, and taking the known
    timestamp instead would present a derived number as fresher than its data.
    """
    ta, tb = _parse_ts(a.ts), _parse_ts(b.ts)
    if ta is None or tb is None:
        return None
    return a.ts if ta <= tb else b.ts


def derive_map(readings: dict) -> Optional[VitalReading]:
    """MAP from a recorded pressure, or None when there is not one.

    Rounded to a whole number: the inputs are whole millimetres of mercury read
    off a cuff, and a MAP of 53.333 claims a precision the measurement does not
    have. Thirds of an integer never land on a half, so the rounding mode never
    arises.

    No range check. Both inputs already passed their own plausibility bands and
    `map` spans everything derivable from them, so a derived MAP cannot be out
    of range without the config being incoherent. A pressure that FAILED those
    bands was never stored, so it yields no MAP here either — the impossible
    input path is unchanged, and this function is simply never reached with one.
    """
    sbp, dbp = (readings or {}).get("sbp"), (readings or {}).get("dbp")
    if sbp is None or dbp is None:
        return None
    value = float(round((sbp.value + 2 * dbp.value) / 3))
    return VitalReading(value=value, unit=_unit("map"),
                        ts=_older_ts(sbp, dbp),
                        raw=f"derived from {sbp.value:g}/{dbp.value:g}",
                        derived=True)


def _apply_map(merged: dict, incoming: dict) -> None:
    """Bring MAP back into agreement with the pressures, in place.

    Recomputed after every fold rather than carried forward: a MAP that outlived
    one of its inputs is a stale vital wearing a fresh one's face.

    A STATED MAP wins over a derived one — the medic may be reading an arterial
    line, and arithmetic does not get to overrule a measurement. It stops
    winning as soon as a pressure is newer than it. "Newer" is turn order, not a
    timestamp comparison, for the same reason merge() orders by replay: a turn
    carrying no `ts` still supersedes the turn before it.
    """
    if "map" in incoming:
        return                       # stated this turn — already folded in, and it wins
    prior = merged.get("map")
    if prior is not None and not prior.derived and not (
            "sbp" in incoming or "dbp" in incoming):
        return                       # a stated MAP stands until a pressure outdates it
    derived = derive_map(merged)
    if derived is not None:
        merged["map"] = derived


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
    # After the fold, so it derives from the state the turn actually left behind.
    # A recompute is not a supersession: nothing was displaced, the same formula
    # was applied to newer inputs, and those inputs are already in `superseded`.
    # Only a MAP the medic restated appears there, via the loop above.
    _apply_map(merged, incoming or {})
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
        # Said out loud, because a computed number that reads as a measured one
        # is exactly the confusion this flag exists to prevent.
        if r.derived:
            line += f", derived {MAP_FORMULA}" if name == "map" else ", derived"
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


# The boolean patient facts a caution rule may arm on, as opposed to a
# measurement in RANGES. Declared here so the meta-test that checks every rule
# names something real still catches a typo in vitals_rules.json — an unknown
# `when` key must fail loudly, not silently never arm.
PATIENT_FLAGS = ("ams_stated",)


def _rule_armed(rule: dict, readings: dict, flags: Optional[dict] = None):
    """The readings that arm this rule, or None if it is not armed.

    A rule whose vital was never recorded is not armed. Absence of a vital is
    not a normal vital — the system does not know the blood pressure, and must
    not reason as though it were fine.

    `flags` carries boolean facts about the patient that are not measurements
    — `ams_stated` is the first. A rule tests one with {"is": true}. They are
    kept out of `readings` because that table stores things that were measured,
    and "the medic called him confused" is not a measurement.
    """
    armed = {}
    flags = flags or {}
    for name, test in (rule.get("when") or {}).items():
        if name in flags:
            if not all(comparator == "is" and bool(flags[name]) == bool(expected)
                       for comparator, expected in test.items()):
                return None
            continue
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


def conflicts(response_text: str, readings: dict,
              flags: Optional[dict] = None) -> list:
    """Cautions where the response and the recorded vitals disagree.

    Returns caution strings, not issues. These never block: apply_safety_gate
    appends them to a served response and downgrades SAFE to
    NEEDS_HUMAN_REVIEW. A parser reading one-handed free text does not get to
    stand between a medic and a protocol answer.
    """
    if not response_text or not (readings or flags):
        return []
    response_lower = response_text.lower()
    out = []
    # Rules sharing a `group` are one caution with more than one way to arm.
    # Hypotension is the case: SBP < 90 and MAP < 65 are the same warning about
    # the same patient, and 82/40 arms both. Saying it twice in two sentences
    # that differ only in which number they quote is how a caution stops being
    # read — which the narrowness of this table exists to prevent. First armed
    # rule in table order speaks for the group.
    spoken_for = set()
    for rule in CAUTIONS:
        group = rule.get("group")
        if group is not None and group in spoken_for:
            continue
        armed = _rule_armed(rule, readings, flags)
        if armed is None:
            continue
        for drug in rule.get("drugs", []):
            if not _drug_present(response_lower, drug):
                continue
            # Quoted back in the unit the medic used. The comparison was
            # canonical; the sentence they read should be the number they typed.
            values = {name: _caution_value(r) for name, r in armed.items()}
            out.append(rule.get("caution", "").format(drug=drug, **values))
            if group is not None:
                spoken_for.add(group)
            break            # one caution per rule, named for the first agent found
    return out
