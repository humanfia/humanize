"""Side questions read a flow without becoming turns of that flow.

A side conversation is the runs' to open -- a read-only fork of a session where its CLI forks,
a seeded copy where it does not, the btw agent otherwise -- and the Host's tests are where that
is checked. What is checked here is what the interface asks for and what it draws: which side
it opens for the view it is on, what it says to it, the `@ask` hops of the btw agent, and
closing what it opened when btw mode is left. The runs are a `FakeLink` that opens sides and
answers their turns as told.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.app import _COMMANDS
from hmz.tui.btw import HOPS, asked, format_snapshot
from hmz.tui.pick import Adjusted
from hmz.tui.settings import Adjusts
from tests.tui.fixtures import FakeLink, holding, idle, told, transcript

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.pilot import Pilot


def _plain(prompt: str) -> str:
    """What every side conversation here answers, whatever it was asked."""
    del prompt
    return "The builder is checking the test suite."


class Sides(FakeLink):
    """Runs that open side conversations and answer their turns as a test says.

    Attributes:
      opened: What each side was opened with, by the side it became.
      turns: Every turn, as the side it went to and the prompt it was.
      reply: What a side answers a prompt with.
      forks: Whether a side opened on a session is a fork of it, as the runs say.
      refusing: Why the runs refuse every side, or "" where they refuse none.
    """

    def __init__(self) -> None:
        super().__init__()
        self.opened: dict[str, dict[str, Any]] = {}
        self.turns: list[tuple[str, str]] = []
        self.reply: Callable[[str], str] = _plain
        self.forks = False
        self.refusing = ""

    def _answering(self, said: dict[str, Any], seconds: float | None) -> dict[str, Any]:
        if said.get("do") != "aside":
            return super()._answering(said, seconds)
        self.requests.append(said)
        if self.refusing:
            return {"ok": False, "why": self.refusing}
        side = said.get("side")
        if side:
            self.turns.append((str(side), str(said["prompt"])))
            return {"ok": True, "answer": self.reply(str(said["prompt"]))}
        opened = f"s{len(self.opened) + 1}"
        self.opened[opened] = said
        return {
            "ok": True,
            "side": opened,
            "forked": self.forks and bool(said.get("fork")),
        }

    @property
    def prompts(self) -> list[str]:
        """Every prompt a side was told, in order."""
        return [prompt for _, prompt in self.turns]

    @property
    def closed(self) -> list[str]:
        """Every side the interface closed."""
        return [str(one["side"]) for one in self.asked_for("unaside")]


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Pumps the interface until a background side turn has posted its answer."""
    deadline = time.monotonic() + 10.0
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.01)
    await driver.pause()


async def typed(driver: Pilot[None], line: str) -> None:
    """Types one line into the prompt and sends it."""
    await driver.press(*line)
    await driver.press("enter")


def status(app: Humanize) -> str:
    """The status line under the prompt, as drawn."""
    return str(app.query_one("#status").render())


@pytest.mark.timeout(60)
async def test_btw_is_offered_and_does_not_enqueue_a_primary_message() -> None:
    """The command is a side turn, not another line for the running flow."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        app._monitor.begins("builder", "m")
        await typed(driver, "/btw what is happening?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        assert not sides.asked_for("say")
        # The btw agent, a copy of the flow's first agent, opened on nothing of its own.
        [opened] = sides.opened.values()
        assert opened["key"] == "builder/1"
        assert not opened.get("fork")
        [prompt] = sides.prompts
        assert "what is happening?" in prompt
        assert "finished: no" in prompt
        assert "builder/1" in prompt


@pytest.mark.timeout(60)
async def test_the_btw_agent_set_in_settings_is_the_one_opened() -> None:
    """An agent as `/settings` names it, rather than a copy of one the flow runs."""
    Settings().btw = "claude@work/m:high"
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        await typed(driver, "/btw what now?")
        await until(lambda: bool(sides.turns), driver)

        [opened] = sides.opened.values()
        assert opened["runs"] == "claude@work/m:high"
        assert "key" not in opened


@pytest.mark.timeout(60)
async def test_btw_mode_is_one_conversation_until_it_is_left() -> None:
    """Each line typed in btw mode is one more turn of the same side conversation."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        await typed(driver, "/btw")
        assert "btw · btw agent" in status(app)
        await typed(driver, "first?")
        await until(lambda: len(sides.turns) == 1, driver)
        await until(lambda: not app._btw or not app._btw.busy, driver)
        await typed(driver, "second?")
        await until(lambda: len(sides.turns) == 2, driver)

        (one, first), (two, second) = sides.turns
        assert one == two
        assert "<flow_snapshot>" in first
        assert "<flow_snapshot>" not in second
        assert "second?" in second
        # Neither went to the flow.
        assert not sides.asked_for("say")

        await driver.press("escape")
        await until(lambda: bool(sides.closed), driver)
        assert app._btw is None
        assert sides.closed == [one]
        assert "btw ·" not in status(app)
        assert "btw: exited" in transcript(app)


