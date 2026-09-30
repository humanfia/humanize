"""`/settings`: every setting humanize has, on a screen of its own, one level at a time.

What opens is the six places settings are kept and nothing else -- this machine's own, this
workspace's, the accounts, the environments, the fallbacks and the flowverses -- each a card
saying what is in it, as a phone's settings or VS Code's open on their categories. Enter or a
click goes into one and esc or backspace comes back out, as k9s and ranger walk in and out of
what they list; the line across the top says where you are, and its first word is a way back.

Inside one is a list, and what is done about the list rather than to one thing on it --
searching it, adding to it, bringing more into it, saving -- is a bar of buttons under it,
as lazygit and gh-dash put what a panel does beside the panel rather than among its rows. Tab
moves between the two. A value is changed by picking it out of every value it can take,
dropped under its row (:mod:`hmz.tui.dropdown`), as Textual's `Select` and Charm's `huh` do,
rather than stepped along with the arrows. And every one of those is a click as well.

What is changed is still held until it is saved, from the bar or from the question leaving
asks: the pages that are lists of things are the classes of :mod:`hmz.tui.pick` this is made
of, which say what a list of accounts or machines does, and this is where they are drawn.
"""

# The pages are the mixins of `pick`, and what they share is that module's own.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from rich.markup import escape
from textual import events, on, work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.geometry import Offset
from textual.message import Message
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from hmz.runtime import telemetry
from hmz.runtime.kept import Runs, read_back, written
from hmz.runtime.telemetry import KEPT, SAYS, SENT

from .dropdown import Dropdown, Value, anchor
from .pick import (
    _ACCOUNTS,
    _ADD,
    _APART,
    _APART_MARK,
    _DIRECTORY,
    _DOCKS,
    _DOT,
    _EVERYWHERE,
    _FALLBACK,
    _FIRST,
    _IMPORTS,
    _INDENT,
    _INFORCE,
    _LABEL,
    _MACHINES,
    _NO,
    _ON_APART,
    _SAVE,
    _SEARCH,
    _SHEET,
    _SPEAKS,
    _VERSES,
    _YES,
    Adjusted,
    Agent,
    Body,
    Fallbacks,
    Flowverses,
    Key,
    Machines,
    Providers,
    _complete,
    _hmz,
    _many,
    _shortly,
)
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from textual.app import App, ComposeResult
    from textual.await_complete import AwaitComplete

    from hmz.coganchor.backends import Model


__all__ = ["PAGES", "Adjusts", "page_of"]


#: What `/settings` is told to open each page by, in the order they are listed: the word on
#: its card, lower case, so that the word typed is the word read.
PAGES = (
    "settings",
    "workspace",
    "accounts",
    "environments",
    "fallback",
    "flowverses",
)

#: The words the first two were opened by before they were called what they are, still
#: taken: a word somebody's fingers know is a word they will type.
_ALIASES = {"everywhere": _EVERYWHERE, "directory": _DIRECTORY}


def page_of(said: str) -> int | None:
    """Which page a word opens, by its name or the name it had.

    Args:
      said: The word, in any case.

    Returns:
      The page, counting from the first, or None for a word that is no page.
    """
    said = said.lower()
    return PAGES.index(said) if said in PAGES else _ALIASES.get(said)


class _Page(NamedTuple):
    """One card of the first screen: what the page is called, its mark, and what is in it.

    Attributes:
      title: What it is called, on its card and across the top once inside it.
      icon: One cell that tells it from the others at a glance.
      blurb: What is kept there, in a line.
    """

    title: str
    icon: str
    blurb: str


#: The pages, in the order of :data:`PAGES`.
_PAGES = (
    _Page("Settings", "⚙", "this machine: error reports, details, and the /btw agent"),
    _Page("Workspace", "⌂", "this directory: its flow, profiling, and forgetting it"),
    _Page("Accounts", "◉", "what agents sign in as, per CLI"),
    _Page("Environments", "▦", "ssh hosts and docker daemons a flow's roles run on"),
    _Page("Fallback", "↻", "where a turn goes when an agent fails"),
    _Page("Flowverses", "⑂", "where flows come from"),
)

#: What the first screen says it is.
_HOME_ABOUT = "Every setting humanize keeps. What you change is held until you save it."

#: The rows the first two pages are made of, by the id each is put up under.
_SENTRY = "reports"
_SENT = "sent"
_DETAILS = "details"
_BTW = "btw"
_WORKSPACE = "workspace"
_RUNS = "flow"
_PROFILES = "profile"
_FORGET = "forget"

#: The kinds of row those are: a switch, turned on or off from the two dropped under it; a
#: value picked out of a list; one that says something when it is opened; and one that is
#: only read -- a directory and the flow it opens on are what is remembered, not set here.
_SWITCH, _PICK, _SAYS, _READ = "switch", "pick", "says", "read"

#: What the /btw agent's list offers beside the agents it can already be: setting one up.
_ANOTHER = f"{_APART_MARK}another"

#: When a setting that cannot land at once does land, said beside its row while it is held
#: and in the transcript once it is saved.
_NEXT_RUN = "takes effect on next flow run"
_NEXT_LAUNCH = "takes effect on next launch"
_NEXT_BTW = "takes effect on next /btw"

