"""This machine's one daemon: which workspace's host each frontend is handed to.

Every workspace's runs are held by a host of their own -- a process standing in the workspace,
since whatever a run starts works where its process stands -- and every host is reached through
the one socket of this machine's daemon. A host says which workspace it holds as it comes up,
and keeps open the connection it said so on. A frontend says which workspace it is reaching for
in the first thing it says, and the daemon reads that without taking it off the socket, then
hands the socket itself down that host's connection: from there on the two talk as though the
host had accepted it, and the daemon carries none of what they say. The daemon keeps its own
end of each socket until the host says it has it, a byte back apiece: a socket nothing but a
message in flight refers to is one a kernel may take for garbage -- macOS does, and empties it.

The daemon goes once it holds no workspace, and its hosts go with it: the connection each was
handed sockets down closing is what tells a host nobody can reach its runs any more.
"""

from __future__ import annotations

import collections
import contextlib
import dataclasses
import os
import socket
import threading
import time
from typing import TYPE_CHECKING, Any

from hmz.daemon import where
from hmz.daemon.carrying import TAKEN
from hmz.daemon.proto import (
    CONTROL,
    GONE,
    MESSAGE,
    PROTOCOL,
    Frames,
    asked,
    frame,
    spoken,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["Router", "serves"]

#: How long the first thing a connection says is waited for. A frontend says it the moment it
#: connects; one that says nothing for this long is not a frontend of this protocol.
_FIRST = 10.0

#: How much of the first thing a connection says is looked at. A hello, a question and a host
#: saying what it holds are each a few hundred bytes.
_PEEK = 1 << 16

#: How often the daemon looks at whether it is still wanted.
_TICK = 0.5

#: How long a daemon nobody has handed a workspace yet waits for one: whoever started it is a
#: moment away from starting the host, and one that never does must not leave it behind.
_GRACE = 60.0

#: How long a daemon whose last host has gone waits before it goes as well: long enough for a
#: frontend that has just started a host to see it say what it holds.
_LINGER = 2.0

#: How often the daemon's own files are marked as used. A temporary directory is cleaned of
#: what nothing has touched in days, and holding a lock or a socket touches neither: a lock
#: taken away from under a running daemon is a second daemon.
_RETOUCH = 3600.0


@dataclasses.dataclass(slots=True)
class _Held:
    """One workspace's host, as the daemon reaches it.

    Attributes:
      handing: The connection it said what it holds on, which every socket for it goes down.
      said: What it said of itself: its pid, its workspace and when it started.
      lock: Held while a socket is on its way down, so that two never interleave -- and
        while the host is being told it was taken on, which goes down first.
      sent: The sockets on their way down that the host has not said it has yet, oldest
        first, each kept open here until it has. Never under `lock` where it is let go of:
        waiting on a host to take one must not be what keeps its word from being heard.
    """

    handing: socket.socket
    said: dict[str, Any]
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    sent: collections.deque[socket.socket] = dataclasses.field(
        default_factory=collections.deque[socket.socket]
    )


class Router:
    """The socket of this machine's daemon, and the host of each workspace it holds."""

    def __init__(self, listening: socket.socket, at: Path) -> None:
        """Holds the socket frontends and hosts arrive on.

        Args:
          listening: The socket, already bound and listening.
          at: The daemon's directory, which is where its socket and its note are.
        """
        self._listening = listening
        self._at = at
        self._lock = threading.Lock()
        self._held: dict[str, _Held] = {}
        self._routing = 0
        self._ever = False
        self._since = time.monotonic()
        self._going = True
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Starts taking connections, on a thread of its own."""
        self._thread = threading.Thread(
            target=self._takes, name="humanize-daemon", daemon=True
        )
        self._thread.start()

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the daemon to be over: closed, or holding nothing for long enough.

        Args:
          timeout: How long to wait, or None for as long as it takes.

        Returns:
          Whether it is over.
        """
        return self._done.wait(timeout)

    def close(self) -> None:
        """Stops being reachable, and lets go of every host -- which closes its runs."""
        self._going = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=_TICK * 4)
        with contextlib.suppress(OSError):
            self._listening.close()
        with self._lock:
            held, self._held = list(self._held.values()), {}
        for one in held:
            with contextlib.suppress(OSError):
                one.handing.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                one.handing.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (self._at / name).unlink()
        self._done.set()

    def _takes(self) -> None:
        self._listening.settimeout(_TICK)
        touched = 0.0
        try:
            while self._going and not self._idle():
                if time.monotonic() - touched > _RETOUCH:
                    touched = time.monotonic()
                    for name in (
                        where.SOCKET,
                        where.RECORD,
                        where.LOCK,
                        where.LOG,
                        ".",
                    ):
                        with contextlib.suppress(OSError):
                            os.utime(self._at / name)
                try:
                    one, _ = self._listening.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                with self._lock:
                    self._routing += 1
                threading.Thread(
                    target=self._routes, args=(one,), daemon=True, name="humanize-route"
                ).start()
        finally:
            self._done.set()

    def _idle(self) -> bool:
        """Whether nothing is left for this daemon to be reached for."""
        with self._lock:
            if self._held or self._routing:
                return False
            waited = time.monotonic() - self._since
        return waited > (_LINGER if self._ever else _GRACE)

    # -- one connection

    def _routes(self, one: socket.socket) -> None:
        """Reads what a connection says first, and does what that says to."""
        kept = False
        try:
            first = _first(one)
            if first is None:
                return
            kind, said, length = first
            if kind == CONTROL and said.get("do") == "serve":
                one.recv(length)  # the host's own, which goes no further
                kept = self._serves(one, said)
            elif kind == CONTROL and "workspace" not in said:
                one.sendall(spoken(CONTROL, self._answers(said)))
            elif kind in (MESSAGE, CONTROL):
                kept = self._hands(one, kind, said)
            else:
                # A reader speaking another protocol -- an older humanize's terminal -- told
                # so rather than left waiting.
                one.sendall(
                    frame(
                        GONE,
                        b"held for frontends by a newer humanize; `hmz` of it reads it",
                    )
                )
        except OSError:
            pass
        finally:
            if not kept:
                with contextlib.suppress(OSError):
                    one.close()
            with self._lock:
                self._routing -= 1
                self._since = time.monotonic()

    def _answers(self, said: dict[str, Any]) -> dict[str, Any]:
        """Answers a question about this machine's runs rather than one workspace's."""
        if said.get("do") != "list":
            return {"ok": False, "why": f"no such request: {said.get('do')!r}"}
        with self._lock:
            held = [dict(one.said) for one in self._held.values()]
        return {"ok": True, "held": held}

    def _hands(self, one: socket.socket, kind: bytes, said: dict[str, Any]) -> bool:
        """Hands a socket to the host of the workspace it names, or says none holds it.

        Returns:
          Whether it was handed, and so is kept here until the host says it has it.
        """
        workspace = str(said.get("workspace") or "")
        with self._lock:
            held = self._held.get(workspace)
        if held is not None:
            with held.lock:
                # Kept before it is sent, since the host may say it has it before this
                # returns; one that could not be sent is taken back off.
                held.sent.append(one)
                try:
                    socket.send_fds(held.handing, [TAKEN], [one.fileno()])
                except OSError:
                    with contextlib.suppress(ValueError):
                        held.sent.remove(one)
                    held = None
        if held is not None:
            return True
        why = f"no runs are held in {workspace or 'no workspace'}"
        if kind == MESSAGE:
            one.sendall(
                spoken(
                    MESSAGE,
                    {
                        "type": "reply",
                        "to": said.get("id", ""),
                        "ok": False,
                        "why": why,
                    },
                )
            )
        else:
            one.sendall(spoken(CONTROL, {"ok": False, "why": why}))
        return False

    def _serves(self, one: socket.socket, said: dict[str, Any]) -> bool:
        """Takes a host on as the one of its workspace, for as long as its connection lasts.

        Returns:
          Whether it was taken on -- refused where another host already holds that workspace,
          which is two flows writing over one epic.
        """
        workspace = str(said.get("workspace") or "")
        held = _Held(
            one,
            {key: said.get(key) for key in ("pid", "workspace", "started")},
        )
        # Told it was taken on before anybody can be handed to it, which is what holding its
        # lock across both does: a socket on its way down ahead of that would be read as the
        # word itself.
        with held.lock:
            with self._lock:
                there = self._held.get(workspace)
                if not workspace or (
                    there is not None and where.alive(int(there.said.get("pid") or 0))
                ):
                    return False
                self._held[workspace] = held
                self._ever = True
            try:
                one.settimeout(None)
                one.sendall(TAKEN)
            except OSError:
                with self._lock:
                    if self._held.get(workspace) is held:
                        del self._held[workspace]
                raise
        threading.Thread(
            target=self._watches,
            args=(workspace, held),
            daemon=True,
            name="humanize-host",
        ).start()
        return True

    def _watches(self, workspace: str, held: _Held) -> None:
        """Lets go of each socket the host says it has, and stops handing it any once it goes."""
        with contextlib.suppress(OSError):
            while taken := held.handing.recv(_PEEK):
                _lets_go(held, len(taken))
        with self._lock:
            if self._held.get(workspace) is held:
                del self._held[workspace]
                self._since = time.monotonic()
        _lets_go(held, len(held.sent))
        with contextlib.suppress(OSError):
            held.handing.close()


