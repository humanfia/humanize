"""The interface's notifications: this machine's notices and an SSH daemon's, told as one.

The interface is served in this process; this machine's notices are a stand-in told what to
say, and an SSH daemon is a stand-in for its interface, reached on a port of this machine as
a forwarded one is: it lets in what comes with its key, says where its notices stand, and
streams what it says after that.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, cast

import yaml

from hmz import home
from tests.integration.doubles_web import PATIENCE, Browser, served

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from hmz.web.site import Site


class _Notices:
    """This machine's notices: what hears them, told each as it is said."""

    def __init__(self) -> None:
        self.hearing: list[Callable[[Any], object]] = []

    def heard(self, callback: Callable[[Any], object]) -> None:
        self.hearing.append(callback)

    def since(self, after: str) -> list[dict[str, Any]]:
        return []

    def says(self, notice: dict[str, Any]) -> None:
        for one in self.hearing:
            one(notice)


class _Daemon(ThreadingHTTPServer):
    """An SSH daemon's interface, as its forwarded port reaches it."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Answers)
        #: What its stream says next, a notice at a time.
        self.saying: list[dict[str, Any]] = []
        #: The `Last-Event-ID` each stream was asked from.
        self.asked: list[str] = []


class _Answers(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def _daemon(self) -> _Daemon:
        return cast("_Daemon", self.server)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:
        if self.path == "/?key=sesame":
            self.send_response(303)
            self.send_header("Set-Cookie", "hmz-4242=sesame; HttpOnly; Path=/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if "hmz-4242=sesame" not in self.headers.get("Cookie", ""):
            self.send_error(401)
            return
        if self.path == "/api/notices":
            body = json.dumps({"notices": [], "last": "5"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._daemon.asked.append(self.headers.get("Last-Event-ID", ""))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.close_connection = True
        # Until the interface following it lets it go.
        with contextlib.suppress(OSError):
            self._says()

    def _says(self) -> None:
        while True:
            while self._daemon.saying:
                notice = self._daemon.saying.pop(0)
                said = (
                    f"id: {notice['id']}\nevent: notice\ndata: {json.dumps(notice)}\n\n"
                )
                self.wfile.write(said.encode())
            self.wfile.write(b": quiet\n\n")
            self.wfile.flush()
            time.sleep(0.05)


class _Remotes:
    """The SSH daemons reached: `gpu`, up on the stand-in's port."""

    def __init__(self, daemon: _Daemon) -> None:
        self._daemon = daemon

    def state(self, name: str) -> dict[str, Any]:
        return {"state": "up" if name == "gpu" else "idle", "detail": "", "version": ""}

    def reached(self, name: str) -> tuple[int, str]:
        return int(self._daemon.server_address[1]), "sesame"


@contextlib.contextmanager
def _told() -> Generator[tuple[Site, Browser, _Notices, _Daemon]]:
    home().mkdir(parents=True, exist_ok=True)
    (home() / "settings.yaml").write_text(
        yaml.safe_dump({"daemons": [{"name": "gpu", "host": "gpu.example"}]})
    )
    daemon = _Daemon()
    threading.Thread(target=daemon.serve_forever, daemon=True).start()
    try:
        with served() as site:
            notices = _Notices()
            site.notices = notices  # pyright: ignore[reportAttributeAccessIssue]
            site.remotes = _Remotes(daemon)
            browser = Browser(site)
            browser.signs_in()
            _waits(lambda: bool(notices.hearing) and bool(daemon.asked), "followed")
            yield site, browser, notices, daemon
    finally:
        daemon.shutdown()
        daemon.server_close()


def _waits(done: Callable[[], bool], what: str) -> None:
    ending = time.monotonic() + PATIENCE
    while not done():
        assert time.monotonic() < ending, f"never {what}"
        time.sleep(0.05)


def _items(browser: Browser) -> list[dict[str, Any]]:
    answer = browser.get("/api/notifications")
    assert answer.status == 200, answer.body
    return answer.json()["items"]


