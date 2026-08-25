#!/usr/bin/env python3
"""
Edit the concentration master list. The sanctioned path.

    python3 set_concentration.py --list
    python3 set_concentration.py --drug ketamine --sign "500 mg / 10 mL vial" \
            --by clinician --date 2026-08-25
    python3 set_concentration.py --drug ketamine --revoke "500 mg / 10 mL vial"
    python3 set_concentration.py --drug rocuronium --declare "100 mg / 10 mL vial" \
            --mass-mg 100 --volume-ml 10 --justification "standard stocked vial"

Hand-editing drug_concentrations.json works too, and the loader will detect and
log it on next import. This tool exists because it cannot get the guardrails
wrong: it validates before writing, refuses to sign anything the loader would
reject, and always clears signoff when a VALUE changes.

WHY SIGNING AND REVOKING ARE NOT SYMMETRIC
──────────────────────────────────────────
--sign requires --by from the authorised signer list. --revoke requires
nothing. Declaring a concentration is an authority claim about what is in the
bag; withdrawing one is a refusal to keep claiming it, and the system degrades
to milligram-only when it lands. If the kit changes mid-deployment and no
signer is reachable, anyone can pull the value in one command and the answer
gets less specific rather than wrong. Requiring a signature to REMOVE a
dangerous claim would be the failure mode this whole module exists to prevent.
"""
import argparse
import json
import sys

import drug_concentrations as dcn

PENDING = dcn.PENDING


def _load_raw():
    return json.loads(dcn.CONFIG.read_text())


def _save_raw(doc):
    dcn.CONFIG.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _find(doc, drug):
    for e in doc["entries"]:
        if e["generic_name"] == drug:
            return e
    return None


def _find_pres(entry, label):
    for p in entry.get("presentations", []):
        if p.get("label_text") == label:
            return p
    return None


def cmd_list():
    for name, entry in sorted(dcn.ENTRIES.items()):
        signed = dcn.signed_presentations(name)
        flag = " [confirm_required]" if entry.get("confirm_required") else ""
        print(f"\n{name}{flag}")
        for p in entry.get("presentations", []):
            state = "SIGNED  " if dcn.presentation_is_signed(p) else "unsigned"
            print(f"  {state} {p.get('label_text'):<26} "
                  f"{p['concentration_mg_ml']:>8g} mg/mL  "
                  f"[{p.get('corroboration')}]")
        status, conc, _ = dcn.resolve(name)
        served = f"{conc:g} mg/mL" if conc else "NO VOLUME SERVED"
        print(f"  -> {status}: {served}")
    if dcn.REJECTIONS:
        print("\nREJECTED (not stored):")
        for r in dcn.REJECTIONS:
            print(f"  {r.generic_name} {r.raw}: {r.reason}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--drug")
    ap.add_argument("--sign", metavar="LABEL")
    ap.add_argument("--revoke", metavar="LABEL")
    ap.add_argument("--declare", metavar="LABEL")
    ap.add_argument("--mass-mg", type=float)
    ap.add_argument("--volume-ml", type=float)
    ap.add_argument("--justification")
    ap.add_argument("--by")
    ap.add_argument("--date")
    ap.add_argument("--reason", default="")
    args = ap.parse_args()

    if args.list or not args.drug:
        cmd_list()
        return 0

    doc = _load_raw()
    entry = _find(doc, args.drug)
    if entry is None:
        print(f"no such drug: {args.drug}")
        return 1

    # ── revoke: no signature required, by design ────────────────────────────
    if args.revoke:
        pres = _find_pres(entry, args.revoke)
        if pres is None:
            print(f"no such presentation: {args.revoke}")
            return 1
        was = dcn.presentation_is_signed(pres)
        pres.update({"signoff": False, "reviewed_by": PENDING,
                     "review_date": PENDING})
        _save_raw(doc)
        dcn.append_log({"event": "REVOKE", "drug": args.drug,
                        "label": args.revoke, "old": [pres["concentration_mg_ml"], was],
                        "new": [pres["concentration_mg_ml"], False],
                        "actor": args.by or "unspecified", "reason": args.reason,
                        "config_hash": dcn._config_hash()})
        print(f"revoked {args.drug} {args.revoke} — this drug now serves "
              f"milligram doses with no volume until it is signed again.")
        return 0

    # ── declare a new presentation ──────────────────────────────────────────
    if args.declare:
        if args.mass_mg is None or args.volume_ml is None:
            print("--declare needs --mass-mg and --volume-ml (declare the vial "
                  "the way it is labelled; the concentration is derived)")
            return 1
        conc = round(args.mass_mg / args.volume_ml, 6)
        pres = {"label_text": args.declare, "mass_mg": args.mass_mg,
                "volume_ml": args.volume_ml, "concentration_mg_ml": conc,
                "source_note": args.reason or "declared via set_concentration.py",
                "justification": args.justification,
                "signoff": False, "reviewed_by": PENDING, "review_date": PENDING,
                "version": "0.1.0-draft"}
        reason = dcn._validate(entry, pres)
        if reason:
            print(f"REJECTED — not written: {reason}")
            return 1
        entry.setdefault("presentations", []).append(pres)
        _save_raw(doc)
        dcn.append_log({"event": "DECLARE", "drug": args.drug,
                        "label": args.declare, "old": None, "new": [conc, False],
                        "actor": args.by or "unspecified", "reason": args.reason,
                        "config_hash": dcn._config_hash()})
        print(f"declared {args.drug} {args.declare} = {conc:g} mg/mL, UNSIGNED. "
              f"Sign it before any volume is served.")
        return 0

    # ── sign: requires an authorised signer ─────────────────────────────────
    if args.sign:
        if not args.by or args.by not in dcn.SIGNOFF_AUTHORS:
            print(f"--by must be one of {', '.join(dcn.SIGNOFF_AUTHORS)}")
            return 1
        if not args.date:
            print("--date is required")
            return 1
        pres = _find_pres(entry, args.sign)
        if pres is None:
            print(f"no such presentation: {args.sign}")
            return 1
        candidate = dict(pres, signoff=True, reviewed_by=args.by,
                         review_date=args.date)
        candidate.setdefault("corroboration",
                             dcn._corroboration(args.drug,
                                                candidate["concentration_mg_ml"]))
        reason = dcn._validate(entry, candidate)
        if reason:
            print(f"REFUSED — not signed: {reason}")
            return 1
        old = [pres["concentration_mg_ml"], dcn.presentation_is_signed(pres)]
        pres.update(candidate)
        _save_raw(doc)
        dcn.append_log({"event": "SIGN", "drug": args.drug, "label": args.sign,
                        "old": old,
                        "new": [pres["concentration_mg_ml"], True],
                        "actor": args.by, "reason": args.reason,
                        "config_hash": dcn._config_hash()})
        print(f"signed {args.drug} {args.sign} = "
              f"{pres['concentration_mg_ml']:g} mg/mL by {args.by} on {args.date}")
        return 0

    cmd_list()
    return 0


if __name__ == "__main__":
    sys.exit(main())
