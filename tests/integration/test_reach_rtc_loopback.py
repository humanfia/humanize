"""Two aiortc peers in one process, joined by signals in memory: a data channel as a carrier.

The daemon's side answers and a client's offers, over this machine's own interfaces with host
candidates alone and no STUN or TURN. Bytes cross both ways, more than a megabyte of them in
messages of at most 16 384 bytes; an answer not the pinned daemon's, or not signed by the key of
its certificate, is refused before the channel opens; a channel the protocol does not fix is
refused by the daemon; and either side closing is seen by the other.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import json
import os
import queue
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, cast

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.x509.oid import NameOID

from hmz.rtc import CHUNK, Pipe, Refused, answer, device, offer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.timeout(120)

#: What ends one direction of the signals.
_END = object()


class _Signals:
    """One side of a join's signals: what it sends is what the other side receives."""

    def __init__(self, inbox: queue.Queue[object], outbox: queue.Queue[object]) -> None:
        self.inbox = inbox
        self.outbox = outbox
        self.sent: list[dict[str, Any]] = []

    def send(self, data: dict[str, Any]) -> None:
        self.sent.append(data)
        self.outbox.put(json.loads(json.dumps(data)))

    def receive(self, timeout: float) -> object:
        try:
            item = self.inbox.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None
        if item is _END:
            raise EOFError
        return item


def _joined() -> tuple[_Signals, _Signals]:
    there: queue.Queue[object] = queue.Queue()
    back: queue.Queue[object] = queue.Queue()
    return _Signals(back, there), _Signals(there, back)


class _Device:
    """A device key and its self-signed certificate, as a native device holds them."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "hmz test")])
        now = datetime.datetime.now(datetime.UTC)
        self.cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(int.from_bytes(os.urandom(16)) >> 1)
            .not_valid_before(now)
            .not_valid_after(
                datetime.datetime(9999, 12, 31, 23, 59, 59, tzinfo=datetime.UTC)
            )
            .sign(self.key, hashes.SHA256())
            .public_bytes(serialization.Encoding.DER)
        )
        self.id = _spki(self.cert)

    def sign(self, text: bytes) -> bytes:
        r, s = decode_dss_signature(self.key.sign(text, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32) + s.to_bytes(32)


def _spki(cert: bytes) -> str:
    spki = (
        x509.load_der_x509_certificate(cert)
        .public_key()
        .public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return base64.b32encode(hashlib.sha256(spki).digest()).decode().rstrip("=").lower()


def _verify(cert: bytes, text: bytes, sig: bytes) -> str:
    key = x509.load_der_x509_certificate(cert).public_key()
    assert isinstance(key, ec.EllipticCurvePublicKey)
    if len(sig) != 64:
        raise ValueError
    der = encode_dss_signature(int.from_bytes(sig[:32]), int.from_bytes(sig[32:]))
    try:
        key.verify(der, text, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as why:
        raise ValueError from why
    return _spki(cert)


@pytest.fixture
def daemon() -> _Device:
    return _Device()


@pytest.fixture
def pool() -> Iterator[ThreadPoolExecutor]:
    with ThreadPoolExecutor(2) as pool:
        yield pool


def _answering(
    pool: ThreadPoolExecutor,
    signals: _Signals,
    daemon: _Device,
    sign: Callable[[bytes], bytes] | None = None,
    timeout: float = 30,
) -> Future[Pipe]:
    return pool.submit(
        answer, signals, cert=daemon.cert, sign=sign or daemon.sign, timeout=timeout
    )


def _read(pipe: Pipe, size: int) -> bytes:
    got = bytearray()
    while len(got) < size:
        chunk = pipe.recv(65536)
        if not chunk:
            break
        got += chunk
    return bytes(got)


def _pair(pool: ThreadPoolExecutor, daemon: _Device) -> tuple[Pipe, Pipe, _Signals]:
    client, served = _joined()
    answered = _answering(pool, served, daemon)
    near = offer(client, pin=daemon.id, verify=_verify)
    return near, answered.result(30), client


def test_bytes_cross_both_ways_in_bounded_messages(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    near, far, client = _pair(pool, daemon)
    with near, far:
        assert near.device == daemon.id
        assert far.device == device(client.sent[0]["sdp"])
        assert far.device.startswith("dtls:")
        assert len(far.device) == len("dtls:") + 52

        near.sendall(b"hello")
        assert _read(far, 5) == b"hello"
        far.sendall(b"and back")
        assert _read(near, 8) == b"and back"

        big = os.urandom(3 * 1024 * 1024 + 7)
        sending = pool.submit(near.sendall, big)
        assert _read(far, len(big)) == big
        sending.result(30)

        echoed = pool.submit(far.sendall, big[::-1])
        assert _read(near, len(big)) == big[::-1]
        echoed.result(30)


def test_messages_are_at_most_one_chunk(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    near, far, _ = _pair(pool, daemon)
    with near, far:
        near.sendall(os.urandom(5 * CHUNK + 1))
        sizes: list[int] = []
        while sum(sizes) < 5 * CHUNK + 1:
            sizes.append(len(far.recv(10 * CHUNK)))
        assert max(sizes) <= CHUNK


def test_an_answer_not_the_pinned_daemons_is_refused(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    client, served = _joined()
    answered = _answering(pool, served, daemon, timeout=5)
    with pytest.raises(Refused, match="not daemon"):
        offer(client, pin=_Device().id, verify=_verify, timeout=10)
    with pytest.raises((TimeoutError, EOFError, ConnectionError)):
        answered.result(30).close()


def test_an_answer_signed_by_another_key_is_refused(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    client, served = _joined()
    answered = _answering(pool, served, daemon, sign=_Device().sign, timeout=5)
    with pytest.raises(Refused, match="signature"):
        offer(client, pin=daemon.id, verify=_verify, timeout=10)
    with pytest.raises((TimeoutError, EOFError, ConnectionError)):
        answered.result(30).close()


def test_a_signature_over_another_offer_is_refused(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    client, served = _joined()
    answered = _answering(pool, _Swapping(served, _offer_sdp()), daemon, timeout=5)
    with pytest.raises(Refused, match="signature"):
        offer(client, pin=daemon.id, verify=_verify, timeout=10)
    with pytest.raises((TimeoutError, EOFError, ConnectionError)):
        answered.result(30).close()


class _Swapping(_Signals):
    """A relay that hands the daemon an offer of its own in place of the client's."""

    def __init__(self, signals: _Signals, sdp: str) -> None:
        super().__init__(signals.inbox, signals.outbox)
        self.sdp = sdp

    def receive(self, timeout: float) -> object:
        item = cast("dict[str, Any]", super().receive(timeout))
        return {"type": "offer", "sdp": self.sdp} if item["type"] == "offer" else item


