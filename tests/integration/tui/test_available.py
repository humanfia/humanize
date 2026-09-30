"""A command is offered while it would do something, and turned down, saying why, otherwise.

`/stop` only while a flow runs and is not already stopping, `/resume` only with nothing going
and a run here to carry on, the flows only while one could be chosen, `/claim` only on an
outworlder nobody else holds. And the list keeps up with the run rather than with the keys:
one left open as a run starts or ends is worked out again there and then, since a list true as
of the last key pressed is a list offering what is no longer there.

Driven headlessly on a fake end of the runs, so what is checked is what is offered and what a
typed line did, in each state a run passes through.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.app import Editor
from tests.tui.fixtures import holding, idle, link, snapshot, told, transcript, until

if TYPE_CHECKING:
    from textual.pilot import Pilot


def _offered(app: Humanize) -> list[str]:
    """What the list above the prompt holds, or nothing where it is not open."""
    listing = app.screen.query_one("#offers", OptionList)
    if not listing.has_class("offering"):
        return []
    return [
        str(listing.get_option_at_index(one).id) for one in range(listing.option_count)
    ]


def _line(app: Humanize) -> str:
    """The row the list shows while a command already written out is still being written."""
    listing = app.screen.query_one("#offers", OptionList)
    assert listing.has_class("hinting")
    return str(listing.get_option_at_index(0).prompt)


async def _sends(driver: Pilot[None], app: Humanize, line: str) -> None:
    """Puts one line at the prompt whole and sends it, past whatever it would be offered."""
    app.query_one(Editor).text = line
    await driver.pause()
    await driver.press("enter")
    await driver.pause()


@pytest.mark.timeout(60)
async def test_the_list_follows_the_run_from_idle_to_running_to_stopping_to_done() -> (
    None
):
    """Held open throughout, and never typed at again: the run moving is what redraws it."""
    app = Humanize()
    async with app.run_test() as driver:
        # Nothing has been run in this directory, which is found out off the screen.
        await until(lambda: bool(app._no_resume), driver)
        await driver.press("/")
        await driver.pause()

        idle_ = _offered(app)
        assert "/flow" in idle_
        assert "/exit" in idle_
        assert "/stop" not in idle_  # nothing to stop
        assert "/resume" not in idle_  # nothing to carry on
        assert "/claim" not in idle_  # no outworlder being read

        run = holding(app, "coder/1")
        await until(lambda: "/stop" in _offered(app), driver)
        assert "/resume" not in _offered(app)  # refused while one runs

        told(app, idle(stopping=0))
        await until(lambda: "/stop" not in _offered(app), driver)
        assert "/flow" in _offered(app)

        told(app, idle())
        await driver.pause()
        assert "/stop" not in _offered(app)
        assert "/flow" in _offered(app)
        assert not run.stopped


@pytest.mark.timeout(60)
async def test_the_keys_bound_to_commands_follow_the_run_too() -> None:
    """Enter says what it does with the line, and what the next ctrl+c does is what it says."""
    app = Humanize()
    async with app.run_test() as driver:
        assert "ctrl+c exit" in app._keys()
        app.query_one(Editor).text = "/clear"
        await driver.pause()
        assert "enter run" in app._keys()  # a command, whatever else is going on
        app.query_one(Editor).text = "/stop"
        await driver.pause()
        assert not any(key.startswith("enter") for key in app._keys())  # only told off
        app.query_one(Editor).text = "fix it"
        await driver.pause()
        assert "enter start" in app._keys()

        holding(app, "coder/1")
        await driver.pause()
        assert "enter send" in app._keys()
        app.query_one(Editor).text = ""
        await driver.pause()
        assert "ctrl+c stop" in app._keys()

        told(app, idle(stopping=0))
        await driver.pause()
        assert "ctrl+c force stop" in app._keys()


@pytest.mark.timeout(60)
async def test_no_flow_is_offered_while_one_runs() -> None:
    """A flow is chosen in order to be started, and both ways of choosing one are refused."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow ")
        await driver.pause()
        assert _offered(app)  # the flows, with nothing running

        holding(app, "coder/1")
        await until(lambda: not _offered(app), driver)
        # The flow menu still opens, on the running flow's agents, and says so.
        assert "Set up the running flow's agents" in _line(app)

        app.query_one(Editor).text = ""
        await driver.press("$")
        await driver.pause()
        assert not _offered(app)


@pytest.mark.timeout(60)
async def test_a_command_typed_while_it_is_not_offered_says_why() -> None:
    """Never silently: in the words the command would have used, and nothing is asked."""
    app = Humanize()
    async with app.run_test() as driver:
        await _sends(driver, app, "/stop")
        await until(lambda: "no flow is running" in transcript(app), driver)

        holding(app, "coder/1")
        await _sends(driver, app, "/resume")
        await until(
            lambda: "cannot resume a run while a flow is running" in transcript(app),
            driver,
        )

        told(app, idle(stopping=0))
        await _sends(driver, app, "/stop")
        await until(lambda: "already stopping" in transcript(app), driver)
        await _sends(driver, app, "/resume")
        await until(
            lambda: (
                "cannot resume a run while the flow is still stopping"
                in transcript(app)
            ),
            driver,
        )
        assert not link(app).asked_for("stop")
        assert not link(app).asked_for("start")


@pytest.mark.timeout(60)
async def test_an_outworlder_another_frontend_holds_is_not_offered_to_claim() -> None:
    """The runs would refuse it, so it is not offered, and typed out it says whose it is."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human"])
        app._now_reading("outworlder:human")
        await driver.pause()
        await driver.press("/")
        await driver.pause()
        assert "/claim" in _offered(app)

        told(
            app,
            snapshot("clients", clients=[{"client": "c2", "name": "bob"}]),
            snapshot("claims", claims={"human": "c2"}),
        )
        await until(lambda: "/claim" not in _offered(app), driver)
        assert "/afk" not in _offered(app)

        await _sends(driver, app, "/claim")
        await until(
            lambda: "human is bob's: cannot claim it" in transcript(app), driver
        )
        assert not link(app).asked_for("claim")


@pytest.mark.timeout(60)
async def test_a_list_put_away_stays_away_when_the_run_moves_under_it() -> None:
    """Brought back of its own accord, it would take the enter meant to send the line."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/c")
        await driver.pause()
        assert _offered(app)
        await driver.press("escape")
        await driver.pause()
        assert not _offered(app)

        holding(app, outworlders=["human"])
        await driver.pause()
        await driver.pause()

        assert not _offered(app)
        await driver.press("l")  # typed at again, so offered again
        await driver.pause()
        assert _offered(app) == ["/clear"]
