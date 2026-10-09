"""Every builtin flow run through `hmz.sdk.Hmz`, on the local workspace, by scripted agents.

The agents are the SDK's own fakes (`hmz.sdk.fakes`) and everything else is real: the flow
is found and loaded by name, handed a local environment on a project of the test's own,
driven by the engine under its budget, and written down as an epic that `Hmz.epics` reads
back -- and picked up from there by `resume`.

The loops pause five seconds between rounds, so a test that needs a second round takes that
long; a round is ended at once by a cost that is not graceful, which stops the turn that
spends it.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from hmz.flows import (
    BudgetExceeded,
    CostExceeded,
    DurationExceeded,
    HarnessKind,
    OutputTokensExceeded,
)
from hmz.sdk import Hmz, Refused, fakes
from tests.integration.doubles_core import MODEL, install

if TYPE_CHECKING:
    from pathlib import Path

#: What a run may spend: the turn that takes it past 0.5 is stopped where it is. Agents
#: costing 0.3 a turn are stopped in their second, agents costing 1 in their first.
BUDGET = {"cost": 0.5, "graceful": False}


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


def _agent(
    reply: fakes.Reply = "worked", *, cost: float = 1.0
) -> fakes.FakeAgentDriver:
    """A scripted `claude`, every turn of which costs `cost`."""
    return fakes.FakeAgentDriver(HarnessKind.CLAUDE, reply=reply, cost=cost)


def test_chat_talks_until_the_person_says_nothing(project: Path) -> None:
    def heard(prompt: str, **_: object) -> str:
        return f"heard {prompt}"

    assistant = _agent(heard, cost=0.0)
    person = fakes.FakeOutworlder(["and then?", ""])
    hmz = Hmz(project)

    hmz.run("chat", "hello", agents={"assistant": assistant}, outworlder=person).run()

    assert assistant.prompts == ["hello", "and then?"]
    assert person.asked == ["heard hello", "heard and then?"]
    # One conversation: the second turn is said in the session of the first.
    assert len(assistant.sessions) == 1
    (epic,) = hmz.epics.all()
    ran = hmz.epics.read(epic)
    assert ran is not None
    assert (ran.flow, ran.task, ran.how) == ("chat", "hello", "done")


def test_goal_sets_the_task_as_the_agents_goal(project: Path) -> None:
    worker = _agent(cost=0.0)

    Hmz(project).run("goal", "win", agents={"worker": worker}, budget={"cost": 1}).run()

    assert worker.prompts == ["/goal win"]


def test_goal_refuses_an_agent_whose_harness_has_no_goal_command(project: Path) -> None:
    with pytest.raises(Refused):
        Hmz(project).run(
            "goal",
            "win",
            agents={"worker": fakes.FakeAgentDriver(HarnessKind.OPENCODE)},
            budget={"cost": 1},
        )


def test_ralph_loop_opens_a_fresh_session_every_round(project: Path) -> None:
    agent = _agent(cost=0.3)

    with pytest.raises(CostExceeded):
        Hmz(project).run(
            "ralph_loop", "the task", agents={"agent": agent}, budget=BUDGET
        ).run()

    assert agent.prompts == ["the task", "the task"]
    assert len(agent.sessions) == 2


def test_stateful_ralph_says_the_task_again_in_one_session(project: Path) -> None:
    agent = _agent(cost=0.3)

    with pytest.raises(CostExceeded):
        Hmz(project).run(
            "stateful_ralph", "the task", agents={"agent": agent}, budget=BUDGET
        ).run()

    assert agent.prompts == ["the task", "the task"]
    assert len(agent.sessions) == 1


def test_continue_loop_nudges_on_after_the_first_turn(project: Path) -> None:
    agent = _agent(cost=0.3)

    with pytest.raises(CostExceeded):
        Hmz(project).run(
            "continue_loop", "the task", agents={"agent": agent}, budget=BUDGET
        ).run()

    assert agent.prompts == ["the task", "continue"]


def test_flame_chase_passes_the_task_between_two_chasers(project: Path) -> None:
    first, second = _agent(cost=0.3), _agent(cost=0.3)

    with pytest.raises(CostExceeded):
        Hmz(project).run(
            "flame_chase",
            "the task",
            agents={"first_chaser": first, "second_chaser": second},
            budget=BUDGET,
        ).run()

    assert first.prompts == ["the task"]
    assert second.prompts == ["the task"]


def test_rlar_ends_when_the_reviewer_says_it_is_done(project: Path) -> None:
    actor = _agent(cost=0.0)
    reviewer = _agent({"done": True, "notes": "all of it, tested"}, cost=0.0)

    returned = (
        Hmz(project)
        .run(
            "rlar",
            "the task",
            agents={"actor": actor, "reviewer": reviewer},
            budget={"cost": 1},
        )
        .run()
    )

    assert returned == "all of it, tested"
    assert actor.prompts == ["the task"]
    (review,) = reviewer.prompts
    # The task, then what the actor said as it ended its turn, which is held to the repository.
    assert review.index("the task") < review.index("worked")


def test_rlar_picked_up_hands_a_fresh_actor_the_last_review(project: Path) -> None:
    hmz = Hmz(project)
    not_yet = {"done": False, "notes": "the tests are missing"}

    # The actor's second turn spends it, after the first round's review is kept.
    with pytest.raises(CostExceeded):
        hmz.run(
            "rlar",
            "the task",
            agents={
                "actor": _agent(cost=0.3),
                "reviewer": _agent(not_yet, cost=0.0),
            },
            budget=BUDGET,
        ).run()
    (first,) = hmz.epics.all()
    assert hmz.epics.picks_up(first)
    assert hmz.epics.state(first)["notes"] == "the tests are missing"

    actor = _agent(cost=0.0)
    hmz.run(
        "rlar",
        "the task",
        agents={
            "actor": actor,
            "reviewer": _agent({"done": True, "notes": "done"}, cost=0.0),
        },
        budget={"cost": 1},
        resume=True,
    ).run()

    (prompt,) = actor.prompts
    assert prompt.startswith("the task")
    assert prompt.endswith("the tests are missing")
    second = hmz.epics.all()[-1]
    ran = hmz.epics.read(second)
    assert ran is not None
    assert ran.picked_up == first.name


def test_a_cost_spent_gracefully_lets_the_turn_finish(project: Path) -> None:
    agent = _agent(cost=1.0)

    with pytest.raises(CostExceeded):
        Hmz(project).run(
            "stateful_ralph", "the task", agents={"agent": agent}, budget={"cost": 0.5}
        ).run()

    # The turn that spent it answered; the next one was refused before it was said.
    assert agent.prompts == ["the task"]


def test_a_duration_spent_stops_a_turn_under_way(project: Path) -> None:
    async def slow(prompt: str, **_: object) -> str:
        await asyncio.sleep(60)
        return prompt

    started = time.monotonic()
    with pytest.raises(DurationExceeded):
        Hmz(project).run(
            "goal",
            "win",
            agents={"worker": _agent(slow, cost=0.0)},
            budget={"duration": 0.5, "graceful": False},
        ).run()
    assert time.monotonic() - started < 30


def test_output_tokens_spent_end_the_run(project: Path) -> None:
    agent = fakes.FakeAgentDriver(HarnessKind.CLAUDE, output_tokens=10)

    with pytest.raises(OutputTokensExceeded):
        Hmz(project).run(
            "continue_loop",
            "the task",
            agents={"agent": agent},
            budget={"output_tokens": 5, "graceful": False},
        ).run()


def test_every_budget_exceeded_is_a_budget_exceeded(project: Path) -> None:
    with pytest.raises(BudgetExceeded):
        Hmz(project).run(
            "ralph_loop", "the task", agents={"agent": _agent()}, budget=BUDGET
        ).run()


def test_a_loop_is_refused_without_a_budget(project: Path) -> None:
    with pytest.raises(Refused, match="budget"):
        Hmz(project).run("ralph_loop", "the task", agents={"agent": _agent()})


def test_a_role_the_flow_does_not_declare_is_refused(project: Path) -> None:
    with pytest.raises(Refused):
        Hmz(project).run(
            "goal",
            "win",
            agents={"worker": _agent(), "stranger": _agent()},
            budget={"cost": 1},
        )


def test_a_flow_that_is_not_there_is_refused(project: Path) -> None:
    with pytest.raises(Refused):
        Hmz(project).run("no_such_flow", "the task", budget={"cost": 1})


def test_exec_drives_the_standin_cli_through_a_whole_rlar(project: Path) -> None:
    returned = Hmz(project).exec(
        [
            "-f",
            "rlar",
            "-a",
            f"actor=claude/{MODEL},reviewer=claude/{MODEL}:low",
            "-p",
            "budget.duration=2m",
            "build it",
        ]
    )

    assert returned == "reviewed"
    assert (project / "landed.txt").read_text() == "build it\n"
