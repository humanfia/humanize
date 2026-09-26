"""The command line: a flow, what each of its roles is given, its params, and its budget.

    hmz exec -f FLOW -a ROLE=CLI[@PROVIDER]/MODEL:EFFORT -e ROLE=BACKEND@PROVIDER/WORKDIR
             -p KEY=VALUE -b duration=...,cost=...,output_tokens=... [--resume] [--json] TASK

Most of what is checked here drives no agent. A flow is handed views of its drivers and decides
for itself whether to open a session, so a flow that only writes down what it was handed
exercises the whole path from the command line to the flow without a turn being taken -- and
every refusal is a usage error before any agent has started. Where a turn is taken, it is taken
by the stand-in `claude` of :mod:`tests.flows.standins`.
"""

from __future__ import annotations

import json
import re
import runpy
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest

from hmz.cli import main
from hmz.runtime.doing.running import Run
from hmz.runtime.epic import epics, read
from hmz.runtime.flowing import BUILTIN_AT, ENTRY
from tests.flows import standins
from tests.stubs import written

#: A flow that takes no turn and writes down what it was handed, beside its own file.
RECORD = """
import json
import os
from pathlib import Path
from typing import NotRequired

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowParams,
    LocalEnv,
    Outworlder,
    flow,
)


class Agents(AgentCollection):
    builder: Agent
    reviewer: NotRequired[Agent]
    human: Outworlder


class Envs(EnvCollection):
    here: LocalEnv
    there: NotRequired[Env]


class Params(FlowParams):
    rounds: int = 1
    tags: list[str] = []


@flow(agents=Agents, envs=Envs, params=Params)
async def record(task, *, agents, envs, params, ctx):
    Path(__file__).with_name("seen.json").write_text(
        json.dumps(
            {
                "agents": {
                    role: [one.harness, one.provider, one.model, one.effort]
                    for role, one in agents.items()
                    if role != "human"
                },
                "away": agents["human"].away,
                "envs": {
                    role: [one.backend, one.provider, str(one.workdir)]
                    for role, one in envs.items()
                },
                "params": params.model_dump(),
                "budget": ctx.budget.model_dump(mode="json"),
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""

#: A flow whose role asks for what only some harnesses do.
PICKY = """
from hmz.flows import (
    AgentCollection,
    ClaudeCodeAgent,
    EnvCollection,
    FlowParams,
    Agent,
    GoalCommandAgentMixin,
    flow,
)


