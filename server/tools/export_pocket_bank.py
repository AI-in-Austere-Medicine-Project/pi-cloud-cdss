#!/usr/bin/env python3
"""Export the signed dose bank for EdgeCDSS Pocket.

    python3 server/tools/export_pocket_bank.py --out <dir> [--set PFC|EMS] [--kit <path>]
    python3 server/tools/export_pocket_bank.py --out <dir> --test [--entries <path>] [--kit <path>]

Writes bank.json (every signed entry of ONE drug set), kit.json (that set's
kit: its signed vials) and manifest.json (set, bank version, EdgeCDSS commit,
sha256 of both). One bank per set (owner, 2026-11-12): PFC is the JTS/SMOG
bank, EMS the agency formulary; an entry of another set never enters a set's
bank, and its drug is a "no signed dose" name there. Pocket has no
model and signs nothing, so this file is the whole of what it can say.

An unsigned entry cannot leave. drug_contracts.entry_is_servable() is the same
gate every serve path uses; the export refuses rather than filters in two
cases, because a smaller bank nobody decided on is a silent failure:
  - an entry marked signed that fails that gate;
  - anything unsigned reaching the writer, however the bank was built.

An entry with signoff false is simply not exported, and is counted. A drug with
nothing signed exports its names only, no number, so the device can say "no
signed dose for magnesium" rather than not recognising the word.

--test (owner, 2026-11-13) writes the EMS-TEST bench bank instead:
bank-ems-test.json, kit-ems-test.json (the EMS kit's signed vials) and
manifest-ems-test.json with "test": true. Its entries are unsigned, status
"test", read from a gitignored file (they reproduce the agency's formulary),
and each carries check_failed (the reasons Pocket says "unverified"). EdgeCDSS
never serves them (drug_contracts.TEST_SETS); only this flag exports them, and
without it the writer still refuses anything unsigned. A test bank holds test
entries only, and the flag never relabels a signed bank.

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
# Each set has its own kit (deployment state, gitignored like the PFC kit).
DEFAULT_KITS = {"PFC": DEFAULT_KIT, "EMS": _SERVER / "drug_concentrations_ems.json"}
# EMS-TEST: unsigned bench entries (gitignored; the agency's formulary as
# transcribed). Its kit is the EMS kit: only signed vials ever leave.
TEST_SET = "EMS-TEST"
DEFAULT_TEST_ENTRIES = _SERVER / "drug_contracts_ems_test.json"
DEFAULT_KITS[TEST_SET] = DEFAULT_KITS["EMS"]
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
    # An EMS entry names its class (the PFC class table is not the EMS
    # formulary's); a PFC entry's class comes from the server's table.
    cls = entry.get("indication_class") or classify(label)
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
        "set": entry["set"],
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
        **({"kit_vial": entry["kit_vial"]} if "kit_vial" in entry else {}),
    }


# ── the bank ───────────────────────────────────────────────────────────────

def _recognised_names() -> dict:
    """{term: generic} for every drug name EdgeCDSS recognises, each generic
    followed to the one it finally resolves to ("hypertonic saline" is an alias
    of sodium chloride 3% and a lexicon drug too)."""
    idx = dc.recognised_drug_index()
    return {t: idx.get(g, g) for t, g in idx.items()}


def build_bank(drugs: dict, version: str, classify: Optional[Callable] = None,
               set_name: str = "PFC") -> dict:
    if set_name not in dc.KNOWN_SETS:
        raise ExportRefused(f"{set_name!r} is not a drug set ({', '.join(dc.KNOWN_SETS)})")
    if classify is None:
        import openai_client  # the class table lives there; imported only when needed
        classify = openai_client.indication_class
    index = _recognised_names()

    entries, unsigned, other_set = [], 0, 0
    for name, drug in drugs.items():
        aliases = set(drug.get("aliases") or []) | {
            t for t, g in index.items() if g == name and t != name.lower()}
        for entry in drug.get("dose_entries", []):
            if entry.get("set") in dc.KNOWN_SETS and entry["set"] != set_name:
                other_set += 1
                continue
            if entry.get("signoff") is not True:
                unsigned += 1
                continue
            ok, why = dc.entry_is_servable(entry, drug, served_set=set_name)
            if not ok:
                raise ExportRefused(f"{name} '{entry.get('indication')}' "
                                    f"({entry.get('route')}) is marked signed and "
                                    f"fails the gate: {why}")
            entries.append(export_entry(name, drug, entry, classify, sorted(aliases)))

    return {
        "set": set_name,
        "bank_version": version,
        "entries": entries,
        "no_signed_dose": _no_dose_names(drugs, {e["drug"] for e in entries}, index),
        "unsigned_left_out": unsigned,
        "other_set_left_out": other_set,
    }


def _no_dose_names(drugs: dict, dosed: set, index: dict) -> list:
    """Every recognised drug with no entry in this bank: its names, no number."""
    unsigned_names = {}
    for name, drug in drugs.items():
        if name not in dosed:
            unsigned_names.setdefault(name, set()).update(drug.get("aliases") or [])
    for term, generic in index.items():
        if generic not in dosed:
            names = unsigned_names.setdefault(generic, set())
            if term != generic.lower():
                names.add(term)
    return [{"drug": n, "aliases": sorted(a)} for n, a in sorted(unsigned_names.items())]


# ── the test bank (EMS-TEST, bench testing only) ──────────────────────────

def _test_entry_problem(entry: dict) -> Optional[str]:
    if entry.get("set") != TEST_SET:
        return f"set {entry.get('set')!r} is not {TEST_SET}: a test bank holds test entries only"
    if entry.get("status") != "test":
        return f"status {entry.get('status')!r} is not \"test\""
    if entry.get("signoff") is True:
        return "it is marked signed: a test bank holds unsigned test entries only"
    cf = entry.get("check_failed")
    if not isinstance(cf, list) or not all(isinstance(x, str) and x.strip() for x in cf):
        return "check_failed must be a list of reasons (empty when every check passed)"
    ok, why = dc._dose_range_ok(entry.get("dose_range"))
    if ok:
        dr = entry["dose_range"]
        kind, _, why = dc.classify_units(dr.get("units"), dr.get("per_kg"))
        ok = kind != dc.UNKNOWN
    if not ok:
        return f"dose: {why}"
    if entry.get("population") not in dc.VALID_POPULATIONS:
        return f"population {entry.get('population')!r}"
    if entry.get("route") not in ("IV", "IM", "IN", "PO", "NEB"):
        return f"route {entry.get('route')!r}"
    if not any(s.get("tier") in (1, 2) for s in entry.get("sources") or []):
        return "no tier 1 or 2 source"
    return None


def build_test_bank(doc: dict, version: str) -> dict:
    """The EMS-TEST bank: every entry of the test file, unsigned, status "test",
    with its check_failed reasons. Refused, not filtered, when anything in it is
    not a test entry."""
    entries = []
    for drug in doc.get("drugs") or []:
        name = drug["generic_name"]
        for entry in drug.get("dose_entries") or []:
            why = _test_entry_problem(entry)
            if why:
                raise ExportRefused(f"{name} '{entry.get('indication')}' "
                                    f"({entry.get('route')}): {why}")
            e = export_entry(name, drug, entry, classify=lambda _l: None)
            e.update(status="test", check_failed=list(entry["check_failed"]))
            entries.append(e)
    if not entries:
        raise ExportRefused("the test file holds no entry")
    names = {d["generic_name"]: d for d in doc["drugs"]}
    return {
        "set": TEST_SET,
        "test": True,
        "bank_version": version,
        "entries": entries,
        "no_signed_dose": _no_dose_names(dict(dc.DRUGS, **names),
                                         {e["drug"] for e in entries}, _recognised_names()),
        "unsigned_left_out": 0,
        "other_set_left_out": 0,
    }


def assert_test(bank: dict, kit: dict) -> None:
    """The test writer's guard: test entries only, and the kit still signed."""
    if bank.get("test") is not True or bank.get("set") != TEST_SET:
        raise ExportRefused(f"--test writes the {TEST_SET} bank only; this is the "
                            f"{bank.get('set')} bank")
    for e in bank["entries"]:
        if e.get("status") != "test" or e.get("set") != TEST_SET or e.get("signoff") is True:
            raise ExportRefused(f"{e.get('drug')} '{e.get('indication')}': not a test entry")
    for v in kit["vials"]:
        why = _signature_problem(v)
        if why:
            raise ExportRefused(f"{v.get('drug')} vial {v.get('label')!r}: {why}")


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


