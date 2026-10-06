"""A socket that is a queue: what the daemon's public functions write, and what they read back.

Nothing here binds, connects or listens. A test hands one of these to whatever would have
connected -- `where.connects`, a listening socket's `accept` -- and says what the far end
answers each frame with.
"""

from __future__ import annotations

import queue
import socket
import threading
from typing import TYPE_CHECKING, Any

from hmz.daemon.proto import Frames, asked

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


class Wire:
    """One end of a connection whose other end is a function."""

    def __init__(
        self,
        answers: Callable[[bytes, dict[str, Any]], Iterable[bytes]] | None = None,
        *,
        arriving: Iterable[bytes] = (),
    ) -> None:
        """Holds what the far end does.

        Args:
          answers: What the far end writes back for each whole frame written to it.
          arriving: What the far end says before it is asked anything.
        """
        self.sent: list[tuple[bytes, dict[str, Any]]] = []
        self.raw: list[bytes] = []
        self.closed = False
        self.ended = threading.Event()
        self.wrote = threading.Event()
        self._answers = answers
        self._frames = Frames()
        self._inbox: queue.SimpleQueue[bytes] = queue.SimpleQueue()
        self._peeked = b""
        for one in arriving:
            self._inbox.put(one)

    def settimeout(self, seconds: float | None) -> None:
        """Takes the timeout, which a queue does not need."""
        del seconds

    def sendall(self, data: bytes) -> None:
        """Takes what was written, and queues what the far end answers it with."""
        if self.closed:
            raise OSError("closed")
        self.raw.append(data)
        self.wrote.set()
        for kind, payload in self._frames.feed(data):
            said = asked(payload)
            self.sent.append((kind, said))
            if self._answers is not None:
                for answer in self._answers(kind, said):
                    self._inbox.put(answer)

    def recv(self, size: int, flags: int = 0) -> bytes:
        """What the far end has said, waiting for it; nothing once either end has closed."""
        if not self._peeked:
            if self.closed and self._inbox.empty():
                return b""
            try:
                self._peeked = self._inbox.get(timeout=5)
            except queue.Empty:
                return b""
        held = self._peeked[:size]
        if not flags & socket.MSG_PEEK:
            self._peeked = self._peeked[size:]
        return held

    def shutdown(self, how: int) -> None:
        """Ends the far end's saying, as a closed socket does."""
        del how
        self._inbox.put(b"")

    def close(self) -> None:
        """Closes it, waking a reader."""
        self.closed = True
        self.ended.set()
        self._inbox.put(b"")

    def fileno(self) -> int:
        """No descriptor at all."""
        return -1

    def say(self, data: bytes) -> None:
        """Has the far end say something unasked."""
        self._inbox.put(data)
