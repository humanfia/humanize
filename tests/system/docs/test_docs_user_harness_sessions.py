"""The pictures of `docs/user/harness-sessions.md`: the sessions a CLI had on its own.

A session Claude Code, Codex and OpenCode each had by hand in `~/shop` is staged as that CLI
writes one down, listed by the switch in General, read, and continued as a chat.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_harness_sessions.py`.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sqlite3
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect
from textual.widgets import OptionList

from hmz.tui.chats import Resumes
from hmz.tui.dropdown import Dropdown
from hmz.tui.settings import Adjusts
from tests.integration.doubles_tui import on, onto, opens, shows, typed, wrapped
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    import pytest
    from playwright.sync_api import Locator, Page

    from tests.system.docs.conftest import World

_CHAT = "Add a discount code to checkout"
_CLAUDE = "5f0c2a7e-91b4-4c3d-8a6e-2d1f7b9c4e10"
_CODEX = "019a3c5e-7d42-7b10-9f6a-3e8c1d5b2a47"
_OPENCODE = "ses_6b1e9d3fa2c4"

_SHIPPING = "Make the cart total include shipping"
_TESTS = "Write tests for the catalogue prices"
_RENAME = "Rename the poster to print"
_MORE = "Make shipping free over 50 dollars"

_DID = (
    "total() now adds a flat 500 cents of shipping to any cart that holds something."
    " An empty cart still comes to 0. I added a test for each case, and all three pass."
)
_FREE = (
    "Done. total() leaves shipping off once the items come to 5000 cents or more."
    " One more test covers it, and all four pass."
)


def _ago(hours: float) -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours)


def _written(log: Path, rows: list[dict[str, Any]], hours: float) -> None:
    """Writes one log a line a record, last written some hours ago."""
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps(one) + "\n" for one in rows))
    at = _ago(hours).timestamp()
    os.utime(log, (at, at))


def _claude_session(world: World, hours: float = 3) -> Path:
    """A session Claude Code had of its own in the project, as it logs one."""
    here = str(world.workspace.resolve())
    began = _ago(hours + 0.1)

    def at(seconds: float) -> str:
        return (began + datetime.timedelta(seconds=seconds)).isoformat()

    def said(seconds: float, ident: str, *blocks: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "assistant",
            "cwd": here,
            "sessionId": _CLAUDE,
            "timestamp": at(seconds),
            "message": {
                "id": ident,
                "model": MODEL,
                "role": "assistant",
                "content": list(blocks),
                "usage": {"input_tokens": 3100, "output_tokens": 180},
            },
        }

    def used(ident: str, name: str, **given: str) -> dict[str, Any]:
        return {"type": "tool_use", "id": ident, "name": name, "input": given}

    def answered(seconds: float, ident: str, result: str) -> dict[str, Any]:
        return {
            "type": "user",
            "cwd": here,
            "sessionId": _CLAUDE,
            "timestamp": at(seconds),
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": ident, "content": result}
                ],
            },
        }

    rows = [
        {
            "type": "user",
            "cwd": here,
            "sessionId": _CLAUDE,
            "timestamp": at(0),
            "message": {"role": "user", "content": _SHIPPING},
        },
        said(4, "msg_1", used("t1", "Read", file_path="shop/cart.py")),
        answered(5, "t1", "def total(items): ..."),
        said(11, "msg_2", used("t2", "Edit", file_path="shop/cart.py")),
        answered(12, "t2", "edited"),
        said(16, "msg_3", used("t3", "Bash", command="pytest -q")),
        answered(18, "t3", "3 passed in 0.18s"),
        said(24, "msg_4", {"type": "text", "text": _DID}),
    ]
    log = (
        world.home
        / ".claude"
        / "projects"
        / re.sub(r"[^a-zA-Z0-9]", "-", here)
        / f"{_CLAUDE}.jsonl"
    )
    _written(log, rows, hours)
    return log


def _stub(name: str) -> None:
    """A CLI that is only a name on PATH: installed, as far as its sessions are listed."""
    at = Path(os.environ["PATH"].split(os.pathsep)[0]) / name
    at.write_text("#!/bin/sh\n")
    at.chmod(0o755)


def _codex_session(
    world: World, monkeypatch: pytest.MonkeyPatch, hours: float = 26
) -> None:
    """A session Codex had of its own in the project, as it writes a rollout."""
    _stub("codex")
    monkeypatch.setenv("CODEX_HOME", str(world.home / ".codex"))
    here = str(world.workspace.resolve())
    began = _ago(hours + 0.1)
    rows = [
        {
            "timestamp": began.isoformat(),
            "type": "session_meta",
            "payload": {"id": _CODEX, "cwd": here, "timestamp": began.isoformat()},
        },
        {
            "timestamp": began.isoformat(),
            "type": "turn_context",
            "payload": {"cwd": here, "model": "gpt-5.2-codex"},
        },
        {
            "timestamp": began.isoformat(),
            "type": "event_msg",
            "payload": {"type": "user_message", "message": _TESTS},
        },
    ]
    log = (
        world.home
        / ".codex"
        / "sessions"
        / f"{began:%Y/%m/%d}"
        / f"rollout-{began:%Y-%m-%dT%H-%M-%S}-{_CODEX}.jsonl"
    )
    _written(log, rows, hours)


def _opencode_session(
    world: World, monkeypatch: pytest.MonkeyPatch, hours: float = 50
) -> None:
    """A session OpenCode had of its own in the project, in the database it keeps."""
    _stub("opencode")
    monkeypatch.setenv("XDG_DATA_HOME", str(world.home / ".local" / "share"))
    store = world.home / ".local" / "share" / "opencode" / "opencode.db"
    store.parent.mkdir(parents=True)
    began = int(_ago(hours + 0.1).timestamp() * 1000)
    ended = int(_ago(hours).timestamp() * 1000)
    with sqlite3.connect(store) as rows:
        rows.execute(
            "create table session (id, parent_id, directory, title, time_created, "
            "time_updated)"
        )
        rows.execute(
            "create table message (id, session_id, time_created, time_updated, data)"
        )
        rows.execute(
            "create table part (id, message_id, session_id, time_created, data)"
        )
        rows.execute(
            "insert into session values (?, null, ?, ?, ?, ?)",
            (_OPENCODE, str(world.workspace.resolve()), _RENAME, began, ended),
        )
        rows.execute(
            "insert into message values ('m1', ?, ?, ?, ?)",
            (_OPENCODE, began, began, json.dumps({"role": "user"})),
        )
        rows.execute(
            "insert into part values ('p1', 'm1', ?, ?, ?)",
            (_OPENCODE, began, json.dumps({"type": "text", "text": _RENAME})),
        )
    rows.close()


def _staged(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """A chat of Humanize's own, and a session each of three CLIs, in the project."""
    world.says(
        {"discount": "Checkout takes a discount code now: WELCOME10 is 10% off."}
    )
    world.chat(_CHAT)
    _claude_session(world)
    _codex_session(world, monkeypatch)
    _opencode_session(world, monkeypatch)


