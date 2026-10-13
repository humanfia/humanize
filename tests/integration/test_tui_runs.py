"""A run from the prompt: a line becomes a turn, and the run is steered, cut off and stopped."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import JOURNAL, epics
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.pick import STOPS, Leaves
from tests.integration.doubles_tui import (
    MODEL,
    RUNS,
    SIZE,
    heard,
    on,
    opened,
    own_flow,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


#: A flow that asks the person something of its own between two turns of its one agent: a
#: question that is part of no conversation, put as `@local/writes` so that `/flow` sets it up.
ASKS = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams
from hmz.flows import LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def writes(task: str, *, agents: Agents, envs: Envs, params: FlowParams,
                 ctx: FlowContext) -> None:
    coder, human = agents["coder"], agents["human"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=envs["workspace"])
    answer = await human.run(f"Ship {said}?", session=await human.spawn())
    await coder.run(answer, session=session, env=envs["workspace"])
"""


def ended(workspace: Path) -> str:
    """How the one run in the workspace ended, as its record says, or "" while it has not."""
    (epic,) = epics(workspace)
    said = [json.loads(one) for one in (epic / JOURNAL).read_text().splitlines()]
    return next((str(one["how"]) for one in said if one.get("event") == "ended"), "")


async def test_a_line_is_the_task_and_the_agent_s_answer_is_drawn(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")

        drawn = await shows(pilot, "heard hello", "waiting for you")

    assert "❯ hello" in drawn
    (argv,) = started(workspace)
    assert argv[argv.index("--model") + 1] == MODEL
    assert argv[argv.index("--effort") + 1] == "high"
    assert heard(workspace) == ["hello"]


async def test_every_line_after_the_first_is_a_turn_of_the_same_conversation(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first")
        await typed(pilot, "second")
        await shows(pilot, "heard second")

    assert heard(workspace) == ["first", "second"]
    assert len(started(workspace)) == 1  # one agent process, holding one conversation


async def test_a_line_typed_while_a_turn_runs_is_put_into_that_turn(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for more")
        await shows(pilot, "still on it")

        await typed(pilot, "and this")

        await shows(pilot, "heard wait for more then and this")

    assert heard(workspace) == ["wait for more", "and this"]


async def test_two_ctrl_c_cut_the_turn_off_and_end_the_run_as_stopped(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait forever")
        await shows(pilot, "still on it")

        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to stop the flow")
        assert "stopping the flow" not in screen(app)

        await pilot.press("ctrl+c")
        await shows(pilot, "stopping the flow", "turn cut off")
        await until(pilot, lambda: ended(workspace) == "stopped", "the run to end")
        assert app.is_running  # the interface stays, for the next run


async def test_stop_ends_a_run_waiting_on_you_without_asking(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "waiting for you")

        await typed(pilot, "/stop")

        await shows(pilot, "stopping the flow")
        await until(pilot, lambda: ended(workspace) == "stopped", "the run to end")


async def test_a_flow_that_will_not_load_is_said_and_the_interface_stays(
    workspace: Path,
) -> None:
    flow = workspace / "broken"
    flow.mkdir()
    (flow / "__init__.py").write_text('raise FileNotFoundError("no prompt.md here")\n')

    app = Humanize(flow=str(flow), agents={"coder": Runs(RUNS)})
    async with app.run_test(size=SIZE) as pilot:
        await typed(pilot, "do it")

        await shows(pilot, "prompt.md")
        assert app.is_running
    assert started(workspace) == []


async def test_exit_while_a_run_is_going_asks_and_stopping_it_ends_both(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait a while")
        await shows(pilot, "still on it")

        await typed(pilot, "/exit")
        await on(pilot, Leaves)
        await shows(pilot, "A flow is running.", "Stop the flow and exit", "Cancel")
        await pilot.click(f"#act-{STOPS}")

        await until(pilot, lambda: not app.is_running, "the interface to close")
    assert ended(workspace) == "stopped"


async def test_a_line_typed_reading_the_conversation_between_turns_is_its_next_turn(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait first")
        # Read already: a run lands on the agent of the first conversation it opens.
        await shows(pilot, "still on it", "─ reading ")
        await typed(pilot, "more")
        await shows(pilot, "heard wait first then more")

        await typed(pilot, "second")

        await shows(pilot, "heard second")
    assert heard(workspace) == ["wait first", "more", "second"]


async def test_what_the_agent_stops_to_ask_is_shown_and_answered_in_its_conversation(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "ask me")
        await shows(pilot, "─ reading ", "Which colour? (red / blue)", "type an answer")

        await typed(pilot, "blue")

        drawn = await shows(pilot, "picked blue")
    assert "❯ blue" in drawn


async def test_a_question_the_flow_asks_of_its_own_is_shown_and_answered_where_you_read(
    workspace: Path,
) -> None:
    own_flow(workspace, ASKS)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, "make it so")

        # Landed on the agent of the run's first conversation, with no view of every agent,
        # and the question put where it is read rather than on a transcript nobody reads.
        drawn = await shows(
            pilot,
            "─ reading ",
            "❯ make it so",
            "Ship heard make it so?",
            "type an answer",
        )
        assert "all agents" not in drawn
        await typed(pilot, "yes")

        await shows(pilot, "heard yes", "the flow is done")
    assert heard(workspace) == ["make it so", "yes"]
