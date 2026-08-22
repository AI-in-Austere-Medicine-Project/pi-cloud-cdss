"""
EdgeCDSS — ventilator card engine.

Three card families, one engine, all deterministic tier: no model call ever
produces card content. This closes F-12's class rather than F-12's instance —
the eval baseline showed 4 of 4 TBI vent queries answering with settings and
0 of 4 DKA vent queries doing so, because the only place the **VENT** block
was specified was a format hint on the JTS prompt, which a retrieval miss
routes around.

    vent_cards.json           physiology -> initial settings
    vent_troubleshooting.json alarms and decompensation -> ordered steps
    vent_devices.json         four field ventilators -> where things live

THE CLINICAL FENCE IS STRUCTURAL, NOT ADVISORY
──────────────────────────────────────────────
This module is engine, schema, dispatch and rendering. It contains no
settings, no doses, no thresholds and no alarm interpretations, and the JSON
files ship with every clinical field empty or PENDING_CLINICAL_SIGNOFF.

`signoff` is the gate. A card with signoff false — or absent, or malformed, or
still carrying a PENDING sentinel in a required clinical field — CANNOT be
served: dispatch returns None and the caller falls through to exactly the
behaviour it had before this module existed. There is no flag, no override and
no debug path that serves an unsigned card, because the failure mode of a
half-authored ventilator card is a patient ventilated on a placeholder.

The owner (A. Azelton) is the sole author of clinical content. Cards go live
one at a time as signoff lands; partial deployment is the normal state, not a
migration step.

IDEAL BODY WEIGHT
─────────────────
Tidal volume is dosed on ideal body weight, not actual. The Devine formula is
specified in the build request and implemented here as engine arithmetic:

    male    50.0 kg + 2.3 kg per inch over 60 inches
    female  45.5 kg + 2.3 kg per inch over 60 inches

It needs height AND sex. When either is missing the engine does not guess: it
serves on actual weight with the caveat line the CARD defines (not one this
module writes) and asks for what is missing as a non-blocking follow-up.

The F-1 weight-confidence rule applies unchanged. A hedged weight lands in
estimated_weight_kg, and estimated weight cannot anchor a tidal volume any
more than it can anchor a drug dose.
"""

import datetime
import json
import os
import pathlib
import re
from typing import Optional

_DIR = pathlib.Path(__file__).parent

PENDING = "PENDING_CLINICAL_SIGNOFF"

# The one author permitted to sign a card, and the name that appears in the
# served source line. Config so a second reviewer is an edit, not a code
# change; a list so co-signature is expressible without reshaping anything.
SIGNOFF_AUTHORS = tuple(
    a.strip() for a in os.getenv("CDSS_CARD_AUTHORS", "A. Azelton").split(",")
    if a.strip())

# Longest content field a device card may carry. Device cards are the owner's
# AUTHORED SUMMARY of an operator's manual, never reproduced manual text, and
# a summary does not run to paragraphs. This is a structural brake on the
# copyright rule, not a style preference — see lint_device_cards().
DEVICE_FIELD_MAX_CHARS = 400


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

# Fields every card in every family carries. `signoff` is last because it is
# the one the engine actually gates on and it should read as the conclusion.
_PROVENANCE_FIELDS = ("source_label", "reviewed_by", "review_date",
                      "references", "version", "signoff")

_FAMILY_SCHEMA = {
    "physiology": {
        "required": ("id", "title", "applies_when", "initial_settings",
                     "titrate_on", "watch_for", "evac_if", "escape_hatch"),
        # Clinical fields — these are what must be non-empty and non-PENDING
        # before the card can be served.
        "clinical": ("initial_settings", "titrate_on", "watch_for", "evac_if",
                     "escape_hatch"),
        "settings_keys": ("mode", "vt_ml_per_kg_ibw", "rate_strategy", "peep",
                          "fio2"),
    },
    "troubleshooting": {
        "required": ("id", "title", "applies_when", "steps"),
        "clinical": ("steps",),
        "step_keys": ("check", "finding", "action"),
    },
    "device": {
        "required": ("id", "title", "applies_when", "startup_sequence",
                     "parameter_map", "alarm_table", "quirks", "crosswalk",
                     "manual_reference"),
        "clinical": ("startup_sequence", "parameter_map", "alarm_table",
                     "quirks", "crosswalk"),
        "manual_keys": ("title", "revision", "verified_date"),
    },
}


