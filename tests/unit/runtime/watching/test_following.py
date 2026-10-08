"""`hmz.runtime.watching.following`: what every frontend works out of a host's records."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import prices
from hmz.runtime.watching.following import Following

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


@pytest.fixture(autouse=True)
def unpriced(monkeypatch: pytest.MonkeyPatch) -> None:
    """No price list read off the disk: what is counted is in tokens here."""

    def cost(usage: Mapping[str, float], model: str) -> float | None:
        return None

    monkeypatch.setattr(prices, "cost", cost)


@pytest.fixture
def following() -> Iterator[Following]:
    """A frontend following run 1, which stops reading logs once the test is done."""
    one = Following()
    one.started({"run": 1, "began": 0.0})
    yield one
    one.ended({"run": 1})


def _event(**said: Any) -> dict[str, Any]:
    """One `event` record as a host sends it, with whatever the test says over the rest."""
    record: dict[str, Any] = {
        "run": 1,
        "key": "builder/1",
        "session": "builder/1",
        "agent": "builder",
        "cli": "claude",
        "model": "big",
        "ident": "",
        "kind": "text",
        "text": "",
        "whose": "",
        "tokens": {},
        "spent": {},
        "mono": 1.0,
    }
    return record | said


def test_a_turn_spent_on_two_models_divides_its_kinds_by_what_each_took(
    following: Following,
) -> None:
    following.heard(
        _event(
            kind="result",
            tokens={"big": 300, "small": 100},
            spent={"input": 200.0, "output": 200.0},
        )
    )

    spending = {spend.model: spend for spend in following.monitor.spending()}
    assert spending["big"].tokens == 300
    assert spending["big"].kinds == {"input": 150.0, "output": 150.0}
    assert spending["small"].kinds == {"input": 50.0, "output": 50.0}


def test_a_run_unwinding_behind_the_next_is_its_agents_alone(
    following: Following,
) -> None:
    following.started({"run": 2, "began": 0.0})

    said = following.heard(
        _event(run=1, kind="begins", tokens={"big": 10}, spent={"output": 10.0})
    )

    assert said is None
    assert following.monitor.shape().turns == {"builder": 1}
    assert following.monitor.shape(sessions=True).turns == {}
    following.ended({"run": 2})
