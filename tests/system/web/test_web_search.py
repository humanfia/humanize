"""Search, laid out and driven as Claude's window lays out and drives its own.

The epics are answered on the wire, before Local is asked: forty chats and twenty epics of a
flow, more than a page of them, found by kind, by flow and by a word as the daemon finds them.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, go, opened

pytestmark = pytest.mark.parametrize("engine", ENGINES)


def _run(number: int) -> dict[str, Any]:
    chat = number % 3 != 0
    return {
        "name": f"e{number}",
        "workspace": "/w/project",
        "task": f"{'Talk about' if chat else 'Build'} thing {number}",
        "kind": "chat" if chat else "flow",
        "flow": "" if chat else "ralph",
        "how": "done",
        "held": False,
        # Each a minute older than the one before it, as the daemon lists them newest first.
        "began": f"2026-10-12T09:{60 - number:02d}:00Z",
        "ended": f"2026-10-12T10:{60 - number:02d}:00Z",
        "agents": [{"name": "coder", "role": "coder", "runs": "claude/sonnet"}],
        "spent": {"money": "$0.12", "tokens": 1234},
        "sessions": 2,
        "resumable": False,
    }


_RUNS = [_run(number) for number in range(1, 61)]


def _chat(row: dict[str, Any], running: bool = False) -> dict[str, Any]:
    """A chat's row as `chat.list` answers it."""
    held = row["held"]
    return {
        "id": row["name"],
        "title": row["task"],
        "workspace": row["workspace"],
        "workdir": row["workspace"],
        "agent": row["agents"][0]["runs"],
        "model": "sonnet",
        "began": row["began"],
        "updated": row["ended"],
        "state": "failed"
        if row["how"] == "failed"
        else "turn"
        if running
        else "going"
        if held
        else "resting",
        "slot": f"chat:{row['name']}" if held else "",
        "asking": [],
        "permission": "workspace-write",
        "archived": False,
        "spent": row["spent"],
    }


def _listed(params: Any) -> dict[str, Any] | None:
    """A page of Search's epics, as the daemon finds it; the sidebar's list is left to Local.

    Search asks for a page of fifty, or, on everything, of each list as far as the page shown.
    """
    params = params or {}
    if params.get("limit") not in (50, 100):
        return None
    kind = [one for one in _RUNS if one["kind"] == "flow"]
    found = [
        one
        for one in kind
        if params.get("flow", one["flow"]) == one["flow"]
        and params.get("status", one["how"]) == one["how"]
        and params.get("q", "").lower() in one["task"].lower()
    ]
    offset = params.get("offset", 0)
    return {
        "result": {
            "runs": found[offset : offset + params["limit"]],
            "total": len(found),
            "offset": offset,
            "limit": params["limit"],
            "counts": {"done": len(kind)},
            "flows": ["chat", "ralph"],
        }
    }


def _chats(params: Any) -> dict[str, Any] | None:
    """A page of Search's chats, as the daemon finds it by `chat.list`."""
    params = params or {}
    if params.get("limit") not in (50, 100):
        return None
    found = [
        _chat(one)
        for one in _RUNS
        if one["kind"] == "chat" and params.get("q", "").lower() in one["task"].lower()
    ]
    offset = params.get("offset", 0)
    return {
        "result": {
            "chats": found[offset : offset + params["limit"]],
            "total": len(found),
            "offset": offset,
            "limit": params["limit"],
        }
    }


def _faked() -> dict[str, Any]:
    """The chats and the epics of the daemon, each by its own list."""
    return {"runs.list": _listed, "chat.list": _chats}


def _box(page: Page, selector: str) -> tuple[int, int, int, int]:
    """Where the first element a selector finds is drawn, in whole pixels: x, y, width, height."""
    box = page.locator(selector).first.bounding_box()
    assert box is not None
    return (
        round(box["x"]),
        round(box["y"]),
        round(box["width"]),
        round(box["height"]),
    )


