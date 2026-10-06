"""`hmz.tui.pick`: what a flow declares, how it was set up, and where its places are."""

from __future__ import annotations

import datetime
import math
from typing import Any

import pydantic
import pytest
from pydantic import BaseModel

import hmz.daemon
import hmz.runtime.flowing
from hmz.flows import Budget
from hmz.runtime.flowing import SpecError
from hmz.tui import pick
from tests.unit.tui import doubles_u14 as doubles


class _Params(BaseModel):
    rounds: int = 3
    goal: str = ""


class _Nothing(BaseModel):
    pass


_CODER, _REVIEWER = doubles.role("coder"), doubles.role("reviewer")
_YOU = doubles.role("you", auto=True)
_BOX, _HERE = doubles.env("box"), doubles.env("here", auto=True)

_FLOWS = {
    "loop": doubles.Described(
        agents=(_CODER, _YOU, _REVIEWER),
        envs=(_BOX, _HERE),
        params=_Params,
        resumable=True,
    ),
    "chat": doubles.Described(agents=(_YOU,), params=_Nothing),
}


@pytest.fixture(autouse=True)
def flows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two flows that load, `chat` the privileged one; any other will not."""
    resolved, privileged = doubles.resolving(_FLOWS, frozenset({"chat"}))
    monkeypatch.setattr(hmz.runtime.flowing, "resolved", resolved)
    monkeypatch.setattr(hmz.runtime.flowing, "privileged", privileged)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> doubles.Hmz:
    """The one store every sheet reaches, in place of humanize's own."""
    held = doubles.Hmz()
    monkeypatch.setattr(hmz.daemon, "Hmz", held)
    return held


def test_declared_of_splits_who_is_chosen_from_who_is_here() -> None:
    declared = pick.declared_of("loop")

    assert declared == pick.Declared(
        (_CODER, _REVIEWER),
        (_BOX,),
        _Params,
        unbounded=False,
        resumable=True,
        outworlders=("you",),
    )
    assert declared is not None
    assert declared.roles == ("coder", "reviewer")
    assert declared.places == ("box",)


def test_declared_of_says_a_privileged_flow_needs_no_budget() -> None:
    declared = pick.declared_of("chat")

    assert declared is not None
    assert declared.unbounded
    assert declared.roles == ()
    assert declared.outworlders == ("you",)


def test_declared_of_a_flow_that_will_not_load_is_none() -> None:
    assert pick.declared_of("missing") is None


@pytest.mark.parametrize(
    ("flow", "model"), [("loop", _Params), ("chat", None), ("gone", None)]
)
def test_params_model_is_none_for_no_fields_or_no_flow(
    flow: str, model: type[BaseModel] | None
) -> None:
    assert pick.params_model(flow) is model


def test_params_of_reads_what_was_kept_through_the_flows_model() -> None:
    assert pick.params_of("loop", {"rounds": "7"}) == _Params(rounds=7)


@pytest.mark.parametrize(
    ("flow", "kept"),
    [
        ("loop", {}),
        ("loop", {"rounds": "many"}),
        ("chat", {"rounds": 1}),
        ("gone", {"rounds": 1}),
    ],
)
def test_params_of_is_none_where_nothing_kept_still_reads(
    flow: str, kept: dict[str, Any]
) -> None:
    assert pick.params_of(flow, kept) is None


def test_why_not_says_nothing_of_a_flow_that_loads(store: doubles.Hmz) -> None:
    assert pick.why_not("loop") == ""


@pytest.mark.parametrize(
    ("raised", "said"),
    [
        (ImportError("  no module named foo\nTraceback more"), "no module named foo"),
        (KeyError(), "KeyError"),
        (ValueError("   \n  "), "ValueError"),
    ],
)
def test_why_not_says_the_first_line_or_the_type(
    store: doubles.Hmz, raised: Exception, said: str
) -> None:
    store.flows.raises = raised

    assert pick.why_not("loop") == said


def test_budget_of_reads_back_what_was_kept(store: doubles.Hmz) -> None:
    store.settings.budgets["loop"] = {"cost": 2, "graceful": False}

    assert pick.budget_of("loop") == Budget(cost=2, graceful=False)


@pytest.mark.parametrize("kept", [None, {}, {"graceful": True}, {"cost": -1}])
def test_budget_of_is_none_for_nothing_or_no_budget(
    store: doubles.Hmz, kept: dict[str, Any] | None
) -> None:
    if kept is not None:
        store.settings.budgets["loop"] = kept

    assert pick.budget_of("loop") is None


def test_placed_says_nothing_of_a_spec_that_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    given: list[list[str]] = []
    monkeypatch.setattr(hmz.runtime.flowing, "parse_envs", given.append)

    assert pick.placed("box", "ssh:dev:~/w") == ""
    assert given == [["box=ssh:dev:~/w"]]


def test_placed_says_why_a_spec_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(values: list[str]) -> None:
        raise SpecError(f"cannot read {values[0]}")

    monkeypatch.setattr(hmz.runtime.flowing, "parse_envs", refuse)

    assert pick.placed("box", "nowhere") == "cannot read box=nowhere"


@pytest.fixture
def durations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Durations read as a number of minutes, and nothing else as one."""

    def parse(text: str) -> datetime.timedelta:
        if not text.strip().isdigit():
            raise SpecError(f"not a duration: {text}")
        return datetime.timedelta(minutes=int(text))

    monkeypatch.setattr(hmz.runtime.flowing, "parse_duration", parse)


@pytest.mark.usefixtures("durations")
def test_budgeted_answers_with_the_budget_it_was_set_to() -> None:
    asked = pick.Budgeted(duration=" 90 ", cost=1.5, output_tokens=0, graceful=False)

    assert asked.duration == "90"
    assert asked.budget() == Budget(
        duration=datetime.timedelta(minutes=90), cost=1.5, graceful=False
    )


@pytest.mark.usefixtures("durations")
@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"duration": "   "},
        {"duration": "soon"},
        {"cost": -1},
        {"output_tokens": -5},
    ],
)
def test_budgeted_refuses_a_budget_that_limits_nothing_or_misreads(
    fields: dict[str, Any],
) -> None:
    with pytest.raises(pydantic.ValidationError):
        pick.Budgeted(**fields)


@pytest.mark.parametrize(
    ("budget", "shown"),
    [
        (
            Budget(
                duration=datetime.timedelta(hours=2), output_tokens=9, graceful=False
            ),
            ("2h", 0.0, 9, False),
        ),
        (Budget(cost=math.inf), ("", 0.0, 0, True)),
        (Budget(cost=0), ("", 0.0, 0, True)),
        (Budget(cost=4.25), ("", 4.25, 0, True)),
    ],
)
def test_budgeted_of_shows_a_budget_without_checking_it(
    budget: Budget, shown: tuple[str, float, int, bool]
) -> None:
    sheet = pick.Budgeted.of(budget)

    assert (sheet.duration, sheet.cost, sheet.output_tokens, sheet.graceful) == shown
