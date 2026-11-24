"""The hosts a daemon holds epics and chats in (`hosts.*`).

A host is named by its workspace and its slot. None of these calls attaches to one, and none
but :meth:`Hosts.open` starts one (Section 4.6 of daemon.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from . import Family

__all__ = ["Host", "Hosts", "Running"]


@dataclass(frozen=True)
class Host:
    """One host a daemon has taken on."""

    pid: int
    """Its process."""
    workspace: str
    """Its workspace, as the daemon knows it."""
    started: str
    """When it started, as an ISO 8601 time."""
    slot: str
    """Its slot: "" for the workspace's own, `chat:<hex>`, `ai:<hex>` or `exec:<hex>`."""


@dataclass(frozen=True)
class Running:
    """One host whose epic or chat is going or stopping."""

    workspace: str
    slot: str
    state: str
    """`running` or `stopping`."""
    run: int
    """The epic number of what is going."""
    kind: str
    """`flow` for an epic, `chat` for a chat."""
    flow: str
    """The epic's flow as named, "" for a chat."""
    epic: str
    """The epic's directory name, "" before it has one and for a chat."""
    chat: str
    """The chat's name, "" before it has one and for an epic."""
    task: str
    """The epic's task, or the chat's first message."""
    asking: tuple[str, ...]
    """The questions it waits on, each `<run>:<question>`."""
    turn: str | None
    """Of a chat or an Ai-chan conversation, `running` or `done`; None for an epic."""


class Hosts(Family):
    """The hosts a daemon holds epics and chats in."""

    METHODS: ClassVar = (
        "hosts.list",
        "hosts.running",
        "hosts.open",
        "hosts.status",
        "hosts.detach",
        "hosts.stop",
    )

    def list(self) -> list[Host]:
        """Every host taken on, in the order they were."""
        return [
            Host(int(one["pid"]), one["workspace"], one["started"], one["slot"])
            for one in self._call("hosts.list")["held"]
        ]

    def running(self) -> list[Running]:
        """Every host whose epic or chat is going or stopping."""
        return [
            Running(
                workspace=one["workspace"],
                slot=one["slot"],
                state=one["state"],
                run=int(one["run"]),
                kind=one["kind"],
                flow=one["flow"],
                epic=one["epic"],
                chat=one["chat"],
                task=one["task"],
                asking=tuple(one["asking"]),
                turn=one.get("turn"),
            )
            for one in self._call("hosts.running")["running"]
        ]

    def open(self, workspace: str, slot: str | None = None) -> dict[str, Any]:
        """Starts the host of a workspace and slot where none is, without attaching.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine.
          slot: None or "" for the workspace's own host; `exec:` or `chat:` alone for a new
            slot of that kind.

        Returns:
          Its `pid`, `workspace`, `started`, `kind`, `protocol` and `slot`.

        Raises:
          hmz.sdk.Refused: For a workspace that is no directory.
        """
        return dict(self._call("hosts.open", workspace=workspace, slot=slot))

    def status(self, workspace: str, slot: str | None = None) -> dict[str, Any]:
        """One host's status: its process, and every key of Section 4.6.4 of daemon.md.

        Raises:
          hmz.sdk.Refused: With code 404 where no host is held there.
        """
        return dict(self._call("hosts.status", workspace=workspace, slot=slot))

    def detach(self, workspace: str, slot: str | None = None) -> int:
        """Lets every frontend of a host go, leaving its epic running.

        Returns:
          How many were let go.

        Raises:
          hmz.sdk.Refused: With code 404 where no host is held there.
        """
        said = self._call("hosts.detach", workspace=workspace, slot=slot)
        return int(said["let_go"])

    def stop(
        self, workspace: str, slot: str | None = None, *, idem: str | None = None
    ) -> None:
        """Closes a host, stopping what it runs; answered before it has closed.

        Raises:
          hmz.sdk.Refused: With code 404 where no host is held there.
        """
        self._call("hosts.stop", workspace=workspace, slot=slot, idem=idem)
