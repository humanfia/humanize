"""The daemon machine's directories, for choosing a folder (`paths.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from . import Family

__all__ = ["Directory", "Entry", "Paths"]


@dataclass(frozen=True)
class Entry:
    """One name in a directory."""

    name: str
    dir: bool
    """Whether it is a directory."""


@dataclass(frozen=True)
class Directory:
    """What is in one directory."""

    at: str
    """The directory, spelled from `~` where it is under the home directory."""
    whole: str
    """Its absolute path."""
    up: str
    """Its parent, "" at the root."""
    entries: tuple[Entry, ...]
    """What is in it, directories first: at most 500."""
    more: int
    """How many were left out."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


class Paths(Family):
    """The daemon machine's directories, for choosing a folder."""

    METHODS: ClassVar = ("paths.list", "paths.complete")

    def list(
        self,
        at: str | None = None,
        *,
        files: bool | None = None,
        hidden: bool | None = None,
        env: str | None = None,
    ) -> Directory:
        """Lists one directory.

        Args:
          at: The directory, `~` expanded on the machine asked; None for the home directory.
          files: Whether files are listed beside directories.
          hidden: Whether names starting with `.` are listed.
          env: The runtime whose machine the directory is on, as `-e` spells one with no
            directory (`ssh@<name>`); None for the daemon's own.

        Raises:
          hmz.sdk.Refused: 404 for a directory that cannot be read; 400 for an `env` that
            names no runtime; 409 for one whose directories cannot be listed, or reached.
        """
        said = self._call("paths.list", at=at, files=files, hidden=hidden, env=env)
        return Directory(
            said["at"],
            said["whole"],
            said["up"],
            tuple(Entry(one["name"], bool(one["dir"])) for one in said["entries"]),
            int(said["more"]),
            dict(said),
        )

    def complete(self, typed: str) -> list[str]:
        """The directories a typed path could become: at most 50, each ending in `/`."""
        return list(self._call("paths.complete", typed=typed)["paths"])
