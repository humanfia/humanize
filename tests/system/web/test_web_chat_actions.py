"""What is done to a chat besides talking in it, on the page, in a real browser.

A chat is renamed where its title stands -- on its bar and in its row of the sidebar -- forked,
archived and put back, and deleted once a dialog has asked; what the daemon refuses is said in
its own words. The archived chats of a workspace are listed in its settings. A new chat is
started in a git worktree where its folder is in a repository. The chats are real ones, of the
stand-in `claude`, on a real daemon. A session a harness had of its own is offered `Continue in
chat` only where its harness carries a copy of one on.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
import urllib.parse
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_web import Browser, served
from tests.system.web.doubles_browser import ENGINES, Wire, go, opened, stop

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from hmz.web.site import Site

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A window as wide as a desk's, and one as narrow as a phone's.
_WIDTHS = [1280, 390]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, asked what it runs, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    (tmp_path / "home").mkdir(exist_ok=True)
    # Where the stand-in keeps what it was started with, before any page has asked it.
    (tmp_path / "claude").mkdir(exist_ok=True)
    return project


def _call(page: Page, method: str, params: dict[str, Any] | None = None) -> Any:
    """Calls one method of the daemon shown, as the page's own script does."""
    return page.evaluate(
        """async ([method, params]) => (await import('/api.js')).call(method, params)""",
        [method, params or {}],
    )


def _chatted(site: Site, task: str, *, stopped: bool = True) -> str:
    """A chat that said one thing and, unless asked otherwise, rests; its id.

    Started as a page starts one (`chat.start`, Section 4.25 of protocol/daemon.md), and
    waited for until its first turn is over.
    """
    browser = Browser(site)
    browser.signs_in()
    with browser.session() as page:
        started = page.call(
            "chat.start",
            workspace=str(site.here),
            slot="chat:",
            agent=AGENT,
            task=task,
            # With nothing to fence it in, so that its turns are taken wherever this runs.
            permission="danger-full-access",
            idem=uuid.uuid4().hex,
        )
        chat = str(started["chat"])
        until = time.monotonic() + 60
        while (state := page.call("chat.get", chat=chat)["state"]) != "going":
            assert state != "failed", "the chat's first turn failed"
            assert time.monotonic() < until, state
            time.sleep(0.1)
        if stopped:
            # A chat is never ended: its host goes, and the chat rests.
            page.call(
                "hosts.stop",
                workspace=str(site.here),
                slot=started["slot"],
                idem=uuid.uuid4().hex,
            )
            while page.call("chat.get", chat=chat)["slot"]:
                time.sleep(0.1)
        return chat


def _rows(page: Page) -> Locator:
    """The chats the sidebar lists."""
    return page.locator("[data-hmz=sidebar] [data-hmz=epic]")


def _sidebar(page: Page, width: int) -> None:
    """Brings the sidebar up where it is a drawer."""
    if width < 860 and not page.locator(".app.side-open").count():
        page.locator("[data-hmz=bar] .bar-side").click()
    expect(_rows(page).first).to_be_visible()


def _bar_menu(page: Page) -> Locator:
    """Opens the menu of the chat's bar."""
    page.locator("[data-hmz=bar] [data-hmz=chat-menu]").click()
    menu = page.get_by_role("menu", name="Chat menu")
    expect(menu).to_be_visible()
    return menu


def _title(page: Page) -> Locator:
    return page.locator("[data-hmz=bar] [data-hmz=chat-title]")


