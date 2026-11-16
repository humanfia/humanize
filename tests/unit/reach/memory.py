"""A pipe in memory: what one end writes the other reads, and either may close."""

from __future__ import annotations

import threading


class Memory:
    """One end of a pipe held in memory, written to by whoever holds :attr:`far`."""

    def __init__(self, *, trusted: bool = False) -> None:
        self.trusted = trusted
        self.held = bytearray()
        self.written = bytearray()
        self.closed = False
        self._changed = threading.Condition()

    def feed(self, data: bytes) -> None:
        """What the far end says."""
        with self._changed:
            self.held += data
            self._changed.notify_all()

    def end(self) -> None:
        """The far end closing."""
        with self._changed:
            self.closed = True
            self._changed.notify_all()

    def recv(self, size: int) -> bytes:
        with self._changed:
            self._changed.wait_for(lambda: self.held or self.closed)
            read = bytes(self.held[:size])
            del self.held[:size]
            return read

    def sendall(self, data: bytes) -> None:
        with self._changed:
            if self.closed:
                raise BrokenPipeError("closed")
            self.written += data
            self._changed.notify_all()

    def close(self) -> None:
        self.end()

    def wrote(self, wanted: bytes, timeout: float = 5.0) -> bool:
        """Whether everything wanted has been written, waiting for it a while."""
        with self._changed:
            return self._changed.wait_for(
                lambda: bytes(self.written) == wanted, timeout
            )
