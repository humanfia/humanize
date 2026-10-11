"""`continue_loop`: the task once, then "continue" until the budget is spent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import CostExceeded, HarnessRefused
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def loop(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "continue_loop")


def test_continue_loop_keeps_nothing_and_needs_one_agent(loop: Any) -> None:
    declared = loop.continue_loop.declared
    assert declared["resumable"] is False
    assert declared["agents"].__required_keys__ == {"agent"}
    assert declared["envs"].__required_keys__ == {"workspace"}


async def test_the_task_goes_once_and_then_continue_in_one_session(loop: Any) -> None:
    agent = doubles.agent("a", "", "c", CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            loop.continue_loop, "the task", ctx=doubles.context(), agent=agent
        )

    assert doubles.prompts(agent) == ["the task", "continue", "continue", "continue"]
    agent.spawn.assert_awaited_once()
    assert len(set(map(id, doubles.sessions(agent)))) == 1


async def test_a_failed_turn_ends_the_run(loop: Any) -> None:
    agent = doubles.agent("a", HarnessRefused("signed out"))

    with pytest.raises(HarnessRefused, match="signed out"):
        await doubles.call(loop.continue_loop, "t", ctx=doubles.context(), agent=agent)
