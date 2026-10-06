"""`hmz.tui.monitor`: what a flow is doing, kept from the turns going past."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import prices
from hmz.tui.monitor import (
    Counted,
    Monitor,
    Shape,
    Spend,
    Under,
    lasting,
    short,
    thousands,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


#: What one token of each kind costs here, in dollars: a price list of the test's own.
_PRICE = {"input": 1.0, "output": 10.0, "cache_read": 0.1, "cache_write": 2.0}


@pytest.fixture(autouse=True)
def priced(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Prices as `hmz.coganchor.prices` would put them, for the model called `priced`."""
    asked: list[str] = []

    def cost(usage: Mapping[str, float], model: str) -> float | None:
        asked.append(model)
        if model != "priced":
            return None
        return sum(_PRICE.get(kind, 0.0) * count for kind, count in usage.items())

    monkeypatch.setattr(prices, "cost", cost)
    return asked


@pytest.mark.parametrize(
    ("count", "said"),
    [
        (0, "0"),
        (999, "999"),
        (999.4, "999"),
        (1000, "1.0k"),
        (12_345, "12.3k"),
        (999_999, "1000.0k"),
        (1_000_000, "1.00M"),
        (2_345_678, "2.35M"),
    ],
)
def test_thousands_abbreviates_once_a_count_stops_fitting(
    count: float, said: str
) -> None:
    assert thousands(count) == said


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0, "0s"),
        (59.9, "59s"),
        (60, "1m00s"),
        (61.5, "1m01s"),
        (3599, "59m59s"),
        (3600, "1h00m"),
        (3 * 3600 + 5 * 60 + 59, "3h05m"),
    ],
)
def test_lasting_reads_like_a_clock(seconds: float, said: str) -> None:
    assert lasting(seconds) == said


@pytest.mark.parametrize(
    ("agent", "said"),
    [
        ("ClaudeCodeAgent#abcdef", "claude#abcd"),
        ("CodexCLI#12", "codex#12"),
        ("KimiAgent#xyz9", "kimi#xyz9"),
        ("builder", "builder"),
        ("a-very-long-agent-name-indeed", "a-very-long-agen"),
    ],
)
def test_short_cuts_an_agent_name_down(agent: str, said: str) -> None:
    assert short(agent) == said


def test_a_new_monitor_has_seen_nothing() -> None:
    monitor = Monitor()

    assert monitor.now_working() == []
    assert monitor.spending() == []
    assert monitor.reckoning() == []
    shape = monitor.shape()
    assert (shape.turns, shape.working, shape.handovers, shape.latest) == (
        {},
        frozenset(),
        {},
        None,
    )


def test_turns_make_the_graph_of_who_handed_to_whom() -> None:
    monitor = Monitor(began=0.0)
    for agent in ("builder", "reviewer", "builder"):
        monitor.begins(agent, "opus", now=1.0)
        monitor.ends(agent, now=2.0)
    monitor.begins("reviewer", "sonnet", now=3.0)

    shape = monitor.shape()

    assert shape.turns == {"builder": 2, "reviewer": 2}
    assert shape.handovers == {("builder", "reviewer"): 2, ("reviewer", "builder"): 1}
    assert shape.latest == ("builder", "reviewer")
    assert shape.working == {"reviewer"}
    assert monitor.now_working() == ["reviewer"]
    assert monitor.models == {"builder": "opus", "reviewer": "sonnet"}


def test_an_agent_handing_to_itself_is_no_handover() -> None:
    monitor = Monitor()
    monitor.begins("solo", "m")
    monitor.ends("solo")
    monitor.begins("solo", "m")

    assert monitor.shape().handovers == {}
    assert monitor.shape().latest is None


def test_an_agent_holding_two_sessions_works_until_both_end() -> None:
    monitor = Monitor()
    monitor.begins("a", "m", now=1.0)
    monitor.begins("a", "m", now=2.0)
    monitor.ends("a", now=3.0)

    assert monitor.now_working() == ["a"]
    monitor.ends("a", now=4.0)
    assert monitor.now_working() == []


def test_the_clock_counts_the_open_turn_and_then_the_rest_since() -> None:
    monitor = Monitor(began=0.0)
    monitor.begins("a", "m", now=10.0)
    monitor.begins("a", "m", now=20.0)  # a second session: the clock is not restarted
    monitor.begins("b", "m", now=5.0)
    monitor.ends("b", now=30.0)
    monitor.stops()
    assert monitor.until is not None
    end = monitor.until

    since = monitor.shape().since

    assert since["a"] == pytest.approx(end - 10.0)
    assert since["b"] == pytest.approx(end - 30.0)


