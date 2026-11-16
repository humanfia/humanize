"""The relay's rooms, served connection by connection over stand-in WebSockets.

Each connection is a pair of queues: what the test says to the relay, and what the relay says
back. A connection the relay closes says so with `None` on the second.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest
from websockets.exceptions import ConnectionClosedOK

import hmz.relay.rooms
from hmz.relay import TEXT, Relay, fingerprint
from tests.unit.relay.doubles_relay import der, made, signed

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

PATIENCE = 2.0


class Socket:
    """One stand-in WebSocket, as the relay sees it."""

    def __init__(self) -> None:
        self.inbox: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self.outbox: asyncio.Queue[str | bytes | None] = asyncio.Queue()
        self.closed = False

    async def recv(self) -> str | bytes:
        if self.closed:
            raise ConnectionClosedOK(None, None)
        message = await self.inbox.get()
        if message is None:
            await self.close()
            raise ConnectionClosedOK(None, None)
        return message

    async def send(self, message: str | bytes) -> None:
        if self.closed:
            raise ConnectionClosedOK(None, None)
        await self.outbox.put(message)

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.inbox.put_nowait(None)
            self.outbox.put_nowait(None)

    def say(self, message: dict[str, Any] | str | bytes | None) -> None:
        """Sends the relay one message, a dict as JSON text; None closes the connection."""
        self.inbox.put_nowait(
            json.dumps(message) if isinstance(message, dict) else message
        )

    async def heard(self) -> Any:
        """The next message from the relay: JSON text read, binary as it is, None once closed."""
        message = await asyncio.wait_for(self.outbox.get(), PATIENCE)
        return json.loads(message) if isinstance(message, str) else message


class World:
    """One relay, and every connection served to it."""

    def __init__(self) -> None:
        self.relay = Relay()
        self.served: list[asyncio.Task[None]] = []

    def connect(self) -> Socket:
        socket = Socket()
        self.served.append(asyncio.ensure_future(self.relay(socket)))
        return socket

    async def register(self) -> tuple[Socket, str]:
        """A daemon registered under a fresh id, and the id."""
        key, cert = made()
        daemon = fingerprint(cert)
        control = self.connect()
        control.say({"t": "register", "id": daemon})
        challenge = await control.heard()
        assert challenge["t"] == "challenge"
        sig = signed(key, challenge["nonce"])
        control.say({"t": "prove", "cert": der(cert), "sig": sig})
        assert await control.heard() == {"t": "registered"}
        return control, daemon


@pytest.fixture
async def world() -> AsyncIterator[World]:
    made = World()
    yield made
    for task in made.served:
        task.cancel()
    await asyncio.gather(*made.served, return_exceptions=True)


async def refused(socket: Socket, why: str) -> None:
    assert await socket.heard() == {"t": "error", "why": why}
    assert await socket.heard() is None


async def test_a_daemon_that_signs_the_nonce_is_registered(world: World) -> None:
    _, daemon = await world.register()
    assert len(daemon) == 52


async def test_a_wrong_signature_is_not_proven(world: World) -> None:
    _, cert = made()
    other, _ = made()
    control = world.connect()
    control.say({"t": "register", "id": fingerprint(cert)})
    nonce = (await control.heard())["nonce"]
    control.say({"t": "prove", "cert": der(cert), "sig": signed(other, nonce)})
    await refused(control, "That daemon id is not proven.")


async def test_the_nonce_is_32_random_bytes_afresh(world: World) -> None:
    nonces: set[str] = set()
    for _ in range(2):
        control = world.connect()
        control.say({"t": "register", "id": "x"})
        nonces.add((await control.heard())["nonce"])
    assert len(nonces) == 2
    assert all(len(nonce) == 43 for nonce in nonces)


async def test_joining_an_absent_daemon_is_refused(world: World) -> None:
    client = world.connect()
    client.say({"t": "join", "id": "nobody", "kind": "native"})
    await refused(client, "No daemon nobody is here.")


async def test_what_cannot_be_read_or_is_not_expected_is_refused(world: World) -> None:
    for said, why in (
        ("{", "That message cannot be read."),
        ('{"t": 1}', "That message cannot be read."),
        (b"\x00", "A binary message is not expected here."),
        ({"t": "signal"}, "A signal is not expected here."),
    ):
        socket = world.connect()
        socket.say(said)
        await refused(socket, why)


async def test_a_text_message_over_the_limit_is_closed(world: World) -> None:
    socket = world.connect()
    socket.say(json.dumps({"t": "join", "pad": "x" * TEXT}))
    assert await socket.heard() is None


async def test_a_native_join_is_spliced_both_ways(world: World) -> None:
    control, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "native"})
    join = await control.heard()
    assert join["t"] == "join"
    assert join["kind"] == "native"
    assert len(join["conn"]) >= 22
    accepted = world.connect()
    accepted.say({"t": "accept", "conn": join["conn"]})
    assert await client.heard() == {"t": "joined"}
    client.say(b"hello")
    assert await accepted.heard() == b"hello"
    accepted.say(b"back")
    assert await client.heard() == b"back"
    client.say(None)
    assert await accepted.heard() is None


async def test_a_text_message_in_a_splice_ends_it(world: World) -> None:
    control, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "native"})
    accepted = world.connect()
    accepted.say({"t": "accept", "conn": (await control.heard())["conn"]})
    assert await client.heard() == {"t": "joined"}
    client.say("text")
    await refused(client, "A splice carries binary messages alone.")
    assert await accepted.heard() is None


async def test_a_refused_native_join_says_why(world: World) -> None:
    control, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "native"})
    conn = (await control.heard())["conn"]
    control.say({"t": "refuse", "conn": conn, "why": "Not now."})
    await refused(client, "Not now.")


async def test_a_native_join_unanswered_is_refused(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hmz.relay.rooms, "ANSWERING", 0.05)
    _, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "native"})
    await refused(client, "The daemon did not answer.")


async def test_an_accept_nobody_waits_for_is_refused(world: World) -> None:
    accepted = world.connect()
    accepted.say({"t": "accept", "conn": "nothing"})
    await refused(accepted, "No join nothing is waiting.")


async def test_anything_from_a_native_client_before_joined_closes_it(
    world: World,
) -> None:
    control, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "native"})
    await control.heard()
    client.say(b"early")
    await refused(client, "A native join sends nothing before it is joined.")


async def test_signals_pass_both_ways_for_a_webrtc_join(world: World) -> None:
    control, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "webrtc"})
    assert await client.heard() == {"t": "joined"}
    conn = (await control.heard())["conn"]
    offer = {"type": "offer", "sdp": "v=0"}
    client.say({"t": "signal", "data": offer})
    assert await control.heard() == {"t": "signal", "conn": conn, "data": offer}
    answer = {"type": "answer", "sdp": "v=0", "cert": "c", "sig": "s"}
    control.say({"t": "signal", "conn": conn, "data": answer})
    assert await client.heard() == {"t": "signal", "data": answer}


async def test_a_webrtc_client_sending_binary_is_closed(world: World) -> None:
    _, daemon = await world.register()
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "webrtc"})
    assert await client.heard() == {"t": "joined"}
    client.say(b"\x00")
    await refused(client, "A binary message is not expected here.")


async def test_a_room_goes_with_its_control_connection(world: World) -> None:
    control, daemon = await world.register()
    waiting = world.connect()
    waiting.say({"t": "join", "id": daemon, "kind": "native"})
    signalled = world.connect()
    signalled.say({"t": "join", "id": daemon, "kind": "webrtc"})
    assert await signalled.heard() == {"t": "joined"}
    await control.heard()
    await control.heard()
    control.say(None)
    assert await waiting.heard() is None
    assert await signalled.heard() is None
    late = world.connect()
    late.say({"t": "join", "id": daemon, "kind": "native"})
    await refused(late, f"No daemon {daemon} is here.")


async def test_registering_again_takes_the_room(world: World) -> None:
    key, cert = made()
    daemon = fingerprint(cert)
    controls: list[Socket] = []
    for _ in range(2):
        control = world.connect()
        control.say({"t": "register", "id": daemon})
        nonce = (await control.heard())["nonce"]
        control.say({"t": "prove", "cert": der(cert), "sig": signed(key, nonce)})
        assert await control.heard() == {"t": "registered"}
        controls.append(control)
    assert await controls[0].heard() is None
    client = world.connect()
    client.say({"t": "join", "id": daemon, "kind": "webrtc"})
    assert await client.heard() == {"t": "joined"}
    assert (await controls[1].heard())["t"] == "join"
