"""Recorded epics: listed, read back, traced, exported, imported (`runs.*`).

A daemon writes down every epic it runs, and this is what was written, of an epic going or
long ended: the list the web page searches, one epic whole, what its sessions did
(:meth:`Runs.trace`), the same laid out as the Exomyth view draws it (:meth:`Runs.timeline`,
:meth:`Runs.span`), the epic as one `.hmzepic` file and back (:meth:`Runs.export`,
:meth:`Runs.import_`), a backup made now (:meth:`Runs.backup`) and what epics spent
(:meth:`Runs.usage`). An epic is a dictionary as the daemon answered it -- an epic row of
Section 4.16.2 of daemon.md -- since what it holds is the daemon's to say.
"""

from __future__ import annotations

import contextlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final

from . import Family

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Bundle", "Exported", "Imported", "Listing", "Runs"]

#: What `Runs.trace` returns, named here since `list` is a method where it is said.
type _Sessions = list[dict[str, Any]]

#: What a backup made by hand is written down as made for (Section 11.3 of core.md).
_BY_HAND: Final = "manual"

#: How often an epic is read again while its backups are waited for.
_LOOKING: Final = 0.5


@dataclass(frozen=True)
class Listing:
    """One page of the epics written down, newest first."""

    runs: list[dict[str, Any]]
    """The epics of this page, each an epic row."""
    total: int
    """How many epics the filters found, this page's and the others'."""
    offset: int
    """How many of those were passed over."""
    limit: int
    """How many a page holds at most."""
    counts: dict[str, int]
    """How many epics there are of each ending, over every epic."""
    flows: list[str]
    """Every flow an epic ran, sorted."""


@dataclass(frozen=True)
class Bundle:
    """An epic packed as one `.hmzepic`, waiting on the daemon's machine to be read."""

    handle: str
    """The read handle of it, for :meth:`hmz.sdk.families.files.Files.download`."""
    filename: str
    """What the file is called: `<name>.hmzepic`."""
    size: int
    """How many bytes it is."""
    type: str
    """Its media type, `application/vnd.hmz.epic+gzip`."""


@dataclass(frozen=True)
class Exported:
    """An epic written to a `.hmzepic` file of this machine."""

    path: Path
    """The file."""
    filename: str
    """What the daemon called it: `<name>.hmzepic`."""
    size: int
    """How many bytes it is."""


@dataclass(frozen=True)
class Imported:
    """An epic read back from a `.hmzepic`."""

    name: str
    """The epic's name, or the chat's where the archive held a chat."""
    workspace: str
    """The workspace it is written down under."""
    resumable: bool
    """Whether it can be resumed on the daemon's machine."""
    why: str
    """Why it cannot, "" where it can."""


