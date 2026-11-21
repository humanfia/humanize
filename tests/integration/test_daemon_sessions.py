"""The daemon as one JSON-RPC endpoint: on its socket, on listeners, over ssh and a relay.

A real daemon, started as the first client starts one, and clients of this test's own: frames
and JSON-RPC of `hmz.rpc` over a socket, mutual TLS of `hmz.trust` over a TCP listener and over
a relay's splice, and `hmz daemon connect --stdio` run through the stand-in `ssh`. A client
device is one of a home of its own, as another machine's is.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import queue
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.reach import dial
from hmz.rpc import PROTOCOL, Code, Peer, RpcError, hello
from hmz.trust import identity, pairing, tls
from tests.integration import doubles_ssh
from tests.integration.doubles_daemon import WAITS, hosting, project, until, written

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.rpc import Call

pytestmark = [
    pytest.mark.timeout(120),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = project(tmp_path, monkeypatch)
    written(at, "waits", WAITS)
    with hosting():
        yield at


def listens(*specs: str) -> None:
    """Writes the setting `listen`."""
    from hmz.coganchor import settings

    settings.changes(lambda held: held.__setitem__("listen", list(specs)))


def device(home: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    """The device of a home of its own: another machine's, as the daemon sees it."""
    was = os.environ["HUMANIZE_HOME"]
    monkeypatch.setenv("HUMANIZE_HOME", str(home))
    try:
        return identity.device()
    finally:
        monkeypatch.setenv("HUMANIZE_HOME", was)


class Client:
    """A session of this test's, and every `epic.event` it was sent."""

    def __init__(self, pipe: Any) -> None:
        self.events: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self.peer = Peer(pipe, self._heard)

    def _heard(self, call: Call) -> None:
        if call.method == "epic.event":
            self.events.put(call.params)

    def call(self, method: str, **params: Any) -> Any:
        return self.peer.call(method, params, timeout=30)

    def until(self, kind: str, **fields: Any) -> dict[str, Any]:
        while True:
            said = self.events.get(timeout=30)["message"]
            if said["type"] == kind and all(
                said.get(k) == v for k, v in fields.items()
            ):
                return said


def local() -> Client:
    """A session over the socket, hello said."""
    client = Client(dial("unix:"))
    hello(client.peer, "test", "cli", timeout=10)
    return client


def code() -> pairing.Code:
    """A pairing code of the daemon, asked for over its socket."""
    client = local()
    try:
        return pairing.read(client.call("pair.create")["code"])
    finally:
        client.peer.close()


def secured(route: str, me: identity.Identity, pin: str) -> Client:
    """A session over an untrusted route, inside mutual TLS, hello said."""
    client = Client(tls.dial(dial(route, daemon=pin), me, pin, "there"))
    hello(client.peer, "afar", "cli", timeout=10)
    return client


def test_a_session_says_hello_first_and_is_paired_on_the_socket(
    workspace: Path,
) -> None:
    daemon.start()
    pipe = dial("unix:")
    peer = Peer(pipe)
    with pytest.raises(RpcError) as first:
        peer.call("hosts.list", timeout=10)
    assert first.value.message == "A client says session.hello first."
    said = hello(peer, "test", "cli", timeout=10)
    assert said["protocol"] == PROTOCOL
    assert said["paired"] is True
    assert said["device"] == "local"
    assert said["daemon_id"] == identity.device().fingerprint
    assert peer.call("rpc.discover", timeout=10)["info"]["version"] == PROTOCOL
    with pytest.raises(RpcError) as missing:
        peer.call("runs.nothing", timeout=10)
    assert missing.value.code == Code.METHOD_NOT_FOUND
    peer.close()


def test_a_newer_client_is_refused_with_the_daemons_protocol(workspace: Path) -> None:
    daemon.start()
    peer = Peer(dial("unix:"))
    with pytest.raises(RpcError) as refused:
        hello(peer, "test", "cli", protocol="4.0.0", timeout=10)
    assert refused.value.code == Code.PROTOCOL_MISMATCH
    assert refused.value.data == {"protocol": PROTOCOL}
    peer.close()


