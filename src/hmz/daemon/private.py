"""A daemon whose hosts are held in this process: a private daemon, or a test's own.

A program that runs an epic on driver objects -- which only that program holds -- runs it
through a daemon of its own in its own process (Section 4.19 of python.md), reached over a
socket pair; a test stands this machine's daemon in with one listening on the test's own
socket. Either is this machine's daemon in every other way: every session is a session of
`protocol/wire.md`, every method is served as :class:`hmz.daemon.routing.Router` serves it,
and every host is a :class:`hmz.runtime.Host` carried over a socket pair as a host process is
(:mod:`hmz.daemon.carrying`) -- on a thread of this process instead, standing in no directory
of its own, and holding its workspace as `holding` makes it.
"""

from __future__ import annotations

import socket
import threading
from typing import TYPE_CHECKING, Any

from hmz.daemon.hosts import Hosted, Hosts
from hmz.daemon.routing import Router

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.rpc import Call, Pipe
    from hmz.runtime import Holding

__all__ = ["Private"]

#: How long a host is given to say what it holds.
_PATIENCE = 10.0

#: How long a host's thread is given to end once the daemon has closed.
_ENDING = 10.0


class _Held(Hosts):
    """Every host the daemon took on, each held on a thread of this process."""

    def __init__(
        self, changed: Callable[[], None], holding: Callable[[str], Holding]
    ) -> None:
        super().__init__(changed)
        self._holding = holding
        #: The thread of every host taken on, which :meth:`ended` waits for.
        self._threads: list[threading.Thread] = []

    def ended(self) -> None:
        """Waits for the thread of every host let go of, so that none outlives its daemon.

        One that did would still read where Humanize keeps this machine's files, which is
        the program's own again once a private daemon has gone (Section 4.19 of python.md).
        """
        threads, self._threads = self._threads, []
        for one in threads:
            one.join(_ENDING)

    def _starts(
        self, workspace: str, slot: str, env: dict[str, str] | None = None
    ) -> Hosted:
        """Holds a host on a thread of this process, and links it; `env` is the process's."""
        del env
        from hmz.daemon.carrying import serves
        from hmz.reach.pipes import SocketPipe
        from hmz.rpc import Peer
        from hmz.runtime import Host

        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        held = Host(self._holding(workspace), slot)
        thread = threading.Thread(
            target=serves,
            args=(held, workspace, theirs),
            kwargs={"slot": slot},
            daemon=True,
            name="hmz-host",
        )
        self._threads = [one for one in self._threads if one.is_alive()]
        self._threads.append(thread)
        thread.start()
        hosted = Hosted(workspace, slot)
        hosted.peer = Peer(
            SocketPipe(ours, trusted=True),
            hosted.told,
            on_close=lambda: self.went(hosted),
            name="hmz-link",
        )
        try:
            said: Any = hosted.peer.call("status", {}, timeout=_PATIENCE)
        except Exception as why:
            hosted.peer.close()
            raise OSError(f"the host did not say what it holds: {why}") from why
        hosted.said = dict(said)
        return hosted


class Private(Router):
    """A daemon whose hosts are held in this process.

    Args:
      at: Its daemon directory.
      listening: Its socket, bound and listening, which :meth:`start` takes sessions on; one
        never started takes them only as :meth:`paired` hands them over.
      holding: What a workspace is held as, by its path: by its hosts, and by `flows.check`.
    """

    def __init__(
        self,
        at: Path,
        listening: socket.socket,
        holding: Callable[[str], Holding],
    ) -> None:
        super().__init__(at, listening, kept=True)
        self._held = _Held(self._touched, holding)
        self.hosts = self._held
        self.hosts.ai = self.links

        def checks(call: Call) -> Any:
            from hmz.daemon.api.flows import checked

            return checked(holding(str(call.params["workspace"])), call.params)

        self.families["flows.check"] = checks
        self.dispatcher.register("flows.check", self._guarded("flows.check", checks))

    def close(self) -> None:
        """Closes as a daemon does, and returns once every host's thread has ended."""
        super().close()
        self._held.ended()

    def paired(self) -> Pipe:
        """A trusted session's pipe to this daemon, over a socket pair: the client's end."""
        from hmz.reach.pipes import SocketPipe

        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.admit(SocketPipe(theirs, trusted=True), fingerprint="", trusted=True)
        return SocketPipe(ours, trusted=True)
