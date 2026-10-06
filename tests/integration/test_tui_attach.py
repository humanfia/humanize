"""Attaching: an interface opened on runs a host holds apart from it, with a run already going."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from hmz.daemon import Hmz, linked
from hmz.tui import Humanize
from hmz.tui.pick import DETACHES, Leaves
from tests.integration.doubles_tui import (
    PATIENCE,
    RUNS,
    SIZE,
    heard,
    on,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.daemon import Host, Link


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` on `PATH`."""
    return stand_in(tmp_path, monkeypatch)


@pytest.fixture
def host(workspace: Path) -> Iterator[Host]:
    """The workspace's runs, held apart from any interface, and closed with the test."""
    held = Hmz(workspace).host()
    try:
        yield held
    finally:
        held.close()


@pytest.fixture
def running(host: Host, workspace: Path) -> Iterator[Link]:
    """Another frontend of the runs, which has started chat on a turn held open."""
    with linked(host, kind="sdk") as other:
        other.start("chat", "wait for it", agents={"assistant": RUNS})
        _waits(lambda: heard(workspace) == ["wait for it"], "the turn to start")
        yield other


def _waits(ready: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + PATIENCE
    while not ready():
        assert time.monotonic() < deadline, f"gave up waiting for {what}"
        time.sleep(0.02)


async def test_an_interface_attached_to_a_run_is_shown_it_so_far_and_steers_it(
    host: Host, running: Link, workspace: Path
) -> None:
    async with Humanize(link=linked(host)).run_test(size=SIZE) as pilot:
        await shows(pilot, "❯ wait for it", "⏺ working", f"assistant · {RUNS}")

        await typed(pilot, "and this")

        await shows(pilot, "heard wait for it then and this")
    assert heard(workspace) == ["wait for it", "and this"]


async def test_a_line_another_frontend_says_lands_in_the_turn_the_interface_shows(
    host: Host, running: Link
) -> None:
    async with Humanize(link=linked(host)).run_test(size=SIZE) as pilot:
        await shows(pilot, "⏺ working")

        await asyncio.to_thread(running.say, "from elsewhere")

        await shows(pilot, "heard wait for it then from elsewhere")


async def test_leaving_an_attached_interface_detached_leaves_the_run_going(
    host: Host, running: Link, workspace: Path
) -> None:
    app = Humanize(link=linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await shows(pilot, "⏺ working")
        await typed(pilot, "/exit")
        await on(pilot, Leaves)
        await shows(pilot, "Detached, it keeps running")

        await pilot.click(f"#act-{DETACHES}")

        await until(pilot, lambda: not app.is_running, "the interface to close")

    assert host.status()["state"] == "running"
    await asyncio.to_thread(running.say, "still there?")
    await asyncio.to_thread(
        _waits, lambda: heard(workspace)[-1:] == ["still there?"], "the run to hear"
    )


async def test_two_ctrl_c_in_an_attached_interface_stop_the_run_for_everybody(
    host: Host, running: Link
) -> None:
    async with Humanize(link=linked(host)).run_test(size=SIZE) as pilot:
        await shows(pilot, "⏺ working")

        await pilot.press("ctrl+c", "ctrl+c")

        await shows(pilot, "stopping the flow")
        await until(pilot, lambda: host.status()["state"] == "idle", "the run to end")
