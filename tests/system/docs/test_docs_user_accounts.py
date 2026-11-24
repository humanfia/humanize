"""The pictures of `docs/user/accounts.md`: the accounts an agent runs as.

The Accounts settings of the app with two accounts of one CLI, one being made there, an
account's menu and the form that corrects it; the same page of the terminal interface, its
form as far as its last answer, an account's menu there, and the list an agent's sheet picks
its account from; and a chat from the command line naming an account nobody made, which is
refused.

No picture is of a turn taken as an account, nor of the terminal's page just after one is
made: this is taken on a Mac, where a CLI that keeps credential files cannot be run as a
named account (`hmz internal cred` needs Linux), and what the terminal says then is that.

Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_accounts.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.dropdown import Dropdown
from hmz.tui.pick import Accounts, Agent, Clis
from tests.integration.doubles_tui import on, onto, opens, picks, shows, typed
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from tests.system.docs.conftest import World

_PAGE = "user-accounts"

#: What every secret is answered with: nothing real.
_KEY = "not-a-real-key"

_ASK = "Where is the checkout total computed?"


def _work(world: World) -> None:
    """An account of Claude Code made by an API key, called `work`."""
    world.call(
        "accounts.create",
        cli="claude",
        name="work",
        way="key",
        answers={"ANTHROPIC_API_KEY": _KEY},
    )


def _personal(world: World) -> None:
    """Another of the same CLI, made by a long-lived token, called `personal`."""
    world.call(
        "accounts.create",
        cli="claude",
        name="personal",
        way="token",
        answers={"CLAUDE_CODE_OAUTH_TOKEN": _KEY},
    )


def _settled(page: Page) -> None:
    """Waits until the page behind the settings has asked what its agent runs."""
    expect(page.get_by_text("Asking…")).to_have_count(0)
    page.wait_for_timeout(300)


def test_the_accounts_of_a_cli_are_listed(world: World) -> None:
    _work(world)
    _personal(world)
    # What this machine's own sign-in runs, asked as `Refresh models` asks it.
    world.call("accounts.models", cli="claude", name="")
    with world.page(desktop=True) as page:
        go(page, "/settings/accounts")
        expect(page.locator("[data-hmz=account]")).to_have_count(3)
        expect(page.get_by_text("2 models")).to_be_visible()
        _settled(page)
        shots.web(page, f"{_PAGE}-list", window="desktop")


def test_an_account_is_made_in_the_app(world: World) -> None:
    _personal(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/accounts")
        expect(page.locator("[data-hmz=account]")).to_have_count(2)
        _settled(page)
        making = page.locator("[data-hmz=make-account]")
        way = page.get_by_label("Sign-in method")
        name = page.get_by_label("Name", exact=True)
        reel = shots.Reel(f"{_PAGE}-new", window="desktop")
        reel.web(
            page, hold=1.6, pointer=way, click=True, caption="Pick a sign-in method"
        )
        way.select_option("key")
        key = making.locator("input[type=password]").first
        expect(key).to_be_visible()
        reel.web(page, hold=1.2, pointer=name, click=True, caption="Name the account")
        reel.type(page, name, "work")
        key.fill(_KEY)
        create = page.get_by_role("button", name="Create")
        reel.web(page, hold=1.4, pointer=create, click=True, caption="Paste the key")
        create.click()
        expect(page.locator("[data-hmz=account]")).to_have_count(3)
        expect(making.get_by_role("status")).to_contain_text("Made claude@work.")
        page.wait_for_timeout(300)
        reel.web(page, hold=3.5, caption="The account is listed", poster=True)
        reel.save()


def test_an_accounts_menu(world: World) -> None:
    _work(world)
    _personal(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/accounts")
        row = page.locator("[data-hmz=account]").filter(has_text="work")
        more = row.get_by_role("button", name="More options")
        more.click()
        menu = page.locator("[role=menu]").last
        expect(menu.get_by_text("Refresh models")).to_be_visible()
        _settled(page)
        shots.web(page, f"{_PAGE}-menu", window="desktop", pointer=more)


def test_an_account_is_edited_in_the_app(world: World) -> None:
    _work(world)
    with world.page(desktop=True) as page:
        go(page, "/settings/accounts")
        row = page.locator("[data-hmz=account]").filter(has_text="work")
        row.get_by_role("button", name="Edit").click()
        form = page.locator("[data-hmz=correct-account]")
        expect(form).to_be_visible()
        page.wait_for_timeout(300)
        shots.web(page, f"{_PAGE}-edit", clip="[data-hmz=make-account]", pad=16)


def test_an_account_nobody_made_is_refused() -> None:
    shots.cli(
        ["hmz", "chat", "start", "-a", f"claude@staging/{MODEL}", _ASK],
        f"{_PAGE}-cli",
        columns=96,
    )


async def test_the_accounts_in_the_terminal(world: World) -> None:
    _work(world)
    _personal(world)
    async with world.tui((100, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings accounts")
        await shows(pilot, "personal", "work", "Local")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-terminal")


async def test_an_account_is_filled_in_at_the_terminal(world: World) -> None:
    _personal(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings accounts")
        await shows(pilot, "personal", "Local")
        await pilot.pause(0.5)
        reel = shots.Reel(f"{_PAGE}-terminal-add")
        reel.tui(app, hold=1.6, keys="/settings accounts")
        await pilot.click("#act-add")
        await shows(pilot, "New account", "what the account is called")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.6, caption="Add account")
        await opens(pilot, "way")
        await on(pilot, Dropdown)
        await pilot.pause(0.3)
        reel.tui(app, hold=2.0, keys="enter", caption="The ways into this CLI")
        await pilot.press("escape")
        await pilot.pause(0.3)
        await picks(pilot, "way", "key")
        await shows(pilot, "ANTHROPIC_API_KEY")
        await opens(pilot, "name")
        await pilot.press("ctrl+u")
        await pilot.press(*"work", "enter")
        await opens(pilot, "ANTHROPIC_API_KEY")
        await pilot.press(*_KEY, "enter")
        await pilot.pause(0.5)
        # On to its button, as tab goes: the line over it says what Done will do.
        app.screen.query_one("#act-done").focus()
        await shows(pilot, "adds the account claude/work")
        await pilot.pause(0.3)
        reel.tui(app, hold=3.5, caption="Answered: Done adds it", poster=True)
        reel.save()


async def test_an_account_is_held_to_be_removed(world: World) -> None:
    _work(world)
    _personal(world)
    async with world.tui((100, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings accounts")
        await shows(pilot, "personal", "work", "Local")
        await onto(pilot, "claude/work")
        await pilot.pause(0.5)
        reel = shots.Reel(f"{_PAGE}-terminal-menu")
        reel.tui(app, hold=1.4)
        await pilot.press("enter")
        await shows(pilot, "Edit", "Sign in again", "Remove")
        await pilot.pause(0.3)
        reel.tui(app, hold=2.6, keys="enter", caption="An account's menu", poster=True)
        await pilot.click("#act-remove")
        await shows(pilot, "will be removed")
        await pilot.pause(0.3)
        reel.tui(app, hold=3.0, caption="Remove is held until you save")
        reel.save()


async def test_an_agents_account_is_picked_in_the_terminal(world: World) -> None:
    _work(world)
    _personal(world)
    async with world.tui((100, 24)) as (app, pilot):
        await shows(pilot, MODEL)
        await typed(pilot, "/settings workspace")
        await shows(pilot, "Chat agent")
        await onto(pilot, "chat-agent")
        await pilot.press("enter")
        await on(pilot, Agent)
        await opens(pilot, "cli")
        await on(pilot, Clis)
        await opens(pilot, "claude")
        await on(pilot, Agent)
        await opens(pilot, "provider")
        await on(pilot, Accounts)
        await shows(pilot, "Pick an account", "Local", "personal", "work")
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-terminal-pick")