def test_a_family_of_methods_is_served_beside_the_daemons_own(workspace: Path) -> None:
    daemon.start()
    client = local()
    listens("tcp://127.0.0.1:0")
    # `settings.get` of the settings family, as the real daemon serves it.
    assert "tcp://127.0.0.1:0" in str(client.call("settings.get"))


def test_a_host_is_still_reached_once_its_directory_is_removed(
    workspace: Path, tmp_path: Path
) -> None:
    # Section 4.5.2 of daemon.md: a host is looked up, not a directory.
    import shutil

    del workspace
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    daemon.start()
    near = local()
    near.call("hosts.open", workspace=str(scratch))
    shutil.rmtree(scratch)

    assert near.call("hosts.status", workspace=str(scratch))["state"] == "idle"
    assert near.call("btw.list", workspace=str(scratch), epic="") == {"asides": []}
    with pytest.raises(RpcError) as env:
        near.call("hosts.env.list", workspace=str(scratch))
    assert env.value.message == "no flow is running, so no env is open"
    assert near.call("hosts.stop", workspace=str(scratch)) == {}
    assert until(lambda: daemon.running(scratch) is None)
    with pytest.raises(RpcError) as nobody:
        near.call("hosts.status", workspace=str(scratch))
    assert (nobody.value.code, nobody.value.message) == (
        404,
        f"no runs are held in {where.workspace(scratch)}",
    )
    # One to start a host in must be there.
    with pytest.raises(RpcError) as missing:
        near.call("hosts.open", workspace=str(scratch))
    assert missing.value.message == f"There is no directory {scratch}."


