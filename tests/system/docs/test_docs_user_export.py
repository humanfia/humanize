"""The pictures of `docs/user/export.md`: an epic exported as a `.hmzepic`, and read back in.

One finished epic of the project: exported from its page and from its row's menu in the app,
dropped back on the window of a machine that has not got it, refused where it is already
there, and named by its path at the import address of a browser; then the same two errands
in the terminal interface, from `/epics`. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_export.py`.
"""

from __future__ import annotations

import base64
import re
import shutil
import time
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.pick import Does, Epics, Exporting, ImportingEpic
from tests.integration.doubles_tui import on, onto, shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-export"

#: The epic the page exports, and an earlier one beside it in the history.
_TASK = "Add a discount code to checkout"
_EARLIER = "Show prices with a currency symbol"

#: What the actor does when told the task, and what the reviewer makes of it.
_WORK = {
    "text": (
        "Checkout takes a discount code now: charge() looks the code up and takes its"
        " discount off the total. WELCOME10 is 10% off. All six tests pass."
    ),
    "tools": [
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.8,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "6 passed in 0.21s",
            "takes": 1.1,
        },
    ],
    "after": 0.5,
}
_REVIEW = {
    "json": {"done": True, "notes": "WELCOME10 takes 10% off. All six tests pass."},
    "after": 0.3,
}


def _ran(world: World) -> str:
    """Stages the history: an earlier epic, and the one the page exports, both done."""
    world.says(
        {
            "meticulous reviewer": _REVIEW,
            "currency": "Prices are shown with a currency symbol now: $12.00.",
            "discount": _WORK,
        }
    )
    world.epic("goal", _EARLIER)
    return world.epic("rlar", _TASK)


def _open(page: Page, name: str) -> None:
    """Opens the epic's own page, drawn as an ended epic is."""
    go(page, f"/epics/{name}")
    expect(page.get_by_role("link", name="Resume").first).to_be_visible()
    expect(page.get_by_text("Reading handovers")).to_have_count(0)
    expect(page.locator(".side-scroll").get_by_text("Running")).to_have_count(0)


def _exported(world: World, name: str) -> Path:
    """Exports the epic as the page does, into the person's Downloads, and answers the file."""
    downloads = world.home / "Downloads"
    downloads.mkdir(exist_ok=True)
    with world.page(desktop=True) as page:
        _open(page, name)
        export = page.locator("[data-hmz=bar]").get_by_role("button", name="Export")
        with page.expect_download() as saving:
            export.click()
        archive = downloads / saving.value.suggested_filename
        saving.value.save_as(archive)
    assert archive.name == f"{name}.hmzepic"
    return archive


def _forgotten(world: World, name: str) -> None:
    """Takes the epic away, as on a machine that has the archive and not the epic."""
    (kept,) = (world.home / ".hmz").rglob(name)
    shutil.rmtree(kept)


#: Carries a file over the window and lets it go there, as a person dragging one does.
_DRAG = """([name, data, kinds]) => {
  const bytes = Uint8Array.from(atob(data), (one) => one.charCodeAt(0))
  const carried = new DataTransfer()
  carried.items.add(new File([bytes], name))
  for (const kind of kinds)
    document.body.dispatchEvent(
      new DragEvent(kind, { dataTransfer: carried, bubbles: true, cancelable: true }))
}"""


def _over(world: World, name: str) -> None:
    """Waits until the epic's record says how it ended, and nothing holds it any more.

    The terminal interface reads the record itself: one read the instant the epic ended can
    come before its last line is written, and is then listed as still going.
    """
    from hmz.runtime import epic

    (kept,) = (world.home / ".hmz").rglob(name)
    deadline = time.monotonic() + 60
    while True:
        ran = epic.read(kept)
        if ran is not None and ran.how and not epic.going(kept):
            return
        assert time.monotonic() < deadline, "the epic's record never said it ended"
        time.sleep(0.2)


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


# -- in the app -----------------------------------------------------------------------


def test_an_epic_is_exported_from_its_page_and_its_menu(world: World) -> None:
    name = _ran(world)
    with world.page(desktop=True) as page:
        _open(page, name)
        bar = page.locator("[data-hmz=bar]")
        export = bar.get_by_role("button", name="Export")
        export.hover()
        page.wait_for_timeout(500)
        shots.web(
            page, f"{_PAGE}-app", window="desktop", pointer=export, most=shots.REEL
        )

        # The menu, over a page that draws little: an epic's graph under it is a heavy picture.
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        row = page.locator(".side-scroll").get_by_text(_TASK[:18]).first
        row.click(button="right")
        item = page.get_by_role("menuitem", name="Export")
        expect(item).to_be_visible()
        item.hover()
        shots.web(
            page, f"{_PAGE}-menu", clip=page.get_by_role("menu"), pad=12, pointer=item
        )


