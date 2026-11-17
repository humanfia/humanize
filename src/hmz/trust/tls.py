"""Mutual TLS 1.3 between two device certificates, over any pipe at all.

A carrier is a pipe of bytes each way -- a socket, the standard streams of a process, a
WebSocket, a relay's splice -- and the standard library's TLS runs over sockets alone. So
OpenSSL is run here over memory: what it wants to send is read out of it and written to the
pipe, and what arrives on the pipe is written into it. Each side shows its own device
certificate and takes the other's on two conditions only: that it is signed by the key it
holds, and, for the client, that the key is the daemon id it pinned. No authority, name or
validity period is asked about, and nothing is sent until both hold: a client whose daemon
answers with another key closes before a single byte of its own crosses.

The daemon admits every device that holds a key; which of them is paired is the daemon's to
say, by the fingerprint :attr:`Secured.peer` reads off the certificate.
"""

from __future__ import annotations

import contextlib
import socket
import threading
from typing import TYPE_CHECKING

from OpenSSL import SSL

from hmz.trust.identity import fingerprint, self_signed
from hmz.trust.pins import matches

if TYPE_CHECKING:
    from collections.abc import Callable

    from cryptography import x509
    from OpenSSL.crypto import X509

    from hmz.rpc.pipe import Pipe
    from hmz.trust.identity import Identity

__all__ = ["ALPN", "ImpostorError", "RefusedError", "Secured", "answer", "dial"]

#: The one application protocol either side offers, and the one it closes a handshake without.
ALPN = b"hmz"

#: How much is read off the pipe at a time: a TLS record and then some.
_CHUNK = 1 << 16


class RefusedError(ConnectionError):
    """The handshake did not end in a session: the pipe is closed, and nothing was sent."""


class ImpostorError(RefusedError):
    """The daemon answered with a key other than the one the client pinned."""


