"""The pictures of `docs/user/daemon.md`: this machine's daemon, as each interface shows it.

The app's list of daemons with this machine's on it, the same in the terminal, and what
`hmz daemon` prints: its help, a daemon served with a listener, and one refused beside
another. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_daemon.py`.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from typing import TYPE_CHECKING

import psutil
from playwright.sync_api import expect

from tests.integration.doubles_tui import shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest

    from tests.system.docs.conftest import World

_PAGE = "user-daemon"

#: The listener the served daemon is given: this machine alone, so nothing is opened to others.
_LISTEN = "tcp://127.0.0.1:41817"


def test_this_machines_daemon_in_the_app(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/daemons")
        expect(page.locator("[data-hmz=daemon-state]").first).to_be_visible()
        page.wait_for_timeout(600)
        listed = page.locator("[data-hmz=daemons]")
        shots.web(page, f"{_PAGE}-app", clip=listed, pad=12)


async def test_this_machines_daemon_in_the_terminal(world: World) -> None:
    async with world.tui((100, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings daemons")
        await pilot.pause(1.0)
        shots.tui(app, f"{_PAGE}-terminal")


def test_the_commands(world: World) -> None:
    shots.cli(["hmz", "daemon", "--help"], f"{_PAGE}-help")


def test_a_second_daemon_is_refused(world: World) -> None:
    shots.cli(["hmz", "daemon", "serve"], f"{_PAGE}-already")


def _interrupts(after: float) -> threading.Thread:
    """Interrupts the daemon a command of this process serves, once it has listened a while."""

    def waits() -> None:
        until = time.monotonic() + 90
        while time.monotonic() < until:
            for one in psutil.Process().children(recursive=True):
                try:
                    line = one.cmdline()
                except psutil.Error:
                    continue
                if line[-4:-1] == ["daemon", "serve", "--listen"]:
                    time.sleep(after)
                    os.kill(one.pid, signal.SIGINT)
                    return
            time.sleep(0.2)

    thread = threading.Thread(target=waits, daemon=True)
    thread.start()
    return thread


def test_a_daemon_is_served_with_a_listener(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A machine of its own, where no daemon runs yet: the world's is held by the test.
    other = world.home.parent / "t"
    other.mkdir()
    monkeypatch.setenv("TMPDIR", str(other))
    # Its user's login shell is asked for its environment: one that says nothing of ours.
    monkeypatch.setenv("SHELL", "/bin/sh")
    stopping = _interrupts(after=12)
    shots.cli(["hmz", "daemon", "serve", "--listen", _LISTEN], f"{_PAGE}-serve")
    stopping.join()
