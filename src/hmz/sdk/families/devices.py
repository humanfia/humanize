"""The devices paired with a daemon, and the codes they are paired by (`pair.*`, `devices.*`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["Code", "Device", "Devices"]


@dataclass(frozen=True)
class Device:
    """One device a daemon lets in."""

    name: str
    """What it was paired as."""
    fingerprint: str
    """The fingerprint of the certificate it is known by."""
    added: str
    """When it was paired, as an ISO 8601 time."""
    seen: str | None
    """When it last opened a session, None where it never has."""


@dataclass(frozen=True)
class Code:
    """A pairing code: what a device claims to be let in."""

    code: str
    """The code, as it is typed or scanned on the device."""
    expires: int
    """When it stops being taken, in seconds since the epoch."""
    said: dict[str, Any]
    """Everything the daemon answered, the two above included."""


class Devices(Family):
    """The devices paired with a daemon."""

    METHODS: ClassVar = ("pair.create", "pair.claim", "devices.list", "devices.revoke")

    def list(self) -> list[Device]:
        """Every paired device, in the order the daemon keeps them."""
        return [
            Device(one["name"], one["fingerprint"], one["added"], one.get("seen"))
            for one in self._call("devices.list")["devices"]
        ]

    def revoke(self, name: str, *, idem: str | None = None) -> int:
        """Revokes a device, and closes the sessions it has open.

        Args:
          name: What it was paired as.
          idem: The key this is done once under.

        Returns:
          How many sessions were closed.

        Raises:
          hmz.sdk.Refused: If no device is paired as that.
        """
        return int(self._call("devices.revoke", name=name, idem=idem)["dropped"])

    def pair(
        self,
        *,
        routes: Sequence[str] | None = None,
        seconds: int | None = None,
        idem: str | None = None,
    ) -> Code:
        """Makes a pairing code for one device to claim.

        Args:
          routes: The routes the code carries, None for the ones the daemon listens on.
          seconds: How long the code is taken for, None for the daemon's own time.
          idem: The key this is done once under.
        """
        said = self._call(
            "pair.create",
            routes=None if routes is None else list(routes),
            seconds=seconds,
            idem=idem,
        )
        return Code(str(said["code"]), int(said["expires"]), dict(said))

    def claim(self, token: str, name: str) -> dict[str, Any]:
        """Pairs this session's device with the token of a pairing code.

        Args:
          token: The token the code carries.
          name: What the device is to be paired as.

        Returns:
          What the daemon answered: the name it was paired under among it.

        Raises:
          hmz.sdk.Refused: If the token is not one, was claimed already, or has expired.
        """
        return dict(self._call("pair.claim", token=token, name=name))
