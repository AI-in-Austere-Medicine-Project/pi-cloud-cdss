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

WHAT A MEDIC READS NOW, AND WHAT THE RECORD KEEPS
────────────────────────────────────────────────
Owner rulings 9-12, 2026-08-26. A cautions[] item may be a bare string or
{"text", "tier"}, and the tier says WHEN the line is read, never whether it is
true. DEFAULT IS SERVE: only "detail" written deliberately takes a line off the
dose screen, so a caution nobody has tiered is safe rather than hidden. The
detail tier is reachable in one question — openai_client's "why this dose?"
gate — and in the worksheet.

Contraindications are NOT tierable. They render at every serve, which is new:
the field had been authored, reviewed and signed since this module existed and
read by nothing at all. Several are thin; lint_thin_contraindications() makes
that visible rather than the field invisible.

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
# NOT env-overridable, deliberately. This decides whose signature the SERVING
# path will honour, which makes it a safety fence rather than a tunable. It
# used to read CDSS_CARD_AUTHORS, and a signing shell that had widened it wrote
# five concentrations under a signer the service — which carried no such export
# — then refused. The signatures were real and the values were right, and every
# volume in the system degraded to mg-only with nothing anywhere saying why. A
# fence a shell export can move is not a fence. Identity beyond the role rides
# in --reason, where the audit log keeps it.
SIGNOFF_AUTHORS = ("clinician", "AI-AIM")

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

# ─────────────────────────────────────────────────────────────────────────────
# OWNER DECLARATION
#
# A third basis for a signable dose, alongside a tier 1 and a tier 2 citation:
# the owner states the number on clinical judgement because no guideline states
# it. It exists because refusing to serve is not automatically the safe answer
# — post-intubation sedation with no pump is a real thing a medic has to do,
# PFC doctrine prescribes the SHAPE (intermittent ketamine push) and no CPG
# anywhere prints the repeat-bolus NUMBER. The choice was between an owner who
# names the value and signs for it, and a system that goes quiet on a case it
# is deployed into.
#
# Everything about the design is aimed at the one failure this opens up:
# OWNER_DECLARED becoming a quiet way to sign an unsourced number. So —
#
#   it is opt-in and per-entry     the flag says so on the entry itself, and it
#                                  does nothing for the entry next door. There
#                                  is no global "the owner has declared" state.
#   it names its own value         declared_value must EQUAL dose_range. Editing
#                                  the dose without re-declaring it breaks the
#                                  match and the entry stops serving. This is
#                                  what makes silent smuggling impossible: the
#                                  number is written twice, deliberately.
#   it cannot be implicit          a declaration block with no flag is refused,
#                                  and a flag with no declaration block is
#                                  refused. Neither half works alone.
#   shape and value stay apart     supporting_doctrine cites what the doctrine
#                                  DOES say (the shape). It is held outside
#                                  sources[] so no reader can mistake a shape
#                                  citation for a citation of the number.
#   it is visible at every serve   provenance_label() rides in the served
#                                  cautions and in the worksheet, so a medic
#                                  reads "owner-declared" on the same line as
#                                  the dose rather than in a file they will
#                                  never open.
OWNER_DECLARED = "OWNER_DECLARED"
MIGRATED_UNSOURCED = "MIGRATED_UNSOURCED"

_DECLARATION_KEYS =("basis", "declared_by", "declared_on", "justification",
                     "declared_value", "supporting_doctrine")


