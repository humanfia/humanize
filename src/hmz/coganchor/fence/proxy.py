"""The one way out of a fenced agent's network: a proxy that passes only named hosts.

A flow whose `online` scope is NONE still has to let its CLI reach the model API it runs on --
a CLI with no model is not a CLI running offline, it is a CLI not running. So the child is
walled in below the CLI (it may open a TCP connection to this proxy's port and to nothing
else, and may not resolve a name at all) and handed this proxy as `HTTPS_PROXY`. Every byte
that leaves the machine then leaves through here, and here is where the hostname is read.

Two kinds of request are served. `CONNECT host:port`, which is how every HTTPS client asks for
a tunnel, and an absolute-form `GET http://host/...`, which is how a plain HTTP one asks for a
page. Either is let through only when the host is on the allow-list and the port is one of the
allowed ports; anything else is answered `403` with the host named in the body, so that a turn
refused by the fence says so rather than failing as a network that happened to be down.

The name is resolved here rather than by the child, which cannot: that is what makes the
allow-list a list of names rather than of addresses, which change. An IP literal is refused
unless that literal is itself listed, because an address names no host and so matches none --
letting one through would be letting the child go anywhere it had the number for.

Each connection is held by one thread per direction, the number of connections held at once
is bounded, and a side that closes its writing half has that passed on rather than taken for
the end of the whole exchange.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import socket
import socketserver
import threading
import urllib.parse
from typing import TYPE_CHECKING, Any, Self

from hmz.coganchor.proto import CHUNK_SIZE

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType

__all__ = ["Proxy", "permits"]

log = logging.getLogger(__name__)

#: The ports a listed host may be reached on unless the proxy is told otherwise: HTTPS and HTTP.
PORTS = (443, 80)

#: How many connections are held at once before another is turned away.
LIMIT = 256

#: The most a request's head may be before it is refused, which is far more than any client
#: sends and far less than a head written to exhaust memory.
_HEAD = 64 * 1024

#: How long a client may take to finish asking, and an upstream to answer a connect, in seconds.
_WAIT = 30.0


def _host(name: str) -> str:
    """A hostname as it is compared: lower case, with no trailing dot and no brackets."""
    return name.strip().strip("[]").rstrip(".").lower()


def _address(name: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(name)
    except ValueError:
        return None


def _entry(written: str) -> tuple[str, int | None]:
    """An allow-list entry split into its host and the one port it names, if it names one."""
    written = written.strip()
    if written.startswith("["):  # `[v6]` or `[v6]:port`
        host, _, rest = written[1:].partition("]")
        port = rest.removeprefix(":")
    elif written.count(":") == 1:  # `host:port`; a bare IPv6 address has more than one
        host, _, port = written.partition(":")
    else:
        host, port = written, ""
    return _host(host), int(port) if port.isdigit() else None


def permits(
    allowed: Iterable[str], host: str, port: int, ports: Iterable[int] = PORTS
) -> bool:
    """Whether a host and port are ones the allow-list names.

    An entry is a hostname, matched exactly, or `*.suffix`, matching every name under that
    suffix but not the suffix itself -- `*.googleapis.com` passes `oauth2.googleapis.com` and
    not `googleapis.com`, which is its own host and has to be listed as one. Both sides are
    compared case-insensitively and without a trailing dot, since `API.Example.com.` is the
    same host as `api.example.com` to every resolver. An entry passes its host on any of
    `ports`; one written `host:port` passes it on that port and no other, which is how a
    gateway somebody runs on a port of its own is let through without every host being.

    An IP literal is compared as an address, and only against entries that are addresses too:
    a wildcard is a statement about names, and no name is an address.

    Args:
      allowed: The allow-list's entries.
      host: The host a request names, bracketed or not if it is an IPv6 literal.
      port: The port it names.
      ports: The ports an entry that names none passes.

    Returns:
      Whether the request may go there.
    """
    host = _host(host)
    if not host:
        return False
    address = _address(host)
    usual = frozenset(ports)
    for written in allowed:
        entry, only = _entry(written)
        if port != only and (only is not None or port not in usual):
            continue
        if address is not None:
            if _address(entry) == address:
                return True
        elif entry.startswith("*."):
            if host.endswith(entry[1:]) and len(host) > len(entry) - 1:
                return True
        elif entry == host:
            return True
    return False


class Proxy:
    """An HTTP proxy on loopback that passes a request only to an allowed host and port.

    Started on an ephemeral port on 127.0.0.1, which :attr:`port` then says; usable as a
    context manager, which starts it on the way in and stops it on the way out.

    Args:
      allowed: The hosts it passes, as :func:`permits` reads them.
      ports: The ports those hosts may be reached on, where an entry names none of its own.
      limit: How many connections it holds at once; one more is closed as it arrives.
    """

    def __init__(
        self,
        allowed: Iterable[str],
        *,
        ports: Iterable[int] = PORTS,
        limit: int = LIMIT,
    ) -> None:
        self.allowed = tuple(allowed)
        self.ports = frozenset(ports)
        self._server = _Server(self, limit)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The loopback port it listens on."""
        return self._server.server_address[1]

    def start(self) -> None:
        """Begin serving, in a thread of this process."""
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            args=(0.1,),  # how often it looks up to see whether it was stopped
            name="fence-proxy",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and cut every connection it still holds."""
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join()
            self._thread = None
        self._server.server_close()
        self._server.sever()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.stop()

    def passes(self, host: str, port: int) -> bool:
        """Whether a request for this host and port goes through."""
        return permits(self.allowed, host, port, self.ports)


#: What a server is handed per connection: a socket, or for a datagram server a packet and one.
type _Request = socket.socket | tuple[bytes, socket.socket]


class _Server(socketserver.ThreadingTCPServer):
    """The listening half: one thread per connection, and no more of them than `limit`."""

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True

    def __init__(self, proxy: Proxy, limit: int) -> None:
        self.proxy = proxy
        self._room = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._held: set[socket.socket] = set()
        super().__init__(("127.0.0.1", 0), _Handler)

    def process_request(self, request: _Request, client_address: Any) -> None:
        if not self._room.acquire(blocking=False):
            log.warning("fence proxy: too many connections; one turned away")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._room.release()
            raise

    def process_request_thread(self, request: _Request, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._room.release()

    def hold(self, sock: socket.socket) -> None:
        with self._lock:
            self._held.add(sock)

    def drop(self, sock: socket.socket) -> None:
        with self._lock:
            self._held.discard(sock)
        _close(sock)

    def sever(self) -> None:
        with self._lock:
            held, self._held = self._held, set()
        for sock in held:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            _close(sock)


class _Handler(socketserver.BaseRequestHandler):
    """One client connection: read what it asks for, decide, then relay or refuse."""

    server: _Server  # pyright: ignore[reportIncompatibleVariableOverride]
    request: socket.socket

    def handle(self) -> None:
        client = self.request
        self.server.hold(client)
        try:
            client.settimeout(_WAIT)
            try:
                head, rest = _read_head(client)
            except (OSError, ValueError):
                return
            try:
                method, target, version, fields = _parse(head)
            except ValueError as error:
                _answer(client, 400, "Bad Request", f"{error}\n")
                return
            self._serve(client, method, target, version, fields, rest)
        finally:
            self.server.drop(client)

    def _serve(
        self,
        client: socket.socket,
        method: str,
        target: str,
        version: str,
        fields: list[bytes],
        rest: bytes,
    ) -> None:
        try:
            host, port, path = _destination(method, target)
        except ValueError as error:
            _answer(client, 400, "Bad Request", f"{error}\n")
            return
        proxy = self.server.proxy
        if not proxy.passes(host, port):
            log.info("fence proxy: refused %s:%d", host, port)
            _answer(
                client,
                403,
                "Forbidden",
                f"hmz: {host}:{port} is not a host this run may reach\n",
            )
            return
        try:
            upstream = socket.create_connection((_host(host), port), timeout=_WAIT)
        except OSError as error:
            _answer(
                client,
                502,
                "Bad Gateway",
                f"hmz: could not reach {host}:{port}: {error}\n",
            )
            return
        self.server.hold(upstream)
        try:
            if method == "CONNECT":
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                first = rest
            else:
                first = _forwarded(method, path, version, fields) + rest
            if first:
                upstream.sendall(first)
            client.settimeout(None)
            upstream.settimeout(None)
            _relay(client, upstream)
        except OSError:
            pass
        finally:
            self.server.drop(upstream)


def _read_head(sock: socket.socket) -> tuple[bytes, bytes]:
    """Read up to the blank line ending a request's head.

    Returns:
      The head, without that blank line, and whatever the client sent after it.

    Raises:
      ValueError: If the connection ends first, or the head is longer than any real one.
    """
    data = b""
    while b"\r\n\r\n" not in data:
        if len(data) > _HEAD:
            raise ValueError("request head too long")
        chunk = sock.recv(CHUNK_SIZE)
        if not chunk:
            raise ValueError("connection closed mid-request")
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def _parse(head: bytes) -> tuple[str, str, str, list[bytes]]:
    """Split a request's head into its method, target, version and header lines."""
    line, *fields = head.split(b"\r\n")
    parts = line.decode("latin-1").split()
    if len(parts) != 3 or not parts[2].startswith("HTTP/"):  # noqa: PLR2004 -- method, target, version
        raise ValueError("malformed request line")
    method, target, version = parts
    return method.upper(), target, version, fields


