"""The fakes a flow is tested on: they behave as their docstrings say a real driver does."""

from __future__ import annotations

import asyncio
import time
from pathlib import PurePosixPath
from typing import Any

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    AskUserHookResult,
    ClaudeCodeAgent,
    CodexAgent,
    CostExceeded,
    CPUEnvMixin,
    DurationExceeded,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvCommandTimeout,
    EnvFileNotFound,
    FlowContext,
    FlowParams,
    GPUEnvMixin,
    HarnessKind,
    HookKind,
    OutputSchemaError,
    OutputTokensExceeded,
    Outworlder,
    Permission,
    PermissionRequestHookResult,
    PreToolUseHookResult,
    RewindError,
    SessionError,
    SessionStartHookResult,
    ShellEnvMixin,
    StopHookResult,
    SubagentStopHookResult,
    TempCloneBusy,
    UnsupportedOperation,
    UserPromptSubmitHookResult,
    WorktreeError,
    flow,
)
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    FakeSession,
    run_fake,
)
from hmz.runtime.flowing.spi import (
    ENV_CAPABILITIES,
    HARNESS_CAPABILITIES,
    HookTable,
    Limits,
    Placement,
    SessionHandle,
    TurnRequest,
)
from tests.unit.runtime.flowing.doubles_u11 import until

HERE = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/work"))


class Sink:
    """Where a turn says what it spent."""

    def __init__(self) -> None:
        self.added: list[tuple[float, int, float]] = []

    def add(self, *, cost: float, output_tokens: int, duration: float) -> None:
        self.added.append((cost, output_tokens, duration))


async def _open(
    driver: FakeAgentDriver,
    hooks: HookTable | None = None,
    placement: Placement = HERE,
    fork_of: Any = None,
) -> FakeSession:
    return await driver.open(
        placement,
        permission=Permission(),
        skills=(),
        hooks=hooks or HookTable(),
        fork_of=fork_of,
    )


async def _turn(driver: FakeAgentDriver, prompt: str = "hi", schema: Any = None) -> Any:
    return await (await _open(driver)).turn(TurnRequest(prompt, schema), Sink())


# ---------------------------------------------------------------------------------- agents


def test_a_fake_agent_is_its_harness_unless_told_otherwise() -> None:
    codex = FakeAgentDriver("codex", model="gpt", effort="high", provider="work")
    bare = FakeAgentDriver(capabilities=())

    assert codex.harness is HarnessKind.CODEX
    assert codex.capabilities == HARNESS_CAPABILITIES[HarnessKind.CODEX]
    assert (codex.model, codex.effort, codex.provider) == ("gpt", "high", "work")
    assert bare.capabilities == frozenset()
    assert "codex/gpt" in repr(codex)


class Answer(pydantic.BaseModel):
    answer: str = "default"


class Strict(pydantic.BaseModel):
    n: int


def _upper(prompt: str, **_: Any) -> str:
    return prompt.upper()


async def _later(prompt: str, **_: Any) -> str:
    return f"later {prompt}"


@pytest.mark.parametrize(
    ("reply", "schema", "said"),
    [
        (None, None, "ok"),
        (None, Answer, Answer()),
        ("constant", None, "constant"),
        (Answer(answer="x"), None, '{"answer":"x"}'),
        (Answer(answer="x"), Answer, Answer(answer="x")),
        ({"n": 3}, Strict, Strict(n=3)),
        ({"n": 3}, None, '{"n": 3}'),
        ('{"n": 4}', Strict, Strict(n=4)),
        (_upper, None, "HI"),
        (_later, None, "later hi"),
        (["first", "second"], None, "first"),
        ([], None, "ok"),
    ],
    ids=[
        "default",
        "default-schema",
        "constant",
        "model-as-text",
        "model",
        "mapping",
        "mapping-as-text",
        "json",
        "function",
        "async-function",
        "queue",
        "empty-queue",
    ],
)
async def test_a_turn_answers_from_its_script(
    reply: Any, schema: Any, said: Any
) -> None:
    assert await _turn(FakeAgentDriver(reply=reply), "hi", schema) == said


@pytest.mark.parametrize(
    ("reply", "schema"),
    [(None, Strict), ({"n": "x"}, Strict), ("not json", Strict)],
    ids=["no-default", "wrong-field", "not-json"],
)
async def test_an_answer_that_is_no_instance_of_its_schema_is_an_output_schema_error(
    reply: Any, schema: Any
) -> None:
    with pytest.raises(OutputSchemaError):
        await _turn(FakeAgentDriver(reply=reply), "hi", schema)


