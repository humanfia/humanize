"""A workspace's runs, held where a terminal closing cannot end them, for whatever reads them.

    from hmz.daemon import host, running

    with (running() or host()).link(name="ci") as link:
        link.start("chat", "say hello", agents={"assistant": "claude/MODEL:low"})

One daemon per workspace. It holds :class:`hmz.runtime.Host` -- the runs of a workspace and who
is outside them -- the way `screen` holds a shell: a process of its own, in a session of its
own, that a terminal closing cannot reach. Any number of frontends read it at once, each a
:class:`Link` of its own saying JSON over the socket beside it: an interface, or a program
written against the SDK. Letting go of one is not stopping the run: the flow goes on
taking its turns, and the next frontend to arrive is told it from the top.

What the runs *are* is the runtime's, and it is reached from here: :class:`Hmz` and
:class:`Host` are handed through from :mod:`hmz.runtime` under this name, and :func:`linked`
makes the same :class:`Link` over runs held in the process that asked, so that a frontend is
written once whichever way it reaches them.
"""

from __future__ import annotations

import contextlib
import errno
import os
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hmz.daemon import where
from hmz.daemon.link import Link, linked
from hmz.daemon.proto import CONTROL, Frames, asked, spoken

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.runtime import Hmz, Host

__all__ = [
    "Daemon",
    "Hmz",
    "Host",
    "Link",
    "daemons",
    "host",
    "linked",
    "running",
]

#: How long a daemon is given to bind its socket before whoever asked for one gives up. It is
#: a fork and a bind; a second is already generous, and ten is a machine under load.
_PATIENCE = 10.0

#: How long a question about a run is given to be answered.
_ANSWERING = 5.0

#: How long a run told to stop is given to go before whoever asked is told it has not.
_UNWINDING = 20.0

#: How often a process being waited on is looked at.
_TICK = 0.1

#: How long the socket of a daemon that may not be listening is given to answer at all. It
#: is a connect to a file on this machine: either it is refused at once or it is taken, and a
#: wedged one must not be what a listing of every run on the machine waits on.
_ANSWERS_AT_ONCE = 1.0


