"""
EdgeCDSS — the spoken brief. What the listen button says.

V3 (owner, 2026-10-26): "A spoken brief for every answer: cards and doses
speak the GIVE line and one WATCH line; a hold speaks one sentence ("Held. No
signed dose for magnesium. Use local protocol."); the full text stays on
screen. Numbers and units written out for speech: "zero point one eight
millilitres", "micrograms", "every five minutes", never abbreviations. Fixed
templates, tested, no model wording in the spoken brief."

The rule that makes it safe is the last one. Every word spoken is one of:
  - a fixed phrase written here ("Held.", "Give", "Use local protocol.");
  - a number, unit or route read off a code-made dose line, written out;
  - a drug name from the recognised-drug index (drug_contracts);
  - a line of a deterministic answer (no model wrote it: a card, a gate
    question, a pre-gate refusal), written out by the same converter, and
    only when nothing unspeakable is left in it.
A model answer's own sentences are never spoken: not its WATCH line, not its
indication clause, not its prose. When nothing qualifies, a fixed sentence
sends the medic to the screen.

The shapes, in order:
  hold          "Held. No signed dose for <drug>. Use local protocol."
                "Held. The <drug> dose in the answer is not the signed dose.
                 Use local protocol."
                "Held. The reason is on the screen. Use local protocol."
  dose          "Give <drug>, <dose>, <route>." per dose line (at most three),
                then "Draw <volume> of <drug>, <concentration>." when the card
                states the volume, or "Confirm the concentration before drawing
                it up." when it says it has none; then one WATCH line
                ("Watch: ...") when a card wrote it.
  card, gate    its GIVE line(s) and WATCH line, or its first brief line, as
                written out by the converter.
  model, no dose  "No dose in this answer. The answer is on the screen."

Text in, text out: built once, after the brief, from the served response. It
changes nothing on screen and nothing any gate saw.
"""

import re

try:
    import drug_contracts
except Exception:  # the voice must not be able to break the answer
    drug_contracts = None

# Owned by openai_client.build_safety_hold; test_brief pins brief.py's copy.
HOLD_OPENER = "Clinical safety hold. This response was blocked."
HOLD_ISSUES_LABEL = "Issues identified:"

USE_LOCAL = "Use local protocol."
HOLD_UNSIGNED = "Held. No signed dose for {drugs}. " + USE_LOCAL
HOLD_NOT_SIGNED = "Held. The {drugs} dose in the answer is not the signed dose. " + USE_LOCAL
HOLD_OTHER = "Held. The reason is on the screen. " + USE_LOCAL
GIVE = "Give {drug}, {dose}, {route}."
DRAW = "Draw {volume} of {drug}, {concentration}."
NO_VOLUME = "Confirm the concentration before drawing it up."
WATCH = "Watch: {line}"
MORE_DOSES = "More doses are on the screen."
SAME_DRUG_TWICE = "There are two doses of {drug}. Read them on the screen."
MODEL_NO_DOSE = "No dose in this answer. The answer is on the screen."
CARD_ON_SCREEN = "The card is on the screen."
# Owner, 2026-10-26: "the which-indication question gets its own spoken
# template: '<Drug>. Which indication: <list>?' with the list of names only."
WHICH_INDICATION = "{drug}. Which indication: {names}?"

MAX_DOSES = 3
DOSE_SECTIONS = ("GIVE", "POST-INTUBATION SEDATION", "DRIP", "RATE")
SECTION_LEAD = {"POST-INTUBATION SEDATION": "After intubation, ", "DRIP": "For the drip, "}
WATCH_SECTIONS = ("WATCH", "WATCH FOR")
INDICATION_LEAD = "For {indication}, "

