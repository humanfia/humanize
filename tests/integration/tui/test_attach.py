"""A transcript per conversation, agent and outworlder, and one where all of them appear.

A flow drives several agents and each of them holds as many conversations as it likes. Every
agent's lines interleaved into one screen is none of them readable, and a screen wiped each
time a loop opened its next conversation is one nobody can read back through -- so a running
conversation is what is stepped onto, all of an agent's conversations run down its one
transcript as well, each outworlder asks on one of its own, and the one this opens on is the
one where all of it appears together. What a line typed on one of them does is asked of the
runs -- said to the view it was typed on, or answering what that view's outworlder asks -- and
which outworlder is whose to answer is what the runs say of the claims on it. Driven headlessly
off the messages the runs tell, so what is checked is what a keystroke asks for and what is
drawn of what was told, rather than where the host puts a line.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import OptionList, Static

from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.app import _KEPT
from hmz.tui.monitor import short
from hmz.tui.pick import EVERY, Held, reads
from tests.stubs import written
from tests.tui.fixtures import (
    asked,
    event,
    holding,
    link,
    opened,
    pending,
    running,
    set_up,
    snapshot,
    started,
    told,
    transcript,
)
from tests.tui.fixtures import until as waited

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

#: A `claude --print` that says which session it is, says one thing, and then holds the turn
#: open until the workspace says it may finish. Which is what makes two turns run at once here,
#: since a turn that has ended is not one to step onto.
PATIENT = """
import json, os, pathlib, sys, time

flags = dict(zip(sys.argv, sys.argv[1:]))
taken = flags.get("--session-id") or flags["--resume"]
print(json.dumps({"type": "system", "session_id": taken}), flush=True)
where = pathlib.Path(os.environ["HUMANIZE_HELD"])
for line in sys.stdin:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "working " + taken}]}}), flush=True)
    while not (where / "go.txt").exists():
        time.sleep(0.02)
    print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""

#: A flow that holds a turn open on each of its agents, so that two of them are working at
#: once and neither ends until the flow is let go. Which is the case that matters: one
#: transcript for two agents talking at the same time is two transcripts interleaved.
HOLDING = """
import asyncio

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="flow")
async def run(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
              ctx: FlowContext) -> None:
    async def hold(agent: Agent) -> None:
        session = await agent.spawn(env=envs["workspace"])
        await agent.run("hold", session=session)

    # A turn apiece, open at the same time and neither answering until the fake CLI is let
    # go: two agents working at once is the case tab is for.
    await asyncio.gather(hold(agents["builder"]), hold(agents["reviewer"]))
"""


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """The shared wait, and then one more pump once it comes back.

    What this file waits on is a turn arriving at a transcript that is not the one on screen,
    so the thing being asserted is drawn by the pump *after* the state it is read off changed:
    without the extra one, `until` returns the moment the flag flips and the line it put up is
    still a message in the queue.

    A wrapper rather than a copy of the body, which is what it was: the pumping is
    `tests.tui.fixtures.until`'s to decide, and what is written here is only the one thing this
    file needs on top of it.

    Args:
      ready: What is being waited for.
      driver: The interface to keep pumping while waiting.
    """
    await waited(ready, driver)
    await driver.pause()


def _above(app: Humanize) -> str:
    """The line above the prompt, which says what each agent runs and what it is holding."""
    return str(app.query_one("#above", Static).content)


async def _types(driver: Pilot[None], line: str) -> None:
    """Types one line and sends it, as somebody at the prompt would."""
    await driver.press(*line)
    await driver.press("enter")
    await driver.pause()


def _answered(
    question: str,
    role: str,
    text: str,
    *,
    by: str = "you@tui",
    client: str = "c1",
) -> dict[str, Any]:
    """The runs saying a question was answered, what with, and by whom."""
    return {
        "type": "answered",
        "run": 0,
        "question": question,
        "role": role,
        "by": by,
        "client": client,
        "text": text,
    }


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A flow that holds two conversations open, and a `claude` it never launches."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    # Where the fake looks for its leave to finish, since a turn is run wherever the flow is.
    monkeypatch.setenv("HUMANIZE_HELD", str(tmp_path))
    written(tmp_path, "flow", HOLDING)
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _two_agents(app: Humanize, driver: Pilot[None], where: Path) -> None:
    """Starts the flow that holds a conversation open for each of two agents, for real.

    Args:
      app: The interface, opened on runs held in this process.
      driver: What is pumping it.
      where: The workspace it is running in.
    """
    set_up(
        app,
        "flow",
        {"builder": Runs("claude/m:high"), "reviewer": Runs("claude/m:high")},
    )
    await driver.press(*"do it")
    await driver.press("enter")
    await until(lambda: len(app._conversations()) == 2, driver)
    # Both working, which is what tab steps between: a turn that has not started is not one
    # to step onto, and one that has ended is not either.
    await until(lambda: len(app._working) == 2, driver)
    assert app._run is not None  # held until it is let go, so nothing here can race
    assert not (where / "go.txt").exists()


