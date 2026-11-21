"""The pictures of `docs/user/manage-chats.md`: chats renamed, pinned, archived and found.

A chat's menu in the app and a chat renamed from it; the list with a chat pinned and one marked
unread; `Group and sort`; a folder's menu; the dialog that deletes a chat; the archived chats
of a folder; Search; `/resume` in the terminal interface with a chat's menu, and the archived
chats there; and `hmz chat --list` and `--rename` from a command line. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_manage_chats.py`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.chats import Archived, Resumes
from tests.integration.doubles_tui import on, opens, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-manage-chats"

#: The chats had in the project, oldest first, each by what was first said in it.
_DISCOUNT = "Add a discount code to checkout"
_CENT = "Why is the cart total off by a cent?"
_TESTS = "Write tests for the catalogue"
_POSTER = "Add a poster in A2 to the catalogue"

#: What the first of them is renamed to.
_TITLE = "Discount codes"

_SAYS = {
    "discount": "Checkout takes a discount code now: WELCOME10 is 10% off.",
    "cent": "total() rounded each line before adding them up. It adds first now.",
    "tests": "Three tests cover the catalogue's prices, and all of them pass.",
    "poster": "The catalogue lists poster-a2 at 1400.",
}


def _staged(world: World, *said: str) -> list[str]:
    """Holds the chats, oldest first, and answers their ids in that order."""
    world.says(_SAYS)
    return [world.chat(one) for one in said or (_DISCOUNT, _CENT, _TESTS, _POSTER)]


def _row(page: Page, title: str) -> Locator:
    """A chat's row in the sidebar, by its title."""
    return page.locator("[data-hmz=sidebar] .side-item").filter(has_text=title).first


def _menu(page: Page, title: str) -> Locator:
    """Opens the menu of a chat's row by its `More options`, and answers the menu."""
    row = _row(page, title)
    row.hover()
    row.get_by_role("button", name="More options").click()
    menu = page.get_by_role("menu")
    expect(menu.get_by_role("menuitem", name="Archive")).to_be_visible()
    return menu


def _cropped(name: str, box: tuple[int, int, int, int]) -> shots.Reel:
    """A reel of one part of the page that no one thing on it names: a box in CSS pixels.

    A list's row and the menu it opens beside it are more than any one locator, which is all
    `clip=` takes.
    """
    reel = shots.Reel(name)
    reel._at = shots._Box(*box)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    return reel


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_a_chat_is_renamed_from_its_menu(world: World) -> None:
    # The chat renamed is the newest, so that its menu has the room to open under its row.
    chats = _staged(world, _CENT, _TESTS, _POSTER, _DISCOUNT)
    with world.page(desktop=True, height=700) as page:
        go(page, f"/chats/{chats[2]}")
        expect(page.get_by_role("log")).to_contain_text("poster-a2")
        row = _row(page, _DISCOUNT)
        row.hover()
        more = row.get_by_role("button", name="More options")
        expect(more).to_be_visible()

        reel = _cropped(f"{_PAGE}-rename", (0, 0, 620, 700))
        reel.web(page, hold=1.4, pointer=more, click=True)
        more.click()
        menu = page.get_by_role("menu")
        rename = menu.get_by_role("menuitem", name="Rename")
        expect(rename).to_be_visible()
        page.wait_for_timeout(300)
        # The menu alone, with the row it was opened on.
        shots.web(page, f"{_PAGE}-menu", clip=menu, pad=28)
        reel.web(page, hold=2.4, pointer=rename, click=True)
        rename.click()
        field = page.locator("[data-hmz=sidebar] [data-hmz=title-edit]")
        expect(field).to_be_focused()
        reel.web(page, hold=1.2, caption="the title becomes a field")
        field.fill(_TITLE)
        reel.web(page, hold=1.4, caption="type the new title", cut=True)
        field.press("Enter")
        expect(field).to_have_count(0)
        expect(_row(page, _TITLE)).to_be_visible()
        page.mouse.move(700, 500)
        page.locator("body").click(position={"x": 900, "y": 300})
        page.wait_for_timeout(400)
        reel.web(page, hold=3.5, keys="enter", poster=True)
        reel.save()


def test_a_chat_is_pinned_and_another_marked_unread(world: World) -> None:
    chats = _staged(world)
    with world.page(desktop=True, height=560) as page:
        go(page, f"/chats/{chats[-1]}")
        expect(page.get_by_role("log")).to_contain_text("poster-a2")
        _menu(page, _DISCOUNT).get_by_role("menuitem", name="Pin").click()
        sidebar = page.locator("[data-hmz=sidebar]")
        expect(sidebar.get_by_text("Pinned", exact=True)).to_be_visible()
        _menu(page, _CENT).get_by_role("menuitem", name="Mark as unread").click()
        expect(_row(page, _CENT).locator("[data-hmz=unread]")).to_be_visible()
        page.mouse.move(700, 500)
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-pinned", clip=sidebar, pad=0)


