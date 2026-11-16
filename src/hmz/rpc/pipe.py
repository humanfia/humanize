"""What a session's frames are carried over: a byte pipe, shaped like a connected socket.

A carrier (Section 3.2.1 of wire.md) is an ordered, reliable stream of bytes in each direction
which either side may close, and the mutual TLS of Section 4.4 over an untrusted one is another
such stream. Frames go over whichever is the top of the two (Section 3.5.3), so both are a
:class:`Pipe`: each carrier of `hmz.reach`, the TLS session of `hmz.trust`, and a WebRTC data
channel of `hmz.rtc` implement these three methods, and a :class:`hmz.rpc.Peer` runs over any
of them. This is the one definition of it; the others import it from here.

The three are a connected socket's own, so a stream socket is a pipe as it is -- but for
:meth:`Pipe.close` waking a reader, which closing a socket alone does not promise on every
system: a socket wanting that is shut down (`socket.SHUT_RDWR`) before it is closed.

Blocking rather than awaited, because the daemon is threads and so are pyOpenSSL and
websockets' synchronous client and server; an asyncio carrier (aiortc's data channel) puts a
blocking face on itself with a queue, and an asyncio caller reaches a peer through
`asyncio.to_thread`.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["Pipe"]


class Pipe(Protocol):
    """An ordered, reliable stream of bytes in each direction, which either side may close.

    A peer calls :meth:`recv` from one thread of its own and :meth:`sendall` from any, one
    call at a time, and :meth:`close` from any thread, while a :meth:`recv` may be blocked in
    another.
    """

    def recv(self, size: int, /) -> bytes:
        """Waits for bytes, and gives back between one and `size` of them.

        Returns:
          What arrived, in order; `b""` once the far end has closed or :meth:`close` was called,
          which a pipe may also say by raising :class:`OSError`.
        """
        ...

    def sendall(self, data: bytes, /) -> None:
        """Sends all of `data`, in order, waiting as long as the pipe needs.

        Raises:
          OSError: If the pipe is closed or broke.
        """
        ...

    def close(self) -> None:
        """Closes both directions, and wakes a :meth:`recv` blocked in another thread.

        Closing a pipe already closed does nothing.
        """
        ...
