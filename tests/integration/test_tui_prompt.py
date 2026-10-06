"""The prompt: opening the interface, typing at it, and what it says back before anything runs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    nothing_installed,
    opened,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


async def test_it_opens_on_chat_with_the_model_the_installed_agent_says_it_runs(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        drawn = await shows(pilot, RUNS)

    assert "chat" in drawn
    assert "assistant" in drawn


async def test_with_no_agent_installed_a_line_is_answered_with_why_it_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nothing_installed(tmp_path, monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "hello")
        await shows(pilot, "no coding agent is installed")

        assert app.is_running


async def test_a_command_that_is_not_one_is_said_so(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await typed(pilot, "/fly")

        await shows(pilot, "no such command")


async def test_a_half_typed_command_is_offered_and_tab_takes_it(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await pilot.press(*"/se")
        await shows(pilot, "/settings [page]")

        await pilot.press("tab")

        drawn = await shows(pilot, "❯ /settings", "workspace")
        assert "general" in drawn  # and now its pages are offered


async def test_shift_enter_breaks_the_line_and_enter_sends_both_lines(
    workspace: Path,
) -> None:
    from tests.integration.doubles_tui import heard

    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press(*"first", "shift+enter", *"second")
        drawn = await shows(pilot, "❯ first")
        assert "heard" not in drawn  # broken, not sent

        await pilot.press("enter")
        await shows(pilot, "heard second")

    assert heard(workspace) == ["first\nsecond"]


async def test_what_was_typed_is_kept_and_up_brings_it_back_in_the_next_interface(
    workspace: Path, tmp_path: Path
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await typed(pilot, "/fly")
        await typed(pilot, "/flew")
        await shows(pilot, "/flew")

    kept = (tmp_path / "humanize-home" / "history.jsonl").read_text().splitlines()
    assert [json.loads(one)["text"] for one in kept] == ["/fly", "/flew"]

    async with Humanize().run_test(size=SIZE) as pilot:
        await pilot.press("up")
        await shows(pilot, "❯ /flew")
        await pilot.press("up")
        await shows(pilot, "❯ /fly")
        await pilot.press("down")
        await shows(pilot, "❯ /flew")


async def test_clear_empties_the_transcript(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "/fly")
        await shows(pilot, "no such command")

        await typed(pilot, "/clear")

        await until(pilot, lambda: "no such command" not in screen(app), "a clear")
        assert app.is_running


async def test_exit_leaves(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "/exit")
        await until(pilot, lambda: not app.is_running, "the interface to close")


async def test_two_ctrl_c_with_nothing_running_leave(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running  # one press only says what the next does

        await pilot.press("ctrl+c")
        await until(pilot, lambda: not app.is_running, "the interface to close")


async def test_ctrl_c_takes_back_a_half_typed_line(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press(*"never mind")
        await shows(pilot, "❯ never mind")

        await pilot.press("ctrl+c")

        await until(pilot, lambda: "never mind" not in screen(app), "the line to go")
        assert app.is_running
