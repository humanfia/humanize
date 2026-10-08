"""`hmz.runtime.watching.btw`: the prompts side questions are asked with, and `@ask` lines."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.watching import btw
from hmz.runtime.watching.btw import (
    HOPS,
    AgentProgress,
    FlowSnapshot,
    Observation,
    asked,
    compact,
    format_answers,
    format_forked,
    format_snapshot,
    format_turn,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def priced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Money as `hmz.coganchor.prices` would say it, without reading any prices."""

    def money(dollars: float) -> str:
        return f"${dollars:.2f}"

    monkeypatch.setattr(btw, "money", money)


def _snapshot(**changed: object) -> FlowSnapshot:
    base = FlowSnapshot(
        flow="rlar", task="fix the bug", workspace="/w", elapsed=12.34, finished=False
    )
    return dataclasses.replace(base, **changed)


def _block(prompt: str, heading: str) -> list[str]:
    """The lines under one heading of the snapshot, up to the next heading."""
    lines = prompt.splitlines()
    at = lines.index(heading) + 1
    under: list[str] = []
    for line in lines[at:]:
        if not line.startswith("- "):
            break
        under.append(line)
    return under


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a  b\n\tc ", "a b c"),
        ("", ""),
        ("x" * 600, "x" * 600),
        ("x" * 601, "x" * 599 + "…"),
    ],
)
def test_compact_normalises_and_bounds_one_event(text: str, expected: str) -> None:
    assert compact(text) == expected


def test_compact_takes_a_limit() -> None:
    assert compact("abcdef", 4) == "abc…"


def test_asked_reads_each_ask_line_off_an_answer() -> None:
    answer = (
        "Let me check.\n@ask builder/1: what did you change?\n  @ask  rev/2 :why\nDone."
    )

    asks, rest = asked(answer)

    assert asks == [("builder/1", "what did you change?"), ("rev/2", "why")]
    assert rest == "Let me check.\n\n\nDone."


@pytest.mark.parametrize(
    "answer", ["no asks here", "@ask builder/1:", "@ask : question", "say @ask x: y"]
)
def test_asked_takes_nothing_that_is_not_an_ask_line(answer: str) -> None:
    asks, rest = asked(answer)

    assert asks == []
    assert rest == answer.strip()


@pytest.mark.parametrize(
    ("more", "last"),
    [
        (True, "Ask again with @ask lines, or answer the user."),
        (False, "No more @ask this turn: answer the user with what you have."),
    ],
)
def test_format_answers_says_each_answer_and_whether_to_ask_more(
    more: bool, last: str
) -> None:
    said = format_answers([("a/1", "one"), ("b/1", "two  lines\nhere")], more=more)

    assert said.splitlines() == [
        '<answer from="a/1">',
        "one",
        "</answer>",
        '<answer from="b/1">',
        "two lines here",
        "</answer>",
        last,
    ]


def test_format_turn_wraps_a_question() -> None:
    assert format_turn(" what  now? ") == "<user_question>\nwhat now?\n</user_question>"


def test_format_forked_names_the_session_and_asks_the_question() -> None:
    said = format_forked("builder/2", "why?")

    assert "read-only side copy of the flow session `builder/2`" in said
    assert "Do not carry on its task." in said
    assert "untrusted data" in said
    assert said.endswith(format_turn("why?"))


def test_a_snapshot_with_nothing_observed_says_so() -> None:
    said = format_snapshot(_snapshot(), "how is it going?")

    assert said.startswith("You are the btw agent")
    assert "<flow_snapshot>" in said
    assert "</flow_snapshot>" in said
    for line in (
        "flow: rlar",
        "task: fix the bug",
        "workspace: /w",
        "elapsed_seconds: 12.3",
        "finished: no",
        "waiting_messages: 0",
        "waiting_for_input: no",
    ):
        assert line in said.splitlines()
    for heading, nothing in (
        ("agents:", "- none observed"),
        ("handovers:", "- none observed"),
        ("spending:", "- none reported"),
        ("tokens_by_kind:", "- none reported"),
        ("recent_observations:", "- none observed"),
    ):
        assert _block(said, heading) == [nothing]
    assert "sessions:" not in said
    assert said.endswith(format_turn("how is it going?"))


def test_a_snapshot_says_what_is_missing_and_clamps_what_cannot_be() -> None:
    said = format_snapshot(
        _snapshot(
            flow="", task="", workspace="", elapsed=-5.0, waiting=-2, finished=True
        ),
        "q",
    )

    for line in (
        "flow: (unknown)",
        "task: (not recorded)",
        "workspace: (unknown)",
        "elapsed_seconds: 0.0",
        "finished: yes",
        "waiting_messages: 0",
    ):
        assert line in said.splitlines()


