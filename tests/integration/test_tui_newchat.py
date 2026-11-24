"""The New chat page and the chat's chips, on the real interface and a daemon of the test's own.

A chat is started from the page with a permission and an effort picked from its chips, and is
then on the log; from the Details view its effort is changed while it goes on, and the turn
said next starts at it. The assistant is the stand-in `claude`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.epic import chats, read
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.shell import Zone
from hmz.tui.views.chips import Chips
from hmz.tui.views.harness import Session
from hmz.tui.views.newchat import NewChat
from tests.integration.doubles_tui import (
    MODEL,
    SIZE,
    Chats,
    on,
    opened,
    screen,
    shows,
    stand_in,
    started,
    typed,
    until,
)

if TYPE_CHECKING:
    from textual.pilot import Pilot

#: Every chat here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.usefixtures("daemon", "loops"), pytest.mark.timeout(180)]


@pytest.fixture
def asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Chats:
    """The stand-in `claude` on `PATH`, and every `chat.*` the interface asks kept."""
    del asking
    stand_in(tmp_path, monkeypatch)
    return Chats().install(monkeypatch)


def _harness_session(tmp_path: Path, workspace: Path, ident: str, said: str) -> Path:
    """A session the stand-in `claude` had of its own in the workspace, as it logs one."""
    workspace = workspace.resolve()
    plain = "".join(one if one.isalnum() else "-" for one in str(workspace))
    log = tmp_path / "claude-home" / "projects" / plain / f"{ident}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = [
        {
            "type": "user",
            "cwd": str(workspace),
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": said},
        },
        {
            "type": "assistant",
            "cwd": str(workspace),
            "timestamp": "2026-01-01T00:00:05+00:00",
            "message": {"model": MODEL, "role": "assistant", "content": []},
        },
    ]
    log.write_text("".join(json.dumps(one) + "\n" for one in rows))
    return log


async def _picks(pilot: Pilot[None], value: str) -> None:
    """Takes one value of the list dropped, by what picking it answers with."""
    dropped = await on(pilot, Dropdown)
    dropped.dismiss(value)
    await until(
        pilot, lambda: not isinstance(pilot.app.screen, Dropdown), "the list to close"
    )


async def test_a_chat_is_started_from_the_page_with_the_permission_and_effort_picked(
    asked: Chats,
) -> None:
    workspace = Path.cwd()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press("ctrl+n")
        page = await on(pilot, NewChat)
        await shows(pilot, "NEW CHAT", f"MODEL Claude Code {MODEL}", "Edit this folder")
        assert "enter Start" in screen(app)

        # Back from the message to the chips: permission, then effort.
        await pilot.press("shift+tab")
        assert getattr(app.focused, "id", "") == "permission"
        assert "enter choose" in screen(app)
        await pilot.press("enter")
        await _picks(pilot, "danger-full-access")
        await shows(pilot, "PERMISSIONS Full access")
        await pilot.press("shift+tab", "enter")
        await _picks(pilot, "low")
        await shows(pilot, "EFFORT Low")

        page.query_one("#message").focus()
        await typed(pilot, "make it so")
        await shows(pilot, "heard make it so")
        assert not isinstance(app.screen, NewChat)

    (start,) = asked.started()
    assert start["permission"] == "danger-full-access"
    assert start["agent"] == f"claude/{MODEL}:low"
    (argv,) = started(workspace)
    assert argv[argv.index("--effort") + 1] == "low"
    (chat,) = chats(workspace)
    ran = read(chat)
    assert ran is not None
    assert ran.permission == "danger-full-access"


async def test_an_effort_changed_from_the_chips_is_what_the_next_turn_starts_at(
    asked: Chats,
) -> None:
    del asked
    workspace = Path.cwd()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first")

        await pilot.press("ctrl+g")
        await shows(pilot, "DETAILS", "Effort", "High", "Edit this folder")
        assert app.query_one("#context", Zone).has_class("open")
        chips = app.query_one(Chips)
        assert app.focused is chips
        assert "enter choose" in screen(app)

        await pilot.press("down", "enter")  # Model, then Effort
        await _picks(pilot, "low")
        await until(
            pilot,
            lambda: (
                "Low" in screen(app) and "High" not in screen(app).split("USAGE")[0]
            ),
            "the effort to change",
        )

        await pilot.press("escape")
        await until(
            pilot, lambda: getattr(app.focused, "id", "") == "editor", "the prompt"
        )
        await typed(pilot, "second")
        await shows(pilot, "heard second")

    efforts = [argv[argv.index("--effort") + 1] for argv in started(workspace)]
    assert efforts[0] == "high"
    assert efforts[-1] == "low"


async def test_a_harness_session_is_read_from_the_page_and_continued_in_a_chat(
    asked: Chats, tmp_path: Path
) -> None:
    del asked
    workspace = Path.cwd()
    ident = "0b0b0b0b-1111-4222-8333-444444444444"
    log = _harness_session(tmp_path, workspace, ident, "the word is guava")
    before = log.read_bytes()
    Settings().harness_sessions = True
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press("ctrl+n")
        await on(pilot, NewChat)
        await shows(
            pilot, "HARNESS SESSIONS", "the word is guava", "Claude Code session"
        )

        await pilot.press("tab")  # from the message on to the list
        await pilot.press("enter")
        await on(pilot, Session)
        await shows(pilot, "HARNESS SESSION", "❯ the word is guava", "Continue in chat")
        assert "the Claude Code session stays as it is" in " ".join(screen(app).split())

        await pilot.press("enter")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the pages to close")
        await shows(pilot, "say something to continue")
        await typed(pilot, "more")
        await shows(pilot, "heard more")

    made = [ran for at in chats(workspace) if (ran := read(at)) and ran.adopted]
    assert [(one.adopted, one.title) for one in made] == [
        (f"claude:{ident}", "the word is guava")
    ]
    # Only read: the session itself is as it was.
    assert log.read_bytes() == before