# ─────────────────────────────────────────────────────────────────────────────
# CAUTION TIERS — WHAT A MEDIC READS NOW, AND WHAT THE RECORD KEEPS
#
# A cautions[] item is either a plain string or {"text": ..., "tier": ...}:
#
#     "..."                     UNCLASSIFIED — it serves
#     {"tier": "serve", ...}    it serves
#     {"tier": "detail", ...}   held for the record and for "why this dose?"
#
# DEFAULT IS SERVE, and that is the whole safety argument for the mechanism.
# The only way to take a line off the screen is to write "detail" on it
# deliberately. Every other state — a newly added string, an author who never
# heard of tiers, a tier key with a typo in it — shows the text. A tiering
# scheme whose default hides is one forgotten annotation away from a caution
# nobody reads, and the entries most likely to be edited in a hurry are the
# ones that matter most.
#
# WHY TIERS AT ALL. The RSI bundle served eighteen caution bullets, several of
# them paragraphs about what a guideline does NOT state, to a medic holding a
# laryngoscope. Prose read under load is not read, so the four lines that
# change what the medic does were being hidden by the fourteen that do not.
# Nothing is deleted: detail-tier text is in the worksheet and in the "why this
# dose?" answer, which is where "the cited guideline states no cumulative
# maximum" was always the right answer to a question nobody asks mid-airway.
#
# The tier is a claim about WHEN a line is read, never about whether it is
# true. A contraindication is not tierable at all — see serve_contraindications.
CAUTION_SERVE = "serve"
CAUTION_DETAIL = "detail"
CAUTION_TIERS = (CAUTION_SERVE, CAUTION_DETAIL)


def caution_text(caution) -> str:
    """The words, whether the item is a bare string or a tiered object."""
    if isinstance(caution, dict):
        return str(caution.get("text") or "").strip()
    return str(caution or "").strip()


def caution_tier(caution) -> str:
    """CAUTION_DETAIL only when the item says so exactly. Everything serves.

    Deliberately permissive in one direction and one direction only: an
    unreadable tier, a missing tier and a misspelled tier all resolve to serve,
    so no caller can hide a line by accident. _cautions_ok() refuses the
    misspelling at the fence, so the mistake is loud as well as harmless.
    """
    if isinstance(caution, dict):
        if str(caution.get("tier") or "").strip().lower() == CAUTION_DETAIL:
            return CAUTION_DETAIL
    return CAUTION_SERVE


def caution_texts(entry: dict) -> list:
    """Every caution on the entry, both tiers, in file order — the record."""
    return [t for t in (caution_text(c) for c in (entry.get("cautions") or []))
            if t]


def detail_cautions(entry: dict) -> list:
    """The lines held back from the serve tier. What "why this dose?" answers."""
    return [caution_text(c) for c in (entry.get("cautions") or [])
            if caution_tier(c) == CAUTION_DETAIL and caution_text(c)]


def is_unclassified_caution(caution) -> bool:
    """A bare string: nobody has said which tier it belongs in. It serves."""
    return not isinstance(caution, dict)


def _cautions_ok(entry: dict) -> tuple:
    """(ok, reason). A cautions[] that would render as junk or vanish.

    Refuses a tier value the schema does not know, for the same reason
    classify_units() refuses an unrecognised unit rather than assuming mg: the
    author of `{"tier": "detials"}` meant something, and a mechanism that
    silently ignored the typo would leave nobody to notice. The ABSENCE of a
    tier is a defined state and passes — that is what unclassified means.
    """
    cautions = entry.get("cautions")
    if cautions is None:
        return True, ""
    if not isinstance(cautions, list):
        return False, "cautions is not a list"
    for c in cautions:
        if isinstance(c, dict):
            if not str(c.get("text") or "").strip():
                return False, "a caution object carries no text"
            tier = c.get("tier")
            if tier is not None and str(tier).strip().lower() not in CAUTION_TIERS:
                return False, (f"caution tier {tier!r} is not one of "
                               f"{', '.join(CAUTION_TIERS)}")
        elif not str(c or "").strip():
            return False, "a caution is empty"
    return True, ""


def serve_contraindications(entry: dict) -> list:
    """The 'do not give' list, as it should reach a medic.

    NOT TIERABLE, and that is owner ruling 12 (2026-08-26). These had never
    been rendered anywhere — the field was authored, signed and then read by
    nothing — which is a hole in the tier that matters most. Several of them
    are thin ("Hypersensitivity" and nothing else); thinness is a content
    problem for lint_thin_contraindications() to make visible, not a reason to
    keep the field invisible.
    """
    return [str(c).strip() for c in (entry.get("contraindications") or [])
            if str(c or "").strip()]


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