def test_a_fleet_hangs_under_the_agent_that_started_it() -> None:
    monitor = Monitor()
    monitor.started("a", "sub1", "read the code")
    monitor.started("a", "sub2", "write the test")
    monitor.finished("a", "sub1")
    monitor.finished("a", "ghost", "never seen to start")

    assert monitor.shape().under == {
        "a": (
            Under("sub1", "read the code", working=False),
            Under("sub2", "write the test"),
            Under("ghost", "never seen to start", working=False),
        )
    }


def test_sessions_are_kept_as_a_graph_of_their_own() -> None:
    monitor = Monitor()
    assert monitor.shape(sessions=True) == Shape({}, frozenset(), {})

    monitor.begins("builder", "m", session="builder/1")
    monitor.started("builder", "sub", "x", session="builder/1")
    monitor.spend("builder", 50, session="builder/1")
    monitor.ends("builder", session="builder/1")
    monitor.begins("builder", "m", session="builder/2")
    monitor.finished("builder", "sub", session="builder/1")

    sessions = monitor.shape(sessions=True)
    assert sessions.turns == {"builder/1": 1, "builder/2": 1}
    assert sessions.handovers == {("builder/1", "builder/2"): 1}
    assert sessions.under == {"builder/1": (Under("sub", "x", working=False),)}
    assert sessions.used == {"builder/1": 50}
    # The bill is the run's, counted once: the sessions say only who spent it.
    assert [one.tokens for one in monitor.spending()] == [50]


def test_spending_is_kept_per_model_in_the_order_first_spent() -> None:
    monitor = Monitor(began=0.0)
    monitor.begins("a", "zeta")
    monitor.begins("b", "alpha")
    monitor.spend("a", 100, now=1.0)
    monitor.spend("b", 50, now=2.0)
    monitor.spend("a", 25, model="sub-model", now=3.0)

    assert [(one.model, one.tokens) for one in monitor.spending(now=10.0)] == [
        ("zeta", 100),
        ("alpha", 50),
        ("sub-model", 25),
    ]
    assert monitor.shape().used == {"a": 125, "b": 50}


@pytest.mark.parametrize("tokens", [0, -5])
def test_nothing_spent_is_not_counted(tokens: int) -> None:
    monitor = Monitor()
    monitor.spend("a", tokens)

    assert monitor.spending() == []


def test_an_agent_with_no_model_spends_under_its_own_name() -> None:
    monitor = Monitor()
    monitor.spend("lonely", 10)

    assert [one.model for one in monitor.spending()] == ["lonely"]


def test_the_kinds_put_a_price_on_what_was_spent() -> None:
    monitor = Monitor(began=0.0)
    monitor.begins("a", "priced")
    monitor.spend("a", 30, kinds={"input": 10, "output": 20}, now=1.0)

    [spend] = monitor.spending(now=10.0)

    assert spend == Spend(
        model="priced",
        tokens=30,
        rate=2.0,
        dollars=210.0,
        kinds={"input": 10.0, "output": 20.0},
    )


def test_what_the_kinds_do_not_account_for_is_spent_under_no_kind() -> None:
    monitor = Monitor()
    monitor.begins("a", "priced")
    monitor.spend("a", 100, kinds={"output": 40})

    [spend] = monitor.spending()

    assert spend.kinds == {"output": 40.0, "": 60.0}


def test_a_remainder_under_a_token_is_not_spending() -> None:
    monitor = Monitor()
    monitor.begins("a", "priced")
    monitor.spend("a", 10, kinds={"input": 4.6, "output": 4.6})

    assert "" not in monitor.spending()[0].kinds


def test_a_model_nobody_prices_has_no_bill_rather_than_a_free_one() -> None:
    monitor = Monitor()
    monitor.begins("a", "unknown")
    monitor.spend("a", 30, kinds={"input": 30})

    assert monitor.spending()[0].dollars is None


def test_a_lump_nobody_broke_down_is_spent_under_no_kind() -> None:
    monitor = Monitor()
    monitor.begins("a", "priced")
    monitor.spend("a", 30)

    [spend] = monitor.spending()
    assert spend.kinds == {"": 30.0}
    assert spend.dollars == 0.0  # what the price list makes of no kind at all


