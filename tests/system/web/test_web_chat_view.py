"""A chat's view: read as a chat app's session, with nothing on it in hmz's own words.

The chat's host is faked on the wire, so the view is drawn with no agent run: its bar is its
title with one menu right after it and, at the far right, a button for each pane beside the
conversation; what a `$` name that is both a skill and a flow does is picked in that menu; its
box holds only Add, what is typed and the button that sends, with its chips in a row under it;
its panel and its box say what they are in plain words. A chat is no epic: it is read by
`chat.get` and listed by `chat.list`, at `#/chats/<id>`, and the button of its box stops the
turn open. A flow's epic, beside it, keeps the bar, the tabs and the words it had; a chat an
earlier hmz recorded as an epic is a chat, and an address of that epic opens the chat. Each in
Chromium and in WebKit.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, frame, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import FloatRect, Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A workspace no host is on, so the page asks the faked host alone.
_FAKE = "/nowhere/fake-workspace"
_SUB = "s-chat"
_SLOT = "chat:fake"
_CHAT = "20261117T000000.000Z-c4a7e0"
_EPIC = "20261117T000000.000Z-f10e00"
_OLD = "20250101T000000.000Z-01dc4a"
_STARTED = {
    "flow": "chat",
    "ref": "chat:chat",
    "task": "hello there",
    "by": "me@web",
    "client": "c1",
    "roles": ["assistant"],
    "names": {"assistant": "Ada"},
    "outworlders": ["human"],
    "agents": {"assistant": "claude/claude-haiku-4-5"},
    "envs": {},
    "params": {},
    "began": 100.0,
    "at": 1794879452.0,
}
#: The chat as `chat.list` rows it: going on its host, between turns.
_ROW: dict[str, Any] = {
    "id": _CHAT,
    "title": "hello there",
    "workspace": _FAKE,
    "workdir": _FAKE,
    "agent": "claude/claude-haiku-4-5",
    "model": "claude-haiku-4-5",
    "began": "2026-11-17T00:00:00.000Z",
    "updated": "2026-11-17T00:00:00.000Z",
    "state": "going",
    "slot": _SLOT,
    "asking": [],
    "permission": "workspace-write",
    "archived": False,
    "spent": None,
}
#: The chat as `chat.get` answers it.
_DETAIL: dict[str, Any] = {
    **_ROW,
    "at": "/nowhere/chat",
    "task": "hello there",
    "prefer": "",
    "forked": "",
    "agents": [
        {
            "name": "Ada",
            "role": "assistant",
            "runs": "claude/claude-haiku-4-5",
            "backend": "claude",
            "model": "claude-haiku-4-5",
            "effort": "",
            "provider": "",
        }
    ],
    "sessions": [],
    "earlier": 0,
    "backup": [],
    "backed": {},
}
#: A flow's epic, written down: what a chat's view must leave as it was.
_FLOWED: dict[str, Any] = {
    "name": _EPIC,
    "workspace": _FAKE,
    "slot": "",
    "kind": "flow",
    "flow": "swe",
    "ref": "swe",
    "task": "build it",
    "began": "2026-11-17T00:00:00.000Z",
    "ended": "2026-11-17T00:01:00.000Z",
    "how": "done",
    "held": False,
    "agents": [
        {"name": "Ada", "role": "coder", "runs": "claude/claude-haiku-4-5"},
        {"name": "Bob", "role": "reviewer", "runs": "claude/claude-haiku-4-5"},
    ],
    "sessions": [],
    "resumable": True,
    "spent": {
        "cost": 0,
        "output_tokens": 0,
        "seconds": 0,
        "money": "$0.00",
        "tokens": "0",
        "worked": "0s",
    },
    "asking": [],
    "backup": [],
    "backed": {},
    "at": "/nowhere/epic",
    "envs": [],
    "used": [],
    "params": {},
    "budget": None,
    "picked_up": "",
    "picks_up": False,
    "foreign": "",
    "calls": [],
}
#: What the chat's host offers: `ralph` both a skill of its CLI and a flow.
_ENTRIES = [
    {"sigil": "/", "name": "model", "about": "", "how": "", "source": "native"},
    {"sigil": "$", "name": "ralph", "about": "", "how": "", "source": "native"},
    {"sigil": "/", "name": "prefer", "about": "", "how": "", "source": "hmz"},
    {"sigil": "$", "name": "ralph", "about": "", "how": "", "source": "flow"},
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def _box(page: Page, selector: str) -> FloatRect:
    """Where an element is drawn, in CSS pixels."""
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box


class _ChatWire(Wire):
    """The wire, which also tells the page what a faked host says."""

    def event(self, sub: str, message: dict[str, Any]) -> None:
        """Tells the page one message of the host attached by `sub`."""
        assert self._page is not None
        self._page.send(
            frame(
                {
                    "jsonrpc": "2.0",
                    "method": "epic.event",
                    "params": {"sub": sub, "message": message},
                }
            )
        )


def _wired() -> tuple[_ChatWire, dict[str, str]]:
    """The wire of a faked chat's host, and the preference that host holds."""
    held = {"prefer": "native", "prefer_from": "settings"}

    def sets(params: dict[str, Any]) -> dict[str, Any]:
        held.update(prefer=params["prefer"], prefer_from="chat")
        return {"result": {}}

    wire = _ChatWire(
        faked={
            "epic.attach": lambda _: {
                "result": {"sub": _SUB, "workspace": _FAKE, "slot": _SLOT}
            },
            "epic.detach": lambda _: {"result": {}},
            # A chat an earlier hmz recorded as an epic is a chat now, by the name it had,
            # and no epic of that name is left.
            "chat.get": lambda params: {
                "result": _DETAIL
                if params["chat"] != _OLD
                else {
                    **_DETAIL,
                    "id": _OLD,
                    "title": "an old chat",
                    "task": "an old chat",
                    "state": "resting",
                    "slot": "",
                }
            },
            "runs.get": lambda params: (
                {"error": {"code": 404, "message": f"There is no epic {_OLD}."}}
                if params["name"] == _OLD
                else {"result": _FLOWED}
            ),
            "chat.commands": lambda _: {"result": {"entries": _ENTRIES, **held}},
            "chat.set": sets,
        }
    )
    return wire, held


