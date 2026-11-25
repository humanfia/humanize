"""The flowverses flows are installed from, and what is installed (`flowverses.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "Flowverses",
    "Index",
    "Installed",
    "Kept",
    "Listed",
    "Release",
    "Skipped",
    "Update",
    "Verse",
]


@dataclass(frozen=True)
class Verse:
    """One flowverse: an index flows are installed out of."""

    name: str
    url: str
    """Where it is fetched from, with nothing signed into it; "" for one that is local."""
    fetched: bool
    fixed: bool
    """Whether it is one that cannot be removed."""
    edited: bool
    """Whether something is written into it, which fetching resets."""
    installed: int
    """How many flows are installed out of it."""


@dataclass(frozen=True)
class Installed:
    """One flow installed out of a flowverse."""

    flow: str
    """What it is started by, and what `install` and `uninstall` take."""
    verse: str
    listed: str
    """What its flowverse lists it as."""
    version: str
    repo: str
    ref: str


@dataclass(frozen=True)
class Update:
    """A newer release of an installed flow."""

    flow: str
    was: str
    """The release installed: the answer's `from`."""
    to: str
    """The newest release there is."""


@dataclass(frozen=True)
class Kept:
    """Every flowverse and installed flow, and what the call that answered it did."""

    verses: tuple[Verse, ...]
    installed: tuple[Installed, ...]
    updates: tuple[Update, ...]
    said: str
    """What was done, in the daemon's words; "" where the call only read."""
    answer: dict[str, Any]
    """Everything the daemon answered."""


@dataclass(frozen=True)
class Release:
    """One release of a flow a flowverse lists."""

    version: str
    description: str
    prerelease: bool
    license: str
    repo: str
    dependencies: Any


@dataclass(frozen=True)
class Listed:
    """One flow a flowverse lists."""

    listed: str
    """What the flowverse lists it as."""
    flow: str
    """What it is offered under once installed, as `install` takes it."""
    installed: str
    """The release installed, "" for none."""
    releases: tuple[Release, ...]
    """Every release, newest first."""


@dataclass(frozen=True)
class Skipped:
    """Something in a flowverse's index that could not be read."""

    at: str
    why: str


@dataclass(frozen=True)
class Index:
    """One flowverse, and everything its index lists."""

    name: str
    url: str
    fetched: bool
    fixed: bool
    edited: bool
    flows: tuple[Listed, ...]
    skipped: tuple[Skipped, ...]
    answer: dict[str, Any]
    """Everything the daemon answered."""


def _kept(said: Mapping[str, Any]) -> Kept:
    return Kept(
        tuple(
            Verse(
                one["name"],
                one["url"],
                bool(one["fetched"]),
                bool(one["fixed"]),
                bool(one["edited"]),
                int(one["installed"]),
            )
            for one in said["verses"]
        ),
        tuple(
            Installed(
                one["flow"],
                one["verse"],
                one["listed"],
                one["version"],
                one["repo"],
                one["ref"],
            )
            for one in said["installed"]
        ),
        tuple(Update(one["flow"], one["from"], one["to"]) for one in said["updates"]),
        said.get("said", ""),
        dict(said),
    )


class Flowverses(Family):
    """The flowverses flows are installed from, and what is installed."""

    METHODS: ClassVar = (
        "flowverses.list",
        "flowverses.get",
        "flowverses.add",
        "flowverses.fetch",
        "flowverses.remove",
        "flowverses.install",
        "flowverses.uninstall",
    )

    def list(self) -> Kept:
        """Every flowverse, every flow installed out of one, and the newer releases."""
        return _kept(self._call("flowverses.list"))

    def get(self, name: str) -> Index:
        """One flowverse: the flows its index lists, each with every release.

        Raises:
          hmz.sdk.Refused: 404, if there is no such flowverse.
        """
        said = self._call("flowverses.get", name=name)
        return Index(
            said["name"],
            said["url"],
            bool(said["fetched"]),
            bool(said["fixed"]),
            bool(said["edited"]),
            tuple(
                Listed(
                    one["listed"],
                    one["flow"],
                    one["installed"],
                    tuple(
                        Release(
                            each["version"],
                            each["description"],
                            bool(each["prerelease"]),
                            each["license"],
                            each["repo"],
                            each["dependencies"],
                        )
                        for each in one["releases"]
                    ),
                )
                for one in said["flows"]
            ),
            tuple(Skipped(one["at"], one["why"]) for one in said["skipped"]),
            dict(said),
        )

    def add(
        self, url: str, name: str | None = None, *, idem: str | None = None
    ) -> Kept:
        """Adds a flowverse.

        Args:
          url: Where it is: `owner/repo`, or the URL of a git repository.
          name: What it is kept as, None for the name its URL gives it.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 400, with why it was not added.
        """
        return _kept(self._call("flowverses.add", idem=idem, url=url, name=name))

    def fetch(self, name: str, *, idem: str | None = None) -> Kept:
        """Fetches a flowverse's index, resetting anything written into it.

        Raises:
          hmz.sdk.Refused: 400, with why it was not fetched.
        """
        return _kept(self._call("flowverses.fetch", idem=idem, name=name))

    def remove(self, name: str, *, idem: str | None = None) -> Kept:
        """Removes a flowverse, and every flow installed out of it.

        Raises:
          hmz.sdk.Refused: 409 while an epic is running; 400 with why it was not removed.
        """
        return _kept(self._call("flowverses.remove", idem=idem, name=name))

    def install(
        self, flow: str, version: str | None = None, *, idem: str | None = None
    ) -> Kept:
        """Installs a release of a flow, in place of the one installed where there is one.

        Args:
          flow: The flow, as `Listed.flow` names it: bare for the official flowverse's,
            `@<flowverse>/<flow>` for another's.
          version: The release, None for the newest.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 409 while an epic is running; 400 with why it was not installed.
        """
        return _kept(
            self._call("flowverses.install", idem=idem, flow=flow, version=version)
        )

    def uninstall(self, flow: str, *, idem: str | None = None) -> Kept:
        """Uninstalls a flow.

        Raises:
          hmz.sdk.Refused: 409 while an epic is running; 400 with why it was not.
        """
        return _kept(self._call("flowverses.uninstall", idem=idem, flow=flow))
