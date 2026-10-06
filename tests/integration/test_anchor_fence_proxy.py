"""The fence's one way out: an HTTP proxy on loopback that passes only allowed hosts.

The proxy and an upstream on this machine, talking over real sockets. Whether the wall
around a fenced program lets it reach nothing but this proxy is the kernel's to enforce,
and a system test's to check.
"""

from __future__ import annotations

import contextlib
import socket
import socketserver
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.fence import Proxy

if TYPE_CHECKING:
    from collections.abc import Iterator


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
