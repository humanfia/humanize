"""The web interface's server: the page's files, `/here`, and the bridges `/rpc` and `/dial`.

It listens on this machine's loopback alone -- IPv4's and, where there is one, IPv6's, on one
port -- and admits only a browser that came in through the address `hmz web` printed: that
address carries a key, which the browser is handed back as a cookie, and `/here`, `/rpc` and
`/dial` are refused without it. A loopback port is open to every account on a machine, where the
daemon's socket is not; the key is what keeps the daemon this account's. The `Host` a request
names is not checked, so a port forwarded or proxied on to it from this machine, under any name,
is answered: what is asked is that the connection came from this machine, and the key. A page
from anywhere else cannot open a bridge either: the browser says where a request came from, and
only this server's own page is admitted -- `Sec-Fetch-Site: same-origin`, or, of a browser that
sends none, an `Origin` over `http` that is the `Host` asked (Section 4.4 of web.md). So a proxy
that serves the page over `https`, or that rewrites `Host`, has its `/rpc` and `/dial` refused
403 in a browser that sends no `Sec-Fetch-Site` with them.

The page's own files are served to anybody on this machine; everything else the page does, it
does over JSON-RPC to a daemon (`hmz.web.bridge`).
"""

from __future__ import annotations

import errno
import hashlib
import ipaddress
import json
import secrets
import socket
import socketserver
import string
import sys
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, ClassVar, cast

from .bridge import Dials

__all__ = ["Site"]

#: How many ports any would do for are tried before one free on both loopbacks is given up on.
_PORTS = 8

#: What binding IPv6's loopback fails with on a machine that has none.
_NO_IPV6 = frozenset({errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT})

#: What each kind of file the page is made of is served as.
_KINDS = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".json": "application/json",
}

#: What a page of the interface may load and run: its own files and nothing else, but that it
#: may reach the relay of any `webrtc:` route, whose host the server cannot know, that the
#: editor and the terminal in static/vendor may style what they draw from their own scripts, and
#: that it may frame its own `faces/frame.html`.
_POLICY = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self' ws: wss:; frame-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

#: The document a question's face runs in, inside a sandboxed frame of the page.
_FACE = "faces/frame.html"

#: What a face may load and run: its own inline code and styles, the page's files, and pictures
#: and fonts it carries itself; nothing it can reach anything with. Only the page may frame it.
_FACE_POLICY = (
    "default-src 'none'; script-src 'unsafe-inline' 'self'; "
    "style-src 'unsafe-inline' 'self'; img-src data: blob:; font-src data:; "
    "connect-src 'none'; frame-ancestors 'self'"
)

#: The files a face may import as modules from its opaque origin, which asks for them across
#: origins as `Origin: null`: libraries anybody on this machine is served anyway. No other
#: origin is let read them.
_SHARED = ("vendor/",)

#: What each part of the name of a file the page is made of is spelled with: words, never a dot,
#: so that no part is `..` and nothing hidden is named.
_SPELLED = frozenset(string.ascii_letters + string.digits + "_-")

#: What a file's kind is spelled with, after its one dot.
_KIND = frozenset(string.ascii_lowercase + string.digits)

#: The longest name a file the page is made of is asked for under.
_LONGEST = 200

#: What only an admitted browser is answered: everything but the page's own files.
_ADMITTED = frozenset({"/here", "/rpc", "/dial"})


class _Refusal(Exception):  # noqa: N818 -- what the browser is told, not what went wrong here
    """A request refused, with its status and the sentence it is refused with."""

    def __init__(self, sentence: str, status: int) -> None:
        super().__init__(sentence)
        self.status = status


