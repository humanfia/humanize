"""Side questions read a flow without becoming turns of that flow."""

from __future__ import annotations

import asyncio
import gc
import time
from typing import TYPE_CHECKING, ClassVar

import pytest

from hmz.coganchor.agents import AgentBase, AgentConfig, Event, SessionBase
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.app import _COMMANDS
from hmz.tui.btw import asked, format_snapshot
from hmz.tui.pick import Adjusted, Adjusts
from tests.tui.fixtures import holding, transcript

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator

    from pydantic import BaseModel
    from textual.pilot import Pilot


CONFIG = AgentConfig(model="m", effort="high")


def _plain(prompt: str) -> str:
    """What every side session here answers, whatever it was asked."""
    del prompt
    return "The builder is checking the test suite."


class SideSession(SessionBase):
    """A deterministic session that records each prompt, and the session it went to."""

    prompts: ClassVar[list[str]] = []
    heard: ClassVar[list[tuple[SessionBase, str]]] = []
    reply: ClassVar[Callable[[str], str]] = staticmethod(_plain)
    closed: ClassVar[list[SessionBase]] = []

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        del schema
        self.prompts.append(prompt)
        self.heard.append((self, prompt))
        yield Event(kind="result", text=type(self).reply(prompt))

    def close(self) -> None:
        self.closed.append(self)
        super().close()


class SideAgent(AgentBase):
    """An agent whose side turns never touch the filesystem."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> SideSession:
        return SideSession(self, cwd)


class MainSession(SideSession):
    """A held primary session, distinguishable from the side session."""


class MainAgent(SideAgent):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> MainSession:
        return MainSession(self, cwd)


class ForkingSession(MainSession):
    """A primary session whose CLI can carry it into a second conversation."""

    @property
    def forks(self) -> bool:
        return True


class ForkingAgent(SideAgent):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> SideSession:
        # Its own conversations fork; the ones made for a fork of it are plain side ones.
        return (ForkingSession if not self.sessions else SideSession)(self, cwd)


@pytest.fixture(autouse=True)
def _fresh() -> Iterator[None]:
    """Each test reads only the prompts it sent itself."""
    SideSession.prompts.clear()
    SideSession.heard.clear()
    SideSession.closed.clear()
    yield
    _HELD.clear()
    SideSession.reply = staticmethod(_plain)


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


#: The primary conversations made here, held: an agent holds its own only weakly.
_HELD: list[SessionBase] = []


def building(session: type[MainAgent | ForkingAgent] = MainAgent) -> AgentBase:
    """A primary agent named for its role, with one conversation that has had a turn."""
    primary = session(CONFIG)
    primary.rename("builder")
    held = primary.new()
    held._id = "primary-1"
    _HELD.append(held)
    return primary


@pytest.mark.timeout(60)
async def test_btw_is_offered_and_does_not_enqueue_a_primary_message() -> None:
    """The command is a side turn, not another line for the running flow."""
    app = Humanize()
    primary = building()
    holding(app, primary)
    app._models = {"builder": Runs("claude/m:high")}
    app._queued = ["keep working"]
    app._given = [(primary.id, "already handed")]
    app._monitor.begins(primary.id, "m")
    before_sessions = list(primary.sessions)

    async with app.run_test() as driver:
        await typed(driver, "/btw what is happening?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        assert app._queued == ["keep working"]
        assert app._given == [(primary.id, "already handed")]
        assert primary.sessions == before_sessions
        assert len(SideSession.prompts) == 1
        assert "what is happening?" in SideSession.prompts[0]
        assert "finished: no" in SideSession.prompts[0]
        assert "builder/1" in SideSession.prompts[0]


@pytest.mark.timeout(60)
async def test_btw_mode_is_one_conversation_until_it_is_left() -> None:
    """Each line typed in btw mode is one more turn of the same side session."""
    app = Humanize()
    primary = building()
    holding(app, primary)

    async with app.run_test() as driver:
        await typed(driver, "/btw")
        assert "btw · btw agent" in status(app)
        await typed(driver, "first?")
        await until(lambda: len(SideSession.heard) == 1, driver)
        await until(lambda: not app._btw or not app._btw.busy, driver)
        await typed(driver, "second?")
        await until(lambda: len(SideSession.heard) == 2, driver)

        (one, first), (two, second) = SideSession.heard
        assert one is two
        assert "<flow_snapshot>" in first
        assert "<flow_snapshot>" not in second
        assert "second?" in second
        # Neither went to the flow.
        assert app._queued == []

        await driver.press("escape")
        await driver.pause()
        assert app._btw is None
        assert one in SideSession.closed
        assert "btw ·" not in status(app)
        assert "btw: left" in transcript(app)


@pytest.mark.timeout(60)
async def test_btw_in_a_session_view_forks_that_session_read_only() -> None:
    """Where the CLI forks, the side conversation carries the session's own history."""
    app = Humanize()
    primary = building(ForkingAgent)
    holding(app, primary)

    async with app.run_test() as driver:
        app._attached = "builder"
        await typed(driver, "/btw why that file?")
        await until(lambda: "The builder is checking" in transcript(app), driver)
        assert "btw · builder/1" in status(app)

        [(forked, prompt)] = SideSession.heard
        assert forked not in primary.sessions
        assert forked._forked_from == "primary-1"
        assert forked._agent.config.permission == "read-only"
        assert forked._agent.config.goals is False
        assert forked._skills == ()
        assert "read-only side copy of the flow session `builder/1`" in prompt
        assert "<flow_snapshot>" not in prompt

        await typed(driver, "/btw")
        await driver.pause()
        assert app._btw is None
        assert forked in SideSession.closed