def __getattr__(name: str) -> object:
    """Hands through the runtime this holds runs in, out of the layer it is written in.

    Fetched when it is named rather than imported at the top, for the reason every layer here
    is: what holds runs apart from a terminal is a process and a socket, and a line that only
    asks which runs are being held must not pay for the flows, the drivers and the traces.

    Args:
      name: What was asked for.

    Returns:
      The same object :mod:`hmz.runtime` holds, so that there is one of each however it was
      reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    if name not in ("Hmz", "Host"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import hmz.runtime

    return getattr(hmz.runtime, name)


@dataclass(frozen=True, slots=True)
class Daemon:
    """One workspace's runs, held where a terminal closing cannot end them.

    Attributes:
      at: The daemon's own directory, which is where its socket is.
      workspace: The project it is holding runs in.
      pid: The process holding them.
      started: When it was started, in UTC.
      protocol: Which version of the frontends' protocol it speaks, or 0 for a daemon of an
        older humanize, which held one run for a terminal and which no frontend reaches.
    """

    at: Path
    workspace: str
    pid: int
    started: str
    protocol: int = 0

    @property
    def alive(self) -> bool:
        """Whether the process holding it is still there."""
        return where.alive(self.pid)

    def link(self, name: str = "", kind: str = "sdk", *, replay: bool = True) -> Link:
        """Attaches a frontend to the runs this daemon hosts.

        Args:
          name: What the frontend is called, or "" for whoever is at this end and `kind`.
          kind: What it is: `tui`, `cli` or `sdk`.
          replay: Whether to be told the run so far, or only what happens from here.

        Returns:
          The link, attached; a context manager, closed to let go.

        Raises:
          OSError: If nothing answers there, or what does is a daemon of an older humanize.
        """
        from hmz.daemon.link import reached

        return reached(self.at, name, kind, replay=replay)

    def status(self) -> dict[str, Any]:
        """What the run says about itself: how many are reading, and what is running.

        Returns:
          What it said, and what is written down beside its socket for a run that would not
          answer -- which is a daemon that is starting up, or one that is wedged. The same
          keys either way: a run that could not be asked answers as one reading nothing and
          running nothing, so that whoever asked reads an answer rather than guessing which
          of the two they got.
        """
        said = self.asked({"do": "status"})
        if said.get("ok"):
            return said
        return {**self._written(), "attached": 0, "flows": [], "calls": []}

    def detach(self) -> int:
        """Lets go of every frontend reading these runs, leaving the runs running.

        Returns:
          How many were let go of.
        """
        said = self.asked({"do": "detach"})
        held = said.get("let go")
        return held if isinstance(held, int) else 0

    def stop(self, *, seconds: float = _UNWINDING) -> bool:
        """Closes the runs and lets every frontend go, and waits for the daemon to go.

        Args:
          seconds: How long to wait for it to go.

        Returns:
          Whether it has gone.
        """
        if not self.asked({"do": "stop"}).get("ok"):
            return not self.alive
        return self._gone(seconds)

    def kill(self, *, seconds: float = _UNWINDING) -> bool:
        """Ends the process holding this run, whatever it was doing.

        The last thing there is to do about a daemon: whatever the run was in the middle of
        is what a killed process is in the middle of.

        Args:
          seconds: How long to wait for it to go before saying it has not.

        Returns:
          Whether it has gone.
        """
        import signal

        with contextlib.suppress(OSError):
            os.kill(self.pid, signal.SIGTERM)
        if not self._gone(seconds):
            with contextlib.suppress(OSError):
                os.kill(self.pid, signal.SIGKILL)
            self._gone(_UNWINDING)
        gone = not self.alive
        if gone:
            for name in (where.SOCKET, where.RECORD):
                with contextlib.suppress(OSError):
                    (self.at / name).unlink()
        return gone

    def _gone(self, seconds: float) -> bool:
        """Waits for the process holding this run to go.

        Args:
          seconds: How long to wait.

        Returns:
          Whether it has gone.
        """
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not self.alive:
                return True
            time.sleep(_TICK)
        return not self.alive

    def asked(self, said: dict[str, Any]) -> dict[str, Any]:
        """Puts one question to the run, and reads the answer.

        Args:
          said: What to ask.

        Returns:
          What it answered, and nothing at all where it would not answer.
        """
        try:
            one = where.connects(self.at)
        except OSError:
            return {}
        try:
            one.settimeout(_ANSWERING)
            one.sendall(spoken(CONTROL, said))
            frames = Frames()
            while True:
                read = one.recv(1 << 16)
                if not read:
                    return {}
                for kind, payload in frames.feed(read):
                    if kind == CONTROL:
                        return asked(payload)
        except (OSError, ValueError):
            return {}
        finally:
            with contextlib.suppress(OSError):
                one.close()

    def _written(self) -> dict[str, Any]:
        """What is written down beside its socket about it."""
        return dict(where.held(self.at))


def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None:
    """The daemon holding a run in one workspace, if one is.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.

    Returns:
      It, or None where nothing is being held there. A directory left behind by a daemon
      whose process has gone reads as nothing being held: a socket file outlives the process
      that bound it.
    """
    return _read(where.at(workspace))


def daemons() -> list[Daemon]:
    """Every run being held on this machine, oldest first."""
    found: list[Daemon] = []
    with contextlib.suppress(OSError):
        for one in sorted(where.under().iterdir()):
            if not one.is_dir():
                continue
            held = _read(one)
            if held is not None:
                found.append(held)
    return sorted(found, key=lambda one: one.started)


def host(
    workspace: str | os.PathLike[str] | None = None, *, seconds: float = _PATIENCE
) -> Daemon:
    """Holds a workspace's runs where a terminal closing cannot end them, for frontends.

    A process of its own -- two forks and a session of its own, one per workspace -- holding
    :class:`hmz.runtime.Host`. What it prints is said to its frontends, and it goes once
    nothing is running or stopping and nobody is attached, or once it is stopped.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.
      seconds: How long to wait for it to bind its socket.

    Returns:
      The daemon hosting this workspace's runs, listening: the one already there, or one
      started now.

    Raises:
      OSError: If a daemon of an older humanize holds this workspace, or no host could be
        started.
    """
    at = where.at(workspace)
    found = _read(at)
    if found is None:
        try:
            return _forks(lambda telling: _hosts(workspace, at, telling), at, seconds)
        except OSError:
            # Another started one in the same breath, which is the one this answers with.
            found = _read(at)
            if found is None:
                raise
    if not found.protocol:
        raise OSError(errno.EADDRINUSE, older(found))
    return found


def older(daemon: Daemon) -> str:
    """What to say of a daemon of an older humanize, which no frontend of this one reaches.

    Args:
      daemon: The daemon.

    Returns:
      Why it cannot be read, and what to do about it.
    """
    return (
        f"the runs in {daemon.workspace} are held by an older humanize (pid {daemon.pid}); "
        "stop it with that version"
    )


def _forks(serving: Callable[[int], object], at: Path, seconds: float) -> Daemon:
    """Starts a daemon doing `serving`, and comes back once it is listening.

    A fork so that whatever asked for it is not waiting on it, `setsid` so that the terminal
    which started it is no longer its own -- which is what keeps a hangup from reaching it --
    and a second fork so that it can never take a controlling terminal again.

    Args:
      serving: What the daemon does, handed the descriptor to say it is listening on.
      at: The daemon's own directory.
      seconds: How long to wait for it to bind its socket.

    Returns:
      The daemon, listening.

    Raises:
      OSError: If it could not be started, or did not come up in the time it was given.
    """
    reading, telling = os.pipe()
    # Before the fork: what this process has written and not yet flushed is buffered in it,
    # and a fork copies the buffer -- so anything left in one would be written twice, once
    # by each of them.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    middle = os.fork()
    if middle == 0:  # pragma: no cover -- the child never comes back to be covered
        os.close(reading)
        _detaches(serving, at, telling)
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
    held = _read(at)
    if held is None:
        raise OSError(f"the run in {at} did not come up")
    return held


def _detaches(
    serving: Callable[[int], object], at: Path, telling: int
) -> None:  # pragma: no cover -- runs only in the forked child
    """The two forks and the session, and then the run, in the process that holds it."""
    status = 0
    try:
        with contextlib.suppress(OSError):
            os.setsid()
        if os.fork() != 0:
            os._exit(0)  # the middle process, which must unwind nothing at all
        # A hangup cannot reach a process with no controlling terminal, and this one has
        # none; refusing it as well costs nothing and says what is meant.
        import signal

        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        serving(telling)
    except BaseException as why:  # noqa: BLE001 -- the last frame of a process nobody reads
        status = 1
        # Said back down the pipe as well as written down: whoever asked for a daemon is
        # still waiting, and `could not be held` on its own is a line nobody can act on.
        with contextlib.suppress(OSError):
            os.write(telling, f"the run could not be held: {why}\n".encode())
            os.close(telling)
        from hmz.daemon.carrying import logged

        with contextlib.suppress(OSError):
            at.mkdir(parents=True, exist_ok=True)
            logged(at, "these runs could not be held apart from the terminal")
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(status)  # nothing of this process is anybody's to unwind


def _hosts(
    workspace: str | os.PathLike[str] | None, at: Path, telling: int
) -> None:  # pragma: no cover -- runs only in the forked child
    """The runs of a workspace, hosted, in the process that holds them."""
    import signal
    import threading

    from hmz.daemon.carrying import Printed, serves
    from hmz.runtime import Hmz

    if workspace is not None:
        os.chdir(workspace)
    at.mkdir(parents=True, exist_ok=True)
    # Nobody types at this process, and nobody reads its terminal: what a CLI it starts
    # writes straight to a descriptor goes down beside the socket, and what is printed in
    # Python is said to every frontend.
    nothing = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nothing, 0)
    written = os.open(at / where.LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    for fd in (1, 2):
        os.dup2(written, fd)
    for fd in (nothing, written):
        os.close(fd)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    hmz = Hmz()
    # If it has been answered yes, and never otherwise: nobody is here to ask.
    hmz.reports()
    held = hmz.host()
    sys.stdout = sys.stderr = Printed(held)

    def closes(_signal: int, _frame: object) -> None:
        # Off the signal's frame: closing waits on threads the frame may be holding up.
        threading.Thread(target=held.close, daemon=True).start()

    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGTERM, closes)
    serves(held, at, telling)


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


def _read(at: Path) -> Daemon | None:
    """The daemon whose directory this is, or None where nothing is being held there."""
    said = where.held(at)
    if not said:
        return None
    pid = said.get("pid")
    if not isinstance(pid, int):
        return None
    if not _listening(at):
        return None
    protocol = said.get("protocol")
    return Daemon(
        at=at,
        workspace=str(said.get("workspace") or ""),
        pid=pid,
        started=str(said.get("started") or ""),
        protocol=protocol if isinstance(protocol, int) else 0,
    )


def _listening(at: Path) -> bool:
    """Whether something is actually listening on the socket there.

    A process of that number may be there and be something else entirely -- numbers come
    round -- so the note beside the socket is not the whole of the answer.
    """
    try:
        where.connects(at, _ANSWERS_AT_ONCE).close()
    except OSError:
        return False
    return True
