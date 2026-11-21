"""The pictures of `docs/user/history.md`: what ran, found again and read back.

A project with four epics behind it -- two that finished, one that failed and one its budget
ended -- and a chat: the sidebar's list with one epic opened out into its agents and their
sessions, an epic's menu, and Search narrowed to the epics that failed, in the app; and in the
terminal interface `/epics`, one epic's menu, its graph read back and one of its sessions read
whole, and the epics another machine's daemon holds. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_history.py`.

The other machine is this one under a home of its own, reached by the stand-in `ssh` of the
integration tests (`doubles_ssh`), staged under the world's own temporary directory so that no
path of it names whoever runs the suite.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from hmz.daemon import where
from hmz.runtime import Hmz
from hmz.runtime.epic import Epic
from hmz.tui.epic import Graph, SessionRead
from hmz.tui.pick import Does, Epics, RemoteEpics
from tests.integration.doubles_ssh import faked
from tests.integration.doubles_tui import on, onto, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Locator, Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-history"

#: The epics the project has behind it, oldest first, each by its task.
_CURRENCY = "Show prices with a currency symbol"
_RECEIPT = "Send a receipt by email"
_CATALOGUE = "Tidy the catalogue module"
_DISCOUNT = "Add a discount code to checkout"

#: A chat had there too.
_CENT = "Why is the cart total off by a cent?"

#: What the actor does when told the newest task: reads, edits, tests, and says so.
_WORK = {
    "text": (
        "Checkout takes a discount code now: charge() looks the code up and takes its"
        " discount off the total. WELCOME10 is 10% off. Two new tests cover it, and all"
        " six pass."
    ),
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.3,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.3,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 0.4,
        },
    ],
}

#: What the reviewer does with it: reads the diff, runs the tests, and passes it.
_REVIEW = {
    "json": {
        "done": True,
        "notes": "charge() takes a code and WELCOME10 takes 10% off. All six tests pass.",
    },
    "tools": [
        {
            "name": "Bash",
            "input": {"command": "git diff"},
            "result": "shop/checkout.py | 7 +++++--",
            "takes": 0.3,
        },
    ],
}

#: What the agent says of the catalogue, round after round, until its budget ends it.
_ROUNDS = [
    "Split the catalogue's prices from its names: shop/catalogue.py reads cleaner.",
    "Typed the catalogue throughout; the type check is clean.",
    "Dropped two helpers nothing called. 6 passed.",
    "Sorted the catalogue by name, with a test that it stays sorted. 7 passed.",
    "Wrote the module up in README.md.",
    "Read it through again: nothing is left to tidy.",
    "Ran the whole suite twice over: 7 passed, nothing flaky.",
    "Read it through once more: nothing is left to do.",
    "Nothing is left to do.",
    "Nothing is left to do.",
]


def _epic(world: World, flow: str, task: str, **how: Any) -> str:
    """Starts an epic once the one before it is let go of, and answers its name.

    An epic that failed is said to have ended a moment before its host lets go of it: one
    started in that moment is refused as `a flow is already running`, or is told the
    failure of the one before as its own. So no epic is started while a host holds one.
    """
    deadline = time.monotonic() + 60
    here = str(world.workspace)
    while any(
        one.get("held") for one in world.call("runs.list", workspace=here)["runs"]
    ):
        assert time.monotonic() < deadline, "the epic before was never let go of"
        time.sleep(0.3)
    time.sleep(0.5)
    return world.epic(flow, task, **how)


def _history(world: World, *, chat: bool = False) -> dict[str, str]:
    """Stages what the project has behind it, and answers each epic's name by its task."""
    world.says(
        {
            "meticulous reviewer": _REVIEW,
            "currency": "Prices are shown with a currency symbol now: $12.00.",
            "receipt": {"fail": "the connection to the model was lost"},
            "catalogue": {"text": _ROUNDS, "after": 0.1},
            "discount": _WORK,
            "cent": "total() rounded each line before adding them up. It adds first now.",
        }
    )
    names = {_CURRENCY: _epic(world, "goal", _CURRENCY)}
    names[_RECEIPT] = _epic(world, "goal", _RECEIPT, failing=True)
    names[_CATALOGUE] = _epic(
        world, "stateful_ralph", _CATALOGUE, budget={"output_tokens": 300}
    )
    if chat:
        world.chat(_CENT)
    names[_DISCOUNT] = _epic(world, "rlar", _DISCOUNT)
    return names