def _search(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(page.locator("[data-hmz=found] [data-hmz=epic]")).to_have_count(50)


def test_search_is_laid_out_as_claudes_window_lays_out_its_own(engine: str) -> None:
    wire = Wire(faked=_faked())
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        _search(page)
        # The box: 672 by 584, in the middle of the window: 104 down one 792 tall.
        left, top, wide, tall = _box(page, "[data-hmz=dialog-search]")
        assert (left, wide, tall) == (312, 672, 584)
        assert abs(top - 104) <= 1
        # Flat: a hairline around it, and no shadow under it or under anything in it.
        assert page.evaluate(
            """() => {
              const box = document.querySelector('[data-hmz=dialog-search]')
              return [box, ...box.querySelectorAll('*')].every(
                (one) => getComputedStyle(one).boxShadow === 'none')
            }"""
        )
        assert (
            page.locator("[data-hmz=dialog-search]").evaluate(
                "(box) => getComputedStyle(box).borderTopWidth"
            )
            == "1px"
        )

        def within(selector: str) -> tuple[int, int, int, int]:
            x, y, w, h = _box(page, selector)
            return (x - left, y - top, w, h)

        # The field across its top, and `Close` at its right.
        assert within("[data-hmz=dialog-search] .dialog-search") == (25, 17, 594, 32)
        assert within("[data-hmz=dialog-search] .dialog-head .icon-btn") == (
            627,
            19,
            28,
            28,
        )
        # Under it the tabs, 29 tall, the first one's word on the field's left edge.
        tabs = page.locator("[data-hmz=search-tabs] [role=tab]")
        expect(tabs).to_have_text(["All", "Chats", "Epics"])
        expect(tabs.first).to_have_attribute("aria-selected", "true")
        assert within("[data-hmz=search-tabs] [role=tab]")[:2] == (17, 57)
        assert (
            tabs.first.evaluate(
                "(one) => parseFloat(getComputedStyle(one).paddingLeft)"
            )
            == 8
        )
        assert set(
            tabs.evaluate_all(
                "(all) => all.map((one) => one.getBoundingClientRect().height)"
            )
        ) == {29}
        # Then what was found: a quiet heading, and a line apiece, 32 tall and 34 apart.
        expect(page.locator("[data-hmz=found] .search-heading").first).to_contain_text(
            "Recents"
        )
        expect(page.locator("[data-hmz=search-count]")).to_have_text(
            "1\N{EN DASH}50 of 60"
        )
        rows = page.locator("[data-hmz=found] [data-hmz=epic]")
        first, second = rows.nth(0).bounding_box(), rows.nth(1).bounding_box()
        assert first is not None
        assert second is not None
        assert (round(first["x"]) - left, round(first["y"]) - top) == (9, 131)
        assert (round(first["height"]), round(second["y"] - first["y"])) == (32, 34)
        # And a foot that says what the keys do, from the field's left edge, in the middle of
        # its 40.
        hints = page.locator("[data-hmz=search-hints] .search-hint")
        expect(hints).to_have_text(
            [
                re.compile("^Close"),
                re.compile("^Change type"),
                re.compile("^Filters"),
                re.compile("^Actions"),
                re.compile("^Move"),
                re.compile("^Open"),
            ]
        )
        foot = within("[data-hmz=dialog-search] .search-foot")
        assert (foot[1], foot[3]) == (543, 40)
        x, y, _, h = within("[data-hmz=search-hints] .search-hint")
        assert x == 25
        assert abs(y + h / 2 - 563) <= 1
        # Nothing is said between what was found and the foot of a line that no key and no
        # pointer has moved to; the room of what will be, 32 tall, is kept, so that nothing
        # moves as the first is.
        expect(page.locator("[data-hmz=search-detail]")).to_be_hidden()
        _, y, _, h = within("[data-hmz=found]")
        assert y + h + 32 == foot[1]
        # A key the pages at the foot's right leave no room for is left unsaid, not cut.
        assert page.evaluate(
            """() => {
              const hints = document.querySelector('[data-hmz=search-hints]')
                .getBoundingClientRect()
              return [...document.querySelectorAll('.search-hint')].every((one) => {
                const box = one.getBoundingClientRect()
                return box.top >= hints.bottom || box.right <= hints.right + 1
              })
            }"""
        )
        assert within("[data-hmz=search-hints] .search-hint:nth-child(4)")[1] == (
            foot[1] + 11
        )
        # Nothing of it is wider than the box, or under its foot.
        assert page.evaluate(
            """() => {
              const box = document.querySelector('[data-hmz=dialog-search]')
              return box.scrollWidth <= box.clientWidth && box.scrollHeight <= box.clientHeight
            }"""
        )


def test_search_is_moved_through_and_opened_by_the_keys(engine: str) -> None:
    wire = Wire(faked=_faked())
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _search(page)
        field = page.get_by_role("combobox", name="Search")
        expect(field).to_be_focused()
        expect(field).to_have_attribute("placeholder", "Search")
        active = page.locator("[data-hmz=found] .active")
        expect(active).to_have_attribute("data-key", "e1")
        # The list the field names holds only what can be moved to, in its groups.
        assert page.evaluate(
            """() => {
              const field = document.querySelector('.dialog-search')
              const list = document.getElementById(field.getAttribute('aria-controls'))
              return list.getAttribute('role') === 'listbox'
                && [...list.children].every((one) => one.getAttribute('role') === 'group')
                && list.querySelectorAll('[role=option]').length === 52
            }"""
        )
        expect(page.locator("[data-hmz=search-detail]")).to_be_hidden()
        # Down and up move along what was found, the focus staying in the field.
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e3")
        page.keyboard.press("ArrowUp")
        expect(active).to_have_attribute("data-key", "e2")
        expect(field).to_be_focused()
        assert field.get_attribute("aria-activedescendant") == active.get_attribute(
            "id"
        )
        # What else there is to say of the one moved to is said over the foot.
        expect(page.locator("[data-hmz=search-detail]")).to_contain_text("$0.12")
        # Up from the first goes round to the last: what can be done, under what was found.
        page.keyboard.press("ArrowUp")
        page.keyboard.press("ArrowUp")
        expect(active).to_have_attribute("data-hmz", "import")
        expect(active).to_be_in_viewport()
        page.keyboard.press("ArrowUp")
        expect(active).to_have_text("New chat")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e1")

        # Right and left change the tab while the field is empty: the chats, then the epics.
        page.keyboard.press("ArrowRight")
        chosen = page.locator("[data-hmz=search-tabs] [aria-selected=true]")
        expect(chosen).to_have_text("Chats")
        found = page.locator("[data-hmz=found] [data-hmz=epic]")
        expect(found).to_have_count(40)
        assert {one.get_attribute("data-kind") for one in found.all()} == {"chat"}
        page.keyboard.press("ArrowRight")
        expect(chosen).to_have_text("Epics")
        expect(found).to_have_count(20)
        assert {one.get_attribute("data-kind") for one in found.all()} == {"flow"}
        page.keyboard.press("ArrowRight")
        expect(chosen).to_have_text("Epics")
        # The epics are asked of `runs.list`, which is asked for no kind.
        assert "kind" not in wire.params("runs.list")[-1]

        # A slash opens the filters, and closes them, while the field is empty.
        filters = page.locator("[data-hmz=search-filters]")
        expect(filters).to_be_hidden()
        page.keyboard.press("/")
        expect(filters).to_be_visible()
        expect(field).to_have_value("")
        page.keyboard.press("/")
        expect(filters).to_be_hidden()

        # Typed into, the field keeps its keys to itself; Enter opens the one moved to.
        field.fill("thing 9")
        expect(found).to_have_count(1)
        page.keyboard.press("/")
        expect(field).to_have_value("thing 9/")
        expect(filters).to_be_hidden()
        page.keyboard.press("ArrowLeft")
        expect(chosen).to_have_text("Epics")
        field.fill("thing 9")
        expect(active).to_have_attribute("data-key", "e9")
        wire.faked["runs.get"] = lambda _: None
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r".*#/epics/e9$"))
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()


