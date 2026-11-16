"""The devices paired with this machine's daemon, in `devices.yaml` beside its identity.

Each is a name the user can tell it by, the fingerprint the daemon knows it by, when it was
paired and when a session of it was last seen. Written by the daemon alone, whole and moved
into place, and read afresh each time it is asked: a user who deleted the file while hmz was
not running unpaired every device, and the next read says so.

Revoking a device removes its entry and tells whoever is watching, which is how the daemon
closes every session that device holds at once -- the one that asked included.
"""

from __future__ import annotations

import contextlib
import datetime
import re
import threading
import time
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz.trust import identity

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = ["FILE", "LOCAL", "SEEN_EVERY", "Device", "Devices"]

#: The file, inside the machine's identity directory.
FILE = "devices.yaml"

#: The device every session over a trusted carrier is, which is never in the file and never
#: revoked.
LOCAL = "local"

#: How often, in seconds, `seen` is written for one device at most.
SEEN_EVERY = 60

#: What a device's name is: a letter or a digit, then letters, digits, `.`, `_` and `-`.
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: How a moment is written in the file: UTC, to the second.
_STAMP = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Device:
    """One device paired with the daemon.

    Attributes:
      name: What the user calls it, unique among them.
      fingerprint: Its device fingerprint.
      added: When it was paired, in UTC.
      seen: When a session of it was last seen, or None before one was.
    """

    name: str
    fingerprint: str
    added: str
    seen: str | None


