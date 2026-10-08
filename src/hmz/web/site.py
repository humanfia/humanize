"""The web interface's server: what a browser on this machine is answered by.

It listens on this machine's loopback alone and answers only a browser that came in through the
address `hmz web` printed: that address carries a key, which the browser is handed back as a
cookie, and every question about the runs must carry it. A loopback port is open to every
account on a machine, where the socket the runs are held behind is not; the key is what keeps
the runs this account's. A page from anywhere else cannot write either, since a write must say
it comes from this server's own page, and a name that is not this machine's is refused outright
whatever port it arrived through -- which is what lets the port be forwarded.
"""

from __future__ import annotations

import contextlib
import hashlib
import http.cookies
import json
import re
import secrets
import shutil
import sys
import threading
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import TYPE_CHECKING, Any, ClassVar, cast

from . import accounts, fallbacks, flows, held, runs, runtimes, settings
from .routing import Asked, Download, Refusal, Route, Stream

if TYPE_CHECKING:
    from pathlib import Path

    from .held import Held
    from .runs import Runs

__all__ = ["Site"]

#: Every route the interface answers, which is the whole of what it answers.
ROUTES: tuple[Route, ...] = (
    *held.ROUTES,
    *runs.ROUTES,
    *flows.ROUTES,
    *settings.ROUTES,
    *accounts.ROUTES,
    *fallbacks.ROUTES,
    *runtimes.ROUTES,
)

#: The names this machine answers to from a browser on it, whatever the port.
_HERE = frozenset({"127.0.0.1", "localhost", "[::1]"})

#: The most a write may send.
_LARGEST = 1 << 20

#: What each kind of file the page is made of is served as.
_KINDS = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
}

#: What a page of the interface may load and run: its own files and nothing else.
_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

