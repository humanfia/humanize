"""One flow calling another: what is checked, what is handed on, and what comes back.

A call refuses what does not meet the callee's declaration before the callee runs -- and says
which of the `RequirementError` leaves it was -- fills what the runtime fills, validates the
params, and then awaits the callee directly: no task, two frames, and whatever the callee
raises reaching the caller as it was raised.
"""

from __future__ import annotations

import asyncio
import itertools
import sys
from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    Budget,
    CapabilityMissing,
    ClaudeCodeAgent,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowCancelled,
    FlowContext,
    FlowDepthExceeded,
    FlowParams,
    FlowRuntimeError,
    GoalCommandAgentMixin,
    HarnessKind,
    HarnessMismatch,
    LocalEnv,
    MissingRole,
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    ParamsError,
    Permission,
    PermissionKind,
    PermissionTooNarrow,
    RequirementError,
    ResourceUnmet,
    ShellEnvMixin,
    flow,
    load,
)
from hmz.runtime.flowing.engine import LiveCall, run_flow, running
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    run_fake,
)

if TYPE_CHECKING:
    from hmz.runtime.flowing.spi import AgentDriver, SessionHandle


class Nothing(FlowParams):
    pass


class Solo(AgentCollection):
    agent: Agent


class NoEnvs(EnvCollection):
    pass


class Place(EnvCollection):
    env: Env


# ------------------------------------------------------------------------- narrowing


class Goal(Agent, GoalCommandAgentMixin): ...


class Wants(AgentCollection):
    agent: Goal


class Online(Agent):
    _permission = Permission(online=PermissionKind.ALL)


class WantsOnline(AgentCollection):
    agent: Online


class WantsClaude(AgentCollection):
    agent: ClaudeCodeAgent


class Files(Env, FilesEnvMixin): ...


class WantsFiles(EnvCollection):
    env: Files


class Big(Env, CPUEnvMixin):
    _cpu_count = 64


class WantsBig(EnvCollection):
    env: Big


@flow(agents=Wants, envs=NoEnvs, params=Nothing)
async def wants_goal(
    task: str, *, agents: Wants, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=WantsOnline, envs=NoEnvs, params=Nothing)
async def wants_online(
    task: str, *, agents: WantsOnline, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=WantsClaude, envs=NoEnvs, params=Nothing)
async def wants_claude(
    task: str, *, agents: WantsClaude, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=AgentCollection, envs=WantsFiles, params=Nothing)
async def wants_files(
    task: str,
    *,
    agents: AgentCollection,
    envs: WantsFiles,
    params: Nothing,
    ctx: FlowContext,
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=AgentCollection, envs=WantsBig, params=Nothing)
async def wants_big(
    task: str,
    *,
    agents: AgentCollection,
    envs: WantsBig,
    params: Nothing,
    ctx: FlowContext,
) -> None:
    del task, agents, envs, params, ctx


@flow(agents=Solo, envs=Place, params=Nothing)
async def calling(
    task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
) -> None:
    """Calls the flow its task names with its own agent and env, and nothing else."""
    callee: Any = load(task)
    await callee(
        "go",
        agents={"agent": agents["agent"]},
        envs={"env": envs["env"]},
        params=Nothing(),
    )


@pytest.mark.parametrize(
    ("callee", "raised"),
    [
        (":wants_goal", CapabilityMissing),
        (":wants_online", PermissionTooNarrow),
        (":wants_claude", HarnessMismatch),
        (":wants_files", CapabilityMissing),
        (":wants_big", ResourceUnmet),
    ],
)
async def test_a_callee_refuses_what_is_narrower_than_it_declared(
    callee: str, raised: type[RequirementError]
) -> None:
    with pytest.raises(raised) as caught:
        await run_fake(
            calling,
            callee,
            agents={"agent": FakeAgentDriver(HarnessKind.CODEX)},
            envs={"env": FakeEnvDriver(cpu_count=4)},
        )
    assert isinstance(caught.value, RequirementError)


