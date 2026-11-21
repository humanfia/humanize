"""The pictures of `docs/user/watch-a-run.md`: an epic watched while it runs.

One run of `rlar` on one task, caught in its second round -- the actor has worked, a reviewer
has read it and handed it back, and the actor is working again -- and looked at from each
interface: the app's epic view (graph, list, an agent picked out, a session's thread, the Epic
panel), the terminal's log and monitor (graph, an agent opened out, list, the epic page), and
what `hmz exec` prints as the same run goes. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_watch_a_run.py`.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.runtime.kept import Runs
from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import (
    AGENT,
    MODEL,
    _heard,  # pyright: ignore[reportPrivateUsage]
    _roles,  # pyright: ignore[reportPrivateUsage]
)
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-watch-a-run"

_TASK = "Add a discount code to checkout"

#: What the reviewer hands back after the first round, which is what the actor is told next.
_NOTES = (
    "The discount works, but a code past its date is still accepted."
    " Make charge() refuse it, and add a test for that."
)


def _script(world: World, *, second: float) -> None:
    """Scripts two rounds of `rlar`: the actor works, is sent back once, and works again.

    The first key found in what an agent is told answers it, so the order here is the order
    they are tried in: the second review (it alone is told of `ExpiredCode`), the first
    review, the actor's second turn (it is told the first review's notes), and its first.

    Args:
      world: The world, whose agent is scripted.
      second: How many seconds the actor's second turn thinks before it answers: long, for a
        picture of a run under way.
    """
    world.says(
        {
            "ExpiredCode": {
                "json": {
                    "done": True,
                    "notes": (
                        "Done: WELCOME10 takes 10% off, a code past its date is"
                        " refused, and both are tested. 7 passed."
                    ),
                },
                "after": 1.0,
            },
            "meticulous reviewer": {
                "json": {"done": False, "notes": _NOTES},
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "git diff"},
                        "result": "shop/checkout.py | 9 +++++++--",
                        "takes": 0.8,
                    }
                ],
                "after": 1.2,
            },
            "still accepted": {
                "text": (
                    "charge() now raises ExpiredCode for a code past its date, and a"
                    " test covers it. 7 passed."
                ),
                "tools": [
                    {
                        "name": "Edit",
                        "input": {"file_path": "shop/checkout.py"},
                        "result": "edited",
                        "takes": 0.6,
                    },
                    {
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                        "result": "7 passed in 0.19s",
                        "takes": 0.8,
                    },
                ],
                "after": second,
            },
            "discount": {
                "text": (
                    "Added a discount code to checkout: charge() takes a code, and"
                    " WELCOME10 takes 10% off. 6 passed."
                ),
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
                        "result": "6 passed in 0.17s",
                        "takes": 0.8,
                    },
                ],
                "after": 1.2,
            },
        }
    )


def _started(world: World) -> str:
    """Starts `rlar` on the task and answers its epic's name, the epic still running.

    `World.epic(until=None)` asks for the epic's name the moment it has started, which is
    sometimes before it is listed: this waits until it is.
    """
    here = str(world.workspace)
    with world.session() as session:
        sub = session.call("epic.attach", workspace=here)["sub"]
        session.call(
            "epic.start",
            sub=sub,
            flow="rlar",
            task=_TASK,
            budget={"duration": 1800, "output_tokens": 200_000},
            agents=dict.fromkeys(_roles(session, "rlar", here), AGENT),
            idem=uuid.uuid4().hex,
        )
        world._until(session, lambda: _heard(session, sub, "started") >= 1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        def listed() -> list[str]:
            runs = session.call("runs.list", workspace=here)["runs"]
            return [str(one["name"]) for one in runs if one["task"] == _TASK]

        world._until(session, listed)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        name = listed()[0]
        session.call("epic.detach", sub=sub)
    return name


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_epic_view_of_a_run_under_way(world: World) -> None:
    _script(world, second=240)
    name = _started(world)
    with world.page(desktop=True) as page:
        go(page, f"/epics/{name}")
        expect(page.get_by_role("button", name="Stop")).to_be_visible()
        graph = page.locator("[data-hmz=graph]")
        # The second round: the actor is at its second turn, the reviewer has read once.
        expect(graph.get_by_text("2 turns")).to_be_visible(timeout=60_000)
        expect(graph.get_by_text(re.compile(r"^working"))).to_have_count(1)
        expect(graph.get_by_text(re.compile(r"^idle"))).to_have_count(1)
        page.wait_for_timeout(2500)
        # The graph with the panel shut, so that it is drawn large.
        toggle = page.get_by_role("button", name="Toggle panel")
        toggle.click()
        page.wait_for_timeout(800)
        page.get_by_role("button", name="Zoom in").click()
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-graph", window="desktop", most=shots.REEL)
        page.get_by_role("button", name="Recenter").click()
        toggle.click()
        page.wait_for_timeout(800)

        # The Epic panel, alone: figures, handovers, spending.
        shots.web(page, f"{_PAGE}-panel", clip=page.locator(".panel-pane"), pad=0)

        # An agent picked out: its node centred, and a section for it atop the panel.
        # (A still: two frames of an epic's graph are more than a reel may weigh.)
        nodes = graph.locator("[data-hmz=graph-agent]")
        actor = nodes.filter(has_text="actor")
        head = actor.locator(".node-head")
        head.click()
        page.wait_for_url(re.compile(r".*/agents/.+"))
        page.wait_for_timeout(1000)
        shots.web(
            page, f"{_PAGE}-pick", clip="#page", pad=0, pointer=head, most=shots.REEL
        )
        row = actor.locator("[data-hmz=graph-session]").first

        # One of its sessions, read as a thread.
        row.click()
        expect(page.locator("[data-hmz=thread]")).to_contain_text("WELCOME10")
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-thread", window="desktop", most=shots.REEL)

        # The same agents as a list.
        go(page, f"/epics/{name}")
        expect(graph.get_by_text("2 turns")).to_be_visible()
        page.get_by_role("button", name="List", exact=True).click()
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-list", window="desktop", most=shots.REEL)
        page.get_by_role("button", name="Graph", exact=True).click()
    world.stop(name)


async def test_the_log_and_the_monitor_in_the_terminal(world: World) -> None:
    _script(world, second=240)
    world.call("settings.set", details=True)
    async with world.tui(size=(100, 34)) as (app, pilot):
        await shows(pilot, MODEL)
        # Set up as its `/flow rlar` page would leave it: an agent a role, and a budget.
        app.settings.remember(
            "rlar",
            {"actor": Runs(AGENT), "reviewer": Runs(AGENT)},
            {},
            None,
            {"duration": "PT30M", "output_tokens": 200_000},
        )
        await pilot.press(*f"/flow rlar {_TASK}", "enter")
        await shows(pilot, "ctrl+c twice to stop")
        await _settled(pilot, 9.0)
        shots.tui(app, f"{_PAGE}-log")

        reel = shots.Reel(f"{_PAGE}-monitor")
        reel.tui(app, hold=1.6, caption="the log of the agent at work")
        await pilot.press("left")
        await shows(pilot, "monitor · graph", "2 turns")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=2.6, keys="left", caption="the monitor: one box per agent")
        shots.tui(app, f"{_PAGE}-monitor-graph")
        await pilot.press("space")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=2.6, keys="space", caption="an agent opened to its sessions")
        await pilot.press("ctrl+t")
        await shows(pilot, "monitor · list")
        await _settled(pilot, 1.0)
        reel.tui(
            app, hold=3.2, keys="ctrl+t", caption="the same as a list", poster=True
        )
        reel.save()

        # The epic's own page, from the monitor's first row.
        await pilot.press("ctrl+t")
        await shows(pilot, "monitor · graph")
        await pilot.press("space")  # shut again; the cursor is on the first agent
        await pilot.press("up")
        await _settled(pilot)
        await pilot.press("enter")
        await shows(pilot, "Figures", "Budget")
        await _settled(pilot, 1.0)
        shots.tui(app, f"{_PAGE}-epic-page")
        await pilot.press("escape")
        await pilot.press(*"/stop", "enter")
        await _settled(pilot, 2.0)


def test_what_exec_prints_as_the_run_goes(world: World) -> None:
    _script(world, second=1.0)
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor={AGENT}",
            "-a",
            f"reviewer={AGENT}",
            "-p",
            "budget.output_tokens=200k",
            _TASK,
        ],
        f"{_PAGE}-exec",
        columns=96,
    )
