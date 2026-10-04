"""`rlar`, which humanize ships: an actor at work, and a fresh reviewer reading it, on fakes.

What it declares and the skill it carries, how a review becomes the actor's next prompt, what
it does with a turn that failed or a review out of shape, and the review it hands a fresh actor
on `--resume`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import Budget, HarnessDropped, OutputTokensExceeded
from hmz.runtime.flowing import BUILTIN_AT
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake
from tests.flows.kit import kept, module, shipped

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.runtime.flowing import FlowImpl

TASK = "make the tests pass"


@pytest.fixture
def rlar(monkeypatch: pytest.MonkeyPatch) -> FlowImpl:
    """The flow, with no pause between rounds: a test waits on nothing."""
    flow = shipped("rlar")
    monkeypatch.setattr(module(flow), "PAUSE", 0)
    return flow


def review(done: bool, notes: str) -> dict[str, Any]:
    return {"done": done, "notes": notes}


def test_rlar_is_an_actor_and_a_reviewer_carrying_its_skill(rlar: FlowImpl) -> None:
    declared = rlar.describe()

    assert declared.name == "rlar"
    assert declared.resumable
    assert [(role.name, role.skills) for role in declared.agents] == [
        ("actor", ()),
        ("reviewer", ("review-notes",)),
    ]
    assert [(role.name, role.auto) for role in declared.envs] == [("workspace", True)]


async def test_the_review_is_the_actors_next_prompt_until_it_says_done(
    rlar: FlowImpl, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    actor = FakeAgentDriver(reply="worked")
    reviewer = FakeAgentDriver(
        reply=[
            review(False, "the parser drops the last line"),
            review(True, "all green"),
        ]
    )
    journal = tmp_path / "run.jsonl"

    said = await run_fake(
        rlar,
        TASK,
        agents={"actor": actor, "reviewer": reviewer},
        journal=journal,
    )

    assert said == "all green"
    assert "all green" in capsys.readouterr().out
    (working,) = actor.sessions
    assert working.prompts == [TASK, "the parser drops the last line"]
    assert len(reviewer.sessions) == 2
    for reading in reviewer.sessions:
        assert reading.prompts == [module(rlar).REVIEW_PROMPT + TASK]
        (skill,) = reading.skills
        assert skill.name == "review-notes"
        assert skill.at == BUILTIN_AT / "rlar" / "skills" / "review-notes"
    assert kept(journal) == {}


async def test_a_turn_that_answered_nothing_is_taken_again_unreviewed(
    rlar: FlowImpl,
) -> None:
    actor = FakeAgentDriver(reply=["", "worked"])
    reviewer = FakeAgentDriver(reply=[review(True, "done")])

    await run_fake(rlar, TASK, agents={"actor": actor, "reviewer": reviewer})

    assert actor.prompts == [TASK, TASK]
    assert len(reviewer.sessions) == 1


async def test_a_review_out_of_shape_is_no_review(rlar: FlowImpl) -> None:
    actor = FakeAgentDriver(reply="worked")
    reviewer = FakeAgentDriver(reply=["not a review", review(True, "done")])

    said = await run_fake(rlar, TASK, agents={"actor": actor, "reviewer": reviewer})

    assert said == "done"
    assert actor.prompts == [TASK, TASK]


async def test_failed_turns_are_taken_again_until_three_in_a_row(
    rlar: FlowImpl,
) -> None:
    worked: list[str] = []

    def actor(prompt: str, **_: Any) -> str:
        worked.append(prompt)
        if len(worked) in (1, 3, 4, 5):
            raise HarnessDropped("the connection went")
        return "worked"

    reviewer = FakeAgentDriver(reply=[review(False, "again")])

    with pytest.raises(HarnessDropped):
        await run_fake(rlar, TASK, agents={"actor": actor, "reviewer": reviewer})

    assert worked == [TASK, TASK, "again", "again", "again"]
    assert len(reviewer.sessions) == 1


async def test_a_run_picked_up_hands_a_fresh_actor_the_last_review(
    rlar: FlowImpl, tmp_path: Path
) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            rlar,
            TASK,
            agents={
                "actor": "worked",
                "reviewer": FakeAgentDriver(reply=[review(False, "left off here")]),
            },
            budget=Budget(output_tokens=2),
            journal=journal,
        )
    assert kept(journal) == {"rounds": 1, "notes": "left off here"}
    actor = FakeAgentDriver(reply="worked")

    said = await run_fake(
        rlar,
        TASK,
        agents={
            "actor": actor,
            "reviewer": FakeAgentDriver(reply=[review(True, "ok")]),
        },
        journal=journal,
        resume=True,
    )

    assert said == "ok"
    assert actor.prompts == [
        module(rlar).PICKED_UP.format(task=TASK, notes="left off here")
    ]
    assert kept(journal) == {}
