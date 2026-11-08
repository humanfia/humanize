"""The fence's one way out: an HTTP proxy on loopback that passes only allowed hosts.

The proxy and an upstream on this machine -- and a proxy upstream of it, where this process
names one -- talking over real sockets. Whether the wall
around a fenced program lets it reach nothing but this proxy is the kernel's to enforce,
and a system test's to check.
"""

from __future__ import annotations

import base64
import contextlib
import socket
import socketserver
import threading
from typing import TYPE_CHECKING, ClassVar

import pytest

from hmz.coganchor.fence import Proxy

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _no_proxy_of_our_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """This process named no proxy upstream, whatever the machine running the tests does."""
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


class _Upstream(socketserver.BaseRequestHandler):
    """Answers a `GET` with its request line and `Host`; echoes anything else until EOF."""

    request: socket.socket

    def handle(self) -> None:
        data = self.request.recv(4096)
        if data.startswith(b"GET "):
            while b"\r\n\r\n" not in data and (more := self.request.recv(4096)):
                data += more
            line, *fields = data.split(b"\r\n\r\n")[0].split(b"\r\n")
            host = next(f for f in fields if f.lower().startswith(b"host:"))
            body = line + b"\n" + host
            self.request.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
            )
            return
        while data:
            self.request.sendall(data)
            data = self.request.recv(4096)
        with contextlib.suppress(OSError):
            self.request.sendall(b"<eof>")


@pytest.fixture
def upstream() -> Iterator[int]:
    """The port of an upstream on loopback."""
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Upstream)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _ask(proxy: Proxy, head: str) -> tuple[socket.socket, bytes]:
    """Sends a request head to the proxy, and reads the head of its answer."""
    sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
    sock.sendall(head.encode())
    answer = b""
    while b"\r\n\r\n" not in answer and (chunk := sock.recv(4096)):
        answer += chunk
    return sock, answer


def _status(proxy: Proxy, head: str) -> bytes:
    sock, answer = _ask(proxy, head)
    sock.close()
    return answer[:12]


def _drain(sock: socket.socket) -> bytes:
    data = b""
    while chunk := sock.recv(4096):
        data += chunk
    return data


def test_an_allowed_tunnel_carries_bytes_both_ways_and_a_half_close(
    upstream: int,
) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 200")
        sock.sendall(b"ping")
        assert sock.recv(4096) == b"ping"
        sock.shutdown(socket.SHUT_WR)
        assert _drain(sock) == b"<eof>"
        sock.close()


