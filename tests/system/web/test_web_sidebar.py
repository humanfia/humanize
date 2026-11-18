"""The sidebar, laid out as a desktop chat app's, and what it sends off.

Its epics and workspaces are answered on the wire, before Local is asked. Its measures are those
of Claude's desktop app at 1296 by 792: 275 wide with a splitter on its right edge, a title row
of 28px buttons that start 84 in, entries and rows 258 by 32, a row's state straight after its
title, and a foot of one 28px row. The answers to what it sends off are held until the test gives
them: an epic opened out, `Show N more`, `Upload` on an epic and `Forget` on a workspace.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, again, go, opened

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

pytestmark = pytest.mark.parametrize("engine", ENGINES)


def _row(name: str, **more: Any) -> dict[str, Any]:
    """An epic row as `runs.list` answers one: a chat that rests, until `more` says otherwise."""
    return {
        "name": name,
        "workspace": "/w",
        "task": f"Ask {name}",
        "kind": "chat",
        "flow": "",
        "how": "stopped",
        "held": False,
        "began": "2026-10-12T09:00:00Z",
        "ended": "2026-10-12T09:30:00Z",
        "asking": [],
        "agents": [{"name": "assistant", "role": "assistant", "runs": "claude/sonnet"}],
        **more,
    }


_RUN = _row(
    "e1",
    task="Fix e1",
    kind="flow",
    flow="ralph",
    how="done",
    ended="2026-10-12T10:00:00Z",
    agents=[{"name": "coder", "role": "coder", "runs": "claude/sonnet"}],
)

#: An epic of a flow and twenty-one chats in one workspace: two more than a group shows at first.
_MANY = [_RUN, *[_row(f"c{at:02d}") for at in range(21)]]

#: A chat going, one asking, one failed and one at rest, an epic of a flow, and a chat elsewhere.
_MIXED = [
    _row("going", how="running", turn="running", held=True, ended=None),
    _row("asks", how="running", held=True, asking=["1:1"], ended=None),
    _row("failed", how="failed"),
    _row("rests"),
    _RUN,
    _row("far", workspace="/v", began="2026-01-02T09:00:00Z", ended=None),
]


def _answers(runs: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "runs": runs,
        "total": len(runs) if total is None else total,
        "offset": 0,
        "limit": 60,
        "counts": {},
        "flows": [],
    }


def _wire(runs: list[dict[str, Any]], **faked: Any) -> Wire:
    """Local's lists answered here: `runs` its epics, `/w` and `/empty` among its workspaces."""
    return Wire(
        faked={
            "runs.list": lambda _: {"result": _answers(runs)},
            "workspaces.list": lambda _: {
                "result": {"workspaces": [{"path": "/w"}, {"path": "/empty"}]}
            },
            **faked,
        }
    )


def _box(target: Locator) -> tuple[int, int, int, int]:
    """Where something is drawn: its left, top, width and height, in whole pixels."""
    box = target.bounding_box()
    assert box
    return (
        round(box["x"]),
        round(box["y"]),
        round(box["width"]),
        round(box["height"]),
    )


def _named(page: Page, *names: str) -> None:
    """Waits until the headings of the list's groups are these, top to bottom."""
    expect(page.locator("[data-hmz=epics] .side-folder-name")).to_have_text(list(names))


def _group_and_sort(page: Page) -> Locator:
    """Opens `Group and sort` from the first heading, and answers its menu."""
    page.locator("[data-hmz=epics] .side-folder").first.hover()
    page.locator("[data-hmz=list-menu-open]").first.click()
    menu = page.locator("[data-hmz=list-menu]")
    expect(menu).to_be_visible()
    return menu


