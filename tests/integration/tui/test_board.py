"""The monitor: the agents that have worked, the fleets under them, and the board.

Three things that all belong on the one screen, because all three are what the run *is doing*.
An agent the flow declared and never reached is not; a subagent one of them started is; and so
is what there is left to do, which is the board -- the lines the person and the flow both
write on and neither waits at.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import OptionList, Static

from hmz.coganchor.agents import Board, Refused
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.monitoring import EVERY, OUTWORLDER, Entry, Monitoring, Place, place_key
from tests.tui.fixtures import (
    event,
    link,
    opened,
    running,
    snapshot,
    started,
    told,
    until,
)

if TYPE_CHECKING:
    from textual.pilot import Pilot


def _drawn(app: Humanize) -> str:
    """Everything the graph has put up, as one block to read."""
    boxes = app.screen.query_one("#graph", OptionList)
    return "\n".join(
        str(boxes.get_option_at_index(at).prompt) for at in range(boxes.option_count)
    )


def _ids(app: Humanize) -> list[str]:
    """The id of every row on the graph, in the order they are drawn."""
    boxes = app.screen.query_one("#graph", OptionList)
    return [str(boxes.get_option_at_index(at).id) for at in range(boxes.option_count)]


def _under(app: Humanize) -> str:
    """What the monitor says under the graph."""
    return str(app.screen.query_one("#under", Static).content)


def _status(app: Humanize) -> str:
    """What the monitor's status line says."""
    return str(app.screen.query_one("#status", Static).content)


async def _opens(app: Humanize, driver: Pilot[None]) -> None:
    """Goes up to the monitor and waits for it to be up."""
    app.action_monitor()
    await until(
        lambda: isinstance(app.screen, Monitoring) and bool(app.screen.query("#graph")),
        driver,
    )
    await driver.pause()


def _two(app: Humanize) -> tuple[str, str]:
    """Two agents of a flow, a session apiece and neither of which has taken a turn yet."""
    # Named for the roles they fill, as a run names the agent behind each session it opens.
    told(app, opened("builder/1"), opened("reviewer/1"))
    app._models = {"builder": Runs("claude/m:high"), "reviewer": Runs("codex/n:high")}
    app._declared = None  # a flow nothing here loads, whose roles are these two
    return "builder", "reviewer"


def _board(app: Humanize, *lines: tuple[str, str, str]) -> None:
    """The board of a run whose flow talks to the person, as the runs say it now.

    Args:
      app: The interface.
      lines: Each line on it, as what it is called, what it says, and whose it is.
    """
    told(
        app,
        snapshot(
            "board",
            items=[
                {
                    "key": key,
                    "value": value,
                    "about": "",
                    "whose": whose,
                    "by": "",
                    "at": 0,
                }
                for key, value, whose in lines
            ],
        ),
    )


@pytest.mark.timeout(60)
async def test_an_agent_that_has_not_worked_is_not_drawn_yet() -> None:
    """The diagram is what the run is doing, and a flow may never take the other branch."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()

        await _opens(app, driver)

        # One box, for the one that has started. The other is a place the flow declared, not
        # something the run is doing.
        assert _ids(app) == [EVERY, one]
        assert "0 of 1 working" not in _drawn(app)
        assert "1 of 1 working" in _drawn(app)


@pytest.mark.timeout(60)
async def test_a_box_appears_as_its_agent_takes_its_first_turn() -> None:
    """Which is what makes this a picture of the run growing rather than of what was set up."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        assert _ids(app) == [EVERY, one]

        told(app, event("reviewer/1", "begins"))
        await until(lambda: _ids(app) == [EVERY, one, two], driver)

        # And it stays once its turn is over: what it did is still worth reading.
        told(app, event("reviewer/1", "ends"))
        await driver.pause()
        assert _ids(app) == [EVERY, one, two]


