"""What a flow is handed: views that let it do exactly what its roles declared."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, cast

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    BashEnvMixin,
    CapabilityNotGranted,
    ClaudeCodeAgent,
    Env,
    EnvBackendKind,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    GitEnvMixin,
    GitWorktreeEnvMixin,
    HarnessKind,
    HookKind,
    LiteLLMAgent,
    OutputSchemaError,
    OutworlderAway,
    OutworlderRunHookResult,
    Permission,
    PermissionKind,
    ScratchDirEnvMixin,
    SessionError,
    ShellEnvMixin,
    SteeringAgentMixin,
    TemporaryClonedDirEnvMixin,
    UnsupportedOperation,
    Usage,
    flow,
)
from hmz.runtime.flowing.declaring import Grant
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    run_fake,
)
from hmz.runtime.flowing.spi import ENV_CAPABILITIES, Limits, default_result
from hmz.runtime.flowing.viewing import (
    CALLING,
    AgentView,
    EnvView,
    Made,
    OutworlderView,
    SessionView,
    Source,
    away_answer,
    limits_of,
)


class Run:
    """What a view reaches of the run: what was derived in it."""

    def __init__(self) -> None:
        self.derived: dict[int, object] = {}


class Node:
    """The flow call a view belongs to, as far as a view asks it anything."""

    def __init__(self) -> None:
        self.run = Run()
        self.checks = 0
        self.made_here: list[tuple[str, str]] = []
        self.unmade_here: list[tuple[str, str]] = []

    def check(self) -> None:
        self.checks += 1

    def made(self, view: object, kind: str, id: str, derived: object) -> None:  # noqa: A002
        self.made_here.append((kind, id))

    def unmade(self, driver: object, kind: str, id: str) -> None:  # noqa: A002
        self.unmade_here.append((kind, id))


def _node() -> Any:
    return Node()


def _env(
    capabilities: frozenset[type] = ENV_CAPABILITIES, **files: str
) -> tuple[EnvView, Any]:
    node = _node()
    driver = FakeEnvDriver(files, run={("make",): (0, "built", "")})
    return EnvView(
        driver, Grant.of(capabilities), node, "repo", "repo=local/work"
    ), node


# ----------------------------------------------------------------------------- environments


async def test_an_env_view_says_what_its_driver_is() -> None:
    view, _ = _env()

    assert (view.backend, view.provider, view.workdir, view.role) == (
        EnvBackendKind.LOCAL,
        "",
        PurePosixPath("/work"),
        "repo",
    )
    assert (view.cpu_count, view.memory, view.gpu_count, view.gpu_memory) == (
        8,
        64 << 30,
        0,
        0,
    )
    assert view.available
    assert view.chain == "repo=local/work"
    assert isinstance(view.driver, FakeEnvDriver)
    assert repr(view) == "<env repo: repo=local/work>"


@pytest.mark.parametrize(
    ("capabilities", "doing"),
    [
        (frozenset[type](), "exec"),
        (frozenset({ShellEnvMixin}), "a script exec"),
        (frozenset({ShellEnvMixin}), "read"),
        (frozenset({ShellEnvMixin}), "write"),
        (frozenset({ShellEnvMixin}), "derive_worktree"),
        (frozenset({ShellEnvMixin}), "snapshot"),
        (frozenset({ShellEnvMixin}), "rewind"),
        (frozenset({ShellEnvMixin}), "snapshots"),
        (frozenset({ShellEnvMixin}), "derive_temp_clone"),
        (frozenset({ShellEnvMixin}), "destroy_temp_clone"),
        (frozenset({ShellEnvMixin}), "derive_scratch"),
        (frozenset({ShellEnvMixin}), "destroy_scratch"),
    ],
)
async def test_what_the_role_did_not_declare_is_not_granted(
    capabilities: frozenset[type], doing: str
) -> None:
    view, node = _env(capabilities)
    calls: dict[str, Any] = {
        "exec": lambda: view.exec(["make"]),
        "a script exec": lambda: view.exec("make"),
        "read": lambda: view.read("x"),
        "write": lambda: view.write("x", b""),
        "derive_worktree": view.derive_worktree,
        "snapshot": view.snapshot,
        "rewind": lambda: view.rewind("HEAD"),
        "snapshots": view.snapshots,
        "derive_temp_clone": lambda: view.derive_temp_clone("t"),
        "destroy_temp_clone": lambda: view.destroy_temp_clone("t"),
        "derive_scratch": lambda: view.derive_scratch("s"),
        "destroy_scratch": lambda: view.destroy_scratch("s"),
    }

    with pytest.raises(CapabilityNotGranted, match=f"repo: {doing} needs"):
        await calls[doing]()
    assert node.checks == 0


async def test_what_was_declared_is_done_by_the_driver() -> None:
    view, node = _env(
        frozenset({ShellEnvMixin, BashEnvMixin, FilesEnvMixin, GitEnvMixin}),
        a="1",
    )

    assert await view.exec(argv=("make",)) == (0, "built", "")
    assert (await view.exec(script="echo hi"))[0] == 127
    await view.write("b", b"2")
    assert await view.read("b") == b"2"
    ref = await view.snapshot("s")
    await view.rewind(ref)
    assert await view.snapshots() == [ref]
    assert node.checks == 7


@pytest.mark.parametrize(
    ("args", "named"),
    [((), {}), ((["a"], "b"), {}), ((["a"],), {"script": "b"}), ((), {"cmd": ["a"]})],
)
async def test_exec_takes_one_command(
    args: tuple[Any, ...], named: dict[str, Any]
) -> None:
    view, _ = _env()

    with pytest.raises(TypeError, match="one command"):
        await view.exec(*args, **named)


async def test_what_is_derived_is_a_view_of_the_same_role_named_by_how_it_was_derived() -> (
    None
):
    capabilities = frozenset(
        {GitWorktreeEnvMixin, TemporaryClonedDirEnvMixin, ScratchDirEnvMixin}
    )
    view, node = _env(capabilities)

    sub = await view.derive_subdir(subdir="sub")
    tree = await view.derive_worktree(ref="main")
    copy = await view.derive_temp_clone("t")
    scratch = await view.derive_scratch("s")
    await view.destroy_temp_clone("t")
    await view.destroy_scratch("s")

    assert [one.chain for one in (sub, tree, copy, scratch)] == [
        "repo=local/work#subdir(sub)",
        "repo=local/work#worktree(main,)",
        "repo=local/work#temp_clone(t)",
        "repo=local/work#scratch(s)",
    ]
    assert all(
        type(one) is EnvView and one.role == "repo"
        for one in (sub, tree, copy, scratch)
    )
    assert all(one.grant is view.grant for one in (sub, tree, copy, scratch))
    assert sub.workdir == PurePosixPath("/work/sub")
    assert len(node.run.derived) == 4
    assert node.made_here == [("temp_clone", "t"), ("scratch", "s")]
    assert node.unmade_here == [("temp_clone", "t"), ("scratch", "s")]


async def test_what_a_call_made_is_removed_when_it_is_released() -> None:
    driver = FakeEnvDriver()
    await driver.derive_temp_clone("t", holder="me")
    await driver.derive_scratch("s")

    await Made(driver, "temp_clone", "t").release()
    await Made(driver, "scratch", "s").release()

    assert (driver.clones, driver.scratches) == ([], [])


# ---------------------------------------------------------------------------------- agents


def _agent(
    capabilities: frozenset[type] = frozenset(),
    permission: Permission | None = None,
    skills: tuple[str, ...] = (),
) -> tuple[AgentView, FakeAgentDriver, Any]:
    driver = FakeAgentDriver(model="opus", effort="high", provider="work")
    node = _node()
    grant = Grant.of(capabilities, permission or Permission(), skills)
    return AgentView(driver, grant, node, "coder"), driver, node


def test_an_agent_view_says_what_its_driver_is() -> None:
    view, driver, _ = _agent()

    assert (view.harness, view.model, view.effort, view.provider, view.role) == (
        HarnessKind.CLAUDE,
        "opus",
        "high",
        "work",
        "coder",
    )
    assert view.driver is driver
    assert repr(view) == "<agent coder: claude/opus:high>"


def test_derive_narrows_and_never_widens() -> None:
    view, _, _ = _agent(
        frozenset({SteeringAgentMixin}),
        Permission(local=PermissionKind.ALL),
        ("a", "b"),
    )
    reading = Permission(local=PermissionKind.READ)

    narrowed = view.derive(permission=reading, skills=("a",))
    same = view.derive()

    assert narrowed.grant.permission == reading
    assert narrowed.grant.skills == ("a",)
    assert narrowed.grant.capabilities == view.grant.capabilities
    assert same.grant is view.grant
    with pytest.raises(CapabilityNotGranted, match="wider"):
        narrowed.derive(permission=Permission())
    with pytest.raises(CapabilityNotGranted, match="b is not among"):
        narrowed.derive(skills=("b",))
    with pytest.raises(TypeError, match="not a Permission"):
        view.derive(permission="all")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "hang",
    ["on_permission_request", "on_subagent_start", "on_subagent_stop", "on_ask_user"],
)
def test_a_hook_only_some_harnesses_reach_needs_its_mixin(hang: str) -> None:
    view, _, _ = _agent()

    async def hook(params: Any) -> Any:
        return None

    with pytest.raises(CapabilityNotGranted, match="hook needs"):
        getattr(view, hang)(hook)


async def test_a_session_is_opened_by_its_first_turn_and_owned_by_its_agent() -> None:
    view, _, node = _agent(frozenset({SteeringAgentMixin}))
    other, _, _ = _agent()

    session = await view.spawn()

    assert type(session) is SessionView
    assert (session.id, session.usage, session.agent) == (None, Usage(), view)
    assert node.checks == 1
    assert repr(session) == "<session of coder>"
    with pytest.raises(SessionError, match="no turn is in flight"):
        await view.steer("x", session=session)
    with pytest.raises(SessionError, match="taken no turn"):
        await view.fork(session)
    with pytest.raises(SessionError, match="not one of this agent's"):
        await other.fork(session)
    with pytest.raises(CapabilityNotGranted, match="steer needs"):
        await other.steer("x", session=session)


# --------------------------------------------------------------------- an agent in a run


class Plain(AgentCollection):
    coder: Agent


class Goals(AgentCollection):
    coder: ClaudeCodeAgent


class Model(AgentCollection):
    model: LiteLLMAgent


class Repo(EnvCollection):
    repo: Env


class NoEnvs(EnvCollection):
    pass


class Prompt(FlowParams):
    prompt: str = "hi"


class Fix(pydantic.BaseModel):
    done: bool = False


@flow(agents=Plain, envs=NoEnvs, params=Prompt)
async def plain(
    task: str, *, agents: Plain, envs: NoEnvs, params: Prompt, ctx: FlowContext
) -> str:
    coder = agents["coder"]
    return await coder.run(params.prompt, session=await coder.spawn())


@flow(agents=Goals, envs=Repo, params=Prompt)
async def goals(
    task: str, *, agents: Goals, envs: Repo, params: Prompt, ctx: FlowContext
) -> list[Any]:
    coder = agents["coder"]
    session = await coder.spawn()
    said: list[Any] = [await coder.run("/goal ship", session=session, env=envs["repo"])]
    said.append(await coder.run("ok", session=session, output_schema=Fix))
    fork = await coder.fork(session)
    said.append(await coder.run("branch", session=fork))
    said.append(
        cast("SessionView", session).id is not None
        and cast("SessionView", fork).id != cast("SessionView", session).id
    )
    return said


@flow(agents=Model, envs=Repo, params=Prompt)
async def model_in_env(
    task: str, *, agents: Model, envs: Repo, params: Prompt, ctx: FlowContext
) -> str:
    model = agents["model"]
    return await model.run("x", session=await model.spawn(), env=envs["repo"])


@pytest.mark.parametrize("prompt", ["/goal ship", "/loop again", "  /goal x"])
async def test_a_harness_command_needs_its_mixin_on_the_role(prompt: str) -> None:
    with pytest.raises(CapabilityNotGranted, match="needs"):
        await run_fake(plain, params={"prompt": prompt})


@pytest.mark.parametrize("prompt", ["/goals", "/help", "plain"])
async def test_what_only_looks_like_a_command_goes_as_it_is(prompt: str) -> None:
    assert (
        await run_fake(plain, agents={"coder": "fine"}, params={"prompt": prompt})
        == "fine"
    )


async def test_a_role_granted_what_it_declared_runs_forks_and_answers_its_schema() -> (
    None
):
    coder = FakeAgentDriver(reply=["shipped", {"done": True}, "branched"])

    said = await run_fake(goals, agents={"coder": coder})

    assert said == ["shipped", Fix(done=True), "branched", True]
    assert coder.prompts == ["/goal ship", "ok", "/goal ship", "ok", "branch"]
    first = coder.sessions[0].placements[0]
    assert (first.workdir, first.env) == (PurePosixPath("/repo"), "repo")
    assert coder.sessions[0].placement.workdir == PurePosixPath("/here"), (
        "the run's own"
    )


async def test_a_model_called_directly_works_in_no_environment() -> None:
    with pytest.raises(UnsupportedOperation, match="litellm"):
        await run_fake(model_in_env)


class Hooked(AgentCollection):
    coder: ClaudeCodeAgent


@flow(agents=Hooked, envs=NoEnvs, params=Prompt)
async def hooked(
    task: str, *, agents: Hooked, envs: NoEnvs, params: Prompt, ctx: FlowContext
) -> list[str]:
    coder = agents["coder"]
    heard: list[str] = []

    def hearing(kind: HookKind) -> Any:
        async def hook(params: Any) -> Any:
            heard.append(kind)
            return default_result(kind)

        return hook

    hangs: dict[HookKind, Any] = {
        HookKind.SESSION_START: coder.on_session_start,
        HookKind.USER_PROMPT_SUBMIT: coder.on_user_prompt_submit,
        HookKind.STOP: coder.on_stop,
        HookKind.SESSION_END: coder.on_session_end,
        HookKind.PERMISSION_REQUEST: coder.on_permission_request,
    }
    for kind, hang in hangs.items():
        hang(hearing(kind))
    session = await coder.spawn()
    await coder.run("one", session=session)
    for hang in hangs.values():
        hang(None)
    await coder.run("two", session=session)
    return heard


async def test_a_hook_is_heard_while_it_is_hung_and_not_once_taken_down() -> None:
    assert await run_fake(hooked) == [
        HookKind.SESSION_START,
        HookKind.USER_PROMPT_SUBMIT,
        HookKind.STOP,
    ]


# ----------------------------------------------------------------------------- outworlders


class Away(pydantic.BaseModel):
    note: str = "none"


class Required(pydantic.BaseModel):
    note: str


async def test_the_runs_outworlder_answers_as_the_role_it_was_filled_for() -> None:
    person = FakeOutworlder(["yes", {"note": "n"}])
    view = OutworlderView(
        Source(person, made=False, node=None), None, "reviewer", "lead"
    )

    session = await view.spawn()

    assert (view.role, view.harness, view.model, view.away) == (
        "reviewer",
        HarnessKind.ACP,
        "",
        False,
    )
    assert (session.id, session.usage) == (None, Usage())
    assert await view.run("ok?", session=session) == "yes"
    assert await view.run("why?", session=session, output_schema=Away) == Away(note="n")
    assert view.derive() is view
    with pytest.raises(CapabilityNotGranted, match="no skills"):
        view.derive(skills=("x",))
    with pytest.raises(UnsupportedOperation):
        await view.fork(session)
    with pytest.raises(CapabilityNotGranted, match=r"Outworlder\.new"):
        view.on_outworlder_run(None)


async def test_an_away_outworlder_answers_for_itself() -> None:
    view = OutworlderView(
        Source(FakeOutworlder(away=True), made=False, node=None), None, "r"
    )
    nobody = OutworlderView(Source(None, made=False, node=None), None, "r")
    session = await view.spawn()

    assert view.away
    assert nobody.away
    assert await view.run("x", session=session) == ""
    assert await view.run("x", session=session, output_schema=Away) == Away()
    with pytest.raises(OutworlderAway):
        await view.run("x", session=session, output_schema=Required)


async def test_a_session_of_another_outworlder_is_refused() -> None:
    one = OutworlderView(Source(FakeOutworlder(), made=False, node=None), None, "a")
    other = OutworlderView(Source(FakeOutworlder(), made=False, node=None), None, "b")

    with pytest.raises(SessionError, match="not one of this outworlder's"):
        await one.run("x", session=await other.spawn())


async def test_an_outworlder_a_flow_made_is_answered_by_its_hook() -> None:
    made = OutworlderView.new()
    session = await made.spawn()

    assert made.away
    assert await made.run("x", session=session) == ""

    async def answer(params: Any) -> OutworlderRunHookResult:
        return OutworlderRunHookResult(output=f"re: {params.prompt}")

    made.on_outworlder_run(answer)

    assert not made.away
    assert await made.run("x", session=session) == "re: x"
    with pytest.raises(OutputSchemaError):
        await made.run("x", session=session, output_schema=Required)


def test_no_flow_call_is_running_outside_one() -> None:
    assert CALLING.get() is None


# ------------------------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    ("args", "limits"),
    [
        (
            (float("inf"), float("inf"), float("inf")),
            Limits(None, None, None, graceful=True),
        ),
        ((1.5, 10.0, 99.0), Limits(1.5, 10, 99.0, graceful=True)),
        ((-1.0, -3.0, 5.0), Limits(0.0, 0, 5.0, graceful=True)),
    ],
    ids=["unlimited", "limits", "overspent"],
)
def test_a_turn_is_told_its_limits_with_infinity_as_none(
    args: tuple[float, float, float], limits: Limits
) -> None:
    assert limits_of(*args, graceful=True) == limits
    assert not limits_of(*args, graceful=False).graceful


def test_an_away_answer_is_empty_text_or_the_schemas_defaults() -> None:
    assert away_answer(None) == ""
    assert away_answer(Away) == Away()
    with pytest.raises(OutworlderAway, match="no default"):
        away_answer(Required)
