#!/usr/bin/env python3
"""Upgrade session-log lines to the current schema (17, V1), into a copy.

    python tools/migrate_session_log.py <in.jsonl> <out.jsonl>
    python tools/migrate_session_log.py <in_dir> <out_dir>     # every cdss_session_*.jsonl

The session log is an audit record: it is never rewritten in place, and the
output path must differ from the input.

What a line gains from schema 17 is `timings: null` (not measured: the turn
was not timed, which is not the same as zero) and `migrated_from_schema`, the
schema it was written under (null for a line written before v4.1, which has
no log_schema key). `log_schema` becomes 17. Nothing else is touched: a field
an earlier schema lacked stays absent, and tooling reads it as unknown, as the
LOG_SCHEMA_VERSION notes in openai_client.py require. A line already at 17 is
copied unchanged; a line that does not parse as a JSON object is copied
verbatim and counted.
"""
import json
import pathlib
import sys

SCHEMA = 17


def migrate_line(entry: dict) -> tuple:
    """(entry at schema 17, whether it changed)."""
    if entry.get("log_schema") == SCHEMA:
        return entry, False
    out = dict(entry)
    out["migrated_from_schema"] = entry.get("log_schema")
    out["log_schema"] = SCHEMA
    out["timings"] = None
    return out, True


def migrate(src, dst) -> dict:
    src, dst = pathlib.Path(src), pathlib.Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("refusing to migrate in place: the session log is an audit record")
    stats = {"migrated": 0, "already_current": 0, "unparsed": 0}
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, encoding="utf-8") as fin, open(dst, "w", encoding="utf-8") as fout:
        for raw in fin:
            line = raw.rstrip("\n")
            try:
                entry = json.loads(line)
            except ValueError:
                entry = None
            if not isinstance(entry, dict):
                stats["unparsed"] += 1
                fout.write(line + "\n")
                continue
            entry, changed = migrate_line(entry)
            stats["migrated" if changed else "already_current"] += 1
            fout.write(json.dumps(entry) + "\n")
    return stats


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, dst = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    pairs = ([(f, dst / f.name) for f in sorted(src.glob("cdss_session_*.jsonl"))]
             if src.is_dir() else [(src, dst)])
    for a, b in pairs:
        print(f"{a.name}: {migrate(a, b)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
