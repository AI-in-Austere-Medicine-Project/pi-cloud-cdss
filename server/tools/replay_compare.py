"""Replay comparison: which rows a change moved, newly held or newly released.

The replays (served, held, gate, log, pipe) each write one JSON object per
tree, {row key: row}. This compares a before tree's output with an after
tree's and lists the rows that changed, the rows newly held and the rows newly
released. The standing rule is 0 newly released; every one is listed for the
owner.

    python tools/replay_compare.py <dir> [--before main] [--after new]

reads <dir>/<kind>_<before>.json and <dir>/<kind>_<after>.json for each kind.
"""
import argparse
import json
import os
import sys

KINDS = ("served", "held", "gate", "log", "pipe")


# What build_safety_hold writes first (openai_client). A test pins the two
# together.
HOLD_HEADER = "Clinical safety hold. This response was blocked."


def is_hold(row):
    """True if the medic got a hold, False if they got anything else, None if
    the row cannot say.

    Owner, 2026-10-23 (#178 review): a row is newly released when it was a
    hold and now serves anything (card, dose, question), regardless of the
    verdict label. So each replay is judged by what it served:
    - pipe: the served response is the safety hold. A question
      (SKIPPED_SAFE_GATE), a card (DETERMINISTIC_CHECKED), a reviewed answer
      (NEEDS_HUMAN_REVIEW) and a new-patient notice all serve.
    - gate: the gate blocked it. Its issues are the recorded validator's, the
      same on both trees, and say nothing about this tree.
    - served, held, log: the deterministic check returned issues.
    """
    if not isinstance(row, dict):
        return None
    if "response" in row:
        return HOLD_HEADER in (row.get("response") or "")
    if "blocked" in row:
        return bool(row["blocked"])
    if "issues" in row:
        return bool(row["issues"])
    if "held" in row:
        return bool(row["held"])
    return None


def compare(before: dict, after: dict) -> dict:
    keys = sorted(set(before) | set(after))
    changed = [k for k in keys if before.get(k) != after.get(k)]
    return {
        "rows": len(after),
        "rows_before": len(before),
        "changed": changed,
        "newly_held": [k for k in changed
                       if is_hold(before.get(k)) is False and is_hold(after.get(k)) is True],
        "newly_released": [k for k in changed
                           if is_hold(before.get(k)) is True and is_hold(after.get(k)) is False],
        # A changed row either side cannot judge: listed, never counted as safe.
        "unknown": [k for k in changed
                    if (k in before and is_hold(before[k]) is None)
                    or (k in after and is_hold(after[k]) is None)],
    }


def _brief(row):
    if not isinstance(row, dict):
        return json.dumps(row)
    return json.dumps({k: v for k, v in row.items() if k != "response"}, ensure_ascii=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir")
    ap.add_argument("--before", default="main")
    ap.add_argument("--after", default="new")
    args = ap.parse_args(argv)
    for kind in KINDS:
        a_path = os.path.join(args.dir, f"{kind}_{args.before}.json")
        b_path = os.path.join(args.dir, f"{kind}_{args.after}.json")
        if not (os.path.exists(a_path) and os.path.exists(b_path)):
            continue
        a, b = json.load(open(a_path)), json.load(open(b_path))
        r = compare(a, b)
        print(f"{kind}: rows {r['rows']} (before {r['rows_before']}), changed {len(r['changed'])}, "
              f"newly held {len(r['newly_held'])}, newly released {len(r['newly_released'])}, "
              f"unjudged {len(r['unknown'])}")
        for label in ("newly_released", "newly_held", "unknown"):
            for k in r[label]:
                print(f"    [{label}] {k[:160]}")
        for k in r["changed"]:
            print("   ", k[:110])
            for side, row in (("before", a.get(k)), ("after", b.get(k))):
                print(f"      {side}: {_brief(row)[:700]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
