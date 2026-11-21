"""The pictures of `docs/user/nous.md`: models, retries and fallback.

What the page shows of a nous on each interface: the Nous page of Settings in Humanize
Desktop's window, the chip a nous is picked on a level at a time, the form a virtual nous and
its graph are written on, the same page and form in the terminal interface, and a chat from
the command line whose agent is a virtual nous and whose first model fails. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_user_nous.py`.

Two things are staged here that the world does not come with:

- a second coding agent: a stand-in `codex` beside the world's stand-in `claude`, the
  integration tests' own, taught to list a model and to answer what `World.says` scripts;
- a usage limit: that `codex` fails every turn with the words Codex says a limit in, so that
  the turn is waited over and then carried on to the next node of the graph.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.integration.doubles_tui import opens, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-nous"

_TASK = "Add a discount code to checkout"

#: The concrete nous the page names.
_CODEX = "codex/gpt-6.1-sol:high"
_OPUS = "claude/claude-opus-4-1:high"
_HAIKU = "claude/claude-haiku-4-5"

#: What Codex says of a usage limit, which is read as a rate limit: waited over, then left.
_LIMIT = "You've hit your usage limit. Try again later."

#: How long a turn waits over a rate limit before it is carried on, and some more, in ms.
_WAITED = 120_000

# What is put before the integration tests' stand-in `codex`: its version, the one model it
# lists, and what a scene scripted it to answer.
_CODEX_HEAD = r"""
import json, os, pathlib, sys

argv = sys.argv[1:]
LINES = pathlib.Path(sys.argv[0]).with_name("lines.json")


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


def scripted(said):
    try:
        lines = json.loads(LINES.read_text())
    except OSError:
        lines = []
    line = next((line for key, line in lines if key in said), None)
    return "Done." if line is None else line.get("text", "")