@pytest.mark.timeout(60)
async def test_an_agent_a_turn_started_of_its_own_is_drawn_under_it() -> None:
    """A fleet under a turn is agents, and it is drawn as agents rather than as tool calls."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        told(app, event("builder/1", "subagent", "Task read the tests", whose="c1"))
        await driver.pause()

        await _opens(app, driver)

        drawn = _drawn(app)
        assert "read the tests" in drawn
        assert "◆" in drawn  # working, and not the mark a flow's own agents wear
        # It is not a row to attach to: nobody chose what it runs and it has no transcript.
        assert _ids(app) == [EVERY, one]

        told(
            app, event("builder/1", "subagent-ends", "Task read the tests", whose="c1")
        )
        await until(lambda: "◇" in _drawn(app), driver)


@pytest.mark.timeout(60)
async def test_a_run_with_no_person_in_its_flow_has_no_board() -> None:
    """A board is what the person and the flow both write on, so it takes a person."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        await _opens(app, driver)

        assert "Board" not in _drawn(app)
        assert "\x00" not in "".join(_ids(app))  # and no row to put a line up with


@pytest.mark.timeout(60)
async def test_the_board_is_under_the_diagram_and_says_what_is_on_it() -> None:
    """Beside how far through the run is: a board somebody has to go and open is unread."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        _board(
            app, ("todo", "fix the build", "both"), ("progress", "two of five", "flow")
        )

        await _opens(app, driver)

        drawn = _drawn(app)
        assert "Board" in drawn
        assert "fix the build" in drawn
        assert "two of five" in drawn
        assert "flow's" in drawn  # the one the person may read and not rewrite


@pytest.mark.timeout(60)
async def test_a_line_the_flow_keeps_to_itself_is_not_one_to_change_here() -> None:
    """A flow writing down how far through it is does not want that edited underneath it."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        _board(app, ("progress", "two of five", "flow"))
        await _opens(app, driver)

        # Down to it, and enter: it says why rather than opening an editor. The last row
        # is the one that puts a line up, so the flow's own line is the one before it.
        while (
            app.screen.query_one("#graph", OptionList).highlighted != len(_ids(app)) - 2
        ):
            await driver.press("down")
        await driver.press("enter")
        await driver.pause()

        assert "can only be changed by the flow" in _under(app)
        assert isinstance(app.screen, Monitoring)
        assert not link(app).asked_for("board")  # refused here, never asked of the runs


@pytest.mark.timeout(60)
async def test_a_line_typed_onto_the_board_is_asked_of_the_runs_at_once() -> None:
    """Neither side waits at the board: what is written here is asked of the runs at once."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        _board(app)
        await _opens(app, driver)

        # The last row is the one that puts a line up, and enter on it is a new line.
        while app.screen.query_one("#graph", OptionList).highlighted != (
            len(_ids(app)) - 1
        ):
            await driver.press("down")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Entry), driver)
        await driver.press(*"todo")
        await driver.press("enter")  # the name, then what it says
        await driver.pause()
        await driver.press(*"fix the build")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Monitoring), driver)
        await until(lambda: bool(link(app).asked_for("board")), driver)

        [asked] = link(app).asked_for("board")
        assert (asked["key"], asked["value"]) == ("todo", "fix the build")
        # And what the runs say the board is now is what is drawn.
        _board(app, ("todo", "fix the build", "both"))
        await until(lambda: "fix the build" in _drawn(app), driver)


def test_the_board_is_named_lines_that_either_side_may_be_kept_off() -> None:
    """The store itself, which is what both the sheet and a flow are reading."""
    board = Board()
    board.put("todo", "one thing", about="what there is to do")
    board.put("progress", "nothing yet", whose="flow")
    board.put("wanted", "", whose="user")

    assert board.get("todo") == "one thing"
    assert [one.key for one in board.items()] == ["todo", "progress", "wanted"]
    # Either side writes the ordinary one.
    board.put("todo", "another", by="user")
    assert board.get("todo") == "another"
    # And neither writes the other's.
    with pytest.raises(Refused):
        board.put("progress", "no", by="user")
    with pytest.raises(Refused):
        board.put("wanted", "no", by="flow")
    with pytest.raises(Refused):
        board.drop("progress", by="user")
    # What a line is for survives writing what it says, so a value is one thing to write.
    held = board.held("todo")
    assert held is not None
    assert held.about == "what there is to do"


def test_a_renamed_line_comes_back_under_its_new_name() -> None:
    """A rename is one write, so what it wrote is what the caller is handed."""
    board = Board()
    board.put("todo", "fix the build", about="what there is to do", whose="user")

    moved = board.moves("todo", to="doing", by="user")

    assert moved.key == "doing"
    assert moved.value == "fix the build"
    assert moved.about == "what there is to do"  # everything else it said survives
    assert moved.whose == "user"
    assert moved.by == "user"
    assert [one.key for one in board.items()] == ["doing"]


def test_a_renamed_line_comes_back_where_something_watching_took_it_away() -> None:
    """The rename happened; what a watcher did on being told is the next thing, not this one.

    Which is the whole board in one call: the line is made under the lock, and what anybody
    else does to the board afterwards cannot turn the answer into a different line or into
    no line at all.
    """

    def away(one: Board) -> None:
        one.drop("doing")

    board = Board()
    board.put("todo", "fix the build")
    board.watch(away)

    moved = board.moves("todo", to="doing")

    assert moved.key == "doing"
    assert moved.value == "fix the build"
    assert board.held("doing") is None  # the watcher got what it asked for


def test_whatever_is_watching_the_board_is_told_when_a_line_moves() -> None:
    """Which is how the sheet redraws without asking the board on a clock."""
    board = Board()
    seen: list[int] = []
    board.watch(lambda one: seen.append(len(one.items())))

    board.put("todo", "one")
    board.put("todo", "two")
    board.drop("todo")

    assert seen == [1, 1, 0]


def test_a_watcher_that_raises_has_said_nothing() -> None:
    """A flow must not fail because something looking at its board did."""

    def up(_board: Board) -> None:
        raise RuntimeError("no")

    board = Board()
    board.watch(up)

    board.put("todo", "one")  # which does not raise

    assert board.get("todo") == "one"


@pytest.mark.timeout(60)
async def test_a_box_says_how_long_its_agent_has_been_at_what_it_is_doing() -> None:
    """The half of a box that moves, and the half nothing else on the screen carries."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = _two(app)
        told(app, event("builder/1", "begins"))
        told(app, event("reviewer/1", "begins"))
        told(app, event("reviewer/1", "ends"))
        await driver.pause()
        # Wound back, so that the clocks say something worth reading in a test.
        app._monitor.opened[one] = time.monotonic() - 65.0
        app._monitor.rested[two] = time.monotonic() - 130.0

        await _opens(app, driver)

        drawn = _drawn(app)
        assert "1m0" in drawn  # the one working, since its turn began
        assert (
            "idle 2m1" in drawn
        )  # the one that has stopped, since its last turn ended


