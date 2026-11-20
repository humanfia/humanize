"""Every chat on this machine as it wrote itself down: `chat.*` by name (Section 4.25 of daemon.md).

A chat is no epic (Section 8 of core.md): it is listed, read, renamed, forked, archived,
backed up and deleted here, by its name, off its own record. What is said to a chat going on
a host -- `chat.start`, `chat.say`, `chat.commands`, `chat.set` and `chat.stop` -- is the
daemon's own to carry to that host (:mod:`hmz.daemon.methods`).

A session a harness had of its own, which no chat or epic wrote down, is listed, read and
adopted as a chat by `chat.harness.*` (Section 4.25.8): its harness's files are only read.

Nothing of Ai-chan's is a chat here (Section 4.25.5.6): her conversations are kept as chats
are, are listed by `aichan.list` alone, and are only read here, by `chat.get`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.daemon import reach
from hmz.daemon.api import runs, workspaces
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping

    from hmz.rpc import Call, Handler
    from hmz.runtime.doing.adopting import Found
    from hmz.runtime.epic import Ran

__all__ = ["CHATS", "METHODS", "detail", "hosted", "listed", "row", "state"]

#: The permission of a chat whose record gives none (Section 8.3.9 of core.md).
_PERMISSION = "workspace-write"

#: How long a title is, at most.
_TITLE = 240


#: The chats of every workspace, as the daemon reads them for every client.
CHATS = runs.CHATS


def hosted() -> dict[str, dict[str, Any]]:
    """How the host of each chat a host is going with stands, by the chat's name."""
    return {
        str(status["chat"]): status
        for status in workspaces.statuses().values()
        if status.get("chat") and status.get("state") in ("running", "stopping")
    }


def state(ran: Ran, status: Mapping[str, Any] | None, *, going: bool = False) -> str:
    """How one chat stands (Section 4.25.5.3 of daemon.md).

    Args:
      ran: The chat.
      status: How the host going with it stands, or None where none is.
      going: Whether another process holds it, where no host does.

    Returns:
      `asking` while its assistant waits on an answer mid-turn, `turn` while a turn is open,
      `going` while it is between turns on a host, `failed` where it ended so, and `resting`
      otherwise.
    """
    if status is None:
        return "failed" if ran.how == "failed" else "going" if going else "resting"
    if _asking(status):
        return "asking"
    return "turn" if status.get("turn") == "running" else "going"


def _asking(status: Mapping[str, Any]) -> list[str]:
    """The questions a chat's assistant waits on mid-turn, each `<run>:<question>`."""
    return [
        f"{status.get('run') or 0}:{one.get('question', '')}"
        for one in status.get("pending") or ()
        if one.get("mode") == "ask"
    ]


def row(
    ran: Ran, status: Mapping[str, Any] | None = None, *, going: bool = False
) -> dict[str, Any]:
    """One chat as a chat row (Section 4.25.5.2 of daemon.md).

    Args:
      ran: The chat.
      status: How the host going with it stands, or None where none is.
      going: Whether another process holds it, where no host does.
    """
    assistant = ran.agents[-1] if ran.agents else None
    workspace = runs.resolved(ran.workspace)
    return {
        "id": ran.name,
        "title": ran.title[:_TITLE],
        "workspace": workspace,
        "workdir": ran.workdir or workspace,
        "agent": assistant.spec if assistant else "",
        "model": assistant.model if assistant else "",
        "began": ran.began,
        "updated": ran.updated,
        "state": state(ran, status, going=going),
        "slot": str(status["slot"]) if status else "",
        "asking": _asking(status) if status else [],
        "permission": ran.permission or _PERMISSION,
        "archived": ran.archived,
        "spent": runs.labelled(ran.spent),
    }


def detail(
    ran: Ran, status: Mapping[str, Any] | None = None, *, going: bool = False
) -> dict[str, Any]:
    """One chat, whole, as `chat.get` says it but for its trace."""
    whole = runs.detail(ran, held=status is not None, picks_up=False)
    return row(ran, status, going=going) | {
        "at": str(ran.at),
        "task": ran.task,
        "prefer": ran.prefer,
        "forked": ran.forked,
        "adopted": ran.adopted,
        "agents": whole["agents"],
        "sessions": whole["sessions"],
        # The sessions it opened before it was last carried on, which are its earlier ones.
        "earlier": sum(1 for one in ran.sessions if one.at < ran.reopened),
        "backup": list(ran.backup),
        "backed": ran.backed,
    }


