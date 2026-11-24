"""Mutual TLS over real carriers: a socket pair, and two spliced by a relay that reads nothing.

A daemon of its own home answers each carrier with `hmz.trust.tls.answer`, admits a session as
paired or unpaired by its device fingerprint, lets an unpaired one claim a code and nothing
else, and drops a session whose device is revoked -- the parts of Section 4 of
`protocol/wire.md` a daemon builds out of `hmz.trust`, in a few lines here rather than the
daemon's, which carries JSON-RPC over the same session.
"""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import threading
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import pytest

from hmz.trust import identity, pairing, tls
from hmz.trust.devices import Device, Devices
from tests.conftest import homed, places

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

Carrier = tuple[socket.socket, socket.socket]


def made(home: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    """The device of a home of its own."""
    del monkeypatch
    with homed(home):
        return identity.device()


def said(session: tls.Secured, message: dict[str, Any]) -> None:
    payload = json.dumps(message).encode()
    session.sendall(struct.pack(">I", len(payload)) + payload)


def heard(session: tls.Secured) -> dict[str, Any] | None:
    held = b""
    while len(held) < 4 or len(held) < 4 + struct.unpack(">I", held[:4])[0]:
        got = session.recv(1 << 16)
        if not got:
            return None
        held += got
    return json.loads(held[4:])


class Daemon:
    """Who answers each carrier: TLS, then one call at a time, refused or answered."""

    def __init__(self, me: identity.Identity, devices: Devices) -> None:
        self.me = me
        self.devices = devices
        self.codes = pairing.Codes()
        self.live: list[tls.Secured] = []
        self.refused: list[BaseException] = []
        devices.watch(self.dropped)

    def dropped(self, device: Device) -> None:
        for session in [one for one in self.live if one.peer == device.fingerprint]:
            session.close()

    def serve(self, end: socket.socket) -> None:
        def run() -> None:
            try:
                session = tls.answer(end, self.me)
            except tls.RefusedError as why:
                self.refused.append(why)
                return
            self.live.append(session)
            paired = self.devices.named(session.peer) is not None
            with suppress(OSError):
                while (call := heard(session)) is not None:
                    method = call["method"]
                    if not pairing.allows(method, paired=paired):
                        said(session, {"error": 401, "message": pairing.NOT_PAIRED})
                    elif method == "pair.claim":
                        try:
                            name = pairing.claim(
                                self.codes,
                                self.devices,
                                call["token"],
                                call["name"],
                                session.peer,
                            )
                        except pairing.InvalidCodeError as why:
                            said(session, {"error": 403, "message": str(why)})
                        else:
                            paired = True
                            said(session, {"device": name})
                    else:
                        said(session, {"result": method})

        threading.Thread(target=run, daemon=True).start()


def socketpair() -> Carrier:
    """A carrier straight from one end to the other."""
    return socket.socketpair()


def relayed() -> Carrier:
    """A carrier through a relay: two socket pairs whose middles a thread splices, unread."""
    near, into = socket.socketpair()
    out_of, far = socket.socketpair()

    def splice(source: socket.socket, sink: socket.socket) -> None:
        with suppress(OSError):
            while got := source.recv(1 << 16):
                sink.sendall(got)
        with suppress(OSError):
            sink.shutdown(socket.SHUT_WR)

    for one, other in ((into, out_of), (out_of, into)):
        threading.Thread(target=splice, args=(one, other), daemon=True).start()
    return near, far


@pytest.fixture(params=[socketpair, relayed], ids=["socketpair", "relay"])
def carrier(request: pytest.FixtureRequest) -> Callable[[], Carrier]:
    return request.param


@pytest.fixture
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Daemon:
    me = made(tmp_path / "daemon", monkeypatch)
    return Daemon(me, Devices(tmp_path / "daemon" / "devices.yaml"))


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    return made(tmp_path / "client", monkeypatch)


def reach(
    daemon: Daemon, client: identity.Identity, carrier: Callable[[], Carrier], pin: str
) -> tls.Secured:
    near, far = carrier()
    near.settimeout(10)
    daemon.serve(far)
    return tls.dial(near, client, pin, "box")


def test_a_paired_client_reaches_the_daemon_it_pins(
    daemon: Daemon, client: identity.Identity, carrier: Callable[[], Carrier]
) -> None:
    daemon.devices.add("laptop", client.fingerprint)
    session = reach(daemon, client, carrier, daemon.me.fingerprint)
    assert session.peer == daemon.me.fingerprint
    said(session, {"method": "epic.attach"})
    assert heard(session) == {"result": "epic.attach"}
    session.close()


def test_a_daemon_of_another_id_is_refused(
    daemon: Daemon,
    client: identity.Identity,
    carrier: Callable[[], Carrier],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daemon.devices.add("laptop", client.fingerprint)
    other = made(tmp_path / "other", monkeypatch)
    with pytest.raises(
        tls.ImpostorError, match="box is not the daemon it was paired with"
    ):
        reach(daemon, client, carrier, other.fingerprint)


def test_an_unpaired_client_may_only_pair_and_then_is_paired(
    daemon: Daemon, client: identity.Identity, carrier: Callable[[], Carrier]
) -> None:
    session = reach(daemon, client, carrier, daemon.me.fingerprint)
    said(session, {"method": "epic.attach"})
    assert heard(session) == {"error": 401, "message": pairing.NOT_PAIRED}
    said(session, {"method": "session.hello"})
    assert heard(session) == {"result": "session.hello"}

    code = pairing.read(
        daemon.codes.make(daemon.me.fingerprint, ["tcp://box:1"]).text()
    )
    assert code.id == daemon.me.fingerprint
    said(session, {"method": "pair.claim", "token": code.token, "name": "laptop"})
    assert heard(session) == {"device": "laptop"}
    said(session, {"method": "epic.attach"})
    assert heard(session) == {"result": "epic.attach"}
    session.close()

    again = reach(daemon, client, carrier, daemon.me.fingerprint)
    said(again, {"method": "epic.attach"})
    assert heard(again) == {"result": "epic.attach"}
    again.close()


def test_a_revoked_client_is_dropped_and_then_refused(
    daemon: Daemon, client: identity.Identity, carrier: Callable[[], Carrier]
) -> None:
    daemon.devices.add("laptop", client.fingerprint)
    session = reach(daemon, client, carrier, daemon.me.fingerprint)
    said(session, {"method": "epic.attach"})
    assert heard(session) == {"result": "epic.attach"}

    daemon.devices.revoke("laptop")
    assert heard(session) is None

    again = reach(daemon, client, carrier, daemon.me.fingerprint)
    said(again, {"method": "epic.attach"})
    assert heard(again) == {"error": 401, "message": pairing.NOT_PAIRED}
    again.close()


def test_an_expired_or_reused_code_is_refused(
    daemon: Daemon,
    client: identity.Identity,
    carrier: Callable[[], Carrier],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1_000_000.0]
    daemon.codes = pairing.Codes(lambda: now[0])
    expired = daemon.codes.make(daemon.me.fingerprint, ["tcp://box:1"], 60)
    used = daemon.codes.make(daemon.me.fingerprint, ["tcp://box:1"])
    now[0] += 60

    session = reach(daemon, client, carrier, daemon.me.fingerprint)
    said(session, {"method": "pair.claim", "token": expired.token, "name": "laptop"})
    assert heard(session) == {"error": 403, "message": pairing.NOT_VALID}

    said(session, {"method": "pair.claim", "token": used.token, "name": "laptop"})
    assert heard(session) == {"device": "laptop"}
    session.close()

    stranger = made(tmp_path / "stranger", monkeypatch)
    other = reach(daemon, stranger, carrier, daemon.me.fingerprint)
    said(other, {"method": "pair.claim", "token": used.token, "name": "phone"})
    assert heard(other) == {"error": 403, "message": pairing.NOT_VALID}
    said(other, {"method": "epic.attach"})
    assert heard(other) == {"error": 401, "message": pairing.NOT_PAIRED}
    other.close()


def test_processes_racing_to_make_the_identity_end_with_one(tmp_path: Path) -> None:
    probe = "from hmz.trust import identity; print(identity.device().fingerprint)"
    environ = {**os.environ, **places(tmp_path / "home")}
    running = [
        subprocess.Popen(
            [sys.executable, "-c", probe],
            env=environ,
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(6)
    ]
    printed = {one.communicate(timeout=60)[0].strip() for one in running}
    assert len(printed) == 1
    (fingerprint,) = printed
    assert identity.is_fingerprint(fingerprint)
    (kept,) = (tmp_path / "home" / "data" / "humanize" / "identity").iterdir()
    assert sorted(one.name for one in kept.iterdir()) == ["cert.pem", "key.pem"]