@pytest.mark.timeout(60)
async def test_a_box_says_when_its_agent_has_something_unread_on_it() -> None:
    """Which box is worth pressing enter on is the question this sheet is answering."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        app._keeping(one).unread = True
        await driver.pause()

        await _opens(app, driver)

        assert "unread" in _drawn(app)


@pytest.mark.timeout(60)
async def test_the_box_under_the_cursor_says_so_on_the_box() -> None:
    """A picture cannot be highlighted: the markup inside it paints over the highlight."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        told(app, event("builder/1", "begins"))
        told(app, event("reviewer/1", "begins"))
        await driver.pause()
        await _opens(app, driver)

        await driver.press("down")  # off the row they all appear on, onto the first box
        await driver.pause()

        boxes = app.screen.query_one("#graph", OptionList)
        assert boxes.highlighted == 1
        assert "❯" in str(boxes.get_option_at_index(1).prompt)
        assert "❯" not in str(boxes.get_option_at_index(2).prompt)


@pytest.mark.timeout(60)
async def test_a_clock_ticking_puts_the_row_back_rather_than_the_whole_list() -> None:
    """A list rebuilt twice a second loses the click somebody is making on it."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Monitoring)
        boxes = sheet.query_one("#graph", OptionList)
        held = boxes.get_option_at_index(1)

        app._monitor.opened[one] = time.monotonic() - 91.0
        sheet._fill()
        await driver.pause()

        assert "1m3" in str(boxes.get_option_at_index(1).prompt)  # it says the new time
        assert boxes.get_option_at_index(1) is held  # in the row that was already there


@pytest.mark.timeout(60)
async def test_what_the_boxes_say_is_not_said_again_under_them() -> None:
    """The diagram is the sheet, so what is written under it is what a picture cannot say."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()

        await _opens(app, driver)

        under = _under(app)
        assert "Flow:" in under  # which flows are running, which no box says
        assert "Tokens:" in under
        assert "Working:" not in under  # the boxes are marked, and once is enough
        assert "Agents:" not in under  # what each runs is on its own box


