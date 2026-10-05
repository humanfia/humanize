"""The two ralph loops humanize ships -- `ralph_loop` and `stateful_ralph` -- on fakes.

One agent and the task, round after round: a fresh session each round, or one session held for
all of them. What each declares, what it says as it goes, when it gives up, and what it keeps
for `--resume`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import Budget, FlowParams, HarnessThrottled, OutputTokensExceeded
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake
from tests.flows.kit import kept, module, shipped

if TYPE_CHECKING:
    from pathlib import Path

LOOPS = ("ralph_loop", "stateful_ralph")


@pytest.fixture(autouse=True)
def _instant(monkeypatch: pytest.MonkeyPatch) -> None:
    """No pause between rounds: a test waits on nothing."""
    for name in LOOPS:
        monkeypatch.setattr(module(shipped(name)), "PAUSE", 0)


def said(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """What the loop printed about its rounds."""
    return [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith(("round ", "stopping: "))
    ]


@pytest.mark.parametrize("name", LOOPS)
def test_a_loop_is_one_agent_resumable_and_takes_no_params(name: str) -> None:
    declared = shipped(name).describe()

    assert declared.name == name
    assert declared.resumable
    assert declared.description
    assert [(role.name, role.auto, role.capabilities) for role in declared.agents] == [
        ("agent", False, frozenset())
    ]
    assert [(role.name, role.auto) for role in declared.envs] == [("workspace", True)]
    assert declared.params is FlowParams


async def test_a_ralph_loop_opens_a_session_a_round_and_stops_on_the_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    agent = FakeAgentDriver(reply="worked")
    journal = tmp_path / "run.jsonl"

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("ralph_loop"),
            "do the thing",
            agents={"agent": agent},
            budget=Budget(output_tokens=3),
            journal=journal,
        )

    # The fourth round's turn is refused by the spent budget before its CLI is started.
    assert len(agent.sessions) == 3
    assert agent.prompts == ["do the thing"] * 3
    assert {one.placement.workdir for one in agent.sessions} == {PurePosixPath("/here")}
    assert said(capsys) == ["round 1", "round 2", "round 3", "round 4"]
    assert kept(journal) == {"rounds": 4}


async def test_a_loop_picked_up_carries_the_round_it_reached(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "run.jsonl"
    for resume in (False, True):
        with pytest.raises(OutputTokensExceeded):
            await run_fake(
                shipped("ralph_loop"),
                "do the thing",
                agents={"agent": "worked"},
                budget=Budget(output_tokens=1),
                journal=journal,
                resume=resume,
            )

    assert said(capsys) == ["round 1", "round 2", "round 3", "round 4"]
    assert kept(journal) == {"rounds": 4}


async def test_a_loop_whose_rounds_all_answer_with_nothing_gives_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "run.jsonl"
    flow = shipped("ralph_loop")

    await run_fake(flow, "do the thing", agents={"agent": ""}, journal=journal)

    assert said(capsys) == [
        "round 1",
        "round 2",
        "round 3",
        "stopping: 3 rounds in a row answered with nothing",
    ]
    assert kept(journal) == {"rounds": module(flow).STALLED}


async def test_a_round_that_answered_puts_the_run_of_empty_ones_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    agent = FakeAgentDriver(reply=["", "", "worked", "", "", ""])

    await run_fake(shipped("ralph_loop"), "do the thing", agents={"agent": agent})

    assert said(capsys) == [
        *(f"round {each}" for each in range(1, 7)),
        "stopping: 3 rounds in a row answered with nothing",
    ]
    assert len(agent.sessions) == 6


async def test_stateful_ralph_holds_one_session_for_every_round(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    agent = FakeAgentDriver(reply="worked")
    journal = tmp_path / "run.jsonl"

    with pytest.raises(OutputTokensExceeded):
        await run_fake(
            shipped("stateful_ralph"),
            "do the thing",
            agents={"agent": agent},
            budget=Budget(output_tokens=2),
            journal=journal,
        )

    (session,) = agent.sessions
    assert session.prompts == ["do the thing", "do the thing"]
    assert said(capsys) == ["round 1", "round 2", "round 3"]
    assert kept(journal) == {"rounds": 3}


async def test_stateful_ralph_gives_up_on_a_run_of_nothing_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    agent = FakeAgentDriver(reply="")
    flow = shipped("stateful_ralph")

    await run_fake(flow, "do the thing", agents={"agent": agent})

    assert said(capsys) == [
        "round 1",
        "round 2",
        "round 3",
        "stopping: 3 rounds in a row answered with nothing",
    ]
    (session,) = agent.sessions
    assert len(session.prompts) == module(flow).STALLED


@pytest.mark.parametrize("name", LOOPS)
async def test_a_failed_turn_counts_as_one_answered_with_nothing(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    turns: list[str] = []

    def reply(prompt: str, **_: Any) -> str:
        turns.append(prompt)
        if len(turns) in (1, 3):
            raise HarnessThrottled("slow down")
        return ""

    await run_fake(shipped(name), "do the thing", agents={"agent": reply})

    assert said(capsys) == [
        "round 1",
        "round 1 failed: slow down",
        "round 2",
        "round 3",
        "round 3 failed: slow down",
        "stopping: 3 rounds in a row answered with nothing",
    ]