class _Bound(ThreadingHTTPServer):
    """A server bound without asking the network what its loopback is called.

    `HTTPServer.server_bind` looks the address up by reverse DNS, for a name this interface
    never uses -- a lookup that can hang for half a minute where the resolver is slow.
    """

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class Site(_Bound):
    """The server.

    Listens on IPv4's loopback itself and on IPv6's beside it, on the same port, so that a
    browser reaching `localhost` by either is answered; a machine with no IPv6 is answered on
    IPv4's alone.

    Args:
      port: The port to listen on, or 0 for any free one on both.

    Raises:
      OSError: If the port cannot be listened on.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int) -> None:
        self._beside: _Beside | None = None
        #: Every `/dial` open, closed as the server closes.
        self.dials = Dials()
        for left in reversed(range(_PORTS)):
            super().__init__(("127.0.0.1", port), _Handler)
            try:
                self._beside = _beside(self)
                break
            except OSError:
                self.server_close()
                # A port any would do for, free on one loopback and taken on the other: the
                # next one picked may be free on both.
                if port or not left:
                    raise
        #: The directory the server started in, which `/here` answers (Section 4.6 of web.md).
        self.here = Path.cwd()
        self._key = secrets.token_urlsafe(32)

    @property
    def site(self) -> Site:
        """Itself: what a connection to either loopback is answered from."""
        return self

    @property
    def port(self) -> int:
        """The port it listens on."""
        return int(self.server_address[1])

    @property
    def address(self) -> str:
        """Where a browser on this machine reaches it, with the key that lets the browser in."""
        return f"http://127.0.0.1:{self.port}/?key={self._key}"

    @property
    def cookie(self) -> str:
        """The cookie a browser that came in through `address` carries: one per port."""
        return f"hmz-{self.port}"

    def lets_in(self, key: str) -> bool:
        """Whether a key is the one `address` carries."""
        return secrets.compare_digest(key.encode(), self._key.encode())

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        """Answers both loopbacks until `shutdown`: IPv6's on a thread of its own.

        However IPv4's ends -- `shutdown`, or an interrupt raised through it -- IPv6's is ended
        with it, before anything closes the socket that thread waits on.
        """
        if self._beside is None:
            super().serve_forever(poll_interval)
            return
        import threading

        threading.Thread(
            target=self._beside.serve_forever,
            args=(poll_interval,),
            daemon=True,
            name="hmz-web-ipv6",
        ).start()
        try:
            super().serve_forever(poll_interval)
        finally:
            self._beside.shutdown()

    def server_close(self) -> None:
        """Stops listening on both loopbacks, and closes every `/dial` open."""
        super().server_close()
        self.dials.close()
        if self._beside is not None:
            self._beside.server_close()


class _Beside(_Bound):
    """IPv6's loopback, answered as the site it stands beside answers IPv4's.

    Args:
      site: The site, listening on IPv4's loopback on the port this one takes too.
    """

    address_family = socket.AF_INET6
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, site: Site) -> None:
        super().__init__(("::1", site.port), _Handler)
        self.site = site


def _beside(site: Site) -> _Beside | None:
    """IPv6's loopback on the port the site took on IPv4's, or None on a machine without one.

    Raises:
      OSError: If the port is taken there.
    """
    if not socket.has_ipv6:
        return None
    try:
        return _Beside(site)
    except OSError as why:
        if why.errno in _NO_IPV6:
            return None
        raise


class _Handler(BaseHTTPRequestHandler):
    """One connection from a browser."""

    protocol_version = "HTTP/1.1"
    #: How long a connection may say nothing before it is let go (Section 4.3.5 of web.md); a
    #: WebSocket is let be quiet for as long as it likes once it is open.
    timeout = 60
    #: What every answer says about itself, whatever it is (Section 4.5.1 of web.md).
    HEADERS: ClassVar[dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }

    @property
    def site(self) -> Site:
        """The site this connection came to, on either loopback."""
        return cast("Site | _Beside", self.server).site

    def do_GET(self) -> None:
        self._answers("GET")

    def do_HEAD(self) -> None:
        self._answers("HEAD")

    def do_POST(self) -> None:
        self._answers("POST")

    def do_PUT(self) -> None:
        self._answers("PUT")

    def do_PATCH(self) -> None:
        self._answers("PATCH")

    def do_DELETE(self) -> None:
        self._answers("DELETE")

    def do_OPTIONS(self) -> None:
        self._answers("OPTIONS")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Says nothing of a request that went as it should: failures say themselves."""

    def _answers(self, method: str) -> None:
        url = urllib.parse.urlsplit(self.path)
        try:
            self._routes(method, url.path, dict(urllib.parse.parse_qsl(url.query)))
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except _Refusal as why:
            self._refuses(str(why), why.status)
        except Exception as why:  # noqa: BLE001 -- said in one sentence, its traceback logged
            traceback.print_exc(file=sys.stderr)
            self._refuses(f"Something went wrong here: {why}", 500)

    def _refuses(self, sentence: str, status: int) -> None:
        """A refusal (Section 4.5.2 of web.md); what the request sent is not read as the next."""
        self.close_connection = True
        self._json({"error": sentence}, status)

    def _routes(self, method: str, path: str, query: dict[str, str]) -> None:
        """Answers one request in the order Section 4.4 of web.md checks it."""
        if not ipaddress.ip_address(str(self.client_address[0])).is_loopback:
            raise _Refusal(
                "Open the address hmz web printed, on the machine it runs on.", 403
            )
        if method == "GET" and path == "/" and "key" in query:
            self._signs_in(query["key"])
            return
        if path in _ADMITTED:
            self._admits()
        if method != "GET":
            raise _Refusal("Only the page's own files are here.", 405)
        if path not in _ADMITTED:
            self._file(path)
        elif path == "/here":
            self._sends(
                json.dumps({"here": str(self.site.here)}).encode(),
                "application/json; charset=utf-8",
                cache="no-store",
            )
        else:
            self._bridges(path, query)

    def _admits(self) -> None:
        """Refuses a browser not let in, or a request not made by this server's own page."""
        if not self._signed_in():
            raise _Refusal(
                "Open the address hmz web printed to let this browser in.", 401
            )
        if not self._from_its_page():
            raise _Refusal("Use this server's own page to make this request.", 403)

    def _signed_in(self) -> bool:
        """Whether the browser carries the key the address handed it.

        Read off the header by name rather than through `http.cookies`, which refuses a whole
        header for one cookie of another site's it cannot parse: cookies are shared by every
        port of a host.
        """
        for one in self.headers.get("Cookie", "").split(";"):
            name, _, value = one.strip().partition("=")
            if name == self.site.cookie and self.site.lets_in(value):
                return True
        return False

    def _from_its_page(self) -> bool:
        """Whether the browser says this server's own page made a request.

        A browser that says where a request came from is taken at its word; one that does not
        is asked only that an `Origin` it names is the `Host` it asked, over `http`.
        """
        fetched = self.headers.get("Sec-Fetch-Site")
        if fetched is not None:
            return fetched == "same-origin"
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        said = urllib.parse.urlsplit(origin)
        return said.scheme == "http" and said.netloc == self.headers.get("Host", "")

    def _signs_in(self, key: str) -> None:
        """Hands a browser that came in with the key a cookie carrying it, and the page."""
        if not self.site.lets_in(key):
            raise _Refusal(
                "That key is not this server's: open the address hmz web printed.", 403
            )
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{self.site.cookie}={key}; HttpOnly; SameSite=Strict; Path=/",
        )
        self._ends(0)

    def _bridges(self, path: str, query: dict[str, str]) -> None:
        """`/rpc` or `/dial`, as a WebSocket."""
        if self.headers.get("Upgrade", "").lower() != "websocket":
            raise _Refusal("Open this as a WebSocket.", 400)
        from .bridge import WebSocket, dials, rpc

        opened = WebSocket.accepted(self, self.HEADERS)
        if opened is None:
            raise _Refusal("Open this as a WebSocket.", 400)
        self.close_connection = True
        if path == "/rpc":
            rpc(opened)
        else:
            dials(opened, query.get("route", ""), query.get("id", ""), self.site.dials)

    def _file(self, path: str) -> None:
        """One of the files the page is made of (Section 4.5.3 and 4.5.4 of web.md)."""
        name = "index.html" if path == "/" else path.lstrip("/")
        if not _is_file(name):
            raise _Refusal("There is nothing here by that name.", 404)
        held = resources.files("hmz.web").joinpath("static", *name.split("/"))
        kind = _KINDS.get(f".{name.rpartition('.')[2]}")
        if kind is None or not held.is_file():
            raise _Refusal("There is nothing here by that name.", 404)
        policy = None
        if name == _FACE:
            policy = _FACE_POLICY
        elif name.endswith(".html"):
            policy = _POLICY
        self._sends(
            held.read_bytes(),
            kind,
            policy=policy,
            framed=name == _FACE,
            shared=name.startswith(_SHARED),
        )

    def _json(self, answer: Any, status: int) -> None:
        body = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
        self._sends(body.encode(), "application/json; charset=utf-8", status)

    def _sends(
        self,
        body: bytes,
        kind: str,
        status: int = 200,
        *,
        policy: str | None = None,
        framed: bool = False,
        shared: bool = False,
        cache: str = "no-cache",
    ) -> None:
        """An answer, which a browser that has it already is told it has.

        Args:
          body: What is answered.
          kind: Its media type.
          status: Its status.
          policy: The Content-Security-Policy it is served with, if any.
          framed: Whether the page may frame it (`faces/frame.html`), which no other may be.
          shared: Whether an opaque origin may read it: a face importing one of the page's
            libraries.
          cache: Its Cache-Control.
        """
        tag = f'W/"{hashlib.sha256(body).hexdigest()[:16]}"'
        null = shared and self.headers.get("Origin") == "null"
        if status == HTTPStatus.OK and self.headers.get("If-None-Match") == tag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", tag)
            if null:
                self.send_header("Access-Control-Allow-Origin", "null")
            self._ends(0, framed=framed)
            return
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", cache)
        self.send_header("ETag", tag)
        if policy is not None:
            self.send_header("Content-Security-Policy", policy)
        if null:
            self.send_header("Access-Control-Allow-Origin", "null")
        self._ends(len(body), framed=framed)
        self.wfile.write(body)

    def _ends(self, length: int, *, framed: bool = False) -> None:
        """Ends the headers of an answer `length` bytes long, which only `framed` may be framed."""
        for name, value in self.HEADERS.items():
            if framed and name == "X-Frame-Options":
                value = "SAMEORIGIN"  # noqa: PLW2901 -- the one file the page frames
            self.send_header(name, value)
        self.send_header("Content-Length", str(length))
        self.end_headers()


def _is_file(name: str) -> bool:
    """Whether a name could be one of the page's own files: parts of words, then a kind.

    Read a character at a time rather than matched, so that how long a hostile name takes to
    refuse is how long it is.
    """
    *folders, last = name.split("/")
    stem, dot, kind = last.rpartition(".")
    return (
        len(name) <= _LONGEST
        and bool(dot)
        and bool(kind)
        and set(kind) <= _KIND
        and all(part and set(part) <= _SPELLED for part in (*folders, stem))
    )