#: The buttons under the list, in the order they stand. Each is one of the rows a page puts
#: above its list, drawn as a button rather than a row: a page shows the ones it has.
_BAR = (_ADD, _SPEAKS, _DOCKS, _IMPORTS, _SEARCH, _SAVE)


def _act(held: str) -> str:
    """The id of the button one of those is drawn as."""
    return f"act-{held.removeprefix(_APART_MARK)}"


class _Setting(NamedTuple):
    """One row of the first two pages.

    Attributes:
      held: Its id.
      named: What it is called.
      value: What it is set to, in words.
      about: What it means.
      kind: Which of the four kinds of row it is -- see :data:`_SWITCH`.
      note: When a change held on it lands, or "" for one that lands at once.
    """

    held: str
    named: str
    value: str
    about: str
    kind: str
    note: str = ""


def _word(on: bool | None) -> str:  # noqa: FBT001 -- a switch is one
    """What a switch says it is."""
    return {True: _YES, False: _NO, None: "not set"}[on]


def _shade(style: str, said: str, *, here: bool) -> str:
    """Words in a colour, or in none on the row under the cursor.

    That row is drawn in the cursor's own pair of colours, which carry their own contrast
    whatever the terminal's are: grey or yellow words inside it are words on blue.

    Args:
      style: The colour, as markup names it.
      said: The words, unescaped.
      here: Whether they are on the row under the cursor.

    Returns:
      The words, as markup.
    """
    return escape(said) if here else f"[{style}]{escape(said)}[/]"


#: What each switch's two values mean, said beside them on the list dropped under it.
_MEANS = {
    _SENTRY: ("send error reports", "send nothing"),
    _DETAILS: ("show tool calls and thinking", "show turn responses only"),
    _PROFILES: ("profile what runs here start", "trace them only"),
    _FORGET: ("clear saved settings here", "keep them"),
}


_SETTINGS = """
Adjusts { align: left top; background: $background; }
Adjusts #sheet { width: 100%; height: 100%; padding: 1 2 0 2; }
Adjusts #rule { display: none; }
Adjusts #tabs { display: none; }
Adjusts #top { height: 1; width: 100%; }
Adjusts #crumb-root { width: auto; color: $text-muted; }
Adjusts #crumb-root.home { color: $primary; text-style: bold; }
Adjusts #crumb-root.link:hover { color: $primary; text-style: underline; }
Adjusts #crumb-sep { width: auto; color: $text-muted; }
Adjusts #asked { width: auto; padding: 0; text-style: bold; color: $primary; }
Adjusts #pending { width: 1fr; text-align: right; color: $warning; }
Adjusts #about { width: 100%; padding: 0 0 1 0; color: $text-muted; }
Adjusts #seek { display: none; border: round $primary; background: $background; }
Adjusts #choices {
    height: 1fr; max-height: 100%; padding: 0; background: $background;
    border: round $accent; scrollbar-size: 1 1; }
Adjusts #choices:focus { border: round $primary; background-tint: $background 0%; }
Adjusts #choices > .option-list--option-highlighted {
    background: $block-cursor-blurred-background;
    color: $block-cursor-blurred-foreground; text-style: none; }
Adjusts #choices:focus > .option-list--option-highlighted {
    background: $block-cursor-background; color: $block-cursor-foreground;
    text-style: bold; }
Adjusts #choices > .option-list--separator { color: $accent; }
Adjusts #tuning { width: 100%; height: auto; padding: 0 1; }
Adjusts #actions { width: 100%; height: auto; padding: 1 0 0 0; }
Adjusts #actions Button {
    height: 1; min-width: 0; padding: 0 2; margin: 0 1 0 0; border: none;
    background: $block-cursor-blurred-background;
    color: $block-cursor-blurred-foreground; text-style: none; }
Adjusts #actions Button.-primary {
    background: $success; color: $block-cursor-foreground; }
Adjusts #actions Button:hover {
    background: $block-cursor-background; color: $block-cursor-foreground; }
Adjusts #actions Button:focus {
    background: $block-cursor-background; color: $block-cursor-foreground;
    text-style: bold; }
Adjusts #actions Button:disabled {
    background: $background; color: $text-muted; text-opacity: 100%;
    text-style: none; }
Adjusts #actions .spacer { width: 1fr; height: 1; }
Adjusts #keys { width: 100%; height: auto; padding: 1 0 0 0; color: $text-muted; }
"""


