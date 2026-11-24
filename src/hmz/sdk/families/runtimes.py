"""The runtimes environments are made on (`runtimes.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["Checked", "Host", "Listed", "Runtime", "Runtimes"]

#: What a runtime is written down with that is not a field of its own.
_OWN = ("backend", "name", "made")


@dataclass(frozen=True)
class Runtime:
    """One runtime a daemon has written down."""

    backend: str
    """What it is: `ssh`, `docker`, `swarm`, `apple-container` or `slurm`."""
    name: str
    """What it is called, which with its backend is what an environment names."""
    made: str
    """How it came to be written down: `typed`, or `imported` from the ssh configuration."""
    fields: dict[str, Any]
    """Everything else it was written with, by field: what `Runtimes.set` takes back."""


@dataclass(frozen=True)
class Listed:
    """Every runtime of a daemon, its own machine, and what a new runtime is made of."""

    local: dict[str, Any]
    """The daemon's own machine: `host`, `system`, `machine`, `cpus` and `memory` in bytes."""
    runtimes: tuple[Runtime, ...]
    """The runtimes written down, in the daemon's order."""
    blanks: dict[str, dict[str, Any]]
    """Each backend's fields, by backend then field, as a runtime holds them unsaid."""


@dataclass(frozen=True)
class Checked:
    """What a runtime said when it was reached and asked what it has."""

    reached: bool
    """Whether it answered at all."""
    why: str
    """Why it did not, in its own words; "" where it did."""
    cpus: float
    """How many CPUs it has."""
    memory: int
    """How many bytes of memory."""
    gpus: tuple[str, ...]
    """Its GPUs, by device id."""
    short: tuple[str, ...]
    """What it was written down as handing out and has not got."""
    said: dict[str, Any]
    """Everything the daemon answered, the above included."""


@dataclass(frozen=True)
class Host:
    """One `Host` of the ssh configuration of a daemon's machine."""

    alias: str
    """The name the configuration gives it."""
    host: str
    """The machine it reaches."""
    user: str
    """Who it logs in as."""
    port: int
    """The port it dials."""
    saved: bool
    """Whether an ssh runtime of its name is written down."""
    said: dict[str, Any]
    """Everything the daemon answered of it, the above included."""


def _listed(said: Mapping[str, Any]) -> Listed:
    return Listed(
        dict(said["local"]),
        tuple(
            Runtime(
                str(one["backend"]),
                str(one["name"]),
                str(one.get("made", "")),
                {name: value for name, value in one.items() if name not in _OWN},
            )
            for one in said["runtimes"]
        ),
        {backend: dict(fields) for backend, fields in said["blanks"].items()},
    )


class Runtimes(Family):
    """The runtimes environments are made on."""

    METHODS: ClassVar = (
        "runtimes.list",
        "runtimes.set",
        "runtimes.remove",
        "runtimes.check",
        "runtimes.hosts",
        "runtimes.import",
    )

    def list(self) -> Listed:
        """Every runtime, the daemon's own machine, and each backend's fields."""
        return _listed(self._call("runtimes.list"))

    def set(
        self,
        backend: str,
        name: str,
        fields: Mapping[str, Any] | None = None,
        *,
        replace: bool = False,
        idem: str | None = None,
    ) -> Listed:
        """Writes a runtime down.

        Args:
          backend: What it is: one of the backends `list().blanks` names.
          name: What it is called.
          fields: What it is written with, by field; a field left out is as its blank has it.
          replace: Whether it takes the place of the runtime of that backend and name.
          idem: The key this is done once under.

        Returns:
          Every runtime afterwards.

        Raises:
          hmz.sdk.Refused: If it is not a runtime, or one is called that already and it is
            not to replace it.
        """
        return _listed(
            self._call(
                "runtimes.set",
                backend=backend,
                name=name,
                fields=dict(fields or {}),
                replace=replace or None,
                idem=idem,
            )
        )

    def remove(self, backend: str, name: str, *, idem: str | None = None) -> Listed:
        """Removes a runtime.

        Returns:
          Every runtime afterwards.

        Raises:
          hmz.sdk.Refused: If there is no such runtime.
        """
        return _listed(
            self._call("runtimes.remove", backend=backend, name=name, idem=idem)
        )

    def check(self, backend: str, name: str, *, wait: float | None = None) -> Checked:
        """Reaches a runtime and says what it has.

        Args:
          backend: What it is.
          name: What it is called.
          wait: How many seconds an answer is waited for, None for as long as it takes.

        Raises:
          hmz.sdk.Refused: If there is no such runtime.
          TimeoutError: If no answer came within `wait`.
        """
        said = self._call("runtimes.check", backend=backend, name=name, wait=wait)
        return Checked(
            bool(said["reached"]),
            str(said["said"] or ""),
            float(said["cpus"] or 0),
            int(said["memory"] or 0),
            tuple(said["gpus"] or ()),
            tuple(said["short"] or ()),
            dict(said),
        )

    def hosts(self) -> tuple[Host, ...]:
        """Every `Host` of the ssh configuration of the daemon's machine.

        Raises:
          hmz.sdk.Refused: If the ssh configuration cannot be read.
        """
        return tuple(
            Host(
                str(one["alias"]),
                str(one["host"]),
                str(one["user"]),
                int(one["port"]),
                bool(one["saved"]),
                dict(one),
            )
            for one in self._call("runtimes.hosts")["hosts"]
        )

    def import_(
        self, names: Sequence[str], *, update: bool = False, idem: str | None = None
    ) -> Listed:
        """Saves an ssh runtime for each `Host` of the ssh configuration named.

        Args:
          names: The hosts, each by its `Host`.
          update: Whether a runtime imported before is written again as the host stands now.
          idem: The key this is done once under.

        Returns:
          Every runtime afterwards.

        Raises:
          hmz.sdk.Refused: If none is named, or the ssh configuration has not got one.
        """
        return _listed(
            self._call(
                "runtimes.import", names=list(names), update=update or None, idem=idem
            )
        )