def _let_go(where: Path) -> None:
    """Lets a held flow finish, there being no turn in it for a key to reach.

    Args:
      where: The workspace it is running in.
    """
    (where / "go.txt").write_text("")


async def _both_working(app: Humanize, driver: Pilot[None], **said: Any) -> None:
    """Two agents with a turn open apiece, which is what there is to step between.

    `builder` and then `reviewer`, one conversation each, as the runs tell a run of them.

    Args:
      app: The interface.
      driver: What is pumping it.
      said: What else the run's start says: its `outworlders`, say.
    """
    record = started(
        roles=["builder", "reviewer"],
        agents={"builder": "claude/m:high", "reviewer": "codex/n:high"},
        **said,
    )
    told(
        app,
        record,
        running(record),
        opened("builder/1"),
        opened("reviewer/1"),
        event("builder/1", "begins"),
        event("reviewer/1", "begins"),
    )
    await driver.pause()


def _frontends(**names: str) -> dict[str, Any]:
    """The `clients` snapshot: every frontend reading the runs, by client id."""
    return snapshot(
        "clients",
        clients=[
            {"client": client, "name": name, "kind": "tui"}
            for client, name in names.items()
        ],
    )


@pytest.mark.timeout(60)
async def test_it_opens_on_the_transcript_every_agent_is_on(
    workspace: Path, hosting: None
) -> None:
    """A flow is watched rather than an agent of it, so that is where a run starts."""
    app = Humanize()
    async with app.run_test() as driver:
        assert app._attached == EVERY

        await _two_agents(app, driver, workspace)

        # Still, with two of them going: stepping onto one is asked for rather than done to
        # somebody the moment a flow opens its first conversation.
        assert app._attached == EVERY
        assert app._reading() is None
        _let_go(workspace)
        await until(lambda: app._run is None, driver)


@pytest.mark.timeout(60)
async def test_shift_tab_steps_round_the_conversations_that_are_running(
    workspace: Path, hosting: None
) -> None:
    """The ones thinking, and the transcript they are all on, which is the way back."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = app._driven()

        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == first

        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == second

        await driver.press("shift+tab")  # round the end, back to all of them
        await driver.pause()
        assert app._attached == EVERY

        _let_go(workspace)
        await until(lambda: app._run is None, driver)


@pytest.mark.timeout(60)
async def test_tab_steps_the_other_way_round(workspace: Path, hosting: None) -> None:
    """The other way round the same ring, which is what a pair of keys is for."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = app._driven()

        await driver.press("tab")  # backwards off all of them is the last of them
        await driver.pause()
        assert app._attached == second

        await driver.press("tab")
        await driver.pause()
        assert app._attached == first

        _let_go(workspace)
        await until(lambda: app._run is None, driver)


@pytest.mark.timeout(60)
async def test_an_agent_that_is_not_working_is_not_stepped_onto() -> None:
    """With ten agents going, what somebody is stepping between is the ones thinking."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        told(app, event("reviewer/1", "ends"))
        await driver.pause()

        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == "builder/1"

        # Past the one that stopped, back to all of them.
        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == EVERY


@pytest.mark.timeout(60)
async def test_each_agent_reads_as_itself_and_all_of_them_read_as_the_lot() -> None:
    """Two agents talking at once interleaved into one transcript is neither of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        told(app, event("builder/1", "text", "from the first"))
        told(app, event("reviewer/1", "text", "from the second"))
        await driver.pause()

        # All of them, which is what it opened on: both, and which of them said each.
        shown = transcript(app)
        assert "from the first" in shown
        assert "from the second" in shown

        await driver.press("shift+tab")
        await driver.pause()

        # That conversation's own, drawn from the top: what the other said is not in it.
        shown = transcript(app)
        assert "from the first" in shown
        assert "from the second" not in shown
        assert "reading" in shown

        await driver.press("shift+tab")
        await driver.pause()
        shown = transcript(app)
        assert "from the second" in shown
        assert "from the first" not in shown