def _notice(kind: str, epic: str, ident: str = "1") -> dict[str, Any]:
    return {"id": ident, "kind": kind, "workspace": "/w", "epic": epic, "text": ""}


def test_every_daemons_notices_are_told_as_one_by_who_said_them() -> None:
    with _told() as (_, browser, notices, daemon):
        notices.says(_notice("done", "here"))
        daemon.saying.append(_notice("asked", "there", "6"))
        _waits(lambda: len(_items(browser)) == 2, "told both")

        items = _items(browser)

        assert [(one["daemon"], one["epic"], one["kind"]) for one in items] == [
            ("gpu", "there", "asked"),
            ("local", "here", "done"),
        ]
        # What the daemon said before it was first reached is not told.
        assert daemon.asked == ["5"]


def test_a_kind_turned_off_is_never_told_and_written_down_as_off() -> None:
    with _told() as (_, browser, notices, _):
        answer = browser.post(
            "/api/notifications/settings", {"kinds": {"listening": False}}
        )

        assert answer.status == 200, answer.body
        assert answer.json() == browser.get("/api/notifications/settings").json()
        written = yaml.safe_load((home() / "settings.yaml").read_text())
        assert written["notifications"]["kinds"]["listening"] is False
        assert written["notifications"]["system"] is True
        assert written["daemons"] == [{"name": "gpu", "host": "gpu.example"}]
        notices.says(_notice("listening", "chat"))
        notices.says(_notice("failed", "broke"))
        assert [one["kind"] for one in _items(browser)] == ["failed"]


def test_settings_that_are_not_notifications_are_refused() -> None:
    with _told() as (_, browser, _, _):
        for wrong in (
            {"kinds": {"x": True}},
            {"kinds": {"done": "no"}},
            {"kinds": False},
            {"system": "yes"},
            {"sound": True},
        ):
            answer = browser.post("/api/notifications/settings", wrong)
            assert answer.status == 400, wrong
        assert "notifications" not in (home() / "settings.yaml").read_text()


def test_notifications_are_read_and_cleared() -> None:
    with _told() as (_, browser, notices, _):
        notices.says(_notice("done", "a"))
        notices.says(_notice("stopped", "b"))
        first = _items(browser)[-1]["id"]

        answer = browser.post("/api/notifications/read", {"ids": [first]})
        assert answer.json()["unread"] == 1
        assert (
            browser.post("/api/notifications/read", {"all": True}).json()["unread"] == 0
        )
        assert browser.post("/api/notifications/clear").json() == {
            "items": [],
            "unread": 0,
        }


def test_the_stream_tells_each_as_it_comes_and_takes_up_where_it_was_left() -> None:
    with _told() as (site, browser, notices, _):
        notices.says(_notice("done", "before"))
        with _following(site, browser, "") as next_event:
            notices.says(_notice("asked", "after"))
            ident, event, data = next_event()
        assert (event, data["epic"], data["daemon"], data["read"]) == (
            "notification",
            "after",
            "local",
            False,
        )
        with _following(site, browser, "1") as next_event:
            assert next_event()[0] == ident


@contextlib.contextmanager
def _following(
    site: Site, browser: Browser, last: str
) -> Generator[Callable[[], tuple[str, str, Any]]]:
    connection = http.client.HTTPConnection("127.0.0.1", site.port, timeout=PATIENCE)
    headers = {"Cookie": browser.cookie} | ({"Last-Event-ID": last} if last else {})
    connection.request("GET", "/api/notifications/stream", headers=headers)
    stream = connection.getresponse()
    assert stream.status == 200

    def next_event() -> tuple[str, str, Any]:
        ident = event = data = ""
        while True:
            line = stream.readline().decode().rstrip("\n")
            if line.startswith("id: "):
                ident = line[4:]
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
            elif not line and event:
                return ident, event, json.loads(data)

    try:
        yield next_event
    finally:
        connection.close()