class Secured:
    """A :class:`hmz.rpc.Pipe` whose bytes cross inside TLS: itself one, of the same three calls.

    One thread may read while another writes, which is how a session is carried: a reader
    waiting on what the other side says next, and whoever has something to say. Two
    writers are written one after the other, whole.

    Attributes:
      certificate: The other side's device certificate.
      peer: Its SPKI fingerprint: the daemon id to a client, the device fingerprint to the
        daemon.
    """

    def __init__(self, connection: SSL.Connection, pipe: Pipe) -> None:
        """Takes a connection whose handshake is over, and the pipe it was carried on.

        Args:
          connection: The TLS connection, run over memory.
          pipe: The carrier.

        Raises:
          RefusedError: If the other side presented no certificate.
        """
        certificate = connection.get_peer_certificate(as_cryptography=True)
        if certificate is None:
            raise RefusedError("the other side presented no certificate")
        self.certificate: x509.Certificate = certificate
        self.peer: str = fingerprint(certificate)
        self._connection = connection
        self._pipe = pipe
        #: Held for each call into OpenSSL, which is not to be entered by two threads.
        self._tls = threading.Lock()
        #: Held from taking what OpenSSL wrote until the pipe has it, so that records cross
        #: in the order they were made.
        self._out = threading.Lock()
        #: What OpenSSL wrote that is not on the pipe yet, oldest first. Under `_tls`.
        self._owed = bytearray()
        self._closed = False

    def recv(self, bufsize: int, /) -> bytes:
        """What the other side sent next, at most `bufsize` bytes of it.

        Returns:
          At least one byte, or `b""` once the other side has closed -- with a close_notify
          or without one, since a frame cut short is told apart one layer up.

        Raises:
          ConnectionError: If what arrived is not TLS from the other side.
        """
        while True:
            got = None
            with self._tls:
                try:
                    got = self._connection.recv(bufsize)
                except SSL.WantReadError:
                    pass
                except SSL.ZeroReturnError:
                    return b""
                except SSL.Error as why:
                    raise ConnectionError(f"the session broke: {why}") from why
            # What reading made OpenSSL say back -- a key update answered -- sent now.
            self._kicked()
            if got is not None:
                return got
            arrived = self._pipe.recv(_CHUNK)
            if not arrived:
                return b""
            with self._tls:
                self._connection.bio_write(arrived)

    def sendall(self, data: bytes, /) -> None:
        """Writes all of `data` to the other side.

        Raises:
          ConnectionError: If the session is broken.
          OSError: If the pipe cannot be written.
        """
        with self._out:
            with self._tls:
                try:
                    self._connection.sendall(data)
                except SSL.Error as why:
                    raise ConnectionError(f"the session broke: {why}") from why
            self._pumped()
        self._kicked()

    def close(self) -> None:
        """Says close_notify where it can without waiting, and closes the pipe.

        A writer stuck on a pipe nobody reads is not waited for: the pipe is closed under it,
        which is what makes it give up.
        """
        if self._closed:
            return
        self._closed = True
        if self._out.acquire(blocking=False):
            try:
                with self._tls, contextlib.suppress(SSL.Error):
                    self._connection.shutdown()
                with contextlib.suppress(OSError):
                    self._pumped()
            finally:
                self._out.release()
        if isinstance(self._pipe, socket.socket):
            # Closing a socket wakes no thread waiting on it, on Linux; shutting it does.
            with contextlib.suppress(OSError):
                self._pipe.shutdown(socket.SHUT_RDWR)
        self._pipe.close()

    def _pumped(self) -> None:
        """Writes to the pipe whatever OpenSSL has to send, in order. Called holding `_out`."""
        while True:
            with self._tls:
                self._owed += _drained(self._connection)
                out = bytes(self._owed)
                self._owed.clear()
            if not out:
                return
            self._pipe.sendall(out)

    def _kicked(self) -> None:
        """Sends what OpenSSL has to send, unless another thread is sending, which then does.

        Never waits on the pipe: a reader that waited for a writer stuck on a pipe the other
        side is not reading -- because its own reader is waiting the same way -- is two sides
        waiting on each other. Whoever is sending looks again once it lets go, so nothing
        put aside meanwhile is left behind.
        """
        while self._out.acquire(blocking=False):
            try:
                self._pumped()
            finally:
                self._out.release()
            with self._tls:
                self._owed += _drained(self._connection)
                if not self._owed:
                    return


def dial(pipe: Pipe, identity: Identity, pinned: str, name: str) -> Secured:
    """Opens TLS as the client, holding the daemon to the id it pinned.

    Args:
      pipe: The carrier, open.
      identity: This device's.
      pinned: The daemon id the client pins.
      name: What the client calls the daemon, or the route where it is given no name, for
        the refusal.

    Returns:
      The session, before any byte of it was sent.

    Raises:
      ImpostorError: If the daemon's key is not `pinned`.
      RefusedError: If nothing is pinned, which no key matches -- which a client refuses
        before it opens the carrier, as Section 3.5.6 of wire.md has it -- or the handshake
        fails otherwise.
    """
    if not pinned:
        pipe.close()
        raise RefusedError(f"{name} needs the id of the daemon it reaches.")
    wrong: list[bool] = []

    def pins(certificate: x509.Certificate) -> bool:
        if matches(fingerprint(certificate), pinned):
            return True
        wrong.append(True)
        return False

    connection = SSL.Connection(_context(identity, pins, serving=False))
    connection.set_connect_state()
    try:
        return _shaken(connection, pipe)
    except RefusedError as why:
        if wrong:
            raise ImpostorError(
                f"{name} is not the daemon it was paired with."
            ) from why
        raise


def answer(pipe: Pipe, identity: Identity) -> Secured:
    """Answers TLS as the daemon, admitting any device that holds the key it shows.

    Args:
      pipe: The carrier, open.
      identity: This machine's.

    Returns:
      The session; whether its :attr:`Secured.peer` is paired is the daemon's to say.

    Raises:
      RefusedError: If the handshake fails.
    """
    connection = SSL.Connection(_context(identity, lambda _: True, serving=True))
    connection.set_accept_state()
    return _shaken(connection, pipe)