@pytest.mark.timeout(60)
async def test_every_conversation_of_one_agent_runs_down_the_same_transcript() -> None:
    """A Ralph loop opens one a turn, and a screen wiped each turn is one nobody can read."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app)
        app._models = {"builder": Runs("claude/m:high")}
        told(
            app,
            opened("builder/1"),
            event("builder/1", "begins"),
            event("builder/1", "text", "the first round"),
            event("builder/1", "ends"),
        )
        await driver.pause()

        await driver.press("tab")
        await driver.pause()
        # Nothing is working, so there is nowhere to step.
        assert app._attached == EVERY
        app._now_reading("builder")
        await driver.pause()

        told(
            app,
            opened("builder/2"),
            event("builder/2", "begins"),
            event("builder/2", "text", "the second round"),
        )
        await driver.pause()

        # Both rounds, on the one screen, with nothing cleared between them.
        shown = transcript(app)
        assert "the first round" in shown
        assert "the second round" in shown
        assert shown.index("the first round") < shown.index("the second round")
        # And each of them says which conversation it was, since there are two now.
        assert "conversation 2 of 2" in shown


@pytest.mark.timeout(60)
async def test_a_typed_line_is_said_to_the_conversation_being_read() -> None:
    """Which is the whole point: a flow drives several, and one of them is on the screen."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)

        await driver.press("shift+tab")
        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == "reviewer/1"

        await _types(driver, "for the second")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert link(app).asked_for("say") == [
            {"do": "say", "text": "for the second", "to": "reviewer/1"}
        ]


@pytest.mark.timeout(60)
async def test_a_line_typed_on_an_agent_s_own_is_said_to_that_agent() -> None:
    """Its newest conversation with a turn open is the runs' to find, by the role."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        app._now_reading("builder")
        await driver.pause()

        await _types(driver, "for the builder")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert link(app).asked_for("say")[0]["to"] == "builder"


@pytest.mark.timeout(60)
async def test_a_word_put_into_a_turn_is_kept_against_the_conversation_that_took_it() -> (
    None
):
    """It is part of that conversation, so it reads back as part of it wherever it was typed."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)

        told(
            app,
            {
                "type": "said",
                "run": 0,
                "text": "try the other way",
                "key": "reviewer/1",
                "by": "you@tui",
                "client": "c1",
            },
        )
        await driver.pause()

        # On the one they all appear on, which is where the run is watched from.
        assert "try the other way" in transcript(app)
        app._now_reading("reviewer/1")
        await driver.pause()
        assert "try the other way" in transcript(app)
        app._now_reading("builder/1")
        await driver.pause()
        assert "try the other way" not in transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_typed_with_every_agent_read_is_said_to_all_of_them() -> None:
    """There is no one agent to have meant, so the runs put it where a turn is open."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)

        await _types(driver, "anybody")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert link(app).asked_for("say") == [
            {"do": "say", "text": "anybody", "to": EVERY}
        ]


@pytest.mark.timeout(60)
async def test_reading_nothing_at_all_is_a_key_that_does_nothing() -> None:
    """With no flow running there is nothing working, and a key that says so is in the way."""
    app = Humanize()
    async with app.run_test() as driver:
        drawn = transcript(app)

        await driver.press("tab")
        await driver.press("shift+tab")
        await driver.pause()

        assert app._attached == EVERY
        assert app._reading() is None
        assert app.is_running
        # Nothing was drawn again, there being nothing to.
        assert transcript(app) == drawn


@pytest.mark.timeout(60)
async def test_a_flow_starting_reads_the_transcript_they_are_all_on(
    workspace: Path, hosting: None
) -> None:
    """What was being read belonged to a flow that has gone, and this is where a run starts."""
    app = Humanize()
    async with app.run_test() as driver:
        told(app, event("builder/1", "text", "the run before"))
        app._now_reading("builder")
        await driver.pause()
        assert app._attached == "builder"

        await _two_agents(app, driver, workspace)

        assert app._attached == EVERY
        assert "that flow has gone" in transcript(app)
        _let_go(workspace)
        await until(lambda: app._run is None, driver)


@pytest.mark.timeout(60)
async def test_the_line_above_the_prompt_says_which_agent_and_how_many() -> None:
    """What is being read has to be visible, and so does what is not, and who is working."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        app._draw()
        await driver.pause()

        # Both working, and neither being read: it opened on all of them.
        above = _above(app)
        assert above.count("●") == 2
        assert "reading" not in above
        # What each runs is what the run was started with, whatever is set up here.
        assert "reviewer · codex/n:high" in above

        # Nothing is unread while all of them are being read: it is on that screen too.
        told(app, event("reviewer/1", "text", "over here"))
        app._draw()
        await driver.pause()
        assert "unread" not in _above(app)

        # Read one of them, and what the other says is something to be told about.
        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == "builder/1"
        assert "reading" in _above(app)
        told(app, event("reviewer/1", "text", "and again"))
        app._draw()
        await driver.pause()
        assert "unread" in _above(app)

        # And reading it is what makes it read.
        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == "reviewer/1"
        assert "unread" not in _above(app)

        # An agent that has stopped says so, in the one mark on this line that moves itself.
        told(app, event("builder/1", "ends"))
        app._draw()
        await driver.pause()
        assert "○" in _above(app)


