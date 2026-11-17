"""The anchor link over a network: TLS 1.3, and the secret proved inside it.

A ``tcp://`` target crosses networks nobody vouches for, so its frames go inside TLS 1.3 with
the application protocol ``hmz-anchor``. The serving half is the server, under a self-signed
certificate it made as it started; this side is the client, shows no certificate, and takes
whichever one the server shows, holding it only to the handshake's own signature. Who is at the
other end is settled one layer up, by the ``HELLO``
(:meth:`hmz.coganchor.remote.RemoteClient.start`): each side proves it holds the key by an HMAC
over the SHA-256 of the server's SubjectPublicKeyInfo -- the *binding* -- so a proof made for
one TLS session is worth nothing in another, and the key itself never crosses.

The standard library's TLS is run over memory rather than over the socket, since a session is
read on one thread while another writes, which one OpenSSL connection is not to be entered by
at once. :mod:`hmz.trust.tls` does the same for the daemon's mutual TLS; this layer may not
import it.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import socket
import ssl
import threading
from dataclasses import dataclass, field

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

__all__ = ["ALPN", "Bound", "Sealed", "dial"]

#: The one application protocol either side offers, and the one it closes a handshake without.
ALPN = "hmz-anchor"

#: What the client's proof is an HMAC of, before the binding.
_COG = b"hmz-anchor cog\0"

#: What the server's proof is an HMAC of, before the binding and the client's proof.
_ANCHOR = b"hmz-anchor anchor\0"

#: How much is read off the socket at a time: a TLS record and then some.
_CHUNK = 1 << 16


@dataclass(frozen=True, slots=True)
class Bound:
    """What the ``HELLO`` of a channel carried inside TLS proves the other end by.

    Attributes:
      binding: SHA-256 of the DER SubjectPublicKeyInfo of the serving half's certificate.
      key: The token, or None where this side holds none.
      whom: The target, as a refusal names it.
    """

    binding: bytes
    key: bytes | None = field(repr=False)
    whom: str

    def cog_proof(self) -> bytes | None:
        """``HMAC-SHA256(key, b"hmz-anchor cog" NUL binding)``, or None without a key."""
        if self.key is None:
            return None
        return hmac.digest(self.key, _COG + self.binding, "sha256")

    def anchor_proved(self, cog: bytes, said: object) -> bool:
        """Whether `said` is the serving half's answer to `cog`, compared in constant time.

        Args:
          cog: This side's own proof.
          said: The ``proof`` of the ``HELLO`` reply, as it came.

        Returns:
          True only for the hex of ``HMAC-SHA256(key, b"hmz-anchor anchor" NUL binding cog)``.
        """
        if self.key is None or not isinstance(said, str):
            return False
        try:
            raw = bytes.fromhex(said)
        except ValueError:
            return False
        expected = hmac.digest(self.key, _ANCHOR + self.binding + cog, "sha256")
        return hmac.compare_digest(raw, expected)


class Sealed:
    """A socket whose bytes cross inside TLS: a :class:`hmz.rpc.Pipe` of its own.

    One thread may read while another writes, which is how a session is carried. Two
    writers are written one after the other, whole.

    Attributes:
      bound: What the session's ``HELLO`` proves the other end by.
    """

    def __init__(
        self,
        tls: ssl.SSLObject,
        incoming: ssl.MemoryBIO,
        outgoing: ssl.MemoryBIO,
        sock: socket.socket,
        bound: Bound,
    ) -> None:
        """Takes a TLS object whose handshake is over, its two buffers, and the socket."""
        self.bound = bound
        self._tls = tls
        self._incoming = incoming
        self._outgoing = outgoing
        self._sock = sock
        #: Held for each call into OpenSSL, which is not to be entered by two threads.
        self._lock = threading.Lock()
        #: Held from taking what OpenSSL wrote until the socket has it, so that records cross
        #: in the order they were made.
        self._out = threading.Lock()
        #: What OpenSSL wrote that is not on the socket yet, oldest first. Under `_lock`.
        self._owed = bytearray()
        self._closed = False

    def recv(self, bufsize: int, /) -> bytes:
        """What the other side sent next, at most `bufsize` bytes of it.

        Returns:
          At least one byte, or ``b""`` once the other side has closed.

        Raises:
          ConnectionError: If what arrived is not TLS from the other side.
        """
        while True:
            got = None
            with self._lock:
                try:
                    got = self._tls.read(bufsize)
                except ssl.SSLWantReadError:
                    pass
                except ssl.SSLZeroReturnError:
                    return b""
                except ssl.SSLError as why:
                    raise ConnectionError(f"the session broke: {why}") from why
                self._owed += self._outgoing.read()
            # What reading made OpenSSL say back, sent now.
            self._kicked()
            if got:
                return got
            try:
                arrived = self._sock.recv(_CHUNK)
            except OSError:
                return b""
            if not arrived:
                return b""
            with self._lock:
                self._incoming.write(arrived)

    def sendall(self, data: bytes, /) -> None:
        """Writes all of `data` to the other side.

        Raises:
          ConnectionError: If the session is broken.
          OSError: If the socket cannot be written.
        """
        with self._out:
            with self._lock:
                try:
                    self._tls.write(data)
                except ssl.SSLError as why:
                    raise ConnectionError(f"the session broke: {why}") from why
            self._pumped()
        self._kicked()

    def close(self) -> None:
        """Says close_notify where it can without waiting, and shuts and closes the socket."""
        if self._closed:
            return
        self._closed = True
        if self._out.acquire(blocking=False):
            try:
                with self._lock, contextlib.suppress(ssl.SSLError):
                    self._tls.unwrap()
                with contextlib.suppress(OSError):
                    self._pumped()
            finally:
                self._out.release()
        # Closing a socket wakes no thread waiting on it, on Linux; shutting it does.
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()

    def _pumped(self) -> None:
        """Writes to the socket whatever OpenSSL has to send, in order. Holding `_out`."""
        while True:
            with self._lock:
                self._owed += self._outgoing.read()
                out = bytes(self._owed)
                self._owed.clear()
            if not out:
                return
            self._sock.sendall(out)

    def _kicked(self) -> None:
        """Sends what OpenSSL has to send, unless another thread is sending, which then does.

        Never waits on the socket: a reader waiting for a writer stuck on a socket the other
        side is not reading, because its own reader waits the same way, is two sides waiting
        on each other.
        """
        while self._out.acquire(blocking=False):
            try:
                self._pumped()
            finally:
                self._out.release()
            with self._lock:
                if not self._owed and not self._outgoing.pending:
                    return


def dial(sock: socket.socket, key: bytes | None, whom: str) -> Sealed:
    """Opens TLS as the client on a connected socket, closing the socket where it fails.

    Args:
      sock: The connection to the serving half, blocking.
      key: The token this side proves, or None.
      whom: The target, as a refusal names it.

    Returns:
      The session, bound to the certificate the serving half showed.

    Raises:
      ConnectionError: If the handshake fails, or agrees on another protocol than
        ``hmz-anchor``.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # Any certificate at all: the HELLO's proofs, bound to its key, say who is there.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols([ALPN])
    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
    tls = context.wrap_bio(incoming, outgoing)
    try:
        shown = _shaken(tls, incoming, outgoing, sock, whom)
        spki = (
            x509.load_der_x509_certificate(shown)
            .public_key()
            .public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        )
    except (ssl.SSLError, ValueError) as why:
        sock.close()
        raise ConnectionError(f"the TLS handshake with {whom} failed: {why}") from why
    except BaseException:
        sock.close()
        raise
    bound = Bound(hashlib.sha256(spki).digest(), key, whom)
    return Sealed(tls, incoming, outgoing, sock, bound)


def _shaken(
    tls: ssl.SSLObject,
    incoming: ssl.MemoryBIO,
    outgoing: ssl.MemoryBIO,
    sock: socket.socket,
    whom: str,
) -> bytes:
    """Carries a handshake's records each way until it is over.

    Returns:
      The DER of the certificate the serving half showed.

    Raises:
      ssl.SSLError: If OpenSSL refuses the other side, or is refused by it.
      ConnectionError: If the other side closes during the handshake, agrees on another
        protocol than ``hmz-anchor``, or shows no certificate.
    """
    while True:
        try:
            tls.do_handshake()
            break
        except ssl.SSLWantReadError:
            if out := outgoing.read():
                sock.sendall(out)
            arrived = sock.recv(_CHUNK)
            if not arrived:
                raise ConnectionError(
                    f"{whom} closed the connection during the TLS handshake"
                ) from None
            incoming.write(arrived)
    if out := outgoing.read():
        sock.sendall(out)
    if tls.selected_alpn_protocol() != ALPN:
        raise ConnectionError(f"{whom} does not speak {ALPN}")
    shown = tls.getpeercert(binary_form=True)
    if shown is None:
        raise ConnectionError(f"{whom} showed no certificate")
    return shown
