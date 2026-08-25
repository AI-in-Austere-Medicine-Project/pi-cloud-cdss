#!/usr/bin/env python3
"""
Generate DRUG_CONTRACT_WORKSHEET.md from drug_contracts.json and the engine.

Generated, not written by hand, so it cannot drift from what the engine
actually requires. Re-run after every authoring pass:

    cd server && python3 gen_drug_worksheet.py

ORDER IS THE POINT. Sections come out in signing order:

    1. drugs ranked by MEASURED dose-query traffic in the v4.3 discovery run
    2. the tropical/austere priority subset
    3. everything else

so the review slots go where the queries actually are, and the
deployment-relevant tropical drugs can be signed early without wading through
the whole file.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import drug_contracts as dc  # noqa: E402

OUT = pathlib.Path(__file__).parent / "DRUG_CONTRACT_WORKSHEET.md"

FIELD_HELP = {
    "dose_range": "min/max, units, per_kg — the numbers the medic acts on",
    "max_single": "ceiling for one administration; null = source states none",
    "max_cumulative": "ceiling across the encounter; null = source states none",
    "contraindications": "absolute 'do not give' list",
    "cautions": "shown with the dose on every serve",
    "sources": "one {citation, tier, url, retrieved_date} per source",
}


def _tier_label(tier):
    return {0: "tier 0 (migration — NOT an approved source)",
            1: "tier 1 (NASEMSO)", 2: "tier 2 (WHO EML)"}.get(tier, f"tier {tier}")


def entry_block(L, drug_name, e, n):
    ok, why = dc.entry_is_servable(e)
    status = "✅ LIVE" if ok else f"⬜ not live — {why}"
    L.append(f"#### {n}. {e.get('indication')} · {e.get('population')} · "
             f"{e.get('route')}")
    L.append("")
    L.append(f"- **status:** {status}")

    flags = e.get("flags") or []
    if flags:
        L.append(f"- **flags:** {', '.join(f'`{f}`' for f in flags)}")
    if "SOURCE_CONFLICT" in flags:
        L.append("  - ⚠️ **SOURCE CONFLICT — both entries are kept and neither "
                 "was picked.** Sign the one you adjudicate to and write why "
                 "in `adjudication`; the engine refuses a signed conflict that "
                 "has no adjudication note.")
    if "CONCENTRATION_MISMATCH" in flags:
        L.append("  - ⚠️ **CONCENTRATION MISMATCH** between the migrated "
                 "calculator and the WHO-listed strength. A wrong "
                 "concentration is a wrong volume at the syringe — resolve "
                 "before signing.")
    if "MIGRATED_UNSOURCED" in flags:
        L.append("  - ⚠️ **MIGRATED, UNSOURCED.** Value carried over verbatim "
                 "from the pre-contract hardcode. The engine will NOT let this "
                 "be signed until a tier 1 or tier 2 citation is attached.")

    dr = e.get("dose_range")
    if dr == dc.NEEDS_MANUAL:
        L.append("- **dose_range:** ❌ `NEEDS_MANUAL_ENTRY`")
    elif isinstance(dr, dict):
        per = "per kg" if dr.get("per_kg") else "flat"
        rng = (f"{dr.get('min')}" if dr.get("min") == dr.get("max")
               else f"{dr.get('min')}–{dr.get('max')}")
        L.append(f"- **dose_range:** `{rng} {dr.get('units')}` ({per})")

    for f in ("max_single", "max_cumulative"):
        v = e.get(f)
        if v == dc.NEEDS_MANUAL:
            L.append(f"- **{f}:** ❌ `NEEDS_MANUAL_ENTRY`")
        elif v is None:
            L.append(f"- **{f}:** none stated by the cited source")
        elif isinstance(v, dict):
            L.append(f"- **{f}:** `{v.get('rule') or v}`")

    for f in ("contraindications", "cautions"):
        v = e.get(f) or []
        if any(x in dc.SENTINELS for x in v if isinstance(x, str)):
            L.append(f"- **{f}:** ❌ `NEEDS_MANUAL_ENTRY`")
        else:
            for x in v:
                L.append(f"- **{f}:** {x}")

    srcs = e.get("sources") or []
    if not srcs:
        L.append("- **sources:** ❌ none — no approved source supports this "
                 "entry yet")
    for s in srcs:
        rd = s.get("retrieved_date")
        rd = "❌ NOT RETRIEVED" if rd == dc.NEEDS_MANUAL else rd
        L.append(f"- **source:** {_tier_label(s.get('tier'))} — "
                 f"{s.get('citation')} · retrieved {rd}")

    if e.get("extraction_notes"):
        L.append(f"- **why no value was written:** {e['extraction_notes']}")
    L.append("")


def drug_block(L, name, drug):
    entries = drug.get("dose_entries", [])
    live = sum(1 for e in entries if dc.entry_is_servable(e)[0])
    rank = drug.get("discovery_rank")
    qn = drug.get("discovery_query_count", 0)

    head = f"### {name}"
    if rank:
        head += f"  — discovery rank #{rank}, {qn} dose queries"
    elif drug.get("tropical_priority"):
        head += "  — tropical/austere subset"
    L.append(head)
    L.append("")
    L.append(f"**{live} of {len(entries)} entries live.** "
             f"class: {drug.get('drug_class')} · "
             f"routes: {', '.join(drug.get('routes') or [])}")
    L.append("")

    aliases = drug.get("aliases") or []
    L.append(f"- **aliases (live, word-anchored):** "
             f"{', '.join(f'`{a}`' for a in aliases) if aliases else '—'}")
    if drug.get("proposed_aliases"):
        L.append(f"- **aliases PROPOSED, not live:** "
                 f"{', '.join(f'`{a}`' for a in drug['proposed_aliases'])} — "
                 f"promoting one of these makes the system answer a query it "
                 f"currently refuses. Your call, not the migration's.")
    for f in drug.get("forms") or []:
        desc = f.get("description")
        if desc == dc.NEEDS_MANUAL:
            L.append("- **form:** ❌ `NEEDS_MANUAL_ENTRY`")
        else:
            conc = f.get("concentration_mg_ml")
            conc = f" — **{conc:g} mg/mL**" if isinstance(conc, (int, float)) else ""
            L.append(f"- **form:** {desc}{conc}")
    if dc.single_concentration(name) is None:
        L.append("- ⚠️ **no single concentration** — the engine cannot turn a "
                 "mg dose into a syringe volume for this drug until exactly "
                 "one form carries `concentration_mg_ml`. It refuses rather "
                 "than picking one.")
    if drug.get("notes"):
        L.append(f"- **note:** {drug['notes']}")
    L.append("")

    for i, e in enumerate(entries, 1):
        entry_block(L, name, e, i)


def main():
    drugs = dc.DRUGS
    raw = json.loads((dc._DIR / "drug_contracts.json").read_text())

    ranked = sorted((d for d in drugs.values() if d.get("discovery_rank")),
                    key=lambda d: d["discovery_rank"])
    ranked_names = {d["generic_name"] for d in ranked}
    tropical = [drugs[n] for n in dc.tropical_priority_drugs()
                if n not in ranked_names]
    tropical_names = {d["generic_name"] for d in tropical}
    rest = [d for n, d in drugs.items()
            if n not in ranked_names and n not in tropical_names]

    total_entries = sum(len(d["dose_entries"]) for d in drugs.values())
    live_entries = sum(len(v) for v in dc.servable_entries().values())

    L = []
    L.append("# Drug dose contracts — content worksheet")
    L.append("")
    L.append("**Author: a credentialed clinician. Nobody else signs an entry.**")
    L.append("")
    L.append("Generated by `server/gen_drug_worksheet.py` from "
             "`drug_contracts.json` and the engine schema, so it cannot drift "
             "from what the engine actually requires. Re-run it after every "
             "authoring pass.")
    L.append("")
    L.append(f"**{live_entries} of {total_entries} dose entries live, across "
             f"{len(drugs)} drugs.**")
    L.append("")

    L.append("## Read this before signing anything")
    L.append("")
    L.append("Entries deploy **one at a time**. Partial deployment is the "
             "normal state, not a migration step — an unsigned entry is "
             "invisible to the pipeline and the query falls through to the "
             "empty-contract fallback that answered it before.")
    L.append("")
    L.append("1. Fill every field marked ❌ for that entry.")
    L.append("2. Attach at least one **tier 1 or tier 2** source. The engine "
             "refuses an entry sourced only to tier 0 (the migration carrier), "
             "no matter who signs it.")
    L.append("3. Set `reviewed_by` to exactly one of "
             f"`{'`, `'.join(dc.SIGNOFF_AUTHORS)}` and `review_date` to the "
             "date you signed it.")
    L.append("4. Set `signoff: true`.")
    L.append("5. Re-run this script and confirm the entry reads ✅ LIVE.")
    L.append("")
    L.append("A signed entry carrying `PENDING_CLINICAL_SIGNOFF` or "
             "`NEEDS_MANUAL_ENTRY` **anywhere** — including in a caution, a "
             "note or a source record — is refused. Signing does not launder "
             "an unauthored field.")
    L.append("")

    L.append("## Source status")
    L.append("")
    for key, label in (("tier_1", "Tier 1"), ("tier_2", "Tier 2")):
        s = raw["approved_sources"][key]
        L.append(f"- **{label} — {s['citation']}**")
        L.append(f"  - {s['retrieval_status']}")
        if s.get("scope_warning"):
            L.append(f"  - ⚠️ {s['scope_warning']}")
    L.append("")

    L.append("## Signing order")
    L.append("")
    L.append("| # | drug | dose queries | live / total | group |")
    L.append("|---|---|---|---|---|")
    for d in ranked:
        n = d["generic_name"]
        live = sum(1 for e in d["dose_entries"] if dc.entry_is_servable(e)[0])
        group = "traffic" + (" + tropical" if d.get("tropical_priority") else "")
        L.append(f"| {d['discovery_rank']} | {n} | "
                 f"{d['discovery_query_count']} | {live} / "
                 f"{len(d['dose_entries'])} | {group} |")
    for d in tropical:
        n = d["generic_name"]
        live = sum(1 for e in d["dose_entries"] if dc.entry_is_servable(e)[0])
        L.append(f"| — | {n} | 0 | {live} / {len(d['dose_entries'])} | "
                 f"tropical |")
    for d in rest:
        n = d["generic_name"]
        live = sum(1 for e in d["dose_entries"] if dc.entry_is_servable(e)[0])
        L.append(f"| — | {n} | 0 | {live} / {len(d['dose_entries'])} | other |")
    L.append("")

    L.append("---")
    L.append("")
    L.append("## Group 1 — ranked by measured dose-query traffic")
    L.append("")
    L.append("Order is the v4.3 discovery run, round 3: 125 dose-seeking "
             "scenarios, drug mentions counted word-anchored across query and "
             "history, RSI-bundle scenarios attributed to the bundle drugs. "
             "Sign down this list and the review effort lands where the "
             "queries actually are.")
    L.append("")
    for d in ranked:
        drug_block(L, d["generic_name"], d)

    L.append("---")
    L.append("")
    L.append("## Group 2 — tropical / austere priority subset")
    L.append("")
    L.append("The deployment's actual disease burden, and almost entirely "
             "absent from NASEMSO. These drew no dose queries in the discovery "
             "run because the run's scenario bank is trauma-shaped — that is a "
             "fact about the bank, not about the deployment. Sign these early "
             "if the deployment is the reason they are here.")
    L.append("")
    for d in tropical:
        drug_block(L, d["generic_name"], d)

    if rest:
        L.append("---")
        L.append("")
        L.append("## Group 3 — everything else")
        L.append("")
        for d in rest:
            drug_block(L, d["generic_name"], d)

    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")
    print(f"{live_entries} of {total_entries} entries live across {len(drugs)} drugs")
    if dc.ALIAS_COLLISIONS:
        print("⚠️  ALIAS COLLISIONS:")
        for p in dc.ALIAS_COLLISIONS:
            print(f"   - {p}")


if __name__ == "__main__":
    main()
