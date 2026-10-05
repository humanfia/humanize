"""What a flow is handed: views answering to every protocol, granting what was declared.

The views are the runtime's own classes, not subclasses of the flow API's protocols, so what
holds them to the protocols is here: the assignments below are checked by pyright -- a view
missing a member, or with one of the wrong shape, fails the type check -- and the tests check
at run time that every member of every protocol and mixin is there, and that each mixin's is
refused to a role that did not declare it.
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any, Protocol, cast

import pydantic
import pytest

from hmz.flows import (
    HARNESS_AGENTS,
    Agent,
    AgentCollection,
    AntigravityAgent,
    AskUserHookAgentMixin,
    AskUserHookParams,
    AskUserHookResult,
    BashEnvMixin,
    CapabilityMissing,
    CapabilityNotGranted,
    ClaudeCodeAgent,
    CodexAgent,
    CPUEnvMixin,
    CursorAgent,
    DeepSeekHarnessAgent,
    Env,
    EnvCollection,
    FilesEnvMixin,
    Flow,
    FlowContext,
    FlowParams,
    FlowState,
    GitEnvMixin,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    GPUEnvMixin,
    GrokBuildAgent,
    HarnessKind,
    KimiCodeAgent,
    LocalEnv,
    LoopCommandAgentMixin,
    MemoryEnvMixin,
    MiMoCodeAgent,
    OpenCodeAgent,
    OutputSchemaError,
    Outworlder,
    Permission,
    PermissionKind,
    PermissionRequestHookAgentMixin,
    PiAgent,
    QwenCodeAgent,
    RewindableEnvMixin,
    ScratchDirEnvMixin,
    Session,
    SessionError,
    ShellEnvMixin,
    SteeringAgentMixin,
    StopHookParams,
    StopHookResult,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    TemporaryClonedDirEnvMixin,
    UnsupportedOperation,
    flow,
)
from hmz.runtime.flowing.engine import Call, FlowImpl
from hmz.runtime.flowing.fakes import FakeAgentDriver, FakeEnvDriver, run_fake
from hmz.runtime.flowing.journaling import FlowStateImpl
from hmz.runtime.flowing.spi import ENV_CAPABILITIES
from hmz.runtime.flowing.viewing import AgentView, EnvView, OutworlderView, SessionView
from tests.flows.kit import flowverse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

# ----------------------------------------------------------------- held to the protocols

_agent: type[Agent] = AgentView
_goal: type[GoalCommandAgentMixin] = AgentView
_loop: type[LoopCommandAgentMixin] = AgentView
_steering: type[SteeringAgentMixin] = AgentView
_permission: type[PermissionRequestHookAgentMixin] = AgentView
_subagent_start: type[SubagentStartHookAgentMixin] = AgentView
_subagent_stop: type[SubagentStopHookAgentMixin] = AgentView
_ask_user: type[AskUserHookAgentMixin] = AgentView
_claude: type[ClaudeCodeAgent] = AgentView
_codex: type[CodexAgent] = AgentView
_cursor: type[CursorAgent] = AgentView
_opencode: type[OpenCodeAgent] = AgentView
_mimo: type[MiMoCodeAgent] = AgentView
_qwen: type[QwenCodeAgent] = AgentView
_kimi: type[KimiCodeAgent] = AgentView
_grok: type[GrokBuildAgent] = AgentView
_pi: type[PiAgent] = AgentView
_agy: type[AntigravityAgent] = AgentView
_dsh: type[DeepSeekHarnessAgent] = AgentView
_outworlder: type[Outworlder] = OutworlderView
_as_agent: type[Agent] = OutworlderView
_session: type[Session] = SessionView
_env: type[Env] = EnvView
_local: type[LocalEnv] = EnvView
_shell: type[ShellEnvMixin] = EnvView
_bash: type[BashEnvMixin] = EnvView
_files: type[FilesEnvMixin] = EnvView
_worktree: type[GitWorktreeEnvMixin] = EnvView
_rewindable: type[RewindableEnvMixin] = EnvView
_git: type[GitEnvMixin] = EnvView
_clone: type[TemporaryClonedDirEnvMixin] = EnvView
_scratch: type[ScratchDirEnvMixin] = EnvView
_cpu: type[CPUEnvMixin] = EnvView
_memory: type[MemoryEnvMixin] = EnvView
_gpu: type[GPUEnvMixin] = EnvView
_context: type[FlowContext] = Call
_state: type[FlowState] = FlowStateImpl
_flow: type[Flow] = FlowImpl

#: What a protocol class holds that is not a member of the protocol.
_MACHINERY = {"_is_protocol", "_is_runtime_protocol", "_abc_impl"}


def _members(protocol: type) -> set[str]:
    """Every member a protocol declares, its bases' included."""
    return {
        name
        for cls in protocol.__mro__
        if cls not in (object, Protocol, typing.Generic)
        for name in vars(cls)
        if not name.startswith("__") and name not in _MACHINERY
    }


