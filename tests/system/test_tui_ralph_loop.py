"""`hmz` at the prompt, start to finish: a builtin flow set up, run, watched and kept.

The interface is opened in the sample project, `ralph_loop` chosen in `/flow` and its agent
set to the cheapest model of a CLI signed in here, a budget given, and the task typed. The
run is watched in the transcript and on the monitor until its budget ends it, and what it
left behind is then checked in the project itself: its tests pass, and only `stats.py` was
changed to make them.

The second test leaves the run going, as `/exit` offers, and comes back to it in a new
interface: the run is held by a host apart from the terminal, which is what `hmz` opens on
at a real terminal.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from hmz.tui import Humanize
from tests.system.doubles_tui import TASK, Screen, cheapest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: Somewhere to draw: wide enough that no line the checks read is wrapped.
SIZE = (140, 50)

#: How long a run may take: a few rounds of a small model, and whichever turn is going.
BUDGET = "4m"

#: How long the budget, and the turn going when it is reached, are waited on.
RUN = 12 * 60.0


@pytest.fixture
def here(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The sample project, as the directory `hmz` is opened in, with prices to cost it in.

    The prices are fetched, as they are anywhere else: the monitor says what a run cost, and
    the budget's dollars hold it to that.
    """
    monkeypatch.delenv("HUMANIZE_PRICES")
    monkeypatch.chdir(workspace)
    return workspace


def _passes(workspace: Path) -> None:
    """The sample's tests pass, and only `stats.py` was changed to make them."""
    tested = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tested.returncode == 0, tested.stdout + tested.stderr
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert "stats.py" in changed
    assert not [one for one in changed if one.startswith("tests/")], changed


async def _watches(screen: Screen, model: str) -> None:
    """Watches a run going: an agent working, and on the monitor its turns and their cost."""
    await screen.waits("agent is working", seconds=180)
    # The monitor, with nothing typed: the agent's box, and the money under the drawing.
    await screen.press("left")
    shown = await screen.waits(
        "▣ monitor", "all agents", model, "turn", "Tokens:", "$", seconds=180
    )
    assert "Flow:" in shown
    assert "ralph_loop" in shown
    await screen.press("right")
    await screen.waits("agent is working", "ctrl+c stop")


@pytest.mark.timeout(20 * 60)
async def test_a_task_typed_at_the_prompt_is_done_by_the_flow_set_up_there(
    here: Path,
) -> None:
    cli, model = cheapest()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        screen = Screen(app, pilot)
        await screen.waits("The agent flow system")
        await screen.sets_up("ralph_loop", cli, model, BUDGET)
        await screen.starts(TASK)
        await screen.waits(TASK)

        await _watches(screen, model)

        shown = await screen.waits("— the flow is done —", seconds=RUN)
        assert "hmz: stopped --" in shown
        assert "◉ ralph_loop" in shown
    _passes(here)


def _host(workspace: Path) -> daemon.Daemon:
    """Starts the host of the project's runs, as `hmz` does at a terminal, and finds it.

    Started from a process of its own, which forks it: this one has threads that a fork
    would copy mid-step -- pytest-xdist's, for one -- and a host forked from here can hang.
    It waits a while for its first interface before it goes.
    """
    subprocess.run(
        [sys.executable, "-c", "from hmz import daemon; daemon.host()"],
        cwd=workspace,
        check=True,
        timeout=120,
    )
    found = daemon.running(workspace)
    assert found is not None
    return found


@pytest.fixture
def hosted(here: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """The project's runs held by a host apart from the interface, which goes after."""
    monkeypatch.setenv("HUMANIZE_DAEMON", "on")
    try:
        yield here
    finally:
        found = daemon.running(here)
        if found is not None:
            found.kill()


@pytest.mark.timeout(20 * 60)
async def test_a_run_left_going_is_found_again_by_the_next_interface(
    hosted: Path,
) -> None:
    cli, model = cheapest()
    first = Humanize(link=_host(hosted).link(kind="tui"))
    async with first.run_test(size=SIZE) as pilot:
        screen = Screen(first, pilot)
        await screen.waits("The agent flow system")
        await screen.sets_up("ralph_loop", cli, model, BUDGET)
        await screen.starts(TASK)
        await screen.waits("agent is working", seconds=180)
        # Leaving, and leaving it running.
        await screen.types("/exit")
        await screen.press("enter")
        await screen.waits("Detach and exit")
        await screen.press("down", "enter")
        deadline = time.monotonic() + 30
        while first.is_running and time.monotonic() < deadline:
            await pilot.pause(0.2)
        assert not first.is_running

    found = daemon.running(hosted)
    assert found is not None
    assert found.status()["state"] == "running"

    again = Humanize(link=found.link(kind="tui"))
    async with again.run_test(size=SIZE) as pilot:
        screen = Screen(again, pilot)
        # Read from the top: what it was started on, and the agent still at it.
        await screen.waits(TASK)
        await _watches(screen, model)
        shown = await screen.waits("— the flow is done —", seconds=RUN)
        assert "hmz: stopped --" in shown
    _passes(hosted)
