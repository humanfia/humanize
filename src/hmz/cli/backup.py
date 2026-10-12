"""`hmz backup` -- one epic backed up to git repositories now, by hand.

    hmz backup 20261012T091500.123Z-1a2b3c --to lab

What the epics menu does, for a line: the epic goes to the targets named, or else to those it
was started with, or else to the defaults -- and the line waits to say how each went, since a
backup somebody asked for is one they are waiting on.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["backup"]


def backup(argv: list[str]) -> int:
    """Backs one epic up, waits for it, and says how it went per target.

    Args:
      argv: What followed the command name.

    Returns:
      Zero where every target took it; one where one did not; two for a line naming no
      epic of this directory's or no target there is.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz backup", description="Back an epic up to git repositories now."
    )
    parser.add_argument(
        "epic", help="the epic, by its name in this directory or its path"
    )
    parser.add_argument(
        "--to",
        action="append",
        metavar="NAME",
        help="a backup target in settings, repeatable; else the epic's own, else the "
        "default targets",
    )
    args = parser.parse_args(argv)

    from hmz.runtime import Hmz

    hmz = Hmz()
    named = next((one for one in hmz.epics.all() if one.name == args.epic), None)
    ran = hmz.epics.read(named or Path(args.epic).expanduser())
    if ran is None:
        parser.error(f"no epic {args.epic} here")
    before = hmz.backups.state(ran)
    try:
        names = hmz.backups.push(ran, args.to)
    except ValueError as why:
        parser.error(str(why))
    if not names:
        parser.error("no backup target: add one under backup in settings, or name one")
    hmz.backups.wait()
    urls = {one.name: one.url for one in hmz.backups.targets()}
    state = hmz.backups.state(ran)
    failed = False
    for name in names:
        # An outcome the epic does not say anew is one it could not be written into.
        said = state.get(name, {})
        if said == before.get(name):
            said = {"error": "the epic could not be written to, to say how it went"}
        if said.get("ok"):
            # Never with what was signed into it: a line printed is a line in a scrollback.
            print(f"{name}: backed up to {hmz.verses.plain(urls.get(name, ''))}")
        else:
            failed = True
            print(f"{name}: failed: {said.get('error') or 'unknown'}", file=sys.stderr)
    return 1 if failed else 0