AGENT_PROTOCOLS = [
    Agent,
    GoalCommandAgentMixin,
    LoopCommandAgentMixin,
    SteeringAgentMixin,
    PermissionRequestHookAgentMixin,
    SubagentStartHookAgentMixin,
    SubagentStopHookAgentMixin,
    AskUserHookAgentMixin,
    *HARNESS_AGENTS.values(),
]
ENV_PROTOCOLS = [
    Env,
    LocalEnv,
    ShellEnvMixin,
    BashEnvMixin,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    RewindableEnvMixin,
    GitEnvMixin,
    TemporaryClonedDirEnvMixin,
    ScratchDirEnvMixin,
    CPUEnvMixin,
    MemoryEnvMixin,
    GPUEnvMixin,
]


@pytest.mark.parametrize(
    ("protocol", "view"),
    [
        *((one, AgentView) for one in AGENT_PROTOCOLS),
        *((one, EnvView) for one in ENV_PROTOCOLS),
        (Outworlder, OutworlderView),
        (Session, SessionView),
        (FlowContext, Call),
        (FlowState, FlowStateImpl),
        (Flow, FlowImpl),
    ],
    ids=lambda one: getattr(one, "__name__", str(one)),
)
def test_every_member_of_every_protocol_is_on_its_view(
    protocol: type, view: type
) -> None:
    missing = {name for name in _members(protocol) if not hasattr(view, name)}
    assert not missing, f"{view.__name__} lacks {missing} of {protocol.__name__}"


def test_a_view_is_no_subclass_of_what_it_answers_to() -> None:
    for view in (AgentView, EnvView, OutworlderView, SessionView):
        assert not {Agent, Env, Outworlder, Session} & set(view.__mro__)
        assert "__dict__" not in dir(view), f"{view.__name__} lost its __slots__"


# --------------------------------------------------------------------- what is refused


class Plain(AgentCollection):
    agent: Agent


class Bare(EnvCollection):
    env: Env


class Shell(Env, ShellEnvMixin): ...


class ShellOnly(EnvCollection):
    env: Shell


class Nothing(FlowParams):
    pass


class Answer(pydantic.BaseModel):
    said: str = ""


#: What a plain `Agent` may not do, each with the mixin that would let it.
AGENT_REFUSALS: dict[str, Callable[[Any, Any], Awaitable[Any]]] = {
    "/goal": lambda agent, session: agent.run("/goal ship it", session=session),
    "/goal alone": lambda agent, session: agent.run("/goal", session=session),
    "/loop": lambda agent, session: agent.run("/loop 5m check", session=session),
    " /goal": lambda agent, session: agent.run("  /goal ship it", session=session),
    "newline /loop": lambda agent, session: agent.run("\n/loop 5m x", session=session),
    "steer": lambda agent, session: agent.steer("go", session=session),
    "on_permission_request": lambda agent, _: _hung(agent.on_permission_request),
    "on_subagent_start": lambda agent, _: _hung(agent.on_subagent_start),
    "on_subagent_stop": lambda agent, _: _hung(agent.on_subagent_stop),
    "on_ask_user": lambda agent, _: _hung(agent.on_ask_user),
}

#: What a plain `Env` may not do.
ENV_REFUSALS: dict[str, Callable[[Any], Awaitable[Any]]] = {
    "exec": lambda env: env.exec(["true"]),
    "read": lambda env: env.read("a"),
    "write": lambda env: env.write("a", b"a"),
    "derive_worktree": lambda env: env.derive_worktree(),
    "snapshot": lambda env: env.snapshot(),
    "rewind": lambda env: env.rewind("HEAD"),
    "snapshots": lambda env: env.snapshots(),
    "derive_temp_clone": lambda env: env.derive_temp_clone("a"),
    "destroy_temp_clone": lambda env: env.destroy_temp_clone("a"),
    "derive_scratch": lambda env: env.derive_scratch("a"),
    "destroy_scratch": lambda env: env.destroy_scratch("a"),
}


