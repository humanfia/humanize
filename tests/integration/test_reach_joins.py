"""A client joining a daemon registered at a relay, through a relay written here from wire.md.

The relay below is Section 5 of wire.md and no more: a daemon registers under its id and
proves it holds the key of that id, a client joins by the id, the daemon accepts the join over
a WebSocket of its own, and the two are spliced, binary message for binary message. The proof
is made here as `hmz.trust` will make it, with a key and a certificate of the test's own.
"""

from __future__ import annotations

import base64
import contextlib
import datetime
import hashlib
import json
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any, cast

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.x509.oid import NameOID
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

from hmz.reach import (
    Pipe,
    ProcessPipe,
    RelayListener,
    SocketPipe,
    StreamPipe,
    WebSocketPipe,
    dial,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def fingerprint(cert: x509.Certificate) -> str:
    """The SPKI fingerprint of a certificate: SHA-256 of its DER SPKI, in base32 (4.2.3)."""
    spki = cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    digest = hashlib.sha256(spki).digest()
    return base64.b32encode(digest).decode().lower().rstrip("=")


class Device:
    """A device's key and self-signed certificate, and its proof to a relay (Section 5.4.2)."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hmz test")])
        now = datetime.datetime.now(datetime.UTC)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(
                datetime.datetime(9999, 12, 31, 23, 59, 59, tzinfo=datetime.UTC)
            )
            .sign(self.key, hashes.SHA256())
        )
        self.id = fingerprint(self.cert)

    def prove(self, nonce: str) -> tuple[str, str]:
        der = self.cert.public_bytes(serialization.Encoding.DER)
        signed = self.key.sign(
            f"hmz-relay/1\n{nonce}".encode(), ec.ECDSA(hashes.SHA256())
        )
        r, s = decode_dss_signature(signed)
        return (
            base64.b64encode(der).decode(),
            _b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big")),
        )


def proven(said: dict[str, Any], daemon: str, nonce: str) -> bool:
    """Whether a `prove` proves `daemon` for `nonce` (Section 5.4.3)."""
    try:
        cert = x509.load_der_x509_certificate(base64.b64decode(said["cert"]))
        sig = _unb64url(said["sig"])
        key = cert.public_key()
        assert isinstance(key, ec.EllipticCurvePublicKey)
        key.verify(
            encode_dss_signature(
                int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
            ),
            f"hmz-relay/1\n{nonce}".encode(),
            ec.ECDSA(hashes.SHA256()),
        )
    except Exception:  # noqa: BLE001 -- anything wrong with it is no proof
        return False
    return fingerprint(cert) == daemon


class Relay:
    """`hmz relay serve` as Section 5 of wire.md says it behaves, for native joins."""

    def __init__(self) -> None:
        self.rooms: dict[str, ServerConnection] = {}
        self.waiting: dict[
            str, tuple[ServerConnection, threading.Event, list[Any]]
        ] = {}
        self.lock = threading.Lock()
        self.server: Server = serve(self.handles, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.server.socket.getsockname()[1]}/r"

    def handles(self, connection: ServerConnection) -> None:
        try:
            first = json.loads(connection.recv())
        except (ValueError, TypeError, ConnectionClosed):
            return self.refuses(connection, "Send a control message first.")
        kind = first.get("t")
        if kind == "register":
            return self.registers(connection, first)
        if kind == "join":
            return self.joins(connection, first)
        if kind == "accept":
            return self.accepts(connection, first)
        return self.refuses(connection, "That message is not expected here.")

    def refuses(self, connection: ServerConnection, why: str) -> None:
        with contextlib.suppress(ConnectionClosed):
            connection.send(json.dumps({"t": "error", "why": why}))
        connection.close()

    def registers(self, connection: ServerConnection, said: dict[str, Any]) -> None:
        daemon, nonce = said["id"], _b64url(secrets.token_bytes(32))
        connection.send(json.dumps({"t": "challenge", "nonce": nonce}))
        proof = json.loads(connection.recv())
        if proof.get("t") != "prove" or not proven(proof, daemon, nonce):
            return self.refuses(connection, "That daemon id is not proven.")
        with self.lock:
            earlier = self.rooms.get(daemon)
            self.rooms[daemon] = connection
        if earlier is not None:
            earlier.close()
        connection.send(json.dumps({"t": "registered"}))
        try:
            for message in connection:
                told = json.loads(message)
                if told.get("t") == "refuse" and told.get("conn") in self.waiting:
                    _, answered, held = self.waiting[told["conn"]]
                    held.append(told.get("why", ""))
                    answered.set()
        except ConnectionClosed:
            pass
        finally:
            with self.lock:
                if self.rooms.get(daemon) is connection:
                    del self.rooms[daemon]
        return None

    def joins(self, client: ServerConnection, said: dict[str, Any]) -> None:
        with self.lock:
            control = self.rooms.get(said.get("id", ""))
        if control is None:
            return self.refuses(client, f"No daemon {said.get('id')} is here.")
        conn = _b64url(secrets.token_bytes(16))
        answered, held = threading.Event(), cast("list[Any]", [])
        self.waiting[conn] = (client, answered, held)
        control.send(json.dumps({"t": "join", "conn": conn, "kind": said["kind"]}))
        if not answered.wait(10):
            return self.refuses(client, "The daemon did not answer.")
        (daemon,) = held
        if isinstance(daemon, str):
            return self.refuses(client, daemon)
        client.send(json.dumps({"t": "joined"}))
        self.splices(client, daemon)
        return None

    def accepts(self, daemon: ServerConnection, said: dict[str, Any]) -> None:
        waiting = self.waiting.pop(said.get("conn", ""), None)
        if waiting is None:
            return self.refuses(daemon, "That join is not waiting.")
        _, answered, held = waiting
        done = threading.Event()
        held.append((daemon, done))
        answered.set()
        # The splice is carried on the client's thread; this one holds the connection open.
        done.wait()
        return None

    def splices(
        self,
        client: ServerConnection,
        accepted: tuple[ServerConnection, threading.Event],
    ) -> None:
        daemon, done = accepted

        def carries(source: ServerConnection, sink: ServerConnection) -> None:
            try:
                for message in source:
                    if isinstance(message, str):
                        break
                    sink.send(message)
            except ConnectionClosed:
                pass
            source.close()
            sink.close()

        back = threading.Thread(target=carries, args=(daemon, client), daemon=True)
        back.start()
        carries(client, daemon)
        back.join(5)
        done.set()

    def drops(self, daemon: str) -> None:
        """Closes a daemon's control connection, as a relay restarting would."""
        with self.lock:
            control = self.rooms.get(daemon)
        assert control is not None
        control.close()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def relay() -> Iterator[Relay]:
    held = Relay()
    yield held
    held.close()


def echoes(listener: RelayListener) -> None:
    """Answers each client joined with what it says."""

    def answers(pipe: Pipe) -> None:
        with contextlib.suppress(OSError):
            while said := pipe.recv(65536):
                pipe.sendall(said)
        pipe.close()

    while True:
        try:
            pipe = listener.accept()
        except OSError:
            return
        threading.Thread(target=answers, args=(pipe,), daemon=True).start()


def registered(listener: RelayListener) -> RelayListener:
    assert listener.registered.wait(10), listener.said
    threading.Thread(target=echoes, args=(listener,), daemon=True).start()
    return listener


def round_trip(pipe: Pipe, said: bytes) -> bytes:
    writing = threading.Thread(target=pipe.sendall, args=(said,), daemon=True)
    writing.start()
    heard = b""
    while len(heard) < len(said) and (read := pipe.recv(len(said) - len(heard))):
        heard += read
    writing.join(5)
    return heard


def test_a_client_joins_a_daemon_registered_and_bytes_cross_the_splice(
    relay: Relay,
) -> None:
    device = Device()
    listener = registered(RelayListener(relay.url, device.id, device.prove))
    try:
        pipe = dial(f"relay:{relay.url}", daemon=device.id)
        assert not trusted(pipe)
        assert round_trip(pipe, b"hello, daemon") == b"hello, daemon"
        # More than one message the relay lets through, split and carried whole.
        long = bytes(range(256)) * 9000
        assert round_trip(pipe, long) == long
        pipe.close()
    finally:
        listener.close()


def test_a_join_of_a_daemon_not_there_is_refused_with_what_the_relay_said(
    relay: Relay,
) -> None:
    with pytest.raises(ConnectionError, match=r"^No daemon nobody is here\.$"):
        dial(f"relay:{relay.url}", daemon="nobody")


def test_a_daemon_that_cannot_prove_its_id_is_not_registered(relay: Relay) -> None:
    device, other = Device(), Device()
    listener = RelayListener(relay.url, device.id, other.prove)
    try:
        deadline = time.monotonic() + 10
        while not listener.said and time.monotonic() < deadline:
            time.sleep(0.05)
        assert listener.said == "That daemon id is not proven."
        assert not listener.registered.is_set()
    finally:
        listener.close()


def test_a_dropped_registration_is_made_again_after_a_second(relay: Relay) -> None:
    device = Device()
    listener = registered(RelayListener(relay.url, device.id, device.prove))
    try:
        relay.drops(device.id)
        deadline = time.monotonic() + 5
        while listener.registered.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        dropped = time.monotonic()
        assert listener.registered.wait(10), listener.said
        assert time.monotonic() - dropped >= 0.9
        pipe = dial(f"relay:{relay.url}", daemon=device.id)
        assert round_trip(pipe, b"again") == b"again"
        pipe.close()
    finally:
        listener.close()


def test_a_closed_registration_accepts_nothing(relay: Relay) -> None:
    device = Device()
    listener = RelayListener(relay.url, device.id, device.prove)
    assert listener.registered.wait(10), listener.said
    listener.close()
    with pytest.raises(OSError, match="closed"):
        listener.accept()


def trusted(pipe: Pipe) -> bool:
    """Whether a pipe `hmz.reach` made says its carrier is trusted."""
    assert isinstance(pipe, SocketPipe | ProcessPipe | StreamPipe | WebSocketPipe)
    return pipe.trusted