@pytest.mark.parametrize("width", _WIDTHS)
def test_a_chat_is_renamed_where_its_title_stands(
    project: Path, engine: str, width: int
) -> None:
    with served() as site:
        name = _chatted(site, "first thing")
        with opened(site, engine=engine, width=width, height=800) as page:
            go(page, f"/chats/{name}")
            title = _title(page)
            expect(title).to_have_text("first thing")
            expect(title).to_have_attribute("aria-label", "first thing, rename")

            # Pressed, the title is a field holding it; Escape leaves it as it was.
            more = page.locator("[data-hmz=bar] [data-hmz=chat-menu]")
            more_at = more.bounding_box()
            title.click()
            field = page.locator("[data-hmz=bar] [data-hmz=title-edit]")
            expect(field).to_be_focused()
            expect(field).to_have_value("first thing")
            # The field lies over the title, which keeps its room: the menu's button after
            # it is not thrown aside, to be pressed where it no longer is.
            assert more_at is not None
            assert more.bounding_box() == more_at
            field.fill("never kept")
            field.press("Escape")
            expect(field).to_have_count(0)
            expect(title).to_have_text("first thing")
            expect(title).to_be_focused()

            # One menu at a time. A right-click in the bar's menu is that menu's own:
            # the title's menu does not open over it.
            menu = _bar_menu(page)
            menu.get_by_role("menuitem", name="Copy link").click(button="right")
            expect(page.locator(".popover.context")).to_have_count(0)
            expect(menu).to_be_visible()
            expect(page.get_by_role("menu")).to_have_count(1)
            # The focus gone to another button, the menu closes; that button's menu,
            # opened by a key, is the only one, and Escape gives its button the focus.
            view = page.locator("[data-hmz=bar] [data-hmz=chat-view]")
            view.focus()
            expect(menu).to_have_count(0)
            page.keyboard.press("Enter")
            expect(page.get_by_role("menu", name="View options")).to_be_visible()
            expect(page.get_by_role("menu")).to_have_count(1)
            page.keyboard.press("Escape")
            expect(page.get_by_role("menu")).to_have_count(0)
            expect(view).to_be_focused()
            if width >= 860:
                # A tip never stands over the menu its own button opened.
                more.hover()
                tip = page.locator(".tip")
                expect(tip).to_have_text("More options")
                more.click()
                page.mouse.move(more_at["x"] + 9, more_at["y"] + 9)
                page.wait_for_timeout(400)
                expect(tip).to_have_count(0)
                expect(page.get_by_role("menu", name="Chat menu")).to_be_visible()
                page.keyboard.press("Escape")

            # Enter saves it, and its row in the sidebar follows.
            title.click()
            field.fill("  Renamed   on the bar ")
            field.press("Enter")
            expect(title).to_have_text("Renamed on the bar")
            assert _call(page, "chat.get", {"chat": name})["title"] == (
                "Renamed on the bar"
            )
            _sidebar(page, width)
            row = _rows(page)
            expect(row.locator(".side-label")).to_have_text("Renamed on the bar")

            # Its row's menu holds what a chat app's does, in its order, and renames it
            # in the row.
            row.click(button="right")
            menu = page.locator(".popover.context")
            labels = menu.get_by_role("menuitem").all_inner_texts()
            for kept in (
                "Open",
                "Pin",
                "Mark as unread",
                "New chat like it",
                "Copy link",
                "Copy first message",
                "Copy ID",
                "Upload",
            ):
                assert kept in labels, labels
            acts = [
                labels.index(one) for one in ("Rename", "Fork", "Archive", "Delete")
            ]
            assert acts == sorted(acts)
            assert labels[-2:] == ["Archive", "Delete"]
            menu.get_by_role("menuitem", name="Rename").click()
            inline = page.locator("[data-hmz=sidebar] [data-hmz=title-edit]")
            expect(inline).to_be_focused()
            inline.fill("Renamed in its row")
            # The list read again meanwhile leaves the field as it is.
            page.wait_for_timeout(4500)
            expect(inline).to_have_value("Renamed in its row")
            inline.press("Enter")
            expect(inline).to_have_count(0)
            expect(_rows(page).locator(".side-label")).to_have_text(
                "Renamed in its row"
            )
            expect(title).to_have_text("Renamed in its row")