@pytest.mark.timeout(60)
async def test_a_run_that_has_not_started_says_so_where_the_boxes_would_be() -> None:
    """A sheet about a run that has not begun is a blank page otherwise."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)

        await _opens(app, driver)

        assert "no agent has taken a turn yet" in _drawn(app)
        # And the agents that are set up are said under it, there being no boxes to say them.
        assert "Agents:" in _under(app)


@pytest.mark.timeout(60)
async def test_a_line_written_down_empty_is_taken_off_the_board() -> None:
    """There is no key that takes a line away: saving it with nothing in it is how."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        _board(app, ("todo", "fix the build", "both"))
        await _opens(app, driver)

        while app.screen.query_one("#graph", OptionList).highlighted != (
            _ids(app).index("\x00todo")
        ):
            await driver.press("down")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Entry), driver)
        for _ in "fix the build":
            await driver.press("backspace")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Monitoring), driver)
        await until(lambda: bool(link(app).asked_for("board")), driver)

        [asked] = link(app).asked_for("board")
        assert (asked["key"], asked["value"]) == ("todo", "")
        assert "removed from the board" in _under(app)


@pytest.mark.timeout(60)
async def test_left_off_an_empty_prompt_is_the_monitor_and_right_comes_back() -> None:
    """The monitor is the parent of the log: `←` goes up to it, `→` back down."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)

        await driver.press("escape")  # which is not how it is opened any more
        await driver.pause()
        assert not isinstance(app.screen, Monitoring)

        await driver.press("x", "left")  # with something typed, it is the editor's
        await driver.pause()
        assert not isinstance(app.screen, Monitoring)
        await driver.press("right", "backspace")  # back to the end, and rubbed out

        await driver.press("left")
        await until(
            lambda: (
                isinstance(app.screen, Monitoring) and bool(app.screen.query("#graph"))
            ),
            driver,
        )
        await driver.pause()
        # The first node is every agent's log, and it is the one the cursor starts on.
        assert app.screen.query_one("#graph", OptionList).highlighted == 0
        assert _ids(app)[0] == EVERY
        assert "all agents" in _drawn(app)

        await driver.press("right")
        await until(lambda: not isinstance(app.screen, Monitoring), driver)
        assert app._attached == EVERY


@pytest.mark.timeout(60)
async def test_space_opens_an_agent_out_to_its_sessions_and_enter_reads_one() -> None:
    """A loop that opens a session a turn is one agent, opened out to its many sessions."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        told(app, event("builder/1", "ends"), opened("builder/2"))
        told(app, event("builder/2", "begins"))
        await driver.pause()
        await _opens(app, driver)
        assert _ids(app) == [EVERY, one]
        assert "▸" in _drawn(app)

        await driver.press("down", "space")
        await until(lambda: _ids(app) == [EVERY, one, f"{one}/1", f"{one}/2"], driver)
        assert _ids(app) == [EVERY, one, f"{one}/1", f"{one}/2"]
        assert "▾" in _drawn(app)
        assert "session 2" in _drawn(app)
        assert "space shut" in _status(app)

        await driver.press("down", "enter")
        await until(lambda: not isinstance(app.screen, Monitoring), driver)
        assert not isinstance(app.screen, Monitoring)
        assert app._attached == f"{one}/1"  # that session's own log

        # And it opens the way it was left.
        await _opens(app, driver)
        assert _ids(app) == [EVERY, one, f"{one}/1", f"{one}/2"]


@pytest.mark.timeout(60)
async def test_space_on_a_session_shuts_the_agent_it_hangs_under() -> None:
    """The way back up a branch is the key that went down it, landing on the agent."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        await driver.press("down", "space")
        await until(lambda: _ids(app) == [EVERY, one, f"{one}/1"], driver)
        assert _ids(app) == [EVERY, one, f"{one}/1"]

        await driver.press("down", "space")
        await until(lambda: _ids(app) == [EVERY, one], driver)
        assert _ids(app) == [EVERY, one]
        graph = app.screen.query_one("#graph", OptionList)
        assert _ids(app)[graph.highlighted or 0] == one


@pytest.mark.timeout(60)
async def test_a_click_on_the_edge_of_an_agent_opens_it_and_two_read_it() -> None:
    """Where its `▸` is, a click opens it out; elsewhere two clicks read it, as enter does."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        told(app, event("builder/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        graph = app.screen.query_one("#graph", OptionList)

        # Row nought is every agent's log, and the agent's name is two rows under it.
        await driver.click(graph, offset=(5, 2))
        await until(lambda: _ids(app) == [EVERY, one, f"{one}/1"], driver)
        assert _ids(app) == [EVERY, one, f"{one}/1"]
        await driver.click(graph, offset=(5, 2))  # on it already, so shut again
        await until(lambda: _ids(app) == [EVERY, one], driver)
        assert _ids(app) == [EVERY, one]

        await driver.double_click(graph, offset=(30, 2))
        await until(lambda: not isinstance(app.screen, Monitoring), driver)
        assert not isinstance(app.screen, Monitoring)
        assert app._attached == one