def _run(turn: str) -> dict[str, Any]:
    """What the chat's host says of its run: a chat's, named as `chat`, and no epic."""
    return {
        "type": "run",
        "state": "running",
        "run": 1,
        "epic": "",
        "chat": _CHAT,
        "slot": _SLOT,
        "turn": turn,
        **_STARTED,
    }


def _chats(page: Page, wire: _ChatWire) -> None:
    """Opens the faked chat, going and between turns."""
    go(page, f"/live?workspace={_FAKE}&slot={_SLOT}")
    while not wire.params("epic.attach"):
        page.wait_for_timeout(50)
    messages: list[dict[str, Any]] = [
        {
            "type": "welcome",
            "epoch": "e1",
            "client": "c1",
            "workspace": _FAKE,
            "slot": _SLOT,
        },
        _run(""),
        {"type": "sessions", "run": 1, "open": ["Ada/1"], "working": []},
        {"type": "pending", "pending": []},
        {"type": "started", "seq": 1, "run": 1, **_STARTED},
        {
            "type": "opened",
            "seq": 2,
            "run": 1,
            "key": "Ada/1",
            "agent": "Ada",
            "role": "assistant",
        },
        {"type": "live", "seq": 2, "elided": 0},
    ]
    for message in messages:
        wire.event(_SUB, message)
    expect(page.locator("[data-hmz=say]")).to_be_visible()


