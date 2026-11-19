"""What is done to a chat besides talking in it, on the page, in a real browser.

A chat is renamed where its title stands -- on its bar and in its row of the sidebar -- forked,
archived and put back, and deleted once a dialog has asked; what the daemon refuses is said in
its own words. The archived chats of a workspace are listed in its settings. A new chat is
started in a git worktree where its folder is in a repository. The chats are real ones, of the
stand-in `claude`, on a real daemon.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.parse
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import AGENT, install
from tests.integration.doubles_web import Browser, served
from tests.system.web.doubles_browser import ENGINES, go, opened, stop

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
            title.click()
            field = page.locator("[data-hmz=bar] [data-hmz=title-edit]")
            expect(field).to_be_focused()
            expect(field).to_have_value("first thing")
            field.fill("never kept")
            field.press("Escape")
            expect(field).to_have_count(0)
            expect(title).to_have_text("first thing")
            expect(title).to_be_focused()

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
            expect(unarchive).to_be_visible()
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
