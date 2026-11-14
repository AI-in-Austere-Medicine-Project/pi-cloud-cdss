#!/usr/bin/env python3
"""Export the signed dose bank for EdgeCDSS Pocket.

    python3 server/tools/export_pocket_bank.py --out <dir> [--kit <path>]

Writes bank.json (every signed entry), kit.json (the kit's signed vials) and
manifest.json (bank version, EdgeCDSS commit, sha256 of both). Pocket has no
model and signs nothing, so this file is the whole of what it can say.

An unsigned entry cannot leave. drug_contracts.entry_is_servable() is the same
gate every serve path uses; the export refuses rather than filters in two
cases, because a smaller bank nobody decided on is a silent failure:
  - an entry marked signed that fails that gate;
  - anything unsigned reaching the writer, however the bank was built.

An entry with signoff false is simply not exported, and is counted. A drug with
nothing signed exports its names only, no number, so the device can say "no
signed dose for magnesium" rather than not recognising the word.

No clock in the output: the same commit and kit export the same bytes.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable, Optional

_SERVER = pathlib.Path(__file__).resolve().parents[1]
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

import drug_concentrations as cc  # noqa: E402
import drug_contracts as dc  # noqa: E402

DEFAULT_KIT = _SERVER / "drug_concentrations.json"
# The tracked files that decide what is exported. The kit is gitignored
# deployment state, so a commit cannot pin it: its hash is in the manifest.
PINNED = ("server/drug_contracts.json", "server/drug_contracts.py",
          "server/drug_concentrations.py", "server/tools/export_pocket_bank.py")


class ExportRefused(Exception):
    """This export must not happen. The reason names what to fix."""


# ── sources ────────────────────────────────────────────────────────────────
# "why" names one source, so it must be one that backs the dose. Many entries
# cite a page for another field: a contraindication list, or an age floor
# ("cited for the age floor only, not the dose"). Every source still travels in
# `sources`.
_OTHER_FIELD_CITATION = re.compile(r"\bonly\b|not the dose", re.IGNORECASE)
_OTHER_FIELD_SUPPORTS = re.compile(r"^\s*(?:contraindication|caution)", re.IGNORECASE)
_PAGE_IN_CITATION = re.compile(r"\bpp?\.\s*(\d+)")
_REPEAT = re.compile(r"\brepeat|\bredos|\bq\s?\d|\bevery \d", re.IGNORECASE)


def _page(source: dict) -> Optional[int]:
    if isinstance(source.get("page"), int):
        return source["page"]
    m = _PAGE_IN_CITATION.search(source.get("citation") or "")
    return int(m.group(1)) if m else None


def _named_source(entry: dict) -> tuple:
    """(source, basis). "dose": it states what it supports and that is the dose.
    "unstated": a citation that does not say which field it backs.
    "other-field": every citation says it backs another field."""
    cited = [s for s in entry["sources"] if s.get("tier") in (1, 2)]
    for s in cited:
        if (s.get("quote") and s.get("supports")
                and not _OTHER_FIELD_SUPPORTS.search(s["supports"])
                and not _OTHER_FIELD_CITATION.search(s["citation"])):
            return s, "dose"
    for s in cited:
        if not s.get("supports") and not _OTHER_FIELD_CITATION.search(s["citation"]):
            return s, "unstated"
    return cited[0], "other-field"


# ── one entry ──────────────────────────────────────────────────────────────

def export_entry(name: str, drug: dict, entry: dict, classify: Callable,
                 aliases: Optional[list] = None) -> dict:
    label = entry["indication"]
    cls = classify(label)
    if not cls:
        raise ExportRefused(f"{name} '{label}' falls in no indication class: "
                            "Pocket would have no word to ask for it")
    source, basis = _named_source(entry)
    declared = dc.is_owner_declared(entry)
    page, quote, named = _page(source), source.get("quote"), source["citation"]
    if declared:
        d = entry["owner_declaration"]
        named = f"Owner declaration, {d['declared_by']}, {d['declared_on']}"
        page, quote, basis = None, None, "owner-declaration"
    cautions = [{"text": dc.caution_text(c), "tier": dc.caution_tier(c)}
                for c in entry.get("cautions") or []]
    return {
        "drug": name,
        "aliases": sorted(set(aliases if aliases is not None else drug.get("aliases") or [])),
        "indication": label,
        "indication_class": cls,
        "population": entry["population"],
        "route": entry["route"],
        "rule": entry["dose_range"],
        "cap": {"max_single": entry.get("max_single"),
                "max_cumulative": entry.get("max_cumulative")},
        "floor": entry.get("min_single"),
        "min_age_months": entry.get("min_age_months"),
        # The signed wording, verbatim. The contract has no repeat field, so
        # this is never parsed into a number.
        "repeat": [c["text"] for c in cautions if _REPEAT.search(c["text"])],
        "cautions": cautions,
        "serve_cautions": dc.serve_cautions(entry),
        "contraindications": dc.serve_contraindications(entry),
        "dilution": dc.push_dilution(entry),
        "source": named,
        "source_basis": basis,
        "page": page,
        "quote": quote,
        "sources": entry["sources"],
        "owner_declared": declared,
        "signoff": entry["signoff"],
        "signer": entry["reviewed_by"],
        "date": entry["review_date"],
        "version": entry.get("version"),
    }


# ── the bank ───────────────────────────────────────────────────────────────

def _recognised_names() -> dict:
    """{term: generic} for every drug name EdgeCDSS recognises, each generic
    followed to the one it finally resolves to ("hypertonic saline" is an alias
    of sodium chloride 3% and a lexicon drug too)."""
    idx = dc.recognised_drug_index()
    return {t: idx.get(g, g) for t, g in idx.items()}


def build_bank(drugs: dict, version: str, classify: Optional[Callable] = None) -> dict:
    if classify is None:
        import openai_client  # the class table lives there; imported only when needed
        classify = openai_client.indication_class
    index = _recognised_names()

    entries, unsigned = [], 0
    for name, drug in drugs.items():
        aliases = set(drug.get("aliases") or []) | {
            t for t, g in index.items() if g == name and t != name.lower()}
        for entry in drug.get("dose_entries", []):
            if entry.get("signoff") is not True:
                unsigned += 1
                continue
            ok, why = dc.entry_is_servable(entry, drug)
            if not ok:
                raise ExportRefused(f"{name} '{entry.get('indication')}' "
                                    f"({entry.get('route')}) is marked signed and "
                                    f"fails the gate: {why}")
            entries.append(export_entry(name, drug, entry, classify, sorted(aliases)))

    signed = {e["drug"] for e in entries}
    unsigned_names = {}
    for name, drug in drugs.items():
        if name not in signed:
            unsigned_names.setdefault(name, set()).update(drug.get("aliases") or [])
    for term, generic in index.items():
        if generic not in signed:
            names = unsigned_names.setdefault(generic, set())
            if term != generic.lower():
                names.add(term)
    return {
        "bank_version": version,
        "entries": entries,
        "no_signed_dose": [{"drug": n, "aliases": sorted(a)}
                           for n, a in sorted(unsigned_names.items())],
        "unsigned_left_out": unsigned,
    }


# ── the kit ────────────────────────────────────────────────────────────────

def build_kit(path) -> dict:
    path = pathlib.Path(path)
    if "example" in path.name.lower():
        raise ExportRefused(f"{path.name} is the EXAMPLE kit, not a deployed one")
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ExportRefused(f"no readable kit at {path}: {e}") from e
    if "example" in str(raw.get("kit_id") or "").lower():
        raise ExportRefused(f"kit_id {raw.get('kit_id')!r} is an EXAMPLE kit")
    vials = []
    for item in raw.get("entries", []):
        for pres in item.get("presentations", []):
            if not cc.presentation_is_signed(pres):
                continue
            why = cc._validate(item, pres)
            if why:
                raise ExportRefused(f"{item['generic_name']} {pres.get('label_text')!r} "
                                    f"is signed and fails validation: {why}")
            vials.append({
                "drug": item["generic_name"],
                "label": pres.get("label_text"),
                "mass_mg": pres["mass_mg"],
                "volume_ml": pres["volume_ml"],
                "concentration_mg_ml": pres["concentration_mg_ml"],
                "confirm_required": bool(item.get("confirm_required")),
                "signer": pres["reviewed_by"],
                "date": pres["review_date"],
            })
    if not vials:
        raise ExportRefused(f"{path} has no signed vial: nothing to export")
    return {"kit_id": raw.get("kit_id"), "vials": vials}


# ── the last guard, and the writing ────────────────────────────────────────

def _signature_problem(item: dict) -> Optional[str]:
    if str(item.get("signer") or "").strip() not in dc.SIGNOFF_AUTHORS:
        return f"signer {item.get('signer')!r} is not an authorised signer"
    if not str(item.get("date") or "").strip():
        return "no signature date"
    if dc.has_sentinel(item):
        return "a sentinel survives in it"
    return None


def assert_signed(bank: dict, kit: dict) -> None:
    for e in bank["entries"]:
        why = ("signoff is not true" if e.get("signoff") is not True
               else _signature_problem(e))
        if why:
            raise ExportRefused(f"{e.get('drug')} '{e.get('indication')}': {why}")
    for v in kit["vials"]:
        why = _signature_problem(v)
        if why:
            raise ExportRefused(f"{v.get('drug')} vial {v.get('label')!r}: {why}")


def _dump(obj) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write_export(out, bank: dict, kit: dict, git: dict, inputs_sha256: dict) -> dict:
    assert_signed(bank, kit)
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    blobs = {"bank.json": _dump(bank), "kit.json": _dump(kit)}
    manifest = {
        "bank_version": bank["bank_version"],
        "edgecdss_commit": git["commit"],
        "edgecdss_commit_date": git["date"],
        "kit_id": kit["kit_id"],
        "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()},
        "inputs_sha256": inputs_sha256,
        "counts": {"entries": len(bank["entries"]),
                   "drugs": len({e["drug"] for e in bank["entries"]}),
                   "vials": len(kit["vials"]),
                   "no_signed_dose": len(bank["no_signed_dose"]),
                   "unsigned_left_out": bank["unsigned_left_out"]},
    }
    for name, blob in blobs.items():
        (out / name).write_bytes(blob)
    (out / "manifest.json").write_bytes(_dump(manifest))
    return manifest


def _git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(_SERVER), *args), check=True,
                          capture_output=True, text=True).stdout.strip()


def git_state() -> dict:
    """The commit, refusing when it is not what is being read."""
    dirty = _git("status", "--porcelain", "--", *(str(_SERVER.parent / p) for p in PINNED))
    if dirty:
        raise ExportRefused(f"uncommitted changes, so no commit describes this bank:\n{dirty}")
    return {"commit": _git("rev-parse", "HEAD"), "date": _git("log", "-1", "--format=%cs")}


def export(out, kit_path=DEFAULT_KIT) -> dict:
    git = git_state()
    contracts = _SERVER / "drug_contracts.json"
    schema = json.loads(contracts.read_text()).get("schema_version", "0")
    version = f"{schema}+{git['date']}.{git['commit'][:7]}"
    kit = build_kit(kit_path)
    bank = build_bank(dc.DRUGS, version)
    return write_export(out, bank, kit, git, {
        "drug_contracts.json": hashlib.sha256(contracts.read_bytes()).hexdigest(),
        "drug_concentrations.json": hashlib.sha256(
            pathlib.Path(kit_path).read_bytes()).hexdigest(),
    })


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--kit", type=pathlib.Path, default=DEFAULT_KIT,
                    help="the deployed drug_concentrations.json (gitignored)")
    args = ap.parse_args(argv)
    try:
        manifest = export(args.out, args.kit)
    except ExportRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
