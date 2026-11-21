"""The pictures of `docs/builder/context.md`: an error caught, one not, and how each ending shows.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_context.py`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"
_BROKEN = "Add gift cards to checkout"
_LONG = "Rename the cart module"

#: The page's flow, as the page prints it: one more try after a harness fails.
_SECOND_TRY = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    HarnessError,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def second_try(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task, and tries once more if its harness fails."""
    coder, workspace = agents["coder"], envs["workspace"]
    try:
        answer = await coder.run(task, session=await coder.spawn(), env=workspace)
    except HarnessError as error:
        again = f"The last try failed: {error}. Try again. {task}"
        answer = await coder.run(again, session=await coder.spawn(), env=workspace)
    return f"{answer} ({ctx.usage.output_tokens} output tokens)"
'''

#: What the coder does on a try that works.
_WORK = {
    "text": "Checkout takes a coupon now: WELCOME10 is 10% off. The tests pass.",
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
}

#: What a try fails with.
_FAIL = {"fail": "the provider closed the connection"}

_EXEC = [
    "hmz",
    "exec",
    "-f",
    "@local/second_try",
    "-a",
    f"coder={AGENT}",
    "-p",
    "budget.output_tokens=20000",
    _TASK,
]


def _own(world: World, name: str, source: str) -> None:
    """Puts a flow among the project's own, as `@local/<name>`."""
    flow = world.workspace / ".hmz" / "flows" / name
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source)


def _epic(world: World, task: str, **how: Any) -> str:
    """Starts an epic of the page's flow once the one before it is let go of.

    An epic is said to have ended a moment before its host lets go of it, and one started
    in that moment is refused as `a flow is already running`.
    """
    deadline = time.monotonic() + 60
    here = str(world.workspace)
    while any(
        one.get("held") for one in world.call("runs.list", workspace=here)["runs"]
    ):
        assert time.monotonic() < deadline, "the epic before was never let go of"
        time.sleep(0.3)
    time.sleep(0.5)
    return world.epic("@local/second_try", task, **how)


def test_an_error_the_flow_catches_is_a_second_try(world: World) -> None:
    _own(world, "second_try", _SECOND_TRY)
    # The second prompt holds both keys, and the first key found answers it.
    world.says({"Try again": _WORK, "coupon": _FAIL})
    shots.cli(_EXEC, "builder-context-caught")


def test_an_error_the_flow_does_not_catch_fails_the_epic(world: World) -> None:
    _own(world, "second_try", _SECOND_TRY)
    world.says({"coupon": _FAIL})
    shots.cli(_EXEC, "builder-context-failed")


def test_each_way_a_flow_ends_is_a_state_in_the_app(world: World) -> None:
    _own(world, "second_try", _SECOND_TRY)
    world.says(
        {
            "gift": _FAIL,
            "Rename": {"text": "Renamed it.", "after": 60},
            "coupon": _WORK,
        }
    )
    _epic(world, _TASK)
    _epic(world, _BROKEN, failing=True)
    stopped = _epic(world, _LONG, until=None)
    world.stop(stopped)
    with world.page(desktop=True, height=560) as page:
        go(page, f"/epics/{stopped}")
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar.get_by_text("Failed").first).to_be_visible()
        expect(sidebar.get_by_text("Stopped").first).to_be_visible()
        expect(sidebar.get_by_text("Done").first).to_be_visible()
        shots.web(page, "builder-context-endings", clip=sidebar, pad=0)