"""


def _codex(world: World, *, limited: bool = False) -> None:
    """Installs a stand-in `codex` beside the world's `claude`, and has the daemon find it.

    Args:
      world: The world.
      limited: Whether every turn of it fails saying its usage limit is spent.
    """
    from tests.integration.doubles_agents import CODEX

    body = CODEX
    was = '    answer = json.dumps({"value": said}) if asked.get("outputSchema") else said\n'
    assert body.count(was) == 1, "the stand-in codex no longer answers so"
    body = body.replace(
        was,
        '    answer = json.dumps({"done": True, "notes": "reviewed"})'
        ' if asked.get("outputSchema") else scripted(said)\n',
    )
    was = '    if said == "unfinished":\n'
    assert body.count(was) == 1, "the stand-in codex no longer fails so"
    body = body.replace(
        was,
        "    if LIMIT:\n"
        '        done(thread, status="failed", error={"message": LIMIT})\n'
        "        return\n" + was,
    )
    at = world._bin / "codex"  # noqa: SLF001 -- the world's own `bin/`, which it keeps to itself
    limit = _LIMIT if limited else ""
    at.write_text(f"#!{sys.executable}\n{_CODEX_HEAD}\nLIMIT = {limit!r}\n{body}\n")
    at.chmod(0o755)
    world.call("nous.scan")


def _careful(world: World) -> None:
    """Writes a virtual nous: Codex first, Claude Code once Codex fails with anything."""
    world.call(
        "nous.set",
        name="careful",
        tries=1,
        policy="exponential-jitter",
        timeout=0,
        graph={
            "start": "n1",
            "nodes": {
                "n1": {"use": _CODEX, "on": {"*": "n2"}},
                "n2": {"use": _OPUS},
            },
        },
        then=None,
    )


def _fast(world: World) -> None:
    """Writes a virtual nous with a balance node, and a concrete one that is tried again."""
    world.call(
        "nous.set",
        name="fast",
        tries=2,
        policy="exponential",
        timeout=300,
        graph={
            "start": "n1",
            "nodes": {
                "n1": {
                    "balance": "round-robin",
                    "among": [
                        {"nous": _HAIKU, "weight": 2},
                        {"nous": "codex/gpt-6.1-sol:low", "weight": 1},
                    ],
                    "spread": 0,
                    "on": {"throttled": "n2"},
                },
                "n2": {"use": "careful"},
            },
        },
        then=None,
    )
    world.call(
        "nous.set",
        name="claude/claude-haiku-4-5",
        tries=3,
        policy="fibonacci",
        timeout=60,
        graph=None,
        then={"start": "n1", "nodes": {"n1": {"use": "claude/claude-opus-4-1"}}},
    )


def _listing(page: Page) -> Locator:
    """The Nous page of Settings, read: both harnesses found."""
    go(page, "/settings/nous")
    listing = page.locator("[data-hmz=nous]")
    expect(listing.locator("[data-hmz=nous-harness][data-cli=codex]")).to_be_visible()
    expect(listing.locator("[data-hmz=nous-scanned]")).to_contain_text("concrete")
    return listing


def test_the_nous_page(world: World) -> None:
    _codex(world)
    _careful(world)
    _fast(world)
    with world.page(desktop=True) as page:
        listing = _listing(page)
        expect(listing.locator("[data-hmz=nous-row][data-name=fast]")).to_be_visible()
        shots.web(page, f"{_PAGE}-page", window="desktop")


def test_a_nous_is_picked_on_the_chip(world: World) -> None:
    _codex(world)
    _careful(world)
    world.account("work")
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
        expect(menu.locator("[data-hmz=step-account]")).to_be_visible()
        reel.web(
            page,
            hold=2.4,
            pointer=harness,
            click=True,
            caption="Virtual nous first, then a concrete one, a level at a time",
        )
        harness.click()
        codex = menu.locator("[role=menuitem][data-cli=codex]").first
        expect(codex).to_be_visible()
        reel.web(page, hold=1.6, pointer=codex, click=True, caption="Harness")
        codex.click()
        model = menu.locator(".nous-list [data-value='gpt-6.1-sol']")
        expect(model).to_be_visible()
        reel.web(page, hold=1.6, pointer=model, click=True, caption="Model")
        model.click()
        if page.locator("[role=menu]").count() == 0:
            chip.click()
        menu = page.locator("[role=menu]").last
        menu.locator("[data-hmz=step-effort]").click()
        high = menu.locator("[role=menuitem][data-value=high]")
        expect(high).to_be_visible()
        reel.web(page, hold=1.6, pointer=high, click=True, caption="Effort")
        high.click()
        if page.locator("[role=menu]").count():
            page.keyboard.press("Escape")
        expect(chip).to_have_attribute("data-agent", _CODEX)
        reel.web(page, hold=3, caption="The chip says what was picked", poster=True)
        reel.save()


def _fits(page: Page, part: Locator) -> None:
    """Scrolls a part of the Settings dialog to its top, and holds that all of it shows."""
    part.evaluate("el => el.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(700)
    inside = part.evaluate(
        """el => {
            let box = el.parentElement
            const scrolls = (one) => /auto|scroll/.test(getComputedStyle(one).overflowY)
            while (box && !scrolls(box)) box = box.parentElement
            const mine = el.getBoundingClientRect(), its = box.getBoundingClientRect()
            return [mine.top - its.top, its.bottom - mine.bottom]
        }"""
    )
    assert min(inside) >= 0, f"it is cut off by the dialog: {inside}"


def test_a_graph_is_written_on_the_form(world: World) -> None:
    _codex(world)
    _careful(world)
    _fast(world)
    with world.page(desktop=True) as page:
        listing = _listing(page)
        form = page.locator("[data-hmz=write-nous]")
        row = listing.locator("[data-hmz=nous-row][data-name=careful]")
        row.locator("[data-hmz=nous-edit]").click()
        expect(form.locator("[data-hmz=graph-edge-to]")).to_have_value("n2")
        graph = form.locator("[data-hmz=nous-graph]")
        _fits(page, graph)
        shots.web(page, f"{_PAGE}-graph", clip=graph, pad=12)

        row = listing.locator("[data-hmz=nous-row][data-name=fast]")
        row.locator("[data-hmz=nous-edit]").evaluate("el => el.click()")
        expect(form.locator("[data-hmz=graph-strategy]")).to_be_visible()
        retries = form.locator("#nous-tries").locator(
            "xpath=ancestor::div[contains(@class,'field')][2]"
        )
        _fits(page, retries)
        shots.web(page, f"{_PAGE}-retries", clip=retries, pad=12)
        balance = form.locator("[data-hmz=graph-node][data-id=n1]")
        _fits(page, balance)
        shots.web(page, f"{_PAGE}-balance", clip=balance, pad=4)


async def test_the_nous_page_in_the_terminal(world: World) -> None:
    _codex(world)
    _careful(world)
    _fast(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings nous")
        await shows(pilot, "careful", "round-robin")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-terminal")

        reel = shots.Reel(f"{_PAGE}-terminal-graph")
        await pilot.press("down")
        await pilot.pause()
        reel.tui(app, hold=1.6, keys="down", caption="to a nous")
        await pilot.press("enter")
        await shows(pilot, "how many times to retry a failed turn")
        reel.tui(app, hold=2.6, keys="enter", caption="its tries, policy and limit")
        await opens(pilot, "graph")
        await shows(pilot, "the node a turn is taken at first")
        reel.tui(app, hold=2.6, keys="enter", caption="its graph: one row per node")
        await opens(pilot, "node:n1")
        await shows(pilot, "what the edges call it")
        reel.tui(app, hold=3.2, keys="enter", caption="a balance node", poster=True)
        reel.save()


def test_a_chat_falls_back_from_the_command_line(world: World) -> None:
    _codex(world, limited=True)
    _careful(world)
    world.says(
        {
            "discount": {
                "text": "Checkout takes a discount code now: SPRING10 is 10% off."
            }
        }
    )
    shots.cli(
        ["hmz", "chat", "-a", "careful", _TASK],
        f"{_PAGE}-chat",
        patience=_WAITED / 1000,
    )