@pytest.mark.timeout(60)
async def test_ctrl_t_lists_the_nodes_with_the_working_ones_on_top() -> None:
    """A list says nothing of who handed to whom, and puts what is working first."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = _two(app)
        told(app, event("builder/1", "begins"), event("builder/1", "ends"))
        told(app, event("reviewer/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        assert _ids(app) == [EVERY, one, two]  # the flow's order, drawn
        assert "↓ 1" in _drawn(app)

        await driver.press("ctrl+t")
        await until(lambda: two in _ids(app) and _ids(app).index(two) == 2, driver)
        assert _ids(app).index(two) == 2
        assert _ids(app)[3] == one  # the one working floated above the one that is not
        assert "↓" not in _drawn(app)
        assert "· list" in _status(app)
        assert "ctrl+t graph" in _status(app)

        # And the switch above it turns it back, as a click.
        await driver.click("#as-graph")
        await until(lambda: _ids(app) == [EVERY, one, two], driver)
        assert _ids(app) == [EVERY, one, two]
        assert not app._monitor_listed


@pytest.mark.timeout(60)
async def test_an_environment_hangs_under_its_session_and_opens_to_a_page() -> None:
    """Where a session works is a node of its own, which opens for what it is."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        where = {
            "role": "repo",
            "kind": "docker",
            "target": "builders",
            "workdir": "/work",
            "anchored": True,
        }
        told(app, opened("builder/1", env=where), opened("reviewer/1"))
        app._models = {"builder": Runs("claude/m:high")}
        app._declared = None
        app._envs = {"repo": "docker@builders/work"}
        told(app, event("builder/1", "begins"))
        await driver.pause()
        await _opens(app, driver)
        assert "▤ repo docker" in _drawn(app)  # said on the box while it is shut

        await driver.press("down", "space")
        await until(lambda: len(_ids(app)) == 4, driver)
        assert len(_ids(app)) == 4
        assert _ids(app)[3].startswith("\x03")
        assert "builders · /work" in _drawn(app)

        await driver.press("down", "down", "enter")
        await until(lambda: isinstance(app.screen, Place), driver)
        assert isinstance(app.screen, Place)
        await driver.pause()
        page = app.screen.query_one("#choices", OptionList)
        said = "\n".join(
            str(page.get_option_at_index(at).prompt) for at in range(page.option_count)
        )
        assert "DOCKER" in said
        assert "builders" in said
        assert "docker@builders/work" in said
        assert "1 of 1 session working" in said

        await driver.press("enter")  # on the session working there, which reads it
        await until(lambda: app._attached == "builder/1", driver)
        assert app._attached == "builder/1"
        assert not isinstance(app.screen, (Place, Monitoring))


@pytest.mark.timeout(60)
async def test_the_list_holds_the_environments_as_nodes_of_their_own() -> None:
    """Every environment is a row of the list, working where a session in it is."""
    app = Humanize()
    async with app.run_test(size=(120, 40)) as driver:
        where = {"role": "workspace", "kind": "local", "workdir": "/proj"}
        told(app, opened("builder/1", env=where), opened("reviewer/1", env=where))
        app._models = {"builder": Runs("claude/m:high"), "reviewer": Runs("codex/n")}
        app._declared = None
        told(app, event("builder/1", "begins"), event("builder/1", "ends"))
        told(app, event("reviewer/1", "begins"))
        await driver.pause()
        app._monitor_listed = True
        await _opens(app, driver)

        ids = _ids(app)
        places = [one for one in ids if one.startswith("\x03")]
        assert len(places) == 1  # one place, however many sessions work in it
        assert ids.index(places[0]) < ids.index("builder")  # working, so above
        assert "2 sessions" in _drawn(app)


