"""What is closed when the interface is closed, and what goes on running.

Closing the interface and stopping the run are two things wherever the runs are held by a
host this interface closing cannot reach: the flow goes on taking its turns for whoever else is
reading it, and `hmz` in this directory reads it again. So `/exit` asks, and letting go of this
interface is one of the answers rather than a command of its own -- what is checked here is that
each answer does what it says, and that the one command says outright that a flow can be left
running.

A host is a `FakeLink` here, which writes down what the interface asked of it; runs held in the
interface's own process are the real thing, driving a `claude` on PATH that keeps its turn open.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from hmz.tui.pick import DETACHES, STAYS, STOPS, Leaves
from tests.stubs import written
from tests.tui.fixtures import ONE, FakeLink, holding, set_up, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow whose one turn does not end until something else is said to it, so that a test can
#: ask what happens to a run that is still running.
FLOW = ONE

#: A `claude` that does not answer until it is told something else, so that a turn stays open.
PATIENT = """
import json
import sys

for line in sys.stdin:
    said = json.loads(line)
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "one"}))
    sys.stdout.flush()
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of our own, with a coding agent that keeps its turn open on PATH."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _says(app: Humanize, driver: Pilot[None], line: str) -> None:
    """Types one line and sends it, as somebody at the prompt would."""
    app.query_one("#editor").text = line  # pyright: ignore[reportAttributeAccessIssue]
    await driver.press("enter")
    await driver.pause()


def test_the_one_way_out_says_that_a_flow_goes_on_running() -> None:
    """The list is where somebody reads what a command does before they type it.

    Leaving with a flow running is the one thing here that does not end what it closes, so
    the line beside `/exit` has to say so: a person who reads `Exit humanize` and means to
    leave the run going has no way of knowing from there that they can.
    """
    from hmz.tui.app import _BY_NAME

    assert "running" in _BY_NAME["exit"].about


@pytest.mark.timeout(60)
async def test_the_key_that_leaves_asks_what_leaving_asks() -> None:
    """ctrl+q is Textual's own, and must not be a way round the question `/exit` puts."""
    app = Humanize(link=FakeLink())
    async with app.run_test() as driver:
        holding(app, "coder/1")
        await driver.press("ctrl+q")
        await until(lambda: isinstance(app.screen, Leaves), driver)

        assert isinstance(app.screen, Leaves)
        assert app.is_running
        app.screen.dismiss(None)
        await driver.pause()


@pytest.mark.timeout(60)
async def test_exit_with_nothing_running_asks_nothing() -> None:
    """A window being closed is a window being closed."""
    app = Humanize()
    async with app.run_test() as driver:
        await _says(app, driver, "/exit")
        await until(lambda: not app.is_running, driver)

    assert not app.is_running


async def _asks(app: Humanize, driver: Pilot[None]) -> None:
    """Puts a run in front of the interface, and asks the interface to close."""
    holding(app, "coder/1")
    await _says(app, driver, "/exit")
    await until(lambda: isinstance(app.screen, Leaves), driver)


@pytest.mark.timeout(60)
async def test_exit_asks_what_is_to_become_of_a_flow_that_is_running() -> None:
    """A day's work is behind three letters that mean `close this` everywhere else."""
    held = FakeLink()
    app = Humanize(link=held)
    async with app.run_test() as driver:
        await _asks(app, driver)

        assert isinstance(app.screen, Leaves)
        assert app.screen.rows()[1][0] == DETACHES  # held by a host, so it may be left
        assert app.is_running  # nothing has been closed and nothing has been stopped
        app.screen.dismiss(None)
        await driver.pause()
        assert not held.requests


@pytest.mark.timeout(60)
async def test_stopping_the_flow_is_what_closes_the_interface() -> None:
    """Stopping a run held by a host stops it for everybody reading it, and then leaves."""
    held = FakeLink()
    app = Humanize(link=held)
    async with app.run_test() as driver:
        await _asks(app, driver)
        app.screen.dismiss(STOPS)
        await until(lambda: not app.is_running, driver)

    assert not app.is_running
    assert [one["do"] for one in held.requests] == ["force"]


@pytest.mark.timeout(60)
async def test_leaving_it_running_lets_go_of_this_interface_alone() -> None:
    """The runs are asked nothing: this interface lets go of them, and they go on."""
    closed: list[bool] = []

    class Closes(FakeLink):
        def close(self) -> None:
            closed.append(True)

    held = Closes()
    app = Humanize(link=held)
    async with app.run_test() as driver:
        await _asks(app, driver)
        app.screen.dismiss(DETACHES)
        await until(lambda: not app.is_running, driver)

    assert closed
    assert not held.requests  # neither stopped nor forced


@pytest.mark.timeout(120)
async def test_runs_held_here_go_with_the_interface(
    workspace: Path, hosting: None
) -> None:
    """With nothing holding them apart from it, leaving is stopping, and nothing is offered.

    The question is still put -- a flow is still running -- but the answer that would leave
    it running is not one there is, and stopping closes the runs held in this process.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "flow")
        await _says(app, driver, "start")
        await until(lambda: "coder/1" in app._working, driver)
        assert "coder/1" in app._working
        await _says(app, driver, "/exit")
        await until(lambda: isinstance(app.screen, Leaves), driver)

        assert isinstance(app.screen, Leaves)
        assert app.screen.rows()[1][0] == STAYS
        host = app._host
        assert host is not None
        app.screen.dismiss(STOPS)
        await until(lambda: not app.is_running, driver)

    assert host.closed


def test_the_second_answer_is_whichever_one_is_true_here() -> None:
    """An answer that cannot be carried out is not one to offer."""
    assert [answer for answer, _, _ in Leaves(held=True).rows()] == [STOPS, DETACHES]
    assert [answer for answer, _, _ in Leaves(held=False).rows()] == [STOPS, STAYS]
