"""The EasyTier networks a daemon's machine joins, and the shared nodes (`easytier.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["EasyTier", "Network", "Node"]


@dataclass(frozen=True)
class Network:
    """One EasyTier entry: a name for a secret and the nodes two machines meet through."""

    name: str
    """What it is called, which an `easytier:<name>` route and listener name."""
    nodes: tuple[str, ...]
    """The shared nodes it meets through, each `<protocol>://<host>:<port>`."""
    secret: bool
    """Whether a secret is written for it. The secret itself is never answered."""


@dataclass(frozen=True)
class Node:
    """A shared EasyTier node to offer, and how it has stood."""

    url: str
    """What EasyTier reaches it by, as `tcp://host:port`."""
    name: str
    """What its monitor calls it."""
    version: str
    """The EasyTier it runs, "" where unknown."""
    up: bool | None
    """Whether it answered last, None where unknown."""
    uptime: float | None
    """The share of the last 24 hours it was up, from 0 to 1, None where unknown."""


def _networks(said: Mapping[str, Any]) -> tuple[Network, ...]:
    return tuple(
        Network(str(one["name"]), tuple(one["nodes"]), bool(one["secret"]))
        for one in said["networks"]
    )


class EasyTier(Family):
    """The EasyTier networks of a daemon's machine."""

    METHODS: ClassVar = (
        "easytier.list",
        "easytier.set",
        "easytier.remove",
        "easytier.nodes",
    )

    def list(self) -> tuple[Network, ...]:
        """Every EasyTier entry, without its secret."""
        return _networks(self._call("easytier.list"))

    def set(
        self,
        name: str,
        nodes: Sequence[str],
        *,
        secret: str | None = None,
        idem: str | None = None,
    ) -> tuple[Network, ...]:
        """Writes an EasyTier entry.

        Args:
          name: What it is called.
          nodes: The shared nodes it meets through, at least one.
          secret: What the network is derived from, at least 16 bytes; None keeps the one
            written.
          idem: The key this is done once under.

        Returns:
          Every entry afterwards.

        Raises:
          hmz.sdk.Refused: If the name, a node or the secret is not one, or no secret is
            given and none is written.
        """
        return _networks(
            self._call(
                "easytier.set", name=name, secret=secret, nodes=list(nodes), idem=idem
            )
        )

    def remove(self, name: str, *, idem: str | None = None) -> tuple[Network, ...]:
        """Removes an EasyTier entry.

        Returns:
          Every entry afterwards.

        Raises:
          hmz.sdk.Refused: If there is no such entry, or the daemon listens on it.
        """
        return _networks(self._call("easytier.remove", name=name, idem=idem))

    def nodes(self) -> tuple[Node, ...]:
        """The shared nodes to offer, and how each has stood where that is known.

        Raises:
          hmz.sdk.Refused: If they cannot be read.
        """
        return tuple(
            Node(
                str(one["url"]),
                str(one.get("name") or ""),
                str(one.get("version") or ""),
                one.get("up"),
                one.get("uptime"),
            )
            for one in self._call("easytier.nodes")["nodes"]
        )
