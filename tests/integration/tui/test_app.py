"""The one prompt: a command reaches the command it names, and a plain line reaches the agent.

Driven headlessly, so what is checked is what a keystroke actually does rather than how it is
drawn -- the interface's own job being to have one line mean both of those things.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest.mock
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from textual import events
from textual.widgets import Button, Input, Label, OptionList, Static

from hmz.coganchor.agents import DshSession
from hmz.coganchor.backends import Model
from hmz.flows import Budget
from hmz.runtime.epic import epics
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.app import _BY_NAME, _COMMANDS, _SAID, Editor, _where
from hmz.tui.flows import _BUDGET, _PROFILING, Flows
from hmz.tui.monitoring import Monitoring
from hmz.tui.pick import (
    _ACT_ADD,
    _ACT_AGAIN,
    _ACT_DONE,
    _ACT_SAVE,
    _ACT_SEARCH,
    Accounts,
    Agent,
    Catalogue,
    Clis,
    Configures,
    Confirms,
    Signing,
)
from hmz.tui.settings import PAGES, Adjusts
from tests.stubs import events as recorded
from tests.stubs import written
from tests.tui.fixtures import (
    ONE,
    event,
    holding,
    link,
    opened,
    set_up,
    snapshot,
    told,
    transcript,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow of one agent for one turn, which writes down what the turn answered -- so a line
#: can be typed while it is running.
FLOW = ONE


#: A `claude` that answers each thing it is told with a turn of its own, as the real one
#: does, but withholds the first answer until a second thing arrives -- which is what makes
#: the interjection observable: the turn cannot end before the typed line lands.
PATIENT = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
heard = []
for line in sys.stdin:
    heard.append(json.loads(line)["message"]["content"][0]["text"])
    if len(heard) == 1:
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working"}]}}), flush=True)
        continue
    for answer in (heard[0], " then ".join(heard)):
        print(json.dumps({"type": "result", "result": answer}), flush=True)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None) -> Path:
    """Puts the patient fake `claude` on PATH and works in a directory of our own.

    And holds the runs in this process, since what it is for is a flow really running.
    """
    del hosting
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    # Hidden, as the collector's own suite hides them: `/collect` reads the agents' home
    # directories, and the real ones hold a developer's whole history of sessions.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "KIMI_CODE_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def ids(app: Humanize) -> list[str]:
    """Every row of the sheet on top, by the id each row was put up under."""
    return [
        str(one.id or "").removeprefix("=")
        for one in app.screen.query_one("#choices", OptionList).options
    ]


def under(app: Humanize) -> str:
    """The row of the sheet on top the cursor is on, by the id it was put up under."""
    from hmz.tui.pick import Sheet

    sheet = app.screen
    assert isinstance(sheet, Sheet)
    return sheet.under()


def rows(app: Humanize) -> list[str]:
    """What the sheet on top is offering: its rows, every list being searched from a button."""
    return ids(app)


async def into_flows(app: Humanize, driver: Pilot[None]) -> None:
    """Opens the flow menu and waits for it to have something in it.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await driver.press(*"/flow")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )


async def onto(app: Humanize, driver: Pilot[None], held: str) -> None:
    """Walks the cursor on to the row put up under one id, or the focus on to a button.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id -- or one of the buttons under the list by its key, which
        tab walks the focus on to, as it would for somebody at the keys.
    """
    if held in bar(app):
        button = app.screen.query_one(f"#act-{held}")
        for _ in range(len(bar(app)) + 3):
            if button.has_focus:
                return
            await driver.press("tab")
            await driver.pause()
        assert button.has_focus, f"tab never reached {held!r}"
        return
    if not app.screen.query_one("#choices").has_focus:
        app.screen.query_one("#choices").focus()
        await driver.pause()
    listing = app.screen.query_one("#choices", OptionList)
    at = ids(app).index(held)
    for _ in range(len(listing.options)):
        if (listing.highlighted or 0) == at:
            return
        await driver.press("down" if (listing.highlighted or 0) < at else "up")
        await driver.pause()


async def into_agent(app: Humanize, driver: Pilot[None], at: int = 0) -> None:
    """Opens the flow the menu is on, and then one of the agents it drives.

    Which every test about what an agent is has to walk through: an agent of a flow is set up
    from the flow that drives it, inside the flow it belongs to.

    Args:
      app: The interface.
      driver: What is pumping it.
      at: Which of the flow's agents, counting from zero.
    """
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    if not sheet._inside:
        await driver.press("enter")  # which opens what drives the flow under the cursor
        # A flow that takes settings of its own puts them up on the way in, that being the
        # moment it is chosen. Esc leaves them exactly as the draft has them, which is what a
        # walk that is about the agents wants.
        await until(lambda: sheet._inside or isinstance(app.screen, Configures), driver)
        if isinstance(app.screen, Configures):
            await driver.press("escape")
        await until(lambda: sheet._inside, driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    await onto(app, driver, str(at))
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Agent), driver)


async def up(app: Humanize, driver: Pilot[None]) -> str:
    """Goes up to the monitor and waits for its graph to be drawn.

    Args:
      app: The interface.
      driver: What is pumping it.

    Returns:
      What it says under the graph.
    """
    app.action_monitor()
    await until(
        lambda: isinstance(app.screen, Monitoring) and bool(app.screen.query("#graph")),
        driver,
    )
    await driver.pause()
    return str(app.screen.query_one("#under", Static).content)


async def opens(app: Humanize, driver: Pilot[None], held: str) -> None:
    """Opens one row of the sheet an agent is set up on.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id -- `cli`, `model`, `skills` and the rest.
    """
    await onto(app, driver, held)
    await driver.press("enter")
    await driver.pause()


async def changes(app: Humanize, driver: Pilot[None], held: str, *keys: str) -> None:
    """Changes one row that is changed where it stands, and keeps what it then says.

    Enter begins changing it, the keys change it, and enter keeps it.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
      keys: What to press while it is being changed.
    """
    await onto(app, driver, held)
    await driver.press("enter")
    await driver.pause()
    await driver.press(*keys)
    await driver.pause()
    await driver.press("enter")
    await driver.pause()


async def into_settings(
    app: Humanize, driver: Pilot[None], page: str = "general"
) -> None:
    """Opens `/settings` on one of its pages, by the name the command is given.

    Args:
      app: The interface.
      driver: What is pumping it.
      page: Which page, by its name: one of :data:`hmz.tui.settings.PAGES`.
    """
    from hmz.tui.settings import PAGES

    await driver.press(*f"/settings {page}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Adjusts), driver)
    sheet = cast("Adjusts", app.screen)
    await until(lambda: sheet._tab == PAGES.index(page) and not sheet._home, driver)
    await driver.pause()


def bar(app: Humanize) -> list[str]:
    """The buttons under the list of the sheet on top, by key, in the order they stand."""
    return [
        (one.id or "").removeprefix("act-")
        for one in app.screen.query("#actions Button")
        if one.display
    ]


def keyed(app: Humanize) -> list[str]:
    """What the row of keys under the sheet on top says, a `key does` apiece.

    Read off the keys the sheet kept rather than out of the line it drew from them, which
    picks each key out from what it does in markup of its own.
    """
    from hmz.tui.pick import Sheet

    sheet = app.screen
    assert isinstance(sheet, Sheet)
    return [f"{one.key} {one.does}" for one in sheet._keyed]


def reads(app: Humanize, at: int) -> str:
    """What one row of the sheet on top says, as words, by where it is in the list.

    A row's line about itself is wrapped onto further lines, each in markup of its own, so a
    phrase is looked for in what the row reads as rather than in how it is laid out.
    """
    from textual.content import Content

    listing = app.screen.query_one("#choices", OptionList)
    said = Content.from_markup(str(listing.get_option_at_index(at).prompt)).plain
    return " ".join(said.split())


async def acts(app: Humanize, driver: Pilot[None], held: str) -> None:
    """Clicks one of the buttons under the list of the sheet on top.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The button, by its key -- `_ACT_ADD`, `_ACT_SAVE` and the rest.
    """
    assert held in bar(app), f"{held!r} is not one of {bar(app)}"
    await driver.click(f"#act-{held}")
    await driver.pause()


async def picks(app: Humanize, driver: Pilot[None], held: str, value: str) -> None:
    """Drops the values of one row under it and picks one, with the keys.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
      value: The value to pick, by what it answers with.
    """
    from hmz.tui.dropdown import Dropdown

    await onto(app, driver, held)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Dropdown), driver)
    dropped = app.screen
    listing = dropped.query_one(OptionList)
    at = [str(one.id) for one in listing.options].index(f"={value}")
    while listing.highlighted != at:
        await driver.press("down")
        await driver.pause()
    await driver.press("enter")
    await until(lambda: app.screen is not dropped, driver)
    await driver.pause()


async def nexts(app: Humanize, driver: Pilot[None], held: str, by: int = 1) -> None:
    """Picks the value one or more along from the one in force, from the list dropped under it.

    What stepping a row along with the arrows across used to do, done the way it is done now.

    Args:
      app: The interface.
      driver: What is pumping it.
      held: The row, by its id.
      by: How far along, wrapping round the end.
    """
    from hmz.tui.dropdown import Dropdown

    await onto(app, driver, held)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Dropdown), driver)
    dropped = cast("Dropdown", app.screen)
    values = [
        str(one.id).removeprefix("=") for one in dropped.query_one(OptionList).options
    ]
    now = values.index(dropped._current) if dropped._current in values else 0
    await driver.press("escape")
    await until(lambda: app.screen is not dropped, driver)
    await picks(app, driver, held, values[(now + by) % len(values)])


async def details(app: Humanize, driver: Pilot[None]) -> None:
    """Turns the details switch round on the first page of `/settings`, and saves it.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await into_settings(app, driver)
    sheet = cast("Adjusts", app.screen)
    await picks(app, driver, "details", "off" if sheet._details else "on")
    await keeps(app, driver)
    await driver.pause()


async def _leaves(app: Humanize, driver: Pilot[None], *answer: str) -> None:
    """Leaves the sheet on top, answering whatever it asks about what it is holding.

    Esc as many times as it takes, each press one step back: `/flow` and `/settings` are
    walked into, so esc on a page comes back out to the one above it, and the press that
    leaves the menu is the one on its first screen.

    Args:
      app: The interface.
      driver: What is pumping it.
      answer: What to press on the question about what it is holding, where it asks one.
    """
    was = app.screen
    for _ in range(5):
        await driver.press("escape")
        await driver.pause()
        if isinstance(app.screen, Confirms):
            await driver.press(*answer)
            await driver.pause()
            break
        if app.screen is not was:
            break
    await until(lambda: app.screen is not was, driver)


async def leaves(app: Humanize, driver: Pilot[None]) -> None:
    """Leaves the sheet on top, which is holding nothing to be asked about.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await _leaves(app, driver)


