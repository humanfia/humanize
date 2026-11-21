"""The home page's pictures: Humanize Desktop, the terminal interface and the CLI at work.

`docs/index.md` (the product page, `docs/.vitepress/theme/components/product`) shows three
reels, each a flow handed one task: in the app's window, in `hmz`, and with `hmz exec`. Run
it by naming it: `uv run pytest tests/system/docs/test_docs_home.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from tests.integration.doubles_tui import (
    gives_a_budget,
    leaves,
    on,
    onto,
    shows,
)
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a coupon code to checkout"

#: What the agent does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": "Checkout takes a coupon now: WELCOME10 is 10% off. All six tests pass.",
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.4,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.6,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 0.8,
        },
    ],
}


def test_the_app_is_handed_a_task_and_runs_it(world: World) -> None:
    world.says({"coupon": _WORK | {"after": 4}})
    reel = shots.Reel("home-desktop", window="desktop")
    reel.splash("starting", hold=1.1)
    with world.page(desktop=True) as page:
        go(page, "/new")
        view = page.locator("[data-hmz=new-epic]")
        picker = view.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).not_to_have_text("…")
        expect(view.get_by_text("Asking…")).to_have_count(0)
        reel.web(page, hold=1.1, pointer=picker, click=True)
        picker.click()
        flow = page.get_by_text("rlar", exact=True)
        expect(flow).to_be_visible()
        reel.web(page, hold=1.3, pointer=flow, click=True)
        flow.click()
        expect(picker.locator("b")).to_have_text("rlar")
        expect(view.get_by_text("reviewer", exact=True)).to_be_visible()
        expect(view.get_by_text("Asking…")).to_have_count(0)
        cost = view.get_by_label("Most it may cost, in dollars")
        reel.web(page, hold=0.9, pointer=cost, click=True)
        cost.fill("5")
        box = view.get_by_placeholder(re.compile("What should"))
        reel.web(page, hold=0.7, pointer=box, click=True)
        reel.type(page, box, _TASK, per=len(_TASK), rest=0.9)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+$"))
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        # The panel beside the graph is folded with its own button: the graph is what this
        # picture is of, and the whole window with the panel open is too large a file.
        page.get_by_role("button", name="Toggle panel").click()
        graph = page.locator("[data-hmz=graph]")
        expect(graph.get_by_text(re.compile(r"^working"))).to_have_count(1)
        expect(graph.get_by_text("not started")).to_have_count(1)
        reel.web(page, hold=2.4)
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(page.get_by_text("Done", exact=True)).to_be_visible()
        reel.web(page, hold=4, poster=True)
    reel.save()


async def test_the_terminal_picks_a_flow_and_runs_it(world: World) -> None:
    world.says({"coupon": _WORK | {"after": 3}})
    async with world.tui((96, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel("home-terminal")
        reel.tui(app, hold=1.1)
        await pilot.press(*"/flow")
        await pilot.pause()
        reel.tui(app, hold=0.6, keys="/flow", cut=True)
        await pilot.press("enter")
        await on(pilot, Flows)
        reel.tui(app, hold=1.1, keys="enter")
        await onto(pilot, "rlar")
        reel.tui(app, hold=1.0, keys="down", caption="to the flow")
        await pilot.press("enter")
        await shows(pilot, "an epic needs one")
        reel.tui(app, hold=1.3, keys="enter")
        await gives_a_budget(pilot)
        await shows(pilot, "stops at $1.00")
        reel.tui(app, hold=1.3, caption="a budget of one dollar")
        await leaves(pilot)
        await shows(pilot, "set up: /flow rlar <task> starts it")
        reel.tui(app, hold=1.1, keys="esc", caption="saved")
        line = f"/flow rlar {_TASK}"
        await pilot.press(*line)
        await pilot.pause()
        reel.tui(app, hold=0.9, caption="the task", cut=True)
        await pilot.press("enter")
        await shows(pilot, "is working", "reviewer")
        reel.tui(app, hold=1.8, keys="enter")
        await shows(pilot, "the flow is done")
        reel.tui(app, hold=4, poster=True)
        reel.save()


def test_the_command_line_runs_a_flow(world: World) -> None:
    world.says({"coupon": _WORK | {"after": 0.8}})
    reel = shots.Reel("home-cli")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            f"worker={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        rows=13,
    )
    reel.save()
