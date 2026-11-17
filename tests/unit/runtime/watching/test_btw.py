"""`hmz.runtime.watching.btw`: the prompts side questions are asked with, and who asks."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.watching import btw
from hmz.runtime.watching.btw import (
    AgentProgress,
    FlowSnapshot,
    Observation,
    compact,
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


def _about(snapshot: FlowSnapshot, question: str) -> str:
    """The first prompt of a side copy of `builder/1`."""
    return format_snapshot(snapshot, question, about="builder/1")


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


def test_format_turn_wraps_a_question() -> None:
    assert format_turn(" what  now? ") == "<user_question>\nwhat now?\n</user_question>"


def test_format_forked_names_the_session_and_asks_the_question() -> None:
    said = format_forked("builder/2", "why?")

    assert "read-only side copy of the flow session `builder/2`" in said
    assert "Do not carry on its task." in said
    assert "untrusted data" in said
    assert said.endswith(format_turn("why?"))


def test_a_snapshot_with_nothing_observed_says_so() -> None:
    said = _about(_snapshot(), "how is it going?")

    assert said.startswith(
        "You are answering a side question about the session `builder/1`"
    )
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
    said = _about(
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
    said = _about(
        _snapshot(
            agents=(
                AgentProgress("NeiKos496", "opus", 3, working=True, role="builder"),
                AgentProgress("codex#cd", "", -1, working=False),
            ),
            handovers=(("builder", "reviewer", 2),),
            waiting_for_input=True,
        ),
        "q",
    )

    assert _block(said, "agents:") == [
        "- NeiKos496 (builder): working, 3 turn(s), model=opus",
        "- codex#cd: idle, 0 turn(s), model=(unknown)",
    ]
    assert _block(said, "handovers:") == ["- builder -> reviewer: 2 time(s)"]
    assert "waiting_for_input: yes" in said.splitlines()


def test_a_snapshot_spends_biggest_first_and_never_prices_the_unpriced() -> None:
    said = _about(
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

    said = _about(_snapshot(observations=observations), "q")

    block = _block(said, "recent_observations:")
    assert block[0] == "- (earlier observations omitted: 8)"
    assert len(block) == 33
    assert block[1] == "- claude#ab [text]: said 8"
    assert block[-1] == "- claude#ab [text]: said 39"


def test_an_observation_with_no_text_or_agent_says_so() -> None:
    said = _about(_snapshot(observations=(Observation("", "x", "", 0.0),)), "q")

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

    block = _block(_about(_snapshot(**{field: many}), "q"), heading)

    assert len(block) == shown + 1
    assert block[-1] == omitted


def test_the_snapshot_types_are_frozen() -> None:
    agent = AgentProgress("a", "m", 1, working=True)

    with pytest.raises(dataclasses.FrozenInstanceError):
        agent.turns = 2  # pyright: ignore[reportAttributeAccessIssue]


class _Runs:
    """The runs, as a side conversation reaches them: each one opened, and each prompt said.

    Args:
      answers: What each side conversation answers, by what it was opened as, in turn.
      forks: Whether a fork of a session will answer, rather than raise.
    """

    def __init__(self, answers: dict[str, list[str]], *, forks: bool = True) -> None:
        self.answers = answers
        self.forks = forks
        self.opened: list[dict[str, object]] = []
        self.closed: list[str] = []
        self.said: list[str] = []
        self._of: dict[str, str] = {}

    def aside(self, **said: object) -> dict[str, object]:
        if "prompt" in said:
            opened = self._of[str(said["side"])]
            if opened.endswith("fork") and not self.forks:
                raise RuntimeError("the fork would not answer")
            self.said.append(str(said["prompt"]))
            return {"answer": self.answers[opened].pop(0)}
        side = f"s{len(self.opened) + 1}"
        self.opened.append(said)
        whose = str(said.get("key") or said.get("runs"))
        self._of[side] = f"{whose} fork" if said.get("fork") else whose
        return {"side": side, "forked": bool(said.get("fork"))}

    def btw(self, target: str = "builder/1") -> btw.Btw:
        return btw.Btw(
            target,
            aside=self.aside,
            unaside=self.closed.append,
            sessions=lambda: ["builder/1", "critic/1"],
        )


def test_a_fork_that_will_not_answer_is_asked_again_as_a_copy() -> None:
    runs = _Runs({"builder/1": ["from the copy"]}, forks=False)

    answer = runs.btw("builder/1").ask("what now", _snapshot())

    assert answer == "from the copy"
    assert runs.opened == [{"key": "builder/1", "fork": True}, {"key": "builder/1"}]
    assert runs.closed == ["s1"]


def test_a_fork_is_told_what_it_is_and_asked_on_without_more() -> None:
    runs = _Runs({"builder/1 fork": ["one", "two"]})
    mode = runs.btw()

    assert mode.ask("first", _snapshot()) == "one"
    assert mode.ask("second", _snapshot()) == "two"

    assert runs.opened == [{"key": "builder/1", "fork": True}]
    assert runs.said == [format_forked("builder/1", "first"), format_turn("second")]


def test_a_copy_is_told_a_snapshot_of_its_own_agent_alone() -> None:
    runs = _Runs({"builder/1": ["from the copy"]}, forks=False)
    observed = (
        Observation("builder", "said", "mine", 1.0),
        Observation("critic", "said", "theirs", 2.0),
        Observation("", "printed", "the flow's", 3.0),
    )

    runs.btw().ask("what now", _snapshot(observations=observed))

    told = runs.said[-1]
    assert "mine" in told
    assert "the flow's" in told
    assert "theirs" not in told


def test_a_session_that_is_not_of_the_run_is_said_not_found() -> None:
    runs = _Runs({})

    assert runs.btw("nobody/9").ask("hello?", _snapshot()) == (
        "(session nobody/9 not found)"
    )
    assert runs.opened == []


def test_a_side_conversation_the_runs_closed_is_opened_again() -> None:
    runs = _Runs({"builder/1 fork": ["one", "two"]})
    mode = runs.btw()
    mode.ask("first", _snapshot())

    mode.forget()
    mode.ask("second", _snapshot())

    assert [one["key"] for one in runs.opened] == ["builder/1", "builder/1"]
    assert runs.said[-1] == format_forked("builder/1", "second")
    assert runs.closed == []


def test_closing_closes_the_side_conversation_or_leaves_it_to_the_runs() -> None:
    runs = _Runs({"builder/1 fork": ["one", "two"]})
    first, second = runs.btw(), runs.btw()
    first.ask("q", _snapshot())
    second.ask("q", _snapshot())

    first.close()
    second.close(unasking=False)

    assert runs.closed == ["s1"]
    assert first.closed
    assert second.closed


def test_a_side_conversation_opened_after_the_mode_was_left_is_closed_again() -> None:
    runs = _Runs({})

    def opens(**said: object) -> dict[str, object]:
        mode.close()
        return runs.aside(**said)

    mode = btw.Btw(
        "builder/1",
        aside=opens,
        unaside=runs.closed.append,
        sessions=lambda: ["builder/1"],
    )

    with pytest.raises(btw.Left):
        mode.ask("anything", _snapshot())
    assert runs.closed == ["s1"]
    assert not mode.busy