def test_a_chat_is_drawn_as_a_chat_apps_session(project: Path, engine: str) -> None:
    wire, held = _wired()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _chats(page, wire)
        bar = page.locator("[data-hmz=bar]")

        # Its bar, as a chat app's session keeps its toolbar: 44px high, its title a
        # button with the one menu right after it, and at the far right a 28px button
        # for each pane, then View options, and Ai-chan's button, which ends every view's
        # bar -- no word of hmz's own, and nothing saying how the chat stands.
        expect(bar.locator("h1")).to_have_text("hello there")
        assert _box(page, "[data-hmz=bar]")["height"] == 44
        title = _box(page, "[data-hmz=chat-title]")
        more_at = _box(page, "[data-hmz=chat-menu]")
        assert 0 <= more_at["x"] - (title["x"] + title["width"]) <= 4
        assert bar.locator(".bar-actions button").evaluate_all(
            "all => all.map((one) => one.getAttribute('aria-label'))"
        ) == ["Details", "Terminal", "Changes", "Files", "View options", "Ai-chan"]
        toggles = [
            _box(page, f"[data-hmz={one}]")
            for one in (
                "chat-menu",
                "pane-details",
                "pane-terminal",
                "pane-changes",
                "pane-files",
                "chat-view",
                "aichan-toggle",
            )
        ]
        assert all((one["width"], one["height"]) == (28, 28) for one in toggles)
        assert [one["x"] for one in toggles] == sorted(one["x"] for one in toggles)
        expect(bar.locator(".badge")).to_have_count(0)
        expect(bar.locator("[data-hmz=prefer]")).to_have_count(0)
        expect(bar).not_to_contain_text(
            re.compile("epic|flow|native|began", re.IGNORECASE)
        )
        # The buttons 4px apart, the last 8px from the edge of the view, which the bar
        # runs the whole width of.
        assert {b["x"] - a["x"] for a, b in pairwise(toggles[1:])} == {32}
        whole = _box(page, ".view-epic")
        barred = _box(page, "[data-hmz=bar]")
        assert (barred["x"], barred["width"]) == (whole["x"], whole["width"])
        ending = _box(page, "[data-hmz=bar] [data-hmz=aichan-toggle]")
        assert whole["x"] + whole["width"] - (ending["x"] + ending["width"]) == 8
        assert bar.locator(".bar-actions > *").last.get_attribute("data-hmz") == (
            "aichan-toggle"
        )
        # Its host holds no environment for it: its three panes are said, cannot open,
        # and say why.
        for pane in ("terminal", "changes", "files"):
            expect(bar.locator(f"[data-hmz=pane-{pane}]")).to_be_disabled()
            expect(bar.locator(f"[data-hmz=pane-{pane}]")).to_have_attribute(
                "title", f"No {pane} in this environment"
            )

        # Nothing is said over its box of how it stands while it only answers: neither
        # who is responding nor that it waits; and its Usage chip is its ring alone.
        expect(page.locator("[data-hmz=chat-status]")).to_have_count(0)
        expect(page.locator("[data-hmz=dock]")).not_to_contain_text(
            re.compile("responding|Waiting", re.IGNORECASE)
        )
        usage = page.locator("[data-hmz=chat-usage]")
        expect(usage).to_have_text("")
        expect(usage).to_have_attribute("aria-label", "Usage")

        # What was a row of buttons is in the menu, with what a right click offers.
        more = bar.locator("[data-hmz=chat-menu]")
        more.click()
        menu = page.get_by_role("menu", name="Chat menu")
        for label in ("Copy link", "Upload", "Skill or flow"):
            expect(menu.get_by_role("menuitem", name=label)).to_be_visible()
        expect(menu).not_to_contain_text(re.compile("epic|native", re.IGNORECASE))

        # What a `$` name that is both does: said in plain words, the one in force
        # marked, and where it comes from said under them.
        menu.get_by_role("menuitem", name="Skill or flow").click()
        prefer = page.locator("[data-hmz=prefer]")
        skill = prefer.locator("[data-prefer=native]")
        flow = prefer.locator("[data-prefer=flow]")
        expect(skill).to_contain_text("Use the skill")
        expect(flow).to_contain_text("Start the flow")
        expect(skill).to_have_attribute("aria-checked", "true")
        expect(prefer.locator("[data-hmz=prefer-from]")).to_have_text("From settings")
        flow.click()
        expect(menu).to_have_count(0)
        assert wire.params("chat.set")[-1]["prefer"] == "flow"
        assert held["prefer_from"] == "chat"
        more.click()
        expect(menu.get_by_role("menuitem", name="Skill or flow")).to_contain_text(
            "Starts the flow · set for this chat"
        )
        menu.get_by_role("menuitem", name="Skill or flow").click()
        expect(flow).to_have_attribute("aria-checked", "true")
        expect(prefer.locator("[data-hmz=prefer-from]")).to_have_text(
            "Set for this chat"
        )
        page.keyboard.press("Escape")

        # `/prefer` still sets it, as it did.
        say = page.locator("[data-hmz=say] textarea")
        say.fill("/prefer native")
        say.press("Enter")
        while wire.params("chat.set")[-1]["prefer"] != "native":
            page.wait_for_timeout(50)

        # Its box is a chat app's: inside it only Add, what is typed and the button
        # that sends, each 28px high in one row; its chips in a row under it, 24px
        # high, at its right -- the model and then what the chat may touch.
        expect(say).to_have_attribute("placeholder", "Reply…")
        expect(page.locator("[data-hmz=say] .composer-box > *")).to_have_count(3)
        inside = [
            _box(page, f"[data-hmz=say] {one}")
            for one in ("[data-hmz=composer-add]", "textarea", ".send")
        ]
        assert [one["height"] for one in inside] == [28, 28, 28]
        assert [one["x"] for one in inside] == sorted(one["x"] for one in inside)
        assert len({one["y"] for one in inside}) == 1
        boxed = _box(page, "[data-hmz=say] .composer-box")
        under = _box(page, "[data-hmz=say] [data-hmz=composer-under]")
        assert under["y"] >= boxed["y"] + boxed["height"]
        chips = page.locator("[data-hmz=say] [data-hmz=composer-under] button:visible")
        assert chips.evaluate_all("all => all.map((one) => one.dataset.hmz)") == [
            "chat-model",
            "permission",
            "chat-usage",
        ]
        expect(chips.first).to_have_text("Claude Code Haiku 4.5 Default")
        for hook in ("chat-model", "permission", "chat-usage"):
            assert _box(page, f"[data-hmz=say] [data-hmz={hook}]")["height"] == 24
        # Usage is a ring 24px square while the chat has spent nothing to say, the last
        # of the row and set in from the box's edge.
        used = _box(page, "[data-hmz=say] [data-hmz=chat-usage]")
        assert used["width"] == 24
        assert boxed["x"] + boxed["width"] - (used["x"] + used["width"]) == 12
        expect(page.locator("[data-hmz=say] [data-hmz=chat-usage]")).to_have_attribute(
            "aria-label", "Usage"
        )
        # It opens a popup of its own by the ring -- this chat, then its folder -- and
        # not the chat's Details.
        page.locator("[data-hmz=say] [data-hmz=chat-usage]").click()
        popup = page.get_by_role("dialog", name="Usage")
        expect(popup).to_be_visible()
        expect(popup.locator(".popover-head").first).to_have_text("This chat")
        expect(popup.locator("[data-hmz=usage-settings]")).to_have_text(
            "Usage settings"
        )
        expect(
            page.locator("[data-hmz=bar] [data-hmz=pane-details]")
        ).to_have_attribute("aria-pressed", "false")
        page.keyboard.press("Escape")
        expect(popup).to_have_count(0)
        expect(page.locator("[data-hmz=say] [data-hmz=chat-usage]")).to_be_focused()
        last = _box(page, "[data-hmz=say] [data-hmz=permission]")
        assert last["x"] > boxed["x"] + boxed["width"] / 2
        expect(
            page.locator("[data-hmz=say] [data-hmz=workspace-picker]")
        ).to_have_count(0)

        # What else it takes is offered by Add, under plain names, and as it is typed.
        add = page.locator("[data-hmz=say] [data-hmz=composer-add]")
        add.click()
        adding = page.get_by_role("menu", name="Add")
        expect(adding.get_by_role("menuitem")).to_have_text(
            ["Add files", "Slash commands", "Skills and flows", "Run a shell command"]
        )
        adding.get_by_role("menuitem", name="Slash commands").click()
        expect(say).to_have_value("/")
        expect(say).to_be_focused()
        offered = page.locator("[data-hmz=completions] .complete-group")
        expect(offered).to_have_text(["Commands", "Humanize"])
        say.fill("r")
        add.click()
        adding.get_by_role("menuitem", name="Skills and flows").click()
        expect(say).to_have_value("$r")
        expect(offered).to_have_text(["Skills", "Flows"])
        say.fill("see")
        add.click()
        adding.get_by_role("menuitem", name="Add files").click()
        expect(say).to_have_value("see @")
        say.fill("")
        add.click()
        adding.get_by_role("menuitem", name="Run a shell command").click()
        expect(say).to_have_value("!")
        say.fill("")

        # No pane is open until one is asked for; Details opens the panel, which says
        # what it is in a chat's words, and pressed again shuts it.
        panel = page.locator("[data-hmz=inspector]")
        details = bar.locator("[data-hmz=pane-details]")
        expect(panel).to_be_hidden()
        expect(details).to_have_attribute("aria-pressed", "false")
        before = _box(page, "[data-hmz=pane-details]")
        details.click()
        expect(panel).to_be_visible()
        expect(details).to_have_attribute("aria-pressed", "true")
        # The bar runs over the pane too: the button stays where it was pressed, so
        # pressing there again shuts the pane.
        assert _box(page, "[data-hmz=pane-details]") == before
        assert _box(page, "[data-hmz=inspector]")["y"] == 44
        page.mouse.click(before["x"] + 14, before["y"] + 14)
        expect(panel).to_be_hidden()
        # The title is a button that renames the chat where it stands, and opens no pane.
        bar.locator("[data-hmz=chat-title]").click()
        renaming = bar.locator("[data-hmz=title-edit]")
        expect(renaming).to_have_value("hello there")
        renaming.press("Escape")
        expect(renaming).to_have_count(0)
        expect(panel).to_be_hidden()
        details.click()
        expect(panel).to_be_visible()
        expect(details).to_have_attribute("aria-pressed", "true")
        # The pane is picked on the bar: it is headed by its name, with no tabs of its own.
        expect(panel.get_by_role("tab")).to_have_count(0)
        expect(panel.locator("[data-hmz=pane-title]")).to_have_text("Details")
        expect(panel.locator("h3")).to_contain_text(
            ["Usage", "First message", "About this chat"]
        )
        expect(panel.locator("dt")).to_have_text(
            [
                "Chat ID",
                "Saved at",
                "Folder",
                "Started",
                "Nous",
                "Environment",
                "Options",
                "Limits",
            ]
        )
        # It counts no sessions, and names none.
        expect(panel).not_to_contain_text(re.compile("session", re.IGNORECASE))
        expect(panel.locator("dd").nth(4)).to_have_text("Claude Code Haiku 4.5 Default")
        # Side questions are under View options, and no pane's button is theirs; Ai-chan
        # is not among them, her button being on the bar.
        bar.locator("[data-hmz=chat-view]").click()
        offered = page.get_by_role("menu", name="View options")
        expect(offered.get_by_role("menuitem")).to_have_text(["Side questions"])
        offered.get_by_role("menuitem", name="Side questions").click()
        expect(details).to_have_attribute("aria-pressed", "false")
        expect(panel.locator("[data-hmz=pane-title]")).to_have_text("Side questions")
        expect(panel).to_contain_text("Side questions never reach this chat.")
        expect(panel.locator("[data-hmz=btw-tab]")).to_have_text("New question")
        expect(panel.locator("[data-hmz=btw] textarea")).to_have_attribute(
            "placeholder", "Ask a side question"
        )
        expect(panel).not_to_contain_text(re.compile("epic", re.IGNORECASE))
        # A chat is one conversation: there is none to pick to ask it of.
        expect(panel.locator("[data-hmz=btw-to]")).to_be_hidden()
        # Ai-chan's drawer is opened from the bar's end, as from any view's, and her
        # button says so.
        toggle = bar.locator("[data-hmz=aichan-toggle]")
        expect(toggle).to_have_attribute("aria-pressed", "false")
        toggle.click()
        expect(page.locator("[data-hmz=app]")).to_have_class(re.compile("aichan-open"))
        expect(toggle).to_have_attribute("aria-pressed", "true")
        # Both would leave the conversation too narrow to read: the drawer takes the
        # pane's place, and the conversation keeps 480 at the least.
        expect(panel).to_be_hidden()
        assert _box(page, "[data-hmz=say]")["width"] >= 480


