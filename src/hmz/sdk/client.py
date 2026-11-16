"""One session of `protocol/wire.md` with one daemon, as a program of the SDK holds it.

The client is the runtime's own (:class:`hmz.runtime.doing.daemons.Client`, what the registry
of other machines' daemons hands out too): this adds only reaching this machine's daemon,
which starting it where none runs is the daemon layer's to do (Section 4.21.1 of python.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.runtime.doing.daemons import Client as Session

if TYPE_CHECKING:
    from hmz.rpc import Kind

__all__ = ["Client"]

#: How long this machine's daemon is given to take the session.
_PATIENCE = 10.0


class Client(Session):
    """One session with one daemon; a context manager, closed to end it."""

    @classmethod
    def local(cls, *, name: str = "", kind: Kind = "sdk") -> Client:
        """A session with this machine's daemon over `unix:`, started where none runs.

        Args:
          name: What this client is called, "" for this machine's host name.
          kind: What it is: `sdk`, `cli`, `tui`.

        Raises:
          OSError: If the daemon cannot be reached or started, or speaks another protocol --
            `EADDRINUSE`, saying so.
        """
        from hmz import daemon
        from hmz.daemon import where
        from hmz.reach.pipes import SocketPipe

        daemon.start()
        one = where.connects(where.at(), _PATIENCE)
        one.settimeout(None)
        return cls.over(SocketPipe(one, trusted=True), name=name, kind=kind)