@pytest.mark.parametrize("width", _WIDTHS)
def test_a_chat_is_forked_archived_put_back_and_deleted(
    project: Path, engine: str, width: int
) -> None:
    with served() as site:
        name = _chatted(site, "first thing")
        with opened(site, engine=engine, width=width, height=800) as page:
            go(page, f"/chats/{name}")
            expect(_title(page)).to_have_text("first thing")

            # Forked from its bar's menu, the fork is opened: a chat of its own.
            _bar_menu(page).get_by_role("menuitem", name="Fork").click()
            page.wait_for_url(
                lambda url: "#/chats/" in url and not url.endswith(f"#/chats/{name}")
            )
            fork = urllib.parse.unquote(page.url.split("#/chats/")[1])
            assert _call(page, "chat.get", {"chat": fork})["forked"] == name
            expect(_title(page)).to_have_text("first thing")
            _sidebar(page, width)
            expect(_rows(page)).to_have_count(2)
            if width < 860:
                page.keyboard.press("Escape")

            # Archived, it leaves the sidebar; still open, its bar offers to put it back.
            _bar_menu(page).get_by_role("menuitem", name="Archive", exact=True).click()
            unarchive = page.locator("[data-hmz=bar] [data-hmz=chat-unarchive]")
            # A narrow page leaves it to the menu, where the title needs the room.
            expect(unarchive).to_be_visible(visible=width >= 860)
            expect(_rows(page)).to_have_count(1)
            expect(_rows(page)).to_have_attribute("href", f"#/chats/{name}")
            # Its menu says the same.
            menu = _bar_menu(page)
            expect(menu.get_by_role("menuitem", name="Unarchive")).to_be_visible()
            expect(
                menu.get_by_role("menuitem", name="Archive", exact=True)
            ).to_have_count(0)
            page.keyboard.press("Escape")

            # The workspace's settings list it among the archived, and put it back.
            go(page, "/settings/workspace")
            archived = page.locator("[data-hmz=archived-chats]")
            expect(archived.locator("h2")).to_have_text("Archived chats")
            listed = archived.locator("[data-hmz=archived-chat]")
            expect(listed).to_have_count(1)
            expect(listed).to_have_attribute("data-chat", fork)
            expect(listed.locator(".archived-title")).to_have_text("first thing")
            listed.get_by_role("button", name="Unarchive").click()
            expect(listed).to_have_count(0)
            expect(archived).to_contain_text("None")
            assert not _call(page, "chat.get", {"chat": fork})["archived"]
            page.keyboard.press("Escape")
            expect(page.locator("[data-hmz=dialog-settings]")).to_have_count(0)
            expect(unarchive).to_have_count(0)
            expect(_rows(page)).to_have_count(2)

            # Deleting asks first, in a dialog that says what goes and what stays.
            _bar_menu(page).get_by_role("menuitem", name="Delete").click()
            dialog = page.locator("[data-hmz=dialog-delete]")
            expect(dialog).to_be_visible()
            expect(dialog.locator("[data-hmz=delete-title]")).to_have_text(
                "first thing"
            )
            expect(dialog).to_contain_text(
                re.compile("permanently removes.*cannot be undone.*left on disk")
            )
            cancel = dialog.locator("[data-hmz=delete-cancel]")
            expect(cancel).to_be_focused()
            cancel.click()
            expect(dialog).to_have_count(0)
            assert page.url.endswith(f"#/chats/{fork}")
            assert _call(page, "chat.get", {"chat": fork})["id"] == fork

            # Confirmed, the chat is gone and a new chat stands in its place.
            _bar_menu(page).get_by_role("menuitem", name="Delete").click()
            dialog.locator("[data-hmz=delete-confirm]").click()
            page.wait_for_url(re.compile(r".*#/new/chat"))
            expect(dialog).to_have_count(0)
            expect(page.locator("div[data-hmz=new-chat]")).to_be_visible()
            assert [one["id"] for one in _call(page, "chat.list")["chats"]] == [name]
            _sidebar(page, width)
            expect(_rows(page)).to_have_count(1)

            # An archived chat is deleted from the settings, asked the same way, and
            # the settings stand again once it is.
            _call(page, "chat.archive", {"chat": name})
            if width < 860:
                page.keyboard.press("Escape")
            go(page, "/settings/workspace")
            expect(listed).to_have_count(1)
            listed.locator("[data-hmz=archived-delete]").click()
            expect(dialog.locator("[data-hmz=delete-title]")).to_have_text(
                "first thing"
            )
            # Escape closes it alone: the settings it was opened over stand again.
            page.keyboard.press("Escape")
            expect(dialog).to_have_count(0)
            expect(page.locator("[data-hmz=dialog-settings]")).to_be_visible()
            expect(listed).to_have_count(1)
            listed.locator("[data-hmz=archived-delete]").click()
            dialog.locator("[data-hmz=delete-confirm]").click()
            expect(dialog).to_have_count(0)
            expect(page.locator("[data-hmz=dialog-settings]")).to_be_visible()
            expect(archived).to_contain_text("None")
            assert _call(page, "chat.list", {"archived": True})["chats"] == []


