"""What a backup target holds, and pulling it back (`backups.*`).

A backup target is a git repository named in the daemon's settings, which epics and chats are
pushed to as their policies say or by hand (:meth:`hmz.sdk.families.runs.Runs.backup`). This
is the other way: what one holds, of every machine that pushes to it, and one of those
downloaded onto the daemon's machine as an import would land it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from . import Family

__all__ = ["Backups", "Stored", "Target"]


@dataclass(frozen=True)
class Target:
    """One backup target of a daemon's settings."""

    name: str
    """What it is called, which is what names it everywhere else."""
    url: str
    """Its git repository, with nothing signed into it."""
    branch: str
    """The branch epics are pushed to."""
    policies: tuple[str, ...]
    """When an epic started with it is pushed: `session`, `interval`, `end`."""
    every: int
    """How many minutes apart `interval` pushes."""
    default: bool
    """Whether an epic that names no target is backed up to it."""


@dataclass(frozen=True)
class Stored:
    """One epic, or one chat, a backup target holds."""

    key: str
    """What it is pulled by: `<machine>/<workspace>/<epic>`."""
    machine: str
    """The machine it ran on."""
    workspace: str
    """The workspace it ran in."""
    epic: str
    """Its name; a chat's name where it is a chat."""
    flow: str
    """The flow it ran, "" for a chat."""
    task: str
    """Its task; a chat's first message."""
    began: str
    """When it began, as an ISO 8601 time."""
    ended: str
    """When it ended, "" where it had not when it was backed up."""
    how: str
    """How it ended, "" where it had not."""
    head: str
    """The commit of the target that holds it."""
    chat: bool
    """Whether it is a chat."""
    here: bool
    """Whether the daemon's machine holds it already."""


class Backups(Family):
    """What a backup target holds, and pulling it back."""

    METHODS: ClassVar = ("backups.epics", "backups.pull")

    def targets(self) -> list[Target]:
        """The backup targets of the daemon's settings, in the order they are kept.

        Read from `settings.get`, which is where a daemon says them; they are set through
        the settings family.
        """
        said = self._client.call("settings.get", {})["backup"]
        defaults = set(said["defaults"])
        return [
            Target(
                str(one["name"]),
                str(one["url"]),
                str(one["branch"]),
                tuple(one["policies"]),
                int(one["every"]),
                one["name"] in defaults,
            )
            for one in said["targets"]
        ]

    def epics(self, target: str) -> list[Stored]:
        """The epics and chats a target holds, newest first, fetched afresh.

        Args:
          target: The target, by name.

        Raises:
          hmz.sdk.Refused: 400 for a target there is not, 502 where its repository cannot be
            reached.
        """
        return [
            Stored(
                str(one["key"]),
                str(one["machine"]),
                str(one["workspace"]),
                str(one["epic"]),
                str(one["flow"]),
                str(one["task"]),
                str(one["began"]),
                str(one["ended"]),
                str(one["how"]),
                str(one["head"]),
                bool(one["chat"]),
                bool(one["here"]),
            )
            for one in self._call("backups.epics", target=target)["epics"]
        ]

    def pull(self, target: str, key: str, *, idem: str | None = None) -> str:
        """Downloads one epic or chat from a target onto the daemon's machine.

        Args:
          target: The target, by name.
          key: Which, as :attr:`Stored.key` names it.
          idem: The key this is done once under.

        Returns:
          The name it has there: an epic's, or a chat's among the chats.

        Raises:
          hmz.sdk.Refused: 400 for a target or a key there is not and for one already there,
            502 where the repository cannot be reached.
        """
        return str(
            self._call("backups.pull", target=target, key=key, idem=idem)["name"]
        )
