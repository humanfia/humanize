"""`rlar`: an actor works in one session until a fresh reviewer says the task is done."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import CostExceeded, HarnessDropped, HarnessKilled, OutputSchemaError
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType
    from unittest import mock


@pytest.fixture
def rlar(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "rlar")


def review(rlar: Any, notes: str, *, done: bool = False) -> Any:
    return rlar.Review(done=done, notes=notes)


def test_rlar_is_resumable_with_an_actor_and_a_reviewer(rlar: Any) -> None:
    declared = rlar.rlar.declared
    assert declared["resumable"] is True
    assert declared["agents"].__required_keys__ == {"actor", "reviewer"}


@pytest.mark.parametrize(
    "given",
    [{"done": True}, {"notes": "n"}, {"done": True, "notes": "n", "score": 1}],
)
def test_a_review_is_done_and_notes_and_nothing_else(rlar: Any, given: Any) -> None:
    with pytest.raises(pydantic.ValidationError):
        rlar.Review.model_validate(given)


async def test_a_review_that_says_done_ends_it_with_its_notes(
    rlar: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    actor = doubles.agent("did it")
    reviewer = doubles.agent(review(rlar, "built and tested", done=True))
    state: dict[str, Any] = {}

    finished = await doubles.call(
        rlar.rlar,
        "the task",
        ctx=doubles.context(state),
        actor=actor,
        reviewer=reviewer,
    )

    assert finished == "built and tested"
    assert "built and tested" in capsys.readouterr().out
    assert doubles.prompts(actor) == ["the task"]
    reviewer.run.assert_awaited_once_with(
        rlar.REVIEW_PROMPT + "the task" + rlar.SAID.format(said="did it"),
        session=doubles.sessions(reviewer)[0],
        env=doubles.WORKSPACE,
        output_schema=rlar.Review,
    )
    assert state == {}


async def test_the_actor_is_told_each_review_in_its_one_session(rlar: Any) -> None:
    actor = doubles.agent("first go", "second go", "third go")
    reviewer = doubles.agent(
        review(rlar, "fix the tests"),
        review(rlar, "now the docs"),
        review(rlar, "done", done=True),
    )
    state: dict[str, Any] = {}

    await doubles.call(
        rlar.rlar,
        "the task",
        ctx=doubles.context(state),
        actor=actor,
        reviewer=reviewer,
    )

    assert doubles.prompts(actor) == ["the task", "fix the tests", "now the docs"]
    actor.spawn.assert_awaited_once()
    assert reviewer.spawn.await_count == 3
    assert len(set(map(id, doubles.sessions(reviewer)))) == 3
    assert state == {}


async def test_each_fresh_reviewer_reads_what_the_actor_said_that_round(
    rlar: Any,
) -> None:
    # A task whose deliverable is the answer itself: there is no file to read it from.
    actor = doubles.agent(
        "one thread at a time", "one thread at a time, on a shared thing"
    )
    reviewer = doubles.agent(
        review(rlar, "say what it guards"), review(rlar, "right", done=True)
    )

    await doubles.call(
        rlar.rlar,
        "what is a mutex",
        ctx=doubles.context({}),
        actor=actor,
        reviewer=reviewer,
    )

    assert doubles.prompts(reviewer) == [
        rlar.REVIEW_PROMPT + "what is a mutex" + rlar.SAID.format(said=said)
        for said in ("one thread at a time", "one thread at a time, on a shared thing")
    ]
    # Told what the actor said and nothing else of its conversation, each in a session of its
    # own: the reviewer stays as fresh as it was.
    assert len(set(map(id, doubles.sessions(reviewer)))) == 2
    assert doubles.prompts(actor) == ["what is a mutex", "say what it guards"]


async def test_each_round_not_done_is_kept_for_a_resume(rlar: Any) -> None:
    actor = doubles.agent("go", "go", CostExceeded("spent"))
    reviewer = doubles.agent(review(rlar, "more"), review(rlar, "still more"))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            rlar.rlar, "t", ctx=doubles.context(state), actor=actor, reviewer=reviewer
        )

    assert state == {"rounds": 2, "notes": "still more"}


async def test_a_resumed_run_hands_the_actor_the_last_review(rlar: Any) -> None:
    actor = doubles.agent("picked up")
    reviewer = doubles.agent(review(rlar, "all good", done=True))
    state: dict[str, Any] = {"rounds": 3, "notes": "the docs are missing"}

    await doubles.call(
        rlar.rlar,
        "the task",
        ctx=doubles.context(state),
        actor=actor,
        reviewer=reviewer,
    )

    assert doubles.prompts(actor) == [
        rlar.PICKED_UP.format(task="the task", notes="the docs are missing")
    ]
    assert state == {}


async def test_a_turn_with_nothing_is_not_reviewed_and_is_taken_again(
    rlar: Any,
) -> None:
    actor = doubles.agent("", "went", CostExceeded("spent"))
    reviewer = doubles.agent(review(rlar, ""))
    state: dict[str, Any] = {}

    with pytest.raises(CostExceeded):
        await doubles.call(
            rlar.rlar, "t", ctx=doubles.context(state), actor=actor, reviewer=reviewer
        )

    reviewer.run.assert_awaited_once()
    # A review with no notes leaves the actor on what it had.
    assert doubles.prompts(actor) == ["t", "t", "t"]
    assert state == {"rounds": 1, "notes": ""}


async def test_a_failed_review_is_taken_again_next_round(rlar: Any) -> None:
    actor = doubles.agent("go", "go again")
    reviewer = doubles.agent(
        OutputSchemaError("out of shape"), review(rlar, "ok", done=True)
    )
    state: dict[str, Any] = {}

    finished = await doubles.call(
        rlar.rlar, "t", ctx=doubles.context(state), actor=actor, reviewer=reviewer
    )

    assert finished == "ok"
    assert doubles.prompts(actor) == ["t", "t"]


async def test_three_failures_in_a_row_end_it_with_the_last(rlar: Any) -> None:
    actor = doubles.agent(HarnessDropped("1"), "went", HarnessKilled("3"))
    reviewer = doubles.agent(HarnessDropped("2"))

    with pytest.raises(HarnessKilled, match="3"):
        await doubles.call(
            rlar.rlar, "t", ctx=doubles.context({}), actor=actor, reviewer=reviewer
        )


async def test_a_review_that_comes_back_resets_the_failures(rlar: Any) -> None:
    actor = doubles.agent(
        HarnessDropped("1"), "went", HarnessDropped("2"), HarnessDropped("3"), "went"
    )
    reviewer = doubles.agent(review(rlar, "more"), review(rlar, "done", done=True))

    finished = await doubles.call(
        rlar.rlar, "t", ctx=doubles.context({}), actor=actor, reviewer=reviewer
    )

    assert finished == "done"
