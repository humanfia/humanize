"""A workspace's runs, held where a terminal closing cannot end them, for whatever reads them.

    from hmz.daemon import host, running

    with (running() or host()).link(name="ci") as link:
        link.start("chat", "say hello", agents={"assistant": "claude/MODEL:low"})

One daemon per machine and user, reached through one socket in the machine's temporary
directory, and holding the runs of every workspace there. Each workspace's are held by a host
of their own -- :class:`hmz.runtime.Host`, the runs and who is outside them, in a process
standing in the workspace -- the way `screen` holds a shell: a process of its own, in a session
of its own, that a terminal closing cannot reach. The daemon hands every frontend to the host of
the workspace it names (:mod:`hmz.daemon.routing`), and any number of frontends read one at
once, each a :class:`Link` of its own saying JSON: an interface, or a program written against
the SDK. Letting go of one is not stopping the run: the flow goes on taking its turns, and the
next frontend to arrive is told it from the top.

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
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where
from hmz.daemon.link import Link, linked
from hmz.daemon.proto import CONTROL, PROTOCOL, Frames, asked, spoken

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

#: How long a daemon or a host is given to come up before whoever asked for one gives up.
#: It is a fork and a bind; a second is already generous, and ten is a machine under load.
_PATIENCE = 10.0

#: How many times a host is started where the daemon it was to say what it holds to went as
#: it came up -- the daemon's last host having gone in the same breath.
_TRIES = 2

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
      at: This machine's daemon's directory, which is where the socket they are reached
        through is.
      workspace: The project it is holding runs in, as :func:`hmz.daemon.where.workspace`
        says it.
      pid: The host process holding them.
      started: When it was started, in UTC.
      protocol: Which version of the frontends' protocol the daemon speaks, or 0 for one of
        an older humanize that said none -- which no frontend of this one reaches.
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

        return reached(self.at, self.workspace, name, kind, replay=replay)

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
        """Ends the process holding this workspace's runs, whatever it was doing.

        The last thing there is to do about a host: whatever the run was in the middle of is
        what a killed process is in the middle of. The daemon, and the other workspaces' hosts,
        go on: it stops handing anybody to this one the moment it has gone.

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
        return not self.alive

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
        """Puts one question to this workspace's runs, and reads the answer.

        Args:
          said: What to ask.

        Returns:
          What it answered, and nothing at all where it would not answer.
        """
        return _asked(self.at, {**said, "workspace": self.workspace})

    def _written(self) -> dict[str, Any]:
        """What the daemon knows of this host without asking it."""
        return {
            "pid": self.pid,
            "workspace": self.workspace,
            "started": self.started,
            "kind": "host",
            "protocol": self.protocol,
        }


def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None:
    """The host holding the runs of one workspace, if one is.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.

    Returns:
      It, or None where nothing is being held there -- which is what a daemon whose process
      has gone reads as, a socket file outliving the process that bound it. Where this
      machine's daemon speaks another protocol, it is that daemon, with what it speaks.
    """
    named = where.workspace(workspace)
    try:
        said = _daemon()
    except OSError:
        said = None
    if said is not None and said.get("protocol") != PROTOCOL:
        return _other(said, named)
    found = _hosts() if said is not None else []
    return next((one for one in found if one.workspace == named), None) or _left(named)


def daemons() -> list[Daemon]:
    """Every workspace's runs being held on this machine, oldest first."""
    try:
        said = _daemon()
    except OSError:
        return []
    if said is None:
        return []
    if said.get("protocol") != PROTOCOL:
        return [_other(said, "")]
    return sorted(_hosts(), key=lambda one: one.started)


def host(
    workspace: str | os.PathLike[str] | None = None, *, seconds: float = _PATIENCE
) -> Daemon:
    """Holds a workspace's runs where a terminal closing cannot end them, for frontends.

    This machine's daemon first, started where none is, and then a host of the workspace's own
    that says what it holds to it: a process of its own -- two forks and a session of its own
    -- standing in the workspace and holding :class:`hmz.runtime.Host`. What it prints is said
    to its frontends, and it goes once nothing is running or stopping and nobody is attached,
    or once it is stopped; the daemon goes once no host is left.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.
      seconds: How long to wait for each of the two to come up.

    Returns:
      The host of this workspace's runs, reachable: the one already there, or one started now.

    Raises:
      OSError: If this machine's daemon is of an older humanize, or no host could be started.
    """
    named = where.workspace(workspace)
    failed: OSError | None = None
    for tried in range(_TRIES):
        if tried:
            time.sleep(_TICK)
        try:
            _machine(seconds)
        except OSError as why:
            if why.errno == errno.EADDRINUSE:
                raise
            # A daemon on its way out still holding its lock as this one came up.
            failed = why
            continue
        found = running(named)
        if found is not None and found.protocol != PROTOCOL:
            raise OSError(errno.EADDRINUSE, older(found))
        if found is not None:
            return found
        try:
            _forks(lambda telling: _hosts_in(named, telling), seconds)
        except OSError as why:
            # Another started one in the same breath, which is the one this answers with --
            # or the daemon went as this one came up, and is started again.
            failed = why
        found = running(named)
        if found is not None:
            return found
    raise failed or OSError(f"the runs in {named} did not come up")


