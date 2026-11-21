"""The pictures of `docs/builder/branching.md`: one conversation forked two ways.

The page's own flow, `two_ways`, has a coder read the code once, then forks that session
twice: each fork tries the task a different way in a worktree of its own, both at once. It is
shown run from the command line, and as its epic in the app: one session, and two forked
from it.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_branching.py`.
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

#: The page's flow, as the page prints it.
_TWO_WAYS = '''
import asyncio

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

WAYS = ("as a percentage off the total", "as a fixed amount off the total")


class Agents(AgentCollection):
    coder: Agent


class Workspace(LocalEnv, GitWorktreeEnvMixin):
    """The project. The flow may add worktrees of it."""


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def two_ways(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> list[str]:
    """Read the code once, then try the task two ways, each in its own worktree."""
    coder, workspace = agents["coder"], envs["workspace"]
    base = await coder.spawn()
    await coder.run(
        f"Read the code this needs. Change nothing yet.\\n\\n{task}",
        session=base,
        env=workspace,
    )

    async def attempt(way: str) -> str:
        tree = await workspace.derive_worktree()
        branch = await coder.fork(base)
        return await coder.run(f"Now do it {way}.", session=branch, env=tree)

    return await asyncio.gather(*(attempt(way) for way in WAYS))
'''


def _edit(result: str) -> list[dict[str, object]]:
    """What a branch does before it answers: the edit, then the tests."""
    return [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.4,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": result,
            "takes": 0.6,
        },
    ]


#: What the coder says to the reading, and to each way on from it.
_SAYS = {
    "Change nothing yet": {
        "text": "charge() in shop/checkout.py returns total(items) in cents."
        " A discount belongs there, after the total.",
        "tools": [
            {
                "name": "Read",
                "input": {"file_path": "shop/checkout.py"},
                "result": "read",
                "takes": 0.3,
            },
            {
                "name": "Read",
                "input": {"file_path": "shop/cart.py"},
                "result": "read",
                "takes": 0.3,
            },
        ],
    },
    "percentage": {
        "text": "charge() takes a code now: WELCOME10 is 10% off the total."
        " The tests pass.",
        "tools": _edit("5 passed in 0.18s"),
    },
    "fixed amount": {
        "text": "charge() takes a code now: FIVEOFF is 500 cents off, never below zero."
        " The tests pass.",
        "tools": _edit("6 passed in 0.21s"),
    },
}


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/two_ways`."""
    flow = world.workspace / ".hmz" / "flows" / "two_ways"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_TWO_WAYS)


def test_one_reading_is_carried_two_ways_on_the_command_line(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/two_ways",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-branching-exec",
    )


def test_the_forks_are_sessions_of_their_own_in_the_app(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    name = world.epic("@local/two_ways", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        sessions = page.locator("[data-hmz=graph-session]")
        expect(sessions).to_have_count(3)
        sessions.nth(1).click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("Now do it")
        page.wait_for_timeout(1000)
        shots.web(page, "builder-branching-epic", window="desktop", most=shots.REEL)