class CardError(ValueError):
    """A card file that cannot be trusted. Raised at load, never at serve."""


def _load(filename: str) -> dict:
    path = _DIR / filename
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  {filename} not found — that card family is unavailable.")
        return {}
    except (json.JSONDecodeError, OSError) as e:
        # Same rule as providers.json and vitals_rules.json: a broken config
        # degrades to the feature being absent, loudly, never to a server that
        # will not boot.
        print(f"⚠️  {filename} is unreadable ({e}) — that card family is unavailable.")
        return {}
    return {c["id"]: c for c in raw.get("cards", []) if isinstance(c, dict) and c.get("id")}


PHYSIOLOGY = _load("vent_cards.json")
TROUBLESHOOTING = _load("vent_troubleshooting.json")
DEVICES = _load("vent_devices.json")

FAMILIES = {
    "physiology": PHYSIOLOGY,
    "troubleshooting": TROUBLESHOOTING,
    "device": DEVICES,
}


def _is_pending(value) -> bool:
    """Whether a field still carries the sentinel, at any depth."""
    if isinstance(value, str):
        return value.strip() == PENDING or value.strip() == ""
    if isinstance(value, dict):
        return not value or any(_is_pending(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return not value or any(_is_pending(v) for v in value)
    return value is None


def card_is_servable(card: dict, family: str) -> tuple:
    """(servable, reason). The single gate every serve path goes through.

    Deliberately returns a REASON rather than a bare bool: "why is this card
    not live" is the question the worksheet exists to answer, and an operator
    who cannot get an answer out of the system will guess.
    """
    if not card:
        return False, "no such card"
    schema = _FAMILY_SCHEMA.get(family)
    if schema is None:
        return False, f"unknown family {family!r}"

    missing = [f for f in schema["required"] + _PROVENANCE_FIELDS if f not in card]
    if missing:
        return False, f"missing field(s): {', '.join(sorted(missing))}"

    if card.get("signoff") is not True:
        return False, "signoff is not true"

    reviewer = str(card.get("reviewed_by") or "").strip()
    if reviewer not in SIGNOFF_AUTHORS:
        return False, f"reviewed_by {reviewer!r} is not an authorised signer"

    if not str(card.get("review_date") or "").strip() or \
            str(card.get("review_date")).strip() == PENDING:
        return False, "review_date is not set"

    pending = [f for f in schema["clinical"] if _is_pending(card.get(f))]
    if pending:
        return False, (f"signoff is true but clinical field(s) still empty or "
                       f"{PENDING}: {', '.join(pending)}")

    if not card.get("references"):
        return False, "references are empty"

    return True, ""


def servable_cards() -> dict:
    """{family: [card_id, ...]} for everything live right now.

    Partial deployment is the normal state: this is what /status and the
    worksheet read to say which cards are carrying traffic.
    """
    out = {}
    for family, cards in FAMILIES.items():
        out[family] = sorted(cid for cid, c in cards.items()
                             if card_is_servable(c, family)[0])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# IDEAL BODY WEIGHT
# ─────────────────────────────────────────────────────────────────────────────

_DEVINE_BASE = {"male": 50.0, "female": 45.5}
_DEVINE_PER_INCH = 2.3
_DEVINE_BASE_INCHES = 60.0


def ideal_body_weight_kg(height_cm: Optional[float], sex: Optional[str]) -> Optional[float]:
    """Devine IBW, or None when the inputs are not both present.

    None is a real answer here and the caller must handle it: the alternative
    — defaulting a sex or a height — puts an invented number under every
    breath the ventilator delivers.
    """
    if height_cm is None or sex not in _DEVINE_BASE:
        return None
    inches = float(height_cm) / 2.54
    over = max(0.0, inches - _DEVINE_BASE_INCHES)
    return round(_DEVINE_BASE[sex] + _DEVINE_PER_INCH * over, 1)


def dosing_basis(ctx) -> dict:
    """What tidal volume should be computed against, and how confident that is.

    Returns {basis, weight_kg, height_cm, sex, missing[]}:
        basis "ibw"      height and sex known — the correct anchor
        basis "actual"   confirmed weight only — usable WITH the card's caveat
        basis None       nothing confirmed to anchor on

    The F-1 rule is not re-implemented, it is reused: only
    confirmed_weight_kg counts. A hedged weight sits in estimated_weight_kg and
    cannot anchor a tidal volume any more than it can anchor a drug dose.
    """
    height = None
    reading = (getattr(ctx, "vitals", None) or {}).get("height")
    if reading is not None:
        height = getattr(reading, "value", None)
    sex = getattr(ctx, "sex", None)
    confirmed = getattr(ctx, "confirmed_weight_kg", None)

    missing = []
    if height is None:
        missing.append("height")
    if sex not in _DEVINE_BASE:
        missing.append("sex")

    ibw = ideal_body_weight_kg(height, sex)
    if ibw is not None:
        return {"basis": "ibw", "weight_kg": ibw, "height_cm": height,
                "sex": sex, "missing": []}
    if confirmed is not None:
        return {"basis": "actual", "weight_kg": float(confirmed),
                "height_cm": height, "sex": sex, "missing": missing}
    return {"basis": None, "weight_kg": None, "height_cm": height,
            "sex": sex, "missing": missing + (["weight"] if confirmed is None else [])}


# ─────────────────────────────────────────────────────────────────────────────
# DISPATCH
# ─────────────────────────────────────────────────────────────────────────────
#
# Word-anchored throughout. This repo is at five substring specimens — the F-2
# alias table, FIXED_PREP_TERMS, the vitals labels, _SHOCK_WORDS and the F-3
# AMS list — and a sixth in a module that decides ventilator settings is not a
# specimen anyone wants to write up.

def _anchored(terms) -> re.Pattern:
    return re.compile(r'(?<!\w)(?:' + "|".join(re.escape(t) for t in terms) + r')(?!\w)')


# Vent context. A device name alone is not enough to route: "T1" is a thoracic
# level, a trauma category and a Hamilton ventilator, and only one of those
# wants a device card.
_VENT_CONTEXT = _anchored([
    "vent", "vents", "ventilator", "ventilated", "ventilation", "on the vent",
    "peep", "fio2", "tidal volume", "vt", "plateau", "pplat", "peak pressure",
    "intubated", "ett", "tube", "bagging", "bvm", "circuit", "settings",
    "mode", "simv", "ac/vc", "prvc", "pressure control", "volume control",
])

# Alarms and decompensation. Priority over settings: a patient deteriorating
# on a ventilator is not a question about what the settings should have been.
_TROUBLE_SIGNALS = _anchored([
    "alarm", "alarming", "alarms", "high pressure", "low pressure",
    "peak pressure alarm", "desat", "desatting", "desaturating",
    "fighting the vent", "bucking", "breath stacking", "stacking",
    "auto-peep", "autopeep", "air trapping", "disconnect", "disconnected",
    "leak", "leaking", "crashing", "decompensating", "decompensated",
    "sudden", "arrest", "obstructed", "kinked", "plugged", "not ventilating",
    "won't ventilate", "cannot ventilate", "hypoxic", "cyanotic",
])

# A request for settings that names no physiology. These phrases used to sit in
# lung_protective_baseline's own applies_when, which made that card the first
# match for almost every real vent question and shadowed the four specific
# cards behind it — a DKA query reached the ARDS-pattern card, which is exactly
# the F-12 failure with the roles reversed. They live here now, and they lead to
# a QUESTION rather than to a default: the physiology decides the settings, and
# guessing which one is not a thing a ventilator card gets to do.
_SETTINGS_REQUEST = _anchored([
    "vent settings", "ventilator settings", "initial settings",
    "vent setup", "settings for the vent", "settings on the vent",
    "set the vent", "setting the vent", "set up the vent", "start the vent",
    "vent the patient", "mechanical ventilation", "what settings",
    "which settings", "what vent settings",
])

# Device aliases. Deliberately short lists — every extra alias is a collision
# waiting to route a clinical query into a hardware manual.
_DEVICE_ALIASES = {
    "hamilton_t1": ("hamilton", "hamilton t1", "t1"),
    "zoll_emv_plus_731": ("zoll", "emv", "emv+", "emv plus", "731", "eagle"),
    "ltv_1200_family": ("ltv", "ltv 1200", "1200", "ltv1200"),
    "ventway_sparrow": ("ventway", "sparrow"),
}

# Aliases that are ordinary clinical or numeric tokens on their own. These
# require vent context before they can name a device — the same
# context-dependent treatment F-6 gave "k", "hs" and "cold" in the router.
_AMBIGUOUS_DEVICE_ALIASES = frozenset({"t1", "1200", "731", "eagle"})

_DEVICE_PATTERNS = {
    device_id: _anchored(sorted(aliases, key=len, reverse=True))
    for device_id, aliases in _DEVICE_ALIASES.items()
}
_UNAMBIGUOUS_DEVICE_PATTERNS = {
    device_id: _anchored(sorted((a for a in aliases
                                 if a not in _AMBIGUOUS_DEVICE_ALIASES),
                                key=len, reverse=True))
    for device_id, aliases in _DEVICE_ALIASES.items()
    if any(a not in _AMBIGUOUS_DEVICE_ALIASES for a in aliases)
}


def has_vent_context(text: str) -> bool:
    return bool(_VENT_CONTEXT.search((text or "").lower()))


def looks_like_vent_trouble(text: str) -> bool:
    """Alarm or decompensation language, in a ventilator context."""
    q = (text or "").lower()
    return bool(_TROUBLE_SIGNALS.search(q)) and has_vent_context(q)


def named_device(text: str) -> Optional[str]:
    """The device this query names, or None.

    An ambiguous alias ("T1", "731", "1200") only names a device when vent
    context is present. An unambiguous one ("hamilton", "ventway") stands on
    its own.
    """
    q = (text or "").lower()
    for device_id, pattern in _UNAMBIGUOUS_DEVICE_PATTERNS.items():
        if pattern.search(q):
            return device_id
    if has_vent_context(q):
        for device_id, pattern in _DEVICE_PATTERNS.items():
            if pattern.search(q):
                return device_id
    return None


def _match_applies_when(card: dict, text: str) -> bool:
    """Whether a card's own signal list matches.

    `applies_when` is authored data, so it is matched with the same word
    anchoring as everything else rather than trusted as a regex — a card file
    must not be able to inject a pattern into the dispatcher.
    """
    signals = card.get("applies_when") or []
    signals = [s for s in signals if isinstance(s, str) and s.strip()
               and s.strip() != PENDING]
    if not signals:
        return False
    return bool(_anchored(signals).search((text or "").lower()))


def dispatch(text: str, ctx=None) -> Optional[tuple]:
    """(family, card) for this query, or None to fall through.

    Priority is troubleshooting > device > physiology, and it is not a
    preference: a ventilator alarming on a patient is a different question
    from what the settings should be, and answering the second when asked the
    first is the S-4 failure with the roles reversed.

    Returns None — meaning "not mine, carry on" — for any query this module
    does not own AND for any card that is not signed off. The caller cannot
    tell those apart, which is deliberate: a pending card must be
    indistinguishable from an absent one.
    """
    q = (text or "").lower()
    if not q.strip():
        return None

    if looks_like_vent_trouble(q):
        for card_id, card in TROUBLESHOOTING.items():
            if _match_applies_when(card, q) and card_is_servable(card, "troubleshooting")[0]:
                return "troubleshooting", card

    device_id = named_device(q)
    if device_id:
        # Device + alarm went to troubleshooting above; reaching here means no
        # troubleshooting card claimed it, so the device card answers and
        # carries the alarm table.
        card = DEVICES.get(device_id)
        if card and card_is_servable(card, "device")[0]:
            return "device", card

    if has_vent_context(q):
        for card_id, card in PHYSIOLOGY.items():
            if _match_applies_when(card, q) and card_is_servable(card, "physiology")[0]:
                return "physiology", card

    return None


def needs_physiology_choice(text: str) -> bool:
    """A settings question in a vent context that names no physiology."""
    q = (text or "").lower()
    if not has_vent_context(q) or not _SETTINGS_REQUEST.search(q):
        return False
    return not any(_match_applies_when(c, q) for c in PHYSIOLOGY.values())


def physiology_gate(text: str) -> Optional[str]:
    """The question to ask instead of guessing a physiology. None to stay quiet.

    Silent unless at least one physiology card is actually live. A question is
    only worth a turn if answering it leads somewhere: with nothing signed off,
    asking "which physiology?" would take a turn and then have nothing to serve,
    while today that same query falls through to a retrieval that already
    answers the TBI phrasings correctly. Blocking working behaviour to ask a
    question we cannot act on would be F-12 in a third costume.

    Lists only the cards that can answer, so the options are never a menu of
    things that are still dark.
    """
    if not needs_physiology_choice(text):
        return None
    live = [c for c in PHYSIOLOGY.values()
            if card_is_servable(c, "physiology")[0]]
    if not live:
        return None
    options = " / ".join(c.get("title") or c["id"] for c in live)
    return f"Which physiology? {options}."


def cross_referenced_device(text: str) -> Optional[dict]:
    """A servable device card named alongside an alarm, for the cross-ref line."""
    device_id = named_device(text)
    if not device_id:
        return None
    card = DEVICES.get(device_id)
    if card and card_is_servable(card, "device")[0]:
        return card
    return None


# ─────────────────────────────────────────────────────────────────────────────
# RENDERING
# ─────────────────────────────────────────────────────────────────────────────
#
# The voice-first action register, mirroring the existing deterministic cards.
# Every line of clinical text below comes OUT OF THE CARD. This module supplies
# headings, ordering and arithmetic and nothing else.

DISCLAIMER = "Guideline-based support only. Not a substitute for clinical judgment."


def source_line(card: dict, family: str) -> str:
    """The third provenance label. JTS corpus / general reference / AUTHORED CARD.

    A card answer is neither retrieved nor general knowledge: a named clinician
    wrote it and put a date on it, and the medic reading it should be able to
    see whose judgement they are acting on.
    """
    refs = ", ".join(str(r) for r in (card.get("references") or []))
    line = (f"**SOURCE**: EdgeCDSS clinical card — reviewed "
            f"{card.get('reviewed_by')}, {card.get('review_date')}")
    if family == "device":
        manual = card.get("manual_reference") or {}
        line += (f" — summarized from operator's manual rev "
                 f"{manual.get('revision')}, verified {manual.get('verified_date')}")
    if refs:
        line += f" — refs: {refs}"
    return line


def _bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items or [])


def _numbered(items) -> str:
    return "\n".join(f"{n}. {i}" for n, i in enumerate(items or [], 1))


def render_physiology(card: dict, basis: dict) -> str:
    """SETTINGS / TITRATE / WATCH FOR / EVAC IF / TLDR.

    The tidal volume LINE is assembled here; the mL/kg FIGURE is the card's.
    When the card gives a figure and the engine has a weight to anchor it to,
    the medic gets millilitres and does no arithmetic — the zero-math rule the
    rest of the system already keeps for drug doses.
    """
    s = card.get("initial_settings") or {}
    out = [f"**{card.get('title', card.get('id', 'VENTILATOR')).upper()}**", ""]

    settings = [f"Mode: {s.get('mode')}"]
    vt = s.get("vt_ml_per_kg_ibw")
    settings.append(_vt_line(vt, basis))
    settings += [f"Rate: {s.get('rate_strategy')}",
                 f"PEEP: {s.get('peep')}",
                 f"FiO2: {s.get('fio2')}"]
    out += ["**SETTINGS**", _bullets(settings), ""]

    out += ["**TITRATE**", _bullets(_as_list(card.get("titrate_on"))), ""]
    out += ["**WATCH FOR**", _bullets(_as_list(card.get("watch_for"))), ""]
    out += ["**EVAC IF**", _bullets(_as_list(card.get("evac_if"))), ""]

    if basis.get("basis") == "actual":
        # The caveat text is the CARD's, not this module's. The engine decides
        # only WHEN it is shown.
        caveat = card.get("actual_weight_caveat") or card.get("escape_hatch")
        out += [f"**CAVEAT**\n- {caveat}", ""]

    tldr = card.get("tldr")
    if tldr and tldr != PENDING:
        out += ["**TLDR**", f"- {tldr}", ""]

    out += [f"**ASSUMES**: {card.get('escape_hatch')}", ""]
    out += [source_line(card, "physiology"), "", DISCLAIMER]
    return "\n".join(out)


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value else []


def _vt_line(vt_ml_per_kg, basis: dict) -> str:
    """The one place engine arithmetic meets card content."""
    if vt_ml_per_kg in (None, PENDING, ""):
        return "VT: —"
    weight = basis.get("weight_kg")
    if weight is None:
        return f"VT: {vt_ml_per_kg} mL/kg IBW — state height and sex, or weight, for millilitres"
    try:
        low, high = _range_of(vt_ml_per_kg)
        anchor = ("IBW %.1f kg" % weight if basis.get("basis") == "ibw"
                  else "ACTUAL weight %.1f kg — not IBW" % weight)
        if low == high:
            return f"VT: {vt_ml_per_kg} mL/kg = {round(low * weight)} mL ({anchor})"
        return (f"VT: {vt_ml_per_kg} mL/kg = {round(low * weight)}-{round(high * weight)} mL "
                f"({anchor})")
    except (TypeError, ValueError):
        return f"VT: {vt_ml_per_kg} mL/kg ({basis.get('basis')})"


def _range_of(value) -> tuple:
    """'6-8' -> (6.0, 8.0); '6' -> (6.0, 6.0). Card content, parsed not trusted."""
    text = str(value).strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)), float(m.group(2))
    return float(text), float(text)


