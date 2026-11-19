"""A workspace's runs, held where a terminal closing cannot end them, for whatever reads them.

    from hmz.daemon import attach, where

    with attach("sdk", "ci", slot=where.chat()) as link:
        link.chat("claude/MODEL:low", "say hello")

One daemon per machine and user, reached through one socket in the machine's temporary
directory, and on whatever it listens on beside it, and holding the runs of every workspace
there (`protocol/daemon.md`). Each workspace's are held by hosts of their own --
:class:`hmz.runtime.Host`, the runs and who is outside them, in a process standing in the
workspace -- the way `screen` holds a shell: a process of its own, in a session of its own,
that a terminal closing cannot reach. A workspace has its own host, which runs its flows one at
a time, and a host per chat and per `hmz exec` beside it, each named by its slot (see
:func:`hmz.daemon.where.slot`); a chat, which is no flow, is started and said to by `chat.*`
(:meth:`Link.chat`). Every client speaks JSON-RPC to the daemon over a session of
`protocol/wire.md` (:mod:`hmz.daemon.routing`), and the daemon speaks for it to the host; any
number of frontends read one host at once, each a :class:`Link` of its own. Letting go of one is
not stopping the run: the flow goes on taking its turns, and the next frontend to arrive is told
it from the top.

What the runs *are* is the runtime's, and it is reached from here: :class:`Hmz`, :class:`Host`
and the :class:`Refused` a link raises are handed through from :mod:`hmz.runtime` under this
name, and :func:`linked` makes the same :class:`Link` over runs held in the process that
asked, so that a frontend is written once whichever way it reaches them.
"""

from __future__ import annotations

import contextlib
import errno
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from hmz.daemon import where
from hmz.daemon.link import Link, linked

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime import Hmz, Host, Refused

__all__ = [
    "Daemon",
    "Hmz",
    "Host",
    "Link",
    "Older",
    "Refused",
    "attach",
    "daemons",
    "host",
    "linked",
    "running",
    "start",
]

#: How long a daemon or a host is given to come up before whoever asked for one gives up.
_PATIENCE = 10.0

#: How many times the daemon is started where the one found went as it was reached.
_TRIES = 2

#: How long a question about a host is given to be answered.
_ANSWERING = 5.0

#: How long a run told to stop is given to go before whoever asked is told it has not.
_UNWINDING = 20.0

#: How often a process being waited on is looked at.
_TICK = 0.1

#: How many times a frontend reaches for the host of its workspace before it gives up, and
#: how long it waits between: a host found on its way out is found gone the next time.
_ATTACHES = 3
_AGAIN = 0.5

#: How long the socket of a daemon that may not be listening is given to answer at all.
_ANSWERS_AT_ONCE = 1.0


def __getattr__(name: str) -> object:
    """Hands through the runtime this holds runs in, out of the layer it is written in.

    Fetched when it is named rather than imported at the top: a line that only asks which runs
    are being held must not pay for the flows, the drivers and the traces.

    Args:
      name: What was asked for.

    Returns:
      The same object :mod:`hmz.runtime` holds.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    if name not in ("Hmz", "Host", "Refused"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import hmz.runtime

    return getattr(hmz.runtime, name)


@dataclass(frozen=True, slots=True)
class Daemon:
    """One host of a workspace's runs, held where a terminal closing cannot end them.

    Attributes:
      at: This machine's daemon's directory, which is where the socket they are reached
        through is.
      workspace: The project it is holding runs in, as :func:`hmz.daemon.where.workspace`
        says it.
      pid: The host process holding them.
      started: When it was started, in UTC.
      protocol: The protocol version the daemon speaks, or "" for one of an older Humanize
        that wrote none.
      slot: Which of the workspace's hosts it is: "" for its own, `chat:<hex>` for a chat's.
    """

    at: Path
    workspace: str
    pid: int
    started: str
    protocol: str = ""
    slot: str = ""

    @property
    def alive(self) -> bool:
        """Whether the process holding it is still there."""
        return where.alive(self.pid)

    def link(self, name: str = "", kind: str = "sdk", *, replay: bool = True) -> Link:
        """Attaches a frontend to the runs this host holds.

        Args:
          name: What the frontend is called, or "" for whoever is at this end and `kind`.
          kind: What it is: `tui`, `cli` or `sdk`.
          replay: Whether to be told the run so far, or only what happens from here.

        Returns:
          The link, attached; a context manager, closed to let go.

        Raises:
          OSError: If nothing answers there, or what does refused it.
        """
        from hmz.daemon.link import reached

        return reached(
            self.at, self.workspace, name, kind, replay=replay, slot=self.slot
        )

    def status(self) -> dict[str, Any]:
        """What the host says about itself: how many are reading, and what is running.

        Returns:
          The daemon's answer to `hosts.status`; where there is none, what is known of the
          host without asking it, as one reading nothing and running nothing.
        """
        said = self.asked({"do": "status"})
        if said:
            return said
        return {**self._written(), "attached": 0, "flows": [], "calls": []}

    def detach(self) -> int:
        """Lets go of every frontend reading these runs, leaving the runs running.

        Returns:
          How many were let go of.
        """
        held = self.asked({"do": "detach"}).get("let_go")
        return held if isinstance(held, int) else 0

    def stop(self, *, seconds: float = _UNWINDING) -> bool:
        """Closes the runs and lets every frontend go, and waits for the host to go.

        Args:
          seconds: How long to wait for it to go.

        Returns:
          Whether it has gone.
        """
        if _asks(self.at, "hosts.stop", self._named) is None:
            return not self.alive
        return self._gone(seconds)

    def kill(self, *, seconds: float = _UNWINDING) -> bool:
        """Ends the process holding this workspace's runs, whatever it was doing.

        The daemon, and the other workspaces' hosts, go on.

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
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not self.alive:
                return True
            time.sleep(_TICK)
        return not self.alive

    def asked(self, said: dict[str, Any]) -> dict[str, Any]:
        """Asks the daemon one thing about this host: `hosts.<do>`, `said["do"]` naming it.

        Args:
          said: What to ask.

        Returns:
          What it answered, and nothing at all where it would not answer.
        """
        params = {key: value for key, value in said.items() if key != "do"}
        answer = _asks(self.at, f"hosts.{said.get('do')}", {**params, **self._named})
        return answer if isinstance(answer, dict) else {}  # pyright: ignore[reportUnknownVariableType]

    @property
    def _named(self) -> dict[str, str]:
        """Which host this is, as a call names it."""
        return {
            "workspace": self.workspace,
            **({"slot": self.slot} if self.slot else {}),
        }

    def _written(self) -> dict[str, Any]:
        """What is known of this host without asking it."""
        return {
            "pid": self.pid,
            "workspace": self.workspace,
            **({"slot": self.slot} if self.slot else {}),
            "started": self.started,
            "kind": "host",
            "protocol": self.protocol,
        }