def test_a_code_claimed_pairs_every_session_its_device_holds_open(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listens("tcp://127.0.0.1:0")
    daemon.start()
    paired = code()
    (route,) = paired.routes
    me = device(tmp_path / "afar", monkeypatch)
    held = secured(route, me, paired.id)
    with pytest.raises(RpcError) as unpaired:
        held.call("hosts.list")
    assert unpaired.value.code == Code.NOT_PAIRED

    # Paired is the device's fingerprint among the paired devices (Section 4.2.7 of
    # wire.md), so the claim of one session pairs the other one too.
    secured(route, me, paired.id).call("pair.claim", token=paired.token, name="afar")
    assert held.call("hosts.list") == {"held": []}
    (listed,) = local().call("devices.list")["devices"]
    assert listed["live"] == 2
    assert local().call("devices.revoke", name="afar") == {"dropped": 2}


def test_a_device_pairs_over_tcp_and_attaches_and_is_dropped_once_revoked(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listens("tcp://127.0.0.1:0")
    daemon.start()
    paired = code()
    (route,) = paired.routes
    # Port 0 named any free port, and the code carries the one taken.
    assert route.startswith("tcp://127.0.0.1:")
    assert int(route.rsplit(":", 1)[1]) > 0
    me = device(tmp_path / "afar", monkeypatch)

    afar = secured(route, me, paired.id)
    with pytest.raises(RpcError) as unpaired:
        afar.call("hosts.list")
    assert unpaired.value.code == Code.NOT_PAIRED
    with pytest.raises(RpcError) as wrong:
        afar.call("pair.claim", token="nope", name="afar")
    assert wrong.value.code == Code.FORBIDDEN
    assert afar.call("pair.claim", token=paired.token, name="afar") == {
        "daemon_id": paired.id,
        "device": "afar",
    }

    sub = afar.call("epic.attach", workspace=str(workspace))["sub"]
    afar.until("live")
    assert (
        afar.call(
            "epic.start",
            sub=sub,
            flow="./waits",
            task="t",
            budget={"cost": 1},
            idem="a",
        )["run"]
        == 1
    )
    afar.until("started", run=1)

    near = local()
    listed = near.call("devices.list")["devices"]
    assert [(one["name"], one["live"]) for one in listed] == [("afar", 1)]
    assert near.call("devices.revoke", name="afar") == {"dropped": 1}
    assert afar.peer.wait(10)
    again = secured(route, me, paired.id)
    with pytest.raises(RpcError) as revoked:
        again.call("hosts.list")
    assert revoked.value.code == Code.NOT_PAIRED
    near.call("hosts.stop", workspace=str(workspace))


def test_a_device_reaches_a_websocket_listener_on_an_ipv6_address(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Section 3.9.2 of daemon.md: `ws://<address>:<port>`, an IPv6 address as much as any.
    listens("ws://[::1]:0")
    daemon.start()
    near = local()
    assert until(lambda: _routes(near))
    paired = code()
    (route,) = paired.routes
    assert route.startswith("ws://[::1]:")
    assert int(route.rsplit(":", 1)[1]) > 0
    afar = secured(route, device(tmp_path / "afar", monkeypatch), paired.id)
    afar.call("pair.claim", token=paired.token, name="afar")
    assert afar.call("hosts.list") == {"held": []}


def test_listeners_open_and_close_as_the_setting_changes(workspace: Path) -> None:
    daemon.start()
    near = local()
    with pytest.raises(RpcError):
        near.call("pair.create")
    listens("tcp://127.0.0.1:0")
    assert until(lambda: _routes(near))
    listens()
    assert until(lambda: not _routes(near))


def _routes(client: Client) -> bool:
    try:
        client.call("pair.create")
    except RpcError:
        return False
    return True


def test_a_client_reaches_the_daemon_of_another_machine_over_ssh(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    host = doubles_ssh.faked(tmp_path, monkeypatch)
    client = Client(dial("stdio:ssh://there"))
    try:
        said = hello(client.peer, "test", "cli", timeout=30)
        assert said["paired"] is True
        assert said["device"] == "local"
        assert client.call("hosts.list") == {"held": []}
    finally:
        client.peer.close()
        pid = where.held(host.tmp / f"humanize-{os.getuid()}").get("pid")
        if isinstance(pid, int):
            with contextlib.suppress(OSError):
                os.kill(pid, 15)


@pytest.fixture
def relay() -> Iterator[str]:
    """A relay on loopback, on a loop of its own."""
    from hmz.relay import listening

    port: queue.SimpleQueue[int] = queue.SimpleQueue()
    stopping = threading.Event()

    async def serves() -> None:
        async with listening("127.0.0.1", 0) as taken:
            port.put(taken)
            await asyncio.to_thread(stopping.wait)

    thread = threading.Thread(target=asyncio.run, args=(serves(),), daemon=True)
    thread.start()
    yield f"ws://127.0.0.1:{port.get(timeout=10)}/"
    stopping.set()
    thread.join(10)


def test_a_device_reaches_the_daemon_through_a_relay(
    workspace: Path, relay: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listens(f"relay:{relay}")
    daemon.start()
    paired = code()
    assert paired.routes == (f"relay:{relay}",)
    me = device(tmp_path / "afar", monkeypatch)

    def joins() -> Client | None:
        try:
            return secured(paired.routes[0], me, paired.id)
        except OSError:
            return None

    assert until(lambda: joins() is not None)
    afar = secured(paired.routes[0], me, paired.id)
    afar.call("pair.claim", token=paired.token, name="afar")
    assert afar.call("hosts.list") == {"held": []}


def test_one_relay_takes_native_joins_beside_webrtc_ones(
    workspace: Path, relay: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One control connection for both listeners (Section 5.4.1 of wire.md): two would take
    # the room from each other every second, each refusing the other's kind of join.
    routes = {f"relay:{relay}", f"webrtc:{relay}"}
    listens(*sorted(routes))
    daemon.start()

    def both() -> bool:
        try:
            return set(code().routes) == routes
        except RpcError:
            return False

    assert until(both)
    paired = code()
    me = device(tmp_path / "afar", monkeypatch)

    def joins() -> bool:
        try:
            secured(f"relay:{relay}", me, paired.id).peer.close()
        except OSError:
            return False
        return True

    # A listener's route is said before its registration is made.
    assert until(joins)
    for _ in range(12):
        secured(f"relay:{relay}", me, paired.id).peer.close()
        time.sleep(0.25)
