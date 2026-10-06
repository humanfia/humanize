"""`continue_loop`: the task once, then "continue" until the budget is spent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import CostExceeded, HarnessDropped, HarnessKilled
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def loop(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "continue_loop")


def test_continue_loop_is_resumable_and_needs_one_agent(loop: Any) -> None:
    declared = loop.continue_loop.declared
    assert declared["resumable"] is True
    assert declared["agents"].__required_keys__ == {"agent"}
    assert declared["envs"].__required_keys__ == {"workspace"}


async def test_the_task_goes_once_and_then_continue_in_one_session(loop: Any) -> None:
    agent = doubles.agent("started", "more", CostExceeded("spent"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded, match="spent"):
        await doubles.call(
            loop.continue_loop, "the task", ctx=doubles.context(state), agent=agent
        )

    assert doubles.prompts(agent) == ["the task", "continue", "continue"]
    agent.spawn.assert_awaited_once()
    assert len(set(map(id, doubles.sessions(agent)))) == 1
    assert state == {"rounds": 3}


async def test_a_turn_with_nothing_or_a_failure_is_sent_again(loop: Any) -> None:
    agent = doubles.agent("", HarnessDropped("cut"), "started", CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            loop.continue_loop, "the task", ctx=doubles.context({}), agent=agent
        )

    assert doubles.prompts(agent) == ["the task"] * 3 + ["continue"]


async def test_three_failures_in_a_row_end_it_with_the_last(loop: Any) -> None:
    agent = doubles.agent(
        HarnessDropped("1"),
        HarnessDropped("2"),
        "fine",
        HarnessDropped("3"),
        HarnessDropped("4"),
        HarnessKilled("5"),
    )

    with pytest.raises(HarnessKilled, match="5"):
        await doubles.call(
            loop.continue_loop, "t", ctx=doubles.context({}), agent=agent
        )

    assert agent.run.await_count == 6


async def test_a_resumed_run_carries_on_counting(loop: Any) -> None:
    agent = doubles.agent(CostExceeded("spent"))
    state: dict[str, Any] = {"rounds": 4}

    with pytest.raises(CostExceeded):
        await doubles.call(
            loop.continue_loop, "t", ctx=doubles.context(state), agent=agent
        )

    assert state == {"rounds": 5}
    assert doubles.prompts(agent) == ["t"]