async def keeps(app: Humanize, driver: Pilot[None]) -> None:
    """Leaves the sheet on top, saving what it is holding when it asks.

    A menu applies nothing until it is left, so this is what applying one is: esc, and then
    the first answer of the question it puts up about what it is holding, which has the focus.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await _leaves(app, driver, "enter")


async def drops(app: Humanize, driver: Pilot[None]) -> None:
    """Leaves the sheet on top, throwing away whatever it is holding.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    await _leaves(app, driver, "down", "enter")


@pytest.mark.timeout(60)
async def test_a_line_typed_while_a_flow_runs_reaches_the_agent(
    workspace: Path,
) -> None:
    """The whole point: the turn is still running, and what is typed lands inside it."""
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        # The turn will not end until it has been told something else, so this cannot race.
        await until(
            lambda: bool(app._seen),
            driver,
        )
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool((workspace / "said.txt").exists()), driver)

    assert (workspace / "said.txt").read_text().strip() == "start then and this"


@pytest.mark.timeout(60)
async def test_a_line_with_nothing_to_run_it_on_says_so_rather_than_vanishing() -> None:
    """A flow is always chosen now, so the only thing a line can be short of is an agent."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"hello?")
        await driver.press("enter")
        await driver.pause()

        assert app._models == {}  # nothing installed, so nothing was set up to run
        assert "no coding agent is installed" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_command_that_is_not_one_is_said_so() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/fly")
        await driver.press("enter")
        await driver.pause()

        assert "no such command" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_flow_that_is_not_there_is_a_line_to_correct_and_not_the_end(
    hosting: None,
) -> None:
    """A flow chosen that will not load is said so, and the interface stays up."""
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "nowhere.py")
        await driver.press(*"do it")
        await driver.press("enter")
        await until(lambda: "nowhere.py" in transcript(app), driver)

        assert app.is_running  # still there to be typed at
        assert "nowhere.py" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_flow_that_fails_as_it_is_read_is_a_line_to_correct_and_not_the_end(
    workspace: Path,
) -> None:
    """Reading a flow imports it, so a flow may fail before it has been asked to do anything.

    One that opens a file beside it and does not find it raises as it is imported -- which
    is where the run is refused, and not somewhere an interface may die.
    """
    written(workspace, "broken", 'raise FileNotFoundError("no prompt.md beside me")\n')
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./broken")
        await driver.press(*"do it")
        await driver.press("enter")
        await until(lambda: "prompt.md" in transcript(app), driver)

        assert app.is_running  # still there to be typed at


def test_only_the_flows_there_are_to_run_are_offered() -> None:
    """A flow anywhere else is a path typed out, not something found by walking the tree."""
    from hmz.runtime.flowing import found
    from hmz.tui.complete import offered

    assert offered("/flow ", _COMMANDS) == [one.name for one in found()]


@pytest.mark.timeout(60)
async def test_what_the_flow_did_is_on_monitor(workspace: Path) -> None:
    """Who worked, who handed to whom, and what it cost -- none of which the flow reports."""
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._seen),
            driver,
        )
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool((workspace / "said.txt").exists()), driver)

        # Read while the flow is still running, which is the whole point of a sheet for it.
        said = await up(app, driver)
        assert "flow" in said
        # The flow itself, drawn: the transcript all of them are on, then a box per agent.
        boxes = app.screen.query_one("#graph", OptionList)
        drawn = "\n".join(
            str(boxes.get_option_at_index(one).prompt)
            for one in range(boxes.option_count)
        )
        assert "all agents" in drawn
        assert "1 turn" in drawn  # the one agent, and its one turn
        assert app._monitor.turns.total() == 1


@pytest.mark.timeout(60)
async def test_a_half_typed_command_is_offered_the_rest_of_itself() -> None:
    """Offered in a list under the editor, and taken with tab: nothing is ever guessed at."""
    from hmz.tui.app import Editor

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/fl")
        await driver.pause()

        offers = app.query_one("#offers", OptionList)
        assert offers.has_class("offering")
        # The name is what is taken; what is shown is the name and what it is for.
        assert [
            str(offers.get_option_at_index(i).id) for i in range(offers.option_count)
        ] == ["/flow"]
        assert "Switch flow" in str(offers.get_option_at_index(0).prompt)

        await driver.press("tab")

        assert app.query_one(Editor).text == "/flow "


@pytest.mark.timeout(60)
async def test_enter_takes_what_is_offered_rather_than_sending_the_half_typed_line() -> (
    None
):
    """Over an open list, enter means take what is under the cursor -- as it does anywhere.

    And the offers run out, so enter goes back to sending: `/flow` takes one flow, and a
    line that already names it has nothing left to be finished with.
    """
    from hmz.runtime.flowing import found
    from hmz.tui.app import Editor

    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await driver.press(*"/fl")
        await driver.press("enter")
        await driver.pause()

        assert editor.text == "/flow "  # taken, not sent
        assert "no such command" not in transcript(app)

        await driver.press("enter")  # and again, for the flow it is offering now
        await driver.pause()

        assert editor.text == f"/flow {found()[0].name} "

        await driver.press("enter")  # nothing left to offer, so this is the line going
        await driver.pause()

        assert editor.text == ""
        assert f"/flow {found()[0].name}" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_arrows_walk_what_was_typed_before_it() -> None:
    """Up for older and down for newer, and what was half typed is given back at the end.

    Which is the whole reason the draft is kept: an arrow pressed by mistake over a prompt
    somebody spent five minutes writing must not be what takes it away.
    """
    from hmz.tui.app import Editor

    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        for said in ("first", "second"):
            await driver.press(*said)
            await driver.press("enter")
        await driver.press(*"half written")

        await driver.press("up")
        assert editor.text == "second"  # newest first

        await driver.press("up")
        assert editor.text == "first"

        await driver.press("up")
        assert editor.text == "first"  # the far end of it, and nothing is lost there

        await driver.press("down")
        assert editor.text == "second"

        await driver.press("down")
        assert editor.text == "half written"  # what was being typed, back again


@pytest.mark.timeout(60)
@pytest.mark.parametrize("key", ["shift+enter", "ctrl+j"])
async def test_the_line_is_broken_rather_than_sent(key: str) -> None:
    """Enter sends, so breaking the line is a key of its own -- and two of them.

    A terminal reports shift+enter as itself only where it speaks a keyboard protocol that
    has a way to say so, and sends a bare carriage return where it does not -- which is
    enter, and would send the line. `ctrl+j` is a line feed, and arrives from anywhere.
    """
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"first")
        await driver.press(key)
        await driver.press(*"second")

        assert editor.text == "first\nsecond"  # still in the editor, and in two lines
        assert "first" not in transcript(app)  # nothing was sent by breaking a line


@pytest.mark.timeout(60)
async def test_the_keys_under_the_prompt_say_how_to_break_a_line() -> None:
    """The one somebody reaches for first, which is the one that reads as a newline."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert "shift+enter newline" in " ".join(app._keys())


@pytest.mark.timeout(60)
async def test_the_arrows_are_the_editor_s_own_inside_a_prompt_of_more_than_one_line() -> (
    None
):
    """A prompt of several lines is moved around in; only its ends walk the history."""
    from hmz.tui.app import Editor

    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"remembered")
        await driver.press("enter")
        editor.text = "one\ntwo"
        editor.move_cursor((1, 3))  # the end of the second line, which is the last

        await driver.press("up")  # up the prompt, not back through what was typed

        assert editor.text == "one\ntwo"
        assert editor.cursor_location[0] == 0

        await driver.press(
            "up"
        )  # and off the top of it, which is the history after all

        assert editor.text == "remembered"


@pytest.mark.timeout(60)
async def test_nothing_is_offered_for_what_is_not_a_command() -> None:

    from hmz.tui.app import Editor

    app = Humanize()
    async with app.run_test() as driver:
        offers = app.query_one("#offers", OptionList)

        await driver.press(*"hello")
        await driver.pause()
        assert not offers.has_class(
            "offering"
        )  # a line said to the agent offers nothing

        app.query_one(
            Editor
        ).text = ""  # ctrl+a is "start of line" here, not "select all"
        await driver.press(*"/zz")
        await driver.pause()
        assert not offers.has_class("offering")  # nor does a command that is not one


@pytest.mark.timeout(60)
async def test_the_offer_is_taken_from_the_commands_there_actually_are() -> None:
    """A command this interface grows must be offered without being listed twice.

    One table holds the name, the line about it, what it takes and what carries it out, so
    what is offered and what a sent line reaches are the same rows by construction.

    And none of the three the command line has that are not things to do to a flow that is
    running: `exec` is what the first thing you say already does, and `anchor` and the wrapper
    a turn is spawned as are each about a run rather than inside one. What both sides do have
    is the store of accounts, which is one thing said in two places.
    """
    from hmz.tui.complete import offered

    offers = offered("/", _COMMANDS)

    assert {f"/{one.name}" for one in _COMMANDS} == set(offers)
    assert {one.name for one in _COMMANDS} == set(_BY_NAME)
    assert not {"/exec", "/anchor", "/cred"} & set(offers)
    # And a command typed in full has nothing left to be finished with, so enter sends it.
    assert offered("/exit", _COMMANDS) == []


@pytest.mark.timeout(90)
async def test_what_is_running_is_not_swapped_underneath_itself(
    workspace: Path,
) -> None:
    """A flow is chosen in order to be started, so the flows are not offered while one runs.

    The menu opens inside the agents of the flow that is going -- an agent thinking too little
    is found out halfway through a run -- and esc there leaves, there being no list of flows
    behind it to step back to.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._seen),
            driver,
        )

        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)

        assert sheet._inside  # it opens on the agents, the flows not being offered
        # And nothing across the top leads back to a list, there being none behind it.
        assert sheet.crumbs() == []
        assert "esc close" in keyed(app)

        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flows), driver)

        assert app._flow_named == "./flow"  # nothing got anywhere
        assert app._models == {"coder": Runs("claude/m:high")}
        # And the monitor is not refused either: it is read, so nothing conflicts with it.
        assert "flow" in await up(app, driver)

        await driver.press("right")
        await until(lambda: not isinstance(app.screen, Monitoring), driver)
        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(90)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("m", ("max", "high")),)},
)
async def test_an_agent_set_up_under_a_running_flow_is_what_the_next_run_starts_on(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    workspace: Path,
) -> None:
    """That page is never shut, and what is saved there waits for the next run.

    A run is handed a driver per role as it starts, and every session of that role opens on
    it: the agent under way is not swapped under the flow holding it, and saying so is the
    whole of what saving does to it.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(lambda: bool(app._seen) and app._run is not None, driver)
        assert app._runs_of("coder") == Runs("claude/m:high")

        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await into_agent(app, driver)
        await picks(app, driver, "effort", "max")  # harder than it was started at
        await keeps(app, driver)
        await keeps(app, driver)
        await until(lambda: "the next run starts on" in transcript(app), driver)

        # The running one, as it started, and what the line above the prompt names it by.
        assert app._runs_of("coder") == Runs("claude/m:high")
        assert app._models == {"coder": Runs("claude/m:max")}  # and the next, as saved
        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(90)
