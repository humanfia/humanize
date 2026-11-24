"""The pictures of `docs/user/settings.md`: the settings dialog, and `/settings`.

The dialog in the app's window on its General page, a change of it saved; the Setup page of
a folder's own settings, and what it remembers forgotten; the screen of pages `/settings`
opens in the terminal interface, a change held on one of them and saved, and its Workspace
page. Run it by naming it: `uv run pytest tests/system/docs/test_docs_user_settings.py`.

Copying a page to another machine's daemon (Batch apply) is pictured by the scenes of
`docs/user/daemons.md`, which run a second daemon; here there is this machine's alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from playwright.sync_api import expect

from hmz.tui.dropdown import Dropdown
from tests.integration.doubles_tui import on, onto, shows, trail, until
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after, and the terminal they are taken in.
_PAGE = "user-settings"
_SIZE = (96, 40)


def _set_up(world: World) -> None:
    """Remembers two flows set up in the project, as starting an epic of each would."""
    from hmz.runtime.kept import read_back
    from hmz.runtime.settings import Settings

    runs = read_back(AGENT)
    assert runs is not None
    kept = Settings(world.workspace)
    kept.remember("rlar", {"actor": runs, "reviewer": runs}, budget={"cost": 5.0})
    kept.remember("goal", {"worker": runs}, budget={"cost": 5.0})


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


def test_the_dialog_opens_on_general_and_saves(world: World) -> None:
    with world.page(desktop=True) as page:
        go(page, "/settings/general")
        dialog = page.get_by_role("dialog", name="Settings")
        harness = dialog.get_by_label("List in sidebar")
        expect(harness).to_be_visible()
        expect(dialog.locator("[data-hmz=settings-of]")).to_have_text("DaemonLocal")
        page.wait_for_timeout(400)
        shots.web(page, f"{_PAGE}-general", window="desktop")

        reel = shots.Reel(f"{_PAGE}-save", clip=dialog, pad=0)
        reel.web(page, hold=2.0, pointer=harness, click=True)
        harness.check()
        save = dialog.get_by_role("button", name="Save", exact=True)
        page.wait_for_timeout(300)
        reel.web(page, hold=1.8, pointer=save, click=True)
        save.click()
        expect(dialog.get_by_role("button", name="Saved")).to_be_visible()
        page.wait_for_timeout(300)
        reel.web(page, hold=3.0, poster=True)
        reel.save()


def test_a_folder_is_forgotten(world: World) -> None:
    _set_up(world)
    with world.page(desktop=True) as page:
        go(page, f"/workspace/setup?workspace={world.workspace}")
        dialog = page.get_by_role("dialog", name="Workspace settings: shop")
        expect(dialog.locator("[data-hmz=workspace-name]")).to_have_text("shop")
        expect(dialog).to_contain_text("goal, rlar")
        forget = dialog.get_by_role("button", name="Forget", exact=True)
        expect(forget).to_be_visible()
        page.wait_for_timeout(400)
        reel = shots.Reel(f"{_PAGE}-forget", clip=dialog, pad=0)
        reel.web(page, hold=2.4, pointer=forget, click=True)
        forget.click()
        expect(dialog).to_contain_text("Forget how 2 flows were set up here?")
        asked = page.get_by_role("dialog", name="Forget how 2 flows")
        yes = asked.get_by_role("button", name="Forget", exact=True)
        page.wait_for_timeout(300)
        reel.web(page, hold=2.2, pointer=yes, click=True)
        yes.click()
        expect(dialog).to_contain_text("Forgotten.")
        page.wait_for_timeout(300)
        reel.web(page, hold=3.2, poster=True)
        reel.save()


async def test_settings_in_the_terminal(world: World) -> None:
    _set_up(world)
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/settings", "enter")
        await shows(pilot, "Every setting is here", "WORKSPACE")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal")

        reel = shots.Reel(f"{_PAGE}-terminal-held")
        reel.tui(app, hold=2.0, keys="/settings", caption="a card per page")
        await onto(pilot, "general")
        await pilot.press("enter")
        await shows(pilot, trail("hmz", "/settings", "General"), "Harness sessions")
        await _settled(pilot)
        reel.tui(app, hold=2.0, keys="enter", caption="General, a row per setting")
        await pilot.press("enter")
        await on(pilot, Dropdown)
        await _settled(pilot)
        reel.tui(app, hold=2.2, keys="enter", caption="a row's values drop under it")
        await pilot.press("enter")
        await shows(pilot, "● Unsaved")
        await _settled(pilot)
        await pilot.press("escape")
        await shows(pilot, "Every setting is here", "■ Unsaved")
        await _settled(pilot)
        reel.tui(
            app,
            hold=3.2,
            keys="enter esc",
            caption="held, and marked on its card, until saved",
            poster=True,
        )
        # The reel is held to its size: tab's own frame, the cards again, is left out.
        await pilot.press("tab")
        await shows(pilot, "enter Save")
        await pilot.press("enter")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu to close")
        await shows(pilot, "Details are on")
        await _settled(pilot)
        reel.tui(
            app,
            hold=3.0,
            keys="tab enter",
            caption="tab reaches Save, enter saves: the menu closes",
        )
        reel.save()


async def test_the_workspace_page_in_the_terminal(world: World) -> None:
    _set_up(world)
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/settings workspace", "enter")
        await shows(
            pilot, trail("hmz", "/settings", "Workspace"), "Default agent", "Forget"
        )
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-terminal-workspace")
