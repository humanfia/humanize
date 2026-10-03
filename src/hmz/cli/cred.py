"""``hmz internal cred`` -- run a program with some of its paths answered by others.

What a turn under a provider is spawned as, what a login run for one is spawned as, and what
every turn whose sessions humanize keeps is spawned as: the program runs here, unchanged and on
this terminal, and the handful of syscalls that name one of its credential files are handed a
path inside the provider's directory instead -- and those naming its sessions, one inside the
directory humanize keeps them in.

Its own command rather than something the driver does in this process, for the reason
`hmz internal anchor` is: the supervisor forks the program and takes the process's signal
handling with it, which a flow pumping turns from threads of its own has no way to lend it.
"""

from __future__ import annotations

import sys

__all__ = ["cred"]


def cred(argv: list[str]) -> int:
    """Runs the program named on the command line, with the paths it was given swapped.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz internal cred",
        description="Run an agent with an account's credentials. humanize runs this "
        "command for every turn taken as an account; do not run it manually.",
    )
    parser.add_argument(
        "--map",
        metavar="FROM=TO",
        action="append",
        default=[],
        dest="maps",
        help="map absolute path FROM to TO; repeatable, and a directory includes "
        "everything inside it",
    )
    parser.add_argument(
        "--keep",
        metavar="FROM=TO",
        action="append",
        default=[],
        dest="keeps",
        help="as --map, but never by copying, for sessions the CLI writes while reading "
        "them back; FROM may hold a glob; repeatable",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="the program to run and its arguments, after --",
    )
    args = parser.parse_args(argv)

    from hmz.coganchor.providers import redirect

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error(
            "no program given; try `hmz internal cred --map FROM=TO -- claude`"
        )
    try:
        swaps = redirect.read(args.maps, args.keeps)
    except ValueError as why:
        parser.error(str(why))
    if not swaps:
        parser.error(
            "nothing to answer with anything: give at least one --map or --keep"
        )

    try:
        return redirect.run(swaps, command)
    except (OSError, RuntimeError, ValueError) as why:
        # A run that could not be supervised must not fall back to running unsupervised: the
        # program would read the credentials of whoever is at this machine, which is a turn
        # taken as the wrong account rather than a turn that failed.
        print(f"hmz internal cred: {why}", file=sys.stderr)
        return 1