def listed(
    chats: runs.Runs,
    held: Mapping[str, Mapping[str, Any]],
    *,
    workspace: str = "",
    archived: bool = False,
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    kept: Callable[[str, str], bool] | None = None,
    hers: Collection[str] = (),
) -> dict[str, Any]:
    """One page of the chats written down, newest first, as `chat.list` answers it.

    Args:
      chats: The chats.
      held: How the host of each chat going stands, as :func:`hosted` says it.
      workspace: Only this workspace's chats, by its path, or "" for every one's.
      archived: The archived ones, in place of those that are not.
      q: Only those whose title, first message or name holds this, or "" for every one.
      offset: How many of those found to pass over.
      limit: How many to answer at most.
      kept: Whether a chat is there at all, by its name and workspace: Ai-chan's reach
        (Section 4.21.4 of daemon.md); None for every one.
      hers: Every Ai-chan conversation, by its name, which is left out.
    """
    wanted = q.casefold()
    found = [
        ran
        for ran in chats.all(workspace)
        if ran.name not in hers
        and ran.archived is archived
        and (kept is None or kept(ran.name, ran.workspace))
        and (
            not wanted
            or any(wanted in one.casefold() for one in (ran.title, ran.task, ran.name))
        )
    ]
    return {
        "chats": [
            row(ran, held.get(ran.name), going=chats.going(ran))
            for ran in found[offset : offset + limit]
        ],
        "total": len(found),
        "offset": offset,
        "limit": limit,
    }


def _hers() -> set[str]:
    """Every Ai-chan conversation, by its name: one her host has named and no file has too."""
    return reach.conversations().epics() | {
        name for name, status in hosted().items() if status["slot"].startswith("ai:")
    }


def _named(call: Call) -> Ran:
    """The chat a call names.

    Raises:
      RpcError: 404 for a name no chat has, an Ai-chan conversation's among them.
    """
    name = str(call.params["chat"])
    if name in _hers():
        raise RpcError(Code.NOT_FOUND, f"There is no chat {name}.")
    return CHATS.named(name)


def _row(ran: Ran) -> dict[str, Any]:
    """A chat's row as it now stands, read afresh."""
    again = CHATS.named(ran.name)
    return row(again, hosted().get(ran.name), going=CHATS.going(again))


def _list(call: Call) -> dict[str, Any]:
    params = call.params
    said: str | None = params.get("workspace")
    return listed(
        CHATS,
        hosted(),
        workspace=str(workspaces.place(said, made=True)) if said is not None else "",
        archived=params.get("archived") is True,
        q=params.get("q", ""),
        offset=runs.within(call, "offset", 0, 0),
        limit=runs.within(call, "limit", 50, 1, runs.PAGE),
        kept=reach.epics(),
        hers=_hers(),
    )


def _get(call: Call) -> dict[str, Any]:
    ran = CHATS.named(str(call.params["chat"]))
    said = detail(ran, hosted().get(ran.name), going=CHATS.going(ran))
    if call.params.get("trace") is True:
        said["trace"] = CHATS.traced(ran)
    return said


def _rename(call: Call) -> dict[str, Any]:
    from hmz.runtime.epic import note

    ran = _named(call)
    title = " ".join(str(call.params["title"]).split())
    if not title:
        raise RpcError(Code.REFUSED, "A chat's title says something.")
    note(ran.at, "set", title=title[:_TITLE])
    return _row(ran)


def _archives(*, archived: bool) -> Handler:
    def sets(call: Call) -> dict[str, Any]:
        from hmz.runtime.epic import note

        ran = _named(call)
        if ran.archived is not archived:
            note(ran.at, "set", archived=archived)
        return _row(ran)

    return sets


def _fork(call: Call) -> dict[str, Any]:
    from hmz.runtime.epic import forked

    ran = _named(call)
    # Not while its conversation may be written: a turn open on a host, or any process
    # but a host holding it, which says nothing of its turns.
    status = hosted().get(ran.name)
    if status.get("turn") != "done" if status else CHATS.going(ran):
        raise RpcError(
            Code.CONFLICT, f"Chat {ran.name} has a turn open; fork it once it is done."
        )
    try:
        return {"chat": forked(ran.at).name}
    except ValueError as why:
        raise RpcError(Code.CONFLICT, runs.reason(str(why))) from why


