"""Replay comparison: which rows a change moved, newly held or newly released.

The replays (served, held, gate, log, pipe) each write one JSON object per
tree, {row key: row}. This compares a before tree's output with an after
tree's and lists the rows that changed, the rows newly held and the rows newly
released, and the rows that newly dose. The standing rule is 0 newly
released; every released row and every newly dosing row is listed for the
owner's sign-off.

    python tools/replay_compare.py <dir> [--before main] [--after new]

reads <dir>/<kind>_<before>.json and <dir>/<kind>_<after>.json for each kind.
"""
import argparse
import json
import os
import re
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


# The pipeline replay's stubbed generator answer (pipe_replay.py).
STUB_ANSWER = "STUB"

# A dose: a number (or range) with a mass or unit, rates included
# ("5-20 mcg", "18.75 mg", "0.05-0.3 mcg/kg/min", "7.5 g", "2 g"). A volume
# alone is not a dose: the drawn volume is always printed with its mg, and
# a recipe ("1 mL of 1:10,000 in 9 mL NS") doses nothing.
_DOSE_RE = re.compile(
    r"\b\d+(?:\.\d+)?(?:\s*(?:-|–|to)\s*\d+(?:\.\d+)?)?\s*"
    r"(?:mg|mcg|micrograms?|g|grams?|units?|meq|mmol|iu)\b",
    re.IGNORECASE)
# A concentration is the vial or the bag, never a dose: "50 mg/mL",
# "500 mg / 10 mL", "1 mg in 250 mL", "10 mcg per mL".
_CONCENTRATION_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g)\s*(?:/|\bin\b|\bper\b)\s*(?:\d+(?:\.\d+)?\s*)?m\s*l\b",
    re.IGNORECASE)


def states_a_dose(text: str) -> bool:
    return _DOSE_RE.search(_CONCENTRATION_RE.sub(" ", text or "")) is not None


def _answer_text(key):
    """The model answer a served, held or gate row key carries, or None."""
    try:
        k = json.loads(key)
    except (TypeError, ValueError):
        return None
    if isinstance(k, list) and len(k) >= 3 and isinstance(k[2], str):
        return k[2]
    return None


def is_dosing(row, key=None):
    """True if the row serves a dose, False if not, None if it cannot say.

    Owner, 2026-10-24 (#179 review): "newly doses" is any row whose after-state
    serves a dose that its before-state did not. A hold never doses.
    - pipe: the response states a dose (concentrations removed), or the row
      reached the stubbed generator with doses offered: the model would write
      one.
    - served, held, gate: the answer text in the row key states a dose.
    - log: no text is kept, so a row that serves is counted as dosing.
    """
    held = is_hold(row)
    if held is None:
        return None
    if held:
        return False
    if "response" in row:
        resp = row.get("response") or ""
        reached_generator = any(l.strip() == STUB_ANSWER for l in resp.splitlines())
        return bool(reached_generator and row.get("allowed")) or states_a_dose(resp)
    text = _answer_text(key)
    if text is None:
        return True
    return states_a_dose(text)


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
        "newly_doses": [k for k in changed
                        if is_dosing(before.get(k), k) is not True
                        and is_dosing(after.get(k), k) is True],
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
              f"newly doses {len(r['newly_doses'])}, "
              f"unjudged {len(r['unknown'])}")
        for label in ("newly_released", "newly_doses", "newly_held", "unknown"):
            for k in r[label]:
                print(f"    [{label}] {k[:160]}")
        for k in r["changed"]:
            print("   ", k[:110])
            for side, row in (("before", a.get(k)), ("after", b.get(k))):
                print(f"      {side}: {_brief(row)[:700]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
