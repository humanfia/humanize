"""The flow API as a flow author writes it, held to the type checker.

Not a test module, and never imported: pyright reads it with the rest of the tree, which is
the whole of how it is checked. What is written plainly must type-check -- the spec's own
examples, and a flow that uses every part of the API. What is written with a
`# pyright: ignore[...]` must *not*: `reportUnnecessaryTypeIgnoreComment` is an error here, so
an ignore that stops being needed -- because a misuse stopped being a type error -- fails the
check exactly as a real error would.
"""

from __future__ import annotations

from typing import NotRequired, assert_type

import pydantic

from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookParams,
    AskUserHookResult,
    BashEnvMixin,
    Budget,
    BudgetExceeded,
    CapabilityNotGranted,
    ClaudeCodeAgent,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    Flow,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    GPUEnvMixin,
    HarnessKind,
    LocalEnv,
    LoopCommandAgentMixin,
    MemoryEnvMixin,
    Outworlder,
    OutworlderRunHookParams,
    OutworlderRunHookResult,
    Permission,
    PermissionKind,
    PermissionRequestHookAgentMixin,
    PermissionRequestHookParams,
    PermissionRequestHookResult,
    PreToolUseHookParams,
    PreToolUseHookResult,
    ScratchDirEnvMixin,
    Session,
    ShellEnvMixin,
    SteeringAgentMixin,
    StopHookParams,
    StopHookResult,
    TemporaryClonedDirEnvMixin,
    Usage,
    flow,
    load,
)

# ---------------------------------------------------------------- the spec's own examples


class MyEnv(Env, CPUEnvMixin, MemoryEnvMixin):
    _cpu_count = 4
    _memory = 8 * 1024 * 1024 * 1024


class MyEnvCollection(EnvCollection):
    my_env: MyEnv


class MyAgent(
    Agent,
    GoalCommandAgentMixin,
    LoopCommandAgentMixin,
    PermissionRequestHookAgentMixin,
):
    _permission = Permission(
        local=PermissionKind.ALL,
        user=PermissionKind.READ,
        system=PermissionKind.NONE,
        online=PermissionKind.NONE,
    )
    _skills = ("review-notes",)


class MyAgentCollection(AgentCollection):
    my_agent: MyAgent


# ------------------------------------------------------------------ a flow using all of it


class Workspace(
    LocalEnv,
    BashEnvMixin,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    TemporaryClonedDirEnvMixin,
    ScratchDirEnvMixin,
):
    """The directory the run was started in, which no `-e` names."""


class Trainer(Env, ShellEnvMixin, GPUEnvMixin):
    _gpu_count = 8
    _gpu_memory = 80 * 1024**3


class Steerer(Agent, SteeringAgentMixin):
    """An agent the flow puts words into mid-turn."""


class Envs(EnvCollection):
    workspace: Workspace
    trainer: NotRequired[Trainer]
    plain: Env


class Agents(AgentCollection):
    coder: MyAgent
    steerer: Steerer
    claude: ClaudeCodeAgent
    human: Outworlder
    plain: Agent


class Params(FlowParams):
    rounds: int = 3
    target: str = "tests pass"


class Verdict(pydantic.BaseModel):
    done: bool = False
    why: str = ""


class ReviewAgents(AgentCollection):
    reviewer: Agent
    human: NotRequired[Outworlder]


class ReviewEnvs(EnvCollection):
    repo: Env


class ReviewParams(FlowParams):
    strict: bool = True


async def refuse_rm(params: PermissionRequestHookParams) -> PermissionRequestHookResult:
    return PermissionRequestHookResult(allow=params.tool != "rm", reason="no rm")


async def keep_going(params: StopHookParams) -> StopHookResult:
    return StopHookResult(block=params.again < 3, reason="keep going")


async def watch(params: PreToolUseHookParams) -> PreToolUseHookResult:
    assert_type(params.ctx, FlowContext)
    assert_type(params.session, Session)
    return PreToolUseHookResult()


async def answer(params: AskUserHookParams) -> AskUserHookResult:
    return AskUserHookResult(answer=params.options[0] if params.options else None)


async def stand_in(params: OutworlderRunHookParams) -> OutworlderRunHookResult:
    if params.output_schema is None:
        return OutworlderRunHookResult(output="yes")
    return OutworlderRunHookResult(output=params.output_schema())


@flow(agents=ReviewAgents, envs=ReviewEnvs, params=ReviewParams, hidden=True)
async def review(
    task: str,
    *,
    agents: ReviewAgents,
    envs: ReviewEnvs,
    params: ReviewParams,
    ctx: FlowContext,
) -> Verdict:
    reviewer = agents["reviewer"]
    session = await reviewer.spawn(env=envs["repo"])
    verdict = await reviewer.run(task, session=session, output_schema=Verdict)
    if params.strict and "human" in agents:
        human = agents["human"]
        human_session = await human.spawn(env=envs["repo"])
        if not human.away:
            verdict = await human.run(
                task, session=human_session, output_schema=Verdict
            )
    return verdict


