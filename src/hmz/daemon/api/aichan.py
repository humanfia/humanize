"""`aichan.*`: making, listing, renaming and forgetting Ai-chan conversations.

Section 4.22 of daemon.md.

Each conversation is recorded in `<home>/ai/<machine>/conversations.yaml`, held on a host of an
`ai:` slot of its own in the workspace of its scope -- `<home>/ai/<machine>` itself for the scope
`daemon` -- and kept until it is forgotten, whether or not a host holds it. What starts that
host, and the scoped link it is told of, is :class:`hmz.daemon.reach.Links`. Served by
whichever daemon names them (:func:`served`), a private one among them.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where
from hmz.daemon.reach import PRESETS, ROLE, SCOPES, preview, ran_in, turning
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.daemon.routing import Router
    from hmz.rpc import Call, Handler

__all__ = ["served"]

#: How long a title taken from the task is, at most, and one given by `aichan.rename`.
_TITLE = 80
_RENAMED = 240

#: What `aichan.list` says of each conversation, beside its `state`.
_LISTED = (
    "id",
    "title",
    "scope",
    "workspace",
    "epic",
    "nous",
    "preset",
    "slot",
)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _nous(said: object) -> str:
    """The nous a conversation is made with: the one given, or the one last used, `ai_chan`.

    Raises:
      RpcError: 400 where none is given or was used yet, or it names no agent.
    """
    from hmz.runtime import Hmz
    from hmz.runtime.flowing import parse_agents

    nous = str(said or "") or Hmz(Path.home()).settings.ai_chan
    if not nous:
        raise _refused("Name Ai-chan's nous: the ai_chan setting names none.")
    try:
        parse_agents([f"{ROLE}={nous}"])
    except ValueError:
        raise _refused(f"{nous} is not a nous or an agent spec.") from None
    return nous


def _checked(params: Mapping[str, Any]) -> tuple[str, str, str]:
    """The scope, workspace and epic a creation names, checked as Section 4.22.2.3 states.

    Raises:
      RpcError: 400 for a scope, workspace or epic said wrongly.
    """
    scope = str(params["scope"])
    workspace = str(params.get("workspace") or "")
    epic = str(params.get("epic") or "")
    if scope not in SCOPES:
        raise _refused("An Ai-chan's scope is daemon, workspace or epic.")
    if scope != "daemon" and not workspace:
        raise _refused(f"A {scope} scope names its workspace.")
    if scope == "daemon" and (workspace or epic):
        raise _refused("A daemon scope names no workspace and no epic.")
    if scope == "workspace" and epic:
        raise _refused("A workspace scope names no epic.")
    if scope == "epic" and not epic:
        raise _refused("An epic scope names its epic.")
    return scope, workspace, epic


def _create(router: Router, call: Call) -> dict[str, Any]:
    from hmz.daemon.methods import workspace as placed
    from hmz.runtime import Hmz

    params = call.params
    scope, workspace, epic = _checked(params)
    preset = str(params.get("preset", "read-only"))
    if preset not in PRESETS:
        raise _refused("An Ai-chan's preset is read-only or danger-full-access.")
    nous = _nous(params.get("nous"))
    task = str(params["task"])
    if not task.strip():
        raise _refused("Tell Ai-chan something to start with.")
    links = router.links
    if scope == "daemon":
        links.kept.at.mkdir(mode=0o700, parents=True, exist_ok=True)
        workspace = where.workspace(links.kept.at)
    else:
        workspace = placed(workspace)
    if epic and ran_in(epic) != workspace:
        raise RpcError(Code.NOT_FOUND, f"There is no epic {epic} in {workspace}.")
    first = task.strip().splitlines()[0].rstrip()
    slot = where.chat("ai")
    made = links.kept.made(
        {
            "title": first[:_TITLE],
            "scope": scope,
            "workspace": workspace,
            "epic": epic,
            "nous": nous,
            "preset": preset,
            "slot": slot,
            # What was last said in it is, until she answers, what it was made with.
            "latest": preview(task),
        }
    )
    links.tasks[slot] = task
    try:
        router.hosts.opened(workspace, slot)
    except RpcError:
        links.tasks.pop(slot, None)
        links.kept.forgot(made["id"])
        raise
    # Her host took the start: its nous is the one the next conversation is offered.
    settings = Hmz(Path.home()).settings
    if settings.ai_chan != nous:
        settings.ai_chan = nous
    return {"id": made["id"], "workspace": workspace, "slot": slot}


def _state(router: Router, conversation: Mapping[str, Any]) -> str:
    """`running`, `waiting` or `folded`, as Section 4.22.3.2 states, starting no host."""
    hosted = router.hosts.get(str(conversation["workspace"]), str(conversation["slot"]))
    if hosted is None:
        return "folded"
    return "running" if turning(hosted.status()) else "waiting"


def _said(router: Router, conversation: dict[str, Any]) -> dict[str, Any]:
    """What was last said in a conversation, and when: its `latest` and its `updated`.

    As its entry keeps them. One an earlier hmz made kept neither: what its chat last said
    is read out of its record, once, and written down with when it was made.
    """
    if "latest" not in conversation:
        read = _recorded(str(conversation.get("record") or ""))
        said = {"latest": read or "", "updated": conversation.get("created")}
        if read is not None:
            router.links.kept.changed(int(conversation["id"]), **said)
        conversation = conversation | said
    return {
        "latest": str(conversation["latest"] or ""),
        "updated": conversation.get("updated") or conversation.get("created"),
    }


def _recorded(record: str) -> str | None:
    """The last thing a chat's assistant said, read out of its record, or its task.

    "" for a conversation written in nothing, and None for one whose record could not be read
    this time: one an earlier hmz kept as an epic that is not yet moved among the chats, say.
    """
    from hmz.daemon.api.chats import CHATS

    if not record:
        return ""
    try:
        ran = CHATS.named(record)
        said = [
            (float(action.get("start") or 0), str(action["args"].get("text") or ""))
            for session in CHATS.traced(ran)
            for action in cast("list[dict[str, Any]]", session["actions"])
            if action.get("category") == "message"
        ]
    except Exception:  # noqa: BLE001 -- a record that cannot be read now is read the next time
        return None
    return preview(max(said)[1] if said else ran.task)


def _list(router: Router, call: Call) -> dict[str, Any]:
    del call
    return {
        "conversations": [
            {key: one.get(key) for key in _LISTED}
            | {"state": _state(router, one), "created": one.get("created")}
            | _said(router, one)
            for one in reversed(router.links.kept.all())
        ]
    }


def _held(router: Router, call: Call) -> dict[str, Any]:
    """The conversation a call names by its `id`.

    Raises:
      RpcError: 404 for an `id` of no conversation.
    """
    ident = int(call.params["id"])
    for one in router.links.kept.all():
        if one["id"] == ident:
            return one
    raise RpcError(Code.NOT_FOUND, f"There is no Ai-chan #{ident}.")


def _rename(router: Router, call: Call) -> dict[str, Any]:
    conversation = _held(router, call)
    title = " ".join(str(call.params["title"]).split())
    if not title:
        raise _refused("A conversation's title says something.")
    router.links.kept.changed(int(conversation["id"]), title=title[:_RENAMED])
    return {}


def _forget(router: Router, call: Call) -> dict[str, Any]:
    conversation = _held(router, call)
    ident = int(conversation["id"])
    kept = router.links.kept
    hosted = router.hosts.get(str(conversation["workspace"]), str(conversation["slot"]))
    # Forgotten before its host is closed: a frontend attached to it that attaches again as
    # it goes finds no conversation to start it again for. Its epic as its host names it,
    # where that was not written down yet, so that it stays off every list of epics.
    status = hosted.status() if hosted else {}
    kept.forgot(ident, str(status.get("chat") or status.get("epic") or ""))
    if hosted is not None:
        hosted.stop()
    return {}


def served(router: Router) -> dict[str, Handler]:
    """Each method of the family, by name, over the daemon that serves it."""
    return {
        "aichan.create": functools.partial(_create, router),
        "aichan.list": functools.partial(_list, router),
        "aichan.rename": functools.partial(_rename, router),
        "aichan.forget": functools.partial(_forget, router),
    }
