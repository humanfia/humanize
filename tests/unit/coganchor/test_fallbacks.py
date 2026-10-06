"""`hmz.coganchor.fallbacks`: where a turn goes, and how it is retried, once a place fails."""

from __future__ import annotations

import math
import random

import pytest
import yaml

from hmz.coganchor import backends, fallbacks, settings
from hmz.coganchor.fallbacks import Falls


def test_every_fault_has_exactly_one_answer() -> None:
    faults = [one.fault for one in fallbacks.ANSWERS]
    assert sorted(faults) == sorted(backends.FAULTS)


@pytest.mark.parametrize("answer", fallbacks.ANSWERS, ids=lambda one: one.fault)
def test_every_answer_is_well_formed(answer: fallbacks.Answer) -> None:
    assert answer.about
    assert answer.tries >= 0
    assert answer.least >= 0
    assert not answer.policy or fallbacks.named(answer.policy) is not None
    if answer.held:
        assert answer.tries == 0  # nothing to schedule for a failure held where it is


@pytest.mark.parametrize("fault", backends.FAULTS)
def test_answers_finds_each_fault(fault: str) -> None:
    assert fallbacks.answers(fault).fault == fault


@pytest.mark.parametrize("fault", ["", "never-heard-of-it"])
def test_answers_an_unclassified_failure_as_a_turn_always_was(fault: str) -> None:
    assert fallbacks.answers(fault) == fallbacks.Answer(fault, "failed")


def test_policies_are_named_once_and_the_default_is_one() -> None:
    names = [one.name for one in fallbacks.POLICIES]
    assert len(names) == len(set(names))
    assert fallbacks.named(fallbacks.DEFAULT) is not None
    assert fallbacks.named("nope") is None


@pytest.mark.parametrize(
    ("backend", "model", "provider", "said"),
    [
        ("claude", "claude-opus-5", "", "claude/claude-opus-5"),
        ("claude", "claude-opus-5", "work", "claude@work/claude-opus-5"),
        ("kimi", "moonshot/kimi-k3", "", "kimi/moonshot/kimi-k3"),
    ],
)
def test_spec(backend: str, model: str, provider: str, said: str) -> None:
    assert fallbacks.spec(backend, model, provider) == said


@pytest.mark.parametrize(
    ("said", "read"),
    [
        ("claude/claude-opus-5", "claude/claude-opus-5"),
        (" claude-code @ work / claude-opus-5 ", "claude@work/claude-opus-5"),
        ("grok-build/grok-5", "grok/grok-5"),
        ("opencode/anthropic/claude-sonnet-5", "opencode/anthropic/claude-sonnet-5"),
        ("claude", ""),
        ("claude/", ""),
        ("claude@/m", ""),
        ("nobody/m", ""),
        ("", ""),
    ],
)
def test_reads(said: str, read: str) -> None:
    assert fallbacks.reads(said) == read


def test_nothing_written_is_a_chain_of_one() -> None:
    assert fallbacks.falls() == []
    assert fallbacks.tried("claude/m") == Falls("claude/m")
    assert fallbacks.chain("claude-code/m") == ["claude/m"]
    assert fallbacks.chain("not a place") == ["not a place"]


def test_points_writes_a_chain_down() -> None:
    step = fallbacks.points("claude/a", ["codex/b", "grok-build/c"])
    assert step == Falls("claude/a", ("codex/b", "grok/c"))
    assert fallbacks.falls() == [step]
    assert fallbacks.chain("claude/a") == ["claude/a", "codex/b", "grok/c"]
    # The places it falls back to are not walked on to chains of their own.
    fallbacks.points("codex/b", ["kimi/d"])
    assert fallbacks.chain("claude/a") == ["claude/a", "codex/b", "grok/c"]
    assert fallbacks.chain("codex/b") == ["codex/b", "kimi/d"]


def test_points_takes_one_string_as_one_place() -> None:
    assert fallbacks.points("claude/a", "codex/b").to == ("codex/b",)


@pytest.mark.parametrize("nowhere", [[], "", "  "])
def test_points_nowhere_takes_the_step_away(nowhere: list[str] | str) -> None:
    fallbacks.points("claude/a", ["codex/b"])
    assert fallbacks.points("claude/a", nowhere) == Falls("claude/a")
    assert fallbacks.falls() == []


def test_points_keeps_the_tries_already_written() -> None:
    fallbacks.retrying("claude/a", 2, "linear", 30)
    step = fallbacks.points("claude/a", ["codex/b"])
    assert step == Falls("claude/a", ("codex/b",), 2, "linear", 30.0)
    fallbacks.points("claude/a", [])
    assert fallbacks.falls() == [Falls("claude/a", (), 2, "linear", 30.0)]


