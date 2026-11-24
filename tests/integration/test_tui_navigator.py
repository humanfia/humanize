"""The navigator and Search of the real interface: what there is to work on, opened and found.

The chats and the epic are the daemon's own, held in this process, had and run through the
interface by the stand-in `claude`; the navigator and Search then list them as the daemon
answers them, and open one in the log by what `/resume` and `/epics` open one with.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Input, OptionList

from hmz.runtime.epic import Ran, chats, epics, read
from hmz.tui import Humanize
from hmz.tui.pick import Acts, Does
from hmz.tui.shell import Zone
from hmz.tui.views.navigator import Navigator
from hmz.tui.views.search import Search
from tests.integration.doubles_tui import (
    OWN,
    SIZE,
    folds_fast,
    on,
    opened,
    opens,
    own_flow,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: Every chat and epic here is held by a daemon of the test's own, in this process.
pytestmark = [pytest.mark.usefixtures("daemon", "loops"), pytest.mark.timeout(180)]

#: A terminal wide enough for the navigator to be open as the interface opens.
WIDE = (140, 44)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, a flow of the workspace's own, chats that fold at once."""
    del asking
    folds_fast(monkeypatch)
    workspace = stand_in(tmp_path, monkeypatch)
    own_flow(workspace)
    return workspace


async def _two(pilot: Pilot[None], workspace: Path) -> tuple[str, str]:
    """Has one chat, leaves it to fold away, and has a second, which is on the screen."""
    await opened(pilot)
    await typed(pilot, "first")
    await shows(pilot, "heard first", "◉ done")
    await typed(pilot, "/clear")
    await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
    (folding,) = chats(workspace)
    await until(pilot, lambda: bool((read(folding) or Ran(folding)).ended), "the fold")
    await typed(pilot, "second")
    await shows(pilot, "heard second", "◉ done")
    first, second = chats(workspace)
    return first.name, second.name


def _listed(app: Humanize) -> list[str]:
    """What the navigator lists, by what each row is put up under."""
    listing = app.query_one(Navigator).query_one(OptionList)
    return [str(one.id) for one in listing.options]


async def _lists(pilot: Pilot[None], app: Humanize, *rows: str) -> Navigator:
    """Has the navigator read the list again, until it lists every one of `rows`."""
    navigator = app.query_one(Navigator)

    def listed() -> bool:
        navigator.reads()
        return all(f"r:{row}" in _listed(app) for row in rows)

    await until(pilot, listed, f"the navigator to list {rows}")
    return navigator


async def _onto(pilot: Pilot[None], navigator: Navigator, row: str) -> None:
    """Gives the navigator the keys, and walks its cursor on to one row."""
    await pilot.press("ctrl+b")
    await until(pilot, lambda: navigator.query_one(OptionList).has_focus, "the keys")
    await pilot.press("home")
    for _ in range(len(navigator.query_one(OptionList).options)):
        if navigator.under() == f"r:{row}":
            return
        await pilot.press("down")
    raise AssertionError(f"{row} is not in the navigator")


@pytest.mark.usefixtures("workspace")
async def test_the_navigator_is_open_on_a_wide_terminal_and_closed_on_a_narrow_one() -> (
    None
):
    wide = Humanize()
    async with wide.run_test(size=WIDE) as pilot:
        zone = wide.query_one("#navigator", Zone)
        await until(pilot, lambda: zone.has_class("open"), "the navigator")
        await shows(pilot, "SIDEBAR")
        # Open, and the keys still the prompt's.
        assert getattr(wide.focused, "id", "") == "editor"

    narrow = Humanize()
    async with narrow.run_test(size=SIZE) as pilot:
        zone = narrow.query_one("#navigator", Zone)
        await opened(pilot)
        assert not zone.has_class("open")
        assert getattr(narrow.focused, "id", "") == "editor"

        await pilot.press("ctrl+b")
        await until(pilot, lambda: zone.has_class("open"), "the navigator")
        assert "esc Back" in screen(narrow)