def state_note(doc: Optional[dict] = None) -> str:
    """The file's `generated_note`, COMPUTED from what the file contains.

    It used to be a sentence somebody typed: "Nothing in this file is signed and
    nothing in it is served. Every dose_entry carries signoff:false and awaits a
    credentialed clinician." That was true the day it was written and false from
    the first signature onwards — and it sat at the top of the file, so it was
    the first thing any reader was told about the state of the bank. A prose
    claim about a file, stored inside that file, drifts the moment the file
    changes and nothing anywhere notices.

    So the sentence is derived and the stored copy is checked against it.
    tools/set_contract.py refreshes it on every write, and a test asserts the
    two agree — which is what turns "somebody must remember" into "the suite
    says so, with the correct string in the failure message".

    Counts SERVABLE rather than merely signed, deliberately: what a reader
    needs from this line is how much of the bank is carrying traffic, and a
    signature the allowlist will not honour carries none.
    """
    drugs = ({d["generic_name"]: d for d in doc.get("drugs", [])
              if isinstance(d, dict) and d.get("generic_name")}
             if doc is not None else DRUGS)
    entries = [(n, e) for n, d in drugs.items()
               for e in d.get("dose_entries", [])]
    live = [(n, e) for n, e in entries if entry_is_servable(e, drugs[n])[0]]
    declared = [1 for _, e in live if is_owner_declared(e)]
    return (
        f"{len(live)} of {len(entries)} dose entries across "
        f"{len({n for n, _ in live})} of {len(drugs)} drugs are signed and "
        f"servable; {len(declared)} of those "
        f"{'serves' if len(declared) == 1 else 'serve'} on an explicit owner "
        f"declaration rather than a citation. Every other entry carries "
        f"signoff:false or fails the fence, and is invisible to the serving "
        f"path — an unsigned entry is not a weaker answer, it is not an "
        f"answer. THIS LINE IS DERIVED FROM THE FILE'S OWN CONTENTS by "
        f"drug_contracts.state_note(); do not hand-edit it."
    )


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


def _declaration_ok(entry: dict) -> tuple:
    """(ok, reason) for the owner-declaration half of an entry.

    Called on EVERY entry, not just declared ones, because half the job is
    catching the two mismatched states: a flag with no declaration, and a
    declaration with no flag. Returns (True, "") for the ordinary entry that
    has neither.
    """
    flags = entry.get("flags") or []
    flagged = OWNER_DECLARED in flags
    decl = entry.get("owner_declaration")

    if decl is not None and not flagged:
        return False, ("carries owner_declaration but is not flagged "
                       f"{OWNER_DECLARED} — a declaration that is not declared "
                       "is how an unsourced value gets in quietly. Flag it or "
                       "remove it")
    if not flagged:
        return True, ""

    if MIGRATED_UNSOURCED in flags:
        return False, (f"flagged both {MIGRATED_UNSOURCED} and "
                       f"{OWNER_DECLARED} — the dose cannot be both blocked as "
                       "an uncorroborated hardcode and declared as the owner's "
                       "judgement. Clear the migration flag deliberately when "
                       "declaring, so the change of basis is a visible edit")
    if not isinstance(decl, dict):
        return False, (f"flagged {OWNER_DECLARED} with no owner_declaration "
                       "object — the flag alone declares nothing")

    missing = [k for k in _DECLARATION_KEYS if k not in decl]
    if missing:
        return False, (f"owner_declaration is missing "
                       f"{', '.join(sorted(missing))}")
    # has_sentinel, not _is_pending: declared_value legitimately carries a null
    # max where min and max are the same number, and _is_pending would read
    # that null as unauthored. The per-key checks below cover the rest.
    if has_sentinel(decl):
        return False, "owner_declaration is not authored"

    for k in ("basis", "declared_by", "declared_on", "justification"):
        if not isinstance(decl.get(k), str) or not decl[k].strip():
            return False, f"owner_declaration.{k} must be a non-empty string"

    # The justification is the whole point of the mechanism: it is the sentence
    # the next reader gets instead of "someone typed a number". A one-word
    # placeholder would satisfy a non-empty check and satisfy nobody else.
    if len(decl["justification"].strip()) < 80:
        return False, ("owner_declaration.justification is too short to be a "
                       "justification — say what doctrine supports the shape "
                       "and why no source states the value")

    doctrine = decl.get("supporting_doctrine")
    if not isinstance(doctrine, list) or not doctrine:
        return False, ("owner_declaration.supporting_doctrine is empty — a "
                       "declared value still has to say what the doctrine "
                       "does support, or it is a bare assertion")
    for d in doctrine:
        if not isinstance(d, dict):
            return False, "a supporting_doctrine item is not an object"
        for k in ("citation", "supports"):
            if not isinstance(d.get(k), str) or not d[k].strip():
                return False, f"a supporting_doctrine item is missing {k}"

    # The declared value, written out a second time and checked against the
    # first. Edit dose_range alone and this stops matching, which takes the
    # entry off the wire until someone re-declares it on purpose.
    dv = decl.get("declared_value")
    if not isinstance(dv, dict):
        return False, "owner_declaration.declared_value is not an object"
    dr = entry.get("dose_range")
    if not isinstance(dr, dict):
        return False, "owner_declaration.declared_value has no dose_range to match"
    for k in _DOSE_RANGE_KEYS:
        if dv.get(k) != dr.get(k):
            return False, (f"owner_declaration.declared_value.{k} is "
                           f"{dv.get(k)!r} but dose_range.{k} is "
                           f"{dr.get(k)!r} — the declaration does not name the "
                           "dose the entry serves. Re-declare the value or "
                           "revert the dose")
    return True, ""