def test_what_the_sidebar_sends_off_says_it_is_going(engine: str) -> None:
    wire = Wire(
        faked={
            # A page more is held until it is given; the first page, and what the new chat
            # form in front reads for itself, are answered at once.
            "runs.list": lambda params: (
                None if params.get("limit") == 120 else {"result": _answers(_MANY, 23)}
            ),
            "runs.get": lambda _: None,
            "runs.backup": lambda _: None,
            "workspaces.list": lambda _: {
                "result": {"workspaces": [{"path": "/w"}, {"path": "/empty"}]}
            },
            "workspaces.forget": lambda _: None,
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        row = page.locator("[data-hmz=epics] .side-item[data-epic=e1]")
        expect(row).to_have_count(1)

        # Opened out: its agents at once, and that its sessions are being read.
        row.locator(".side-toggle").click()
        reading = row.locator("[data-hmz=reading]")
        expect(reading).to_have_text("Reading…")
        expect(row.locator("[data-hmz=agent]")).to_have_count(1)
        wire.answer(page, "runs.get", {"name": "e1", "sessions": []})
        expect(reading).to_have_count(0)

        working = page.locator("[data-hmz=working]")
        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Upload").click()
        expect(working).to_have_text("Uploading…")
        wire.answer(page, "runs.backup", {"queued": ["s3"]})
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Uploading to s3")

        # Brought into view first: a list that scrolls takes down the menu open over it.
        empty = page.locator("[data-hmz=workspace][data-path='/empty'] .side-folder")
        empty.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        empty.click(button="right")
        page.get_by_role("menuitem", name="Forget").click()
        expect(working).to_have_text("Forgetting…")
        wire.answer(page, "workspaces.forget", {})
        expect(working).to_have_count(0)
        expect(page.locator(".toast")).to_have_text("Forgotten")

        # The group shows its first twenty rows, and brings the rest where asked: those read
        # at once, and a page more of the list, said to be read until it is.
        group = page.locator("[data-hmz=workspace][data-path='/w']")
        rows = group.locator("[data-hmz=epic]")
        more = group.locator(".side-more")
        expect(rows).to_have_count(20)
        expect(more).to_have_text("Show 2 more")
        # Told from another group's, by whoever cannot see which it ends, by its group's name.
        described = more.get_attribute("aria-describedby")
        assert described
        expect(page.locator(f"[id='{described}']")).to_have_text("w")
        more.click()
        expect(rows).to_have_count(22)
        expect(more).to_have_text("Loading…")
        expect(more).to_be_disabled()
        assert wire.params("runs.list")[-1] == {"limit": 120}
        wire.answer(page, "runs.list", _answers(_MANY, 23))
        expect(more).to_have_count(0)
        expect(rows).to_have_count(22)


def test_the_sidebar_is_laid_out_as_a_desktop_chat_apps(engine: str) -> None:
    wire = _wire(_MIXED)
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        side = page.locator("[data-hmz=sidebar]")
        expect(side.locator("[data-hmz=epic]")).to_have_count(6)
        assert _box(side) == (0, 0, 275, 792)
        # The splitter lies across its right edge.
        assert _box(side.locator("[data-hmz=side-split]")) == (269, 0, 12, 792)

        # The title row: the mark, where a desktop app's window keeps its traffic lights, then
        # hiding it, back and forward, side by side from 84 in; the bell last.
        top = side.locator(".side-top")
        expect(top.locator(":scope > *")).to_have_count(5)
        assert _box(top.locator(".brand")) == (8, 8, 76, 28)
        boxes = [
            _box(top.get_by_role("button", name=name, exact=True))
            for name in ("Hide sidebar", "Back", "Forward", "Notifications")
        ]
        assert [box[1:] for box in boxes] == [(8, 28, 28)] * 4
        assert [box[0] for box in boxes] == [84, 112, 140, 238]

        # Hidden and shown again: the button that undoes each has the focus, and the mark,
        # under the pointer that pressed `Show sidebar`, says nothing over the first entry.
        top.get_by_role("button", name="Hide sidebar").click()
        shows = page.get_by_role("button", name="Show sidebar")
        expect(shows).to_be_focused()
        shows.click()
        expect(top.get_by_role("button", name="Hide sidebar")).to_be_focused()
        page.wait_for_timeout(600)
        expect(page.locator(".tip")).to_have_count(0)

        # The entries: 258 by 32, 2px apart, 8px in, all drawn alike but the one the page is on.
        entries = side.locator(".side-nav a")
        assert [_box(one) for one in entries.all()] == [
            (8, 46 + 34 * at, 258, 32) for at in range(4)
        ]
        expect(entries.nth(0)).to_have_attribute("aria-current", "page")
        weights = {
            one.evaluate("(el) => getComputedStyle(el).fontWeight")
            for one in entries.all()
        }
        assert len(weights) == 1

        # A heading 24 tall, a chat's row 258 by 32 under it, rows 2px apart.
        group = side.locator("[data-hmz=workspace][data-path='/w']")
        head = group.locator(".side-folder")
        assert _box(head) == (14, 204, 248, 24)
        chats = group.locator("[data-hmz=epic][data-kind=chat]")
        # The two going first, then, past the flow's epic of two lines, the two that are not.
        assert [_box(one) for one in chats.all()] == [
            (8, top, 258, 32) for top in (234, 268, 355, 389)
        ]
        # What sorts the list and what starts a chat stand at the heading's end once pointed at.
        sort, add = head.locator(".side-sort"), head.locator(".side-add")
        expect(sort).to_have_css("opacity", "0")
        head.hover()
        expect(sort).to_have_css("opacity", "1")
        assert _box(head.locator(".side-toggle")) == (14, 204, 196, 24)
        assert _box(sort) == (214, 204, 24, 24)
        assert _box(add) == (238, 204, 24, 24)
        expect(add).to_have_attribute("aria-label", "New chat in w")

        # A chat says how it stands in quiet words straight after its title, and no more:
        # no glyph, no dot, no flow, nothing that opens it out.
        said = {
            name: group.locator(f".side-item[data-epic={name}] [data-hmz=chat-state]")
            for name in ("going", "asks", "failed", "rests")
        }
        expect(said["going"]).to_have_text("Running")
        expect(said["asks"]).to_have_text("Awaiting input")
        expect(said["asks"]).to_have_css("animation-name", "none")
        expect(said["failed"]).to_have_text("Failed")
        expect(said["rests"]).to_have_count(0)
        chat = group.locator(".side-item[data-epic=going]")
        expect(chat.locator(".side-run > a > *")).to_have_count(2)
        expect(chat.locator("svg, .side-toggle, [data-hmz=epic-flow]")).to_have_count(1)
        expect(chat.locator(".side-run > a svg")).to_have_count(0)
        for name in ("going", "asks", "failed"):
            title = _box(group.locator(f".side-item[data-epic={name}] .side-label"))
            state = _box(said[name])
            assert title[0] == 18
            assert state[0] == title[0] + title[2] + 6

        # Its menu's button, 24 by 24 at its far end, once the row is pointed at or holds
        # the focus.
        more = chat.locator("[data-hmz=row-menu]")
        expect(more).to_have_css("opacity", "0")
        chat.locator("[data-hmz=epic]").focus()
        expect(more).to_have_css("opacity", "1")
        page.locator("body").evaluate("() => document.activeElement.blur()")
        expect(more).to_have_css("opacity", "0")
        chat.hover()
        expect(more).to_have_css("opacity", "1")
        assert _box(more) == (238, 238, 24, 24)

        # A flow's epic keeps what makes it another kind, on a first line as tall as a chat's.
        flow = group.locator(".side-item[data-epic=e1]")
        expect(flow.locator(".side-toggle")).to_have_count(1)
        expect(flow.locator("[data-hmz=epic-flow]")).to_have_text("ralph")
        expect(flow.locator("[data-hmz=epic-state]")).to_have_text("Done")
        assert _box(flow.locator(".side-line").first)[3] == 32
        title = _box(flow.locator(".side-label").first)
        assert _box(flow.locator("[data-hmz=epic-state]"))[0] == title[0] + title[2] + 6
        flow.hover()
        assert _box(flow.locator("[data-hmz=row-menu]"))[0] == 238

        # The foot: one row, the daemon bar and the settings beside it.
        assert _box(side.locator("[data-hmz=daemon-bar]")) == (8, 756, 222, 28)
        gear = side.get_by_role("button", name="Settings", exact=True)
        assert _box(gear) == (236, 756, 28, 28)
        gear.click()
        page.wait_for_url(re.compile(r"#/settings/general$"))
        expect(page.locator("[data-hmz=overlay]")).to_be_visible()
        page.keyboard.press("Escape")
        page.wait_for_url(re.compile(r"#/new/chat\b"))

        # Back and forward step through where the page has been.
        side.locator(".side-nav a[data-nav=flows]").click()
        page.wait_for_url(re.compile(r"#/flows\b"))
        side.locator("[data-hmz=back]").click()
        page.wait_for_url(re.compile(r"#/new/chat\b"))
        side.locator("[data-hmz=forward]").click()
        page.wait_for_url(re.compile(r"#/flows\b"))


def test_the_sidebar_is_sized_by_its_splitter_and_stays_so(engine: str) -> None:
    wire = _wire(_MIXED)
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        side = page.locator("[data-hmz=sidebar]")
        split = side.get_by_role("separator", name="Resize sidebar")
        expect(split).to_have_attribute("aria-valuenow", "275")
        expect(side.locator("[data-hmz=epic]")).to_have_count(6)
        # A press that goes nowhere sizes nothing, wherever on the splitter it lands.
        page.mouse.click(279, 400)
        assert _box(side)[2] == 275
        assert page.evaluate("localStorage.getItem('hmz-side-wide')") is None
        # Dragged, it moves by as far as the pointer went.
        page.mouse.move(279, 400)
        page.mouse.down()
        page.mouse.move(344, 400, steps=4)
        page.mouse.up()
        expect(split).to_have_attribute("aria-valuenow", "340")
        assert _box(side)[2] == 340
        assert _box(page.locator("[data-hmz=page]"))[0] == 340
        # Kept for the next visit.
        again(page)
        assert _box(side)[2] == 340
        # By the keyboard, within its bounds: on a view that takes the focus for nothing of
        # its own, as a new chat does for its box once it is drawn.
        go(page, "#/flows")
        split.focus()
        page.keyboard.press("ArrowLeft")
        assert _box(side)[2] == 324
        page.keyboard.press("Home")
        assert _box(side)[2] == 200
        page.keyboard.press("End")
        assert _box(side)[2] == 480
        # Double-clicked, it is as wide as it usually is, and nothing is kept.
        split.dblclick()
        assert _box(side)[2] == 275
        assert page.evaluate("localStorage.getItem('hmz-side-wide')") is None

    # A phone's drawer has none.
    with (
        served() as site,
        opened(site, engine=engine, width=390, height=800, routed=wire.routes) as page,
    ):
        expect(page.locator("[data-hmz=side-split]")).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollWidth") == 390


def test_the_list_is_grouped_sorted_and_filtered_as_its_menu_says(engine: str) -> None:
    wire = _wire(_MIXED)
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        epics = page.locator("[data-hmz=epics] [data-hmz=epic]")
        expect(epics).to_have_count(6)
        # By folder, the last updated first: what is going, then what ended last.
        _named(page, "w", "v", "empty")
        expect(epics.locator(".side-label:not(.side-tag *)")).to_have_text(
            ["Ask going", "Ask asks", "Fix e1", "Ask failed", "Ask rests", "Ask far"]
        )

        menu = _group_and_sort(page)
        expect(
            menu.locator(":scope > .choice-sub > .choice .choice-label")
        ).to_have_text(["Group by", "Sort by", "Show"])
        expect(
            menu.locator(":scope > .choice-sub > .choice .choice-about")
        ).to_have_text(["Folder", "Last updated"])
        expect(menu.locator(":scope > .choice")).to_have_text("Reset to defaults")
        menu.get_by_role("menuitem", name="Sort by").hover()
        expect(page.get_by_role("menuitemradio")).to_have_text(
            ["Last updated", "Created"]
        )
        expect(
            page.get_by_role("menuitemradio", name="Last updated")
        ).to_have_attribute("aria-checked", "true")
        menu.get_by_role("menuitem", name="Group by").hover()
        expect(page.get_by_role("menuitemradio")).to_have_text(
            ["Folder", "Date", "None"]
        )
        page.get_by_role("menuitemradio", name="None").click()
        expect(menu).to_have_count(0)
        _named(page, "All", "Folders")
        expect(epics).to_have_count(6)
        # What sorts the list has the focus back, though the list was drawn again.
        expect(page.locator("[data-hmz=list-menu-open]").first).to_be_focused()

        menu = _group_and_sort(page)
        menu.get_by_role("menuitem", name="Show").hover()
        epics_shown = page.get_by_role("menuitemcheckbox", name="Epics")
        expect(epics_shown).to_have_attribute("aria-checked", "true")
        epics_shown.click()
        expect(epics).to_have_count(5)
        expect(page.locator("[data-hmz=epic][data-kind=flow]")).to_have_count(0)

        menu = _group_and_sort(page)
        menu.get_by_role("menuitem", name="Group by").hover()
        page.get_by_role("menuitemradio", name="Date").click()
        _named(page, "Today", "Older", "Folders")

        # Kept for the next visit.
        again(page)
        expect(epics).to_have_count(5)
        _named(page, "Today", "Older", "Folders")

        # With nothing left to show, a heading stays, and on it what brings the rows back.
        menu = _group_and_sort(page)
        menu.get_by_role("menuitem", name="Show").hover()
        page.get_by_role("menuitemcheckbox", name="Chats").click()
        expect(epics).to_have_count(0)
        _named(page, "Today", "Folders")
        expect(
            page.locator("[data-hmz=group][data-group=':date:today'] .side-quiet")
        ).to_have_text("Nothing here yet")

        _group_and_sort(page).get_by_role("menuitem", name="Reset to defaults").click()
        expect(epics).to_have_count(6)
        _named(page, "w", "v", "empty")
        assert page.evaluate("localStorage.getItem('hmz-list')") is None

        menu = _group_and_sort(page)
        menu.get_by_role("menuitem", name="Sort by").hover()
        page.get_by_role("menuitemradio", name="Created").click()
        # By when each began: those of `/w` began together and stand as they were listed.
        expect(epics.locator(".side-label:not(.side-tag *)")).to_have_text(
            ["Ask going", "Ask asks", "Ask failed", "Ask rests", "Fix e1", "Ask far"]
        )


def test_a_row_is_pinned_and_marked_unread_from_its_menu(engine: str) -> None:
    wire = _wire(_MIXED)
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        row = page.locator("[data-hmz=epics] .side-item[data-epic=rests]")
        expect(row).to_have_count(1)

        # The button at its end opens the menu a right click opens, in a desktop app's order.
        row.hover()
        row.locator("[data-hmz=row-menu]").click()
        menu = page.locator(".popover.context")
        expect(menu.locator(".choice-label")).to_have_text(
            [
                "Open",
                "Pin",
                "Mark as unread",
                "New chat like it",
                "Copy link",
                "Copy first message",
                "Copy ID",
                "Export",
                "Upload",
            ]
        )
        menu.get_by_role("menuitem", name="Pin").click()
        _named(page, "Pinned", "w", "v", "empty")
        pinned = page.locator("[data-hmz=group][data-group=':pinned']")
        expect(pinned.locator("[data-hmz=epic]")).to_have_text("Ask rests")
        expect(row).to_have_count(1)

        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Mark as unread").click()
        expect(row.locator("[data-hmz=unread]")).to_have_count(1)
        # Folded away, its group carries the mark.
        pinned.locator(".side-toggle").click()
        expect(pinned.locator(".side-folder [data-hmz=unread]")).to_have_count(1)
        pinned.locator(".side-toggle").click()

        # Both are kept for the next visit.
        again(page)
        _named(page, "Pinned", "w", "v", "empty")
        expect(row.locator("[data-hmz=unread]")).to_have_count(1)

        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Mark as read").click()
        expect(row.locator("[data-hmz=unread]")).to_have_count(0)
        row.locator("[data-hmz=epic]").click(button="right")
        page.get_by_role("menuitem", name="Unpin").click()
        _named(page, "w", "v", "empty")
        assert page.evaluate(
            "['hmz-pinned', 'hmz-unread'].map((key) => localStorage.getItem(key))"
        ) == [None, None]


def test_a_list_by_date_with_nothing_in_it_keeps_a_heading(engine: str) -> None:
    wire = Wire(
        faked={
            "runs.list": lambda _: {"result": _answers([])},
            "workspaces.list": lambda _: {"result": {"workspaces": []}},
        }
    )
    kept = "localStorage.setItem('hmz-list', JSON.stringify({ group: 'date' }))"
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=kept) as page,
    ):
        _named(page, "Today")
        expect(page.locator("[data-hmz=epics] .side-quiet")).to_have_text(
            "Nothing here yet"
        )
        _group_and_sort(page).get_by_role("menuitem", name="Reset to defaults").click()
        # By folder, with no folder either, the group of none is the heading kept.
        _named(page, "No folder")
        assert page.evaluate("localStorage.getItem('hmz-list')") is None