def test_an_agent_holding_nothing_says_nothing_about_it() -> None:
    """Which is every agent of a flow that is not running, and how that line always read."""
    runs = [Runs("claude/claude-opus-5:max")]

    # The role and what it runs, and nothing about what it may do: that is the flow's.
    at = "builder · claude/claude-opus-5:max"

    assert reads(("builder",), runs) == [at]
    assert reads(("builder",), runs, [Held()]) == [at]
    # And a running one says whether it is working, which is the one thing on this line that
    # changes by itself: a filled circle for a turn open, a hollow one for an agent stopped.
    assert reads(("builder",), runs, [Held(many=5)]) == [f"{at} · ○ 5"]
    assert reads(("builder",), runs, [Held(many=5, working=True)]) == [f"{at} · ● 5"]
    assert reads(("builder",), runs, [Held(many=5, reading=True, working=True)]) == [
        f"{at} · ● 5 · reading"
    ]
    assert reads(("builder",), runs, [Held(many=5, unread=True, working=True)]) == [
        f"{at} · ● 5 · unread"
    ]


@pytest.mark.timeout(60)
async def test_a_question_the_agent_itself_put_reaches_the_person() -> None:
    """A codex or kimi server speaks for every conversation of its agent, so it says none.

    It goes against the agent, all of whose conversations are the one transcript -- and onto
    the one they all appear on, which is where somebody watching the flow will come across it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)

        await driver.press("shift+tab")
        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == "reviewer/1"

        told(app, event("builder/1", "asks", "which way?", session=False))
        app._draw()
        await driver.pause()
        # It is the first agent's, which is not the one being read.
        assert "which way?" not in transcript(app)
        assert "unread" in _above(app)

        await driver.press("tab")
        await driver.pause()
        assert app._attached == "builder/1"
        assert "which way?" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_diagram_reads_an_agent_that_is_not_working() -> None:
    """Stepping is held to the ones thinking, so this reaches the one that has stopped."""
    from hmz.tui.monitoring import Monitoring

    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        told(app, event("reviewer/1", "text", "then it stopped"))
        told(app, event("reviewer/1", "ends"))
        await driver.pause()
        assert app._working_agents() == ["builder"]  # so tab cannot reach the second

        await driver.press("left")
        await until(
            lambda: (
                isinstance(app.screen, Monitoring) and bool(app.screen.query("#graph"))
            ),
            driver,
        )
        await driver.pause()
        boxes = app.screen.query_one("#graph", OptionList)
        drawn = [
            str(boxes.get_option_at_index(at).id) for at in range(boxes.option_count)
        ]
        assert drawn == [EVERY, "builder", "reviewer"]

        # Clicked rather than walked to: a box is drawn where it is in order to be pointed at.
        # Row nought is the one they all appear on, and a box is four rows under the one above.
        await driver.click(boxes, offset=(4, 1 + 4 + 4))
        await until(lambda: app._attached == "reviewer", driver)

        assert "then it stopped" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_diagram_marks_who_is_working_and_who_handed_to_whom() -> None:
    """The shape of a run is not written anywhere: it is read off the turns going past."""
    from hmz.tui.monitoring import Monitoring

    app = Humanize()
    async with app.run_test() as driver:
        holding(app)
        told(app, opened("builder/1"), opened("reviewer/1"))
        app._models = {
            "builder": Runs("claude/m:high"),
            "reviewer": Runs("codex/n:high"),
        }
        # A turn, and then a turn of the other agent: which is a handover between them.
        told(app, event("builder/1", "begins"))
        told(app, event("builder/1", "ends"))
        told(app, event("reviewer/1", "begins"))
        await driver.pause()

        await driver.press("left")
        await until(
            lambda: (
                isinstance(app.screen, Monitoring) and bool(app.screen.query("#graph"))
            ),
            driver,
        )
        await driver.pause()
        boxes = app.screen.query_one("#graph", OptionList)
        drawn = "\n".join(
            str(boxes.get_option_at_index(at).prompt)
            for at in range(boxes.option_count)
        )

        assert "┌" in drawn  # a box apiece
        assert "└" in drawn
        assert "↓ 1" in drawn  # the handover from the first to the second
        assert "1 of 2 working" in drawn
        assert "1 turn" in drawn


@pytest.mark.timeout(60)
async def test_a_cleared_screen_still_says_which_agent_a_line_is_from() -> None:
    """The name is said once as it changes, so a screen cleared under one has to forget it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        told(app, event("builder/1", "text", "before the clear"))
        await driver.pause()
        app.action_clear()
        await driver.pause()
        assert "before the clear" not in transcript(app)

        told(app, event("builder/1", "text", "after the clear"))
        await driver.pause()

        shown = transcript(app)
        assert "after the clear" in shown
        # Said again, there being nothing above it that said it.
        assert short("builder") in shown


