#!/usr/bin/env python3
"""Contributor access to Pocket's teach page (/pocket/teach).

  pocket_contributors.py status              on or off, the limits, each speaker's clips
  pocket_contributors.py on | off            turn contributor access on or off
  pocket_contributors.py password            change the shared password (asked twice)
  pocket_contributors.py limits [key=value]  show or change the contributor limits
  pocket_contributors.py delete speaker-N    delete one speaker's clips and their label
  pocket_contributors.py migrate             once, after deploying: move the owner's
                                             earlier clips into speaker-1

The password is stored hashed in $POCKET_CONTRIBUTORS_FILE (default
~/pocket-web/contributors.json, mode 600); clips are in $POCKET_OWNER_CLIPS (default
~/pocket-web/owner-clips), one folder per speaker. The server reads both on every
request, so no restart is needed. The owner token is not affected by any of this.
"""
import getpass
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pocket_teach as pt  # noqa: E402

MIN_PASSWORD = 8


def _password(stdin) -> str:
    if stdin.isatty():
        first, second = getpass.getpass("New contributor password: "), getpass.getpass("Again: ")
    else:
        first, second = stdin.readline().rstrip("\n"), stdin.readline().rstrip("\n")
    if first != second:
        raise SystemExit("The two entries differ; the password is unchanged.")
    if len(first) < MIN_PASSWORD:
        raise SystemExit(f"Use at least {MIN_PASSWORD} characters; the password is unchanged.")
    return first


def _status() -> None:
    cfg = pt.load_config()
    print(f"Contributor access: {'ON' if cfg['enabled'] else 'off'}"
          f"{'' if cfg['password'] else ' (no password set)'}")
    print(f"Config: {pt.contributors_file()}")
    print(f"Clips:  {pt.clips_dir()}")
    print("Limits (contributors; the owner is not capped):")
    for k, v in pt.limits(cfg).items():
        print(f"  {k} = {v:g}" if isinstance(v, float) else f"  {k} = {v}")
    rows = pt.speakers()
    print("Speakers:" if rows else "Speakers: none yet")
    for s in rows:
        who = " (owner)" if s["label"] == pt.OWNER_LABEL else ""
        n = f"{s['takes']} take{'' if s['takes'] == 1 else 's'}"
        if s["label"] == pt.OWNER_LABEL:
            print(f"  {s['label']}{who}: {n}, audio kept ({s['bytes'] / 1e6:.1f} MB)")
        else:
            left = f"; {s['audio_files']} audio files from before, remove with delete" if s["audio_files"] else ""
            print(f"  {s['label']}: {n}, text only{left}")


def _limits(pairs) -> None:
    changes = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if key not in pt.LIMITS:
            raise SystemExit(f"Unknown limit {key!r}; known: {', '.join(pt.LIMITS)}")
        try:
            v = type(pt.LIMITS[key])(value)
        except ValueError:
            raise SystemExit(f"{key} needs a number, not {value!r}") from None
        if v <= 0:
            raise SystemExit(f"{key} must be above 0")
        changes[key] = v
    if changes:
        pt.set_limits(changes)


def main(argv=None, stdin=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stdin = stdin or sys.stdin
    cmd, rest = (argv[0], argv[1:]) if argv else ("status", [])
    try:
        if cmd == "status":
            _status()
        elif cmd in ("on", "off"):
            if cmd == "on" and not pt.load_config()["password"]:
                raise SystemExit("Set a password first: pocket_contributors.py password")
            pt.set_enabled(cmd == "on")
            print(f"Contributor access is {cmd.upper() if cmd == 'on' else 'off'}.")
        elif cmd == "password":
            pt.set_password(_password(stdin))
            print("Contributor password changed. Browsers using the old one are asked again.")
        elif cmd == "limits":
            _limits(rest)
            _status()
        elif cmd == "migrate":
            moved = pt.migrate_legacy()
            print(f"Moved {moved} entries into {pt.clips_dir() / pt.OWNER_LABEL}." if moved
                  else "Nothing to move.")
        elif cmd == "delete" and len(rest) == 1:
            try:
                found = pt.delete_speaker(rest[0])
            except ValueError as e:
                raise SystemExit(str(e)) from None
            if not found:
                raise SystemExit(f"No clips or label for {rest[0]}.")
            print(f"Deleted {rest[0]}'s clips and label. The label is not given out again.")
        else:
            print(__doc__)
            return 2
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