async def test_a_queue_is_answered_in_order_then_by_default() -> None:
    driver = FakeAgentDriver(reply=["one", "two"])
    session = await _open(driver)

    said = [await session.turn(TurnRequest(str(n)), Sink()) for n in range(3)]

    assert said == ["one", "two", "ok"]
    assert driver.prompts == ["0", "1", "2"]
    assert session.turns == 3


async def test_a_turn_spends_what_it_is_told_through_the_sink() -> None:
    driver = FakeAgentDriver(cost=0.5, output_tokens=7, seconds=2.0)
    session = await _open(driver)
    sink = Sink()

    await session.turn(TurnRequest("a"), sink)
    await session.turn(TurnRequest("b"), sink)

    assert sink.added == [(0.5, 7, 2.0), (0.5, 7, 2.0)]
    assert (session.usage.cost, session.usage.output_tokens) == (1.0, 14)
    assert session.usage.duration.total_seconds() == 4.0


@pytest.mark.parametrize(
    ("limits", "kind", "spent"),
    [
        (Limits(cost=0.1, graceful=False), CostExceeded, (0.1, 7)),
        (Limits(output_tokens=3, graceful=False), OutputTokensExceeded, (0.5, 3)),
        (Limits(deadline=0.0, graceful=False), DurationExceeded, (0, 0)),
        (Limits(cost=0.1, graceful=True), None, (0.5, 7)),
    ],
    ids=["cost", "tokens", "deadline", "graceful"],
)
async def test_a_hard_limit_stops_a_turn_at_it(
    limits: Limits, kind: type[Exception] | None, spent: tuple[float, int]
) -> None:
    session = await _open(FakeAgentDriver(cost=0.5, output_tokens=7))
    sink = Sink()

    if kind is None:
        await session.turn(TurnRequest("x", limits=limits), sink)
    else:
        with pytest.raises(kind):
            await session.turn(TurnRequest("x", limits=limits), sink)

    assert [(cost, tokens) for cost, tokens, _ in sink.added] == [spent]


async def test_a_hard_deadline_cuts_off_a_turn_its_answer_holds_open() -> None:
    async def forever(prompt: str, *, session: FakeSession, **_: Any) -> str:
        return await session.until_steered()

    session = await _open(FakeAgentDriver(reply=forever))
    limits = Limits(deadline=time.monotonic() + 0.01, graceful=False)

    with pytest.raises(DurationExceeded):
        await session.turn(TurnRequest("x", limits=limits), Sink())


async def test_a_turn_held_open_goes_on_with_what_it_is_steered_with() -> None:
    async def held_open(prompt: str, *, session: FakeSession, **_: Any) -> str:
        return await session.until_steered()

    session = await _open(FakeAgentDriver(reply=held_open))
    turning = asyncio.ensure_future(session.turn(TurnRequest("x"), Sink()))
    await until(lambda: session.turns > 0)
    await asyncio.sleep(0)

    await session.steer("go on", queued=True)

    assert await turning == "go on"
    assert session.steered == [("go on", True)]
    with pytest.raises(SessionError, match="not taking a turn"):
        await session.steer("late", queued=False)


async def test_a_session_that_never_took_a_turn_waits_on_no_steer() -> None:
    session = await _open(FakeAgentDriver())

    with pytest.raises(SessionError, match="not taking a turn"):
        await session.until_steered()


async def test_an_interrupted_turn_is_a_session_error() -> None:
    async def held_open(prompt: str, *, session: FakeSession, **_: Any) -> str:
        return await session.until_steered()

    session = await _open(FakeAgentDriver(reply=held_open))
    turning = asyncio.ensure_future(session.turn(TurnRequest("x"), Sink()))
    await until(lambda: session.turns > 0)
    await asyncio.sleep(0)

    session.interrupt()

    with pytest.raises(SessionError, match="interrupted"):
        await turning


