"""`aichan.*`: making, listing and forgetting Ai-chan conversations (Section 4.22 of daemon.md).

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
from hmz.daemon.reach import PRESETS, ROLE, SCOPES, ran_in
from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.daemon.routing import Router
    from hmz.rpc import Call, Handler

__all__ = ["served"]

#: How long a title taken from the task is, at most.
_TITLE = 80

#: What `aichan.list` says of each conversation, beside its `state`.
_LISTED = (
    "id",
    "title",
    "scope",
    "workspace",
    "epic",
    "nous",
    "preset",
    "network",
    "slot",
)


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


def _nous(said: object) -> str:
    """The nous a conversation is made with: the one given, or the `ai_chan` setting's.

    Raises:
      RpcError: 400 where none is given or set, or it names no agent.
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
    first = task.strip().splitlines()[0]
    slot = where.chat("ai")
    made = links.kept.made(
        {
            "title": str(params.get("title") or "") or first[:_TITLE],
            "scope": scope,
            "workspace": workspace,
            "epic": epic,
            "nous": nous,
            "preset": preset,
            "network": params.get("network") is True,
            "slot": slot,
        }
    )
    links.tasks[slot] = task
    try:
        router.hosts.opened(workspace, slot)
    except RpcError:
        links.tasks.pop(slot, None)
        links.kept.forgot(made["id"])
        raise
    return {"id": made["id"], "workspace": workspace, "slot": slot}


def _state(router: Router, conversation: Mapping[str, Any]) -> str:
    """`running`, `waiting` or `folded`, as Section 4.22.3.2 states, starting no host."""
    hosted = router.hosts.get(str(conversation["workspace"]), str(conversation["slot"]))
    if hosted is None:
        return "folded"
    status = hosted.status()
    if "turn" in status:
        return "running" if status["turn"] == "running" else "waiting"
    # Her turn is open while her epic runs and asks nobody what to say next.
    pending = cast("list[dict[str, Any]]", status.get("pending") or [])
    listening = any(one.get("mode") == "listen" for one in pending)
    return (
        "running" if status.get("state") == "running" and not listening else "waiting"
    )


def _list(router: Router, call: Call) -> dict[str, Any]:
    del call
    return {
        "conversations": [
            {key: one.get(key) for key in _LISTED}
            | {"state": _state(router, one), "created": one.get("created")}
            for one in reversed(router.links.kept.all())
        ]
    }


def _forget(router: Router, call: Call) -> dict[str, Any]:
    ident = int(call.params["id"])
    kept = router.links.kept
    conversation = next((one for one in kept.all() if one["id"] == ident), None)
    if conversation is None:
        raise RpcError(Code.NOT_FOUND, f"There is no Ai-chan #{ident}.")
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
        "aichan.forget": functools.partial(_forget, router),
    }
