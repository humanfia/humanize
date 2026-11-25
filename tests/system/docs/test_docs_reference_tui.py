"""The pictures of `docs/reference/tui.md`: the offer list of commands, and a menu's keys.

The list `/` opens over the prompt, with what each command takes and does, and one menu
(`/settings daemons`) with its list, its buttons and the line of keys every menu ends in.
Run it by naming it: `uv run pytest tests/system/docs/test_docs_reference_tui.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import MODEL

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "reference-tui"


async def _settled(pilot: Pilot[None], seconds: float = 0.4) -> None:
    await pilot.pause(seconds)
    await pilot.pause()


async def test_the_commands_are_offered(world: World) -> None:
    # Wide enough that the longest line of the list, what `/settings` takes, is not cut.
    async with world.tui((126, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press("/")
        await shows(pilot, "/settings")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-commands")


async def test_a_menu_says_its_keys(world: World) -> None:
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await _settled(pilot)
        await pilot.press(*"/settings daemons", "enter")
        await shows(pilot, "Only Local so far")
        await _settled(pilot)
        shots.tui(app, f"{_PAGE}-menu")