def is_owner_declared(entry: dict) -> bool:
    """Whether this entry's DOSE rests on the owner's declaration.

    True only when the flag and a well-formed declaration are both present, so
    a caller can never be told 'declared' about an entry the fence would refuse.
    """
    if not isinstance(entry, dict):
        return False
    return (OWNER_DECLARED in (entry.get("flags") or [])
            and _declaration_ok(entry)[0])


# TWO FORMS OF ONE CLAIM — owner ruling 11, 2026-08-26.
#
# The banner and the short label say the same thing to two different readers.
# The medic mid-airway needs to know the number is a declaration and not a
# guideline value; they do not need to read a name and a date to act, and a
# four-line paragraph at the top of the cautions pushed the clinical lines off
# the screen. The record needs the name and the date, because a declaration
# whose signer is not written down is an anonymous number.
#
# So: the short form serves, the full banner is kept by the worksheet and by
# the "why this dose?" answer. Both are generated from the declaration itself,
# so neither can drift from it and neither can be hand-copied wrongly onto an
# entry that carries no declaration at all.
def provenance_label(entry: dict) -> str:
    """The FULL banner — for the record, not for the screen mid-procedure.

    Names the declarer and the date. Rendered by the worksheet and by
    build_why_this_dose_response(); serve paths take provenance_label_short().
    """
    if not is_owner_declared(entry):
        return ""
    d = entry["owner_declaration"]
    return (f"OWNER-DECLARED DOSE — NOT FROM A PUBLISHED GUIDELINE. This number "
            f"is the clinical judgement of {d['declared_by']} "
            f"({d['declared_on']}), not a value any CPG states. The approach is "
            f"doctrine; the number is a declaration.")


def provenance_label_short(entry: dict) -> str:
    """The serve-tier form: the fact, in one clause, at the top of the cautions.

    Carries no name and no date on purpose. What changes what a medic does is
    that the number is a declaration; who declared it changes nothing at the
    bedside and costs a line of screen at the worst possible moment.
    """
    if not is_owner_declared(entry):
        return ""
    return "OWNER-DECLARED dose — not a guideline value."


