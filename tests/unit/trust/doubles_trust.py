"""What the trust tests stand in for: a pipe held in memory, devices, and the files they keep.

Nothing here opens a socket: a pipe is two queues of bytes, one each way, and a device is made
in a home of the test's own, with `hmz.coganchor.atomic` replaced by a plain write.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import TYPE_CHECKING

from hmz.trust import identity

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    import pytest


class End:
    """One end of a pipe held in memory: what a connected socket is, without the socket."""

    def __init__(
        self, arriving: queue.Queue[bytes], leaving: queue.Queue[bytes]
    ) -> None:
        self._arriving = arriving
        self._leaving = leaving
        self._held = b""
        self._lock = threading.Lock()
        self.closed = False
        #: Every byte written, in order, which a test reads to say what crossed.
        self.sent = bytearray()

    def recv(self, bufsize: int, /) -> bytes:
        with self._lock:
            if not self._held:
                if self.closed:
                    return b""
                self._held = self._arriving.get()
            out, self._held = self._held[:bufsize], self._held[bufsize:]
            return out

    def sendall(self, data: bytes, /) -> None:
        if self.closed:
            raise BrokenPipeError("closed")
        self.sent += data
        self._leaving.put(bytes(data))

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        # The other end reads its end of the pipe, and this one stops waiting on its own.
        self._leaving.put(b"")
        self._arriving.put(b"")


def pipe() -> tuple[End, End]:
    """A pipe held in memory: two ends, each reading what the other writes."""
    one: queue.Queue[bytes] = queue.Queue()
    other: queue.Queue[bytes] = queue.Queue()
    return End(one, other), End(other, one)


def plain_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts a plain write where `hmz.coganchor.atomic.writes` is."""
    from hmz.coganchor import atomic

    def writes(
        at: Path, said: str | bytes | Iterable[bytes], *, mode: int | None = None
    ) -> None:
        if isinstance(said, str):
            at.write_text(said, encoding="utf-8")
        else:
            at.write_bytes(said if isinstance(said, bytes) else b"".join(said))
        if mode is not None:
            os.chmod(at, mode)  # noqa: PTH101

    monkeypatch.setattr(atomic, "writes", writes)


def device(home: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    """A device of its own home, made there as this machine's would be."""
    was = os.environ["XDG_DATA_HOME"]
    monkeypatch.setenv("XDG_DATA_HOME", str(home))
    try:
        return identity.device()
    finally:
        monkeypatch.setenv("XDG_DATA_HOME", was)