@flow(
    agents=Agents,
    envs=Envs,
    params=Params,
    name="main",
    description="Everything the flow API offers, used once.",
    resumable=True,
)
async def everything(
    task: str,
    *,
    agents: Agents,
    envs: Envs,
    params: Params,
    ctx: FlowContext,
) -> str:
    coder, workspace = agents["coder"], envs["workspace"]
    assert_type(coder.harness, HarnessKind)
    assert_type(workspace.workdir.name, str)

    session = await coder.spawn(env=workspace)
    said = await coder.run(task, session=session)
    assert_type(said, str)
    verdict = await coder.run(
        "done?", session=session, output_schema=Verdict, budget=Budget(cost=0.5)
    )
    assert_type(verdict, Verdict)
    await coder.run(f"/goal {params.target}", session=session)
    assert_type(session.usage, Usage)

    coder.on_permission_request(refuse_rm)
    coder.on_stop(keep_going)
    coder.on_pre_tool_use(watch)
    coder.on_stop(None)
    narrow = coder.derive(
        permission=Permission(user=PermissionKind.NONE, system=PermissionKind.NONE)
    )
    assert_type(narrow, MyAgent)

    steerer = agents["steerer"]
    running = await steerer.spawn(env=workspace)
    await steerer.steer("focus on the tests", session=running, queued=False)

    claude = agents["claude"]
    claude.on_ask_user(answer)
    claude.on_subagent_stop(None)
    forked = await claude.fork(session, env=workspace)
    await claude.steer("and the docs", session=forked)

    code, out, err = await workspace.exec(["git", "status", "--short"])
    assert_type(code, int)
    await workspace.exec("git log --oneline | head -1", timeout=10)
    notes = await workspace.read("NOTES.md")
    await workspace.write("NOTES.md", notes + out.encode() + err.encode())
    tree = await workspace.derive_worktree(ref="main")
    await tree.exec("make test")
    clone = await workspace.derive_temp_clone("try-1")
    assert_type(clone, Workspace)
    await workspace.destroy_temp_clone("try-1")
    scratch = await workspace.derive_scratch("notes")
    await scratch.write("a.txt", b"a")
    await workspace.destroy_scratch("notes")
    sub = await workspace.derive_subdir(subdir="docs")
    assert_type(sub, Env)

    if "trainer" in envs:
        await envs["trainer"].exec(["nvidia-smi"])

    if ctx.state is not None:
        ctx.state["round"] = ctx.state["round"] + 1 if "round" in ctx.state else 1
        del ctx.state["round"]
    assert_type(ctx.budget, Budget)
    assert_type(ctx.flow, Flow)

    reviewing = load(":review")
    try:
        result = await reviewing(
            task,
            agents={"reviewer": agents["plain"], "human": agents["human"]},
            envs={"repo": workspace},
            params=ReviewParams(strict=False),
            budget=Budget(cost=1.0, graceful=False),
        )
    except (BudgetExceeded, CapabilityNotGranted):
        result = None

    helper = Outworlder.new()
    helper.on_outworlder_run(stand_in)
    await load("humanize1:gen-plan")(
        task, agents={"planner": coder, "human": helper}, envs=envs, params=params
    )
    await review(task, agents=agents, envs=envs, params=params)
    return f"{said} {result}"


# ------------------------------------------------ what must not type-check, and does not


async def misuse(agents: Agents, envs: Envs, session: Session) -> None:
    plain, trainer = agents["plain"], envs.get("trainer")

    # Steering an agent whose role did not ask to be steered.
    await plain.steer("x", session=session)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    # A hook only some harnesses reach, on an agent that did not declare it.
    plain.on_permission_request(refuse_rm)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    agents["steerer"].on_ask_user(answer)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    # A hook of one moment hung on another.
    plain.on_pre_tool_use(keep_going)  # pyright: ignore[reportArgumentType]

    # A script where only programs were declared, and files where none were.
    if trainer is not None:
        await trainer.exec("nvidia-smi | head")  # pyright: ignore[reportArgumentType]
        await trainer.read("x")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    await envs["plain"].exec(["ls"])  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    # A permission written as strings, and an outworlder hook on an agent that is not one.
    Permission(local="all")  # pyright: ignore[reportArgumentType]
    plain.on_outworlder_run(stand_in)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]

    # A schema that is not a model.
    await plain.run("x", session=session, output_schema=dict)  # pyright: ignore[reportArgumentType]

    # Calling a flow without what it needs.
    await review("x")  # pyright: ignore[reportCallIssue]


def sync_flow(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    del task, agents, envs, params, ctx


# A flow must be an async function.
flow(agents=Agents, envs=Envs, params=Params)(sync_flow)  # pyright: ignore[reportArgumentType]
