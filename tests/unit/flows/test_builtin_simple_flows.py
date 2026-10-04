"""Three of the loops humanize ships -- `goal`, `continue_loop`, `flame_chase` -- on fakes.

What each declares, every turn a run of it takes, and what a resumable one keeps for
`--resume`, with nothing started but the flow itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    Budget,
    CapabilityMissing,
    FlowParams,
    GoalCommandAgentMixin,
    HarnessKind,
    HarnessThrottled,
    OutputTokensExceeded,
)
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake
from tests.flows.kit import kept, module, shipped

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime.flowing import Declaration


@pytest.fixture(autouse=True)
def _instant(monkeypatch: pytest.MonkeyPatch) -> None:
    """No pause between turns: a test waits on nothing."""
    for name in ("continue_loop", "flame_chase"):
        monkeypatch.setattr(module(shipped(name)), "PAUSE", 0)


def failing(fails: set[int], turns: list[str], said: str = "worked") -> Any:
    """A reply that throttles on the turns numbered in `fails`, and records every prompt."""

    def reply(prompt: str, **_: Any) -> str:
        turns.append(prompt)
        if len(turns) in fails:
            raise HarnessThrottled("slow down")
        return said

    return reply


def roles(declared: Declaration) -> list[tuple[str, frozenset[type]]]:
    return [(role.name, role.capabilities) for role in declared.agents]


def test_goal_asks_for_an_agent_that_takes_goals() -> None:
    declared = shipped("goal").describe()

    assert declared.name == "goal"
    assert not declared.resumable
    assert roles(declared) == [("worker", frozenset({GoalCommandAgentMixin}))]
    assert [(role.name, role.auto) for role in declared.envs] == [("workspace", True)]
    assert declared.params is FlowParams


async def test_goal_sets_the_task_once_as_the_workers_goal() -> None:
    worker = FakeAgentDriver(reply="met")

    said = await run_fake(shipped("goal"), "ship it", agents={"worker": worker})

    assert said is None
    (session,) = worker.sessions
    assert session.prompts == ["/goal ship it"]


async def test_goal_refuses_a_harness_with_no_goal_command() -> None:
    worker = FakeAgentDriver(HarnessKind.GROK)

    with pytest.raises(CapabilityMissing, match="GoalCommandAgentMixin"):
        await run_fake(shipped("goal"), "ship it", agents={"worker": worker})

    assert worker.sessions == []


def test_continue_loop_is_one_resumable_agent() -> None:
    declared = shipped("continue_loop").describe()

    assert declared.name == "continue_loop"
    assert declared.resumable
    assert roles(declared) == [("agent", frozenset())]
    assert [(role.name, role.auto) for role in declared.envs] == [("workspace", True)]


async def test_continue_loop_nudges_one_session_until_the_budget_stops_it(
    tmp_path: Path,
) -> None:
    agent = FakeAgentDriver(reply=["", "worked", "", "worked"])
    journal = tmp_path / "run.jsonl"

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("continue_loop"),
            "do the thing",
            agents={"agent": agent},
            budget=Budget(output_tokens=4),
            journal=journal,
        )

    (session,) = agent.sessions
    assert session.prompts == ["do the thing", "do the thing", "continue", "continue"]
    assert kept(journal) == {"rounds": 5}


async def test_continue_loop_picked_up_counts_on_in_a_fresh_session(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("continue_loop"),
            "do the thing",
            agents={"agent": "worked"},
            budget=Budget(output_tokens=2),
            journal=journal,
        )
    agent = FakeAgentDriver(reply="worked")

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("continue_loop"),
            "do the thing",
            agents={"agent": agent},
            budget=Budget(output_tokens=2),
            journal=journal,
            resume=True,
        )

    (session,) = agent.sessions
    assert session.prompts == ["do the thing", "continue"]
    assert kept(journal) == {"rounds": 6}


async def test_continue_loop_sends_a_failed_turn_again_and_ends_on_three(
    tmp_path: Path,
) -> None:
    turns: list[str] = []
    journal = tmp_path / "run.jsonl"

    with pytest.raises(HarnessThrottled):
        await run_fake(
            shipped("continue_loop"),
            "do the thing",
            agents={"agent": failing({1, 3, 4, 5}, turns)},
            journal=journal,
        )

    assert turns == ["do the thing", "do the thing", "continue", "continue", "continue"]
    assert kept(journal) == {"rounds": 5}


def test_flame_chase_is_two_resumable_chasers() -> None:
    declared = shipped("flame_chase").describe()

    assert declared.name == "flame_chase"
    assert declared.resumable
    assert roles(declared) == [
        ("first_chaser", frozenset()),
        ("second_chaser", frozenset()),
    ]
    assert [(role.name, role.auto) for role in declared.envs] == [("workspace", True)]


def chasers(order: list[str]) -> dict[str, FakeAgentDriver]:
    """The two chasers, each writing its name into `order` as it takes a turn."""

    def chaser(name: str) -> FakeAgentDriver:
        def reply(prompt: str, **_: Any) -> str:
            order.append(name)
            return f"{name} worked on {prompt}"

        return FakeAgentDriver(reply=reply)

    return {name: chaser(name) for name in ("first_chaser", "second_chaser")}


async def test_flame_chase_takes_turns_in_fresh_sessions(tmp_path: Path) -> None:
    order: list[str] = []
    agents = chasers(order)
    journal = tmp_path / "run.jsonl"

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("flame_chase"),
            "chase it",
            agents=agents,
            budget=Budget(output_tokens=5),
            journal=journal,
        )

    assert order == ["first_chaser", "second_chaser"] * 2 + ["first_chaser"]
    sessions = [one for agent in agents.values() for one in agent.sessions]
    assert all(one.prompts in ([], ["chase it"]) for one in sessions)
    assert kept(journal) == {"turn": 1, "rounds": 2}


async def test_flame_chase_picked_up_starts_with_the_chaser_that_was_next(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("flame_chase"),
            "chase it",
            agents=chasers([]),
            budget=Budget(output_tokens=1),
            journal=journal,
        )
    order: list[str] = []

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("flame_chase"),
            "chase it",
            agents=chasers(order),
            budget=Budget(output_tokens=2),
            journal=journal,
            resume=True,
        )

    assert order == ["second_chaser", "first_chaser"]
    assert kept(journal) == {"turn": 1, "rounds": 1}


async def test_flame_chase_passes_a_failed_turn_on_and_ends_on_three(
    tmp_path: Path,
) -> None:
    turns: list[str] = []
    reply = failing({2, 3, 4}, turns)
    journal = tmp_path / "run.jsonl"

    with pytest.raises(HarnessThrottled):
        await run_fake(
            shipped("flame_chase"),
            "chase it",
            agents={"first_chaser": reply, "second_chaser": reply},
            journal=journal,
        )

    assert len(turns) == 4
    assert kept(journal) == {"turn": 1, "rounds": 1}