@pytest.mark.timeout(60)
async def test_a_run_still_unwinding_says_nothing_into_the_next_run_s_conversation() -> (
    None
):
    """Each run numbers its conversations from one, so the two runs' keys are the same keys.

    What the run before says on its way out is its agent's, and goes there and on the one
    every agent is on -- not into the conversation of the run that replaced it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        # A run has started since the one this is from.
        record = started(1, roles=["builder"])
        told(app, record, running(record))
        told(app, opened("builder/1", run=1), event("builder/1", "begins", run=1))
        told(app, event("builder/1", "text", "from the run before", run=0))
        await driver.pause()

        assert "builder/1" in app._working  # the run going now's, still working
        app._now_reading("builder/1")
        await driver.pause()
        assert "from the run before" not in transcript(app)
        app._now_reading("builder")
        await driver.pause()
        assert "from the run before" in transcript(app)


@pytest.mark.timeout(60)
async def test_what_is_kept_is_held_to_the_last_few_agents() -> None:
    """A machine that has run twenty flows cannot keep every agent of all of them."""
    app = Humanize()
    async with app.run_test() as driver:
        roles = [f"agent{at}" for at in range(_KEPT + 4)]
        for at, role in enumerate(roles):
            told(app, event(f"{role}/1", "text", f"agent {at}"))
        await driver.pause()

        assert len(app._kept) == _KEPT
        # The newest are the ones there is still any reason to read, and neither the one
        # being read nor the one they are all on is ever among what is dropped.
        assert EVERY in app._kept
        assert roles[-1] in app._kept
        assert roles[0] not in app._kept


@pytest.mark.timeout(60)
async def test_an_outworlder_asks_on_a_transcript_of_its_own_and_is_answered_there() -> (
    None
):
    """What it puts to the person and nothing else, and a line typed there answers it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver, outworlders=["human"])
        told(app, event("builder/1", "text", "an agent's own line"))
        question = asked("q1", "human", "which way?", options=("north", "south"))
        told(app, question, pending(question))
        await driver.pause()

        # One stop of the ring, the last: backwards off all of them is where it is.
        assert app._ring()[-1] == "outworlder:human"
        await driver.press("tab")
        await driver.pause()
        assert app._attached == "outworlder:human"
        shown = transcript(app)
        assert "which way?" in shown
        assert "2. south" in shown  # numbered, so that one is chosen by its number
        assert "an agent's own line" not in shown
        assert "asking" in _above(app)

        await _types(driver, "2")
        await until(lambda: bool(link(app).asked_for("answer")), driver)
        assert link(app).asked_for("answer") == [
            {"do": "answer", "question": "q1", "text": "2"}
        ]

        # And what it was answered with is on its transcript once the runs say so.
        told(app, _answered("q1", "human", "south"), pending())
        await driver.pause()
        assert "south" in transcript(app).split("which way?")[-1]
        assert "asking" not in _above(app)