def file_names(set_name: str) -> dict:
    """PFC keeps the names Pocket already reads; another set's files say its set."""
    sfx = "" if set_name == "PFC" else f"-{set_name.lower()}"
    return {k: f"{k}{sfx}.json" for k in ("bank", "kit", "manifest")}


def write_export(out, bank: dict, kit: dict, git: dict, inputs_sha256: dict,
                 test: bool = False) -> dict:
    if test:
        assert_test(bank, kit)
    elif bank.get("test") or bank.get("set") in dc.TEST_SETS:
        raise ExportRefused(f"a {bank.get('set')} bank is a test bank: it is written only with --test")
    else:
        assert_signed(bank, kit)
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names = file_names(bank["set"])
    blobs = {names["bank"]: _dump(bank), names["kit"]: _dump(kit)}
    manifest = {
        "set": bank["set"],
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
                   "unsigned_left_out": bank["unsigned_left_out"],
                   "other_set_left_out": bank["other_set_left_out"]},
    }
    if test:
        manifest["test"] = True
        manifest["counts"]["check_failed"] = sum(bool(e["check_failed"]) for e in bank["entries"])
    for name, blob in blobs.items():
        (out / name).write_bytes(blob)
    (out / names["manifest"]).write_bytes(_dump(manifest))
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


