"""The flow engine: defining, loading and running flows over the package's own fakes."""

from __future__ import annotations

import asyncio
import datetime
import math
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import atomic
from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    CapabilityMissing,
    ClaudeCodeAgent,
    CostExceeded,
    CPUEnvMixin,
    DurationExceeded,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowDefinitionError,
    FlowDepthExceeded,
    FlowParams,
    FlowRuntimeError,
    GoalCommandAgentMixin,
    HarnessKind,
    HarnessMismatch,
    MissingRole,
    Outworlder,
    ParamsError,
    RequirementError,
    ResourceUnmet,
    flow,
    load,
)
from hmz.runtime.flowing import loading
from hmz.runtime.flowing.engine import (
    DEPTH,
    Call,
    FlowImpl,
    LiveCall,
    current,
    define_flow,
    full_view,
    load_flow,
    new_outworlder,
    run_flow,
    running,
)
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    run_fake,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

UNLIMITED = Budget(cost=math.inf)


class Nothing(FlowParams):
    pass


class Rounds(FlowParams):
    rounds: int = 1
    tags: list[str] = []  # noqa: RUF012 -- pydantic copies a default


class Solo(AgentCollection):
    coder: Agent


class Goal(Agent, GoalCommandAgentMixin): ...


class WantsGoal(AgentCollection):
    coder: Goal


class WantsClaude(AgentCollection):
    coder: ClaudeCodeAgent


class WithPerson(AgentCollection):
    person: Outworlder


class NoEnvs(EnvCollection):
    pass


class Files(Env, FilesEnvMixin): ...


class Big(Env, CPUEnvMixin):
    _cpu_count = 64


class WantsFiles(EnvCollection):
    repo: Files


class WantsBig(EnvCollection):
    box: Big


async def ask(agent: Agent, prompt: str) -> str:
    session = await agent.spawn()
    return await agent.run(prompt, session=session)


