"""The pictures of `docs/builder/goals.md`: a task handed to an agent as its own goal.

The page's own flow, `aim`, sets its task as the worker's goal in one `run`. It is shown run
from the command line, refused for a harness with no goal command, and as its epic in the app
with the session's thread open: one `/goal` prompt of the flow's, and what the agent did
until it called the goal met.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_goals.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "checkout takes a coupon code, and pytest -q passes"

#: The page's flow, as the page prints it.
_AIM = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    flow,
)


class Worker(Agent, GoalCommandAgentMixin): ...


class Agents(AgentCollection):
    worker: Worker


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def aim(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """The task, set once as the agent's own goal."""
    worker = agents["worker"]
    session = await worker.spawn()
    return await worker.run(f"/goal {task}", session=session, env=envs["workspace"])
'''

#: What the worker does under the goal: it works, checks, works again, and calls it met.
_SAYS = {
    "coupon": {
        "text": "Goal met: charge() takes a coupon code, and pytest -q passes.",
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
                "result": "1 failed, 4 passed in 0.21s",
                "takes": 0.6,
            },
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


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/aim`."""
    flow = world.workspace / ".hmz" / "flows" / "aim"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_AIM)


def test_the_task_is_one_goal_on_the_command_line(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/aim",
            "-a",
            f"worker={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-goals-exec",
    )


def test_a_harness_with_no_goal_command_is_refused_before_it_starts(
    world: World,
) -> None:
    _own(world)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/aim",
            "-a",
            "worker=pi/gpt-5.5",
            "-p",
            "budget.output_tokens=20000",
            "ship it",
        ],
        "builder-goals-refused",
    )


def test_the_goal_is_one_prompt_in_the_app(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    name = world.epic("@local/aim", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        page.locator("[data-hmz=graph-session]").first.click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("/goal checkout takes a coupon code")
        expect(thread).to_contain_text("Goal met")
        page.wait_for_timeout(1000)
        shots.web(page, "builder-goals-thread", window="desktop", most=shots.REEL)
