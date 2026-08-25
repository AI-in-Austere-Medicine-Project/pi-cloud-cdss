"""
EdgeCDSS — drug dose-contract engine.

Sibling to vent_module.py, same doctrine, same fence. One deterministic tier:
no model call ever produces a dose. This closes the gap the v4.3 discovery run
found — 4 of ~16 drugs that actually received dose queries had a contract, and
the other 12 fell through to the generator's own pharmacology.

    drug_contracts.json    drug -> forms, routes, aliases, dose_entries[]

THE CLINICAL FENCE IS STRUCTURAL, NOT ADVISORY
──────────────────────────────────────────────
This module is engine, schema, alias resolution and lint. It contains no doses,
no concentrations and no maximums; every clinical value lives in the JSON, and
the JSON ships with every dose_entry unsigned.

`signoff` is the gate, and it is PER DOSE ENTRY, not per drug. An entry with
signoff false — or absent, or malformed, or still carrying a PENDING /
NEEDS_MANUAL_ENTRY sentinel in a required clinical field — CANNOT be served:
it is filtered out before the contract is built, and a drug with no servable
entries produces no ALLOWED_DOSES at all, which lands the query on exactly the
empty-contract fallback it had before this module existed. There is no flag, no
override and no debug path that serves an unsigned entry, because the failure
mode of a half-authored dose is a patient who receives it.

Entry-level granularity is deliberate. "Ketamine analgesia IV" and "ketamine
RSI induction" are different clinical claims with different evidence; the owner
signs one without being forced to sign the other, and partial deployment is the
normal state rather than a migration step.

TWO SENTINELS, ONE MEANING: NOT YET AUTHORED
────────────────────────────────────────────
    PENDING_CLINICAL_SIGNOFF   nobody has filled this in yet
    NEEDS_MANUAL_ENTRY         a source was read and the value could NOT be
                               extracted safely — the figure was an image, the
                               prose was ambiguous, or the source was
                               unreachable. The reason rides along in
                               `extraction_notes`.

They gate identically. The distinction exists so the worksheet can tell the
owner "nobody has started this" apart from "a machine tried and refused to
guess", which are different pieces of work.

A null `max_single` / `max_cumulative` is NOT a sentinel. It means the cited
source states no maximum for that entry, which is a fact about the source and
is allowed to be signed.

ALIASES ARE WORD-ANCHORED, AND MAY NOT SHADOW A REAL DRUG
─────────────────────────────────────────────────────────
`vitamin k` was mapped to ketamine as a dictation-mangling alias. Vitamin K is
a real drug with its own indication, so "vitamin K dose for warfarin reversal"
built a ketamine contract. That is the fifth specimen of the substring/shadow
collision class in this codebase, so the fix here is structural rather than a
patch to one string:

    1. every alias match is word-anchored — never `alias in query`
    2. lint_alias_collisions() REFUSES any alias that is the generic_name or
       an alias of a DIFFERENT contracted drug

Rule 2 is what actually kills the class. A mangled-dictation alias is only
admissible while it collides with nothing; the moment the collided-with drug
becomes real, the alias loses and the lint says so at load.
"""

import json
import os
import pathlib
import re
from typing import Optional

_DIR = pathlib.Path(__file__).parent

PENDING = "PENDING_CLINICAL_SIGNOFF"
NEEDS_MANUAL = "NEEDS_MANUAL_ENTRY"
SENTINELS = (PENDING, NEEDS_MANUAL)

# Same signer list as the vent cards, read from the same variable, because a
# second reviewer should be one edit in one place rather than two.
SIGNOFF_AUTHORS = tuple(
    a.strip() for a in os.getenv("CDSS_CARD_AUTHORS",
                                 "clinician,AI-AIM").split(",")
    if a.strip())

# The four drugs that had hardcoded calculators before this module existed.
# Their legacy calculators STAY LIVE until the owner re-signs the migrated
# entries, because the build request said preserve current behaviour exactly
# and said sign nothing, and those two together mean the model cannot be the
# serving path for these four yet. Every other drug serves from the model or
# not at all. See openai_client.build_allowed_doses().
LEGACY_CALCULATOR_DRUGS = ("ketamine", "rocuronium", "succinylcholine",
                           "lorazepam")


class ContractError(ValueError):
    """A contract file that cannot be trusted. Raised at load, never at serve."""


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

_DRUG_REQUIRED = ("generic_name", "aliases", "drug_class", "forms", "routes",
                  "dose_entries")