def render_troubleshooting(card: dict, device_card: Optional[dict] = None) -> str:
    """DO NOW leading, because the patient is deteriorating while this is read."""
    steps = card.get("steps") or []
    lines = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        lines.append(f"{step.get('check')} → if {step.get('finding')}: "
                     f"{step.get('action')}")
    out = [f"**{card.get('title', card.get('id', 'VENT PROBLEM')).upper()}**", "",
           "**DO NOW**", _numbered(lines), ""]
    if card.get("watch_for"):
        out += ["**WATCH FOR**", _bullets(_as_list(card.get("watch_for"))), ""]
    if card.get("evac_if"):
        out += ["**EVAC IF**", _bullets(_as_list(card.get("evac_if"))), ""]
    if card.get("tldr") and card["tldr"] != PENDING:
        out += ["**TLDR**", f"- {card['tldr']}", ""]
    if device_card is not None:
        out += [f"**ON THIS DEVICE**: see the {device_card.get('title')} card "
                f"for alarm text and where each control lives.", ""]
    out += [f"**ASSUMES**: {card.get('escape_hatch')}", ""] if card.get("escape_hatch") else []
    out += [source_line(card, "troubleshooting"), "", DISCLAIMER]
    return "\n".join(out)


def render_device(card: dict) -> str:
    """Startup, where the settings live, alarms, quirks.

    Every field is the owner's authored summary. The source line names the
    manual revision it was summarised from, which is the visible half of the
    copyright rule; DEVICE_FIELD_MAX_CHARS and lint_device_cards() are the
    structural half.
    """
    out = [f"**{card.get('title', card.get('id', 'DEVICE')).upper()} — DEVICE CARD**", ""]
    out += ["**STARTUP**", _numbered(_as_list(card.get("startup_sequence"))), ""]

    pmap = card.get("parameter_map") or {}
    if isinstance(pmap, dict) and pmap:
        out += ["**WHERE THE SETTINGS LIVE**",
                _bullets(f"{k}: {v}" for k, v in pmap.items()), ""]

    alarms = card.get("alarm_table") or []
    rows = [f"\"{a.get('display')}\" → {a.get('meaning')} → {a.get('first_action')}"
            for a in alarms if isinstance(a, dict)]
    if rows:
        out += ["**ALARMS**", _bullets(rows), ""]

    if card.get("quirks"):
        out += ["**QUIRKS**", _bullets(_as_list(card.get("quirks"))), ""]
    if card.get("crosswalk"):
        out += ["**ENTERING A SETTINGS CARD ON THIS DEVICE**",
                _bullets(_as_list(card.get("crosswalk"))), ""]
    out += [source_line(card, "device"), "", DISCLAIMER]
    return "\n".join(out)


