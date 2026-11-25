"""The pictures of `docs/builder/flow.md`: one flow of the project's own, named and run.

The flow is the page's own, as the page prints it: a module `tidy` holding two flows, the one
named after it and one inside it. It is put among the project's own flows, run with
`hmz exec`, picked in the app's New epic and set up in the terminal. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_flow.py`.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import on, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-flow"

_TASK = "Add a discount code to checkout"

#: The flow as the page prints it.
_TIDY = '''
from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

AGAIN = "Read your change again. Fix anything wrong or missing."


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


class Params(FlowParams):
    rounds: int = 1


@flow(agents=Agents, envs=Envs, params=Params)
async def tidy(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> str:
    """Do the task, then read it over and fix it."""
    coder, workspace = agents["coder"], envs["workspace"]
    session = await coder.spawn()
    said = await coder.run(task, session=session, env=workspace)
    for _ in range(params.rounds):
        said = await coder.run(AGAIN, session=session, env=workspace)
    return said


@flow(agents=Agents, envs=Envs, params=FlowParams, name="once")
async def tidy_once(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """Do the task in one turn."""
    coder = agents["coder"]
    return await coder.run(task, session=await coder.spawn(), env=envs["workspace"])
'''

#: The same flow written wrong: its function does not take `ctx`.
_WRONG = _TIDY.replace(", ctx: FlowContext\n) -> str:", "\n) -> str:", 1)

#: What the agent says when told the task, and when told to read it again.
_SAYS = {
    "discount": {
        "text": (
            "Added a discount code to checkout: charge() takes a code, and WELCOME10"
            " takes 10% off."
        ),
        "tools": [
            {
                "name": "Edit",
                "input": {"file_path": "shop/checkout.py"},
                "result": "edited",
                "takes": 0.4,
            },
        ],
    },
    "Read your change again": {
        "text": "An unknown code raised KeyError. It is ignored now. 3 tests pass.",
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "3 passed in 0.12s",
                "takes": 0.5,
            }
        ],
    },
}


def _written(world: World, source: str = _TIDY) -> None:
    """Writes the flow where the page says to: `.hmz/flows/tidy/`, the project's only."""
    flows = world.workspace / ".hmz" / "flows"
    shutil.rmtree(flows)
    (flows / "tidy").mkdir(parents=True)
    (flows / "tidy" / "__init__.py").write_text(source.lstrip())


def _exec(flow: str) -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        flow,
        "-a",
        f"coder={AGENT}",
        "-p",
        "budget.duration=10m",
        _TASK,
    ]


def test_the_flow_runs_by_its_name(world: World) -> None:
    _written(world)
    world.says(_SAYS)
    shots.cli(_exec("tidy"), f"{_PAGE}-exec")


def test_a_flow_written_wrong_is_refused_saying_why(world: World) -> None:
    _written(world, _WRONG)
    shots.cli(_exec("tidy"), f"{_PAGE}-wrong")


def test_the_app_offers_both_flows_and_asks_what_one_declares(world: World) -> None:
    _written(world)
    reel = shots.Reel(f"{_PAGE}-app", window="desktop")
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel.web(page, hold=1.1, pointer=picker, click=True)
        picker.click()
        flow = page.get_by_text("@local/tidy", exact=True)
        expect(flow).to_be_visible()
        expect(page.get_by_text("@local/tidy:once", exact=True)).to_be_visible()
        reel.web(page, hold=2.6, pointer=flow, click=True)
        flow.click()
        expect(picker.locator("b")).to_have_text("@local/tidy")
        expect(view.get_by_role("spinbutton", name="rounds")).to_have_value("1")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel.web(page, hold=4, poster=True)
        reel.save()


async def test_the_terminal_sets_the_flow_up_by_its_name(world: World) -> None:
    from hmz.tui.flows import Flows

    _written(world)
    async with world.tui() as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow tidy", "enter")
        await on(pilot, Flows)
        await shows(pilot, "coder")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-tui")
