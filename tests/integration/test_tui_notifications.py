"""Notifications: the interface tells of another workspace's epic, never of the one it shows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

import hmz.daemon
from hmz.coganchor import settings
from hmz.daemon import Hmz, linked
from hmz.tui import Humanize
from hmz.tui.pick import Epics
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import (
    RUNS,
    SIZE,
    heard,
    leaves,
    on,
    onto,
    opened,
    picks,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.daemon import Host


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, asked what it runs."""
    del asking
    return stand_in(tmp_path, monkeypatch)


@pytest.fixture
def elsewhere(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Host]]:
    """Another workspace's runs, which the daemon says it holds."""
    del workspace
    other = tmp_path / "elsewhere"
    other.mkdir()
    host = Hmz(other).host()
    held = SimpleNamespace(workspace=str(other), status=host.status)
    monkeypatch.setattr(hmz.daemon, "daemons", lambda: [held])
    try:
        yield other, host
    finally:
        host.close()


async def test_another_epic_is_told_and_dotted_until_opened_and_this_one_never(
    workspace: Path, elsewhere: tuple[Path, Host]
) -> None:
    other, host = elsewhere
    app = Humanize()
    async with app.run_test(size=SIZE, notifications=True) as pilot:
        await opened(pilot)
        # The epic on the screen: its turn ends, and is told of nowhere.
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")
        with linked(host, kind="sdk") as someone:
            someone.start("chat", "hello there", agents={"assistant": RUNS})
            await until(pilot, lambda: heard(other) == ["hello there"], "its turn")
            await shows(pilot, "chat · elsewhere")
        await pilot.pause(2.5)
        assert "chat · workspace" not in screen(app)

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await pilot.press("ctrl+t")
        await until(pilot, lambda: "chat ●" in screen(app), "the dot on its epic")
        assert screen(app).count("●") == 1

        listed = app.screen.query_one("#choices", OptionList)
        (dotted,) = [
            str(one.id).removeprefix("=")
            for one in listed.options
            if "●" in str(one.prompt)
        ]
        await onto(pilot, dotted)
        await pilot.press("enter")
        await until(pilot, lambda: not isinstance(app.screen, Epics), "the epic open")
        await pilot.press("escape")
        await on(pilot, Epics)
        await until(pilot, lambda: "chat ●" not in screen(app), "the dot gone")


async def test_a_kind_turned_off_on_notifications_is_told_of_nowhere(
    workspace: Path, elsewhere: tuple[Path, Host]
) -> None:
    other, host = elsewhere
    app = Humanize()
    async with app.run_test(size=SIZE, notifications=True) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings notifications")
        await on(pilot, Adjusts)
        await shows(pilot, "Done", "Questions", "Chat turns", "System")
        for kind in ("done", "listening"):
            await picks(pilot, kind, "off")
        await leaves(pilot)
        wanted = settings.read()["notifications"]
        assert wanted["kinds"]["done"] is False
        assert wanted["kinds"]["listening"] is False

        with linked(host, kind="sdk") as someone:
            someone.start("chat", "hello there", agents={"assistant": RUNS})
            await until(pilot, lambda: heard(other) == ["hello there"], "its turn")
            await pilot.pause(4.5)
        assert "elsewhere" not in screen(app)
