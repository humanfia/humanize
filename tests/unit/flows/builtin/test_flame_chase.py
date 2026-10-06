"""`flame_chase`: two agents take turns on the same task, a fresh session each turn."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import CostExceeded, HarnessDropped, HarnessKilled
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def chase(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "flame_chase")


def test_flame_chase_is_resumable_and_needs_two_chasers(chase: Any) -> None:
    declared = chase.flame_chase.declared
    assert declared["resumable"] is True
    assert declared["agents"].__required_keys__ == {"first_chaser", "second_chaser"}


async def test_the_chasers_take_turns_each_in_a_fresh_session(chase: Any) -> None:
    first = doubles.agent("a", "b")
    second = doubles.agent("c", CostExceeded("spent"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "the task",
            ctx=doubles.context(state),
            first_chaser=first,
            second_chaser=second,
        )

    assert doubles.prompts(first) == ["the task"] * 2
    assert doubles.prompts(second) == ["the task"] * 2
    assert first.spawn.await_count == 2
    assert second.spawn.await_count == 2
    assert len(set(map(id, doubles.sessions(first) + doubles.sessions(second)))) == 4
    # Three turns done: the first round whole, and the first chaser's half of the next.
    assert state == {"turn": 1, "rounds": 1}


async def test_a_failed_turn_passes_to_the_other(chase: Any) -> None:
    first = doubles.agent(HarnessDropped("cut"), CostExceeded("spent"))
    second = doubles.agent("took it")

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({}),
            first_chaser=first,
            second_chaser=second,
        )

    assert second.run.await_count == 1


async def test_three_failures_in_a_row_end_it_with_the_last(chase: Any) -> None:
    first = doubles.agent(HarnessDropped("1"), HarnessKilled("3"))
    second = doubles.agent(HarnessDropped("2"))

    with pytest.raises(HarnessKilled, match="3"):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({}),
            first_chaser=first,
            second_chaser=second,
        )


async def test_a_success_resets_the_failures(chase: Any) -> None:
    first = doubles.agent(HarnessDropped("1"), HarnessDropped("3"), CostExceeded("x"))
    second = doubles.agent("fine", HarnessDropped("4"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({}),
            first_chaser=first,
            second_chaser=second,
        )


async def test_a_resumed_run_picks_up_with_whoever_was_next(chase: Any) -> None:
    first = doubles.agent(CostExceeded("spent"))
    second = doubles.agent("went")
    state: dict[str, Any] = {"turn": 1, "rounds": 4}

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context(state),
            first_chaser=first,
            second_chaser=second,
        )

    assert second.run.await_count == 1
    assert state == {"turn": 0, "rounds": 5}
