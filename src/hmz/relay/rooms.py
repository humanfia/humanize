"""The relay: rooms of daemons, and the clients joined to them.

A daemon that cannot be dialled -- behind a NAT, on a laptop that moves -- can still dial out,
and so can whoever wants to reach it. The relay is where both dial. A daemon keeps one control
connection open to it, under its daemon id, once it has signed a nonce with the key that id
was made of; that connection and what the relay keeps for it are the daemon's room. A client
names the id it wants and is joined to whichever daemon holds that room.

A native client is joined by a splice: the daemon opens a second WebSocket for that one join,
and from then on every binary message of either is sent on the other, as it came. What crosses
is mutual TLS from one end to the other, which the relay has no key to, so it carries bytes it
cannot read and does not look at. A browser is joined by signals instead: the offer, the
answer and the candidates of a WebRTC connection pass through the relay's hands to the
daemon's control connection and back, and the data channel they set up goes wherever ICE finds
a way, signed end to end by the daemon's device key.

Nothing is written down and nothing outlives a connection: a room goes with its control
connection, a join that was not spliced goes with its room, and a splice goes when either end
does.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NoReturn, Protocol, cast

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from .proof import proven

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine

__all__ = [
    "ANSWERING",
    "BINARY",
    "PINGING",
    "SILENT",
    "TEXT",
    "Peer",
    "Relay",
    "listening",
]

#: How long the daemon has to accept or refuse a native join.
ANSWERING = 10.0

#: The longest text message, in bytes, the relay reads before it closes the connection.
TEXT = 65_536

#: The longest binary message, in bytes, the relay carries.
BINARY = 1_048_576

#: How often every connection is pinged.
PINGING = 30.0

#: How long a connection may stay silent before it is closed.
SILENT = 90.0

#: How many random bytes a nonce and a conn are made of.
_NONCE = 32
_CONN = 16

#: What a join may ask for.
_KINDS = ("native", "webrtc")


class Peer(Protocol):
    """One WebSocket connection to the relay, as much of it as the relay uses."""

    async def recv(self) -> str | bytes:
        """The next message, text or binary."""
        ...

    async def send(self, message: str | bytes) -> None:
        """Sends one message, text or binary."""
        ...

    async def close(self) -> None:
        """Closes the connection, if it is not closed already."""
        ...


@dataclass(eq=False)
class _Room:
    """A registered daemon: its control connection, and the joins it has been sent."""

    control: Peer
    joins: dict[str, _Join]


@dataclass(eq=False)
class _Join:
    """One client's join of a room, until it is spliced, refused or gone."""

    kind: str
    client: Peer
    #: The daemon's own WebSocket for a native join it accepted, or why it refused.
    answer: asyncio.Future[Peer | str]
    #: Set once the client has been told it is joined to a native splice.
    spliced: bool = False
    #: Set once the client's end is over, which is when an accepting WebSocket is let go.
    over: asyncio.Event = field(default_factory=asyncio.Event)


class _RefusedError(Exception):
    """A connection answered with `error` and closed, or closed outright."""


