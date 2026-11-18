"""`workspaces.*`: every workspace of the daemon's machine, and how each host there stands.

A workspace is somewhere an epic ran, somewhere set up or written down in the settings, or
the directory a client calls its own (`here`). Which of them has a host going is asked of each
host's status, attaching to none, which is also where notices are worked out of and what a
change to the flows installed waits on.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence

    from hmz.rpc import Call, Handler

__all__ = ["METHODS", "going", "left", "listed", "place", "statuses"]

#: The states of a host whose epic is going.
_GOING = ("running", "stopping")


def place(workspace: str, *, made: bool = False) -> Path:
    """The workspace a call names, as its whole path, every link followed (Section 4.5.2).

    Args:
      workspace: As the call says it, `~` and all.
      made: Whether a directory that is not there may still be named: one forgotten, or an
        epic read back from a workspace since removed.

    Raises:
      RpcError: 400 for a path that is not absolute, 404 for no directory there.
    """
    at = Path(workspace).expanduser()
    if not at.is_absolute():
        raise RpcError(
            Code.REFUSED, f"Say the workspace as a whole path, not {workspace}."
        )
    if not made and not at.is_dir():
        raise RpcError(Code.NOT_FOUND, f"There is no directory {at}.")
    return at.resolve()


def statuses() -> dict[str, dict[str, Any]]:
    """How every host of this machine stands, as each says of itself, attaching to none.

    Returns:
      Each host's status with its `workspace`, its whole path, and its `slot`, by workspace
      and slot; a host that would not answer is left out.
    """
    from hmz import daemon
    from hmz.daemon import routing

    said: dict[str, dict[str, Any]] = {}
    if routing.serving is not None:
        # This process is the daemon: its hosts are asked down their links, not over its socket.
        for hosted in routing.serving.hosts.listed():
            said[f"{hosted.workspace}\0{hosted.slot}"] = {
                **hosted.status(),
                "workspace": hosted.workspace,
                "slot": hosted.slot,
            }
        return said
    with contextlib.suppress(Exception):
        for one in daemon.daemons():
            with contextlib.suppress(Exception):
                workspace = str(Path(one.workspace).resolve())
                said[f"{workspace}\0{one.slot}"] = {
                    **one.status(),
                    "workspace": workspace,
                    "slot": one.slot,
                }
    return said


def left() -> dict[str, dict[str, Any]]:
    """How every host that went since this was last asked stood as it went, asked once.

    Returns:
      As `statuses`, of the hosts this process, where it is the daemon, held and no longer
      does: what an epic that ended as its host went is told from.
    """
    from hmz.daemon import routing

    if routing.serving is None:
        return {}
    return {
        f"{workspace}\0{slot}": {**status, "workspace": workspace, "slot": slot}
        for (workspace, slot), status in routing.serving.hosts.left().items()
    }


def going() -> list[str]:
    """The workspace of every host whose epic is going, once for each such host."""
    return [
        status["workspace"]
        for status in statuses().values()
        if status.get("state") in _GOING
    ]


def listed(
    here: str, ran: Sequence[Any], running: Collection[str], written: Sequence[str]
) -> list[dict[str, Any]]:
    """Every workspace there is to offer, with how many epics it has and when the latest began.

    Args:
      here: The directory the client calls its own, whole, or "" for none.
      ran: Every epic as it reads back, newest first.
      running: The workspaces whose hosts have an epic going.
      written: The workspaces the settings write down, in the order written.

    Returns:
      Each once: `here`, then those going, then those where epics ran, newest first, then
      those only written down.
    """
    mine: dict[str, list[Any]] = {}
    for one in ran:
        mine.setdefault(_whole(one.workspace), []).append(one)
    seen: dict[str, None] = {here: None} if here else {}
    for one in (*running, *mine, *written):
        seen.setdefault(str(one), None)
    return [
        {
            "path": where,
            "name": Path(where).name or where,
            "epics": len(mine.get(where, [])),
            "last": mine[where][0].began if mine.get(where) else "",
            "running": where in running,
            "here": where == here,
            "there": Path(where).is_dir(),
        }
        for where in seen
    ]


def _whole(workspace: str) -> str:
    """A workspace's path as one is compared with another: whole, every link followed."""
    return str(Path(workspace).expanduser().resolve()) if workspace else ""


def _answer(call: Call) -> dict[str, Any]:
    """What `workspaces.list` answers, `here` as the call says it."""
    from hmz.daemon.reach import conversations
    from hmz.runtime import Hmz
    from hmz.runtime.epic import every, read

    here = _whole(call.params.get("here", ""))
    # Nothing of Ai-chan's is a workspace's (Section 4.17.5.5): neither her hosts, nor her
    # epics, the one a host of hers has named and no file has yet among them.
    hosts = list(statuses().values())
    hers = conversations().epics() | {
        status.get("epic") for status in hosts if status["slot"].startswith("ai:")
    }
    ran = [
        one
        for at in reversed(every())
        if at.name not in hers and (one := read(at)) is not None
    ]
    running = {
        status["workspace"]
        for status in hosts
        if status.get("state") in _GOING and not status["slot"].startswith("ai:")
    }
    written = Hmz(Path.home()).settings.workspaces()
    return {"here": here, "workspaces": listed(here, ran, running, written)}


def _add(call: Call) -> dict[str, Any]:
    from hmz.runtime import Hmz

    at = place(call.params["workspace"])
    Hmz(at).settings.keeps()
    return {"kept": str(at)} | _answer(call)


def _forget(call: Call) -> dict[str, Any]:
    from hmz.runtime import Hmz

    Hmz(place(call.params["workspace"], made=True)).settings.forget()
    return _answer(call)


#: Each method of the family, by name.
METHODS: Mapping[str, Handler] = {
    "workspaces.list": _answer,
    "workspaces.add": _add,
    "workspaces.forget": _forget,
}
