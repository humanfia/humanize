"""`hmz web`'s Daemons, Notifications, Usage and Accounts settings pages, driven in a browser.

The page is the real one, served in the test's own process. The daemons and the notification
settings are this browser's own, kept in its IndexedDB, and read back from there; what the page
asks of Local goes over `/rpc`, where a test holds a call back, or answers it itself, to see
what the page shows meanwhile. Each test runs in Chromium and in WebKit.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any

import pytest
from playwright.sync_api import expect

from tests.integration.doubles_core import install
from tests.integration.doubles_web import served
from tests.system.web.doubles_browser import ENGINES, Wire, go, kept, opened

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Page

pytestmark = [
    pytest.mark.parametrize("engine", ENGINES),
    pytest.mark.usefixtures("daemon"),
]

#: A daemon kept, pinned, that nothing answers where it is reached.
_BOX = {"name": "box", "id": "a" * 52, "routes": ["tcp://127.0.0.1:9"]}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve."""
    project = install(tmp_path, monkeypatch)
    # The home it gives the CLI is this machine's home, which the daemon's own settings are of.
    (tmp_path / "home").mkdir(exist_ok=True)
    return project


def _kept(page: Page) -> list[dict[str, Any]]:
    """Every remote daemon this browser keeps."""
    return page.evaluate("async () => (await import('/api.js')).daemons.list()")