async def test_two_ctrl_c_stop_the_flow_and_not_just_the_turn(workspace: Path) -> None:
    """Ctrl+c twice ends the run, rather than only the turn under way.

    A flow is a loop, so stopping the turn under way is not stopping anything: the loop
    would go round again. The run is stopped, which interrupts the turn and unwinds every
    call of the flow from where it stands.

    Twice, because a day's work is behind a key that is also pressed by mistake: the first
    press says what the next one does and the second one does it.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._seen),
            driver,
        )
        await driver.press("ctrl+c")
        await driver.pause()
        assert app._run is not None  # one press asks, and asks rather than doing it
        assert "press ctrl+c again" in transcript(app)

        await driver.press("ctrl+c")
        await until(lambda: app._run is None, driver)  # the flow itself is over
        await until(lambda: app._stopping is None, driver)  # and has unwound

        assert "stopping the flow" in transcript(app)
        # And the run is over with it: an epic is one run of one flow, and this ends one.
        (epic,) = epics(workspace)
        assert recorded(epic)[-1] == {
            "event": "ended",
            "at": unittest.mock.ANY,
            "how": "stopped",
        }


@pytest.mark.timeout(90)
async def test_the_run_is_read_by_going_up_to_it_and_neither_key_stops_it(
    workspace: Path,
) -> None:
    """A key pressed to dismiss things must not be the key that ends a day's work, nor `←`."""
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "./flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._seen),
            driver,
        )
        held = app._run

        await driver.press("escape")
        await driver.pause()
        assert app._run is held  # esc stops nothing
        assert not isinstance(app.screen, Monitoring)  # and opens nothing either

        await driver.press("left")  # which is how the run is read now
        await until(lambda: isinstance(app.screen, Monitoring), driver)
        assert app._run is held  # read, and nothing stopped by reading it
        await driver.press("right")
        await driver.pause()
        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(90)
async def test_a_line_to_a_running_flow_is_never_turned_away() -> None:
    """Between two turns there is no turn to steer, and the line still has to land.

    A flow that is running takes what is typed either way: into the turn under way, or into
    whichever turn starts next. There is no third answer -- a flow that is not running is
    what makes the first thing you say the task. Which is the runs' to settle: the interface
    says it to them, on the view it was typed on.
    """
    app = Humanize()
    async with app.run_test() as driver:
        # A flow that is running, with nobody mid-turn.
        holding(app, "coder/1")
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert link(app).asked_for("say") == [
            {"do": "say", "text": "and this", "to": ""}
        ]
        assert not link(app).asked_for("start")  # said, not taken for a task
        assert "nothing is running to be told" not in transcript(app)


@pytest.mark.timeout(60)
async def test_exit_leaves() -> None:
    """`/exit`, as opencode spells it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/exit")
        await driver.press("enter")
        await driver.pause()

        assert not app.is_running


def test_what_the_agents_run_is_known_without_starting_one() -> None:
    """Starting a backend to ask it costs a minute here, which no prompt can wait on.

    `claude --help` took over thirty seconds on the machine this was written on, and
    `codex app-server` seventy-six -- so what they run is known rather than asked for.
    """
    from hmz.tui.discover import installed

    with unittest.mock.patch("subprocess.Popen") as started:
        found = installed()

    assert not started.called  # nothing was run to find this out
    # And an effort a model does not take is not offered against it.
    efforts = {model.name: model.efforts for model in found.get("codex", ())}
    if efforts:
        assert efforts["gpt-5.5"] != efforts["gpt-5.6-sol"]


@pytest.mark.timeout(60)
async def test_a_flow_between_two_turns_is_a_flow_that_is_running() -> None:
    """It sleeps off a round, commits, reads what the last turn wrote -- and that is the run.

    Which is why the rate is measured over the whole of it: the status line says the same
    thing, naming the flow and how long the run has been going rather than falling back to
    saying where it is, as if nothing were happening.
    """
    from hmz.coganchor.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
    async with app.run_test() as driver:
        # A flow that is running, with nobody mid-turn: the flow's own code has the time.
        app._flow_named = "rlcr"
        holding(app, ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")))
        app._monitor.began = time.monotonic() - 90
        app._draw()
        await driver.pause()

        status = str(app.query_one("#status", Static).content)

    assert "rlcr" in status  # what is running
    assert "90s" in status  # and for how long the run has been going, turn or no turn


@pytest.mark.timeout(60)
async def test_a_flow_that_called_another_names_both_of_them() -> None:
    """A flow may reach for another and run it, and what is running is then both."""
    now = time.monotonic()
    started = {"ref": "chat:chat", "name": "chat", "depth": 1, "since": now, "id": 0}
    inner = {"ref": "rlar:review", "name": "review", "depth": 2, "since": now, "id": 0}
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named = "chat"
        told(
            app,
            snapshot(
                "calls", calls=[{**started, "parent": None}, {**inner, "parent": 0}]
            ),
        )
        app._draw()
        await driver.pause()
        status = str(app.query_one("#status", Static).content)

        assert "chat ▸ rlar:review" in status

        # And back to the one that is set up to run, once nothing is.
        told(app, snapshot("calls", calls=[]))
        app._draw()
        await driver.pause()
        assert "chat" in str(app.query_one("#status", Static).content)


@pytest.mark.timeout(60)
async def test_the_readout_says_what_a_run_cost_in_money_as_well_as_in_tokens(
    priced: str,
) -> None:
    """A token count says how much work was done and nothing about what it came to."""
    app = Humanize()
    async with app.run_test() as driver:
        told(app, opened("actor/1"))
        app._monitor.begins("actor", priced)
        app._monitor.spend("actor", 1040, kinds={"input": 1000, "output": 40})
        app._draw()
        await driver.pause()

        above = str(app.query_one("#above", Static).content)

    # Kind by kind rather than as one total over them: an input token and an output token
    # are two different things bought at two different prices.
    assert "input 1.0k" in above
    assert "output 40" in above
    assert "$0.0012" in above  # a thousand in at $1/M and forty out at $5/M
    assert "out/s" in above  # and the rate is the output alone, which it says


@pytest.mark.timeout(60)
async def test_a_turn_that_lands_carries_the_kinds_its_bill_is_made_of(
    priced: str,
) -> None:
    """The `result` says what it cost by model and by kind, and the money needs both."""
    app = Humanize()
    async with app.run_test():
        told(
            app,
            event(
                "actor/1",
                "result",
                "done",
                tokens={priced: 1040},
                spent={"input": 1000, "output": 40},
                model=priced,
            ),
        )

        (spending,) = app._monitor.spending()

    assert spending.tokens == 1040
    assert spending.dollars == pytest.approx(1000 / 1e6 * 1 + 40 / 1e6 * 5)


@pytest.mark.timeout(60)
async def test_a_turn_spread_over_two_models_keeps_the_kinds_it_was_made_of(
    priced: str,
) -> None:
    """A turn that reached for a cheaper model for a sub-turn says the kinds of the pair.

    Nothing in it says which of the two a cached read was made against, so they are divided
    by what each model took. Dropped instead -- which is what happened before -- the whole
    turn counted as tokens of no kind at all: missing from every per-kind figure and priced
    at nothing, which is a worse answer than an apportioned one.
    """
    app = Humanize()
    async with app.run_test():
        told(
            app,
            event(
                "actor/1",
                "result",
                "done",
                tokens={priced: 1000, "some-lite-model": 40},
                spent={"input": 1000, "output": 40},
                model=priced,
            ),
        )

        spending = {one.model: one for one in app._monitor.spending()}

    assert sum(one.tokens for one in spending.values()) == 1040
    # Each model's share of each kind, which comes to the turn's own reckoning again.
    assert spending[priced].kinds["input"] == pytest.approx(1000 * 1000 / 1040)
    assert spending["some-lite-model"].kinds["input"] == pytest.approx(1000 * 40 / 1040)
    assert sum(one.kinds["output"] for one in spending.values()) == pytest.approx(40)
    # And the one that is priced has a bill, where before neither of them had one.
    assert spending[priced].dollars is not None
    assert spending["some-lite-model"].dollars is None  # nobody lists it


@pytest.mark.timeout(60)
async def test_the_tokens_group_on_the_monitor_carries_the_bill_beside_the_count(
    priced: str,
) -> None:
    """Per model, since two agents at one model are one bill -- and one bill is money."""
    app = Humanize()
    async with app.run_test() as driver:
        app._monitor.begins("actor", priced)
        app._monitor.spend("actor", 1040, kinds={"input": 1000, "output": 40})
        said = await up(app, driver)

    assert priced in said
    assert "1.0k" in said
    assert "$0.0012" in said


@pytest.mark.timeout(60)
async def test_the_remainder_of_dividing_a_turn_between_models_marks_nothing(
    priced: str,
) -> None:
    """A millionth of a token is not spending nobody said the kind of.

    Dividing a turn's kinds between the two models it named leaves a remainder in the last
    bit of a float. Counted as tokens of no named kind, it would mark every figure of a run
    that is counting everything as a floor -- a warning about arithmetic, on the commonest
    turn Claude Code takes, since a turn that reached for a sub-agent names two models.
    """
    app = Humanize()
    async with app.run_test():
        app._monitor.reporting("actor", {"input", "output", "cache_read"})
        told(
            app,
            event(
                "actor/1",
                "result",
                "done",
                tokens={priced: 201_391, "some-lite-model": 1755},
                spent={"input": 1663, "output": 410, "cache_read": 201_073},
                model=priced,
            ),
        )

        counted = app._monitor.reckoning()

    assert [one.kind for one in counted] == ["input", "output", "cache_read"]
    assert all(one.whole for one in counted), counted


@pytest.mark.timeout(60)
async def test_the_readout_marks_a_kind_one_of_the_backends_running_does_not_report(
    priced: str,
) -> None:
    """The union over two backends is short by whatever the one that never counts it spent.

    Claude Code says what a cache write cost; Codex counts its cached reads inside the input
    and never names a write at all. So a run driving both has a `cache_write` column made of
    Claude's writes alone, and drawn as though it were the total it would be a claim about
    the run that nothing here can make.
    """
    app = Humanize()
    async with app.run_test() as driver:
        app._monitor.reporting(
            "builder", {"input", "output", "cache_read", "cache_write"}
        )
        app._monitor.reporting("reviewer", {"input", "output", "cache_read"})
        app._monitor.spend(
            "builder", 1200, model=priced, kinds={"input": 1000, "cache_write": 200}
        )
        app._monitor.spend("reviewer", 40, model=priced, kinds={"output": 40})
        app._draw()
        await driver.pause()

        above = str(app.query_one("#above", Static).content)

    (counted,) = [line for line in above.splitlines() if "input" in line]
    assert "input 1.0k·" in counted.replace(" · ", "·")  # both count it: whole
    assert "cache_write 200+" in counted  # one of them never does: a floor


@pytest.mark.timeout(60)
async def test_the_kinds_group_on_the_monitor_says_what_a_run_spent_its_tokens_on(
    priced: str,
) -> None:
    """Under the models, since a cached read is the same thing whichever model made it."""
    app = Humanize()
    async with app.run_test() as driver:
        app._monitor.reporting("actor", {"input", "output", "cache_read"})
        app._monitor.reporting("other", {"input", "output"})
        app._monitor.spend(
            "actor",
            1140,
            model=priced,
            kinds={"input": 1000, "cache_read": 100, "output": 40},
        )
        said = await up(app, driver)

    assert "Kinds" in said
    assert "cache_read" in said
    assert "minimum: not all agents report this kind" in said


@pytest.mark.timeout(60)
async def test_a_model_nobody_prices_is_a_token_count_with_no_dollars_beside_it() -> (
    None
):
    """`$0.00` against an unlisted model would be a claim about a bill, and a wrong one."""
    app = Humanize()
    async with app.run_test() as driver:
        told(app, opened("actor/1"))
        app._monitor.begins("actor", "a-model-nobody-lists")
        app._monitor.spend("actor", 4000, kinds={"input": 3000, "output": 1000})
        app._draw()
        await driver.pause()

        above = str(app.query_one("#above", Static).content)

    (counted,) = [line for line in above.splitlines() if "input" in line]
    assert "input 3.0k" in counted
    assert "output 1.0k" in counted
    assert "$" not in above.replace("$text-muted", "")  # a colour is not a currency


@pytest.mark.timeout(60)
async def test_a_turn_that_has_gone_quiet_still_reads_as_one_that_is_running() -> None:
    """A model thinks for minutes without a word, and the clock is what says it is alive."""
    app = Humanize()
    async with app.run_test() as driver:
        told(app, event("one/1", "begins", "do it"))
        app._began["one"] = time.monotonic() - 42  # a turn that started a while ago
        app._draw()
        await driver.pause()

        status = str(app.query_one("#status", Static).content)

    assert "one" in status  # who is working
    assert "42s" in status  # and for how long, which a turn saying nothing does not say


@pytest.mark.timeout(60)
async def test_a_flow_is_opened_to_reach_its_agents_and_esc_comes_back() -> None:
    """One menu walked into, which is what enter and esc mean everywhere else here.

    Its agents are the flow's own, so they are a page under the flow rather than a view beside
    the list it was picked from; and the list of flows is a page under the first screen.
    """
    from hmz.tui.flows import HOME

    app = Humanize()
    # Whatever this machine has installed, since the menu is only put up if there is one.
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await into_flows(app, driver)
            sheet = cast("Flows", app.screen)
            assert "chat" in rows(app)  # what is installed, the built in ones first
            assert "enter set up" in keyed(app)

            # Tab moves the focus between the list and the buttons under it, and turns no
            # page: the flows and their agents are not two views of one thing.
            await driver.press("tab")
            await driver.pause()
            assert not sheet._inside
            await driver.press("shift+tab")
            await driver.pause()

            await driver.press("enter")
            await until(lambda: sheet._inside, driver)
            # The role the person chooses an agent for -- the person being the other, and
            # nobody's to choose -- what a run may spend and whether it is profiled; the lot is
            # saved from a button.
            assert rows(app) == ["0", _BUDGET, _PROFILING]
            assert bar(app)[-1] == _ACT_SAVE
            assert "chat" in str(sheet.query_one("#asked", Label).content)
            assert "esc back" in keyed(app)

            await driver.press("escape")
            await until(lambda: not sheet._inside, driver)
            assert app.screen is sheet  # one step back, and not out of the menu
            assert "chat" in rows(app)

            await driver.press("escape")  # and up to the first screen, then out
            await until(lambda: sheet._page == HOME, driver)
            await driver.press("escape")
            await until(lambda: not isinstance(app.screen, Flows), driver)

            assert app._models == {}


@pytest.mark.timeout(60)
async def test_the_commands_that_were_pages_of_settings_are_gone() -> None:
    """`/settings` is every setting, so the four commands it swallowed are nobody's now."""
    app = Humanize()
    async with app.run_test() as driver:
        for gone in ("fallback", "providers", "flowverses", "details"):
            await driver.press(*f"/{gone}")
            await driver.press("enter")
            await driver.pause()
            assert f"no such command: /{gone}" in transcript(app)
            assert gone not in _BY_NAME