@pytest.mark.parametrize(
    ("said", "to", "why"),
    [
        ("nobody/a", ["codex/b"], "is not a place"),
        ("claude/a", ["codex"], "is not a place"),
        ("claude/a", ["claude-code/a"], "cannot fall back to itself"),
        ("claude/a", ["codex/b", "codex/b"], "already one of the places"),
    ],
)
def test_points_refuses_a_chain_that_cannot_be(
    said: str, to: list[str], why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        fallbacks.points(said, to)
    assert fallbacks.falls() == []


def test_points_leaves_every_other_setting_as_it_was() -> None:
    settings.changes(lambda held: held.update(other={"kept": True}))
    fallbacks.points("claude/a", ["codex/b"])
    assert settings.read()["other"] == {"kept": True}


def test_retrying_writes_the_tries_down() -> None:
    step = fallbacks.retrying("claude@work/a", 3, "fibonacci", 0)
    assert step == Falls("claude@work/a", (), 3, "fibonacci", 0.0)
    assert fallbacks.tried("claude@work/a") == step


def test_retrying_nothing_takes_the_step_away() -> None:
    fallbacks.retrying("claude/a", 3, "constant", 0)
    fallbacks.retrying("claude/a", 0, "constant", 0)
    assert fallbacks.falls() == []


@pytest.mark.parametrize(
    ("said", "tries", "policy", "timeout", "why"),
    [
        ("nobody/a", 1, "constant", 0, "is not a place"),
        ("claude/a", 1, "sometimes", 0, "is not a retry policy"),
        ("claude/a", -1, "constant", 0, "counts"),
        ("claude/a", 1, "constant", -1, "counts"),
        ("claude/a", 1, "constant", math.inf, "counts"),
        ("claude/a", 1, "constant", math.nan, "counts"),
    ],
)
def test_retrying_refuses_what_no_waiting_can_be_made_of(
    said: str, tries: int, policy: str, timeout: float, why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        fallbacks.retrying(said, tries, policy, timeout)


def test_clear_takes_a_whole_step_away() -> None:
    fallbacks.points("claude/a", ["codex/b"])
    fallbacks.retrying("claude/a", 2, "constant", 0)
    fallbacks.points("codex/b", ["kimi/c"])
    assert fallbacks.clear("claude-code/a")
    assert [one.spec for one in fallbacks.falls()] == ["codex/b"]
    assert not fallbacks.clear("claude/a")
    assert not fallbacks.clear("not a place")


def _hand_written(rows: object) -> None:
    at = settings.where()
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(yaml.safe_dump({"fallbacks": rows}), encoding="utf-8")


def test_falls_reads_what_somebody_wrote_by_hand_forgivingly() -> None:
    _hand_written(
        [
            "not a row",
            {"spec": "nobody/a", "to": ["codex/b"]},
            {"spec": "claude/a"},  # says nothing
            {
                "spec": "claude-code/a",
                "to": ["codex/b", "claude/a", "codex/b", "junk", 7],
                "tries": "3",
                "timeout": "inf",
            },
            {"spec": "claude/a", "to": ["kimi/c"]},  # a second row for one place
            {"spec": "codex/b", "tries": "many", "timeout": -5, "to": "kimi/c"},
            {"spec": "grok/g", "tries": -2, "to": ["kimi/c"], "timeout": 12},
        ]
    )
    assert fallbacks.falls() == [
        Falls("claude/a", ("codex/b",), 3, fallbacks.DEFAULT, 0.0),
        Falls("grok/g", ("kimi/c",), 0, fallbacks.DEFAULT, 12.0),
    ]


@pytest.mark.parametrize("held", ["a string", {"a": "map"}, None])
def test_falls_of_something_that_is_not_a_list_is_nothing(held: object) -> None:
    _hand_written(held)
    assert fallbacks.falls() == []


def test_falls_of_an_unreadable_file_is_nothing() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("fallbacks: [unclosed\n", encoding="utf-8")
    assert fallbacks.falls() == []
    with pytest.raises(OSError, match="cannot be read"):
        fallbacks.points("claude/a", ["codex/b"])


@pytest.mark.parametrize(
    ("falls", "says"),
    [
        (Falls("x/y"), False),
        (Falls("x/y", tries=1), True),
        (Falls("x/y", ("a/b",)), True),
        (Falls("x/y", policy="none", timeout=9), False),
    ],
)
def test_says(falls: Falls, says: bool) -> None:
    assert falls.says() is says


@pytest.mark.parametrize(
    ("policy", "waits"),
    [
        ("none", [0, 0, 0, 0, 0]),
        ("constant", [0, 1, 1, 1, 1]),
        ("linear", [0, 1, 2, 3, 4]),
        ("exponential", [0, 1, 2, 4, 8]),
        ("fibonacci", [0, 1, 1, 2, 3]),
    ],
)
def test_waits(policy: str, waits: list[float]) -> None:
    assert [fallbacks.waits(policy, attempt) for attempt in range(1, 6)] == waits


@pytest.mark.parametrize("policy", ["linear", "exponential", "fibonacci", "constant"])
def test_waits_scale_with_the_base_and_stop_at_the_ceiling(policy: str) -> None:
    assert fallbacks.waits(policy, 2, base=3.0) == 3.0
    assert (
        fallbacks.waits(policy, 10**6, base=fallbacks.CEILING * 2) == fallbacks.CEILING
    )


@pytest.mark.parametrize("attempt", [0, 1, -3])
def test_the_first_try_waits_for_nothing(attempt: int) -> None:
    assert fallbacks.waits("constant", attempt) == 0.0


@pytest.mark.parametrize("policy", ["exponential-jitter", "not a policy"])
def test_jitter_waits_anywhere_up_to_the_exponential(
    policy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def highest(low: float, high: float) -> float:
        return high

    def lowest(low: float, high: float) -> float:
        return low

    monkeypatch.setattr(random, "uniform", highest)
    assert [fallbacks.waits(policy, attempt) for attempt in range(1, 6)] == [
        0,
        1,
        2,
        4,
        8,
    ]
    assert fallbacks.waits(policy, 10**6) == fallbacks.CEILING
    monkeypatch.setattr(random, "uniform", lowest)
    assert fallbacks.waits(policy, 5) == 0.0
