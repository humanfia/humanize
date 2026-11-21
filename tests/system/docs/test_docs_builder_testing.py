"""The picture of `docs/builder/testing.md`: a flow's tests run on fakes, under pytest.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_testing.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.system.docs import shots

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: The page's flow, as the page prints it: a coder works until the tests pass, and then a
#: person decides whether to ship.
_FIX = r'''from pydantic import BaseModel

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowContext,
    FlowParams,
    LocalEnv,
    Outworlder,
    ShellEnvMixin,
    flow,
)


class Verdict(BaseModel):
    ship: bool = False


class Agents(AgentCollection):
    coder: Agent
    human: Outworlder


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


class Params(FlowParams):
    rounds: int = 3


@flow(agents=Agents, envs=Envs, params=Params)
async def fix(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """A coder works until the tests pass, then a person decides whether to ship."""
    coder, human, workspace = agents["coder"], agents["human"], envs["workspace"]
    session = await coder.spawn()
    prompt = task
    for _ in range(params.rounds):
        await coder.run(prompt, session=session, env=workspace)
        status, out, _ = await workspace.exec(["pytest", "-q"])
        if status == 0:
            break
        prompt = f"The tests fail: {out}"
    else:
        return "gave up"
    await workspace.write("NOTES.md", f"{task}: tests pass\n".encode())
    verdict = await human.run(
        "Ship it?", session=await human.spawn(), output_schema=Verdict
    )
    return "shipped" if verdict.ship else "held"
'''

#: The page's tests of it, as the page prints them.
_TESTS = r"""import pytest

from hmz.flows import ParamsError
from hmz.sdk import fakes


async def test_it_ships_once_the_tests_pass() -> None:
    results = iter([(1, "1 failed", ""), (0, "5 passed", "")])
    coder = fakes.FakeAgentDriver(reply=["Added the code.", "Fixed the total."])
    workspace = fakes.FakeEnvDriver(
        {"shop/checkout.py": "TOTAL = 0\n"},
        run=lambda command, env: next(results) if command[0] == "pytest" else None,
    )
    human = fakes.FakeOutworlder(reply={"ship": True})

    result = await fakes.run_fake(
        "fix",
        "add a discount code to checkout",
        agents={"coder": coder},
        local=workspace,
        outworlder=human,
    )

    assert result == "shipped"
    assert coder.prompts == [
        "add a discount code to checkout",
        "The tests fail: 1 failed",
    ]
    assert workspace.commands == [("pytest", "-q"), ("pytest", "-q")]
    assert workspace.text("NOTES.md").endswith("tests pass\n")
    assert human.asked == ["Ship it?"]


async def test_it_gives_up_after_its_rounds() -> None:
    workspace = fakes.FakeEnvDriver(run={("pytest", "-q"): (1, "1 failed", "")})

    result = await fakes.run_fake("fix", "x", local=workspace, params={"rounds": 2})

    assert result == "gave up"
    assert len(workspace.commands) == 2


async def test_nobody_there_means_held() -> None:
    workspace = fakes.FakeEnvDriver(run={("pytest", "-q"): (0, "5 passed", "")})

    assert await fakes.run_fake("fix", "x", local=workspace) == "held"


async def test_wrong_params_are_refused_before_anything_runs() -> None:
    coder = fakes.FakeAgentDriver()

    with pytest.raises(ParamsError):
        await fakes.run_fake("fix", "x", agents={"coder": coder}, params={"rounds": "many"})

    assert coder.sessions == []
"""

#: What the page has the project's `pyproject.toml` say, so that pytest runs `async def` tests.
_ASYNC = """
[tool.pytest.ini_options]
asyncio_mode = "auto"
"""


def test_the_tests_of_a_flow_pass_on_fakes(world: World) -> None:
    flow = world.workspace / ".hmz" / "flows" / "fix"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_FIX)
    with (world.workspace / "pyproject.toml").open("a") as project:
        project.write(_ASYNC)
    (world.workspace / "tests" / "test_fix.py").write_text(_TESTS)
    shots.cli(
        ["pytest", "--no-header", "-v", "tests/test_fix.py"],
        "builder-testing-pytest",
        columns=84,
    )
