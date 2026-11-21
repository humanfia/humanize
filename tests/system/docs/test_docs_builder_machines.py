"""The pictures of `docs/builder/machines.md`: what a machine must have, and a session moved.

Two flows of the page's own. `train` declares a role whose machine must have a GPU, and is
shown refused on a machine that has none, before any agent starts. `plan_then_build` has one
session plan in the project and then build in a worktree of it: the same conversation, its
second turn somewhere else. It is shown run from the command line, and as its epic in the app.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_machines.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a discount code to checkout"

#: The page's first flow, as the page prints it: a role that says what its machine must have.
_TRAIN = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    CPUEnvMixin,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    GPUEnvMixin,
    ImageEnvMixin,
    MemoryEnvMixin,
    ShellEnvMixin,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Box(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, GPUEnvMixin, ImageEnvMixin):
    """Where the training runs."""

    _cpu_count = 4
    _memory = 8 << 30  # bytes: 8 GiB
    _gpu_count = 1
    _gpu_memory = 24 << 30  # bytes per GPU
    _image = "pytorch/pytorch:latest"


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def train(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Do the task on a machine with a GPU."""
    coder, box = agents["coder"], envs["box"]
    session = await coder.spawn()
    return await coder.run(task, session=session, env=box)
'''

#: The page's second flow, as the page prints it: one session, two places.
_PLAN_THEN_BUILD = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GitWorktreeEnvMixin,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, GitWorktreeEnvMixin):
    """The project. The flow may add worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def plan_then_build(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Plan in the project, then build in a worktree, in one conversation."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(
        f"Plan this. Change nothing yet.\\n\\n{task}", session=session, env=workspace
    )
    tree = await workspace.derive_worktree()
    return await coder.run("Now build it here.", session=session, env=tree)
'''

#: What the coder says to the planning, and to the building.
_SAYS = {
    "Change nothing yet": {
        "text": "Plan: charge() in shop/checkout.py takes a code and takes 10% off"
        " the total for WELCOME10. One test for it.",
        "tools": [
            {
                "name": "Read",
                "input": {"file_path": "shop/checkout.py"},
                "result": "read",
                "takes": 0.3,
            },
        ],
    },
    "build it here": {
        "text": "Built as planned: WELCOME10 is 10% off the total. The tests pass.",
        "tools": [
            {
                "name": "Edit",
                "input": {"file_path": "shop/checkout.py"},
                "result": "edited",
                "takes": 0.4,
            },
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "5 passed in 0.18s",
                "takes": 0.6,
            },
        ],
    },
}


def _own(world: World, name: str, source: str) -> None:
    """Puts one of the page's flows among the project's own, as `@local/<name>`."""
    flow = world.workspace / ".hmz" / "flows" / name
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


def test_a_machine_without_what_the_role_needs_is_refused(world: World) -> None:
    _own(world, "train", _TRAIN)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/train",
            "-a",
            f"coder={AGENT}",
            "-e",
            "box=local/~/shop",
            "-p",
            "budget.output_tokens=20000",
            "Train the ranking model",
        ],
        "builder-machines-refused",
    )


def test_one_session_plans_here_and_builds_in_a_worktree(world: World) -> None:
    _own(world, "plan_then_build", _PLAN_THEN_BUILD)
    world.says(_SAYS)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/plan_then_build",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-machines-exec",
    )


def test_the_moved_session_is_one_conversation_in_the_app(world: World) -> None:
    _own(world, "plan_then_build", _PLAN_THEN_BUILD)
    world.says(_SAYS)
    name = world.epic("@local/plan_then_build", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        sessions = page.locator("[data-hmz=graph-session]")
        expect(sessions).to_have_count(2)
        sessions.nth(1).click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("Now build it here")
        page.wait_for_timeout(1000)
        shots.web(page, "builder-machines-epic", window="desktop", most=shots.REEL)