class Adjusts(Providers, Machines, Fallbacks, Flowverses):
    """Every setting humanize has: `/settings`, six pages opened from one screen of them.

    Settings is what is true of this machine however many projects are driven from it; the
    workspace is one directory's; the accounts, the environments, the fallbacks and the
    flowverses are what agents run as, the machines their work goes on, where turns go when
    they cannot, and where flows come from. One menu because they are one question -- what
    does humanize remember -- and a command apiece was six things to learn the names of.

    A menu rather than a file to edit, for the reason every other menu here is one: what is
    written down is written down in humanize's own words, and a person should not have to know
    the shape of a YAML file to turn a thing off. What is held lands together when it is saved,
    from the bar or from the question leaving asks, and each setting takes effect at once where
    it can; where it cannot, the row says when it will while it is held and the transcript says
    so once it is saved. What runs a command of its own -- making an account, signing one in,
    saving or checking a machine, fetching a flowverse -- happens as it is asked for.
    """

    CSS = _SHEET + _SETTINGS

    BINDINGS: ClassVar = [
        # Out a level, as esc is: the key a file manager and a browser both go up with.
        Binding("backspace", "up", "back", show=False),
        Binding("slash", "search", "search", show=False),
    ]

    class Settled(Message):
        """Says what the settings menu was answered with, to whoever applies it.

        Posted to the interface rather than only answered to whoever opened the menu: the
        flow menu opens it too, onto its flowverses, and what was changed there is the
        interface's to apply all the same -- the details it shows, the directory it remembers.
        """

        def __init__(self, said: Adjusted) -> None:
            """Carries the answer.

            Args:
              said: What the menu was answered with.
            """
            super().__init__()
            self.said = said

    def __init__(
        self,
        agents: Mapping[str, tuple[Model, ...]],
        *,
        page: int | None = None,
        only: bool = False,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the menu on what is remembered now.

        What is written down rather than what is happening: the environment may answer the
        reporting question for one run, and a menu that showed that would be a menu offering
        to change a thing it cannot. The page says so under the list where the two differ.

        Args:
          agents: The backends offered here, and what each of them says it runs, which is
            what the fallback page chooses a place out of.
          page: Which page to open inside, or None for the screen of them all.
          only: Whether that page is the whole of it, for a menu opened from another one for
            that page alone: esc on it leaves rather than going up to the others.
          unavailable: The optional backends that still need installing, which the btw agent
            is offered as it is anywhere else an agent is set up.
        """
        super().__init__()
        settings = _hmz().settings
        self._sentry = self._sentry_was = settings.enable_sentry
        self._overridden = telemetry.enabled() is not self._sentry
        self._details = self._details_was = settings.details
        #: The agent `/btw` talks to outside a session, or "" for the flow's first.
        self._btw = self._btw_was = settings.btw
        self._unavailable = unavailable
        self._workspace = str(Path.cwd())
        self._flow = settings.flow
        self._roles = len(settings.agents(settings.flow))
        self._flows = len(settings.flows())
        self._profile = self._profile_was = settings.profiling
        self._forget = False
        self._offered = dict(agents)
        self._steps = list(_hmz().fallbacks.all())
        #: The steps as they were read, so the card can say the page is holding a change.
        self._steps_was = list(self._steps)
        #: Whether the screen of pages is what is drawn, rather than one of them.
        self._home = page is None
        self._tab = page or 0
        self._only = only and page is not None
        #: The row each page's cursor was last on, by id, for when it is gone back into.
        self._cursors: dict[int, str] = {}
        #: The buttons the page being drawn asks for: `(id, label, what it does)` apiece.
        self._bar: list[tuple[str, str, str]] = []
        #: The keys the page last said it had, before where the focus is was said as well.
        self._page_keys: tuple[Key, ...] = ()
        #: How wide the names of the first two pages' rows are, where their values start.
        self._values_at = 0
        #: How wide the screen was last drawn, which the cards are laid out across.
        self._width = 0

    def compose(self) -> ComposeResult:
        """The way here across the top, the page, the list, what it says, the bar, the keys.

        The rule and the titles every sheet has are there, and not shown: a screen of its own
        is ruled by its edges, and the pages are its first screen rather than tabs over one.
        """
        with Body(id="sheet"):
            yield Label(id="rule")
            yield Label(id="tabs")
            with Horizontal(id="top"):
                yield Label("/settings", id="crumb-root")
                yield Label(
                    " \N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK} ", id="crumb-sep"
                )
                yield Label(id="asked")
                yield Label(id="pending")
            yield Label(id="about")
            yield Input(placeholder="type to filter", id="seek")
            yield Choices(id="choices")
            yield Label(id="tuning")
            with Horizontal(id="actions"):
                for held in _BAR:
                    if held == _SAVE:
                        # Saving at the far end, set apart from what is done to the list.
                        yield Static(classes="spacer")
                    yield Button(
                        _ON_APART[held],
                        id=_act(held),
                        variant="primary" if held == _SAVE else "default",
                        compact=True,
                    )
            yield Label(id="keys")

    def _ask(self) -> None:
        """Reads the pages that are lists, and puts up whichever is open."""
        listing = self.query_one("#choices", OptionList)
        # As tall as the screen leaves it: this is the whole screen, not a sheet over one.
        listing.styles.max_height = None
        self._read_accounts()
        self._read_machines()
        self._read_verses()
        self._fill()
        self._settles_focus()

    def _settles_focus(self) -> None:
        """Puts the focus on the list, or on the bar where the list has nothing to land on.

        Which on a page with nothing in it is the button that adds the first thing.
        """
        listing = self.query_one("#choices", OptionList)
        if any(not one.disabled for one in listing.options):
            listing.focus()
            return
        for held in _BAR:
            button = self.query_one(f"#{_act(held)}", Button)
            if button.display and not button.disabled:
                button.focus()
                return
        listing.focus()

    def shortens(self) -> None:
        """Lays the cards out across the screen again, where it changed width.

        Nothing is shortened: the list is as tall as the screen leaves it, and scrolls.
        """
        width = self.size.width
        if width != self._width:
            self._width = width
            if self.query("#choices"):
                self._fill()

    # -- Going in and out ----------------------------------------------------------------------

    def _opens(self, page: int | None) -> None:
        """Goes into one page, or back out to the screen of them all.

        What was said on the page left, and where its cursor was, are kept for when it is gone
        back into: what became of something done on a page is still true of it after a look at
        another. A search goes with the page it was typed into.

        Args:
          page: The page, or None for the screen of them all.
        """
        listing = self.query_one("#choices", OptionList)
        if not self._home:
            self._saids[self._tab] = self._said
            self._cursors[self._tab] = self._was
        self._said = ""
        self._typed = ""
        seek = self.query_one("#seek", Input)
        seek.display = False
        with seek.prevent(Input.Changed):
            seek.value = ""
        listing.clear_options()
        self._drawn = None
        if page is None:
            self._home = True
        else:
            self._home = False
            self._tab = page
            self._said = self._saids.pop(page, "")
            self._was = self._cursors.get(page, "")
        self._fill()
        self._settles_focus()

    def _tell(self, page: int, said: str) -> None:
        """Says what became of something done on one page, whichever is open now.

        Args:
          page: The page it was done on.
          said: What to say, as markup.
        """
        if self._home or self._tab != page:
            self._saids[page] = said
        else:
            self._said = said

    def action_up(self) -> None:
        """Goes back out to the screen of pages, from inside one."""
        if not self._home and not self._only:
            self._opens(None)

    def action_back(self) -> None:
        """Comes out of a search, or out of the page, or leaves.

        Leaving asks first whether to save what is held, as every menu holding changes does.
        """
        if self._typed or self.query_one("#seek", Input).display:
            self._clears_search()
            return
        if not self._home and not self._only:
            self._opens(None)
            return
        self.leaving()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Whether one of this screen's keys is live now.

        The arrows across are the search box's own while it has the focus, as are its letters
        and backspace; and a search is started only where the page has one.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it.
        """
        typing = isinstance(self.focused, Input)
        if action == "across":
            return not typing
        if action == "search":
            return not typing and any(held == _SEARCH for held, _, _ in self._bar)
        if action == "up":
            return not typing
        return super().check_action(action, parameters)

    def action_across(self, by: int) -> None:
        """Steps along the bar, or goes into the card under the cursor, or back out.

        Right goes in and left comes out, as they do in a file manager that lists what is in
        the folder beside the one it is in; along the bar they move between its buttons.

        Args:
          by: One on, or one back.
        """
        focus = self.focused
        if isinstance(focus, Button):
            shown = [
                one
                for one in self.query_one("#actions", Horizontal).query(Button)
                if one.display and not one.disabled
            ]
            if focus in shown:
                shown[(shown.index(focus) + by) % len(shown)].focus()
            return
        if self._home and by > 0:
            self.action_enter()
        elif not self._home and by < 0:
            self.action_up()

    def action_walk(self, by: int) -> None:
        """Walks the list, or comes back to it from the search box above it or the bar below.

        Args:
          by: One row down, or one up.
        """
        focus = self.focused
        listing = self.query_one("#choices", OptionList)
        if isinstance(focus, Input):
            if by > 0:
                listing.focus()
            return
        if isinstance(focus, Button):
            if by < 0:
                listing.focus()
            return
        super().action_walk(by)

    def action_enter(self) -> None:
        """Opens the row under the cursor, presses the button with the focus, or ends typing."""
        focus = self.focused
        if isinstance(focus, Input):
            self.query_one("#choices", OptionList).focus()
            return
        if isinstance(focus, Button):
            focus.press()
            return
        super().action_enter()

    def on_click(self, event: events.Click) -> None:
        """Takes a click on the first word across the top as the way back out.

        Args:
          event: The click.
        """
        if event.widget is self.query_one("#crumb-root") and not self._home:
            self.action_up()

    def on_descendant_focus(self) -> None:
        """Says the keys again, which are not the same on the list, the search and the bar."""
        if self._page_keys:
            self._footed(*self._page_keys)

    # -- Searching ---------------------------------------------------------------------------

    def action_search(self) -> None:
        """Opens the box a search is typed into, above the list, and puts the letters there."""
        seek = self.query_one("#seek", Input)
        seek.display = True
        seek.focus()

    @on(Input.Changed, "#seek")
    def _seeks(self, event: Input.Changed) -> None:
        """Narrows the list to what has been typed, as it is typed.

        Args:
          event: What the box says now.
        """
        self._typed = event.value
        # On the first thing found while there is something typed; where it was, once not.
        self._seek = _FIRST if event.value else ""
        self._fill()

    def _clears_search(self) -> None:
        """Takes the search away, and the list back to all of itself, the cursor where it was."""
        seek = self.query_one("#seek", Input)
        with seek.prevent(Input.Changed):
            seek.value = ""
        seek.display = False
        self._typed = ""
        self._fill()
        self.query_one("#choices", OptionList).focus()

    # -- Drawing -----------------------------------------------------------------------------

    def _fill(self) -> None:
        """Puts up the screen of pages, or the page that is open, and the bar under it."""
        self._bar = []
        self._draws_top()
        self.query_one("#about", Label).update(
            _HOME_ABOUT
            if self._home
            else {
                _EVERYWHERE: "Global settings for humanize on this machine.",
                _DIRECTORY: "Saved settings for this directory: the default flow, and "
                "how it was last configured.",
                _ACCOUNTS: self.ACCOUNTS_ABOUT,
                _MACHINES: self.MACHINES_ABOUT,
                _FALLBACK: self.STEPS_ABOUT,
                _VERSES: self.VERSES_ABOUT,
            }[self._tab]
        )
        if self._home:
            self._fill_home()
        elif self._tab == _ACCOUNTS:
            self._fill_accounts()
        elif self._tab == _MACHINES:
            self._fill_machines()
        elif self._tab == _FALLBACK:
            self._fill_steps()
        elif self._tab == _VERSES:
            self._fill_verses()
        else:
            self._fill_own()
        self._shows_bar()

    def _draws_top(self) -> None:
        """Says where this is across the top: `/settings`, and the page inside it."""
        root = self.query_one("#crumb-root", Label)
        root.display = not self._only
        root.set_class(self._home, "home")
        root.set_class(not self._home, "link")
        self.query_one("#crumb-sep", Label).display = not (self._home or self._only)
        asked = self.query_one("#asked", Label)
        asked.display = not self._home
        asked.update(_PAGES[self._tab].title)
        self.query_one("#pending", Label).update(
            "● unsaved changes" if self._holding() else ""
        )

    def _summary(self, page: int) -> str:
        """What one page's card says is in it, in a few words."""
        if page == _EVERYWHERE:
            return f"reports {_word(self._sentry)}{_DOT}details {_word(self._details)}"
        if page == _DIRECTORY:
            return f"{_shortly(self._workspace)}{_DOT}flow {self._flow or 'none'}"
        if page == _ACCOUNTS:
            return _many(len([one for one in self._accounts if one.name]), "account")
        if page == _MACHINES:
            return _many(len(self._saved_machines), "machine")
        if page == _FALLBACK:
            return _many(len(self._steps), "rule")
        return _many(len(self._verses), "flowverse")

    def _pending(self, page: int) -> bool:
        """Whether one page is holding a change that saving would land."""
        if page == _EVERYWHERE:
            return (self._sentry, self._details, self._btw) != (
                self._sentry_was,
                self._details_was,
                self._btw_was,
            )
        if page == _DIRECTORY:
            return self._profile != self._profile_was or self._forget
        if page == _ACCOUNTS:
            return bool(self._gone or self._chains or self._edits)
        if page == _FALLBACK:
            return self._steps != self._steps_was
        return False

    def _width_of(self, listing: OptionList) -> int:
        """How many cells across the list has to lay its rows out in."""
        return listing.scrollable_content_region.width or max(self.size.width - 6, 40)

    def _holding(self) -> bool:
        """Whether any page is holding a change that saving would land.

        Read off what each page holds rather than off whether anything was ever changed: a
        switch turned on and back off again is nothing to save, and nothing to be asked about
        on the way out.
        """
        return any(self._pending(page) for page in range(len(PAGES)))

    def leaving(self) -> None:
        """Asks whether to save what is held, where anything still is, and leaves."""
        if not self._holding():
            self.dismiss(None)
            return
        self.asks_to_save()

    def _fill_home(self) -> None:
        """Puts up a card per page: its mark, its name, what is in it, and what it is for."""
        listing = self.query_one("#choices", OptionList)
        at = (
            listing.highlighted
            if listing.option_count == len(PAGES) and listing.highlighted is not None
            else self._tab
        )
        width = self._width_of(listing)
        cards: list[Option | None] = []
        for page, card in enumerate(_PAGES):
            here = page == at
            summary = self._summary(page)
            pending = self._pending(page)
            said = f"{summary}  ● unsaved" if pending else summary
            pad = " " * max(2, width - 5 - len(card.title) - len(said))
            right = _shade("$text-muted", summary, here=here) + (
                f"  {_shade('$warning', '● unsaved', here=here)}" if pending else ""
            )
            cards.append(
                Option(
                    f" {_shade('$primary', card.icon, here=here)}  "
                    f"[b]{escape(card.title)}[/]{pad}{right}\n"
                    f"    {_shade('$text-muted', card.blurb, here=here)}",
                    id=f"={PAGES[page]}",
                )
            )
            # A rule between two cards, which the cursor steps over.
            cards.append(None)
        listing.set_options(cards[:-1])
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update("")
        self._bar.append(
            (
                _SAVE,
                "save",
                "save all changes" if self._holding() else "nothing to save yet",
            )
        )
        self._footed(Key("enter", "open"), Key("esc", "close"))

    def _settings(self) -> list[_Setting]:
        """The rows of the first two pages, as they are held now."""
        if self._tab == _DIRECTORY:
            return [
                _Setting(
                    _WORKSPACE,
                    "Directory",
                    _shortly(self._workspace),
                    "the directory these settings apply to",
                    _READ,
                ),
                _Setting(
                    _RUNS,
                    "Default flow",
                    self._flow or "none",
                    f"configured with {_many(self._roles, 'agent')}; chosen with /flow",
                    _READ,
                ),
                _Setting(
                    _PROFILES,
                    "Profiling",
                    _word(self._profile),
                    "profile programs started by runs here",
                    _SWITCH,
                    _NEXT_RUN if self._profile != self._profile_was else "",
                ),
                _Setting(
                    _FORGET,
                    "Forget",
                    _word(self._forget),
                    f"clear saved settings here, across {_many(self._flows, 'flow')}",
                    _SWITCH,
                    _NEXT_LAUNCH if self._forget else "",
                ),
            ]
        return [
            _Setting(
                _SENTRY,
                "Error reports",
                _word(self._sentry),
                "send error reports to humanize",
                _SWITCH,
            ),
            _Setting(
                _SENT,
                "What is sent",
                "",
                "what error reports include and exclude",
                _SAYS,
            ),
            _Setting(
                _DETAILS,
                "Details",
                _word(self._details),
                "show every tool call and all of the thinking",
                _SWITCH,
            ),
            _Setting(
                _BTW,
                "/btw agent",
                self._btw or "the flow's first agent",
                "the agent /btw uses outside a session",
                _PICK,
                _NEXT_BTW if self._btw != self._btw_was else "",
            ),
        ]

    @staticmethod
    def _chip(one: _Setting, *, here: bool) -> tuple[str, int]:
        """What a row says it is set to, as markup, and how many cells that takes.

        A switch is a dot that is filled while it is on; a value picked from a list says it
        is one with the mark a `<select>` has; a row that opens says so; one that is only
        read is only its value.

        Args:
          one: The row.
          here: Whether it is the one under the cursor.

        Returns:
          The markup, and its width.
        """
        if one.kind == _SWITCH:
            dot = "●" if one.value == _YES else "○"
            if one.value == _YES and not here:
                return f"[$success]{dot}[/] {_YES} [$text-muted]▾[/]", len(_YES) + 4
            said = f"{dot} {one.value} ▾"
            return _shade("$text-muted", said, here=here), len(said)
        if one.kind == _PICK:
            said = f"{one.value} ▾"
            return (
                (
                    escape(said)
                    if here
                    else f"[$secondary]{escape(one.value)}[/] [$text-muted]▾[/]"
                ),
                len(said),
            )
        if one.kind == _SAYS:
            return _shade("$text-muted", "▸", here=here), 1
        return _shade("$text-muted", one.value, here=here), len(one.value)

    def _fill_own(self) -> None:
        """Puts up the first or second page: a row per setting, its value at the far end."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = self._settings()
        held = [one.held for one in rows]
        landing = self._was if self._was in held else held[0]
        width = self._width_of(listing)
        options: list[Option | None] = []
        for one in rows:
            here = one.held == landing
            chip, cells = self._chip(one, here=here)
            pad = max(2, width - 2 - len(one.named) - cells)
            if here:
                self._values_at = 1 + len(one.named) + pad
            note = (
                f"{_DOT}{_shade('$warning', one.note, here=here)}" if one.note else ""
            )
            options.append(
                Option(
                    f" [b]{escape(one.named)}[/]{' ' * pad}{chip}\n"
                    f"   {_shade('$text-muted', one.about, here=here)}{note}",
                    id=f"={one.held}",
                )
            )
            options.append(None)
        listing.set_options(options[:-1])
        listing.highlighted = held.index(landing)
        self._was = landing
        self._drawn = listing.highlighted
        self._saving(here=False)
        said = self._said
        if (
            not said
            and self._tab == _EVERYWHERE
            and self._overridden
            and self._sentry == self._sentry_was
        ):
            said = f"{SAYS} is set, overriding this setting for this run"
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        kind = next((one.kind for one in rows if one.held == landing), _READ)
        does = {_SWITCH: "change", _PICK: "choose", _SAYS: "read"}.get(kind)
        self._footed(*((Key("enter", does),) if does else ()), Key("esc", "back"))

    def _row(
        self, at: int, label: str, about: str, *, here: bool, inforce: bool
    ) -> str:
        """One thing on a page's list: its name and what it is, and no number.

        Args:
          at: Which one it is, which a list with a cursor drawn on it has no use for.
          label: What it is called.
          about: The line about it.
          here: Whether the cursor is on it.
          inforce: Whether it is marked as in force.

        Returns:
          The row, as markup.
        """
        del at
        named = f"[b]{escape(label)}[/]" + (
            f" {_shade('$success', _INFORCE, here=here)}" if inforce else ""
        )
        shown = len(label) + (2 if inforce else 0)
        pad = " " * max(1, _LABEL - shown)
        # Wrapped here rather than by the list, so that a second line starts under the first
        # rather than under the name: the column of what each thing is stays a column.
        starts = 1 + max(_LABEL, shown + 1)
        room = max(self._width_of(self.query_one("#choices", OptionList)) - starts, 20)
        lines = textwrap.wrap(about, room) or [""]
        said = f"\n{' ' * starts}".join(
            _shade("$text-muted", line, here=here) for line in lines
        )
        return f" {named}{pad}{said}"

    def _lands(self, atop: Sequence[str], items: Sequence[str]) -> str:
        """Lands the cursor as a page does, and the focus with it on something just added.

        Something added from a button is what somebody wants to look at next, so the focus
        goes back to the list it landed on rather than staying on the button that made it.

        Args:
          atop: What a page would put above its list, which is the bar here.
          items: The things listed, by id.

        Returns:
          The id of the row the cursor goes on.
        """
        aimed = self._aim
        landing = super()._lands(atop, items)
        if aimed and landing == aimed:
            self.call_after_refresh(self.query_one("#choices", OptionList).focus)
        return landing

    def _atop(self, rows: Sequence[tuple[str, str, str]], *, here: str) -> list[Option]:
        """Takes what a page would put above its list as the buttons under it instead.

        Args:
          rows: One `(id, what it is called, the line about it)` apiece.
          here: Where the cursor is, which a button has no use for.

        Returns:
          Nothing to put above the list.
        """
        del here
        self._bar.extend(rows)
        return []

    def _saving(self, *, here: bool) -> Option:
        """Takes the row a page is saved from as the button that saves, at the end of the bar.

        Args:
          here: Where the cursor is, which a button has no use for.

        Returns:
          A row that :meth:`_put` leaves off the list.
        """
        del here
        self._bar.append(
            (
                _SAVE,
                "save",
                "save all changes" if self._holding() else "nothing to save yet",
            )
        )
        return Option("", id=f"={_SAVE}")

    def _put(self, listing: OptionList, rows: list[Option], landing: str) -> None:
        """Puts the things listed up, and none of the rows about them, which are buttons.

        The headings a list is grouped under are drawn in the list's own left margin, and the
        cursor lands on the first thing listed where what it was to land on is a button.

        Args:
          listing: The list.
          rows: The rows, as the page built them.
          landing: The id of the row the cursor goes on.
        """
        kept: list[Option] = []
        for one in rows:
            held = str(one.id or "").removeprefix("=")
            if held in _APART:
                continue
            if one.disabled and one.id is None and str(one.prompt):
                one = Option(f" {str(one.prompt).removeprefix(_INDENT)}", disabled=True)  # noqa: PLW2901
            kept.append(one)
        listing.set_options(kept)
        listing.highlighted = next(
            (at for at, one in enumerate(kept) if one.id == f"={landing}"),
            next((at for at, one in enumerate(kept) if not one.disabled), None),
        )

    def _shows_bar(self) -> None:
        """Shows the buttons this page asked for, as it words them, and hides the rest."""
        asked = {held: (label, about) for held, label, about in self._bar}
        for held in _BAR:
            button = self.query_one(f"#{_act(held)}", Button)
            if held not in asked:
                button.display = False
                continue
            label, about = asked[held]
            button.display = True
            button.label = label[:1].upper() + label[1:]
            button.tooltip = about or None
            button.disabled = held == _SAVE and not self._holding()
        self.query_one("#actions", Horizontal).display = bool(asked)
        focus = self.focused
        if isinstance(focus, Button) and (not focus.display or focus.disabled):
            self.query_one("#choices", OptionList).focus()

    def _footed(self, *keys: Key) -> None:
        """Says the keys, for where the focus is as well as for the page.

        Args:
          keys: The page's keys, for its list.
        """
        self._page_keys = keys
        focus = self.focused
        back = Key("esc", "close" if self._home or self._only else "back")
        if isinstance(focus, Input):
            keys = (Key("enter", "to list"), Key("esc", "clear"))
        elif isinstance(focus, Button):
            held = f"{_APART_MARK}{(focus.id or '').removeprefix('act-')}"
            keys = (
                Key("enter", _ON_APART.get(held, "press")),
                Key("←/→", "move"),
                Key("tab", "list"),
                back,
            )
        else:
            keys = (
                *(one for one in keys if one.key == "enter"),
                *(
                    (Key("/", "search"),)
                    if any(held == _SEARCH for held, _, _ in self._bar)
                    else ()
                ),
                *(
                    (Key("tab", "actions"),)
                    # A save button with nothing to save cannot be tabbed to.
                    if any(held != _SAVE or self._holding() for held, _, _ in self._bar)
                    else ()
                ),
                back,
            )
        super()._footed(*keys)

    def keys_line(self, keys: Sequence[Key]) -> str:
        """The keys with the key picked out from what it does, as a footer draws them.

        Args:
          keys: The keys.

        Returns:
          The row, as markup.
        """
        return "   ".join(
            f"[b $accent]{escape(one.key)}[/] {escape(one.does)}" for one in keys
        )

    # -- Doing -------------------------------------------------------------------------------

    @on(OptionList.OptionSelected, "#choices")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Goes into the card chosen, or does what enter does on the row chosen.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if self._home:
            self._opens(PAGES.index(held))
            return
        self._takes(held)

    @on(Button.Pressed, "#actions Button")
    def _acted(self, event: Button.Pressed) -> None:
        """Does what the button pressed is for.

        Args:
          event: The press.
        """
        event.stop()
        self._takes(f"{_APART_MARK}{(event.button.id or '').removeprefix('act-')}")

    def _takes(self, held: str) -> None:
        """Does what one row or button is for, which each page says for itself.

        Args:
          held: The row or the button, by the id it answers with.
        """
        if held == _SAVE:
            if self._holding():
                self.applied()
        elif held == _SEARCH:
            self.action_search()
        elif self._tab == _ACCOUNTS:
            self._took_account(held)
        elif self._tab == _MACHINES:
            self._took_machine(held)
        elif self._tab == _FALLBACK:
            self._took_step(held)
        elif self._tab == _VERSES:
            self._took_verse(held)
        elif held == _SENT:
            sent, kept = "; ".join(SENT), "; ".join(KEPT)
            self._said = f"Sent: {sent}. Never sent: {kept}."
            self._fill()
        elif held == _BTW:
            self._chooses_btw()
        elif held in _MEANS:
            self._switches(held)

    def _dropped_at(self) -> Offset:
        """Where the value of the row under the cursor starts, which its list drops under."""
        return anchor(self.query_one("#choices", OptionList)) + Offset(
            self._values_at, 0
        )

    def _switched(self, held: str) -> bool | None:
        """What one switch is held at now."""
        return {
            _SENTRY: self._sentry,
            _DETAILS: self._details,
            _PROFILES: self._profile,
            _FORGET: self._forget,
        }[held]

    @work
    async def _switches(self, held: str) -> None:
        """Asks whether a switch is on or off, from the two dropped under it, and holds it.

        The list opens on the answer it is not, so that enter twice turns it round.

        Args:
          held: The switch, by id.
        """
        if self.opening():
            return
        now = self._switched(held)
        yes, no = _MEANS[held]
        named = next(one.named for one in self._settings() if one.held == held)
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            picked = await showing.push_screen_wait(
                Dropdown(
                    named,
                    [Value(_YES, _YES, yes), Value(_NO, _NO, no)],
                    _word(now) if now is not None else "",
                    at=self._dropped_at(),
                    cursor=_NO if now else _YES,
                )
            )
        finally:
            self.opened()
        if picked is None or (now is not None and picked == _word(now)):
            return
        on_ = picked == _YES
        if held == _SENTRY:
            self._sentry = on_
        elif held == _DETAILS:
            self._details = on_
        elif held == _PROFILES:
            self._profile = on_
        else:
            self._forget = on_
        self._said = ""
        self.changed()
        self._fill()

    @work
    async def _chooses_btw(self) -> None:
        """Asks which agent /btw talks to, from the list dropped under its row, and holds it.

        The flow's first agent, the one chosen already where one is, or another -- set up on
        the sheet every agent is set up on.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            values = [Value("", "the flow's first agent", "whichever it names first")]
            if self._btw:
                values.append(Value(self._btw, self._btw, "chosen"))
            values.append(Value(_ANOTHER, "another…", "set one up"))
            picked = await showing.push_screen_wait(
                Dropdown("/btw agent", values, self._btw, at=self._dropped_at())
            )
            if picked == _ANOTHER:
                chosen = await showing.push_screen_wait(
                    Agent(
                        "btw agent",
                        read_back(self._btw) or Runs(""),
                        self._offered,
                        unavailable=self._unavailable,
                    )
                )
                picked = (
                    written(chosen)
                    if chosen is not None and _complete(chosen)
                    else None
                )
        finally:
            self.opened()
        if picked is None or picked == self._btw:
            return
        self._btw, self._said = picked, ""
        self.changed()
        self._fill()

    def applied(self) -> None:
        """Lands what every page was holding, and answers with what was changed."""
        told = list(self._told)
        self._applies_accounts(told)
        self._applies_steps(told)
        self.dismiss(
            Adjusted(
                enable_sentry=self._sentry
                if self._sentry is not None and self._sentry != self._sentry_was
                else None,
                details=self._details if self._details != self._details_was else None,
                profile=self._profile if self._profile != self._profile_was else None,
                forget=self._forget,
                btw=self._btw if self._btw != self._btw_was else None,
                told=tuple(told),
                placed=self._placed,
            )
        )

    def dismiss(self, result: Adjusted | None = None) -> AwaitComplete:
        """Answers, saying what happened even where nothing held was saved.

        Making an account, saving a machine and fetching a flowverse happen as they are
        asked for, so a menu walked out of without saving -- or with what it held thrown
        away -- still has something to say about them. And it is said to the interface as
        well as answered, since the interface is what applies the rest.

        Args:
          result: What the menu is answered with, or None for nothing held.

        Returns:
          The waiting, as a sheet's own is.
        """
        said = result or (
            Adjusted(told=tuple(self._told), placed=self._placed)
            if self._told
            else None
        )
        if said is not None and not self._answered:
            showing = cast(
                "App[None]",
                self.app,  # pyright: ignore[reportUnknownMemberType]
            )
            showing.post_message(self.Settled(said))
        return super().dismiss(said)