def test_searchs_filters_stay_in_reach_under_its_tabs(engine: str) -> None:
    wire = Wire(faked=_faked())
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _search(page)
        chosen = page.locator("[data-hmz=search-tabs] [aria-selected=true]")
        found = page.locator("[data-hmz=found] [data-hmz=epic]")
        filters = page.locator("[data-hmz=search-filters]")
        opener = page.locator("[data-hmz=search-filtering]")
        expect(filters).to_be_hidden()
        opener.click()
        expect(opener).to_have_attribute("aria-expanded", "true")
        expect(filters.get_by_role("group", name="How it went")).to_be_visible()
        expect(page.locator("[data-hmz=search-workspace]")).to_be_visible()
        # The flows offered are every flow the daemon names, one named `chat` as any other;
        # a chat is of no flow, and the chats offer none to filter by.
        flows = page.locator("[data-hmz=search-flow]")
        expect(flows.locator("option")).to_have_text(["All flows", "chat", "ralph"])
        page.get_by_role("tab", name="Chats").click()
        expect(found).to_have_count(40)
        expect(flows).to_be_hidden()
        expect(page.locator("[data-hmz=search-workspace]")).to_be_visible()
        page.get_by_role("tab", name="Epics").click()
        expect(flows).to_be_visible()
        flows.select_option("ralph")
        expect(chosen).to_have_text("Epics")
        expect(found).to_have_count(20)
        assert re.search(r"kind=flow.*flow=ralph", page.url)
        # And the chats drop the flow again.
        page.get_by_role("tab", name="Chats").click()
        expect(flows).to_have_value("")
        expect(found).to_have_count(40)

        # A page of fifty, and the one after it, from the foot.
        page.get_by_role("tab", name="All").click()
        expect(page.locator("[data-hmz=search-count]")).to_have_text(
            "1\N{EN DASH}50 of 60"
        )
        page.get_by_role("button", name="Older", exact=True).click()
        expect(page.locator("[data-hmz=search-count]")).to_have_text(
            "51\N{EN DASH}60 of 60"
        )
        expect(found).to_have_count(10)

        # Opened again on an address that names a filter, the filters are open.
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()
        page.evaluate("location.hash = '/search?kind=flow&status=done'")
        expect(chosen).to_have_text("Epics")
        expect(filters).to_be_visible()
        expect(found).to_have_count(20)
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()
        # A chat is not found by how it went: the filter by it is not offered on the chats.
        page.evaluate("location.hash = '/search?kind=chat&status=done'")
        expect(chosen).to_have_text("Chats")
        expect(filters).to_be_hidden()
        expect(found).to_have_count(40)
        # A flow named `chat` is a flow as any other: offered among the flows, and what an
        # address that names it filters the epics by.
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=overlay]")).to_be_hidden()
        page.evaluate("location.hash = '/search?flow=chat'")
        expect(chosen).to_have_text("All")
        expect(filters).to_be_visible()
        expect(flows).to_have_value("chat")
        expect(found).to_have_count(0)
        assert wire.params("runs.list")[-1]["flow"] == "chat"

        # What can be done stands under what was found, whatever was.
        expect(page.locator("[data-hmz=search-new-chat]")).to_have_text("New chat")
        expect(page.locator("[data-hmz=import]")).to_have_text("Import")


