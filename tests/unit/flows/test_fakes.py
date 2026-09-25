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
    SessionError,
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