def render(family: str, card: dict, ctx=None, query: str = "") -> str:
    if family == "physiology":
        return render_physiology(card, dosing_basis(ctx))
    if family == "troubleshooting":
        return render_troubleshooting(card, cross_referenced_device(query))
    return render_device(card)


def follow_up_ask(family: str, basis: dict) -> Optional[str]:
    """The non-blocking follow-up, appended after the card.

    Non-blocking is the whole point: the settings are served, and the ask is
    for what would make the NEXT answer better. Blocking here would reproduce
    F-12 — a vent question that returns something other than vent settings.
    """
    if family != "physiology":
        return None
    missing = basis.get("missing") or []
    if not missing or basis.get("basis") == "ibw":
        return None
    if "weight" in missing:
        return None          # the dose pre-gate already owns a missing weight
    return (f"Send {' and '.join(missing)} and I will recompute tidal volume "
            f"on ideal body weight.")


# ─────────────────────────────────────────────────────────────────────────────
# COPYRIGHT LINT
# ─────────────────────────────────────────────────────────────────────────────

def lint_device_cards(manual_texts: Optional[dict] = None) -> list:
    """Structural enforcement of the copyright rule. Returns a list of problems.

    Two checks:

      1. No device-card content field may exceed DEVICE_FIELD_MAX_CHARS. A
         summary does not run to paragraphs, and length is the cheapest proxy
         for "this stopped being a summary".

      2. If manual text is ever present — it must NOT be committed, and
         `.manual.` is in .gitignore for that reason — no card field may share
         a long verbatim run with it.

    The second check takes its corpus as an argument rather than reading the
    filesystem, so the test can exercise it without a manual ever existing in
    the repo.
    """
    problems = []
    for card_id, card in DEVICES.items():
        for field, value in card.items():
            if field in _PROVENANCE_FIELDS or field in ("id", "title", "applies_when"):
                continue
            for text in _walk_strings(value):
                if len(text) > DEVICE_FIELD_MAX_CHARS:
                    problems.append(
                        f"{card_id}.{field}: {len(text)} chars exceeds the "
                        f"{DEVICE_FIELD_MAX_CHARS}-char summary limit — device "
                        f"cards are authored summaries, not manual text")
                for manual_name, manual_text in (manual_texts or {}).items():
                    run = _longest_shared_run(text, manual_text)
                    if len(run) >= 60:
                        problems.append(
                            f"{card_id}.{field} shares a {len(run)}-character "
                            f"verbatim run with {manual_name}: {run[:60]!r}")
    return problems


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk_strings(v)


def _longest_shared_run(a: str, b: str) -> str:
    """Longest common substring, normalised for whitespace and case.

    Quadratic, and that is fine: it runs over a handful of short card fields
    in a test, never in the request path.
    """
    import difflib
    a_n = " ".join((a or "").lower().split())
    b_n = " ".join((b or "").lower().split())
    if not a_n or not b_n:
        return ""
    match = difflib.SequenceMatcher(None, a_n, b_n, autojunk=False) \
        .find_longest_match(0, len(a_n), 0, len(b_n))
    return a_n[match.a:match.a + match.size]