def serve_cautions(entry: dict) -> list:
    """The cautions as they should reach a medic: provenance first, serve tier.

    Every serve path goes through this rather than reading entry["cautions"]
    directly, so an owner-declared dose cannot reach a screen looking like a
    cited one just because a new call site forgot — and so a detail-tier line
    cannot reach one just because a new call site did not know about tiers.
    """
    cautions = [caution_text(c) for c in (entry.get("cautions") or [])
                if caution_tier(c) == CAUTION_SERVE and caution_text(c)]
    label = provenance_label_short(entry)
    return [label] + cautions if label else cautions


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

    # A cautions[] whose shape is wrong is text a medic would be shown as a
    # dict repr, or a line that silently vanishes from the serve tier.
    ok, why = _cautions_ok(entry)
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
    # Checked BEFORE the migration flag and the tier rule, because both of the
    # states it catches are malformed rather than merely unsourced, and naming
    # the malformation is more use than reporting the symptom.
    ok, why = _declaration_ok(entry)
    if not ok:
        return False, why

    declared = is_owner_declared(entry)

    if MIGRATED_UNSOURCED in (entry.get("flags") or []):
        return False, ("flagged MIGRATED_UNSOURCED: the DOSE came from the "
                       "pre-contract hardcode and no approved source "
                       "corroborates it. A citation supporting another field "
                       "does not change that — clear the flag only when the "
                       "dose itself has a tier 1 or tier 2 source, or when the "
                       "owner declares the value under OWNER_DECLARED")

    # Three bases, not two. A tier 1 citation, a tier 2 citation, or the
    # owner's declaration — and the third one holds for THIS entry only,
    # because is_owner_declared() reads this entry's own flag and its own
    # declaration block. There is no state here that another entry can inherit:
    # an undeclared entry with nothing but tier 0 sources is refused whether or
    # not the entry beside it is declared.
    tiers = {s.get("tier") for s in entry["sources"]}
    if not tiers & {1, 2} and not declared:
        return False, ("no approved source: every source is tier "
                       f"{sorted(t for t in tiers if t is not None)} and a "
                       "signed entry needs at least one tier 1 or tier 2 "
                       "citation, or an explicit owner declaration")

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


def unhonoured_signatures() -> list:
    """(drug, indication, route, signer) for every entry SIGNED by someone the
    allowlist will not honour.

    Same failure the concentration list hit: entry_is_servable() reports
    "reviewed_by ... is not an authorised signer" per entry, but only if
    someone asks it entry by entry. This names the whole set at once, so a
    signature that is not being honoured is visible rather than inferred from
    an absent dose.
    """
    out = []
    for name, drug in DRUGS.items():
        for e in drug.get("dose_entries", []):
            if e.get("signoff") is not True:
                continue
            signer = str(e.get("reviewed_by") or "").strip()
            if signer not in SIGNOFF_AUTHORS:
                out.append((name, e.get("indication"), e.get("route"), signer))
    return out


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
    """{generic_name: {"live": n, "total": n, "reasons": [...]}} for reporting.

    INTENTIONALLY UNCALLED. Owner ruling 2026-08-26: kept as the reporting
    surface for /status and for anything that needs to describe the bank
    without reimplementing the fence. A dead-code sweep will find it — this
    note is the answer, so it is not deleted and then rebuilt.

    Unlike the two functions deleted the same day, this one is safe to leave
    dormant: it READS state and serves nothing. Those returned doses while
    bypassing a gate, which is why they went.
    """
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


# Run at import, the same as the alias lint above.
#
# This was DEFINED and never CALLED — from the day it was written until
# 2026-08-26. A collision lint nobody runs is the vitamin-K class waiting to
# recur: that bug was a substring alias quietly eating a real drug, and it was
# found by a person reading code, not by the lint that exists to find it. An
# unrun lint is worse than no lint, because the file reads as though the class
# were covered.
#
# INFORMATIONAL, and deliberately not fatal — unlike ALIAS_COLLISIONS, which
# refuses. A combination product legitimately contains its components' names,
# so failing on one would either block a legal entry or teach everyone to
# ignore the warning, and the second is how the alias lint would stop working
# too. resolve_drugs() handles these by longest-match-wins; the lint's job is
# to make sure a human knows which names overlap.
GENERIC_NAME_OVERLAPS = lint_generic_name_overlaps()


def _overlap_is_expected(line: str) -> bool:
    """A combination product containing its own components' names.

    Five of these exist in the bank today — 'artemether + lumefantrine' and the
    four-drug TB regimen. Printing them on every import would put five lines of
    known-fine warning in front of every server start and every test run, and a
    warning that is always there is a warning nobody reads. That is the failure
    this lint is trying to prevent, so it must not be the failure the lint
    causes. The full list stays in GENERIC_NAME_OVERLAPS for anything that
    wants it; only the unexplained ones get printed.
    """
    return " + " in line.split(" contains ")[0]


