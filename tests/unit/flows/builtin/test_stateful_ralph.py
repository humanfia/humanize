"""`stateful_ralph`: the task again and again, in one session that remembers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    CostExceeded,
    HarnessDropped,
    HarnessNotInstalled,
    HarnessSandboxed,
)
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


async def test_every_round_is_the_task_in_the_one_session(ralph: Any) -> None:
    agent = doubles.agent("one", "two", CostExceeded("spent"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            ralph.stateful_ralph, "fix it", ctx=doubles.context(state), agent=agent
        )

    assert doubles.prompts(agent) == ["fix it"] * 3
    agent.spawn.assert_awaited_once()
    assert len(set(map(id, doubles.sessions(agent)))) == 1
    assert {one.kwargs["env"] for one in agent.run.await_args_list} == {
        doubles.WORKSPACE
    }
    assert state == {"rounds": 3}


async def test_it_stops_after_three_rounds_in_a_row_with_nothing(
    ralph: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    agent = doubles.agent("", "", "said", "", "", "")
    state: dict[str, Any] = {}

    await doubles.call(
        ralph.stateful_ralph, "t", ctx=doubles.context(state), agent=agent
    )

    assert agent.run.await_count == 6
    assert state == {"rounds": 6}
    assert "stopping: 3 rounds in a row" in capsys.readouterr().out


async def test_a_failed_round_counts_as_nothing(
    ralph: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    agent = doubles.agent(HarnessDropped("cut off"), HarnessDropped("x"), "")

    await doubles.call(ralph.stateful_ralph, "t", ctx=doubles.context({}), agent=agent)

    assert agent.run.await_count == 3
    assert "round 1 failed: cut off" in capsys.readouterr().out


@pytest.mark.parametrize("error", [HarnessNotInstalled, HarnessSandboxed])
async def test_a_cli_that_cannot_start_ends_the_run(
    ralph: Any, error: type[Exception]
) -> None:
    agent = doubles.agent(error("cannot start"))

    with pytest.raises(error, match="cannot start"):
        await doubles.call(
            ralph.stateful_ralph, "t", ctx=doubles.context({}), agent=agent
        )


async def test_a_resumed_run_carries_on_counting(ralph: Any) -> None:
    agent = doubles.agent(CostExceeded("spent"))
    state: dict[str, Any] = {"rounds": 2}

    with pytest.raises(CostExceeded):
        await doubles.call(
            ralph.stateful_ralph, "t", ctx=doubles.context(state), agent=agent
        )

    assert state == {"rounds": 3}
