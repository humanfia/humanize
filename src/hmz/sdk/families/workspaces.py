"""The folders a daemon knows as workspaces (`workspaces.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Known", "Workspace", "Workspaces"]


@dataclass(frozen=True)
class Workspace:
    """One workspace: a folder of the daemon's machine epics run in and chats are had in."""

    path: str
    name: str
    """The last part of its path."""
    epics: int
    chats: int
    last: str
    """When its latest epic or chat began, "" where none has."""
    running: bool
    here: bool
    """Whether it is the one the call said it was made from."""
    there: bool
    """Whether the directory exists."""


@dataclass(frozen=True)
class Known:
    """Every workspace a daemon knows, as one call answered it."""

    here: str
    """The directory the call said it was made from, whole, or ""."""
    workspaces: tuple[Workspace, ...]
    """`here` first, then those going, then those something ran in, newest first, then those
    only written in the settings."""
    kept: str
    """The absolute path of the workspace `add` wrote; "" from any other call."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


def _known(said: Mapping[str, Any]) -> Known:
    return Known(
        said["here"],
        tuple(
            Workspace(
                one["path"],
                one["name"],
                int(one["epics"]),
                int(one["chats"]),
                one["last"],
                bool(one["running"]),
                bool(one["here"]),
                bool(one["there"]),
            )
            for one in said["workspaces"]
        ),
        said.get("kept", ""),
        dict(said),
    )


class Workspaces(Family):
    """The folders a daemon knows as workspaces."""

    METHODS: ClassVar = ("workspaces.list", "workspaces.add", "workspaces.forget")

    def list(self, here: str | None = None) -> Known:
        """Every workspace.

        Args:
          here: The directory this is asked from, which is listed first.
        """
        return _known(self._call("workspaces.list", here=here))

    def add(
        self, workspace: str, here: str | None = None, *, idem: str | None = None
    ) -> Known:
        """Writes a workspace in the settings, so that it is listed before anything runs there.

        Args:
          workspace: An absolute path of the daemon's machine, `~` expanded there.
          here: The directory this is asked from.
          idem: The key this is done once under.

        Returns:
          Every workspace, `kept` being the absolute path of the one written.

        Raises:
          hmz.sdk.Refused: If it is not a directory there.
        """
        return _known(
            self._call("workspaces.add", idem=idem, workspace=workspace, here=here)
        )

    def forget(
        self, workspace: str, here: str | None = None, *, idem: str | None = None
    ) -> Known:
        """Forgets what a workspace was set up with, which unlists one nothing ran in.

        Args:
          workspace: The workspace, which need not exist any more.
          here: The directory this is asked from.
          idem: The key this is done once under.
        """
        return _known(
            self._call("workspaces.forget", idem=idem, workspace=workspace, here=here)
        )