_UNEXPECTED = [p for p in GENERIC_NAME_OVERLAPS if not _overlap_is_expected(p)]
if _UNEXPECTED:
    for _p in _UNEXPECTED:
        print(f"⚠️  drug_contracts generic-name overlap: {_p}")
    print(f"⚠️  {len(_UNEXPECTED)} overlap(s) are NOT combination products — "
          "check that resolve_drugs() picks the one you mean")


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


def range_values(entry: dict) -> list:
    """The numbers this entry's dose_range actually authorises, min first.

    resolve_dose() serves the MINIMUM, which is right for a bolus that has to
    become one volume. It is wrong as the whole story for an entry the
    guideline wrote as a RANGE: epinephrine push dose is 10-20 mcg titrated to
    MAP, and serving "10 mcg" alone silently retires the top half of the
    guideline's own window. Callers that show a range to a human use this;
    callers that draw up a syringe still use resolve_dose().
    """
    rng = entry.get("dose_range")
    if not isinstance(rng, dict):
        return []
    return [v for v in (rng.get("min"), rng.get("max"))
            if isinstance(v, (int, float))]


def range_text(entry: dict) -> Optional[str]:
    """The dose_range as the source wrote it: "10-20 mcg", "0.25 mg/kg".

    None when the units are unservable, for the same reason resolve_dose fails
    closed there: a number whose unit this module will not vouch for is not a
    dose, and prose is not the place to start guessing.
    """
    vals = range_values(entry)
    rng = entry.get("dose_range") or {}
    units = rng.get("units")
    kind, _, _ = classify_units(units, bool(rng.get("per_kg")))
    if not vals or kind == UNKNOWN:
        return None
    lo = vals[0]
    hi = vals[-1]
    head = f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"
    return f"{head} {units}"


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


# age_banded_entries() was DELETED on 2026-08-26 — no call site anywhere,
# including tests. It returned age-banded entries WITHOUT the age that
# distinguishes them, for a "ask which band" flow that was never built.
# signed_entries_by_indication() already refuses to guess a band when the age
# is unknown; this returned the candidates anyway, so serving from it would
# have undone that refusal. Same A2 shape as the template deleted last week.


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


# ─────────────────────────────────────────────────────────────────────────────
# VISIBILITY LINTS — the ones that report rather than refuse
#
# Three things below are content problems, not structural ones: a caution
# nobody has tiered, a contraindication list that says nothing, and a serve
# tier that has grown back into a wall. None of them can be a refusal — taking
# a signed dose off the wire because its contraindications are thin would
# remove the dose and leave the thinness — so each one is counted, held on the
# module, and summarised in ONE line at import.
#
# One line each, deliberately. The generic-name overlap lint above prints only
# its unexplained cases for exactly this reason: five known-fine warnings on
# every server start is a warning nobody reads, which is the failure the lint
# exists to prevent.
# ─────────────────────────────────────────────────────────────────────────────

# A contraindication that names nothing a medic could act on. Every drug in
# the bank is contraindicated in hypersensitivity to itself; a field
# containing only that has the shape of an answer and the content of a shrug.
TRIVIAL_CONTRAINDICATIONS = frozenset({
    "hypersensitivity", "known hypersensitivity", "hypersensitivity to the drug",
    "allergy", "known allergy", "allergy to the drug", "none", "none known",
    "none stated", "n/a", "na",
})

# The serve tier is a screen a medic reads while doing something else. These
# are the ceilings that keep it one, and they are pinned by a test rather than
# enforced at serve: a dose withheld because its cautions are long is a worse
# failure than a long screen.
SERVE_CAUTION_BUDGET = 5
SERVE_CAUTION_CHAR_BUDGET = 500


def _entry_id(name: str, entry: dict) -> tuple:
    return (name, entry.get("indication"), entry.get("route"),
            entry.get("population"))


def _is_trivial_contraindication(text: str) -> bool:
    t = re.sub(r"[^a-z ]", " ", str(text).lower())
    return " ".join(t.split()) in TRIVIAL_CONTRAINDICATIONS


