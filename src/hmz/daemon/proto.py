"""What the socket between a workspace's runs and whatever reads them carries.

A frame is a kind and some bytes, and there are three kinds. One is a frontend's: one JSON
object, a request one way and a message the other, which is the whole of what a frontend of a
host and the host say to each other. One is a line asking the runs a question about
themselves, answered with one of the same and closed. And one says the runs have let go of
whatever is reading, and why -- which is what a reader speaking something else is told rather
than being left waiting.

Framed rather than a raw pipe both ways, because a message has to arrive whole: a length ahead
of each is what tells one JSON object from the next, and a socket closing mid-way from one
that has said all it had to say.
"""

from __future__ import annotations

import json
import struct
from typing import Any, cast

__all__ = [
    "CONTROL",
    "GONE",
    "MESSAGE",
    "PROTOCOL",
    "Frames",
    "asked",
    "frame",
    "spoken",
]

#: The runs have let go of whatever is reading, and why.
GONE = b"X"
#: A question about the runs rather than a frontend reading them, answered with one of the
#: same.
CONTROL = b"C"
#: One JSON object between a frontend and the host it is attached to: a request on its way in,
#: and a reply or a message about the runs on its way out.
MESSAGE = b"M"

#: Which version of what a frontend and a host say to each other this is, written down beside
#: a host's socket so that a frontend reaching one it cannot read says so rather than hanging.
PROTOCOL = 1

#: How long a frame may be. A message is kilobytes and a replay is many of them; a length
#: longer than this is a socket that is not carrying this protocol.
_LONGEST = 1 << 22

#: The kind, and then the length: one byte and four, which is what every frame begins with.
_HEAD = struct.Struct(">cI")


def frame(kind: bytes, payload: bytes = b"") -> bytes:
    """One frame, ready to be written.

    Args:
      kind: Which of the three it is.
      payload: What it carries.

    Returns:
      The bytes.
    """
    return _HEAD.pack(kind, len(payload)) + payload


def spoken(kind: bytes, said: dict[str, Any]) -> bytes:
    """One frame carrying a mapping, which is how a question and its answer are written."""
    return frame(kind, json.dumps(said).encode())


def asked(payload: bytes) -> dict[str, Any]:
    """What one such frame said, and nothing at all for one that is not a mapping."""
    try:
        held: object = json.loads(payload.decode())
    except (ValueError, UnicodeDecodeError):
        return {}
    return cast("dict[str, Any]", held) if isinstance(held, dict) else {}


class Frames:
    """A socket read a piece at a time, and the whole frames that came out of it.

    A stream socket hands back whatever has arrived, which is half a frame as often as it is
    two: what is read is fed in here and what has been completed comes back out.
    """

    def __init__(self) -> None:
        #: What has arrived and is not a whole frame yet, which is nothing most of the time:
        #: a read is usually one whole frame, being a message on its way to a frontend or a
        #: request on its way back.
        self._held = b""

    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]:
        """Takes what was read, and gives back every whole frame in it.

        Answered whole rather than a frame at a time. What is read is taken out of the buffer
        before any of it is handed over, so that a caller which stops reading partway -- a
        frontend that has just been told the runs let go of it -- cannot leave a frame that has
        been handed out sitting in the buffer to be handed out again.

        Args:
          data: What came off the socket.

        Returns:
          The kind and the payload of each frame that is now complete, in the order they
          arrived, and nothing at all where none is.

        Raises:
          ValueError: If a length arrives that no frame of this protocol has, which is a
            socket carrying something else.
        """
        held = self._held + data if self._held else data
        at = 0
        whole: list[tuple[bytes, bytes]] = []
        while len(held) - at >= _HEAD.size:
            kind, length = _HEAD.unpack_from(held, at)
            if length > _LONGEST:
                self._held = b""
                raise ValueError(f"a frame of {length} bytes is not one of these")
            if len(held) - at < _HEAD.size + length:
                break
            begins = at + _HEAD.size
            at = begins + length
            whole.append((kind, held[begins:at]))
        self._held = held[at:] if at else held
        return whole