def test_what_the_daemon_refuses_of_a_chat_going_is_said_in_its_words(
    project: Path, engine: str
) -> None:
    with served() as site:
        name = _chatted(site, "still going", stopped=False)
        with opened(site, engine=engine, width=1280, height=800) as page:
            go(page, f"/chats/{name}")
            expect(_title(page)).to_have_text("still going")
            _bar_menu(page).get_by_role("menuitem", name="Delete").click()
            dialog = page.locator("[data-hmz=dialog-delete]")
            dialog.locator("[data-hmz=delete-confirm]").click()
            expect(dialog.locator(".delete-said")).to_have_text(
                f"Chat {name} is going on; delete it once it rests."
            )
            # The chat stays, and so does the dialog, to be cancelled.
            dialog.locator("[data-hmz=delete-cancel]").click()
            expect(dialog).to_have_count(0)
            assert _call(page, "chat.get", {"chat": name})["id"] == name
            stop(page)


def _git(at: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *argv],
        cwd=at,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
    )


@pytest.mark.parametrize("width", _WIDTHS)
def test_a_new_chat_is_started_in_a_worktree_of_a_repository(
    project: Path, engine: str, width: int
) -> None:
    with served() as site, opened(site, engine=engine, width=width, height=800) as page:
        # A folder in no repository offers no worktree, and says why.
        go(page, "/new/chat")
        box = page.locator("[data-hmz=new-worktree]")
        label = page.locator("[data-hmz=start] .desk-check")
        expect(label).to_have_text("Worktree")
        expect(box).to_be_disabled()
        expect(label).to_have_attribute(
            "data-tip", "This folder is not a git repository"
        )
        # After the folder, in the row's left group.
        assert label.evaluate(
            "(el) => el.previousElementSibling.matches('.menu-holder, .flow-picker')"
            " || Boolean(el.previousElementSibling.querySelector('[data-hmz=workspace-picker]'))"
        )

        # Nor does no folder.
        go(page, "/new/chat?scratch=1")
        expect(box).to_be_disabled()
        expect(label).to_have_attribute("data-tip", "A worktree needs a folder")

        # In a repository it is on offer; ticked, the chat works in a worktree of it.
        _git(project, "init", "-q")
        (project / "kept.txt").write_text("kept\n")
        _git(project, "add", ".")
        _git(project, "commit", "-q", "-m", "first")
        go(page, f"/new/chat?workspace={urllib.parse.quote(str(project))}")
        expect(box).to_be_enabled()
        expect(box).not_to_be_checked()
        label.click()
        expect(box).to_be_checked()
        expect(
            page.locator("[data-role=assistant] [data-hmz=pick-model]")
        ).to_have_attribute("data-value", "claude-haiku-4-5")
        # With nothing to fence it in, so that its turn is taken wherever this runs.
        page.locator("[data-hmz=start] [data-hmz=permission]").click()
        page.get_by_role("menu", name="Permissions").locator(
            "[data-permission=danger-full-access]"
        ).click()
        page.locator("[data-hmz=composer-text]").fill("in a worktree")
        page.locator("[data-hmz=composer-text]").press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        name = urllib.parse.unquote(page.url.split("#/chats/")[1])
        chat = _call(page, "chat.get", {"chat": name})
        assert chat["workspace"] == str(project)
        assert chat["workdir"] != chat["workspace"]

        # Its Details say where it works, beside its folder.
        page.locator("[data-hmz=bar] [data-hmz=pane-details]").click()
        works = page.locator("[data-hmz=inspector] [data-hmz=chat-workdir]")
        expect(works.locator(".path")).to_have_attribute("data-path", chat["workdir"])
        expect(page.locator("[data-hmz=inspector] dt")).to_contain_text(["Works in"])
        stop(page)