class Runs(Family):
    """Recorded epics: listed, read back, traced, exported, imported."""

    METHODS: ClassVar = (
        "runs.list",
        "runs.get",
        "runs.trace",
        "runs.timeline",
        "runs.span",
        "runs.bundle",
        "runs.backup",
        "runs.import",
        "runs.usage",
    )

    def list(
        self,
        *,
        workspace: str | None = None,
        status: str | None = None,
        flow: str | None = None,
        query: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> Listing:
        """The epics written down, newest first, a page of them.

        Args:
          workspace: Only this workspace's, by its folder's path; every workspace's for None.
          status: Only those that went so: `done`, `failed`, `stopped`, `running` or
            `unfinished`.
          flow: Only those of this flow.
          query: Only those whose task, flow or name holds this text.
          offset: How many of those found to pass over, none for None.
          limit: How many to answer at most, 1 to 200; 50 for None.
        """
        said = self._call(
            "runs.list",
            workspace=workspace,
            status=status,
            flow=flow,
            q=query,
            offset=offset,
            limit=limit,
        )
        return Listing(
            list(said["runs"]),
            int(said["total"]),
            int(said["offset"]),
            int(said["limit"]),
            dict(said["counts"]),
            list(said["flows"]),
        )

    def get(self, name: str) -> dict[str, Any]:
        """One epic, whole: its row, its whole task, its agents, sessions and flow calls.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has.
        """
        return dict(self._call("runs.get", name=name))

    def trace(self, name: str) -> _Sessions:
        """What each session of an epic said and did, read out of the logs it kept.

        Returns:
          Each session that did anything, in the order it first did: its `key`, its `agent`
          and its `actions`, each with `category`, `name`, `at`, `start`, `seconds` and
          `args`.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has.
        """
        return list(self._call("runs.trace", name=name)["sessions"])

    def timeline(self, name: str) -> dict[str, Any]:
        """An epic's Exomyth timeline, as Section 10.6 of core.md defines the document.

        Laid out afresh on every call while the epic is going.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has.
        """
        return dict(self._call("runs.timeline", name=name))

    def span(
        self, name: str, ident: int | str, layout: int | str | None = None
    ) -> dict[str, Any]:
        """One span of an epic's timeline, whole, with everything it carried.

        Args:
          name: The epic.
          ident: The span's id: its track's `first` plus its place in the track.
          layout: The `layout` of the timeline the id was read in. For None the timeline is
            laid out first and the span read in that, whatever its ids were before.

        Raises:
          hmz.sdk.Refused: 404 for an epic or a span there is not, 409 where the epic has
            been laid out again since `layout`.
        """
        if layout is None:
            layout = self.timeline(name)["layout"]
        return dict(self._call("runs.span", name=name, id=ident, layout=layout))

    def bundle(self, name: str) -> Bundle:
        """Has the daemon pack an epic as one `.hmzepic`, credentials struck out.

        Returns:
          The file, by a read handle the caller reads and ends. :meth:`export` does both.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has.
        """
        said = self._call("runs.bundle", name=name)
        return Bundle(
            str(said["handle"]),
            str(said["filename"]),
            int(said["size"]),
            str(said["type"]),
        )

    def export(self, name: str, to: str | os.PathLike[str] | None = None) -> Exported:
        """Writes an epic to a `.hmzepic` file of this machine.

        Args:
          name: The epic.
          to: The file to write, or a directory to write `<name>.hmzepic` into -- one
            there is, or a path ending in a separator, which is made; the working directory
            for None. A file already there is replaced.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has.
          OSError: If the file cannot be written.
        """
        packed = self.bundle(name)
        said = os.fspath(to) if to is not None else ""
        at = Path(said)
        # A directory there is, or one written as one: `epics/` is made where it is not.
        if at.is_dir() or said.endswith(("/", os.sep)):
            at /= packed.filename
        try:
            at.parent.mkdir(parents=True, exist_ok=True)
        except BaseException:
            with contextlib.suppress(OSError, ValueError, TimeoutError):
                self._client.files.close(packed.handle)
            raise
        size = self._client.files.download(packed.handle, at)
        return Exported(at.absolute(), packed.filename, size)

    def backup(
        self,
        name: str,
        *,
        to: Sequence[str] | None = None,
        wait: float | None = 0,
        idem: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Backs an epic up now: to the targets named, else its own, else the defaults.

        The daemon queues the uploads and answers at once; how each went is written into
        the epic, and read back from it here where `wait` asks for that.

        Args:
          name: The epic.
          to: The targets, by name.
          wait: How many seconds to wait for the uploads to be done: 0 not to wait at all,
            None for as long as they take.
          idem: The key this is done once under.

        Returns:
          Each target the upload was queued for, with how it went -- `at`, `ok`, `error` and
          `why` -- or with nothing where it was not waited for.

        Raises:
          hmz.sdk.Refused: 404 for a name no epic has, 400 for a target there is not, 409
            where there is no target at all.
          TimeoutError: If an upload was not done within `wait`. It carries on regardless.
        """
        before: dict[str, Any] = {} if wait == 0 else self.get(name)["backed"]
        said = self._call(
            "runs.backup", name=name, to=None if to is None else list(to), idem=idem
        )
        queued = [str(one) for one in said["queued"]]
        went: dict[str, dict[str, Any]] = {one: {} for one in queued}
        if wait == 0:
            return went
        until = None if wait is None else time.monotonic() + wait
        while True:
            backed: dict[str, Any] = self.get(name)["backed"]
            # An upload is done once the epic says of its target what it did not before,
            # and says it of one made by hand: one a policy made meanwhile is not this one.
            for one in queued:
                said: dict[str, Any] = backed.get(one) or {}
                if went[one] or said == before.get(one):
                    continue
                if said.get("why") == _BY_HAND:
                    went[one] = dict(said)
            if all(went.values()):
                return went
            if until is not None and time.monotonic() >= until:
                left = ", ".join(one for one in queued if not went[one])
                raise TimeoutError(f"no backup of {name} to {left} in {wait}s")
            time.sleep(_LOOKING)

    def imported(
        self,
        *,
        handle: str | None = None,
        path: str | None = None,
        idem: str | None = None,
    ) -> Imported:
        """Imports a `.hmzepic` the daemon already has: by a write handle, or by its path.

        Args:
          handle: A write handle holding the archive, which this call ends.
          path: The archive's absolute path on the daemon's machine.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 400 for neither or both, and for an archive that cannot be
            imported; 409 for an epic already there, its name in `data`.
        """
        said = self._call("runs.import", handle=handle, path=path, idem=idem)
        return Imported(
            str(said["name"]),
            str(said["workspace"]),
            bool(said["resumable"]),
            str(said["why"]),
        )

    def import_(
        self, path: str | os.PathLike[str], *, idem: str | None = None
    ) -> Imported:
        """Sends a `.hmzepic` file of this machine to the daemon and imports it.

        Args:
          path: The file.
          idem: The key the import is done once under.

        Raises:
          OSError: If the file cannot be read.
          hmz.sdk.Refused: As :meth:`imported`; 413 for a file too large to send.
        """
        handle = self._client.files.upload(path)
        try:
            return self.imported(handle=handle, idem=idem)
        except BaseException:
            # Taken by the call where it got that far, and ended here where it did not.
            with contextlib.suppress(OSError, ValueError, TimeoutError):
                self._client.files.close(handle)
            raise

    def usage(
        self, *, days: int | None = None, workspace: str | None = None
    ) -> dict[str, Any]:
        """What chats and epics spent, by day and by flow.

        Args:
          days: How many days back, today among them, 1 to 365; 30 for None.
          workspace: Only this workspace's, by its folder's path.

        Returns:
          `days_back`, `days` (a UTC day each, oldest first), `flows` (costliest first),
          `ended` (how many ended each way) and `whole`; each but `ended` with `runs`,
          `cost`, `output_tokens`, `seconds`, and `money`, `tokens` and `worked` as text.
        """
        return dict(self._call("runs.usage", days=days, workspace=workspace))