def _machine(seconds: float) -> dict[str, Any]:
    """This machine's daemon, started where none is.

    Args:
      seconds: How long to wait for it to come up.

    Returns:
      What it wrote down about itself.

    Raises:
      OSError: If it is a daemon of an older humanize, or none could be started.
    """
    said = _daemon()
    failed: OSError | None = None
    if said is None:
        from hmz.daemon import routing

        try:
            _forks(routing.serves, seconds)
        except OSError as why:
            # Another started one in the same breath, which is the one this answers with.
            failed = why
        said = _daemon()
    if said is None:
        raise failed or OSError("this machine's daemon did not come up")
    if said.get("protocol") != PROTOCOL:
        raise OSError(errno.EADDRINUSE, older(_other(said, "")))
    return said


def older(daemon: Daemon) -> str:
    """What to say of a daemon of an older humanize, which no frontend of this one reaches.

    Args:
      daemon: The daemon.

    Returns:
      Why it cannot be read, and what to do about it.
    """
    held = f"in {daemon.workspace}" if daemon.workspace else "on this machine"
    return (
        f"the runs {held} are held by an older humanize (pid {daemon.pid}); "
        "stop it with that version"
    )


def _forks(serving: Callable[[int], object], seconds: float) -> None:
    """Starts a process doing `serving` apart from the terminal, and comes back once it is up.

    A fork so that whatever asked for it is not waiting on it, `setsid` so that the terminal
    which started it is no longer its own -- which is what keeps a hangup from reaching it --
    and a second fork so that it can never take a controlling terminal again.

    Args:
      serving: What the process does, handed the descriptor to say it is listening on.
      seconds: How long to wait for it to say so.

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
        # Nobody types at this process, and nobody reads its terminal -- which is still the
        # terminal of whoever asked for it until this: what it writes straight to a
        # descriptor belongs to no run yet, and goes beside the daemon's socket.
        _quiet()
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

        # Into the daemon's log itself rather than whatever the process had made of its
        # descriptors by then -- a host's pipe, which nobody reads once this exits.
        with contextlib.suppress(OSError):
            _quiet()
        logged("these runs could not be held apart from the terminal")
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(status)  # nothing of this process is anybody's to unwind


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


def _hosts_in(
    workspace: str, telling: int
) -> None:  # pragma: no cover -- runs only in the forked child
    """The runs of a workspace, hosted, in the process that holds them."""
    import signal
    import threading

    from hmz.daemon.carrying import Printed, keeps, serves
    from hmz.runtime import Hmz

    os.chdir(workspace)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    hmz = Hmz()
    # If it has been answered yes, and never otherwise: nobody is here to ask.
    hmz.reports()
    held = hmz.host()
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
    serves(held, workspace, telling)


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


def _daemon() -> dict[str, Any] | None:
    """What this machine's daemon wrote down about itself, or None where none is listening.

    Raises:
      PermissionError: If its directory is one somebody else could write.
    """
    at = where.at()
    said = where.held(at)
    if not said or not _listening(at):
        return None
    return said


def _hosts() -> list[Daemon]:
    """Every workspace's host this machine's daemon holds, as it says."""
    at = where.at()
    said = _asked(at, {"do": "list"})
    found: list[Daemon] = []
    listed: object = said.get("held")
    for one in cast("list[dict[str, Any]]", listed if isinstance(listed, list) else []):
        pid = one.get("pid")
        if not isinstance(pid, int) or not where.alive(pid):
            # Gone, and the daemon not told yet: a socket handed it would go nowhere.
            continue
        found.append(
            Daemon(
                at=at,
                workspace=str(one.get("workspace") or ""),
                pid=pid,
                started=str(one.get("started") or ""),
                protocol=PROTOCOL,
            )
        )
    return found


def _left(workspace: str) -> Daemon | None:
    """A host an older humanize left holding this workspace, as each was kept then.

    One per workspace, under humanize's home, and reached on a socket of its own: what an
    upgrade finds still running in a directory, and what a host of this humanize beside it
    would be two flows over one workspace with.
    """
    from hmz import home

    with contextlib.suppress(OSError):
        for one in (home() / "daemons").iterdir():
            said = where.held(one)
            if said.get("workspace") == workspace and _listening(one):
                protocol = said.get("protocol")
                return Daemon(
                    at=one,
                    workspace=workspace,
                    pid=int(said["pid"]),
                    started=str(said.get("started") or ""),
                    protocol=protocol if isinstance(protocol, int) else 0,
                )
    return None


def _other(said: dict[str, Any], workspace: str) -> Daemon:
    """This machine's daemon, of a humanize speaking another protocol, as a daemon to name."""
    pid, protocol = said.get("pid"), said.get("protocol")
    return Daemon(
        at=where.at(),
        workspace=workspace,
        pid=pid if isinstance(pid, int) else 0,
        started=str(said.get("started") or ""),
        protocol=protocol if isinstance(protocol, int) else 0,
    )


def _asked(at: Path, said: dict[str, Any]) -> dict[str, Any]:
    """Puts one question to this machine's daemon, or through it to a workspace's host.

    Args:
      at: The daemon's directory.
      said: What to ask, with the workspace it is about where it is about one.

    Returns:
      What it answered, and nothing at all where it would not answer.
    """
    try:
        one = where.connects(at)
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