@pytest.mark.timeout(60)
async def test_settings_is_one_menu_of_five_pages() -> None:
    """General, the accounts, the fallbacks, the runtimes, the workspace."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        sheet = cast("Adjusts", app.screen)
        await driver.pause()

        # What opens is the pages and nothing else, each a card of its own.
        assert sheet._home
        # From the broadest to the nearest: this machine, who agents are and what takes
        # over when one fails, where work goes, this directory. Where flows come from is
        # `/flow`'s.
        assert ids(app) == [
            "general",
            "accounts",
            "fallback",
            "runtimes",
            "workspace",
        ]
        prompts = [
            str(one.prompt) for one in sheet.query_one("#choices", OptionList).options
        ]
        assert "General" in prompts[0]
        assert "Workspace" in prompts[-1]

        # Enter goes into one, and esc comes back out onto the card it went in from.
        await onto(app, driver, "runtimes")
        await driver.press("enter")
        await until(lambda: not sheet._home, driver)
        assert sheet._tab == PAGES.index("runtimes")
        # What is done about the list is a button under it, and nothing on this page is
        # held, so there is nothing to save it from.
        assert _ACT_ADD in bar(app)
        assert _ACT_SAVE not in bar(app)

        await driver.press("escape")
        await until(lambda: sheet._home, driver)
        assert under(app) == "runtimes"
        assert isinstance(app.screen, Adjusts)


@pytest.mark.timeout(60)
async def test_the_flowverses_page_of_settings_is_on_flow_now() -> None:
    """Asked for by its old name, `/flow` opens on it and says where it went."""
    from hmz.tui.flows import VERSES

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings flowverses")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)

        assert sheet._page == VERSES
        assert "flowverses are on /flow now" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_page_of_settings_is_gone_into_and_come_out_of_with_the_mouse() -> None:
    """A click on a card goes into it, and a click on the way across the top comes back."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        await driver.press(*"/settings")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        sheet = cast("Adjusts", app.screen)
        await driver.pause()
        listing = sheet.query_one("#choices", OptionList)

        # The second card, two lines and a rule down from the top of the list.
        await driver.click("#choices", offset=(10, 1 + 3 * 1))
        await until(lambda: not sheet._home, driver)
        assert sheet._tab == PAGES.index("accounts")
        assert str(sheet.query_one("#asked", Label).content) == "Accounts"

        # The way across the top is the prompt, then `/settings`, then the page it is on.
        assert str(sheet.query_one("#crumb-1", Label).content) == "/settings"
        await driver.click("#crumb-1")
        await until(lambda: sheet._home, driver)
        assert listing.highlighted == 1

        # And the arrows across go in and come out as well, as a file manager's do -- on a
        # page with rows, since on an empty one the focus is on its buttons, which the arrows
        # across walk along instead.
        await driver.press("up", "right")
        await until(lambda: not sheet._home, driver)
        assert sheet._tab == PAGES.index("general")
        await driver.press("left")
        await until(lambda: sheet._home, driver)
        assert sheet._home


#: A `claude` that stops to ask before it answers, as the real one does when it reaches for
#: the tool that puts a question to a person: a control request on the same stream the turn is
#: read from, which the turn cannot get past until it is answered.
ASKING = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    print(json.dumps({"type": "control_request", "request_id": "req_1", "request": {
        "subtype": "can_use_tool", "tool_name": "AskUserQuestion", "tool_use_id": "t_1",
        "requires_user_interaction": True, "input": {"questions": [
            {"header": "Way", "question": "Which way?",
             "options": [{"label": "left"}, {"label": "right"}]}]}}}), flush=True)
    answered = json.loads(sys.stdin.readline())["response"]["response"]
    print(json.dumps({"type": "result", "result": json.dumps(answered)}), flush=True)
"""


@pytest.fixture
def asking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None) -> Path:
    """Puts a `claude` on PATH that stops to ask before it answers, and holds the runs here."""
    del hosting
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{ASKING}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(90)
async def test_an_agent_that_stops_to_ask_reaches_the_prompt(asking: Path) -> None:
    """The point of the prompt being here at all: a turn that needs a person can have one.

    Through the flow, which hangs its agent's question on whoever is outside the run -- as
    `chat` does -- and so through this prompt.
    """
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "chat", {"assistant": Runs("claude/m:high")})
        await driver.press(*"start")
        await driver.press("enter")
        # Waited for to its last option: the agent says the question as it stops to ask,
        # before the flow puts it to whoever is outside the run with what it offers.
        await until(lambda: "2. right" in transcript(app), driver)

        # The question and what it offers are shown, and the next line typed is the answer.
        assert "Which way?" in transcript(app)
        assert "left" in transcript(app)
        await driver.press(*"right")
        await driver.press("enter")
        await until(lambda: "updatedInput" in app._last_answer, driver)

        # Which reached the tool as its answer, against the question it was asked.
        assert json.loads(app._last_answer)["updatedInput"]["answers"] == {
            "Which way?": "right"
        }
        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(90)
async def test_away_means_the_agent_is_told_nobody_is_there_rather_than_waiting(
    asking: Path,
) -> None:
    """A question nobody is going to answer is a flow that has stopped, so it is refused."""
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "chat", {"assistant": Runs("claude/m:high")})
        assert (
            not app._afk
        )  # it starts off, so an agent may ask until you say otherwise
        await driver.press(*"/afk")
        await driver.press("enter")
        await until(lambda: app._afk, driver)  # as the runs say, which hold it

        await driver.press(*"start")
        await driver.press("enter")
        await until(lambda: bool(app._last_answer), driver)
        # And an outworlder that is away answers nothing, so the conversation is over too.
        await until(lambda: app._run is None, driver)

    # Nobody answered, so the tool was declined and the turn carried on from that.
    assert json.loads(app._last_answer)["behavior"] == "deny"


@pytest.mark.timeout(60)
async def test_ctrl_c_takes_back_the_line_and_never_the_interface() -> None:
    """The nearest thing there is to take back, and leaving is not one of them."""
    app = Humanize()
    async with app.run_test() as driver:
        from hmz.tui.app import Editor

        await driver.press(*"half a prompt")
        await driver.press("ctrl+c")
        await driver.pause()

        assert (
            app.query_one(Editor).text == ""
        )  # the line, and the interface is still up
        assert app.is_running

        await driver.press("ctrl+c")
        await driver.pause()

        assert app.is_running  # with nothing left to take back it stays up


@pytest.mark.timeout(60)
async def test_a_third_ctrl_c_does_not_wait_for_the_flow_to_unwind() -> None:
    """A flow told to stop goes in its own time, and the press after that does not wait.

    Every conversation still open is closed under its turn, which is the backend's process
    going: what the flow gets back is a turn that failed, exactly as it would have had the
    agent fallen over by itself. It is the last thing a key can do about a run.
    """
    app = Humanize()
    async with app.run_test() as driver:
        run = holding(app, "builder/1")
        told(app, event("builder/1", "begins"))
        link(app).answers["force"] = {"ok": True, "closed": 1}
        await driver.pause()

        await driver.press("ctrl+c")
        await driver.press("ctrl+c")
        await until(lambda: run.stopped, driver)
        assert app._run is None  # stopped, and still unwinding
        assert app._stopping == run.number
        assert not run.closed
        assert (
            "builder/1" in app._working
        )  # which is a turn nothing has reported the end of

        await driver.press("ctrl+c")
        await until(lambda: "closed 1 conversation" in transcript(app), driver)

        # Closed, whatever the stop came to: a backend that ignored one is the reason there
        # is a third press at all. And the run reads as over from here.
        assert run.closed
        assert app.is_running  # the run, rather than the interface
        assert app._stopping is None  # and nothing left for a fourth press to reach
        told(app, snapshot("sessions", run=run.number, open=[], working=[]))
        assert "builder/1" not in app._working  # as the runs say, once they have


@pytest.mark.timeout(60)
async def test_two_ctrl_c_leave_when_there_is_nothing_running() -> None:
    """Leaving is not what ctrl+c means anywhere else, so it is asked for twice here too."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press("ctrl+c")
        await driver.pause()

        assert app.is_running
        assert "press ctrl+c again to exit" in transcript(app)

        await driver.press("ctrl+c")
        await driver.pause()

        assert not app.is_running


