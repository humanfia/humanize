"""A Unix socket that is two byte buffers, for the relays `hmz internal` runs.

Put in place of `socket.socket` for the length of a test: nothing is bound or connected, and a
test says what the flow on the other end answers.
"""

from __future__ import annotations

import io
import sys
import threading
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import pytest


class Socket:
    """One socket a relay made: where it connected, what it wrote, and what it read back."""

    def __init__(self, family: int = 0, kind: int = 0) -> None:
        del family, kind
        self.at = ""
        self.written = io.BytesIO()
        self.answer = b""
        self.refuses: OSError | None = None
        self.closed = False
        self.shut = threading.Event()

    def connect(self, at: str) -> None:
        self.at = at
        if self.refuses is not None:
            raise self.refuses

    def makefile(self, mode: str) -> Any:
        if "w" in mode and "r" not in mode:
            return _Kept(self.written)
        if "w" in mode:
            return _Both(self.written, io.BytesIO(self.answer))
        return io.BytesIO(self.answer)

    def shutdown(self, how: int) -> None:
        del how
        self.shut.set()

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class _Kept(io.BufferedIOBase):
    """A writable file over a buffer that outlives it being closed."""

    def __init__(self, into: io.BytesIO) -> None:
        super().__init__()
        self._into = into

    def writable(self) -> bool:
        return True

    def write(self, data: Any) -> int:
        return self._into.write(data)


class _Both(_Kept):
    """A file read from one buffer and written to another."""

    def __init__(self, into: io.BytesIO, out_of: io.BytesIO) -> None:
        super().__init__(into)
        self._out_of = out_of

    def readable(self) -> bool:
        return True

    def readline(self, size: int | None = -1) -> bytes:
        return self._out_of.readline(size)


def sockets(monkeypatch: pytest.MonkeyPatch, made: Socket) -> None:
    """Has the next socket made be `made`."""
    import socket

    def making(*args: object) -> Socket:
        del args
        return made

    monkeypatch.setattr(socket, "socket", making)


def stdin(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    """Has what is read off stdin be `data`."""
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