async def test_a_chat_is_opened_in_the_log_from_the_navigator(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=WIDE) as pilot:
        first, second = await _two(pilot, workspace)
        navigator = await _lists(pilot, app, first, second)
        # The one on the log is the newest, and the folder's heading stands over both.
        assert _listed(app).index(f"r:{second}") < _listed(app).index(f"r:{first}")
        assert workspace.name.upper() in screen(app)

        await _onto(pilot, navigator, first)
        await pilot.press("enter")

        # As one picked on `/resume` is: folded away, it is carried on by the next line.
        await shows(pilot, f"say something to continue chat {first}")
        await until(
            pilot, lambda: getattr(app.focused, "id", "") == "editor", "the prompt"
        )
        assert app.showing() == first
        assert "heard second" not in screen(app)
        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        assert len(chats(workspace)) == 2


async def test_a_row_is_pinned_and_its_menu_copies_and_archives(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=WIDE) as pilot:
        first, second = await _two(pilot, workspace)
        navigator = await _lists(pilot, app, first, second)
        await _onto(pilot, navigator, first)

        await pilot.press("p")
        await shows(pilot, "PINNED")
        assert navigator.kept.has("pinned", first)
        # Pinned, it stands over its folder, and the cursor went with it.
        assert _listed(app).index(f"r:{first}") < _listed(app).index(f"r:{second}")
        assert navigator.under() == f"r:{first}"

        await pilot.press("full_stop")
        await on(pilot, Acts)
        await opens(pilot, "archive")
        await shows(pilot, "Archived")
        await until(pilot, lambda: f"r:{first}" not in _listed(app), "it to leave")
        assert f"r:{second}" in _listed(app)


async def test_an_epic_is_gone_into_from_the_navigator(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=WIDE) as pilot:
        await set_up_own_flow(pilot)
        await typed(pilot, f"${OWN} hello")
        await shows(pilot, "the flow is done")
        (epic,) = epics(workspace)
        navigator = await _lists(pilot, app, epic.name)
        await shows(pilot, "hello")

        await _onto(pilot, navigator, epic.name)
        await pilot.press("enter")

        # What `/epics` goes into: the epic's own sheet, and esc is one step back from it.
        await on(pilot, Does)
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the log")


async def test_search_finds_a_chat_by_what_was_typed_and_opens_it(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=WIDE) as pilot:
        first, second = await _two(pilot, workspace)

        await pilot.press("ctrl+k")
        search = await on(pilot, Search)
        found = search.query_one(OptionList)
        await until(
            pilot,
            lambda: (
                {str(one.id) for one in found.options} == {f"r:{first}", f"r:{second}"}
            ),
            "both chats",
        )
        assert "RECENTS" in screen(app)

        await pilot.press(*"first")
        await until(
            pilot,
            lambda: [str(one.id) for one in found.options] == [f"r:{first}"],
            "the one chat",
        )
        assert "RESULTS" in screen(app)
        assert isinstance(app.focused, Input)

        await pilot.press("enter")
        await until(pilot, lambda: len(app.screen_stack) == 1, "Search to close")
        await shows(pilot, f"say something to continue chat {first}")
        assert app.showing() == first


@pytest.mark.usefixtures("workspace")
async def test_the_key_of_search_closes_it_and_esc_does() -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await pilot.press("ctrl+k")
        await on(pilot, Search)
        await pilot.press("ctrl+k")
        await until(pilot, lambda: len(app.screen_stack) == 1, "Search to close")

        await pilot.press("ctrl+k")
        await on(pilot, Search)
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "Search to close")
        assert getattr(app.focused, "id", "") == "editor"


@pytest.mark.usefixtures("workspace")
async def test_the_key_of_a_zone_is_left_alone_while_search_is_over_the_log() -> None:
    app = Humanize()
    async with app.run_test(size=WIDE) as pilot:
        await opened(pilot)
        await pilot.press("ctrl+k")
        page = await on(pilot, Search)
        await shows(pilot, "esc Close", "F2 How it went")

        await pilot.press("ctrl+b", "f1")
        await pilot.pause()

        # The zones are under the page: its keys stay its own, and its hint line too.
        assert app.screen is page
        assert "esc Close" in screen(app)
