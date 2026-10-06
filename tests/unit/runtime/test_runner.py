"""What starts a flow: the `hmz exec` line, the checks before a run, and the run written down."""

from __future__ import annotations

import asyncio
import datetime
import json
import math
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

import pydantic
import pytest

from hmz.coganchor import prices, providers
from hmz.flows import (
    Budget,
    BudgetExceeded,
    EnvError,
    FlowCancelled,
    FlowNotFound,
    HarnessKind,
    ParamsError,
    RequirementError,
    Usage,
)
from hmz.runtime import epic, flowing
from hmz.runtime.flowing import environments, harnesses
from hmz.runtime.flowing import specs as flowing_specs
from hmz.runtime.flowing.specs import AgentSpec, EnvSpec
from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES
from hmz.runtime.runner import Line, Refused, Runner, read_line

if TYPE_CHECKING:
    from collections.abc import Callable


# ------------------------------------------------------------------ the line


def test_a_whole_line_is_read() -> None:
    line = read_line(
        [
            "-f",
            "ralph",
            "-a",
            "builder=claude/opus:high,reviewer=codex@me/o3",
            "-e",
            "box=local/srv",
            "-p",
            "rounds=3,budget.cost=5",
            "--params",
            "budget.duration=1h",
            "--profile",
            "--resume",
            "--json",
            "--",
            "-do it",
        ]
    )

    assert line.flow == "ralph"
    assert line.task == "-do it"
    assert [str(one) for one in line.agents] == [
        "builder=claude/opus:high",
        "reviewer=codex@me/o3:auto",
    ]
    assert line.envs == (
        EnvSpec("box", line.envs[0].backend, "", PurePosixPath("/srv")),
    )
    assert line.params == {"rounds": "3"}
    assert line.budget == Budget(cost=5.0, duration=datetime.timedelta(hours=1))
    assert (line.profile, line.resume, line.as_json) == (True, True, True)


def test_a_bare_line_is_a_flow_and_a_task() -> None:
    line = read_line(["--flow", "chat", "hello"])

    assert line == Line("chat", "hello")
    assert line.agents == line.envs == ()
    assert line.params == {}
    assert line.budget is None
    assert (line.profile, line.resume, line.as_json) == (False, False, False)