class Relay:
    """The rooms one relay keeps, and what serves each connection to it.

    Every connection is served by calling the relay with it; what the first message says
    makes it a daemon's control connection, a client's join, or a daemon's accepting end of
    one.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, _Room] = {}
        self._joins: dict[str, _Join] = {}
        self._closing: set[asyncio.Task[None]] = set()

    def _aside(self, closing: Coroutine[Any, Any, None]) -> None:
        """Runs a close beside whatever is being served, holding it until it is done."""
        task = asyncio.ensure_future(closing)
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)

    async def __call__(self, peer: Peer) -> None:
        """Serves one connection until it, or the relay's side of it, closes.

        Args:
          peer: The connection.
        """
        with contextlib.suppress(ConnectionClosed, _RefusedError):
            said = await _read(peer)
            match said.get("t"):
                case "register":
                    await self._register(peer, said)
                case "join":
                    await self._join(peer, said)
                case "accept":
                    await self._accept(peer, said)
                case kind:
                    await _refuse(peer, f"{_kind(kind)} is not expected here.")

    async def _register(self, peer: Peer, said: dict[str, Any]) -> None:
        """A daemon's control connection: proven, then held as its room until it closes."""
        daemon = _text(said, "id")
        nonce = secrets.token_urlsafe(_NONCE)
        await _send(peer, {"t": "challenge", "nonce": nonce})
        proof = await _read(peer)
        if proof.get("t") != "prove":
            await _refuse(peer, f"{_kind(proof.get('t'))} is not expected here.")
        cert, sig = _text(proof, "cert"), _text(proof, "sig")
        if not proven(daemon, nonce, cert, sig):
            await _refuse(peer, "That daemon id is not proven.")
        room = _Room(peer, {})
        earlier = self._rooms.get(daemon)
        self._rooms[daemon] = room
        try:
            await _send(peer, {"t": "registered"})
            if earlier is not None:
                # Closed beside this room rather than before it: an earlier connection gone
                # half-dead would hold the new one's messages up for its close handshake.
                self._aside(earlier.control.close())
            await self._control(room)
        finally:
            if self._rooms.get(daemon) is room:
                del self._rooms[daemon]
            await asyncio.gather(
                *(
                    join.client.close()
                    for join in room.joins.values()
                    if not join.spliced
                )
            )

    async def _control(self, room: _Room) -> None:
        """What a registered daemon says on its control connection, until it closes."""
        while True:
            said = await _read(room.control)
            match said.get("t"):
                case "signal":
                    conn, data = _text(said, "conn"), await _data(room.control, said)
                    join = room.joins.get(conn)
                    if join is not None and join.kind == "webrtc":
                        with contextlib.suppress(ConnectionClosed):
                            await _send(join.client, {"t": "signal", "data": data})
                case "refuse":
                    conn, why = _text(said, "conn"), _text(said, "why")
                    join = room.joins.get(conn)
                    if join is not None and not join.answer.done():
                        join.answer.set_result(why)
                case kind:
                    await _refuse(room.control, f"{_kind(kind)} is not expected here.")

    async def _join(self, peer: Peer, said: dict[str, Any]) -> None:
        """A client's join: told the daemon, then spliced or signalled through."""
        daemon, kind = _text(said, "id"), _text(said, "kind")
        if kind not in _KINDS:
            await _refuse(peer, f"A join of kind {kind} cannot be made.")
        room = self._rooms.get(daemon)
        if room is None:
            await _refuse(peer, f"No daemon {daemon} is here.")
        conn = secrets.token_urlsafe(_CONN)
        join = _Join(kind, peer, asyncio.get_running_loop().create_future())
        room.joins[conn] = self._joins[conn] = join
        try:
            await _send(room.control, {"t": "join", "conn": conn, "kind": kind})
            if kind == "native":
                await _native(join)
            else:
                await _signalled(room, conn, join)
        finally:
            del room.joins[conn], self._joins[conn]
            join.over.set()
            if not join.answer.done():
                join.answer.cancel()

    async def _accept(self, peer: Peer, said: dict[str, Any]) -> None:
        """A daemon's own WebSocket for one native join, held until the splice is over."""
        conn = _text(said, "conn")
        join = self._joins.get(conn)
        if join is None or join.kind != "native" or join.answer.done():
            await _refuse(peer, f"No join {conn} is waiting.")
        join.answer.set_result(peer)
        await join.over.wait()