def test_search_fills_a_narrow_window_and_scrolls_inside_it(engine: str) -> None:
    wire = Wire(faked=_faked())
    with (
        served() as site,
        opened(site, engine=engine, width=390, height=800, routed=wire.routes) as page,
    ):
        page.evaluate("location.hash = '/search'")
        expect(page.locator("[data-hmz=found] [data-hmz=epic]")).to_have_count(50)
        assert _box(page, "[data-hmz=dialog-search]") == (0, 0, 390, 800)
        expect(page.locator("[data-hmz=search-tabs] [role=tab]")).to_have_count(3)
        # What was found scrolls inside the box, which is no taller than the window.
        assert page.evaluate(
            """() => {
              const found = document.querySelector('[data-hmz=found]')
              return found.scrollHeight > found.clientHeight
                && document.documentElement.scrollWidth <= innerWidth
            }"""
        )
        # What else there is to say of each stands under it, whole: nothing here moves to one.
        more = page.locator("[data-hmz=found] [data-hmz=epic] .result-more")
        expect(more.nth(8)).to_contain_text("2 sessions")
        expect(more.nth(8)).to_contain_text("took 1h00m")
        assert more.nth(8).evaluate(
            "(one) => one.scrollWidth <= one.clientWidth"
            " && one.getBoundingClientRect().right <= innerWidth"
        )
        expect(page.locator("[data-hmz=search-detail]")).to_be_hidden()
        page.locator("[data-hmz=search-filtering]").click()
        expect(page.locator("[data-hmz=search-workspace]")).to_be_visible()
        expect(page.get_by_role("button", name="Older", exact=True)).to_be_visible()