@pytest.mark.timeout(60)
async def test_an_answer_the_runs_refuse_leaves_the_question_to_answer_again() -> None:
    """A line that answered nothing is said to have, and the next line answers it instead."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver, outworlders=["human"])
        question = asked("q1", "human", "go on?")
        told(app, question, pending(question))
        link(app).answers["answer"] = {"ok": False, "why": "an answer says something"}
        await _types(driver, "   x")
        await until(lambda: "an answer says something" in transcript(app), driver)

        assert app._answers_to() == pending(question)["pending"][0]
        del link(app).answers["answer"]
        await _types(driver, "yes")
        await until(lambda: len(link(app).asked_for("answer")) == 2, driver)
        assert not link(app).asked_for("say")


@pytest.mark.timeout(60)
async def test_every_agent_s_transcript_answers_an_outworlder_and_a_conversation_s_does_not() -> (
    None
):
    """Where all of them are is where every outworlder is answered; a conversation is said to."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver, outworlders=["human"])
        question = asked("q1", "human", "go on?")
        told(app, question, pending(question))
        await driver.pause()
        assert "go on?" in transcript(app)  # it opened on all of them, and it is there

        await driver.press("shift+tab")
        await driver.pause()
        assert "go on?" not in transcript(app)  # nor on a conversation's own
        await _types(driver, "to the agent")
        await until(lambda: bool(link(app).asked_for("say")), driver)
        assert link(app).asked_for("say")[0]["to"] == "builder/1"
        assert app._pending  # still up, since that line went to the agent

        await driver.press("tab")
        await driver.pause()
        assert app._attached == EVERY
        await _types(driver, "yes")
        await until(lambda: bool(link(app).asked_for("answer")), driver)
        assert link(app).asked_for("answer") == [
            {"do": "answer", "question": "q1", "text": "yes"}
        ]


@pytest.mark.timeout(60)
async def test_an_ended_conversation_leaves_the_ring_and_can_still_be_read() -> None:
    """Stepping is held to what is running, and the monitor reaches the rest by name."""
    app = Humanize()
    async with app.run_test() as driver:
        await _both_working(app, driver)
        told(app, event("reviewer/1", "text", "said before it ended"))
        told(app, event("reviewer/1", "ends"))
        await driver.pause()

        assert app._ring() == [EVERY, "builder/1"]
        app._now_reading("reviewer/1")
        await driver.pause()
        assert "said before it ended" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_on_one_outworlder_s_transcript_is_that_one_s_alone() -> None:
    """Two waiting to be told what next, and the line goes to the one it was typed at."""
    app = Humanize()
    async with app.run_test() as driver:
        # A run, and no turn open in it: each is told what to say next.
        holding(app, outworlders=["alice", "bob"])
        alice = asked("q1", "alice", "alice?", mode="listen")
        bob = asked("q2", "bob", "bob?", mode="listen")
        told(app, alice, bob, pending(alice, bob))
        await driver.pause()

        app._now_reading("outworlder:bob")
        await _types(driver, "for bob")
        await until(lambda: bool(link(app).asked_for("answer")), driver)
        assert link(app).asked_for("answer") == [
            {"do": "answer", "question": "q2", "text": "for bob"}
        ]

        # And one typed at an outworlder asking nothing is refused rather than left for
        # whichever outworlder reads the queue next.
        await _types(driver, "for bob again")
        await until(lambda: "bob is not asking anything" in transcript(app), driver)
        assert len(link(app).asked_for("answer")) == 1
        assert not link(app).asked_for("say")

        app._now_reading(EVERY)
        await _types(driver, "for alice")
        await until(lambda: len(link(app).asked_for("answer")) == 2, driver)
        assert link(app).asked_for("answer")[-1] == {
            "do": "answer",
            "question": "q1",
            "text": "for alice",
        }


