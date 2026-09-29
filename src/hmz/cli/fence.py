"""``hmz internal fence`` -- run a program held to what a flow's permission lets it reach.

What every turn of an agent whose permission fences anything is spawned as, outermost of
whatever else the turn is wrapped in: the program runs here, unchanged and on this terminal,
walled in by Landlock and, where the network is cut, by a socket filter and a proxy that
passes only the hosts its model is at. :mod:`hmz.coganchor.fence.wrap` is what does it.

Its own command rather than something the driver does in this process, for the reason
`hmz internal cred` is: a wall can only be put up by the process it walls in, just before it
becomes the program, and the process that serves the proxy and passes the signals on has to
be one that stays outside it.
"""

from __future__ import annotations

__all__ = ["fence"]


def fence(argv: list[str]) -> int:
    """Runs the program named on the command line, inside the fence it was given.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz internal fence",
        description="Run an agent held to the paths and hosts its flow permits. humanize "
        "runs this command for every turn it fences; do not run it manually.",
    )
    parser.add_argument(
        "--policy",
        metavar="JSON",
        required=True,
        help="the fence, as JSON, or @PATH for a file holding it",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="COMMAND",
        help="the program to run and its arguments, after --",
    )
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error(
            "no program given; try `hmz internal fence --policy=... -- claude`"
        )

    from hmz.coganchor.fence import wrap

    return wrap.main(args.policy, command)
