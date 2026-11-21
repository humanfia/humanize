"""`easytier.*`: the EasyTier networks this machine listens on and dials, and the shared nodes.

Each entry is a name for a secret and the shared nodes the two ends of a network meet through,
written under `easytier` in the settings file (Section 3.4.10 of the files, Section 4.18.5 of
the daemon protocol). The secret goes in and never comes out: a client is told only that one
is written, and an entry written again without one keeps it.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING, Any, cast

from hmz.rpc import Code, RpcError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.rpc import Handler

__all__ = ["METHODS", "listed", "nodes", "remove", "write"]

#: What an entry may be called (Section 3.4.6.3 of the files).
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def listed() -> dict[str, Any]:
    """Every EasyTier entry of this machine, as `name`, `nodes` and whether a secret is written."""
    from hmz.coganchor import settings

    return {
        "networks": [
            {
                "name": name,
                "nodes": _nodes(one.get("nodes")),
                "secret": isinstance(one.get("secret"), str),
            }
            for name, one in _entries(settings.read()).items()
        ]
    }


def write(name: str, secret: str | None, nodes: Sequence[object]) -> dict[str, Any]:
    """Writes an EasyTier entry, keeping the secret written where none is sent.

    Args:
      name: What it is called.
      secret: What the network is derived from, or None to keep the one written.
      nodes: The shared nodes it meets through, each `<protocol>://<host>:<port>`.

    Returns:
      What :func:`listed` answers afterwards.

    Raises:
      RpcError: 400 for a name that is not one, no node or one that is not one, and a secret
        shorter than 16 bytes.
    """
    from hmz.coganchor import easytier, settings

    if not _NAMED.fullmatch(name) or name.lower() == "local":
        raise _refused(
            f"{name} is not a name: say it with letters, digits, ., _ and -."
        )
    if not nodes:
        raise _refused("An EasyTier daemon needs at least one node.")
    if not all(isinstance(one, str) for one in nodes):
        raise _refused("Say nodes as a list of text.")
    said = [str(one) for one in nodes]

    def change(held: dict[str, Any]) -> None:
        # The secret kept is the one written now, under the lock, not one read before it.
        kept = _entries(held).get(name, {}).get("secret", "")
        written = easytier.checked(str(kept) if secret is None else secret)
        if not isinstance(held.get("easytier"), dict):
            held["easytier"] = {}
        held["easytier"][name] = {"secret": written, "nodes": said}

    try:
        for one in said:
            easytier.node(one)
        settings.changes(change)
    except ValueError as why:
        raise _refused(str(why)) from why
    return listed()


def remove(name: str) -> dict[str, Any]:
    """Removes an EasyTier entry no listener names.

    Raises:
      RpcError: 404 for no such entry, and 409 for one the daemon listens on.
    """
    from hmz.coganchor import settings

    from .settings import listening

    held = settings.read()
    if name not in _entries(held):
        raise RpcError(Code.NOT_FOUND, f"There is no EasyTier entry {name}.")
    if f"easytier:{name}" in listening(held):
        raise RpcError(Code.CONFLICT, f"{name} is listened on.")

    def change(now: dict[str, Any]) -> None:
        entries: object = now.get("easytier")
        if isinstance(entries, dict):
            cast("dict[str, Any]", entries).pop(name, None)

    settings.changes(change)
    return listed()


def nodes() -> dict[str, Any]:
    """The shared EasyTier nodes to offer, and how each has stood where that is known."""
    from hmz.coganchor import easytier

    return {"nodes": [dataclasses.asdict(one) for one in easytier.shared()]}


def _entries(held: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The entries one reading of the settings file holds, each a mapping."""
    said: object = held.get("easytier")
    if not isinstance(said, dict):
        return {}
    return {
        str(name): cast("dict[str, Any]", one)
        for name, one in cast("dict[object, object]", said).items()
        if isinstance(one, dict)
    }


def _nodes(said: object) -> list[str]:
    """The nodes an entry names, as text."""
    if not isinstance(said, list):
        return []
    return [one for one in cast("list[object]", said) if isinstance(one, str)]


def _refused(message: str) -> RpcError:
    return RpcError(Code.REFUSED, message)


#: Every method of `easytier.*`, by name.
METHODS: Mapping[str, Handler] = {
    "easytier.list": lambda _: listed(),
    "easytier.set": lambda call: write(
        call.params["name"], call.params.get("secret"), call.params["nodes"]
    ),
    "easytier.remove": lambda call: remove(call.params["name"]),
    "easytier.nodes": lambda _: nodes(),
}