async def _hung(method: Any) -> None:
    async def hook(params: Any) -> Any:
        del params

    method(hook)


@pytest.mark.parametrize("refused", sorted(AGENT_REFUSALS))
async def test_a_plain_agent_is_refused_what_it_did_not_declare(refused: str) -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def plain(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn()
        await AGENT_REFUSALS[refused](agent, session)

    driver = FakeAgentDriver(HarnessKind.CLAUDE)
    with pytest.raises(CapabilityNotGranted):
        await run_fake(plain, agents={"agent": driver})
    assert driver.prompts == [], "a refused prompt reached the harness"


@pytest.mark.parametrize("refused", sorted(ENV_REFUSALS))
async def test_a_plain_env_is_refused_what_it_did_not_declare(refused: str) -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def plain(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        await ENV_REFUSALS[refused](envs["env"])

    env = FakeEnvDriver()
    with pytest.raises(CapabilityNotGranted):
        await run_fake(plain, envs={"env": env})
    assert env.commands == []


class Rewindable(Env, RewindableEnvMixin): ...


class RewindableOnly(EnvCollection):
    env: Rewindable


@pytest.mark.parametrize("refused", ["snapshot", "rewind", "snapshots"])
async def test_rewindable_alone_grants_nothing(refused: str) -> None:
    @flow(agents=Plain, envs=RewindableOnly, params=Nothing)
    async def rewinds(
        task: str,
        *,
        agents: Plain,
        envs: RewindableOnly,
        params: Nothing,
        ctx: FlowContext,
    ) -> None:
        await ENV_REFUSALS[refused](envs["env"])

    with pytest.raises(CapabilityNotGranted, match="needs GitEnvMixin"):
        await run_fake(rewinds, envs={"env": FakeEnvDriver()})


class Repo(Env, GitEnvMixin): ...


class Repos(EnvCollection):
    repo: Repo


class Here(LocalEnv, GitEnvMixin): ...


class Heres(EnvCollection):
    here: Here


@flow(agents=Plain, envs=Repos, params=Nothing)
async def snapshots_one(
    task: str, *, agents: Plain, envs: Repos, params: Nothing, ctx: FlowContext
) -> str:
    return await envs["repo"].snapshot()


@flow(agents=Plain, envs=Heres, params=Nothing)
async def snapshots_here(
    task: str, *, agents: Plain, envs: Heres, params: Nothing, ctx: FlowContext
) -> str:
    return await envs["here"].snapshot()


async def test_git_is_refused_up_front_where_the_machine_has_none() -> None:
    gitless = ENV_CAPABILITIES - {GitEnvMixin}

    with pytest.raises(CapabilityMissing, match="needs git on the machine's PATH"):
        await run_fake(
            snapshots_one, envs={"repo": FakeEnvDriver(capabilities=gitless)}
        )
    with pytest.raises(CapabilityMissing, match="needs git on the machine's PATH"):
        await run_fake(snapshots_here, local=FakeEnvDriver(capabilities=gitless))
    assert await run_fake(snapshots_one) == "refs/hmz/snapshots/1"


class Trees(Env, GitWorktreeEnvMixin, BashEnvMixin): ...


class Forest(EnvCollection):
    trees: Trees


@flow(agents=Plain, envs=Forest, params=Nothing)
async def plants(
    task: str, *, agents: Plain, envs: Forest, params: Nothing, ctx: FlowContext
) -> None:
    raise AssertionError("a flow refused up front ran")


async def test_a_worktree_and_a_script_are_refused_up_front_where_their_tool_is_not() -> (
    None
):
    gitless = ENV_CAPABILITIES - {GitEnvMixin, GitWorktreeEnvMixin}
    with pytest.raises(CapabilityMissing) as refused:
        await run_fake(plants, envs={"trees": FakeEnvDriver(capabilities=gitless)})
    assert str(refused.value).endswith(
        "needs GitWorktreeEnvMixin, which local/work does not support: "
        "GitWorktreeEnvMixin needs git on the machine's PATH, and it has none"
    )

    bare = gitless - {BashEnvMixin}
    with pytest.raises(CapabilityMissing) as refused:
        await run_fake(plants, envs={"trees": FakeEnvDriver(capabilities=bare)})
    assert str(refused.value).endswith(
        "does not support: BashEnvMixin needs bash on the machine's PATH, and it has none; "
        "GitWorktreeEnvMixin needs git on the machine's PATH, and it has none"
    )


async def test_a_script_needs_bash_where_an_argv_needs_only_a_shell() -> None:
    @flow(agents=Plain, envs=ShellOnly, params=Nothing)
    async def shell(
        task: str, *, agents: Plain, envs: ShellOnly, params: Nothing, ctx: FlowContext
    ) -> tuple[int, str, str]:
        env = envs["env"]
        with pytest.raises(CapabilityNotGranted):
            await env.exec("echo hi | tr a-z A-Z")  # pyright: ignore[reportArgumentType]
        return await env.exec(["echo", "hi"])

    assert await run_fake(shell) == (0, "hi\n", "")


class Everything(AgentCollection):
    agent: ClaudeCodeAgent


class Anything(
    Env,
    BashEnvMixin,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    GitEnvMixin,
    TemporaryClonedDirEnvMixin,
    ScratchDirEnvMixin,
): ...


class AllOf(EnvCollection):
    env: Anything


async def test_what_is_declared_is_granted() -> None:
    @flow(agents=Everything, envs=AllOf, params=Nothing)
    async def everything(
        task: str,
        *,
        agents: Everything,
        envs: AllOf,
        params: Nothing,
        ctx: FlowContext,
    ) -> list[Any]:
        agent, env = agents["agent"], envs["env"]
        session = await agent.spawn()
        said: list[Any] = [
            await agent.run("/goal ship it", session=session, env=env),
            await agent.run("/loop 5m check", session=session, env=env),
            await agent.run("/goalkeeper is no command", session=session, env=env),
        ]
        for hang in (
            agent.on_permission_request,
            agent.on_subagent_start,
            agent.on_subagent_stop,
            agent.on_ask_user,
        ):
            hang(None)
        await env.write("a.txt", b"a")
        said.append(await env.read("a.txt"))
        said.append(await env.exec("anything"))
        said.append(await env.exec(argv=["echo", "x"]))
        said.append(await env.exec(script="more"))
        tree = await env.derive_worktree(ref="main")
        clone = await env.derive_temp_clone("c")
        scratch = await env.derive_scratch("s")
        sub = await env.derive_subdir(subdir="deeper")
        said.extend(one.workdir.as_posix() for one in (tree, clone, scratch, sub))
        await env.destroy_temp_clone("c")
        await env.destroy_scratch("s")
        said.append(await env.snapshot("s"))
        said.append(await env.snapshots())
        await env.rewind("refs/hmz/snapshots/s")
        return said

    scripted = FakeEnvDriver(run=lambda command, env: (0, str(command), ""))
    said = await run_fake(everything, envs={"env": scripted})
    assert said[:3] == ["ok", "ok", "ok"]
    assert said[3] == b"a"
    assert said[4] == (0, "anything", "")
    assert said[5] == (0, "('echo', 'x')", "")
    assert said[6] == (0, "more", "")
    assert said[10] == "/work/deeper"
    assert said[11:] == ["refs/hmz/snapshots/s", ["refs/hmz/snapshots/s"]]


async def test_exec_takes_one_command() -> None:
    @flow(agents=Plain, envs=AllOf, params=Nothing)
    async def twice(
        task: str, *, agents: Plain, envs: AllOf, params: Nothing, ctx: FlowContext
    ) -> None:
        await envs["env"].exec(["a"], script="b")  # pyright: ignore[reportCallIssue]

    with pytest.raises(TypeError, match="one command"):
        await run_fake(twice)


# ------------------------------------------------------------------------- narrowing


class Narrow(AgentCollection):
    agent: Agent


DERIVING = """
    from typing import Any

    import pytest

    from hmz.flows import (
        Agent, AgentCollection, CapabilityNotGranted, Env, EnvCollection, FlowContext,
        FlowParams, Permission, PermissionKind, flow,
    )


    class Wide(Agent):
        _permission = Permission(online=PermissionKind.ALL)
        _skills = ("a", "b")


    class Agents(AgentCollection):
        agent: Wide


    class Envs(EnvCollection):
        env: Env


    @flow(agents=Agents, envs=Envs, params=FlowParams)
    async def deriving(task, *, agents, envs, params, ctx) -> list[Any]:
        agent = agents["agent"]
        narrow = agent.derive(
            permission=Permission(online=PermissionKind.NONE), skills=("a",)
        )
        same = agent.derive()
        with pytest.raises(CapabilityNotGranted):
            narrow.derive(permission=Permission(online=PermissionKind.ALL))
        with pytest.raises(CapabilityNotGranted):
            narrow.derive(skills=("b",))
        with pytest.raises(CapabilityNotGranted):
            agent.derive(
                permission=Permission(system=PermissionKind.ALL, user=PermissionKind.ALL)
            )
        with pytest.raises(TypeError):
            agent.derive(permission="read")
        for one in (narrow, same):
            await one.run("x", session=await one.spawn(), env=envs["env"])
        return [(one.grant.permission, one.grant.skills) for one in (narrow, same)]
"""


async def test_derive_only_narrows(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "deriving": {
                "__init__.py": DERIVING,
                "skills/a/SKILL.md": "a",
                "skills/b/SKILL.md": "b",
            }
        },
    )
    driver = FakeAgentDriver()
    (narrow, same) = await run_fake(str(flows / "deriving"), agents={"agent": driver})
    assert narrow == (Permission(online=PermissionKind.NONE), ("a",))
    assert same == (Permission(online=PermissionKind.ALL), ("a", "b"))
    given = [[skill.name for skill in one.skills] for one in driver.sessions]
    assert given == [["a"], ["a", "b"]]
    assert driver.sessions[0].skills[0].at == flows / "deriving" / "skills" / "a"


async def test_a_derived_agent_shares_the_hooks_and_the_sessions_it_came_from() -> None:
    heard: list[str] = []

    async def stop(params: StopHookParams) -> StopHookResult:
        heard.append(params.said)
        return StopHookResult()

    @flow(agents=Narrow, envs=Bare, params=Nothing)
    async def deriving(
        task: str, *, agents: Narrow, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> Permission:
        agent = agents["agent"]
        agent.on_stop(stop)
        reader = agent.derive(
            permission=Permission(local=PermissionKind.READ, user=PermissionKind.READ)
        )
        mine = await reader.spawn()
        await reader.run("one", session=mine, env=envs["env"])
        theirs = await agent.spawn()
        await reader.run("two", session=theirs, env=envs["env"])
        reader.on_stop(None)
        await agent.run("three", session=mine, env=envs["env"])
        driver: FakeAgentDriver = cast("Any", reader).driver
        return driver.sessions[0].permission

    permission = await run_fake(deriving, agents={"agent": FakeAgentDriver(reply="x")})
    assert heard == ["x", "x"]
    assert permission == Permission(local=PermissionKind.READ, user=PermissionKind.READ)


# --------------------------------------------------------------------------- sessions


async def test_a_session_is_its_agent_s_alone() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing, name="other")
    async def other(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        del task, agents, envs, params, ctx

    class Two(AgentCollection):
        a: Agent
        b: Agent

    @flow(agents=Two, envs=Bare, params=Nothing)
    async def two(
        task: str, *, agents: Two, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        a, b = agents["a"], agents["b"]
        session = await a.spawn()
        with pytest.raises(SessionError):
            await b.run("x", session=session, env=envs["env"])
        with pytest.raises(SessionError):
            await b.fork(session)
        with pytest.raises(SessionError):
            await a.run("x", session=object())  # pyright: ignore[reportArgumentType]
        with pytest.raises(TypeError):
            await a.run("x", session=session, env=object())  # pyright: ignore[reportArgumentType]
        with pytest.raises(SessionError, match="no turn"):
            await a.fork(session)
        await a.run("x", session=session, env=envs["env"])
        forked = await a.fork(session)
        assert await a.run("in the fork", session=forked, env=envs["env"]) == "ok"

    await run_fake(two)


async def test_a_session_takes_one_turn_at_a_time() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def overlapping(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn()
        first = agent.run("slow", session=session, env=envs["env"])
        import asyncio

        turning = asyncio.ensure_future(first)
        await asyncio.sleep(0)
        with pytest.raises(SessionError, match="under way"):
            await agent.run("again", session=session, env=envs["env"])
        view: SessionView = session  # pyright: ignore[reportAssignmentType]
        handle: Any = view._handle
        handle.interrupt()
        with pytest.raises(SessionError):
            await turning

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del output_schema
        if prompt == "slow":
            return await session.until_steered()
        return "ok"

    await run_fake(overlapping, agents={"agent": FakeAgentDriver(reply=reply)})


async def test_an_answer_that_is_not_the_schema_asked_for_is_refused() -> None:
    class Strict(pydantic.BaseModel):
        n: int

    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def schema(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> Answer:
        agent = agents["agent"]
        session = await agent.spawn()
        with pytest.raises(OutputSchemaError):
            await agent.run("x", session=session, env=envs["env"], output_schema=Strict)
        return await agent.run(
            "y", session=session, env=envs["env"], output_schema=Answer
        )

    answered = await run_fake(
        schema, agents={"agent": FakeAgentDriver(reply=['{"said": 1}', {"said": "y"}])}
    )
    assert answered == Answer(said="y")


async def test_a_harness_that_cannot_fork_says_so() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def forking(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        agent = agents["agent"]
        session = await agent.spawn()
        await agent.run("x", session=session, env=envs["env"])
        forked = await agent.fork(session)
        await agent.run("y", session=forked, env=envs["env"])

    with pytest.raises(UnsupportedOperation):
        await run_fake(forking, agents={"agent": FakeAgentDriver(forks=False)})


async def test_a_session_takes_each_turn_where_that_turn_is_given() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def moving(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> list[str]:
        agent = agents["agent"]
        session = await agent.spawn()
        return [
            await agent.run("one", session=session, env=envs["env"]),
            await agent.run("two", session=session),
            await agent.run("three", session=session, env=None),
        ]

    driver = FakeAgentDriver(reply=lambda prompt, **_: prompt)
    assert await run_fake(moving, agents={"agent": driver}) == ["one", "two", "three"]
    # One conversation, carried from the flow's environment into the run's own workspace.
    (session,) = driver.sessions
    assert session.prompts == ["one", "two", "three"]
    assert [(one.workdir.as_posix(), one.env) for one in session.placements] == [
        ("/env", "env"),
        ("/here", ""),
    ]


async def test_a_session_is_not_carried_where_its_harness_cannot_carry_it() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def moving(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> str:
        agent = agents["agent"]
        session = await agent.spawn()
        await agent.run("one", session=session, env=envs["env"])
        with pytest.raises(UnsupportedOperation):
            await agent.run("two", session=session)
        # Refused, it is still where it was, and goes on there.
        return await agent.run("three", session=session, env=envs["env"])

    driver = FakeAgentDriver(HarnessKind.OPENCODE)
    assert await run_fake(moving, agents={"agent": driver}) == "ok"
    (session,) = driver.sessions
    assert session.prompts == ["one", "three"]


async def test_a_fork_cut_while_its_parent_takes_a_turn_is_refused() -> None:
    import asyncio

    cutting, cut = asyncio.Event(), asyncio.Event()

    class Slow(FakeAgentDriver):
        async def open(self, *args: Any, **kwargs: Any) -> Any:
            if kwargs.get("fork_of") is not None:
                cutting.set()
                await cut.wait()
            return await super().open(*args, **kwargs)

    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def racing(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> None:
        agent, env = agents["agent"], envs["env"]
        session = await agent.spawn()
        await agent.run("one", session=session, env=env)
        forked = await agent.fork(session)

        async def meanwhile() -> None:
            await cutting.wait()
            await agent.run("two", session=session, env=env)
            cut.set()

        with pytest.raises(SessionError, match="taken a turn since"):
            await asyncio.gather(agent.run("three", session=forked, env=env), meanwhile())

    driver = Slow()
    await run_fake(racing, agents={"agent": driver})
    parent, fork = driver.sessions
    assert parent.prompts == ["one", "two"]
    assert fork.closed


async def test_a_session_says_what_it_is() -> None:
    @flow(agents=Plain, envs=Bare, params=Nothing)
    async def looking(
        task: str, *, agents: Plain, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> tuple[Any, ...]:
        agent = agents["agent"]
        session = await agent.spawn()
        before = session.usage.output_tokens
        await agent.run("x", session=session, env=envs["env"])
        return (
            session.agent is agent,
            before,
            session.usage.output_tokens,
            agent.role,
            agent.harness,
            agent.model,
            agent.effort,
            agent.provider,
            envs["env"].role,
            envs["env"].backend,
            envs["env"].available,
        )

    said = await run_fake(
        looking,
        agents={
            "agent": FakeAgentDriver(
                HarnessKind.CODEX,
                model="m",
                effort="high",
                provider="p",
                output_tokens=3,
            )
        },
    )
    assert said == (
        True,
        0,
        3,
        "agent",
        HarnessKind.CODEX,
        "m",
        "high",
        "p",
        "env",
        "local",
        True,
    )


async def test_an_agent_answers_the_steer_it_was_given() -> None:
    class Steered(AgentCollection):
        agent: ClaudeCodeAgent

    @flow(agents=Steered, envs=Bare, params=Nothing)
    async def steering(
        task: str, *, agents: Steered, envs: Bare, params: Nothing, ctx: FlowContext
    ) -> str:
        import asyncio

        agent = agents["agent"]
        session = await agent.spawn()
        with pytest.raises(SessionError):
            await agent.steer("nobody is listening", session=session)
        turning = asyncio.ensure_future(
            agent.run("wait", session=session, env=envs["env"])
        )
        await asyncio.sleep(0)
        await agent.steer("now", session=session, queued=False)
        return await turning

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del prompt, output_schema
        return await session.until_steered()

    assert (
        await run_fake(steering, agents={"agent": FakeAgentDriver(reply=reply)})
        == "now"
    )


async def test_permission_request_hooks_answer_the_tools_an_agent_reaches_for() -> None:
    from hmz.flows import (
        PermissionRequestHookParams,
        PermissionRequestHookResult,
        PreToolUseHookParams,
        PreToolUseHookResult,
    )

    class Guarded(Agent, PermissionRequestHookAgentMixin): ...

    class GuardedAgents(AgentCollection):
        agent: Guarded

    asked: list[tuple[str, dict[str, Any], Any]] = []

    async def pre(params: PreToolUseHookParams) -> PreToolUseHookResult:
        return PreToolUseHookResult(block=params.tool == "rm")

    async def guard(params: PermissionRequestHookParams) -> PermissionRequestHookResult:
        asked.append((params.tool, dict(params.input), params.ctx))
        return PermissionRequestHookResult(allow=params.input.get("force") is not True)

    @flow(agents=GuardedAgents, envs=Bare, params=Nothing)
    async def guarded(
        task: str,
        *,
        agents: GuardedAgents,
        envs: Bare,
        params: Nothing,
        ctx: FlowContext,
    ) -> Any:
        agent = agents["agent"]
        agent.on_pre_tool_use(pre)
        agent.on_permission_request(guard)
        session = await agent.spawn()
        await agent.run("go", session=session, env=envs["env"])
        return ctx

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str:
        del prompt, output_schema
        return str(
            [
                await session.tool("rm", {"path": "/"}),
                await session.tool("git", {"force": True}),
                await session.tool("git", {"force": False}),
            ]
        )

    driver = FakeAgentDriver(HarnessKind.CODEX, reply=reply)
    ctx = await run_fake(guarded, agents={"agent": driver})
    assert driver.sessions[0].tools == [
        ("rm", {"path": "/"}, False),
        ("git", {"force": True}, False),
        ("git", {"force": False}, True),
    ]
    assert [(tool, said) for tool, said, _ in asked] == [
        ("git", {"force": True}),
        ("git", {"force": False}),
    ]
    assert all(one is ctx for _, _, one in asked)


async def test_ask_user_hooks_answer_the_agent() -> None:
    class Asking(Agent, AskUserHookAgentMixin): ...

    class AskingAgents(AgentCollection):
        agent: Asking

    async def answer(params: AskUserHookParams) -> AskUserHookResult:
        return AskUserHookResult(answer=params.options[-1])

    @flow(agents=AskingAgents, envs=Bare, params=Nothing)
    async def asking(
        task: str,
        *,
        agents: AskingAgents,
        envs: Bare,
        params: Nothing,
        ctx: FlowContext,
    ) -> str:
        agent = agents["agent"]
        agent.on_ask_user(answer)
        session = await agent.spawn()
        return await agent.run("go", session=session, env=envs["env"])

    async def reply(prompt: str, *, session: Any, output_schema: Any) -> str | None:
        del prompt, output_schema
        return await session.ask("which?", ("a", "b"))

    said = await run_fake(asking, agents={"agent": FakeAgentDriver(reply=reply)})
    assert said == "b"