async def test_a_turn_fires_the_hooks_a_real_session_would() -> None:
    hooks = HookTable()
    fired: list[tuple[HookKind, dict[str, Any]]] = []

    def hang(kind: HookKind, result: Any) -> None:
        async def hook(handle: SessionHandle, fields: dict[str, Any]) -> Any:
            fired.append((kind, fields))
            return result(fields) if callable(result) else result

        hooks.set(kind, hook)

    hang(HookKind.SESSION_START, SessionStartHookResult(context="ctx"))
    hang(HookKind.USER_PROMPT_SUBMIT, UserPromptSubmitHookResult(context="more"))

    def stopping(fields: dict[str, Any]) -> StopHookResult:
        return StopHookResult(block=fields["again"] == 0, reason="again")

    hang(HookKind.STOP, stopping)
    hang(HookKind.SESSION_END, None)
    driver = FakeAgentDriver(reply=_upper)
    session = await _open(driver, hooks)

    said = await session.turn(TurnRequest("p"), Sink())
    await session.turn(TurnRequest("q"), Sink())
    await session.close()
    await session.close()

    assert said == "AGAIN"
    assert session.prompts == ["ctx\n\np\n\nmore", "again", "q\n\nmore", "again"]
    kinds = [kind for kind, _ in fired]
    assert kinds.count(HookKind.SESSION_START) == 1
    assert kinds.count(HookKind.SESSION_END) == 1
    assert kinds.count(HookKind.STOP) == 4
    assert (session.closed, driver.live) == (True, 0)


