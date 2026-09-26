"""The one flow humanize keeps in the package: what a run of it is, and what it leaves.

`chat` is one agent talking, and it is here rather than in the official flowverse because it is
what humanize does before anything has been fetched. Everything else humanize offers is in that
repository, and what those flows do is tested where they live.

Nothing here starts a coding agent: the agent is the stand-in Claude Code of
:mod:`tests.flows.standins`, and the person is an outworlder answering from a list -- or nobody,
which is what a command line is.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from hmz.flows import AskUserHookAgentMixin, Budget, HarnessError, HarnessKind
from hmz.runtime.epic import RESUME, epics, read
from hmz.runtime.flowing import HARNESS_CAPABILITIES, builtin, resolved
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeOutworlder,
    FakeSession,
    run_fake,
)
from hmz.runtime.runner import Runner
from tests.flows import standins

if TYPE_CHECKING:
    from pathlib import Path

#: What the agent runs, as `-a` spells it after the role.
AGENT = "claude/claude-haiku-4-5:low"


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in Claude Code on PATH, with a home of its own, run from a project of its own."""
    standins.install(tmp_path / "bin", "claude", standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    (tmp_path / "project").mkdir()
    monkeypatch.chdir(tmp_path / "project")


def test_chat_is_humanize_s_own_and_takes_whichever_agent_it_is_given() -> None:
    """One agent role any harness fills, and whoever is outside the run; nothing to resume."""
    flow = resolved("chat")
    declared = flow.describe()

    assert builtin(flow)
    assert not declared.resumable
    assert [(one.name, one.auto, one.capabilities) for one in declared.agents] == [
        ("assistant", False, frozenset()),
        ("human", True, frozenset()),
    ]
    assert [(one.name, one.auto) for one in declared.envs] == [("workspace", True)]


@pytest.mark.parametrize(
    ("harness", "put"),
    [
        (HarnessKind.CLAUDE, ["left"]),
        (HarnessKind.KIMI, ["left"]),
        (HarnessKind.CODEX, ["left"]),
    ],
)
async def test_a_question_the_agent_asks_is_put_to_the_person(
    harness: HarnessKind, put: list[str]
) -> None:
    """On a harness that asks, the hook chat hangs puts the question to the outworlder.

    Which chat can only do because it is handed its harness's full view: it declares a plain
    `Agent`, and the hook is `AskUserHookAgentMixin`'s.
    """
    asked: list[str | None] = []

    async def asks(prompt: str, *, session: FakeSession, **_: object) -> str:
        del prompt
        asked.append(await session.ask("Which way?", ("left", "right")))
        return "done"

    agent = FakeAgentDriver(harness, reply=asks)
    person = FakeOutworlder(["left", ""])

    await run_fake(
        resolved("chat"), "go", agents={"assistant": agent}, outworlder=person
    )

    assert person.asked[0] == "Which way? (left / right)"
    assert asked == put


async def test_a_harness_that_cannot_ask_is_not_hung_a_hook_for_it() -> None:
    """Full view is the harness's own: cursor-agent asks nothing, and chat hangs nothing."""
    agent = FakeAgentDriver(HarnessKind.CURSOR_AGENT, reply="done")
    person = FakeOutworlder([""])

    await run_fake(
        resolved("chat"), "go", agents={"assistant": agent}, outworlder=person
    )

    assert AskUserHookAgentMixin not in HARNESS_CAPABILITIES[HarnessKind.CURSOR_AGENT]
    assert person.asked == ["done"]


async def test_chat_goes_on_for_as_long_as_the_person_answers() -> None:
    """Each answer is the next turn of the one conversation, and nothing said ends it."""
    agent = FakeAgentDriver(reply=["one", "two", "three"])
    person = FakeOutworlder(["more", "and more", ""])

    await run_fake(
        resolved("chat"), "hello", agents={"assistant": agent}, outworlder=person
    )

    assert agent.prompts == ["hello", "more", "and more"]
    assert person.asked == ["one", "two", "three"]
    assert len(agent.sessions) == 1


def test_chat_runs_with_no_budget_of_its_own(claude: None, tmp_path: Path) -> None:
    """Under `Budget(cost=inf)`, the one flow that may be; and nobody here ends it at once."""
    runner = Runner("chat", agents={"assistant": AGENT})

    assert runner.budget == Budget(cost=math.inf)
    assert runner.run("Reply with the single word: hello") is None
    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert ran.how == "done"
    assert ran.budget == {
        "duration": None,
        "cost": "Infinity",
        "output_tokens": None,
        "graceful": True,
    }
    assert [one.agent for one in ran.sessions] == ["assistant"]
    # What was said is the backend's log, and there is nothing to pick up.
    assert not (epic / RESUME).exists()


def test_a_chat_whose_opening_turn_cannot_be_taken_says_so(claude: None) -> None:
    """The first turn is the one that fails out loud, and the reason is the loop's own shape.

    Swallowed, a turn that failed answers with nothing -- and nothing is what the person
    answers with where nobody is at a prompt, which this flow reads as a conversation that is
    over. So a refused turn and a finished conversation would be the same run: no output, no
    error and a clean exit, on a flow that had done none of what it was asked.
    """
    with pytest.raises(HarnessError, match="no such thing"):
        Runner("chat", agents={"assistant": AGENT}).run("fail: no such thing")
