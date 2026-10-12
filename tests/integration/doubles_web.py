"""What the web interface's integration tests share: the interface served, and a browser.

The interface is served over runs held in the test's own process, as `hmz web` serves it where
runs are not held apart, and answers on a thread of its own until the test is done. A browser
is a client speaking HTTP to it from this machine, one connection a request -- let in with the
key the address carries, or not -- and the stream of a run is read as a browser reads it, an
event at a time. A page is the page itself, drawn by a real browser opened on the address --
headless Chromium, or WebKit as the desktop app's window draws it, as Playwright drives them --
in which anything the page throws or logs as an error fails the test.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.web import listening

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from playwright.sync_api import Page

    from hmz.web.site import Site

#: How long anything here waits for the interface before failing the test.
PATIENCE = 30.0

#: The engines a page is drawn by: Chromium's, and WebKit's, which the macOS app's window is.
ENGINES = ("chromium", "webkit")

# Where Playwright keeps its browsers is under the home of whoever installed them, and a test
# gives the stand-in a home of its own: the browsers are pinned to the real one before it does.
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(
        Path.home() / "Library" / "Caches" / "ms-playwright"
        if sys.platform == "darwin"
        else Path.home() / ".cache" / "ms-playwright"
    ),
)

#: The home a browser runs in: the real one, since WebKit on macOS never loads a page from a
#: home made in a temporary directory.
_HOME = str(Path.home())


@contextlib.contextmanager
def served() -> Generator[Site]:
    """The web interface, answering on a thread of its own until the block ends."""
    with listening(apart=False) as site:
        threading.Thread(
            target=site.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
            name="hmz-web-test",
        ).start()
        try:
            yield site
        finally:
            site.shutdown()


@contextlib.contextmanager
def opened(
    site: Site,
    *,
    engine: str = "chromium",
    width: int = 1280,
    height: int = 860,
    dark: bool = False,
    user_agent: str | None = None,
    init: str | None = None,
) -> Generator[Page]:
    """The page, in a browser let in by the address, until the block ends.

    Args:
      site: The interface it is opened on.
      engine: One of `ENGINES`, the browser it is drawn by.
      width: How wide the window is: under 860, a phone's layout.
      height: How tall it is.
      dark: Whether the system the browser runs on asks for dark colours.
      user_agent: What the browser says it is, where not its own: as the macOS app's window.
      init: A script run in the page before any of its own.

    Yields:
      The page, drawn and with its sidebar up.

    Raises:
      AssertionError: If the page threw anything, or logged an error, while it was open.
    """
    from playwright.sync_api import expect, sync_playwright

    expect.set_options(timeout=PATIENCE * 1000)

    with sync_playwright() as driving:
        kind = driving.webkit if engine == "webkit" else driving.chromium
        browser = kind.launch(env={**os.environ, "HOME": _HOME})
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme="dark" if dark else "light",
                user_agent=user_agent,
            )
            context.set_default_timeout(PATIENCE * 1000)
            if init:
                context.add_init_script(init)
            page = context.new_page()
            failed: list[str] = []
            page.on("pageerror", lambda error: failed.append(str(error)))
            # A refusal is the server answering, which the page says where it happened; what
            # fails the test is the page throwing, or the server failing.
            page.on(
                "console",
                lambda said: (
                    failed.append(said.text)
                    if said.type == "error"
                    and not re.search(r"status of 4\d\d", said.text)
                    and "status of 502" not in said.text
                    else None
                ),
            )
            page.goto(site.address)
            page.wait_for_selector("[data-hmz=sidebar] .brand")
            _drawn(page)
            yield page
            assert not failed, f"the page went wrong: {failed}"
        finally:
            browser.close()


def go(page: Page, address: str) -> None:
    """Goes to another view of the page by its address, as a link does, once it is drawn.

    Until then, the view left still stands, and what is done on the page would be done to it.
    """
    page.evaluate(
        """(to) => new Promise((done) => {
            const was = location.hash
            addEventListener('hashchange', () => done(), { once: true })
            location.hash = to
            // The address it is on already, which goes nowhere.
            if (location.hash === was) done()
        })""",
        address,
    )
    _drawn(page)


def _drawn(page: Page) -> None:
    page.wait_for_selector("[data-hmz=page]:not([aria-busy])", state="attached")


@dataclass
class Answer:
    """What the interface answered one request with."""

    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        """The body, read as the JSON it is."""
        return json.loads(self.body)


@dataclass
class Browser:
    """A browser on this machine: what it names the server as, and the cookie it carries.

    Attributes:
      site: The interface it reaches.
      host: What its requests name the server as, which is the address's own by default.
      cookie: The cookie it carries, or "" before it is let in.
      at: Which loopback it connects to.
    """

    site: Site
    host: str = ""
    cookie: str = field(default="")
    at: str = "127.0.0.1"

    def signs_in(self) -> Answer:
        """Opens the address the interface printed, keeping the cookie it is handed."""
        query = urllib.parse.urlsplit(self.site.address).query
        answer = self.get(f"/?{query}")
        said = answer.headers.get("set-cookie", "")
        self.cookie = said.split(";", 1)[0]
        return answer

    def get(self, path: str, **headers: str) -> Answer:
        """Asks for one thing."""
        return self._asks("GET", path, None, headers)

    def post(self, path: str, body: Any = None, **headers: str) -> Answer:
        """Sends one thing, as the page's own script sends it unless `headers` say otherwise."""
        sent = {
            "Origin": f"http://{self._host()}",
            "Content-Type": "application/json",
        } | headers
        return self._asks("POST", path, json.dumps(body or {}).encode(), sent)

    def _host(self) -> str:
        return self.host or f"127.0.0.1:{self.site.port}"

    def _asks(
        self, method: str, path: str, body: bytes | None, headers: dict[str, str]
    ) -> Answer:
        connection = http.client.HTTPConnection(
            self.at, self.site.port, timeout=PATIENCE
        )
        try:
            sent = {"Host": self._host()} | (
                {"Cookie": self.cookie} if self.cookie else {}
            )
            connection.request(method, path, body=body, headers=sent | headers)
            answer = connection.getresponse()
            return Answer(
                answer.status,
                {name.lower(): value for name, value in answer.getheaders()},
                answer.read(),
            )
        finally:
            connection.close()

    @contextlib.contextmanager
    def follows(
        self, last: str = "", *, workspace: str = ""
    ) -> Generator[Callable[[], tuple[str, str, Any]]]:
        """Listens to the runs' stream, as the page does, from where it last heard.

        Args:
          last: The id of the last event it heard, or "" for the start.
          workspace: Whose runs, or "" for those of where the interface was started.

        Yields:
          What gives the next event: its id, what it is, and what it carries.
        """
        connection = http.client.HTTPConnection(
            self.at, self.site.port, timeout=PATIENCE
        )
        headers = {"Host": self._host(), "Cookie": self.cookie}
        if last:
            headers["Last-Event-ID"] = last
        query = (
            f"?{urllib.parse.urlencode({'workspace': workspace})}" if workspace else ""
        )
        connection.request("GET", f"/api/held/stream{query}", headers=headers)
        stream = connection.getresponse()

        def next_event() -> tuple[str, str, Any]:
            ident = event = ""
            data: list[str] = []
            while True:
                line = stream.readline().decode().rstrip("\n")
                if line.startswith("id: "):
                    ident = line[len("id: ") :]
                elif line.startswith("event: "):
                    event = line[len("event: ") :]
                elif line.startswith("data: "):
                    data.append(line[len("data: ") :])
                elif not line and event:
                    return ident, event, json.loads("\n".join(data))

        try:
            yield next_event
        finally:
            connection.close()


def until(
    next_event: Callable[[], tuple[str, str, Any]],
    wanted: Callable[[str, Any], bool],
    what: str,
) -> tuple[str, Any]:
    """Reads the stream until an event is the one wanted.

    Args:
      next_event: What gives the next event.
      wanted: Whether an event, by what it is and what it carries, is the one.
      what: What is waited for, for the failure.

    Returns:
      Its id, and what it carries.

    Raises:
      AssertionError: If none comes in time.
    """
    ending = time.monotonic() + PATIENCE
    while time.monotonic() < ending:
        ident, event, data = next_event()
        if wanted(event, data):
            return ident, data
    raise AssertionError(f"the stream never said {what}")