@pytest.mark.timeout(60)
async def test_btw_in_a_session_view_asks_a_fork_of_that_session() -> None:
    """Where the runs fork it, the side conversation carries the session's own history."""
    sides = Sides()
    sides.forks = True
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        app._attached = "builder"
        await typed(driver, "/btw why that file?")
        await until(lambda: "The builder is checking" in transcript(app), driver)
        assert "btw · builder/1" in status(app)

        [(side, opened)] = sides.opened.items()
        assert opened["key"] == "builder/1"
        assert opened["fork"] is True
        [(asked_of, prompt)] = sides.turns
        assert asked_of == side
        assert "read-only side copy of the flow session `builder/1`" in prompt
        assert "<flow_snapshot>" not in prompt

        await typed(driver, "/btw")
        await until(lambda: bool(sides.closed), driver)
        assert app._btw is None
        assert sides.closed == [side]


@pytest.mark.timeout(60)
async def test_a_fork_that_answers_nothing_is_given_up_for_a_seeded_copy() -> None:
    """A fork that opened and says nothing is closed, and a copy told the snapshot asked."""
    sides = Sides()
    sides.forks = True
    sides.reply = lambda prompt: (
        "" if "read-only side copy" in prompt else _plain(prompt)
    )
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        app._attached = "builder/1"
        await typed(driver, "/btw what now?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        assert [opened.get("fork") for opened in sides.opened.values()] == [True, None]
        forked, copied = sides.opened
        assert sides.closed == [forked]
        assert [side for side, _ in sides.turns] == [forked, copied]
        assert "<flow_snapshot>" in sides.prompts[-1]
        assert app._btw is not None
        assert app._btw.sides == {"builder/1": copied}


@pytest.mark.timeout(60)
async def test_btw_on_a_session_that_cannot_fork_asks_a_seeded_copy() -> None:
    """Without a fork, a read-only copy of the same agent is told what the flow did."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        app._attached = "builder"
        await typed(driver, "/btw what now?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        [prompt] = sides.prompts
        assert "the session `builder/1`" in prompt
        assert "<flow_snapshot>" in prompt


@pytest.mark.timeout(60)
async def test_btw_reaches_an_ended_session_with_no_flow_running() -> None:
    """A session of a run that is over can still be asked about."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        told(app, idle())  # which is what the run ending leaves behind
        app._attached = "builder/1"
        await typed(driver, "/btw what did you do?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        assert "finished: yes" in sides.prompts[0]


@pytest.mark.timeout(60)
async def test_btw_on_a_session_there_is_none_of_says_so() -> None:
    """A view of a conversation the run never opened is nothing to ask."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        app._attached = "builder/2"
        await typed(driver, "/btw anybody?")
        await until(lambda: "has no conversation to ask" in transcript(app), driver)

        assert app._btw is None
        assert not sides.opened


@pytest.mark.timeout(60)
async def test_the_btw_agent_asks_a_session_by_writing_a_line() -> None:
    """`@ask <key>: ...` is carried out, and its answer handed back to the btw agent."""

    def reply(prompt: str) -> str:
        if '<answer from="builder/1">' in prompt:
            return "The builder says: it is fixing the parser."
        if "the session `builder/1`" in prompt:
            return "fixing the parser"
        return "@ask builder/1: what are you doing?"

    sides = Sides()
    sides.reply = reply
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        await typed(driver, "/btw what is the builder up to?")
        await until(lambda: "fixing the parser." in transcript(app), driver)

        shown = transcript(app)
        assert "btw · asking builder/1: what are you doing?" in shown
        assert "@ask" not in shown.split("asking builder/1")[-1]
        assert len(sides.opened) == 2  # the btw agent's, and one for builder/1
        assert len({side for side, _ in sides.turns}) == 2
        assert app._btw is not None
        assert set(app._btw.sides) == {"", "builder/1"}


@pytest.mark.timeout(60)
async def test_the_btw_agent_stops_asking_after_a_few() -> None:
    """An agent that keeps asking is told to answer with what it has."""

    def reply(prompt: str) -> str:
        if "No more @ask this turn" in prompt:
            return "enough"
        if "the session `builder/1`" in prompt or prompt.startswith("<user_question>"):
            return "busy"
        return "@ask builder/1: again?"

    sides = Sides()
    sides.reply = reply
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        await typed(driver, "/btw loop")
        await until(lambda: "enough" in transcript(app), driver)
        assert transcript(app).count("btw · asking builder/1") == HOPS


@pytest.mark.timeout(60)
async def test_a_side_the_runs_would_not_open_is_said_in_red() -> None:
    """A refusal is the runs' to word, and it is said rather than answered as nothing."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        sides.refusing = "builder/1 has no conversation to ask"
        app._attached = "builder/1"
        await typed(driver, "/btw why?")
        await until(lambda: "hmz: /btw:" in transcript(app), driver)

        assert "builder/1 has no conversation to ask" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_new_run_leaves_btw_mode_and_closes_its_sides() -> None:
    """A side conversation is about the run it was opened on, and that run has gone."""
    sides = Sides()
    app = Humanize(link=sides)
    async with app.run_test() as driver:
        holding(app, "builder/1")
        await typed(driver, "/btw what now?")
        await until(lambda: bool(sides.turns), driver)
        await until(lambda: not app._btw or not app._btw.busy, driver)

        holding(app, "builder/1", run=1)
        await until(lambda: bool(sides.closed), driver)

        assert app._btw is None
        assert "a new flow started" in transcript(app)
        assert sides.closed == list(sides.opened)


def test_btw_snapshot_format_includes_runtime_progress() -> None:
    """The prompt gives the side agent facts instead of guessing a static flow graph."""
    from hmz.tui.btw import AgentProgress, FlowSnapshot, Observation

    snapshot = FlowSnapshot(
        flow="review",
        task="run the tests",
        workspace="/tmp/project",
        elapsed=12.5,
        finished=False,
        agents=(AgentProgress("builder", "m", 2, True),),
        handovers=(("builder", "reviewer", 1),),
        observations=(Observation("builder", "tool", "Bash uv run pytest", 1.0),),
        waiting=1,
        sessions=(("builder/1", "working, model=m"),),
    )

    prompt = format_snapshot(snapshot, "is the reviewer waiting?")

    assert "flow: review" in prompt
    assert "builder: working, 2 turn(s)" in prompt
    assert "builder -> reviewer: 1 time(s)" in prompt
    assert "Bash uv run pytest" in prompt
    assert "- builder/1: working, model=m" in prompt
    assert "@ask <session>: <question>" in prompt
    assert "is the reviewer waiting?" in prompt


def test_asks_are_read_off_an_answer() -> None:
    asks, rest = asked("Let me check.\n@ask builder/2: why?\n  @ask reviewer/1 : ok?")
    assert asks == [("builder/2", "why?"), ("reviewer/1", "ok?")]
    assert rest == "Let me check."


def test_btw_is_listed_as_a_command() -> None:
    from hmz.tui.app import _BY_NAME
    from hmz.tui.complete import offered

    assert _BY_NAME["btw"].about
    assert _BY_NAME["btw"].takes == "[question]"
    assert "/btw" in offered("/b", _COMMANDS)


@pytest.mark.timeout(60)
async def test_the_btw_agent_set_in_settings_is_written_down_and_said_when() -> None:
    """Choosing it takes effect the next time btw mode is entered, and says so."""
    app = Humanize()

    async with app.run_test() as driver:
        app._took_settings(Adjusts.Settled(Adjusted(btw="claude@work/m:high")))
        await driver.pause()

        assert Settings().btw == "claude@work/m:high"
        assert "next time you enter btw mode" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_btw_agent_is_a_row_of_settings_set_up_on_the_agent_sheet() -> None:
    """One row on the page of what is true everywhere, opening the sheet an agent is set on."""
    from textual.widgets import OptionList

    from hmz.tui.pick import _APART_MARK, Agent
    from tests.integration.tui.test_app import picks

    app = Humanize()
    async with app.run_test() as driver:
        await typed(driver, "/settings settings")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        await driver.pause()
        listing = app.screen.query_one("#choices", OptionList)
        assert "the flow's first agent" in str(listing.get_option_at_index(3).prompt)
        # Its list offers the flow's first agent, and another set up on the agent sheet.
        await picks(app, driver, "btw", f"{_APART_MARK}another")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert isinstance(app.screen, Agent)
