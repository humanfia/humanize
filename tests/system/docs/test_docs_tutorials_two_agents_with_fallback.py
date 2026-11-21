"""The pictures of `docs/tutorials/two-agents-with-fallback.md`: two coding agents, one fallback.

One journey in Humanize Desktop's window, as the page tells it: Codex and Claude Code are both
found, a virtual nous `careful` is made that takes a turn on Codex and carries it on to Claude
Code when Codex fails, an epic of `rlar` is started with `careful` as its actor and a cheaper
model at a higher effort as its reviewer, Codex runs into its usage limit, and the epic says
which model answered and what each cost. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_two_agents_with_fallback.py`.

Three things are staged here that the world does not come with:

- a second coding agent: a stand-in `codex` beside the world's stand-in `claude`, the
  integration tests' own, taught to list a model and to answer what `World.says` scripts;
- a usage limit: that `codex` fails every turn with the words Codex says a limit in, so that
  the turn is waited over and then carried on to the next node of the graph;
- prices: the models that answer, written where a fetched price list is kept, since nothing
  is fetched here and a model nobody prices is shown as tokens alone.
"""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from tests.system.docs import shots
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-two-agents-with-fallback"

_TASK = "Add a discount code to checkout"

#: The nous the page names: the two of the graph, and the reviewer's.
_CODEX = "codex/gpt-6.1-sol:high"
_CLAUDE = "claude/claude-opus-4-1:high"
_REVIEWER = "claude/claude-haiku-4-5:high"

#: What Codex says of a usage limit, which is read as a rate limit: waited over, then left.
_LIMIT = "You've hit your usage limit. Try again later."

#: How long a turn waits over a rate limit before it is carried on, and some more, in ms.
_WAITED = 120_000

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"SPRING10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a discount code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agent that answers does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": "Checkout takes a discount code now: SPRING10 takes 10% off. The tests pass.",
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
            "result": "5 passed in 0.18s",
            "takes": 0.8,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
}

#: The price list as a fetch of OpenLLMPrices keeps it, cut to the models that answer here:
#: dollars per million tokens, as their vendors list them.
_PRICES = {
    "source": "https://openllmprices.com/data/prices.json",
    "etag": "",
    "date": "2026-09-30",
    "models": {
        "claude-haiku-4.5": {
            "provider": "Anthropic",
            "name": "Claude Haiku 4.5",
            "per_million": {
                "input": 1.0,
                "cache_write": 1.25,
                "cache_read": 0.1,
                "output": 5.0,
            },
        },
        "claude-opus-4.1": {
            "provider": "Anthropic",
            "name": "Claude Opus 4.1",
            "per_million": {
                "input": 15.0,
                "cache_write": 18.75,
                "cache_read": 1.5,
                "output": 75.0,
            },
        },
        "gpt-6.1-sol": {
            "provider": "OpenAI",
            "name": "GPT-6.1 Sol",
            "per_million": {
                "input": 2.0,
                "cache_read": 0.1,
                "cache_write": 2.5,
                "output": 10.0,
            },
        },
    },
}

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


def _priced() -> None:
    """Keeps a price list where a fetched one is kept: what a turn cost is then said."""
    from hmz.coganchor import prices

    at = prices.where()
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(json.dumps(_PRICES | {"fetched": time.time()}))


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
    """Writes the virtual nous the page makes, as its form writes it."""
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
                "n2": {"use": _CLAUDE},
            },
        },
        then=None,
    )


def _picked(page: Page, chip: Locator, harness: str, model: str, effort: str) -> None:
    """Picks a concrete nous on a chip, a level at a time, as a person does."""
    chip.click()
    menu = page.locator("[role=menu]").last
    menu.locator("[data-hmz=step-harness]").click()
    # Its model is picked next, with nothing pressed: the level a harness picked leads to.
    menu.locator(f"[role=menuitem][data-cli={harness}]").first.click()
    menu.locator(f".nous-list [data-value='{model}']").click()
    if page.locator("[role=menu]").count() == 0:
        chip.click()
    menu = page.locator("[role=menu]").last
    menu.locator("[data-hmz=step-effort]").click()
    menu.locator(f"[role=menuitem][data-value={effort}]").click()
    if page.locator("[role=menu]").count():
        page.keyboard.press("Escape")
    expect(chip).to_have_attribute("data-agent", f"{harness}/{model}:{effort}")


