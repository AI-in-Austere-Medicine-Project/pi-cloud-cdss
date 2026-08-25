#!/usr/bin/env python3
"""
Sign a dose entry in the drug contract file. The sanctioned path.

    python3 set_contract.py --list
    python3 set_contract.py --list --drug ketamine
    python3 set_contract.py --drug ketamine --indication "RSI induction" \
            --population adult --route IV --sign --by clinician --date 2026-08-25
    python3 set_contract.py --drug ketamine --indication "RSI induction" \
            --population adult --route IV --unsign

Sibling to set_concentration.py, same doctrine, same asymmetry. Hand-editing
drug_contracts.json still works; this exists because signing an entry by hand
is three fields in three places and the interesting failure is getting two of
them right.

WHAT IT REFUSES, AND WHY EACH ONE IS SEPARATE FROM THE ENGINE
─────────────────────────────────────────────────────────────
drug_contracts.entry_is_servable() already refuses most of this at SERVE time.
Checking it again here at SIGN time is not redundant: a refusal at serve time
is a dose that silently is not there, discovered by a medic who asks for it. A
refusal at sign time is a message to the person who can fix it, while they are
looking at it. The tool therefore states its own reason first and then runs the
engine's gate as the final word, so it can never sign something the engine
would decline to serve.

Four refusals are named explicitly because they are the four the owner asked
for by name, and because each one has been a real defect in this file:

    a sentinel anywhere      NEEDS_MANUAL_ENTRY in a cautions[] line is text a
                             medic gets shown.
    tier-0-only              tier 0 is the migration carrier for the
                             pre-contract hardcodes. It is not evidence.
    unresolved SOURCE_CONFLICT   two sources disagree and nobody has said which
                             one wins. Signing one IS the adjudication, so the
                             adjudication has to be written down first.
    MIGRATED_UNSOURCED       the DOSE is the hardcoded number. An entry can
                             carry a tier 1 citation for its CONTRAINDICATIONS
                             while its dose_range is still the hardcode —
                             ketamine post-intubation sedation is exactly this
                             — and the tier check cannot tell which field a
                             source backs, so the flag carries that fact.

A fifth refusal joined them with OWNER_DECLARED, the owner's declaration as a
third basis for a signable dose:

    a malformed declaration  OWNER_DECLARED with no owner_declaration object, a
                             declaration block on an entry that is not flagged,
                             a justification too short to be one, or a
                             declared_value that no longer matches dose_range.
                             The last is the important one: it is what makes
                             editing the number without re-declaring it take
                             the entry off the wire instead of silently
                             re-using the old signature.

The engine refuses all of them too, and deliberately: the fence is the thing that
must not be bypassable, and a tool is bypassable by not using it. What is NOT
duplicated is the wording. entry_is_servable() answers "why is this dose not
live" for a worksheet; sign_refusal() answers "what do I have to do about it"
for the person holding the pen, and it is checked against the entry as it would
read once signed, so it never reports the missing signature as the problem.

SIGNING AND UNSIGNING ARE NOT SYMMETRIC
───────────────────────────────────────
--sign requires --by from the authorised signer list and --date. --unsign
requires neither. Signing a dose is an authority claim that a number is safe to
give; unsigning is a refusal to keep claiming it, and what lands when it does is
the drug going quiet — the query falls back to the empty-contract path it had
before this module existed. If a value turns out to be wrong mid-deployment and
no signer is reachable, anyone can pull it in one command and the system gets
less useful rather than wrong. Requiring a signature to WITHDRAW a dangerous
dose would be the failure mode this whole layer exists to prevent.

THE VERSION SUFFIX IS PART OF THE SIGNATURE
───────────────────────────────────────────
Every dose entry ships with a -draft suffix on its version; the signed vent
cards carry a bare version with no suffix. --sign strips the suffix and
--unsign puts it back, so an entry's version string never claims a review that
has not happened. This is the entry's own version, unrelated to the server
version in version.py.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys

import drug_contracts as dc

PENDING = dc.PENDING

CONFIG = dc._DIR / "drug_contracts.json"
CHANGE_LOG = pathlib.Path(os.getenv("CDSS_CONTRACT_LOG",
                                    str(dc._DIR / "drug_contracts.log.jsonl")))

# The selector. Four fields, because three of them are not unique on their own:
# ketamine has four "agitated or violent patient" entries that differ only by
# population and route.
SELECTOR = ("indication", "population", "route")


# ─────────────────────────────────────────────────────────────────────────────
# FILE
# ─────────────────────────────────────────────────────────────────────────────

def _load_raw() -> dict:
    return json.loads(CONFIG.read_text())


def _save_raw(doc: dict) -> None:
    CONFIG.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _config_hash() -> str:
    try:
        return hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    except OSError:
        return ""


def append_log(record: dict) -> None:
    """One JSON object per line: who signed what, when, and against which file.

    No whole-file snapshot, unlike the concentration log. That log carries one
    because it also runs an external-edit detector that diffs against it; there
    is no such detector here yet, and a snapshot nothing reads is a large field
    that looks like an audit guarantee without being one.
    """
    record = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              **record}
    try:
        CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGE_LOG, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        # A log we cannot write is worth printing, not worth failing a signature
        # over — but the operator has to be told the record did not land.
        print(f"⚠️  could not write {CHANGE_LOG.name} ({e}): {record}")


# ─────────────────────────────────────────────────────────────────────────────
# SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def _find_drug(doc: dict, name: str):
    for d in doc.get("drugs", []):
        if d.get("generic_name") == name:
            return d
    return None


def _select(drug: dict, indication: str, population: str, route: str):
    """(entry, error). Exactly one match or nothing — never a best guess."""
    want = {"indication": indication, "population": population, "route": route}
    hits = [e for e in drug.get("dose_entries", [])
            if all(str(e.get(k)) == want[k] for k in SELECTOR)]
    if not hits:
        lines = [f"  --indication {e.get('indication')!r} --population "
                 f"{e.get('population')!r} --route {e.get('route')!r}"
                 for e in drug.get("dose_entries", [])]
        return None, (f"no entry of {drug['generic_name']} matches "
                      f"{indication!r} / {population!r} / {route!r}. It has:\n"
                      + "\n".join(lines))
    if len(hits) > 1:
        # Cannot happen in the shipped file and must never start happening: a
        # selector that matches two entries would sign an unreviewed one.
        return None, (f"{len(hits)} entries of {drug['generic_name']} match "
                      f"that selector — refusing to guess which one you meant")
    return hits[0], ""


# ─────────────────────────────────────────────────────────────────────────────
# THE REFUSALS
# ─────────────────────────────────────────────────────────────────────────────

# reviewed_by and review_date hold PENDING_CLINICAL_SIGNOFF on every unsigned
# entry — that is what unsigned MEANS, and --sign is what overwrites them. They
# are excluded from the sentinel scan so the refusal names the field that is
# actually blocking rather than restating the question.
_SIGNATURE_FIELDS = ("signoff", "reviewed_by", "review_date")


def sign_refusal(entry: dict) -> str:
    """Why this entry may not be signed, or "" if it may.

    Judged on the entry as it WOULD read once signed: clinical content only,
    with the signature fields set aside. The signer and the date themselves are
    checked by the caller.
    """
    flags = entry.get("flags") or []

    content = {k: v for k, v in entry.items() if k not in _SIGNATURE_FIELDS}
    if dc.has_sentinel(content):
        leaked = sorted(k for k, v in content.items() if dc.has_sentinel(v))
        return (f"a {' / '.join(dc.SENTINELS)} sentinel is still in: "
                f"{', '.join(leaked)}")

    # Checked before the tier rule, because a half-written declaration is a
    # malformed entry rather than an unsourced one, and because a valid one
    # changes what the tier rule is allowed to accept.
    ok, why = dc._declaration_ok(entry)
    if not ok:
        return why
    declared = dc.is_owner_declared(entry)

    sources = entry.get("sources")
    if not isinstance(sources, list) or not sources:
        return "the entry cites no sources at all"
    tiers = {s.get("tier") for s in sources if isinstance(s, dict)}
    if not tiers & {1, 2} and not declared:
        return (f"every source is tier {sorted(t for t in tiers if t is not None)} "
                f"— tier 0 is the migration carrier, not clinical evidence, and "
                f"a signed entry needs at least one tier 1 or tier 2 citation, "
                f"or an explicit owner declaration under "
                f"{dc.OWNER_DECLARED}")

    if "SOURCE_CONFLICT" in flags:
        adj = str(entry.get("adjudication") or "").strip()
        if not adj or adj in dc.SENTINELS:
            grp = entry.get("conflict_group") or "?"
            return (f"flagged SOURCE_CONFLICT (group {grp!r}) with no "
                    f"adjudication — record which source wins and why before "
                    f"signing either side")

    if dc.MIGRATED_UNSOURCED in flags:
        return ("flagged MIGRATED_UNSOURCED — the dose is the pre-contract "
                "hardcode and no approved source states it. A tier 1 citation "
                "elsewhere in the entry does not source the NUMBER. Corroborate "
                "it and re-flag MIGRATION_CORROBORATED, retire it, or — if the "
                "owner is prepared to put a name to the number — declare it "
                f"under {dc.OWNER_DECLARED} with a full owner_declaration")

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────────────────────

def _entry_line(entry: dict) -> str:
    dr = entry.get("dose_range")
    if isinstance(dr, dict):
        lo, hi, u = dr.get("min"), dr.get("max"), dr.get("units")
        dose = f"{lo:g}-{hi:g} {u}" if lo != hi else f"{lo:g} {u}"
    else:
        dose = str(dr)
    # The marker rides on the line every command prints — --list, the signing
    # confirmation, the unsign confirmation — because "which of these rests on
    # the owner rather than a guideline" is a question the person holding the
    # pen should not have to open the JSON to answer.
    declared = "  [OWNER-DECLARED]" if dc.is_owner_declared(entry) else ""
    return (f"{entry.get('indication')} · {entry.get('population')} · "
            f"{entry.get('route')} — {dose}{declared}")


def cmd_list(only: str = None) -> int:
    """Three states, not two.

    "unsigned" alone is the number the owner already knows. What the signing
    pass needs is the split inside it: which entries are waiting on a signature
    and which are waiting on WORK, because those are two different queues and
    only one of them is this tool's job.
    """
    signed = ready = blocked = 0
    if only and only not in dc.DRUGS:
        print(f"no such drug: {only}")
        return 1
    for name, drug in dc.DRUGS.items():
        if only and name != only:
            continue
        print(f"\n{name}"
              f"{'  [tropical]' if drug.get('tropical_priority') else ''}"
              f"  q={drug.get('discovery_query_count', 0)}")
        for e in drug.get("dose_entries", []):
            live, why = dc.entry_is_servable(e, drug)
            if live:
                signed += 1
                print(f"  SIGNED    {_entry_line(e)}  "
                      f"[{e.get('reviewed_by')} {e.get('review_date')}]")
                continue
            block = sign_refusal(e)
            if block:
                blocked += 1
                print(f"  BLOCKED   {_entry_line(e)}")
                print(f"            └─ {block}")
            elif e.get("signoff") is True:
                # Signed in the file but not servable: a bad signer, a missing
                # date, something the content check does not cover. Loud,
                # because a signature that does not serve looks like it does.
                blocked += 1
                print(f"  BROKEN    {_entry_line(e)}")
                print(f"            └─ signed but not servable: {why}")
            else:
                ready += 1
                print(f"  ready     {_entry_line(e)}")
    print(f"\n{signed} signed, {ready} ready to sign, "
          f"{blocked} blocked on work")
    unhonoured = dc.unhonoured_signatures()
    if unhonoured:
        # Called out separately from BROKEN above because this one cause is
        # invisible in the response — the dose just is not there — and it is
        # fixed by re-signing rather than by clinical work.
        print(f"\n⚠️  {len(unhonoured)} signature(s) NOT HONOURED — these serve nothing:")
        for name, ind, route, signer in unhonoured:
            print(f"  {name} · {ind} · {route}: signed by {signer!r}, "
                  f"not one of {', '.join(dc.SIGNOFF_AUTHORS)}")
        print("  Re-sign with --by from that list; put your name in --reason.")
    return 0


def cmd_sign(args) -> int:
    if not args.by or args.by not in dc.SIGNOFF_AUTHORS:
        print(f"REFUSED — --by must be one of "
              f"{', '.join(dc.SIGNOFF_AUTHORS)} (got {args.by!r})")
        return 1
    if not args.date:
        print("REFUSED — --date is required")
        return 1

    doc = _load_raw()
    drug = _find_drug(doc, args.drug)
    if drug is None:
        print(f"no such drug: {args.drug}")
        return 1
    entry, err = _select(drug, args.indication, args.population, args.route)
    if entry is None:
        print(err)
        return 1

    if entry.get("signoff") is True:
        print(f"already signed by {entry.get('reviewed_by')} on "
              f"{entry.get('review_date')} — nothing written")
        return 0

    # Validate BEFORE writing. The tool's own reasons first, then the engine's
    # gate on the candidate as it WOULD be written.
    reason = sign_refusal(entry)
    if reason:
        print(f"REFUSED — not signed: {reason}")
        return 1

    old_version = str(entry.get("version") or "")
    candidate = dict(entry, signoff=True, reviewed_by=args.by,
                     review_date=args.date,
                     version=old_version[:-len("-draft")]
                     if old_version.endswith("-draft") else old_version)
    ok, why = dc.entry_is_servable(candidate, drug)
    if not ok:
        print(f"REFUSED — not signed: the engine would not serve it: {why}")
        return 1

    entry.update(candidate)
    _save_raw(doc)
    append_log({"event": "SIGN", "drug": args.drug,
                "indication": args.indication, "population": args.population,
                "route": args.route,
                "dose_range": entry.get("dose_range"),
                "sources": [s.get("citation") for s in entry.get("sources", [])
                            if isinstance(s, dict)],
                # A declared dose is the one kind of signature where the audit
                # log cannot reconstruct the basis from the citations, because
                # there is no citation for the number. Record the declaration
                # itself, at the moment the signature lands.
                "owner_declared": dc.is_owner_declared(entry),
                "owner_declaration": entry.get("owner_declaration"),
                "version": [old_version, entry.get("version")],
                "signer": args.by, "date": args.date, "reason": args.reason,
                "config_hash": _config_hash()})
    print(f"signed {args.drug} · {_entry_line(entry)} "
          f"by {args.by} on {args.date}")
    return 0


def cmd_unsign(args) -> int:
    doc = _load_raw()
    drug = _find_drug(doc, args.drug)
    if drug is None:
        print(f"no such drug: {args.drug}")
        return 1
    entry, err = _select(drug, args.indication, args.population, args.route)
    if entry is None:
        print(err)
        return 1

    was = (entry.get("reviewed_by"), entry.get("review_date"))
    version = str(entry.get("version") or "")
    entry.update({"signoff": False, "reviewed_by": PENDING,
                  "review_date": PENDING,
                  "version": version if version.endswith("-draft")
                  else version + "-draft"})
    _save_raw(doc)
    append_log({"event": "UNSIGN", "drug": args.drug,
                "indication": args.indication, "population": args.population,
                "route": args.route,
                "dose_range": entry.get("dose_range"),
                "was_signed_by": list(was),
                "signer": args.by or "unspecified", "date": args.date,
                "reason": args.reason, "config_hash": _config_hash()})
    live = [e for e in drug.get("dose_entries", [])
            if dc.entry_is_servable(e, drug)[0]]
    print(f"unsigned {args.drug} · {_entry_line(entry)} — this drug now has "
          f"{len(live)} live entr{'y' if len(live) == 1 else 'ies'}"
          f"{' and serves no dose at all' if not live else ''}.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="signed/unsigned per entry, with the reason")
    ap.add_argument("--drug")
    ap.add_argument("--indication")
    ap.add_argument("--population", choices=list(dc.VALID_POPULATIONS))
    ap.add_argument("--route")
    ap.add_argument("--sign", action="store_true")
    ap.add_argument("--unsign", action="store_true")
    ap.add_argument("--by")
    ap.add_argument("--date")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()

    if args.sign and args.unsign:
        print("--sign and --unsign are opposites; pick one")
        return 1

    if args.list or not (args.sign or args.unsign):
        return cmd_list(args.drug)

    missing = [f"--{k}" for k in ("drug", "indication", "population", "route")
               if not getattr(args, k)]
    if missing:
        print(f"an entry is selected by drug + indication + population + "
              f"route; missing {', '.join(missing)}")
        return 1

    return cmd_sign(args) if args.sign else cmd_unsign(args)


if __name__ == "__main__":
    sys.exit(main())
