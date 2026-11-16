"""Pairing codes: what admits one device to a daemon, once, before it expires.

A code is everything a client needs to reach a daemon it has never met and to know it when it
does -- the daemon's id, the routes to it -- and a token, 256 random bits, that the daemon holds
in its memory alone and forgets once it is claimed or expired. Whoever claims it over a session
pairs the device that session's certificate is: so a code is a secret until it is claimed, and
nothing after.

`hmz-pair:` and then the base64url of a JSON object, so that it is one word to paste.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from hmz.trust.identity import is_fingerprint

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.trust.devices import Devices

__all__ = [
    "HELD",
    "LIFETIME",
    "LONGEST",
    "NOT_PAIRED",
    "NOT_VALID",
    "PREFIX",
    "SHORTEST",
    "UNPAIRED",
    "Code",
    "Codes",
    "InvalidCodeError",
    "allows",
    "claim",
    "read",
]

#: What every pairing code begins with.
PREFIX = "hmz-pair:"

#: How long a code admits, in seconds, unless it was asked to live otherwise.
LIFETIME = 600

#: The shortest and the longest a code may be asked to live, in seconds.
SHORTEST = 60
LONGEST = 86_400

#: How many codes a daemon holds at once; making one more forgets the oldest.
HELD = 16

#: The methods an unpaired session may call: saying hello, claiming a code, and asking what
#: there is to call.
UNPAIRED = frozenset({"session.hello", "pair.claim", "rpc.discover"})

#: Why any other method is refused to an unpaired session, with 401.
NOT_PAIRED = "This device is not paired: claim a pairing code first."

#: Why a token that is not held, was claimed or has expired is refused, with 403.
NOT_VALID = "That pairing code is not valid: ask for a new one."

#: The keys of a code's JSON, and no others.
_KEYS = frozenset({"v", "id", "routes", "token", "expires"})


class InvalidCodeError(Exception):
    """A pairing code the daemon does not hold, or no longer does."""

    def __init__(self) -> None:
        super().__init__(NOT_VALID)


@dataclass(frozen=True)
class Code:
    """One pairing code, as it is written and read.

    Attributes:
      id: The daemon id the client is to pin.
      routes: The routes to reach the daemon over, in the order they are tried.
      token: 32 random bytes in base64url, which the claim gives back.
      expires: The moment, in Unix seconds, it stops admitting.
    """

    id: str
    routes: tuple[str, ...]
    token: str
    expires: int

    def text(self) -> str:
        """The code as a client is handed it: `hmz-pair:` and the base64url of its JSON."""
        said = {
            "v": 1,
            "id": self.id,
            "routes": list(self.routes),
            "token": self.token,
            "expires": self.expires,
        }
        return PREFIX + _b64url(json.dumps(said, ensure_ascii=False).encode())


def read(text: str) -> Code:
    """A pairing code, read back.

    Args:
      text: What the user pasted: `hmz-pair:...`, surrounding white space allowed.

    Returns:
      The code. Whether it is still valid is the daemon's to say.

    Raises:
      ValueError: If it is not a pairing code: another prefix, not base64url of a JSON
        object, or one of other keys or of a value of the wrong type.
    """
    text = text.strip()
    if not text.startswith(PREFIX):
        raise ValueError("That is not a pairing code: one begins with hmz-pair:.")
    encoded = text.removeprefix(PREFIX)
    try:
        held: object = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
    except (ValueError, binascii.Error) as why:
        raise ValueError("That is not a pairing code: it does not decode.") from why
    if not isinstance(held, dict) or frozenset(cast("dict[str, Any]", held)) != _KEYS:
        raise ValueError("That is not a pairing code: it holds other keys.")
    said = cast("dict[str, Any]", held)
    routes: object = said["routes"]
    if (
        type(said["v"]) is not int
        or said["v"] != 1
        or not is_fingerprint(said["id"])
        or not isinstance(routes, list)
        or not routes
        or not all(isinstance(one, str) for one in cast("list[object]", routes))
        or not isinstance(said["token"], str)
        or type(said["expires"]) is not int
    ):
        raise ValueError("That is not a pairing code: a value of it is not one.")
    return Code(
        said["id"],
        tuple(cast("list[str]", routes)),
        said["token"],
        said["expires"],
    )


class Codes:
    """The tokens of the codes a daemon made: in its memory alone, at most 16 of them."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """Holds no code yet.

        Args:
          clock: What says the time, in Unix seconds.
        """
        self._clock = clock
        #: Each token held, to the moment it expires, oldest first.
        self._held: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()

    def make(
        self,
        daemon_id: str,
        routes: list[str] | tuple[str, ...],
        seconds: int = LIFETIME,
    ) -> Code:
        """Makes a code, with a token of its own, and holds the token.

        Args:
          daemon_id: This daemon's id.
          routes: The routes the code is to carry.
          seconds: How long it admits, 60 to 86 400.

        Returns:
          The code.

        Raises:
          ValueError: If `seconds` is not a whole number of seconds in bounds, which is
            refused 400 with this message.
        """
        if type(seconds) is not int or not SHORTEST <= seconds <= LONGEST:
            raise ValueError("A code lives 60 to 86400 seconds.")
        token = _b64url(secrets.token_bytes(32))
        expires = int(self._clock()) + seconds
        with self._lock:
            self._forget()
            self._held[token] = expires
            while len(self._held) > HELD:
                self._held.popitem(last=False)
        return Code(daemon_id, tuple(routes), token, expires)

    def claims[T](self, token: str, admits: Callable[[], T]) -> T:
        """Admits what a token is claimed for, once: held and not expired, then forgotten.

        Every held token is compared, each in constant time, so that how long this takes
        says nothing of which of them came closest. The token is forgotten only once the
        admitting is done, so that a device the daemon failed to write down can claim the
        same code again.

        Args:
          token: What the claim gave.
          admits: What the claim does -- pairing the device -- called holding the codes.

        Returns:
          What `admits` returned.

        Raises:
          InvalidCodeError: If no held token is it.
        """
        with self._lock:
            self._forget()
            found = ""
            for one in self._held:
                if secrets.compare_digest(one.encode(), token.encode()):
                    found = one
            if not found:
                raise InvalidCodeError
            admitted = admits()
            del self._held[found]
        return admitted

    def _forget(self) -> None:
        """Lets go of every token that has expired. Called holding the lock."""
        now = self._clock()
        for one in [one for one, expires in self._held.items() if expires <= now]:
            del self._held[one]


def claim(
    codes: Codes, devices: Devices, token: str, name: str, fingerprint: str
) -> str:
    """Pairs the device a session is, on the token it claimed.

    Args:
      codes: The daemon's codes.
      devices: Its paired devices.
      token: The code's token, as `pair.claim` gave it.
      name: The device's name, as `pair.claim` gave it.
      fingerprint: The device fingerprint of the session that claimed.

    Returns:
      The name the device was paired under, made unique.

    Raises:
      ValueError: If `name` is not a device name, which leaves the token held.
      InvalidCodeError: If the token is not held.
      OSError: If the device cannot be written down, which leaves the token held too.
    """
    devices.check(name)
    return codes.claims(token, lambda: devices.add(name, fingerprint))


def allows(method: str, *, paired: bool) -> bool:
    """Whether a session may call a method: any, paired; three, unpaired."""
    return paired or method in UNPAIRED


def _b64url(data: bytes) -> str:
    """Bytes in base64url, without padding."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
