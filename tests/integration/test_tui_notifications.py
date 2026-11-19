"""Notifications: the interface tells of another epic or chat, never of the one it shows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

import hmz.daemon
from hmz.coganchor import settings
from hmz.daemon import linked
from hmz.runtime import Holding, Host
from hmz.runtime.epic import Epic
from hmz.tui import Humanize
from hmz.tui.pick import Epics
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import (
    OWN,
    RUNS,
    SIZE,
    heard,
    leaves,
    on,
    onto,
    opened,
    own_flow,
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

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, asked what it runs."""
    del asking
    return stand_in(tmp_path, monkeypatch)


@pytest.fixture
def elsewhere(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Host]]:
    """A chat of another workspace, which the daemon says it holds."""
    del workspace
    yield from _held(tmp_path, "chat:0a1b2c3d4e5f", monkeypatch)


@pytest.fixture
def flowing(
    tmp_path: Path, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Host]]:
    """Another workspace's own host, and a flow for it to run."""
    own_flow(workspace)
    yield from _held(tmp_path, "", monkeypatch)


def _held(
    tmp_path: Path, slot: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Host]]:
    """One host of another workspace, which the daemon says it holds, closed afterwards."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    host = Host(Holding(other), slot=slot)
    held = SimpleNamespace(workspace=str(other), slot=slot, status=host.status)
    monkeypatch.setattr(hmz.daemon, "daemons", lambda: [held])
    try:
        yield other, host
    finally:
        host.close()


async def test_another_chat_is_told_with_no_epic_to_dot_and_this_one_never(
    workspace: Path, elsewhere: tuple[Path, Host]
) -> None:
    other, host = elsewhere
    app = Humanize()
    async with app.run_test(size=SIZE, notifications=True) as pilot:
        await opened(pilot)
        # The chat on the screen: its turn ends, and is told of nowhere.
        await typed(pilot, "hello")
        await shows(pilot, "heard hello")
        with linked(host, kind="sdk") as someone:
            someone.chat(RUNS, "hello there")
            await until(pilot, lambda: heard(other) == ["hello there"], "its turn")
            await shows(pilot, "chat · elsewhere")
        await pilot.pause(2.5)
        assert "chat · workspace" not in screen(app)

        # A chat is no epic: none is listed, and none dotted.
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await pilot.press("ctrl+t")
        await shows(pilot, "no flow has been run on this machine yet")
        assert "●" not in screen(app)


async def test_another_epic_is_told_and_dotted_until_opened(
    workspace: Path, flowing: tuple[Path, Host]
) -> None:
    other, host = flowing
    # An epic of this directory, told of nothing, which is never dotted.
    with Epic(OWN, "here", workspace):
        pass
    app = Humanize()
    async with app.run_test(size=SIZE, notifications=True) as pilot:
        await opened(pilot)
        with linked(host, kind="sdk") as someone:
            someone.start(
                OWN, "wait for it", agents={"coder": RUNS}, budget={"cost": 100}
            )
            await until(pilot, lambda: heard(other) == ["wait for it"], "its turn")
            someone.stop()
            # It stopped, which is told of.
            await shows(pilot, f"{OWN} · elsewhere")

            await typed(pilot, "/epics")
            await on(pilot, Epics)
            await pilot.press("ctrl+t")
            await until(pilot, lambda: "●" in screen(app), "the dot on its epic")
            assert screen(app).count("●") == 1

            listed = app.screen.query_one("#choices", OptionList)
            (dotted,) = [
                str(one.id).removeprefix("=")
                for one in listed.options
                if "●" in str(one.prompt)
            ]
            await onto(pilot, dotted)
            await pilot.press("enter")
            await shows(pilot, "export epic")
            await pilot.press("escape")
            await on(pilot, Epics)
            await until(pilot, lambda: "●" not in screen(app), "the dot gone")


async def test_a_kind_turned_off_on_notifications_is_told_of_nowhere(
    workspace: Path, elsewhere: tuple[Path, Host]
) -> None:
    other, host = elsewhere
    app = Humanize()
    async with app.run_test(size=SIZE, notifications=True) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings notifications")
        await on(pilot, Adjusts)
        await shows(pilot, "Done", "Questions", "Waiting", "System")
        for kind in ("done", "listening"):
            await picks(pilot, kind, "off")
        await leaves(pilot)
        wanted = settings.read()["notifications"]
        assert wanted["kinds"]["done"] is False
        assert wanted["kinds"]["listening"] is False

        with linked(host, kind="sdk") as someone:
            someone.chat(RUNS, "hello there")
            await until(pilot, lambda: heard(other) == ["hello there"], "its turn")
            await pilot.pause(4.5)
        assert "elsewhere" not in screen(app)