async def _native(join: _Join) -> None:
    """A native join, from the daemon's answer to the end of its splice."""
    heard = asyncio.ensure_future(join.client.recv())
    try:
        await asyncio.wait(
            {join.answer, heard}, timeout=ANSWERING, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        heard.cancel()
    if heard.done() and not heard.cancelled():
        # Anything before `joined` ends the join, and a close ends it at once.
        if heard.exception() is not None:
            return
        await _refuse(join.client, "A native join sends nothing before it is joined.")
    if not join.answer.done():
        await _refuse(join.client, "The daemon did not answer.")
    answer = join.answer.result()
    if isinstance(answer, str):
        await _refuse(join.client, answer)
    await _send(join.client, {"t": "joined"})
    join.spliced = True
    await _splice(join.client, answer)


async def _signalled(room: _Room, conn: str, join: _Join) -> None:
    """A WebRTC join: joined at once, then each signal passed to the daemon."""
    await _send(join.client, {"t": "joined"})
    while True:
        said = await _read(join.client)
        if said.get("t") != "signal":
            await _refuse(join.client, f"{_kind(said.get('t'))} is not expected here.")
        data = await _data(join.client, said)
        await _send(room.control, {"t": "signal", "conn": conn, "data": data})


async def _splice(one: Peer, other: Peer) -> None:
    """Carries every binary message of each to the other, until either closes."""
    pumps = [
        asyncio.ensure_future(_pump(one, other)),
        asyncio.ensure_future(_pump(other, one)),
    ]
    try:
        await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for pump in pumps:
            pump.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)
        await one.close()
        await other.close()


async def _pump(source: Peer, sink: Peer) -> None:
    """Carries one direction of a splice, unread, until either end closes."""
    with contextlib.suppress(ConnectionClosed, _RefusedError):
        while True:
            message = await source.recv()
            if isinstance(message, str):
                await _refuse(source, "A splice carries binary messages alone.")
            await sink.send(message)


async def _read(peer: Peer) -> dict[str, Any]:
    """The next control message on a connection.

    Raises:
      _RefusedError: Once the connection has been closed for a message too long, a binary one, or
        one that is not a JSON object naming its kind.
    """
    message = await peer.recv()
    if isinstance(message, bytes):
        await _refuse(peer, "A binary message is not expected here.")
    if len(message.encode()) > TEXT:
        await peer.close()
        raise _RefusedError
    try:
        said: object = json.loads(message)
    except ValueError:
        said = None
    if not isinstance(said, dict) or not isinstance(
        cast("dict[str, Any]", said).get("t"), str
    ):
        await _refuse(peer, "That message cannot be read.")
    return cast("dict[str, Any]", said)


def _text(said: dict[str, Any], key: str) -> str:
    """A text field of a control message, or the empty text where it is not one."""
    value = said.get(key)
    return value if isinstance(value, str) else ""


async def _data(peer: Peer, said: dict[str, Any]) -> dict[str, Any]:
    """The `data` of a signal, which is passed on as it came.

    Raises:
      _RefusedError: Once the connection has been closed for `data` that is not an object.
    """
    data = said.get("data")
    if not isinstance(data, dict):
        await _refuse(peer, "That message cannot be read.")
    return cast("dict[str, Any]", data)


def _kind(kind: object) -> str:
    """A control message's kind, as a sentence names it."""
    return f"A {kind}" if isinstance(kind, str) else "That message"


async def _send(peer: Peer, said: dict[str, Any]) -> None:
    """Sends one control message."""
    await peer.send(json.dumps(said, separators=(",", ":")))


async def _refuse(peer: Peer, why: str) -> NoReturn:
    """Answers `error` with why, closes the connection, and gives up on serving it.

    Raises:
      _RefusedError: Always.
    """
    with contextlib.suppress(ConnectionClosed):
        await _send(peer, {"t": "error", "why": why})
    await peer.close()
    raise _RefusedError


@contextlib.asynccontextmanager
async def listening(host: str, port: int) -> AsyncGenerator[int]:
    """A relay serving plain WebSockets at an address, until the block is left.

    Args:
      host: The address to listen on.
      port: The port, or 0 for any free one.

    Yields:
      The port it listens on.

    Raises:
      OSError: Where it cannot listen there.
    """
    relay = Relay()
    async with serve(
        relay,
        host,
        port,
        max_size=BINARY,
        ping_interval=PINGING,
        ping_timeout=SILENT - PINGING,
    ) as server:
        yield next(iter(server.sockets)).getsockname()[1]
