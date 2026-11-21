"""The pictures of `docs/builder/hooks.md`: a stop hook keeping a turn going.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_hooks.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"

#: The page's flow, as the page prints it: one hook starts the session with a rule, and
#: another keeps the turn going until the agent reports its tests.
_TESTED = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    SessionStartHookParams,
    SessionStartHookResult,
    StopHookParams,
    StopHookResult,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


async def house_rules(params: SessionStartHookParams) -> SessionStartHookResult:
    return SessionStartHookResult(context="Keep the change small.")


async def until_tested(params: StopHookParams) -> StopHookResult:
    if "passed" in params.said or params.again >= 2:
        return StopHookResult()  # changes nothing: the turn ends
    return StopHookResult(block=True, reason="Run pytest -q and say what it printed.")


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def tested(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task and is kept going until it reports its tests."""
    coder = agents["coder"]
    coder.on_session_start(house_rules)
    coder.on_stop(until_tested)
    return await coder.run(task, session=await coder.spawn(), env=envs["workspace"])
'''

#: What the coder says: first of the task, with no word of its tests, and then, told by the
#: stop hook to run them, what they printed.
_LINES = {
    "coupon": {
        "text": "Checkout takes a coupon now: WELCOME10 is 10% off.",
        "tools": [
            {
                "name": "Edit",
                "input": {"file_path": "shop/checkout.py"},
                "result": "edited",
                "takes": 0.4,
            }
        ],
    },
    "Run pytest -q": {
        "text": "pytest -q printed: 5 passed in 0.18s.",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "5 passed in 0.18s",
                "takes": 0.6,
            }
        ],
    },
}


def _own(world: World, name: str, source: str) -> None:
    """Puts a flow among the project's own, as `@local/<name>`."""
    flow = world.workspace / ".hmz" / "flows" / name
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


def test_a_stop_hook_keeps_the_turn_going(world: World) -> None:
    _own(world, "tested", _TESTED)
    world.says(_LINES)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/tested",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-hooks-exec",
    )


def test_the_same_turn_in_the_app(world: World) -> None:
    _own(world, "tested", _TESTED)
    world.says(_LINES)
    name = world.epic("@local/tested", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        page.get_by_text("every session").first.click()
        expect(
            page.get_by_text("Run pytest -q and say what it printed.")
        ).to_be_visible()
        expect(page.get_by_text("5 passed in 0.18s.").first).to_be_visible()
        shots.web(page, "builder-hooks-log", window="desktop", most=shots.REEL)