def test_a_list_by_folder_with_nothing_to_show_keeps_a_heading(engine: str) -> None:
    # A daemon with no workspace, its one chat of no folder, and Show without the chats.
    wire = Wire(
        faked={
            "runs.list": lambda _: {"result": _answers([_row("lone", workspace="")])},
            "workspaces.list": lambda _: {"result": {"workspaces": []}},
        }
    )
    kept = (
        "localStorage.setItem('hmz-list',"
        " JSON.stringify({ group: 'folder', chats: false }))"
    )
    with (
        served() as site,
        opened(site, engine=engine, routed=wire.routes, init=kept) as page,
    ):
        _named(page, "No folder")
        epics = page.locator("[data-hmz=epics] [data-hmz=epic]")
        expect(epics).to_have_count(0)
        expect(page.locator("[data-hmz=epics] .side-quiet")).to_have_text(
            "Nothing here yet"
        )
        # What brings the chat back is on that heading.
        menu = _group_and_sort(page)
        menu.get_by_role("menuitem", name="Show").hover()
        page.get_by_role("menuitemcheckbox", name="Chats").click()
        expect(epics).to_have_count(1)
        _named(page, "No folder")


def test_the_folders_are_rows_of_their_own_where_the_list_is_not_grouped_by_them(
    engine: str,
) -> None:
    wire = _wire(_MIXED)
    # Answered when the test says, so that what it says meanwhile is seen.
    wire.faked["workspaces.forget"] = lambda _: None
    kept = "localStorage.setItem('hmz-list', JSON.stringify({ group: 'none' }))"
    with (
        served() as site,
        opened(
            site,
            engine=engine,
            width=1296,
            height=792,
            routed=wire.routes,
            init=kept,
        ) as page,
    ):
        _named(page, "All", "Folders")
        folders = page.locator("[data-hmz=group][data-group=':folders']")
        rows = folders.locator("[data-hmz=place]")
        expect(rows).to_have_text(["w", "v", "empty"])
        assert _box(rows.first)[2:] == (258, 32)
        # A row opens a new chat in its folder.
        rows.first.click()
        page.wait_for_url(re.compile(r"#/new/chat\?workspace=%2Fw$"))

        # Its menu is a folder's, bar folding it: by a right click, and by the button at its end.
        empty = folders.locator(".side-item[data-place='/empty']")
        empty.locator("[data-hmz=place]").click(button="right")
        labels = page.locator(".popover.context .choice-label")
        offered = [
            "New chat here",
            "New epic here",
            "Flows here",
            "Search here",
            "Copy path",
            "Settings",
            "Usage",
            "Forget",
        ]
        expect(labels).to_have_text(offered)
        page.keyboard.press("Escape")
        full = folders.locator(".side-item[data-place='/w']")
        full.hover()
        full.locator("[data-hmz=row-menu]").click()
        expect(labels).to_have_text(offered[:-1])
        page.keyboard.press("Escape")
        expect(full.locator("[data-hmz=row-menu]")).to_be_focused()

        empty.hover()
        empty.locator("[data-hmz=row-menu]").click()
        page.get_by_role("menuitem", name="Forget").click()
        expect(page.locator("[data-hmz=working]")).to_have_text("Forgetting…")
        wire.answer(page, "workspaces.forget", {})
        expect(page.locator(".toast")).to_have_text("Forgotten")


