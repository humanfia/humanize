"""What a run may spend, and what it has: a budget limits something, and survives JSON."""

from __future__ import annotations

import datetime
import math

import pydantic
import pytest

from hmz.flows import Budget, Usage


@pytest.mark.parametrize(
    "limits",
    [
        {"duration": datetime.timedelta(hours=1)},
        {"cost": 2.5},
        {"output_tokens": 100_000},
        {"cost": 0},
        {"duration": 90, "cost": 1, "output_tokens": 5, "graceful": False},
    ],
)
def test_a_budget_limits_at_least_one_thing(limits: dict[str, object]) -> None:
    budget = Budget.model_validate(limits)
    assert (budget.duration, budget.cost, budget.output_tokens) != (None, None, None)


def test_a_budget_that_limits_nothing_is_refused() -> None:
    with pytest.raises(pydantic.ValidationError, match="at least one"):
        Budget()
    with pytest.raises(pydantic.ValidationError, match="at least one"):
        Budget(graceful=False)


@pytest.mark.parametrize(
    "limits",
    [
        {"cost": -0.01},
        {"cost": math.nan},
        {"output_tokens": -1},
        {"duration": datetime.timedelta(seconds=-1)},
        {"cost": 1, "hours": 2},
    ],
)
def test_a_negative_or_unknown_limit_is_refused(limits: dict[str, object]) -> None:
    with pytest.raises(pydantic.ValidationError):
        Budget.model_validate(limits)


def test_a_budget_is_graceful_unless_told_otherwise() -> None:
    assert Budget(cost=1).graceful
    assert not Budget(cost=1, graceful=False).graceful


def test_unlimited_is_an_infinite_cost_and_survives_json() -> None:
    unlimited = Budget(cost=math.inf)
    written = unlimited.model_dump_json()
    assert '"Infinity"' in written
    read = Budget.model_validate_json(written)
    assert read == unlimited
    assert read.cost == math.inf


def test_every_limit_survives_json() -> None:
    budget = Budget(
        duration=datetime.timedelta(hours=1, minutes=30, seconds=0.5),
        cost=12.75,
        output_tokens=200_000,
        graceful=False,
    )
    assert Budget.model_validate_json(budget.model_dump_json()) == budget
    assert Budget.model_validate(budget.model_dump(mode="json")) == budget


def test_a_budget_is_a_value() -> None:
    budget = Budget(cost=1)
    with pytest.raises(pydantic.ValidationError):
        budget.cost = 2
    assert hash(budget) == hash(Budget(cost=1))


def test_usage_starts_at_nothing() -> None:
    spent = Usage()
    assert spent.duration == datetime.timedelta(0)
    assert spent.cost == 0.0
    assert spent.output_tokens == 0


def test_usage_survives_json() -> None:
    spent = Usage(duration=datetime.timedelta(minutes=3), cost=0.42, output_tokens=1234)
    assert Usage.model_validate_json(spent.model_dump_json()) == spent