async def test_a_prompt_a_hook_refused_is_never_answered() -> None:
    hooks = HookTable()

    async def refuse(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return UserPromptSubmitHookResult(block=True, reason="no")

    hooks.set(HookKind.USER_PROMPT_SUBMIT, refuse)
    session = await _open(FakeAgentDriver(), hooks)

    with pytest.raises(SessionError, match="refused the prompt: no"):
        await session.turn(TurnRequest("x"), Sink())
    assert (session.turns, session.prompts, session.named) == (1, [], False)


async def test_what_an_answer_reaches_for_goes_through_the_hooks() -> None:
    hooks = HookTable()

    async def pre(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return PreToolUseHookResult(block=fields["tool"] == "rm")

    async def permit(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return PermissionRequestHookResult(allow=fields["tool"] != "push")

    async def ask(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return AskUserHookResult(answer=f"{fields['question']} yes")

    async def sub(handle: SessionHandle, fields: dict[str, Any]) -> Any:
        return SubagentStopHookResult(block=True, reason="keep going")

    for kind, hook in [
        (HookKind.PRE_TOOL_USE, pre),
        (HookKind.PERMISSION_REQUEST, permit),
        (HookKind.ASK_USER, ask),
        (HookKind.SUBAGENT_STOP, sub),
    ]:
        hooks.set(kind, hook)
    reached: dict[str, Any] = {}

    async def busy(prompt: str, *, session: FakeSession, **_: Any) -> str:
        reached["tools"] = [
            await session.tool("ls"),
            await session.tool("rm", {"path": "/"}),
            await session.tool("push"),
        ]
        reached["asked"] = await session.ask("ok?", ["yes", "no"])
        reached["sub"] = await session.subagent("explorer", "look", "found")
        await session.notify("note")
        return "done"

    session = await _open(FakeAgentDriver(reply=busy), hooks)
    await session.turn(TurnRequest("x"), Sink())

    assert reached == {
        "tools": [True, False, False],
        "asked": "ok? yes",
        "sub": "keep going",
    }
    assert session.tools == [
        ("ls", {}, True),
        ("rm", {"path": "/"}, False),
        ("push", {}, False),
    ]


async def test_a_harness_that_cannot_ask_its_user_refuses_to() -> None:
    async def asks(prompt: str, *, session: FakeSession, **_: Any) -> Any:
        return await session.ask("?")

    with pytest.raises(UnsupportedOperation, match="does not ask"):
        await _turn(FakeAgentDriver(capabilities=(), reply=asks))


async def test_a_session_takes_one_turn_at_a_time_and_none_once_closed() -> None:
    async def held_open(prompt: str, *, session: FakeSession, **_: Any) -> str:
        return await session.until_steered()

    driver = FakeAgentDriver(reply=held_open)
    session = await _open(driver)
    turning = asyncio.ensure_future(session.turn(TurnRequest("x"), Sink()))
    await until(lambda: session.turns > 0)

    with pytest.raises(SessionError, match="already"):
        await session.turn(TurnRequest("y"), Sink())
    await session.close()
    with pytest.raises(SessionError):
        await turning
    with pytest.raises(SessionError, match="closed"):
        await session.turn(TurnRequest("z"), Sink())
    with pytest.raises(SessionError, match="closed"):
        await session.move(HERE)


async def test_a_session_is_named_as_its_first_turn_goes_where_the_cli_names_late() -> (
    None
):
    late = await _open(FakeAgentDriver(names_late=True))
    early = await _open(FakeAgentDriver())

    assert late.id is None
    assert early.id is not None
    await late.turn(TurnRequest("x"), Sink())
    assert late.id is not None


async def test_the_driver_counts_its_sessions_and_closes_them_all() -> None:
    driver = FakeAgentDriver()
    one, two = await _open(driver), await _open(driver)
    await one.close()
    await _open(driver)

    await driver.close()

    assert (driver.peak, driver.live, driver.closed) == (2, 0, 1)
    assert driver.sessions[1] is two
    assert all(session.closed for session in driver.sessions)


# ---------------------------------------------------------------------------------- forks


async def test_a_session_forks_once_it_has_taken_a_turn() -> None:
    driver = FakeAgentDriver(reply=_upper)
    parent = await _open(driver)

    with pytest.raises(SessionError, match="no turn"):
        await _open(driver, fork_of=parent)
    await parent.turn(TurnRequest("a"), Sink())
    fork = await _open(driver, fork_of=parent)
    await fork.turn(TurnRequest("b"), Sink())

    assert fork.forked_from is parent
    assert fork.prompts == ["a", "b"]
    with pytest.raises(SessionError, match="not a session of this agent"):
        await _open(FakeAgentDriver(), fork_of=parent)


async def test_a_fork_is_refused_at_its_first_turn_if_its_parent_moved_on() -> None:
    driver = FakeAgentDriver()
    parent = await _open(driver)
    await parent.turn(TurnRequest("a"), Sink())
    fork = await _open(driver, fork_of=parent)
    await parent.turn(TurnRequest("b"), Sink())

    with pytest.raises(SessionError, match="taken a turn since"):
        await fork.turn(TurnRequest("c"), Sink())


@pytest.mark.parametrize(
    ("harness", "forks", "placement", "why"),
    [
        (HarnessKind.CURSOR_AGENT, None, HERE, "cannot fork"),
        (HarnessKind.CLAUDE, False, HERE, "cannot fork"),
        (
            HarnessKind.CLAUDE,
            None,
            Placement(EnvBackendKind.SSH, "box", PurePosixPath("/work")),
            "onto another machine",
        ),
        (
            HarnessKind.OPENCODE,
            None,
            Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/elsewhere")),
            "into another workdir",
        ),
    ],
    ids=["unforked-harness", "told-not-to", "other-machine", "in-place-only"],
)
async def test_a_fork_a_harness_could_not_make_is_unsupported(
    harness: HarnessKind, forks: bool | None, placement: Placement, why: str
) -> None:
    driver = FakeAgentDriver(harness, forks=forks)
    parent = await _open(driver)
    await parent.turn(TurnRequest("a"), Sink())

    with pytest.raises(UnsupportedOperation, match=why):
        await _open(driver, placement=placement, fork_of=parent)


async def test_a_session_moves_where_its_harness_can_carry_it() -> None:
    elsewhere = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/elsewhere"))
    claude = await _open(FakeAgentDriver())
    opencode = await _open(FakeAgentDriver(HarnessKind.OPENCODE))
    fresh = await _open(FakeAgentDriver(HarnessKind.OPENCODE))
    for one in (claude, opencode):
        await one.turn(TurnRequest("a"), Sink())
    named = claude.id

    assert not await claude.move(HERE)
    assert await claude.move(elsewhere)
    assert claude.id != named
    assert claude.placements == [HERE, elsewhere]
    with pytest.raises(UnsupportedOperation):
        await opencode.move(elsewhere)
    assert await fresh.move(elsewhere), "nothing to carry: started afresh there"


# ---------------------------------------------------------------------------- environments


def test_a_fake_env_says_where_it_is_and_what_it_has() -> None:
    env = FakeEnvDriver(
        {"a.txt": "hi", "b/c": b"\x00"},
        workdir="/repo",
        backend="ssh",
        provider="box",
        gpu_count=2,
    )

    assert env.placement() == Placement(
        EnvBackendKind.SSH, "box", PurePosixPath("/repo")
    )
    assert env.files == {"a.txt": b"hi", "b/c": b"\x00"}
    assert env.text("a.txt") == "hi"
    assert env.capabilities == ENV_CAPABILITIES
    assert (env.cpu_count, env.gpu_count, env.available) == (8, 2, True)


@pytest.mark.parametrize(
    ("command", "said"),
    [
        (["true"], (0, "", "")),
        ([":"], (0, "", "")),
        (["false"], (1, "", "")),
        (["echo", "a", "b"], (0, "a b\n", "")),
        (["cat", "a.txt"], (0, "hi", "")),
        (["cat", "a.txt", "nope"], (1, "hi", "cat: nope: No such file or directory\n")),
        (["ls"], (0, "a.txt\nsub\n", "")),
        (["ls", "sub"], (0, "x\n", "")),
        (["git", "rev-parse", "--is-inside-work-tree"], (0, "true\n", "")),
        (["make"], (127, "", "fake: make: command not found\n")),
        (
            "echo hi",
            (127, "", "fake: scripts are answered by `run=`, not interpreted\n"),
        ),
    ],
    ids=str,
)
async def test_a_few_commands_are_answered_by_default(command: Any, said: Any) -> None:
    env = FakeEnvDriver({"a.txt": "hi", "sub/x": ""})

    assert await env.exec(command, timeout=0) == said


async def test_commands_are_answered_by_a_table_or_a_function_first() -> None:
    table = FakeEnvDriver(run={("make",): (0, "built", ""), "echo hi": (0, "hi\n", "")})

    async def answering(command: Any, env: FakeEnvDriver) -> Any:
        return (2, "", "no") if command == ("make",) else None

    function = FakeEnvDriver(run=answering)

    assert await table.exec(["make"], timeout=0) == (0, "built", "")
    assert await table.exec("echo hi", timeout=0) == (0, "hi\n", "")
    assert await function.exec(["make"], timeout=0) == (2, "", "no")
    assert await function.exec(["true"], timeout=0) == (0, "", "")
    assert table.commands == [("make",), "echo hi"]


async def test_a_command_past_its_timeout_says_so() -> None:
    with pytest.raises(EnvCommandTimeout):
        await FakeEnvDriver().exec(["sleep", "5"], timeout=0.01)


async def test_a_fake_repository_is_not_one_where_told() -> None:
    env = FakeEnvDriver(repo=False)

    assert (await env.exec(["git", "rev-parse", "--is-inside-work-tree"], timeout=0))[
        0
    ] == 128
    for doing in (env.snapshot(None), env.rewind("HEAD"), env.snapshots()):
        with pytest.raises(RewindError):
            await doing
    with pytest.raises(WorktreeError):
        await env.derive_worktree(ref=None, dir=None)


async def test_files_are_read_and_written_under_the_workdir() -> None:
    env = FakeEnvDriver()

    await env.write("a/b", b"x")

    assert await env.read("a/b") == b"x"
    assert env.machine == {"/work/a/b": b"x"}
    with pytest.raises(EnvFileNotFound):
        await env.read("missing")


async def test_a_subdirectory_shares_the_machine_and_stays_under_the_workdir() -> None:
    env = FakeEnvDriver()
    sub = await env.derive_subdir("sub")

    await sub.write("x", b"1")

    assert env.files == {"sub/x": b"1"}
    for outside in ("/abs", "../up"):
        with pytest.raises(ValueError, match="not under"):
            await env.derive_subdir(outside)


async def test_a_worktree_is_a_copy_at_a_known_ref_in_a_free_place() -> None:
    env = FakeEnvDriver({"a": "1"}, refs=("HEAD", "main"))

    tree = await env.derive_worktree(ref="main", dir=None)
    told = await env.derive_worktree(ref=None, dir="/elsewhere")

    assert tree.files == told.files == {"a": b"1"}
    assert told.workdir == PurePosixPath("/elsewhere")
    with pytest.raises(WorktreeError, match="no ref"):
        await env.derive_worktree(ref="nope", dir=None)
    with pytest.raises(WorktreeError, match="taken"):
        await env.derive_worktree(ref=None, dir="/elsewhere")


async def test_a_snapshot_is_rewound_to_and_a_ref_is_the_files_it_began_with() -> None:
    env = FakeEnvDriver({"a": "1", ".hmz/state": "kept"})
    await env.write("a", b"2")
    ref = await env.snapshot("two")
    await env.write("a", b"3")
    await env.write("new", b"x")

    await env.rewind(ref)
    assert env.files == {"a": b"2", ".hmz/state": b"kept"}
    await env.rewind("HEAD")
    assert env.files == {"a": b"1", ".hmz/state": b"kept"}
    assert await env.snapshots() == ["refs/hmz/snapshots/two"]
    assert (await env.snapshot(None)).startswith("refs/hmz/snapshots/")
    with pytest.raises(RewindError, match="no ref"):
        await env.rewind("nope")


async def test_a_temporary_copy_is_its_holders_until_the_run_that_took_it_closes() -> (
    None
):
    env = FakeEnvDriver({"a": "1"})

    copy = await env.derive_temp_clone("t", holder="me")
    again = await env.derive_temp_clone("t", holder="me")
    with pytest.raises(TempCloneBusy):
        await env.derive_temp_clone("t", holder="you")
    await copy.write("a", b"changed")
    await env.close()
    resumed = await env.derive_temp_clone("t", holder="you")

    assert again is copy
    assert resumed.files == {"a": b"changed"}, "taken again as it was left"
    assert env.clones == ["t"]
    await env.destroy_temp_clone("t")
    await env.destroy_temp_clone("t")
    assert env.clones == []
    assert not any("/clones/" in path for path in env.machine)


async def test_closing_a_copy_lets_go_of_its_hold() -> None:
    env = FakeEnvDriver()
    copy = await env.derive_temp_clone("t", holder="me")

    await copy.close()

    assert (await env.derive_temp_clone("t", holder="you")).workdir == copy.workdir


async def test_a_scratch_directory_is_one_per_id_until_removed() -> None:
    env = FakeEnvDriver()

    one = await env.derive_scratch("s")
    await one.write("x", b"1")

    assert await env.derive_scratch("s") is one
    assert env.scratches == ["s"]
    await env.destroy_scratch("s")
    await env.destroy_scratch("s")
    assert env.scratches == []
    assert env.machine == {}


# ----------------------------------------------------------------------------- outworlders


async def test_a_fake_outworlder_answers_from_its_script_or_is_away() -> None:
    here = FakeOutworlder(["yes", Answer(answer="a")])
    away = FakeOutworlder(away=True)

    assert await here.run("ok?", None) == "yes"
    assert await here.run("which?", Answer, "reviewer") == Answer(answer="a")
    assert here.asked == ["ok?", "which?"]
    assert not here.away_for("anyone")
    assert away.away_for("anyone")


# ----------------------------------------------------------------------------------- a run


class Big(Env, CPUEnvMixin, GPUEnvMixin):
    _cpu_count = 128
    _gpu_count = 4
    _gpu_memory = 1 << 36


class Wants(AgentCollection):
    claude: ClaudeCodeAgent
    codex: CodexAgent
    plain: Agent
    human: Outworlder


class Places(EnvCollection):
    big: Big


class Nothing(FlowParams):
    pass


@flow(agents=Wants, envs=Places, params=Nothing)
async def wanting(
    task: str, *, agents: Wants, envs: Places, params: Nothing, ctx: FlowContext
) -> list[Any]:
    human = agents["human"]
    session = await human.spawn()
    big = envs["big"]
    return [
        agents["claude"].harness,
        agents["codex"].harness,
        agents["plain"].harness,
        big.workdir,
        await human.run("ok?", session=session),
    ]


async def test_run_fake_fills_every_role_with_a_fake_of_what_it_asks_for() -> None:
    said = await run_fake(wanting, agents={"human": "sure"})

    assert said == [
        HarnessKind.CLAUDE,
        HarnessKind.CODEX,
        HarnessKind.CLAUDE,
        PurePosixPath("/big"),
        "sure",
    ]


class Coding(AgentCollection):
    coder: Agent


class Shell(Env, ShellEnvMixin): ...


class Shelling(EnvCollection):
    repo: Shell


@flow(agents=Coding, envs=Shelling, params=Nothing)
async def coding(
    task: str, *, agents: Coding, envs: Shelling, params: Nothing, ctx: FlowContext
) -> tuple[str, tuple[int, str, str]]:
    coder = agents["coder"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=envs["repo"])
    return said, await envs["repo"].exec(["cat", "README.md"])


async def test_run_fake_runs_on_the_drivers_and_files_it_is_given() -> None:
    coder = FakeAgentDriver(reply=_upper)

    said = await run_fake(
        coding, "fix", agents={"coder": coder}, envs={"repo": {"README.md": "hi"}}
    )

    assert said == ("FIX", (0, "hi", ""))
    assert coder.prompts == ["fix"]
    assert coder.sessions[0].placement.workdir == PurePosixPath("/repo")


async def test_run_fake_answers_a_role_with_what_it_is_told_to_reply() -> None:
    said = await run_fake(coding, "fix", agents={"coder": "patched"})

    assert said[0] == "patched"
