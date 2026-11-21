"""The pictures of `docs/builder/async.md`: three turns of one agent, taken at once.

The page's flow, `review_parts`, is one of the project's own: a reviewer reads three files
of the shop in three sessions at the same time, then sums the three reviews up in a fourth.
Here it is run from the command line, and watched in the app and in the terminal's monitor
while its three sessions work. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_builder_async.py`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

from hmz.runtime.kept import Runs
from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "builder-async"

_TASK = "Review the shop for bugs"

#: The page's flow, as the page prints it.
_FLOW = '''
import asyncio

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    flow,
)

PARTS = ("catalogue", "cart", "checkout")


class Agents(AgentCollection):
    reviewer: Agent


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def review_parts(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One reviewer reads three files at once, then sums up."""
    reviewer, workspace = agents["reviewer"], envs["workspace"]

    async def review(part: str) -> str:
        session = await reviewer.spawn()  # one session per concurrent turn
        return await reviewer.run(
            f"{task}\\n\\nLook only at shop/{part}.py.", session=session, env=workspace
        )

    notes = await asyncio.gather(*(review(part) for part in PARTS))
    return await reviewer.run(
        "Sum up these reviews:\\n\\n" + "\\n\\n".join(notes),
        session=await reviewer.spawn(),
        env=workspace,
    )
'''


def _own(world: World) -> None:
    """Puts the page's flow among the project's own, as `@local/review_parts`."""
    flow = world.workspace / ".hmz" / "flows" / "review_parts"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_FLOW)


def _script(world: World, *, after: float) -> None:
    """Scripts the three reviews and the summary: each reads its file, then says of it."""

    def line(text: str, part: str) -> dict[str, Any]:
        return {
            "text": text,
            "tools": [
                {
                    "name": "Read",
                    "input": {"file_path": f"shop/{part}.py"},
                    "result": "read",
                    "takes": 0.4,
                }
            ],
            "after": after,
        }

    world.says(
        {
            "Look only at shop/catalogue.py": line(
                "catalogue.py: prices are whole cents and every name is unique."
                " Nothing to fix.",
                "catalogue",
            ),
            "Look only at shop/cart.py": line(
                "cart.py: total() raises KeyError for an item the catalogue does not"
                " list, and accepts a negative count.",
                "cart",
            ),
            "Look only at shop/checkout.py": line(
                "checkout.py: charge() passes the cart straight through. It is"
                " correct, and has no test of its own.",
                "checkout",
            ),
            "Sum up these reviews": (
                "One bug: total() in shop/cart.py accepts a negative count and fails"
                " on an unknown item. catalogue.py and checkout.py are fine;"
                " checkout.py has no test."
            ),
        }
    )


_EXEC = [
    "hmz",
    "exec",
    "-f",
    "@local/review_parts",
    "-a",
    f"reviewer={AGENT}",
    "-p",
    "budget.output_tokens=20000",
    _TASK,
]


def test_three_reviews_from_the_command_line(world: World) -> None:
    _own(world)
    _script(world, after=1.6)
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(_EXEC, rows=26, hold=4.0)
    reel.save()


def _running(world: World) -> str:
    """Starts the flow on the task and answers its epic's name, the three turns under way.

    `World.epic` looks its epic up the instant it started, which may be before it is
    listed: looked up again here until it is.
    """
    try:
        return world.epic(
            "@local/review_parts", _TASK, budget={"output_tokens": 200_000}, until=None
        )
    except StopIteration:
        pass
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        runs = world.call("runs.list", workspace=str(world.workspace))["runs"]
        for one in runs:
            if one["task"] == _TASK:
                return str(one["name"])
        time.sleep(0.2)
    raise AssertionError("the epic was never listed")


def test_three_sessions_in_the_app(world: World) -> None:
    _own(world)
    _script(world, after=60)
    name = _running(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        expect(page.get_by_text("every session")).to_be_visible()
        # The sidebar reads the epic's sessions again as they open: all three are listed.
        expect(page.locator('[data-hmz="session"]')).to_have_count(3, timeout=30_000)
        zoom = page.get_by_role("button", name="Zoom in")
        zoom.click()
        zoom.click()
        page.wait_for_timeout(3000)
        shots.web(page, f"{_PAGE}-app", window="desktop", most=shots.REEL)
    world.stop(name)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_three_sessions_in_the_terminal_monitor(world: World) -> None:
    _own(world)
    _script(world, after=60)
    async with world.tui(size=(108, 34)) as (app, pilot):
        await shows(pilot, MODEL)
        # Set up as its `/flow review_parts` page would leave it: an agent, a budget.
        app.settings.remember(
            "@local/review_parts",
            {"reviewer": Runs(AGENT)},
            {},
            None,
            {"output_tokens": 200_000},
        )
        await pilot.press(*f"/flow @local/review_parts {_TASK}", "enter")
        await shows(pilot, "conversation 3 of 3")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-monitor")
        reel.tui(app, hold=1.8, caption="three turns start")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "3 sessi")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=2.0, keys="left", caption="the monitor")
        await pilot.press("space")
        await shows(pilot, "session 3")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=3.5, keys="space", caption="its sessions", poster=True)
        reel.save()
        await pilot.press(*"/stop", "enter")
        await _settled(pilot, 2.0)
