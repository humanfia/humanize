"""The frames a session carries (Section 6.3 of wire.md): a length, then one JSON object.

Every byte after a session's security layer, if it has one, belongs to a frame: the length of
its payload as an unsigned 32-bit big-endian integer, then the payload, one JSON object in
UTF-8. A length of nothing, or of more than :data:`LONGEST`, is a pipe carrying something else,
and the session it arrives on is closed.
"""

from __future__ import annotations

import json
import struct
from typing import Any

__all__ = ["LONGEST", "FrameError", "Frames", "encode"]

#: The longest payload a reader accepts, and so the longest a writer may send: 32 MiB.
LONGEST = 33_554_432

#: The length ahead of every payload.
_HEAD = struct.Struct(">I")


class FrameError(ValueError):
    """A frame no reader accepts: one of no bytes, or of more than :data:`LONGEST`.

    Attributes:
      whole: The payloads that were whole ahead of it in the same read, which are still handed
        out, once and in order, before the session closes.
    """

    def __init__(self, message: str, whole: list[bytes] | None = None) -> None:
        super().__init__(message)
        self.whole = whole or []


def encode(message: dict[str, Any]) -> bytes:
    """One frame, ready to be written.

    Non-ASCII characters are written as themselves, and a value JSON has no type for -- a path,
    a datetime -- as its text (Section 6.3.3). NaN and the infinities are not JSON, and are
    refused rather than written as the tokens no other reader parses.

    Args:
      message: What it carries.

    Returns:
      The length and then the payload.

    Raises:
      FrameError: If the payload is longer than a reader accepts, which is a frame that must
        not be sent.
      ValueError: If the message holds what JSON cannot: NaN, a cycle.
      TypeError: If it holds a mapping whose keys are not text.
    """
    payload = json.dumps(
        message, ensure_ascii=False, default=str, allow_nan=False
    ).encode()
    if len(payload) > LONGEST:
        raise FrameError(f"a frame of {len(payload)} bytes is more than {LONGEST}")
    return _HEAD.pack(len(payload)) + payload


class Frames:
    """A pipe read a piece at a time, and the whole payloads that came out of it.

    A read hands back whatever has arrived, which is half a frame as often as it is two: what
    is read is fed in here, and each payload that is now whole comes back out exactly once and
    in the order it arrived (Section 6.3.4).
    """

    def __init__(self) -> None:
        #: What has arrived and is not a whole frame yet, grown in place: a frame of 32 MiB
        #: arrives in hundreds of reads, and copying it whole at each would be quadratic.
        self._held = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        """Takes what was read, and gives back the payload of every whole frame in it.

        Args:
          data: What came off the pipe.

        Returns:
          Each payload now complete, in the order they arrived; nothing where none is.

        Raises:
          FrameError: If a length arrives that no frame has, after which the session is to be
            closed and nothing more fed here; it holds the payloads whole ahead of that length.
        """
        held = self._held
        held += data
        at = 0
        whole: list[bytes] = []
        while len(held) - at >= _HEAD.size:
            (length,) = _HEAD.unpack_from(held, at)
            if not 0 < length <= LONGEST:
                held.clear()
                raise FrameError(
                    f"a frame of {length} bytes is not one of these", whole
                )
            if len(held) - at < _HEAD.size + length:
                break
            begins = at + _HEAD.size
            at = begins + length
            whole.append(bytes(held[begins:at]))
        del held[:at]
        return whole
