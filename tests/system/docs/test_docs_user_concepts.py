"""The pictures of `docs/user/concepts.md`: one flow set up in the app, the terminal and a command.

The page is a glossary, and each picture is where its words are seen together: a flow, its
roles, the nous each is given, and the epic that comes of it. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_concepts.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.flows import Flows
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

_TASK = "Add a discount code to checkout"

_ANSWER = (
    "Checkout takes a discount code now: WELCOME10 is 10% off. Two new tests cover"
    " it, and all six pass."
)


def test_a_flow_is_set_up_in_the_app(world: World) -> None:
    world.account("work")
    with world.page(desktop=True) as page:
        go(page, "/new?flow=rlar")
        view = page.locator("[data-hmz=new-epic]")
        expect(view.locator("[data-hmz=flow-picker] b")).to_have_text("rlar")
        expect(view.get_by_text("reviewer", exact=True)).to_be_visible()
        expect(view.get_by_text("Asking…")).to_have_count(0)
        view.get_by_label("Most it may cost, in dollars").fill("5")
        view.get_by_placeholder(re.compile("What should")).fill(_TASK)
        chip = view.get_by_role("button", name=re.compile("Nous: .*Haiku")).first
        chip.click()
        menu = page.locator("[role=menu][aria-label=Nous]")
        expect(menu).to_be_visible()
        shots.web(page, "user-concepts-app", window="desktop")


async def test_a_flow_is_set_up_in_the_terminal(world: World) -> None:
    async with world.tui((96, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/flow", "enter")
        await on(pilot, Flows)
        await onto(pilot, "rlar")
        await pilot.press("enter")
        await shows(pilot, "an epic needs one")
        shots.tui(app, "user-concepts-terminal")


def test_a_flow_is_run_from_the_command_line(world: World) -> None:
    world.says({"discount": {"text": _ANSWER, "after": 0.8}})
    reel = shots.Reel("user-concepts-cli")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor={AGENT}:high",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        rows=12,
    )
    reel.save()
