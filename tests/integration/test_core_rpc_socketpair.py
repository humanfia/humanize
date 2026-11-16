"""Two `hmz.rpc` peers over a real socket pair: frames and JSON-RPC as the kernel carries them."""

import contextlib
import socket
import struct
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from hmz.rpc import (
    LONGEST,
    PROTOCOL,
    Call,
    Closed,
    Code,
    Dispatcher,
    Peer,
    RpcError,
    admit,
    hello,
)


class Sock:
    """A connected stream socket as a pipe."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    def read(self, size: int) -> bytes:
        return self.sock.recv(size)

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


#: What the client end serves: a method the daemon end calls back on, outside the protocol's
#: own document, since the protocol has the daemon call nothing.
CLIENT_DOCUMENT: dict[str, Any] = {
    "openrpc": "1.3.2",
    "info": {"title": "client", "version": PROTOCOL},
    "methods": [
        {
            "name": "client.ping",
            "params": [{"name": "n", "required": True, "schema": {"type": "integer"}}],
            "result": {"name": "pong", "schema": {"type": "integer"}},
        }
    ],
    "x-notifications": [{"name": "epic.event", "params": []}],
}


class Ends:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.event = threading.Event()
        self.cancelled = threading.Event()
        self.big = False
        self.sockets = socket.socketpair()
        daemon_side = Dispatcher()
        daemon_side.register("session.hello", self.hello)
        daemon_side.register("files.close", self.files_close)
        daemon_side.register("paths.list", self.paths_list)
        client_side = Dispatcher(CLIENT_DOCUMENT)
        client_side.register("client.ping", lambda call: call.params["n"] + 1)
        client_side.register("epic.event", self.told)
        self.daemon = Peer(Sock(self.sockets[0]), daemon_side, name="daemon")
        self.client = Peer(Sock(self.sockets[1]), client_side, name="client")

    def hello(self, call: Call) -> dict[str, Any]:
        admit(call.params["protocol"])
        return {"daemon_id": "d", "protocol": PROTOCOL, "paired": True}

    def files_close(self, call: Call) -> dict[str, Any]:
        if call.cancelled.wait(10):
            self.cancelled.set()
            raise RpcError(Code.CANCELLED, "The call was cancelled.")
        return {}

    def paths_list(self, call: Call) -> dict[str, Any]:
        if self.big:
            return {"entries": "x" * LONGEST}
        pong = call.peer.call("client.ping", {"n": 41}, timeout=5)
        call.peer.notify("epic.event", {"sub": "s", "message": {"type": "x"}})
        return {"pong": pong, "at": call.params.get("at")}

    def told(self, call: Call) -> None:
        self.events.append(call.params)
        self.event.set()


@pytest.fixture
def ends() -> Iterator[Ends]:
    made = Ends()
    yield made
    made.client.close()
    made.daemon.close()


@pytest.fixture
def greeted(ends: Ends) -> Ends:
    assert hello(ends.client, "here", "cli", timeout=5)["protocol"] == PROTOCOL
    return ends


def test_hello_then_calls_both_ways_and_a_notification(greeted: Ends) -> None:
    answer = greeted.client.call("paths.list", {"at": "/tmp/日本"}, timeout=5)
    assert answer == {"pong": 42, "at": "/tmp/日本"}
    assert greeted.event.wait(5)
    assert greeted.events == [{"sub": "s", "message": {"type": "x"}}]
    discovered = greeted.client.call("rpc.discover", timeout=5)
    assert discovered["info"]["version"] == PROTOCOL


def test_nothing_is_served_before_hello(ends: Ends) -> None:
    with pytest.raises(RpcError) as refused:
        ends.client.call("rpc.discover", timeout=5)
    assert refused.value.code == Code.INVALID_REQUEST


def test_a_client_of_another_major_is_refused(ends: Ends) -> None:
    with pytest.raises(RpcError) as refused:
        hello(ends.client, "here", "cli", protocol="4.0.0", timeout=5)
    assert refused.value.code == 426
    assert refused.value.data == {"protocol": PROTOCOL}


def test_a_timeout_cancels_the_call_at_the_far_end(greeted: Ends) -> None:
    with pytest.raises(TimeoutError):
        greeted.client.call("files.close", {"handle": "h"}, timeout=0.2)
    assert greeted.cancelled.wait(5)
    assert greeted.client.call("paths.list", timeout=5)["pong"] == 42


def test_closing_fails_the_call_still_waiting(greeted: Ends) -> None:
    pending = greeted.client.request("files.close", {"handle": "h"})
    threading.Timer(0.2, greeted.daemon.close).start()
    with pytest.raises(Closed):
        pending.result(5)
    assert greeted.client.wait(5)
    assert greeted.cancelled.wait(5)


def test_an_oversize_frame_closes_the_session(greeted: Ends) -> None:
    pending = greeted.client.request("files.close", {"handle": "h"})
    greeted.sockets[1].sendall(struct.pack(">I", LONGEST + 1))
    assert greeted.daemon.wait(5)
    with pytest.raises(Closed):
        pending.result(5)


def test_an_answer_too_large_is_413_and_the_session_goes_on(greeted: Ends) -> None:
    greeted.big = True
    with pytest.raises(RpcError) as refused:
        greeted.client.call("paths.list", timeout=30)
    assert refused.value.code == 413
    assert greeted.client.call("rpc.discover", timeout=5)["openrpc"] == "1.3.2"