def test_both_agents_are_found(world: World) -> None:
    _codex(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/nous")
        listing = page.locator("[data-hmz=nous]")
        expect(
            listing.locator("[data-hmz=nous-harness][data-cli=codex]")
        ).to_be_visible()
        expect(listing.locator("[data-hmz=nous-scanned]")).to_contain_text("concrete")
        shots.web(page, f"{_PAGE}-found", window="desktop")


def test_a_virtual_nous_is_made(world: World) -> None:
    _codex(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/nous")
        listing = page.locator("[data-hmz=nous]")
        expect(
            listing.locator("[data-hmz=nous-harness][data-cli=codex]")
        ).to_be_visible()
        expect(listing.locator("[data-hmz=nous-scanned]")).to_contain_text("concrete")
        reel = shots.Reel(f"{_PAGE}-nous", window="desktop")
        add = listing.locator("[data-hmz=nous-add]")
        reel.web(page, hold=1.4, pointer=add, click=True)
        add.click()
        name = page.locator("#nous-name")
        expect(name).to_be_focused()
        page.wait_for_timeout(700)
        name.fill("careful")
        page.locator("#nous-tries").fill("1")
        graph = page.locator("[data-hmz=nous-graph]")
        use = graph.locator("[data-hmz=graph-add-use]")
        use.scroll_into_view_if_needed()
        reel.web(
            page, hold=1.6, pointer=use, click=True, caption="Name it, then add a node"
        )
        use.click()
        first = graph.locator("[data-hmz=graph-node]").nth(0)
        _picked(
            page, first.locator("[data-hmz=pick-model]"), "codex", "gpt-6.1-sol", "high"
        )
        use.scroll_into_view_if_needed()
        reel.web(
            page, hold=1.6, pointer=use, click=True, caption="The first node: Codex"
        )
        use.click()
        second = graph.locator("[data-hmz=graph-node]").nth(1)
        _picked(
            page,
            second.locator("[data-hmz=pick-model]"),
            "claude",
            "claude-opus-4-1",
            "high",
        )
        edge = first.locator("[data-hmz=graph-add-edge]")
        edge.scroll_into_view_if_needed()
        reel.web(
            page,
            hold=1.6,
            pointer=edge,
            click=True,
            caption="The second node: Claude Code",
        )
        edge.click()
        expect(first.locator("[data-hmz=graph-edge-to]")).to_have_value("n2")
        save = page.get_by_role("button", name="Save")
        save.scroll_into_view_if_needed()
        reel.web(
            page,
            hold=2.2,
            pointer=save,
            click=True,
            caption="An edge: on any fault, go to n2",
        )
        save.click()
        row = listing.locator("[data-hmz=nous-row][data-name=careful]")
        expect(row).to_be_visible()
        # Back at the top of the list, where the new row is: the form is under it.
        listing.locator("header").evaluate("el => el.scrollIntoView({block: 'start'})")
        page.wait_for_timeout(700)
        expect(row).to_be_in_viewport()
        reel.web(page, hold=3.5, caption="Saved: careful is listed", poster=True)
        reel.save()
        shots.web(
            page,
            f"{_PAGE}-listed",
            clip=listing.locator("[data-hmz=nous-virtual]"),
            pad=4,
        )
    (careful,) = (one for one in world.call("nous.list")["nous"] if one["virtual"])
    assert careful["tries"] == 1
    assert [one["use"] for one in careful["graph"]["nodes"]] == [_CODEX, _CLAUDE]


def test_an_epic_falls_back(world: World) -> None:
    _priced()
    _codex(world, limited=True)
    _careful(world)
    world.says({"discount": _WORK})
    with world.page(desktop=True) as page:
        go(page, "/new?flow=rlar")
        roles = page.locator("[data-hmz=options] [data-hmz=role-row]")
        actor = roles.and_(page.locator("[data-role=actor]")).locator(
            "[data-hmz=pick-model]"
        )
        reviewer = roles.and_(page.locator("[data-role=reviewer]")).locator(
            "[data-hmz=pick-model]"
        )
        expect(actor).to_be_visible()
        actor.click()
        virtual = page.locator("[role=menu] [data-hmz=pick-virtual]")
        expect(virtual).to_have_text(["careful"])
        shots.web(page, f"{_PAGE}-pick", window="desktop", pointer=virtual)
        virtual.click()
        if page.locator("[role=menu]").count():
            page.keyboard.press("Escape")
        expect(actor).to_have_text("careful")
        _picked(page, reviewer, "claude", "claude-haiku-4-5", "high")
        page.get_by_placeholder("dollars").fill("5")
        box = page.get_by_placeholder("What should rlar do?")
        box.click()
        box.press_sequentially(_TASK)
        shots.web(page, f"{_PAGE}-roles", window="desktop")
        page.keyboard.press("Enter")
        session = page.locator("[data-hmz=graph-session]").first
        expect(session).to_be_visible(timeout=_WAITED)
        # The graph of the epic, where the session of the actor is what is clicked next.
        shots.web(
            page,
            f"{_PAGE}-graph",
            clip=page.locator("[data-hmz=graph] .frame.root"),
            pad=24,
            pointer=session,
        )
        session.click()
        log = page.get_by_role("log")
        expect(log).to_contain_text("trying again in 30s", timeout=_WAITED)
        # The transcript alone: the panel beside it names the folder the world was staged in.
        panel = page.locator(".panel-toggle:visible").first
        panel.click()
        shots.web(page, f"{_PAGE}-waiting", window="desktop")
        panel.click()
        expect(log).to_contain_text("carrying on as", timeout=_WAITED)
        expect(page.get_by_role("link", name="Resume").first).to_be_visible(
            timeout=_WAITED
        )
        expect(page.get_by_text("Spending")).to_be_visible(timeout=_WAITED)
        expect(page.get_by_text("Opus 4.1").first).to_be_visible()
        page.wait_for_timeout(1500)
        # The whole window is what the page is about: the transcript beside the spending.
        shots.web(page, f"{_PAGE}-done", window="desktop", most=shots.REEL)


def test_the_same_from_the_command_line(world: World) -> None:
    _priced()
    _codex(world, limited=True)
    _careful(world)
    world.says({"discount": _WORK})
    shots.cli(
        [
            "hmz",
            "exec",
            "-f",
            "rlar",
            "-a",
            f"actor=careful,reviewer={_REVIEWER}",
            "-p",
            "budget.cost=5",
            _TASK,
        ],
        f"{_PAGE}-exec",
        patience=_WAITED / 1000,
    )