# Fields a dose_entry must carry at all.
_ENTRY_REQUIRED = ("indication", "population", "route", "dose_range",
                   "max_single", "max_cumulative", "contraindications",
                   "cautions", "sources", "signoff", "reviewed_by",
                   "review_date", "version")

# Of those, the ones that must be non-empty and sentinel-free before the entry
# can be served. max_single / max_cumulative are excluded on purpose: null is a
# real, signable answer meaning "the source states no maximum".
_ENTRY_CLINICAL = ("indication", "population", "route", "dose_range", "sources")

_DOSE_RANGE_KEYS = ("min", "max", "units", "per_kg")

_SOURCE_KEYS = ("citation", "tier", "url", "retrieved_date")

VALID_POPULATIONS = ("adult", "peds", "weight-based", "adult|peds")


def _load(filename: str = "drug_contracts.json") -> dict:
    path = _DIR / filename
    try:
        with open(path) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  {filename} not found — no drug dose contracts are available.")
        return {}
    except (json.JSONDecodeError, OSError) as e:
        # Same rule as vent_cards.json and providers.json: a broken config
        # degrades to the feature being absent, loudly, never to a server that
        # will not boot.
        print(f"⚠️  {filename} is unreadable ({e}) — no drug dose contracts "
              f"are available.")
        return {}
    return {d["generic_name"]: d for d in raw.get("drugs", [])
            if isinstance(d, dict) and d.get("generic_name")}


DRUGS = _load()


def tropical_priority_drugs() -> list:
    """The austere/tropical deployment subset, in file order.

    A separate group rather than a separate file: same fence, same schema, same
    signing path. What makes them a group is that the deployment's actual
    disease burden is not what NASEMSO covers, so these are the entries whose
    signing order is driven by where the patients are rather than by query
    traffic.
    """
    return [name for name, d in DRUGS.items() if d.get("tropical_priority")]


# ─────────────────────────────────────────────────────────────────────────────
# THE FENCE
# ─────────────────────────────────────────────────────────────────────────────