def test_two_sources_counting_the_same_tokens_are_one_bill() -> None:
    monitor = Monitor()
    monitor.counted("read", "priced", 100, kinds={"input": 40, "output": 60})
    monitor.counted("told", "priced", 80, kinds={"input": 30, "output": 50})

    [spend] = monitor.spending()

    assert spend.tokens == 100
    assert spend.kinds == {"input": 40.0, "output": 60.0}


def test_a_total_read_again_from_the_top_keeps_what_it_said() -> None:
    monitor = Monitor()
    monitor.counted("read", "m", 100)
    monitor.counted("read", "m", 40)

    assert monitor.spending()[0].tokens == 100


def test_the_fullest_breakdown_is_priced_rather_than_the_biggest_lump() -> None:
    monitor = Monitor()
    monitor.counted("told", "priced", 500, kinds={"": 500})
    monitor.counted("read", "priced", 100, kinds={"input": 100})

    [spend] = monitor.spending()

    assert spend.tokens == 500
    assert spend.kinds == {"input": 100.0}
    assert spend.dollars == 100.0


def test_a_breakdown_a_source_stopped_saying_is_dropped() -> None:
    monitor = Monitor()
    monitor.counted("read", "priced", 100, kinds={"input": 100})
    monitor.counted("read", "priced", 150)

    [spend] = monitor.spending()

    assert spend.tokens == 150
    assert spend.kinds == {}
    assert spend.dollars is None


def test_the_rate_is_output_over_the_last_five_minutes() -> None:
    monitor = Monitor(began=0.0)
    monitor.begins("a", "m")
    monitor.spend("a", 600, kinds={"output": 600}, now=10.0)
    monitor.spend("a", 1000, kinds={"input": 1000}, now=20.0)

    assert monitor.spending(now=100.0)[0].rate == pytest.approx(6.0)
    # Five minutes on, the output has fallen out of the window.
    assert monitor.spending(now=400.0)[0].rate == 0.0


def test_a_run_that_is_over_is_read_at_its_own_end() -> None:
    monitor = Monitor()
    monitor.begins("a", "m")
    monitor.spend("a", 100, kinds={"output": 100})
    monitor.stops()
    assert monitor.until is not None
    ended = monitor.spending(now=monitor.until)[0].rate

    assert monitor.spending(now=monitor.until + 10_000)[0].rate == ended


def test_figures_are_worked_out_again_only_when_something_moved(
    priced: list[str],
) -> None:
    monitor = Monitor(began=0.0)
    monitor.begins("a", "priced")
    monitor.spend("a", 10, kinds={"input": 10}, now=1.0)

    monitor.spending(now=2.0)
    monitor.spending(now=3.0)
    assert priced == ["priced"]

    monitor.stirring()
    monitor.spending(now=3.5)
    assert priced == ["priced", "priced"]

    monitor.spending(now=10.0)  # five seconds have passed
    assert priced == ["priced", "priced", "priced"]


def test_reckoning_one_agent_marks_nothing_as_a_floor() -> None:
    monitor = Monitor()
    monitor.reporting("a", {"input", "output"})
    monitor.begins("a", "m")
    monitor.spend("a", 30, kinds={"input": 10, "output": 20})

    assert monitor.reckoning() == [
        Counted("input", 10.0, whole=True),
        Counted("output", 20.0, whole=True),
    ]


def test_a_kind_one_backend_never_reports_is_a_floor() -> None:
    monitor = Monitor()
    monitor.reporting("a", {"input", "output", "cache_read"})
    monitor.reporting("b", {"input", "output"})
    monitor.begins("a", "m1")
    monitor.begins("b", "m2")
    monitor.spend("a", 30, kinds={"input": 10, "output": 15, "cache_read": 5})
    monitor.spend("b", 20, kinds={"input": 5, "output": 15})

    assert monitor.reckoning() == [
        Counted("input", 15.0, whole=True),
        Counted("output", 30.0, whole=True),
        Counted("cache_read", 5.0, whole=False),
    ]


def test_spending_of_no_kind_makes_every_figure_a_floor() -> None:
    monitor = Monitor()
    monitor.reporting("a", {"input", "output"})
    monitor.begins("a", "m")
    monitor.spend("a", 100, kinds={"input": 10})

    assert monitor.reckoning() == [
        Counted("input", 10.0, whole=False),
        Counted("output", 0.0, whole=False),
    ]


def test_a_kind_nobody_names_is_listed_after_the_known_ones() -> None:
    monitor = Monitor()
    monitor.begins("a", "m")
    monitor.spend("a", 15, kinds={"zebra": 5, "input": 10})

    assert [one.kind for one in monitor.reckoning()] == ["input", "zebra"]