def _backup(call: Call) -> dict[str, Any]:
    to: list[Any] | None = call.params.get("to")
    return runs.backup(CHATS, _named(call).name, to)


def _delete(call: Call) -> dict[str, Any]:
    from hmz.runtime.epic import going

    ran = _named(call)
    if ran.name in hosted() or going(ran.at):
        raise RpcError(
            Code.CONFLICT, f"Chat {ran.name} is going on; delete it once it rests."
        )
    # Its record and the sessions kept beside it; a worktree it worked in is never removed.
    shutil.rmtree(ran.at)
    return {}


def _harnessed(call: Call) -> tuple[Path, list[Found]]:
    """The workspace a call names, and the sessions each harness had of its own there.

    Those no chat and no epic of this machine opened, last written first (Section 4.25.8.2).
    """
    from hmz.runtime.doing import adopting

    said = str(call.params["workspace"])
    workspaces.place(said, made=True)
    # As it was said, not resolved: a harness wrote down the path it was run under.
    workspace = Path(said).expanduser()
    owned = {
        (one.backend, one.ident)
        for held in (runs.RUNS, CHATS)
        for ran in held.all()
        for one in ran.sessions
    }
    return workspace, adopting.listed(workspace, owned)


def _harness_row(one: Found, workspace: Path) -> dict[str, Any]:
    """One harness session as a harness session row (Section 4.25.8.3 of daemon.md)."""
    from hmz.runtime.doing import adopting

    return {
        "id": one.ident,
        "harness": one.harness,
        "title": one.title,
        "workspace": str(workspace.resolve()),
        "model": one.model,
        "began": one.began,
        "updated": one.updated,
        "continuable": one.harness in adopting.CARRIED,
    }


def _harness_named(call: Call) -> tuple[Path, Found]:
    """The harness session a call names.

    Raises:
      RpcError: 404 for one no harness has of its own in that workspace.
    """
    harness, session = str(call.params["harness"]), str(call.params["session"])
    workspace, found = _harnessed(call)
    for one in found:
        if (one.harness, one.ident) == (harness, session):
            return workspace, one
    raise RpcError(
        Code.NOT_FOUND, f"There is no {harness} session {session} of {workspace}."
    )


def _harness_list(call: Call) -> dict[str, Any]:
    offset = runs.within(call, "offset", 0, 0)
    limit = runs.within(call, "limit", 50, 1, runs.PAGE)
    workspace, found = _harnessed(call)
    return {
        "sessions": [
            _harness_row(one, workspace) for one in found[offset : offset + limit]
        ],
        "total": len(found),
        "offset": offset,
        "limit": limit,
    }


def _harness_get(call: Call) -> dict[str, Any]:
    from hmz.runtime.doing import adopting

    workspace, one = _harness_named(call)
    said = _harness_row(one, workspace)
    if call.params.get("trace") is True:
        said["trace"] = adopting.said(one)
    return said


def _harness_adopt(call: Call) -> dict[str, Any]:
    from hmz.runtime.doing import adopting

    harness = str(call.params["harness"])
    if harness not in adopting.CARRIED:
        raise RpcError(
            Code.CONFLICT, f"A session of {harness} cannot be continued in a chat."
        )
    workspace, one = _harness_named(call)
    try:
        at = adopting.adopt(one, workspace, str(call.params.get("agent") or ""))
    except ValueError as why:
        raise RpcError(Code.CONFLICT, runs.reason(str(why))) from why
    return {"chat": at.name}


#: The methods of `chat.*` that name a chat as it is written down.
METHODS: Mapping[str, Handler] = {
    "chat.list": _list,
    "chat.get": _get,
    "chat.rename": _rename,
    "chat.fork": _fork,
    "chat.archive": _archives(archived=True),
    "chat.unarchive": _archives(archived=False),
    "chat.backup": _backup,
    "chat.delete": _delete,
    "chat.harness.list": _harness_list,
    "chat.harness.get": _harness_get,
    "chat.harness.adopt": _harness_adopt,
}
