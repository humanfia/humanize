"""The fake kit: drivers in memory that keep every promise a real one does.

Flowverse's tests and the engine's own run flows on these, so they are held to the same
contract checks as the real drivers, and what they add for a test -- scripts, defaults, the
moments a scripted answer can reach -- is checked here.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import pydantic
import pytest

from hmz.flows import (
    Agent,
    AgentCollection,
    ClaudeCodeAgent,
    CodexAgent,
    CPUEnvMixin,
    Env,
    EnvBackendKind,
    EnvCollection,
    EnvCommandTimeout,
    FlowContext,
    FlowParams,
    GPUEnvMixin,
    HarnessKind,
    OutputSchemaError,
    Outworlder,
    Permission,
    RewindError,
    SessionError,
    TempCloneBusy,
    UnsupportedOperation,
    WorktreeError,
    flow,
)
from hmz.runtime.flowing.fakes import (
    FakeAgentDriver,
    FakeEnvDriver,
    FakeOutworlder,
    run_fake,
)
from hmz.runtime.flowing.spi import (
    HARNESS_CAPABILITIES,
    HookTable,
    Placement,
    TurnRequest,
)
from tests.flows.contracts import (
    ANSWERS,
    Answer,
    RecordingSink,
    check_agent_driver,
    check_env_driver,
)


def _upper(prompt: str, **_: Any) -> str:
    return prompt.upper()


PLACED = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/work"))
QUICK = 0.02
SLOW = "count to a million, slowly"


async def _slow(prompt: str, *, session: Any, output_schema: Any) -> Any:
    if prompt == SLOW:
        return await session.until_steered()
    return None


@pytest.mark.parametrize("harness", sorted(HARNESS_CAPABILITIES))
async def test_a_fake_agent_of_every_harness_keeps_the_contract(
    harness: HarnessKind,
) -> None:
    driver = FakeAgentDriver(harness, reply=_slow)
    await check_agent_driver(driver, PLACED, slow_prompt=SLOW, settle=QUICK)
    assert driver.closed == 2


async def test_a_fake_agent_that_cannot_fork_keeps_the_contract() -> None:
    await check_agent_driver(FakeAgentDriver(forks=False), PLACED, settle=QUICK)


async def test_a_fake_env_keeps_the_contract() -> None:
    env = FakeEnvDriver(run=ANSWERS)
    await check_env_driver(env, repo=True, settle=QUICK)
    assert env.closed == 2


async def test_a_fake_env_serving_nothing_keeps_the_contract() -> None:
    await check_env_driver(FakeEnvDriver(capabilities=()), settle=QUICK)


# ------------------------------------------------------------------------- the agents


async def _turn(driver: FakeAgentDriver, prompt: str, schema: Any = None) -> Any:
    session = await driver.open(
        PLACED, permission=Permission(), skills=(), hooks=HookTable()
    )
    return await session.turn(TurnRequest(prompt, schema), RecordingSink())


class Strict(pydantic.BaseModel):
    n: int


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
        (["first"], None, "first"),
        ([], None, "ok"),
    ],
    ids=[
        "default",
        "default schema",
        "constant",
        "model as text",
        "model",
        "mapping",
        "mapping as text",
        "json",
        "function",
        "queue",
        "empty queue",
    ],
)
async def test_a_fake_agent_answers_from_its_script(
    reply: Any, schema: Any, said: Any
) -> None:
    assert await _turn(FakeAgentDriver(reply=reply), "hi", schema) == said


async def test_a_fake_agent_takes_its_script_in_order() -> None:
    driver = FakeAgentDriver(reply=["a", "b"])
    session = await driver.open(
        PLACED, permission=Permission(), skills=(), hooks=HookTable()
    )
    sink = RecordingSink()
    said = [await session.turn(TurnRequest(str(n)), sink) for n in range(3)]
    assert said == ["a", "b", "ok"]
    assert driver.prompts == ["0", "1", "2"]


async def test_a_fake_agent_refuses_a_schema_it_has_no_answer_for() -> None:
    with pytest.raises(OutputSchemaError):
        await _turn(FakeAgentDriver(), "hi", Strict)
    with pytest.raises(OutputSchemaError):
        await _turn(FakeAgentDriver(reply={"n": "x"}), "hi", Strict)


async def test_a_fake_session_reaches_only_what_its_harness_serves() -> None:
    driver = FakeAgentDriver(HarnessKind.OPENCODE)
    session = await driver.open(
        PLACED, permission=Permission(), skills=(), hooks=HookTable()
    )
    with pytest.raises(UnsupportedOperation):
        await session.ask("which?")
    assert await session.tool("ls") is True
    assert await session.subagent("x", said="y") == "y"
    other = await FakeAgentDriver().open(
        PLACED, permission=Permission(), skills=(), hooks=HookTable()
    )
    with pytest.raises(SessionError):
        await driver.open(
            PLACED, permission=Permission(), skills=(), hooks=HookTable(), fork_of=other
        )
    await session.close()
    with pytest.raises(SessionError):
        await driver.open(
            PLACED,
            permission=Permission(),
            skills=(),
            hooks=HookTable(),
            fork_of=session,
        )
    with pytest.raises(SessionError):
        await session.until_steered()


async def _opened(driver: FakeAgentDriver, fork_of: Any = None) -> Any:
    return await driver.open(
        PLACED, permission=Permission(), skills=(), hooks=HookTable(), fork_of=fork_of
    )


#: The harnesses a fake forks on by default, which are the ones a real CLI forks on.
FORKING = sorted(kind for kind in HARNESS_CAPABILITIES if FakeAgentDriver(kind).forks)


def test_a_fake_forks_where_its_harness_does() -> None:
    from hmz.coganchor import agents, backends
    from hmz.coganchor.agents.base import SessionBase
    from hmz.runtime.flowing import fakes

    for kind in HARNESS_CAPABILITIES:
        profile = backends.named(kind.value)
        if profile is not None:
            assert FakeAgentDriver(kind).forks is profile.forks, kind
    assert FakeAgentDriver(HarnessKind.CURSOR_AGENT, forks=True).forks
    del agents  # imported for every backend's sessions to be among the subclasses below
    classes: list[type[SessionBase]] = [SessionBase]
    elsewhere: set[str] = set()
    while classes:
        one = classes.pop()
        classes.extend(one.__subclasses__())
        if one.forks_elsewhere:
            elsewhere.add(one.__module__.rpartition(".")[2])
    assert elsewhere == set(fakes._FORKS_ELSEWHERE)


@pytest.mark.parametrize("harness", FORKING)
async def test_a_fake_session_with_no_turn_has_nothing_to_fork(
    harness: HarnessKind,
) -> None:
    driver = FakeAgentDriver(harness)
    parent = await _opened(driver)
    with pytest.raises(SessionError):
        await _opened(driver, parent)
    # Nor does a fork that has taken no turn of its own.
    await parent.turn(TurnRequest("one"), RecordingSink())
    child = await _opened(driver, parent)
    with pytest.raises(SessionError):
        await _opened(driver, child)
    await child.turn(TurnRequest("two"), RecordingSink())
    assert await _opened(driver, child) is not None
    # Refused for that before it is refused for the harness, as a real driver refuses it.
    lone = FakeAgentDriver(harness, forks=False)
    with pytest.raises(SessionError):
        await _opened(lone, await _opened(lone))


@pytest.mark.parametrize("harness", FORKING)
async def test_a_fake_fork_is_refused_once_its_parent_has_moved_on(
    harness: HarnessKind,
) -> None:
    driver = FakeAgentDriver(harness)
    parent = await _opened(driver)
    await parent.turn(TurnRequest("one"), RecordingSink())
    child = await _opened(driver, parent)
    await parent.turn(TurnRequest("two"), RecordingSink())
    with pytest.raises(SessionError):
        await child.turn(TurnRequest("three"), RecordingSink())
    with pytest.raises(SessionError):
        await child.turn(TurnRequest("three"), RecordingSink())
    # Cut again from where the parent is now, it carries on, and the parent moving on after
    # the cut is nothing to it.
    again = await _opened(driver, parent)
    assert await again.turn(TurnRequest("four"), RecordingSink()) == "ok"
    await parent.turn(TurnRequest("five"), RecordingSink())
    assert await again.turn(TurnRequest("six"), RecordingSink()) == "ok"
    assert again.prompts == ["one", "two", "four", "six"]


@pytest.mark.parametrize("harness", FORKING)
async def test_a_fake_forks_only_where_its_harness_can(harness: HarnessKind) -> None:
    driver = FakeAgentDriver(harness)
    parent = await _opened(driver)
    await parent.turn(TurnRequest("one"), RecordingSink())

    async def forked(placement: Placement) -> Any:
        return await driver.open(
            placement,
            permission=Permission(),
            skills=(),
            hooks=HookTable(),
            fork_of=parent,
        )

    with pytest.raises(UnsupportedOperation):
        await forked(Placement(EnvBackendKind.SSH, "box", PurePosixPath("/work")))
    there = Placement(EnvBackendKind.LOCAL, "", PurePosixPath("/there"))
    if harness in {HarnessKind.CLAUDE, HarnessKind.CODEX, HarnessKind.KIMI}:
        assert (await forked(there)).placement == there
    else:
        with pytest.raises(UnsupportedOperation):
            await forked(there)


# --------------------------------------------------------------------- the environments


@pytest.mark.parametrize(
    ("command", "said"),
    [
        (("true",), (0, "", "")),
        (("false",), (1, "", "")),
        (("echo", "a", "b"), (0, "a b\n", "")),
        (("cat", "a.txt"), (0, "A", "")),
        (("cat", "missing"), (1, "", "cat: missing: No such file or directory\n")),
        (("ls",), (0, "a.txt\ndir\n", "")),
        (("ls", "dir"), (0, "b.txt\n", "")),
        (("git", "rev-parse", "--is-inside-work-tree"), (0, "true\n", "")),
        (("nope",), (127, "", "fake: nope: command not found\n")),
        (
            "echo | tr",
            (127, "", "fake: scripts are answered by `run=`, not interpreted\n"),
        ),
    ],
    ids=str,
)
async def test_a_fake_env_answers_a_few_commands_by_default(
    command: Any, said: tuple[int, str, str]
) -> None:
    env = FakeEnvDriver({"a.txt": "A", "dir/b.txt": b"B"})
    assert await env.exec(command, timeout=0) == said
    assert env.commands == [command]


async def test_a_fake_env_asks_its_handler_first() -> None:
    async def handler(command: Any, env: FakeEnvDriver) -> Any:
        return (0, "handled", "") if command == ("make",) else None

    env = FakeEnvDriver(run=handler)
    assert await env.exec(["make"], timeout=0) == (0, "handled", "")
    assert await env.exec(["true"], timeout=0) == (0, "", "")
    with pytest.raises(EnvCommandTimeout):
        await env.exec(["sleep", "5"], timeout=0.01)


async def test_a_fake_env_copies_and_forgets() -> None:
    env = FakeEnvDriver({"a.txt": "A"}, repo=False)
    assert env.text("a.txt") == "A"
    with pytest.raises(WorktreeError):
        await env.derive_worktree(ref=None, dir=None)
    clone = await env.derive_temp_clone("c", holder="me")
    assert clone.files == {"a.txt": b"A"}
    await clone.write("b.txt", b"B")
    assert env.files == {"a.txt": b"A"}
    await env.destroy_temp_clone("c")
    assert list(env.machine) == ["/work/a.txt"]
    assert await env.exec(["git", "rev-parse", "--is-inside-work-tree"], timeout=0) == (
        128,
        "",
        "fatal: not a git repository\n",
    )


async def test_a_fake_env_lets_go_of_a_copy_as_it_is_closed_and_keeps_it() -> None:
    env = FakeEnvDriver({"a.txt": "A"})
    clone = await env.derive_temp_clone("c", holder="first")
    await clone.write("b.txt", b"B")
    with pytest.raises(TempCloneBusy):
        await env.derive_temp_clone("c", holder="second")
    await clone.close()
    again = await env.derive_temp_clone("c", holder="second")
    assert again.workdir == clone.workdir
    assert again.files == {"a.txt": b"A", "b.txt": b"B"}
    with pytest.raises(TempCloneBusy):
        await env.derive_temp_clone("c", holder="first")
    await clone.close()
    with pytest.raises(TempCloneBusy):
        await env.derive_temp_clone("c", holder="first")
    await env.close()
    third = await env.derive_temp_clone("c", holder="third")
    assert third.workdir == clone.workdir
    assert env.clones == ["c"]
    await env.destroy_temp_clone("c")
    assert (env.clones, list(env.machine)) == ([], ["/work/a.txt"])


async def test_a_fake_env_rewinds_to_a_snapshot_or_to_what_it_was_made_with() -> None:
    env = FakeEnvDriver({"a.txt": "A"})
    await env.write("b.txt", b"B")
    ref = await env.snapshot("b")
    await env.write("a.txt", b"changed")
    await env.write("c.txt", b"C")
    await env.rewind(ref)
    assert env.files == {"a.txt": b"A", "b.txt": b"B"}
    await env.rewind("main")
    assert env.files == {"a.txt": b"A"}
    assert await env.snapshots() == ["refs/hmz/snapshots/b"]
    # humanize's own directory, now and as it was called before, is neither kept nor taken.
    await env.write(".hmz/flows/x.py", b"x")
    await env.write(".humanize/old", b"o")
    await env.rewind(await env.snapshot("own"))
    await env.rewind("main")
    assert env.files == {"a.txt": b"A", ".hmz/flows/x.py": b"x", ".humanize/old": b"o"}
    with pytest.raises(RewindError):
        await env.rewind("no-such-ref")
    with pytest.raises(RewindError):
        await FakeEnvDriver(repo=False).snapshot(None)


async def test_a_fake_env_refuses_a_worktree_where_one_is() -> None:
    env = FakeEnvDriver({"a.txt": "A"})
    await env.derive_worktree(ref="main", dir="/elsewhere")
    with pytest.raises(WorktreeError):
        await env.derive_worktree(ref=None, dir="/elsewhere")


# ------------------------------------------------------------------------- run_fake


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
    session = await human.spawn(env=envs["big"])
    return [
        agents["claude"].harness,
        agents["codex"].harness,
        agents["plain"].harness,
        envs["big"].workdir,
        await human.run("ok?", session=session),
    ]


async def test_run_fake_fills_every_role_with_what_it_asks_for() -> None:
    said = await run_fake(wanting, agents={"human": "sure"})
    assert said == [
        HarnessKind.CLAUDE,
        HarnessKind.CODEX,
        HarnessKind.CLAUDE,
        PurePosixPath("/big"),
        "sure",
    ]


async def test_run_fake_takes_drivers_and_files() -> None:
    codex = FakeAgentDriver(HarnessKind.CODEX, model="picked")
    big = FakeEnvDriver(cpu_count=256, gpu_count=8, gpu_memory=1 << 40, workdir="/mine")
    said = await run_fake(
        wanting,
        agents={"codex": codex, "human": FakeOutworlder("person")},
        envs={"big": big},
    )
    assert said[3] == PurePosixPath("/mine")
    assert said[4] == "person"


async def test_run_fake_refuses_what_the_flow_does_not_declare() -> None:
    from hmz.flows import RequirementError

    with pytest.raises(RequirementError):
        await run_fake(wanting, agents={"nobody": "x"})
    with pytest.raises(RequirementError):
        await run_fake(wanting, envs={"nowhere": {}})
    with pytest.raises(TypeError):
        await run_fake(object())  # pyright: ignore[reportArgumentType]
