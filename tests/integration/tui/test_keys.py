"""What a menu's keys are, and where they are said: one set of keys, one place, once.

Every menu is drawn and worked as `/settings` is. The arrows up and down walk its rows, enter
opens the row under the cursor, esc steps back, the arrows across go into what a row opens and
back out or along the buttons under the list, backspace goes up to the menu this one was opened
from, tab moves between the search, the list and the buttons, and `/` searches -- and nothing
else. Whatever a letter used to do is a button under the list, so nothing about working a menu
has to be known before it is opened, and every one of those is a click as well.

And the row of keys is built in one place -- :meth:`hmz.tui.pick.Sheet._footed` -- which is
what makes `said once` a thing to check rather than a thing to remember: that row is the only
place `#keys` is written, no sheet names a key twice in it, it names no key but those, and the
line about a sheet names no key at all.
"""

from __future__ import annotations

import re
import unittest.mock
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import Button, Input, Label, OptionList

import hmz.tui.flows
import hmz.tui.pick
import hmz.tui.settings
from hmz.coganchor.backends import Model
from hmz.coganchor.machines.store import SSHRuntime
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.dropdown import Dropdown
from hmz.tui.flows import _PROFILING, HOME, INSTALLED, VERSES, Fetches, Flows, Removes
from hmz.tui.pick import (
    _ACT_ADD,
    _ACT_DONE,
    _ACT_REMOVE,
    _ACT_SAVE,
    _ACT_SEARCH,
    _DOT,
    Account,
    Agent,
    Budgeted,
    Catalogue,
    Clis,
    Configures,
    Confirms,
    Docking,
    Epics,
    Failing,
    Hosting,
    Hosts,
    Importing,
    Leaves,
    Machine,
    Places,
    Placing,
    Reports,
    Sheet,
    Signing,
    Speaks,
    Swarming,
    Unsaved,
)
from hmz.tui.settings import PAGES, Adjusts
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
#: list to pick from and a value to drop.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: Two, for a list with something to narrow.
TWO = {**CLAUDE, "codex": (Model("gpt-5.5", ("high",)),)}

#: The keys a menu has, as its row of keys says them -- and typing, on a form's written rows.
_KEYS = {"←/→", "enter", "esc", "type", "tab", "/"}

#: How a key reads when it is named in prose. The line about a sheet MUST NOT name one -- the
#: row under the list is where the keys are said -- so this is what to look for up there.
_NAMES = re.compile(
    r"\b(?:enter|esc|escape|tab|space|backspace|arrows?)\b"
    r"|[←→↑↓]"
    r"|\b(?:ctrl|shift)\+\w+"
    r"|\b[a-z] (?:to |adds?|asks?|makes?|opens?|copies|fetches|puts|says|twice)\b",
    re.IGNORECASE,
)

#: The letters and chords a menu used to have, none of which it has any more.
_GONE = ("s", "a", "r", "d", "f", "v", "space", "ctrl+j")

#: What every menu is drawn with, as `/settings` is: the way here, the question, the search,
#: the list, the buttons, the keys.
_CHROME = ("#top", "#asked", "#about", "#seek", "#choices", "#actions", "#keys")


def once(sheet: Screen[Any]) -> None:
    """Asserts that one sheet says each of its keys once, only its own, only at the bottom.

    Args:
      sheet: The sheet, as it is drawn now. What its keys are depends on which row the cursor
        is on, where the focus is and whether a search is running, so this is asked of
        whatever is on the screen rather than of the class it is of.
    """
    assert isinstance(sheet, Sheet)
    keyed = [one.key for one in sheet._keyed]

    assert keyed, f"{type(sheet).__name__} says no keys at all"
    assert len(keyed) == len(set(keyed)), f"{type(sheet).__name__} says {keyed}"
    assert set(keyed) <= _KEYS, f"{type(sheet).__name__} says {keyed}"
    # And the line about the sheet says what the sheet is, and nothing about how to work it.
    about = str(sheet.query_one("#about", Label).content)
    found = _NAMES.search(about)
    assert found is None, f"{type(sheet).__name__} names {found and found.group()!r}"


