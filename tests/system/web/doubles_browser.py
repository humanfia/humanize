"""The web interface's page, drawn by a real browser opened on its address.

Headless Chromium, or WebKit as the desktop app's window draws it, as Playwright drives them;
anything the page throws or logs as an error fails the test. Fetch both with
`uv run playwright install chromium webkit` first.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from tests.integration.doubles_web import PATIENCE

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from playwright.sync_api import Page

    from hmz.web.site import Site

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
def opened(
    site: Site,
    *,
    engine: str = "chromium",
    width: int = 1280,
    height: int = 860,
    dark: bool = False,
    user_agent: str | None = None,
    init: str | None = None,
    routed: Callable[[Page], object] | None = None,
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
      routed: Told the page before it is opened, to answer some of its requests itself.

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
            if routed:
                routed(page)
            failed: list[str] = []
            # Bar the browser's word that a resize took more than one frame to settle: a
            # notice, not a failure, which WebKit raises as an error on a busy machine.
            page.on(
                "pageerror",
                lambda error: (
                    failed.append(str(error))
                    if not str(error).startswith("ResizeObserver loop")
                    else None
                ),
            )
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


def stop(page: Page) -> None:
    """Stops the epic in front, as a script would -- a chat offers no Stop -- until it has ended.

    An ended chat is done, as a chat app's conversation is: never stopped.
    """
    from playwright.sync_api import expect

    page.evaluate(
        """async () => {
          const name = decodeURIComponent(location.hash.match(/epics\\/([^/?]+)/)[1])
          const epic = await (await fetch(`/api/runs/${encodeURIComponent(name)}`)).json()
          await fetch('/api/held/stop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({workspace: epic.workspace}),
          })
        }"""
    )
    expect(page.locator("[data-hmz=bar] .badge")).to_have_text(
        re.compile("done|stopped")
    )
