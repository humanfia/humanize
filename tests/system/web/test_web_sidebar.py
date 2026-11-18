"""The sidebar, laid out as a desktop chat app's, and what it sends off.

Its epics and workspaces are answered on the wire, before Local is asked. Its measures are those
of Claude's desktop app at 1296 by 792: 275 wide with a splitter on its right edge, a title row
of 28px buttons, entries and rows 258 by 32, and a foot of one 28px row. The answers to what it
sends off are held until the test gives them: an epic opened out, `Show N more`, `Upload` on an
epic and `Forget` on a workspace.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, again, opened

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
            # The first page is answered at once; a page more is held until it is given.
            "runs.list": lambda params: (
                {"result": _answers(_MANY, 23)} if params.get("limit") == 60 else None
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

        # The title row: the mark, then hiding it, back and forward, side by side; the bell last.
        top = side.locator(".side-top")
        expect(top.locator(":scope > *")).to_have_count(5)
        assert _box(top.locator(".brand"))[:2] == (8, 8)
        boxes = [
            _box(top.get_by_role("button", name=name, exact=True))
            for name in ("Hide sidebar", "Back", "Forward", "Notifications")
        ]
        assert [box[1:] for box in boxes] == [(8, 28, 28)] * 4
        hide, back, forward, bell = (box[0] for box in boxes)
        assert (back, forward) == (hide + 28, hide + 56)
        assert bell == 238

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

        # A chat says how it stands in quiet words at the right of its line, and no more:
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
        state = _box(said["going"])
        assert state[0] + state[2] == 234

        # Its menu's button, 24 by 24 at its far end, once the row is pointed at.
        more = chat.locator("[data-hmz=row-menu]")
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
        page.mouse.move(275, 400)
        page.mouse.down()
        page.mouse.move(340, 400, steps=4)
        page.mouse.up()
        assert _box(side)[2] == 340
        assert _box(page.locator("[data-hmz=page]"))[0] == 340
        # Kept for the next visit.
        again(page)
        assert _box(side)[2] == 340
        # By the keyboard, within its bounds.
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
        _named(page, "All")
        expect(epics).to_have_count(6)

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
        _named(page, "Today", "Older")

        # Kept for the next visit.
        again(page)
        expect(epics).to_have_count(5)
        _named(page, "Today", "Older")

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
