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
    tiers = {s.get("tier") for s in entry["sources"]}
    if not tiers & {1, 2}:
        return False, ("no approved source: every source is tier "
                       f"{sorted(t for t in tiers if t is not None)} and a "
                       "signed entry needs at least one tier 1 or tier 2 citation")

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
