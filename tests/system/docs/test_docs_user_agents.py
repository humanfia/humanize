"""The pictures of `docs/user/agents.md`: the coding agents, and how one is named.

What the page shows of each interface: the nous chip of a new chat walked a level at a time in
Humanize Desktop's window -- harness, then model, with `Refresh models` under the list -- the
agent sheet of the terminal interface and the models its coding agent last reported, and an
agent written as `CLI/MODEL:EFFORT` on a command line, once well and once misspelled. Run it
by naming it: `uv run pytest tests/system/docs/test_docs_user_agents.py`.

One thing is staged here that the world does not come with: a second coding agent, a stand-in
`codex` beside the world's stand-in `claude` -- the integration tests' own, taught to list a
model -- so that there is more than one harness to pick from.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.pick import Agent, Catalogue, Clis
from tests.integration.doubles_tui import on, onto, opens, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-agents"

_TASK = "Add a discount code to checkout"

# What is put before the integration tests' stand-in `codex`: its version, and the one model
# it lists when it is asked what it runs.
_CODEX_HEAD = r"""
import json, os, pathlib, sys

argv = sys.argv[1:]


def note(said=""):
    pass


def out(obj):
    print(json.dumps(obj), flush=True)


if "--version" in argv:
    print("codex-cli 0.166.0")
    sys.exit(0)
if argv[:2] == ["debug", "models"]:
    levels = [{"effort": one} for one in ("low", "medium", "high", "xhigh")]
    out({"models": [{"slug": "gpt-6.1-sol", "visibility": "list",
                     "supported_reasoning_levels": levels}]})
    sys.exit(0)

"""


def _codex(world: World) -> None:
    """Installs a stand-in `codex` beside the world's `claude`, and has the daemon ask it."""
    from tests.integration.doubles_agents import CODEX

    at = world._bin / "codex"  # noqa: SLF001 -- the world's own `bin/`, which it keeps to itself
    at.write_text(f"#!{sys.executable}\n{_CODEX_HEAD}\n{CODEX}\n")
    at.chmod(0o755)
    world.call("nous.scan")


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_chip_picks_a_harness_then_a_model(world: World) -> None:
    _codex(world)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-hmz=pick-model]").first
        expect(chip).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-chip", window="desktop")
        reel.web(page, hold=1.4, pointer=chip, click=True)
        chip.click()
        menu = page.locator("[role=menu]").last
        harness = menu.locator("[data-hmz=step-harness]")
        expect(harness).to_be_visible()
        reel.web(
            page,
            hold=1.8,
            pointer=harness,
            click=True,
            caption="The chip opens on its levels",
        )
        harness.click()
        codex = menu.locator("[role=menuitem][data-cli=codex]").first
        expect(codex).to_be_visible()
        reel.web(
            page,
            hold=1.8,
            pointer=codex,
            click=True,
            caption="Harness: the coding agents installed here",
        )
        codex.click()
        model = menu.locator(".nous-list [data-value='gpt-6.1-sol']")
        expect(model).to_be_visible()
        expect(menu.locator("[data-hmz=pick-refresh]")).to_be_visible()
        reel.web(
            page,
            hold=2.2,
            pointer=model,
            click=True,
            caption="Model: what that harness says it runs",
        )
        model.click()
        if page.locator("[role=menu]").count():
            page.keyboard.press("Escape")
        expect(chip).to_have_attribute("data-agent", "codex/gpt-6.1-sol")
        page.wait_for_timeout(400)
        reel.web(page, hold=3.2, caption="The chat will run on Codex", poster=True)
        reel.save()


def test_the_model_level_lists_what_the_harness_runs(world: World) -> None:
    _codex(world)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        chip = page.locator("[data-hmz=pick-model]").first
        expect(chip).to_be_visible()
        chip.click()
        menu = page.locator("[role=menu]").last
        menu.locator("[data-hmz=step-model]").click()
        refresh = menu.locator("[data-hmz=pick-refresh]")
        expect(refresh).to_be_visible()
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-models", clip=menu, pad=28, pointer=refresh)


async def test_an_agent_is_set_up_in_the_terminal(world: World) -> None:
    _codex(world)
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-terminal")
        await typed(pilot, "/settings workspace")
        await shows(pilot, "Chat agent")
        await onto(pilot, "chat-agent")
        await _settled(pilot)
        reel.tui(app, hold=1.6, keys="/settings workspace")
        await pilot.press("enter")
        await on(pilot, Agent)
        await _settled(pilot)
        reel.tui(app, hold=2.0, keys="enter", caption="One agent: four rows")
        await opens(pilot, "cli")
        await on(pilot, Clis)
        await _settled(pilot)
        reel.tui(app, hold=2.2, keys="enter", caption="The coding agents installed")
        shots.tui(app, f"{_PAGE}-terminal-clis")
        await opens(pilot, "claude")
        await on(pilot, Agent)
        await opens(pilot, "model")
        await on(pilot, Catalogue)
        await shows(pilot, "Check again")
        await _settled(pilot)
        reel.tui(app, hold=2.6, keys="enter", caption="Its models, and Check again")
        shots.tui(app, f"{_PAGE}-terminal-models")
        await opens(pilot, MODEL)
        await on(pilot, Agent)
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="enter", caption="The agent, set up", poster=True)
        reel.save()


def test_an_agent_is_named_on_a_command_line(world: World) -> None:
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
        columns=104,
    )


def test_a_misspelled_agent_is_refused(world: World) -> None:
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "goal",
            "-a",
            "worker=claud/claude-haiku-4-5:low",
            _TASK,
        ],
        f"{_PAGE}-refused",
        columns=104,
    )
