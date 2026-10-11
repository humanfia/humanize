"""`hmz exec`, run as a program, driving the stand-in `claude` on the local workspace.

    hmz exec -f FLOW -a ROLE=CLI/MODEL[:EFFORT] [-e ROLE=BACKEND[/WORKDIR]] [-p KEY=VALUE]
             [--json] TASK

Each run here is a real `python -m hmz exec`: the line read, the flow found and loaded, the
stand-in started where the real CLI would be, its stream read back, the run written down as
an epic. A line that is wrong is refused with exit status 2 before anything is started, which
`hmz.cli.main` is asked in this process.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.cli import main
from hmz.sdk import Hmz
from tests.integration.doubles_core import (
    AGENT,
    MODEL,
    TOKENS,
    hmz_exec,
    install,
    started,
    write_flow,
)

if TYPE_CHECKING:
    from pathlib import Path

#: A flow working somewhere other than the workspace, which `-e` names.
ELSEWHERE = """
from typing import NotRequired

from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    worker: Agent


class Envs(EnvCollection):
    workspace: LocalEnv
    there: NotRequired[Env]


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def elsewhere(task, *, agents, envs, params, ctx):
    worker = agents["worker"]
    return await worker.run(task, session=await worker.spawn(), env=envs["there"])
"""


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return install(tmp_path, monkeypatch)


def _refused(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    """Runs a line that is to be refused, and answers with what it said on the way out."""
    with pytest.raises(SystemExit) as stopped:
        main(["exec", *argv])
    assert stopped.value.code == 2
    return capsys.readouterr().err


def test_chat_answers_on_stdout_and_works_in_the_project(
    tmp_path: Path, project: Path
) -> None:
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}:high", "hello there")

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "did: hello there"
    (start,) = started(tmp_path)
    assert start["cwd"] == str(project.resolve())
    assert start["argv"][start["argv"].index("--model") + 1] == MODEL
    assert start["argv"][start["argv"].index("--effort") + 1] == "high"
    assert (project / "landed.txt").read_text() == "hello there\n"
    epics = Hmz(project).epics
    (epic,) = epics.all()
    ran_as = epics.read(epic)
    assert ran_as is not None
    assert (ran_as.flow, ran_as.task, ran_as.how) == ("chat", "hello there", "done")
    assert [one.spec for one in ran_as.agents] == [f"{AGENT}:high"]
    (session,) = ran_as.sessions
    assert (session.agent, session.backend) == ("assistant", "claude")
    assert session.ident == start["session"]


def test_goal_says_the_task_as_a_goal() -> None:
    ran = hmz_exec("-f", "goal", "-a", f"worker={AGENT}", "-p", "budget.cost=1", "win")

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "goal met: win"


def test_a_failed_first_turn_fails_the_run_with_what_the_cli_said() -> None:
    ran = hmz_exec("-f", "chat", "-a", f"assistant={AGENT}", "--", "fail: it broke")

    assert ran.returncode != 0
    assert "it broke" in ran.stderr


def test_a_spent_duration_ends_a_loop_as_an_ordinary_stop(project: Path) -> None:
    ran = hmz_exec(
        "-f", "ralph_loop", "-a", f"agent={AGENT}", "-p", "budget.duration=2s", "work"
    )

    assert ran.returncode == 0, ran.stderr
    assert "did: work" in ran.stdout
    assert "hmz exec: stopped --" in ran.stderr
    assert "duration" in ran.stderr
    assert "Traceback" not in ran.stderr
    epics = Hmz(project).epics
    (epic,) = epics.all()
    ran_as = epics.read(epic)
    assert ran_as is not None
    assert ran_as.budget is not None
    assert ran_as.budget["duration"] is not None


def test_output_tokens_spent_cut_off_the_turn_that_spends_them(tmp_path: Path) -> None:
    ran = hmz_exec(
        "-f",
        "stateful_ralph",
        "-a",
        f"agent={AGENT}",
        "-p",
        f"budget.output_tokens={TOKENS - 1},budget.graceful=false",
        "work",
    )

    assert ran.returncode == 0, ran.stderr
    assert f"wrote {TOKENS} of {TOKENS - 1} output tokens" in ran.stderr
    assert len(started(tmp_path)) == 1


def test_json_writes_the_run_as_one_object_per_line() -> None:
    ran = hmz_exec(
        "--json", "-f", "goal", "-a", f"worker={AGENT}", "-p", "budget.cost=1", "win"
    )

    assert ran.returncode == 0, ran.stderr
    said = [json.loads(line) for line in ran.stdout.splitlines()]
    assert said[0]["kind"] == "begins"
    assert said[-1]["kind"] == "ends"
    (result,) = [one for one in said if one["kind"] == "result"]
    assert result["text"] == "goal met: win"
    assert (result["agent"], result["cli"], result["model"]) == (
        "worker",
        "claude",
        MODEL,
    )
    assert result["tokens"] == {MODEL: 10 + TOKENS}


def test_an_env_role_works_where_its_e_names(tmp_path: Path) -> None:
    flow = write_flow(tmp_path / "flows", "elsewhere", ELSEWHERE)
    there = tmp_path / "there"
    there.mkdir()

    ran = hmz_exec(
        "-f",
        flow,
        "-a",
        f"worker={AGENT}",
        "-e",
        f"there=local/{there}",
        "-p",
        "budget.cost=1",
        "work there",
    )

    assert ran.returncode == 0, ran.stderr
    (start,) = started(tmp_path)
    assert start["cwd"] == str(there.resolve())
    assert (there / "landed.txt").read_text() == "work there\n"


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["-a", "assistant"], "assistant"),
        (["-a", "assistant=no-such-cli/m"], "no-such-cli"),
        (["-a", f"assistant={AGENT},stranger={AGENT}"], "stranger"),
        (["-a", f"assistant={AGENT}", "-e", "workspace=nowhere/x"], "nowhere"),
        (["-a", f"assistant={AGENT}", "-e", "workspace=local/elsewhere"], "workspace"),
        (["-a", f"assistant={AGENT}", "-e", "stranger=local"], "stranger"),
        (["-a", f"assistant={AGENT}", "-p", "rounds=3"], "rounds"),
        (["-a", f"assistant={AGENT}", "-p", "budget.cost=lots"], "lots"),
        (["-a", f"assistant={AGENT}", "-p", "budget.duration=soon"], "soon"),
        (["-a", f"assistant={AGENT}", "-p", "novalue"], "novalue"),
    ],
)
def test_a_wrong_agent_env_or_param_is_refused_before_anything_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], says: str
) -> None:
    said = _refused(capsys, "-f", "chat", *argv, "hello")

    assert "hmz exec: error" in said
    assert says in said
    assert not started(tmp_path)


def test_a_loop_without_a_budget_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    said = _refused(capsys, "-f", "ralph_loop", "-a", f"agent={AGENT}", "work")

    assert "budget" in said


def test_a_flow_that_is_not_there_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    said = _refused(capsys, "-f", "./no_such_flow", "-p", "budget.cost=1", "work")

    assert "no_such_flow" in said


def test_a_role_left_out_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    said = _refused(
        capsys, "-f", "rlar", "-a", f"actor={AGENT}", "-p", "budget.cost=1", "x"
    )

    assert "reviewer" in said