def export(out, kit_path=None, set_name="PFC", test=False, entries_path=None) -> dict:
    if test:
        return export_test(out, kit_path, entries_path)
    kit_path = DEFAULT_KITS[set_name] if kit_path is None else kit_path
    git = git_state()
    contracts = _SERVER / "drug_contracts.json"
    schema = json.loads(contracts.read_text()).get("schema_version", "0")
    version = f"{schema}+{git['date']}.{git['commit'][:7]}"
    kit = build_kit(kit_path)
    bank = build_bank(dc.DRUGS, version, set_name=set_name)
    return write_export(out, bank, kit, git, {
        "drug_contracts.json": hashlib.sha256(contracts.read_bytes()).hexdigest(),
        pathlib.Path(kit_path).name: hashlib.sha256(
            pathlib.Path(kit_path).read_bytes()).hexdigest(),
    })


def export_test(out, kit_path=None, entries_path=None) -> dict:
    """The EMS-TEST bench bank. The entries file is gitignored, so the commit
    cannot pin it: its hash is in the manifest, beside the kit's."""
    kit_path = pathlib.Path(DEFAULT_KITS[TEST_SET] if kit_path is None else kit_path)
    entries_path = pathlib.Path(DEFAULT_TEST_ENTRIES if entries_path is None else entries_path)
    git = git_state()
    try:
        doc = json.loads(entries_path.read_text())
    except (OSError, ValueError) as e:
        raise ExportRefused(f"no readable test entries at {entries_path}: {e}") from e
    if doc.get("set") != TEST_SET or doc.get("test") is not True:
        raise ExportRefused(f"{entries_path.name} is not an {TEST_SET} file (set and test:true)")
    version = f"{doc.get('schema_version', '0')}+{git['date']}.{git['commit'][:7]}.test"
    kit = build_kit(kit_path)
    bank = build_test_bank(doc, version)
    return write_export(out, bank, kit, git, {
        entries_path.name: hashlib.sha256(entries_path.read_bytes()).hexdigest(),
        kit_path.name: hashlib.sha256(kit_path.read_bytes()).hexdigest(),
    }, test=True)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=pathlib.Path)
    class _Set(argparse.Action):  # remembers that --set was given, for --test
        def __call__(self, parser, ns, value, option_string=None):
            ns.set, ns.set_given = value, True

    ap.set_defaults(set_given=False)
    ap.add_argument("--set", default="PFC", choices=dc.KNOWN_SETS, action=_Set,
                    help="the drug set to export (one bank per set; default PFC)")
    ap.add_argument("--test", action="store_true",
                    help=f"write the {TEST_SET} bench bank (unsigned, test:true; never served)")
    ap.add_argument("--entries", type=pathlib.Path, default=None,
                    help="with --test: the test entries file (gitignored; default "
                         "server/drug_contracts_ems_test.json)")
    ap.add_argument("--kit", type=pathlib.Path, default=None,
                    help="the set's deployed kit (gitignored; default "
                         "drug_concentrations.json for PFC, drug_concentrations_ems.json for EMS)")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.test and args.set_given:
            raise ExportRefused(f"--test exports the {TEST_SET} set only, not {args.set}")
        if args.entries is not None and not args.test:
            raise ExportRefused("--entries is the test entries file: it needs --test")
        manifest = export(args.out, args.kit, args.set, test=args.test,
                          entries_path=args.entries)
    except ExportRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