def test_a_host_not_listed_is_refused_naming_it(upstream: int) -> None:
    with Proxy(["api.anthropic.com"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        answer += _drain(sock)
        sock.close()

    assert answer.startswith(b"HTTP/1.1 403")
    assert f"localhost:{upstream}".encode() in answer


def test_a_port_passes_only_where_the_list_or_the_ports_say(upstream: int) -> None:
    with Proxy(["localhost"]) as proxy:
        assert _status(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n") == (
            b"HTTP/1.1 403"
        )
    with Proxy([f"localhost:{upstream}"]) as proxy:
        assert _status(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n") == (
            b"HTTP/1.1 200"
        )


def test_an_address_passes_only_where_it_is_listed_as_one(upstream: int) -> None:
    connect = f"CONNECT 127.0.0.1:{upstream} HTTP/1.1\r\n\r\n"
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        assert _status(proxy, connect) == b"HTTP/1.1 403"
    with Proxy(["127.0.0.1"], ports=[upstream]) as proxy:
        assert _status(proxy, connect) == b"HTTP/1.1 200"


def test_plain_http_is_forwarded_in_origin_form(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        sock.sendall(
            f"GET http://localhost:{upstream}/models?x=1 HTTP/1.1\r\n"
            f"Host: localhost:{upstream}\r\n\r\n".encode()
        )
        answer = _drain(sock)
        sock.close()

    assert answer.startswith(b"HTTP/1.1 200")
    assert answer.split(b"\r\n\r\n", 1)[1] == (
        f"GET /models?x=1 HTTP/1.1\nHost: localhost:{upstream}".encode()
    )


def test_what_is_not_a_proxy_request_is_bad(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        for head in ("GET / HTTP/1.1\r\n\r\n", "CONNECT localhost HTTP/1.1\r\n\r\n"):
            assert _status(proxy, head) == b"HTTP/1.1 400"


def test_stopping_cuts_every_tunnel_it_holds(upstream: int) -> None:
    proxy = Proxy(["localhost"], ports=[upstream])
    proxy.start()
    sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 200")

    proxy.stop()

    assert _drain(sock) == b""
    sock.close()


# --- a proxy upstream of this one --------------------------------------------------------------


class _Chained(socketserver.BaseRequestHandler):
    """A proxy upstream: records each head it is sent, tunnels as an echo, refuses `nope`."""

    request: socket.socket
    heads: ClassVar[list[bytes]] = []

    def handle(self) -> None:
        data = b""
        while b"\r\n\r\n" not in data and (more := self.request.recv(4096)):
            data += more
        head, _, rest = data.partition(b"\r\n\r\n")
        type(self).heads.append(head)
        if head.startswith(b"CONNECT nope"):
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        elif head.startswith(b"CONNECT "):
            self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.request.sendall(rest)
            while more := self.request.recv(4096):
                self.request.sendall(more)
        else:
            line = head.split(b"\r\n", 1)[0]
            self.request.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(line), line)
            )


@pytest.fixture
def chained(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[bytes]]:
    """A proxy upstream named as this process's own, and the heads it is sent."""
    _Chained.heads = []
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Chained)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    named = f"http://me:s%40cret@127.0.0.1:{server.server_address[1]}"
    monkeypatch.setenv("HTTPS_PROXY", named)
    monkeypatch.setenv("HTTP_PROXY", named)
    try:
        yield _Chained.heads
    finally:
        server.shutdown()
        server.server_close()


_SIGNED = b"Proxy-Authorization: Basic " + base64.b64encode(b"me:s@cret")


def test_an_allowed_tunnel_is_asked_of_the_proxy_upstream(chained: list[bytes]) -> None:
    with Proxy(["api.example.com"]) as proxy:
        sock, answer = _ask(proxy, "CONNECT api.example.com:443 HTTP/1.1\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 200")
        sock.sendall(b"ping")
        assert sock.recv(4096) == b"ping"
        sock.close()

    (head,) = chained
    assert head.split(b"\r\n") == [
        b"CONNECT api.example.com:443 HTTP/1.1",
        b"Host: api.example.com:443",
        _SIGNED,
    ]


def test_plain_http_goes_through_a_tunnel_the_proxy_upstream_never_reads_in(
    chained: list[bytes],
) -> None:
    # A second request written after the first would be read by a proxy handed requests as
    # one more, for whatever host it named; inside a tunnel it is the allowed host's.
    with Proxy(["api.example.com"]) as proxy:
        sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        sock.sendall(
            b"GET http://api.example.com/models HTTP/1.1\r\n"
            b"Host: api.example.com\r\nProxy-Authorization: Basic theirs\r\n\r\n"
            b"GET http://elsewhere.example/ HTTP/1.1\r\nHost: elsewhere.example\r\n\r\n"
        )
        sock.shutdown(socket.SHUT_WR)
        answer = _drain(sock)
        sock.close()

    assert answer.startswith(b"GET /models HTTP/1.1\r\n")
    assert b"theirs" not in answer
    (head,) = chained
    assert head.split(b"\r\n") == [
        b"CONNECT api.example.com:80 HTTP/1.1",
        b"Host: api.example.com:80",
        _SIGNED,
    ]


def test_what_is_refused_never_reaches_the_proxy_upstream(chained: list[bytes]) -> None:
    with Proxy(["api.example.com"]) as proxy:
        assert _status(proxy, "CONNECT other.example.com:443 HTTP/1.1\r\n\r\n") == (
            b"HTTP/1.1 403"
        )
    assert chained == []


def test_a_tunnel_the_proxy_upstream_refuses_is_a_bad_gateway(
    chained: list[bytes],
) -> None:
    with Proxy(["nope"]) as proxy:
        sock, answer = _ask(proxy, "CONNECT nope:443 HTTP/1.1\r\n\r\n")
        answer += _drain(sock)
        sock.close()

    assert answer.startswith(b"HTTP/1.1 502")
    assert b"403 Forbidden" in answer
    assert len(chained) == 1


def test_a_host_no_proxy_names_goes_around_the_proxy_upstream(
    monkeypatch: pytest.MonkeyPatch, chained: list[bytes], upstream: int
) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost")
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 200")
        sock.sendall(b"ping")
        assert sock.recv(4096) == b"ping"
        sock.close()
    assert chained == []