def drawn(sheet: Screen[Any]) -> None:
    """Asserts that one sheet is drawn as `/settings` is, and not as the sheets were before.

    Args:
      sheet: The sheet.
    """
    for part in _CHROME:
        assert sheet.query(part), f"{type(sheet).__name__} has no {part}"
    prompts = [str(one.prompt) for one in sheet.query_one(OptionList).options]
    # The row under the cursor is filled rather than marked, and no row is numbered.
    assert not any("❯" in one for one in prompts), prompts
    assert not any(re.match(r"\s*(?:\[[^\]]*\])?\s*\d+\.", one) for one in prompts)


def said(sheet: Screen[Any]) -> str:
    """The row of keys under a sheet, as it reads."""
    assert isinstance(sheet, Sheet)
    return _DOT.join(f"{one.key} {one.does}" for one in sheet._keyed)


def test_the_keys_are_written_in_one_place() -> None:
    """Which is what makes `said once` a thing to check rather than a thing to remember.

    Nowhere else either: `/settings` and `/flow` are drawn by the same sheet, rather than
    each building a row of keys -- or a way across the top, or a bar -- of its own.
    """

    def source(module: object) -> str:
        return Path(str(getattr(module, "__file__", ""))).read_text(encoding="utf-8")

    assert source(hmz.tui.pick).count('"#keys"') == 1
    for menu in (hmz.tui.settings, hmz.tui.flows):
        for part in ('"#keys"', "#actions", "#top", "def compose", "BINDINGS"):
            assert part not in source(menu), f"{menu.__name__} draws its own {part}"


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
        pytest.param(Swarming, id="swarming"),
        pytest.param(Importing, id="importing"),
        pytest.param(
            partial(Machine, SSHRuntime(name="gpu", host="gpu")), id="machine"
        ),
        pytest.param(partial(Account, "claude", "work"), id="account"),
        pytest.param(partial(Clis, dict(TWO), "claude"), id="clis"),
        pytest.param(
            partial(Catalogue, "claude", "", CLAUDE["claude"], "claude-opus-5"),
            id="catalogue",
        ),
        pytest.param(partial(Places, dict(CLAUDE), "Select a place"), id="places"),
        pytest.param(partial(Hosts, "ssh", unsaved=True), id="hosts"),
        pytest.param(Unsaved, id="unsaved"),
        pytest.param(partial(Placing, "box"), id="placing"),
        pytest.param(partial(Adjusts, dict(CLAUDE)), id="settings"),
        *(
            pytest.param(
                partial(Adjusts, dict(CLAUDE), page=page), id=f"settings-{page}"
            )
            for page in range(len(PAGES))
        ),
        *(
            pytest.param(
                partial(Flows, "chat", {}, None, dict(CLAUDE), {}, page=page),
                id=f"flows-{page}",
            )
            for page in (HOME, INSTALLED, VERSES)
        ),
        pytest.param(
            partial(Flows, "chat", {}, None, dict(CLAUDE), {}, inside=True),
            id="flows-roles",
        ),
        pytest.param(partial(Removes, "theirs", 1), id="removes"),
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
        assert isinstance(app.screen, Sheet)
        await driver.pause()

        sheet = app.screen
        assert isinstance(sheet, Sheet)
        once(sheet)
        drawn(sheet)
        # And where the focus is on the buttons, they are what the keys are about.
        for button in sheet.query("#actions Button").results(Button):
            if button.display and not button.disabled:
                button.focus()
                await driver.pause()
                once(sheet)
                assert any(one.key == "enter" for one in sheet._keyed)


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
        drawn(app.screen)

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
        assert app.screen is sheet

        # Dropped, walked, and nothing picked.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Dropdown), driver)
        assert isinstance(app.screen, Dropdown)
        await driver.press("down")
        await driver.pause()
        assert sheet._effort == was
        await driver.press("escape")
        await until(lambda: app.screen is sheet, driver)
        assert app.screen is sheet
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
    """And saving is a button and that question, and no chord."""
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
        assert isinstance(app.screen, Confirms)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, (Agent, Confirms)), driver)
        assert not isinstance(app.screen, (Agent, Confirms))


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_no_letter_is_a_key_of_a_menu(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """What a letter used to do is a button under the list instead."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Agent)
        before = ids(app)

        for key in _GONE:
            await driver.press(key)
            await driver.pause()
        assert app.screen is sheet
        assert not sheet._searching
        assert not sheet._changed
        assert ids(app) == before
        assert bar(app) == [_ACT_SAVE]


@pytest.mark.timeout(60)
async def test_a_search_is_a_box_above_the_list_and_says_what_the_keys_do_in_it() -> (
    None
):
    """The letters are the box's then, and esc empties it before it leaves the sheet."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Clis(dict(TWO), "claude"))
        await until(lambda: isinstance(app.screen, Clis), driver)
        assert isinstance(app.screen, Clis)
        sheet = app.screen
        assert isinstance(sheet, Clis)
        await driver.pause()
        seek = sheet.query_one("#seek", Input)
        assert not seek.display
        assert _ACT_SEARCH in bar(app)
        assert "/ search" in said(sheet)

        await driver.press("slash")
        await until(lambda: seek.has_focus, driver)
        assert seek.has_focus
        await driver.press(*"zzzz")
        await driver.pause()

        once(sheet)
        assert "esc clear" in said(sheet)
        # Nothing is called that, and the button that searches is still there.
        assert rows(app) == []
        assert seek.value == "zzzz"
        assert _ACT_SEARCH in bar(app)

        await driver.press("escape")
        await driver.pause()
        assert not seek.display
        assert rows(app) == ["claude", "codex"]
        assert app.screen is sheet

        # And the button starts one as the key does.
        await acts(app, driver, _ACT_SEARCH)
        await until(lambda: seek.has_focus, driver)
        assert seek.has_focus


@pytest.mark.timeout(60)
async def test_a_search_lands_on_the_first_thing_it_finds() -> None:
    """The letters narrow the list as they are typed, and enter takes the best of the rest."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Clis(dict(TWO), "claude"))
        await until(lambda: isinstance(app.screen, Clis), driver)
        assert isinstance(app.screen, Clis)
        sheet = app.screen
        assert isinstance(sheet, Clis)
        await driver.pause()
        assert sheet.under() == "claude"

        await driver.press("slash", *"cod")
        await driver.pause()
        assert sheet.under() == "codex"

        # Down to the list, and out of the search, back on the list as it was.
        await driver.press("down")
        await driver.pause()
        assert sheet.query_one("#choices").has_focus
        await driver.press("escape")
        await driver.pause()
        assert sheet.under() == "codex"
        assert rows(app) == ["claude", "codex"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_saving_is_a_button_under_the_list_rather_than_one_of_its_rows(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """A menu whose way out looks like one of its answers is a menu hiding the way out."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Agent)

        assert bar(app) == [_ACT_SAVE]
        # Nothing to save until something is held, and so nothing tab can reach.
        save = sheet.query_one(f"#act-{_ACT_SAVE}", Button)
        assert save.disabled
        assert "tab actions" not in said(sheet)

        await picks(app, driver, "effort", "max")
        assert not save.disabled
        assert "tab actions" in said(sheet)
        assert sheet.query_one("#pending", Label).content

        await onto(app, driver, _ACT_SAVE)
        once(sheet)
        assert said(sheet).startswith("enter save")
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Agent), driver)
        assert not isinstance(app.screen, Agent)


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
        assert isinstance(app.screen, Adjusts)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        await driver.pause()
        once(sheet)
        assert said(sheet) == "enter open · esc close"

        # Enter goes into the first page, whose rows are changed from a list dropped under
        # them: the arrow right changes nothing there.
        await driver.press("enter")
        await until(lambda: not sheet._home, driver)
        assert not sheet._home
        once(sheet)
        assert [one for one in rows(app) if one] == [
            "details",
            "btw",
            "reports",
            "sent",
        ]
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
        assert not isinstance(app.screen, Adjusts)

    assert Settings(tmp_path).enable_sentry is False


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_flow_menu_is_walked_as_the_settings_menu_is(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """Its pages are gone into with the arrow right and come back out of every way there is."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Flows)
        assert sheet._page == INSTALLED
        once(sheet)
        drawn(sheet)

        # Up to the first screen, which is cards as `/settings` opens on, and back in.
        for up in ("left", "backspace", "escape"):
            await driver.press(up)
            await until(lambda: sheet._page == HOME, driver)
            once(sheet)
            assert said(sheet) == "enter open · esc close"
            await driver.press("right")
            await until(lambda: sheet._page == INSTALLED, driver)

        # No letter is a key of it: what one used to do is a button under the list.
        before = ids(app)
        for key in _GONE:
            await driver.press(key)
            await driver.pause()
        assert app.screen is sheet
        assert sheet._page == INSTALLED
        assert ids(app) == before
        assert not sheet._changed
        assert {_ACT_SEARCH, "copy", "more", _ACT_SAVE} <= set(bar(app))

        # Into what a flow runs on, where whether it is profiled is a switch whose two values
        # are dropped under it, rather than turned over in place or stepped with the arrows.
        await driver.press("right")
        await until(lambda: sheet._inside or isinstance(app.screen, Configures), driver)
        if isinstance(app.screen, Configures):
            await driver.press("escape")
        await until(lambda: sheet._inside, driver)
        once(sheet)
        await onto(app, driver, _PROFILING)
        assert "enter choose" in said(sheet)
        await driver.press("right")
        await driver.pause()
        assert app.screen is sheet
        await picks(app, driver, _PROFILING, "on")
        assert sheet._profile
        once(sheet)

        # And back out to what is installed, holding what was changed.
        await driver.press("left")
        await until(lambda: sheet._page == INSTALLED, driver)
        assert sheet._changed


@pytest.mark.timeout(60)
@pytest.mark.parametrize("page", ["accounts", "fallback", "runtimes"])
async def test_adding_is_the_first_button_of_every_page_that_is_a_list(
    page: str,
) -> None:
    """Found in the same place on each of them, and on an empty one where the focus is."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Adjusts({}, page=PAGES.index(page)))
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        assert isinstance(app.screen, Adjusts)
        await driver.pause()

        assert bar(app)[0] == _ACT_ADD
        # Saved from the last button where the page holds anything, and from none where not.
        assert (bar(app)[-1] == _ACT_SAVE) is (page in ("accounts", "fallback"))
        if not rows(app):
            assert app.screen.focused is app.screen.query_one("#act-add")


@pytest.mark.timeout(60)
async def test_a_form_is_written_by_typing_and_answered_from_its_done_button() -> None:
    """On a form a letter can only be an answer, so typing on a row writes it."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Speaks())
        await until(lambda: isinstance(app.screen, Speaks), driver)
        assert isinstance(app.screen, Speaks)
        sheet = app.screen
        assert isinstance(sheet, Speaks)
        await driver.pause()
        assert rows(app) == ["command"]
        assert bar(app) == [_ACT_DONE]
        assert said(sheet) == "type to edit · tab actions · esc back"

        await driver.press(*"my-agent")
        await driver.pause()
        assert sheet._editing == "command"
        assert said(sheet) == "enter keep · esc undo"
        # Kept, and on to the button that answers the form, nothing else being left to say.
        await driver.press("enter")
        await driver.pause()
        assert sheet._typed_in["command"] == "my-agent"
        assert sheet.focused is sheet.query_one(f"#act-{_ACT_DONE}")
        assert said(sheet).startswith("enter done")
        # Which says what answering it will do, under the list.
        assert "saves it as a backend" in str(sheet.query_one("#tuning", Label).content)

        # Begun again by typing, written, and put back.
        await onto(app, driver, "command")
        await driver.press(*" --acp", "escape")
        await driver.pause()
        assert sheet._typed_in["command"] == "my-agent"
        # Or begun with enter, which is the same thing the long way round.
        await changes(app, driver, "command", *" --acp")
        assert sheet._typed_in["command"] == "my-agent --acp"

        await onto(app, driver, _ACT_DONE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Speaks), driver)
        assert not isinstance(app.screen, Speaks)


@pytest.mark.timeout(60)
async def test_the_question_about_what_a_menu_holds_is_five_words() -> None:
    """It arrives over a menu somebody just spent a minute in, and either answer is a word."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Confirms())
        await until(lambda: isinstance(app.screen, Confirms), driver)
        assert isinstance(app.screen, Confirms)
        sheet = app.screen
        await driver.pause()

        assert str(sheet.query_one("#asked", Label).content) == "Save?"
        assert not str(sheet.query_one("#about", Label).content)
        assert bar(app) == ["keep", "drop"]
        words = f"{sheet.query_one('#asked', Label).content} {said(sheet)}"
        # Every word in the box, keys and all, less the dot that separates two keys.
        split = words.replace("·", " ").split()
        assert len(split) <= 5, split


@pytest.mark.timeout(60)
async def test_a_question_that_arrives_is_answered_with_its_buttons() -> None:
    """The arrows move between them, enter takes one, and a click off the box takes none."""
    app = Humanize()
    async with app.run_test() as driver:
        answered: list[str | None] = []
        app.push_screen(Confirms(), answered.append)
        await until(lambda: isinstance(app.screen, Confirms), driver)
        assert isinstance(app.screen, Confirms)
        sheet = app.screen
        await driver.pause()
        assert sheet.focused is sheet.query_one("#act-keep")

        for key, lands in (("down", "drop"), ("down", "keep"), ("left", "drop")):
            await driver.press(key)
            await driver.pause()
            assert sheet.focused is sheet.query_one(f"#act-{lands}"), key
        await driver.click(offset=(1, 1))
        await until(lambda: not isinstance(app.screen, Confirms), driver)
        assert not isinstance(app.screen, Confirms)
        assert answered == [None]

        app.push_screen(Confirms(), answered.append)
        await until(lambda: isinstance(app.screen, Confirms), driver)
        assert isinstance(app.screen, Confirms)
        await driver.pause()
        await driver.click("#act-drop")
        await until(lambda: not isinstance(app.screen, Confirms), driver)
        assert not isinstance(app.screen, Confirms)
        assert answered == [None, "drop"]


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
        assert isinstance(app.screen, Reports)
        await driver.pause()
        button = app.screen.query_one("#act-on", Button)

        # Both presses before either is handled, which is what a terminal delivers when
        # somebody leans on enter: the button posts one message apiece and both are answered.
        button.press()
        button.press()
        await until(lambda: not isinstance(app.screen, Reports), driver)
        assert not isinstance(app.screen, Reports)
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
        assert isinstance(app.screen, Signing)
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
async def test_the_flow_menu_is_saved_from_its_last_button(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """One menu walked into, saved from the last button under its roles."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Flows)
        assert not sheet._inside
        # Searching, copying a flow here and installing more are buttons under the list.
        assert {_ACT_SEARCH, "copy", "more"} <= set(bar(app))

        await driver.press("enter")
        await until(lambda: sheet._inside, driver)
        assert sheet._inside
        once(sheet)
        assert bar(app)[-1] == _ACT_SAVE

        # And what lands is what the menu was holding, flow and agents together.
        await onto(app, driver, _ACT_SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)
        assert not isinstance(app.screen, Flows)

    assert app._models


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_arrows_across_go_into_a_row_and_backspace_comes_back_up(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """As in a file manager: right into what a row opens, left or backspace back out of it."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        agent = app.screen
        assert isinstance(agent, Agent)

        for back in ("left", "backspace"):
            await onto(app, driver, "cli")
            await driver.press("right")
            await until(lambda: isinstance(app.screen, Clis), driver)
            assert isinstance(app.screen, Clis)
            await driver.press(back)
            await until(lambda: app.screen is agent, driver)
            assert app.screen is agent
            assert not agent._changed

        # And up out of the agent too, to the flow it is an agent of.
        await driver.press("backspace")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert isinstance(app.screen, Flows)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_way_across_the_top_is_the_way_back(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """Each menu a sheet was opened from is a step across its top, and a click goes back."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        flows = app.screen
        assert isinstance(flows, Flows)
        await into_agent(app, driver)
        agent = app.screen
        assert isinstance(agent, Agent)
        await onto(app, driver, "cli")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Clis), driver)
        assert isinstance(app.screen, Clis)
        clis = app.screen
        assert isinstance(clis, Clis)
        await driver.pause()

        # The prompt, then `/flow` and each of its pages on the way to the flow, then the
        # agent: a menu with pages of its own is a step apiece.
        steps = [one.screen for one in clis._crumbed]
        assert steps == [app.screen_stack[0], flows, flows, flows, agent]
        said = [str(one.content) for one in clis.query(".crumb").results(Label)]
        assert said[:5] == ["hmz", "/flow", "Installed", flows._flow, agent._named]

        # The flow is two menus back: both are left, as esc on each would leave them.
        await driver.click("#crumb-3")
        await until(lambda: app.screen is flows, driver)
        assert app.screen is flows
        assert flows._inside

        # And a page of it further back is the menu turned back to that page.
        await into_agent(app, driver)
        await driver.click("#crumb-1")
        await until(lambda: app.screen is flows and flows._page == HOME, driver)
        assert app.screen is flows
        assert flows._page == HOME

        # And the prompt is the way out of every menu at once, which is the way out a
        # pointer has.
        await driver.press(
            "enter"
        )  # into what is installed, the first screen's first card
        await until(lambda: flows._page == INSTALLED, driver)
        await into_agent(app, driver)
        await driver.click("#crumb-0")
        await until(lambda: not isinstance(app.screen, Sheet), driver)
        assert not isinstance(app.screen, Sheet)


@pytest.mark.timeout(60)
async def test_tab_walks_between_the_search_the_list_and_the_buttons() -> None:
    """And every one of them says what the keys do there."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Account("claude", "work"))
        await until(lambda: isinstance(app.screen, Account), driver)
        assert isinstance(app.screen, Account)
        sheet = app.screen
        await driver.pause()
        assert sheet.query_one("#choices").has_focus
        assert bar(app) == [_ACT_REMOVE]

        await driver.press("tab")
        await driver.pause()
        assert sheet.focused is sheet.query_one(f"#act-{_ACT_REMOVE}")
        once(sheet)
        assert said(sheet).startswith("enter remove")
        await driver.press("shift+tab")
        await driver.pause()
        assert sheet.query_one("#choices").has_focus
        once(sheet)


@pytest.mark.timeout(60)
async def test_backspace_and_the_arrow_left_are_a_written_row_s_own() -> None:
    """On a row written where it stands, they are the first keys of fixing it, not the way up."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(
            Agent("builder", Runs("claude/claude-opus-5:high"), CLAUDE)
        )
        await until(lambda: isinstance(app.screen, Agent), driver)
        agent = app.screen
        assert isinstance(agent, Agent)
        app.push_screen(Configures("flow", Budgeted, None, asked="Set budget"))
        await until(lambda: isinstance(app.screen, Configures), driver)
        sheet = app.screen
        assert isinstance(sheet, Configures)
        await driver.pause()
        await onto(app, driver, "cost")

        for key in ("backspace", "left"):
            await driver.press(key)
            await driver.pause()
            assert app.screen is sheet, key

        # And on a row that is not written, up they go, as on any other.
        await onto(app, driver, "graceful")
        await driver.press("backspace")
        await until(lambda: app.screen is agent, driver)
        assert app.screen is agent
