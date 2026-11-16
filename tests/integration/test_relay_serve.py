"""A real relay on loopback: a daemon registering with a fresh key, clients joined to it.

The daemon is this test, signing with a key made for it; the clients are WebSockets this test
opens. Last, `hmz relay serve` is run as a program, waited on until it says it listens, and
terminated. A relay behind a public TLS proxy is a deployment's, and is not run here.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

import hmz.relay.rooms
from hmz.relay import TEXT, fingerprint, listening
from tests.unit.relay.doubles_relay import der, made, signed

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

PATIENCE = 10.0


@pytest.fixture
async def relay() -> AsyncGenerator[str]:
    """The URL of a relay listening on loopback."""
    async with listening("127.0.0.1", 0) as port:
        yield f"ws://127.0.0.1:{port}/any/path"


async def told(socket: ClientConnection, said: dict[str, Any]) -> None:
    await socket.send(json.dumps(said))


async def heard(socket: ClientConnection) -> Any:
    message = await socket.recv()
    return json.loads(message) if isinstance(message, str) else message


async def closed(socket: ClientConnection) -> None:
    with pytest.raises(ConnectionClosed):
        await socket.recv()


async def registered(url: str) -> tuple[ClientConnection, str]:
    """A daemon's control connection, registered under the id of a fresh key."""
    key, cert = made()
    daemon = fingerprint(cert)
    control = await connect(url)
    await told(control, {"t": "register", "id": daemon})
    challenge = await heard(control)
    await told(
        control,
        {"t": "prove", "cert": der(cert), "sig": signed(key, challenge["nonce"])},
    )
    assert await heard(control) == {"t": "registered"}
    return control, daemon


async def joined(
    url: str, control: ClientConnection, daemon: str
) -> tuple[ClientConnection, ClientConnection]:
    """A native client spliced to the daemon's accepting WebSocket: client, then daemon."""
    client = await connect(url)
    await told(client, {"t": "join", "id": daemon, "kind": "native"})
    join = await heard(control)
    assert join["kind"] == "native"
    accepted = await connect(url)
    await told(accepted, {"t": "accept", "conn": join["conn"]})
    assert await heard(client) == {"t": "joined"}
    return client, accepted


@pytest.mark.timeout(60)
async def test_two_native_clients_are_spliced_both_ways(relay: str) -> None:
    control, daemon = await registered(relay)
    one, one_daemon = await joined(relay, control, daemon)
    two, two_daemon = await joined(relay, control, daemon)
    big = os.urandom(1_000_000)
    await one.send(b"one up")
    await two.send(big)
    assert await one_daemon.recv() == b"one up"
    assert await two_daemon.recv() == big
    await one_daemon.send(b"one down")
    await two_daemon.send(b"two down")
    assert await one.recv() == b"one down"
    assert await two.recv() == b"two down"
    await one.close()
    await closed(one_daemon)
    await two_daemon.send(b"still")
    assert await two.recv() == b"still"
    await control.close()


@pytest.mark.timeout(60)
async def test_a_wrong_signature_is_refused(relay: str) -> None:
    _, cert = made()
    other, _ = made()
    async with connect(relay) as control:
        await told(control, {"t": "register", "id": fingerprint(cert)})
        nonce = (await heard(control))["nonce"]
        await told(
            control, {"t": "prove", "cert": der(cert), "sig": signed(other, nonce)}
        )
        assert await heard(control) == {
            "t": "error",
            "why": "That daemon id is not proven.",
        }
        await closed(control)


@pytest.mark.timeout(60)
async def test_joining_an_absent_daemon_is_refused(relay: str) -> None:
    async with connect(relay) as client:
        await told(client, {"t": "join", "id": "absent", "kind": "native"})
        assert await heard(client) == {"t": "error", "why": "No daemon absent is here."}
        await closed(client)


@pytest.mark.timeout(60)
async def test_signals_pass_through_for_a_webrtc_join(relay: str) -> None:
    control, daemon = await registered(relay)
    async with connect(relay) as browser:
        await told(browser, {"t": "join", "id": daemon, "kind": "webrtc"})
        assert await heard(browser) == {"t": "joined"}
        conn = (await heard(control))["conn"]
        offer = {"type": "offer", "sdp": "v=0\r\n"}
        await told(browser, {"t": "signal", "data": offer})
        assert await heard(control) == {"t": "signal", "conn": conn, "data": offer}
        candidate = {"type": "candidate", "candidate": "c", "sdpMid": "0"}
        await told(control, {"t": "signal", "conn": conn, "data": candidate})
        assert await heard(browser) == {"t": "signal", "data": candidate}
    await control.close()


@pytest.mark.timeout(60)
async def test_a_daemon_refusing_a_webrtc_join_tells_the_browser(relay: str) -> None:
    control, daemon = await registered(relay)
    async with connect(relay) as browser:
        await told(browser, {"t": "join", "id": daemon, "kind": "webrtc"})
        assert await heard(browser) == {"t": "joined"}
        conn = (await heard(control))["conn"]
        why = "This daemon cannot answer WebRTC."
        await told(control, {"t": "refuse", "conn": conn, "why": why})
        assert await heard(browser) == {"t": "error", "why": why}
        await closed(browser)
    await control.close()


@pytest.mark.timeout(60)
async def test_a_connection_that_says_nothing_in_time_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hmz.relay.rooms, "SPEAKING", 0.2)
    async with (
        listening("127.0.0.1", 0) as port,
        connect(f"ws://127.0.0.1:{port}") as silent,
    ):
        assert await heard(silent) == {"t": "error", "why": "Nothing was said in time."}
        await closed(silent)


@pytest.mark.timeout(60)
async def test_messages_over_the_limits_close_the_connection(relay: str) -> None:
    async with connect(relay) as client:
        await client.send(json.dumps({"t": "join", "pad": "x" * TEXT}))
        await closed(client)
    control, daemon = await registered(relay)
    client, _ = await joined(relay, control, daemon)
    await client.send(b"x" * (1_048_576 + 1))
    await closed(client)
    await control.close()


@pytest.mark.timeout(60)
def test_hmz_relay_serve_says_where_it_listens_and_stops_on_a_terminate() -> None:
    serving = subprocess.Popen(
        [sys.executable, "-m", "hmz", "relay", "serve", "--listen", "127.0.0.1:0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        line = serving.stdout.readline()
        assert line.startswith("hmz relay: listening on ws://127.0.0.1:")
        assert int(line.rsplit(":", 1)[1]) > 0
        serving.send_signal(signal.SIGTERM)
        assert serving.wait(PATIENCE) == 0
    finally:
        if serving.poll() is None:
            serving.kill()
            serving.wait()