def test_the_keys_go_on_after_the_pointer_presses_a_tab_a_filter_or_a_page(
    engine: str,
) -> None:
    wire = Wire(faked=_faked())
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _search(page)
        field = page.get_by_role("combobox", name="Search")
        active = page.locator("[data-hmz=found] .active")
        found = page.locator("[data-hmz=found] [data-hmz=epic]")
        # A tab pressed leaves the focus in the field, and is the element it was.
        page.get_by_role("tab", name="Chats").click()
        expect(found).to_have_count(40)
        expect(field).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e2")
        # The counts by how it went are the epics' own: a chat is not found by it.
        page.get_by_role("tab", name="Epics").click()
        expect(found).to_have_count(20)
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e6")
        page.locator("[data-hmz=search-filtering]").click()
        done = page.locator("[data-hmz=search-filters] [data-how=done]")
        expect(done.locator(".count")).to_have_text("20")
        done.click()
        expect(done).to_have_attribute("aria-pressed", "true")
        expect(field).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e9")
        # Tabbed to and pressed by a key, a filter keeps the focus itself: it is not made again.
        done.focus()
        page.keyboard.press("Enter")
        expect(done).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e12")
        # A page turned leaves it in the field too, and Enter opens the one moved to.
        field.focus()
        page.get_by_role("tab", name="All").click()
        page.locator("[data-hmz=search-filters] [data-how=all]").click()
        page.get_by_role("button", name="Older", exact=True).click()
        expect(found).to_have_count(10)
        expect(field).to_be_focused()
        page.keyboard.press("ArrowDown")
        expect(active).to_have_attribute("data-key", "e52")
        wire.faked["chat.get"] = lambda _: None
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/e52$"))


def test_enter_opens_what_was_typed_not_what_was_listed_before_it(engine: str) -> None:
    wire = Wire(faked=_faked())
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _search(page)
        wire.faked["chat.get"] = lambda _: None
        page.keyboard.type("thing 59")
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/e59$"))


def test_the_menu_of_the_one_moved_to_is_opened_by_a_key(engine: str) -> None:
    wire = Wire(faked=_faked())
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _search(page)
        field = page.get_by_role("combobox", name="Search")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Alt+Enter")
        menu = page.locator(".popover.context")
        expect(menu.locator(".context-head")).to_have_text("Talk about thing 2")
        expect(menu.get_by_role("menuitem", name="Copy link")).to_be_visible()
        # Closed, it gives the focus back to the field, and Search is still open.
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)
        expect(field).to_be_focused()
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        # What can be done has no menu of its own.
        page.keyboard.press("ArrowUp")
        page.keyboard.press("ArrowUp")
        expect(page.locator("[data-hmz=found] .active")).to_have_attribute(
            "data-hmz", "import"
        )
        page.keyboard.press("Alt+Enter")
        expect(menu).to_have_count(0)