class Pursues(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    claude: ClaudeCodeAgent
    pursuer: Pursues


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def picky(task, *, agents, envs, params, ctx):
    pass
"""

#: A resumable flow, which takes no turn either.
KEEPS = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, resumable=True)
async def keeps(task, *, agents, envs, params, ctx):
    ctx.state["runs"] = (ctx.state["runs"] if "runs" in ctx.state else 0) + 1
    print(f"run {ctx.state['runs']}")
"""

#: What every line here names for `builder`, unless it names something else.
BUILDER = "builder=claude/claude-haiku-4-5:high"

#: What a line gives a run to spend, unless it is a line about budgets.
BUDGET = ["-b", "cost=1"]


def _flow(tmp_path: Path, source: str = RECORD, name: str = "record") -> str:
    """Writes a flow out as a directory and answers with its path, as a line would name it."""
    return str(written(tmp_path / "flows", name, source))


def _seen(tmp_path: Path, name: str = "record") -> dict[str, Any]:
    """What the flow written by :data:`RECORD` was handed."""
    return json.loads((tmp_path / "flows" / name / "seen.json").read_text())


def _refused(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    """Runs a line that is to be refused, and answers with what it said on the way out."""
    with pytest.raises(SystemExit) as stopped:
        main(["exec", *argv])
    assert stopped.value.code == 2
    return capsys.readouterr().err


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project of its own to run in."""
    at = tmp_path / "project"
    at.mkdir()
    monkeypatch.chdir(at)
    return at


def test_it_drives_the_flow_with_what_the_line_names(
    tmp_path: Path, here: Path
) -> None:
    flow = _flow(tmp_path)

    assert (
        main(
            [
                "exec",
                "-f",
                flow,
                "-a",
                BUILDER,
                "-p",
                "rounds=3",
                "-b",
                "duration=1h,cost=2.5",
                "the task",
            ]
        )
        == 0
    )

    seen = _seen(tmp_path)
    assert seen["agents"] == {"builder": ["claude", "", "claude-haiku-4-5", "high"]}
    # Nobody is at a prompt, so whoever is outside the run is away.
    assert seen["away"] is True
    # The workspace is where the line was given, and a role nobody named is not there.
    assert seen["envs"] == {"here": ["local", "", str(here.resolve())]}
    assert seen["params"] == {"rounds": 3, "tags": []}
    assert seen["budget"]["cost"] == 2.5
    assert seen["budget"]["duration"] is not None
    assert seen["task"] == "the task"
    assert Path(seen["cwd"]).resolve() == here.resolve()


def test_one_option_may_name_several_agents_and_every_option_adds_to_them(
    tmp_path: Path, here: Path
) -> None:
    flow = _flow(tmp_path)

    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            f"{BUILDER},reviewer=codex@work/gpt-5.5:low",
            *BUDGET,
            "task",
        ]
    )
    together = _seen(tmp_path)["agents"]
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            BUILDER,
            "--agents",
            "reviewer=codex@work/gpt-5.5:low",
            *BUDGET,
            "task",
        ]
    )

    assert _seen(tmp_path)["agents"] == together
    # And the account is the reviewer's own: after the `@`, before the model.
    assert together["reviewer"] == ["codex", "work", "gpt-5.5", "low"]


def test_an_environment_role_is_given_where_it_is(tmp_path: Path, here: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    main(
        [
            "exec",
            "-f",
            _flow(tmp_path),
            "-a",
            BUILDER,
            "-e",
            f"there=local@{elsewhere}",
            *BUDGET,
            "task",
        ]
    )

    assert _seen(tmp_path)["envs"]["there"] == ["local", "", str(elsewhere)]


@pytest.mark.parametrize(
    ("said", "read"),
    [
        (["rounds=4"], {"rounds": 4, "tags": []}),
        (['tags=["a","b"]'], {"rounds": 1, "tags": ["a", "b"]}),
        (["rounds=2,tags=[]"], {"rounds": 2, "tags": []}),
    ],
)
def test_a_param_is_read_as_the_flow_declared_it(
    tmp_path: Path, here: Path, said: list[str], read: dict[str, Any]
) -> None:
    argv = [one for value in said for one in ("-p", value)]

    main(["exec", "-f", _flow(tmp_path), "-a", BUILDER, *argv, *BUDGET, "task"])

    assert _seen(tmp_path)["params"] == read


@pytest.mark.parametrize(
    ("said", "complaint"),
    [
        (["-p", "nope=1"], "nope"),
        (["-p", "rounds=many"], "rounds"),
        (["-a", "human=claude/m:high"], "filled by the runtime"),
        (["-e", "here=local@/tmp"], "is the workspace"),
        (["-a", "nobody=claude/m:high"], "has no agent role 'nobody'"),
        (["-e", "nowhere=local@/tmp"], "has no environment role 'nowhere'"),
        (["-e", "there=local@/no/such/directory"], "no directory"),
    ],
)
def test_what_the_flow_does_not_take_is_a_usage_error(
    tmp_path: Path,
    here: Path,
    capsys: pytest.CaptureFixture[str],
    said: list[str],
    complaint: str,
) -> None:
    error = _refused(
        capsys, "-f", _flow(tmp_path), "-a", BUILDER, *said, *BUDGET, "task"
    )

    assert error.startswith("hmz exec: error:")
    assert complaint in error
    assert not (tmp_path / "flows" / "record" / "seen.json").exists()
    assert (
        epics() == []
    )  # refused before any agent started, and before a run was written


def test_a_required_role_left_out_is_a_usage_error(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _refused(capsys, "-f", _flow(tmp_path), *BUDGET, "task")

    assert "needs an agent for 'builder'" in error


def test_a_run_is_given_a_budget_or_is_not_started(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _refused(capsys, "-f", _flow(tmp_path), "-a", BUILDER, "task")

    assert "is given a budget" in error
    assert epics() == []


@pytest.mark.parametrize(
    ("agents", "complaint"),
    [
        (
            ["claude=codex/gpt-5.5:low", "pursuer=claude/m:high"],
            "'claude' is claude, and codex was given",
        ),
        (
            ["claude=claude/m:high", "pursuer=opencode/opencode/big-pickle:high"],
            "needs GoalCommandAgentMixin",
        ),
    ],
)
def test_an_agent_that_cannot_be_what_its_role_asks_is_refused_before_the_run(
    tmp_path: Path,
    here: Path,
    capsys: pytest.CaptureFixture[str],
    agents: list[str],
    complaint: str,
) -> None:
    flow = _flow(tmp_path, PICKY, "picky")

    error = _refused(capsys, "-f", flow, "-a", ",".join(agents), *BUDGET, "task")

    assert complaint in error


@pytest.mark.parametrize(
    "spec",
    [
        "builder=claude/claude-opus-4-8",
        "builder=claude",
        "builder=gemini/g:high",
        "builder=/m:high",
        "builder=claude/:high",
        "claude/m:high",
        "builder=",
        "builder=claude/m:high,builder=claude/m:low",
    ],
)
def test_an_agent_that_is_not_a_role_a_cli_a_model_and_an_effort_is_a_usage_error(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    error = _refused(capsys, "-f", _flow(tmp_path), "-a", spec, *BUDGET, "task")

    assert "-a" in error
    assert not (tmp_path / "flows" / "record" / "seen.json").exists()


@pytest.mark.parametrize("effort", ["auto", ""])
def test_an_agent_at_no_effort_is_named_with_auto_and_runs(
    tmp_path: Path, here: Path, effort: str
) -> None:
    """`auto` is the word for the CLI's own default, and a spec without one says the same."""
    main(
        [
            "exec",
            "-f",
            _flow(tmp_path),
            "-a",
            f"builder=claude/m:{effort}",
            *BUDGET,
            "task",
        ]
    )

    assert _seen(tmp_path)["agents"]["builder"] == ["claude", "", "m", ""]


def test_a_flow_that_is_not_there_is_a_usage_error(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _refused(
        capsys, "-f", str(tmp_path / "nowhere"), "-a", BUILDER, *BUDGET, "task"
    )

    assert "nowhere" in error


def test_a_directory_that_holds_no_flow_is_a_usage_error(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    error = _refused(
        capsys,
        "-f",
        _flow(tmp_path, "HELD = 1\n", "empty"),
        "-a",
        BUILDER,
        *BUDGET,
        "task",
    )

    assert "defines no flow" in error


def test_a_flow_fails_as_it_would_anywhere_when_it_is_the_flow_that_failed(
    tmp_path: Path, here: Path
) -> None:
    """A flow whose own import cannot find a file has not been mistyped on the command line."""
    flow = _flow(tmp_path, RECORD.replace("import json\n", "open('nowhere.md')\n", 1))

    with pytest.raises(SystemExit) as stopped:
        main(["exec", "-f", flow, "-a", BUILDER, *BUDGET, "task"])
    # Refused with the reason the import gave, before any agent started.
    assert stopped.value.code == 2

    failing = _flow(
        tmp_path,
        RECORD.replace(
            "    Path(__file__)",
            "    raise FileNotFoundError(task)\n    Path(__file__)",
        ),
        "failing",
    )
    with pytest.raises(FileNotFoundError, match="task"):
        main(["exec", "-f", failing, "-a", BUILDER, *BUDGET, "task"])
    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert ran.how == "failed"


def test_resume_picks_up_the_newest_run_and_only_of_a_flow_that_can_be(
    tmp_path: Path, here: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    keeps = _flow(tmp_path, KEEPS, "keeps")

    assert "no run here to pick up" in _refused(
        capsys, "-f", keeps, *BUDGET, "--resume", "task"
    )
    main(["exec", "-f", keeps, *BUDGET, "task"])
    main(["exec", "-f", keeps, *BUDGET, "--resume", "task"])
    main(["exec", "-f", keeps, *BUDGET, "task"])

    assert capsys.readouterr().out.split("\n")[:3] == ["run 1", "run 2", "run 1"]
    assert "does not say it can be picked up" in _refused(
        capsys, "-f", _flow(tmp_path), "-a", BUILDER, *BUDGET, "--resume", "task"
    )


def test_python_m_hmz_is_the_hmz_command(
    tmp_path: Path, here: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _flow(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["hmz", "exec", "-f", flow, "-a", BUILDER, *BUDGET, "task"]
    )

    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("hmz", run_name="__main__")

    assert stopped.value.code == 0
    assert _seen(tmp_path)["task"] == "task"


def test_every_example_runs_as_the_command_line_it_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each flow humanize ships shows an `hmz exec` line, and it is one that would start it."""
    shipped = sorted(
        path / ENTRY
        for path in BUILTIN_AT.iterdir()
        if not path.name.startswith("_") and (path / ENTRY).is_file()
    )
    assert shipped
    ran: list[str] = []

    def nothing(self: Run) -> None:
        """Every line is checked as far as the flow, and no further."""
        ran.append(self.flow)

    monkeypatch.setattr(Run, "run", nothing)
    monkeypatch.chdir(Path(__file__).resolve().parents[3])
    for flow in shipped:
        shown = re.search(r"^\s*hmz exec (?:.*\\\n)*.*", flow.read_text(), re.MULTILINE)
        assert shown is not None, f"{flow}: no `hmz exec` command line to be checked"
        assert main(shlex.split(shown[0].replace("\\\n", " "))[1:]) == 0
    assert len(ran) == len(shipped)


def test_a_flow_of_your_own_is_found_where_flows_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest wins: this project, then yours, then the ones humanize came with.

    A flow written down beside the traces is one humanize knows about without being told
    where it is -- and one taking a built-in's name stands in for it, which is what makes
    a project able to mean its own `chat` by `chat`.

    What each of them is *called* is another question, and the answer is the one every place
    gets: `<where it came from>/<flow>`, which for these two places is `local` and `user`. So
    one of yours sharing a name with one of humanize's is listed beside it under a name of its
    own rather than instead of it.
    """
    from hmz.runtime.flowing import find, found

    home, project = tmp_path / "home", tmp_path / "project"
    for where in (home / ".humanize/flows", project / ".humanize/flows"):
        where.mkdir(parents=True)
    written(home / ".humanize/flows", "yours", RECORD)
    written(project / ".humanize/flows", "theirs", RECORD)
    written(project / ".humanize/flows", "chat", RECORD)  # a name humanize uses
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    named = [(one.whose, one.name) for one in found()]

    assert ("local", "local/theirs") in named
    assert ("user", "user/yours") in named
    # Both, under names of their own: one is not offered as if it were the other.
    assert ("local", "local/chat") in named
    assert ("official", "chat") in named
    # `-f` still takes a bare name, and the nearest flow answering to it is what runs.
    assert find("chat") == str((project / ".humanize/flows/chat" / ENTRY).resolve())
    assert find("yours") == str((home / ".humanize/flows/yours" / ENTRY).resolve())
    # And a flow of humanize's own said outright is not one the project can stand in for.
    assert find("official/chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())
    assert find("user/yours") == str((home / ".humanize/flows/yours" / ENTRY).resolve())
    assert find("local/chat") == str(
        (project / ".humanize/flows/chat" / ENTRY).resolve()
    )
    # A path is still a path, `~` and all: a flow being written lives wherever it is.
    assert find("~/.humanize/flows/yours") == str(
        (home / ".humanize/flows/yours" / ENTRY).resolve()
    )
    assert find("nowhere") == "nowhere"  # a path is taken as given


def test_a_flow_of_your_own_runs_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of finding it: `-f theirs` starts it, with no path said anywhere."""
    project = tmp_path / "project"
    written(project / ".humanize/flows", "theirs", RECORD)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)

    assert main(["exec", "-f", "theirs", "-a", BUILDER, *BUDGET, "do it"]) == 0

    seen = json.loads((project / ".humanize/flows/theirs/seen.json").read_text())
    assert seen["task"] == "do it"


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` on PATH, with a home of its own; its log."""
    log = standins.install(tmp_path / "bin", "claude", standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    return log


def test_chat_runs_with_no_budget_and_does_the_one_thing_it_was_given(
    here: Path, claude: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nobody is at a prompt on a command line, so there is no next thing to wait for."""
    assert (
        main(
            [
                "exec",
                "-f",
                "chat",
                "-a",
                "assistant=claude/claude-haiku-4-5:low",
                "Reply with the single word: hello",
            ]
        )
        == 0
    )

    # What the turn answered is on stdout, for a script reading it.
    assert "hello" in capsys.readouterr().out
    said = [
        json.loads(line) for line in claude.read_text().splitlines() if "said" in line
    ]
    assert [one["said"] for one in said] == ["Reply with the single word: hello"]
    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    assert ran.budget is not None
    assert ran.budget["cost"] == "Infinity"
