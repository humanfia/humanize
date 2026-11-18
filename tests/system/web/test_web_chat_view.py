"""A chat's view: read as a chat app's session, with nothing on it in hmz's own words.

The chat's host is faked on the wire, so the view is drawn with no agent run: its bar is its
title, one menu and the panel's button; what a `$` name that is both a skill and a flow does is
picked in that menu; its panel and its box say what they are in plain words. A flow's epic,
beside it, keeps the bar, the tabs and the words it had. Each in Chromium and in WebKit.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, frame, go, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

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
_DETAIL: dict[str, Any] = {
    "name": _CHAT,
    "workspace": _FAKE,
    "slot": _SLOT,
    "kind": "chat",
    "flow": "chat",
    "task": "hello there",
    "began": "2026-11-17T00:00:00.000Z",
    "ended": None,
    "how": "running",
    "agents": [{"name": "Ada", "role": "assistant", "runs": "claude/claude-haiku-4-5"}],
    "sessions": [],
    "resumable": True,
    "spent": None,
    "held": True,
    "asking": [],
    "backup": [],
    "backed": {},
    "at": "/nowhere/epic",
    "ref": "chat:chat",
    "envs": [],
    "used": [],
    "params": {},
    "budget": None,
    "picked_up": "",
    "earlier": 0,
    "picks_up": False,
    "foreign": "",
    "calls": [],
}
#: A flow's epic, written down: what a chat's view must leave as it was.
_FLOWED: dict[str, Any] = {
    **_DETAIL,
    "name": _EPIC,
    "slot": "",
    "kind": "flow",
    "flow": "swe",
    "ref": "swe",
    "task": "build it",
    "ended": "2026-11-17T00:01:00.000Z",
    "how": "done",
    "held": False,
    "agents": [
        {"name": "Ada", "role": "coder", "runs": "claude/claude-haiku-4-5"},
        {"name": "Bob", "role": "reviewer", "runs": "claude/claude-haiku-4-5"},
    ],
    "spent": {
        "cost": 0,
        "output_tokens": 0,
        "seconds": 0,
        "money": "$0.00",
        "tokens": "0",
        "worked": "0s",
    },
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
            "runs.get": lambda params: {
                "result": _FLOWED if params["name"] == _EPIC else _DETAIL
            },
            "chat.commands": lambda _: {"result": {"entries": _ENTRIES, **held}},
            "chat.set": sets,
        }
    )
    return wire, held


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
        {
            "type": "run",
            "state": "running",
            "run": 1,
            "epic": _CHAT,
            "slot": _SLOT,
            "turn": "",
            **_STARTED,
        },
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

        # Its bar: its title, one menu, the panel's button and Ai-chan's -- no row of
        # buttons, no switch, and no word of hmz's own.
        expect(bar.locator("h1")).to_have_text("hello there")
        expect(bar.locator(".bar-actions > *")).to_have_count(3)
        expect(bar.locator("[data-hmz=prefer]")).to_have_count(0)
        expect(bar).not_to_contain_text(
            re.compile("epic|flow|native|began", re.IGNORECASE)
        )

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

        # Its box is as quiet as a chat app's: what else it takes is said on hover, and
        # offered, under plain names, as it is typed.
        expect(say).to_have_attribute("placeholder", "Reply…")
        say.hover()
        expect(page.locator(".tip")).to_contain_text("$ for skills and flows")
        say.fill("/")
        offered = page.locator("[data-hmz=completions] .complete-group")
        expect(offered).to_have_text(["Commands", "Humanize"])
        say.fill("$r")
        expect(offered).to_have_text(["Skills", "Flows"])
        say.fill("")

        # Its panel says what it is in a chat's words.
        panel = page.locator("[data-hmz=inspector]")
        expect(panel.get_by_role("tab")).to_have_text(["Details", "Side questions"])
        expect(panel.locator("h3")).to_contain_text(
            ["Usage", "First message", "About this chat"]
        )
        expect(panel.locator("dt")).to_have_text(
            [
                "Chat ID",
                "Saved at",
                "Folder",
                "Started",
                "Model",
                "Environment",
                "Options",
                "Limits",
                "Sessions",
            ]
        )
        expect(panel.locator("dd").nth(4)).to_have_text("claude/claude-haiku-4-5")
        panel.get_by_role("tab", name="Side questions").click()
        expect(panel).to_contain_text("Side questions never reach this chat.")
        expect(panel.locator("[data-hmz=btw-tab]")).to_have_text("New question")
        expect(panel.locator("[data-hmz=btw] textarea")).to_have_attribute(
            "placeholder", "Ask a side question"
        )
        expect(panel).not_to_contain_text(re.compile("epic", re.IGNORECASE))


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

        panel = page.locator("[data-hmz=inspector]")
        expect(panel.get_by_role("tab")).to_have_text(["Epic", "Aside"])
        expect(panel.locator("h3")).to_contain_text(["Figures", "Task", "Setup"])
        expect(panel.locator("dt")).to_contain_text(["epic", "written to", "workdir"])
        panel.get_by_role("tab", name="Aside").click()
        expect(panel).to_contain_text("Side questions never reach the epic.")
        expect(panel.locator("[data-hmz=btw-tab]")).to_have_text("New aside")
