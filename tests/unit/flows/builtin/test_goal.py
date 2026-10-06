"""`goal`: the task set once as the agent's own goal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import Agent, CapabilityNotGranted, GoalCommandAgentMixin
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def goal(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "goal")


def test_goal_asks_for_a_harness_with_a_goal_command(goal: Any) -> None:
    declared = goal.goal.declared
    assert declared["resumable"] is False
    assert declared["agents"].__required_keys__ == {"worker"}
    assert {Agent, GoalCommandAgentMixin} <= set(goal.Worker.__mro__)


async def test_the_task_is_one_goal_turn_in_one_session(goal: Any) -> None:
    worker = doubles.agent("met")

    assert (
        await doubles.call(goal.goal, "ship it", ctx=doubles.context(), worker=worker)
        is None
    )

    worker.spawn.assert_awaited_once()
    worker.run.assert_awaited_once_with(
        "/goal ship it",
        session=doubles.sessions(worker)[0],
        env=doubles.WORKSPACE,
    )


async def test_a_turn_that_fails_fails_the_flow(goal: Any) -> None:
    worker = doubles.agent(CapabilityNotGranted("no /goal"))

    with pytest.raises(CapabilityNotGranted, match="no /goal"):
        await doubles.call(goal.goal, "t", ctx=doubles.context(), worker=worker)
