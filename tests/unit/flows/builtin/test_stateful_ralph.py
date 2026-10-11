"""`stateful_ralph`: the task again and again, in one session that remembers."""

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
    return doubles.builtin(monkeypatch, "stateful_ralph")


def test_stateful_ralph_is_resumable_and_needs_one_agent(ralph: Any) -> None:
    declared = ralph.stateful_ralph.declared
    assert declared["resumable"] is True
    assert declared["agents"].__required_keys__ == {"agent"}
    assert declared["envs"].__required_keys__ == {"workspace"}


async def test_every_round_is_the_task_in_the_one_session_kept(ralph: Any) -> None:
    agent = doubles.agent("one", "", CostExceeded("spent"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            ralph.stateful_ralph, "fix it", ctx=doubles.context(state), agent=agent
        )

    assert doubles.prompts(agent) == ["fix it"] * 3
    agent.spawn.assert_awaited_once()
    (session,) = set(doubles.sessions(agent))
    assert {one.kwargs["env"] for one in agent.run.await_args_list} == {
        doubles.WORKSPACE
    }
    assert state == {"session": session}


async def test_a_resumed_run_carries_the_kept_session_on(ralph: Any) -> None:
    kept = object()
    agent = doubles.agent(CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            ralph.stateful_ralph,
            "t",
            ctx=doubles.context({"session": kept}),
            agent=agent,
        )

    agent.spawn.assert_not_awaited()
    assert doubles.sessions(agent) == [kept]


async def test_a_failed_turn_ends_the_run(ralph: Any) -> None:
    agent = doubles.agent(HarnessRefused("signed out"))
    state: dict[str, Any] = {}

    with pytest.raises(HarnessRefused, match="signed out"):
        await doubles.call(
            ralph.stateful_ralph, "t", ctx=doubles.context(state), agent=agent
        )

    assert state == {}
