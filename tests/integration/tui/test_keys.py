"""What a menu's keys are, and where they are said: four keys, one place, once.

A menu has the arrows up and down to walk its rows, the arrows across to turn its pages, enter
to open the row under the cursor or begin changing it, and esc to step back -- and nothing
else. Whatever a letter used to do is a row the arrows walk to, so nothing about working a
menu has to be known before it is opened.

And the row of keys is built in one place -- :meth:`hmz.tui.pick.Sheet._footed` -- which is
what makes `said once` a thing to check rather than a thing to remember: that row is the only
place `#keys` is written, no sheet names a key twice in it, it names no key but those four,
and the line about a sheet names no key at all.
"""

from __future__ import annotations

import re
import unittest.mock
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import Label, OptionList

import hmz.tui.pick
from hmz.coganchor.backends import Model
from hmz.coganchor.machines.store import SSHProvider
from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.pick import (
    _ACT_ADD,
    _ACT_SAVE,
    _ACT_SEARCH,
    _ADD,
    _DONE,
    _DOT,
    _FORK,
    _SAVE,
    _SEARCH,
    _WHENCE,
    Agent,
    Confirms,
    Docking,
    Epics,
    Failing,
    Fetches,
    Flows,
    Flowverses,
    Hosting,
    Hosts,
    Importing,
    Leaves,
    Machine,
    Placing,
    Reports,
    Sheet,
    Signing,
    Speaks,
    Unsaved,
)
from hmz.tui.settings import Adjusts
from tests.integration.tui.test_app import (
    acts,
    bar,
    changes,
    ids,
    into_agent,
    into_flows,
    onto,
    picks,
    rows,
)
from tests.tui.fixtures import until

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.screen import Screen

#: One installed CLI at two efforts, so that the sheets an agent is set up on have both a
#: list to pick from and a rung to step along.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: The keys a menu has, as its row of keys says them -- and typing, on a form's written rows.
_KEYS = {"←/→", "enter", "esc", "type"}

#: And the two more `/settings` has, being a screen with a search box and a bar of buttons
#: under its list: tab between the list and the bar, and `/` into the search.
_SETTINGS_KEYS = {*_KEYS, "tab", "/"}

#: How a key reads when it is named in prose. The line about a sheet MUST NOT name one -- the
#: row under the list is where the keys are said -- so this is what to look for up there.
_NAMES = re.compile(
    r"\b(?:enter|esc|escape|tab|space|backspace|arrows?)\b"
    r"|[←→↑↓]"
    r"|\b(?:ctrl|shift)\+\w+"
    r"|\b[a-z] (?:to |adds?|asks?|makes?|opens?|copies|fetches|puts|says|twice)\b",
    re.IGNORECASE,
)

#: The letters, chords and keys a menu used to have, none of which it has any more.
_GONE = ("s", "a", "r", "d", "f", "v", "space", "tab", "shift+tab", "ctrl+j")


def once(sheet: Screen[Any]) -> None:
    """Asserts that one sheet says each of its keys once, only its four, only at the bottom.

    Args:
      sheet: The sheet, as it is drawn now. What its keys are depends on which row the cursor
        is on and on whether a search is running, so this is asked of whatever is on the
        screen rather than of the class it is of.
    """
    assert isinstance(sheet, Sheet)
    keyed = [one.key for one in sheet._keyed]

    assert keyed, f"{type(sheet).__name__} says no keys at all"
    assert len(keyed) == len(set(keyed)), f"{type(sheet).__name__} says {keyed}"
    allowed = _SETTINGS_KEYS if isinstance(sheet, Adjusts) else _KEYS
    assert set(keyed) <= allowed, f"{type(sheet).__name__} says {keyed}"
    # And the line about the sheet says what the sheet is, and nothing about how to work it.
    about = str(sheet.query_one("#about", Label).content)
    found = _NAMES.search(about)
    assert found is None, f"{type(sheet).__name__} names {found and found.group()!r}"


def said(sheet: Screen[Any]) -> str:
    """The row of keys under a sheet, as it reads."""
    assert isinstance(sheet, Sheet)
    return _DOT.join(f"{one.key} {one.does}" for one in sheet._keyed)