def _asks(at: Path, method: str, params: dict[str, Any]) -> Any:
    """Makes one call of this machine's daemon over a session of its own.

    Returns:
      Its result, or None where nothing answered it in time or it was refused.
    """
    from hmz.daemon.link import dialed
    from hmz.rpc import Closed, RpcError

    try:
        peer, _ = dialed(at, seconds=_ANSWERING)
    except OSError:
        return None
    try:
        return peer.call(method, params, timeout=_ANSWERING)
    except (RpcError, Closed, TimeoutError):
        return None
    finally:
        peer.close()


def _speaks(said: dict[str, Any]) -> bool:
    """Whether a daemon record names a protocol of this one's major version."""
    from hmz.rpc import PROTOCOL

    protocol = said.get("protocol")
    return (
        isinstance(protocol, str) and protocol.split(".")[0] == PROTOCOL.split(".")[0]
    )


def running(
    workspace: str | os.PathLike[str] | None = None, *, slot: str = ""
) -> Daemon | None:
    """The host holding the runs of one workspace, if one is.

    Args:
      workspace: The project directory, or None for wherever Humanize is being run.
      slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's.

    Returns:
      It, or None where nothing is being held there. Where this machine's daemon speaks
      another protocol, it is that daemon, with what it speaks.
    """
    named = where.workspace(workspace)
    try:
        said = _daemon()
    except OSError:
        said = None
    if said is not None and not _speaks(said):
        return _other(said, named)
    found = _hosts() if said is not None else []
    return next(
        (one for one in found if one.workspace == named and one.slot == slot), None
    )


def daemons() -> list[Daemon]:
    """Every host of every workspace held on this machine, oldest first."""
    try:
        said = _daemon()
    except OSError:
        return []
    if said is None:
        return []
    if not _speaks(said):
        return [_other(said, "")]
    return sorted(_hosts(), key=lambda one: one.started)


def host(
    workspace: str | os.PathLike[str] | None = None,
    *,
    seconds: float = _PATIENCE,
    slot: str = "",
) -> Daemon:
    """Holds a workspace's runs where a terminal closing cannot end them, for frontends.

    This machine's daemon first, started where none is, and then the host of that workspace
    and slot, which the daemon starts where none is (`hosts.open`).

    Args:
      workspace: The project directory, or None for wherever Humanize is being run.
      seconds: How long to wait for each of the two to come up.
      slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's.

    Returns:
      The host of this workspace's runs, reachable.

    Raises:
      OSError: If this machine's daemon is of an older Humanize, or no host could be started.
    """
    from hmz.daemon.link import dialed
    from hmz.rpc import Closed, RpcError

    named = where.workspace(workspace)
    failed: OSError | None = None
    for tried in range(_TRIES):
        if tried:
            time.sleep(_TICK)
        try:
            at = where.at()
            _machine(seconds)
            peer, _ = dialed(at, seconds=seconds)
        except OSError as why:
            if why.errno == errno.EADDRINUSE:
                raise
            # A daemon on its way out still holding its lock as this one came up.
            failed = why
            continue
        try:
            said: Any = peer.call(
                "hosts.open", {"workspace": named, "slot": slot}, timeout=seconds * 2
            )
        except RpcError as why:
            raise OSError(why.message) from why
        except (Closed, TimeoutError) as why:
            failed = OSError(f"the runs in {named} did not come up: {why}")
            continue
        finally:
            peer.close()
        return Daemon(
            at=at,
            workspace=str(said.get("workspace") or named),
            pid=int(said.get("pid") or 0),
            started=str(said.get("started") or ""),
            protocol=str(said.get("protocol") or ""),
            slot=str(said.get("slot") or ""),
        )
    raise failed or OSError(f"the runs in {named} did not come up")