def test_an_address_and_an_empty_tab_say_what_is_so(engine: str) -> None:
    def none(params: Any) -> dict[str, Any] | None:
        answer = _chats(params)
        if answer is not None:
            answer["result"].update(chats=[], total=0)
        return answer

    wire = Wire(faked={"runs.list": _listed, "chat.list": none})
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        # The chats named with a flow drop it: no filter is set, and the row of them is shut.
        page.evaluate("location.hash = '/search?kind=chat&flow=ralph'")
        chosen = page.locator("[data-hmz=search-tabs] [aria-selected=true]")
        expect(chosen).to_have_text("Chats")
        expect(page.locator("[data-hmz=search-filters]")).to_be_hidden()
        assert "flow=" not in page.url
        # No chats, and nothing typed or filtered: there is no filter to clear.
        empty = page.locator("[data-hmz=found] .empty")
        expect(empty).to_contain_text("No chats yet")
        expect(empty).not_to_contain_text("filters")
        expect(page.locator("[data-hmz=search-new-chat]")).to_be_visible()
        # What gets a chat there is offered with it, and is no line the arrows move to.
        start = empty.get_by_role("link", name="New chat")
        expect(start).to_have_attribute("href", "#/new/chat")
        expect(empty.locator("[role=option]")).to_have_count(0)
        field = page.get_by_role("combobox", name="Search")
        field.fill("zebra")
        expect(empty).to_contain_text("Nothing is like that")
        expect(empty.get_by_role("link")).to_have_count(0)
        # Cleared, what was typed is gone and the tab stays; the keys stay in the field.
        empty.get_by_role("button", name="Clear filters").click()
        expect(field).to_have_value("")
        expect(field).to_be_focused()
        expect(empty).to_contain_text("No chats yet")
        expect(chosen).to_have_text("Chats")
        assert "q=" not in page.url


#: A chat going, one that asks, one that failed, one at rest and an epic of a flow.
_STANDING = [
    {**_run(1), "task": "Ask going", "how": "running", "turn": "running", "held": True},
    {**_run(2), "task": "Ask asks", "how": "running", "held": True, "asking": ["1:1"]},
    {**_run(4), "task": "Ask failed", "how": "failed"},
    {**_run(5), "task": "Ask rests", "how": "stopped"},
    {**_run(6), "task": "Fix it", "how": "done"},
]


def _standing() -> dict[str, Any]:
    """The lists of what stands: the chats, the epic, and what each chat's host says it waits on."""
    chats = [one for one in _STANDING if one["kind"] == "chat"]
    epics = [one for one in _STANDING if one["kind"] == "flow"]
    running = [
        {
            "state": "running",
            "run": 1,
            "kind": "chat",
            "flow": "",
            "epic": "",
            "chat": one["name"],
            "task": one["task"],
            "workspace": one["workspace"],
            "slot": f"chat:{one['name']}",
            "turn": "running" if one.get("turn") == "running" else "done",
            "asking": one.get("asking", []),
        }
        for one in chats
        if one["held"]
    ]
    said: dict[str, dict[str, Any]] = {
        "chat.list": {
            "chats": [_chat(one, one.get("turn") == "running") for one in chats],
            "total": len(chats),
            "offset": 0,
            "limit": 60,
        },
        "runs.list": {
            "runs": epics,
            "total": len(epics),
            "offset": 0,
            "limit": 60,
            "counts": {"done": 1},
            "flows": ["ralph"],
        },
        "hosts.running": {"running": running},
    }

    def says(result: dict[str, Any]) -> Any:
        def answers(_: Any) -> dict[str, Any]:
            return {"result": result}

        return answers

    return {method: says(result) for method, result in said.items()}


