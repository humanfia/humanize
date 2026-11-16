"""A process started apart from the terminal: this machine's daemon, and each host it starts.

A fork so that whatever asked for it is not waiting on it, `setsid` so that the terminal which
started it is no longer its own -- which is what keeps a hangup from reaching it -- and a second
fork so that it can never take a controlling terminal again. The process says down a pipe that
it is listening, or why it could not be, and whoever started it waits for that.
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable, Collection

__all__ = ["BACKING", "forks", "hosts_in"]

#: How long a host process that is done is given to finish backing its epics up before it
#: goes: within what a stop waits for it, so that a stop is never taken for one that failed.
BACKING = 15.0


def forks(
    serving: Callable[[int], object], seconds: float, keep: Collection[int] = ()
) -> None:
    """Starts a process doing `serving` apart from the terminal, and comes back once it is up.

    Args:
      serving: What the process does, handed the descriptor to say it is listening on.
      seconds: How long to wait for it to say so.
      keep: The descriptors besides the standard three and that one the process keeps;
        every other one it inherited is closed, so that a host started by the daemon holds
        none of the daemon's sockets open.

    Raises:
      OSError: If it could not be started, or did not come up in the time it was given.
    """
    reading, telling = os.pipe()
    # Before the fork: what this process has written and not yet flushed is buffered in it,
    # and a fork copies the buffer -- so anything left in one would be written twice.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    proxied = _proxied()
    middle = os.fork()
    if middle == 0:  # pragma: no cover -- the child never comes back to be covered
        os.close(reading)
        proxied()
        _closes_but({telling, *keep})
        _detaches(serving, telling)
    os.close(telling)
    try:
        _waits(reading, seconds)
    finally:
        with contextlib.suppress(OSError):
            os.close(reading)
        # The middle process has already gone: it forked the one that holds the run and
        # exited, so that the run's own parent is whatever adopts it rather than this.
        with contextlib.suppress(ChildProcessError):
            os.waitpid(middle, 0)


def _closes_but(keep: Collection[int]) -> None:  # pragma: no cover -- in the child
    """Closes every descriptor past the standard three but those kept."""
    try:
        highest = os.sysconf("SC_OPEN_MAX")
    except (OSError, ValueError):
        highest = 1024
    low = 3
    for one in sorted(keep):
        os.closerange(low, one)
        low = one + 1
    os.closerange(low, highest)


def _proxied() -> Callable[[], None]:
    """This machine's proxies as asked here, told to a child forked after this.

    macOS answers through CoreFoundation, which crashes a child forked from a process that has
    used it -- and anything sending a request asks, a report among them, first thing in a host.
    So it is asked before the fork, and the child is handed the answer instead of asking.

    Returns:
      What the child calls to take the answer, which elsewhere does nothing.
    """
    if sys.platform != "darwin":
        return lambda: None
    import urllib.request

    # What `getproxies` and `proxy_bypass` ask on macOS, by these names, which no public
    # function of urllib's lets a caller answer instead.
    asked = cast("Any", urllib.request)
    proxies = asked._get_proxies()  # noqa: SLF001
    settings = asked._get_proxy_settings()  # noqa: SLF001

    def told() -> None:  # pragma: no cover -- runs only in the forked child
        asked._get_proxies = lambda: proxies  # noqa: SLF001
        asked._get_proxy_settings = lambda: settings  # noqa: SLF001

    return told


def _detaches(
    serving: Callable[[int], object], telling: int
) -> None:  # pragma: no cover -- runs only in the forked child
    """The two forks and the session, and then the serving, in the process that does it."""
    status = 0
    try:
        with contextlib.suppress(OSError):
            os.setsid()
        if os.fork() != 0:
            os._exit(0)  # the middle process, which must unwind nothing at all
        # Nobody types at this process, and nobody reads its terminal: what it writes straight
        # to a descriptor belongs to no run yet, and goes beside the daemon's socket.
        _quiet()
        # A hangup cannot reach a process with no controlling terminal, and this one has
        # none; refusing it as well costs nothing and says what is meant.
        import signal

        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            # A terminate is this process's own to take, whatever the one that forked it made
            # of one -- ignored, or its own way out: unwound, so that what it holds is let go.
            signal.signal(signal.SIGTERM, _terminated)
        serving(telling)
    except _Terminated:
        pass
    except BaseException as why:  # noqa: BLE001 -- the last frame of a process nobody reads
        status = 1
        # Said back down the pipe as well as written down: whoever asked is still waiting,
        # and `could not be held` on its own is a line nobody can act on.
        with contextlib.suppress(OSError):
            os.write(telling, f"the run could not be held: {why}\n".encode())
            os.close(telling)
        from hmz.daemon.carrying import logged

        with contextlib.suppress(OSError):
            _quiet()
        logged("these runs could not be held apart from the terminal")
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(status)  # nothing of this process is anybody's to unwind


class _Terminated(BaseException):
    """A detached process told to end, on its way out."""


def _terminated(
    _signal: int, _frame: object
) -> None:  # pragma: no cover -- in the child
    """Ends a detached process by unwinding it."""
    raise _Terminated


def _quiet() -> None:  # pragma: no cover -- runs only in the forked child
    """Takes this process off the terminal it was started from, onto the daemon's log."""
    nothing = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nothing, 0)
    os.close(nothing)
    try:
        written = os.open(
            where.at() / where.LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
    except OSError:
        # A directory refused as somebody else's says so down the pipe, where it is read.
        written = os.open(os.devnull, os.O_WRONLY)
    for fd in (1, 2):
        os.dup2(written, fd)
    os.close(written)


def hosts_in(
    workspace: str, telling: int, link: int, slot: str = ""
) -> None:  # pragma: no cover -- runs only in the forked child
    """The runs of a workspace, or of one slot of it, hosted in the process that holds them.

    Args:
      workspace: The workspace.
      telling: The descriptor to say it is listening on.
      link: This end of the socket pair the daemon reaches it through.
      slot: Which of the workspace's hosts.
    """
    import signal
    import socket
    import threading

    from hmz.daemon.carrying import Printed, keeps, serves
    from hmz.runtime import Hmz

    os.chdir(workspace)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    hmz = Hmz()
    # If it has been answered yes, and never otherwise: nobody is here to ask.
    hmz.reports()
    held = hmz.host(slot)
    # What a CLI a run starts writes straight to a descriptor goes into that run's epic, and
    # what is printed in Python is said to every frontend. Only now, with something reading
    # the pipe: a failure before this goes into the daemon's log as it is.
    reading, writing = os.pipe()
    threading.Thread(
        target=keeps, args=(reading, held), daemon=True, name="humanize-kept"
    ).start()
    for fd in (1, 2):
        os.dup2(writing, fd)
    os.close(writing)
    sys.stdout = sys.stderr = Printed(held)

    def closes(_signal: int, _frame: object) -> None:
        # Off the signal's frame: closing waits on threads the frame may be holding up.
        threading.Thread(target=held.close, daemon=True).start()

    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGTERM, closes)
    serves(held, workspace, socket.socket(fileno=link), telling, slot=slot)
    # A backup of the last epic still going is let finish, for so long: nothing waits on it.
    hmz.backups.wait(BACKING)


def _waits(reading: int, seconds: float) -> None:
    """Waits for the detached process to say it is listening, or for the time to run out."""
    import selectors

    selector = selectors.DefaultSelector()
    selector.register(reading, selectors.EVENT_READ)
    try:
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not selector.select(0.1):
                continue
            said = os.read(reading, 1 << 12)
            if not said or said.startswith(b"listening"):
                return
            raise OSError(said.decode(errors="replace").strip())
    finally:
        selector.close()