def _machine(seconds: float) -> dict[str, Any]:
    """This machine's daemon, started where none is.

    Args:
      seconds: How long to wait for it to come up.

    Returns:
      What it wrote down about itself.

    Raises:
      OSError: If it is a daemon of an older Humanize, or none could be started.
    """
    said = _daemon()
    failed: OSError | None = None
    if said is None:
        from hmz.daemon.detaching import spawns

        try:
            spawns(["daemon"], seconds)
        except OSError as why:
            # Another started one in the same breath, which is the one this answers with.
            failed = why
        said = _daemon()
    if said is None:
        raise failed or OSError("this machine's daemon did not come up")
    if not _speaks(said):
        raise OSError(errno.EADDRINUSE, older(_other(said, "")))
    return said


def start(seconds: float = _PATIENCE) -> None:
    """Starts this machine's daemon where none runs, as the first client that needs it does.

    Args:
      seconds: How long to wait for it to come up.

    Raises:
      OSError: If it is a daemon of an older Humanize -- `EADDRINUSE`, saying so -- or none
        could be started.
    """
    _machine(seconds)


class Older(RuntimeError):  # noqa: N818 -- what holds the runs, not what went wrong
    """The runs asked for are held by an older Humanize, which no frontend of this one reads.

    A second daemon started beside it would fight it over the socket, so a frontend says so
    and opens nothing rather than holding the runs itself.
    """


def attach(
    kind: str,
    name: str = "",
    *,
    workspace: str | os.PathLike[str] | None = None,
    slot: str = "",
) -> Link:
    """Links a frontend to the runs held for a workspace, starting a host where none is.

    Args:
      kind: What the frontend is, as the runs list their frontends: `tui`, `sdk`.
      name: What to call it there, or "" for the runs to name it.
      workspace: The project directory, or None for wherever Humanize is being run.
      slot: Which of its hosts: "" for its own, `chat:<hex>` for a chat's -- a new one is a
        new chat's, started here.

    Returns:
      The link, attached.

    Raises:
      Older: If this workspace's runs are held by an older Humanize.
      OSError: If no host could be reached or started, after a few tries.
    """
    from hmz.daemon.link import reached

    named = where.workspace(workspace)
    failed = OSError(f"the runs in {named} could not be reached")
    slot = where.slot(slot)
    for _ in range(_ATTACHES):
        try:
            start()
            return reached(where.at(), named, name, kind, slot=slot)
        except OSError as why:
            if why.errno == errno.EADDRINUSE:
                raise Older(why.strerror or str(why)) from why
            failed = why
            time.sleep(_AGAIN)
    raise failed


def older(daemon: Daemon) -> str:
    """What to say of a daemon of an older Humanize, which no frontend of this one reaches.

    Args:
      daemon: The daemon.

    Returns:
      Why it cannot be read, and what to do about it.
    """
    held = f"in {daemon.workspace}" if daemon.workspace else "on this machine"
    return (
        f"the runs {held} are held by an older Humanize (pid {daemon.pid}); "
        "stop it with that version"
    )


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
    """Every host of every workspace this machine's daemon holds, as it says."""
    at = where.at()
    said = _asks(at, "hosts.list", {})
    listed: object = (
        cast("dict[str, Any]", said).get("held") if isinstance(said, dict) else None
    )
    found: list[Daemon] = []
    for one in cast("list[dict[str, Any]]", listed if isinstance(listed, list) else []):
        pid = one.get("pid")
        if not isinstance(pid, int) or not where.alive(pid):
            continue
        from hmz.rpc import PROTOCOL

        found.append(
            Daemon(
                at=at,
                workspace=str(one.get("workspace") or ""),
                pid=pid,
                started=str(one.get("started") or ""),
                protocol=PROTOCOL,
                slot=str(one.get("slot") or ""),
            )
        )
    return found


def _other(said: dict[str, Any], workspace: str) -> Daemon:
    """This machine's daemon, of a Humanize speaking another protocol, as a daemon to name."""
    pid, protocol = said.get("pid"), said.get("protocol")
    return Daemon(
        at=where.at(),
        workspace=workspace,
        pid=pid if isinstance(pid, int) else 0,
        started=str(said.get("started") or ""),
        protocol=protocol if isinstance(protocol, str) else "",
    )


def _listening(at: Path) -> bool:
    """Whether something is actually listening on the socket there."""
    try:
        where.connects(at, _ANSWERS_AT_ONCE).close()
    except OSError:
        return False
    return True