#: A file the page is made of, by the name it is asked for under.
_FILE = re.compile(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.[a-z0-9]+")


class Site(ThreadingHTTPServer):
    """The server, holding what its routes are answered from.

    Args:
      port: The port to listen on, or 0 for any free one.
      hmz: humanize, for the workspace the runs are of.
      held: The runs held for that workspace, as this interface follows them.
      runs: The runs written down there.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, *, hmz: Any, held: Held, runs: Runs) -> None:
        super().__init__(("127.0.0.1", port), _Handler)
        self.hmz = hmz
        self.held = held
        self.runs = runs
        #: Set as the server stops, which is what ends every stream it is sending.
        self.going = threading.Event()
        self._key = secrets.token_urlsafe(32)

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


class _Handler(BaseHTTPRequestHandler):
    """One connection from a browser."""

    protocol_version = "HTTP/1.1"
    #: What every answer says about itself, whatever it is.
    _HEADERS: ClassVar[dict[str, str]] = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
    }

    @property
    def site(self) -> Site:
        """The server this connection came to, which holds what it is answered from."""
        return cast("Site", self.server)

    def do_GET(self) -> None:
        self._answers("GET")

    def do_POST(self) -> None:
        self._answers("POST")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Says nothing of a request that went as it should: failures say themselves."""

    def _answers(self, method: str) -> None:
        url = urllib.parse.urlsplit(self.path)
        try:
            self._routes(method, url.path, dict(urllib.parse.parse_qsl(url.query)))
        except Refusal as why:
            self._json({"error": str(why)}, why.status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _routes(self, method: str, path: str, query: dict[str, str]) -> None:
        """Answers one request: the API, the key a browser comes in with, or a file."""
        if not self._here():
            raise Refusal(
                "Open the address hmz web printed, on the machine it runs on.", 403
            )
        if path.startswith("/api/"):
            self._api(method, path, query)
        elif method != "GET":
            raise Refusal("Only the page's own files are here.", 405)
        elif path == "/" and "key" in query:
            self._signs_in(query["key"])
        else:
            self._file(path)

    def _here(self) -> bool:
        """Whether the browser named this machine, which a page elsewhere cannot make it do."""
        named = self.headers.get("Host", "")
        name = named.rpartition(":")[0] if named.rstrip("]").count(":") else named
        if named.startswith("[") and "]" in named:
            name = named[: named.index("]") + 1]
        return name.lower() in _HERE

    def _signed_in(self) -> bool:
        """Whether the browser carries the key the address handed it."""
        jar = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        held = jar.get(self.site.cookie)
        return held is not None and self.site.lets_in(held.value)

    def _signs_in(self, key: str) -> None:
        """Hands a browser that came in with the key a cookie carrying it, and the page."""
        if not self.site.lets_in(key):
            raise Refusal(
                "That key is not this server's: open the address hmz web printed.", 403
            )
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{self.site.cookie}={key}; HttpOnly; SameSite=Strict; Path=/",
        )
        self._ends(0)

    def _api(self, method: str, path: str, query: dict[str, str]) -> None:
        if not self._signed_in():
            raise Refusal(
                "Open the address hmz web printed to let this browser in.", 401
            )
        body: dict[str, Any] = {}
        if method == "POST":
            body = self._body()
        for route in ROUTES:
            matched = route.match(method, path)
            if matched is None:
                continue
            asked = Asked(self.site, matched, query, body)
            try:
                answer = route.answers(asked)
            except Refusal:
                raise
            except Exception as why:
                traceback.print_exc(file=sys.stderr)
                raise Refusal(f"Something went wrong here: {why}", 500) from why
            if isinstance(answer, Stream):
                self._streams(answer, query)
            elif isinstance(answer, Download):
                self._downloads(answer)
            else:
                self._json(answer)
            return
        known = any(
            route.match(other, path) is not None
            for route in ROUTES
            for other in ("GET", "POST")
        )
        raise Refusal("There is nothing here by that name.", 405 if known else 404)

    def _body(self) -> dict[str, Any]:
        """What a write sent, which must come from this server's own page and be JSON."""
        origin = self.headers.get("Origin", "")
        if origin != f"http://{self.headers.get('Host', '')}":
            raise Refusal("Use this server's own page to make this request.", 403)
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise Refusal("Send JSON.", 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as why:
            raise Refusal("Say how long what is sent is.", 411) from why
        if length > _LARGEST:
            raise Refusal("That is more than a request here may send.", 413)
        try:
            said = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as why:
            raise Refusal("Send JSON.", 400) from why
        if not isinstance(said, dict):
            raise Refusal("Send a JSON object.", 400)
        return dict(said)  # pyright: ignore[reportUnknownArgumentType]

    def _json(self, answer: Any, status: int = 200) -> None:
        body = json.dumps(
            answer, ensure_ascii=False, separators=(",", ":"), default=str
        )
        self._sends(body.encode(), "application/json; charset=utf-8", status)

    def _file(self, path: str) -> None:
        """One of the files the page is made of."""
        name = "index.html" if path == "/" else path.lstrip("/")
        if not _FILE.fullmatch(name):
            raise Refusal("There is nothing here by that name.", 404)
        held = resources.files("hmz.web").joinpath("static", *name.split("/"))
        kind = _KINDS.get(f".{name.rpartition('.')[2]}")
        if kind is None or not held.is_file():
            raise Refusal("There is nothing here by that name.", 404)
        self._sends(held.read_bytes(), kind, 200, page=name.endswith(".html"))

    def _sends(
        self, body: bytes, kind: str, status: int, *, page: bool = False
    ) -> None:
        """An answer, which a browser that has it already is told it has."""
        tag = f'W/"{hashlib.sha256(body).hexdigest()[:16]}"'
        if status == HTTPStatus.OK and self.headers.get("If-None-Match") == tag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", tag)
            self._ends(0)
            return
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", tag)
        if page:
            self.send_header("Content-Security-Policy", _POLICY)
        self._ends(len(body))
        self.wfile.write(body)

    def _ends(self, length: int) -> None:
        """Ends the headers of an answer `length` bytes long."""
        for name, value in self._HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(length))
        self.end_headers()

    def _downloads(self, answer: Download) -> None:
        try:
            size = answer.path.stat().st_size
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", answer.kind)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{urllib.parse.quote(answer.name)}",
            )
            self.send_header("Cache-Control", "no-store")
            self._ends(size)
            with answer.path.open("rb") as held:
                shutil.copyfileobj(held, self.wfile)
        finally:
            if answer.gone:
                _removes(answer.path)

    def _streams(self, answer: Stream, query: dict[str, str]) -> None:
        """Server-sent events, for as long as the browser listens and the server is up."""
        last = self.headers.get("Last-Event-ID") or query.get("last", "")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for name, value in self._HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        # Without a length the stream ends where the connection does.
        self.close_connection = True
        self.wfile.write(b"retry: 2000\n\n")
        self.wfile.flush()
        for said in answer.events(last, self.site.going):
            if said is None:
                self.wfile.write(b": quiet\n\n")
            else:
                ident, event, data = said
                lines = [f"id: {ident}"] if ident else []
                lines += [
                    f"event: {event}",
                    f"data: {json.dumps(data, default=str)}",
                    "",
                    "",
                ]
                self.wfile.write("\n".join(lines).encode())
            self.wfile.flush()


def _removes(path: Path) -> None:
    """Removes a file an answer made for itself, and the directory made to hold it."""
    with contextlib.suppress(OSError):
        path.unlink()
        path.parent.rmdir()