@pytest.mark.timeout(60)
async def test_btw_on_a_session_that_cannot_fork_asks_a_seeded_copy() -> None:
    """Without a fork, a read-only copy of the same agent is told what the flow did."""
    app = Humanize()
    primary = building()
    holding(app, primary)

    async with app.run_test() as driver:
        app._attached = "builder"
        await typed(driver, "/btw what now?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        [(side, prompt)] = SideSession.heard
        assert side not in primary.sessions
        assert side._agent.config.permission == "read-only"
        assert "the session `builder/1`" in prompt
        assert "<flow_snapshot>" in prompt


@pytest.mark.timeout(60)
async def test_btw_reaches_an_ended_session_with_no_flow_running() -> None:
    """A session of a run that is over can still be asked about."""
    app = Humanize()
    primary = MainAgent(CONFIG)
    primary.rename("builder")
    # Told as a run tells it, and then let go of by everything but the interface: an agent
    # holds its conversations weakly, and a flow that has ended holds none of them.
    ended = primary.new()
    ended._id = "ended-1"
    holding(app, primary)
    app._run = None  # which is what the run ending leaves behind
    del ended
    gc.collect()

    async with app.run_test() as driver:
        app._attached = "builder/1"
        await typed(driver, "/btw what did you do?")
        await until(lambda: "The builder is checking" in transcript(app), driver)

        assert "finished: yes" in SideSession.prompts[0]


@pytest.mark.timeout(60)
async def test_the_btw_agent_asks_a_session_by_writing_a_line() -> None:
    """`@ask <key>: ...` is carried out, and its answer handed back to the btw agent."""

    def reply(prompt: str) -> str:
        if '<answer from="builder/1">' in prompt:
            return "The builder says: it is fixing the parser."
        if "the session `builder/1`" in prompt:
            return "fixing the parser"
        return "@ask builder/1: what are you doing?"

    SideSession.reply = staticmethod(reply)
    app = Humanize()
    primary = building()
    holding(app, primary)

    async with app.run_test() as driver:
        await typed(driver, "/btw what is the builder up to?")
        await until(lambda: "fixing the parser." in transcript(app), driver)

        shown = transcript(app)
        assert "btw · asking builder/1: what are you doing?" in shown
        assert "@ask" not in shown.split("asking builder/1")[-1]
        sessions = {session for session, _ in SideSession.heard}
        assert len(sessions) == 2  # the btw agent's, and one for builder/1
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

    SideSession.reply = staticmethod(reply)
    app = Humanize()
    holding(app, building())

    async with app.run_test() as driver:
        await typed(driver, "/btw loop")
        await until(lambda: "enough" in transcript(app), driver)
        assert transcript(app).count("btw · asking builder/1") == 4


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
        assert "from the next time btw mode is entered" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_btw_agent_is_a_row_of_settings_set_up_on_the_agent_sheet() -> None:
    """One row on the page of what is true everywhere, opening the sheet an agent is set on."""
    from textual.widgets import OptionList

    from hmz.tui.pick import Agent

    app = Humanize()
    async with app.run_test() as driver:
        await typed(driver, "/settings")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        listing = app.screen.query_one("#choices", OptionList)
        assert "the flow's first agent" in str(listing.get_option_at_index(3).prompt)
        listing.highlighted = 3
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert isinstance(app.screen, Agent)
