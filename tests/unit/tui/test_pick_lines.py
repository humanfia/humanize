"""`hmz.tui.pick`: the lines the sheets say -- agents, switches, colours, settings, budgets."""

from __future__ import annotations

import datetime
import math

import pytest
from pydantic import BaseModel, Field

from hmz.flows import Budget
from hmz.runtime.kept import Runs
from hmz.tui import pick
from hmz.tui.dropdown import Value


@pytest.mark.parametrize(
    ("roles", "at", "said"),
    [
        (("coder", "reviewer"), 0, "coder"),
        (("coder", "reviewer"), 1, "reviewer"),
        (("coder",), 1, "agent 2 of 1"),
        ((), 0, "agent 1 of 0"),
    ],
)
def test_called_names_the_role_or_says_which_of_how_many(
    roles: tuple[str, ...], at: int, said: str
) -> None:
    assert pick.called(roles, at) == said


def test_reads_says_role_spec_and_account_apiece() -> None:
    runs = [Runs("claude/opus:high", "work"), Runs("codex/gpt:low")]

    assert pick.reads(("coder", "reviewer"), runs) == [
        "coder · claude/opus:high · work",
        "reviewer · codex/gpt:low",
    ]


def test_reads_leaves_out_a_role_it_was_not_given() -> None:
    assert pick.reads((), [Runs("claude/opus:high")]) == ["claude/opus:high"]


def test_reads_escapes_markup_in_what_it_was_given() -> None:
    (line,) = pick.reads(("[bold]",), [Runs("x/y:z")])

    assert line.startswith("\\[bold]")


@pytest.mark.parametrize(
    ("held", "tail"),
    [
        (pick.Held(), ""),
        (pick.Held(many=2), " · ○ 2"),
        (pick.Held(many=1, working=True), " · ● 1"),
        (pick.Held(many=3, unread=True), " · ○ 3 · unread"),
        (pick.Held(many=3, reading=True, unread=True), " · ○ 3 · reading"),
    ],
)
def test_reads_says_what_a_running_agent_holds(held: pick.Held, tail: str) -> None:
    (line,) = pick.reads(("coder",), [Runs("a/b:c")], [held])

    assert line == f"coder · a/b:c{tail}"


def test_reads_says_nothing_held_for_an_agent_past_the_holdings() -> None:
    lines = pick.reads(("a", "b"), [Runs("x/1:h"), Runs("y/2:h")], [pick.Held(many=1)])

    assert lines == ["a · x/1:h · ○ 1", "b · y/2:h"]


@pytest.mark.parametrize(
    ("values", "answer"),
    [
        (["on", "off"], True),
        (["off", "on"], True),
        (["on", "on"], False),
        (["on", "off", "auto"], False),
        (["yes", "no"], False),
        ([], False),
    ],
)
def test_switch_is_on_and_off_and_nothing_else(values: list[str], answer: bool) -> None:
    assert pick.switch(values) is answer


@pytest.mark.parametrize(("current", "cursor"), [("on", "off"), ("off", "on")])
def test_switched_opens_on_the_side_it_is_not(current: str, cursor: str) -> None:
    drop = pick.switched("details", current, ("shown", "hidden"))

    assert drop == pick.Drop(
        "details",
        (Value("on", "on", "shown"), Value("off", "off", "hidden")),
        current,
        cursor=cursor,
    )
    assert pick.switch([one.value for one in drop.values])


def test_switched_says_nothing_beside_its_values_unless_told() -> None:
    drop = pick.switched("x", "on")

    assert [one.about for one in drop.values] == ["", ""]


@pytest.mark.parametrize(
    ("colour", "said", "marked"),
    [
        (pick.bad, "broke", "[red]broke[/red]"),
        (pick.iffy, "hm", "[yellow]hm[/yellow]"),
        (pick.bad, "", ""),
        (pick.iffy, "", ""),
    ],
)
def test_bad_and_iffy_colour_a_line_and_leave_nothing_blank(
    colour: object, said: str, marked: str
) -> None:
    assert callable(colour)
    assert colour(said) == marked


@pytest.mark.parametrize(
    ("ref", "said"),
    [
        ("chat:chat", "chat"),
        ("loop:review", "loop:review"),
        ("chat", "chat"),
        ("pkg.mod:mod", "pkg.mod:mod"),
    ],
)
def test_named_as_drops_the_name_a_module_already_says(ref: str, said: str) -> None:
    assert pick.named_as(ref) == said


class _Params(BaseModel):
    rounds: int = 3
    strict: bool = False
    note: str | None = None
    tags: list[str] = Field(default_factory=list)


def test_setting_says_nothing_of_no_config() -> None:
    assert pick.setting(None) == []


def test_setting_says_nothing_of_defaults() -> None:
    assert pick.setting(_Params()) == []


def test_setting_says_each_changed_setting_in_declared_order() -> None:
    config = _Params(tags=["a"], rounds=5, strict=True)

    lines = [line.split(maxsplit=1) for line in pick.setting(config)]

    assert lines == [["rounds", "5"], ["strict", "on"], ["tags", "['a']"]]


def test_setting_lines_values_up_in_one_column() -> None:
    lines = pick.setting(_Params(rounds=1, note="x"))

    assert len({line.index(line.split()[1]) for line in lines}) == 1


def test_setting_says_a_switch_turned_off_as_off() -> None:
    class On(BaseModel):
        loud: bool = True

    assert [line.split() for line in pick.setting(On(loud=False))] == [["loud", "off"]]


@pytest.fixture
def priced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Money said as the number it is, so a line reads without knowing how prices are."""

    def money(dollars: float) -> str:
        return f"${dollars}"

    monkeypatch.setattr(pick, "money", money)


@pytest.mark.usefixtures("priced")
@pytest.mark.parametrize(
    ("budget", "said"),
    [
        (Budget(cost=math.inf), "no limit"),
        (Budget(cost=2.5), "$2.5"),
        (Budget(output_tokens=500), "500 out"),
        (Budget(duration=datetime.timedelta(hours=1, minutes=30)), "1h30m"),
        (Budget(duration=datetime.timedelta(days=12)), "12d"),
        (Budget(duration=datetime.timedelta(seconds=1.5)), "1.5s"),
        (Budget(duration=datetime.timedelta(0)), "0s"),
        (Budget(duration=datetime.timedelta(minutes=1, seconds=5)), "1m5s"),
        (
            Budget(duration=datetime.timedelta(seconds=90), output_tokens=10, cost=1),
            "1m30s, 10 out, $1.0",
        ),
        (Budget(cost=3, graceful=False), "$3.0, even mid-turn"),
    ],
)
def test_spent_says_each_cap_shortest_first(budget: Budget, said: str) -> None:
    assert pick.spent(budget) == said


def test_chosen_defaults_to_no_envs_params_budget_or_profiling() -> None:
    chosen = pick.Chosen("chat", {"you": Runs("claude/opus:high")})

    assert (chosen.envs, chosen.params, chosen.budget, chosen.profile) == (
        {},
        None,
        None,
        False,
    )


def test_held_defaults_to_holding_nothing() -> None:
    assert pick.Held() == pick.Held(0, reading=False, unread=False, working=False)


def test_the_every_transcript_is_no_agents() -> None:
    assert pick.EVERY == ""
    assert len({pick.STOPS, pick.DETACHES, pick.STAYS}) == 3