def _row(page: Page, task: str) -> Locator:
    """An epic's row in the sidebar, by its task."""
    return page.locator("[data-hmz=sidebar] .side-item").filter(has_text=task).first


def _listed(page: Page) -> None:
    """Waits until the sidebar lists the history as it ended: nothing of it still going."""
    go(page, "/new/chat")
    expect(page.get_by_role("textbox", name="First message")).to_be_visible()
    expect(_row(page, _DISCOUNT)).to_be_visible()
    expect(page.locator(".side-scroll").get_by_text("Running")).to_have_count(0)
    # The box says what it runs once it has read it: `Asking…` until then.
    expect(page.get_by_text("Haiku 4.5").first).to_be_visible()


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- in the app -----------------------------------------------------------------------


def test_an_epic_is_opened_out_into_its_agents_and_sessions(world: World) -> None:
    _history(world)
    with world.page(desktop=True, height=720) as page:
        _listed(page)
        row = _row(page, _DISCOUNT)
        chevron = row.get_by_role("button", name="Expand")
        reel = shots.Reel(f"{_PAGE}-sidebar", window="desktop")
        reel.web(page, hold=1.6, pointer=chevron, click=True)
        chevron.click()
        session = row.locator("[data-hmz=session]").first
        expect(session).to_be_visible()
        expect(row.locator("[data-hmz=agent]")).to_have_count(2)
        page.wait_for_timeout(300)
        reel.web(
            page,
            hold=2.2,
            pointer=session,
            click=True,
            caption="its agents, and each one's sessions",
        )
        session.click()
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        page.wait_for_timeout(400)
        reel.web(page, hold=4, caption="one session, read back", poster=True)
        reel.save()


def test_an_epic_has_a_menu(world: World) -> None:
    _history(world)
    with world.page(desktop=True, height=760) as page:
        _listed(page)
        row = _row(page, _CATALOGUE)
        row.hover()
        more = row.get_by_role("button", name="More options")
        expect(more).to_be_visible()
        # The row and the menu it opens beside it are more than any one locator: a box.
        reel = shots.Reel(f"{_PAGE}-menu")
        reel._at = shots._Box(0, 0, 600, 760)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        reel.web(page, hold=1.6, pointer=more, click=True)
        more.click()
        menu = page.get_by_role("menu")
        expect(menu.get_by_role("menuitem", name="Resume")).to_be_visible()
        expect(menu.get_by_role("menuitem", name="Export")).to_be_visible()
        resume = menu.get_by_role("menuitem", name="Resume")
        resume.hover()
        page.wait_for_timeout(600)
        reel.web(
            page,
            hold=5,
            pointer=resume,
            caption="what can be done with one epic",
            poster=True,
        )
        reel.save()


def test_search_finds_the_epics_that_failed(world: World) -> None:
    _history(world, chat=True)
    with world.page(desktop=True) as page:
        _listed(page)
        page.keyboard.press("Meta+k")
        dialog = page.get_by_role("dialog")
        box = dialog.get_by_role("combobox", name="Search")
        expect(box).to_be_focused()
        expect(dialog.get_by_text(_CENT).first).to_be_visible()
        expect(dialog.get_by_text(_DISCOUNT).first).to_be_visible()
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-search", clip=dialog, pad=20)
        epics = dialog.get_by_role("tab", name="Epics")
        reel.web(
            page,
            hold=2.0,
            keys="cmd+k",
            caption="chats and epics, newest first",
            pointer=epics,
            click=True,
        )
        epics.click()
        expect(dialog.get_by_text(_CENT)).to_have_count(0)
        filters = dialog.get_by_role("button", name="Filters")
        page.wait_for_timeout(300)
        reel.web(page, hold=1.6, pointer=filters, click=True)
        filters.click()
        failed = dialog.get_by_role("group", name="How it went").get_by_role(
            "button", name="Failed"
        )
        expect(failed).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=1.8, pointer=failed, click=True)
        failed.click()
        expect(dialog.get_by_text(_DISCOUNT)).to_have_count(0)
        expect(dialog.get_by_text(_RECEIPT).first).to_be_visible()
        found = dialog.get_by_role("option").filter(has_text=_RECEIPT)
        found.hover()
        expect(dialog.locator("[data-hmz=search-detail]")).to_contain_text("took")
        page.wait_for_timeout(500)
        reel.web(
            page,
            hold=4.5,
            pointer=found,
            caption="the ones that failed, and more of the one pointed at",
            poster=True,
        )
        reel.save()