@pytest.mark.timeout(60)
async def test_details_covers_the_thinking_as_well_as_the_tools() -> None:
    """One question -- how much of the working to show -- and so one switch.

    Off to begin with: a flow is watched to see where it has got to, and what the agents said
    is that. How each of them got there is asked for.
    """
    from hmz.runtime.settings import Settings

    app = Humanize()
    async with app.run_test() as driver:
        assert not app._details

        await details(app, driver)

        assert app._details  # at once, rather than from the next launch
        assert "thinking" in transcript(app)  # said to be part of the same switch

    # And remembered, so that the next launch opens showing it too.
    assert Settings().details
    app = Humanize()
    async with app.run_test():
        assert app._details


@pytest.mark.timeout(60)
async def test_what_a_turn_did_on_the_way_is_shown_only_where_it_is_asked_for() -> None:
    """The complaint this answers: a screen of tool rows, with the answer somewhere in it."""
    app = Humanize()
    async with app.run_test() as driver:
        told(app, opened("actor/1"))

        def turn() -> None:
            told(
                app,
                event("actor/1", "begins"),
                event("actor/1", "tool", "Read pyproject.toml"),
                event("actor/1", "reasoning", "thinking aloud"),
                event("actor/1", "text", "the answer"),
                event("actor/1", "ends"),
            )

        await asyncio.to_thread(turn)
        await until(lambda: "Worked for" in transcript(app), driver)

        shown = transcript(app)
        # What the flow is doing, and what it said: which agent is working, and its answer.
        assert "is working" in shown
        assert "the answer" in shown
        # And none of how it got there, which is what nobody asked to read.
        assert "pyproject.toml" not in shown
        assert "thinking aloud" not in shown

        await details(app, driver)
        await asyncio.to_thread(turn)
        await until(lambda: "thinking aloud" in transcript(app), driver)

        shown = transcript(app)
        assert "Read(pyproject.toml)" in shown
        assert "thinking aloud" in shown


@pytest.mark.timeout(60)
async def test_what_humanize_is_doing_about_a_turn_is_not_hidden_with_the_working() -> (
    None
):
    """A turn told to wait half a minute and a turn that has hung look the same from here.

    The line saying which it is was said as a tool call, so asking not to see every file read
    was asking not to be told a rate limit was being waited out either.
    """
    app = Humanize()
    async with app.run_test() as driver:
        told(app, opened("actor/1"))

        def turn() -> None:
            told(
                app,
                event("actor/1", "begins"),
                event("actor/1", "tool", "Read pyproject.toml"),
                event("actor/1", "notice", "waiting 30s for a rate limit"),
                event("actor/1", "ends"),
            )

        assert not app._details
        await asyncio.to_thread(turn)
        await until(lambda: "Worked for" in transcript(app), driver)

        shown = transcript(app)
        assert "waiting 30s for a rate limit" in shown
        # And still none of the working, which is the other half of the same switch.
        assert "pyproject.toml" not in shown


def test_a_backend_offers_what_it_last_said_it_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Read off the disk rather than asked for: asking is a coding agent starting up.

    What each backend runs is not written down anywhere -- `hmz.coganchor.models` asks it and keeps
    the answer -- so a prompt reads the answer and nothing else.
    """
    from hmz.coganchor import models
    from hmz.tui import discover

    kept = models.where("claude")
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(
        json.dumps(
            {
                "asked": "2026-08-12T00:00:00Z",
                "models": [{"name": "claude-nine", "efforts": ["max", "high"]}],
            }
        )
    )

    def program(command: str) -> str:
        return f"/usr/bin/{command}"

    monkeypatch.setattr(discover, "program", program)

    found = discover.installed()

    assert [model.name for model in found["claude"]] == ["claude-nine"]
    assert found["claude"][0].efforts == ("max", "high")
    # And a backend nobody has asked yet is a catalogue to fill rather than one with nothing
    # in it: the interface asks it as it opens, and the models sheet says which key asks it.
    assert found["codex"] == ()


#: A `claude` that answers each thing it is told with one result and nothing else, which is
#: what makes a conversation countable: one turn in, one turn out.
ANSWERING = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "heard " + said}), flush=True)
"""


@pytest.fixture
def talking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None) -> Path:
    """One `claude` on PATH, an interface that opens set up to talk to it, and runs held here."""
    del hosting
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{ANSWERING}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "hmz.tui.app.installed",
        lambda: {"claude": (Model("claude-opus-5", ("max", "high")),)},
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(60)
async def test_it_opens_ready_to_be_talked_to(talking: Path) -> None:
    """Nothing has to be picked first: a flow is what you reach for once one agent is not it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app._flow_named == "chat"
        # The first agent installed, at the first model it runs -- but never at the hardest
        # effort, which is a thing to ask for rather than to spend before anyone has.
        assert app._models == {"assistant": Runs("claude/claude-opus-5:high")}


@pytest.mark.timeout(60)
async def test_it_opens_saying_so_when_there_is_nothing_to_talk_to() -> None:
    """And still opens: an interface that would not start is worse than one that says why."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app._flow_named == "chat"
        assert app._models == {}
        assert app.is_running


@pytest.mark.timeout(90)
async def test_every_line_typed_between_turns_is_a_turn_of_one_conversation(
    talking: Path,
) -> None:
    """The whole of what was asked for: saying something is all it takes, twice over."""

    def asking() -> str:
        """What the flow is waiting to be told what next about, which is what it answered."""
        return next((str(one["text"]) for one in app._pending), "")

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        # The turn is over and the flow is waiting to be told the next one, rather than gone.
        await until(lambda: asking() == "heard first", driver)
        assert app._waits_on() == "you"

        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: asking() == "heard second", driver)
        assert "second" in transcript(app)  # an answer, drawn as the runs said it was

        # One session: the second turn was taken in the first's conversation rather than in
        # another, so the agent had the first in context.
        (seen,) = app._seen.values()
        assert seen.id == "assistant"
        assert len(seen.idents) == 1
        # And nothing is left pinned above the prompt: a flow waiting to be told something
        # takes what was typed at once, so it was said rather than held.
        assert not app.query_one("#queued", Static).has_class("waiting")
        assert app._queued == []

        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"dsh": (Model("deepseek-v4-flash", ("max", "high", "off")),)},
)
def test_deepseek_with_a_local_key_can_be_the_chat_default(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "dsh-home"))

    app = Humanize()

    assert app._models == {"assistant": Runs("dsh/deepseek-v4-flash:high")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"dsh": (Model("deepseek-v4-flash", ("max", "high", "off")),)},
)
async def test_deepseek_chat_sends_hello_and_draws_the_sdk_reply(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
    monkeypatch: pytest.MonkeyPatch,
    hosting: None,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    session_id = "session-chat"
    message_id = "message-chat"
    subscription = unittest.mock.MagicMock()
    subscription.__enter__.return_value = subscription
    subscription.next.side_effect = [
        SimpleNamespace(
            method="session.event",
            payload={
                "sessionId": session_id,
                "event": {
                    "type": "agent/inbox/spliced",
                    "data": {"inserted": [{"id": message_id}]},
                },
            },
        ),
        SimpleNamespace(
            method="session.event",
            payload={
                "sessionId": session_id,
                "event": {
                    "type": "assistant/message",
                    "data": {
                        "turn": 1,
                        "step": 1,
                        "message": {
                            "content": [{"type": "text", "text": "hello from DeepSeek"}]
                        },
                        "usage": {},
                    },
                },
            },
        ),
        SimpleNamespace(
            method="session.event",
            payload={
                "sessionId": session_id,
                "event": {
                    "type": "turn/end",
                    "data": {"turn": 1, "reason": {"kind": "completed"}},
                },
            },
        ),
        SimpleNamespace(
            method="session.status",
            payload={"sessionId": session_id, "status": "idle"},
        ),
    ]
    client = unittest.mock.MagicMock()
    client.subscribe_session_notifications.return_value = subscription
    client.session_prompt.return_value = message_id
    harness = unittest.mock.MagicMock()
    harness.client = client

    def running(_session: DshSession) -> unittest.mock.MagicMock:
        return harness

    monkeypatch.setattr(DshSession, "_running", running)
    monkeypatch.setattr(
        "hmz.coganchor.agents.dsh.uuid.uuid4", lambda: SimpleNamespace(hex="chat")
    )

    # Installed as far as the engine asks too, which looks for it on its own: a machine
    # without dsh would otherwise refuse the turn before the runtime above is reached.
    def found(command: str) -> str:
        return command

    monkeypatch.setattr("hmz.coganchor.backends.program", found)

    app = Humanize(agents={"assistant": Runs("dsh/deepseek-v4-flash:high")})
    async with app.run_test() as driver:
        await driver.press(*"hello")
        await driver.press("enter")
        await until(lambda: "hello from DeepSeek" in transcript(app), driver)

        sent = client.session_prompt.call_args
        assert sent.args[1] == [{"type": "text", "text": "hello"}]
        assert sent.kwargs["notification_subscription"] is subscription

        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(90)
async def test_a_flow_waiting_to_be_told_something_can_still_be_stopped(
    talking: Path,
) -> None:
    """A key has to reach a flow doing nothing at all, or nothing ever releases it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        await until(lambda: app._waits_on() == "you", driver)  # with no turn open

        await driver.press("ctrl+c")
        await driver.press("ctrl+c")
        await until(lambda: app._run is None and app._stopping is None, driver)

        # And the run is written down as stopped rather than as one that finished.
        (epic,) = epics(talking)
        assert recorded(epic)[-1] == {
            "event": "ended",
            "at": unittest.mock.ANY,
            "how": "stopped",
        }


@pytest.mark.timeout(60)
async def test_clearing_the_screen_clears_the_screen_and_nothing_else(
    talking: Path,
) -> None:
    """There is nothing else to clear: no turn carries context across an epic."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"remember this")
        await driver.press("enter")
        await until(
            lambda: "remember this" in transcript(app) and app._run is not None, driver
        )

        await driver.press(*"/clear")
        await driver.press("enter")
        await until(lambda: "remember this" not in transcript(app), driver)

        # The screen, and only the screen: what was set up to run is still set up to run,
        # and what is running is still running.
        assert app._flow_named == "chat"
        assert app._models == {"assistant": Runs("claude/claude-opus-5:high")}
        # The flow the first line started was not stopped with the screen.
        assert app._run is not None

        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


@pytest.mark.timeout(60)
async def test_looking_at_the_flows_and_walking_out_changes_nothing(
    talking: Path,
) -> None:
    """Tab is pressed to see what there is, and seeing must not cost what was set up."""
    app = Humanize()
    async with app.run_test() as driver:
        was = (app._flow_named, dict(app._models))

        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flows), driver)

        assert (app._flow_named, app._models) == was