@pytest.mark.timeout(60)
async def test_a_command_typed_on_the_monitor_is_carried_out_there() -> None:
    """The prompt under the graph is the log's own: every command works from it."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        await _opens(app, driver)

        await driver.press(*"/afk on")
        await driver.press("enter")
        await until(lambda: "away" in _under(app), driver)

        assert isinstance(app.screen, Monitoring)  # still up
        assert "away" in _under(app)  # and it answered where it was typed
        [asked] = link(app).asked_for("afk")
        assert asked["on"] is True


@pytest.mark.timeout(60)
async def test_the_person_is_a_node_of_their_own() -> None:
    """An outworlder is not an agent the flow drives, and it is read on a log of its own."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        app._outworlders = ["human"]
        await _opens(app, driver)

        assert _ids(app)[1] == f"{OUTWORLDER}human"
        assert "outworlder" in _drawn(app)

        await driver.press("down", "enter")
        await until(lambda: not isinstance(app.screen, Monitoring), driver)
        assert app._attached == f"{OUTWORLDER}human"  # what that outworlder asks


#: An environment on another machine, which every session working in it reaches by anchor.
_DOCKER = {
    "role": "repo",
    "kind": "docker",
    "target": "builders",
    "workdir": "/work",
    "anchored": True,
}

#: The workspace, on this machine.
_HERE = {"role": "workspace", "kind": "local", "workdir": "/proj", "anchored": False}


async def _page(app: Humanize, driver: Pilot[None], where: dict[str, Any]) -> str:
    """Opens an environment's page over the monitor, and says everything on it."""
    await _opens(app, driver)
    app.push_screen(Place(place_key(where), app._places, app._branches))
    await until(lambda: isinstance(app.screen, Place), driver)
    await driver.pause()
    page = app.screen.query_one("#choices", OptionList)
    return "\n".join(
        str(page.get_option_at_index(at).prompt) for at in range(page.option_count)
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    ("went", "where", "says"),
    [
        (
            "self",
            _DOCKER,
            "self: on this environment's machine, with the CLI installed there",
        ),
        ("local", _DOCKER, "local: on this machine; what it runs lands here"),
        (
            "ssh:box",
            _DOCKER,
            "ssh:box: on a runtime of its own, reaching this environment through the anchor",
        ),
        ("", _HERE, "local: on this machine, in this workdir"),
    ],
)
async def test_an_environment_s_page_says_where_the_run_put_its_harnesses(
    went: str, where: dict[str, Any], says: str
) -> None:
    """As the session found it, not as the environment's kind hints."""
    app = Humanize()
    async with app.run_test(size=(160, 40)) as driver:
        began = started(1, flow="placed", roles=["builder"])
        told(app, began, running(began))
        told(app, opened("builder/1", run=1, env=where, harness=went))
        told(app, event("builder/1", "begins", run=1))
        await driver.pause()

        said = await _page(app, driver, where)
        assert says in said
        assert "→" not in said


@pytest.mark.timeout(60)
async def test_sessions_whose_harnesses_went_two_ways_are_said_one_by_one() -> None:
    """One role's harness may go to the machine and another's stay here."""
    app = Humanize()
    async with app.run_test(size=(160, 40)) as driver:
        began = started(1, flow="placed", roles=["builder", "reviewer"])
        told(app, began, running(began))
        told(app, opened("builder/1", run=1, env=_DOCKER, harness="self"))
        told(app, opened("reviewer/1", run=1, env=_DOCKER, harness="local"))
        told(app, event("builder/1", "begins", run=1))
        await driver.pause()

        assert "self for builder/1 · local for reviewer/1" in await _page(
            app, driver, _DOCKER
        )


@pytest.mark.timeout(60)
async def test_the_models_spent_on_keep_their_rows_as_one_overtakes_another() -> None:
    """In the order each was first spent on, which is an order spending does not change."""
    app = Humanize()
    async with app.run_test(size=(160, 40)) as driver:
        _two(app)
        told(app, event("builder/1", "begins"))
        app._monitor.spend("builder", 100, model="small")
        app._monitor.spend("reviewer", 50, model="big")
        await driver.pause()
        await _opens(app, driver)
        before = _under(app)
        assert before.index("small") < before.index("big")

        app._monitor.spend("reviewer", 5000, model="big")  # overtaking it
        await until(lambda: "5.0k" in _under(app), driver)
        after = _under(app)
        assert after.index("small") < after.index("big")
