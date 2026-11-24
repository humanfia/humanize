"""Attaching: an interface opened on runs a host holds apart from it, with a run already going."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from hmz.daemon import linked
from hmz.runtime import Holding, Host
from hmz.tui import Humanize
from hmz.tui.pick import DETACHES, Leaves
from tests.integration.doubles_tui import (
    PATIENCE,
    RUNS,
    SIZE,
    TALKS,
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

    from hmz.daemon import Link

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` on `PATH`."""
    return stand_in(tmp_path, monkeypatch)


@pytest.fixture
def host(workspace: Path) -> Iterator[Host]:
    """The workspace's runs, held apart from any interface, and closed with the test."""
    held = Host(Holding(workspace))
    try:
        yield held
    finally:
        held.close()


@pytest.fixture
def running(host: Host, workspace: Path) -> Iterator[Link]:
    """Another frontend of the runs, which has started a flow on a turn held open."""
    yield from _started(host, workspace, TALKS)


@pytest.fixture
def chatting(workspace: Path) -> Iterator[tuple[Host, Link]]:
    """A chat's host, and another frontend of it, which has started a turn held open."""
    held = Host(Holding(workspace), slot="chat:0a1b2c3d4e5f")
    try:
        with linked(held, kind="sdk") as other:
            other.chat(RUNS, "wait for it")
            _waits(lambda: heard(workspace) == ["wait for it"], "the turn to start")
            yield held, other
    finally:
        held.close()


def _started(host: Host, workspace: Path, flow: str) -> Iterator[Link]:
    with linked(host, kind="sdk") as other:
        other.start(
            flow, "wait for it", agents={"assistant": RUNS}, budget={"cost": 100}
        )
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
        await shows(pilot, "❯ wait for it", "still on it", f"assistant · {RUNS}")

        await typed(pilot, "and this")

        await shows(pilot, "heard wait for it then and this")
    assert heard(workspace) == ["wait for it", "and this"]


async def test_a_line_another_frontend_says_lands_in_the_turn_the_interface_shows(
    host: Host, running: Link
) -> None:
    async with Humanize(link=linked(host)).run_test(size=SIZE) as pilot:
        await shows(pilot, "still on it")

        await asyncio.to_thread(running.say, "from elsewhere")

        await shows(pilot, "heard wait for it then from elsewhere")


async def test_leaving_an_attached_interface_detached_leaves_the_run_going(
    host: Host, running: Link, workspace: Path
) -> None:
    app = Humanize(link=linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await shows(pilot, "still on it")
        await typed(pilot, "/exit")
        await on(pilot, Leaves)
        await shows(pilot, "Detached, the flow keeps running")

        await pilot.click(f"#act-{DETACHES}")

        await until(pilot, lambda: not app.is_running, "the interface to close")

    assert host.status()["state"] == "running"
    await asyncio.to_thread(running.say, "still there?")
    await asyncio.to_thread(
        _waits, lambda: heard(workspace)[-1:] == ["still there?"], "the run to hear"
    )


async def test_exit_leaves_a_chat_a_host_holds_going_without_asking(
    chatting: tuple[Host, Link], workspace: Path
) -> None:
    host, other = chatting
    app = Humanize(link=linked(host))
    async with app.run_test(size=SIZE) as pilot:
        await shows(pilot, "still on it", "running…")

        await typed(pilot, "/exit")

        await until(pilot, lambda: not app.is_running, "the interface to close")

    assert host.status()["state"] == "running"
    await asyncio.to_thread(other.chat_say, "still there?")
    await asyncio.to_thread(
        _waits, lambda: heard(workspace)[-1:] == ["still there?"], "the run to hear"
    )


async def test_two_ctrl_c_in_an_attached_interface_stop_the_run_for_everybody(
    host: Host, running: Link
) -> None:
    async with Humanize(link=linked(host)).run_test(size=SIZE) as pilot:
        await shows(pilot, "still on it")

        await pilot.press("ctrl+c", "ctrl+c")

        await shows(pilot, "stopping the flow")
        await until(pilot, lambda: host.status()["state"] == "idle", "the run to end")