def _context(
    identity: Identity, admits: Callable[[x509.Certificate], bool], *, serving: bool
) -> SSL.Context:
    """What either side's TLS is: 1.3 alone, its own certificate, ALPN `hmz`.

    Args:
      identity: This device's.
      admits: What else the other side's certificate is held to, beyond its own signature.
      serving: Whether this is the daemon, which asks for the client's certificate.

    Returns:
      The context.
    """
    context = SSL.Context(SSL.TLS_METHOD)
    context.set_min_proto_version(SSL.TLS1_3_VERSION)
    context.set_max_proto_version(SSL.TLS1_3_VERSION)
    context.use_certificate(identity.certificate)
    context.use_privatekey(identity.key)

    def verify(
        _: SSL.Connection, shown: X509, _error: int, depth: int, _ok: int
    ) -> bool:
        # Every error OpenSSL finds -- self-signed, expired, no chain -- is one this does
        # not ask about; only the certificate the other side is, at depth 0, is checked.
        if depth:
            return True
        certificate = shown.to_cryptography()
        return self_signed(certificate) and admits(certificate)

    context.set_verify(
        SSL.VERIFY_PEER | (SSL.VERIFY_FAIL_IF_NO_PEER_CERT if serving else 0), verify
    )
    if serving:
        context.set_alpn_select_callback(
            lambda _, offered: ALPN if ALPN in offered else SSL.NO_OVERLAPPING_PROTOCOLS
        )
    else:
        context.set_alpn_protos([ALPN])
    return context


def _shaken(connection: SSL.Connection, pipe: Pipe) -> Secured:
    """Runs a handshake over a pipe to its end, closing the pipe where it fails.

    Args:
      connection: The TLS connection, in its connect or accept state.
      pipe: The carrier.

    Returns:
      The session.

    Raises:
      RefusedError: If the handshake fails, the other side closes during it, or it agrees on
        another application protocol than `hmz`.
    """
    try:
        _handshake(connection, pipe)
    except SSL.Error as why:
        # The alert that says why, where OpenSSL wrote one.
        with contextlib.suppress(OSError):
            _sent(connection, pipe)
        pipe.close()
        raise RefusedError(f"the TLS handshake failed: {why}") from why
    except BaseException:
        pipe.close()
        raise
    if connection.get_alpn_proto_negotiated() != ALPN:
        pipe.close()
        raise RefusedError("the other side does not speak hmz")
    try:
        return Secured(connection, pipe)
    except RefusedError:
        pipe.close()
        raise


def _handshake(connection: SSL.Connection, pipe: Pipe) -> None:
    """Carries a handshake's records each way until OpenSSL says it is over.

    Raises:
      SSL.Error: If OpenSSL refuses the other side, or is refused by it.
      RefusedError: If the other side closes before the handshake is over.
    """
    while True:
        try:
            connection.do_handshake()
        except SSL.WantReadError:
            _sent(connection, pipe)
            arrived = pipe.recv(_CHUNK)
            if not arrived:
                raise RefusedError(
                    "the other side closed during the handshake"
                ) from None
            connection.bio_write(arrived)
        else:
            _sent(connection, pipe)
            return


def _sent(connection: SSL.Connection, pipe: Pipe) -> None:
    """Writes to the pipe whatever OpenSSL has to send, where it has anything."""
    out = _drained(connection)
    if out:
        pipe.sendall(out)


def _drained(connection: SSL.Connection) -> bytes:
    """Everything OpenSSL has written to send, taken out of it."""
    out = bytearray()
    while True:
        try:
            out += connection.bio_read(_CHUNK)
        except SSL.WantReadError:
            return bytes(out)