def test_a_flows_epic_keeps_its_bar_its_tabs_and_its_words(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, f"/epics/{_EPIC}")
        bar = page.locator("[data-hmz=bar]")
        expect(bar.locator("h1")).to_have_text("build it")
        expect(bar.locator(".bar-sub")).to_contain_text("swe")
        expect(bar.locator(".bar-sub")).to_contain_text("began")
        expect(bar.locator("[data-hmz=chat-menu]")).to_have_count(0)
        for label in ("Export", "Upload", "Copy link"):
            expect(bar.get_by_role("button", name=label)).to_be_visible()
        expect(bar.locator("[data-hmz=exomyth-open]")).to_be_visible()

        # Its bar ends with Ai-chan's button, as every view's does.
        assert bar.locator(".bar-actions > *").last.get_attribute("data-hmz") == (
            "aichan-toggle"
        )
        # What says where its handovers come from stands clear of what picks the shape.
        note = _box(page, ".graph-note")
        switch = _box(page, ".shape-switch")
        assert (
            note["y"] >= switch["y"] + switch["height"]
            or note["x"] + note["width"] <= switch["x"]
        )

        panel = page.locator("[data-hmz=inspector]")
        expect(panel.get_by_role("tab")).to_have_text(["Epic", "Aside"])
        expect(panel.locator("h3")).to_contain_text(["Figures", "Task", "Setup"])
        expect(panel.locator("dt")).to_contain_text(["epic", "written to", "workdir"])
        panel.get_by_role("tab", name="Aside").click()
        expect(panel).to_contain_text("Side questions never reach the epic.")
        expect(panel.locator("[data-hmz=btw-tab]")).to_have_text("New aside")