def lint_thin_contraindications() -> list:
    """Entries whose 'do not give' list is empty or says only 'hypersensitivity'.

    OWNER RULING 12, 2026-08-26. Contraindications now render at every serve,
    which turns their thinness from a private fact about the file into
    something a medic sees. The ruling was to render them anyway and make the
    thinness visible here, rather than to keep the field invisible because
    parts of it are weak: never having rendered them at all is the bigger hole,
    and a lint is how the content gets fixed instead of forgotten.

    Returns (drug, indication, route, population, reason, servable).
    """
    live = servable_entries()
    out = []
    for name, drug in DRUGS.items():
        live_ids = {id(e) for e in live.get(name, [])}
        for e in drug.get("dose_entries", []):
            cis = serve_contraindications(e)
            if has_sentinel(cis):
                continue        # unauthored, and the fence already refuses it
            if not cis:
                reason = "no contraindications recorded"
            elif all(_is_trivial_contraindication(c) for c in cis):
                reason = f"only trivial: {'; '.join(cis)}"
            else:
                continue
            out.append(_entry_id(name, e) + (reason, id(e) in live_ids))
    return out


def lint_unclassified_cautions() -> list:
    """Cautions nobody has tiered. They serve — that is the default — and this
    is the backlog of lines that have never been read with 'does a medic need
    this now?' in mind.

    Not an error. Default-is-serve means an unclassified caution is SAFE; it
    just is not finished. The distinction matters because a lint that treats
    unfinished as broken is a lint that gets silenced.

    Returns (drug, indication, route, population, text, servable).
    """
    live = servable_entries()
    out = []
    for name, drug in DRUGS.items():
        live_ids = {id(e) for e in live.get(name, [])}
        for e in drug.get("dose_entries", []):
            for c in e.get("cautions") or []:
                if is_unclassified_caution(c) and caution_text(c):
                    out.append(_entry_id(name, e)
                               + (caution_text(c), id(e) in live_ids))
    return out


def serve_caution_overruns() -> list:
    """Servable entries whose serve tier is over budget — too many lines, or
    too many characters of them.

    Both ceilings, because they fail differently: six short bullets and one
    500-word paragraph are both unreadable at the moment of giving a drug, and
    a count on its own would pass the paragraph.

    Returns (drug, indication, route, population, count, chars).
    """
    out = []
    for name, entries in servable_entries().items():
        for e in entries:
            served = serve_cautions(e)
            chars = sum(len(c) for c in served)
            if len(served) > SERVE_CAUTION_BUDGET or chars > SERVE_CAUTION_CHAR_BUDGET:
                out.append(_entry_id(name, e) + (len(served), chars))
    return out


# Run last: these need resolve_dose(), which needs the unit tables above.
refresh_dose_magnitude_lint()
for _p in DOSE_MAGNITUDE_PROBLEMS:
    print(f"⚠️  drug_contracts dose-magnitude lint: {_p}")

THIN_CONTRAINDICATIONS = lint_thin_contraindications()
_THIN_LIVE = [r for r in THIN_CONTRAINDICATIONS if r[-1]]
if _THIN_LIVE:
    print(f"⚠️  drug_contracts contraindication lint: {len(_THIN_LIVE)} servable "
          f"entr{'y' if len(_THIN_LIVE) == 1 else 'ies'} carry empty or trivial "
          f"contraindications and render them anyway "
          f"({len(THIN_CONTRAINDICATIONS)} across the whole bank) — see "
          f"drug_contracts.THIN_CONTRAINDICATIONS")

UNCLASSIFIED_CAUTIONS = lint_unclassified_cautions()
_UNCLASSIFIED_LIVE = [r for r in UNCLASSIFIED_CAUTIONS if r[-1]]
if _UNCLASSIFIED_LIVE:
    print(f"⚠️  drug_contracts caution-tier lint: {len(_UNCLASSIFIED_LIVE)} "
          f"caution(s) on servable entries are untiered and therefore SERVE "
          f"({len(UNCLASSIFIED_CAUTIONS)} across the whole bank) — see "
          f"drug_contracts.UNCLASSIFIED_CAUTIONS")
