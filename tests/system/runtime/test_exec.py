"""`hmz exec` driving a real coding agent CLI, as the account this machine is signed in as.

The stand-in half is `tests/integration/cli/test_run_command.py`, which holds the line, its
refusals and the flow to a stand-in `claude`. What only the real thing can show is that a line
naming a real harness gets a turn out of it: a flow of this project's own with a role, a
workspace and a param, run under a budget, and `chat`, which is run with none. Claude Code on
its cheapest model, since that is one prompt a test; a machine without it installed, or signed
out of it, skips saying so.

These cost tokens and need network access, so they only run with ``pytest --run-agents``.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.cli import main
from hmz.flows import HarnessError
from hmz.runtime.epic import epics, read, sessions
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.agent, pytest.mark.timeout(600)]

#: The cheapest model Claude Code takes, at the least effort it takes.
WORKER = "claude/claude-haiku-4-5-20251001:low"

#: A flow of this project's own: one role, the workspace it is started in, and a param.
DEMO = '''"""Asks for a word a round, and writes down what came back."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    LocalEnv,
    flow,
)


class Workspace(LocalEnv, FilesEnvMixin): ...


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=Envs, params=Params)
async def demo(task, *, agents, envs, params, ctx):
    worker, here = agents["worker"], envs["workspace"]
    session = await worker.spawn(env=here)
    said = []
    for n in range(params.rounds):
        said.append(
            await worker.run(
                f"Reply with exactly one word, the word round{n}, and nothing else.",
                session=session,
            )
        )
    await here.write("demo.json", repr(said).encode())
    return said
'''


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project of its own, with the demo flow in it; skipped where there is no `claude`."""
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed here")
    written(tmp_path / ".humanize" / "flows", "demo", DEMO)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _exec(*argv: str) -> int:
    """One `hmz exec` line, skipped where the account refuses rather than the run failing."""
    try:
        return main(["exec", *argv])
    except HarnessError as refused:
        pytest.skip(f"claude would not take the turn here: {refused}")


def test_a_flow_of_your_own_runs_on_a_real_cli(project: Path) -> None:
    assert (
        _exec(
            "-f",
            "demo",
            "-a",
            f"worker={WORKER}",
            "-p",
            "rounds=2",
            "-b",
            "cost=0.5",
            "two words",
        )
        == 0
    )

    said = (project / "demo.json").read_text()
    assert "round0" in said
    assert "round1" in said
    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert ran.how == "done"
    assert ran.params == {"rounds": 2}
    # One session, named for its role, and the output tokens the run spent written down.
    (one,) = sessions(epic)
    assert one.agent == "worker"
    usage = [
        json.loads(line)
        for line in (epic / "epic.jsonl").read_text().splitlines()
        if '"usage"' in line
    ]
    assert usage[-1]["output_tokens"] > 0


def test_chat_runs_on_a_real_cli_with_no_budget_and_ends_after_one_turn(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        _exec(
            "-f",
            "chat",
            "-a",
            f"assistant={WORKER}",
            "Reply with exactly one word, the word pineapple, and nothing else.",
        )
        == 0
    )

    assert "pineapple" in capsys.readouterr().out.lower()
    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert ran.budget is not None
    assert ran.budget["cost"] == "Infinity"


def test_a_run_written_for_a_program_is_one_object_a_line(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        _exec(
            "-f",
            "demo",
            "-a",
            f"worker={WORKER}",
            "-b",
            "cost=0.5",
            "--json",
            "one word",
        )
        == 0
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines
    objects = [json.loads(line) for line in lines]
    assert {one["agent"] for one in objects} == {"worker"}
    assert any(one["kind"] == "result" for one in objects)