# ── Numbers ─────────────────────────────────────────────────────────────────

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _int_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + ("" if rest == 0 else " and " + _int_words(rest))
    if n < 1_000_000:
        rest = n % 1000
        joiner = "" if rest == 0 else (" and " if rest < 100 else " ")
        return _int_words(n // 1000) + " thousand" + ("" if rest == 0 else joiner + _int_words(rest))
    raise ValueError(n)


def number_words(text: str) -> str:
    """'0.18' -> 'zero point one eight'; '2000' -> 'two thousand';
    '1,000' -> 'one thousand'. Digits after the point are read one by one."""
    whole, _, frac = text.replace(",", "").partition(".")
    out = _int_words(int(whole or "0"))
    if frac:
        out += " point " + " ".join(_ONES[int(d)] for d in frac)
    return out


# ── Units ───────────────────────────────────────────────────────────────────
# (pattern, singular, plural). Compound units first: the longest match wins.
_UNITS = [
    (r"mcg/kg/min", "microgram per kilogram per minute", "micrograms per kilogram per minute"),
    (r"mg/kg/hr?", "milligram per kilogram per hour", "milligrams per kilogram per hour"),
    (r"mcg/kg", "microgram per kilogram", "micrograms per kilogram"),
    (r"mg/kg", "milligram per kilogram", "milligrams per kilogram"),
    (r"mL/kg", "millilitre per kilogram", "millilitres per kilogram"),
    (r"mg/mL", "milligram per millilitre", "milligrams per millilitre"),
    (r"mcg/mL", "microgram per millilitre", "micrograms per millilitre"),
    (r"mL/hr?", "millilitre per hour", "millilitres per hour"),
    (r"mg/hr?", "milligram per hour", "milligrams per hour"),
    (r"L/min", "litre per minute", "litres per minute"),
    (r"mmHg", "millimetre of mercury", "millimetres of mercury"),
    (r"mEq", "milliequivalent", "milliequivalents"),
    (r"mcg|µg|micrograms?", "microgram", "micrograms"),
    (r"mg|milligrams?", "milligram", "milligrams"),
    (r"mL|ml|millilit(?:re|er)s?", "millilitre", "millilitres"),
    (r"kg|kilograms?", "kilogram", "kilograms"),
    (r"g|grams?", "gram", "grams"),
    (r"L", "litre", "litres"),
    (r"units?", "unit", "units"),
    (r"min|minutes?", "minute", "minutes"),
    (r"hrs?|hours?|h", "hour", "hours"),
    (r"%", "percent", "percent"),
]
_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"   # 2,000 is a number; "30, never" is not
_UNIT_ALT = "|".join(f"(?:{p})" for p, _, _ in _UNITS)
_AMOUNT_RE = re.compile(rf"({_NUM})(?:\s*[-–]\s*({_NUM}))?\s*({_UNIT_ALT})(?![A-Za-z])")


def _unit_words(unit: str, singular: bool) -> str:
    for pattern, one, many in _UNITS:
        if re.fullmatch(pattern, unit):
            return one if singular else many
    raise ValueError(unit)


def amount_words(lo: str, hi: str, unit: str) -> str:
    """'5', '20', 'mcg' -> 'five to twenty micrograms'; '1', None, 'mL' ->
    'one millilitre'."""
    if hi:
        return f"{number_words(lo)} to {number_words(hi)} {_unit_words(unit, False)}"
    return f"{number_words(lo)} {_unit_words(unit, lo.replace(',', '') == '1')}"


# Units that stand alone, with no number: "document concentration in mg/mL".
_BARE_UNITS = [(r"mcg/kg/min", "micrograms per kilogram per minute"),
               (r"mL/kg", "millilitres per kilogram"), (r"mg/mL", "milligrams per millilitre"), (r"mcg/mL", "micrograms per millilitre"),
               (r"mL/hr?", "millilitres per hour"), (r"mg/kg", "milligrams per kilogram"),
               (r"mcg/kg", "micrograms per kilogram"), (r"kg", "kilograms"),
               (r"mg", "milligrams"), (r"mcg", "micrograms"), (r"mL", "millilitres")]

# ── Routes and abbreviations ────────────────────────────────────────────────

ROUTE_SPOKEN = {"IV": "intravenously", "IO": "intraosseously", "IM": "intramuscularly",
                "IN": "intranasally", "PO": "by mouth", "SC": "subcutaneously",
                "SQ": "subcutaneously", "IV/IO": "intravenously or intraosseously",
                "IO/IV": "intraosseously or intravenously"}
_ROUTE_ALT = "|".join(sorted((re.escape(r) for r in ROUTE_SPOKEN), key=len, reverse=True))

# In running text (a card's WATCH line, a gate question). Case-sensitive, as
# written on the cards. A line with an abbreviation not in this table is not
# spoken.
ABBREVIATIONS = {
    "IV/IO": "intravenous or intraosseous", "IV": "intravenous", "IO": "intraosseous",
    "IM": "intramuscular", "PO": "by mouth",
    "BP": "blood pressure", "SBP": "systolic blood pressure", "HR": "heart rate",
    "RR": "respiratory rate", "SpO2": "oxygen saturation",
    "ETCO2": "end-tidal carbon dioxide", "EtCO2": "end-tidal carbon dioxide",
    "GCS": "Glasgow coma scale", "CPR": "C P R", "ECG": "E C G", "TXA": "tranexamic acid",
    "TBI": "traumatic brain injury", "ICP": "intracranial pressure",
    "RSI": "rapid sequence intubation", "DCR": "damage control resuscitation",
    "LTOWB": "low titre O whole blood", "NS": "normal saline", "PEEP": "PEEP",
    "CICO": "can't intubate, can't oxygenate", "MAP": "mean arterial pressure",
    "pH": "P H", "FiO2": "inspired oxygen", "VT": "tidal volume", "IBW": "ideal body weight",
}
# Spelled-out letters and PEEP are words a medic says; the guard lets them by.
_SAID_AS_LETTERS = {"C P R", "E C G", "P H", "PEEP", "O"}
_ABBR_RE = re.compile(r"(?<![\w/])(" + "|".join(sorted((re.escape(a) for a in ABBREVIATIONS),
                                                     key=len, reverse=True)) + r")(?![\w/])")


def _unspeakable(text: str) -> bool:
    """Anything left that a voice would read as letters or symbols."""
    t = text
    for ok in _SAID_AS_LETTERS:
        t = t.replace(ok, "")
    return bool(re.search(r"\d|[/=<>≥≤×*#|@\\\[\]{}%]|\b[A-Z]{2,}\b|\b\w*[a-z][A-Z]\w*\b"
                          r"|\b[A-Za-z]+\d|\b(?:mg|mcg|ml|mL|kg|min|hrs?|mmHg|mEq|IU)\b", t))


def speak_line(line: str):
    """A deterministic line, written out for speech, or None when something
    in it cannot be said (a number in an unknown form, an abbreviation not in
    the table). Never a line a model wrote: the caller decides that."""
    t = re.sub(r"\*\*|`", "", line or "").strip()
    t = re.sub(r"^(?:[-•*]|\d+[.)])\s+", "", t)
    t = re.sub(r"\bq\s*(\d+)\s*(min|minutes?|hrs?|hours?|h)\b", r"every \1 \2", t, flags=re.I)
    # "500 mg / 10 mL" is a vial: five hundred milligrams in ten millilitres.
    t = re.sub(rf"({_NUM}\s*(?:mg|mcg|g))\s*/\s*({_NUM}\s*mL)", r"\1 in \2", t)
    t = _AMOUNT_RE.sub(lambda m: amount_words(m.group(1), m.group(2), m.group(3)), t)
    for pattern, words in _BARE_UNITS:
        t = re.sub(rf"(?<![\w/]){pattern}(?![\w/])", words, t)
    t = _ABBR_RE.sub(lambda m: ABBREVIATIONS[m.group(1)], t)
    t = re.sub(r"\s*(?:>=|≥)\s*", " at least ", t)
    t = re.sub(r"\s*(?:<=|≤)\s*", " at most ", t)
    t = re.sub(r"\s*<\s*", " under ", t)
    t = re.sub(r"\s*>\s*", " over ", t)
    t = re.sub(rf"(?<![\w.:])({_NUM})(?:\s*[-–]\s*({_NUM}))?(?![\w:]|\.\d)",
               lambda m: number_words(m.group(1)) + (f" to {number_words(m.group(2))}" if m.group(2) else ""), t)
    t = re.sub(r"\s*=\s*", " means ", t)
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = re.sub(r"(?<=[A-Za-z])\s*/\s*(?=[A-Za-z])", " or ", t)
    t = re.sub(r"\s*\(\s*", ", ", t)
    t = re.sub(r"\s*\)\s*", ", ", t)
    t = t.replace("&", " and ").replace("+", " plus ")
    t = re.sub(r",\s*([,.?!:;])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,")
    if not t or _unspeakable(t):
        return None
    if t[-1] not in ".?!":
        t += "."
    return t


# ── Reading the response ────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^\s*(?:⚠️\s*)?\*\*([^*a-z]*[A-Z][^*a-z]*)\*\*:?\s*(.*)$")
_ITEM_RE = re.compile(r"^(?:[-•*]|\d+[.)])\s+")


def sections(response: str) -> dict:
    """{HEADING: [item, ...]}, in order, first occurrence of each heading."""
    out, current = {}, None
    for raw in (response or "").splitlines():
        m = _HEADING_RE.match(raw)
        if m:
            current = m.group(1).strip().rstrip(":").upper()
            out.setdefault(current, [])
            if m.group(2).strip():
                out[current].append(m.group(2).strip())
            continue
        line = _ITEM_RE.sub("", raw.strip())
        if current and line:
            out[current].append(line)
    return out


def _drug_index() -> dict:
    """term -> generic name, every drug the dose check recognises."""
    if drug_contracts is None:
        return {}
    try:
        return {t.lower(): g.lower() for t, g in drug_contracts.recognised_drug_index().items()}
    except Exception:
        return {}


def _say_drug(name: str):
    """A drug name for speech: "sodium chloride 3%" -> "sodium chloride three
    percent". None if anything in it still cannot be said."""
    said = re.sub(r"(\d+(?:\.\d+)?)\s*%", lambda m: f"{number_words(m.group(1))} percent", name)
    return None if _unspeakable(said) else said


def _known_drug(text: str, index: dict):
    """The drug as written on a dose line, said aloud, if it is a recognised
    drug name, else None."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if t not in index and t not in index.values():
        return None
    return _say_drug(t)


# The dose lines are code-made (openai_client's canonical GIVE line and the
# card builders), in three shapes:
#   Draw 0.18 mL of 1mg/mL epinephrine IM (0.18 mg).
#   Draw 168 mg of artesunate IV (168 mg).
#   ketamine IV: 160 mg (2 mg/kg × 80 kg). NO VOLUME — confirm concentration …
_DRAW_RE = re.compile(
    rf"^Draw ({_NUM}) mL of ({_NUM})\s*(mg|mcg)/mL (.+?) ({_ROUTE_ALT}) \(({_NUM}) (mg|mcg|g|units)\)\.?")
_DRAW_MASS_RE = re.compile(
    rf"^Draw ({_NUM}) (mg|mcg|g|units) of (.+?) ({_ROUTE_ALT}) \(({_NUM}) (mg|mcg|g|units)\)\.?")
_COLON_RE = re.compile(
    rf"^(.+?) ({_ROUTE_ALT}):\s*({_NUM})(?:\s*[-–]\s*({_NUM}))?\s*"
    r"(mcg/kg/min|mg/kg/hr?|mcg/kg|mg/kg|mg|mcg|g|units|mL)(?![\w/])")
_NO_VOLUME_RE = re.compile(r"\bno volume\b", re.IGNORECASE)


def dose_sentences(line: str, index: dict):
    """(drug, [sentences]) for a code-made dose line, or None when the line is
    not one (or names a drug the index does not know)."""
    body = line.split(" Indication:")[0].strip()
    m = _DRAW_RE.match(body)
    if m:
        vol, conc, cu, drug, route, dose, du = m.groups()
        name = _known_drug(drug, index)
        if not name:
            return None
        return name, [GIVE.format(drug=name, dose=amount_words(dose, None, du),
                                  route=ROUTE_SPOKEN[route]),
                      DRAW.format(volume=amount_words(vol, None, "mL"), drug=name,
                                  concentration=amount_words(conc, None, f"{cu}/mL"))]
    m = _DRAW_MASS_RE.match(body)
    if m:
        amt, au, drug, route, dose, du = m.groups()
        name = _known_drug(drug, index)
        if not name:
            return None
        return name, [GIVE.format(drug=name, dose=amount_words(dose, None, du),
                                  route=ROUTE_SPOKEN[route]), NO_VOLUME]
    m = _COLON_RE.match(body)
    if m:
        drug, route, lo, hi, unit = m.groups()
        name = _known_drug(drug, index)
        if not name:
            return None
        out = [GIVE.format(drug=name, dose=amount_words(lo, hi, unit), route=ROUTE_SPOKEN[route])]
        if _NO_VOLUME_RE.search(body):
            out.append(NO_VOLUME)
        return name, out
    return None


def _hold(response: str, index: dict) -> str:
    issues = response.split(HOLD_ISSUES_LABEL, 1)[1] if HOLD_ISSUES_LABEL in response else ""
    issues = [_ITEM_RE.sub("", l.strip()) for l in issues.splitlines() if l.strip().startswith("-")]
    # A39's hold (openai_client.unsigned_drug_hold_issue): the names it lists
    # are the recognised-drug index's own.
    for issue in issues:
        m = re.search(r"has no signed entry for (.+?), so it gives no answer", issue)
        if m:
            names = [_known_drug(n, index) for n in m.group(1).split(" or ")]
            if names and all(names):
                return HOLD_UNSIGNED.format(drugs=" or ".join(names))
    # The dose check's holds say "signed" (or name ALLOWED_DOSES): the drug
    # they are about is said from the index, never the issue's own words.
    named = []
    for issue in issues:
        if not re.search(r"\bsigned\b|ALLOWED_DOSES", issue):
            continue
        low = issue.lower()
        found = sorted(((low.find(g), g) for g in set(index.values())
                        if re.search(rf"(?<![\w-]){re.escape(g)}(?![\w-])", low)))
        for _, g in found:
            said = _say_drug(g)
            if said and said not in named:
                named.append(said)
    if named:
        return HOLD_NOT_SIGNED.format(drugs=" and ".join(named[:2]))
    return HOLD_OTHER


def build(result: dict) -> str:
    """The spoken brief for one served answer. Never raises: a failure here
    is a fixed sentence pointing at the screen, not a missing answer."""
    try:
        return _build(result)
    except Exception:
        return CARD_ON_SCREEN


def _lead(lead: str, sentence: str) -> str:
    return lead + sentence[0].lower() + sentence[1:]


def _indication(item: str):
    """A deterministic dose line's own Indication clause, said aloud, or None."""
    m = re.search(r"\bIndication:\s*(.+)$", item)
    said = speak_line(m.group(1)) if m else None
    return said.rstrip(".") if said else None


def indication_name(word: str):
    """One option of the which-indication question, as a name for speech:
    the bracketed qualifier dropped ("penetrating brain or spinal injury
    (antibiotic prophylaxis)" -> "penetrating brain or spinal injury"), the
    rest through speak_line. None if it cannot be said."""
    said = speak_line(re.sub(r"\s*\([^)]*\)", "", word))
    return said.rstrip(".") if said else None


def _which_indication(response: str):
    """WHICH_INDICATION for a which-indication question, or None when the
    question is not exactly the one openai_client.which_indication_question
    writes from INDICATION_CLASSES: the options are matched against that fixed
    list and the question must rebuild from them word for word."""
    from openai_client import INDICATION_CLASSES, INDICATION_QUESTION_PREFIX
    text = response.strip()
    if not text.startswith(INDICATION_QUESTION_PREFIX) or not text.endswith("?"):
        return None
    drug, sep, tail = text[len(INDICATION_QUESTION_PREFIX):-1].partition(" — ")
    if not sep:
        return None
    words, taken = [], []
    for w in sorted({w for _n, w, _l, _c in INDICATION_CLASSES}, key=len, reverse=True):
        for m in re.finditer(re.escape(w), tail):
            if not any(m.start() < b and a < m.end() for a, b in taken):
                taken.append((m.start(), m.end()))
                words.append((m.start(), w))
    words = [w for _, w in sorted(words)]
    if len(words) < 2 or f"{', '.join(words[:-1])} or {words[-1]}" != tail:
        return None
    said_drug = _say_drug(drug.strip())
    names = [indication_name(w) for w in words]
    if not said_drug or not all(names):
        return None
    return WHICH_INDICATION.format(drug=_capitalised(said_drug),
                                   names=f"{', '.join(names[:-1])} or {names[-1]}")


def _build(result: dict) -> str:
    response = result.get("response") or ""
    index = _drug_index()
    if response.lstrip().startswith(HOLD_OPENER):
        return _hold(response, index)
    which = _which_indication(response)
    if which:
        return which
    deterministic = not result.get("model")
    secs = sections(response)

    dose_lines = [(sec, item, dose_sentences(item, index))
                  for sec in DOSE_SECTIONS for item in secs.get(sec, [])]
    # One drug twice in a section is told apart by its indication. On a card
    # that is the signed entry's own clause; a model's is model wording, so a
    # model answer sends the medic to the screen instead.
    repeated = set()
    for sec in DOSE_SECTIONS:
        names = [got[0] for s_, _, got in dose_lines if s_ == sec and got]
        repeated.update((sec, n) for n in names if names.count(n) > 1)
    for sec, name in repeated:
        if not deterministic:
            return SAME_DRUG_TWICE.format(drug=name)
    sections_with_doses = {sec for sec, _, got in dose_lines if got}

    spoken, doses = [], 0
    for sec, item, got in dose_lines:
        if got:
            if doses == MAX_DOSES:
                spoken.append(MORE_DOSES)
                break
            doses += 1
            name, sentences = got
            first = sentences[0]
            if (sec, name) in repeated:
                ind = _indication(item)
                if not ind:
                    return SAME_DRUG_TWICE.format(drug=name)
                first = _lead(INDICATION_LEAD.format(indication=ind), first)
            elif len(sections_with_doses) > 1 and sec in SECTION_LEAD:
                first = _lead(SECTION_LEAD[sec], first)
            spoken.extend([first] + sentences[1:])
        elif deterministic:
            said = speak_line(item)
            if said:
                spoken.append(said)

    if not deterministic:
        return _capitalised(" ".join(spoken)) if spoken else MODEL_NO_DOSE
    if not spoken:
        first = (result.get("brief") or "").splitlines()
        said = speak_line(first[0]) if first else None
        if said:
            spoken.append(said)
    watch = [w for sec in WATCH_SECTIONS for w in secs.get(sec, [])][:1]
    for line in watch:
        said = speak_line(line)
        if said:
            keep_case = said.startswith(("Glasgow", "C P R", "E C G", "P H", "PEEP", "O "))
            spoken.append(WATCH.format(line=said if keep_case else said[0].lower() + said[1:]))
    return _capitalised(" ".join(spoken)) if spoken else CARD_ON_SCREEN


def _capitalised(text: str) -> str:
    return text[:1].upper() + text[1:]