def test_the_list_is_arranged_by_group_and_sort(world: World) -> None:
    _staged(world)
    with world.page(desktop=True, height=560) as page:
        go(page, "/new/chat")
        sidebar = page.locator("[data-hmz=sidebar]")
        heading = sidebar.get_by_text("shop", exact=True).first
        heading.hover()
        sort = sidebar.get_by_role("button", name="Group and sort").first
        expect(sort).to_be_visible()
        reel = _cropped(f"{_PAGE}-group-sort", (0, 0, 620, 560))
        reel.web(page, hold=1.4, pointer=sort, click=True)
        sort.click()
        by = page.get_by_role("menuitem", name=re.compile("Group by"))
        expect(by).to_be_visible()
        by.click()
        date = page.get_by_role("menuitemradio", name="Date")
        expect(date).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=2.4, pointer=date, click=True)
        date.click()
        expect(sidebar.get_by_text("Today", exact=True)).to_be_visible()
        page.keyboard.press("Escape")
        page.mouse.move(700, 500)
        page.wait_for_timeout(300)
        reel.web(page, hold=3.5, caption="by date, the folders last", poster=True)
        reel.save()


def test_a_folder_has_a_menu_of_its_own(world: World) -> None:
    _staged(world, _DISCOUNT, _CENT)
    with world.page(desktop=True, height=560) as page:
        go(page, "/new/chat")
        sidebar = page.locator("[data-hmz=sidebar]")
        sidebar.get_by_text("shop", exact=True).first.click(button="right")
        expect(page.get_by_role("menuitem", name="Search here")).to_be_visible()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-folder-menu", clip=page.get_by_role("menu"), pad=48)


def test_deleting_a_chat_is_asked_first(world: World) -> None:
    chats = _staged(world, _DISCOUNT, _CENT)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chats[0]}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        _menu(page, _CENT).get_by_role("menuitem", name="Delete").click()
        dialog = page.get_by_role("dialog", name="Delete chat")
        expect(dialog.locator("[data-hmz=delete-title]")).to_have_text(_CENT)
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-delete", clip=dialog, pad=24)


def test_archived_chats_are_kept_in_the_folders_settings(world: World) -> None:
    chats = _staged(world)
    world.call("chat.archive", chat=chats[1])
    world.call("chat.archive", chat=chats[2])
    with world.page(desktop=True) as page:
        go(page, "/settings/archived")
        listed = page.locator("[data-hmz=archived-chat]")
        expect(listed).to_have_count(2)
        expect(listed.first.get_by_role("button", name="Unarchive")).to_be_visible()
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-archived", clip=page.get_by_role("dialog"), pad=16)


def test_search_finds_a_chat_by_its_words(world: World) -> None:
    chats = _staged(world)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chats[-1]}")
        expect(page.get_by_role("log")).to_contain_text("poster-a2")
        page.keyboard.press("Meta+k")
        dialog = page.get_by_role("dialog")
        box = dialog.get_by_role("combobox", name="Search")
        expect(box).to_be_focused()
        expect(dialog.get_by_text(_CENT).first).to_be_visible()
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-search", clip=dialog, pad=20)
        reel.web(page, hold=2.2, keys="cmd+k", caption="everything, newest first")
        reel.type(page, box, "catalogue", per=5)
        expect(dialog.get_by_text(_DISCOUNT)).to_have_count(0)
        expect(dialog.get_by_text(_TESTS).first).to_be_visible()
        page.wait_for_timeout(400)
        reel.web(page, hold=4, caption="what says catalogue", poster=True)
        reel.save()


async def test_resume_lists_the_chats_and_each_has_a_menu(world: World) -> None:
    _staged(world)
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-resume")
        reel.tui(app, hold=1.0)
        await pilot.press(*"/resume")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.0, keys="/resume", cut=True)
        await pilot.press("enter")
        await on(pilot, Resumes)
        await shows(pilot, _DISCOUNT, _POSTER)
        await _settled(pilot)
        reel.tui(app, hold=2.4, keys="enter", caption="the chats of this directory")
        await pilot.press("down")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.0, keys="down", cut=True)
        await pilot.press("m")
        await shows(pilot, "rename", "fork", "archive", "delete", "copy id")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="m", caption="one chat's menu", poster=True)
        await pilot.press("down", "down")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.0, keys="down down", cut=True)
        await pilot.press("enter")
        await shows(pilot, "/settings workspace puts it back")
        await _settled(pilot)
        reel.tui(app, hold=3.0, keys="enter", caption="archived, and out of the list")
        reel.save()


async def test_archived_chats_are_put_back_from_the_workspace_page(
    world: World,
) -> None:
    chats = _staged(world, _DISCOUNT, _CENT, _TESTS)
    world.call("chat.archive", chat=chats[0])
    world.call("chat.archive", chat=chats[1])
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await typed(pilot, "/settings workspace")
        await shows(pilot, "Archived chats")
        await opens(pilot, "archived")
        await on(pilot, Archived)
        await shows(pilot, _DISCOUNT, _CENT)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-archived-terminal")


def test_chats_are_listed_and_renamed_from_a_command_line(world: World) -> None:
    chats = _staged(world, _DISCOUNT, _CENT, _TESTS)
    shots.cli(["hmz", "chat", "--list"], f"{_PAGE}-cli-list", columns=76)
    reel = shots.Reel(f"{_PAGE}-cli-rename")
    reel.cli(
        ["hmz", "chat", "--rename", chats[0], _TITLE], columns=76, rows=5, hold=3.5
    )
    reel.save()
