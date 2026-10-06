"""What the tracing tests write their logs with."""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

#: A window that cuts nothing off.
ALL = (-math.inf, math.inf)


def jsonl(path: Path, rows: Iterable[dict[str, Any] | str]) -> Path:
    """Writes records as JSON Lines, making the directory; a `str` row is written verbatim."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        (row if isinstance(row, str) else json.dumps(row)) + "\n" for row in rows
    )
    path.write_text(text, encoding="utf-8")
    return path


def varint(value: int) -> bytes:
    """One protobuf base-128 number."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field(number: int, value: int | bytes | str) -> bytes:
    """One protobuf field: a varint for an `int`, length-delimited otherwise."""
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    raw = value.encode() if isinstance(value, str) else value
    return varint(number << 3 | 2) + varint(len(raw)) + raw


def stamp(number: int, seconds: int, nanos: int = 0) -> bytes:
    """A `google.protobuf.Timestamp` held at ``number``."""
    return field(number, field(1, seconds) + field(2, nanos))