def test_an_archive_dropped_on_the_window_is_imported(world: World) -> None:
    name = _ran(world)
    archive = _exported(world, name)
    carried = [archive.name, base64.b64encode(archive.read_bytes()).decode()]
    _forgotten(world, name)
    # In a browser: there the page itself takes the drop, outlines itself and opens the epic.
    # Humanize Desktop takes a drop itself and opens the import address, which no stand-in is.
    with world.page() as page:
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        listed = page.locator(".side-scroll").get_by_text(_TASK[:18])
        expect(listed).to_have_count(0)
        reel = shots.Reel(f"{_PAGE}-drop", window="browser")
        reel.web(page, hold=1.4)
        page.evaluate(_DRAG, [*carried, ["dragenter", "dragover"]])
        expect(page.locator("body.dropping")).to_have_count(1)
        reel.web(
            page,
            hold=2.0,
            pointer=(640, 420),
            caption="a .hmzepic file dragged over the window",
        )
        page.evaluate(_DRAG, [*carried, ["drop"]])
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+$"))
        expect(page.get_by_role("link", name="Resume").first).to_be_visible()
        expect(page.get_by_text("Reading handovers")).to_have_count(0)
        expect(listed.first).to_be_visible()
        reel.web(page, hold=4.5, caption="dropped: the epic is imported", poster=True)
        reel.save()

        # Dropped a second time, it is here already: refused, with a way to it.
        go(page, "/new/chat")
        expect(page.get_by_role("textbox", name="First message")).to_be_visible()
        page.evaluate(_DRAG, [*carried, ["dragenter", "dragover", "drop"]])
        notice = page.locator("[data-hmz=import-notice]")
        expect(notice.get_by_role("link", name="Open")).to_be_visible()
        shots.web(page, f"{_PAGE}-already", clip=notice, pad=24)


def test_a_browser_asks_before_importing_a_file_named_by_its_path(
    world: World,
) -> None:
    name = _ran(world)
    archive = _exported(world, name)
    _forgotten(world, name)
    with world.page() as page:
        go(page, f"/epics/import?path={archive}")
        button = page.get_by_role("button", name="Import")
        expect(button).to_be_visible()
        shots.web(page, f"{_PAGE}-address", window="browser", pointer=button)
        # And pressed, it is what it says: the epic's trace opens.
        button.click()
        page.wait_for_url(re.compile(r".*#/epics/[^/?]+/exomyth$"))


# -- in the terminal ------------------------------------------------------------------


async def test_an_epic_is_exported_and_imported_in_the_terminal(world: World) -> None:
    name = _ran(world)
    (world.home / "Downloads").mkdir()
    _over(world, name)
    async with world.tui(size=(110, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        reel = shots.Reel(f"{_PAGE}-terminal")
        await pilot.press(*"/epics")
        await pilot.pause()
        reel.tui(app, hold=1.0, keys="/epics", cut=True)
        await pilot.press("enter")
        await on(pilot, Epics)
        await shows(pilot, "Every epic in this directory")
        await _settled(pilot)
        reel.tui(app, hold=1.8, keys="enter")
        await pilot.press("enter")
        await on(pilot, Does)
        await shows(pilot, "export epic")
        await onto(pilot, "export")
        await _settled(pilot)
        reel.tui(app, hold=2.2, keys="enter down down", caption="export epic")
        await pilot.press("enter")
        await on(pilot, Exporting)
        await shows(pilot, "~/Downloads/")
        await _settled(pilot)
        reel.tui(app, hold=2.6, keys="enter", caption="where the archive goes")
        for _ in range(3):
            if not isinstance(app.screen, Exporting):
                break
            await pilot.press("enter")
            await _settled(pilot)
        await on(pilot, Epics)
        await shows(pilot, f"{name}.hmzepic")
        await _settled(pilot)
        reel.tui(app, hold=4.5, keys="enter enter", caption="written", poster=True)
        reel.save()

        # Read back in, on a machine that has not got it: `i`, and the file.
        await pilot.press("escape")
        await _settled(pilot)
    _forgotten(world, name)
    async with world.tui(size=(110, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/epics", "enter")
        await on(pilot, Epics)
        await shows(pilot, "Every epic in this directory")
        await pilot.press("i")
        await on(pilot, ImportingEpic)
        await shows(pilot, "Import epic")
        await pilot.press(*f"~/Downloads/{name}.hmzepic")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-import")
        for _ in range(3):
            if not isinstance(app.screen, ImportingEpic):
                break
            await pilot.press("enter")
            await _settled(pilot)
        await on(pilot, Epics)
        await shows(pilot, "imported into")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-imported")
