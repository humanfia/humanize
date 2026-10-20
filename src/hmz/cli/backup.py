"""`hmz backup` -- one epic backed up to git repositories now, by hand, and back down again.

    hmz backup 20261012T091500.123Z-1a2b3c --to lab
    hmz backup --list --to lab
    hmz backup --pull 20261012T091500.123Z-1a2b3c --to lab

What the epics menu does, for a line: the epic goes to the targets named, or else to those it
was started with, or else to the defaults -- and the line waits to say how each went, since a
backup somebody asked for is one they are waiting on. `--list` says which epics the targets
hold, of every machine, and `--pull` downloads one of them into this machine's epics, as an
import would.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    from collections.abc import Generator

    from hmz.runtime import Hmz

__all__ = ["backup"]

#: How much of an epic's task a listing shows, on its one line.
_TASK = 60


def backup(argv: list[str]) -> int:
    """Backs one epic up, lists what targets hold, or downloads one, and says how it went.

    Args:
      argv: What followed the command name.

    Returns:
      Zero where every target did what it was asked; one where one did not, or the epic
      downloaded is one this machine will not take; two for a line naming no epic there is
      or no target there is.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz backup",
        description="Back an epic up to git repositories now, list what they hold, or "
        "download one.",
    )
    parser.add_argument(
        "epic", nargs="?", help="the epic, by its name in this directory or its path"
    )
    parser.add_argument(
        "--to",
        action="append",
        metavar="NAME",
        help="a backup target in settings, repeatable; else the epic's own, else the "
        "defaults; for --list and --pull, else every target",
    )
    doing = parser.add_mutually_exclusive_group()
    doing.add_argument(
        "--list", action="store_true", help="list the epics the targets hold"
    )
    doing.add_argument(
        "--pull",
        metavar="EPIC",
        help="download an epic a target holds, by name or <machine>/<workspace>/<epic>",
    )
    args = parser.parse_args(argv)

    from hmz.runtime import Hmz

    hmz = Hmz()
    if args.list or args.pull is not None:
        if args.epic:
            parser.error("an epic to back up goes without --list or --pull")
        return _held(parser, hmz, args)
    if not args.epic:
        parser.error("the following arguments are required: epic")
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
    with _spinning(f"backing up to {', '.join(names)}"):
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


def _held(parser: argparse.ArgumentParser, hmz: Hmz, args: argparse.Namespace) -> int:
    """Lists what each target holds, or downloads one epic out of the first that holds it.

    Args:
      parser: The line's parser, for a usage error.
      hmz: humanize.
      args: The line, read.

    Returns:
      What :func:`backup` returns.
    """
    known = [one.name for one in hmz.backups.targets()]
    names = list(dict.fromkeys(args.to or known))
    if not names:
        parser.error("no backup target: add one under backup in settings")
    if missing := [one for one in names if one not in known]:
        parser.error(f"no backup target is named {', '.join(missing)}")
    failed = False
    for name in names:
        try:
            with _spinning(f"asking {name} what it holds"):
                held = hmz.backups.listed(name)
        except OSError as why:
            failed = True
            print(f"{name}: failed: {why}", file=sys.stderr)
            continue
        if args.list:
            print(f"{name}: {len(held)} epic{'' if len(held) == 1 else 's'}")
            for one in held:
                task = " ".join(one.task.split())
                task = task if len(task) <= _TASK else f"{task[: _TASK - 1]}…"
                print(
                    f"  {one.machine}  {one.workspace}  {one.epic}  "
                    f"{one.how or 'unfinished'}  {task}"
                )
            continue
        found = [one for one in held if args.pull in {one.key, one.epic}]
        if len(found) > 1:
            parser.error(
                f"{name} holds {args.pull} from more than one machine: name one of "
                + ", ".join(one.key for one in found)
            )
        if found:
            try:
                with _spinning(f"downloading {found[0].key} from {name}"):
                    where = hmz.backups.pulled(name, found[0].key)
                print(where)
            except (ValueError, OSError) as why:
                print(f"hmz backup: {why}", file=sys.stderr)
                return 1
            return 0
    if args.pull is None:
        return 1 if failed else 0
    if not failed:
        parser.error(f"no target holds an epic {args.pull}")
    print(f"hmz backup: no target that answered holds {args.pull}", file=sys.stderr)
    return 1


@contextlib.contextmanager
def _spinning(says: str) -> Generator[None]:
    """A spinner on a terminal while git is asked something, gone once it has answered.

    A push, a fetch or a clone can take a while and prints nothing until it is done. Nothing
    is drawn but on a terminal, so what a script reads does not change.

    Args:
      says: What is being done.
    """
    from .output import Out

    with Out() as out:
        out.spins(lambda: says)
        yield