def test_a_snapshot_says_each_agent_and_handover() -> None:
    said = format_snapshot(
        _snapshot(
            agents=(
                AgentProgress("claude#ab", "opus", 3, working=True, role="builder"),
                AgentProgress("codex#cd", "", -1, working=False),
            ),
            handovers=(("builder", "reviewer", 2),),
            waiting_for_input=True,
        ),
        "q",
    )

    assert _block(said, "agents:") == [
        "- builder (claude#ab): working, 3 turn(s), model=opus",
        "- codex#cd: idle, 0 turn(s), model=(unknown)",
    ]
    assert _block(said, "handovers:") == ["- builder -> reviewer: 2 time(s)"]
    assert "waiting_for_input: yes" in said.splitlines()


def test_a_snapshot_spends_biggest_first_and_never_prices_the_unpriced() -> None:
    said = format_snapshot(
        _snapshot(
            spent=(("small", 10, 0.5, 0.25), ("big", 1000, 12.0, None)),
            kinds=(("input", 900.0, True), ("cache_read", 100.0, False)),
        ),
        "q",
    )

    assert _block(said, "spending:") == [
        "- big: 1000 token(s), 12.0 output token(s)/s",
        "- small: 10 token(s), 0.5 output token(s)/s, $0.25",
    ]
    assert _block(said, "tokens_by_kind:") == [
        "- input: 900",
        "- cache_read: 100 (a floor: not every agent here reports this kind)",
    ]


def test_a_snapshot_keeps_only_the_recent_observations() -> None:
    observations = tuple(
        Observation("claude#ab" if at else "", "text", f"said {at}", float(at))
        for at in range(40)
    )

    said = format_snapshot(_snapshot(observations=observations), "q")

    block = _block(said, "recent_observations:")
    assert block[0] == "- (earlier observations omitted: 8)"
    assert len(block) == 33
    assert block[1] == "- claude#ab [text]: said 8"
    assert block[-1] == "- claude#ab [text]: said 39"


def test_an_observation_with_no_text_or_agent_says_so() -> None:
    said = format_snapshot(
        _snapshot(observations=(Observation("", "x", "", 0.0),)), "q"
    )

    assert _block(said, "recent_observations:") == ["- (flow) [x]: (no text)"]


def _agent(at: int) -> AgentProgress:
    return AgentProgress(f"a{at}", "m", 0, working=False)


def _handover(at: int) -> tuple[str, str, int]:
    return (f"s{at}", f"r{at}", 1)


def _spent(at: int) -> tuple[str, int, float, float | None]:
    return (f"m{at}", at, 0.0, None)


@pytest.mark.parametrize(
    ("field", "heading", "make", "shown", "omitted"),
    [
        (
            "agents",
            "agents:",
            _agent,
            64,
            "- (agents omitted: 6)",
        ),
        (
            "handovers",
            "handovers:",
            _handover,
            128,
            "- (handovers omitted: 6)",
        ),
        (
            "spent",
            "spending:",
            _spent,
            32,
            "- (spending entries omitted: 6)",
        ),
    ],
)
def test_a_snapshot_bounds_what_it_lists(
    field: str, heading: str, make: Callable[[int], object], shown: int, omitted: str
) -> None:
    many = tuple(make(at) for at in range(shown + 6))

    block = _block(format_snapshot(_snapshot(**{field: many}), "q"), heading)

    assert len(block) == shown + 1
    assert block[-1] == omitted


def test_the_btw_agent_is_told_how_to_ask_the_sessions() -> None:
    said = format_snapshot(
        _snapshot(sessions=(("builder/1", "the builder"), ("rev/1", "the reviewer"))),
        "q",
    )

    assert _block(said, "sessions:") == [
        "- builder/1: the builder",
        "- rev/1: the reviewer",
    ]
    assert "`@ask <session>: <question>`" in said
    assert f"You may ask up to {HOPS} per user question." in said


def test_a_side_question_about_one_session_is_not_told_how_to_ask() -> None:
    said = format_snapshot(
        _snapshot(sessions=(("builder/1", "the builder"),)), "q", about="builder/1"
    )

    assert said.startswith(
        "You are answering a side question about the session `builder/1`"
    )
    assert "@ask" not in said


def test_sessions_past_the_bound_are_counted() -> None:
    many = tuple((f"r/{at}", "x") for at in range(70))

    block = _block(format_snapshot(_snapshot(sessions=many), "q"), "sessions:")

    assert len(block) == 65
    assert block[-1] == "- (sessions omitted: 6)"


def test_the_snapshot_types_are_frozen() -> None:
    agent = AgentProgress("a", "m", 1, working=True)

    with pytest.raises(dataclasses.FrozenInstanceError):
        agent.turns = 2  # pyright: ignore[reportAttributeAccessIssue]
