"""Opening the carrier a route names, from a client's side.

One function, :func:`dial`, for every kind of route a native client reaches: the socket of the
daemon of this machine or one named by its path, a child whose standard streams reach the far
daemon -- `hmz daemon connect --stdio` here, over `ssh` or under WSL -- a TCP connection, a
WebSocket, a port EasyTier forwards, and a join through a relay. A `webrtc:` route is a
browser's way in, opened by `hmz.rtc` where it is opened at all, and refused here.

What comes back is a :class:`~hmz.reach.pipes.Pipe` and nothing more: whether its far end is
the daemon a client pinned is for the TLS over it, or the `session.hello` over it, to say.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hmz.reach.pipes import MESSAGE, ProcessPipe, SocketPipe, WebSocketPipe
from hmz.reach.routes import Route

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from websockets.sync.client import ClientConnection

    from hmz.reach.pipes import Pipe

__all__ = ["OPENING", "EasyTier", "command", "dial", "websocket"]

#: How long a carrier may take to open before it is given up on (Section 3.4.9).
OPENING = 30.0

#: What a child reaching the far daemon runs there: `hmz daemon connect --stdio`, as a login
#: shell finds `hmz`, with where `uv tool` puts it in front, which a login shell may not have.
_CONNECT = 'export PATH="$HOME/.local/bin:$PATH"; exec hmz daemon connect --stdio'

#: What every `ssh` a route opens is told before anything the route says, since ssh keeps the
#: first value it is given: batch mode, so that it asks for no password and accepts no host key
#: it does not know (Section 3.4.3), and as long to connect as any carrier has to open.
_BATCH = (("BatchMode", "yes"), ("ConnectTimeout", str(int(OPENING))))

#: What no destination handed to `ssh` may hold: a space, a second line or a NUL.
_UNSAYABLE = frozenset(" \t\n\r\0")

#: How often a port not answering yet is tried again.
_AGAIN = 0.1


@dataclass(frozen=True, slots=True)
class EasyTier:
    """An EasyTier entry: what an `easytier:<name>` route joins (Section 3.4.10 of [FILES]).

    Attributes:
      secret: What the network is derived from, which never leaves this machine.
      nodes: The shared nodes it meets the daemon's side through.
    """

    secret: str
    nodes: tuple[str, ...]


def command(route: Route) -> list[str]:
    """The argv this machine runs for a `stdio:` route, whose standard streams are its carrier.

    Args:
      route: A `stdio:local`, `stdio:ssh` or `stdio:wsl` route.

    Returns:
      `sh` for `stdio:local`; `ssh` in batch mode, with the user, port, identity file, proxy
      jump and options the route names; `wsl.exe`, in the distribution it names. Each runs
      `hmz daemon connect --stdio` through a login shell there.

    Raises:
      ValueError: For a route of another kind.
    """
    shell = ["sh", "-lc", _CONNECT]
    if route.kind == "local":
        return shell
    if route.kind == "wsl":
        distro = ["-d", route.name] if route.name else []
        return ["wsl.exe", *distro, "--exec", *shell]
    if route.kind == "ssh":
        from hmz.coganchor.transport import Road, Target

        login = f"{route.user}@{route.host}" if route.user else route.host
        if login.startswith("-") or _UNSAYABLE & set(login) or not route.host:
            # A destination ssh would read as an option, or as more than one line.
            raise ValueError(f"{route} cannot be reached from here.")
        target = Target(
            "ssh", host=login, port=route.port or 0, options=(*_BATCH, *route.options)
        )
        return Road.to(target).line(shell)
    raise ValueError(f"{route} is not run as a command.")


def dial(
    route: Route | str,
    *,
    daemon: str = "",
    easytier: Mapping[str, EasyTier] | None = None,
    start: Callable[[], object] | None = None,
    timeout: float = OPENING,
) -> Pipe:
    """Opens the carrier a route names.

    Args:
      route: It.
      daemon: The daemon id a `relay:` route joins.
      easytier: This machine's EasyTier entries, by name, which an `easytier:` route names one
        of.
      start: What starts the daemon of this machine where `unix:` finds none running.
      timeout: How long it may take to open.

    Returns:
      The carrier, trusted or not as its kind is.

    Raises:
      ValueError: `<route> is not a route.`, `<route> cannot be reached from here.`, or what
        else keeps a route from being dialed: an EasyTier entry that is not there, a relay
        route with no daemon id to join.
      OSError: If the carrier could not be opened, saying why.
    """
    if isinstance(route, str):
        route = Route.parse(route)
    if route.kind == "unix":
        return _unix(route, start, timeout)
    if route.kind in ("local", "ssh") or (
        route.kind == "wsl" and sys.platform == "win32"
    ):
        child = subprocess.Popen(
            command(route),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        return ProcessPipe(child, trusted=True)
    if route.kind == "tcp":
        return SocketPipe(_tcp(route.host, route.port or 0, timeout), trusted=False)
    if route.kind == "ws":
        return WebSocketPipe(websocket(route.url, timeout))
    if route.kind == "easytier":
        return _easytier(route, easytier or {}, timeout)
    if route.kind == "relay":
        from hmz.reach.relays import join

        if not daemon:
            raise ValueError(f"{route} needs the id of the daemon it joins.")
        return join(route.url, daemon, timeout)
    raise ValueError(f"{route} cannot be reached from here.")


def _unix(route: Route, start: Callable[[], object] | None, timeout: float) -> Pipe:
    """The socket a `unix:` route names, the daemon of this machine started where it must be."""
    if route.path:
        one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            one.settimeout(timeout)
            one.connect(route.path)
            one.settimeout(None)
        except OSError:
            one.close()
            raise
        return SocketPipe(one, trusted=True)
    from hmz.daemon import where

    at = where.at()
    ending = time.monotonic() + timeout
    started = False
    while True:
        try:
            one = where.connects(at, timeout)
        except OSError:
            if start is None or time.monotonic() > ending:
                raise
            if not started:
                start()
                started = True
            time.sleep(_AGAIN)
            continue
        one.settimeout(None)
        return SocketPipe(one, trusted=True)


def _tcp(host: str, port: int, timeout: float) -> socket.socket:
    try:
        one = socket.create_connection((host, port), timeout=timeout)
    except OverflowError as why:
        # A port past 65535, which the grammar lets a route name.
        raise OSError(f"{host} has no port {port}") from why
    one.settimeout(None)
    # Nagle off: a session is a small call and a small answer, over and over.
    one.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return one


def websocket(url: str, timeout: float = OPENING) -> ClientConnection:
    """A WebSocket opened on a URL, whose messages are at most what the relay lets through.

    Raises:
      OSError: If it could not be opened, a handshake refused among it.
    """
    from websockets.exceptions import InvalidHandshake, InvalidURI
    from websockets.sync.client import connect

    try:
        opening = connect(url, open_timeout=timeout, max_size=MESSAGE, compression=None)
        # Entered as the context manager `connect` is, and never left: a carrier lives as
        # long as its session rather than for a block, and is ended by its own `close`.
        return contextlib.ExitStack().enter_context(opening)
    except (InvalidHandshake, InvalidURI) as why:
        raise ConnectionError(f"{url}: {why}") from why


def _easytier(
    route: Route, entries: Mapping[str, EasyTier], timeout: float
) -> SocketPipe:
    """A TCP connection to the daemon's port, through EasyTier forwarding it to this loopback."""
    from hmz.coganchor import easytier

    entry = entries.get(route.name)
    if entry is None:
        raise ValueError(f"There is no EasyTier entry {route.name}.")
    with socket.socket() as free:
        free.bind(("127.0.0.1", 0))
        local: int = free.getsockname()[1]
    joined = easytier.joining(
        entry.secret, local, port=easytier.PORT, peers=entry.nodes
    )

    def stops() -> None:
        if joined.poll() is None:
            joined.terminate()
            try:
                joined.wait(5)
            except subprocess.TimeoutExpired:
                joined.kill()
                joined.wait()

    ending = time.monotonic() + timeout
    while True:
        try:
            one = _tcp("127.0.0.1", local, max(ending - time.monotonic(), _AGAIN))
        except OSError as why:
            if joined.poll() is not None:
                raise ConnectionError(
                    f"EasyTier stopped, exiting {joined.returncode}."
                ) from why
            if time.monotonic() > ending:
                stops()
                raise
            time.sleep(_AGAIN)
            continue
        return SocketPipe(one, trusted=False, ending=stops)