def test_search_that_finds_nothing_offers_to_clear_the_filters(world: World) -> None:
    _history(world, chat=True)
    with world.page(desktop=True) as page:
        _listed(page)
        page.keyboard.press("Meta+k")
        dialog = page.get_by_role("dialog")
        box = dialog.get_by_role("combobox", name="Search")
        expect(box).to_be_focused()
        expect(dialog.get_by_text(_DISCOUNT).first).to_be_visible()
        dialog.get_by_role("tab", name="Epics").click()
        dialog.get_by_role("button", name="Filters").click()
        dialog.get_by_role("group", name="How it went").get_by_role(
            "button", name="Failed"
        ).click()
        expect(dialog.get_by_text(_RECEIPT).first).to_be_visible()
        box.fill("refund")
        clear = dialog.get_by_role("button", name="Clear filters")
        expect(clear).to_be_visible()
        expect(dialog.get_by_text(_RECEIPT)).to_have_count(0)
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-search-none", clip=dialog, pad=20, pointer=clear)


# -- in the terminal ------------------------------------------------------------------


async def test_epics_lists_what_ran_here(world: World) -> None:
    _history(world)
    async with world.tui((104, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "Add a discount code", "Send a receipt", "failed")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-epics")


async def test_an_epic_is_read_back_down_to_one_session(world: World) -> None:
    _history(world)
    async with world.tui((104, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "Add a discount code")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-read")
        reel.tui(app, hold=2.0, keys="/epics", caption="the epics of this directory")
        await pilot.press("enter")
        await on(pilot, Does)
        await shows(pilot, "its agents, called flows and sessions, read back")
        await _settled(pilot)
        reel.tui(app, hold=2.4, keys="enter", caption="one epic's menu")
        await onto(pilot, "graph")
        await pilot.press("enter")
        await on(pilot, Graph)
        await shows(pilot, "actions", "turn")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=3.0, keys="down enter", caption="its graph, read back")
        await pilot.press("enter")
        await on(pilot, SessionRead)
        await shows(pilot, "read back from its log", "pytest -q")
        await _settled(pilot, 1.0)
        reel.tui(app, hold=4.5, keys="enter", caption="one session, whole", poster=True)
        reel.save()
        shots.tui(app, f"{_PAGE}-session")


@pytest.fixture
def server(world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Another machine, `server`, whose daemon holds two epics of a project of its own."""
    far = world.home.parent / "far"
    far.mkdir()
    found = faked(far, monkeypatch)
    here = os.environ["HUMANIZE_HOME"]
    # Written there as a run there writes it: under that machine's own home.
    monkeypatch.setenv("HUMANIZE_HOME", str(found.humanize))
    project = found.home / "pricing"
    project.mkdir()
    for flow, task in (
        ("rlar", "Fit the price model to last month's orders"),
        ("ralph_loop", "Speed up the nightly price import"),
    ):
        with Epic(flow, task, project):
            pass
        time.sleep(1.1)
    monkeypatch.setenv("HUMANIZE_HOME", here)
    Hmz().daemons.write("server", {"routes": ["stdio:ssh://server.example"]})
    yield
    # The daemon `hmz daemon connect --stdio` started there, which outlives its client.
    pid = where.held(found.tmp / f"humanize-{os.getuid()}").get("pid")
    if isinstance(pid, int):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


@pytest.mark.usefixtures("server")
async def test_another_daemons_epics_are_listed(world: World) -> None:
    async with world.tui((104, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/epics @server")
        await on(pilot, RemoteEpics)
        await shows(pilot, "Epics on server", "Fit the price model")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-remote")
