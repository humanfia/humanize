"""Just enough of the protocol buffer wire format to read a field nobody named.

One of the CLIs humanize drives keeps its trajectory as protobuf, and ships no
schema to read it back with: the `.proto` files are the vendor's, the messages
are theirs, and what reaches this machine is the bytes. So the fields are reached
by number, which is the half of protobuf that is self-describing -- every field
carries its number and its wire type ahead of it, and a reader that knows only
those can walk a message it has never been told the shape of.

Which is why this is here rather than `protobuf` being a dependency: the library
reads a message against a schema, and there is no schema. What it would buy --
names, types, defaults -- is exactly what is missing, so it would be a dependency
that could not be used for the one thing it is for.

Unknown fields are the ordinary case rather than an error, and so are fields that
are not what a caller hoped: what is read out of somebody else's file is only ever
what the bytes turned out to hold, and a reader that raised on a message it did not
recognise would be a trace that stops on the first release that moved a field.
Nothing here raises. A truncated message ends where it was cut, a field that does
not fit stops the walk, and the caller gets what was read before that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The wire types this reads. `VARINT` is a number, `BYTES` is a string, an
#: embedded message or a packed array -- which of the three is a question the
#: bytes cannot answer, so it is the caller that decides by what it asks for.
#: The two fixed widths are skipped over rather than read: nothing reached here
#: is stored as one, and skipping keeps the walk on the rails past a field that
#: is.
VARINT, SIXTY_FOUR, BYTES, THIRTY_TWO = 0, 1, 2, 5

#: The widest a varint may be before it is one the bytes cannot be holding: the
#: format's own numbers are 64 bits, so a tenth group of seven is a message that
#: was cut or was never one.
_WIDEST = 63


def fields(buf: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Every field of one message, as `(number, wire type, value)`.

    Args:
        buf: The message, which need not be whole.

    Yields:
        One per field in the order written, a varint as its `int` and a
        length-delimited field as its `bytes`. Stops where the bytes stop making
        sense, which is where a truncated message ends.
    """
    at, size = 0, len(buf)
    while at < size:
        key, at = _varint(buf, at)
        if key is None or at is None:
            return
        number, kind = key >> 3, key & 7
        if kind == VARINT:
            value, at = _varint(buf, at)
            if value is None or at is None:
                return
            yield number, kind, value
        elif kind == BYTES:
            length, at = _varint(buf, at)
            if length is None or at is None or at + length > size:
                return
            yield number, kind, buf[at : at + length]
            at += length
        elif kind == SIXTY_FOUR:
            at += 8
        elif kind == THIRTY_TWO:
            at += 4
        else:
            # A group, or a wire type nobody has minted: neither is skippable
            # without knowing where it ends, so the walk stops rather than
            # guessing its way through the rest.
            return


def _varint(buf: bytes, at: int) -> tuple[int | None, int | None]:
    """One base-128 number, and where it ended, or `(None, None)` for one cut short."""
    value, shift, size = 0, 0, len(buf)
    while at < size:
        byte = buf[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > _WIDEST:
            return None, None
    return None, None


def message(buf: bytes, number: int) -> bytes | None:
    """The first embedded message at ``number``, or None where there is none."""
    for found, kind, value in fields(buf):
        if found == number and kind == BYTES and isinstance(value, bytes):
            return value
    return None


def numbers(buf: bytes) -> dict[int, int]:
    """Every varint of one message, by field number, last one winning.

    What a usage message is: a handful of counts under numbers rather than names.
    """
    return {
        number: value
        for number, kind, value in fields(buf)
        if kind == VARINT and isinstance(value, int)
    }


def text(buf: bytes, number: int) -> str:
    """The field at ``number`` read as UTF-8, or "" where it is not there or not text."""
    for found, kind, value in fields(buf):
        if found == number and kind == BYTES and isinstance(value, bytes):
            try:
                return value.decode()
            except UnicodeDecodeError:
                return ""
    return ""


def moment(buf: bytes, number: int) -> float | None:
    """A `google.protobuf.Timestamp` at ``number``, as epoch seconds.

    Two fields, seconds and nanos, which is the one vendor message shape common
    enough to be worth naming here.
    """
    held = message(buf, number)
    if held is None:
        return None
    said = numbers(held)
    seconds = said.get(1)
    if seconds is None:
        return None
    return seconds + said.get(2, 0) / 1_000_000_000
