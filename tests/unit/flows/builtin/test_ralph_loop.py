"""`ralph_loop`: the task again and again, a fresh session every round."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import CostExceeded, HarnessRefused
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def ralph(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "ralph_loop")


def test_ralph_loop_keeps_nothing_and_needs_one_agent(ralph: Any) -> None:
    declared = ralph.ralph_loop.declared
    assert declared["resumable"] is False
    assert declared["agents"].__required_keys__ == {"agent"}
    assert declared["envs"].__required_keys__ == {"workspace"}


async def test_each_round_is_a_fresh_session_given_the_task(ralph: Any) -> None:
    agent = doubles.agent("one", "", CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            ralph.ralph_loop, "fix it", ctx=doubles.context(), agent=agent
        )

    assert doubles.prompts(agent) == ["fix it"] * 3
    assert len(set(map(id, doubles.sessions(agent)))) == 3
    assert {one.kwargs["env"] for one in agent.run.await_args_list} == {
        doubles.WORKSPACE
    }


async def test_a_failed_turn_ends_the_run(ralph: Any) -> None:
    agent = doubles.agent("ok", HarnessRefused("signed out"))

    with pytest.raises(HarnessRefused, match="signed out"):
        await doubles.call(ralph.ralph_loop, "t", ctx=doubles.context(), agent=agent)

    assert agent.run.await_count == 2