def test_a_chat_a_backup_target_holds_is_opened_and_downloaded_as_a_chat(
    project: Path, engine: str
) -> None:
    import yaml

    from hmz import home

    target: dict[str, Any] = {
        "name": "t",
        "url": str(project / "nowhere.git"),
        "policies": [],
    }
    (home() / "settings.yaml").write_text(
        yaml.safe_dump({"backup": {"targets": [target], "defaults": []}})
    )

    def stored(name: str, *, here: bool) -> dict[str, Any]:
        return {
            "key": f"m/w/{name}",
            "machine": "m",
            "workspace": str(project),
            "epic": name,
            "flow": "",
            "task": name,
            "began": "2026-01-01T00:00:00Z",
            "how": "stopped",
            "chat": True,
            "here": here,
        }

    wire = Wire(
        faked={
            "backups.epics": lambda _: {
                "result": {
                    "epics": [stored("kept", here=True), stored("away", here=False)]
                }
            },
            "backups.pull": lambda _: {"result": {"name": "away"}},
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/download")
        kept = page.locator("[data-hmz=stored-epic][data-epic=kept]")
        # Said as a chat, and opened among the chats.
        expect(kept).to_contain_text("chat")
        expect(kept.get_by_role("link", name="Open")).to_have_attribute(
            "href", "#/chats/kept"
        )
        away = page.locator("[data-hmz=stored-epic][data-epic=away]")
        away.get_by_role("button", name="Download").click()
        page.wait_for_url(re.compile(r".*#/chats/away$"))


def test_a_harness_session_is_offered_a_chat_only_where_its_harness_carries_one_on(
    project: Path, engine: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.settings import Settings

    here = str(project.resolve())
    # One the stand-in `claude` had of its own, as it logs one: carried on from a copy.
    plain = "".join(one if one.isalnum() else "-" for one in here)
    log = (
        tmp_path
        / "claude"
        / "projects"
        / plain
        / "c0c0c0c0-1111-4222-8333-444444444444"
    )
    log.parent.mkdir(parents=True)
    log.with_suffix(".jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "cwd": here,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "message": {"role": "user", "content": "the word is guava"},
            }
        )
        + "\n"
    )
    # And one of an `opencode` that is only a name on PATH, in the database it keeps every
    # session in: listed and read, and carried on by nothing.
    stub = tmp_path / "bin" / "opencode"
    stub.write_text("#!/bin/sh\n")
    stub.chmod(0o755)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    store = tmp_path / "share" / "opencode" / "opencode.db"
    store.parent.mkdir(parents=True)
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
            "insert into session values ('ses_1', null, ?, 'The word is plum', 1000, 2000)",
            (here,),
        )
        rows.execute(
            "insert into message values ('m1', 'ses_1', 1000, 1000, ?)",
            (json.dumps({"role": "user"}),),
        )
        rows.execute(
            "insert into part values ('p1', 'm1', 'ses_1', 1000, ?)",
            (json.dumps({"type": "text", "text": "the word is plum"}),),
        )
    rows.close()
    before = store.read_bytes()
    Settings().harness_sessions = True
    workspace = urllib.parse.quote(here, safe="")

    with served() as site, opened(site, engine=engine, width=1280, height=800) as page:
        listed = page.locator("[data-hmz=sidebar] [data-hmz=harness-session]")
        expect(listed).to_have_count(2)
        note = page.locator("[data-hmz=harness-note]")
        adopt = page.locator("[data-hmz=harness-adopt]")

        go(page, f"/harness/opencode/ses_1?workspace={workspace}")
        expect(page.locator("[data-hmz=thread]")).to_contain_text("the word is plum")
        expect(note).to_have_text(
            "Read-only. A session of opencode cannot be continued in a chat."
        )
        expect(adopt).to_have_count(0)
        refused = page.evaluate(
            """async (named) => (await import('/api.js')).call('chat.harness.adopt', named)
                .then(() => '', (error) => error.message)""",
            {"workspace": here, "harness": "opencode", "session": "ses_1"},
        )
        assert refused == "A session of opencode cannot be continued in a chat."

        go(page, f"/harness/claude/{log.name}?workspace={workspace}")
        expect(note).to_contain_text("Continuing copies it into a chat here")
        expect(adopt).to_be_visible()
    assert store.read_bytes() == before