def test_repeated_flags_add_up_in_order() -> None:
    line = read_line(
        [
            "-f",
            "x",
            "-a",
            "b=claude/opus",
            "--agents",
            "c=codex/o3",
            "-e",
            "d=local/a",
            "t",
        ]
    )

    assert [one.role for one in line.agents] == ["b", "c"]
    assert [one.role for one in line.envs] == ["d"]


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (["task"], "the following arguments are required: -f/--flow"),
        (["-f", "x"], "the following arguments are required: task"),
        (["-f", "x", "--nope", "t"], "unrecognized arguments: --nope"),
        (["-f", "x", "-a", "builder", "t"], "-a 'builder'"),
        (["-f", "x", "-a", "b=claude/opus,b=codex/o3", "t"], "given twice"),
        (["-f", "x", "-a", "b=claude/opus,", "t"], "expected one agent"),
        (["-f", "x", "-e", "", "t"], "an item is empty"),
        (["-f", "x", "-e", "box", "t"], "-e 'box'"),
        (["-f", "x", "-e", "box=local@/srv", "t"], "local takes no provider"),
        (["-f", "x", "-e", "box=nowhere/srv", "t"], "is not a backend"),
        (["-f", "x", "-e", "1box=local/srv", "t"], "is not an identifier"),
        (["-f", "x", "-e", "box=ssh/srv", "t"], "ssh needs a host"),
        (["-f", "x", "-p", "rounds", "t"], "-p"),
        (["-f", "x", "-p", "budget.nope=1", "t"], "not a limit"),
        (["-f", "x", "-p", "budget.cost=lots", "t"], "budget.cost"),
        (["-f", "x", "-p", "budget.output_tokens=1.5", "t"], "budget.output_tokens"),
        (["-f", "x", "-p", "budget.graceful=perhaps", "t"], "true or false"),
    ],
)
def test_a_line_that_is_not_one_exits_saying_why(
    argv: list[str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        read_line(argv)

    assert exited.value.code == 2
    assert says in capsys.readouterr().err


def test_help_loads_no_flow(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        read_line(["--help"])

    assert exited.value.code == 0
    assert "hmz exec" in capsys.readouterr().out


# ------------------------------------------------------------------ the flow


@dataclass(frozen=True)
class Permission:
    local: str = "read"
    user: str = "none"
    system: str = "none"
    online: str = "none"


@dataclass(frozen=True)
class AgentRole:
    name: str
    required: bool = True
    auto: bool = False
    harness: object = None
    capabilities: frozenset[type] = frozenset()
    permission: Permission = Permission()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnvRole:
    name: str
    required: bool = True
    auto: bool = False
    resources: bool = False


@dataclass
class Declaration:
    agents: tuple[AgentRole, ...] = ()
    envs: tuple[EnvRole, ...] = ()

    def agent(self, name: str) -> AgentRole | None:
        return next((one for one in self.agents if one.name == name), None)

    def env(self, name: str) -> EnvRole | None:
        return next((one for one in self.envs if one.name == name), None)


class Params(pydantic.BaseModel):
    rounds: int = 1


@dataclass
class Impl:
    """A flow, loaded, as far as a runner reads one."""

    declared: Declaration
    ref: str = "official/ralph"
    resumable: bool = False
    refuses_params: bool = False

    def describe(self) -> Declaration:
        return self.declared

    def params_of(self, given: object) -> Params:
        if self.refuses_params:
            raise ParamsError("rounds: not a number")
        if isinstance(given, Params):
            return given
        return Params.model_validate(given)


#: A capability a claude agent has, which the flow's builder needs.
CAPABLE = min(HARNESS_CAPABILITIES[HarnessKind.CLAUDE], key=lambda one: one.__name__)


@dataclass
class Agent:
    """An agent driver, as far as a runner reads one."""

    harness: str = "claude"
    model: str = "opus"
    effort: str = "high"
    provider: str = ""
    capabilities: frozenset[type] = frozenset({CAPABLE})
    closed: int = 0
    watched: list[object] = field(default_factory=list[object])

    async def close(self) -> None:
        self.closed += 1

    def watch(self, listener: object) -> None:
        self.watched.append(listener)


@dataclass
class Env:
    """An environment driver, as far as a runner reads one."""

    backend: str = "local"
    provider: str = ""
    workdir: str = "/srv"
    closed: int = 0
    refuses: bool = False

    async def close(self) -> None:
        self.closed += 1
        if self.refuses:
            raise RuntimeError("would not close")

    def placement(self) -> str:
        return f"{self.backend}:{self.workdir}"


@dataclass
class Flowing:
    """Everything a runner asks of the engine and its drivers, answered here."""

    impl: Impl
    privileged: bool = False
    refuses: BaseException | None = None
    opened_agents: list[AgentSpec] = field(default_factory=list[AgentSpec])
    opened_envs: list[EnvSpec] = field(default_factory=list[EnvSpec])
    env_refuses: BaseException | None = None
    agent_refuses: BaseException | None = None
    local: Env = field(default_factory=Env)
    ran: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    flow: Callable[[dict[str, Any]], Any] | None = None
    probed: list[object] = field(default_factory=list[object])
    readied: int = 0
    refreshed: int = 0
    priced: dict[str, object] = field(default_factory=dict[str, object])
    found: dict[tuple[str, str], object] = field(
        default_factory=dict[tuple[str, str], object]
    )
    settled: list[EnvSpec] = field(default_factory=list[EnvSpec])

    def resolved(self, named: str) -> Impl:
        if self.refuses is not None:
            raise self.refuses
        self.named = named
        return self.impl

    def open_agent(self, spec: AgentSpec, harbors: object) -> Agent:
        if self.agent_refuses is not None:
            raise self.agent_refuses
        self.opened_agents.append(spec)
        return Agent(str(spec.harness), spec.model, spec.effort, spec.provider)

    def open_env(self, spec: EnvSpec, role: object) -> Env:
        if self.env_refuses is not None:
            raise self.env_refuses
        self.opened_envs.append(spec)
        return Env(str(spec.backend), spec.provider, str(spec.workdir))

    async def run_flow(self, impl: Impl, task: str, **said: Any) -> Any:
        said["task"] = task
        self.ran.append(said)
        if self.flow is None:
            return "returned"
        return self.flow(said)

    def is_privileged(self, impl: Impl) -> bool:
        return self.privileged

    def local_env(self, at: Path) -> Env:
        return self.local

    def find(self, cli: str, name: str) -> object:
        return self.found.get((cli, name))

    async def probe(self, driver: object) -> None:
        self.probed.append(driver)

    async def settle(
        self, spec: EnvSpec, driver: object, role: object, **_: Any
    ) -> tuple[EnvSpec, object]:
        self.settled.append(spec)
        return spec, driver


@pytest.fixture
def declared() -> Declaration:
    return Declaration(
        agents=(
            AgentRole("builder", capabilities=frozenset({CAPABLE})),
            AgentRole("reviewer", required=False),
            AgentRole("outworlder", auto=True),
        ),
        envs=(EnvRole("box", required=False), EnvRole("local", auto=True)),
    )


@pytest.fixture
def engine_(declared: Declaration, monkeypatch: pytest.MonkeyPatch) -> Flowing:
    made = Flowing(Impl(declared))
    monkeypatch.setattr(flowing, "resolved", made.resolved, raising=False)
    monkeypatch.setattr(flowing, "privileged", made.is_privileged, raising=False)
    monkeypatch.setattr(flowing, "run_flow", made.run_flow, raising=False)
    monkeypatch.setattr(flowing, "probe", made.probe, raising=False)
    monkeypatch.setattr(flowing, "local_env", made.local_env, raising=False)
    monkeypatch.setattr(flowing, "open_outworlder", lambda: "nobody", raising=False)
    monkeypatch.setattr(harnesses, "open_agent", made.open_agent)
    monkeypatch.setattr(environments, "open_env", made.open_env)
    monkeypatch.setattr(environments, "settle", made.settle)
    monkeypatch.setattr(flowing_specs, "fallbacks", _nowhere)
    monkeypatch.setattr(providers, "find", made.find)
    monkeypatch.setattr(prices, "price", made.priced.get)

    def ready(*, stopped: object = None) -> bool:
        made.readied += 1
        return True

    def refresh(*, wait: bool = False) -> bool:
        made.refreshed += 1
        return True

    monkeypatch.setattr(prices, "ready", ready)
    monkeypatch.setattr(prices, "refresh", refresh)
    return made


BUDGET = {"cost": 5.0}


def _nowhere(spec: EnvSpec) -> list[EnvSpec]:
    return []


def _onwards(spec: EnvSpec) -> list[EnvSpec]:
    return [spec]


def _runner(**said: Any) -> Runner:
    given: dict[str, Any] = {"agents": {"builder": Agent()}, "budget": BUDGET, **said}
    return Runner("ralph", **given)


def test_a_flow_given_what_it_needs_is_loaded_and_nothing_starts(
    engine_: Flowing, tmp_path: Path
) -> None:
    builder = Agent()
    runner = Runner(
        "ralph",
        agents=cast("Any", {"builder": builder}),
        params={"rounds": "4"},
        budget=BUDGET,
        profile=True,
        workspace=tmp_path,
    )

    assert runner.flow == "ralph"
    assert runner.impl is engine_.impl
    assert runner.declaration is engine_.impl.declared
    assert runner.agents == {"builder": builder}
    assert runner.envs == {}
    assert runner.used == {}
    assert runner.params == Params(rounds=4)
    assert runner.budget == Budget(cost=5.0)
    assert runner.profile is True
    assert runner.picked_up is None
    assert runner.workspace == tmp_path
    assert runner.recorder is None
    assert builder.closed == 0


def test_the_workspace_is_this_directory_unless_named(
    engine_: Flowing, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _runner().workspace == tmp_path


def test_a_flow_named_by_a_path_is_named_as_one(engine_: Flowing) -> None:
    runner = Runner(
        Path("flows/mine.py"), agents=cast("Any", {"builder": Agent()}), budget=BUDGET
    )

    assert runner.flow == "./flows/mine.py"
    assert engine_.named == "./flows/mine.py"


def test_a_flow_that_cannot_be_loaded_is_refused(engine_: Flowing) -> None:
    engine_.refuses = FlowNotFound("no flow called ralph")

    with pytest.raises(Refused, match="no flow called ralph") as refused:
        _runner()
    assert isinstance(refused.value.__cause__, FlowNotFound)


def test_specs_are_opened_as_drivers_and_spelled_as_given(engine_: Flowing) -> None:
    runner = _runner(
        agents={"builder": "claude/opus:high", "reviewer": "codex/o3"},
        envs={"box": "local/srv"},
    )

    assert [str(one) for one in engine_.opened_agents] == [
        "builder=claude/opus:high",
        "reviewer=codex/o3:auto",
    ]
    assert [str(one) for one in engine_.opened_envs] == ["box=local/srv"]
    assert set(runner.agents) == {"builder", "reviewer"}
    assert runner.used == {"box": "local/srv"}


def test_specs_a_line_read_are_taken_as_they_are(engine_: Flowing) -> None:
    line = read_line(
        ["-f", "ralph", "-a", "builder=claude/opus", "-e", "box=local/a", "t"]
    )

    runner = _runner(agents=line.agents, envs=line.envs)

    assert engine_.opened_agents == list(line.agents)
    assert runner.used == {"box": "local/a"}


def test_a_driver_given_for_an_environment_is_spelled_as_dash_e_spells_it(
    engine_: Flowing,
) -> None:
    box = Env("local", "", "/x")

    runner = _runner(envs={"box": box})

    assert runner.envs == {"box": box}
    assert runner.used == {"box": "local/x"}


@pytest.mark.parametrize(
    ("agents", "says"),
    [
        (
            {"builder": Agent(), "nobody": Agent()},
            "has no agent role 'nobody'; available roles are 'builder', 'reviewer'",
        ),
        (
            {"builder": Agent(), "outworlder": Agent()},
            "'outworlder' is assigned automatically",
        ),
        ({"builder": "claude"}, "-a 'builder=claude'"),
        (
            {"builder": Agent(capabilities=frozenset())},
            f"'builder' needs {CAPABLE.__name__}, which claude does not support",
        ),
        ({"reviewer": Agent()}, "needs an agent for 'builder'"),
        ({}, "needs an agent for 'builder'; specify each with -a"),
    ],
)
def test_agents_the_flow_cannot_take_are_refused(
    agents: dict[str, object], says: str, engine_: Flowing
) -> None:
    with pytest.raises(Refused, match=__import__("re").escape(says)):
        _runner(agents=agents)


def test_an_agent_role_given_twice_is_refused(engine_: Flowing) -> None:
    spec = AgentSpec("builder", HarnessKind.CLAUDE, "", "opus", "high", "claude")

    with pytest.raises(Refused, match="duplicate agent role 'builder'"):
        _runner(agents=[spec, spec])


def test_a_role_held_to_one_harness_refuses_another(
    engine_: Flowing, declared: Declaration
) -> None:
    engine_.impl.declared = Declaration(agents=(AgentRole("builder", harness="codex"),))

    with pytest.raises(Refused, match="'builder' requires codex, but got claude"):
        _runner()


def test_an_account_nobody_made_is_refused_before_anything_runs(
    engine_: Flowing,
) -> None:
    with pytest.raises(Refused, match="names no claude account called 'work'"):
        _runner(agents={"builder": "claude@work/opus"})

    engine_.found["claude", "work"] = object()
    assert set(_runner(agents={"builder": "claude@work/opus"}).agents) == {"builder"}


@pytest.mark.parametrize(
    ("envs", "says"),
    [
        (
            {"nowhere": "local/x"},
            "has no environment role 'nowhere'; available roles are 'box'",
        ),
        ({"local": "local/x"}, "'local' is the workspace the run started in"),
        ({"box": "local@/x"}, "local takes no provider"),
    ],
)
def test_environments_the_flow_cannot_take_are_refused(
    envs: dict[str, object], says: str, engine_: Flowing
) -> None:
    with pytest.raises(Refused, match=__import__("re").escape(says)):
        _runner(envs=envs)


def test_an_environment_role_given_twice_is_refused(engine_: Flowing) -> None:
    (spec,) = read_line(["-f", "x", "-e", "box=local/a", "t"]).envs

    with pytest.raises(Refused, match="duplicate environment role 'box'"):
        _runner(envs=[spec, spec])


def test_a_required_environment_left_out_is_refused(engine_: Flowing) -> None:
    engine_.impl.declared = Declaration(
        agents=engine_.impl.declared.agents, envs=(EnvRole("box"), EnvRole("spare"))
    )

    with pytest.raises(Refused, match="needs an environment for 'box', 'spare'"):
        _runner()


def test_params_the_flow_does_not_take_are_refused(engine_: Flowing) -> None:
    engine_.impl.refuses_params = True

    with pytest.raises(Refused, match="rounds: not a number"):
        _runner()


def test_params_left_out_are_the_flows_defaults(engine_: Flowing) -> None:
    assert _runner().params == Params()
    assert _runner(params=Params(rounds=7)).params == Params(rounds=7)


def test_a_run_with_no_budget_is_refused_unless_it_is_chat(engine_: Flowing) -> None:
    with pytest.raises(Refused, match="requires a budget"):
        _runner(budget=None)

    engine_.privileged = True
    assert _runner(budget=None).budget == Budget(cost=math.inf)


def test_a_budget_is_read_off_json_or_refused(engine_: Flowing) -> None:
    assert _runner(budget={"output_tokens": 10}).budget == Budget(output_tokens=10)
    assert _runner(budget=Budget(cost=1.0)).budget == Budget(cost=1.0)

    with pytest.raises(Refused, match="the budget is invalid"):
        _runner(budget={"cost": -1})


def test_a_driver_that_cannot_be_made_is_refused(engine_: Flowing) -> None:
    engine_.agent_refuses = RequirementError("claude is not configured")

    with pytest.raises(Refused, match="claude is not configured"):
        _runner(agents={"builder": "claude/opus"})


def test_an_environment_that_cannot_be_opened_is_refused_where_nothing_falls_back(
    engine_: Flowing, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_.env_refuses = EnvError("no such workdir")

    with pytest.raises(Refused, match="no such workdir"):
        _runner(envs={"box": "local/x"})

    monkeypatch.setattr(flowing_specs, "fallbacks", _onwards)
    runner = _runner(envs={"box": "local/x"})
    assert runner.envs == {}
    assert runner.used == {"box": "local/x"}


def test_any_other_refusal_opening_an_environment_is_refused(engine_: Flowing) -> None:
    engine_.env_refuses = RequirementError("not that kind")

    with pytest.raises(Refused, match="not that kind"):
        _runner(envs={"box": "local/x"})


# ------------------------------------------------------------------ picking up


def _picked_up(at: Path) -> Path:
    at.mkdir(parents=True, exist_ok=True)
    (at / epic.RESUME).write_text(
        json.dumps({"t": "call", "id": 1, "parent": 0}) + "\n"
    )
    return at


def test_a_flow_that_cannot_be_picked_up_is_not(engine_: Flowing) -> None:
    with pytest.raises(Refused, match="does not support resuming"):
        _runner(resume=True)


def test_resuming_with_nothing_to_resume_is_refused(
    engine_: Flowing, tmp_path: Path
) -> None:
    engine_.impl.resumable = True

    with pytest.raises(Refused, match="has no run to resume here"):
        _runner(resume=True, workspace=tmp_path)
    with pytest.raises(Refused, match="has no saved progress"):
        _runner(resume=tmp_path / "empty")


def test_a_run_is_picked_up_from_the_epic_named_or_the_newest(
    engine_: Flowing, tmp_path: Path
) -> None:
    engine_.impl.resumable = True
    named = _picked_up(tmp_path / "named")

    assert _runner(resume=named).picked_up == named
    assert _runner(resume=str(named)).picked_up == named

    with epic.Epic("ralph", "t", tmp_path, ref="official/ralph", resumable=True) as one:
        _picked_up(one.path)
    assert _runner(resume=True, workspace=tmp_path).picked_up == one.path


# ------------------------------------------------------------------ prices


def test_a_cap_nothing_prices_is_said_before_the_first_turn(engine_: Flowing) -> None:
    runner = _runner(agents={"builder": Agent(model="mystery")})

    said = runner.unreadable()

    assert (
        said == "nobody lists a price for mystery, so cost=5 cannot stop what it spends"
    )
    assert engine_.readied == 1
    # Asked once a run, whichever way it was started.
    runner.unreadable()
    assert engine_.readied == 1
    assert engine_.refreshed == 0


def test_a_cap_over_priced_models_is_readable(engine_: Flowing) -> None:
    engine_.priced["opus"] = object()

    assert _runner().unreadable() == ""


def test_a_run_with_no_cost_cap_fetches_prices_without_waiting(
    engine_: Flowing,
) -> None:
    runner = _runner(budget={"output_tokens": 5})

    assert runner.unreadable() == ""
    assert (engine_.readied, engine_.refreshed) == (0, 1)


def test_every_session_is_watched_through_each_driver_that_can_be(
    engine_: Flowing,
) -> None:
    builder, reviewer = Agent(), Agent()
    runner = _runner(agents={"builder": builder, "reviewer": reviewer})

    runner.watch(print)

    assert builder.watched == [print]
    assert reviewer.watched == [print]


# ------------------------------------------------------------------ running


def _ran(runner: Runner) -> dict[str, Any]:
    ran = epic.read(epic.epics(runner.workspace)[-1])
    assert ran is not None
    return ran._asdict()


def test_a_run_is_written_down_and_returns_what_the_flow_did(
    engine_: Flowing, tmp_path: Path
) -> None:
    builder = Agent()
    runner = Runner(
        "ralph",
        agents=cast("Any", {"builder": builder}),
        envs={"box": "local/srv"},
        params={"rounds": 2},
        budget=BUDGET,
        workspace=tmp_path,
    )
    started: list[epic.Epic] = []

    returned = asyncio.run(runner.arun("fix it", started=started.append))

    assert returned == "returned"
    (said,) = engine_.ran
    assert said["task"] == "fix it"
    assert said["agents"] == {"builder": builder}
    assert said["outworlder"] == "nobody"
    assert said["journal"] is None
    assert said["resume"] is False
    assert said["local"] is engine_.local
    assert said["recorder"] is runner.recorder
    assert [str(one) for one in engine_.settled] == ["box=local/srv"]
    assert engine_.probed == []
    ran = _ran(runner)
    assert started[0].path == ran["at"]
    assert (ran["flow"], ran["task"], ran["ref"], ran["how"]) == (
        "ralph",
        "fix it",
        "official/ralph",
        "done",
    )
    assert ran["agents"] == (epic.Drove("builder", "claude", "opus", "high"),)
    assert ran["envs"] == ("box=local/srv",)
    assert ran["params"] == {"rounds": 2}
    assert ran["budget"]["cost"] == 5.0
    usage = [
        json.loads(one)
        for one in (ran["at"] / epic.JOURNAL).read_text().splitlines()
        if '"usage"' in one
    ]
    assert usage[0]["cost"] == 0.0
    # Every driver goes once the run does, the workspace's among them.
    assert builder.closed == 1
    assert engine_.local.closed == 1
    assert all(cast("Env", one).closed == 1 for one in runner.envs.values())


def test_an_environment_given_as_a_driver_is_probed_where_it_stands(
    engine_: Flowing, tmp_path: Path
) -> None:
    box = Env("local", "", "/x")
    runner = _runner(envs={"box": box}, workspace=tmp_path)

    runner.run("t")

    assert engine_.probed == [box]
    assert engine_.settled == []
    assert runner.envs == {"box": box}


@dataclass(eq=False)
class Live:
    ref: str
    depth: int = 0
    parent: Live | None = None
    since: float = 0.0


def test_a_report_made_during_a_run_says_what_was_running_and_on_what(
    engine_: Flowing, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime import telemetry

    top = Live("official/ralph")
    calls = (top, Live("official/inner", 1, top))
    monkeypatch.setattr(flowing, "running", lambda: calls, raising=False)
    held: list[Any] = []
    engine_.flow = lambda said: held.append(telemetry.held()["flow"])

    _runner(agents={"builder": Agent(provider="work")}, workspace=tmp_path).run(
        "secret task"
    )

    (said,) = held
    assert said["flow"] == "official/ralph"
    assert said["calls"] == 2
    assert [(one["flow"], one["deep"], one["under"]) for one in said["running"]] == [
        ("official/ralph", 0, ""),
        ("official/inner", 1, "official/ralph"),
    ]
    assert said["agents"] == [
        {
            "flow": "official/ralph",
            "called": "builder",
            "cli": "claude",
            "model": "opus",
            "effort": "high",
            "account": "work",
            "may": "local=read user=none system=none online=none",
            "skills": [],
        }
    ]
    assert "secret task" not in json.dumps(said)
    # Once the run is over it is no longer one that was running.
    assert cast("dict[str, Any]", telemetry.held()["flow"])["agents"] == []


def test_a_run_of_chat_writes_down_a_cost_that_reads_back(
    engine_: Flowing, tmp_path: Path
) -> None:
    engine_.privileged = True
    runner = Runner(
        "chat", agents=cast("Any", {"builder": Agent()}), workspace=tmp_path
    )

    runner.run("hello")

    assert _ran(runner)["budget"]["cost"] == "Infinity"


def test_a_resumable_flow_keeps_its_journal_in_the_epic(
    engine_: Flowing, tmp_path: Path
) -> None:
    engine_.impl.resumable = True
    picked = _picked_up(tmp_path / "before")
    runner = _runner(resume=picked, workspace=tmp_path, profile=False)

    runner.run("again")

    said = engine_.ran[0]
    assert said["journal"] == _ran(runner)["at"] / epic.RESUME
    assert said["resume"] is True
    assert _ran(runner)["picked_up"] == "before"


def test_the_engine_refusing_before_the_flow_was_called_is_a_refusal(
    engine_: Flowing, tmp_path: Path
) -> None:
    def refuses(said: dict[str, Any]) -> Any:
        raise RequirementError("builder cannot write")

    engine_.flow = refuses
    builder = Agent()

    with pytest.raises(Refused, match="builder cannot write"):
        _runner(agents={"builder": builder}, workspace=tmp_path).run("t")
    assert builder.closed == 1


def test_the_engine_refusing_once_the_flow_was_called_is_raised_as_it_was(
    engine_: Flowing, tmp_path: Path
) -> None:
    def refuses(said: dict[str, Any]) -> Any:
        said["recorder"].entered(Call())
        raise RequirementError("later")

    engine_.flow = refuses

    with pytest.raises(RequirementError, match="later"):
        _runner(workspace=tmp_path).run("t")


@pytest.mark.parametrize("why", [FlowCancelled("stop"), BudgetExceeded("spent")])
def test_a_run_stopped_or_out_of_budget_ends_stopped(
    why: BaseException, engine_: Flowing, tmp_path: Path
) -> None:
    def stops(said: dict[str, Any]) -> Any:
        raise why

    engine_.flow = stops
    runner = _runner(workspace=tmp_path)

    with pytest.raises(type(why)):
        runner.run("t")
    assert _ran(runner)["how"] == "stopped"


def test_a_flow_that_failed_ends_failed(engine_: Flowing, tmp_path: Path) -> None:
    def fails(said: dict[str, Any]) -> Any:
        raise ValueError("bug")

    engine_.flow = fails
    runner = _runner(workspace=tmp_path)

    with pytest.raises(ValueError, match="bug"):
        runner.run("t")
    assert _ran(runner)["how"] == "failed"


def test_an_environment_that_cannot_be_reached_refuses_the_run_and_closes_everything(
    engine_: Flowing, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def settle(spec: object, driver: object, role: object, **_: Any) -> Any:
        raise EnvError("box is down")

    monkeypatch.setattr(environments, "settle", settle)
    builder = Agent()
    runner = _runner(
        agents={"builder": builder}, envs={"box": "local/x"}, workspace=tmp_path
    )

    with pytest.raises(Refused, match="box is down"):
        runner.run("t")
    assert engine_.ran == []
    assert builder.closed == 1
    assert epic.epics(tmp_path) == []


def test_an_environment_moved_down_its_fallback_list_is_where_the_run_says_it_ran(
    engine_: Flowing, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    moved = Env("docker", "", "/y")
    notices: list[str] = []

    async def settle(
        spec: EnvSpec, driver: object, role: object, *, fits: Any, moved: Any
    ) -> tuple[EnvSpec, Env]:
        moved("box moved to docker")
        return EnvSpec(
            spec.role, cast("Any", "docker"), "", PurePosixPath("/y")
        ), moved_to

    moved_to = moved
    monkeypatch.setattr(environments, "settle", settle)
    runner = _runner(envs={"box": "local/x"}, workspace=tmp_path)

    asyncio.run(runner.arun("t", noticed=notices.append))

    assert notices == ["box moved to docker"]
    assert runner.envs == {"box": moved}
    assert runner.used == {"box": "docker/y"}
    ran = _ran(runner)
    assert ran["envs"] == ("box=local/x",)
    assert ran["used"] == ("box=docker/y",)


def test_a_driver_that_will_not_close_does_not_stop_the_rest(
    engine_: Flowing, tmp_path: Path
) -> None:
    builder = Agent()
    box = Env(refuses=True)
    runner = _runner(agents={"builder": builder}, envs={"box": box}, workspace=tmp_path)

    asyncio.run(runner.aclose())

    assert box.closed == 1
    assert builder.closed == 1


# ------------------------------------------------------------------ what writes it down


@dataclass(eq=False)
class Call:
    parent: Call | None = None
    ref: str = "official/inner"
    task: str = "a part"
    resumable: bool = False


@dataclass(eq=False)
class Handle:
    id: str | None = None
    agent: object = None
    coganchor: object = None
    placement: object = None


@dataclass
class Named:
    """A coganchor agent, as far as what writes a run down reads one."""

    renamed: list[str] = field(default_factory=list[str])
    epic: object = None

    def rename(self, role: str) -> None:
        self.renamed.append(role)


def _events(at: Path) -> list[dict[str, Any]]:
    return [json.loads(one) for one in at.read_text().splitlines()]


def _recording(
    engine_: Flowing,
    tmp_path: Path,
    does: Callable[[Any], None],
    opened: Callable[..., None] | None = None,
) -> tuple[Runner, epic.Epic]:
    """Runs a flow that does to what writes the run down what `does` does, as an engine would."""
    started: list[epic.Epic] = []

    def flow(said: dict[str, Any]) -> None:
        does(said["recorder"])

    engine_.flow = flow
    runner = _runner(workspace=tmp_path)
    asyncio.run(runner.arun("t", started=started.append, opened=opened))
    return runner, started[0]


def _called(written: epic.Epic) -> dict[str, Any]:
    return next(one for one in _events(written.journal) if one["event"] == "called")


def test_a_flow_called_inside_the_run_is_written_in_a_record_of_its_own(
    engine_: Flowing, tmp_path: Path
) -> None:
    top, inner = Call(), Call()
    inner.parent = top
    seen: list[bool] = []

    def does(recorder: Any) -> None:
        seen.append(recorder.started)
        recorder.entered(top)
        seen.append(recorder.started)
        recorder.entered(inner)
        recorder.left(inner, None)
        recorder.left(top, None)

    _, written = _recording(engine_, tmp_path, does)

    assert seen == [False, True]
    called = _called(written)
    assert (called["flow"], called["task"]) == ("official/inner", "a part")
    assert _events(written.path / called["epic"])[-1]["how"] == "done"


@pytest.mark.parametrize(
    ("raised", "how"),
    [
        (RuntimeError("x"), "failed"),
        (FlowCancelled("x"), "stopped"),
        (BudgetExceeded("x"), "stopped"),
        (asyncio.CancelledError(), "stopped"),
    ],
)
def test_a_called_flow_ends_saying_how(
    raised: BaseException, how: str, engine_: Flowing, tmp_path: Path
) -> None:
    top, inner = Call(), Call()
    inner.parent = top

    def does(recorder: Any) -> None:
        recorder.entered(top)
        recorder.entered(inner)
        recorder.left(inner, raised)
        recorder.left(top, raised)

    _, written = _recording(engine_, tmp_path, does)

    assert _events(written.path / _called(written)["epic"])[-1]["how"] == how


def test_a_session_of_a_driver_with_no_agent_is_written_down_once_it_is_named(
    engine_: Flowing, tmp_path: Path
) -> None:
    top = Call()
    driver = Agent(harness="fake", provider="me")
    unnamed, named = Handle(), Handle(id="s2")
    held: list[tuple[Any, ...]] = []

    def does(recorder: Any) -> None:
        recorder.entered(top)
        recorder.spawned(top, "builder", unnamed, driver)
        recorder.spawned(top, "builder", named, driver)
        unnamed.id = "s1"
        recorder.named(top, "builder", unnamed, driver)
        held.append(recorder.sessions)
        recorder.closed(unnamed)
        held.append(recorder.sessions)

    runner, written = _recording(engine_, tmp_path, does)

    opened = [one for one in _events(written.journal) if one["event"] == "opened"]
    assert [(one["session"], one["backend"], one["provider"]) for one in opened] == [
        ("s2", "fake", "me"),
        ("s1", "fake", "me"),
    ]
    assert held == [(unnamed, named), (named,)]
    assert runner.recorder is not None
    assert runner.recorder.sessions == (named,)


def test_a_session_with_an_agent_behind_it_is_named_for_its_role(
    engine_: Flowing, tmp_path: Path
) -> None:
    told: list[tuple[object, ...]] = []

    def tells(*said: object) -> None:
        told.append(said)

    top = Call()
    agent, conversation = Named(), object()
    handle = Handle(id="s1", agent=agent, coganchor=conversation, placement="here")

    def does(recorder: Any) -> None:
        recorder.entered(top)
        recorder.spawned(top, "builder", handle, Agent())
        recorder.named(top, "builder", handle, Agent())

    _, written = _recording(engine_, tmp_path, does, tells)

    assert agent.renamed == ["builder"]
    assert isinstance(agent.epic, epic.Epic)
    assert agent.epic.path == written.path
    assert told == [("builder", agent, conversation, "here")]
    # The agent writes its own session down; the run does not write it twice.
    assert [one for one in _events(written.journal) if one["event"] == "opened"] == []


def test_what_a_run_spent_is_the_engines_reckoning_kept_when_it_ends(
    engine_: Flowing, tmp_path: Path
) -> None:
    spent = [Usage(cost=1.5, output_tokens=7)]
    before: list[Usage] = []

    def does(recorder: Any) -> None:
        before.append(recorder.usage())
        recorder.began(lambda: spent[0])
        before.append(recorder.usage())

    runner, written = _recording(engine_, tmp_path, does)
    spent[0] = Usage(cost=9.0)

    assert before == [Usage(), Usage(cost=1.5, output_tokens=7)]
    assert runner.recorder is not None
    assert runner.recorder.usage() == Usage(cost=1.5, output_tokens=7)
    (usage,) = [one for one in _events(written.journal) if one["event"] == "usage"]
    assert (usage["cost"], usage["output_tokens"], usage["seconds"]) == (1.5, 7, 0.0)
