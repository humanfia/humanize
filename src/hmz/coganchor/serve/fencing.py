"""Running a command on this machine held to the fence its turn is held to.

A client whose agent is fenced says so with every command it has run here, in the levels its
flow's permission was drawn from (:func:`hmz.coganchor.fence.abroad.told`). This end draws the
fence again around its own paths -- the directories it exports as the workdir, this user's own
home, this machine's minimum -- and runs the command under ``hmz internal fence``, the same
wrapper a fenced turn runs under on the machine it was started from: Landlock for the paths
and TCP, a seccomp filter for every other socket, and where the network is cut, a proxy that
passes only the hosts the fence names -- none at all, for a command a supervised agent runs.

What this machine cannot hold, it refuses rather than runs. It says whether it can at the
handshake (:func:`able`), so that a session is refused before its first turn, and refuses
each command besides, so that a client that did not ask is not a command run wider than its
flow allows.
"""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.coganchor.serve.exports import ExportTable

__all__ = ["able", "fenced"]


def able() -> dict[str, bool]:
    """What this machine can fence, as the handshake says it.

    Returns:
      `fs`, whether it has Landlock at all, and `net`, whether it can cut the network too --
      Landlock ABI 4 with the socket filter loadable beside it.
    """
    try:
        from hmz.coganchor import fence
    except ImportError:  # pragma: no cover -- a bundle without it is one that cannot
        return {"fs": False, "net": False}
    return {"fs": fence.enforceable(net=False), "net": fence.enforceable(net=True)}


def fenced(
    said: Mapping[str, Any],
    table: ExportTable,
    argv: list[str],
    program: str | None,
    env: Mapping[str, str],
) -> list[str]:
    """The command to run in place of one, so that it runs inside its fence.

    Args:
      said: The levels the client said, as :func:`~hmz.coganchor.fence.abroad.told` says them.
      table: What this machine exports, each directory of which is a workdir.
      argv: The command.
      program: The path the client's agent ran it by, or None to look `argv[0]` up. One this
        machine has not got is looked up by its name instead, as an unfenced command is.
      env: What it runs with, for the `PATH` a name is looked up on.

    Returns:
      ``hmz internal fence --policy=... -- PROGRAM ARGS...``.

    Raises:
      PermissionError: If this machine cannot hold the fence.
      ValueError: If what was said is not a fence's levels.
    """
    from hmz.coganchor import fence
    from hmz.coganchor.fence import abroad

    online = said.get("online", True)
    if not fence.enforceable(net=online is False):
        needs = "Landlock ABI 4 and seccomp" if online is False else "Landlock"
        raise PermissionError(
            errno.EPERM,
            f"this machine cannot fence a command: it needs {needs}",
            argv[0] if argv else None,
        )
    run = argv[0]
    if program:
        run = program if os.path.exists(program) else os.path.basename(program)
    home = os.path.expanduser("~")
    held = abroad.drawn(
        said,
        workdirs=[one.real for one in table.exports],
        home=home,
        read=abroad.installed(_named([run, *argv[1:]]), env.get("PATH"))
        if said.get("programs")
        else (),
    )
    if said.get("write"):
        abroad.ready(held, home)
    return [*fence.wrapper(held), run, *argv[1:]]


def _named(argv: list[str]) -> str:
    """The program a command line runs, past the `env` a native CLI is started behind.

    `env -u NAME ... NAME=VALUE ... PROGRAM ARGS`, which is how a CLI driven on this machine is
    started: the program whose install tree it needs to read is the one after all of that.
    """
    if os.path.basename(argv[0]) != "env":
        return argv[0]
    words = iter(argv[1:])
    for word in words:
        if word == "-u":
            next(words, None)
        elif "=" not in word and not word.startswith("-"):
            return word
    return argv[0]
