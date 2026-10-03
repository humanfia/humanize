"""The fence's proxy, driven over loopback against an upstream this file writes.

The upstream is one small server: it answers a request that starts with an HTTP verb with the
request line and `Host` it was sent, and echoes anything else back, closing its writing half
once the client has closed its own. That is enough to see a tunnel carry bytes both ways and
survive a half-close, and to see what a plain HTTP request looks like once forwarded.
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
    request: socket.socket

    def handle(self) -> None:
        data = b""
        while chunk := self.request.recv(4096):
            data += chunk
            if data.startswith(b"GET ") and b"\r\n\r\n" in data:
                line, *fields = data.split(b"\r\n\r\n")[0].split(b"\r\n")
                host = next(f for f in fields if f.lower().startswith(b"host:"))
                closes = any(f.lower() == b"connection: close" for f in fields)
                body = line + b"\n" + host + b"\n" + (b"closes" if closes else b"keeps")
                self.request.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body) + body
                )
                return
            if not data.startswith(b"GET"):
                self.request.sendall(chunk)
        with contextlib.suppress(OSError):  # the proxy may have cut this already
            self.request.sendall(b"<eof>")
            self.request.shutdown(socket.SHUT_WR)


@pytest.fixture
def upstream() -> Iterator[int]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Upstream)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _ask(proxy: Proxy, head: str) -> tuple[socket.socket, bytes]:
    sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
    sock.sendall(head.encode())
    answer = b""
    while b"\r\n\r\n" not in answer:
        chunk = sock.recv(4096)
        if not chunk:
            break
        answer += chunk
    return sock, answer


def _drain(sock: socket.socket) -> bytes:
    data = b""
    while chunk := sock.recv(4096):
        data += chunk
    return data


def test_an_allowed_connect_carries_bytes_both_ways_and_a_half_close(
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


def test_a_host_not_listed_is_refused_with_403_naming_it(upstream: int) -> None:
    with Proxy(["api.anthropic.com"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        answer += _drain(sock)
        sock.close()
    assert answer.startswith(b"HTTP/1.1 403")
    assert f"localhost:{upstream}".encode() in answer


def test_a_listed_host_on_a_port_not_listed_is_refused(upstream: int) -> None:
    with Proxy(["localhost"]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        sock.close()
    assert answer.startswith(b"HTTP/1.1 403")


def test_an_entry_naming_a_port_passes_that_port_on_its_own(upstream: int) -> None:
    with Proxy([f"localhost:{upstream}"]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        sock.close()
    assert answer.startswith(b"HTTP/1.1 200")


def test_plain_http_is_forwarded_in_origin_form_and_closed(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        sock = socket.create_connection(("127.0.0.1", proxy.port), timeout=10)
        sock.sendall(
            f"GET http://localhost:{upstream}/models?x=1 HTTP/1.1\r\n"
            f"Host: localhost:{upstream}\r\nProxy-Connection: keep-alive\r\n\r\n".encode()
        )
        answer = _drain(sock)
        sock.close()
    assert answer.startswith(b"HTTP/1.1 200")
    body = answer.split(b"\r\n\r\n", 1)[1]
    assert body == (
        b"GET /models?x=1 HTTP/1.1\n"
        + f"Host: localhost:{upstream}".encode()
        + b"\ncloses"
    )


def test_a_wildcard_entry_passes_names_under_it(upstream: int) -> None:
    try:
        socket.getaddrinfo("api.localhost", upstream)
    except OSError:
        pytest.skip("this resolver does not answer for names under .localhost")
    with Proxy(["*.localhost"], ports=[upstream]) as proxy:
        sock, answer = _ask(
            proxy, f"CONNECT API.localhost.:{upstream} HTTP/1.1\r\n\r\n"
        )
        sock.close()
        assert answer.startswith(b"HTTP/1.1 200")
        sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        sock.close()
        assert answer.startswith(b"HTTP/1.1 403")


def test_an_ip_literal_is_refused_unless_it_is_listed(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT 127.0.0.1:{upstream} HTTP/1.1\r\n\r\n")
        sock.close()
        assert answer.startswith(b"HTTP/1.1 403")
        sock, answer = _ask(proxy, f"GET http://127.0.0.1:{upstream}/ HTTP/1.1\r\n\r\n")
        sock.close()
        assert answer.startswith(b"HTTP/1.1 403")
    with Proxy(["127.0.0.1"], ports=[upstream]) as proxy:
        sock, answer = _ask(proxy, f"CONNECT 127.0.0.1:{upstream} HTTP/1.1\r\n\r\n")
        sock.close()
        assert answer.startswith(b"HTTP/1.1 200")


def test_what_is_not_a_proxy_request_is_refused_as_bad(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream]) as proxy:
        for head in ("GET / HTTP/1.1\r\n\r\n", "CONNECT localhost HTTP/1.1\r\n\r\n"):
            sock, answer = _ask(proxy, head)
            sock.close()
            assert answer.startswith(b"HTTP/1.1 400")


def test_stopping_cuts_the_tunnels_it_holds(upstream: int) -> None:
    proxy = Proxy(["localhost"], ports=[upstream])
    proxy.start()
    sock, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
    assert answer.startswith(b"HTTP/1.1 200")
    proxy.stop()
    assert _drain(sock) == b""
    sock.close()


def test_connections_past_the_limit_are_turned_away(upstream: int) -> None:
    with Proxy(["localhost"], ports=[upstream], limit=1) as proxy:
        held, answer = _ask(proxy, f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 200")
        # Closed unanswered: an end of file where the request had not yet arrived when it
        # was, a reset where it had -- which is what a Mac's kernel says of unread bytes.
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=10) as extra:
            extra.sendall(f"CONNECT localhost:{upstream} HTTP/1.1\r\n\r\n".encode())
            try:
                answer = extra.recv(4096)
            except ConnectionResetError:
                answer = b""
        assert answer == b""
        held.close()
