"""The pictures of `docs/user/desktop.md`: the app's window, and its launch window's states.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_desktop.py`.

The launch window's states but `Starting` are drawn on Windows alone, where the window has no
traffic lights: they are taken here with no window around them, in a window of a smaller size
than the app first opens at, so that what they say can be read. `shots.splash` draws only the
macOS window at its first size, so the sheet is made here from the same parts it is made of.
"""

# ruff: noqa: SLF001 -- the splash at another size is made of `shots`' own parts.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a discount code to checkout"

_ANSWER = (
    "Checkout takes a discount code now: charge() looks the code up and takes its"
    " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
    " six pass."
)

#: A window the splash is drawn in: wider than the least the app's may be (640 by 480).
_SMALL = (720, 440)

#: What the Windows app's window says it is (`chrome.rs`): WebView2's, then the app.
_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0 humanize-desktop/0.0.0"
)


def _sheet(state: str, detail: Any) -> Any:
    """The splash in one state, as `shots.splash` stages it, in the smaller Windows window."""
    return shots._Sheet(  # pyright: ignore[reportPrivateUsage]
        *_SMALL,
        address=shots._SPLASH.as_uri(),  # pyright: ignore[reportPrivateUsage]
        init=shots._status(state, detail),  # pyright: ignore[reportPrivateUsage]
        agent=_WINDOWS,
        ready=f"main[data-state={state}]",
    )


def _splash(state: str, detail: Any, name: str) -> None:
    """A still of the splash in one state, with no window drawn around it."""
    defs = shots._Defs()  # pyright: ignore[reportPrivateUsage]
    frame = shots._draw(_sheet(state, detail), defs)  # pyright: ignore[reportPrivateUsage]
    shots._still(name, frame, defs)  # pyright: ignore[reportPrivateUsage]


def test_the_window_shows_the_page_with_its_lights_in_the_top_row(world: World) -> None:
    world.says({"discount": _ANSWER})
    chat = world.chat(_TASK)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        shots.web(page, "user-desktop-window", window="desktop")


def test_notifications_are_shown_by_the_system(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/notifications")
        expect(page.get_by_text(re.compile("Shown by macOS"))).to_be_visible()
        shots.web(page, "user-desktop-notifications", window="desktop")


def test_the_cli_is_installed_in_wsl_as_a_reel() -> None:
    reel = shots.Reel("user-desktop-install")
    steps = (
        ("starting", None, 1.2),
        ("installing", {"updating": False, "step": "uv", "line": ""}, 1.2),
        (
            "installing",
            {"updating": False, "step": "python", "line": "Downloading cpython-3.12"},
            1.4,
        ),
        (
            "installing",
            {"updating": False, "step": "hmz", "line": "Resolved 61 packages"},
            1.2,
        ),
        (
            "installing",
            {"updating": False, "step": "hmz", "line": "Installed 61 packages"},
            2.2,
        ),
    )
    for state, detail, hold in steps:
        frame = shots._draw(_sheet(state, detail), reel._defs)  # pyright: ignore[reportPrivateUsage]
        reel._add(frame, hold, poster=hold == 1.4)  # pyright: ignore[reportPrivateUsage]
    reel.save()


def test_each_startup_error_says_what_to_do() -> None:
    _splash(
        "install-failed",
        {
            "updating": False,
            "said": "WSL missing: no Linux distribution is installed",
            "keep": False,
        },
        "user-desktop-wsl-missing",
    )
    _splash(
        "install-failed",
        {
            "updating": True,
            "said": (
                "error: Failed to fetch: `https://pypi.org/simple/hmz/`\n"
                "  Caused by: operation timed out"
            ),
            "keep": True,
        },
        "user-desktop-update-failed",
    )
    _splash("waiting", "0.4.2", "user-desktop-update-waiting")
    _splash("missing", None, "user-desktop-not-found")
