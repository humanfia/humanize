"""`hmz internal cli`: one run of a flow's own command line, relayed to the flow.

A command line a flow shelves for its agent is a script on the agent's PATH, and the script is
two lines: it starts this, with the socket the flow is listening on, the name it was run as and
the words it was run with. This carries those words to the flow, which parses them and calls
its own function, and carries back what to print on each stream and what to exit with -- so the
program the agent ran answers exactly as one that did the work itself would have.

Spawned rather than typed, like `hmz internal tools`: it is a command line because a script on
PATH is how a shell runs anything, and not because it is a thing anybody runs by hand.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import socket
import sys

__all__ = ["cli"]


def cli(argv: list[str]) -> int:
    """Runs one of a flow's command lines, by asking the flow what it answers.

    Args:
      argv: The arguments after `hmz internal cli`.

    Returns:
      What the flow said the program exits with, or one for a flow that is no longer there --
      a program that failed, which is what it is to the agent that ran it.
    """
    parser = argparse.ArgumentParser(
        prog="hmz internal cli",
        description="Relay one run of a flow's command line to the flow. Humanize puts "
        "scripts on agents' PATH that run this; do not run it manually.",
    )
    parser.add_argument(
        "--at", required=True, metavar="SOCKET", help="socket the flow serves on"
    )
    parser.add_argument(
        "--name", required=True, help="the name the command line was run as"
    )
    parser.add_argument(
        "words", nargs="*", metavar="-- WORDS", help="the words it was run with"
    )
    # Everything after the first `--` is the run's, untouched: a parser left to read it would
    # take the run's own `--` and `--help` for its own.
    cut = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:cut])
    args.words = [*args.words, *argv[cut + 1 :]]
    held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with held:
        try:
            held.connect(args.at)
        except OSError as why:
            print(
                f"{args.name}: the flow serving it has ended ({why})", file=sys.stderr
            )
            return 1
        with held.makefile("wb") as writing:
            asked = {"name": args.name, "argv": args.words}
            writing.write((json.dumps(asked) + "\n").encode())
        # Said once and done: the flow reads one line, and needs to know nothing more is coming.
        with contextlib.suppress(OSError):
            held.shutdown(socket.SHUT_WR)
        with held.makefile("rb") as reading:
            line = reading.readline()
    try:
        said = json.loads(line)
        code, out, err = int(said["code"]), str(said["out"]), str(said["err"])
    except (ValueError, KeyError, TypeError):
        print(f"{args.name}: the flow serving it gave no answer", file=sys.stderr)
        return 1
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code