def _lets_go(held: _Held, taken: int) -> None:
    """Closes this end of as many of the sockets on their way to a host as it has taken."""
    for _ in range(taken):
        try:
            one = held.sent.popleft()
        except IndexError:
            return
        one.close()


def _first(one: socket.socket) -> tuple[bytes, dict[str, Any], int] | None:
    """The first frame a connection sends, looked at and left where it is.

    Returns:
      Its kind, what it says, and how long it is whole; or None for a connection that closed,
      said nothing in time, or said something that is not a frame of this protocol.
    """
    one.settimeout(_FIRST)
    until = time.monotonic() + _FIRST
    while time.monotonic() < until:
        seen = one.recv(_PEEK, socket.MSG_PEEK)
        if not seen:
            return None
        try:
            whole = Frames().feed(seen)
        except ValueError:
            # A length no frame has: whatever is on the other end is not speaking this.
            return None
        if whole:
            kind, payload = whole[0]
            return kind, asked(payload), 5 + len(payload)
        if len(seen) >= _PEEK:
            return None
        # Half a frame: what is there stays readable, so this is a wait rather than a select.
        time.sleep(0.01)
    return None


def serves(telling: int | None = None) -> None:
    """Holds this machine's socket for every workspace's host, until none is left to hold.

    Args:
      telling: A descriptor to say on that it is listening, and then close, or None.

    Raises:
      OSError: If a daemon of this machine is already running, or the socket cannot be bound
        -- the one failure whoever asked for a daemon has to hear about.
    """
    at = where.at()
    # Taken before anything is looked at: two started in the same second would both find
    # nothing here, and one of them would take the other's socket away as stale.
    holding = where.holds(at)
    try:
        listening = _listens(at)
        where.wrote(
            at,
            {
                "pid": os.getpid(),
                "started": where.now(),
                "kind": "daemon",
                "protocol": PROTOCOL,
            },
        )
        if telling is not None:
            # Said and left open: the descriptor is whoever forked this one's to close, and
            # one closed here could be written to again as somebody else's.
            with contextlib.suppress(OSError):
                os.write(telling, b"listening\n")
        router = Router(listening, at)
        router.start()
        try:
            router.wait()
        finally:
            router.close()
    finally:
        with contextlib.suppress(OSError):
            os.close(holding)


def _listens(at: Path) -> socket.socket:
    """Binds the socket this daemon is reached on, taking away one a daemon that is gone left.

    Called with this machine's daemon lock already held, so that taking a socket away as stale
    cannot be taking one from a daemon that is coming up beside this.

    Args:
      at: The daemon's directory.

    Returns:
      The socket, listening.

    Raises:
      OSError: If it cannot be bound.
    """
    path = at / where.SOCKET
    if path.exists():
        # A socket file outlives the process that bound it, and one nothing is listening on
        # is a reader that hangs rather than one that says nothing is running.
        with contextlib.suppress(OSError):
            path.unlink()
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(at) as reaching:
            listening.bind(reaching)
        path.chmod(0o600)
        listening.listen(64)
    except OSError:
        listening.close()
        raise
    return listening