def _destination(method: str, target: str) -> tuple[str, int, str]:
    """Where a request is for: its host, its port, and the path to ask that host for.

    Raises:
      ValueError: For a target a proxy cannot act on -- a `CONNECT` with no port, a request
        in origin form, or one for a scheme other than plain HTTP.
    """
    if method == "CONNECT":
        split = urllib.parse.urlsplit(f"//{target}")
        if not split.hostname or split.port is None:
            raise ValueError("CONNECT needs host:port")
        return split.hostname, split.port, ""
    split = urllib.parse.urlsplit(target)
    if split.scheme.lower() != "http" or not split.hostname:
        raise ValueError("only absolute http:// requests and CONNECT are proxied")
    path = split.path or "/"
    if split.query:
        path = f"{path}?{split.query}"
    return split.hostname, split.port or 80, path


#: Headers that describe the hop to this proxy rather than the request, and are not passed on.
_HOP = frozenset(
    {b"connection", b"keep-alive", b"proxy-connection", b"proxy-authorization"}
)


def _forwarded(method: str, path: str, version: str, fields: list[bytes]) -> bytes:
    """A plain HTTP request's head as the origin server is sent it.

    In origin form, and closed after one exchange: a kept-alive connection would carry the
    client's next request to this host whatever host that request named.
    """
    kept = [
        field for field in fields if field.split(b":", 1)[0].strip().lower() not in _HOP
    ]
    lines = [
        f"{method} {path} {version}".encode("latin-1"),
        *kept,
        b"Connection: close",
    ]
    return b"\r\n".join(lines) + b"\r\n\r\n"


def _answer(sock: socket.socket, code: int, reason: str, body: str) -> None:
    payload = body.encode()
    head = (
        f"HTTP/1.1 {code} {reason}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    with contextlib.suppress(OSError):
        sock.sendall(head + payload)


def _relay(client: socket.socket, upstream: socket.socket) -> None:
    """Carry bytes both ways until both sides have finished sending.

    One direction runs on a thread of its own, so neither can stall the other. A side that
    stops sending has its writing half shut on the other side, which is what a half-close is:
    the far end may still answer, and that answer still comes back.
    """
    back = threading.Thread(
        target=_pump, args=(upstream, client), name="fence-relay", daemon=True
    )
    back.start()
    _pump(client, upstream)
    back.join()


def _pump(source: socket.socket, sink: socket.socket) -> None:
    try:
        while data := source.recv(CHUNK_SIZE):
            sink.sendall(data)
    except OSError:
        # One side is gone; take the other down with it, so the opposite pump ends too.
        for sock in (source, sink):
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
        return
    with contextlib.suppress(OSError):
        sink.shutdown(socket.SHUT_WR)


def _close(sock: socket.socket) -> None:
    with contextlib.suppress(OSError):
        sock.close()
