"""The pictures of `docs/builder/agents.md`: what a flow's agent roles come to where it is run.

The flow is the page's own, as the page prints it: a coder role declared with a mixin, and a
reviewer nobody has to give. It is run with `hmz exec`, refused on a harness that cannot fill
the coder's role, and set up in the app and in the terminal. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_agents.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import on, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-agents"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_CAREFUL = '''
from typing import NotRequired

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    GoalCommandAgentMixin,
    LocalEnv,
    Permission,
    flow,
)


class Coder(Agent, GoalCommandAgentMixin):
    """Pursues the task as a goal of its harness."""


class Agents(AgentCollection):
    coder: Coder
    reviewer: NotRequired[Agent]


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def careful(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """A coder pursues the task; a reviewer, if given, reads the change."""
    coder, workspace = agents["coder"], envs["workspace"]
    said = await coder.run(f"/goal {task}", session=await coder.spawn(), env=workspace)
    reviewer = agents.get("reviewer")
    if reviewer is None:
        return said
    reader = reviewer.derive(permission=Permission(preset="read-only"))
    return await reader.run(
        "Review the change in this repository.",
        session=await reader.spawn(),
        env=workspace,
    )
'''

#: The same flow with the mixin left off its coder: it says `/goal` without having asked to.
_HASTY = _CAREFUL.replace(
    "class Coder(Agent, GoalCommandAgentMixin):", "class Coder(Agent):"
)

#: What the coder does when told the task, and what the reviewer says of it.
_SAYS = {
    "discount": {
        "text": (
            "Goal met. charge() takes a code now, and WELCOME10 takes 10% off."
            " The tests pass."
        ),
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
                "result": "4 passed in 0.15s",
                "takes": 0.5,
            },
        ],
    },
    "Review the change": {
        "text": "The change is right. An unknown code is ignored, which the tests cover.",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "git diff"},
                "result": "shop/checkout.py | 9 +++++++--",
                "takes": 0.3,
            }
        ],
    },
}


def _own(world: World, source: str = _CAREFUL) -> None:
    """Puts the flow among the project's own, as `@local/careful`."""
    flow = world.workspace / ".hmz" / "flows" / "careful"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(source.lstrip())


def _exec(*agents: str) -> list[str]:
    given = [word for agent in agents for word in ("-a", agent)]
    return [
        "hmz",
        "exec",
        "-f",
        "@local/careful",
        *given,
        "-p",
        "budget.output_tokens=20000",
        _TASK,
    ]


def test_both_roles_take_their_turns(world: World) -> None:
    _own(world)
    world.says(_SAYS)
    shots.cli(
        _exec(f"coder={AGENT}", "reviewer=claude/claude-opus-4-1"), f"{_PAGE}-exec"
    )


def test_a_harness_that_cannot_fill_a_role_is_refused(world: World) -> None:
    _own(world)
    shots.cli(_exec("coder=cursor-agent/auto"), f"{_PAGE}-refused")


def test_what_a_role_did_not_declare_is_not_granted(world: World) -> None:
    _own(world, _HASTY)
    shots.cli(_exec(f"coder={AGENT}"), f"{_PAGE}-not-granted")


def test_the_app_asks_for_an_agent_per_role(world: World) -> None:
    _own(world)
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        picker.click()
        page.get_by_text("@local/careful", exact=True).click()
        expect(picker.locator("b")).to_have_text("@local/careful")
        expect(view.locator('[data-hmz="role-row"]')).to_have_count(2)
        expect(view.get_by_text("Optional")).to_be_visible()
        expect(view.get_by_text("Asking…")).to_have_count(0)
        shots.web(page, f"{_PAGE}-app", window="desktop")


async def test_the_terminal_asks_for_an_agent_per_role(world: World) -> None:
    from hmz.tui.flows import Flows

    _own(world)
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow careful", "enter")
        await on(pilot, Flows)
        await shows(pilot, "reviewer")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-tui")