def test_more_options_is_a_popup_button_that_keeps_the_focus(engine: str) -> None:
    wire = _wire(_MIXED)
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        row = page.locator("[data-hmz=epics] .side-item[data-epic=rests]")
        more = row.locator("[data-hmz=row-menu]")
        menu = page.locator(".popover.context")
        expect(more).to_have_attribute("aria-haspopup", "menu")
        expect(more).to_have_attribute("aria-expanded", "false")

        # By the keyboard: it opens on its first choice, and Escape gives the button the focus.
        more.focus()
        page.keyboard.press("Enter")
        expect(more).to_have_attribute("aria-expanded", "true")
        expect(menu.get_by_role("menuitem", name="Open")).to_be_focused()
        # As a desktop app's: narrow, each choice one line of 28px.
        width = _box(menu)[2]
        assert 154 <= width <= 260
        assert {_box(one)[3] for one in menu.locator(".choice").all()} == {28}
        # The list is not drawn again under a menu open from it: the button stays the one.
        page.wait_for_timeout(4500)
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        expect(more).to_be_focused()
        expect(more).to_have_attribute("aria-expanded", "false")

        # Pressed again, it shuts the menu it opened.
        more.click()
        expect(menu).to_have_count(1)
        more.click()
        expect(menu).to_have_count(0)

        # A choice made, the focus is on the row's button still, wherever the row went.
        more.click()
        menu.get_by_role("menuitem", name="Pin").click()
        pinned = page.locator("[data-hmz=group][data-group=':pinned']")
        expect(pinned.locator("[data-hmz=row-menu]")).to_be_focused()

        # What the keyboard left in the list holds the focus as the list is read again.
        link = pinned.locator("[data-hmz=epic]")
        link.focus()
        page.wait_for_timeout(4500)
        expect(link).to_be_focused()