@flow(agents=Solo, envs=NoEnvs, params=Nothing)
async def echo(
    task: str, *, agents: Solo, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> str:
    """Asks its coder the task, once."""
    del envs, params, ctx
    return await ask(agents["coder"], task)


@flow(agents=Solo, envs=NoEnvs, params=Nothing)
async def twice(
    task: str, *, agents: Solo, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> list[str]:
    del envs, params, ctx
    return [await ask(agents["coder"], task), await ask(agents["coder"], task)]


@flow(agents=AgentCollection, envs=NoEnvs, params=Rounds)
async def counts(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Rounds,
    ctx: FlowContext,
) -> tuple[int, list[str]]:
    del task, agents, envs, ctx
    return params.rounds, params.tags


@flow(agents=WantsGoal, envs=NoEnvs, params=Nothing)
async def wants_goal(
    task: str, *, agents: WantsGoal, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=WantsClaude, envs=NoEnvs, params=Nothing)
async def wants_claude(
    task: str, *, agents: WantsClaude, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=AgentCollection, envs=WantsFiles, params=Nothing)
async def reads(
    task: str,
    *,
    agents: AgentCollection,
    envs: WantsFiles,
    params: Nothing,
    ctx: FlowContext,
) -> bytes:
    del agents, params, ctx
    return await envs["repo"].read(task)


@flow(agents=AgentCollection, envs=WantsBig, params=Nothing)
async def big(
    task: str,
    *,
    agents: AgentCollection,
    envs: WantsBig,
    params: Nothing,
    ctx: FlowContext,
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=WithPerson, envs=NoEnvs, params=Nothing)
async def asks_person(
    task: str, *, agents: WithPerson, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> tuple[bool, str | None]:
    del envs, params, ctx
    person = agents["person"]
    if person.away:
        return True, None
    return False, await ask(person, task)


@flow(agents=Solo, envs=NoEnvs, params=Nothing)
async def parent(
    task: str, *, agents: Solo, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> dict[str, Any]:
    del envs, params
    inner = await load(":child")(
        f"inner {task}", agents=agents, envs={}, params=Nothing()
    )
    return {
        "inner": inner,
        "depth": current() is ctx and isinstance(ctx, Call),
        "usage": ctx.usage.cost,
    }


@flow(agents=Solo, envs=NoEnvs, params=Nothing)
async def child(
    task: str, *, agents: Solo, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> list[str]:
    del envs, params, ctx
    return [await ask(agents["coder"], task), *(one.ref for one in running())]


@flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
async def deep(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Nothing,
    ctx: FlowContext,
) -> None:
    del ctx
    await load(":deep")(task, agents=agents, envs=envs, params=params)


@flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
async def waits(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Nothing,
    ctx: FlowContext,
) -> None:
    del task, agents, envs, params, ctx
    await asyncio.Event().wait()


@flow(agents=AgentCollection, envs=NoEnvs, params=Nothing, resumable=True)
async def keeps(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Nothing,
    ctx: FlowContext,
) -> tuple[bool, int]:
    del agents, envs, params
    state = ctx.state
    assert state is not None
    was = ctx.resumed
    state["n"] = state["n"] + 1 if was else 1
    if task == "fail":
        raise RuntimeError("stopped partway")
    return was, state["n"]


@flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
async def stateless(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Nothing,
    ctx: FlowContext,
) -> object:
    del task, agents, envs, params
    return ctx.state


# --------------------------------------------------------------------------- running


async def test_a_run_hands_the_flow_its_agents_and_returns_what_it_did() -> None:
    coder = FakeAgentDriver(reply="done")
    assert isinstance(echo, FlowImpl)
    said = await run_flow(
        echo, "fix it", agents={"coder": coder}, envs={}, params={}, budget=UNLIMITED
    )
    assert said == "done"
    assert coder.prompts == ["fix it"]
    assert coder.live == 0
    assert running() == ()
    assert current() is None


async def test_a_flow_reads_what_its_environment_holds() -> None:
    repo = FakeEnvDriver({"README.md": "hi"})
    assert await run_fake(reads, "README.md", envs={"repo": repo}) == b"hi"


PARAMS: list[tuple[object, tuple[int, list[str]]]] = [
    ({}, (1, [])),
    ({"rounds": "3"}, (3, [])),
    ({"rounds": 2, "tags": '["a", "b"]'}, (2, ["a", "b"])),
    (Rounds(rounds=5), (5, [])),
    (Nothing(), (1, [])),
]


@pytest.mark.parametrize(("params", "expected"), PARAMS)
async def test_params_are_read_from_what_a_command_line_gives(
    params: Any, expected: tuple[int, list[str]]
) -> None:
    said = await run_flow(
        counts, "", agents={}, envs={}, params=params, budget=UNLIMITED
    )
    assert said == expected


@pytest.mark.parametrize("params", [{"rounds": "many"}, {"tags": "not json"}, [1, 2]])
async def test_params_that_do_not_validate_are_refused(params: Any) -> None:
    with pytest.raises(ParamsError):
        await run_flow(counts, "", agents={}, envs={}, params=params, budget=UNLIMITED)


@pytest.mark.parametrize(
    ("run", "raised", "says"),
    [
        (
            lambda: run_fake(echo, agents={"coder": "x", "other": "y"}),
            RequirementError,
            "declares no agent role 'other'",
        ),
        (
            lambda: run_flow(echo, "", agents={}, envs={}, params={}, budget=UNLIMITED),
            MissingRole,
            "no agent was given for 'coder'",
        ),
        (
            lambda: run_flow(
                asks_person,
                "",
                agents={"person": FakeAgentDriver()},
                envs={},
                params={},
                budget=UNLIMITED,
            ),
            RequirementError,
            "filled by the runtime",
        ),
        (
            lambda: run_fake(
                wants_goal, agents={"coder": FakeAgentDriver(capabilities=())}
            ),
            CapabilityMissing,
            "GoalCommandAgentMixin",
        ),
        (
            lambda: run_fake(
                wants_claude, agents={"coder": FakeAgentDriver(HarnessKind.CODEX)}
            ),
            HarnessMismatch,
            "requires claude",
        ),
        (
            lambda: run_fake(reads, envs={"repo": FakeEnvDriver(capabilities=())}),
            CapabilityMissing,
            "FilesEnvMixin",
        ),
        (
            lambda: run_fake(reads, envs={"nowhere": {}}),
            RequirementError,
            "declares no environment role",
        ),
        (
            lambda: run_fake(big, envs={"box": FakeEnvDriver(cpu_count=8)}),
            ResourceUnmet,
            "needs 64 CPUs",
        ),
    ],
)
async def test_a_run_that_does_not_meet_the_declaration_never_starts(
    run: Any, raised: type[Exception], says: str
) -> None:
    with pytest.raises(raised, match=says):
        await run()
    assert running() == ()


async def test_run_flow_refuses_what_is_not_a_flow_or_a_budget() -> None:
    with pytest.raises(TypeError, match="not a flow the engine made"):
        await run_flow(object(), "", agents={}, envs={}, params={}, budget=UNLIMITED)  # pyright: ignore[reportArgumentType]
    with pytest.raises(TypeError, match="is not a Budget"):
        await run_flow(counts, "", agents={}, envs={}, params={}, budget={"cost": 1})  # pyright: ignore[reportArgumentType]


async def test_the_runs_outworlder_fills_an_outworlder_role() -> None:
    person = FakeOutworlder(reply="sure")
    assert await run_fake(asks_person, "ok?", outworlder=person) == (False, "sure")
    assert person.asked == ["ok?"]
    assert await run_fake(asks_person, "ok?") == (True, None)


# ----------------------------------------------------------------------- flow calls


def shout(prompt: str, **_: object) -> str:
    return prompt.upper()


async def test_a_flow_calls_a_flow_beside_it() -> None:
    coder = FakeAgentDriver(reply=shout)
    said = await run_fake(parent, "go", agents={"coder": coder})
    module = __name__
    assert said == {
        "inner": ["INNER GO", f"{module}:parent", f"{module}:child"],
        "depth": True,
        "usage": 0.0,
    }


async def test_a_flow_called_outside_a_run_is_refused() -> None:
    with pytest.raises(FlowRuntimeError, match="from inside a run"):
        await echo("x", agents={}, envs={}, params=Nothing())


async def test_flows_called_too_deep_are_refused() -> None:
    with pytest.raises(FlowDepthExceeded, match=f"{DEPTH} is the most"):
        await run_fake(deep)


async def test_a_recorder_hears_every_call() -> None:
    heard: list[tuple[str, str, int, str | None]] = []

    class Hears:
        def entered(self, call: LiveCall) -> None:
            heard.append(("in", call.name, call.depth, None))

        def left(self, call: LiveCall, error: BaseException | None) -> None:
            heard.append(
                ("out", call.name, call.depth, type(error).__name__ if error else None)
            )

    await run_fake(parent, "go", recorder=Hears())  # pyright: ignore[reportArgumentType]
    assert heard == [
        ("in", "parent", 1, None),
        ("in", "child", 2, None),
        ("out", "child", 2, None),
        ("out", "parent", 1, None),
    ]


# -------------------------------------------------------------------------- budgets


async def test_spending_past_a_hard_budget_stops_the_turn() -> None:
    coder = FakeAgentDriver(reply="ok", cost=1.0)
    with pytest.raises(CostExceeded):
        await run_fake(
            twice, agents={"coder": coder}, budget=Budget(cost=1.5, graceful=False)
        )
    assert len(coder.prompts) == 2


async def test_a_budget_with_room_lets_every_turn_spend() -> None:
    coder = FakeAgentDriver(reply="ok", cost=1.0)
    said = await run_fake(twice, agents={"coder": coder}, budget=Budget(cost=2.0))
    assert said == ["ok", "ok"]


async def test_a_duration_budget_is_a_deadline() -> None:
    with pytest.raises(DurationExceeded):
        await run_fake(
            waits, budget=Budget(duration=datetime.timedelta(milliseconds=1))
        )


# ---------------------------------------------------------------------------- state


@pytest.fixture
def plain_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    def writes(at: Path, said: Iterable[bytes]) -> None:
        at.write_bytes(b"".join(said))

    monkeypatch.setattr(atomic, "writes", writes)


@pytest.mark.usefixtures("plain_writes")
async def test_a_resumed_run_picks_up_the_state_it_left(tmp_path: Path) -> None:
    journal = tmp_path / "run.jsonl"
    with pytest.raises(RuntimeError, match="partway"):
        await run_fake(keeps, "fail", journal=journal)
    assert await run_fake(keeps, "go", journal=journal, resume=True) == (True, 2)
    assert await run_fake(keeps, "go", journal=journal) == (False, 1)


async def test_a_resumable_flow_without_a_journal_keeps_state_in_memory() -> None:
    assert await run_fake(keeps, "go") == (False, 1)


async def test_a_flow_that_is_not_resumable_has_no_state() -> None:
    assert await run_fake(stateless) is None


# ------------------------------------------------------------------- definition


def test_a_flow_says_what_it_declares() -> None:
    assert isinstance(echo, FlowImpl)
    said = echo.describe()
    assert (said.name, said.ref, said.description) == (
        "echo",
        f"{__name__}:echo",
        "Asks its coder the task, once.",
    )
    assert [one.name for one in said.agents] == ["coder"]
    assert said.envs == ()
    assert said.params is Nothing
    assert (echo.expected_agents, echo.expected_envs, echo.expected_params) == (
        Solo,
        NoEnvs,
        Nothing,
    )
    assert repr(echo) == f"<flow {__name__}:echo>"


def test_define_flow_refuses_what_is_not_a_flow() -> None:
    def sync(task: str, *, agents: Any, envs: Any, params: Any, ctx: Any) -> None:
        del task, agents, envs, params, ctx

    with pytest.raises(FlowDefinitionError, match="async def"):
        define_flow(
            sync,  # pyright: ignore[reportArgumentType]
            agents=AgentCollection,
            envs=EnvCollection,
            params=Nothing,
            name=None,
            description=None,
            hidden=False,
            resumable=False,
            caller_globals={},
            caller_locals={},
        )


def test_full_view_takes_only_a_flow_the_engine_made() -> None:
    assert isinstance(stateless, FlowImpl)
    assert full_view(stateless) is stateless
    with pytest.raises(TypeError, match="not a flow the engine made"):
        full_view(object())  # pyright: ignore[reportArgumentType]


async def test_load_flow_is_looked_up_once_inside_a_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []
    asked: list[str] = []
    loads = loading.load

    def counted(ref: str, caller_globals: Mapping[str, Any]) -> object:
        asked.append(ref)
        return loads(ref, caller_globals)

    monkeypatch.setattr(loading, "load", counted)

    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def looks(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> None:
        del task, agents, envs, params, ctx
        asking = globals()
        seen.extend(
            [
                load_flow(":echo", caller_globals=asking),
                load_flow(":echo", caller_globals=asking),
            ]
        )

    await run_fake(looks)
    assert seen == [echo, echo]
    assert asked == [":echo"]
    assert load_flow(":echo", caller_globals=globals()) is echo
    assert asked == [":echo", ":echo"]


def test_a_flows_own_outworlder_is_away_until_a_hook_answers() -> None:
    made = new_outworlder()
    assert made.away is True
    assert made.role == ""
