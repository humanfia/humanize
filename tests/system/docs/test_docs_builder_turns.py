"""The pictures of `docs/builder/turns.md`: one session of a flow taking two turns.

The page's own flow, `finish`, has a coder do the task and then say what it changed, both in
one session. It is shown run from the command line, and as its epic in the app with the
session's thread open: two prompts of the flow's, two answers of the agent's.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_builder_turns.py`.
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

#: The page's flow, as the page prints it.
_FINISH = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def finish(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder does the task, then says what it changed in one line."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    line = await coder.run(
        "Say what you changed in one line.", session=session, env=workspace
    )
    return f"{line} ({session.usage.output_tokens} tokens written)"
'''

#: What the coder says to each of the flow's two prompts.
_SAYS = {
    "one line": "checkout: charge() takes a coupon code; WELCOME10 is 10% off.",
    "coupon": {
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
    },
}


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/finish`."""
    flow = world.workspace / ".hmz" / "flows" / "finish"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_FINISH)


def test_one_session_takes_two_turns_on_the_command_line(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/finish",
            "-a",
            f"coder={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        "builder-turns-exec",
    )


def test_the_session_is_one_thread_in_the_app(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    name = world.epic("@local/finish", _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        page.locator("[data-hmz=graph-session]").first.click()
        thread = page.locator("[data-hmz=thread]")
        expect(thread).to_contain_text("WELCOME10")
        expect(thread).to_contain_text("Say what you changed in one line.")
        expect(thread).to_contain_text("charge() takes a coupon code")
        page.wait_for_timeout(1000)
        shots.web(page, "builder-turns-thread", window="desktop", most=shots.REEL)