@pytest.mark.timeout(60)
async def test_claiming_an_outworlder_asks_the_runs_and_is_drawn_as_yours() -> None:
    """Typed on its own transcript, since which role is meant is the one being read."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human"])
        app._now_reading("outworlder:human")
        await driver.pause()

        await _types(driver, "/claim")
        await until(lambda: bool(link(app).asked_for("claim")), driver)
        assert link(app).asked_for("claim") == [{"do": "claim", "role": "human"}]
        await until(
            lambda: "yours to answer, and nobody else's" in transcript(app), driver
        )

        told(app, _frontends(c1="you@tui"), snapshot("claims", claims={"human": "c1"}))
        await driver.pause()
        assert any(
            "human · outworlder · yours" in one for one in app._outworlder_lines()
        )

        # Again, and it is given back: a switch, as `/afk` is.
        await _types(driver, "/claim")
        await until(lambda: bool(link(app).asked_for("release")), driver)
        assert link(app).asked_for("release") == [{"do": "release", "role": "human"}]


@pytest.mark.timeout(60)
async def test_claiming_is_refused_off_an_outworlder_s_transcript() -> None:
    """On the one every agent is on there is no one role for it to mean."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human"])

        await _types(driver, "/claim")
        await until(lambda: "/claim works on" in transcript(app), driver)

        assert not link(app).asked_for("claim")


@pytest.mark.timeout(60)
async def test_a_role_another_frontend_holds_is_theirs_to_answer() -> None:
    """Drawn as theirs, not answered here, and said to be theirs where it is typed at."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, "builder/1", outworlders=["human"])
        told(
            app,
            _frontends(c1="you@tui", c2="bob@tui"),
            snapshot("claims", claims={"human": "c2"}),
        )
        question = asked("q1", "human", "which way?", owner="c2")
        told(app, question, pending(question))
        await driver.pause()

        assert any(
            "human · outworlder · bob@tui's" in one for one in app._outworlder_lines()
        )
        assert "bob@tui's to answer" in transcript(app)
        # On the one every agent is on, it is not this interface's to answer: said instead.
        assert app._answers_to() is None
        await _types(driver, "a word for the run")
        await until(lambda: bool(link(app).asked_for("say")), driver)
        assert not link(app).asked_for("answer")

        app._now_reading("outworlder:human")
        await _types(driver, "mine")
        await until(
            lambda: "human is bob@tui's to answer, not yours" in transcript(app), driver
        )
        assert not link(app).asked_for("answer")

        # And once they answer it, who did is on the transcript.
        told(
            app, _answered("q1", "human", "north", by="bob@tui", client="c2"), pending()
        )
        await driver.pause()
        assert "north · by bob@tui" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_role_taken_from_this_interface_says_whose_it_is_now() -> None:
    """A take-over is said to the one it was taken from, once it is reading live."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human"])
        told(
            app,
            _frontends(c1="you@tui", c2="bob@tui"),
            snapshot("claims", claims={"human": "c1"}),
            {"type": "live", "seq": 0, "elided": 0},
        )
        await driver.pause()

        told(app, snapshot("claims", claims={"human": "c2"}))
        await driver.pause()

        assert "human is bob@tui's to answer now" in transcript(app)


@pytest.mark.timeout(60)
async def test_away_on_an_outworlder_s_transcript_is_asked_for_that_one_alone() -> None:
    """Every one of them from where all of them are, one from its own transcript."""
    app = Humanize()
    async with app.run_test() as driver:
        holding(app, outworlders=["human"])
        app._now_reading("outworlder:human")
        await driver.pause()

        await _types(driver, "/afk")
        await until(lambda: bool(link(app).asked_for("afk")), driver)
        assert link(app).asked_for("afk") == [
            {"do": "afk", "on": True, "role": "human"}
        ]
        await until(lambda: "away as human" in transcript(app), driver)

        # How it stands is the runs' to say, and the status line says it once they have.
        told(app, snapshot("away", all=False, of={"human": True}))
        await driver.pause()
        assert app._away_marker() == "afk human"

        app._now_reading(EVERY)
        await _types(driver, "/afk off")
        await until(lambda: len(link(app).asked_for("afk")) == 2, driver)
        assert link(app).asked_for("afk")[-1] == {"do": "afk", "on": False}
