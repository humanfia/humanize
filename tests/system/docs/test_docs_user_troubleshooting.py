"""The pictures of `docs/user/troubleshooting.md`: what a failure looks like on each interface.

A chat whose agent was refused its sign-in, as the app shows it and as the terminal interface
says why; the launch window in each of its startup errors; a command line refused before
anything ran; and the terminal interface on a machine with no coding agent. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_troubleshooting.py`.
"""

# ruff: noqa: SLF001 -- the splash at another size is made of `shots`' own parts.

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.integration.doubles_tui import shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-troubleshooting"

_TASK = "Add a discount code to checkout"

#: A window the splash is drawn in: wider than the least the app's may be (640 by 480), and
#: smaller than the one it first opens at, so that what it says can be read.
_SMALL = (720, 440)

#: What the Windows app's window says it is (`chrome.rs`): WebView2's, then the app.
_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
    " Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0 humanize-desktop/0.0.0"
)

#: What a coding agent says when its sign-in has lapsed.
_SIGNED_OUT = "Invalid API key · Please run /login"


def test_a_chat_says_why_its_turn_failed(world: World) -> None:
    world.says({"discount": {"fail": _SIGNED_OUT}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        expect(
            page.get_by_role("button", name=re.compile("Nous: .*Haiku"))
        ).to_be_visible()
        box = page.get_by_role("textbox", name="First message")
        box.fill(_TASK)
        box.press("Enter")
        expect(page.get_by_text("The chat failed")).to_be_visible()
        expect(page.get_by_text("Failed", exact=True)).to_be_visible()
        page.wait_for_timeout(800)
        # The line over the box makes the printed document a hair taller than its window,
        # which prints a second, empty sheet: the document is held to the window's height.
        page.add_style_tag(content="html, body { height: 100vh; overflow: hidden; }")
        shots.web(page, f"{_PAGE}-chat-failed", window="desktop")


async def test_the_terminal_says_why_the_turn_failed(world: World) -> None:
    world.says({"discount": {"fail": _SIGNED_OUT}})
    async with world.tui(size=(100, 20)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, _TASK)
        await shows(pilot, "signing in again")
        shots.tui(app, f"{_PAGE}-signed-out")


def _sheet(state: str, detail: Any) -> Any:
    """The splash in one state, as `shots.splash` stages it, in the smaller Windows window."""
    return shots._Sheet(  # pyright: ignore[reportPrivateUsage]
        *_SMALL,
        address=shots._SPLASH.as_uri(),  # pyright: ignore[reportPrivateUsage]
        init=shots._status(state, detail),  # pyright: ignore[reportPrivateUsage]
        agent=_WINDOWS,
        ready=f"main[data-state={state}]",
    )


def test_the_launch_window_says_each_startup_error() -> None:
    reel = shots.Reel(f"{_PAGE}-startup")
    states = (
        (
            "install-failed",
            {
                "updating": False,
                "said": "WSL missing: no distribution is installed",
                "keep": False,
            },
        ),
        (
            "install-failed",
            {
                "updating": False,
                "said": "error: failed to fetch https://example.invalid/hmz: timed out",
                "keep": False,
            },
        ),
        ("waiting", "0.4.2"),
    )
    for at, (state, detail) in enumerate(states):
        frame = shots._draw(_sheet(state, detail), reel._defs)  # pyright: ignore[reportPrivateUsage]
        reel._add(frame, 3.0, poster=at == 1)  # pyright: ignore[reportPrivateUsage]
    reel.save()


def test_a_line_is_refused_before_anything_runs(world: World) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            "worker=codex/gpt-5.6-sol",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-refused",
    )


async def test_the_terminal_says_no_agent_is_installed(world: World) -> None:
    # A machine with no coding agent.
    agent = world._bin / "claude"  # pyright: ignore[reportPrivateUsage]
    agent.unlink()
    async with world.tui(size=(100, 20)) as (app, pilot):
        await pilot.pause(1.5)
        await typed(pilot, _TASK)
        await shows(pilot, "No coding agent is installed")
        shots.tui(app, f"{_PAGE}-no-agent")
