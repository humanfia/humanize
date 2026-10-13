"""The web interface's server: what a browser on this machine is answered by.

It listens on this machine's loopback alone -- IPv4's and, where there is one, IPv6's, on one
port -- and answers only a browser that came in through the address `hmz web` printed: that
address carries a key, which the browser is handed back as a cookie, and every question about
the runs must carry it. A loopback port is open to every account on a machine, where the socket
the runs are held behind is not; the key is what keeps the runs this account's. What name the
browser reached it by is not asked, so a port forwarded or proxied on to it is answered: what is
asked is that the connection came from this machine, and the key. A page elsewhere that points a
name of its own at the loopback is answered as a stranger, since a browser hands a name the
cookies of that name alone. A page from anywhere else cannot ask anything either: the browser
says where a request came from, and only this server's own page, or an address typed or opened,
is answered -- a page served from another port of this machine is the same site to a cookie, and
not to this. A write must also say it comes from this server's own page.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import socket
import socketserver
import string
import sys
import tempfile
import threading
import traceback
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from . import (
    accounts,
    daemons,
    fallbacks,
    flows,
    held,
    notifications,
    paths,
    places,
    proxy,
    remote,
    runs,
    runtimes,
    settings,
    verses,
)
from .routing import Asked, Download, Made, Refusal, Route, Stream

if TYPE_CHECKING:
    from collections.abc import Generator

    from hmz.runtime.watching.notices import Notices

    from .notifications import Notifications
    from .places import Places
    from .remote import Remotes
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
    *daemons.ROUTES,
    *paths.ROUTES,
    *places.ROUTES,
    *verses.ROUTES,
    *remote.ROUTES,
    *notifications.ROUTES,
)

#: What a daemon is called in the paths a page asks another machine's daemon by.
_DAEMON = frozenset(string.ascii_letters + string.digits + "._-")

#: How many ports any would do for are tried before one free on both loopbacks is given up on.
_PORTS = 8

#: What binding IPv6's loopback fails with on a machine that has none.
_NO_IPV6 = frozenset({errno.EADDRNOTAVAIL, errno.EAFNOSUPPORT})

#: The most a write may send as JSON.
_LARGEST = 1 << 20

#: The most a write may send as a file.
_LARGEST_FILE = 2 << 30

#: How much of a file sent is read at a time.
_CHUNK = 1 << 20

#: The header a file sent says its name in.
_FILENAME = "X-Hmz-Filename"

#: The longest name a file sent may have, in bytes, as a file system takes one.
_NAMED = 255

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

#: What each part of the name of a file the page is made of is spelled with: words, never a dot,
#: so that no part is `..` and nothing hidden is named.
_SPELLED = frozenset(string.ascii_letters + string.digits + "_-")

#: What a file's kind is spelled with, after its one dot.
_KIND = frozenset(string.ascii_lowercase + string.digits)

#: The longest name a file the page is made of is asked for under.
_LONGEST = 200


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
    """The server, holding what its routes are answered from.

    Listens on IPv4's loopback itself and on IPv6's beside it, on the same port, so that a
    browser reaching `localhost` by either is answered; a machine with no IPv6 is answered on
    IPv4's alone.

    Args:
      port: The port to listen on, or 0 for any free one on both.
      places: Every workspace on this machine, and the runs held for each as this follows them.
      runs: The runs written down, of every workspace.
      notices: What happened to the runs worth telling somebody about.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self, port: int, *, places: Places, runs: Runs, notices: Notices
    ) -> None:
        self._beside: _Beside | None = None
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
        self.places = places
        self.hmz: Any = places.hmz
        self.runs = runs
        self.notices = notices
        #: The daemons on other machines, as each is reached, once `listening` has them.
        self.remotes: Remotes | None = None
        #: Every daemon's notices, as this interface tells them, once it is listening.
        self.notifications: Notifications | None = None
        #: Set as the server stops, which is what ends every stream it is sending.
        self.going = threading.Event()
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
        """Answers both loopbacks until `shutdown`: IPv6's on a thread of its own."""
        if self._beside is not None:
            threading.Thread(
                target=self._beside.serve_forever,
                args=(poll_interval,),
                daemon=True,
                name="hmz-web-ipv6",
            ).start()
        super().serve_forever(poll_interval)

    def shutdown(self) -> None:
        """Stops answering both loopbacks."""
        super().shutdown()
        if self._beside is not None:
            self._beside.shutdown()

    def server_close(self) -> None:
        """Stops listening on both loopbacks."""
        super().server_close()
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
    #: How long a connection may say nothing before it is let go, so that one left open is not
    #: a thread held for good. A stream writes more often than this.
    timeout = 60
    #: What every answer says about itself, whatever it is.
    _HEADERS: ClassVar[dict[str, str]] = {
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

    def do_POST(self) -> None:
        self._answers("POST")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Says nothing of a request that went as it should: failures say themselves."""

    def _answers(self, method: str) -> None:
        url = urllib.parse.urlsplit(self.path)
        try:
            self._routes(method, url.path, dict(urllib.parse.parse_qsl(url.query)))
        except Refusal as why:
            # What a refused write sent may not have been read: it is no next request.
            if method == "POST":
                self.close_connection = True
            self._json({"error": str(why)} | why.said, why.status)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _routes(self, method: str, path: str, query: dict[str, str]) -> None:
        """Answers one request: the API, the key a browser comes in with, or a file."""
        if not self._here():
            raise Refusal(
                "Open the address hmz web printed, on the machine it runs on.", 403
            )
        # This machine's own daemon, named as a page names every daemon it asks.
        if path.startswith("/d/local/api/"):
            path = path.removeprefix("/d/local")
        if path.startswith("/api/"):
            self._api(method, path, query)
        elif path.startswith("/d/"):
            self._daemon(method, path, query)
        elif method != "GET":
            raise Refusal("Only the page's own files are here.", 405)
        elif path == "/" and "key" in query:
            self._signs_in(query["key"])
        else:
            self._file(path)

    def _here(self) -> bool:
        """Whether the connection came from this machine, by whatever name it was reached.

        Whatever forwards or proxies a port on to this one does it from here as well.
        """
        return ipaddress.ip_address(str(self.client_address[0])).is_loopback

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

    def _asked_here(self) -> bool:
        """Whether a request came from this server's own page, or from an address opened.

        A browser says where a request came from: `same-origin` from this server's page,
        `none` from an address typed or opened. One that does not say is not a browser of
        today: it is let in by the key alone, unless it names a page that is not this one.
        """
        fetched = self.headers.get("Sec-Fetch-Site")
        if fetched is not None:
            return fetched in ("same-origin", "none")
        return "Origin" not in self.headers or self._from_its_page()

    def _from_its_page(self) -> bool:
        """Whether the browser says this server's own page made a request.

        As the page was reached, through a proxy too: a browser that says where a request came
        from is taken at its word, and one that does not is asked for an `Origin` naming the
        `Host` it asked, by either scheme, since a proxy may have added one.
        """
        fetched = self.headers.get("Sec-Fetch-Site")
        if fetched is not None:
            return fetched == "same-origin"
        origin = urllib.parse.urlsplit(self.headers.get("Origin", ""))
        return origin.scheme in ("http", "https") and origin.netloc == self.headers.get(
            "Host", ""
        )

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

    def _admits(self) -> None:
        """Refuses a request to the API from a browser not let in, or from another page."""
        if not self._signed_in():
            raise Refusal(
                "Open the address hmz web printed to let this browser in.", 401
            )
        if not self._asked_here():
            raise Refusal("Use this server's own page to make this request.", 403)

    def _daemon(self, method: str, path: str, query: dict[str, str]) -> None:
        """The API of a daemon by name, `/d/<name>/api/...`.

        This machine's own for `local`, and otherwise asked of the interface on the machine
        it names.
        """
        name, _, rest = path.removeprefix("/d/").partition("/")
        rest = f"/{rest}"
        if not name or not set(name) <= _DAEMON or not rest.startswith("/api/"):
            raise Refusal("There is nothing here by that name.", 404)
        if name == "local":
            self._api(method, rest, query)
            return
        self._admits()
        if method == "POST" and not self._from_its_page():
            raise Refusal("Use this server's own page to make this request.", 403)
        if self.site.remotes is None:
            raise Refusal("There is no daemon by that name.", 404)
        port, said = self.site.remotes.asks(name)
        asked = urllib.parse.urlsplit(self.path).query
        proxy.forwards(self, port, said, method, rest + (f"?{asked}" if asked else ""))

    def _api(self, method: str, path: str, query: dict[str, str]) -> None:
        self._admits()
        for route in ROUTES:
            matched = route.match(method, path)
            if matched is None:
                continue
            try:
                with self._sent(method, route) as (body, file):
                    answer = route.answers(Asked(self.site, matched, query, body, file))
            except Refusal:
                raise
            except Exception as why:
                traceback.print_exc(file=sys.stderr)
                raise Refusal(f"Something went wrong here: {why}", 500) from why
            if isinstance(answer, Stream):
                self._streams(answer, query)
            elif isinstance(answer, Download):
                self._downloads(answer)
            elif isinstance(answer, Made):
                self._json(answer.answer, HTTPStatus.CREATED)
            else:
                self._json(answer)
            return
        known = any(
            route.match(other, path) is not None
            for route in ROUTES
            for other in ("GET", "POST")
        )
        raise Refusal("There is nothing here by that name.", 405 if known else 404)

    @contextlib.contextmanager
    def _sent(
        self, method: str, route: Route
    ) -> Generator[tuple[dict[str, Any], Path | None]]:
        """What a write sent, which must come from this server's own page: JSON, or a file.

        A file is taken only by a route that takes one, sent as the kind it takes or as bytes,
        and is kept until the route has answered.

        Yields:
          The JSON sent, and the file, or None.
        """
        if method != "POST":
            yield {}, None
            return
        if not self._from_its_page():
            raise Refusal("Use this server's own page to make this request.", 403)
        kind = self.headers.get("Content-Type", "").partition(";")[0].strip()
        if route.file and kind in (route.file, "application/octet-stream"):
            from hmz import machine

            scratch = Path(tempfile.mkdtemp(dir=machine()))
            try:
                yield {}, self._file_sent(scratch)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
            return
        if kind != "application/json":
            raise Refusal("Send JSON.", 415)
        yield self._body(), None

    def _length(self, largest: int) -> int:
        """How long what a write sent says it is, no longer than `largest`."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as why:
            raise Refusal("Say how long what is sent is.", 411) from why
        if length < 0:
            raise Refusal("Say how long what is sent is.", 411)
        if length > largest:
            raise Refusal("That is more than a request here may send.", 413)
        return length

    def _body(self) -> dict[str, Any]:
        """What a write sent as JSON."""
        length = self._length(_LARGEST)
        try:
            said = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, RecursionError) as why:
            raise Refusal("Send JSON.", 400) from why
        if not isinstance(said, dict):
            raise Refusal("Send a JSON object.", 400)
        return dict(said)  # pyright: ignore[reportUnknownArgumentType]

    def _file_sent(self, scratch: Path) -> Path:
        """A file a write sent, written into `scratch` under the name it was sent as.

        The name is said, percent-encoded, in `X-Hmz-Filename`.
        """
        name = os.path.basename(urllib.parse.unquote(self.headers.get(_FILENAME, "")))  # noqa: PTH119
        # Its last part, and nothing that would put it anywhere but straight in `scratch`.
        at = os.path.normpath(os.path.join(scratch, name))  # noqa: PTH118
        if (
            not at.startswith(f"{scratch}{os.sep}")
            or os.sep in at.removeprefix(f"{scratch}{os.sep}")
            or "\0" in at
            or len(name.encode()) > _NAMED
        ):
            raise Refusal(f"Say the file's name in {_FILENAME}.", 400)
        left = self._length(_LARGEST_FILE)
        with open(at, "wb") as written:  # noqa: PTH123
            while left:
                read = self.rfile.read(min(left, _CHUNK))
                if not read:
                    raise Refusal("The file sent was cut short.", 400)
                written.write(read)
                left -= len(read)
        return Path(at)

    def _json(self, answer: Any, status: int = 200) -> None:
        body = json.dumps(
            answer, ensure_ascii=False, separators=(",", ":"), default=str
        )
        self._sends(body.encode(), "application/json; charset=utf-8", status)

    def _file(self, path: str) -> None:
        """One of the files the page is made of."""
        name = "index.html" if path == "/" else path.lstrip("/")
        if not _is_file(name):
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
        # Where it starts from is settled before the browser hears it is answered: what comes
        # once it has heard so is never before the start.
        events = answer.events(last, self.site.going)
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
        for said in events:
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


def _removes(path: Path) -> None:
    """Removes a file an answer made for itself, and the directory made to hold it."""
    with contextlib.suppress(OSError):
        path.unlink()
        path.parent.rmdir()