def _session(world: World, harness: str, ident: str) -> str:
    workspace = urllib.parse.quote(str(world.workspace.resolve()), safe="")
    return f"/harness/{harness}/{ident}?workspace={workspace}"


def _rows(page: Page) -> Locator:
    return page.locator("[data-hmz=sidebar] [data-hmz=harness-session]")


def test_the_switch_in_general_lists_them(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staged(world, monkeypatch)
    with world.page(desktop=True) as page:
        go(page, "/settings/general")
        box = page.get_by_role("checkbox", name="List in sidebar")
        expect(box).to_be_visible()
        expect(_rows(page)).to_have_count(0)
        reel = shots.Reel("user-harness-sessions-switch", window="desktop")
        reel.web(page, hold=1.6, pointer=box, click=True)
        box.check()
        save = page.get_by_role("button", name="Save", exact=True)
        reel.web(page, hold=1.0, pointer=save, click=True)
        save.click()
        expect(page.get_by_role("button", name="Saved", exact=True)).to_be_visible()
        expect(_rows(page)).to_have_count(3)
        close = page.get_by_role("button", name="Close", exact=True)
        reel.web(page, hold=1.2, pointer=close, click=True)
        close.click()
        expect(box).to_be_hidden()
        reel.web(
            page,
            hold=4,
            pointer=_rows(page).first,
            poster=True,
            caption="listed after the folder's chats",
        )
        reel.save()


def test_one_is_read_and_continued_in_a_chat(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staged(world, monkeypatch)
    world.says({"free": _FREE})
    world.call("settings.set", harness_sessions=True)
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        expect(_rows(page)).to_have_count(3)
        row = _rows(page).filter(has_text=_SHIPPING)

        reel = shots.Reel("user-harness-sessions-continue", window="desktop")
        reel.web(page, hold=1.5, pointer=row, click=True)
        row.click()
        note = page.locator("[data-hmz=harness-note]")
        expect(note).to_contain_text("Continuing copies it into a chat here")
        expect(page.get_by_role("log")).to_contain_text("flat 500 cents")
        shots.web(page, "user-harness-sessions-read", window="desktop")
        adopt = page.get_by_role("button", name="Continue in chat")
        reel.web(page, hold=2.2, pointer=adopt, click=True, caption="read-only")
        adopt.click()
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        box = page.get_by_role("textbox", name="What to say")
        expect(box).to_be_visible()
        expect(_rows(page)).to_have_count(2)
        reel.web(page, hold=1.6, pointer=box, click=True, caption="a copy, now a chat")
        reel.type(page, box, _MORE, per=12)
        box.press("Enter")
        expect(page.get_by_role("log")).to_contain_text("all four pass")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_a_row_has_a_menu_and_some_are_only_read(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staged(world, monkeypatch)
    world.call("settings.set", harness_sessions=True)
    with world.page(desktop=True) as page:
        go(page, _session(world, "opencode", _OPENCODE))
        note = page.locator("[data-hmz=harness-note]")
        expect(note).to_have_text(
            "Read-only. A session of OpenCode cannot be continued in a chat."
        )
        expect(_rows(page)).to_have_count(3)
        shots.web(page, "user-harness-sessions-read-only", window="desktop")

        go(page, "/new/chat")
        row = _rows(page).filter(has_text=_TESTS)
        row.click(button="right")
        menu = page.get_by_role("menu")
        expect(menu).to_contain_text("Copy session ID")
        shots.web(page, "user-harness-sessions-menu", window="desktop")


async def test_the_switch_in_the_terminal(world: World) -> None:
    async with world.tui((96, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings general")
        await on(pilot, Adjusts)
        await wrapped(pilot, "Harness sessions", "to continue as chats")
        await opens(pilot, "harness_sessions")
        dropped = await on(pilot, Dropdown)
        listing = dropped.query_one(OptionList)
        for _ in range(3):
            if listing.highlighted == 0:
                break
            await pilot.press("up")
            await pilot.pause()
        assert listing.highlighted == 0
        shots.tui(app, "user-harness-sessions-terminal-switch")


async def test_resume_lists_them_in_the_terminal(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _staged(world, monkeypatch)
    world.says({"free": {"text": _FREE, "after": 0.5}})
    world.call("settings.set", harness_sessions=True)
    async with world.tui((100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel("user-harness-sessions-resume")
        await pilot.press(*"/resume")
        await pilot.pause()
        reel.tui(app, hold=1.2, keys="/resume")
        await pilot.press("enter")
        await on(pilot, Resumes)
        await shows(pilot, _SHIPPING, "claude session, read-only")
        shots.tui(app, "user-harness-sessions-resume-list")
        reel.tui(app, hold=2.4, keys="enter")
        await onto(pilot, f"harness:claude:{_CLAUDE}")
        await pilot.pause()
        reel.tui(app, hold=1.6, keys="down", caption="to the Claude Code session")
        await pilot.press("enter")
        await shows(pilot, "Say something to continue")
        reel.tui(app, hold=1.8, keys="enter", caption="a copy, now a chat")
        await pilot.press(*_MORE)
        await pilot.pause()
        reel.tui(app, hold=1.0)
        await pilot.press("enter")
        await shows(pilot, "all four pass")
        reel.tui(app, hold=4, keys="enter", poster=True)
        reel.save()