#: How tall each of the elements a locator finds is drawn, in whole pixels.
_TALL = "all => all.map((one) => Math.round(one.getBoundingClientRect().height))"


def _listed(*rows: dict[str, Any]) -> dict[str, Any]:
    """What `chat.list` answers: these rows, as the sidebar and Search read them."""
    return {
        "result": {"chats": list(rows), "total": len(rows), "offset": 0, "limit": 60}
    }


def test_the_button_of_a_chats_box_stops_the_turn_open(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    refusing: list[bool] = []

    def stops(_: dict[str, Any]) -> dict[str, Any]:
        if refusing:
            why = "no turn is open, so there is nothing to stop"
            return {"error": {"code": 409, "message": why}}
        return {"result": {}}

    wire.faked["chat.stop"] = stops
    wire.faked["chat.say"] = lambda _: {"result": {}}
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        _chats(page, wire)
        # The address names the chat, by its id, and never as an epic.
        expect(page).to_have_url(re.compile(rf"#/chats/{re.escape(_CHAT)}$"))
        button = page.locator("[data-hmz=say] .send")
        say = page.locator("[data-hmz=say] textarea")
        # Between turns the button sends.
        wire.event(_SUB, _run("done"))
        expect(button).to_have_attribute("aria-label", "Send")

        # A turn open: the button stops it, by `chat.stop` of the chat's workspace and
        # slot, and the chat stays -- its box with it.
        wire.event(_SUB, _run("running"))
        expect(button).to_have_attribute("aria-label", "Stop")
        expect(button).to_have_attribute("data-hmz", "stop")
        button.click()
        while not wire.params("chat.stop"):
            page.wait_for_timeout(50)
        stopped = wire.params("chat.stop")[0]
        assert (stopped["workspace"], stopped["slot"]) == (_FAKE, _SLOT)
        assert not wire.params("epic.stop")
        expect(say).to_be_visible()

        # What is typed is still said into the turn by Enter, and stops nothing.
        say.fill("one more thing")
        say.press("Enter")
        while not wire.params("chat.say"):
            page.wait_for_timeout(50)
        assert wire.params("chat.say")[0]["text"] == "one more thing"
        assert len(wire.params("chat.stop")) == 1

        # Refused, the box says the daemon's own sentence.
        refusing.append(True)
        button.click()
        expect(page.locator("[data-hmz=say] .composer-said")).to_have_text(
            "no turn is open, so there is nothing to stop"
        )

        # The turn done, it sends again.
        wire.event(_SUB, _run("done"))
        expect(button).to_have_attribute("aria-label", "Send")
        expect(button).to_have_attribute("data-hmz", "send")


def test_an_address_of_the_epic_a_chat_was_recorded_as_opens_the_chat(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/new/chat")
        before = page.evaluate("history.length")
        go(page, f"/epics/{_OLD}")
        # The address becomes the chat's, by the name the epic had, with no step between.
        expect(page).to_have_url(re.compile(rf"#/chats/{re.escape(_OLD)}$"))
        assert page.evaluate("history.length") == before + 1
        bar = page.locator("[data-hmz=bar]")
        # A chat's bar and a chat's box: it is said to as any chat is, and nothing of an
        # epic's view is drawn.
        expect(bar.locator("[data-hmz=chat-title]")).to_have_text("an old chat")
        expect(bar.locator("[data-hmz=chat-menu]")).to_have_count(1)
        expect(page.locator("[data-hmz=inspector]").get_by_role("tab")).to_have_count(0)
        expect(page.locator("[data-hmz=dock] textarea")).to_have_count(1)
        expect(page.locator("[data-hmz=dock] textarea")).to_have_attribute(
            "placeholder", "Reply…"
        )
        expect(page.locator("body")).not_to_contain_text("Resume")
        assert wire.params("chat.get")[-1]["chat"] == _OLD
        # An epic of a flow that is not there is said not to be, and stays where it is.
        go(page, "/epics/20200101T000000.000Z-000000")
        wire.faked["runs.get"] = lambda _: {
            "error": {"code": 404, "message": "There is no epic."}
        }
        wire.faked["chat.get"] = lambda _: {
            "error": {"code": 404, "message": "There is no chat."}
        }
        go(page, "/epics/20200101T000000.000Z-111111")
        expect(page.locator(".view-epic")).to_contain_text("There is no epic.")
        expect(page).to_have_url(re.compile(r"#/epics/20200101T000000\.000Z-111111$"))


def test_an_address_of_that_epic_opened_before_the_daemon_answers_opens_the_chat_once_it_does(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    was = dict(wire.faked)
    down = {"error": {"code": 503, "message": "The daemon is not reached."}}
    wire.faked["runs.get"] = lambda _: down
    wire.faked["chat.get"] = lambda _: down
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, f"/epics/{_OLD}")
        expect(page.locator(".view-epic")).to_contain_text("The daemon is not reached.")
        assert wire.params("chat.get")
        # The daemon up, the epic is refused as no epic and the chat is asked for again.
        wire.faked.update(was)
        expect(page).to_have_url(
            re.compile(rf"#/chats/{re.escape(_OLD)}$"), timeout=30_000
        )
        expect(page.locator("[data-hmz=bar] [data-hmz=chat-title]")).to_have_text(
            "an old chat"
        )


def test_a_chat_kept_as_an_epic_imported_by_its_path_opens_as_the_chat(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    wire.faked["runs.import"] = lambda _: {
        "result": {"name": _OLD, "workspace": _FAKE, "resumable": True, "why": ""}
    }
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/new/chat")
        go(page, "/epics/import?path=/somewhere/old.hmzepic")
        page.locator("[data-hmz=importing]").get_by_role(
            "button", name="Import"
        ).click()
        # A chat has no Exomyth: it is opened as the chat it was read back in as.
        expect(page).to_have_url(re.compile(rf"#/chats/{re.escape(_OLD)}$"))
        expect(page.locator("[data-hmz=bar] [data-hmz=chat-title]")).to_have_text(
            "an old chat"
        )
        assert [one["path"] for one in wire.params("runs.import")] == [
            "/somewhere/old.hmzepic"
        ]
        # Going back never imports it again.
        page.go_back()
        expect(page).to_have_url(re.compile(r"#/new/chat$"))
        assert len(wire.params("runs.import")) == 1


def test_search_closed_over_a_chat_just_started_leaves_it_as_it_was(
    project: Path, engine: str
) -> None:
    wire, _ = _wired()
    wire.faked["chat.list"] = lambda _: _listed(_ROW)
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        # Opened as a chat just started is: by its host, the address then naming the chat.
        _chats(page, wire)
        address = re.compile(rf"#/chats/{re.escape(_CHAT)}$")
        expect(page).to_have_url(address)
        current = page.locator("[data-hmz=sidebar] [data-hmz=epic][aria-current=page]")
        expect(current).to_have_count(1)
        box = page.locator("[data-hmz=say] [data-hmz=composer-text]")
        box.click()
        page.keyboard.type("a draft")

        # Search opened over it with its menu open, and closed by one Escape: the menu is
        # gone, the address and the row marked are the chat's still, and the draft stands.
        page.locator("[data-hmz=chat-menu]").click()
        expect(page.get_by_role("menu", name="Chat menu")).to_be_visible()
        page.keyboard.press("Control+k")
        dialog = page.locator("[data-hmz=dialog-search]")
        expect(dialog).to_be_visible()
        expect(page.get_by_role("menu", name="Chat menu")).to_have_count(0)
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(page).to_have_url(address)
        expect(current).to_have_count(1)
        expect(box).to_have_value("a draft")
        expect(page.locator("[data-hmz=chat-menu]")).to_be_focused()

        # From the box and back to it.
        box.click()
        page.keyboard.press("Control+k")
        expect(dialog).to_be_visible()
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(box).to_be_focused()
        expect(page).to_have_url(address)
        expect(current).to_have_count(1)


@pytest.mark.parametrize("width", [1296, 390])
def test_a_new_chats_chips_and_menus_are_a_chat_apps(
    project: Path, engine: str, width: int
) -> None:
    with (
        served() as site,
        opened(site, engine=engine, width=width, height=800) as page,
    ):
        go(page, "/new/chat")
        under = page.locator("[data-hmz=composer-under]")
        model = under.locator("[data-hmz=pick-model]")
        expect(model).to_have_text("Claude Code Haiku 4.5 Default")
        # Each chip is named by what it picks and what is picked; the row ends with Usage.
        chips = under.locator(".under-left button:visible, .under-right > *")
        assert chips.evaluate_all(
            "all => all.map((one) => (one.matches('button, a') ? one :"
            " one.querySelector('button')).getAttribute('aria-label'))"
        ) == [
            "Environment: Local, project",
            "Nous: Claude Code Haiku 4.5 Default",
            "Permissions: Edit this folder",
            "Usage",
        ]
        usage = _box(page, "[data-hmz=new-usage]")
        assert (usage["width"], usage["height"]) == (24, 24)
        permission = _box(page, "[data-hmz=permission]")
        assert usage["x"] >= permission["x"] + permission["width"]
        # Usage opens a popup of its own by the ring, not a page of Settings: what the
        # folder has used today and over 7 days, and the way to the whole page.
        ring = under.locator("[data-hmz=new-usage]")
        ring.click()
        used = page.get_by_role("dialog", name="Usage")
        expect(used).to_be_visible()
        expect(page).to_have_url(re.compile(r"#/new/chat"))
        expect(used.locator(".popover-head")).to_have_text(["project"])
        expect(used.locator("dt")).to_have_text(["Today (UTC)", "Last 7 days"])
        expect(used.locator("[data-hmz=usage-settings]")).to_have_attribute(
            "href", re.compile(r"#/settings/usage\?workspace=")
        )
        popped = _box(page, "[role=dialog][aria-label=Usage]")
        assert popped["width"] == min(308, width - 16)
        assert popped["y"] + popped["height"] <= usage["y"]
        page.keyboard.press("Escape")
        expect(used).to_have_count(0)
        expect(ring).to_be_focused()
        # Tab past its last stop leaves it as Escape does: closed, the focus on the ring.
        page.keyboard.press("Enter")
        expect(used.locator("[data-hmz=usage-settings]")).to_be_focused()
        page.keyboard.press("Tab")
        expect(used).to_have_count(0)
        expect(ring).to_be_focused()
        if width >= 860:
            # What a chip says where pointed at stands over the whole box, never on it.
            model.hover()
            expect(page.locator(".tip")).to_have_text("claude/claude-haiku-4-5")
            tip, typed = _box(page, ".tip"), _box(page, ".composer-box")
            assert tip["y"] + tip["height"] <= typed["y"]
            page.mouse.move(1, 1)

        # Permissions: 308 wide where there is room, the three in rows of 44 under no
        # heading, opened on the one in force.
        under.locator("[data-hmz=permission]").click()
        menu = page.get_by_role("menu", name="Permissions")
        expect(menu.locator(".popover-head")).to_have_count(0)
        expect(menu.get_by_role("menuitem")).to_have_count(3)
        assert _box(page, "[role=menu][aria-label=Permissions]")["width"] == 308
        assert set(menu.get_by_role("menuitem").evaluate_all(_TALL)) == {44}
        expect(menu.locator("[data-permission=workspace-write]")).to_be_focused()
        expect(menu.locator(".permission-note")).to_be_visible()
        # It opens from its chip, its foot by the chip's top and its right edge on the chip's.
        chip, popped = permission, _box(page, "[role=menu][aria-label=Permissions]")
        assert 0 <= chip["y"] - popped["y"] - popped["height"] <= 6
        assert abs(chip["x"] + chip["width"] - popped["x"] - popped["width"]) <= 1
        page.keyboard.press("Escape")

        # Nous: a harness and a model a row, then Effort and More, each one row that opens
        # beside it.
        model.click()
        menu = page.get_by_role("menu", name="Nous")
        rows = menu.locator(
            ".nous-list > [role=menuitem][data-cli=claude], .model-menu > .choice-sub"
        )
        expect(rows).to_have_text(
            [
                "Claude Code - Haiku 4.5",
                "Claude Code - Opus 4.1",
                "EffortDefault",
                "More",
            ]
        )
        assert set(rows.evaluate_all(_TALL)) == {28}
        chip, popped = (
            _box(page, "[data-hmz=pick-model]"),
            _box(page, "[role=menu][aria-label=Nous]"),
        )
        assert 0 <= chip["y"] - popped["y"] - popped["height"] <= 6
        expect(menu.locator("[data-value=claude-haiku-4-5]")).to_be_focused()
        # One opened beside it takes the other's place: never two side by side.
        menu.get_by_role("menuitem", name="Effort").click()
        expect(page.locator("[data-hmz=pick-effort]")).to_be_visible()
        # It ends no lower than the menu it came from: never on the chips, nor the box.
        beside = _box(page, "[data-hmz=pick-effort]")
        assert beside["y"] + beside["height"] <= popped["y"] + popped["height"] + 1
        menu.get_by_role("menuitem", name="More").click()
        expect(page.locator("[data-hmz=pick-effort]")).to_have_count(0)
        more = page.locator("[data-hmz=pick-more]")
        expect(more.locator("[data-hmz=pick-model-typed]")).to_be_visible()
        expect(
            more.locator(":scope > .choice-sub, :scope > [role=menuitem]")
        ).to_have_text(["AccountLocal", "Refresh models"])
        # A menu opened from More shuts alone, by the left arrow.
        more.get_by_role("menuitem", name="Account").click()
        expect(page.locator("[data-hmz=pick-account]")).to_be_visible()
        page.keyboard.press("ArrowLeft")
        expect(page.locator("[data-hmz=pick-account]")).to_have_count(0)
        expect(more).to_be_visible()
        # And so does More, by Escape: one press closes one menu, the topmost.
        page.keyboard.press("Escape")
        expect(more).to_have_count(0)
        expect(menu).to_be_visible()
        expect(menu.get_by_role("menuitem", name="More")).to_be_focused()
        page.keyboard.press("Escape")
        expect(menu).to_have_count(0)


#: What holds the focus, said by what it is marked or named.
_FOCUSED = (
    "() => document.activeElement.dataset.hmz"
    " || document.activeElement.getAttribute('aria-label') || document.activeElement.tagName"
)


@pytest.mark.usefixtures("loops")
def test_a_form_read_late_leaves_the_focus_where_it_was_put(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with (
        served() as site,
        opened(site, engine=engine, width=1296, height=792, routed=wire.routes) as page,
    ):
        box = page.locator("[data-hmz=composer-text]")
        model = page.locator("[data-hmz=pick-model]")
        permission = page.locator("[data-hmz=permission]")

        def reads(address: str, method: str) -> None:
            """Opens a form whose reading is held back: drawn, with what it reads to come."""
            go(page, "/flows")
            wire.holds(method)
            go(page, address)
            wire.waits(page)

        # Left alone while it is read, a new chat's box is what is typed into next.
        reads("/new/chat", "settings.get")
        expect(model).to_have_count(0)
        wire.lets_through()
        expect(model).to_have_text("Claude Code Haiku 4.5 Default")
        assert page.evaluate(_FOCUSED) == "composer-text"

        # A chip's menu opened and closed while it is read: the chip has the focus back, and
        # what is read after that does not take it for the box.
        reads("/new/chat", "settings.get")
        permission.click()
        expect(page.get_by_role("menu", name="Permissions")).to_be_visible()
        page.keyboard.press("Escape")
        expect(permission).to_be_focused()
        wire.lets_through()
        expect(model).to_have_text("Claude Code Haiku 4.5 Default")
        assert page.evaluate(_FOCUSED) == "permission"

        # And so with a dialog opened from the chip and closed, which gives it the focus back.
        reads("/new/chat", "settings.get")
        permission.focus()
        page.keyboard.press("Control+k")
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=dialog-search]")).to_have_count(0)
        expect(permission).to_be_focused()
        wire.lets_through()
        expect(model).to_have_text("Claude Code Haiku 4.5 Default")
        assert page.evaluate(_FOCUSED) == "permission"

        # A dialog closed over a form nothing held the focus in leaves it on the page as a
        # whole, which is nowhere in particular: the box takes it once the form is read.
        reads("/new/chat", "settings.get")
        page.keyboard.press("Control+k")
        expect(page.locator("[data-hmz=dialog-search]")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("[data-hmz=page]")).to_be_focused()
        wire.lets_through()
        expect(model).to_have_text("Claude Code Haiku 4.5 Default")
        assert page.evaluate(_FOCUSED) == "composer-text"

        # A new epic's form reads its flow the same way.
        reads("/new?flow=goal", "flows.get")
        wire.lets_through()
        expect(box).to_have_attribute("placeholder", "What should goal do?")
        assert page.evaluate(_FOCUSED) == "composer-text"
        reads("/new?flow=goal", "flows.get")
        picker = page.locator("[data-hmz=flow-picker]")
        picker.click()
        expect(page.get_by_role("menu", name="Flows")).to_be_visible()
        page.keyboard.press("Escape")
        expect(picker).to_be_focused()
        wire.lets_through()
        expect(box).to_have_attribute("placeholder", "What should goal do?")
        assert page.evaluate(_FOCUSED) == "flow-picker"


@pytest.mark.parametrize("width", [1296, 390])
def test_a_new_epic_with_no_flow_says_so_where_it_is_read(
    project: Path, engine: str, width: int
) -> None:
    # A machine with no flow installed, as hmz is installed: it ships none.
    wire = Wire(faked={"flows.list": lambda _: {"result": {"flows": [], "flow": ""}}})
    with (
        served() as site,
        opened(
            site, engine=engine, width=width, height=800, routed=wire.routes
        ) as page,
    ):
        go(page, "/new")
        # hmz ships no flow: the middle of the page says so, and where one is installed.
        lacking = page.locator("[data-hmz=no-flow]")
        expect(lacking).to_be_visible()
        expect(lacking).to_contain_text("No flow installed yet.")
        assert _box(page, "[data-hmz=no-flow]")["height"] > 40
        opens = lacking.locator("[data-hmz=no-flow-open]")
        expect(opens).to_have_text("Open Flows")
        # Flows is of no folder: where one is installed, its flowverses.
        expect(opens).to_have_attribute("href", re.compile(r"#/flows\?tab=verses$"))
        # What picks the flow says there is none, and offers the same.
        picker = page.locator("[data-hmz=flow-picker]")
        expect(picker.locator("b")).to_have_text("None")
        picker.click()
        expect(
            page.get_by_role("menu", name="Flows").get_by_role("menuitem")
        ).to_have_text(["Open Flows"])
        page.keyboard.press("Escape")
        # Of what a flow is set up with there is where it runs alone, and no Options.
        expect(page.get_by_role("button", name="Options", exact=True)).to_have_count(0)
        expect(page.locator("[data-hmz=options] > *:visible")).to_have_count(1)
        expect(
            page.locator("[data-hmz=options] [data-hmz=setup-environment]")
        ).to_be_visible()
        expect(page.locator("[data-hmz=options] [data-hmz=role-row]")).to_have_count(0)
        # Started all the same, it is refused with what to do first.
        text = page.locator("[data-hmz=composer-text]")
        text.fill("do it")
        text.press("Enter")
        expect(page.locator("[data-hmz=start] .composer-said")).to_have_text(
            "Install a flow first, from Flows."
        )
        opens.click()
        expect(page).to_have_url(re.compile(r"#/flows"))