def test_the_keys_are_written_in_one_place() -> None:
    """Which is what makes `said once` a thing to check rather than a thing to remember."""
    source = Path(str(hmz.tui.pick.__file__)).read_text(encoding="utf-8")

    assert source.count('"#keys"') == 1


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "opens",
    [
        pytest.param(Confirms, id="confirms"),
        pytest.param(partial(Leaves, held=True), id="leaves"),
        pytest.param(Reports, id="reports"),
        pytest.param(Fetches, id="fetches"),
        pytest.param(Speaks, id="speaks"),
        pytest.param(partial(Failing, dict(CLAUDE)), id="failing"),
        pytest.param(Signing, id="signing"),
        pytest.param(Epics, id="epics"),
        pytest.param(Hosting, id="hosting"),
        pytest.param(Docking, id="docking"),
        pytest.param(Importing, id="importing"),
        pytest.param(
            partial(Machine, SSHProvider(name="gpu", host="gpu")), id="machine"
        ),
        pytest.param(partial(Hosts, "ssh", unsaved=True), id="hosts"),
        pytest.param(Unsaved, id="unsaved"),
        pytest.param(partial(Placing, "box"), id="placing"),
        pytest.param(partial(Adjusts, dict(CLAUDE)), id="settings"),
        *(
            pytest.param(
                partial(Adjusts, dict(CLAUDE), page=page), id=f"settings-{page}"
            )
            for page in range(6)
        ),
    ],
)
async def test_a_sheet_says_each_of_its_keys_once(
    opens: Callable[[], Sheet[Any]], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A home of its own: importing reads the ssh config in it, and a test reads nobody's.
    monkeypatch.setenv("HOME", str(tmp_path))
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(opens())
        await until(lambda: isinstance(app.screen, Sheet), driver)
        await driver.pause()

        once(app.screen)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_menus_walked_into_say_each_of_their_keys_once(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """The ones that are not made but reached: the flows, a flow's agents, one agent."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        once(app.screen)

        await into_agent(app, driver)
        once(app.screen)

        # And on a row whose values are dropped under it, where enter drops them.
        await onto(app, driver, "effort")
        once(app.screen)
        assert "enter choose" in said(app.screen)
        assert "←/→" not in said(app.screen)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_row_is_changed_only_once_a_value_is_picked_for_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """Enter drops its values, the arrows walk them, enter picks one and esc picks none."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Agent)
        await onto(app, driver, "effort")
        was = sheet._effort

        # Walking past it, or pressing across on it, changes nothing.
        await driver.press("right")
        await driver.pause()
        assert sheet._effort == was
        assert not sheet._changed

        # Dropped, walked, and nothing picked.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        await driver.press("down")
        await driver.pause()
        assert sheet._effort == was
        await driver.press("escape")
        await until(lambda: app.screen is sheet, driver)
        assert sheet._effort == was
        assert sheet.under() == "effort"
        assert not sheet._changed

        # Dropped, and another picked -- which is a change the menu is holding.
        other = next(one for one in sheet._efforts() if one != was)
        await picks(app, driver, "effort", other)
        assert sheet._effort == other
        assert sheet._changed


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_esc_on_a_menu_holding_changes_asks_whether_to_save(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """And saving is a row and that question, and no chord."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await picks(app, driver, "effort", "max")

        # The chords that used to save save nothing.
        for key in ("shift+enter", "ctrl+j"):
            await driver.press(key)
            await driver.pause()
            assert isinstance(app.screen, Agent)

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, (Agent, Confirms)), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_no_letter_is_a_key_of_a_menu(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """What a letter used to do on the flows is a row below them instead."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Flows)
        before = ids(app)

        for key in _GONE:
            await driver.press(key)
            await driver.pause()
        assert app.screen is sheet
        assert not sheet._searching
        assert not sheet._inside
        assert ids(app) == before

        # Searching, copying a flow here and where flows come from are rows.
        assert before[-3:] == [_SEARCH, _FORK, _WHENCE]


@pytest.mark.timeout(60)
async def test_a_search_is_a_box_above_the_list_and_says_what_the_keys_do_in_it() -> (
    None
):
    """The letters are the box's then, and esc empties it before it leaves the page."""
    from textual.widgets import Input

    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Adjusts({}, page=5))
        await until(lambda: isinstance(app.screen, Flowverses), driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        await driver.pause()
        seek = sheet.query_one("#seek", Input)
        assert not seek.display
        assert _ACT_SEARCH in bar(app)
        assert "/ search" in said(sheet)

        await driver.press("slash")
        await until(lambda: seek.has_focus, driver)
        await driver.press(*"zzzz")
        await driver.pause()

        once(sheet)
        assert "esc clear" in said(sheet)
        # Nothing is called that, and the button that adds one is still there.
        assert rows(app) == []
        assert seek.value == "zzzz"
        assert _ACT_ADD in bar(app)

        await driver.press("escape")
        await driver.pause()
        assert not seek.display
        assert rows(app)
        assert isinstance(app.screen, Flowverses)
        assert not sheet._home

        # And the button starts one as the key does.
        await acts(app, driver, _ACT_SEARCH)
        await until(lambda: seek.has_focus, driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_saving_is_a_row_below_the_choices_rather_than_one_of_them(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """A menu whose way out looks like one of its answers is a menu hiding the way out."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        listing = app.screen.query_one("#choices", OptionList)

        assert rows(app)[-1] == _SAVE
        # Out of the numbering, and with a row of air above it: what is left to do about the
        # menu rather than one more thing to pick out of it.
        last = str(listing.get_option_at_index(listing.option_count - 1).prompt)
        assert last.startswith("\n")
        assert "save" in last
        assert f"{listing.option_count}." not in last

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Agent), driver)


@pytest.mark.timeout(60)
async def test_the_settings_menu_is_walked_into_and_its_rows_changed_from_a_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is true of one menu that holds what is changed in it is true of all of them."""
    from hmz.runtime.settings import Settings

    monkeypatch.chdir(tmp_path)
    Settings(tmp_path).answers(enable_sentry=True)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        await driver.pause()
        once(sheet)
        assert said(sheet) == "enter open · esc close"

        # Enter goes into the first page, whose rows are changed from a list dropped under
        # them: the arrows across change nothing there.
        await driver.press("enter")
        await until(lambda: not sheet._home, driver)
        once(sheet)
        assert rows(app) == ["reports", "sent", "details", "btw"]
        assert "enter choose" in said(sheet)
        await driver.press("right")
        await driver.pause()
        assert sheet._sentry is True
        assert not sheet._home

        await picks(app, driver, "reports", "off")
        assert sheet._sentry is False

        # Tab goes to the bar, where saving is, and enter presses it.
        await driver.press("tab")
        await driver.pause()
        assert sheet.focused is sheet.query_one("#act-save")
        once(sheet)
        assert "enter save" in said(sheet)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Adjusts), driver)

    assert Settings(tmp_path).enable_sentry is False


@pytest.mark.timeout(60)
@pytest.mark.parametrize("page", [2, 3, 4, 5])
async def test_adding_is_the_first_button_of_every_page_that_is_a_list(
    page: int,
) -> None:
    """Found in the same place on each of them, and on an empty one where the focus is."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Adjusts({}, page=page))
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        await driver.pause()

        assert bar(app)[0] == _ACT_ADD
        assert _ADD not in rows(app)
        # Saved from the last button where the page holds anything, and from none where not.
        assert (bar(app)[-1] == _ACT_SAVE) is (page in (2, 4))
        if not rows(app):
            assert app.screen.focused is app.screen.query_one("#act-add")


@pytest.mark.timeout(60)
async def test_a_form_is_written_by_typing_and_answered_from_its_done_row() -> None:
    """On a form a letter can only be an answer, so typing on a row writes it."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Speaks())
        await until(lambda: isinstance(app.screen, Speaks), driver)
        sheet = app.screen
        assert isinstance(sheet, Speaks)
        await driver.pause()
        assert rows(app) == ["command", _DONE]
        assert said(sheet) == "type to edit · esc back"

        await driver.press(*"my-agent")
        await driver.pause()
        assert sheet._editing == "command"
        assert said(sheet) == "enter keep · esc undo"
        # Kept, and on to the row that answers the form, nothing else being left to say.
        await driver.press("enter")
        await driver.pause()
        assert sheet._typed_in["command"] == "my-agent"
        assert sheet.under() == _DONE

        # Begun again by typing, written, and put back.
        await onto(app, driver, "command")
        await driver.press(*" --acp", "escape")
        await driver.pause()
        assert sheet._typed_in["command"] == "my-agent"
        # Or begun with enter, which is the same thing the long way round.
        await changes(app, driver, "command", *" --acp")
        assert sheet._typed_in["command"] == "my-agent --acp"

        await onto(app, driver, _DONE)
        assert "enter done" in said(sheet)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Speaks), driver)


@pytest.mark.timeout(60)
async def test_the_question_about_what_a_menu_holds_is_five_words() -> None:
    """It arrives over a menu somebody just spent a minute in, and either answer is a word."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Confirms())
        await until(lambda: isinstance(app.screen, Confirms), driver)
        sheet = app.screen
        await driver.pause()

        assert str(sheet.query_one("#asked", Label).content) == "Save?"
        assert not str(sheet.query_one("#about", Label).content)
        assert rows(app) == ["keep", "drop"]
        words = " ".join(
            str(sheet.query_one(one, Label).content) for one in ("#asked", "#keys")
        )
        # Every word in the box, keys and all, less the dot that separates two keys.
        split = words.replace("·", " ").split()
        assert len(split) <= 5, split


@pytest.mark.timeout(60)
async def test_a_sheet_is_answered_once_however_fast_the_key_is_pressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two answers to one question pops the screen under it, which on a first start is a crash."""
    from hmz.runtime import telemetry

    monkeypatch.delenv(telemetry.SAYS, raising=False)
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: isinstance(app.screen, Reports), driver)
        listing = app.screen.query_one("#choices", OptionList)

        # Both presses before either is handled, which is what a terminal delivers when
        # somebody leans on enter: the list posts one message apiece and both are answered.
        listing.action_select()
        listing.action_select()
        await until(lambda: not isinstance(app.screen, Reports), driver)
        await driver.pause()

        # The interface is still standing, which is the whole of it: a second answer that
        # popped the screen under this one would have taken the interface with it.
        assert app.is_running
        assert not isinstance(app.screen, Sheet)


