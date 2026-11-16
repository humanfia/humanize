"""`hmz.trust.tls`: mutual TLS between two devices, over a pipe held in memory."""

from __future__ import annotations

import datetime
import ssl
import threading
from typing import TYPE_CHECKING

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from hmz.trust import identity, tls
from tests.unit.trust.doubles_trust import End, device, pipe

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    return device(tmp_path / "daemon", monkeypatch)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> identity.Identity:
    return device(tmp_path / "client", monkeypatch)


def answering(
    end: End, daemon: identity.Identity
) -> tuple[threading.Thread, list[object]]:
    """The daemon's end answering TLS in a thread, and what it came to: a session or a refusal."""
    came: list[object] = []

    def answer() -> None:
        try:
            came.append(tls.answer(end, daemon))
        except tls.RefusedError as why:
            came.append(why)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    return thread, came


def test_each_side_knows_the_other_by_its_key(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    dialed = tls.dial(near, client, daemon.fingerprint, "box")
    thread.join(5)
    (answered,) = came
    assert isinstance(answered, tls.Secured)
    assert dialed.peer == daemon.fingerprint
    assert answered.peer == client.fingerprint
    assert answered.certificate == client.certificate

    dialed.sendall(b"hello")
    assert answered.recv(100) == b"hello"
    answered.sendall(b"there")
    assert dialed.recv(100) == b"there"
    assert b"hello" not in near.sent


def test_a_lot_crosses_both_ways_at_once(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    dialed = tls.dial(near, client, daemon.fingerprint, "box")
    thread.join(5)
    (answered,) = came
    assert isinstance(answered, tls.Secured)
    much = bytes(range(256)) * 4096

    def drained(session: tls.Secured, into: bytearray) -> Callable[[], None]:
        def read() -> None:
            while len(into) < len(much):
                got = session.recv(1 << 16)
                if not got:
                    return
                into.extend(got)

        return read

    one, other = bytearray(), bytearray()
    readers = [
        threading.Thread(target=drained(answered, one)),
        threading.Thread(target=drained(dialed, other)),
    ]
    for reader in readers:
        reader.start()
    writers = [
        threading.Thread(target=dialed.sendall, args=(much,)),
        threading.Thread(target=answered.sendall, args=(much,)),
    ]
    for writer in writers:
        writer.start()
    for each in writers + readers:
        each.join(30)
    assert bytes(one) == much
    assert bytes(other) == much


def test_a_daemon_of_another_key_is_refused_before_anything_is_sent(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    with pytest.raises(
        tls.ImpostorError, match=r"^box is not the daemon it was paired with\.$"
    ):
        tls.dial(near, client, client.fingerprint, "box")
    thread.join(5)
    assert isinstance(came[0], tls.RefusedError)
    assert near.closed
    assert far.closed


def test_nothing_pinned_admits_no_daemon(client: identity.Identity) -> None:
    near, _ = pipe()
    with pytest.raises(
        tls.RefusedError, match=r"^box needs the id of the daemon it reaches\.$"
    ) as refused:
        tls.dial(near, client, "", "box")
    assert not isinstance(refused.value, tls.ImpostorError)
    assert near.closed
    assert not near.sent


def test_a_client_certificate_another_key_signed_is_refused(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    forged = (
        x509.CertificateBuilder()
        .subject_name(client.certificate.subject)
        .issuer_name(client.certificate.subject)
        .public_key(client.key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC))
        .not_valid_after(datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC))
        .sign(other, hashes.SHA256())
    )
    near, far = pipe()
    thread, came = answering(far, daemon)
    # TLS 1.3 ends the client's handshake before the daemon has read its certificate: the
    # refusal is what the client reads next.
    with pytest.raises(ConnectionError):
        tls.dial(
            near, identity.Identity(client.key, forged), daemon.fingerprint, "box"
        ).recv(1)
    thread.join(5)
    assert isinstance(came[0], tls.RefusedError)


def stdlib(
    end: End,
    client: identity.Identity,
    tmp_path: Path,
    configure: Callable[[ssl.SSLContext], None],
) -> None:
    """A client of the standard library's TLS over a pipe, configured as a test says."""
    (tmp_path / "c.pem").write_bytes(
        client.certificate.public_bytes(serialization.Encoding.PEM)
    )
    (tmp_path / "k.pem").write_bytes(
        client.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.load_cert_chain(tmp_path / "c.pem", tmp_path / "k.pem")
    configure(context)
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    tied = context.wrap_bio(incoming, outgoing)
    while True:
        try:
            tied.do_handshake()
        except ssl.SSLWantReadError:
            end.sendall(outgoing.read())
            got = end.recv(1 << 16)
            if not got:
                raise ConnectionError("closed") from None
            incoming.write(got)
        else:
            end.sendall(outgoing.read())
            tied.read(1)


def tls12(context: ssl.SSLContext) -> None:
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["hmz"])


def no_alpn(context: ssl.SSLContext) -> None:
    context.minimum_version = ssl.TLSVersion.TLSv1_3


def other_alpn(context: ssl.SSLContext) -> None:
    context.set_alpn_protocols(["h2"])


@pytest.mark.parametrize("configure", [tls12, no_alpn, other_alpn])
def test_the_daemon_speaks_tls_13_and_hmz_alone(
    daemon: identity.Identity,
    client: identity.Identity,
    tmp_path: Path,
    configure: Callable[[ssl.SSLContext], None],
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    with pytest.raises((ssl.SSLError, ConnectionError)):
        stdlib(near, client, tmp_path, configure)
    thread.join(5)
    assert isinstance(came[0], tls.RefusedError)
    assert far.closed


def test_a_daemon_that_closes_during_the_handshake_is_refused(
    client: identity.Identity, daemon: identity.Identity
) -> None:
    near, far = pipe()
    far.close()
    with pytest.raises(tls.RefusedError, match="closed during the handshake"):
        tls.dial(near, client, daemon.fingerprint, "box")
    assert near.closed


def test_closing_says_so_and_the_other_side_reads_the_end(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    dialed = tls.dial(near, client, daemon.fingerprint, "box")
    thread.join(5)
    (answered,) = came
    assert isinstance(answered, tls.Secured)
    dialed.sendall(b"last")
    before = len(near.sent)
    dialed.close()
    dialed.close()
    assert len(near.sent) > before, "a close_notify was written"
    assert near.closed
    assert answered.recv(100) == b"last"
    assert answered.recv(100) == b""


def test_a_pipe_cut_without_close_notify_reads_as_the_end(
    daemon: identity.Identity, client: identity.Identity
) -> None:
    near, far = pipe()
    thread, came = answering(far, daemon)
    tls.dial(near, client, daemon.fingerprint, "box")
    thread.join(5)
    (answered,) = came
    assert isinstance(answered, tls.Secured)
    near.close()
    assert answered.recv(100) == b""