def test_search_says_how_each_stands_in_the_sidebars_words(engine: str) -> None:
    wire = Wire(faked=_standing())
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        side = page.locator("[data-hmz=sidebar] [data-hmz=epic]")
        expect(side).to_have_count(5)
        # What each row says of how it stands: its word, or what its dot is named where a
        # chat that waits on its person is marked by one.
        said = {
            one.locator(".side-label").first.inner_text(): one.locator(
                ".side-status, [data-hmz=chat-state]"
            ).evaluate_all(
                "all => all.map((one) => one.textContent || one.getAttribute('aria-label'))"
            )
            for one in side.all()
        }
        page.keyboard.press("Control+k")
        found = page.locator("[data-hmz=found] [data-hmz=epic]")
        expect(found).to_have_count(5)
        # Side by side, the same chat is said to stand the same way: nothing while it rests,
        # and in words here what the sidebar's dot is named.
        for one in found.all():
            task = one.locator(".result-task").inner_text()
            assert one.locator("[data-hmz=result-how]").all_inner_texts() == said[task]
        assert said == {
            "Ask going": ["Running"],
            "Ask asks": ["Awaiting input"],
            "Ask failed": ["Failed"],
            "Ask rests": [],
            "Fix it": ["Done"],
        }
        # And in the line over the foot, of the one moved to.
        page.keyboard.press("ArrowDown")
        expect(
            page.locator("[data-hmz=search-detail] [data-hmz=result-state]")
        ).to_have_text("Awaiting input")
        # A chat's agent is said by what it runs, with no name or role of an epic's agent.
        chip = page.locator("[data-hmz=search-detail] .chip")
        expect(chip).to_have_text("Claude Code sonnet")
        expect(chip).to_have_attribute("title", "claude/sonnet")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        expect(
            page.locator("[data-hmz=search-detail] [data-hmz=result-state]")
        ).to_have_count(0)


def test_search_keeps_the_keys_and_leaves_the_page_as_it_was(engine: str) -> None:
    wire = Wire(faked=_faked())
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        # A view before the one Search is opened over, to step back to.
        go(page, "/flows")
        go(page, "/new/chat")
        box = page.locator("[data-hmz=composer-text]")
        box.click()
        page.keyboard.type("a draft")
        # A menu open under it is closed as Search opens over it.
        page.locator("[data-hmz=permission]").click()
        expect(page.get_by_role("menu", name="Permissions")).to_be_visible()
        _search(page)
        expect(page.get_by_role("menu", name="Permissions")).to_have_count(0)
        dialog = page.locator("[data-hmz=dialog-search]")
        expect(page.locator("[data-hmz=found] [data-hmz=epic]")).to_have_count(50)

        # What can be done stays in sight under fifty found, inside the dialog.
        ends = _box(page, "[data-hmz=dialog-search]")
        for action in ("search-new-chat", "import"):
            at = _box(page, f"[data-hmz=dialog-search] [data-hmz={action}]")
            assert ends[1] < at[1]
            assert at[1] + at[3] <= ends[1] + ends[3]

        # Tab goes round within it, both ways, and never to the page under it.
        for key in (*["Tab"] * 9, *["Shift+Tab"] * 9):
            page.keyboard.press(key)
            assert page.evaluate(
                "() => Boolean(document.activeElement.closest('[data-hmz=dialog-search]'))"
            )

        # One Escape closes it: the page is where it was, the chip the menu was opened
        # from has the focus it held, and the draft stands.
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(page.locator("[data-hmz=permission]")).to_be_focused()
        expect(box).to_have_value("a draft")
        assert "#/new/chat" in page.url

        # Opened from the box and closed, the box is typed into again.
        box.click()
        _search(page)
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(box).to_be_focused()
        page.keyboard.type(" more")
        expect(box).to_have_value("a draft more")

        # Search left no step behind: Back goes to what was open before, not to Search.
        page.locator("[data-hmz=back]").click()
        expect(page.locator("[data-hmz=new-chat]")).to_have_count(0)
        expect(dialog).to_have_count(0)
        assert "#/flows" in page.url

        # What is opened from Search takes its place: Back from it is the view Search
        # was over.
        _search(page)
        expect(page.locator("[data-hmz=found] [data-hmz=epic]")).to_have_count(50)
        page.locator("[data-hmz=dialog-search] [data-hmz=search-new-chat]").click()
        expect(dialog).to_have_count(0)
        expect(page.locator("[data-hmz=new-chat]")).to_be_visible()
        page.locator("[data-hmz=back]").click()
        expect(page.locator("[data-hmz=new-chat]")).to_have_count(0)
        expect(dialog).to_have_count(0)
        assert "#/flows" in page.url
