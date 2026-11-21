"""The pictures of `docs/tutorials/first-flow.md`: a first flow, written and run.

The flow is the page's own, as the page prints it at each step: one agent takes a turn, then
a loop of turns, then a param says how many. It is put among the project's own flows, run with
`hmz exec`, and started from the app's New epic. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_first_flow.py`.
"""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-first-flow"

_TASK = "Add a discount code to checkout"

#: What the flow says to its agent each round after the first.
_AGAIN = "Read your change again. Fix anything wrong or missing."

_HEAD = """
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

"""

#: The flow as the page first writes it: one agent, one turn.
_ONE_TURN = (
    _HEAD
    + '''
@flow(agents=Agents, envs=Envs, params=FlowParams)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """Do the task, then read it over and fix it."""
    coder = agents["coder"]
    workspace = envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
'''
)

#: And as the page leaves it: a loop of turns in one session, a param saying how many.
_ROUNDS = (
    _HEAD
    + f'''
AGAIN = "{_AGAIN}"


class Params(FlowParams):
    rounds: int = 2


@flow(agents=Agents, envs=Envs, params=Params)
async def polish(
    task: str, *, agents: Agents, envs: Envs, params: Params, ctx: FlowContext
) -> None:
    """Do the task, then read it over and fix it."""
    coder = agents["coder"]
    workspace = envs["workspace"]
    session = await coder.spawn()
    await coder.run(task, session=session, env=workspace)
    for _ in range(params.rounds):
        await coder.run(AGAIN, session=session, env=workspace)
'''
)

#: What the agent says when told the task, and each time it is told to read it again.
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
                "takes": 0.5,
            },
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "2 passed in 0.10s",
                "takes": 0.7,
            },
        ],
        "after": 0.8,
    },
    "Read your change again": {
        "text": [
            "An unknown code raised KeyError. It is ignored now, and a test covers it.",
            "The discount was applied before rounding. Fixed: 3 tests pass.",
            "Read it through once more: nothing left to change. 3 tests pass.",
        ],
        "tools": [
            {
                "name": "Bash",
                "input": {"command": "pytest -q"},
                "result": "3 passed in 0.12s",
                "takes": 0.6,
            }
        ],
        "after": 0.8,
    },
}


def _written(world: World, source: str) -> None:
    """Writes the flow where the page says to: `.hmz/flows/polish.py`, the project's only."""
    flows = world.workspace / ".hmz" / "flows"
    shutil.rmtree(flows)
    flows.mkdir()
    (flows / "polish.py").write_text(source.lstrip())


def _exec(*params: str) -> list[str]:
    return [
        "hmz",
        "exec",
        "-f",
        "polish",
        "-a",
        f"coder={AGENT}",
        *(part for one in params for part in ("-p", one)),
        "-p",
        "budget.duration=10m",
        _TASK,
    ]


def test_the_first_flow_runs_from_the_command_line(world: World) -> None:
    _written(world, _ONE_TURN)
    world.says(_SAYS)
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(_exec(), rows=10)
    reel.save()


def test_the_loop_takes_its_rounds(world: World) -> None:
    _written(world, _ROUNDS)
    world.says(_SAYS)
    shots.cli(_exec("rounds=3"), f"{_PAGE}-rounds")


def test_a_param_the_flow_has_not_is_refused(world: World) -> None:
    _written(world, _ROUNDS)
    shots.cli(_exec("round=3"), f"{_PAGE}-refused")


def test_the_flow_is_started_from_the_app(world: World) -> None:
    _written(world, _ROUNDS)
    world.says(_SAYS)
    reel = shots.Reel(f"{_PAGE}-app", window="desktop")
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel.web(page, hold=1.1, pointer=picker, click=True)
        picker.click()
        flow = page.get_by_text("@local/polish", exact=True)
        expect(flow).to_be_visible()
        reel.web(page, hold=1.4, pointer=flow, click=True)
        flow.click()
        expect(picker.locator("b")).to_have_text("@local/polish")
        rounds = view.get_by_role("spinbutton", name="rounds")
        expect(rounds).to_have_value("2")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel.web(page, hold=1.4, pointer=rounds, click=True)
        rounds.fill("3")
        minutes = view.get_by_label("Longest it may take, in minutes")
        reel.web(page, hold=0.9, pointer=minutes, click=True)
        minutes.fill("10")
        box = view.get_by_placeholder(re.compile("What should"))
        reel.web(page, hold=0.8, pointer=box, click=True)
        reel.type(page, box, _TASK, per=len(_TASK), rest=0.9)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        page.get_by_role("button", name="Toggle panel").click()
        graph = page.locator("[data-hmz=graph]")
        expect(graph.get_by_text(re.compile(r"^working"))).to_have_count(1)
        reel.web(page, hold=2.2)
        expect(page.get_by_role("button", name="Stop")).to_have_count(0)
        expect(page.get_by_text("Done", exact=True)).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()
        # The one session, and every turn the loop took in it.
        page.locator('a[href*="/sessions/"]').first.click()
        page.wait_for_url(re.compile(r".*/sessions/.+"))
        expect(page.get_by_text("nothing left to change").first).to_be_visible()
        shots.web(page, f"{_PAGE}-session", window="desktop", most=shots.REEL)