def test_the_list_reads_no_more_than_it_is_asked_to(engine: str) -> None:
    # Four hundred chats, ten to a folder: no folder holds any back.
    many = [_row(f"r{at:03d}", workspace=f"/f{at % 40:02d}") for at in range(400)]
    wire = Wire(
        faked={
            "runs.list": lambda params: {
                "result": _answers(many[: params["limit"]], len(many))
            },
            "workspaces.list": lambda _: {"result": {"workspaces": []}},
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        rows = page.locator("[data-hmz=epics] [data-hmz=epic]")
        expect(rows).to_have_count(60)
        expect(page.locator("[data-hmz=group-more]")).to_have_count(0)
        # Read again and again as it is, it asks for the one page; the new chat form in front
        # reads the chats that wait for itself, two hundred at once.
        page.wait_for_timeout(5000)
        assert {one["limit"] for one in wire.params("runs.list")} - {200} == {60}
        expect(rows).to_have_count(60)

        # The list ends with what reads a page more.
        more = page.locator("[data-hmz=list-more]")
        expect(more).to_have_text("Show more")
        more.click()
        expect(rows).to_have_count(120)
        assert {one["limit"] for one in wire.params("runs.list")} - {200} == {60, 120}
        expect(more).to_have_text("Show more")


def test_a_group_shown_in_full_holds_nothing_back_later(engine: str) -> None:
    listed = {"runs": [_row(f"c{at:02d}") for at in range(23)]}
    wire = Wire(
        faked={
            "runs.list": lambda _: {"result": _answers(listed["runs"])},
            "workspaces.list": lambda _: {"result": {"workspaces": []}},
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        group = page.locator("[data-hmz=workspace][data-path='/w']")
        rows = group.locator("[data-hmz=epic]")
        more = group.locator("[data-hmz=group-more]")
        expect(more).to_have_text("Show 3 more")
        more.click()
        expect(rows).to_have_count(23)
        # A chat started since stands first, and pushes none of the others back out.
        listed["runs"] = [_row("newer", ended="2026-10-13T09:30:00Z"), *listed["runs"]]
        expect(rows).to_have_count(24)
        expect(more).to_have_count(0)


def test_on_a_touch_screen_a_chat_says_when_it_began(engine: str) -> None:
    wire = _wire(_MIXED)
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        row = page.locator("[data-hmz=epics] .side-item[data-epic=asks]")
        expect(row).to_have_count(1)
        # Where the row can be pointed at, it says so there, and draws nothing of it.
        expect(row.locator("[data-hmz=chat-began]")).to_have_count(0)

    with (
        served() as site,
        opened(
            site,
            engine=engine,
            width=1296,
            height=792,
            touch=True,
            routed=wire.routes,
        ) as page,
    ):
        row = page.locator("[data-hmz=epics] .side-item[data-epic=asks]")
        began = row.locator("[data-hmz=chat-began]")
        more = row.locator("[data-hmz=row-menu]")
        # Drawn at the row's end, before its menu's button, which is always there too.
        expect(began).to_have_text(re.compile(r"\S"))
        expect(more).to_have_css("opacity", "1")
        when, state = _box(began), _box(row.locator("[data-hmz=chat-state]"))
        assert state[0] + state[2] <= when[0]
        assert when[0] + when[2] <= _box(more)[0]


def test_the_drawer_on_a_phone_holds_the_focus_and_closes_by_escape(
    engine: str,
) -> None:
    wire = _wire(_MIXED)
    with (
        served() as site,
        opened(site, engine=engine, width=390, height=800, routed=wire.routes) as page,
    ):
        app = page.locator("[data-hmz=app]")
        side = page.locator("[data-hmz=sidebar]")
        shows = page.get_by_role("button", name="Show sidebar")
        expect(page.locator("[data-hmz=composer-text]")).to_be_visible()
        shows.click()
        expect(app).to_have_class(re.compile("side-open"))
        # The focus is in the drawer, and Tab never reaches the page it covers.
        expect(side.get_by_role("button", name="Hide sidebar")).to_be_focused()
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate(
                "() => !document.activeElement.closest('[data-hmz=page]')"
            )
        # Escape closes it, and the button that opens it has the focus back.
        page.keyboard.press("Escape")
        expect(app).not_to_have_class(re.compile("side-open"))
        expect(page.locator("[data-hmz=scrim]")).to_be_hidden()
        expect(shows).to_be_focused()
        # The page under it is typed into again.
        page.locator("[data-hmz=composer-text]").click()
        page.keyboard.type("hello")
        expect(page.locator("[data-hmz=composer-text]")).to_have_value("hello")