async def test_a_refusal_is_remembered_and_said_the_same_again() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def twice(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> list[str]:
        said: list[str] = []
        for _ in range(2):
            try:
                await wants_goal(
                    "x", agents={"agent": agents["agent"]}, envs={}, params=Nothing()
                )
            except CapabilityMissing as error:
                said.append(str(error))
        return said

    first, second = await run_fake(twice)
    assert first == second
    assert "GoalCommandAgentMixin" in first


async def test_a_required_role_left_out_is_missing() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def leaving_out(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        with pytest.raises(MissingRole):
            await calling(task, agents={}, envs={"env": envs["env"]}, params=Nothing())
        with pytest.raises(MissingRole):
            await calling(
                task, agents={"agent": agents["agent"]}, envs={}, params=Nothing()
            )

    await run_fake(leaving_out)


async def test_what_is_not_the_run_s_own_agent_or_env_is_refused() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def smuggling(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        with pytest.raises(RequirementError):
            await calling(":x", agents={"agent": object()}, envs=envs, params=Nothing())  # pyright: ignore[reportArgumentType]
        with pytest.raises(RequirementError):
            await calling(":x", agents=agents, envs={"env": "/tmp"}, params=Nothing())  # pyright: ignore[reportArgumentType]

    await run_fake(smuggling)


async def test_a_callee_gets_exactly_what_it_declared() -> None:
    class Plain(AgentCollection):
        agent: Agent

    @flow(agents=Plain, envs=NoEnvs, params=Nothing)
    async def narrowed(
        task: str, *, agents: Plain, envs: NoEnvs, params: Nothing, ctx: FlowContext
    ) -> Any:
        return agents["agent"]

    @flow(agents=WantsClaude, envs=NoEnvs, params=Nothing)
    async def wide(
        task: str,
        *,
        agents: WantsClaude,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> tuple[Any, Any]:
        agent = agents["agent"]
        passed = await narrowed(
            task, agents={"agent": agent, "extra": agent}, envs={}, params=Nothing()
        )
        return agent, passed

    wide_view, narrow_view = await run_fake(wide)
    assert narrow_view is not wide_view
    assert narrow_view.driver is wide_view.driver
    assert narrow_view.grant.capabilities == frozenset()
    assert wide_view.grant.capabilities == HARNESS_CAPABILITIES_CLAUDE
    assert narrow_view.role == "agent"


HARNESS_CAPABILITIES_CLAUDE = __import__(
    "hmz.runtime.flowing.spi", fromlist=["HARNESS_CAPABILITIES"]
).HARNESS_CAPABILITIES[HarnessKind.CLAUDE]


# ------------------------------------------------------------------------- auto roles


class WithHuman(AgentCollection):
    human: Outworlder


class Answer(pydantic.BaseModel):
    ok: bool = True


@flow(agents=WithHuman, envs=NoEnvs, params=Nothing)
async def asking(
    task: str, *, agents: WithHuman, envs: NoEnvs, params: Nothing, ctx: FlowContext
) -> Any:
    human = agents["human"]
    session = await human.spawn(env=_nowhere(ctx))
    return await human.run(task, session=session)


def _nowhere(ctx: Any) -> Any:
    """An environment view, which a session of an outworlder is opened in for form's sake."""
    from hmz.runtime.flowing.viewing import EnvView

    return EnvView(FakeEnvDriver(), _GRANT, ctx, "nowhere", "fake@/nowhere")


_GRANT = __import__("hmz.runtime.flowing.declaring", fromlist=["Grant"]).Grant(
    frozenset()
)


def _plain(ctx: Any) -> Any:
    """An environment view granted nothing."""
    return _nowhere(ctx)


async def test_an_outworlder_role_is_the_run_s_own_when_left_out() -> None:
    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def outer(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> Any:
        return await asking(task, agents={}, envs={}, params=Nothing())

    person = FakeOutworlder(reply="yes")
    assert await run_fake(outer, "may I?", outworlder=person) == "yes"
    assert person.asked == ["may I?"]


async def test_an_outworlder_made_by_the_caller_wins() -> None:
    heard: list[Any] = []

    async def answering(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
        heard.append((params.prompt, params.ctx))
        return OutworlderRunHookResult(output="as you like")

    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def outer(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> Any:
        stand_in = Outworlder.new()
        away = await asking(task, agents={"human": stand_in}, envs={}, params=Nothing())
        stand_in.on_outworlder_run(answering)
        said = await asking(task, agents={"human": stand_in}, envs={}, params=Nothing())
        return away, said, ctx

    person = FakeOutworlder(reply="the person")
    away, said, ctx = await run_fake(outer, "may I?", outworlder=person)
    assert (away, said) == ("", "as you like")
    assert heard == [("may I?", ctx)]
    assert person.asked == []


async def test_an_outworlder_role_cannot_be_given_a_driver() -> None:
    with pytest.raises(RequirementError, match="filled by the runtime"):
        await run_flow(
            asking,
            "x",
            agents={"human": FakeAgentDriver()},
            envs={},
            params={},
            budget=Budget(cost=1),
        )


async def test_an_agent_is_no_outworlder_and_an_outworlder_no_agent_with_mixins() -> (
    None
):
    @flow(agents=Solo, envs=NoEnvs, params=Nothing)
    async def swapping(
        task: str, *, agents: Solo, envs: NoEnvs, params: Nothing, ctx: FlowContext
    ) -> Any:
        with pytest.raises(CapabilityMissing):
            await asking(
                task, agents={"human": agents["agent"]}, envs={}, params=Nothing()
            )
        with pytest.raises(CapabilityMissing):
            await wants_goal(
                task, agents={"agent": Outworlder.new()}, envs={}, params=Nothing()
            )
        stand_in = Outworlder.new()

        class Plain(AgentCollection):
            agent: Agent

        @flow(agents=Plain, envs=NoEnvs, params=Nothing)
        async def plain(
            task: str, *, agents: Plain, envs: NoEnvs, params: Nothing, ctx: FlowContext
        ) -> Any:
            return agents["agent"]

        return await plain(task, agents={"agent": stand_in}, envs={}, params=Nothing())

    filled = await run_fake(swapping, agents={"agent": FakeAgentDriver()})
    assert filled.role == "agent"
    assert filled.away


class HereEnvs(EnvCollection):
    here: LocalEnv


class HereShell(LocalEnv, ShellEnvMixin): ...


class HereShellEnvs(EnvCollection):
    here: HereShell


async def test_a_local_role_is_the_run_s_workspace_unless_one_is_passed() -> None:
    @flow(agents=AgentCollection, envs=HereShellEnvs, params=Nothing)
    async def inner(
        task: str,
        *,
        agents: AgentCollection,
        envs: HereShellEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> str:
        return str(envs["here"].workdir)

    class Shell(Env, ShellEnvMixin): ...

    class ShellPlace(EnvCollection):
        env: Shell

    @flow(agents=AgentCollection, envs=ShellPlace, params=Nothing)
    async def outer(
        task: str,
        *,
        agents: AgentCollection,
        envs: ShellPlace,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[str]:
        with pytest.raises(CapabilityMissing):
            await inner(task, agents={}, envs={"here": _plain(ctx)}, params=Nothing())
        left_out = await inner(task, agents={}, envs={}, params=Nothing())
        passed = await inner(
            task, agents={}, envs={"here": envs["env"]}, params=Nothing()
        )
        return [left_out, passed]

    said = await run_fake(
        outer,
        envs={"env": FakeEnvDriver(workdir="/elsewhere")},
        local=FakeEnvDriver(workdir="/home/me/project"),
    )
    assert said == ["/home/me/project", "/elsewhere"]


@pytest.mark.parametrize("declared", [HereEnvs, HereShellEnvs])
async def test_a_local_role_refuses_an_environment_on_another_machine(
    declared: type[EnvCollection],
) -> None:
    """A `LocalEnv` is this machine: one on an ssh host is refused, down either path."""

    @flow(agents=AgentCollection, envs=declared, params=Nothing)
    async def inner(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: Nothing,
        ctx: FlowContext,
    ) -> str:
        return str(envs["here"].workdir)

    class Shell(Env, ShellEnvMixin): ...

    class Two(EnvCollection):
        remote: Shell
        local: Shell

    @flow(agents=AgentCollection, envs=Two, params=Nothing)
    async def outer(
        task: str,
        *,
        agents: AgentCollection,
        envs: Two,
        params: Nothing,
        ctx: FlowContext,
    ) -> str:
        for _ in range(2):  # the second time a grant is met is the fast path's
            with pytest.raises(CapabilityMissing, match="not this machine"):
                await inner(
                    task, agents={}, envs={"here": envs["remote"]}, params=Nothing()
                )
        return await inner(
            task, agents={}, envs={"here": envs["local"]}, params=Nothing()
        )

    said = await run_fake(
        outer,
        envs={
            "remote": FakeEnvDriver(workdir="/far", backend="ssh", provider="box"),
            "local": FakeEnvDriver(workdir="/near"),
        },
    )
    assert said == "/near"


async def test_a_local_role_cannot_be_given_a_driver() -> None:
    @flow(agents=AgentCollection, envs=HereEnvs, params=Nothing)
    async def here(
        task: str,
        *,
        agents: AgentCollection,
        envs: HereEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> None:
        del task, agents, envs, params, ctx

    with pytest.raises(RequirementError, match="filled by the runtime"):
        await run_flow(
            here,
            "x",
            agents={},
            envs={"here": FakeEnvDriver()},
            params={},
            budget=Budget(cost=1),
            local=FakeEnvDriver(),
        )


async def test_a_local_env_short_of_what_a_role_needs_is_refused() -> None:
    @flow(agents=AgentCollection, envs=HereShellEnvs, params=Nothing)
    async def here(
        task: str,
        *,
        agents: AgentCollection,
        envs: HereShellEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> None:
        del task, agents, envs, params, ctx

    with pytest.raises(CapabilityMissing):
        await run_fake(here, local=FakeEnvDriver(capabilities=()))


# ------------------------------------------------------------------ the top of a run


async def test_run_flow_refuses_before_anything_runs() -> None:
    ran: list[str] = []

    @flow(agents=Wants, envs=Place, params=Nothing)
    async def checked(
        task: str, *, agents: Wants, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        ran.append(task)

    budget = Budget(cost=1)
    env = FakeEnvDriver()
    for agents, envs, raised in [
        ({}, {"env": env}, MissingRole),
        ({"agent": FakeAgentDriver()}, {}, MissingRole),
        (
            {"agent": FakeAgentDriver(HarnessKind.CURSOR_AGENT)},
            {"env": env},
            CapabilityMissing,
        ),
        (
            {"agent": FakeAgentDriver(), "extra": FakeAgentDriver()},
            {"env": env},
            RequirementError,
        ),
        ({"agent": FakeAgentDriver()}, {"env": env, "extra": env}, RequirementError),
    ]:
        with pytest.raises(raised):
            await run_flow(
                checked, "x", agents=agents, envs=envs, params={}, budget=budget
            )
    with pytest.raises(HarnessMismatch):
        await run_flow(
            wants_claude,
            "x",
            agents={"agent": FakeAgentDriver(HarnessKind.CODEX)},
            envs={},
            params={},
            budget=budget,
        )
    with pytest.raises(CapabilityMissing):
        await run_flow(
            wants_files,
            "x",
            agents={},
            envs={"env": FakeEnvDriver(capabilities=())},
            params={},
            budget=budget,
        )
    with pytest.raises(ResourceUnmet):
        await run_flow(
            wants_big,
            "x",
            agents={},
            envs={"env": FakeEnvDriver(cpu_count=2)},
            params={},
            budget=budget,
        )
    with pytest.raises(TypeError):
        await run_flow(
            checked,
            "x",
            agents={},
            envs={},
            params={},
            budget=None,  # pyright: ignore[reportArgumentType]
        )
    with pytest.raises(TypeError):
        await run_flow(object(), "x", agents={}, envs={}, params={}, budget=budget)  # pyright: ignore[reportArgumentType]
    assert ran == []


async def test_a_flow_called_outside_a_run_says_so() -> None:
    with pytest.raises(FlowRuntimeError, match="run_flow"):
        await wants_goal("x", agents={}, envs={}, params=Nothing())


async def test_a_full_view_flow_is_handed_everything_its_harness_does() -> None:
    from hmz.runtime.flowing.engine import full_view

    class Plain(AgentCollection):
        agent: Agent

    @flow(agents=Plain, envs=NoEnvs, params=Nothing)
    async def chat(
        task: str, *, agents: Plain, envs: NoEnvs, params: Nothing, ctx: FlowContext
    ) -> Any:
        return agents["agent"]

    full_view(chat)
    agent = await run_fake(chat, agents={"agent": FakeAgentDriver(HarnessKind.KIMI)})
    assert agent.grant.capabilities == FakeAgentDriver(HarnessKind.KIMI).capabilities


# --------------------------------------------------------------------------- params


class Numbers(FlowParams):
    rounds: int = 1
    tags: list[str] = pydantic.Field(default_factory=list[str])
    ratio: float = 0.5


class Sub(Numbers):
    extra: str = ""


class Foreign(pydantic.BaseModel):
    rounds: int = 7


class Unknown(FlowParams):
    unknown: int = 1


@flow(agents=AgentCollection, envs=NoEnvs, params=Numbers)
async def numbers(
    task: str,
    *,
    agents: AgentCollection,
    envs: NoEnvs,
    params: Numbers,
    ctx: FlowContext,
) -> Numbers:
    return params


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ({}, Numbers()),
        ({"rounds": "3"}, Numbers(rounds=3)),
        ({"rounds": 3, "ratio": "0.25"}, Numbers(rounds=3, ratio=0.25)),
        ({"tags": '["a", "b"]'}, Numbers(tags=["a", "b"])),
        ({"tags": ["a"]}, Numbers(tags=["a"])),
        (Numbers(rounds=4), Numbers(rounds=4)),
        (Foreign(), Numbers(rounds=7)),
    ],
    ids=str,
)
async def test_params_are_validated_from_whatever_they_were_given_as(
    given: Any, expected: Numbers
) -> None:
    assert await run_fake(numbers, params=given) == expected


async def test_a_subclass_of_the_params_is_the_params() -> None:
    given = Sub(rounds=2, extra="x")
    assert await run_fake(numbers, params=given) is given


@pytest.mark.parametrize(
    "given",
    [{"rounds": "many"}, {"nope": 1}, {"tags": "a,b"}, 3, "rounds=3"],
    ids=str,
)
async def test_params_that_do_not_validate_are_refused(given: Any) -> None:
    with pytest.raises(ParamsError):
        await run_fake(numbers, params=given)


async def test_a_callee_validates_what_a_caller_hands_it() -> None:
    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def caller(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[Any]:
        said: list[Any] = [
            await numbers(task, agents={}, envs={}, params={"rounds": 2}),  # pyright: ignore[reportArgumentType]
            await numbers(task, agents={}, envs={}, params=Foreign()),  # pyright: ignore[reportArgumentType]
        ]
        assert await numbers(task, agents={}, envs={}, params=params) == Numbers()
        with pytest.raises(ParamsError):
            await numbers(task, agents={}, envs={}, params=Unknown())
        with pytest.raises(TypeError):
            await numbers(task, agents={}, envs={}, params=Numbers(), budget="1")  # pyright: ignore[reportArgumentType]
        return said

    assert await run_fake(caller) == [Numbers(rounds=2), Numbers(rounds=7)]


# ------------------------------------------------------------------ depth and errors


class Depth(FlowParams):
    left: int = 0


@flow(agents=AgentCollection, envs=NoEnvs, params=Depth)
async def deep(
    task: str, *, agents: AgentCollection, envs: NoEnvs, params: Depth, ctx: FlowContext
) -> int:
    if params.left == 0:
        return 1
    return 1 + await deep(
        task, agents=agents, envs=envs, params=Depth(left=params.left - 1)
    )


@flow(agents=AgentCollection, envs=NoEnvs, params=Depth)
async def forever(
    task: str, *, agents: AgentCollection, envs: NoEnvs, params: Depth, ctx: FlowContext
) -> int:
    return await forever(task, agents=agents, envs=envs, params=params)


async def test_flows_may_call_flows_sixty_four_deep() -> None:
    assert await run_fake(deep, params={"left": 63}) == 64


async def test_flows_called_deeper_raise_flow_depth_exceeded_not_recursion_error() -> (
    None
):
    with pytest.raises(FlowDepthExceeded) as raised:
        await run_fake(forever)
    assert isinstance(raised.value, RecursionError)
    assert "64" in str(raised.value)


async def test_the_depth_limit_holds_under_a_low_recursion_limit() -> None:
    was = sys.getrecursionlimit()
    sys.setrecursionlimit(max(was, 400))
    try:
        with pytest.raises(FlowDepthExceeded):
            await run_fake(forever)
    finally:
        sys.setrecursionlimit(was)


class BoomError(Exception):
    pass


@flow(agents=AgentCollection, envs=NoEnvs, params=Depth)
async def boom(
    task: str, *, agents: AgentCollection, envs: NoEnvs, params: Depth, ctx: FlowContext
) -> None:
    if params.left:
        await boom(task, agents=agents, envs=envs, params=Depth(left=params.left - 1))
    raise BoomError(task)


async def test_a_callee_s_exception_reaches_the_caller_as_it_was_raised() -> None:
    with pytest.raises(BoomError) as raised:
        await run_fake(boom, "deep", params={"left": 5})
    assert raised.value.args == ("deep",)
    assert type(raised.value) is BoomError


async def test_exceptions_leave_gathers_and_task_groups_unwrapped() -> None:
    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def gathering(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[str]:
        seen: list[str] = []
        try:
            await asyncio.gather(
                deep(task, agents={}, envs={}, params=Depth(left=2)),
                boom(task, agents={}, envs={}, params=Depth(left=2)),
            )
        except BoomError as error:
            seen.append(f"gather {error}")
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(boom("a", agents={}, envs={}, params=Depth(left=1)))
                group.create_task(boom("b", agents={}, envs={}, params=Depth()))
        except* BoomError as grouped:
            seen.extend(
                f"group {one}" for one in sorted(str(e) for e in grouped.exceptions)
            )
        return seen

    assert await run_fake(gathering, "x") == ["gather x", "group a", "group b"]


# ------------------------------------------------------------------------ the context


async def test_the_context_says_what_the_call_is() -> None:
    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing, resumable=True)
    async def keeping(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> dict[str, Any]:
        state = ctx.state
        assert state is not None
        state["seen"] = [1, 2]
        return {
            "flow": ctx.flow,
            "resumed": ctx.resumed,
            "state": state["seen"],
            "usage": ctx.usage,
            "budget": ctx.budget,
        }

    said = await run_fake(keeping, budget=Budget(cost=2))
    assert said["flow"] is keeping
    assert said["resumed"] is False
    assert said["state"] == [1, 2]
    assert said["usage"].cost == 0
    assert said["budget"].cost == 2


async def test_a_flow_that_is_not_resumable_keeps_no_state() -> None:
    @flow(agents=AgentCollection, envs=NoEnvs, params=Nothing)
    async def stateless(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Nothing,
        ctx: FlowContext,
    ) -> Any:
        return ctx.state

    assert await run_fake(stateless) is None


# ------------------------------------------------------------------ the running tree


async def test_running_is_every_call_going_now_and_nothing_once_it_ends() -> None:
    seen: list[tuple[LiveCall, ...]] = []
    leaves: list[None] = []
    all_there = asyncio.Event()

    @flow(agents=AgentCollection, envs=NoEnvs, params=Depth)
    async def watched(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Depth,
        ctx: FlowContext,
    ) -> None:
        if params.left:
            await asyncio.gather(
                *(
                    watched(
                        task, agents={}, envs={}, params=Depth(left=params.left - 1)
                    )
                    for _ in range(2)
                )
            )
        else:
            leaves.append(None)
            if len(leaves) == 4:
                all_there.set()
            await all_there.wait()
            seen.append(running())

    await run_fake(watched, params={"left": 2})
    assert running() == ()
    last = max(seen, key=len)
    assert len(last) == 7
    depths = sorted(one.depth for one in last)
    assert depths == [1, 2, 2, 3, 3, 3, 3]
    for one in last:
        assert one.name == "watched"
        assert (one.parent is None) == (one.depth == 1)
        if one.parent is not None:
            assert one.parent.depth == one.depth - 1


class Heard:
    def __init__(self) -> None:
        self.said: list[tuple[Any, ...]] = []

    def entered(self, call: LiveCall) -> None:
        self.said.append(("entered", call.name, call.depth, call.task))

    def left(self, call: LiveCall, error: BaseException | None) -> None:
        self.said.append(("left", call.name, type(error).__name__ if error else None))

    def spawned(
        self, call: LiveCall, role: str, session: SessionHandle, driver: AgentDriver
    ) -> None:
        self.said.append(("spawned", call.name, role, session.id is not None))

    def closed(self, session: SessionHandle) -> None:
        self.said.append(("closed", session.id is not None))


async def test_a_recorder_hears_every_call_and_session() -> None:
    @flow(agents=Solo, envs=Place, params=Nothing)
    async def recorded(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        session = await agents["agent"].spawn(env=envs["env"])
        with pytest.raises(BoomError):
            await boom("under", agents={}, envs={}, params=Depth())
        del session
        await asyncio.sleep(0)

    heard = Heard()
    await run_fake(recorded, "over", recorder=heard)
    assert heard.said == [
        ("entered", "recorded", 1, "over"),
        ("spawned", "recorded", "agent", True),
        ("entered", "boom", 2, "under"),
        ("left", "boom", "BoomError"),
        ("closed", True),
        ("left", "recorded", None),
    ]


# ------------------------------------------------------------------ what a call costs


async def test_a_sequential_call_starts_no_task_and_adds_two_frames() -> None:
    frames: list[int] = []

    @flow(agents=AgentCollection, envs=NoEnvs, params=Depth)
    async def counted(
        task: str,
        *,
        agents: AgentCollection,
        envs: NoEnvs,
        params: Depth,
        ctx: FlowContext,
    ) -> None:
        frames.append(len(_stack()))
        if params.left:
            await counted(task, agents={}, envs={}, params=Depth(left=params.left - 1))

    loop = asyncio.get_running_loop()
    made: list[object] = []
    factory = loop.get_task_factory()

    def counting(loop: asyncio.AbstractEventLoop, coro: Any, **kw: Any) -> Any:
        made.append(coro)
        return asyncio.Task(coro, loop=loop, **kw)

    loop.set_task_factory(counting)
    try:
        await run_fake(counted, params={"left": 20})
    finally:
        loop.set_task_factory(factory)
    assert made == [], "a sequential call started a task"
    steps = {b - a for a, b in itertools.pairwise(frames)}
    assert steps == {2}, f"frames added per level: {steps}"


def _stack() -> list[Any]:
    frame = sys._getframe(1)
    said: list[Any] = []
    while frame is not None:
        said.append(frame)
        frame = frame.f_back
    return said


async def test_an_orphan_is_cancelled_at_its_next_step() -> None:
    started = asyncio.Event()
    carry_on = asyncio.Event()
    outcome: list[str] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def orphan(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        started.set()
        await carry_on.wait()
        try:
            await agents["agent"].spawn(env=envs["env"])
        except FlowCancelled:
            outcome.append("cancelled")
            raise

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def parent(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        async def fail() -> None:
            await started.wait()
            raise BoomError

        await asyncio.gather(
            orphan(task, agents=agents, envs=envs, params=params), fail()
        )

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def top(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        with pytest.raises(BoomError):
            await parent(task, agents=agents, envs=envs, params=params)
        carry_on.set()
        for _ in range(5):
            await asyncio.sleep(0)

    await run_fake(top)
    assert outcome == ["cancelled"]


async def test_a_call_under_a_call_whose_caller_has_ended_is_cancelled() -> None:
    go_on = asyncio.Event()
    said: list[str] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def last(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        said.append("ran")

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def middle(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        await go_on.wait()
        try:
            await last(task, agents=agents, envs=envs, params=params)
        except FlowCancelled:
            said.append("cancelled")

    detached: list[asyncio.Future[Any]] = []

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def first(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        detached.append(
            asyncio.ensure_future(middle(task, agents=agents, envs=envs, params=params))
        )
        await asyncio.sleep(0)

    await run_fake(first)
    go_on.set()
    await detached[0]
    assert said == ["cancelled"]


async def test_a_derived_agent_passed_on_is_checked_once_per_kind() -> None:
    from hmz.flows import Permission, PermissionKind
    from hmz.runtime.flowing.declaring import Grant

    reader = Permission(local=PermissionKind.READ, user=PermissionKind.READ)
    assert Grant.of(frozenset(), reader) is Grant.of(frozenset(), reader)

    class Reader(Agent):
        _permission = reader

    class Reading(AgentCollection):
        agent: Reader

    @flow(agents=Reading, envs=Place, params=Nothing)
    async def taking(
        task: str, *, agents: Reading, envs: Place, params: Nothing, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    @flow(agents=Solo, envs=Place, params=Nothing)
    async def passing(
        task: str, *, agents: Solo, envs: Place, params: Nothing, ctx: FlowContext
    ) -> int:
        for _ in range(100):
            narrow = agents["agent"].derive(permission=reader)
            with pytest.raises(PermissionTooNarrow):
                await wants_online(
                    task, agents={"agent": narrow}, envs={}, params=params
                )
            await taking(task, agents={"agent": narrow}, envs=envs, params=params)
        described: Any = taking
        role = described.describe().agents[0]
        return len(role._seen)

    assert await run_fake(passing) <= 1


class Mixed(FlowParams):
    note: str = ""
    tags: list[str] = pydantic.Field(default_factory=list[str])


@flow(agents=AgentCollection, envs=NoEnvs, params=Mixed)
async def mixed(
    task: str, *, agents: AgentCollection, envs: NoEnvs, params: Mixed, ctx: FlowContext
) -> Mixed:
    return params


async def test_text_that_looks_like_json_stays_text_where_text_was_asked_for() -> None:
    said = await run_fake(mixed, params={"note": "42", "tags": '["x"]'})
    assert said == Mixed(note="42", tags=["x"])
    said = await run_fake(mixed, params={"note": "true", "tags": '["a", "b"]'})
    assert said == Mixed(note="true", tags=["a", "b"])