@pytest.mark.timeout(60)
async def test_the_switches_on_a_form_are_flipped_the_way_every_row_is_changed() -> (
    None
):
    """Which other backends an account goes to is switches, changed as rows are."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Signing("claude"))
        await until(lambda: isinstance(app.screen, Signing), driver)
        sheet = app.screen
        assert isinstance(sheet, Signing)
        await driver.pause()
        # A way is picked from the ways dropped under the row, and not stepped along.
        await onto(app, driver, "way")
        assert "enter choose" in said(sheet)
        await driver.press("right")
        await driver.pause()
        assert not isinstance(app.screen, Dropdown)
        await picks(app, driver, "way", "key")
        assert sheet._typed_in["way"] == "key"
        once(sheet)

        # Nothing is installed in a test, so every one of them starts off.
        assert not sheet._also("pi")
        await picks(app, driver, "also:pi", "on")
        assert sheet._also("pi")
        once(sheet)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_flow_menu_is_saved_from_its_row(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """One menu walked into, saved from the row below its roles."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Flows)
        assert not sheet._inside

        await driver.press("enter")
        await until(lambda: sheet._inside, driver)
        once(sheet)
        assert rows(app)[-1] == _SAVE

        # And what lands is what the menu was holding, flow and agents together.
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._models


@pytest.mark.timeout(60)
async def test_a_search_above_a_list_lands_on_the_first_thing_it_finds() -> None:
    """The letters narrow the list as they are typed, and enter takes the best of the rest."""
    from hmz.runtime.flowing import OFFICIAL

    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Adjusts({}, page=5))
        await until(lambda: isinstance(app.screen, Flowverses), driver)
        sheet = app.screen
        assert isinstance(sheet, Flowverses)
        await driver.pause()

        await driver.press("slash", *"offi")
        await driver.pause()
        assert sheet.under() == OFFICIAL

        # And out of it, back on the list as it was.
        await driver.press("escape")
        await driver.pause()
        assert sheet.under() == OFFICIAL
