"""The pictures of `docs/user/terminal.md`: the terminal interface itself.

Its screen as it opens, a command completed out of the offer list, a menu with a dropdown, a
held change and the `Save?` box, and the views of a running flow stepped through. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_user_terminal.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.tui.dropdown import Dropdown
from hmz.tui.pick import Confirms
from tests.integration.doubles_tui import on, shows, until
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after, and the terminal they are taken in.
_PAGE = "user-terminal"
_SIZE = (96, 26)

#: What the flow of the last scene is set to do.
_TASK = "Add a discount code to checkout"


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_the_screen_as_it_opens(world: World) -> None:
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-home")


async def test_a_command_is_completed_and_a_menu_holds_a_change(world: World) -> None:
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)

        # -- a command, and what it takes, out of the offer list -----------------------
        reel = shots.Reel(f"{_PAGE}-commands")
        reel.tui(app, hold=1.0)
        await pilot.press("/")
        await shows(pilot, "tab select")
        reel.tui(
            app, hold=2.0, keys="/", cut=True, caption="the commands that work now"
        )
        await pilot.press("s", "e")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.2, keys="/se", cut=True)
        await pilot.press("tab")
        await shows(pilot, "notifications", "workspace")
        reel.tui(app, hold=1.8, keys="tab", caption="then what it takes")
        await pilot.press("n")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.0, keys="n", cut=True)
        await pilot.press("tab")
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.4, keys="tab")
        await pilot.press("enter")
        await shows(pilot, "Which epics on this machine you are told of")
        await _settled(pilot)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()

        # -- a menu: a dropdown, a held change, and the question on the way out --------
        shots.tui(app, f"{_PAGE}-menu")
        reel = shots.Reel(f"{_PAGE}-save")
        reel.tui(app, hold=1.4)
        await pilot.press("enter")
        dropped = await on(pilot, Dropdown)
        await _settled(pilot, 0.2)
        reel.tui(app, hold=1.8, keys="enter", caption="a row ending ▾ drops its values")
        await pilot.press("enter")
        await until(pilot, lambda: app.screen is not dropped, "the list to close")
        await shows(pilot, "unsaved changes")
        reel.tui(app, hold=2.0, keys="enter", caption="held, not saved yet")
        await pilot.press("escape")
        await shows(pilot, "Every setting Humanize keeps")
        await pilot.press("escape")
        await on(pilot, Confirms)
        await _settled(pilot, 0.2)
        reel.tui(app, hold=3.5, keys="esc esc", caption="leaving asks", poster=True)
        reel.save()
        # Dropped: nothing of the world's is changed by a picture.
        await pilot.press("right", "enter")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the menu to close")


async def test_the_views_of_a_running_flow_are_stepped_through(world: World) -> None:
    world.says(
        {"discount": {"text": "Added a discount code to checkout.", "after": 40}}
    )
    world.epic("@local/sign_off", _TASK, until=None)
    async with world.tui(_SIZE) as (app, pilot):
        await shows(pilot, "is working", "outworlder")
        await _settled(pilot)
        reel = shots.Reel(f"{_PAGE}-views")
        reel.tui(app, hold=2.2, caption="the agent's view")
        await pilot.press("shift+tab")
        await _settled(pilot, 0.6)
        reel.tui(app, hold=2.6, keys="shift+tab", caption="the person's view")
        await pilot.press("shift+tab")
        await _settled(pilot, 0.6)
        reel.tui(
            app, hold=2.2, keys="shift+tab", caption="and round again", poster=True
        )
        reel.save()
        await pilot.press("ctrl+c", "ctrl+c")
        await shows(pilot, "ctrl+c exit")
