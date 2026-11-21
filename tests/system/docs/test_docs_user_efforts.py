"""The pictures of `docs/user/efforts.md`: an effort chosen on each interface, and a swarm.

What the page shows: the Effort level of a new chat's chip in Humanize Desktop's window, the
`effort` row of the terminal's agent sheet with its rungs dropped under it, the `swarm` row
that sheet grows for a model that runs a turn as a fleet, and `hmz exec` taking one effort
and refusing a word its coding agent has no rung for. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_efforts.py`.

One thing is staged here that the world does not come with: a stand-in `kimi` beside the
world's stand-in `claude`, which answers only what it is asked when it is asked what it runs.
No turn is taken on it: it is there so that the sheet has a model that swarms to show.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from playwright.sync_api import expect
from textual.widgets import OptionList

from hmz.tui.dropdown import Dropdown
from hmz.tui.pick import Agent, Catalogue, Clis
from tests.integration.doubles_tui import on, onto, opens, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-efforts"

_TASK = "Add a discount code to checkout"

#: The model the stand-in `kimi` says it runs.
_KIMI_MODEL = "kimi-code/k3"

# A `kimi` that can only say what it is and what it runs: two models, each at Kimi Code's
# own thinking levels.
_KIMI = r"""
import json, sys

argv = sys.argv[1:]
if "--version" in argv:
    print("kimi 1.42.0")
    sys.exit(0)
if argv[:2] == ["provider", "list"]:
    efforts = ["low", "medium", "high", "max"]
    print(json.dumps({"models": {
        "kimi-code/k3": {"supportEfforts": efforts},
        "kimi-code/k3-turbo": {"supportEfforts": efforts[:3]},
    }}), flush=True)
    sys.exit(0)
sys.exit(2)
"""


def _kimi(world: World) -> None:
    """Installs the stand-in `kimi` beside the world's `claude`, and has the daemon ask it."""
    at = world._bin / "kimi"  # noqa: SLF001 -- the world's own `bin/`, which it keeps to itself  # pyright: ignore[reportPrivateUsage]
    at.write_text(f"#!{sys.executable}\n{_KIMI}")
    at.chmod(0o755)
    world.call("nous.scan")


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_an_effort_is_picked_on_the_chip(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-hmz=pick-model]").first
        expect(chip).to_be_visible()
        expect(chip).to_contain_text("Haiku 4.5")
        reel = shots.Reel(f"{_PAGE}-chip", window="desktop")
        reel.web(page, hold=1.4, pointer=chip, click=True)
        chip.click()
        menu = page.locator("[role=menu]").last
        effort = menu.locator("[data-hmz=step-effort]")
        expect(effort).to_be_visible()
        reel.web(
            page,
            hold=1.6,
            pointer=effort,
            click=True,
            caption="The chip's last level is Effort",
        )
        effort.click()
        low = menu.get_by_role("menuitem", name="Low", exact=True)
        expect(low).to_be_visible()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-levels", clip=menu, pad=28, pointer=low)
        reel.web(
            page,
            hold=2.2,
            pointer=low,
            click=True,
            caption="The efforts this model takes, hardest first",
        )
        low.click()
        if page.locator("[role=menu]").count():
            page.keyboard.press("Escape")
        expect(chip).to_contain_text("Low")
        page.wait_for_timeout(400)
        reel.web(page, hold=3.2, caption="The chat will think at Low", poster=True)
        reel.save()


async def test_an_effort_is_picked_on_the_sheet(world: World) -> None:
    async with world.tui((96, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal")
        await typed(pilot, "/settings workspace")
        await shows(pilot, "Chat agent")
        await onto(pilot, "chat-agent")
        await pilot.press("enter")
        await on(pilot, Agent)
        await opens(pilot, "cli")
        await on(pilot, Clis)
        await opens(pilot, "claude")
        await on(pilot, Agent)
        await opens(pilot, "model")
        await on(pilot, Catalogue)
        await shows(pilot, MODEL)
        await opens(pilot, MODEL)
        await on(pilot, Agent)
        await onto(pilot, "effort")
        await _settled(pilot)
        reel.tui(app, hold=2.0, caption="The agent sheet: effort is the last row")
        await pilot.press("enter")
        dropped = await on(pilot, Dropdown)
        await _settled(pilot)
        reel.tui(app, hold=2.4, keys="enter", caption="The model's efforts")
        listing = dropped.query_one(OptionList)
        at = [str(one.id) for one in listing.options].index("=low")
        for _ in range(len(listing.options) + 1):
            if listing.highlighted == at:
                break
            await pilot.press("down" if (listing.highlighted or 0) < at else "up")
        await _settled(pilot)
        reel.tui(app, hold=1.4, keys="down", caption="Down to low")
        await pilot.press("enter")
        await on(pilot, Agent)
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="enter", caption="Picked", poster=True)
        reel.save()


async def test_a_model_that_swarms_has_a_switch(world: World) -> None:
    _kimi(world)
    async with world.tui((96, 28)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await typed(pilot, "/settings workspace")
        await shows(pilot, "Chat agent")
        await onto(pilot, "chat-agent")
        await pilot.press("enter")
        await on(pilot, Agent)
        await opens(pilot, "cli")
        await on(pilot, Clis)
        await opens(pilot, "kimi")
        await on(pilot, Agent)
        await opens(pilot, "model")
        await on(pilot, Catalogue)
        await shows(pilot, _KIMI_MODEL, "swarms")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-models")
        await opens(pilot, _KIMI_MODEL)
        await on(pilot, Agent)
        await shows(pilot, "run turns as a swarm")
        await _settled(pilot)
        await opens(pilot, "swarm")
        await on(pilot, Dropdown)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-swarm")


def test_an_effort_is_written_on_a_command_line(world: World) -> None:
    world.says(
        {"discount": "Checkout takes a discount code now: SPRING10 takes 10% off."}
    )
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            "worker=claude/claude-haiku-4-5:low",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-exec",
    )


def test_a_word_off_the_ladder_is_refused(world: World) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            "worker=claude/claude-haiku-4-5:turbo",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-refused",
    )


def test_a_swarm_is_refused_where_there_is_none(world: World) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            "worker=claude/claude-haiku-4-5:swarmmax",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        f"{_PAGE}-noswarm",
    )