@pytest.mark.timeout(60)
async def test_a_hidden_file_beside_the_flows_is_not_one_of_them(
    tmp_path: Path,
) -> None:
    """A `._lx.py` a macOS tarball left behind, or a flow hidden by a dot, is listed as nothing.

    No name may start with a dot, so offering one would be offering what `-f` refuses -- and
    the menu that reads the name back would fall over on it.
    """
    flows = tmp_path / ".hmz" / "flows"
    written(flows, "lx", FLOW)
    (flows / "._lx.py").write_text(FLOW)
    (flows / ".old").mkdir()
    (flows / ".old" / "__init__.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)

        mine = [one for one in rows(app) if one.startswith("@local/")]
        assert mine == ["@local/lx"]


@pytest.mark.timeout(60)
async def test_it_is_drawn_in_the_terminals_own_colours() -> None:
    """Nothing here is a colour of ours, so there is nothing to read off the terminal.

    A scheme of our own is a guess about the background it lands on, and that guess is what a
    black interface in a white terminal is.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app.current_theme.ansi  # so ANSI reaches the terminal unconverted
        assert app.native_ansi_color
        # Every surface is the terminal's own, which is what leaves it showing through.
        for surface in ("background", "surface", "panel", "foreground"):
            assert app.theme_variables[surface] in ("transparent", "ansi_default")
        # Except where the cursor is, which is the one thing that must not be left to the
        # terminal: a row that says it is under the cursor by being a shade of the background
        # says it to nobody. Both ends of that pair are named, so it carries its own contrast.
        for end in ("block-cursor-background", "block-cursor-foreground"):
            assert app.theme_variables[end] != "ansi_default"


@pytest.mark.timeout(60)
async def test_a_theme_asked_for_is_the_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Following the terminal is the default and not the rule: `TEXTUAL_THEME` still wins."""
    monkeypatch.setenv("TEXTUAL_THEME", "gruvbox")
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app.theme == "gruvbox"


def test_the_terminal_theme_names_no_colour_of_its_own() -> None:
    """Every colour in it is one of the sixteen the terminal already has a setting for."""
    from hmz.tui.app import _TERMINAL

    named = [
        _TERMINAL.primary,
        _TERMINAL.secondary,
        _TERMINAL.accent,
        _TERMINAL.warning,
        _TERMINAL.error,
        _TERMINAL.success,
        _TERMINAL.foreground,
        _TERMINAL.background,
        _TERMINAL.surface,
        _TERMINAL.panel,
        _TERMINAL.boost,
        *(
            value
            for name, value in (_TERMINAL.variables or {}).items()
            if not name.endswith("text-style")
        ),
    ]
    assert named  # or this checks nothing
    assert all(colour and colour.startswith("ansi_") for colour in named), named


@pytest.mark.timeout(60)
async def test_a_turn_reads_the_way_claude_code_renders_one() -> None:
    """What you said behind `❯`, what the agent said on the bullet, and a line closing it.

    Which is Claude Code's own shape, read off its own screen: no bars, no boxes, nothing
    indented -- every line starts where the terminal does.
    """
    app = Humanize()
    async with app.run_test() as driver:
        told(
            app, opened("actor/1")
        )  # so the conversation it opens is one there is to read
        app._said_by_you("do the thing")

        app._details = True  # so that a tool row is one of the parts there are to draw

        # From a thread of its own, as a turn always says things: `_heard` hands them to the
        # event loop, which it may only do from somewhere that is not the event loop.
        def turn() -> None:
            told(
                app,
                event("actor/1", "begins"),
                event("actor/1", "tool", "Bash git status"),
                event("actor/1", "text", "one\ntwo"),
                event("actor/1", "ends"),
            )

        await asyncio.to_thread(turn)
        await until(lambda: "Worked for" in transcript(app), driver)

        shown = transcript(app)

    assert "❯ do the thing" in shown  # what you said
    assert "is working" in shown  # which agent has the turn, said as it starts
    # The bullet is the terminal's rather than ours -- one system draws a different glyph --
    # so it is asked for by the same name the interface draws it under.
    assert f"{_SAID} Bash(git status)" in shown  # a tool, its argument in brackets
    assert f"{_SAID} one" in shown
    assert "\n  two" in shown
    assert "✻ Worked for" in shown  # and the line Claude Code closes a turn with


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max", "high", "low")),),
        "codex": (Model("gpt-5.6-sol", ("xhigh",)),),
    },
)
async def test_what_an_agent_runs_is_a_row_of_its_own_and_an_effort_is_picked(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """One sheet per agent, a row per thing it is, rather than a walk of a sheet apiece.

    The CLI settles which models there are, so the models are opened from a row under it and
    are that CLI's own rather than every model there is.
    """
    from textual.geometry import Offset

    from hmz.tui.dropdown import Dropdown, anchor

    app = Humanize()
    async with app.run_test() as driver:
        # Walked into the way it is walked into: a flow, then what each of its agents is.
        await into_flows(app, driver)
        await into_agent(app, driver)
        assert rows(app) == ["cli", "provider", "model", "effort"]
        # Saved from the button under them, which nothing changed yet gives nothing to do.
        assert bar(app) == [_ACT_SAVE]
        assert app.screen.query_one(f"#act-{_ACT_SAVE}", Button).disabled

        # The CLIs installed here, opened from the row that says which one it is.
        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        assert rows(app) == ["claude", "codex"]
        assert "kimi" not in rows(app)  # not installed, so not offered
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        # And under it that CLI's models, and a button that asks it again what they are.
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        assert rows(app) == ["claude-opus-5"]
        assert _ACT_AGAIN in bar(app)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        # The effort is picked from the ones the model takes, dropped under its row.
        sheet = app.screen
        await onto(app, driver, "effort")
        listing = sheet.query_one("#choices", OptionList)

        def effort() -> str:
            at = rows(app).index("effort")
            return str(listing.get_option_at_index(at).prompt)

        # It opens on what the agent runs, which is not the hardest thing there is: that is
        # the one to reach for, and this is the one to spend before anybody asked for it.
        assert "high" in effort()
        assert "▾" in effort()
        # A click on the row drops them, hardest first, with the cursor on the one in force;
        # a click on one takes it.
        await driver.click(offset=anchor(listing) + Offset(8, 0))
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        values = app.screen.query_one(OptionList)
        assert [str(one.id) for one in values.options] == ["=max", "=high", "=low"]
        assert values.highlighted == 1
        await driver.click(values, offset=(2, 1))
        await until(lambda: app.screen is sheet, driver)
        assert "max" in effort()
        # And the keys do the same: enter drops, the arrows walk, enter takes.
        await picks(app, driver, "effort", "high")
        assert "high" in effort()

        await keeps(app, driver)  # out of the agent, holding it
        await keeps(app, driver)  # and out of the menu, saving the lot

    assert app._models == {"assistant": Runs("claude/claude-opus-5:high")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max", "high")),),
        "codex": (Model("gpt-5.6-sol", ("xhigh",)), Model("gpt-5.5", ("high",))),
    },
)
async def test_changing_the_cli_lets_go_of_the_model_that_belonged_to_the_last_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """A model belongs to the CLI that runs it, so it cannot survive the CLI changing.

    Which is why the rows are in the order they are in: the CLI settles which models there
    are to choose between, and the account settles which of them that CLI will name.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await driver.press("down")  # codex
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # The models of the CLI that was chosen, and no others -- the cursor on the first
        # of them, the one this agent ran having gone with the CLI it belonged to.
        assert rows(app) == ["gpt-5.6-sol", "gpt-5.5"]
        assert under(app) == "gpt-5.6-sol"

        await driver.press("down")  # the second of that CLI's models
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    assert app._models == {"assistant": Runs("codex/gpt-5.5:high")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max",)),),
        "dsh": (
            Model("deepseek-v4-flash", ("max", "high", "off")),
            Model("deepseek-v4-pro", ("max", "high", "off")),
        ),
    },
)
async def test_deepseek_is_selectable_from_agents(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    dsh_home = tmp_path / "dsh-home"
    dsh_home.mkdir()
    (dsh_home / ".credentials.yaml").write_text("DEEPSEEK_API_KEY: saved-key\n")
    (dsh_home / ".credentials.yaml").chmod(0o600)
    (dsh_home / "settings.yaml").write_text(
        "llm-deepseek:\n  baseURL: https://deepseek.example/v1\n"
    )
    monkeypatch.setenv("DSH_HOME", str(dsh_home))
    goal = tmp_path / "goal.py"
    goal.write_text(
        """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import GoalCommandAgentMixin, flow


