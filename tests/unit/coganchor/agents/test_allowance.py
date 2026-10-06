"""`hmz.coganchor.agents.allowance`: what a whole run may spend, and the ledger holding it."""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING, ClassVar

import pytest

from hmz.coganchor import prices
from hmz.coganchor.agents.allowance import (
    MILLION,
    Allowance,
    Ledger,
    Reading,
    blinded,
)
from hmz.coganchor.agents.config import AgentConfig
from hmz.coganchor.agents.event import Usage
from hmz.coganchor.agents.human import HumanAgent
from tests.unit.coganchor.agents.doubles_core import Scripted

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Dollars per output token, by model: what the price list says, as these tests have it.
_PRICED = {"priced": 1e-6, "dear": 1e-3}


@pytest.fixture(autouse=True)
def _prices(monkeypatch: pytest.MonkeyPatch) -> None:
    """A price list of the tests' own: `priced` and `dear` are on it, nothing else is."""

    def cost(usage: Mapping[str, float], model: str) -> float | None:
        per = _PRICED.get(model)
        return None if per is None else usage.get("output", 0.0) * per

    def price(model: str) -> object | None:
        return _PRICED.get(model)

    monkeypatch.setattr(prices, "cost", cost)
    monkeypatch.setattr(prices, "price", price)


class _Spender(Scripted):
    """An agent that has spent what it was told to, and counts its output."""

    counts: ClassVar[frozenset[str]] = frozenset({"output"})

    def __init__(self, model: str, output: float = 0.0) -> None:
        super().__init__(AgentConfig(model=model, effort=""))
        self.output = output
        self.stops = 0

    def spent(self) -> Usage:
        return Usage(input=1.0, output=self.output)

    def stop(self) -> None:
        self.stops += 1
        super().stop()


def test_million() -> None:
    assert MILLION == 1_000_000.0


def test_an_empty_allowance_bounds_nothing() -> None:
    allowance = Allowance()
    assert not allowance.bounded
    assert allowance.over(seconds=1e9, output=1e12, dollars=1e9) == ""


@pytest.mark.parametrize(
    ("allowance", "seconds", "output", "dollars", "over"),
    [
        (Allowance(hours=6), 6 * 3600 - 1, 0, None, ""),
        (Allowance(hours=6), 6 * 3600, 0, None, "6h"),
        (Allowance(tokens=2), 0, 1_999_999, None, ""),
        (Allowance(tokens=2), 0, 2_000_000, None, "2M output tokens"),
        (Allowance(dollars=50), 0, 0, 49.99, ""),
        (Allowance(dollars=50), 0, 0, 50.0, "$50"),
        (Allowance(dollars=50), 0, 0, None, ""),  # a bill nobody can read is not $0
        (Allowance(hours=1, dollars=0.5), 3600, 0, 1.0, "1h"),
    ],
)
def test_an_allowance_says_which_dimension_ran_out(
    allowance: Allowance,
    seconds: float,
    output: float,
    dollars: float | None,
    over: str,
) -> None:
    assert allowance.bounded
    assert allowance.over(seconds=seconds, output=output, dollars=dollars) == over


@pytest.mark.parametrize("field", ["hours", "tokens", "dollars"])
def test_an_allowance_cannot_be_less_than_nothing(field: str) -> None:
    with pytest.raises(ValueError, match="less than nothing"):
        Allowance(**{field: -1.0})


@pytest.mark.parametrize(
    ("allowance", "models", "counting", "blind"),
    [
        (Allowance(tokens=1, dollars=1), [], False, set[str]()),
        (Allowance(tokens=1), ["priced"], True, set[str]()),
        (Allowance(tokens=1), ["priced"], False, {"tokens"}),
        (Allowance(dollars=1), ["unknown"], True, {"dollars"}),
        (Allowance(dollars=1), ["unknown", "priced"], True, set[str]()),
        (Allowance(hours=1), ["unknown"], False, set[str]()),
    ],
)
def test_blinded_names_the_caps_nothing_can_read(
    allowance: Allowance, models: list[str], counting: bool, blind: set[str]
) -> None:
    assert blinded(allowance, models, counting=counting) == blind


def test_a_ledger_reads_every_agent_once() -> None:
    cheap, dear, unknown = (
        _Spender("priced", 1000),
        _Spender("dear", 10),
        _Spender("x", 5),
    )
    ledger = Ledger(Allowance(dollars=1), [cheap, dear])
    ledger.enrol(unknown)
    ledger.enrol(cheap)
    read = ledger.reads()
    assert isinstance(read, Reading)
    assert read.output == 1015
    assert read.dollars == pytest.approx(0.011)
    assert read.floor  # the unknown model's bill is missing
    assert read.blind == frozenset()
    assert read.seconds >= 0
    assert ledger.allowance == Allowance(dollars=1)
    assert ledger.began > 0


def test_a_ledger_of_nothing_priced_reads_no_money() -> None:
    spender = _Spender("x")
    read = Ledger(Allowance(dollars=1), [spender]).reads()
    assert read.dollars is None
    assert not read.floor
    assert read.blind == {"dollars"}


def test_the_person_at_the_prompt_is_not_counted() -> None:
    person = HumanAgent()
    spender = _Spender("priced")
    ledger = Ledger(Allowance(dollars=1), [person, spender])
    assert ledger.agents() == (spender,)


def test_a_ledger_holds_once_it_runs_out_and_stops_everyone_once() -> None:
    first, second = _Spender("priced", 10), _Spender("priced", 10)
    ledger = Ledger(Allowance(tokens=1e-5), [first, second])
    assert ledger.over() == "1e-05M output tokens"
    assert ledger.spent
    first.output = 0  # a reading that came back short does not unstop a run
    assert ledger.over() == "1e-05M output tokens"
    ledger.stops()
    ledger.stops()
    assert (first.stops, second.stops) == (1, 1)


def test_a_ledger_inside_its_allowance_is_not_spent() -> None:
    spender = _Spender("priced", 10)
    ledger = Ledger(Allowance(tokens=1), [spender])
    assert ledger.over() == ""
    assert not ledger.spent
    spender.output = 1e12
    assert Ledger(Allowance(), [spender]).over() == ""


def test_agents_a_run_no_longer_holds_drop_out() -> None:
    held = _Spender("priced")
    ledger = Ledger(Allowance(hours=1), [held, _Spender("priced")])
    gc.collect()
    assert ledger.agents() == (held,)