class Devices:
    """The paired devices of this machine's daemon: listed, added, revoked, seen."""

    def __init__(
        self, at: Path | None = None, clock: Callable[[], float] = time.time
    ) -> None:
        """Reads nothing yet.

        Args:
          at: The file, or None for `devices.yaml` in this machine's identity directory.
          clock: What says the time, in Unix seconds.
        """
        self._at = at
        self._clock = clock
        self._lock = threading.Lock()
        self._watching: list[Callable[[Device], None]] = []

    @property
    def at(self) -> Path:
        """The file, found once: which machine this is does not change while it runs."""
        if self._at is None:
            self._at = identity.directory() / FILE
        return self._at

    def listed(self) -> list[Device]:
        """Every paired device, in the order paired.

        An entry that is not a mapping of the four keys, each of its type, is left out; a
        file that cannot be read pairs nothing.
        """
        try:
            held: object = yaml.safe_load(self.at.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            return []
        if not isinstance(held, list):
            return []
        devices: list[Device] = []
        for one in cast("list[object]", held):
            device = _device(one)
            if device is not None:
                devices.append(device)
        return devices

    def named(self, fingerprint: str) -> str | None:
        """The name a device fingerprint is paired under, or None where it is not paired.

        Read afresh, so that it can be asked as often as a session wants to know it still is.
        """
        for device in self.listed():
            if device.fingerprint == fingerprint:
                return device.name
        return None

    @staticmethod
    def check(name: str) -> None:
        """Refuses what cannot be a device's name.

        Raises:
          ValueError: If it does not begin with a letter or a digit, holds anything but
            letters, digits, `.`, `_` and `-`, or is `local`.
        """
        if not _NAME.fullmatch(name) or name == LOCAL:
            raise ValueError(
                "A device's name begins with a letter or a digit, holds letters, digits,"
                " '.', '_' and '-', and is not local."
            )

    def add(self, name: str, fingerprint: str) -> str:
        """Pairs a device, under its name made unique by `#2`, `#3` and on.

        Args:
          name: What it asked to be called.
          fingerprint: Its device fingerprint.

        Returns:
          The name it was paired under; the one it already has where it is paired.

        Raises:
          ValueError: If `name` is not a device name, or the file is not YAML.
          TypeError: If the file is not a list.
          OSError: If the file cannot be read or written.
        """
        self.check(name)
        with self._lock:
            held = self._held()
            devices = [one for one in map(_device, held) if one is not None]
            for device in devices:
                if device.fingerprint == fingerprint:
                    return device.name
            taken = {device.name for device in devices}
            unique, n = name, 1
            while unique in taken:
                n += 1
                unique = f"{name}#{n}"
            self._wrote([*held, asdict(Device(unique, fingerprint, self._now(), None))])
        return unique

    def revoke(self, name: str) -> Device:
        """Unpairs a device, and then tells whoever is watching.

        Args:
          name: Its name.

        Returns:
          The device that was revoked.

        Raises:
          ValueError: If it is `local`, which is refused 400.
          LookupError: If no device has that name, which is refused 404 with this message.
          OSError: If the file cannot be read or written.
          TypeError: If the file is not a list.
        """
        if name == LOCAL:
            raise ValueError("local cannot be revoked.")
        with self._lock:
            held = self._held()
            gone = next(
                (one for one in map(_device, held) if one and one.name == name), None
            )
            if gone is None:
                raise LookupError(f"There is no device {name}.")
            self._wrote([one for one in held if _device(one) != gone])
            watching = list(self._watching)
        for told in watching:
            told(gone)
        return gone

    def seen(self, fingerprint: str) -> None:
        """Writes down that a session of a device opened: at most once a minute for one.

        Kept where it can be: a file that cannot be written is no reason a session of a
        paired device should not open.

        Args:
          fingerprint: Its device fingerprint. One not paired is not written.
        """
        now = self._clock()
        with self._lock, contextlib.suppress(OSError, ValueError, TypeError):
            held = self._held()
            for at, one in enumerate(held):
                device = _device(one)
                if device is None or device.fingerprint != fingerprint:
                    continue
                if device.seen is not None and now - _seconds(device.seen) < SEEN_EVERY:
                    return
                held[at] = asdict(
                    Device(device.name, device.fingerprint, device.added, self._now())
                )
                self._wrote(held)
                return

    def watch(self, told: Callable[[Device], None]) -> Callable[[], None]:
        """Has a device that is revoked told to a callback, after it is gone from the file.

        Args:
          told: Called with each device revoked, in the thread that revoked it.

        Returns:
          What stops it being told.
        """
        with self._lock:
            self._watching.append(told)

        def unwatch() -> None:
            with self._lock:
                if told in self._watching:
                    self._watching.remove(told)

        return unwatch

    def _now(self) -> str:
        """This moment, as the file writes one."""
        return datetime.datetime.fromtimestamp(self._clock(), datetime.UTC).strftime(
            _STAMP
        )

    def _held(self) -> list[object]:
        """Every entry of the file as it is, for a write to change and write back.

        Strict where :meth:`listed` is lenient: a write made from a file that could not be
        read would write every device it could not see out of it. An entry this does not
        read as a device is written back as it was.

        Raises:
          OSError: If the file is there and cannot be read.
          ValueError: If it is not YAML.
          TypeError: If it is not a list.
        """
        try:
            text = self.at.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            held: object = yaml.safe_load(text)
        except yaml.YAMLError as why:
            raise ValueError(f"{self.at} is not YAML: {why}") from why
        if held is None:
            return []
        if not isinstance(held, list):
            raise TypeError(f"{self.at} is not a list of devices")
        return list(cast("list[object]", held))

    def _wrote(self, entries: list[object]) -> None:
        """Writes the file whole, `0600`, in a directory `0700`. Called holding the lock."""
        from hmz.coganchor import atomic

        self.at.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic.writes(self.at, yaml.safe_dump(entries, sort_keys=False), mode=0o600)


def _device(said: object) -> Device | None:
    """One entry of the file, or None where it is not one."""
    if not isinstance(said, dict):
        return None
    entry = cast("dict[str, Any]", said)
    if set(entry) != {"name", "fingerprint", "added", "seen"}:
        return None
    name, fingerprint = entry["name"], entry["fingerprint"]
    added, seen = _stamp(entry["added"]), _stamp(entry["seen"])
    if not isinstance(name, str) or not isinstance(fingerprint, str) or added is None:
        return None
    if seen is None and entry["seen"] is not None:
        return None
    return Device(name, fingerprint, added, seen)


def _stamp(said: object) -> str | None:
    """A moment as the file writes it, from what YAML read; None where it is not one."""
    if isinstance(said, datetime.datetime):
        moment = said if said.tzinfo else said.replace(tzinfo=datetime.UTC)
        return moment.astimezone(datetime.UTC).strftime(_STAMP)
    if isinstance(said, str):
        try:
            datetime.datetime.strptime(said, _STAMP).replace(tzinfo=datetime.UTC)
        except ValueError:
            return None
        return said
    return None


def _seconds(stamp: str) -> float:
    """A moment the file wrote, in Unix seconds."""
    return (
        datetime.datetime.strptime(stamp, _STAMP)
        .replace(tzinfo=datetime.UTC)
        .timestamp()
    )