def _is_pending(value) -> bool:
    """Whether a value is unauthored, at any depth.

    None is pending here only for strings/containers reached recursively; the
    callers that allow a meaningful null (max_single) never route through this.
    """
    if isinstance(value, str):
        return value.strip() in SENTINELS or not value.strip()
    if isinstance(value, dict):
        return not value or any(_is_pending(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return not value or any(_is_pending(v) for v in value)
    if value is None:
        return True
    return False


def has_sentinel(value) -> bool:
    """Whether a sentinel STRING appears anywhere in this value.

    Distinct from _is_pending: an empty list is pending but carries no
    sentinel, and a signed entry is allowed neither.
    """
    return any(s in json.dumps(value) for s in SENTINELS)


def _dose_range_ok(dr) -> tuple:
    if not isinstance(dr, dict):
        return False, "dose_range is not an object"
    missing = [k for k in _DOSE_RANGE_KEYS if k not in dr]
    if missing:
        return False, f"dose_range missing {', '.join(missing)}"
    if _is_pending(dr.get("units")) or _is_pending(dr.get("min")):
        return False, "dose_range is not authored"
    if not isinstance(dr.get("per_kg"), bool):
        return False, "dose_range.per_kg must be a boolean"
    for k in ("min", "max"):
        v = dr.get(k)
        if v is not None and not isinstance(v, (int, float)):
            return False, f"dose_range.{k} must be a number or null"
    lo, hi = dr.get("min"), dr.get("max")
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi < lo:
        return False, "dose_range.max is below dose_range.min"
    return True, ""


def _sources_ok(sources) -> tuple:
    if not isinstance(sources, list) or not sources:
        return False, "sources are empty"
    for s in sources:
        if not isinstance(s, dict):
            return False, "a source is not an object"
        missing = [k for k in _SOURCE_KEYS if k not in s]
        if missing:
            return False, f"a source is missing {', '.join(missing)}"
        if _is_pending(s.get("citation")) or _is_pending(s.get("tier")):
            return False, "a source is not authored"
    return True, ""


def entry_is_servable(entry: dict, drug: Optional[dict] = None) -> tuple:
    """(servable, reason). The single gate every serve path goes through.

    Returns a REASON rather than a bare bool for the same argument the vent
    cards make: "why is this dose not live" is the question the worksheet
    exists to answer, and an operator who cannot get an answer will guess.
    """
    if not entry or not isinstance(entry, dict):
        return False, "no such entry"

    missing = [f for f in _ENTRY_REQUIRED if f not in entry]
    if missing:
        return False, f"missing field(s): {', '.join(sorted(missing))}"

    if entry.get("signoff") is not True:
        return False, "signoff is not true"

    reviewer = str(entry.get("reviewed_by") or "").strip()
    if reviewer not in SIGNOFF_AUTHORS:
        return False, f"reviewed_by {reviewer!r} is not an authorised signer"

    review_date = str(entry.get("review_date") or "").strip()
    if not review_date or review_date in SENTINELS:
        return False, "review_date is not set"

    pending = [f for f in _ENTRY_CLINICAL if _is_pending(entry.get(f))]
    if pending:
        return False, (f"signoff is true but clinical field(s) still empty or "
                       f"sentinel: {', '.join(pending)}")

    # A sentinel ANYWHERE in a signed entry is a refusal, not just in the
    # fields the schema calls clinical. A cautions[] line that still reads
    # NEEDS_MANUAL_ENTRY is text a medic would be shown.
    if has_sentinel(entry):
        leaked = sorted(k for k, v in entry.items() if has_sentinel(v))
        return False, (f"signoff is true but a sentinel survives in: "
                       f"{', '.join(leaked)}")

    ok, why = _dose_range_ok(entry.get("dose_range"))
    if not ok:
        return False, why

    ok, why = _sources_ok(entry.get("sources"))
    if not ok:
        return False, why

    # Populate ONLY from the two approved sources. Tier 0 is the migration
    # carrier for the four pre-contract hardcodes; it is not clinical evidence,
    # so an entry that cites nothing but tier 0 cannot be signed no matter who
    # signs it. This is what stops the migration from laundering an unsourced
    # number into a served dose.
    # A MIGRATED_UNSOURCED entry is one whose DOSE came from the pre-contract
    # hardcode and which no approved source corroborates. Attaching a tier-1
    # citation that supports some OTHER field — a contraindication list, say —
    # must not make the dose signable: the tier check cannot tell which field a
    # source backs, so the flag carries that fact instead. Clearing the flag is
    # how someone asserts the dose itself is now sourced.
    if "MIGRATED_UNSOURCED" in (entry.get("flags") or []):
        return False, ("flagged MIGRATED_UNSOURCED: the DOSE came from the "
                       "pre-contract hardcode and no approved source "
                       "corroborates it. A citation supporting another field "
                       "does not change that — clear the flag only when the "
                       "dose itself has a tier 1 or tier 2 source")

    tiers = {s.get("tier") for s in entry["sources"]}
    if not tiers & {1, 2}:
        return False, ("no approved source: every source is tier "
                       f"{sorted(t for t in tiers if t is not None)} and a "
                       "signed entry needs at least one tier 1 or tier 2 citation")

    # Unit sanity. Refused rather than flagged: a thousandfold dose is not a
    # thing to warn about underneath and serve anyway.
    r = resolve_dose(entry, _LINT_WEIGHT_KG)
    if r["kind"] == UNKNOWN and r["reason"]:
        return False, f"dose units unusable: {r['reason']}"
    if entry.get("_unit_error"):
        return False, f"dose magnitude refused: {entry['_unit_error']}"

    if entry.get("population") not in VALID_POPULATIONS:
        return False, f"population {entry.get('population')!r} is not one of " \
                      f"{', '.join(VALID_POPULATIONS)}"

    # A conflict the owner signed through must say how it was adjudicated.
    # Signing one of two conflicting entries IS the adjudication; recording it
    # is what stops the next reader from re-opening the same question.
    if "SOURCE_CONFLICT" in (entry.get("flags") or []):
        adj = str(entry.get("adjudication") or "").strip()
        if not adj or adj in SENTINELS:
            return False, ("entry is flagged SOURCE_CONFLICT and signed but "
                           "carries no adjudication note")

    return True, ""


def servable_entries() -> dict:
    """{generic_name: [entry, ...]} for everything live right now.

    Partial deployment is the normal state: this is what the worksheet and
    /status read to say which doses are carrying traffic.
    """
    out = {}
    for name, drug in DRUGS.items():
        live = [e for e in drug.get("dose_entries", [])
                if entry_is_servable(e, drug)[0]]
        if live:
            out[name] = live
    return out


def contract_status() -> dict:
    """{generic_name: {"live": n, "total": n, "reasons": [...]}} for reporting."""
    out = {}
    for name, drug in DRUGS.items():
        entries = drug.get("dose_entries", [])
        reasons = []
        live = 0
        for e in entries:
            ok, why = entry_is_servable(e, drug)
            if ok:
                live += 1
            else:
                reasons.append((e.get("indication"), e.get("route"), why))
        out[name] = {"live": live, "total": len(entries), "reasons": reasons,
                     "tropical": bool(drug.get("tropical_priority"))}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ALIAS RESOLUTION — WORD-ANCHORED, NON-SHADOWING
# ─────────────────────────────────────────────────────────────────────────────

# Anything that separates two words of a drug name in the wild: whitespace, the
# "+" of a combination product, a hyphen, a slash, a comma. Normalising these
# is why "artemether + lumefantrine", "artemether-lumefantrine" and
# "artemether lumefantrine" are one term rather than three near-misses.
_SEP = r'[\s+/,-]+'


def _term_pattern(term: str) -> str:
    """Word-anchored regex for a drug term, separator-agnostic."""
    tokens = [t for t in re.split(r'[^0-9a-z]+', term.lower()) if t]
    if not tokens:
        return r'(?!)'          # matches nothing
    return r'\b' + _SEP.join(re.escape(t) for t in tokens) + r'\b'


def _has_word(text: str, term: str) -> bool:
    """Word-boundary match — 'roc' matches "give roc" but not "rock".

    Multi-word terms ("vitamin k", "artemether + lumefantrine") anchor on the
    ends of the whole phrase, with the internal separators normalised, so a
    term can never fire on a fragment of a longer word.
    """
    return re.search(_term_pattern(term), text.lower()) is not None


def alias_index() -> dict:
    """{alias_or_generic: generic_name}. Built fresh so a lint failure cannot
    be cached into the serving path."""
    idx = {}
    for name, drug in DRUGS.items():
        idx[name.lower()] = name
        for a in drug.get("aliases", []):
            if isinstance(a, str) and a.strip():
                idx.setdefault(a.strip().lower(), name)
    return idx


def lint_alias_collisions() -> list:
    """Every way one drug's alias can shadow another drug. Empty list = clean.

    THIS IS THE CLASS FIX. Checked at load and asserted in the test suite, so a
    future mangled-dictation alias cannot quietly eat a real drug's name the
    way `vitamin k -> ketamine` ate vitamin K's.
    """
    problems = []
    generics = {n.lower(): n for n in DRUGS}

    # An alias may not be another drug's generic name.
    for name, drug in DRUGS.items():
        for a in drug.get("aliases", []):
            al = str(a).strip().lower()
            if al in generics and generics[al] != name:
                problems.append(
                    f"{name!r} claims alias {a!r}, which is the generic name of "
                    f"{generics[al]!r} — an alias may never shadow a real drug")

    # Two drugs may not claim the same alias.
    owner = {}
    for name, drug in DRUGS.items():
        for a in drug.get("aliases", []):
            al = str(a).strip().lower()
            if al in owner and owner[al] != name:
                problems.append(
                    f"alias {a!r} is claimed by both {owner[al]!r} and {name!r}")
            owner.setdefault(al, name)

    # An alias may not be a strict substring-with-word-boundaries of another
    # drug's generic name in a way that would fire on it — belt and braces for
    # the class, since _has_word already prevents the bare-substring case.
    for al, name in owner.items():
        for other in DRUGS:
            if other == name:
                continue
            if _has_word(other.lower(), al):
                problems.append(
                    f"alias {al!r} (of {name!r}) word-matches inside the "
                    f"generic name {other!r}")

    return problems


ALIAS_COLLISIONS = lint_alias_collisions()
if ALIAS_COLLISIONS:
    for _p in ALIAS_COLLISIONS:
        print(f"⚠️  drug_contracts alias lint: {_p}")


def lint_generic_name_overlaps() -> list:
    """Generic names that contain another generic name as a word.

    Informational, NOT an error: a combination product legitimately contains
    its components' names ("artemether + lumefantrine" contains "artemether").
    Kept separate from lint_alias_collisions() because conflating the two would
    either fail the build on a legal combination or teach the team to ignore
    the lint that catches the real shadows. resolve_drugs() handles these by
    longest-match-wins.
    """
    out = []
    for a in DRUGS:
        for b in DRUGS:
            if a != b and _has_word(a.lower(), b.lower()):
                out.append(f"{a!r} contains the generic name {b!r}")
    return out


def resolve_drugs(query: str) -> list:
    """Generic names named in the query, word-anchored, longest match wins.

    Longest-match-wins is what keeps "artemether + lumefantrine dose" from also
    resolving bare artemether: the longer term consumes the span, so a
    combination product is never shadowed by one of its own components.
    Order is file order, so the contract is deterministic for a given query.
    """
    q = (query or "").lower()
    idx = alias_index()
    matched = []
    for term, generic in idx.items():
        m = re.search(_term_pattern(term), q)
        if m:
            matched.append((m.start(), m.end(), term, generic))

    hits = set()
    for start, end, term, generic in matched:
        # Drop a match wholly contained inside a longer match.
        if any(s2 <= start and end <= e2 and (e2 - s2) > (end - start)
               for s2, e2, _, _ in matched):
            continue
        hits.add(generic)
    return [n for n in DRUGS if n in hits]


# ─────────────────────────────────────────────────────────────────────────────
# UNITS
# ─────────────────────────────────────────────────────────────────────────────
#
# The dose builder used to do `dose_mg = value * weight if per_kg else value`
# and call the result milligrams whatever the entry actually said. So dextrose
# "25 g" became 25 mg and epinephrine "10 mcg" became 10 mg — a thousandfold
# error in both directions, and the volume audit could not see it: that check
# verifies volume against the STATED milligrams, so a wrongly-parsed dose that
# is internally consistent passes it cleanly.
#
# Two rules here, and the second matters as much as the first:
#
#   1. every unit family the contracts actually use is converted explicitly;
#   2. anything NOT on this list fails closed. Defaulting to milligrams is what
#      caused the bug, so there is no default.
#
# The SOURCE unit survives conversion. A medic reads "25 g" because that is what
# the guideline says; the milligram figure exists only to derive a volume and is
# never displayed on its own.

_MASS_TO_MG = {"g": 1000.0, "mg": 1.0, "mcg": 0.001}
_RATE_MARKERS = ("/min", "/h", "/hr", "/hour", "/minute")

MASS = "MASS"                 # a flat dose: 25 g, 10 mcg
MASS_PER_KG = "MASS_PER_KG"   # weight-based: 0.1 mg/kg
RATE = "RATE"                 # an infusion rate: 0.05 mcg/kg/min — not a bolus
UNKNOWN = "UNKNOWN"           # fail closed


def classify_units(units, per_kg: bool) -> tuple:
    """(kind, mass_unit, reason). kind UNKNOWN means: do not serve this.

    Also catches units and per_kg CONTRADICTING each other. "mg/kg" with
    per_kg false is not a dose anyone can act on — it is a data error, and
    guessing which half is right is exactly the habit that produced the
    thousandfold bug.
    """
    if not isinstance(units, str) or not units.strip():
        return UNKNOWN, None, "dose_range has no units"
    u = units.strip().lower().replace("µ", "mc")

    if any(m in u for m in _RATE_MARKERS):
        head = u.split("/")[0]
        if head not in _MASS_TO_MG:
            return UNKNOWN, None, f"unrecognised rate unit {units!r}"
        if not per_kg and "/kg" in u:
            return UNKNOWN, None, (f"units {units!r} are weight-based but "
                                   f"per_kg is false")
        return RATE, head, ""

    if u.endswith("/kg"):
        head = u[:-3]
        if head not in _MASS_TO_MG:
            return UNKNOWN, None, f"unrecognised mass unit in {units!r}"
        if not per_kg:
            return UNKNOWN, None, (f"units {units!r} are per-kilogram but "
                                   f"per_kg is false")
        return MASS_PER_KG, head, ""

    if u in _MASS_TO_MG:
        if per_kg:
            return UNKNOWN, None, (f"units {units!r} are a flat mass but "
                                   f"per_kg is true")
        return MASS, u, ""

    return UNKNOWN, None, (f"unrecognised dose unit {units!r} — this is not "
                           f"defaulted to mg, because defaulting is what "
                           f"caused the g/mcg thousandfold error")


def to_mg(value: float, mass_unit: str) -> float:
    return value * _MASS_TO_MG[mass_unit]


def resolve_dose(entry: dict, weight_kg: Optional[float]) -> dict:
    """Turn a dose_entry into something servable, or say why not.

    Returns {kind, dose_mg, display_value, display_units, reason}. dose_mg is
    None for anything that must not become a single volume — a rate, or a unit
    this module does not recognise.
    """
    out = {"kind": UNKNOWN, "dose_mg": None, "display_value": None,
           "display_units": None, "reason": ""}
    rng = entry.get("dose_range")
    if not isinstance(rng, dict):
        out["reason"] = "dose_range is not authored"
        return out

    kind, mass_unit, why = classify_units(rng.get("units"), bool(rng.get("per_kg")))
    out["kind"], out["display_units"] = kind, rng.get("units")
    if kind == UNKNOWN:
        out["reason"] = why
        return out
    if kind == RATE:
        # An infusion rate is a rate. It has no single volume, and pretending
        # otherwise is how "0.05 mcg/kg/min" would become a 0.05 mL push.
        out["reason"] = ("this is an infusion RATE, not a bolus — no single "
                         "volume can be derived from it")
        out["display_value"] = rng.get("min")
        return out

    base = rng.get("min")
    if base is None:
        out["kind"] = UNKNOWN
        out["reason"] = "dose_range has no minimum"
        return out

    if kind == MASS_PER_KG:
        if weight_kg is None:
            out["kind"] = UNKNOWN
            out["reason"] = "weight-based dose with no confirmed weight"
            return out
        value = base * weight_kg
    else:
        value = base

    dose_mg = to_mg(value, mass_unit)

    cap = entry.get("max_single")
    if isinstance(cap, dict) and isinstance(cap.get("value"), (int, float)):
        ck, cu, cwhy = classify_units(cap.get("units"),
                                      str(cap.get("units", "")).endswith("/kg"))
        if ck == MASS:
            dose_mg = min(dose_mg, to_mg(cap["value"], cu))
        elif ck == MASS_PER_KG and weight_kg is not None:
            dose_mg = min(dose_mg, to_mg(cap["value"] * weight_kg, cu))
        elif ck == UNKNOWN:
            out["kind"] = UNKNOWN
            out["reason"] = f"max_single unit is unusable: {cwhy}"
            return out

    out["dose_mg"] = dose_mg
    # Back into the unit the SOURCE stated, so the medic reads the guideline's
    # own unit rather than a conversion of it.
    out["display_value"] = round(dose_mg / _MASS_TO_MG[mass_unit], 4)
    out["display_units"] = mass_unit
    return out


# The unit-error signature is a factor of exactly 1000 — g read as mg, mcg read
# as mg. Measured against the real file, the widest LEGITIMATE spread between
# two doses of one drug is epinephrine's 500x: 10 mcg push against 5 mg
# nebulised. So 1000x separates the error class from real clinical variation,
# with a margin of two. That margin is thin, and it is thin because
# epinephrine genuinely spans that much — if a drug is ever added with a wider
# honest spread, this threshold has to be revisited rather than the entry
# silenced.
DOSE_MAGNITUDE_FACTOR = 1000.0
_LINT_WEIGHT_KG = 70.0


def lint_dose_magnitude() -> list:
    """Entries whose dose is a thousandfold out of family for their own drug.

    The check the volume audit structurally cannot do. That audit verifies a
    volume against the STATED milligrams, so a dose whose unit was mis-entered
    is internally consistent and sails through. This compares each bolus entry
    against its siblings, where a factor-of-1000 outlier is a unit error and
    not a clinical decision.
    """
    problems = []
    for name, drug in DRUGS.items():
        doses = []
        for e in drug.get("dose_entries", []):
            r = resolve_dose(e, _LINT_WEIGHT_KG)
            if r["dose_mg"]:
                doses.append((r["dose_mg"], e))
        if len(doses) < 2:
            continue
        lo = min(v for v, _ in doses)
        hi = max(v for v, _ in doses)
        for value, e in doses:
            others = [v for v, _ in doses if v is not value]
            if not others:
                continue
            if all(value >= o * DOSE_MAGNITUDE_FACTOR for o in others) or \
                    all(value * DOSE_MAGNITUDE_FACTOR <= o for o in others):
                msg = (f"{name}/{e.get('indication')}/{e.get('population')}: "
                       f"{e['dose_range'].get('min')} "
                       f"{e['dose_range'].get('units')} is {value:g} mg at "
                       f"{_LINT_WEIGHT_KG:g} kg, more than "
                       f"{DOSE_MAGNITUDE_FACTOR:g}x from every other dose of "
                       f"{name} ({lo:g}-{hi:g} mg) — the signature of a unit "
                       f"error")
                # Stamped on the entry, not held in a side table keyed by
                # identity: entry_is_servable is routinely handed a COPY of an
                # entry, and a verdict that a copy loses is a verdict the fence
                # cannot enforce.
                e["_unit_error"] = msg
                problems.append(msg)
            else:
                e.pop("_unit_error", None)
    return problems


DOSE_MAGNITUDE_PROBLEMS = []


def refresh_dose_magnitude_lint() -> list:
    global DOSE_MAGNITUDE_PROBLEMS
    DOSE_MAGNITUDE_PROBLEMS = lint_dose_magnitude()
    return DOSE_MAGNITUDE_PROBLEMS


def single_concentration(generic_name: str) -> Optional[float]:
    """The one concentration this drug can be drawn from, or None.

    None when the drug has no stated concentration, or MORE THAN ONE. Refusing
    the ambiguous case is the point: WHO lists ketamine at both 10 mg/mL and
    50 mg/mL, and a contract that silently picked one would be authoring a
    five-fold volume error. The owner resolves it by stating which vial this
    deployment actually carries.
    """
    drug = DRUGS.get(generic_name)
    if not drug:
        return None
    concs = {f.get("concentration_mg_ml") for f in drug.get("forms", [])
             if isinstance(f, dict) and isinstance(f.get("concentration_mg_ml"),
                                                   (int, float))}
    if len(concs) != 1:
        return None
    return float(next(iter(concs)))


def signed_entries_by_indication(patterns, is_pediatric: bool = False,
                                 age_years: Optional[float] = None) -> list:
    """(drug, entry) pairs whose INDICATION matches, whatever the query named.

    An RSI query rarely names its drugs — "RSI now" is the whole request — so
    a lookup that only matches drugs mentioned in the text would drop the
    induction agent from the one bundle that always needs one. The legacy
    calculators knew the bundle; the contract path has to know it too, or
    signing an entry makes RSI worse rather than better.
    """
    out = []
    live = servable_entries()
    for name, entries in live.items():
        for e in entries:
            ind = (e.get("indication") or "").lower()
            if not any(p.lower() in ind for p in patterns):
                continue
            pop = e.get("population")
            if is_pediatric and pop == "adult":
                continue
            if not is_pediatric and pop == "peds":
                continue
            # Age-banded entries need an age. Neither band is a safe default:
            # too little paralytic is a patient who moves, too much is a longer
            # apnoea. So a band is used only when the age is known, and the
            # gap is visible rather than papered over.
            band = _age_band(e)
            if band is not None:
                if age_years is None:
                    continue
                lo, hi = band
                if not (lo <= age_years < hi):
                    continue
            out.append((name, e))
    return out


def _age_band(entry: dict):
    """(low, high) years this entry is banded to, or None if it is not."""
    ind = (entry.get("indication") or "").lower()
    m = re.search(r"under (\d+(?:\.\d+)?) year", ind)
    if m:
        return (0.0, float(m.group(1)))
    m = re.search(r"(\d+(?:\.\d+)?) years? and above", ind)
    if m:
        return (float(m.group(1)), 200.0)
    return None


def age_banded_entries(patterns, is_pediatric: bool = True) -> list:
    """Signed entries that WOULD apply but need an age to choose between."""
    return [(n, e) for n, es in servable_entries().items() for e in es
            if _age_band(e) is not None
            and any(p.lower() in (e.get("indication") or "").lower()
                    for p in patterns)
            and (e.get("population") != "adult" if is_pediatric else True)]


def signed_entries_for(query: str, route: Optional[str] = None,
                       is_pediatric: bool = False) -> list:
    """(generic_name, entry) pairs that are BOTH named by this query and signed.

    The only lookup the serving path is allowed to use.
    """
    out = []
    live = servable_entries()
    for name in resolve_drugs(query):
        for e in live.get(name, []):
            if route and e.get("route") not in (route, "IV/IO", "any"):
                continue
            pop = e.get("population")
            if is_pediatric and pop == "adult":
                continue
            if not is_pediatric and pop == "peds":
                continue
            out.append((name, e))
    return out


# Run last: the lint needs resolve_dose(), which needs the unit tables above.
refresh_dose_magnitude_lint()
for _p in DOSE_MAGNITUDE_PROBLEMS:
    print(f"⚠️  drug_contracts dose-magnitude lint: {_p}")