def _offer_sdp() -> str:
    """The offer of another connection, which nobody answers."""
    from aiortc import RTCConfiguration, RTCPeerConnection

    async def run() -> str:
        connection = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        connection.createDataChannel("hmz")
        await connection.setLocalDescription(await connection.createOffer())
        await connection.close()
        return connection.localDescription.sdp

    return asyncio.run(run())


def test_closing_either_side_ends_the_other(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    for closer in ("near", "far"):
        near, far, _ = _pair(pool, daemon)
        closing, other = (near, far) if closer == "near" else (far, near)
        closing.close()
        assert other.recv(1) == b""
        with pytest.raises(BrokenPipeError):
            other.sendall(b"anyone there?")
        other.close()
        other.close()
        with pytest.raises(BrokenPipeError):
            closing.sendall(b"after close")
    assert "hmz-rtc" not in {thread.name for thread in threading.enumerate()}


def test_the_daemon_refuses_a_channel_the_protocol_does_not_fix(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    client, served = _joined()
    answered = _answering(pool, served, daemon, timeout=20)
    stray = pool.submit(_raw_offer, client, "other")
    with pytest.raises(Refused, match="ordered and reliable"):
        answered.result(30)
    stray.result(30)


def test_a_text_message_closes_the_channel(
    pool: ThreadPoolExecutor, daemon: _Device
) -> None:
    client, served = _joined()
    answered = _answering(pool, served, daemon, timeout=20)
    texting = pool.submit(_raw_offer, client, "hmz", "hello")
    with answered.result(30) as far:
        assert far.recv(1) == b""
    texting.result(30)


def _raw_offer(signals: _Signals, label: str, text: str = "") -> None:
    """Offers a data channel by aiortc directly, sending `text` on it once it opens."""
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

    async def run() -> None:
        connection = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        channel = connection.createDataChannel(label)
        if text:
            channel.on("open", lambda: channel.send(text))
        await connection.setLocalDescription(await connection.createOffer())
        signals.send({"type": "offer", "sdp": connection.localDescription.sdp})
        reply = await asyncio.to_thread(signals.inbox.get, True, 20)
        sdp = cast("dict[str, str]", reply)["sdp"]
        await connection.setRemoteDescription(RTCSessionDescription(sdp, "answer"))
        await asyncio.sleep(5)
        await connection.close()

    asyncio.run(run())
