"""What crosses the relay before a data channel opens, and what each side reads off it.

The relay carries signals it cannot be trusted with: it could hand either side a description of
its own and sit between them. So the daemon signs both DTLS fingerprints, the browser's from the
offer and its own from the answer, with its device key, and the side that offered checks that
signature against the daemon id it pins before a byte crosses the channel. DTLS then holds each
side to the certificate its fingerprint names, which is also how the daemon knows a browser: by
the fingerprint of the certificate the browser keeps for every connection, `dtls:` and its
base32.

Nothing here touches the network or aiortc: these are the texts, and the one interface the
relay's signals are handed over by.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Protocol

__all__ = [
    "CHUNK",
    "LABEL",
    "Refused",
    "Signals",
    "device",
    "fingerprint",
    "signed",
]

#: The label of the one data channel an offer opens.
LABEL = "hmz"

#: The most bytes one message of the data channel carries.
CHUNK = 16384

#: What a signature over two fingerprints opens with, so that it signs nothing else.
_CONTEXT = "hmz-webrtc/1"

#: A DTLS fingerprint line of a description, its algorithm and its value.
_FINGERPRINT = re.compile(r"^a=fingerprint:(\S+)[ \t]+(\S+)[ \t]*\r?$", re.MULTILINE)

#: The value of a SHA-256 fingerprint: 32 bytes in hex, a colon between each.
_SHA256 = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){31}")


class Refused(ConnectionError):  # noqa: N818 -- what happened, not what went wrong
    """A peer whose signals or channel are not what the protocol has them be, or not who it is.

    Raised for a signal that cannot be read, a description with no one SHA-256 fingerprint, an
    answer whose certificate is not the daemon pinned or whose signature does not verify, and a
    data channel other than the one an offer opens. The connection is closed by then.
    """


class Signals(Protocol):
    """The signals of one join, in each direction, as the relay carries them.

    What is sent and received is the `data` of a relay's `signal` message: the relay's own
    envelope, and which join it belongs to, are the caller's to add and take off. A queue in
    each direction is one; the relay's control connection, read for one `conn`, is another.
    The daemon's refusal of the join is the relay's `refuse` for that `conn`, which the relay
    passes to the browser (Section 4.7.10 of wire.md).
    """

    def send(self, data: dict[str, Any]) -> None:
        """Sends one signal to the other side.

        Args:
          data: The signal, a JSON object.

        Raises:
          OSError: If the relay cannot be reached any more.
        """
        ...

    def receive(self, timeout: float) -> object:
        """The next signal from the other side, waiting for one.

        Args:
          timeout: How long to wait for it, in seconds.

        Returns:
          The signal, as the relay carried it: a JSON value, which is read here.

        Raises:
          TimeoutError: If none arrives within `timeout`.
          EOFError: If none ever will: the relay or the other side has gone.
        """
        ...

    def refuse(self, why: str) -> None:
        """Refuses the join, saying why: the relay's `refuse`, sent once, and no signal after.

        Args:
          why: One sentence, which the browser is told.

        Raises:
          OSError: If the relay cannot be reached any more.
        """
        ...


def fingerprint(sdp: str) -> str:
    """The SHA-256 DTLS fingerprint of a session description, as written there.

    Each media section may say the fingerprint again, and a description may say others beside
    it, of other algorithms; what is signed and pinned is the one SHA-256 value.

    Args:
      sdp: The description, an offer or an answer.

    Returns:
      The value, its hex and colons as the description writes them.

    Raises:
      Refused: If the description says no SHA-256 fingerprint, a malformed one, or two.
    """
    values = {
        value for name, value in _FINGERPRINT.findall(sdp) if name.lower() == "sha-256"
    }
    if len(values) != 1:
        msg = "A description must say exactly one sha-256 fingerprint."
        raise Refused(msg)
    (value,) = values
    if not _SHA256.fullmatch(value):
        msg = f"{value} is not a sha-256 fingerprint."
        raise Refused(msg)
    return value


def device(sdp: str) -> str:
    """The device fingerprint of the side that wrote a description: `dtls:` and a base32.

    Args:
      sdp: The description, a browser's offer.

    Returns:
      `dtls:` followed by the base32, lowercase and unpadded, of the 32 bytes of its SHA-256
      fingerprint.

    Raises:
      Refused: If the description has no one SHA-256 fingerprint.
    """
    raw = bytes.fromhex(fingerprint(sdp).replace(":", ""))
    return "dtls:" + base64.b32encode(raw).decode().rstrip("=").lower()


def signed(offer: str, answer: str) -> bytes:
    """What the daemon signs, and the offering side verifies, for one offer and its answer.

    Args:
      offer: The offer's description.
      answer: The answer's description.

    Returns:
      `hmz-webrtc/1`, the offer's SHA-256 fingerprint and the answer's, a line feed between
      each, in UTF-8.

    Raises:
      Refused: If either description has no one SHA-256 fingerprint.
    """
    return f"{_CONTEXT}\n{fingerprint(offer)}\n{fingerprint(answer)}".encode()