def test_a_daemon_is_added_a_part_at_a_time(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/daemons")
        rows = page.locator("[data-hmz=daemon]")
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text("Local")
        expect(rows.first.get_by_role("button", name="Remove")).to_have_count(0)
        form = page.locator("[data-hmz=write-daemon]")
        form.get_by_label("Name").fill("lab")
        form.locator("[data-hmz=daemon-kind]").get_by_role("button", name="SSH").click()
        form.get_by_role("button", name="Custom").click()
        form.locator("#daemon-host").fill("lab.example")
        form.locator("#daemon-user").fill("ann")
        form.locator("#daemon-port").fill("2222")
        form.locator("#daemon-identity").fill("~/.ssh/lab")
        form.locator("#daemon-jump").fill("me@jump")
        options = form.locator(".list-editor", has=page.locator("#daemon-options"))
        options.get_by_role("button", name="Add", exact=True).click()
        options.locator(".pair-key").fill("ServerAliveInterval")
        options.locator(".pair-value").fill("30")
        form.get_by_role("button", name="Add", exact=True).last.click()
        expect(rows).to_have_count(2)
        row = page.locator("[data-hmz=daemon][data-name=lab]")
        expect(row).to_contain_text("ann@lab.example:2222")
        ((saved),) = _kept(page)
        assert saved["name"] == "lab"
        assert saved["routes"] == [
            (
                "stdio:ssh://ann@lab.example:2222?identity=~%2F.ssh%2Flab&jump=me%40jump"
                "&option=ServerAliveInterval%3D30"
            )
        ]


def test_a_daemon_is_removed_once_confirmed(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine) as page:
        kept(page, _BOX)
        go(page, "/settings/daemons")
        row = page.locator("[data-hmz=daemon][data-name=box]")
        # Local's devices, listed over it, are read: nothing over it is still to be drawn.
        expect(
            page.locator("[data-hmz=daemon-devices][data-name=local] .loading")
        ).to_have_count(0)
        # Its button stays as it is, and asks by itself: nothing beside it moves.
        remove = row.locator("button[aria-haspopup=dialog]")
        expect(remove).to_have_text("Remove")
        asked = page.get_by_role("dialog", name="Remove box?")
        before = remove.bounding_box()
        remove.click()
        expect(asked.get_by_role("button", name="Cancel")).to_be_focused()
        expect(remove).to_have_attribute("aria-expanded", "true")
        assert remove.bounding_box() == before
        assert _kept(page) == [_BOX]
        asked.get_by_role("button", name="Cancel").click()
        expect(asked).to_have_count(0)
        expect(remove).to_have_attribute("aria-expanded", "false")

        # Escape takes the question back, and that alone: Settings stays, on the button.
        remove.click()
        expect(asked).to_be_visible()
        page.keyboard.press("Escape")
        expect(asked).to_have_count(0)
        expect(remove).to_be_focused()
        expect(page.locator("[data-hmz=settings-daemons]")).to_be_visible()
        assert _kept(page) == [_BOX]

        # It is the one thing that floats, and a press elsewhere takes it back unanswered.
        remove.click()
        expect(asked).to_be_visible()
        expect(page.locator(".popover:visible")).to_have_count(1)
        page.locator("[data-hmz=write-daemon] [data-hmz=daemon-kind]").get_by_role(
            "button", name="SSH"
        ).click()
        expect(asked).to_have_count(0)
        assert _kept(page) == [_BOX]

        remove.click()
        asked.get_by_role("button", name="Remove").click()
        expect(row).to_have_count(0)
        assert _kept(page) == []


def test_a_refused_connection_is_said_where_it_happened(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine) as page:
        kept(page, _BOX)
        go(page, "/settings/daemons")
        row = page.locator("[data-hmz=daemon][data-name=box]")
        row.get_by_role("button", name="Connect").click()
        state = row.locator("[data-hmz=daemon-state]")
        expect(state).to_contain_text("failed")
        expect(state.locator(".daemon-detail")).to_contain_text("refused")


#: The browser's notifications, as a page that was never asked sees them, granting when asked.
_NOTIFICATION = """
window.Notification = class { constructor() {} }
window.Notification.permission = 'default'
window.Notification.requestPermission = async () => {
  window.__asked = (window.__asked || 0) + 1
  window.Notification.permission = 'granted'
  return 'granted'
}
"""


def _preferences(page: Page) -> Any:
    """The notification settings this browser keeps."""
    return page.evaluate(
        "async () => (await import('/notifications.js')).kept.preferences()"
    )


def test_notification_kinds_are_saved_as_they_are_toggled(
    project: Path, engine: str
) -> None:
    with served() as site, opened(site, engine=engine, init=_NOTIFICATION) as page:
        page.evaluate(
            """async () => (await import('/notifications.js')).kept.prefer(
                {kinds: {done: true, failed: false}, system: true})"""
        )
        go(page, "/settings/notifications")
        expect(page.locator("[data-hmz=notify-failed]")).not_to_be_checked()
        expect(page.locator("[data-hmz=notify-asked]")).to_be_checked()
        for label in ("Done", "Failed", "Stopped", "Questions", "Waiting"):
            expect(page.get_by_label(label, exact=True)).to_be_visible()
        page.get_by_label("Questions", exact=True).uncheck()
        said = page.locator("[data-hmz=notifications-said]")
        expect(said).to_have_text("Saved")
        kinds = {
            "done": True,
            "failed": False,
            "stopped": True,
            "asked": False,
            "listening": True,
        }
        assert _preferences(page) == {"kinds": kinds, "system": True}
        page.locator("[data-hmz=notify-system]").uncheck()
        expect(said).to_have_text("Saved")
        assert _preferences(page) == {"kinds": kinds, "system": False}


def test_notifications_are_allowed_from_a_click(project: Path, engine: str) -> None:
    with served() as site, opened(site, engine=engine, init=_NOTIFICATION) as page:
        go(page, "/settings/notifications")
        state = page.locator("[data-hmz=permission-state]")
        shown_by = page.locator("[data-hmz=notifications-shown-by]")
        expect(state).to_have_text("Not asked")
        expect(shown_by).to_have_text("Shown by the browser, once you allow it.")
        # From the keyboard: the button goes once answered, and the focus stays in its place.
        page.locator("[data-hmz=allow-notifications]").focus()
        page.keyboard.press("Enter")
        expect(state).to_have_text("Allowed")
        expect(shown_by).to_have_text("Shown by the browser.")
        expect(page.locator("[data-hmz=allow-notifications]")).to_have_count(0)
        expect(state).to_be_focused()
        assert page.evaluate("window.__asked") == 1


def test_what_is_being_read_says_so_until_it_is_answered(
    project: Path, engine: str
) -> None:
    (project.parent / "home" / "keys").mkdir(parents=True)
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/daemons")
        expect(page.locator("[data-hmz=daemon]")).to_have_count(1)

        wire.holds("paths.list")
        form = page.locator("[data-hmz=write-daemon]")
        form.locator("[data-hmz=daemon-kind]").get_by_role("button", name="SSH").click()
        form.get_by_role("button", name="Custom").click()
        form.locator("[data-hmz=path-browse]").click()
        panel = page.get_by_role("dialog", name="Choose Identity file")
        expect(panel.locator(".loading")).to_have_text("Reading…")
        wire.waits(page)
        wire.lets_through()
        expect(panel.locator(".path-list")).to_be_visible()
        wire.holds("paths.list")
        panel.locator(".path-entry", has_text="keys").click()
        expect(panel).to_have_attribute("aria-busy", "true")
        expect(panel.locator(".crumb").last).to_have_text("~")
        wire.waits(page)
        wire.lets_through()
        expect(panel).not_to_have_attribute("aria-busy", "true")
        expect(panel.locator(".crumb").last).to_have_text("keys")


def test_a_range_shown_stays_busy_until_the_next_is_read(
    project: Path, engine: str
) -> None:
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/usage")
        usage = page.locator("[data-hmz=usage]")
        expect(usage.locator(".panel").first).to_be_visible()
        wire.holds("runs.usage")
        page.get_by_role("button", name="7d").click()
        expect(usage).to_have_attribute("aria-busy", "true")
        expect(usage.locator(".panel").first).to_be_visible()
        wire.waits(page)
        assert wire.params("runs.usage")[-1]["days"] == 7
        wire.lets_through()
        expect(usage).not_to_have_attribute("aria-busy", "true")


def test_what_the_chats_spent_is_named_in_the_pages_language(
    project: Path, engine: str
) -> None:
    spent = {"runs": 1, "cost": 0.5, "money": "$0.50", "tokens": "1.2k", "worked": "3m"}
    wire = Wire(
        faked={
            "runs.usage": lambda _: {
                "result": {
                    "days_back": 30,
                    "days": [{"day": "2026-01-01", **spent}],
                    # The chats are summed as of the flow `chat`: a word of the page's.
                    "flows": [{"flow": "chat", **spent}, {"flow": "goal", **spent}],
                    "ended": {"done": 2},
                    "whole": {**spent, "runs": 2},
                }
            }
        }
    )
    with (
        served() as site,
        opened(site, engine=engine, locale="zh-TW", routed=wire.routes) as page,
    ):
        go(page, "/settings/usage")
        named = page.locator("[data-hmz=usage] tbody td:first-child a")
        expect(named).to_have_text(["聊天", "goal"])
        expect(named.first).to_have_attribute("title", "聊天")


def test_a_settings_list_with_nothing_in_it_offers_what_adds_to_it(
    project: Path, engine: str
) -> None:
    """Section 3.4.6 of protocol/web.md: said in place of the list, with the way to its form."""
    with served() as site, opened(site, engine=engine) as page:
        for name, said, button, field in (
            ("backup", "No backup target yet.", "Add target", "#backup-name"),
            ("runtimes", "No other runtime yet.", "Add runtime", "#runtime-name"),
        ):
            go(page, f"/settings/{name}")
            empty = page.locator(f"[data-hmz=settings-{name}] .empty")
            expect(empty.locator("strong")).to_have_text(said)
            # Nothing is written by it: the form under the list takes the keys.
            empty.get_by_role("button", name=button).click()
            expect(page.locator(field)).to_be_focused()
            expect(empty).to_be_visible()
        # Nothing spent yet: a chat is what spends.
        go(page, "/settings/usage")
        none = page.locator("[data-hmz=usage] .empty")
        expect(none.locator("strong")).to_have_text("Nothing ran in this range.")
        expect(none.get_by_role("link", name="New chat")).to_have_attribute(
            "href", "#/new/chat"
        )


def test_an_account_saved_or_made_says_so_until_it_is_answered(
    project: Path, engine: str
) -> None:
    way = {
        "name": "api-key",
        "about": "A key of its own.",
        "terminal": False,
        "asks": [{"env": "KEY", "about": "", "secret": True, "fixed": ""}],
    }
    accounts = {
        "accounts": [
            {
                "cli": "claude",
                "name": "work",
                "way": "api-key",
                "sets": ["KEY"],
                "models": [],
                "asked": None,
                "serves": [],
            }
        ],
        "backends": [{"cli": "claude", "ways": [way], "wants": ""}],
        "gateway": "LiteLLM",
    }
    # What is saved or made is held; what the page reads beside it is answered at once.
    wire = Wire(
        faked={
            "accounts.list": lambda _: {"result": accounts},
            "accounts.correct": lambda _: None,
            "accounts.create": lambda _: None,
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/accounts")
        page.locator("[data-hmz=account]").get_by_role("button", name="Edit").click()
        correct = page.locator("[data-hmz=correct-account]")
        correct.get_by_label("KEY").fill("new")
        correct.get_by_role("button", name="Save").click()
        saving = correct.get_by_role("button", name="Saving…")
        expect(saving).to_be_disabled()
        wire.answer(page, "accounts.correct", accounts)
        expect(saving).to_have_count(0)

        made = page.locator("[data-hmz=make-account]")
        made.get_by_role("button", name="Cancel").click()
        made.get_by_label("Name").fill("home")
        made.get_by_label("KEY").fill("other")
        made.get_by_role("button", name="Create").click()
        creating = made.get_by_role("button", name="Creating…")
        expect(creating).to_be_disabled()
        wire.answer(page, "accounts.create", accounts)
        expect(made.get_by_role("button", name="Create")).to_be_enabled()


def test_what_else_is_done_with_an_account_is_behind_more_options(
    project: Path, engine: str
) -> None:
    one = {
        "cli": "claude",
        "name": "work",
        "way": "api-key",
        "sets": ["KEY"],
        "models": [],
        "asked": None,
        "serves": ["pi"],
    }
    listed = {"accounts": [one], "backends": [], "gateway": "LiteLLM"}
    none = {**listed, "accounts": []}
    wire = Wire(
        faked={
            "accounts.list": lambda _: {"result": listed},
            "accounts.copy": lambda _: {"result": listed},
            "accounts.remove": lambda _: {"result": none},
        }
    )
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        go(page, "/settings/accounts")
        row = page.locator("[data-hmz=account]")
        more = row.get_by_role("button", name="More options")
        more.click()
        menu = page.get_by_role("menu")
        expect(menu.get_by_role("menuitem")).to_have_text(
            ["Refresh models", "Copy to Pi", "Remove"]
        )
        menu.get_by_role("menuitem", name="Copy to Pi").click()
        expect(page.locator(".toast")).to_have_text("Copied to Pi")
        ((copied),) = wire.params("accounts.copy")
        assert copied["into"] == "pi"

        # Removing asks first, in the row, on the safe answer: Escape takes the question back
        # and leaves Settings open.
        more.click()
        page.get_by_role("menuitem", name="Remove").click()
        asked = row.locator("[data-hmz=account-removing]")
        expect(asked).to_contain_text("Remove Claude Code · work, credentials and all?")
        expect(asked.get_by_role("button", name="Cancel")).to_be_focused()
        page.keyboard.press("Escape")
        expect(asked).to_have_count(0)
        expect(more).to_be_focused()
        assert wire.params("accounts.remove") == []

        more.click()
        page.get_by_role("menuitem", name="Remove").click()
        asked.get_by_role("button", name="Remove").click()
        expect(row).to_have_count(0)
        ((removed),) = wire.params("accounts.remove")
        assert (removed["cli"], removed["name"]) == ("claude", "work")


def test_the_daemons_own_machine_is_first_of_the_runtimes_and_cannot_be_changed(
    project: Path, engine: str
) -> None:
    """Section 3.11.2.7.1 of protocol/web.md: always there, with nothing to press."""
    with served() as site, opened(site, engine=engine) as page:
        go(page, "/settings/runtimes")
        listing = page.locator("[data-hmz=runtimes]")
        local = listing.locator("[data-hmz=runtime-local]")
        expect(local.locator("b")).to_have_text("This machine")
        expect(local.locator(".chip")).to_have_text("Built in")
        expect(local.locator("[data-hmz=runtime-local-has]")).to_contain_text(
            socket.gethostname()
        )
        expect(local).to_contain_text("Chats and epics run here")
        expect(local.locator("button, a, input, select")).to_have_count(0)
        # None written down is none other, not none.
        expect(listing.locator(".empty strong")).to_have_text("No other runtime yet.")

        # One written down stands under it, and it is still there.
        page.evaluate(
            "async () => (await import('/api.js')).call('runtimes.set',"
            " {backend: 'ssh', name: 'gpu', fields: {host: 'gpu.lab'}})"
        )
        go(page, "/settings/general")
        go(page, "/settings/runtimes")
        expect(listing.locator("[data-hmz=runtime]")).to_have_count(1)
        expect(listing.locator(".empty")).to_have_count(0)
        expect(local.locator("b")).to_have_text("This machine")
        first = page.evaluate(
            "() => document.querySelector('[data-hmz=runtimes] :is("
            "[data-hmz=runtime-local], table)').dataset.hmz"
        )
        assert first == "runtime-local"


def test_a_workspace_has_a_group_of_its_own_under_the_daemons(
    project: Path, engine: str, tmp_path: Path
) -> None:
    """Sections 3.11.1.5 and 3.11.1.6 of protocol/web.md: picked by name, said by its path."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    wire = Wire()
    with served() as site, opened(site, engine=engine, routed=wire.routes) as page:
        page.evaluate(
            "async (workspace) => (await import('/api.js')).call('workspaces.add',"
            " {workspace})",
            str(other),
        )
        go(page, "/settings/workspace")
        nav = page.locator(".settings-nav")
        expect(nav.locator(".settings-group")).to_have_text(
            ["App", "Daemon", "Workspace"]
        )
        # The last group, under the daemon's own pages.
        expect(nav.locator("a").nth(-2)).to_have_text("Setup")
        expect(nav.locator("a").last).to_have_text("Archived chats")
        expect(nav.locator("a[aria-current=page]")).to_have_text("Setup")

        picker = page.locator("[data-hmz=settings-workdir]")
        expect(picker).to_have_value(str(project))
        expect(picker.locator("option")).to_have_text([project.name, other.name])
        said = page.locator("[data-hmz=settings-workdir-path] .path")
        expect(said).to_have_attribute("data-path", str(project))
        shown = page.locator("[data-hmz=settings-workspace] dd").first
        expect(shown).to_have_text(str(project))

        # Another picked is the page's, and the address's; the other page opens on it.
        picker.select_option(str(other))
        expect(said).to_have_attribute("data-path", str(other))
        expect(shown).to_have_text(str(other))
        assert "workspace=" in page.url
        nav.get_by_role("link", name="Archived chats").click()
        expect(page.locator("[data-hmz=settings-workdir]")).to_have_value(str(other))
        expect(page.locator("[data-hmz=archived-chats] .empty strong")).to_have_text(
            "No archived chats."
        )

        # A directory gone is said beside the picker, not in it.
        other.rmdir()
        go(page, "/settings/general")
        go(page, f"/settings/workspace?workspace={other}")
        expect(page.locator("[data-hmz=settings-workdir] option")).to_have_text(
            [project.name, other.name]
        )
        expect(page.locator("[data-hmz=settings-workdir-missing]")).to_have_text(
            "Missing"
        )

        # A daemon with no folder says so, with nothing to pick.
        wire.faked["workspaces.list"] = lambda _: {
            "result": {"here": "", "workspaces": []}
        }
        go(page, "/settings/general")
        go(page, "/settings/archived")
        none = page.locator("[data-hmz=settings-archived] .empty")
        expect(none.locator("strong")).to_have_text("No folder yet.")
        expect(none.get_by_role("link", name="New chat")).to_have_attribute(
            "href", "#/new/chat"
        )
        expect(page.locator("[data-hmz=settings-workdir]")).to_be_hidden()
