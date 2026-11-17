"""`flame_chase`: two agents take turns on the same task, a fresh session each turn."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import Budget, CostExceeded, DurationExceeded, HarnessRefused
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
    assert len(set(map(id, doubles.sessions(first) + doubles.sessions(second)))) == 4
    assert state == {"turn": 1}


async def test_a_failed_turn_ends_the_run(chase: Any) -> None:
    first = doubles.agent(HarnessRefused("signed out"))
    second = doubles.agent()

    with pytest.raises(HarnessRefused, match="signed out"):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({}),
            first_chaser=first,
            second_chaser=second,
        )

    second.run.assert_not_awaited()


async def test_a_resumed_run_picks_up_with_whoever_was_next(chase: Any) -> None:
    first = doubles.agent()
    second = doubles.agent(CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({"turn": 1}),
            first_chaser=first,
            second_chaser=second,
        )

    first.run.assert_not_awaited()
    second.run.assert_awaited_once()


async def test_each_chaser_turn_is_held_to_its_own_quota(chase: Any) -> None:
    first = doubles.agent("a")
    second = doubles.agent(CostExceeded("spent"))

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context({}),
            params={"first_chaser_cost": "1.5", "first_chaser_duration": "600"},
            first_chaser=first,
            second_chaser=second,
        )

    assert first.run.await_args.kwargs["budget"] == Budget(
        cost=1.5, duration=datetime.timedelta(seconds=600), graceful=False
    )
    assert second.run.await_args.kwargs["budget"] is None


async def test_a_turn_out_of_its_quota_hands_over_to_the_other_chaser(
    chase: Any,
) -> None:
    quota = DurationExceeded("the turn ran past its deadline")
    quota.own = True
    first = doubles.agent(quota)
    second = doubles.agent(CostExceeded("spent"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            chase.flame_chase,
            "t",
            ctx=doubles.context(state),
            params={"first_chaser_duration": "60"},
            first_chaser=first,
            second_chaser=second,
        )

    first.run.assert_awaited_once()
    second.run.assert_awaited_once()
    assert state == {"turn": 1}