class Worker(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    worker: Worker


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def goal(task: str, *, agents: Agents, envs: EnvCollection, params: FlowParams,
               ctx: FlowContext) -> None:
    pass
"""
    )
    app = Humanize(flow=str(goal), agents={"worker": Runs("claude/claude-opus-5:max")})
    app._budget = Budget(cost=1)
    async with app.run_test() as driver:
        # Opened on the flow by its path, which is a flow of nobody's list: its one role
        # runs `/goal`, which DeepSeek's harness serves.
        await driver.press(*f"/flow {goal}")
        await driver.press("enter")
        await into_agent(app, driver)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await onto(app, driver, "dsh")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        # The account it runs as, whose first row is always the machine's own.
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        assert rows(app) == [""]
        assert _ACT_ADD in bar(app)
        assert "as local" in reads(app, 0)
        assert "saved by dsh" in reads(app, 0)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        await until(lambda: "deepseek-v4-flash" in rows(app), driver)
        assert rows(app) == ["deepseek-v4-flash", "deepseek-v4-pro"]

        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    assert app._models == {"worker": Runs("dsh/deepseek-v4-pro:max")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "dsh": (
            Model("deepseek-v4-flash", ("max", "high", "off")),
            Model("deepseek-v4-pro", ("max", "high", "off")),
        ),
        "kimi": (Model("kimi-code/k3", ("max", "high")),),
    },
)
async def test_deepseek_has_its_own_ways_after_switching_from_kimi(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor import providers

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    providers.add("kimi", "subscription", way="login")
    app = Humanize(agents={"assistant": Runs("kimi/kimi-code/k3:high")})
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        # Look at Kimi's accounts first, then come back to dsh as the failing walk does.
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        assert "subscription" in rows(app)
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await onto(app, driver, "dsh")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        assert rows(app) == [""]
        assert "saved by dsh" in reads(app, 0)

        await onto(app, driver, _ACT_ADD)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Signing), driver)
        sheet = cast("Signing", app.screen)
        form = app.screen.query_one("#choices", OptionList)
        # No question of which CLI -- it is the one the agent is on -- and only dsh's own
        # ways in, stepped where they stand.
        assert rows(app)[:3] == ["way", "name", "DEEPSEEK_API_KEY"]
        assert list(sheet.choices("way")) == ["key", "gateway"]
        shown = " ".join(
            [
                str(app.screen.query_one("#asked", Label).content),
                str(app.screen.query_one("#about", Label).content),
                *(str(option.prompt) for option in form.options),
            ]
        ).lower()
        for stale in ("kimi", "subscription", "login"):
            assert stale not in shown

        await changes(app, driver, "name", *"mine")
        await onto(app, driver, "DEEPSEEK_API_KEY")
        await driver.press("enter")
        await driver.pause()
        form.post_message(events.Paste("test-key\n"))
        await driver.pause()
        await driver.press("enter")
        # A DeepSeek key is a DeepSeek key wherever it is held, so the form asks which other
        # backends to write it down for as well -- none, where none is installed. The last
        # question kept, what the keys are on is the button that answers the form.
        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")

        # Making one here is choosing it, so what comes back is the agent with it on.
        await until(lambda: isinstance(app.screen, Agent), driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    made = providers.find("dsh", "mine")
    assert made is not None
    assert made.way == "key"
    assert made.env == {"DEEPSEEK_API_KEY": "test-key"}
    assert app._models == {"assistant": Runs("dsh/deepseek-v4-flash:max", "mine")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max",)),)},
)
@unittest.mock.patch(
    "hmz.tui.app.installable",
    return_value={
        "dsh": (
            Model("deepseek-v4-flash", ("max", "high", "off")),
            Model("deepseek-v4-pro", ("max", "high", "off")),
        )
    },
)
async def test_agents_says_how_to_install_deepseek_when_its_sdk_is_missing(
    _installable: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- patch hands it over
) -> None:
    app = Humanize(agents={"assistant": Runs("claude/claude-opus-5:max")})
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await onto(app, driver, "dsh")
        installing = reads(app, rows(app).index("dsh"))
        assert "DeepSeek Harness is not installed" in installing
        assert "uv pip install --python" in installing
        assert "deepseek-harness-sdk" in installing

        await drops(app, driver)
        await until(lambda: isinstance(app.screen, Agent), driver)
        await drops(app, driver)
        await drops(app, driver)

    assert app._models == {"assistant": Runs("claude/claude-opus-5:max")}


def test_deepseek_install_hint_targets_the_python_running_humanize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.tui import pick

    monkeypatch.setattr("hmz.tui.pick.sys.executable", "/opt/hmz/bin/python")

    assert "uv pip install --python /opt/hmz/bin/python" in pick._installing("dsh")


def test_kimi_install_hint_names_what_is_missing_rather_than_the_cli() -> None:
    """The CLI is what got it into the list, so what it is short of is the package."""
    from hmz.tui import pick

    installing = pick._installing("kimi")

    assert "Kimi Code is installed" in installing
    assert "websockets>=15,<18" in installing


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max",)), Model("claude-sonnet-5", ("max",)))
    },
)
async def test_one_cli_is_still_a_row_that_is_opened_and_answered(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """One backend is one row in the list, rather than a question that is skipped."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        assert rows(app) == ["claude"]
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        models = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(models.options), driver)
        assert rows(app) == ["claude-opus-5", "claude-sonnet-5"]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max", "high")),),
        "codex": (Model("gpt-5.6-sol", ("xhigh",)),),
    },
)
async def test_a_search_is_asked_for_and_left_rather_than_being_what_typing_does(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """The letters only search once a search is asked for, with its button or with `/`.

    And they go into a box of their own above the list, which is where they are seen going.
    """
    from hmz.coganchor import providers

    providers.add("claude", "deepseek", way="key", env={"ANTHROPIC_API_KEY": "k"})
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "provider")
        await until(lambda: isinstance(app.screen, Accounts), driver)
        sheet = cast("Accounts", app.screen)
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        await driver.press(*"deep")  # typing at the list is not searching it
        await driver.pause()
        assert not sheet._searching
        assert rows(app) == ["", "deepseek"]

        await onto(app, driver, _ACT_SEARCH)
        await driver.press("enter")
        await driver.pause()
        assert sheet._searching
        assert isinstance(sheet.focused, Input)
        await driver.press(*"deep")
        await driver.pause()
        assert rows(app) == ["deepseek"]

        # And esc comes out of the search rather than out of the sheet.
        await driver.press("escape")
        await driver.pause()
        assert not sheet._searching
        assert sheet._typed == ""
        assert app.screen is sheet
        assert rows(app) == ["", "deepseek"]

        # `/` asks for it from the list as well, and esc leaves it the same way.
        await driver.press("/")
        await driver.pause()
        assert sheet._searching
        await driver.press("escape")
        await driver.pause()
        assert not sheet._searching
        assert app.screen is sheet


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (
            Model("claude-sonnet-4-5", ("max",)),
            Model("claude-opus-5", ("max",)),
            Model("claude-sonnet-5", ("max",)),
        )
    },
)
async def test_a_model_typed_out_whole_is_found_above_one_that_only_holds_its_letters(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """`claude-sonnet-5` is spread through `claude-sonnet-4-5`, and is not what was meant.

    Found under real load: the search found both and left them in the order the CLI listed
    them, so the model typed out exactly came second and enter took the other one.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        sheet = cast("Catalogue", app.screen)
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await onto(app, driver, _ACT_SEARCH)
        await driver.press("enter")
        await driver.press(*"claude-sonnet-5")
        await driver.pause()
        assert rows(app)[:2] == ["claude-sonnet-5", "claude-sonnet-4-5"]

        # The start of a name comes before letters spread through one, and rows equally near
        # keep the order they were listed in.
        await driver.press(*["backspace"] * len("claude-sonnet-5"), *"sonnet")
        await driver.pause()
        assert rows(app)[:2] == ["claude-sonnet-4-5", "claude-sonnet-5"]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("ultracode", "max", "high")),),
        "kimi": (Model("kimi-code/k3", ("max", "low"), swarms=True),),
    },
)
async def test_a_turn_is_said_to_run_hard_and_said_to_run_wide_separately(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Claude's ultracode is an effort; Kimi's swarm mode is a second thing, so it is a key.

    How hard a turn thinks and how wide it runs are not two ends of one dial: a swarm at low
    effort is a real thing to ask for, and a list that mixed them could not say it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        # Claude opens on ultracode, which is the hardest thing it takes, and has no swarm.
        listing = app.screen.query_one("#choices", OptionList)

        def shown(held: str) -> str:
            return str(listing.get_option_at_index(rows(app).index(held)).prompt)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        listing = app.screen.query_one("#choices", OptionList)
        # Claude's hardest is an effort like any other, picked from the same list.
        await picks(app, driver, "effort", "ultracode")
        assert "ultracode" in shown("effort")
        assert "swarm" not in rows(app)  # nothing to turn on, so no row saying so

        # Kimi has one, which is a row of its own rather than a rung of the effort.
        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await onto(app, driver, "kimi")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: "swarm" in rows(app), driver)
        assert "off" in shown("swarm")

        await picks(app, driver, "swarm", "on")
        assert "on" in shown("swarm")
        await picks(app, driver, "effort", "low")  # and still on at another effort
        assert "low" in shown("effort")
        assert "on" in shown("swarm")

        await keeps(app, driver)
        await keeps(app, driver)

    # One turn, at one effort, run wide -- which is how Kimi is asked for a fleet.
    assert app._models == {"assistant": Runs("kimi/kimi-code/k3:swarmlow")}


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={
        "claude": (
            Model("claude-opus-5", ("high",)),
            Model("claude-haiku-4-5", ("high",)),
        ),
        "codex": (Model("gpt-5.6-sol", ("high",)),),
    },
)
async def test_a_list_too_long_to_walk_is_narrowed_by_typing_at_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """Every model of every CLI is longer than a screen, so the letters go into it."""
    for name in ("chatter", "chatty", "loop"):
        written(tmp_path / ".hmz" / "flows", name, FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        listing = sheet.query_one("#choices", OptionList)

        # This project's own flows, there being more than one of those to narrow.
        def flows() -> list[str]:
            return [one for one in rows(app) if one.startswith("@local/")]

        await until(lambda: len(flows()) == 3, driver)
        every = listing.option_count

        await driver.press("slash")
        await driver.press("c", "h", "a", "t", "t", "e")
        await driver.pause()
        assert flows() == ["@local/chatter"]

        await driver.press("backspace")  # and one letter back is a wider list again
        await driver.pause()
        # `chatty` is in it too, which the last letter had ruled out.
        assert len(flows()) > 1

        await driver.press("z", "z")  # narrowed to nothing rather than to everything
        await driver.pause()
        assert not flows()

        await driver.press("escape")  # which esc steps back out of before it leaves
        await driver.pause()
        assert listing.option_count == every
        assert isinstance(app.screen, Flows)
        await onto(app, driver, flows()[0])

        # Spread through the name in order, rather than a prefix: `hk` finds `claude-haiku`.
        await into_agent(app, driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        await onto(app, driver, _ACT_SEARCH)
        await driver.press("enter")
        await driver.press("h", "k")
        await driver.pause()

        assert rows(app) == ["claude-haiku-4-5"]


@pytest.mark.timeout(60)
async def test_the_cursor_can_be_seen_in_the_lists_that_are_chosen_from() -> None:
    """A list you cannot see the cursor in is one you choose from blind.

    Every menu fills the row under the cursor, as `/settings` does, rather than marking it
    with a character beside it -- so what is checked is what is drawn: the cursor's colours
    are on the row the cursor is on and on no other.
    """
    app = Humanize()
    async with app.run_test() as driver:
        # Two CLIs to choose between, which a list of them always has, whatever ran here.
        await app.push_screen(
            Clis(
                {
                    "claude": (Model("claude-opus-5", ("high",)),),
                    "codex": (Model("gpt-5.5", ("high",)),),
                },
                "claude",
            )
        )
        await until(lambda: isinstance(app.screen, Clis), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: len(listing.options) > 1, driver)
        await until(lambda: listing.has_focus, driver)

        def filled() -> list[int]:
            """The rows drawn in the cursor's colours, by where each is in the list."""
            cursor = listing.get_component_rich_style("option-list--option-highlighted")
            starts = listing._index_to_line
            drawn = [
                round(listing.scroll_offset.y) + y
                for y in range(listing.size.height)
                if any(
                    one.style is not None and one.style.bgcolor == cursor.bgcolor
                    for one in listing.render_line(y)
                )
            ]
            return sorted(
                {max(at for at, line in starts.items() if line <= y) for y in drawn}
            )

        assert listing.has_focus  # and so in the colours of a cursor that has the keys
        assert filled() == [listing.highlighted]

        await driver.press("down")
        await driver.pause()
        assert filled() == [listing.highlighted]


async def _away(app: Humanize, driver: Pilot[None], line: str) -> dict[str, object]:
    """Types an `/afk` line, and has the runs say it is so, as a host holding them would.

    Away is the runs' to hold rather than the interface's, so what the line does is ask; what
    the status line then says is what the runs answer with, which is told back here: the one
    role it names, or every role with none claimed -- which is all a fake end of them has.

    Args:
      app: The interface.
      driver: What is pumping it.
      line: What is typed.

    Returns:
      What was asked, without the role where it named none.
    """
    before = len(link(app).asked_for("afk"))
    await driver.press(*line)
    await driver.press("enter")
    await until(lambda: len(link(app).asked_for("afk")) > before, driver)
    said = dict(link(app).asked_for("afk")[-1])
    role, on = str(said.get("role") or ""), bool(said["on"])
    if role:
        told(app, snapshot("away", all=app._afk, of={**app._afk_of, role: on}))
    else:
        told(app, snapshot("away", all=on, of={}))
        said.pop("role", None)
    return said


@pytest.mark.timeout(60)
async def test_a_switch_takes_on_and_off_as_well_as_being_flipped() -> None:
    """A toggle is what you reach for; `on` is what you write down and replay."""
    app = Humanize()
    async with app.run_test() as driver:
        for said, want in (("/afk on", True), ("/afk on", True), ("/afk", False)):
            assert await _away(app, driver, said) == {"do": "afk", "on": want}, said
            assert app._afk is want, said

        await driver.press(*"/afk sideways")
        await driver.press("enter")
        await driver.pause()
        assert app._afk is False  # unchanged, and said so rather than guessed at
        assert len(link(app).asked_for("afk")) == 3  # and nothing asked of the runs
        assert "expected 'on' or 'off'" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_status_line_says_which_modes_this_is_in() -> None:
    """A mode that decides whether an agent may stop and ask you is one you must be able to see.

    Both switches say which way they went once, in the transcript, and that line has scrolled
    away by the time an agent wants a person -- and what happens then is a question nobody is
    ever put. So the line that says what is going on says which mode this is in while it is
    in it, and says nothing once it is not.
    """
    app = Humanize()
    async with app.run_test() as driver:
        status = str(app.query_one("#status", Static).content)
        assert "afk" not in status  # nothing to say while an agent may ask

        await _away(app, driver, "/afk")
        assert "afk" in str(app.query_one("#status", Static).content)

        await details(app, driver)
        status = str(app.query_one("#status", Static).content)
        assert "afk" in status
        assert "details" in status

        await _away(app, driver, "/afk off")
        status = str(app.query_one("#status", Static).content)
        assert "afk" not in status
        assert "details" in status  # the other switch is left where it was


@pytest.mark.timeout(60)
async def test_the_marker_is_where_a_narrow_terminal_cannot_take_it_away() -> None:
    """A marker that falls off a small screen is a marker nobody has.

    The keys on the right are dropped one at a time to make room, and what is running and
    where it is running can fill a narrow row on their own -- so the modes go in front of
    both, which is the one place on this line that is always drawn.
    """
    from textual.content import Content

    app = Humanize()
    async with app.run_test(size=(40, 12)) as driver:
        app._afk = True
        app._draw()
        await driver.pause()

        # As drawn rather than as written: what takes up the columns of a row this narrow is
        # the text, and the markup naming its colours is not part of it.
        drawn = str(Content.from_markup(str(app.query_one("#status", Static).content)))

        assert drawn.startswith("afk")  # ahead of the flow, the directory and the keys


@pytest.mark.timeout(60)
async def test_afk_is_one_outworlder_on_its_own_transcript_and_every_one_elsewhere() -> (
    None
):
    """Each outworlder is its own person to be away as; where all of them are, it is all."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human", "guide"])

        async def send(line: str) -> None:
            await driver.press(*line)
            await driver.press("enter")
            await driver.pause()

        app._now_reading("outworlder:guide")
        assert await _away(app, driver, "/afk on") == {
            "do": "afk",
            "on": True,
            "role": "guide",
        }
        assert app._away("guide")
        assert not app._away("human")
        assert "afk guide" in str(app.query_one("#status", Static).content)

        app._now_reading("")
        assert await _away(app, driver, "/afk on") == {"do": "afk", "on": True}
        assert app._away("guide")
        assert app._away("human")
        assert await _away(app, driver, "/afk") == {"do": "afk", "on": False}
        assert not app._away("guide")
        assert not app._away("human")

        # And not on one agent's, which asks nobody anything: it is not offered there, and
        # typed out anyway it says where it works rather than doing something.
        app._now_reading("builder/1")
        await driver.press(*"/af")
        await driver.pause()
        assert not app.query_one("#offers", OptionList).has_class("offering")
        app.query_one(Editor).text = ""
        await send("/afk on")
        assert not app._away("human")
        assert "/afk is only available on" in transcript(app)
        assert len(link(app).asked_for("afk")) == 3  # nothing asked of the runs for it


def test_the_commands_are_offered_in_alphabetical_order() -> None:
    """The one order a list of commands has that a reader can predict."""
    from hmz.tui.complete import offered

    offers = offered("/", _COMMANDS)

    assert offers == sorted(offers)
    assert "/help" not in offers  # the bottom bar says what the keys are


#: A `claude` that answers each thing it is told the way the real one does: the words as it
#: says them, and then the same words again as the answer the turn settles on. Two answers
#: for two things said, which is what makes a reply counted twice countable.
TWICE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
heard = []
for line in sys.stdin:
    heard.append(json.loads(line)["message"]["content"][0]["text"])
    if len(heard) == 1:
        # Still working, so a second thing said lands inside this same turn.
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working"}]}}), flush=True)
        continue
    for said in heard:
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "answer to " + said}]}}), flush=True)
        print(json.dumps({"type": "result", "result": "answer to " + said}), flush=True)
"""


@pytest.mark.timeout(90)
async def test_two_things_said_get_two_answers_and_not_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None
) -> None:
    """A turn says its answer as it says it and again as it settles; one of those is enough.

    Passing both on showed every mid-turn answer twice, so saying two things read as three
    replies -- which is the whole of what is being checked here.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{TWICE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "hmz.tui.app.installed",
        lambda: {"claude": (Model("claude-opus-5", ("high",)),)},
    )
    monkeypatch.chdir(tmp_path)

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        # The turn will not end until it has been told something else, so this cannot race.
        await until(lambda: bool(app._seen), driver)
        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: "answer to second" in transcript(app), driver)
        await driver.pause()

        shown = transcript(app)
        assert shown.count("answer to first") == 1
        assert shown.count("answer to second") == 1

        app.action_stop_flow()
        await until(lambda: app._run is None and app._stopping is None, driver)


def test_the_offers_say_what_each_command_takes() -> None:
    """A switch takes `on` or `off` as well as being flipped, and only the list says so."""
    for one in _COMMANDS:
        assert one.about, one.name  # or it is offered with nothing said about it

    assert _BY_NAME["afk"].takes == "[on|off]"
    assert _BY_NAME["exit"].takes == ""  # a command that takes nothing says nothing


@pytest.mark.timeout(60)
async def test_taking_an_offer_types_the_command_and_not_its_arguments() -> None:
    """The brackets say what may be written; they are not themselves something to write."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/af")
        await driver.pause()
        await driver.press("tab")
        await driver.pause()

        assert app.query_one(Editor).text == "/afk "  # not `/afk [on|off]`


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_the_box_at_the_top_says_what_this_is_and_not_what_is_set_up(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """The name, the version, what humanize is, where this is, and how to begin.

    Not what is set up to run: the transcript is append-only, so a line written into it is a
    line about the moment it was written, and a copy of the setup up there could only ever be
    the copy that was true when the interface opened. It is on the two lines round the editor
    instead, which are redrawn twice a second.
    """
    from importlib.metadata import metadata

    app = Humanize()
    async with app.run_test() as driver:
        opened = transcript(app)
        assert "humanize v" in opened
        assert str(metadata("hmz")["Summary"]) in opened  # what it was published as
        assert "claude/claude-opus-5" not in opened
        assert (
            _where() not in opened
        )  # where it works is on the status line, and only there

        # And another flow leaves the box alone, there being nothing in it to correct. What
        # is set up is on the two lines round the editor: the agents above it, the flow on
        # the status line under it.
        app._flow_named = "ralph_loop"
        app._draw()
        await driver.pause()

        assert transcript(app) == opened
        assert "claude/claude-opus-5:high" in str(
            app.query_one("#above", Static).content
        )
        # The flow, and beside it the directory it would run in.
        status = str(app.query_one("#status", Static).content)
        assert app._flow_named in status
        assert _where() in status


#: A flow that settles what only a person can settle, in the model it is going to run on.
QUESTIONNAIRE = '''
"""Ask the person, in a shape."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv
from hmz.flows import Outworlder, flow


class Agents(AgentCollection):
    """Nobody but the person."""

    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


class Settled(BaseModel):
    """What has to be settled before anything runs."""

    model_config = {"extra": "forbid"}

    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")


@flow(agents=Agents, envs=Envs, params=FlowParams, name="flow")
async def run(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
              ctx: FlowContext) -> None:
    human = agents["human"]
    session = await human.spawn(env=envs["workspace"])
    settled = await human.run(task, session=session, output_schema=Settled)
    Path("settled.json").write_text(settled.model_dump_json())
'''


@pytest.mark.timeout(90)
async def test_the_person_asked_for_a_shape_is_asked_a_question_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None
) -> None:
    """A flow settles what only a person can settle, in the model it is going to run on.

    Whoever is outside the run is asked for it, so the interface shows each field as a
    question with what it will take under it, and the next line typed is the answer.
    """
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", QUESTIONNAIRE)
    app = Humanize()
    async with app.run_test() as driver:
        # As `/flow` sets it: the flow, and no agent role -- the only one it has is the
        # person, and nobody chooses who that is.
        set_up(app, "./flow", {})
        await driver.press(*"how should I do this")
        await driver.press("enter")

        # The flow's own words above the first field, and the answers it will take under it.
        await until(
            lambda: "Which way should this be built?" in transcript(app), driver
        )
        assert "how should I do this" in transcript(app)
        assert "careful" in transcript(app)
        await driver.press(*"careful")
        await driver.press("enter")

        await until(lambda: "Write tests for it?" in transcript(app), driver)
        await driver.press(*"yes")
        await driver.press("enter")

        # The one with a default says what to type to leave it, and what that will take.
        await until(lambda: "How many rounds" in transcript(app), driver)
        assert "`-` for 3" in transcript(app)
        await driver.press("-")
        await driver.press("enter")

        await until((tmp_path / "settled.json").exists, driver)

    assert json.loads((tmp_path / "settled.json").read_text()) == {
        "approach": "careful",
        "tests": True,
        "rounds": 3,
    }
