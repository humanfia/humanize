"""The sheets: which flow, how it is set up, what each of its agents runs, and how it goes.

Drawn as Claude Code draws its own `/model`, which is the same question one step along: a rule
of `▔` across the top, the question and a line about it indented three, the choices numbered
with `❯` against the one under the cursor and a `✔` against the one already in force, and
under them the one setting that is adjusted rather than chosen -- the effort -- on a line the
left and right arrows move along.

Two things are said in one place for the whole file. The keys are said at the bottom and
nowhere else: :meth:`Sheet._footed` builds that row, so that `no key said twice on one sheet`
is a rule about the whole row rather than about any line of it -- a sheet that wrote its own
had no way of knowing it had said `esc` in the line about itself and `esc` again at the
bottom. And whatever is to be done about a list rather than picked out of it -- saving what
the menu holds, adding one more of what the list is of, being rid of what the sheet is about
-- is a row set apart from the choices and out of their numbering: numbered among them, saving
read as one more thing to pick, and a menu whose way out looks like one of its answers is a
menu nobody can see the way out of. On the pages of `/settings` what is done about a list is
above it and saving below everything, so that each page is laid out as the last one was.

A flow is set up by role: each agent role it declares is a CLI, an account, a model and an
effort (:class:`Agent`); each environment role is where it is, written as `-e` writes it; and
beside them are the flow's own params and what a run of it may spend. The order of one agent's
rows is the order of what depends on what: an account belongs to a backend and a model belongs
to the CLI that runs it, so neither can be asked before the CLI has been. The backends are read
one at a time, a tab apiece: the ones installed here plus an optional one the sheet can teach
somebody to install. Every model of
every CLI in one list is a list that grows each time any of them ships a model. The effort is
the line with the arrows on it, exactly as Claude Code's is, and beside it the things that
really are side questions about the same agent.

The run itself, drawn, is not a sheet: it is the monitor, a screen of its own in
:mod:`hmz.tui.monitoring`.
"""

from __future__ import annotations

import contextlib
import shlex
import sys
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    Protocol,
    cast,
    get_args,
    get_origin,
    runtime_checkable,
)

from pydantic import BaseModel, Field, field_validator, model_validator
from rich.markup import escape
from textual import events, on, work
from textual.await_complete import AwaitComplete
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.coganchor import backends
from hmz.coganchor.agents import SWARM, driver
from hmz.coganchor.prices import money
from hmz.flows import Budget
from hmz.runtime import telemetry
from hmz.runtime.kept import Runs, read_back, written
from hmz.runtime.telemetry import KEPT, SAYS, SENT

from .discover import installed, ready_to_open
from .monitor import lasting, thousands
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from pydantic.fields import FieldInfo
    from textual.app import App, ComposeResult

    from hmz.coganchor.agents import AgentBase
    from hmz.coganchor.backends import Model, Way

    # Under another name, because `Falls` here is the sheet one account's chain is chosen on
    # and this is the step itself. Two things called the same thing in one file is one of
    # them being read as the other.
    from hmz.coganchor.fallbacks import Falls as Step
    from hmz.coganchor.providers import Provider
    from hmz.daemon import Hmz
    from hmz.runtime.epic import Ran
    from hmz.runtime.flowing import AgentRole, EnvRole, Flowverse, Offer


__all__ = [
    "DETACHES",
    "EVERY",
    "EXPORTED",
    "PAGES",
    "RESUMES",
    "STAYS",
    "STOPS",
    "Account",
    "Accounts",
    "Agent",
    "Catalogue",
    "Chosen",
    "Clis",
    "Configures",
    "Confirms",
    "Declared",
    "Does",
    "Doing",
    "Drafts",
    "Epics",
    "Failing",
    "Fallbacks",
    "Falls",
    "Flows",
    "Flowverses",
    "Held",
    "Holds",
    "Leaves",
    "Picks",
    "Places",
    "Popup",
    "Providers",
    "Sheet",
    "Signing",
    "Signs",
    "Speaks",
    "budget_of",
    "called",
    "declared_of",
    "named_as",
    "opens_on",
    "params_model",
    "params_of",
    "reads",
    "serves",
    "setting",
    "settled",
    "spent",
]


def called(roles: Sequence[str], at: int) -> str:
    """What to call the agent being configured, which every step of configuring it says.

    In one place because it is said in three, and an agent that read as two different things
    between one step and the next would be two.

    Args:
      roles: The agent roles the flow declares, in the order it declares them.
      at: Which of them is being asked about, counting from zero.

    Returns:
      The role, which is what the flow calls it.
    """
    return roles[at] if at < len(roles) else f"agent {at + 1} of {len(roles)}"


#: What Claude Code rules the top of a sheet with, and how far in everything under it sits.
_RULE = "▔"
_INDENT = "   "

#: The dot Claude Code separates the parts of a line with.
_DOT = " · "

#: The marker against the choice under the cursor, and against the one already in force.
_HERE = "❯"
_INFORCE = "✔"

#: What says a row opens onto a sheet of its own, and what says it is cycled where it stands.
#: Two marks because they are the two things a row of a menu can be, and a reader who has to
#: press a key to find out which one they are on is a reader the row did not tell.
_OPENS, _CYCLES = "▸", "↔"

#: What the rows set below the choices are put up under. A numbered row is one of the things
#: the list is asking about; these are what to do about the list itself -- search it, save
#: what it is holding, add one more of what it is of, be rid of what the sheet is about -- so
#: they are set apart, and a sheet that reads which row the cursor is on has to be able to
#: tell them from the answers. Every one of them is a row rather than a letter: a menu has
#: four keys and no more, so whatever a letter used to do is a row the arrows walk to.
#:
#: Each carries a byte no name has in it, because the rows above them are put up under names
#: somebody chose: a flowverse may be called `add` and an account may be called `save`, and
#: one taken for the row below the list is one that can never be opened.
_APART_MARK = "\x1e"
_SAVE = f"{_APART_MARK}save"
_ADD = f"{_APART_MARK}add"
_SEARCH = f"{_APART_MARK}search"
#: Asking again what a list is of: fetching a flowverse again, asking a CLI what it runs.
_AGAIN = f"{_APART_MARK}again"
#: Copying the flow the cursor was last on into this project, and opening where flows come
#: from: the two things the list of flows offers beside picking one.
_FORK = f"{_APART_MARK}fork"
_WHENCE = f"{_APART_MARK}whence"
#: Answering a form with everything written into it: `done`, on every form.
_DONE = f"{_APART_MARK}done"
#: Writing down a CLI of your own that speaks ACP, which is a backend rather than an account
#: and so a row of its own beside the one that adds an account.
_SPEAKS = f"{_APART_MARK}speaks"

#: And what the row that sets what a run may spend answers with. Set apart for the reason
#: saving is: the rows of the flow menu's second page are the agents it drives, and what the
#: run is allowed to cost is not one of them.
_BUDGET = f"{_APART_MARK}budget"

#: What the row that takes a sheet's subject away answers with, on each of the submenus that
#: has one. Where every row of a list opens onto what it is, taking one away belongs in there
#: with everything else about it rather than on a key of the list -- so three sheets grew the
#: same row, and one spelling is one thing for the sheet that opened them to read back.
_TAKES_AWAY = f"{_APART_MARK}take-away"

#: All of them together, for the sheets that keep which row the cursor was on: a row set
#: apart is not one of the things being kept track of, and one taken for one would move the
#: cursor off it the moment it was walked to.
_APART = frozenset(
    {_SAVE, _ADD, _SEARCH, _AGAIN, _FORK, _WHENCE, _DONE, _TAKES_AWAY, _BUDGET, _SPEAKS}
)

#: And what each of them is called, which is both the word on the row and what the row of
#: keys says enter does while the cursor is on it: they are not answers to the question the
#: list is asking, so what enter means on them is not what it means on the rows above them,
#: and a row of keys saying `enter choose` over a row that saves is about some other row.
_ON_APART = {
    _SAVE: "save",
    _ADD: "add",
    _SEARCH: "search",
    _AGAIN: "refresh",
    _FORK: "copy",
    _WHENCE: "open",
    _DONE: "done",
    _TAKES_AWAY: "take it away",
    _BUDGET: "set",
    _SPEAKS: "add",
}

#: The search row, as a row above a list is written down: it draws itself.
_SEEK = (_SEARCH, "search…", "")

#: How wide the column of names is before the line about each one starts. A model id
#: may hold slashes of its own -- Kimi Code's and opencode's are `provider/id` -- and is
#: shown as the CLI is given it, since a name shortened here is not the name of anything.
_LABEL = 26

#: How wide the column of field names under the diagram is, so the values line up beside
#: them.
_FIELD = 18

#: How often the monitor is redrawn, in seconds. It is read while a flow is running, which is
#: the whole point of it: a sheet that froze what it said the moment it opened would be a
#: snapshot of a run, and the run is what is being watched. Twice a second because the clocks
#: on it count in seconds, and a second hand that stutters reads as a run that has stalled.
_LIVE = 0.5


class Held(NamedTuple):
    """What one agent of a running flow is holding, and whether it is the one being read.

    Attributes:
      many: How many conversations it has open, which is none for an agent that has opened
        none and for every agent of a flow that is not running.
      reading: Whether this agent's transcript is the one on the screen. All of its
        conversations are that one transcript, so this is a yes or a no rather than which of
        them: an agent is what is stepped onto, and a loop that opens one conversation a
        turn runs them all down the same screen.
      unread: Whether it has said something since it was last looked at.
      working: Whether any of its conversations has a turn open. Which is the first thing
        somebody looks for with several agents going at once -- who is thinking and who has
        stopped -- and the only one of these that changes by itself.
    """

    many: int = 0
    reading: bool = False
    unread: bool = False
    working: bool = False


#: What says an agent is working and what says it is not. A filled circle and a hollow one:
#: the same two marks the sheets use for what is in force and what is not, and the one thing
#: on this line that moves on its own.
_WORKING, _IDLE = "●", "○"


def _holds(held: Held) -> str:
    """What one agent's conversations say about themselves beside what it runs.

    Args:
      held: What it is holding.

    Returns:
      Whether it is working, how many conversations it has, `reading` for the one whose
      transcript is on the screen and `unread` for one that has said something since it was
      last looked at. Nothing at all for an agent holding none, which is every agent of a
      flow that is not running.
    """
    if not held.many:
        return ""
    said = f"{_WORKING if held.working else _IDLE} {held.many}"
    if held.reading:
        return f"{said}{_DOT}reading"
    return f"{said}{_DOT}unread" if held.unread else said


def reads(
    named: tuple[str, ...], runs: Sequence[Runs], holding: Sequence[Held] = ()
) -> list[str]:
    """One line per agent role a flow declares: what it runs, and what it is holding.

    In one place because it is read in two -- above the prompt while a flow runs, and under
    the monitor before any agent has worked -- and an agent that read as two
    different things in them would be two. What it is holding is only asked for above the
    prompt, that being where a conversation is read and said to; the sheet asks for the same
    line without it, and it says nothing there.

    Args:
      named: The role each of them fills.
      runs: What each of them runs.
      holding: The conversations each of them has open, in the same order, or nothing at all
        for a flow that is not running -- which holds none.

    Returns:
      One line apiece, in the order the flow takes them.
    """
    return [
        _DOT.join(
            escape(part)
            for part in (
                named[at] if at < len(named) else "",
                one.spec,
                # The account it runs as, where it is not the one this machine is already
                # signed in as -- which is the line saying nothing new.
                one.provider,
                _holds(holding[at]) if at < len(holding) else "",
            )
            if part
        )
        for at, one in enumerate(runs)
    ]


_SHEET = """
Configures, Flows, Form, Models, Providers, RunsAs {
    align: center middle; background: $background; }
#sheet { width: 100%; height: auto; padding: 0; }
#rule { height: 1; color: $primary; }
#asked { padding: 0 0 0 3; text-style: bold; color: $primary; }
#about { padding: 0 3 1 3; color: $text-muted; width: 1fr; }
/* The row above the list: the titles of a sheet that is several pages, and the places a
   list of flows is one of. A sheet with neither says nothing here, and a label with nothing
   in it is a row nobody paid for. */
#tabs { padding: 0 0 1 3; width: 1fr; }
OptionList { border: none; background: $background; scrollbar-size: 0 0; padding: 0; }
/* The marker says where the cursor is, so the row is not filled as well. */
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
/* As wide as the sheet, so that what is said under the list and the keys under that wrap
   onto a second row rather than running off the side of a narrow terminal: a key nobody can
   see is a key nobody has. */
#tuning { padding: 1 0 1 3; width: 1fr; }
#keys { padding: 0 0 0 3; color: $text-muted; width: 1fr; }
/* The fields carry their own indent, as the numbered rows above them do. */
#said { padding: 0 0 1 0; }
"""


#: The one question that is not a sheet: a box in the middle of the screen, over the menu it
#: is about rather than instead of it. A sheet is walked to and fills the width it is drawn
#: in; this arrives, says one thing, and is answered in a keypress -- so it is drawn as the
#: thing every terminal draws that as, which is a bordered box with the question in it. The
#: parts a sheet has and this has no use for are taken away rather than left blank.
_POPUP = """
Confirms { align: center middle; background: transparent; }
#sheet { width: 66; max-width: 100%; height: auto; padding: 1 2; border: round $primary;
         background: $background; }
#rule { display: none; }
#tuning { display: none; }
#asked { padding: 0; text-style: bold; color: $primary; }
#about { padding: 0 0 1 0; color: $text-muted; width: 1fr; }
OptionList { border: none; background: $background; scrollbar-size: 0 0; padding: 0; }
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
#keys { padding: 1 0 0 0; color: $text-muted; width: 1fr; }
"""


#: The arrows across, as the row of keys says them. A menu has four keys and no more -- the
#: arrows up and down walk the rows, these turn the pages or step between the lists a page is
#: made of, enter opens the row under the cursor or begins changing it, and esc steps back --
#: so nothing about working one has to be known before it is opened. Across is also what
#: changes a row while it is being changed, which is the one time the pages stay put.
_ACROSS = "←/→"

#: The one chord left on any sheet, which breaks the line in the one row that takes a list of
#: them while it is being written: enter keeps what was written, so a line break needs a key
#: of its own. Two spellings because only one of them always arrives -- a terminal reports
#: shift+enter as itself only where it speaks a keyboard protocol that has a way to say so,
#: and `ctrl+j` is a line feed that arrives from every terminal there is.
_CHORD_KEYS = ("shift+enter", "ctrl+j")
_CHORD = "/".join(_CHORD_KEYS)


class Key(NamedTuple):
    """One key of a sheet and what it does, as the row of keys under the list says it.

    Attributes:
      key: The key, spelled as the terminal names it and in the case a keyboard has it in.
      does: What it does, in as few words as it takes. A row of keys is read at a glance
        while the eye is on the list above it, so `open` says what `to open the row under
        the cursor` says and takes a sixth of the width doing it.
    """

    key: str
    does: str


def _said(*keys: Key) -> str:
    """The row of keys under a sheet, built in the one place every sheet builds it.

    In one place because `no key said twice on one sheet` is a rule about the whole row
    rather than about any line of it: a sheet that wrote its own row said `esc` in what it
    had written and said `esc` again in the search it appended to it.

    Args:
      keys: The keys, in the order they are reached for.

    Returns:
      The row, as plain words.
    """
    return _DOT.join(f"{one.key} {one.does}" for one in keys)


#: Which side of a row set apart from the choices the row of air between them goes.
_ABOVE, _BELOW = "above", "below"

#: Where a search sends the cursor once letters have narrowed the list: its first row.
_FIRST = "\x1ffirst"


def _aired(row: str, air: str) -> str:
    """One row with its row of air on the side it goes, or on neither.

    Args:
      row: The row, as markup.
      air: `above`, `below`, or "" for none.

    Returns:
      The row with the air carried in it.
    """
    return f"\n{row}" if air == _ABOVE else f"{row}\n" if air == _BELOW else row


#: The most rows of choices a sheet shows however tall the terminal is: a list longer than
#: this is one that is walked rather than read.
_MOST = 14
#: The fewest it shortens to before giving up. A terminal with no room for three rows has no
#: room for the sheet either, and a list shortened to nothing is not a list.
_LEAST = 3


class Body(Vertical):
    """What a sheet is drawn down, which says when it has grown taller than the terminal.

    A sheet is a question with its keys under it, and the one part of it that can be any
    length is the list in the middle: every flow there is, every model a CLI runs. Drawn as
    tall as it likes, that list pushes the keys off the bottom of a short terminal -- so the
    column says when its height changes and the list is shortened to fit. Resize does not
    bubble, so nothing else would hear about it.
    """

    def on_resize(self) -> None:
        """Tells whoever is holding this column that it is a different height now."""
        sheet = self.screen
        if isinstance(sheet, Sheet):
            sheet.shortens()


class Sheet[T](ModalScreen[T | None]):
    """One question drawn the way Claude Code draws one, answered by picking a line.

    What answering it comes to is the sheet's own: a flow is a name, an agent is what it runs
    and where, and walking out without answering is None wherever it is asked.

    A sheet of several pages says so: the titles are across the top and the arrows across turn
    between them. Pages are what two views of one question are, either of which may be read
    first: turning between them is orientation. What is reached by picking something is not a
    page and is not a tab -- it is opened with enter on the thing it is about and left on esc,
    because a tab between a list and the thing picked out of it reads as a view that was there
    all along, which hides that anything was picked at all.

    Four keys and no more: the arrows up and down walk the rows, the arrows across turn the
    pages, enter opens the row under the cursor and esc steps back. Everything else a sheet
    does is a row of it -- searching, adding, saving -- so that nothing has to be known before
    it is found. A row that is changed where it stands rather than opened is changed the same
    way everywhere: enter begins, the arrows across or typing change it, enter keeps what it
    now says and esc puts back what it said before.
    """

    CSS = _SHEET
    # All of them priority, so that they are taken in the order they were pressed: a key the
    # list under the cursor took for itself would be handled after one the sheet took, and
    # enter then an arrow pressed quickly would turn the page before the row was begun on.
    BINDINGS: ClassVar = [
        Binding("escape", "back", "back", show=False, priority=True),
        Binding("up", "walk(-1)", "up", show=False, priority=True),
        Binding("down", "walk(1)", "down", show=False, priority=True),
        Binding("enter", "enter", "open", show=False, priority=True),
        # Refused where they do nothing -- see :meth:`check_action` -- so that a sheet with no
        # pages and nothing being changed lets them fall through.
        Binding("left", "across(-1)", "back one", show=False, priority=True),
        Binding("right", "across(1)", "on one", show=False, priority=True),
    ]

    #: The parallel pages this sheet is, in the order they are turned between: nothing at all
    #: for a sheet that is one page, and for one whose deeper view is opened rather than
    #: turned to. A sheet with tabs shows their titles whether or not there are two: a page
    #: nobody can see the name of is a page nobody knows they are on.
    TABS: ClassVar[tuple[str, ...]] = ()

    #: Which row the marker was last drawn against. Putting the rows up moves the cursor,
    #: which asks for them to be put up again -- and the message saying so is posted rather
    #: than called, so a flag set around the drawing is already clear by the time it arrives.
    #: What breaks the loop is having nothing to do: the marker is already where it goes.
    _drawn: int | None = None
    #: How many columns the numbering takes, so that every row starts in the same one.
    _counting = 1
    #: What has been typed to narrow the list down. A list of every model of every CLI is
    #: longer than a screen, and a list you walk to the end of to find one thing is one you
    #: read rather than use -- so there is somewhere for the letters to go.
    _typed: str = ""
    #: Where the next search moved the cursor to, for a list whose search row is above it --
    #: see :meth:`_sought` -- or "" where it moved nothing.
    _seek = ""
    #: Whether the letters are going there now. Asked for rather than assumed, from the row
    #: that says `search`: a sheet where typing always searched would be one where a stray
    #: letter quietly emptied the list.
    _searching = False
    #: Which row is being changed, by its id, or "" while none is. Changing one is begun on
    #: purpose, with enter, so that walking past a row can never change it.
    _editing = ""
    #: What the sheet held before that row was begun on, which esc puts back.
    _before: object = None
    #: Which page is open, counting the tabs.
    _tab = 0
    #: How many rows of choices there is room for, or None before it has been worked out.
    #: Kept so that working it out again changes nothing where nothing has changed: setting
    #: it is what changes the height that asks for it to be worked out.
    _room: int | None = None
    #: Whether this sheet has answered already. A key pressed twice before the first press
    #: has been handled is two answers to one question, and the second of them pops the sheet
    #: underneath this one -- which is a crash on the first start, where the question about
    #: reporting is the only thing on the stack.
    _answered = False
    #: And whether a walk out of a row of this sheet is already open. The same two presses on
    #: a row that opens something rather than answering are two walks started, one stacked on
    #: the other -- and the second is answered by somebody who thought they were answering the
    #: first. See :meth:`opening`.
    _walking = False

    #: What this sheet has put on letter keys, by action. They are the sheet's keys only
    #: while nothing is being typed into a search -- see :meth:`check_action`. No menu has
    #: any; what is drawn of a run rather than asked has.
    LETTERS: ClassVar[frozenset[str]] = frozenset()

    #: Whether this sheet's list is long enough to be searched, which gives it the row that
    #: starts one.
    SEARCHES: ClassVar[bool] = False

    #: Whether the arrows across step between lists of this one page, for a sheet that has
    #: them instead of pages.
    ASIDE: ClassVar[bool] = False

    #: What the row that answers a form is called, for a sheet that is one. The same word on
    #: every form, so that the way out of one is found where it was found on the last.
    DONE: ClassVar[str] = "done"

    #: Whether typing on a row that is written begins writing it, which a form's rows are:
    #: a letter on a sheet of questions can only be an answer, so the enter that used to
    #: begin one was a keypress spent saying so.
    TYPES: ClassVar[bool] = False

    #: The keys this sheet last said it had, as :meth:`_footed` drew them.
    _keyed: tuple[Key, ...] = ()

    #: The most rows this sheet's list may grow to before the terminal is what limits it.
    #: `_MOST` for a sheet that asks a question, since a list longer than that is one that is
    #: walked rather than read; a sheet whose list is a picture of a run says otherwise.
    TALLEST: ClassVar[int] = _MOST

    def turnable(self) -> tuple[bool, ...]:
        """Which pages may be opened now, which is not always all of them.

        Returns:
          One per tab, in the order they go. All of them unless a sheet says otherwise -- a
          page that cannot be opened is one the tabs step over and one the titles say is
          shut, rather than one that is not there at all.
        """
        return tuple(True for _ in self.TABS)

    def _turns(self) -> bool:
        """Whether this sheet has more than one page open to turn between."""
        return sum(self.turnable()) > 1

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002 -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of this sheet's own keys is live now.

        The arrows across only where they do something: while a row is being changed, on a
        sheet of pages, and on a sheet whose one page is several lists. Anywhere else they are
        refused, so that they fall through to whatever is under the sheet rather than being
        swallowed by it. And a key that is a letter is the sheet's only while nothing is being
        typed into a search.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it. A binding refused here is one the key falls through.
        """
        if action == "across":
            if self._editing:
                return self.steps(self._editing)
            return self._turns() or self.ASIDE
        if action in ("walk", "enter"):
            return bool(self.query("#choices"))
        return not (self._searching and action in self.LETTERS)

    def action_walk(self, by: int) -> None:
        """Walks the cursor a row up or down, unless the row it is on is being changed.

        Args:
          by: One row down, or one up.
        """
        listing = self.query_one("#choices", OptionList)
        if by < 0:
            listing.action_cursor_up()
        else:
            listing.action_cursor_down()

    def action_enter(self) -> None:
        """Opens the row under the cursor, or begins or keeps changing it -- see :meth:`pressed`."""
        self.query_one("#choices", OptionList).action_select()

    def action_across(self, by: int) -> None:
        """Changes the row being changed, or turns the page, or steps to the next list.

        Args:
          by: One on, or one back.
        """
        if self._editing:
            self.step(self._editing, by)
            self._fill()
        elif self._turns():
            self._turn_page(by)
        else:
            self.aside(by)

    def aside(self, by: int) -> None:
        """Steps to another of the lists this page is made of, for a sheet that has them.

        Args:
          by: One on, or one back.
        """

    def editable(self, row: str) -> bool:
        """Whether a row is changed where it stands rather than opened, which each sheet says.

        Args:
          row: The row, by id.

        Returns:
          True for one that enter begins changing.
        """
        del row
        return False

    def steps(self, row: str) -> bool:
        """Whether the arrows across change a row, rather than only typing does.

        Args:
          row: The row, by id.

        Returns:
          True for a switch, a rung, or anything else that moves along.
        """
        return self.editable(row)

    def step(self, row: str, by: int) -> None:
        """Moves a row being changed one along, which each sheet says for itself.

        Args:
          row: The row, by id.
          by: One on, or one back.
        """

    def writes(self, row: str, event: events.Key) -> bool:
        """Types one key into a row being changed, for a row that is written.

        Args:
          row: The row, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        del row, event
        return False

    def held(self) -> object:
        """Everything a row of this sheet can be changed to, as esc would put it back.

        Returns:
          Something :meth:`put_back` takes back, and that compares equal while nothing moved.
        """
        return None

    def put_back(self, was: object) -> None:
        """Puts back what :meth:`held` answered, which is esc while a row is being changed.

        Args:
          was: What it answered.
        """

    def edited(self) -> None:
        """Says a row was changed and kept, which a menu holding changes takes note of."""

    def kept(self, row: str) -> None:
        """Says a row was kept, which a form answers by moving on to the next question.

        Args:
          row: The row, by id.
        """

    def written(self, row: str) -> bool:
        """Whether a row is one typing begins writing, which only a form's written rows are.

        Args:
          row: The row, by id.

        Returns:
          True for a row changed where it stands by typing rather than by the arrows.
        """
        return self.TYPES and self.editable(row) and not self.steps(row)

    def pressed(self) -> bool:
        """Takes enter where it begins or ends changing a row, or starts a search.

        Asked by the list before it picks the row under the cursor, whether enter was pressed
        or the row was clicked: enter on a row that is changed where it stands begins changing
        it and does not pick it, and enter while one is being changed keeps what it now says.

        Returns:
          True where that is what enter was, and the row is not to be picked.
        """
        if self._editing:
            row, self._editing = self._editing, ""
            if self.held() != self._before:
                self.edited()
            self.kept(row)
            self._fill()
            return True
        row = self.under()
        if row == _SEARCH:
            if not self._searching:
                self.action_search()
            return True
        if self.editable(row):
            self._editing, self._before = row, self.held()
            self._fill()
            return True
        return False

    def _turn_page(self, by: int) -> None:
        """Turns to the next page that may be opened, wrapping round at either end.

        Nothing is applied on the way: a menu is answered once, when it is left, so turning a
        page is reading rather than choosing.

        Args:
          by: One page forward or back.
        """
        able = self.turnable()
        if sum(able) < 2:  # noqa: PLR2004 -- one page is nowhere to turn to
            return
        at = self._tab
        for _ in range(len(self.TABS)):
            at = (at + by) % len(self.TABS)
            if able[at]:
                break
        if at == self._tab:
            return
        self._tab = at
        # What was typed goes with the page it was typed into, as it goes with a tab
        # anywhere else: a search that narrowed one page to one row would narrow the next to
        # none, which reads as a page with nothing in it rather than as a search still on.
        self._typed, self._searching = "", False
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()

    def _tab_line(self) -> str:
        """The titles, with the one being read marked and the shut ones struck through."""
        if not self.TABS:
            return ""
        able = self.turnable()
        return _DOT.join(
            f"[b $primary]{escape(one)}[/]"
            if at == self._tab
            else f"[$text-muted]{escape(one)}[/]"
            if able[at]
            else f"[$text-muted][s]{escape(one)}[/s][/]"
            for at, one in enumerate(self.TABS)
        )

    def action_search(self) -> None:
        """Starts narrowing the list by what is typed, until esc says to stop."""
        self._searching = True
        self.query_one("#choices", OptionList).highlighted = 0
        self._seek = _SEARCH
        self._drawn = 0
        self._fill()

    def _sought(self, items: Sequence[str]) -> str | None:
        """Where a search puts the cursor, on a list whose search row is above it.

        On the search row as it starts, so the letters are seen landing where they go, and
        on the first thing they found once they have found something: enter then takes the
        best of what is left, as it does on a list whose rows are below it.

        Args:
          items: The things listed, by id, as the search has narrowed them.

        Returns:
          The id of the row to land on -- which may be "", an answer like any other -- or None
          where the search moved nothing.
        """
        seek, self._seek = self._seek, ""
        if seek == _FIRST:
            return items[0] if items else _SEARCH
        return seek or None

    def fits(self, *fields: str) -> bool:
        """Whether a row is one of the ones still worth showing.

        Args:
          fields: Everything the row says, which is all of it that is searched: what a thing
            is called, and where it came from.

        Returns:
          True if what has been typed is spread through one of them in order, so that a few
          letters anywhere in a name find it -- nobody types a model id out to narrow a list
          of them. One of them rather than all of them run together, or a search would run
          off the end of the name it was narrowing to and finish itself in the word beside
          it: `chat` would find `flame_chase builtin`, which is a match nobody typed.
        """
        if not self._typed:
            return True
        wanted = self._typed.lower()
        for field in fields:
            looking, at = field.lower(), 0
            for letter in wanted:
                at = looking.find(letter, at) + 1
                if not at:
                    break
            else:
                return True
        return False

    def _seeking(self, *, here: bool, air: str = _ABOVE) -> Option:
        """The row a search is started from, which says what has been typed once one is.

        With the block the next letter lands on, so that a search nothing has been typed into
        yet still looks like one.

        Args:
          here: Whether the cursor is on it.
          air: Which side of it the row of air goes -- see :meth:`_apart`.

        Returns:
          The row.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        typed = (
            f"   [$secondary]{escape(self._typed)}[/][reverse] [/reverse]"
            if self._searching
            else ""
        )
        return Option(
            _aired(
                f"{mark}{' ' * (self._counting + 2)}[$primary]search…[/]{typed}", air
            ),
            id=f"={_SEARCH}",
        )

    def _atop(self, rows: Sequence[tuple[str, str, str]], *, here: str) -> list[Option]:
        """The rows about a list, put above it, with a row of air between them and it.

        Above rather than below, on every page of `/settings`: what is done about a list --
        adding to it, searching it, bringing more into it -- is found in the same place on
        each of them, and on a list that is empty it is the whole of the page.

        Args:
          rows: One `(id, what it is called, the line about it)` apiece, in order.
          here: The id of the row the cursor is on.

        Returns:
          The rows.
        """
        made: list[Option] = []
        for at, (held, label, about) in enumerate(rows):
            air = _BELOW if at == len(rows) - 1 else ""
            made.append(
                self._seeking(here=held == here, air=air)
                if held == _SEARCH
                else Option(
                    self._apart(label, about, here=held == here, air=air),
                    id=f"={held}",
                )
            )
        return made

    def _footed(self, *keys: Key) -> None:
        """Puts the row of keys under the list, which is where this sheet's keys are said.

        Every sheet writes its row here rather than building one of its own, because the rule
        that matters about it is a rule about the whole row: a key said once in the line
        about the sheet and again at the bottom is a key said twice, and a sheet that built
        its own row had no way of knowing it had done that.

        The row says what the keys do *now*. While a row is being changed that is changing
        it and nothing else. Otherwise enter is what the row under the cursor is, the arrows
        across turn the pages where there are pages, and esc comes out of a running search
        before it leaves the sheet.

        Args:
          keys: This sheet's keys, in the order they are reached for.
        """
        if self._editing:
            keys = (
                # The one chord, which only a row being written that takes a list has.
                *(one for one in keys if one.key == _CHORD),
                *((Key(_ACROSS, "change"),) if self.steps(self._editing) else ()),
                Key("enter", "keep"),
                Key("esc", "undo"),
            )
        else:
            under = self.under() if self.query("#choices") else ""
            apart = under if under in _APART else ""
            said = (
                self.DONE
                if apart == _DONE
                else _ON_APART.get(apart)
                or ("change" if under and self.editable(under) else None)
            )
            if under and self.written(under):
                # Typing is what writes it, so typing is what the row of keys says: enter
                # begins it as well, which is the same thing done the long way round.
                keys = (
                    Key("type", "to write"),
                    *(one for one in keys if one.key != "enter"),
                )
            elif said:
                keys = (
                    Key("enter", said),
                    *(one for one in keys if one.key != "enter"),
                )
            if self._turns() and all(one.key != _ACROSS for one in keys):
                keys = (
                    *(one for one in keys if one.key != "esc"),
                    Key(_ACROSS, "page"),
                    *(one for one in keys if one.key == "esc"),
                )
            if self._searching:
                keys = (
                    *(one for one in keys if one.key != "esc"),
                    Key("esc", "leave search"),
                )
        # Kept as well as drawn, so that `no key twice on one sheet` is a thing a test can
        # read off the sheet rather than pick back out of a line of markup.
        self._keyed = keys
        self.query_one("#keys", Label).update(_said(*keys))

    def on_key(self, event: events.Key) -> None:
        """Takes a key as writing the row being changed, or as narrowing the list.

        Narrowing only once a search has been asked for, and writing only once a row has been
        begun on: a list where typing always did either is one where a stray letter changes
        something nobody meant to. The arrows walk it and enter takes what is under the
        cursor, either way.

        Args:
          event: The key.
        """
        if self._editing:
            if self.writes(self._editing, event):
                event.prevent_default()
                event.stop()
                self._fill()
            return
        row = "" if self._searching else self.under()
        if (
            row
            and self.written(row)
            and (event.key == "backspace" or (event.is_printable and event.character))
        ):
            # A letter on a written row of a form begins writing it, and is the first letter
            # of what is written: begun exactly as enter begins it, so esc puts it back.
            self._editing, self._before = row, self.held()
            self.writes(row, event)
            event.prevent_default()
            event.stop()
            self._fill()
            return
        if not self._searching:
            return
        if event.key == "backspace":
            self._typed = self._typed[:-1]
        elif event.is_printable and event.character:
            self._typed += event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self.query_one("#choices", OptionList).highlighted = 0
        self._seek = _FIRST
        self._drawn = 0
        self._fill()

    def compose(self) -> ComposeResult:
        """The rule, the question, the tabs, what there is to choose, what is tuned, the keys.

        Every sheet is made of the same parts whether or not it uses them. The tabs are the
        one part that is taken away again where a sheet has none -- see :meth:`tabbed` -- so
        that a sheet which is one list is drawn as one list and nothing moved down a row.
        """
        with Body(id="sheet"):
            yield Label(id="rule")
            yield Label(id="asked")
            yield Label(id="about")
            yield Label(id="tabs")
            yield Choices(id="choices")
            yield Label(id="tuning")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Rules the top of the sheet across, and asks."""
        self.query_one("#choices", OptionList).styles.max_height = self.TALLEST
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        # The titles where there are any, and gone rather than blank where there are not: a
        # label with nothing in it still takes the row it is padded to, and a sheet that is
        # one page must be drawn exactly as it was before any sheet had two.
        self.tabbed(self._tab_line())
        self._ask()

    def tabbed(self, said: str) -> None:
        """Puts the row above the choices up, or takes it back where there is nothing for it.

        Args:
          said: The titles of the pages, or whatever else a sheet says the list is one of, as
            markup -- and "" for a sheet that is one list of one thing.
        """
        showing = self.query_one("#tabs", Label)
        showing.display = bool(said)
        showing.update(said)

    def on_resize(self) -> None:
        """Rules the new width across, and shortens the list to the room left under it."""
        if not self.query("#sheet"):
            return  # resized before there is anything on it, which is nothing to fit
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        self.shortens()

    def shortens(self) -> None:
        """Shortens the list until what is under it is inside the terminal.

        The list is what gives. Everything else on a sheet is a line or two -- what is being
        asked, what it comes to, the keys -- and the rows are what there are a hundred of, so
        a sheet that does not fit is a sheet whose list is too long for the terminal it is
        drawn in rather than a sheet with too much on it. The keys are the last row, so they
        are what falls off the bottom, and a key nobody can see is a key nobody has.

        Called each time the column changes height, which is each time the list is put up
        again, and each time the terminal changes size. It settles at once: how tall the rest
        of the sheet is does not depend on how many rows the list is showing.
        """
        listing = self.query_one("#choices", OptionList)
        column = self.query_one("#sheet", Body).outer_size.height
        rest = column - listing.outer_size.height
        room = max(_LEAST, min(self.TALLEST, self.size.height - rest))
        if room == self._room:
            return
        self._room = room
        listing.styles.max_height = room

    def action_back(self) -> None:
        """Puts back the row being changed, or comes out of the search, or leaves.

        A row being changed and a search are the two places esc has something to step back
        to: leaving from either would throw away the walk in as well as the wrong letters.
        """
        if self._editing:
            self.put_back(self._before)
            self._editing = ""
            self._fill()
            return
        if self._searching:
            self._searching, self._typed = False, ""
            if self.under() == _SEARCH:
                # Back on the rows, which the search is not one of.
                self.query_one("#choices", OptionList).highlighted = 0
                self._seek = _FIRST
            self._drawn = 0
            self._fill()
            return
        self.leaving()

    def leaving(self) -> None:
        """What esc comes to once there is no search to leave, which is walking out.

        A sheet holding changes that have not been applied says something else here -- see
        :class:`Drafts` -- because walking out of one of those is a decision rather than a
        step back.
        """
        self.dismiss(None)

    def _row(
        self,
        at: int,
        label: str,
        about: str,
        *,
        here: bool,
        inforce: bool,
    ) -> str:
        """One numbered choice, laid out as Claude Code lays one out.

        Args:
          at: Which one it is, counting from zero.
          label: What it is called.
          about: The line about it, which is said quietly.
          here: Whether the cursor is on it.
          inforce: Whether it is the one already in force.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        # Right-aligned, so that the tenth row starts where the ninth does.
        number = f"{at + 1:>{self._counting}}."
        named = escape(label) + (f" [$success]{_INFORCE}[/]" if inforce else "")
        # Padded on what is shown rather than on what is written: markup is not columns.
        pad = " " * max(
            1,
            _LABEL - len(label) - (2 if inforce else 0),
        )
        return (
            f"{mark}[$text-muted]{number}[/] {named}{pad}"
            f"[$text-muted]{escape(about)}[/]"
        )

    def _apart(
        self, label: str, about: str = "", *, here: bool, air: str = _ABOVE
    ) -> str:
        """One row set apart from the choices rather than among them.

        For the things that are not answers to the question the list is asking: saving what
        the menu is holding, adding one more of whatever the list is of, being rid of what
        the sheet is about. Numbered among the choices, saving read as one more thing to
        pick -- and a menu whose way out looks like one of its answers is a menu nobody can
        see the way out of.

        The row of air between it and the choices is carried in the row itself rather than
        being a row of its own: a blank row is somewhere the cursor can land.

        Args:
          label: What it is called.
          about: The line about it, said quietly, or "" for one that says itself.
          here: Whether the cursor is on it.
          air: Whether the row of air goes above it, which is where it goes for the rows below
            a list, below it, for the last of the rows above one, or nowhere, for a row with
            another of its kind on the side the choices are.

        Returns:
          The row, as markup: out of the numbering, so that nothing about it reads as one of
          the answers beside it.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        # Padded on what is shown rather than on what is written: markup is not columns.
        pad = " " * max(1, _LABEL - len(label))
        return _aired(
            f"{mark}{' ' * (self._counting + 2)}[$primary]{escape(label)}[/]"
            + (f"{pad}[$text-muted]{escape(about)}[/]" if about else ""),
            air,
        )

    def _adding(self, about: str, *, here: bool) -> Option:
        """The row one more of whatever the list is of is added from.

        A row rather than a letter, for the reason saving is one: a key advertised at the
        bottom of the screen is a key somebody has to read the bottom of the screen to find.
        So adding is a thing on the list, where the arrows reach it.

        Args:
          about: What gets added, in a word or two.
          here: Whether the cursor is on it.

        Returns:
          The row.
        """
        return Option(self._apart(_ON_APART[_ADD], about, here=here), id=f"={_ADD}")

    @on(OptionList.OptionHighlighted)
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Redraws, so the marker sits beside the row the cursor moved to.

        Only when it has moved somewhere the marker is not already: putting the rows up sets
        the cursor, which posts one of these, and redrawing on that would be one keypress and
        renders without end -- which is what a list that lags is.

        Args:
          event: Where the cursor is now.
        """
        if event.option_index == self._drawn:
            return
        self._drawn = event.option_index
        self._fill()

    def under(self) -> str:
        """What the cursor is on, by the id the row was put up under.

        Returns:
          The id, less the `=` a row whose answer may be the empty string carries, or "" for
          a list with nothing in it and for a cursor sitting on a heading.
        """
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "").removeprefix("=")

    def apart(self) -> str:
        """Which of the rows set below the choices the cursor is on, or "" for none of them.

        The id of the row, for a sheet whose rows are put up under what they answer with --
        which is nearly all of them. A sheet that puts them up under something else says so
        for itself, so that the row of keys can still say what enter does on one.

        Returns:
          One of :data:`_APART`, or "".
        """
        held = self.under()
        return held if held in _APART else ""

    def opening(self) -> bool:
        """Whether a walk out of this sheet is already open, so this press is a second at it.

        The list posts one message per keypress, so enter pressed twice before the first has
        been handled starts the walk twice: two sheets stacked on this one, and the second of
        them answered by somebody who believed they were answering the first. The first press
        is the one that counts, and the flag goes down when what it opened comes back.

        Returns:
          True where one is already open, which is a press to ignore.
        """
        if self._walking:
            return True
        self._walking = True
        return False

    def opened(self) -> None:
        """Says the walk is back, so the row is a row to press again."""
        self._walking = False

    def dismiss(self, result: T | None = None) -> AwaitComplete:
        """Answers the question, and only ever once.

        Two answers to one question is what enter pressed twice before the first press has
        been handled comes to: the list posts one message per press, both are handled, and
        the second pops the sheet underneath this one. On the first start, where the question
        about reporting is the only thing over the interface, that second pop is a crash.

        Args:
          result: What the sheet is answered with.

        Returns:
          The waiting, as Textual's own does -- and a waiting on nothing for a second answer,
          there being nothing left to pop.
        """
        if self._answered:
            return AwaitComplete()
        self._answered = True
        return super().dismiss(result)

    def _fill(self) -> None:
        """Puts the choices up, which each sheet says for itself."""
        raise NotImplementedError

    def _ask(self) -> None:
        """Draws whatever is being asked for now, which each sheet says for itself."""
        raise NotImplementedError


#: What the sheet that asks about unsaved changes answers with.
_KEEP, _DROP = "keep", "drop"


class Drafts[T](Sheet[T]):
    """A sheet that holds everything changed in it until it is asked to apply the lot.

    Which is what makes several pages one menu: turning a page applies nothing, so what is
    read on the second page is what the first page is holding rather than what is written
    down. Nothing lands until the menu is left and saving is confirmed -- and esc on a menu
    holding changes asks, because walking out of one is a decision rather than a step back.
    Saving is a row of the menu and the answer to that question, and nothing else: a key that
    saved from anywhere would be one more key to know.
    """

    #: Whether anything has been changed since it opened, which is the whole of what esc has
    #: to ask about.
    _changed = False

    def changed(self) -> None:
        """Says that something has been changed, so that esc asks before throwing it away."""
        self._changed = True

    def edited(self) -> None:
        """Takes a row changed and kept as a change the menu is holding."""
        self.changed()

    def applied(self) -> None:
        """Answers with everything held, which each menu says for itself."""
        raise NotImplementedError

    def _saves(self, about: str, *, here: bool) -> Option:
        """The row the menu is saved from, set below the choices rather than among them.

        Below them because it is not one of them: the rows of a menu are the things it is
        asking about, and this is what to do with the lot of them. Numbered among the
        answers it read as one more thing to pick, which is a menu whose way out is hidden in
        plain sight.

        Args:
          about: What lands, in a word or two.
          here: Whether the cursor is on it.

        Returns:
          The row.
        """
        return Option(self._apart(_ON_APART[_SAVE], about, here=here), id=f"={_SAVE}")

    def leaving(self) -> None:
        """Asks whether to save what is held, and does whichever was asked for.

        Nothing at all where nothing was changed: a walk in to look and out again is not a
        question anybody wants asked of them.
        """
        if not self._changed:
            self.dismiss(None)
            return
        self.asks_to_save()

    @work
    async def asks_to_save(self) -> None:
        """Puts the question up, and does what it is answered with."""
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Confirms())
        if said == _KEEP:
            self.applied()
        elif said == _DROP:
            # Answered a menu and then threw the answers away, which is somebody finding out
            # that what they had done was not what they meant to do.
            telemetry.snag("changes-dropped", sheet=type(self).__name__)
            self.dismiss(None)
        # And anything else is staying here, which is what a third answer is for.


class Chosen(NamedTuple):
    """What the flow menu was answered with: what to run, on what, and set up how.

    One answer rather than four, because the menu is one thing answered once: what is held
    on each of its pages lands together when it is saved, or none of it does.

    Attributes:
      flow: The flow to run, by the name it was offered under.
      agents: What each of its agent roles runs, by role.
      envs: Where each of its environment roles is, by role, as `-e` spells one.
      params: What the flow itself is set up with, or None for a flow that takes no params
        and one that was left at its defaults.
      budget: What a run of it may spend, or None for none -- which only a flow humanize
        ships may be run with.
    """

    flow: str
    agents: dict[str, Runs]
    envs: dict[str, str] = {}  # noqa: RUF012 -- a NamedTuple's default, never written to
    params: BaseModel | None = None
    budget: Budget | None = None


class Declared(NamedTuple):
    """What a flow declares that the menu asks about, read once per flow.

    Attributes:
      agents: The agent roles somebody chooses an agent for, in the order the flow declares
        them. An `Outworlder` role is whoever is at this prompt, and is not among them.
      envs: The environment roles somebody names a place for. A `LocalEnv` role is the
        workspace a run is started in, and is not among them either.
      params: What the flow can be set up with.
      unbounded: Whether a run of it needs no budget: a flow humanize ships -- `chat`, a
        conversation, which stops when the person does.
      resumable: Whether a run of it can be picked up where it left off.
      outworlders: The `Outworlder` roles, by name, in the order the flow declares them:
        whoever is at this prompt, once apiece, each with a transcript of what it asks.
    """

    agents: tuple[AgentRole, ...]
    envs: tuple[EnvRole, ...]
    params: type[BaseModel]
    unbounded: bool = False
    resumable: bool = False
    outworlders: tuple[str, ...] = ()

    @property
    def roles(self) -> tuple[str, ...]:
        """The agent roles, by name, in the order the flow declares them."""
        return tuple(one.name for one in self.agents)

    @property
    def places(self) -> tuple[str, ...]:
        """The environment roles, by name, in the order the flow declares them."""
        return tuple(one.name for one in self.envs)


def declared_of(flow: str) -> Declared | None:
    """What a flow declares, or None for a flow that will not load.

    Args:
      flow: The flow, by the name it was offered under -- not by the file that name resolves
        to, since a module may hold several and which of them was asked for is the half after
        the colon.

    Returns:
      Its roles, params and marks, and None where reading the flow raised at all -- which is
      a flow to report rather than a reason for a menu not to draw.
    """
    from hmz.runtime.flowing import builtin, resolved

    try:
        # Loaded once, and asked both questions: loading a flow reads its directory.
        impl = resolved(flow)
        said = impl.describe()
        unbounded = builtin(impl)
    except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
        return None
    return Declared(
        tuple(one for one in said.agents if not one.auto),
        tuple(one for one in said.envs if not one.auto),
        said.params,
        unbounded=unbounded,
        resumable=said.resumable,
        outworlders=tuple(one.name for one in said.agents if one.auto),
    )


def _harness(backend: str) -> str:
    """Which harness a CLI is, as the flow API names it: its own name, or `acp`."""
    from hmz.flows import HarnessKind

    try:
        return HarnessKind(backend).value
    except ValueError:
        return HarnessKind.ACP.value


def serves(backend: str, role: AgentRole | None) -> bool:
    """Whether one CLI could fill an agent role, as a run of the flow would ask it.

    Args:
      backend: The CLI.
      role: What the flow declared of the role, or None for an agent that is no flow's --
        either end of a fallback step, which a flow says nothing about.

    Returns:
      False for a CLI that is not the harness the role names, or that cannot do what the
      role declares it must; True otherwise.
    """
    if role is None:
        return True
    from hmz.flows import HarnessKind
    from hmz.runtime.flowing import HARNESS_CAPABILITIES

    harness = HarnessKind(_harness(backend))
    if role.harness is not None and harness != role.harness:
        return False
    return role.capabilities <= HARNESS_CAPABILITIES[harness]


def opens_on(
    agents: Mapping[str, tuple[Model, ...]], role: AgentRole | None = None
) -> list[Runs]:
    """The one agent to fall back on where nothing has been remembered for a role.

    The first backend installed here that has said what it runs, can be opened without
    further setup and could fill the role, at the first model it named -- which is that CLI's
    own idea of what it runs by default, and the only idea of it worth having. Nothing is
    written down here: a model named in this file would be a model this file was right about
    on the day it was written.

    Args:
      agents: The backends there are, and what each of them says it runs.
      role: What the flow declared of the role, or None for any.

    Returns:
      The one agent, or nothing at all where no backend here has both said what it runs and
      can be opened without further setup.
    """
    where = Path.cwd()
    for backend, found in agents.items():
        if found and serves(backend, role) and ready_to_open(backend, where):
            # Not the hardest effort, which is where the cursor starts: that is the one to
            # reach for, and this is the one to spend before anybody has asked for anything.
            # `high` where the model takes it, which is nearly always -- and the least it
            # does take otherwise, since a model that is offered at three efforts and run at
            # a fourth is a turn its backend refuses before it starts.
            one = found[0]
            # And no effort at all for a model that takes none, which is what a backend
            # whose models carry their own effort in their names says of the rest of them.
            effort = "high" if "high" in one.efforts else ""
            if not effort and one.efforts:
                effort = one.efforts[-1]
            return [Runs(f"{backend}/{one.name}:{backends.written(effort)}")]
    return []


def why_not(flow: str) -> str:
    """Why a flow will not load, in the words of whatever refused it.

    "will not load" on its own is a dead end: the reasons are nothing alike -- a flowverse
    that has not been fetched, a module the flow imports that is not installed, a syntax
    error somebody just wrote, a module holding several flows and none of them named -- and
    each is fixed somewhere else. So the reason is read off the exception rather than
    swallowed, and shown where the flow is picked.

    Read by loading the flow again, which only happens on the path where it has already
    failed: the answer is worth one more read of a file that did not work.

    Args:
      flow: The flow, by the name it was offered under.

    Returns:
      The first line of what was raised, as the type and what it said -- or "" for a flow
      that loads, this being asked only of one that did not.
    """
    try:
        _hmz().flows.declared(flow)
    except Exception as why:  # noqa: BLE001 -- the reason is the answer here
        said = str(why).strip().splitlines()
        first = said[0].strip() if said else ""
        # Its type where it said nothing of its own: `KeyError` alone is thin, and thinner
        # still is a blank line after a colon.
        return first or type(why).__name__
    return ""


def bad(said: str) -> str:
    """One line about something that went wrong, in the colour wrong things are drawn in.

    Written down once and reached for by everything that says one. The lines under a list are
    otherwise all the same grey -- what was fetched, what stays, what goes, and what failed --
    and a failure that reads like a description is a failure nobody sees. Red for what did not
    work and yellow for what did but is worth knowing about, which is :func:`iffy`.

    Args:
      said: The line, already escaped.

    Returns:
      It, marked up, or "" for nothing to say -- an empty line is not a colour.
    """
    return f"[red]{said}[/red]" if said else ""


def iffy(said: str) -> str:
    """One line about something worth knowing, in the colour such things are drawn in.

    Args:
      said: The line, already escaped.

    Returns:
      It, marked up, or "" for nothing to say.
    """
    return f"[yellow]{said}[/yellow]" if said else ""


def _wont_load(flow: str, also: str = "") -> str:
    """What to say about a flow that will not load: which flow, why, and what follows.

    In red, that being what it is: a flow that will not load is the one thing on this menu
    that is wrong rather than merely unset, and a line about it in the same grey as the rest
    is a line that reads as description.

    Args:
      flow: The flow, by the name it was offered under.
      also: What follows from it here, where anything does.

    Returns:
      The line, ready to draw.
    """
    said = f"{escape(flow)} will not load"
    why = why_not(flow)
    if why:
        said += f": {escape(why)}"
    if also:
        said += f"; {also}"
    return bad(said)


def params_model(flow: str) -> type[BaseModel] | None:
    """What a flow can be set up with, where it takes anything at all.

    Args:
      flow: The flow, by name or as a path.

    Returns:
      Its params model, or None for a flow whose params have no fields -- a sheet with
      nothing on it is not a question -- and for one that will not load, which is a flow to
      report where it is run rather than here.
    """
    declared = declared_of(flow)
    if declared is None or not declared.params.model_fields:
        return None
    return declared.params


def params_of(flow: str, kept: Mapping[str, Any]) -> BaseModel | None:
    """How a flow was last set up, read back through the flow's own model rather than trusted.

    Args:
      flow: The flow.
      kept: What was written down for it, field by field.

    Returns:
      What it was set up with, or None for a flow that takes no params, has not been set
      up here, or has since changed enough that what was kept no longer reads -- a settings
      file is a convenience, and one that no longer fits is one to start over from.
    """
    model = params_model(flow)
    if model is None or not kept:
        return None
    try:
        return model.model_validate(dict(kept))
    except Exception:  # noqa: BLE001 -- what was kept no longer fits the flow
        return None


def spent(budget: Budget) -> str:
    """What a budget caps, shortest first, as a row says it.

    Args:
      budget: The budget.

    Returns:
      Each limit it sets -- the time, the output tokens, the money -- and `no limit` for the
      one a conversation runs under, whose one cap is an infinite cost.
    """
    import math

    caps: list[str] = []
    if budget.duration is not None:
        caps.append(lasting(budget.duration.total_seconds()))
    if budget.output_tokens is not None:
        caps.append(f"{thousands(budget.output_tokens)} out")
    if budget.cost is not None and not math.isinf(budget.cost):
        caps.append(money(budget.cost))
    if not caps:
        return "no limit"
    return ", ".join(caps) + ("" if budget.graceful else ", cut mid-turn")


def _spending(held: Budget | None, *, unbounded: bool) -> str:
    """What a run of this flow may spend, said the way a row about it says it.

    Said on the row rather than only inside the sheet it opens, because a budget nobody can
    see without opening something is one nobody checks: the row is where a person finds out
    what the run they are about to start is held to -- or that it is held to nothing yet,
    which is a run that will not start.

    Args:
      held: What was set here, or None for none.
      unbounded: Whether the flow needs none: a conversation, which stops when you do.

    Returns:
      The caps, or what having none comes to.
    """
    if held is None:
        return (
            "none needed; it stops when you stop talking"
            if unbounded
            else "none yet; a run is given one"
        )
    return f"stops at {spent(held)}"


def budget_of(flow: str) -> Budget | None:
    """What a run of one flow here was last set to be allowed to spend.

    Args:
      flow: The flow.

    Returns:
      The budget, or None for a flow nobody has set one for here. What was written down is
      read back rather than trusted, so a settings file somebody edited by hand into
      something that is not a budget is one that asks again.
    """
    kept = _hmz().settings.budget(flow)
    if not kept:
        return None
    try:
        return Budget.model_validate(kept)
    except ValueError:
        return None


def settled(
    runs: Mapping[str, Runs],
    roles: Sequence[AgentRole],
    agents: Mapping[str, tuple[Model, ...]] | None = None,
) -> dict[str, Runs]:
    """One agent per role a flow declares, out of whatever was remembered for it.

    A flow that has grown a role since it was last run here is a flow with a role nothing was
    remembered for, and one that has lost one is a flow with an agent nobody will drive.
    Neither is a reason to start over: what is there is kept, and what is missing falls back
    on the agent the interface opens talking to, where one here could fill that role.

    Args:
      runs: What was remembered, by role.
      roles: What the flow declares now.
      agents: The backends there are, for a role nothing was remembered for, or None where
        there is nothing to fall back on -- which leaves such a role unanswered.

    Returns:
      One agent per role that has one, by role, in the order the flow declares them.
    """
    held: dict[str, Runs] = {}
    for role in roles:
        one = runs.get(role.name)
        if one is None and agents is not None:
            spare = opens_on(agents, role)
            one = spare[0] if spare else None
        if one is not None:
            held[role.name] = one
    return held


def _complete(runs: Runs) -> bool:
    """Whether one agent has been answered at all, which is a CLI and a model of that CLI.

    Args:
      runs: The agent.

    Returns:
      True if there is something to run it on.
    """
    return bool(_cli(runs) and _model(runs))


def _cli(runs: Runs) -> str:
    """Which backend one agent of the menu is driven by, out of what it was set up as.

    Args:
      runs: The agent.

    Returns:
      The CLI, or "" for an agent nobody has answered yet.
    """
    return runs.spec.partition("/")[0]


def _model(runs: Runs) -> str:
    """What one agent of the menu runs, out of the `cli/model:effort` it was set up as.

    Read from both ends, as :func:`hmz.runtime.kept.read_back` reads the same word: a model
    may hold slashes of its own, while a CLI and an effort never do.

    Args:
      runs: The agent.

    Returns:
      The model, or "" for an agent nobody has answered yet.
    """
    return runs.spec.partition("/")[2].rpartition(":")[0]


def placed(role: str, spec: str) -> str:
    """What is wrong with where an environment role was said to be, or "" for nothing.

    Read the way `-e` is read, so that what the menu takes is what a command line would.

    Args:
      role: The role.
      spec: Where it is, as `-e` spells one after `<role>=`.

    Returns:
      Why it is not one, in words, or "" for a spec that reads.
    """
    from hmz.runtime.flowing import SpecError, parse_envs

    try:
        parse_envs([f"{role}={spec}"])
    except SpecError as why:
        return str(why)
    return ""


#: What separates the two halves of a row's id among the flows: which place it came from,
#: and which flow it is. A byte no name has in it, since the second half may hold anything --
#: a flow is offered under the place it came from, and holds a slash and may hold a colon.
_HALVES = "\x1f"


@runtime_checkable
class Lists(Protocol):
    """A sheet holding a list of flows it read off the disk.

    What they have in common is the one thing anything outside them needs: the list was read
    once, reading it means running every flow in it, and a fetch landing underneath makes it
    wrong. This is how such a sheet is told so, without whatever fetched having to know which
    sheets there are or how either of them keeps its list.
    """

    def reread(self) -> None:
        """Drops what was read off the disk and draws the list again."""


class Flows(Drafts[Chosen]):
    """Which flow runs and what each of its agents is: one menu, walked into.

    The flows, and then the agents of the one that was opened. Not two pages turned between:
    a flow is picked out of a list and what drives it is that flow's own, so a tab between
    them would read as a second view that had been there all along -- and which flow's agents
    were being set up would be a thing nobody could see they had chosen. Enter opens a flow
    and esc comes back to the flows, which is what those two keys mean everywhere else here.

    Choosing a flow is not offered at all while one is running: a flow is chosen in order to
    be started, and there is one going. The menu opens inside the agents then, and esc leaves
    rather than stepping back to a list that is not there. Its agents are the other way
    round -- an agent that is thinking too little, on the wrong account, or allowed too much
    is found out halfway through a run -- so they are reachable whatever is happening.

    The flows are read a place at a time -- every flowverse there is, fetched or not, and then
    this project's flows and yours -- with the left and right arrows stepping between the
    places and the list holding only the one being read. All of them run together under
    headings was one list nobody could see the end of, and one where walking to a flow meant
    walking past every flow that came before it. Stepping between the places is about which
    list of flows is being read; what can happen to a flowverse is the menu the row below the
    flows opens, which is a question about the places rather than about which flow to run.

    Choosing a flow asks what that flow itself takes -- its params -- where it takes anything,
    and then opens its roles: a row per agent role somebody chooses an agent for, a row per
    environment role somebody says the place of, what a run of it may spend, and saving. The
    roles the runtime fills -- whoever is at this prompt, the workspace a run starts in -- are
    not rows: nobody chooses them.

    Nothing is applied by walking in or back out. What the menu holds is a draft of the whole
    of it, and it lands together from the save row or when saving is confirmed on the way out.
    """

    # The places the flows come from: the list walks up and down, so across is what is left
    # for stepping between the lists there are.
    ASIDE: ClassVar = True
    SEARCHES: ClassVar = True

    def __init__(
        self,
        flow: str,
        runs: Mapping[str, Runs],
        params: BaseModel | None,
        agents: dict[str, tuple[Model, ...]],
        kept: dict[str, Any],
        *,
        envs: Mapping[str, str] | None = None,
        budget: Budget | None = None,
        unavailable: frozenset[str] = frozenset(),
        running: bool = False,
        inside: bool = False,
    ) -> None:
        """Initializes the menu on what is set up now.

        Args:
          flow: The flow running now, or the one this workspace is set up to run.
          runs: What each of its agent roles runs, by role.
          params: What the flow itself is set up with, for one that takes params.
          agents: The backends offered here, and what each of them says it runs.
          kept: What each flow was last set up with here, by flow -- read when the draft flow
            changes, so that turning to a flow this workspace has run finds it as it was left.
          envs: Where each of its environment roles is, by role.
          budget: What a run of it may spend here, or None for none yet.
          unavailable: The optional backends among them that still need installing.
          running: Whether a flow is running, which is what takes the flows away.
          inside: Whether to open inside the flow's roles rather than on the flows, for a
            menu opened already naming one -- a flow that was named has been chosen, so what
            is left to answer is what drives it.
        """
        super().__init__()
        self._agents = dict(agents)
        self._unavailable = unavailable
        self._kept = kept
        # Said outright, all of them: the flow is read where it is set, so what it is has to
        # be settled without reading what reads it.
        self._flow: str = flow
        #: What the flow declares, read once per flow rather than on every redraw: reading
        #: it means importing the flow, and the roles page is drawn on every keystroke.
        self._declared: Declared | None = declared_of(flow)
        self._runs: dict[str, Runs]
        self._envs: dict[str, str]
        if runs:
            self._runs = self._fitted(dict(runs))
            self._envs = dict(envs or {})
            self._params = params
            self._budget = budget
        else:
            # A flow the interface is not set up on, opened straight into: what it was last
            # set up with here is what it opens holding, exactly as turning to it would be.
            self._runs = self._fitted(self._remembered(flow))
            self._envs = self._placed(flow)
            self._params = params_of(flow, self._held(flow).get("params") or {})
            self._budget = budget_of(flow)
        #: Every flow there is, read once: this is redrawn on every keystroke, and reading it
        #: means importing each flow to see what it holds. Cleared when a flowverse is
        #: fetched or taken away, which is when the list is something else.
        self._offers: list[Offer] | None = None
        #: Which row of the flows the cursor is on, as `where it came from` and `which flow`:
        #: a place with nothing in it is a row with no flow on it at all, so a row number is
        #: not a flow. Kept whole so that it still says which list it was a row of.
        self._was = ""
        #: Which of the rows below the flows the cursor is on, or "" for one of the flows.
        self._below = ""
        #: Which place's flows are being read, the arrows stepping between them. "" until the
        #: flows are first drawn: which place the flow in force came from is a thing only the
        #: list of every flow there is can say, and reading that list is importing every flow.
        self._where = ""
        #: What became of the last fetch, said under the list.
        self._said = ""
        #: What is being fetched now, so that a second fetch is not started over it and so
        #: that what is said under the list is what is being fetched. "" for none.
        self._fetching = ""
        #: Whether the roles are the whole of this menu, there being no flows behind them to
        #: step back to: while a flow runs choosing one is not offered, and a flow that was
        #: named was chosen on the line that named it rather than picked out of a list. Esc
        #: reads off this -- a step back to a list nobody walked through is a step somebody
        #: did not take, and on a `$` that named a flow it would swallow the line typed with
        #: it.
        self._only = running or inside
        #: Whether what is open is the roles of the flow rather than the flows.
        self._inside = self._only

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],
    ) -> bool | None:
        """Whether one of this sheet's keys is live, which the agents of a flow narrow.

        Not the arrows across inside a flow: the places are about which list of flows is
        being read, and the agents of one come from nowhere but that flow.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it.
        """
        if self._inside and action == "across":
            return False
        return super().check_action(action, parameters)

    def _follows(self, listing: OptionList) -> None:
        """Takes which row the cursor is on off the list, rather than off a row number.

        Read here rather than kept as the cursor moves, so that the two cannot disagree: the
        list is a different list under each place, and the row under the cursor is the only
        thing that says which flow is meant. Kept as the whole id -- where it came from and
        which flow it is -- so that a row remembered under one place cannot be taken for a
        row of the next.

        Only a row that says where it came from, which is what a row of flows is: the list is
        read as the flows are drawn, and coming back out of a flow draws them while its agents
        are still the rows -- so an id with no place in it is a row of some other list, and
        taking it would lose where the cursor was before the walk in.

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return
        named = str(listing.get_option_at_index(at).id or "")
        if _HALVES in named:
            self._was, self._below = named, ""
        elif named.removeprefix("=") in (_SEARCH, _FORK, _WHENCE):
            # Below the flows, where the flow last walked off is the one copying copies.
            self._below = named.removeprefix("=")

    def _fitted(self, runs: Mapping[str, Runs]) -> dict[str, Runs]:
        """One agent per agent role the flow declares, whatever there was to fill it with.

        A role nothing was remembered for and nothing falls back on still has a row: this is
        where it is set up, and a role with no row is a role nobody can answer. What such a
        row holds is an agent that names nothing, which says it has not been answered yet.

        Args:
          runs: What there is, by role.

        Returns:
          One apiece, by role, in the order the flow declares them.
        """
        declared = self._declared
        if declared is None:
            return dict(runs)
        held = settled(runs, declared.agents, self._agents)
        return {role: held.get(role, Runs("")) for role in declared.roles}

    def _held(self, name: str) -> dict[str, Any]:
        """What one flow was last set up with here, which is nothing for one never run."""
        held = self._kept.get(name)
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _remembered(self, name: str) -> dict[str, Runs]:
        """What one flow's agent roles were last set up as here, by role.

        Args:
          name: The flow.

        Returns:
          One agent per role that has one, and nothing at all for a flow this workspace has
          never run -- which is a flow whose agents fall back on the one the interface opens
          talking to.
        """
        from hmz.runtime.kept import read_back

        agents = self._held(name).get("agents")
        if not isinstance(agents, dict):
            return {}
        held: dict[str, Runs] = {}
        for role, said in cast("dict[str, Any]", agents).items():
            runs = read_back(said)
            if runs is not None:
                held[str(role)] = runs
        return held

    def _placed(self, name: str) -> dict[str, str]:
        """Where one flow's environment roles were last said to be here, by role."""
        envs = self._held(name).get("envs")
        if not isinstance(envs, dict):
            return {}
        return {
            str(role): str(said)
            for role, said in cast("dict[str, Any]", envs).items()
            if isinstance(said, str)
        }

    def _ask(self) -> None:
        """Puts up whichever of the two it opened on, and catches up on fetches."""
        self._fill()
        self.query_one("#choices", OptionList).focus()
        self._catches_up()

    @work
    async def _catches_up(self) -> None:
        """Fetches whatever has never been fetched, as the menu opens.

        A flowverse that is here and has never been fetched is a list with nothing in it and
        a key to press about it, which is a step nobody would choose to take: it is here
        because its flows are wanted. humanize's own repository of the rest is the one this
        is ever true of -- one that was added was cloned as it was added -- and it is the one
        every flow that is not in the package is in.

        Off the loop and out of the way: the menu is drawn first and stays drawn, what is
        being read is left where it is, and a fetch that fails says so under the list. Once
        per opening, however it goes, so that a machine with no network says so once rather
        than hammering a server on every keystroke.

        The first fetch only, which is the half of it worth saying something about: a place
        nobody has fetched holds no flows at all, so somebody opening this menu to pick one is
        somebody owed either the list or the reason there is not one. The interface fetches
        every place as it opens, this one included, in the background and silently -- there is
        already a list to show there and nobody waiting on it. Whichever of the two gets there
        first, what the other finds is a place already fetched, and it goes on to the next.
        """
        import asyncio

        verses = _hmz().verses
        for one in verses.all():
            if not one.url or one.fetched:
                continue
            self._fetching, self._said = one.name, ""
            self._fill()
            try:
                await asyncio.to_thread(verses.fetch, one.name)
            except (OSError, ValueError) as why:
                # Said under the list rather than raised at whoever opened the menu: the
                # question the menu is asking is still worth answering.
                self._said = bad(escape(str(why)))
            else:
                self._offers = None  # a place that has flows in it now
            self._fetching = ""
            self._fill()

    def reread(self) -> None:
        """Drops the flows read before a fetch landed, and draws the list again.

        What the flow in force declares too: its module may be one of the ones that just came
        down, and the roles page is drawn off what was read from the old one. A flow that
        would not load before the fetch is exactly the flow this is for.
        """
        self._offers = None
        if self._flow:
            self._declared = declared_of(self._flow)
            self._runs = self._fitted(self._runs)
        self._fill()

    def _walks(self, *, inside: bool) -> None:
        """Opens what drives the flow, or comes back out to the flows.

        What was typed and where the cursor was are left behind either way: the two are
        different lists, so a search that narrowed one to a row would narrow the other to
        none -- which reads as a list with nothing in it rather than as a search still on.

        Args:
          inside: Whether to end up on the agents.
        """
        self._inside = inside
        self._typed, self._searching = "", False
        self._said, self._below = "", ""
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()

    def _fill(self) -> None:
        """Puts up whichever is open: the flows, or the agents of the one walked into."""
        if self._inside:
            # Which flow these drive, said where the menu says what it is asking: a list of
            # agents that did not name its flow would be a list nobody could see they had
            # opened.
            self.query_one("#asked", Label).update(escape(self._flow))
            self.query_one("#about", Label).update(
                "What each of its roles is given: an agent -- the CLI that takes its turns, "
                "the account they run as, and the model at an effort -- or where an "
                "environment is."
            )
            self.tabbed("")
            self._agents_page()
            return
        self.query_one("#asked", Label).update("Flow")
        self.query_one("#about", Label).update(
            "Which flow drives the agents; what it is to do is the next thing you say. A "
            "flow anywhere else is a path you type."
        )
        # The places, since that is what the list under them is one of: settled before either
        # is drawn, so that the strip and the list agree.
        wheres = self._stepping()
        if self._where not in wheres:
            self._where = self._opens(wheres)
        self.tabbed(self._where_line(wheres))
        self._flows_page()

    def _all(self) -> list[Offer]:
        """Every flow there is, read once."""
        if self._offers is None:
            self._offers = _hmz().flows.all()
        return self._offers

    def _wheres(self) -> list[str]:
        """The places flows come from, in the order the arrows step through them.

        Returns:
          Every flowverse there is, fetched or not, except an empty one of your own. A
          flowverse is one of them whether or not it has been downloaded -- fetching it is
          what having it here is for -- but your own directories are not places to fetch
          anything into, so an empty one is nothing to step to.
        """
        from hmz.runtime.flowing import MINE

        return [
            one.name
            for one in _hmz().verses.all()
            if one.name not in MINE
            or any(offer.whose == one.name for offer in self._all())
        ]

    def _stepping(self) -> list[str]:
        """The places there are to step between, which a search narrows to the ones it found.

        Returns:
          Every place while nothing is typed. While something is, only the places holding a
          flow that matches it -- a search is for finding a flow whose flowverse is the thing
          nobody remembers, so it MUST NOT leave somebody stepping through empty lists to
          reach the one row it found. All of them again where it found nothing anywhere,
          there being no narrower list to offer than the one that is already empty.
        """
        wheres = self._wheres()
        if not self._typed:
            return wheres
        found = [
            whose
            for whose in wheres
            if any(one.whose == whose and self.fits(one.name) for one in self._all())
        ]
        return found or wheres

    def _opens(self, wheres: list[str]) -> str:
        """Which place is read when the flows are drawn without one already being read.

        Args:
          wheres: The places there are to step between.

        Returns:
          The one the flow in force came from, that being the flow the menu is about, and
          otherwise the first there is.
        """
        return next(
            (
                one.whose
                for one in self._all()
                if one.name == self._flow and one.whose in wheres
            ),
            wheres[0] if wheres else "",
        )

    def _where_line(self, wheres: list[str]) -> str:
        """The places flows come from, with the one being read marked.

        Args:
          wheres: The places, in the order the arrows step through them.

        Returns:
          The strip, as markup. Every place, so that the one being read is read as one of
          however many there are: a flowverse nobody can see is a flowverse nobody steps to.
        """
        return _DOT.join(
            f"[b $primary]{escape(one)}[/]"
            if one == self._where
            else f"[$text-muted]{escape(one)}[/]"
            for one in wheres
        )

    def _verse(self, named: str) -> Flowverse | None:
        """The flowverse of that name, or None for a name none of them answers to."""
        return _hmz().verses.find(named)

    def aside(self, by: int) -> None:
        """Turns to another of the places flows come from, wrapping round at either end.

        Args:
          by: One place on or back.
        """
        if self._inside:
            return  # the agents of one flow come from nowhere but that flow
        wheres = self._stepping()
        if len(wheres) < 2:  # noqa: PLR2004 -- one place is nowhere to step to
            return
        at = wheres.index(self._where) if self._where in wheres else 0
        self._where = wheres[(at + by) % len(wheres)]
        # What a key was armed against and what a fetch had to say were both about the place
        # being stepped off, and neither is about the one being stepped on to.
        self._was, self._said = "", ""
        self._fill()

    def _flows_page(self) -> None:
        """Puts up the flows of the place being read, and nothing from any other place.

        And below them what else there is to do from here, a row apiece: search every place
        for a flow, copy the flow the cursor was last on into this project, and open where
        flows come from.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        mine = [
            one
            for one in self._all()
            if one.whose == self._where and self.fits(one.name)
        ]
        self._counting = len(str(max(len(mine), 1)))
        held = [f"{self._where}{_HALVES}{one.name}" for one in mine]
        if not held and not self._typed:
            # A place with nothing in it, which for a flowverse is what having it here is
            # for: an empty list that explained nothing would read as one with no flows.
            held = [f"{self._where}{_HALVES}"]
        if self._was not in held:
            # Stepped on to, narrowed away, or never there: the cursor lands on the flow in
            # force, or on the first row, and an empty list has nothing to be on at all.
            self._was = next(
                (one for one in held if one.partition(_HALVES)[2] == self._flow),
                held[0] if held else "",
            )
        rows = [
            Option(
                self._row(
                    at,
                    one.name,
                    _briefly(one.about, self.size.width),
                    here=not self._below and held[at] == self._was,
                    inforce=one.name == self._flow,
                ),
                id=held[at],
            )
            for at, one in enumerate(mine)
        ]
        if not rows and held:
            rows = [
                Option(
                    f"{_INDENT}  [$text-muted]{self._empty(self._where)}[/]", id=held[0]
                )
            ]
        named = self._was.partition(_HALVES)[2]
        below = [_SEARCH, *((_FORK,) if named else ()), _WHENCE]
        if self._below not in below:
            self._below = ""
        rows.append(self._seeking(here=self._below == _SEARCH))
        if named:
            rows.append(
                Option(
                    self._apart(
                        f"copy {named.rpartition('/')[2]} here",
                        "yours to change",
                        here=self._below == _FORK,
                    ),
                    id=f"={_FORK}",
                )
            )
        rows.append(
            Option(
                self._apart(
                    "where flows come from",
                    "flowverses",
                    here=self._below == _WHENCE,
                ),
                id=f"={_WHENCE}",
            )
        )
        listing.set_options(rows)
        listing.highlighted = (
            len(rows) - len(below) + below.index(self._below)
            if self._below
            else held.index(self._was)
            if self._was in held
            else None
        )
        self._drawn = listing.highlighted
        said = self._nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(
            Key("enter", "open"),
            *((Key(_ACROSS, "place"),) if len(self._stepping()) > 1 else ()),
            Key("esc", "close"),
        )

    def _empty(self, whose: str) -> str:
        """What a place with no flows in it says on the row where its flows would be."""
        verse = self._verse(whose)
        if verse is not None and not verse.fetched:
            return "not fetched yet; where flows come from, below, fetches it"
        return "nothing in it yet"

    def _nothing(self) -> str:
        """What to say under the flows: how a fetch went, or that a search found nothing."""
        if self._fetching:
            said = f"fetching {escape(self._fetching)}…"
            # And why a key was refused while it runs, where one was: a key that did nothing
            # and said nothing is a key somebody presses again.
            return f"{said}{_DOT}{self._said}" if self._said else said
        if self._said:
            return self._said
        if self._typed and not any(self.fits(one.name) for one in self._all()):
            return "no flow of that name"
        return ""

    def _roles(self) -> tuple[str, ...]:
        """The agent roles somebody chooses an agent for, in the flow's own order."""
        return self._declared.roles if self._declared is not None else ()

    def _places(self) -> tuple[str, ...]:
        """The environment roles somebody names a place for, in the flow's own order."""
        return self._declared.places if self._declared is not None else ()

    def _agents_page(self) -> None:
        """Puts up each role the flow declares, its budget, and saving the whole setup."""
        listing = self.query_one("#choices", OptionList)
        roles, places = self._roles(), self._places()
        runs = [self._runs.get(role, Runs("")) for role in roles]
        lines = reads(roles, runs)
        # The rows set apart are past the end of the numbering, so what is numbered is the
        # roles: the agents, then the environments.
        count = len(roles) + len(places)
        self._counting = len(str(max(count, 1)))
        # One row past the roles for what a run may spend, and one past that for saving.
        at = min(listing.highlighted or 0, count + 1)
        rows = [
            Option(
                self._row(
                    seen,
                    called(roles, seen),
                    lines[seen].split(_DOT, 1)[-1]
                    if runs[seen].spec
                    else "not chosen yet",
                    here=seen == at,
                    inforce=False,
                ),
                id=f"={seen}",
            )
            for seen in range(len(roles))
        ]
        rows.extend(
            Option(
                self._row(
                    len(roles) + seen,
                    place,
                    self._envs.get(place) or "not said yet",
                    here=len(roles) + seen == at,
                    inforce=False,
                ),
                id=f"=@{place}",
            )
            for seen, place in enumerate(places)
        )
        rows.append(
            Option(
                self._apart(
                    "budget",
                    _spending(
                        self._budget,
                        unbounded=self._declared is not None
                        and self._declared.unbounded,
                    ),
                    here=at == count,
                ),
                id=f"={_BUDGET}",
            )
        )
        rows.append(self._saves("the flow and its roles", here=at == count + 1))
        listing.set_options(rows)
        listing.highlighted = at
        self._drawn = listing.highlighted
        said = self._said or ("" if count else self._noagents())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        # Esc is out of the menu only where there is no list of flows to step back to,
        # which is while a flow is running: the row says what the key does here.
        back = Key("esc", "close" if self._only else "back to the flows")
        # What enter says is read off the row it is on -- `open` over a role, `set` over the
        # budget and `save` over saving, which `Sheet._footed` rewrites from the row set apart.
        self._footed(Key("enter", "open"), back)

    def _noagents(self) -> str:
        """Why there is no role to set up, which is not always the same reason."""
        if self._declared is None:
            return _wont_load(self._flow, "nothing here can be set up")
        return f"{escape(self._flow)} has no role to choose for; it talks only to you"

    @work
    async def _configures(self) -> None:
        """Asks what the flow itself takes, and turns to its roles.

        Which is the moment to ask it: a flow that takes params has just been chosen, and
        what it is set up with is a thing about the flow rather than about its agents. A flow
        that takes none is not asked -- a sheet with nothing on it is not a question -- and
        the walk is the same either way, so nobody has to know which kind they picked.
        """
        model = params_model(self._flow)
        if model is not None:
            showing = cast(
                "App[None]",
                self.app,  # pyright: ignore[reportUnknownMemberType]
            )
            held = await showing.push_screen_wait(
                Configures(
                    self._flow,
                    model,
                    self._params if isinstance(self._params, model) else None,
                )
            )
            if held is not None:
                self._params = held
                self.changed()
            # And walking out of it leaves the flow set up as the draft has it, which is
            # still a flow to go on and answer the roles of.
        self._walks(inside=True)

    @work
    async def _budgets(self) -> None:
        """Asks what a run of this flow may spend, from the row on the roles page.

        A row reached rather than a sheet the walk goes through, because most runs want the
        budget they already have: a page that had to be pressed past on the way to the roles
        would be a question asked of somebody who has answered it. It is not among the
        flow's params because it is a setting of the run: the flow's model would refuse the
        fields, and a budget read back as one of the flow's params is the one mistake this
        must not make.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        spends = await showing.push_screen_wait(
            Configures(
                self._flow,
                Budgeted,
                Budgeted.of(self._budget) if self._budget is not None else None,
                asked=f"What a run of {self._flow} may spend",
                about="A run stops at whichever limit it reaches first; at least one is "
                "set. Empty or 0 is no limit on that one.",
            )
        )
        if isinstance(spends, Budgeted):
            self._budget = spends.budget()
            self.changed()
        self._fill()

    @work
    async def _placing(self, role: str) -> None:
        """Asks where one environment role is, as `-e` says it, and holds the answer.

        Args:
          role: The environment role.
        """
        from pydantic import create_model

        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        model = create_model(
            "Where",
            where=(
                str,
                Field(
                    default="",
                    description="local@/abs/path, or ssh@host/abs/path -- "
                    "ssh@host/~/path under the login's home",
                ),
            ),
        )
        held = await showing.push_screen_wait(
            Configures(
                self._flow,
                model,
                model(where=self._envs.get(role, "")),
                asked=f"Where {role} is",
                about="The machine and the directory this environment role works in, "
                "as -e says one after the role.",
            )
        )
        if held is None:
            return
        said = str(held.model_dump().get("where") or "").strip()
        wrong = placed(role, said) if said else ""
        if wrong:
            self._said = bad(escape(wrong))
        else:
            if said:
                self._envs[role] = said
            else:
                self._envs.pop(role, None)
            self._said = ""
            self.changed()
        self._fill()

    def _forks(self) -> None:
        """Copies the flow the cursor was last on into this project's own, to be changed.

        A flow is a directory, so a copy of one is a flow of yours: the entry point, what it
        imports and the skills it brings all come across, under the name it already had --
        and your own flows are looked in first, so from then on that name means your copy.

        Which is the way to change a flow at all. A flowverse is somebody else's repository,
        fetched again over whatever was written into it, so an edit made there is an edit
        that goes away; a copy here is yours, and is what the row that copies is for.
        """
        from hmz.runtime.flowing import LOCAL

        if self._inside:
            return
        named = self._was.partition(_HALVES)[2]
        if not named:
            self._said = "no flow under the cursor to copy"
            self._fill()
            return
        try:
            at = _hmz().flows.fork(named)
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        # The list is something else now: there is a flow of yours that was not there, and
        # the name it took means it from here on.
        self._offers, self._was, self._below = None, "", ""
        self._where = LOCAL
        mine = escape(named.rpartition("/")[2])
        self._said = (
            f"copied to {escape(at)} -- yours to change, and {mine} now means it"
        )
        self._fill()

    @work
    async def _verses(self) -> None:
        """Opens where flows come from, which is the flowverses page of `/settings`.

        That menu rather than three more rows here, and reached from here rather than from
        `/settings` alone: adding a repository, fetching one again and taking one away are
        done to the list of places rather than to the flow under the cursor. Its own menu for
        a second reason as well -- each of those runs git as it is asked for, and something
        that has already been cloned is not a draft this one could hold until it is saved.

        What comes back is a different list of flows, so they are read again, and what
        happened to the places is said under them.
        """
        if self._inside:
            return  # the agents of one flow come from nowhere but that flow
        if self._fetching:
            # The menu fetches what has never been fetched as it opens, and the other menu
            # fetches what it is asked to: two clones of one flowverse land in one directory,
            # where the second finds the path taken and git's tidying up after itself takes
            # the first one's work away with it.
            self._said = "the places open once it is done"
            self._fill()
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Adjusts(self._agents, page=_VERSES))
        self._offers = None
        if said is not None and said.placed:
            # What happened to the places, said under the flows. Only where something did:
            # a walk in to look and out again must not wipe what the list was already saying.
            self._said = said.placed
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Chooses the flow under the cursor, or opens the role under it.

        Args:
          event: What was chosen.
        """
        if not self._inside:
            below = str(event.option.id or "").removeprefix("=")
            if below == _FORK:
                self._forks()
            elif below == _WHENCE:
                self._verses()
            _, _, name = below.partition(_HALVES)
            if name:
                self._chose(name)
            return
        held = str(event.option.id or "").removeprefix("=")
        if held == _SAVE:
            self.applied()
            return
        if held == _BUDGET:
            self._budgets()
            return
        if held.startswith("@"):
            self._placing(held[1:])
            return
        try:
            at = int(held)
        except ValueError:
            return
        self._configuring(at)

    def _chose(self, name: str) -> None:
        """Takes a flow as the one to run, and reads back what it was last set up with.

        Nothing is written down: what the menu holds is a draft, and a flow chosen and then
        walked away from must leave the interface exactly as ready as it was.

        Args:
          name: The flow, by the name it was offered under.
        """
        if name != self._flow:
            declared = declared_of(name)
            if declared is None:
                self._said = _wont_load(name)
                self._fill()
                return
            self._flow, self._declared = name, declared
            self._runs = self._fitted(self._remembered(name))
            self._envs = self._placed(name)
            self._params = params_of(name, self._held(name).get("params") or {})
            self._budget = budget_of(name)
            self.changed()
        # On to what the flow itself takes, where it takes anything, and then to its roles:
        # things about one flow, asked in the order they depend on nothing.
        self._configures()

    @work
    async def _configuring(self, at: int) -> None:
        """Opens one agent role of the flow, and holds whatever comes back as a draft.

        Args:
          at: Which of them, counting from zero.
        """
        declared = self._declared
        if declared is None or not 0 <= at < len(declared.agents):
            return
        role = declared.agents[at]
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(
            Agent(
                role.name,
                self._runs.get(role.name, Runs("")),
                self._agents,
                role=role,
                unavailable=self._unavailable,
            )
        )
        if chosen is None:
            return  # walked out of it, which leaves that agent as the draft has it
        self._runs[role.name] = chosen
        self.changed()
        self._fill()

    def leaving(self) -> None:
        """Comes back out to the flows, or asks about the draft once there is nowhere back.

        Esc is one step back everywhere in this interface, and walking into a flow is a step:
        leaving outright from the agents would throw away the walk in along with the menu.
        There is no step back out of a menu that opened inside one -- while a flow runs, and
        on a flow that was named rather than picked -- so esc there is esc on the menu.
        """
        if self._inside and not self._only:
            self._walks(inside=False)
            return
        super().leaving()

    def applied(self) -> None:
        """Answers with the flow, its roles and how it is set up, all of it at once.

        Unless something a run needs has not been answered: an agent that names no model is
        a run that stops on its first turn, an environment nobody said the place of is a run
        refused before it starts, and so is a run given no budget -- which only a flow
        humanize ships may be. Each is said where it would be answered.
        """
        declared = self._declared
        missing = [
            role
            for role, one in self._runs.items()
            if not _complete(one) and (declared is None or role in declared.roles)
        ]
        if declared is not None:
            missing.extend(
                one.name
                for one in declared.envs
                if one.required and not self._envs.get(one.name)
            )
        if missing:
            telemetry.snag("save-refused", missing=len(missing))
            if not self._inside:
                # Refused from the flows, on the way out: the roles are what is to be looked
                # at, and the cursor was on a row of another list.
                self._walks(inside=True)
            self._said = iffy(f"{escape(', '.join(missing))} is not set up yet")
            self._fill()
            return
        if self._budget is None and declared is not None and not declared.unbounded:
            telemetry.snag("save-refused", missing=0)
            if not self._inside:
                self._walks(inside=True)
            self._said = iffy(
                "a run of this flow is given a budget: set what it may spend first"
            )
            self._fill()
            return
        self.dismiss(
            Chosen(
                self._flow,
                dict(self._runs),
                dict(self._envs),
                self._params,
                self._budget,
            )
        )


def _added(url: str, name: str) -> str:
    """Fetches a flowverse and answers with what it is called here."""
    return _hmz().verses.add(url, name).name


def _came_from(one: Flowverse) -> str:
    """Where a flowverse came from, as a row may show it.

    Asked of which flowverse it is rather than of whether its URL is empty: an empty URL
    means both `the package's own` and `a directory whose origin could not be read`, and
    answering the second with the first would put humanize's name on somebody else's flows.

    Args:
      one: The flowverse.

    Returns:
      The URL with whatever was signed into it taken out -- a private one is added as
      `https://x-access-token:$TOKEN@...`, and this is drawn where somebody can read it --
      or, for the ones fetched from nowhere, what they are instead: the package's own flows,
      and the directory each of yours is read from.
    """
    return _hmz().verses.whence(one, "not a clone of anything")


class Holds(Sheet[str]):
    """What one flowverse holds, and the one thing there is to do to the flowverse itself.

    Mostly a reading: which flow to run is asked on `/flow`, where the flows of every place
    are walked. This is the other question -- what is in this one -- and it is the one
    question about a flowverse that costs something to answer, since what a file holds is not
    a fact its name carries: reading a flow means running it.

    Fetching it again and taking it away are rows above the flows and out of their numbering,
    as what is done about a list is on every page of `/settings`. They are here because this
    is where a flowverse is opened, and what one *is* is what it holds: somebody deciding to be
    rid of one has the thing they are deciding about under the row that does it.
    """

    SEARCHES: ClassVar = True

    def __init__(self, one: Flowverse) -> None:
        """Reads one flowverse's flows.

        Args:
          one: The flowverse.
        """
        super().__init__()
        self._verse = one
        self._offers: list[Offer] | None = None

    def _ask(self) -> None:
        """Says which flowverse this is, and puts its flows up."""
        self.query_one("#asked", Label).update(self._verse.name)
        self.query_one("#about", Label).update(
            f"What it holds, read from {escape(_came_from(self._verse))}. Which of them to "
            "run is asked on /flow, where every place's flows are."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _flows(self) -> list[Offer]:
        """The flows it holds, read once: reading one means running its entry point."""
        if self._offers is None:
            try:
                self._offers = _hmz().verses.holds(self._verse)
            except OSError:
                self._offers = []
        return self._offers

    def reread(self) -> None:
        """Drops what it read before a fetch landed, and puts the flows up again."""
        self._offers = None
        self._fill()

    def _takes(self) -> bool:
        """Whether this is one there is any taking away, which four of them are not."""
        return not self._verse.fixed

    def _fill(self) -> None:
        """Puts the flows up, each with the line it says about itself, under what can be done.

        The rows about the place are above the flows and out of both the numbering and
        whatever a search narrowed them to: they are about the place rather than about
        anything in it, and a search for a flow that found nothing must still be a sheet
        somebody can be rid of the place from. The cursor opens on the first flow, where
        there is one, since what a place holds is what opening it was for.
        """
        listing = self.query_one("#choices", OptionList)
        shown = [one for one in self._flows() if self.fits(one.name, one.about)]
        self._counting = len(str(max(len(shown), 1)))
        atop = [
            (
                _AGAIN,
                "fetch it again" if self._verse.fetched else "fetch it",
                "from where it came from",
            ),
            *(
                (
                    (
                        _TAKES_AWAY,
                        f"take {self._verse.name} away",
                        "flows and all, at once",
                    ),
                )
                if self._takes()
                else ()
            ),
            _SEEK,
        ]
        sought = self._sought([one.name for one in shown])
        was = (
            (self.under() if sought is None else sought) if listing.option_count else ""
        )
        ids = [held for held, _, _ in atop] + [one.name for one in shown]
        landing = (
            was
            if was in ids
            else shown[0].name
            if shown and not listing.option_count
            else ids[0]
        )
        rows = [
            *self._atop(atop, here=landing),
            *(
                Option(
                    self._row(
                        seen,
                        one.name,
                        _briefly(one.about, self.size.width),
                        here=one.name == landing,
                        inforce=False,
                    ),
                    id=f"={one.name}",
                )
                for seen, one in enumerate(shown)
            ),
        ]
        listing.set_options(rows)
        listing.highlighted = ids.index(landing)
        self._drawn = listing.highlighted
        said = self._nothing(shown)
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("esc", "close"))

    def _nothing(self, shown: Sequence[Offer]) -> str:
        """What to say under the list, which is why it is empty and why it is here for good.

        Args:
          shown: The flows on the sheet, which is what there is to say nothing about.

        Returns:
          Why there is nothing in it, where there is nothing in it, and why there is no
          taking away the four that are always here -- a row somebody went looking for and
          did not find is a sheet that has not said anything.
        """
        said: list[str] = []
        if not shown:
            # What was typed comes first. `official` holds the flows in the package before it
            # has been fetched, so a search of it that found nothing is a list emptied by the
            # search rather than by the download -- and saying the download is why would send
            # somebody to fetch a flowverse that is already showing them what it has.
            if self._typed:
                said.append("no flow of that name in it")
            elif not self._verse.fetched:
                said.append("not fetched yet; the row above fetches it")
            else:
                said.append("nothing in it: a flowverse keeps its flows in flows/")
        if not self._takes():
            said.append(f"{escape(self._verse.name)} is always here, and does not go")
        return "\n".join(said)

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the flowverse fetched again or going, the rows that are not a reading.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if held in (_AGAIN, _TAKES_AWAY):
            # Answered rather than done here: what happens to the list of places is the list
            # of places', which is also where what became of it is said.
            self.dismiss(held)


class Pages(Drafts["Adjusted"]):
    """What every page of `/settings` shares: where the cursor is, and what has been said.

    One menu rather than five, so there is one line under the list and one account of what
    happened for the transcript however many pages it happened on. Each page after the first
    two is a class of its own that :class:`Adjusts` is made of -- what a list of accounts does
    is a good deal of code, and it reads better beside the sheets it opens than folded into
    one class five times as long -- and this is what they have in common.

    And each of those is put up the same way, so that a page is laid out as the last one was:
    the rows about the list first, through :meth:`_atop` -- `add …`, anything else that brings
    one in, `search…` -- then the list, then :meth:`_saving` where the page holds anything
    until it is saved, with the cursor landed by :meth:`_lands` and put there by :meth:`_put`.
    Enter on something listed opens its own menu, taking it away last; adding one opens a
    :class:`Form`, answered from its `done` row.
    """

    def __init__(self) -> None:
        """Starts with the cursor nowhere and nothing said."""
        super().__init__()
        #: Which row the cursor is on, by the id it was put up under: a search narrows the
        #: rows and a heading is not one, so a row number is not the thing it was on.
        self._was = ""
        #: What became of the last thing done, said under the list.
        self._said = ""
        #: What was just added to the list, which the cursor goes to next time it is put up.
        self._aim = ""
        #: What was last said on each page that is not the one open, by page.
        self._saids: dict[int, str] = {}
        #: What is worth saying again once this menu is done with, as it was said: whoever
        #: opened it says it where they say things, which is not always a transcript.
        self._told: list[str] = []

    def _follows(self, listing: OptionList) -> None:
        """Takes which row the cursor is on off the list, by its id.

        Only a row that is one of the things listed: the rows below them are about the list
        rather than in it, and one taken for one would be looked for among them, not found,
        and the cursor put back on the first of them as it arrived.

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named and named not in _APART:
                self._was = named

    def _lands(self, atop: Sequence[str], items: Sequence[str]) -> str:
        """Which row the cursor goes on as a page is put up again, by its id.

        The row it was on, where that is still there; else the first thing listed, since
        what is on a list is what somebody turning to it came to read; else the first of the
        rows above it, which on an empty list is the one that adds something to it.

        Args:
          atop: The rows above the list, by id.
          items: The things listed, by id, as a search has narrowed them.

        Returns:
          The id.
        """
        under = self.under() if self.query("#choices") else ""
        if (sought := self._sought(items)) is not None:
            if sought in items:
                self._was = sought
            return sought
        if self._aim in items:
            # Something just made or written, which is what somebody wants to see next.
            self._was, self._aim = self._aim, ""
            return self._was
        if under in _APART and (under in atop or under == _SAVE):
            return under
        if self._was not in items:
            self._was = items[0] if items else ""
        return self._was or (atop[0] if atop else _SAVE)

    def _tell(self, page: int, said: str) -> None:
        """Says what became of something done on one page, whichever page is open now.

        Under the list where it is the page open, and kept for when it is turned back to
        where it is not: what finishes in the background -- a clone, a CLI asked what it runs
        -- finishes whichever page somebody went on to read meanwhile.

        Args:
          page: The page it was done on.
          said: What to say, as markup.
        """
        if self._tab == page:
            self._said = said
        else:
            self._saids[page] = said

    def _saving(self, *, here: bool) -> Option:
        """The row the whole menu is saved from, under the last thing on the page."""
        return self._saves(
            "what every page holds" if self._changed else "nothing held yet", here=here
        )

    @staticmethod
    def _put(listing: OptionList, rows: list[Option], landing: str) -> None:
        """Puts the rows up with the cursor on one of them, by its id.

        Args:
          listing: The list.
          rows: The rows.
          landing: The id of the row the cursor goes on.
        """
        listing.set_options(rows)
        with contextlib.suppress(KeyError):
            listing.highlighted = listing.get_option_index(f"={landing}")


class Flowverses(Pages):
    """The flowverses page of `/settings`: what there is, what one holds, what can happen.

    Also what the row below the flows on the menu a flow is chosen at turns to. Nothing on it
    is held until the menu is saved, so it has no row to save from: adding a repository and
    fetching one again each run git as they are asked for, and something that has already
    been cloned is not a draft.

    Taking one away and fetching one again are not rows here: enter opens what a flowverse
    holds, and both are said in there, among everything else about it.
    """

    #: What the page says it is.
    VERSES_ABOUT = (
        "Where flows come from: a git repository with a flows/ directory apiece, cloned "
        "under humanize's home, and the flows of your own read where they lie. What happens "
        "here happens at once."
    )

    def __init__(self) -> None:
        """Holds nothing until the page is first read."""
        super().__init__()
        self._verses: list[Flowverse] = []
        #: What is being fetched now, so that a second fetch is not started over it.
        self._fetching = ""
        #: The last thing that happened to the places, for the flow menu this was opened from
        #: to say under its flows: the transcript is told about every page, and the flows are
        #: a different list because of this one alone.
        self._placed = ""

    def _read_verses(self) -> None:
        """Reads the flowverses off the disk, which is what the rows are drawn from."""
        self._verses = _hmz().verses.all()

    @staticmethod
    def _verse_about(one: Flowverse) -> str:
        """What a row says about one flowverse: where it came from, and whether it is here."""
        said = _came_from(one)
        if not one.fetched:
            return f"{said}{_DOT}not fetched yet"
        return said

    def _fill_verses(self) -> None:
        """Puts the flowverses up under the rows about them, marked where the cursor is.

        No row to save from: nothing on this page is held, so a save row here would be one
        that did something only for the other pages.
        """
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._verses if self.fits(one.name, one.url)]
        self._counting = len(str(max(len(shown), 1)))
        atop = [(_ADD, "add a flowverse", "a git repository of flows"), _SEEK]
        landing = self._lands(
            [held for held, _, _ in atop], [one.name for one in shown]
        )
        self._put(
            listing,
            [
                *self._atop(atop, here=landing),
                *(
                    Option(
                        self._row(
                            seen,
                            one.name,
                            self._verse_about(one),
                            here=one.name == landing,
                            inforce=False,
                        ),
                        id=f"={one.name}",
                    )
                    for seen, one in enumerate(shown)
                ),
            ],
            landing,
        )
        self._drawn = listing.highlighted
        said = f"fetching {escape(self._fetching)}…" if self._fetching else self._said
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "what it holds"), Key("esc", "close"))

    def _took_verse(self, named: str) -> None:
        """Opens what the flowverse chosen holds, or adds one.

        Args:
          named: The row chosen, by its id.
        """
        if named == _ADD:
            self._adds_verse()
            return
        one = next((each for each in self._verses if each.name == named), None)
        if one is not None:
            self._opens_verse(one)

    @work
    async def _opens_verse(self, one: Flowverse) -> None:
        """Reads what one flowverse holds, which means running each flow in it."""
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Holds(one))
        if said == _TAKES_AWAY:
            self._removes(one)
        elif said == _AGAIN:
            await self._refetches(one)
            return
        self._fill()

    @work
    async def _adds_verse(self) -> None:
        """Asks where a flowverse is and what to call it here, and clones it."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            said = await showing.push_screen_wait(Fetches())
        finally:
            self.opened()
        if said is None:
            return
        url, name = said
        await self._fetches(name or url, lambda: _added(url, name))

    async def _refetches(self, one: Flowverse) -> None:
        """Fetches one flowverse again, or for the first time, as its own sheet asked.

        Args:
          one: The flowverse.
        """
        if not one.url:
            from hmz.runtime.flowing.verses import MINE

            # The other way to have no URL is a directory under the flowverses home that is
            # not a clone, which is what a clone killed partway leaves behind: there is
            # nothing to fetch it from, and taking it away is what it wants.
            said = (
                f"is read from {MINE[one.name]}"
                if one.name in MINE
                else "is not a clone of anything; take it away instead"
            )
            self._said = bad(f"{escape(one.name)} {said}; there is nothing to fetch")
            self._fill()
            return
        name = one.name

        def fetching() -> str:
            _hmz().verses.fetch(name)
            return name

        await self._fetches(name, fetching)

    def _removes(self, one: Flowverse) -> None:
        """Takes a flowverse away, flows and all, as what it holds was just asked for.

        Nothing is asked again here: the row that answers with this said what it was going to
        do, and it was chosen on the sheet that had just shown what is about to go. What
        became of it is said under the list rather than raised at whoever opened the menu --
        the question this page is asking still stands -- and the cursor is let go of, since a
        marker left against a name nothing answers to is a list pointing at nothing.

        Args:
          one: The flowverse.
        """
        try:
            _hmz().verses.remove(one.name)
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            return
        self._said = bad(f"{escape(one.name)} is no longer here")
        self._placed = self._said
        self._told.append(f"[dim]{self._said}[/dim]")
        self._was = ""
        self._read_verses()

    async def _fetches(self, named: str, doing: Callable[[], str]) -> None:
        """Runs one git fetch off the event loop, and shows the list it left behind.

        Off the loop because a clone is seconds of network: an interface that stopped
        redrawing while it ran would be one that looked as though it had gone away.

        Args:
          named: What is being fetched, said under the list while it runs.
          doing: What to do, answering with the flowverse it left behind.
        """
        import asyncio

        if self._fetching:
            return
        self._fetching, self._said = named or "it", ""
        self._fill()
        try:
            name = await asyncio.to_thread(doing)
        except (OSError, ValueError) as why:
            # Said under the list rather than raised at whoever opened the menu: the question
            # this page is asking is still worth answering.
            self._fetching = ""
            self._tell(_VERSES, escape(str(why)))
            self._fill()
            return
        self._fetching = ""
        said = f"{escape(name)} is fetched"
        self._tell(_VERSES, said)
        self._placed = said
        self._told.append(f"[dim]{said}[/dim]")
        self._read_verses()
        self._aim = name
        self._fill()


def _briefly(said: str, width: int) -> str:
    """One flow's line about itself, clipped to the room the row has for it.

    Args:
      said: The line, which is the first line of what the flow says about itself and so is
        as long as that sentence is.
      width: How wide the sheet is.

    Returns:
      As much of it as fits beside the name, ending in an ellipsis where it was cut.
    """
    room = max(width - len(_INDENT) - _LABEL - 8, 20)
    return said if len(said) <= room else f"{said[: room - 1].rstrip()}…"


#: The three kinds of row a form is made of: one written into, one stepped along where it
#: stands, and one that opens a sheet of its own to be answered on.
_WRITES, _STEPS, _OPENS_ONTO = "writes", "steps", "opens"


class Question(NamedTuple):
    """One row of a form: what the answer is kept under, what it is called, what it asks.

    Attributes:
      held: What the answer is kept under, which is also the row's id.
      named: What the row is called on the screen.
      about: What is asked, said quietly beside it.
      kind: Written into, stepped along, or opened -- see :data:`_WRITES`.
      secret: Whether what is typed is drawn as bullets and never shown back.
      needed: Whether it is still to be answered, which is where keeping a row moves on to.
    """

    held: str
    named: str
    about: str
    kind: str = _WRITES
    secret: bool = False
    needed: bool = False


class Form[T](Drafts[T]):
    """A sheet written into rather than picked from: a row per question, and one that answers.

    Typing on a written row writes it, and enter keeps what was written and moves on to the
    next row still to be answered, or to the one that answers the form where none is -- so a
    form of three questions is three answers and an enter apiece, not an enter to begin each,
    an enter to keep it and an arrow to the next. A stepped row is begun with enter, moved
    with the arrows across and kept with enter, as every row changed where it stands is; an
    opened row opens a sheet of its own. Esc puts back a row being changed, and on a form
    holding something asks whether to keep it, as every menu holding changes does.

    Answered from its `done` row, whose line says what answering it will do: the same word on
    every form, so the way out of one is where it was on the last.
    """

    TYPES: ClassVar = True

    def __init__(self) -> None:
        """Initializes the asking."""
        super().__init__()
        self._typed_in: dict[str, str] = {}
        #: The written rows still holding an answer nobody typed -- a name the form made up
        #: -- which the first letter typed into one replaces rather than lands after.
        self._fresh: set[str] = set()
        #: What was wrong with it, once the form has been answered.
        self._wrong = ""
        #: The questions as they were last put up, which is what a row's kind is read off:
        #: asking them can read the disk, and a row's kind is asked of per keystroke.
        self._now: list[Question] | None = None

    def asked(self) -> list[Question]:
        """Every question, in the order they are asked, which each form says for itself."""
        raise NotImplementedError

    def choices(self, held: str) -> Sequence[str]:
        """What a stepped row steps through, which each form with one says for itself.

        Args:
          held: The row.

        Returns:
          Its rungs, in order.
        """
        del held
        return ()

    def stepped(self, held: str) -> None:
        """Answers a stepped row having moved, for a form whose other rows follow from it.

        Args:
          held: The row.
        """

    def opens(self, held: str) -> None:
        """Opens what an opened row is a way of asking, which each form with one says.

        Args:
          held: The row.
        """

    def lines(self, held: str) -> bool:
        """Whether a written row takes a list, a line apiece, which is where one can break.

        Args:
          held: The row.

        Returns:
          False, unless a form says otherwise.
        """
        del held
        return False

    def shown(self, one: Question) -> str:
        """What one row says it holds: what was typed, or a bullet apiece for a secret."""
        value = self._typed_in.get(one.held, "")
        return "•" * len(value) if one.secret else value

    def beside(self) -> list[tuple[str, str, str]]:
        """The rows set apart above the one that answers the form, for a form that has any.

        Returns:
          One `(id, what it is called, the line about it)` apiece.
        """
        return []

    def besides(self, held: str) -> None:
        """Does what one of those rows does.

        Args:
          held: The row.
        """

    def done_about(self) -> str:
        """What answering the form will do, said on the row that answers it."""
        return ""

    def note(self) -> str:
        """What to say under the form while nothing is wrong with it, already escaped."""
        return ""

    def _fill(self) -> None:
        """Puts the questions up, the rows set apart from them, and the row that answers."""
        listing = self.query_one("#choices", OptionList)
        rows = self._now = self.asked()
        apart = [*self.beside(), (_DONE, self.DONE, self.done_about())]
        self._counting = len(str(max(len(rows), 1)))
        at = min(listing.highlighted or 0, len(rows) + len(apart) - 1)
        # Three columns sized to what is in them: what each row is called, what it holds,
        # and what it asks. A column wide enough for the longest thing any form has is a
        # form whose answers sit halfway across the screen from their questions.
        named = max((len(one.named) for one in rows), default=0) + 2
        wide = min(
            max((len(self.shown(one)) + 3 for one in rows), default=0) + 2, _WIDEST
        )
        listing.set_options(
            [
                Option(
                    self._line(seen, one, here=seen == at, named=named, wide=wide),
                    id=f"={one.held}",
                )
                for seen, one in enumerate(rows)
            ]
            + [
                Option(
                    self._apart(
                        label,
                        about,
                        here=len(rows) + seen == at,
                        air=_ABOVE if not seen else "",
                    ),
                    id=f"={held}",
                )
                for seen, (held, label, about) in enumerate(apart)
            ]
        )
        listing.highlighted = at
        self._drawn = at
        note = self.note()
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]"
            if self._wrong
            else f"[$text-muted]{note}[/]"
            if note
            else ""
        )
        # A line broken only in a row that takes a list, and only while it is being written:
        # enter keeps what was written, so that row needs a key of its own to hold more than
        # one line at all. Said where it works and nowhere else.
        self._footed(
            *(
                (Key(_CHORD, "break the line"),)
                if self._editing and self.lines(self._editing)
                else ()
            ),
            *(
                (Key("enter", "open"),)
                if self._kind(self.under()) == _OPENS_ONTO
                else ()
            ),
            Key("esc", "back"),
        )

    def _line(
        self, at: int, one: Question, *, here: bool, named: int, wide: int
    ) -> str:
        """One question: what it is called, what it holds, and what it asks.

        Args:
          at: Which one it is, counting from zero.
          one: The question.
          here: Whether the cursor is on it.
          named: How wide the column of names is.
          wide: How wide the column of answers is.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        value = self.shown(one)
        # A block where the next letter goes, on the row being written and on no other: a
        # caret is what says the letters are going somewhere.
        caret = (
            "[reverse] [/reverse]"
            if self._editing == one.held and one.kind == _WRITES
            else ""
        )
        # And which of the other two kinds it is, said on the row: a reader who has to press
        # a key to find out whether a row opens or steps is a reader the row did not tell.
        moves = {_STEPS: f" {_CYCLES}", _OPENS_ONTO: f" {_OPENS}"}.get(one.kind, "")
        # Padded on what is shown rather than on what is written: markup is not columns.
        label = escape(one.named) + " " * max(1, named - len(one.named))
        room = wide - len(value) - (1 if caret else 0) - len(moves)
        return (
            f"{mark}[$text-muted]{number}[/] {label}"
            f"[$secondary]{escape(value)}[/]{caret}[$text-muted]{moves}[/]"
            f"{' ' * max(1, room)}[$text-muted]{escape(one.about)}[/]"
        )

    def _kind(self, row: str) -> str:
        """Which kind of row one is, or "" for one that is not a question."""
        rows = self._now if self._now is not None else self.asked()
        return next((one.kind for one in rows if one.held == row), "")

    def editable(self, row: str) -> bool:
        """A written or a stepped row is changed where it stands; an opened one is opened.

        Args:
          row: The row, by id.

        Returns:
          True for a question that is not opened.
        """
        return self._kind(row) in (_WRITES, _STEPS)

    def steps(self, row: str) -> bool:
        """Whether the arrows across move a row, which a stepped row's do.

        Args:
          row: The row, by id.

        Returns:
          True for a stepped row.
        """
        return self._kind(row) == _STEPS

    def step(self, row: str, by: int) -> None:
        """Moves a stepped row one rung, and lets whatever follows from it follow.

        Args:
          row: The row, by id.
          by: One on or back.
        """
        among = self.choices(row)
        if among:
            self._typed_in[row] = _stepped(among, self._typed_in.get(row, ""), by)
            self._wrong = ""
            self.stepped(row)

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter as answering the question being written.

        Args:
          row: The question, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        typed = event.key == "backspace" or (event.is_printable and event.character)
        if typed and row in self._fresh:
            # An answer nobody typed is replaced by the first thing that is.
            self._fresh.discard(row)
            self._typed_in[row] = ""
        if event.key == "backspace":
            self._typed_in[row] = self._typed_in.get(row, "")[:-1]
        elif event.key in _CHORD_KEYS and self.lines(row):
            self._typed_in[row] = self._typed_in.get(row, "") + "\n"
        elif event.is_printable and event.character:
            self._typed_in[row] = self._typed_in.get(row, "") + event.character
        else:
            return False
        self._wrong = ""
        return True

    def held(self) -> object:
        """Everything the form holds now, which esc on a row being changed puts back."""
        return (dict(self._typed_in), frozenset(self._fresh))

    def put_back(self, was: object) -> None:
        """Puts back what the form held before the row was begun on.

        Args:
          was: What :meth:`held` answered.
        """
        typed, fresh = cast("tuple[dict[str, str], frozenset[str]]", was)
        self._typed_in, self._fresh = dict(typed), set(fresh)

    def kept(self, row: str) -> None:
        """Moves on from a row just kept: to the next, or to what is still to be answered.

        To the next row still to be answered, where there is one: the key a way in asks for,
        once the way in is chosen. Where there is none, a stepped row moves on to the row
        after it, which is usually what it decided -- the way in after the CLI -- and a
        written or opened one to the next written row nothing is in, which is one that may be
        left blank and has not been yet, and then to the row that answers the form: a form
        whose rows are all answered is a form to be done with.

        Args:
          row: The row, by id.
        """
        rows = self.asked()
        at = next((seen for seen, one in enumerate(rows) if one.held == row), None)
        if at is None:
            return
        after = range(at + 1, len(rows))
        onward = next((seen for seen in after if rows[seen].needed), None)
        if onward is None and rows[at].kind != _STEPS:
            onward = next(
                (
                    seen
                    for seen in after
                    if rows[seen].kind == _WRITES
                    and not self._typed_in.get(rows[seen].held)
                ),
                None,
            )
        # Past the questions is always `done`, and never a row set apart above it: keeping
        # the last question must not leave enter over `take it away`.
        self.query_one("#choices", OptionList).highlighted = (
            onward
            if onward is not None
            else at + 1
            if rows[at].kind == _STEPS and at + 1 < len(rows)
            else len(rows) + len(self.beside())
        )

    def action_walk(self, by: int) -> None:
        """Walks the cursor, keeping first whatever the row it leaves was being written to.

        Args:
          by: One row down, or one up.
        """
        if self._editing:
            self._editing = ""
            if self.held() != self._before:
                self.edited()
            self._fill()
        super().action_walk(by)

    def on_paste(self, event: events.Paste) -> None:
        """Pastes an answer into a written row, begun on as typing into one begins it."""
        event.stop()
        row = self._editing or self.under()
        if not event.text or not self.written(row):
            return
        if not self._editing:
            self._editing, self._before = row, self.held()
        if row in self._fresh:
            self._fresh.discard(row)
            self._typed_in[row] = ""
        pasted = event.text.replace("\r\n", "\n").replace("\r", "\n")
        if not self.lines(row):
            # A clipboard commonly ends in a newline. A row of one value takes one line, as
            # Textual's own Input does; only a row that takes a list takes several.
            pasted = pasted.split("\n", 1)[0]
        self._typed_in[row] = self._typed_in.get(row, "") + pasted
        self._wrong = ""
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers the form, does what a row set apart does, or opens an opened row.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if held == _DONE:
            self.action_done()
        elif any(held == one for one, _, _ in self.beside()):
            self.besides(held)
        elif self._kind(held) == _OPENS_ONTO:
            self.opens(held)

    def applied(self) -> None:
        """Saving a form on the way out of it is answering it."""
        self.action_done()

    def action_done(self) -> None:
        """Answers with what was written, which each form says for itself."""
        raise NotImplementedError


#: The widest the column of answers grows before a long one pushes its question along
#: rather than every question on the form.
_WIDEST = 36


class Fetches(Form[tuple[str, str]]):
    """Where a flowverse is, and what it is to be called here.

    A form rather than a list, as signing in to an account is: there is nothing to pick, both
    rows being written where they stand. The name is second because it is the one with an
    answer already: a flowverse is called what its repository is called.
    """

    def asked(self) -> list[Question]:
        """The repository, and what to call it here."""
        return [
            Question(
                "repository",
                "repository",
                "a URL, or owner/repo for one on GitHub",
                needed=not self._typed_in.get("repository", "").strip(),
            ),
            Question(
                "name",
                "name",
                "what to call it here, blank for the repository's own name",
            ),
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "clones it, and offers its flows"

    def _ask(self) -> None:
        """Says what a flowverse is."""
        self.query_one("#asked", Label).update("Add a flowverse")
        self.query_one("#about", Label).update(
            "A git repository with a flows/ directory in it: one .py file per flow, and "
            "whatever they import beside them. It is cloned under ~/.humanize/flowverses, "
            "and its flows are offered under the name it is kept under."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with where it is and what to call it, once there is somewhere to fetch."""
        url = self._typed_in.get("repository", "").strip()
        name = self._typed_in.get("name", "").strip()
        if not url:
            self._wrong = "a flowverse is a repository, and none was named"
            self._fill()
            return
        if name:
            try:
                _hmz().verses.where(name)
            except ValueError as why:
                self._wrong = str(why)
                self._fill()
                return
        self.dismiss((url, name))


class Speaks(Form[str]):
    """A CLI of your own that speaks the Agent Client Protocol, and what starts it.

    A form rather than a list, as adding a flowverse is: there is nothing to pick, the one row
    being written where it stands. One question because the protocol answers it -- it has no
    discovery and no flag every agent agrees on, so the command is asked for -- and because
    the other question has only one answer: a backend answers to the command it registers, so
    what this is called here is what the command is called.
    """

    def asked(self) -> list[Question]:
        """What starts it."""
        return [
            Question(
                "command",
                "command",
                "what starts it, as you would type it: my-agent --acp",
                needed=not self._typed_in.get("command", "").strip(),
            )
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "writes it down as a backend"

    def _ask(self) -> None:
        """Says what one of these is."""
        self.query_one("#asked", Label).update("Add a CLI that speaks ACP")
        self.query_one("#about", Label).update(
            "Any coding agent that speaks the Agent Client Protocol, driven over the stdin "
            "and stdout of the command you give. The protocol names no models and no "
            "efforts, so it runs as whoever installed it configured it."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with the command, once there is something to start."""
        said = self._typed_in.get("command", "").strip()
        try:
            argv = shlex.split(said)
        except ValueError as why:  # an unbalanced quote is a line to correct
            self._wrong = str(why)
            self._fill()
            return
        if not argv:
            self._wrong = "nothing was given to start it with"
            self._fill()
            return
        self.dismiss(said)


#: How many times over a turn may be tried again, and how long the retrying may be given.
#: Rungs rather than a number to type: this is a setting somebody steps through until it
#: reads right, and a text box for an integer is a text box to validate.
_TRIES = (0, 1, 2, 3, 5, 8, 13, 21)
_FOR = (0.0, 30.0, 60.0, 300.0, 900.0, 3600.0)

#: The rows a step is tried again by, on the sheet a step is written on.
_HOW_MANY = "tries"
_POLICY = "policy"
_HOW_LONG = "for"


def _stepped[T](among: Sequence[T], held: T, by: int) -> T:
    """One rung on or back through a list, wrapping round and starting from the nearest.

    Args:
      among: The rungs, in order.
      held: What it is now, which need not be one of them -- a setting written by hand is
        stepped from the first rung rather than refused.
      by: One on or back.

    Returns:
      The rung to move to.
    """
    at = among.index(held) if held in among else 0
    return among[(at + by) % len(among)]


def _lasting(seconds: float) -> str:
    """How long something may go on for, as a row of a sheet says it."""
    if not seconds:
        return "as long as it takes"
    if seconds < 60:  # noqa: PLR2004 -- a minute, in the units the number is in
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.0f}m"


#: How wide the column of setting names is, and the column of their values, so that a sheet
#: of settings reads down three columns: what it is called, what it is, and what it is for.
#: Wide enough for the longest name any flow here has, since a column that a name overruns
#: is one the three of them stop lining up in.
_SETTING = 34
_VALUE = 13

#: What a switch reads as. Both are words pydantic takes back as a boolean, so what is shown
#: is also what is validated -- there is no second spelling of `on` for this to get wrong.
_ON = "on"
_OFF = "off"


class Budgeted(BaseModel):
    """What a run of a flow may spend, as the menu asks it.

    A model rather than four rows written by hand, so that the budget is asked with the same
    sheet a flow's own params are asked with: one place that knows how a number is typed,
    stepped and read back, and a description apiece saying what each limit means. What comes
    out of it is a :class:`hmz.flows.Budget`, which is where "at least one limit" is settled.

    Not a turn's budget, which is a flow's to give. This is the run's.
    """

    duration: str = Field(
        default="",
        description="how long the run may take: 1h30m, 90s, PT2H; empty for no limit",
    )
    cost: float = Field(
        default=0.0, ge=0, description="US dollars it may cost, 0 for no limit"
    )
    output_tokens: int = Field(
        default=0, ge=0, description="output tokens it may come to, 0 for no limit"
    )
    graceful: bool = Field(
        default=True,
        description="off to cut a turn off mid-way when a limit is reached",
    )

    @field_validator("duration")
    @classmethod
    def _reads(cls, said: str) -> str:
        """Refuses a duration that is not one, where it is typed."""
        from hmz.runtime.flowing import parse_duration

        if said.strip():
            parse_duration(said)
        return said.strip()

    @model_validator(mode="after")
    def _limits_something(self) -> Budgeted:
        """Refuses a budget that limits nothing, which is no budget."""
        if not (self.duration or self.cost or self.output_tokens):
            raise ValueError("set at least one of duration, cost and output_tokens")
        return self

    @classmethod
    def of(cls, budget: Budget) -> Budgeted:
        """A budget, as the sheet shows it."""
        import math

        seconds = budget.duration.total_seconds() if budget.duration else 0.0
        return cls(
            duration=f"{seconds:g}s" if seconds else "",
            cost=budget.cost
            if budget.cost is not None and not math.isinf(budget.cost)
            else 0.0,
            output_tokens=budget.output_tokens or 0,
            graceful=budget.graceful,
        )

    def budget(self) -> Budget:
        """What the sheet was answered with, as a run's budget."""
        from hmz.runtime.flowing import parse_duration

        return Budget(
            duration=parse_duration(self.duration) if self.duration else None,
            cost=self.cost or None,
            output_tokens=self.output_tokens or None,
            graceful=self.graceful,
        )


def _shown(value: object) -> str:
    """One setting's value, as a line about it says it.

    Args:
      value: What it is set to.

    Returns:
      A switch as `on` or `off`, anything else as it is written, and something unset as the
      empty string rather than as `None` -- a setting nobody has given a value is blank.
    """
    if isinstance(value, bool):
        return _ON if value else _OFF
    return "" if value is None else str(value)


def _grouped(field: FieldInfo) -> str:
    """Which part of the sheet a setting belongs under, if the flow said.

    A flow groups its settings by writing `json_schema_extra={"section": "..."}` where it
    declares them: twenty settings in one list is a list nobody reads, and the flow is the
    only thing that knows which of them belong together.

    Args:
      field: The field, as the model declared it.

    Returns:
      The heading to draw above it, or "" for a flow that grouped nothing.
    """
    extra = field.json_schema_extra
    if not isinstance(extra, dict):
        return ""
    said = cast("dict[str, Any]", extra).get("section")
    return str(said) if said else ""


def named_as(ref: str) -> str:
    """A flow's canonical ref as a line about it says it.

    Args:
      ref: `<module>:<flow>`, as the running tree names a call.

    Returns:
      The module alone for the flow named after it -- `chat` rather than `chat:chat` -- and
      the ref as it is otherwise.
    """
    where, _, name = ref.partition(":")
    return where if name == where else ref


def setting(config: BaseModel | None) -> list[str]:
    """What a flow was set up with, one line per setting that is not at its default.

    Read in two places -- the monitor and the box a run opens with -- and only the settings
    that were changed: a flow with forty of them says nothing by listing the thirty-nine
    nobody touched, and the one that was touched is the thing worth reading.

    Args:
      config: What the flow was set up with, or None for a flow that takes no setting up or
        was left as it comes.

    Returns:
      One `name value` apiece, in the order the model declares them, and nothing at all for
      a flow left entirely at its defaults.
    """
    if config is None:
        return []
    return [
        f"{name:<{_SETTING}}{_shown(getattr(config, name))}"
        for name, field in type(config).model_fields.items()
        if getattr(config, name) != field.get_default(call_default_factory=True)
    ]


class Configures(Drafts["BaseModel"]):
    """How the flow is set up, asked once between choosing it and choosing its agents.

    A flow says what it can be set up with by declaring a model, and this is that model with
    a cursor on it: one row per field, the name, what it is set to, and the line the field
    was declared with. Nothing here knows what any of the settings mean -- the types say how
    a value is moved, and the model itself says which combinations it will not take, so a
    flow that refuses `gen_idea` without `gen_plan` refuses it here rather than an hour in.

    Every value is held as it is typed and handed to the model to read back, so a field is
    only ever wrong in one place: pydantic coerces `on`, `42` and `discussion` into the bool,
    the int and the literal the flow declared, and says what is wrong with anything else.
    """

    DONE = "set"

    def __init__(
        self,
        flow: str,
        model: type[BaseModel],
        now: BaseModel | None,
        *,
        asked: str = "",
        about: str = "",
    ) -> None:
        """Initializes the setting up.

        Args:
          flow: The flow these settings are for.
          model: What it says it can be set up with.
          now: How it is set up already, or None to start from the model's own defaults.
          asked: What to call the sheet, or "" for setting the flow up. Given by the one
            other thing asked this way -- what a run of the flow may spend, which is a
            question about the run rather than about the flow and has to say so.
          about: The line under it, or "" for the one setting a flow up carries.
        """
        super().__init__()
        self._flow = flow
        self._asked = asked
        self._about = about
        self._model = model
        self._fields = list(model.model_fields.items())
        self._counting = len(str(len(self._fields)))
        #: Every value as text, which is what is shown and what is read back: one spelling
        #: of a setting, so that what is on screen is what the model is given.
        self._typed_in: dict[str, str] = {
            name: _shown(
                getattr(now, name)
                if now is not None
                else field.get_default(call_default_factory=True)
            )
            for name, field in self._fields
        }
        #: What the model said was wrong with them, if it has been asked yet.
        self._wrong = ""
        #: Which setting the cursor was last on, counting settings rather than rows: the
        #: headings between them are rows nothing can land on, so a row number is not one.
        #: One past the last for the row that sets them all.
        self._was = 0

    def _ask(self) -> None:
        """Says what is being set up."""
        self.query_one("#asked", Label).update(self._asked or f"Set up {self._flow}")
        self.query_one("#about", Label).update(
            self._about
            or "How this flow runs, which it says for itself. What is refused here is the "
            "flow's own refusal rather than this list's."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the settings up, grouped, with the marker beside the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at(listing.highlighted)
        rows: list[Option] = []
        group = ""
        for seen, (name, field) in enumerate(self._fields):
            under = _grouped(field)
            if under != group:
                group = under
                # A heading, and a blank line above it once there is something above it. It
                # cannot be landed on, so the arrows walk the settings and step over these.
                # A flow that grouped nothing gets neither, and reads as one list.
                if group:
                    if rows:
                        rows.append(Option("", disabled=True))
                    rows.append(
                        Option(f"{_INDENT}[$primary]{escape(group)}[/]", disabled=True)
                    )
            rows.append(Option(self._line(seen, name, here=seen == at), id=name))
        rows.append(
            Option(
                self._apart(self.DONE, "all of them", here=at == len(self._fields)),
                id=f"={_DONE}",
            )
        )
        listing.set_options(rows)
        listing.highlighted = self._row_of(at)
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]" if self._wrong else ""
        )
        self._footed(Key("esc", "back"))

    def _row_of(self, at: int) -> int:
        """Which row of the list one setting is on, once the headings are counted.

        Args:
          at: Which setting it is, counting from zero, or one past the last for the row that
            sets them all.

        Returns:
          The row.
        """
        rows = 0
        group = ""
        for seen, (_, field) in enumerate(self._fields):
            under = _grouped(field)
            if under != group:
                group = under
                if group:
                    rows += 2 if rows else 1
            if seen == at:
                return rows
            rows += 1
        return rows

    def _at(self, row: int | None) -> int:
        """Which setting a row of the list is, which is what the cursor is really on.

        Args:
          row: Where the cursor is, or None for a list nothing is highlighted in.

        Returns:
          The setting, counting from zero, one past the last for the row that sets them all,
          and the nearest one where the cursor is on a heading -- which is where it lands
          when the list is first put up.
        """
        listing = self.query_one("#choices", OptionList)
        if row is not None and 0 <= row < listing.option_count:
            named = listing.get_option_at_index(row).id
            if named == f"={_DONE}":
                self._was = len(self._fields)
            elif named is not None:
                self._was = next(
                    (
                        seen
                        for seen, (one, _) in enumerate(self._fields)
                        if one == named
                    ),
                    0,
                )
        return self._was

    def _line(self, at: int, name: str, *, here: bool) -> str:
        """One setting: what it is called, what it is set to, and what it is for.

        A setting being written carries a caret, where the next letter would land. Without it
        a blank one reads as a setting nothing can be typed into -- which is the one thing
        about this list that has to be visible, since a switch and a word look the same until
        you try to type at one.

        Args:
          at: Which one it is, counting from zero.
          name: The field.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        value = self._typed_in[name]
        about = dict(self._fields)[name].description or ""
        # A block where the next letter goes, drawn by reversing what is already there --
        # the one thing a list in the terminal's own colours can show without naming one.
        caret = (
            "[reverse] [/reverse]"
            if self._editing == name and not self._steps(name)
            else ""
        )
        # And the mark that says which rows move where they stand, which is the other half of
        # the same thing the caret is: a switch and a word look the same until you try one. A
        # number wears both, being a row that is written into *and* stepped along.
        cycles = f" {_CYCLES}" if self._moves(name) else ""
        # Padded on what is shown rather than on what is written: markup is not columns,
        # and the caret is one of them.
        named = escape(name) + " " * max(1, _SETTING - len(name))
        room = _VALUE - len(value) - (1 if caret else 0) - len(cycles)
        return (
            f"{mark}[$text-muted]{number}[/] {named}"
            f"[$secondary]{escape(value)}[/]{caret}[$text-muted]{cycles}[/]"
            f"{' ' * max(1, room)}[$text-muted]{escape(about)}[/]"
        )

    def _steps(self, name: str) -> tuple[str, ...]:
        """What a setting steps through, where it is one of a fixed few.

        Args:
          name: The field.

        Returns:
          Every value it takes, in the order the flow wrote them -- the two words of a
          switch, or the words of a literal -- and nothing at all for one that is written
          rather than stepped.
        """
        kind = dict(self._fields)[name].annotation
        # `Literal["a", "b"] | None` and `Literal["a", "b"]` are the same few words to step
        # through, so the union is unwrapped before the literal is read off it.
        for said in (kind, *get_args(kind)):
            if get_origin(said) is Literal:
                return tuple(str(one) for one in get_args(said))
        if kind is bool:
            return (_OFF, _ON)
        return ()

    def _moves(self, name: str) -> bool:
        """Whether the arrows move this setting where it stands.

        Args:
          name: The field.

        Returns:
          True for one of a fixed few values, which they cycle through, and for a number,
          which they count up and down. False for one that is only ever written.
        """
        if self._steps(name):
            return True
        return dict(self._fields)[name].annotation in (int, float)

    def editable(self, row: str) -> bool:
        """Every setting is changed where it stands.

        Args:
          row: The row, by id.

        Returns:
          True for a setting, and False for the row that sets them all.
        """
        return row in dict(self._fields)

    def steps(self, row: str) -> bool:
        """Whether the arrows move a setting, which a word that is written they do not.

        Args:
          row: The setting.

        Returns:
          True for a switch, a literal and a number.
        """
        return row in dict(self._fields) and self._moves(row)

    def held(self) -> object:
        """Every setting as it is written now."""
        return dict(self._typed_in)

    def put_back(self, was: object) -> None:
        """Puts every setting back as it was written before.

        Args:
          was: What :meth:`held` answered.
        """
        self._typed_in = dict(cast("dict[str, str]", was))

    def step(self, row: str, by: int) -> None:
        """Moves one setting along, however that setting moves.

        Args:
          row: The setting.
          by: One step forward or back.
        """
        if steps := self._steps(row):
            at = steps.index(self._typed_in[row]) if self._typed_in[row] in steps else 0
            self._typed_in[row] = steps[(at + by) % len(steps)]
        elif dict(self._fields)[row].annotation in (int, float):
            try:
                now = float(self._typed_in[row] or 0)
            except ValueError:
                now = 0
            moved = now + by
            self._typed_in[row] = str(
                int(moved) if dict(self._fields)[row].annotation is int else moved
            )
        else:
            return  # a setting that is written is not one an arrow has a step for
        self._wrong = ""

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter as writing the setting being changed.

        Args:
          row: The setting.
          event: The key.

        Returns:
          Whether it was taken: never on a switch or a literal, which are stepped.
        """
        if self._steps(row):
            return False
        if event.key == "backspace":
            self._typed_in[row] = self._typed_in[row][:-1]
        elif event.is_printable and event.character:
            self._typed_in[row] += event.character
        else:
            return False
        self._wrong = ""
        return True

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Sets them all, from the row below them.

        Args:
          event: What was chosen.
        """
        if str(event.option.id or "").removeprefix("=") == _DONE:
            self.applied()

    def applied(self) -> None:
        """Reads every setting back into the model, and answers with it if it takes them.

        What the model refuses is shown where it was typed rather than raised at the flow:
        a combination the flow will not run is a combination to correct before it starts,
        and this is the moment it is being said.
        """
        from pydantic import ValidationError

        try:
            self.dismiss(self._model.model_validate(self._typed_in))
        except ValidationError as refused:
            first = refused.errors()[0]
            where = ".".join(str(part) for part in first.get("loc") or ())
            self._wrong = f"{where}: {first['msg']}" if where else str(first["msg"])
            self._fill()


class Picks(Sheet[str]):
    """A question that is only a list of named things, answered by picking one of them.

    Two of the sheets here are that and nothing else -- which CLI a new account is for, and
    how to sign into it -- and two lists drawn two ways would read as two different kinds of
    question. So the drawing is here, and each of them says only what it asks and what there
    is to choose between.
    """

    #: The question at the top of the sheet, and the line under it saying what choosing one
    #: does. Every sheet of this shape says both for itself.
    asked = ""
    about = ""

    #: What the row below the choices adds, in a word or two, for a list that is added to as
    #: well as picked from -- and "" for one that is only picked from, which has no such row.
    adds = ""

    #: What the row that asks again what the list is of says, for a list that is read off
    #: something that can be asked again -- and "" for one that cannot.
    again = ""

    SEARCHES: ClassVar = True

    #: Whether the rows about the list go above it, as they do on everything `/settings`
    #: opens, rather than below it -- in which case the cursor opens on the choice in force.
    ATOP: ClassVar[bool] = False

    def __init__(self, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          current: What is in force already, which is the row the tick goes against.
        """
        super().__init__()
        self._current = current
        self._rows: list[tuple[str, str, str]] | None = None

    def rows(self) -> list[tuple[str, str, str]]:
        """What there is to choose between, which each sheet says for itself.

        Returns:
          One `(what picking it answers with, what it is called, the line about it)` apiece,
          in the order to show them.
        """
        raise NotImplementedError

    def nothing(self) -> str:
        """What to say under the list where the list alone does not say it.

        Returns:
          The line, already escaped, or "" for a list that speaks for itself.
        """
        return ""

    def _ask(self) -> None:
        """Says what is being chosen, and puts the choices up."""
        self.query_one("#asked", Label).update(self.asked)
        self.query_one("#about", Label).update(self.about)
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def added(self) -> None:
        """Adds one more, for a list that is added to as well as picked from."""

    def asked_again(self) -> None:
        """Asks again what the list is of, for a list that can be."""

    def _fill(self) -> None:
        """Puts the rows up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        if self._rows is None:
            # Once: looking means reading a directory, and this is redrawn per keystroke.
            self._rows = self.rows()
        shown = [row for row in self._rows if self.fits(row[1], row[2])]
        self._counting = len(str(max(len(shown), 1)))
        if self.ATOP:
            self._fill_atop(listing, shown)
            return
        below = [
            *((_SEARCH,) if self.SEARCHES else ()),
            *((_ADD,) if self.adds else ()),
            *((_AGAIN,) if self.again else ()),
        ]
        at = min(listing.highlighted or 0, max(len(shown) + len(below) - 1, 0))
        rows = [
            Option(
                self._row(
                    seen, label, about, here=seen == at, inforce=answer == self._current
                ),
                # Every row answers with a string and "" is one of the answers, which an id
                # of its own keeps tellable from a row that was never chosen.
                id=f"={answer}",
            )
            for seen, (answer, label, about) in enumerate(shown)
        ]
        for one in below:
            here = at == len(rows)
            rows.append(
                self._seeking(here=here)
                if one == _SEARCH
                else self._adding(self.adds, here=here)
                if one == _ADD
                else Option(self._apart(self.again, here=here), id=f"={_AGAIN}")
            )
        listing.set_options(rows)
        listing.highlighted = at if rows else None
        self._drawn = at
        said = self.nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "choose"), Key("esc", "back"))

    def _fill_atop(
        self, listing: OptionList, shown: list[tuple[str, str, str]]
    ) -> None:
        """Puts the rows up under the rows about them, the cursor opening on the one in force.

        Args:
          listing: The list.
          shown: The choices, as a search has narrowed them.
        """
        atop = [
            *(((_ADD, f"add {self.adds}", ""),) if self.adds else ()),
            *(((_AGAIN, self.again, ""),) if self.again else ()),
            *((_SEEK,) if self.SEARCHES else ()),
        ]
        ids = [held for held, _, _ in atop] + [answer for answer, _, _ in shown]
        sought = self._sought([answer for answer, _, _ in shown])
        was = (
            (self.under() if sought is None else sought)
            if listing.option_count
            else None
        )
        landing = (
            was
            if was in ids
            else self._current
            if was is None and any(one[0] == self._current for one in shown)
            else shown[0][0]
            if shown
            else ids[0]
            if ids
            else ""
        )
        listing.set_options(
            [
                *self._atop(atop, here=landing),
                *(
                    Option(
                        self._row(
                            seen,
                            label,
                            about,
                            here=answer == landing,
                            inforce=answer == self._current,
                        ),
                        id=f"={answer}",
                    )
                    for seen, (answer, label, about) in enumerate(shown)
                ),
            ]
        )
        listing.highlighted = ids.index(landing) if landing in ids else None
        self._drawn = listing.highlighted
        said = self.nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "choose"), Key("esc", "back"))

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with what was picked, or does what a row below the choices does.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id).removeprefix("=")
        if held == _ADD:
            self.added()
            return
        if held == _AGAIN:
            self.asked_again()
            return
        if held == _SEARCH:  # started a search rather than answered
            return
        self.dismiss(held)


def _hmz() -> Hmz:
    """humanize, as the one object every sheet reaches a store through.

    Made where it is wanted rather than held: it costs nothing until something is asked of
    it, and a sheet that reads a store twice reads the same store both times.
    """
    from hmz.daemon import Hmz

    return Hmz()


def _sets(provider: Provider) -> str:
    """What one account says about itself on a row: the way it was made by, and what it sets.

    Args:
      provider: The account.

    Returns:
      The line, with the variables named and never a value in it -- this is drawn where
      somebody can read it, and a key on a screen is a key in a photograph.
    """
    variables = ", ".join(sorted(provider.env))
    return f"{provider.way}{_DOT}{variables}" if variables else provider.way


def _drives(backend: str) -> type[AgentBase] | None:
    """What drives one backend, or None for a name nothing here drives.

    A CLI somebody added themselves is driven too -- by the one class that speaks the Agent
    Client Protocol -- so this asks what would build it rather than reading one table.

    Args:
      backend: The backend, by name.

    Returns:
      The agent class, or None.
    """
    try:
        return driver(backend)[0]
    except KeyError:
        return None


#: What each backend behind an extra is missing when it is missing, and the requirement that
#: ends that. The requirement rather than the extra: `hmz[dsh]` asks an index for humanize
#: itself, which is not where the humanize running this came from, whereas one package into
#: the environment already open is a line that works wherever it was installed from.
_EXTRAS = {
    "dsh": (
        "DeepSeek Harness is not installed",
        f"'{backends.DSH_SDK}' 'python-dotenv>=1.2.3'",
    ),
    "kimi": (
        "Kimi Code is installed, but the websocket client it is driven over is not",
        "'websockets>=15,<18'",
    ),
}

#: The ways an account of DeepSeek Harness can be made by, read off its profile rather than
#: named here: every one of them asks for `DEEPSEEK_API_KEY` -- the key on its own, or a
#: gateway's URL and the key that endpoint takes -- and its driver refuses an account made
#: any other way, so these are the accounts of it worth offering at all.
_DSH_WAYS = frozenset(
    way.name for one in backends.PROFILES if one.name == "dsh" for way in one.ways
)


def _installing(backend: str) -> str:
    """The command that adds an optional backend to this Python environment."""
    if (extra := _EXTRAS.get(backend)) is None:
        return f"install {backend}, then reopen humanize"
    missing, requirement = extra
    executable = str(Path(sys.executable).absolute())
    command = f"uv pip install --python {shlex.quote(executable)} {requirement}"
    return f"{missing}; run: {command}; then reopen hmz"


class Made(NamedTuple):
    """What making an account came to.

    Attributes:
      provider: The account written down, or None where the walk was left without making one.
      status: What the way's own command exited with, or 0 for a way that runs nothing and
        for one nobody got as far as running.
      why: What went wrong, or "" where nothing did: before anything was written down where
        there is no account, or in running its way in where there is one.
      way_runs: Whether the way had a command of its own, which is what tells an account that
        was signed in from one that was only written down.
      copied: The other backends this account was written down for as well, which is nothing
        for one that could run nothing else and for one nobody asked to copy.
    """

    provider: Provider | None = None
    status: int = 0
    why: str = ""
    way_runs: bool = False
    copied: tuple[str, ...] = ()


async def made(host: App[None], cli: str = "") -> Made:
    """Asks for an account on the one form that makes one, and writes it down.

    Here rather than beside whatever asked for it, because both places that ask are here:
    the accounts page of `/settings`, which asks which CLI on the form, and the sheets an
    account is chosen on, which know the CLI already and would otherwise have to send
    somebody out of the question they are answering to answer it.

    What it runs is not asked here: that is a coding agent starting up, and whoever asked
    for the account says how that is going where they say things.

    Args:
      host: The interface, which is what the form is pushed onto and what hands the terminal
        over while a login owns it.
      cli: The backend the account is for, or "" to ask on the form.

    Returns:
      What came of it: the account, whether its way in exited badly, and what stopped it.
      All of them empty for a form that was left.
    """
    signs = await host.push_screen_wait(Signing(cli))
    if signs is None:
        return Made()  # walked out of, which changes nothing
    accounts = _hmz().accounts
    way = accounts.way(signs.cli, signs.way)
    if way is None:  # the form steps through that backend's own, so there are none else
        return Made(why=f"{signs.way} is not a way in {signs.cli} has")
    try:
        provider = accounts.make(signs.cli, signs.name, way, signs.answers)
    except (ValueError, OSError) as why:  # a name or a directory that will not do
        return Made(why=str(why))
    if not way.argv:
        return Made(provider=provider, copied=_copied(provider, signs.also))
    # A login is a browser opened, a code read out, a token exchanged: it owns the screen
    # while it runs, and there is nothing for an interface to draw over it.
    try:
        with handed_over(host):
            status = accounts.sign_in(provider, way, signs.answers)
    except OSError as why:  # the backend's own command is not on this machine
        return Made(provider=provider, status=127, why=f"{way.argv[0]}: {why}")
    return Made(
        provider=provider,
        status=status,
        way_runs=True,
        copied=() if status else _copied(provider, signs.also),
    )


def _copied(one: Provider, among: Sequence[str]) -> tuple[str, ...]:
    """Writes one account down for the other backends it was asked to be, where each takes it.

    Args:
      one: The account.
      among: The other backends it was switched on for, on the form it was made on.

    Returns:
      The ones it was written down for: a backend that will not take it is one it is not.
    """
    accounts = _hmz().accounts
    copied: list[str] = []
    for cli in among:
        try:
            accounts.copies(one, cli)
        except (OSError, ValueError):
            continue
        copied.append(cli)
    return tuple(copied)


async def asks(cli: str, name: str) -> tuple[int, str]:
    """Asks a new account's CLI what it runs, so that there is a list when one is asked for.

    Here rather than where an account is written down: what a backend runs is that account's
    and is found by starting that backend, which is a thing to do once an account exists and
    not a thing the store of them should be doing at all.

    Off the event loop, because it is a coding agent starting up.

    Args:
      cli: The backend the account is for.
      name: What the account is called.

    Returns:
      How many models it said it runs, and why it would not say where it would not -- which
      is a list to ask for again rather than an account that will not work.
    """
    import asyncio

    from rich.text import Text

    try:
        found = await asyncio.to_thread(_hmz().accounts.ask, cli, name)
    except Exception as why:  # noqa: BLE001 -- a CLI that will not say is one to ask again later
        # As plain words: what a CLI says on its way out is often coloured for a terminal,
        # and escape codes read into markup are markup nobody wrote.
        return 0, Text.from_ansi(str(why)).plain.strip() or type(why).__name__
    return len(found), ""


@contextlib.contextmanager
def handed_over(host: App[None]) -> Generator[None]:
    """Gives the terminal away for as long as something else needs to own it.

    Where there is one to give: a driver that cannot be suspended is one nobody is watching --
    a test, a web terminal -- and what was going to run still has to run.

    Args:
      host: The interface holding the terminal.
    """
    from textual.app import SuspendNotSupported

    try:
        with host.suspend():
            yield
    except SuspendNotSupported:
        yield


class Signs(NamedTuple):
    """What an account is to be made out of, as the form it is asked on answers.

    Attributes:
      name: What the account is called, which is what an agent is configured with.
      answers: What each question was answered with, by the variable that answer becomes.
      cli: The backend it is for.
      way: The way in it is made by, by name.
      also: The other backends it is to be written down for as well, in the order shown.
    """

    name: str
    answers: dict[str, str]
    cli: str = ""
    way: str = ""
    also: tuple[str, ...] = ()


#: The rows of the form an account is made on that are not what its way asks, by the id each
#: is put up under. Lower case, where every variable a way asks for is upper, so that no
#: question a backend puts can be taken for one of them.
_BY = "way"
_CALLED = "name"
#: The row a way that asks nothing in particular is answered in, and the question on it. Its
#: own id rather than a variable's, since what is typed here is the variables themselves.
_TYPED = " "
_TYPED_ABOUT = "the variables, as NAME=VALUE, one per line"
#: What each row asking whether to write the account down for another backend as well is put
#: up under, in front of that backend's name.
_ALSO = "also:"


class Signing(Form[Signs]):
    """The one form an account is made on, corrected on, and signed in again from.

    Making one is one form rather than a walk of five: which CLI and which way in are rows
    stepped where they stand, the name is written for you -- the way in, unless something is
    already called that -- and what the way asks is under them, then which other backends to
    write it down for as well, switched on for the ones installed here. So the one question
    somebody came with, the key, is the one thing there is to type, and where the cursor goes
    once the way in is chosen.

    Correcting one asks what its way asks again, and signing one in again asks only what its
    way still needs; neither asks for its CLI, its way or its name, which it has. A secret is
    drawn as bullets and never shown back -- it is on its way into a credential store, and a
    screen is somewhere it can be read off -- so a secret left blank while correcting keeps
    the one it has rather than being taken for the answer.
    """

    def __init__(
        self,
        cli: str = "",
        way: Way | None = None,
        name: str = "",
        held: Mapping[str, str] | None = None,
        *,
        copies: bool = True,
    ) -> None:
        """Initializes the answering.

        Args:
          cli: The backend this account is for, or "" to ask which on the form.
          way: The way in it is being made by, for one that already has one -- one being
            corrected or signed in again -- or None to ask which on the form.
          name: What it is called already, for one that has a name.
          held: What that account holds now, for one being corrected rather than made. A
            secret among them is not read back on to the screen.
          copies: Whether to ask which other backends to write it down for as well, which
            signing one in again does not.
        """
        super().__init__()
        hmz = _hmz()
        self._making = way is None
        self._fixed = bool(cli)
        self._name = name
        self._held = dict(held or {})
        self._copies = copies
        #: What is installed here, read once: the form is redrawn per keystroke.
        self._here = frozenset(installed())
        names = [profile.name for profile in hmz.backends()]
        #: The backends a new account could be for, the ones installed here first.
        self._clis = [one for one in names if one in self._here] + [
            one for one in names if one not in self._here
        ]
        #: Every name an account is kept under already, on any backend: a name taken
        #: nowhere is one a copy lands under without writing over anything.
        self._taken = frozenset(one.name for one in hmz.accounts.all())
        cli = cli or (self._clis[0] if self._clis else "")
        self._typed_in = {_CLI: cli, _BY: way.name if way else ""}
        if not way:
            ways = hmz.accounts.ways(cli)
            self._typed_in[_BY] = ways[0].name if ways else ""
        self._defaults()
        # And what the account being corrected holds, less its secrets: only what may be
        # read back. Correcting one is then a matter of the row that is wrong.
        asked = {one.env: one for one in way.asks} if way else {}
        self._typed_in |= {
            where: value
            for where, value in self._held.items()
            if where in asked and not asked[where].secret
        }

    def _cli(self) -> str:
        """The backend the account is for, as the form now says."""
        return self._typed_in.get(_CLI, "")

    def _way(self) -> Way | None:
        """The way in it is made by, as the form now says."""
        return _hmz().accounts.way(self._cli(), self._typed_in.get(_BY, ""))

    def _defaults(self) -> None:
        """Answers what has an answer nobody need be asked for, as the way in now stands.

        A question a way answers itself -- a region that is usually right -- and the name,
        which is the way in unless something is already called that. Neither is written over
        once somebody has typed into it.
        """
        way = self._way()
        if way is None:
            return
        for one in way.asks:
            if one.fixed and one.env not in self._typed_in:
                self._typed_in[one.env] = one.fixed
                self._fresh.add(one.env)
        if not self._making:
            return
        if self._typed_in.get(_CALLED, "") and _CALLED not in self._fresh:
            return  # written by somebody, which is theirs
        base, count = way.name, 1
        while (named := base if count == 1 else f"{base}-{count}") in self._taken:
            count += 1
        self._typed_in[_CALLED] = named
        self._fresh.add(_CALLED)

    def _among(self) -> list[str]:
        """The other backends this account could be written down for, as it now stands."""
        from hmz.coganchor.providers import Provider

        way = self._way()
        if not self._copies or way is None:
            return []
        if not way.asks and not way.argv:
            try:
                env = _hmz().accounts.env(self._typed_in.get(_TYPED, ""))
            except ValueError:
                env = {}
            # Left blank while correcting, it keeps what it holds, and goes where that goes.
            env = env or dict(self._held)
        else:
            # What it will hold, by name, whether or not it has been typed yet: the rows
            # asking about the other backends must not come and go under the typing.
            env = {one.env: "_" for one in way.asks if one.keep} | dict(way.sets)
        one = Provider(cli=self._cli(), name=self._name, way=way.name, env=env)
        return list(_hmz().accounts.serves(one))

    def _also(self, cli: str) -> bool:
        """Whether the account is to be written down for another backend as well.

        What was switched, or else where it starts: on for a backend installed here, for an
        account being made -- those are the ones an agent could be run on tomorrow -- and on
        for one already holding a copy of it, for one being corrected, since a key rotated is
        a key rotated everywhere it was copied to.
        """
        said = self._typed_in.get(f"{_ALSO}{cli}")
        if said:
            return said == _YES
        if self._making:
            return cli in self._here
        return _hmz().accounts.find(cli, self._name) is not None

    def asked(self) -> list[Question]:
        """Which CLI and way, its name, what its way asks, and where else it goes."""
        way = self._way()
        cli = self._cli()
        rows: list[Question] = []
        if self._making:
            if not self._fixed:
                rows.append(
                    Question(
                        _CLI,
                        "cli",
                        "installed here"
                        if cli in self._here
                        else "not installed here yet",
                        kind=_STEPS,
                    )
                )
            rows.append(Question(_BY, "way", way.about if way else "", kind=_STEPS))
            rows.append(
                Question(
                    _CALLED,
                    "name",
                    "what to call this account",
                    needed=not self._typed_in.get(_CALLED, "").strip(),
                )
            )
        if way is None:
            return rows
        for one in way.asks:
            keeps = not self._making and one.secret and bool(self._held.get(one.env))
            rows.append(
                Question(
                    one.env,
                    one.env,
                    f"{one.about}; blank keeps the one it has" if keeps else one.about,
                    secret=one.secret,
                    needed=not self._typed_in.get(one.env)
                    and not one.fixed
                    and not keeps,
                )
            )
        if not way.asks and not way.argv:
            # A way that asks nothing in particular is asked for everything at once: the way
            # every backend has is variables of its own, and which ones they are is the
            # answer rather than the question.
            rows.append(
                Question(
                    _TYPED,
                    "variables",
                    _TYPED_ABOUT,
                    secret=True,
                    needed=self._making and not self._typed_in.get(_TYPED, "").strip(),
                )
            )
        name = self._name or self._typed_in.get(_CALLED, "")
        for other in self._among():
            about = (
                "installed here" if other in self._here else "not installed here yet"
            )
            if self._making and name and _hmz().accounts.find(other, name) is not None:
                about += f"{_DOT}writes over {other}/{name}"
            rows.append(Question(f"{_ALSO}{other}", f"also for {other}", about, _STEPS))
        return rows

    def shown(self, one: Question) -> str:
        """What a row holds, and on or off for whether it is written down elsewhere too."""
        if one.held.startswith(_ALSO):
            return _YES if self._also(one.held.removeprefix(_ALSO)) else _NO
        return super().shown(one)

    def choices(self, held: str) -> Sequence[str]:
        """The CLIs there are, and the ways into the one chosen."""
        if held == _CLI:
            return self._clis
        if held == _BY:
            return [one.name for one in _hmz().accounts.ways(self._cli())]
        return ()

    def step(self, row: str, by: int) -> None:
        """Moves a stepped row one along, or turns a switch round.

        Args:
          row: The row, by id.
          by: One on or back.
        """
        if row.startswith(_ALSO):
            self._typed_in[row] = _NO if self._also(row.removeprefix(_ALSO)) else _YES
            return
        super().step(row, by)

    def stepped(self, held: str) -> None:
        """Lets go of what belonged to the CLI or the way in before it moved.

        Args:
          held: The row that moved.
        """
        if held == _CLI:
            ways = _hmz().accounts.ways(self._cli())
            self._typed_in[_BY] = ways[0].name if ways else ""
        # Which others it goes to is asked again of what it now is.
        for one in [key for key in self._typed_in if key.startswith(_ALSO)]:
            del self._typed_in[one]
        self._defaults()

    def lines(self, held: str) -> bool:
        """The one row that takes a list, a line apiece: variables of your own."""
        return held == _TYPED

    def done_about(self) -> str:
        """What answering it does, which is written down, run, and copied."""
        way = self._way()
        cli = self._cli()
        named = f"{cli}/{self._name or self._typed_in.get(_CALLED, '').strip()}"
        if self._making:
            said = f"adds {named}"
        elif self._copies:
            said = f"corrects {named} once /settings is saved"
        else:
            said = f"signs {named} in again"
        if way is not None and way.argv:
            said += ", handing the terminal to its own login"
        elsewhere = [other for other in self._among() if self._also(other)]
        if elsewhere:
            said += f", for {', '.join(elsewhere)} too"
        return said

    def note(self) -> str:
        """What to say about a CLI that is not installed here, where one is being made."""
        cli = self._cli()
        if not self._making or not cli or cli in self._here:
            return ""
        way = self._way()
        if way is not None and way.argv:
            return f"{escape(cli)} is not installed here, and this way in runs its own login"
        return f"{escape(cli)} is not installed here yet: the account waits for it"

    def _ask(self) -> None:
        """Says what is being made, corrected or signed in, and puts the questions up."""
        cli = escape(self._cli())
        named = f"{cli}/{escape(self._name)}"
        self.query_one("#asked", Label).update(
            (f"Add a {cli} account" if self._fixed else "Add an account")
            if self._making
            else f"Correct {named}"
            if self._copies
            else f"Sign {named} in again"
        )
        self.query_one("#about", Label).update(
            "One named sign-in for one CLI, kept apart from the CLI's own and from every "
            "other account. A secret is drawn as bullets and never shown back."
            if self._making
            else "What it was made with, asked again. A secret is never drawn back, so one "
            "left blank keeps what it holds."
            if self._copies
            else "What its way in still has to be told before it runs."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with the account, once everything its way in needs has been said.

        What is missing is said where it was typed rather than raised at whoever opened the
        form: a question left blank is a question to answer, and this is where it happens.
        """
        accounts = _hmz().accounts
        way = self._way()
        cli = self._cli()
        if way is None:
            self._wrong = f"{cli} has no way in called {self._typed_in.get(_BY, '')}"
            self._fill()
            return
        name = (self._name or self._typed_in.get(_CALLED, "")).strip()
        answers = {
            one.env: value
            for one in way.asks
            # A secret left blank keeps the one it has: it is never drawn back to be kept.
            if (
                value := self._typed_in.get(one.env, "")
                or (self._held.get(one.env, "") if one.secret else "")
            )
        }
        # Only for the way that asks for them: what was typed there before the way was
        # stepped on is on no row of the form now, and nothing on no row is written down.
        typed = not way.asks and not way.argv
        try:
            accounts.where(cli, name)
            if typed and (said := self._typed_in.get(_TYPED, "").strip()):
                # Read here rather than where the account is made, so that a line that is not
                # a variable is said on the row it was typed on.
                answers |= accounts.env(said.replace("\r", "\n"))
            elif typed and not self._making:
                answers |= self._held  # left blank, so kept as they were
        except ValueError as why:
            self._wrong = str(why)
            self._fill()
            return
        if self._making and accounts.find(cli, name) is not None:
            self._wrong = (
                f"{cli} has an account called {name} already; correct it from its own "
                "row, or call this one something else"
            )
            self._fill()
            return
        if still := accounts.asks(way, answers):
            self._wrong = f"{still[0]} is still to be answered"
            self._fill()
            return
        if not answers and not way.argv:
            self._wrong = "an account that says nothing signs nothing in"
            self._fill()
            return
        self.dismiss(
            Signs(
                name,
                answers,
                cli,
                way.name,
                tuple(other for other in self._among() if self._also(other)),
            )
        )


class Falls(Picks):
    """Which account a turn under this one carries on as when it fails: its fail-over.

    A name rather than a mark: each account names the next, so what a turn walks is a chain
    -- a subscription that runs out fails over to a key, and a key that is refused to a
    gateway -- rather than there being one place every failure of that CLI goes.

    Only that CLI's own accounts are offered: an account is credentials for one backend, and
    a turn cannot be carried on under credentials for another. And a row to make one, since
    this is where somebody finds out the one they want is not there yet.
    """

    ATOP: ClassVar = True
    adds = "an account"

    def __init__(self, cli: str, name: str, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          cli: The backend these accounts are of.
          name: The account this is about, which is not among the ones offered.
          current: What it fails over to now, or "" for the end of the line.
        """
        super().__init__(current)
        self._cli = cli
        self._name = name
        self._said = ""
        self.asked = (
            f"What {cli}/{name} fails over to"
            if name
            else f"What {cli}, as this machine is signed in, fails over to"
        )
        self.about = (
            "The account a turn carries on as once the tries its place was given are spent, "
            "inside the conversation that was running. That account fails over too: a turn "
            "walks the chain to the end of it."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The end of the line first, then that CLI's own other accounts."""
        return [
            ("", "nowhere", "the end of the line: a failed turn is a failed turn"),
            *(
                (one.name, one.name, _sets(one))
                for one in _hmz().accounts.all(self._cli)
                if one.name != self._name
            ),
        ]

    def nothing(self) -> str:
        """What came of making one, or that there is none but the end of the line."""
        if self._said:
            return self._said
        if len(self._rows or []) > 1:
            return ""
        return f"{escape(self._cli)} has no other account to fail over to yet"

    def added(self) -> None:
        """Makes one, which is then the one it fails over to."""
        self._new()

    @work
    async def _new(self) -> None:
        """Makes an account of this CLI without leaving the question, and chooses it."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            outcome = await made(showing, self._cli)
        finally:
            self.opened()
        if outcome.provider is None or outcome.status:
            self._said = (
                bad(escape(outcome.why))
                if outcome.why
                else bad(
                    f"{escape(outcome.provider.name)} is written down, but signing it in "
                    f"exited {outcome.status}"
                )
                if outcome.provider is not None
                else ""
            )
            self._rows = None
            self._fill()
            return
        self.dismiss(outcome.provider.name)


class Popup(Picks):
    """A question that arrived rather than one somebody walked to.

    Drawn as a box in the middle of the screen rather than as a sheet: a sheet is walked to
    and fills the width it is drawn in, and this arrives over whatever was there, says one
    thing and is answered in a keypress. Each of these says for itself what it asks and what
    box it is drawn in; what is here is the one thing they all do, which is to be read rather
    than searched.
    """

    #: None: two rows are read rather than narrowed, and a box in the middle of the screen
    #: has no room for a row that searches.
    SEARCHES: ClassVar = False

    def _ask(self) -> None:
        """Says what is being asked, and takes back the line under it where there is none.

        A box is a question and two answers. The line about it is a row of the box paid for,
        so one with nothing in it is a blank row in the middle of the screen.
        """
        super()._ask()
        self.query_one("#about", Label).display = bool(self.about)


class Confirms(Popup):
    """Whether to keep what a menu is holding, asked as it is walked out of.

    A menu applies nothing until it is left, so leaving one is the moment the changes in it
    either land or do not. Asked rather than assumed either way: what was changed took typing
    to change, and throwing it away silently is worse than one more question.

    Drawn as a box in the middle of the screen rather than as a sheet, because it is not one:
    a sheet is a question somebody walked to, and this is one that arrived over the menu they
    were walking out of. Two answers, since the third -- going back to the menu -- is what esc
    already is everywhere else, and an answer that is also a key is a row that says the key is
    not there.
    """

    CSS = _POPUP

    #: Five words for the whole box, keys and all: it arrives over a menu somebody has just
    #: spent a minute in, it asks the one thing that is left, and either answer is a word.
    #: Anything more is prose read at the moment nobody is reading.
    asked = "Save?"

    def rows(self) -> list[tuple[str, str, str]]:
        """The two things there are to do about a menu holding changes."""
        return [(_KEEP, "save", ""), (_DROP, "discard", "")]

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here.

        Esc is the third answer -- back to the menu, changing nothing -- so it says so. Every
        other sheet leaves on it, and one that said `cancel` over a menu holding changes would
        read as the one thing it is not.
        """
        super()._fill()
        self._footed(Key("enter", "choose"), Key("esc", "back"))


#: What to do about a flow that is running when the interface is being closed: stop it, let
#: go of the terminal and leave it running, or stay here after all. Named out here because
#: what to do about each is the interface's rather than this sheet's: one of them closes it.
STOPS, DETACHES, STAYS = "stops", "detaches", "stays"


class Leaves(Popup):
    """What is to become of the flow that is running, asked as the interface is closed.

    Closing the interface is not on its own a thing to do to a run. A flow is a loop and a
    turn thinks for minutes, so a day's work is behind the same three letters that close a
    window -- and where the runs are held by a host this interface closing cannot reach, the
    two are genuinely different things and only the person at the prompt knows which is meant:
    leaving lets go of this interface alone, and stopping stops the run for everybody reading
    it.

    Drawn as a box in the middle of the screen rather than as a sheet, for the reason the
    question about a menu holding changes is: a sheet is a question somebody walked to, and
    this is one that arrived.
    """

    #: The same box, said again for this class: every rule in this file selects by the name
    #: of the sheet it is about, so a box drawn for another one is a rule of its own.
    CSS = f"Leaves {{ align: center middle; background: transparent; }}\n{_POPUP}"

    asked = "A flow is running."

    def __init__(self, *, held: bool) -> None:
        """Initializes the question.

        Args:
          held: Whether the runs are held by a host that outlives this interface, which is
            what makes leaving it running an answer there is.
        """
        super().__init__()
        self._held = held

    def rows(self) -> list[tuple[str, str, str]]:
        """The two answers, the second of which is whichever one is true here."""
        return [
            (STOPS, "stop it, then leave", ""),
            # The one line worth a word: that the run outlives this interface is the whole of
            # what makes letting go of it an answer rather than a way of abandoning it.
            (DETACHES, "leave it running", "`hmz` here reads it again")
            if self._held
            else (STAYS, "stay here", ""),
        ]

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here."""
        super()._fill()
        self._footed(Key("enter", "choose"), Key("esc", "stay"))


#: The two answers to the question humanize asks about itself on a first start.
_REPORTS, _QUIET = "on", "off"

#: The rows the first two pages of the settings menu are made of, by the id each is put up
#: under.
_SENTRY = "reports"
_SENT = "sent"
_DETAILS = "details"
_BTW = "btw"
#: The row that puts the btw agent back to the flow's first, shown while another is chosen.
_BTW_FIRST = "btw-first"
_WORKSPACE = "workspace"
_RUNS = "flow"
_PROFILES = "profile"
_FORGET = "forget"

#: Which of them are turned round where they stand, which is what enter and the arrows do to
#: the row under the cursor. The rest are a reading: a directory and the flow it opens on are
#: what is remembered rather than something to set here.
_SWITCHES = (_SENTRY, _DETAILS, _PROFILES, _FORGET)

#: The pages of `/settings`, in the order they are turned between.
_EVERYWHERE, _DIRECTORY, _ACCOUNTS, _FALLBACK, _VERSES = range(5)

#: What `/settings` is told to open each of them by, in the same order: the first word of
#: each title that is not `this`, lower case, so that the word typed is the word on the tab.
PAGES = ("everywhere", "directory", "accounts", "fallback", "flowverses")

#: The pages that are lists of things, which are the ones with a search and a row to add
#: one more from rather than switches to turn round.
_LISTS = frozenset({_ACCOUNTS, _FALLBACK, _VERSES})

#: When a setting that cannot land at once does land, said beside its row while it is held
#: and in the transcript once it is saved.
_NEXT_RUN = "from the next flow run"
_NEXT_LAUNCH = "from the next launch"
_NEXT_BTW = "from the next time btw mode is entered"


#: How much of a directory a row says: the last of it, which is what tells one project from
#: another. The rest is a home directory, which says nothing and is nobody else's business.
_ENOUGH = 2


def _shortly(said: str) -> str:
    """One path, as much of it as a row has room for: the last parts of it."""
    parts = said.rstrip("/").split("/")
    return "/".join(parts[-_ENOUGH:]) if len(parts) > _ENOUGH else said


class Reports(Popup):
    """Whether humanize reports its own failures, asked once, on a first start.

    Asked rather than assumed either way. Assumed on, it would be a tool that started sending
    things about somebody's machine before they had heard of it; assumed off, it would be a
    tool whose crashes nobody ever sees, which on something this young is how a bug survives
    a year. So it is a question, put once, with what it means written out beside it -- what
    goes, and what does not -- and answered for every project from then on.

    Drawn as a box in the middle of the screen, for the reason the save question is: it is
    not a sheet somebody walked to. Esc leaves it unanswered, and unanswered is asked again
    next time rather than taken as a no.
    """

    #: The same box, said again under this name, for the reason the one about a run being
    #: left behind is: every rule in this file selects by the name of the sheet it is about,
    #: so a box drawn for another one is a rule of its own.
    CSS = f"Reports {{ align: center middle; background: transparent; }}\n{_POPUP}"

    asked = "Report what goes wrong to humanize?"

    def __init__(self) -> None:
        """Initializes the question on its default answer, which is yes."""
        super().__init__()
        sent, kept = "; ".join(SENT), "; ".join(KEPT)
        # What goes and what does not, where the question is asked rather than somewhere to
        # go and read: this is the whole of what anybody has to decide on, so it stays.
        self.about = (
            f"A crash nobody sees is a bug nobody fixes. Sent: {sent}. Never: {kept}. "
            "/settings changes it later."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The two answers, the one that helps first.

        Two words and no line about either: what is sent and what never is, is said in the
        question above them, and saying it again beside the answers would be the same list
        twice in a box that is read in a second.
        """
        return [(_REPORTS, "yes", ""), (_QUIET, "no", "")]

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here."""
        super()._fill()
        self._footed(Key("enter", "choose"), Key("esc", "ask again next time"))


#: How wide the column of aspect names is on the sheet one agent is set up on, and the column
#: of their values, so that it reads down three columns: what is being said, what it is, and
#: what it means. Wide enough for a model id, which is the longest of them by a distance.
_ASPECT = 12
_HOW = 34

#: What a switch on that sheet reads as. One row is a switch -- whether the turn runs as a
#: fleet -- and it is a thing about the model rather than about what the agent is allowed.
_YES, _NO = "on", "off"

#: The account an agent runs as when nobody has chosen one, which is always the first row it
#: is chosen from: the machine is signed in already, and that is what an agent nobody was
#: asked about has always run as.
_LOCAL = "as local"

#: The rows the sheet is made of, by the id each is put up under. In the order they are asked,
#: which is the order of what depends on what: the CLI settles which accounts and which models
#: there are, and the account settles which models that CLI will name.
_CLI = "cli"
_ACCOUNT = "provider"
_MODEL = "model"
_EFFORT = "effort"
_SWARM = "swarm"

#: Which of them are stepped along where they stand rather than opened, and which are opened.
_STEPPED = (_EFFORT, _SWARM)


class Agent(Drafts[Runs]):
    """Everything one agent is, on one sheet, each row opened or stepped where it stands.

    An agent is a CLI, an account, and a model at an effort -- the word `-a` takes after the
    role -- and nothing else. What it may do, what it is capable of and the skills it carries
    are the flow's, declared where the flow declares the role this agent fills; where its work
    lands is the environment the flow opens its session in. A row offering to set any of
    those would be a second answer to a question already settled.

    The order the rows go in is still the order of what depends on what: the CLI settles which
    accounts there are to choose from and which models that CLI will name, and the account
    settles which of them it may name. Changing the CLI therefore lets go of the model, which
    belonged to the CLI before it.
    """

    def __init__(
        self,
        named: str,
        runs: Runs,
        agents: dict[str, tuple[Model, ...]],
        *,
        role: AgentRole | None = None,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the sheet on what the agent is now.

        Args:
          named: The role being set up, which the question at the top says.
          runs: What it is now, which every row reads back.
          agents: The backends offered here, and what each of them says it runs.
          role: What the flow declared of the role, which is what rules a CLI out, or None
            for an agent that is no flow's.
          unavailable: The optional backends that still need installing.
        """
        super().__init__()
        self._named = named
        self._agents = dict(agents)
        self._unavailable = unavailable
        self._role = role
        cli, _, rest = runs.spec.partition("/")
        model, _, effort = rest.rpartition(":")
        # Said outright, all of them: each is read where it is set -- what a CLI runs is
        # looked up as the CLI that is chosen now -- so what they are has to be settled
        # without reading what reads them.
        self._cli: str = cli
        self._model: str = model
        # `swarm` in front of the effort is how a fleet is written down, so it comes off again
        # before the effort is looked for among the ones the model takes.
        self._swarm: bool = effort.startswith(SWARM)
        self._effort: str = effort.removeprefix(SWARM)
        self._provider: str = runs.provider
        #: What the chosen CLI says it runs as the chosen account, read once per pair: this
        #: is redrawn each time the cursor moves, and reading it is reading a file.
        self._catalogue: tuple[Model, ...] | None = None
        self._read_for: tuple[str, str] = ("", "")
        #: What became of asking a CLI what it runs, said under the rows rather than raised
        #: at whoever opened the sheet.
        self._said = ""

    def _ask(self) -> None:
        """Says whose agent this is, and what setting it up settles."""
        self.query_one("#asked", Label).update(f"Set up {escape(self._named)}")
        self.query_one("#about", Label).update(
            "What this one agent is: the CLI that takes its turns, the account they run as, "
            "and the model at an effort."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _rows(self) -> list[tuple[str, str, str]]:
        """Every row this agent is made of: its id, what it is now, and what it means.

        Returns:
          One `(id, what it is set to, the line about it)` apiece, in the order they are
          asked. The fleet row only for a model that runs a turn as one.
        """
        rows: list[tuple[str, str, str]] = [
            (_CLI, self._cli or "—", "which coding agent takes its turns"),
            (_ACCOUNT, self._provider or _LOCAL, "the account those turns run as"),
            (_MODEL, self._model or "—", "which of that CLI's models it runs"),
            (_EFFORT, self._effort or "—", "how hard it thinks"),
        ]
        if self._swarms():
            rows.append(
                (_SWARM, _YES if self._swarm else _NO, "one turn run as a fleet")
            )
        return rows

    def _fill(self) -> None:
        """Puts the rows up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(max(len(rows), 1)))
        at = min(listing.highlighted or 0, len(rows))
        listing.set_options(
            [
                Option(
                    self._line(seen, held, value, about, here=seen == at),
                    id=f"={held}",
                )
                for seen, (held, value, about) in enumerate(rows)
            ]
            + [self._saves("this agent", here=at == len(rows))]
        )
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said}[/]" if self._said else ""
        )
        self._footed(Key("enter", "open"), Key("esc", "close"))

    def _line(self, at: int, held: str, value: str, about: str, *, here: bool) -> str:
        """One row: what is being said, what it is set to, and what it means.

        Args:
          at: Which one it is, counting from zero.
          held: What the row is called.
          value: What it is set to.
          about: The line about it, said quietly.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        # Which of the two kinds of row this is, said on the row: one opens a sheet of its
        # own and one is cycled where it stands, and a reader who has to press a key to find
        # out which is a reader the row did not tell.
        moves = f" {_CYCLES}" if held in _STEPPED else f" {_OPENS}"
        # Called what the rest of humanize calls it -- an account -- whatever it is kept
        # under. Padded on what is shown rather than on what is written: markup is not
        # columns.
        said = "account" if held == _ACCOUNT else held
        named = escape(said) + " " * max(1, _ASPECT - len(said))
        room = _HOW - len(value) - len(moves)
        return (
            f"{mark}[$text-muted]{number}[/] {named}"
            f"[$secondary]{escape(value)}[/][$text-muted]{moves}[/]"
            f"{' ' * max(1, room)}[$text-muted]{escape(about)}[/]"
        )

    def _models(self) -> tuple[Model, ...]:
        """What the chosen CLI says it runs as the chosen account, read once per pair."""
        if self._catalogue is None or self._read_for != (self._cli, self._provider):
            self._read_for = (self._cli, self._provider)
            self._catalogue = (
                _hmz().accounts.models(self._cli, self._provider)
                if self._provider
                else self._agents.get(self._cli, ())
            )
        return self._catalogue

    def _under_model(self) -> Model | None:
        """The model this agent runs, as the CLI described it, or None where it named none."""
        return next(
            (one for one in self._models() if one.name == self._model),
            None,
        )

    def _efforts(self) -> tuple[str, ...]:
        """What the chosen model takes, hardest first.

        Returns:
          The efforts, or the one this agent is already at for a model the CLI has not
          described -- an agent read back off a file names a model whose catalogue may not
          have been fetched yet, and its effort is still the effort it runs at. A model whose
          own name carries its effort -- Antigravity lists `gemini-3.7-flash-low` -- says so
          by offering that one and no other.
        """
        model = self._under_model()
        if model is not None and model.efforts:
            return model.efforts
        return (self._effort,) if self._effort else ()

    def _swarms(self) -> bool:
        """Whether the chosen model runs a turn as a fleet as well as as an agent."""
        model = self._under_model()
        return model is not None and model.swarms

    def _made(self) -> Runs:
        """This agent as it now stands, which is what the sheet answers with."""
        # `swarm` in front of the effort is how a fleet is asked for: one turn at one effort,
        # run wide. A model that does not take it is asked for at the effort alone.
        wide = SWARM if self._swarm and self._swarms() else ""
        return Runs(
            f"{self._cli}/{self._model}:{wide}{backends.written(self._effort)}",
            self._provider,
        )

    def applied(self) -> None:
        """Answers with the agent as it now stands."""
        self.dismiss(self._made())

    def editable(self, row: str) -> bool:
        """Whether a row is stepped where it stands rather than opened.

        Args:
          row: The row, by id.

        Returns:
          True for how hard it thinks, and whether a turn is run as a fleet.
        """
        return row in _STEPPED

    def held(self) -> object:
        """What the two stepped rows say now."""
        return (self._effort, self._swarm)

    def put_back(self, was: object) -> None:
        """Puts the two stepped rows back as they were.

        Args:
          was: What :meth:`held` answered.
        """
        self._effort, self._swarm = cast("tuple[str, bool]", was)

    def step(self, row: str, by: int) -> None:
        """Moves one stepped row along, coming round at either end.

        Args:
          row: The row, by id.
          by: One on or back. On, for the efforts, is towards the one that thinks hardest,
            which is the first of them.
        """
        if row == _EFFORT:
            efforts = self._efforts()
            if not efforts:
                return
            at = efforts.index(self._effort) if self._effort in efforts else 0
            self._effort = efforts[(at - by) % len(efforts)]
        elif row == _SWARM:
            self._swarm = not self._swarm
        self._said = ""

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Opens the row under the cursor, or saves.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if held == _SAVE:
            self.applied()
            return
        if held in (_CLI, _ACCOUNT, _MODEL):
            self._opens(held)

    @work
    async def _opens(self, held: str) -> None:
        """Asks whatever that row is a way of asking, and holds the answer.

        Args:
          held: The row, by id.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        if held == _CLI:
            await self._chose_cli(showing)
        elif held == _ACCOUNT:
            await self._chose_account(showing)
        elif held == _MODEL:
            await self._chose_model(showing)
        self._fill()

    async def _chose_cli(self, showing: App[None]) -> None:
        """Asks which coding agent takes this one's turns, and lets go of what was its."""
        chosen = await showing.push_screen_wait(
            Clis(
                self._agents,
                self._cli,
                role=self._role,
                unavailable=self._unavailable,
            )
        )
        if chosen is None or chosen == self._cli:
            return
        # An account belongs to a backend and a model belongs to the CLI that runs it, so
        # neither of them survives the CLI changing under it.
        self._cli, self._provider, self._model, self._effort = chosen, "", "", ""
        self._swarm = False
        self._said = ""
        self.changed()

    async def _chose_account(self, showing: App[None]) -> None:
        """Asks which account its turns run as, out of that CLI's own."""
        if not self._cli:
            self._said = "choose the coding agent first; the accounts are its own"
            return
        chosen = await showing.push_screen_wait(Accounts(self._cli, self._provider))
        if chosen is None or chosen == self._provider:
            return
        # What one account may name is not what another may: the models are the account's.
        self._provider, self._said = chosen, ""
        self.changed()
        if chosen and not _hmz().accounts.asked(self._cli, chosen):
            # One never asked -- one just made, most often -- is asked now, without holding
            # the sheet up: the model row is what it is asked for.
            self._asks_models()

    @work
    async def _asks_models(self) -> None:
        """Asks this agent's CLI what it runs as its account, saying so while it does."""
        cli, provider = self._cli, self._provider
        self._said = f"asking {escape(cli)} what it runs as {escape(provider)}…"
        self._fill()
        runs, why = await asks(cli, provider)
        if (self._cli, self._provider) != (cli, provider):
            return  # chosen away from while it was asked, which is somebody else's answer
        self._catalogue, self._read_for = None, ("", "")
        self._said = (
            ""
            if runs
            else bad(
                f"{escape(cli)} did not say what it runs as {escape(provider)}"
                + (f": {escape(why)}" if why else "")
            )
        )
        self._fill()

    async def _chose_model(self, showing: App[None]) -> None:
        """Asks which of that CLI's models it runs, and starts it at the hardest effort."""
        if not self._cli:
            self._said = "choose the coding agent first; a model belongs to the CLI"
            return
        chosen = await showing.push_screen_wait(
            Catalogue(self._cli, self._provider, self._models(), self._model)
        )
        if chosen is None:
            return
        self._model, self._said = chosen, ""
        self._catalogue, self._read_for = None, ("", "")
        efforts = self._efforts()
        if self._effort not in efforts:
            # The hardest the model takes, which is where the cursor of the sheet that used
            # to ask this started: what is reached for rather than what is spent by default.
            self._effort = efforts[0] if efforts else ""
        self.changed()


class Clis(Picks):
    """Which coding agent takes one agent's turns, out of the ones that could.

    Not always all of them: a role typed as one harness -- `ClaudeCodeAgent` -- is that
    harness and no other, and one declared with a capability -- `/goal`, steering, a hook
    only some harnesses fire -- is one only the harnesses that have it can fill. A CLI that
    cannot is one choosing would make the run refuse to start, so it is not offered.
    """

    asked = "Select which coding agent takes its turns"
    about = (
        "The CLI behind this agent. Its accounts and its models are its own, so choosing "
        "another lets go of them."
    )

    def __init__(
        self,
        agents: dict[str, tuple[Model, ...]],
        current: str = "",
        *,
        role: AgentRole | None = None,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the choosing.

        Args:
          agents: The backends offered here, and what each of them says it runs.
          current: The one it is now.
          role: What the flow declared of the role this agent fills, which is what rules a
            CLI out, or None where a CLI is being chosen for something that is not a flow's
            agent -- the two ends of a fallback step, which a flow says nothing about.
          unavailable: The optional backends that still need installing.
        """
        super().__init__(current)
        self._agents = dict(agents)
        self._role = role
        self._unavailable = unavailable

    def rows(self) -> list[tuple[str, str, str]]:
        """Every CLI that could take this one's turns, and what each of them runs."""
        listed: list[tuple[str, str, str]] = []
        for backend in sorted(self._agents):
            if _drives(backend) is None or not serves(backend, self._role):
                continue
            listed.append(
                (
                    backend,
                    backend,
                    _installing(backend)
                    if backend in self._unavailable
                    else f"{len(self._agents[backend])} models"
                    if self._agents[backend]
                    else "has not said what it runs yet",
                )
            )
        return listed

    def nothing(self) -> str:
        """Says so where the flow has ruled every backend here out, which is worth knowing."""
        if self._rows:
            return ""
        role = self._role
        if role is not None and (role.harness is not None or role.capabilities):
            asked = [
                *([str(role.harness)] if role.harness is not None else []),
                *sorted(one.__name__ for one in role.capabilities),
            ]
            return (
                f"{escape(role.name)} needs {escape(', '.join(asked))}, and no coding agent "
                "installed here has that"
            )
        return "no coding agent installed here can take this one's turns"


class Accounts(Picks):
    """Which account one agent's turns run as, out of one CLI's own.

    The machine's own is always the first of them: an agent nobody has been asked about runs
    as whoever signed the CLI in, and that is a row rather than a blank. Making one is a row
    here, this being the moment somebody finds out they have none for this CLI.
    """

    asked = "Select the account its turns run as"
    about = (
        "An account is one backend's -- what signs in to Claude Code is not what signs in to "
        "codex -- so these are that CLI's own. Its sessions, its settings and its skills are "
        "the CLI's whichever account it runs as."
    )
    adds = "an account"

    def __init__(self, backend: str, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          backend: The CLI whose accounts these are.
          current: The account it runs as now, or "" for the machine's own.
        """
        super().__init__(current)
        self._backend = backend
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """The machine's own first, and then every account that CLI has here."""
        found = _hmz().accounts.all(self._backend)
        if self._backend == "dsh":
            # Only the accounts a turn of it would actually run under. Its driver refuses one
            # made some other way -- dsh is the one backend with no `env` way, so an account
            # claiming one was not made here -- and a row offered here that every turn
            # refuses is a row whose only effect is the failure it leads to. Which ways those
            # are is read off the profile rather than listed, so that one added there is one
            # this list offers without being touched.
            found = [
                one
                for one in found
                if one.way in _DSH_WAYS and one.env.get("DEEPSEEK_API_KEY", "").strip()
            ]
        return [
            (
                "",
                _LOCAL,
                "using credentials and the base URL saved by dsh, or this environment"
                if self._backend == "dsh"
                else "signed in as you signed it in",
            ),
            *((one.name, one.name, _sets(one)) for one in found),
        ]

    def nothing(self) -> str:
        """Says what came of making one, or where they come from for a CLI that has none."""
        if self._said:
            return self._said
        if self._backend == "dsh" and len(self._rows or []) < 2:  # noqa: PLR2004
            return (
                "DeepSeek Harness needs an API key; add stores one, or set DEEPSEEK_API_KEY "
                "and reopen hmz"
            )
        if len(self._rows or []) > 1:
            return ""
        return f"{escape(self._backend)} has no accounts here yet"

    def added(self) -> None:
        """Makes one, which is what the row below the choices is for."""
        self._new()

    @work
    async def _new(self) -> None:
        """Makes an account for this CLI without leaving the question it is chosen in.

        The same form the accounts page opens, less the question it has already answered:
        which backend. What comes of it is what this list is now showing, so a new account is
        chosen straight away -- making one here is choosing it -- and the agent's sheet asks
        its CLI what it runs. Unless its own way in failed, which is said under the list and
        left for whoever is looking to decide about.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            outcome = await made(showing, self._backend)
        finally:
            self.opened()
        if outcome.why:
            self._said = bad(escape(outcome.why))
        if outcome.provider is None:
            self._rows = None  # it may have been made and then failed; look again
            self._fill()
            return
        if outcome.status:
            self._said = (
                f"{escape(outcome.provider.name)} is written down, but signing it in "
                f"exited {outcome.status}"
            )
            self._rows = None
            self._fill()
            return
        self.dismiss(outcome.provider.name)


class Catalogue(Picks):
    """Which model one agent runs, out of what its CLI last said it runs as its account.

    The rows are what that CLI said rather than a list written down anywhere: a CLI ships a
    model without asking anybody, and which of them a turn may name is the account's. The row
    below them asks it again, which is what somebody who came here for a model that is not
    in the list wants -- and is the whole reason the row is on this sheet rather than
    somewhere else.
    """

    again = "ask it again"

    def __init__(
        self,
        backend: str,
        provider: str,
        models: tuple[Model, ...],
        current: str = "",
    ) -> None:
        """Initializes the choosing.

        Args:
          backend: The CLI whose models these are.
          provider: The account it was asked as, or "" for the machine's own.
          models: What it last said it runs as that account, which is nothing at all for one
            that has never been asked -- and is what asking again here fills.
          current: The model it runs now.
        """
        super().__init__(current)
        self.asked = f"Select what {backend} runs"
        self.about = (
            f"Which model of {backend} takes this one's turns, and how hard it may be asked "
            "to think. These are what it last said it runs as this account."
        )
        self._backend = backend
        self._provider = provider
        self._models = models
        self._asking = False
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """Every model that CLI named, and what efforts each of them takes."""
        return [
            (
                one.name,
                one.name,
                ", ".join(one.efforts) + (f"{_DOT}swarms" if one.swarms else ""),
            )
            for one in self._models
        ]

    def nothing(self) -> str:
        """What to say where there is no model to say anything else about."""
        if self._asking:
            return f"asking {escape(self._backend)} what it runs…"
        if self._said:
            return self._said
        if self._models:
            return ""  # narrowed away by what was typed, which the search itself says
        whose = f" as {escape(self._provider)}" if self._provider else ""
        return (
            f"{escape(self._backend)} has not said what it runs{whose} yet; asking it "
            "again asks it"
        )

    def asked_again(self) -> None:
        """Asks this CLI what it runs, from the row below the models."""
        self._refresh()

    @work
    async def _refresh(self) -> None:
        """Asks this CLI what it runs as this account, and puts up what it answers.

        Off the event loop, because asking means starting a coding agent -- some of them take
        the better part of a minute over it -- or reaching an endpoint that may not answer at
        all: an interface that stopped redrawing while either ran would be one that looked as
        though it had gone away.
        """
        import asyncio

        if not self._backend or self._asking:
            return
        self._asking, self._said = True, ""
        self._fill()
        try:
            found = await asyncio.to_thread(
                _hmz().accounts.ask, self._backend, self._provider
            )
        except Exception as why:  # noqa: BLE001 -- a CLI that would not answer, however
            # Said under the list rather than raised at whoever opened the sheet: a CLI that
            # is not signed in cannot say what it runs, and the question here still stands.
            self._said = bad(escape(str(why) or type(why).__name__))
            self._asking = False
            self._fill()
            return
        self._asking, self._models = False, found
        self._said = "" if found else f"{escape(self._backend)} named no models it runs"
        self._rows = None
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()


#: The two places a step is written between, by the id each is put up under on its form.
_FAILS, _GOES = "fails", "goes"

#: What a row of the list of places is put up under when the account it is of has not said
#: what it runs: this, then the CLI and the account either side of :data:`_HALVES`.
_UNASKED = "\x1d"


class Places(Picks):
    """Which place: every CLI here, as each of its accounts, at each model it runs -- one list.

    One list rather than three questions in a row. A place is the three of them together,
    and somebody looking for one knows it by any of them -- `opus`, `work`, `codex` -- which
    a search of one list finds and a walk of three sheets makes them answer in order. An
    account that has not said what it runs is a row of its own, and choosing it asks.
    """

    ATOP: ClassVar = True

    def __init__(
        self,
        offered: Mapping[str, tuple[Model, ...]],
        asked: str,
        current: str = "",
        *,
        leaving: str = "",
        nowhere: bool = False,
    ) -> None:
        """Initializes the choosing.

        Args:
          offered: The backends offered here, which is which CLIs there are to choose from.
          asked: What the sheet asks.
          current: The place in force now, which the tick goes against.
          leaving: The place a step is written against, which is not one it can go to.
          nowhere: Whether falling back nowhere is one of the answers.
        """
        super().__init__(current)
        self.asked = asked
        self.about = (
            "A place is a CLI, the account it runs as and one of its models: what a turn "
            "can fail for having named. A search finds one by any of the three."
        )
        self._offered = dict(offered)
        self._leaving = leaving
        self._nowhere = nowhere
        self._asking = ""
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """Every place there is, by CLI and then by account, and the ones not yet asked."""
        hmz = _hmz()
        listed: list[tuple[str, str, str]] = (
            [
                (
                    "",
                    "nowhere",
                    "once its tries are spent, a failed turn is a failed turn",
                )
            ]
            if self._nowhere
            else []
        )
        for cli in sorted(self._offered):
            if _drives(cli) is None:
                continue
            for account in ["", *(one.name for one in hmz.accounts.all(cli))]:
                # The machine's own as the interface last read it, and an account's as it
                # last said: both are what was asked, and neither starts a CLI to draw.
                models = (
                    hmz.accounts.models(cli, account)
                    if account
                    else self._offered[cli] or hmz.accounts.models(cli)
                )
                if not models:
                    whose = f"{cli}@{account}" if account else cli
                    listed.append(
                        (
                            f"{_UNASKED}{cli}{_HALVES}{account}",
                            f"{whose}/…",
                            "has not said what it runs; choosing it asks",
                        )
                    )
                    continue
                for model in models:
                    spec = hmz.fallbacks.spec(cli, model.name, account)
                    if spec != self._leaving:
                        listed.append((spec, spec, ", ".join(model.efforts)))
        return listed

    def nothing(self) -> str:
        """What came of asking, or that there is nowhere to choose."""
        if self._asking:
            return f"asking {escape(self._asking)} what it runs…"
        if self._said:
            return self._said
        return (
            "" if self._rows else "no coding agent installed here has a place to offer"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the place, or asks an account that has not said what it runs.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id).removeprefix("=")
        if held.startswith(_UNASKED):
            cli, _, account = held.removeprefix(_UNASKED).partition(_HALVES)
            self._asks(cli, account)
            return
        if held not in _APART:
            self.dismiss(held)

    @work
    async def _asks(self, cli: str, account: str) -> None:
        """Asks one account what it runs, and puts up what it said.

        Args:
          cli: The backend.
          account: The account, or "" for the one this machine is signed into.
        """
        if self._asking:
            return
        self._asking, self._said = f"{cli}@{account}" if account else cli, ""
        self._fill()
        runs, why = await asks(cli, account)
        if not account:
            self._offered[cli] = _hmz().accounts.models(cli)
        self._asking = ""
        self._said = bad(escape(why)) if why else "" if runs else "it named no models"
        self._rows = None
        self._fill()


def _tried(tries: int) -> str:
    """How many times over a failed turn is tried again, as its row says it."""
    return str(tries) if tries else "none"


class Failing(Form["Step | str"]):
    """Everything about one step, on one form: where it fails, where it goes, how it retries.

    One form rather than a walk. Adding a step used to be the three questions a place is,
    asked twice over on six sheets, and how it is tried again a menu of its own opened from
    another: here the two places are a row apiece, each opening the one list of places, and
    the three that say how a failed turn is tried again are stepped where they stand beside
    them -- the tries first, since they are spent before the step is taken.

    Held until `/settings` is saved, as the rest of the page is. On a step already written,
    taking it away is a row of its own above the one that keeps it.
    """

    def __init__(
        self,
        offered: Mapping[str, tuple[Model, ...]],
        step: Step | None = None,
        *,
        steps: Sequence[Step] = (),
    ) -> None:
        """Initializes the form on a step, or on nothing for one being added.

        Args:
          offered: The backends offered here, which is what a place is chosen out of.
          step: What is written against the place now, or None to write a new one.
          steps: The steps the page is holding, so that a step added for a place that has
            one already starts from it rather than quietly replacing it with nothing.
        """
        from hmz.coganchor.fallbacks import Falls

        super().__init__()
        self._offered = dict(offered)
        self._held_steps = {one.spec: one for one in steps}
        #: What to say under the form while nothing is wrong with it.
        self._noted = ""
        self._unwritten = step is None
        held = step or Falls("")
        self._typed_in = {
            _FAILS: held.spec,
            _GOES: held.to,
            _HOW_MANY: _tried(held.tries),
            _POLICY: held.policy,
            _HOW_LONG: _lasting(held.timeout),
        }

    def asked(self) -> list[Question]:
        """The two places, and the three rungs of trying again."""
        said = _hmz().fallbacks.named(self._typed_in[_POLICY])
        return [
            *(
                (
                    Question(
                        _FAILS,
                        "fails at",
                        "the place whose turns cannot be taken",
                        _OPENS_ONTO,
                        needed=not self._typed_in[_FAILS],
                    ),
                )
                if self._unwritten
                else ()
            ),
            Question(
                _GOES,
                "falls back to",
                "where its turns go instead, in a conversation of their own",
                _OPENS_ONTO,
                needed=self._unwritten and not self._typed_in[_GOES],
            ),
            Question(
                _HOW_MANY,
                "tries",
                "how many times over a failed turn is tried again here first",
                _STEPS,
            ),
            Question(
                _POLICY,
                "policy",
                said.about if said is not None else "how long to wait between tries",
                _STEPS,
            ),
            Question(
                _HOW_LONG, "for", "the longest the trying again may go on for", _STEPS
            ),
        ]

    def shown(self, one: Question) -> str:
        """What a row holds, and what an empty place means."""
        value = self._typed_in.get(one.held, "")
        if one.held == _GOES and not value:
            return "nowhere"
        if one.held == _FAILS and not value:
            return "—"
        return value

    def choices(self, held: str) -> Sequence[str]:
        """The rungs of trying again."""
        if held == _HOW_MANY:
            return [_tried(one) for one in _TRIES]
        if held == _POLICY:
            return [one.name for one in _hmz().fallbacks.policies()]
        if held == _HOW_LONG:
            return [_lasting(one) for one in _FOR]
        return ()

    def beside(self) -> list[tuple[str, str, str]]:
        """Taking it away, for a step already written."""
        if self._unwritten:
            return []
        return [(_TAKES_AWAY, "take it away", "this place says nothing, once saved")]

    def besides(self, held: str) -> None:
        """Answers that it is to go.

        Args:
          held: The row, which is the one that takes it away.
        """
        if held == _TAKES_AWAY:
            self.dismiss(_TAKES_AWAY)

    def done_about(self) -> str:
        """What answering it does, which is hold it."""
        return "holds this step until /settings is saved"

    def note(self) -> str:
        """That the place chosen has a step already, which this form is now changing."""
        return self._noted

    def _takes_up(self, place: str) -> None:
        """Starts from the step a place chosen to fail already has, where it has one.

        Only what has not been changed on the form: a row somebody set is theirs.

        Args:
          place: The place chosen as the one that fails.
        """
        from hmz.coganchor.fallbacks import Falls

        was = self._held_steps.get(place)
        if was is None:
            self._noted = ""
            return
        fresh = Falls(place)
        for held, theirs, unset in (
            (_GOES, was.to, fresh.to),
            (_HOW_MANY, _tried(was.tries), _tried(fresh.tries)),
            (_POLICY, was.policy, fresh.policy),
            (_HOW_LONG, _lasting(was.timeout), _lasting(fresh.timeout)),
        ):
            if self._typed_in[held] == unset:
                self._typed_in[held] = theirs
        self._noted = (
            f"{escape(place)} has a step already; this is it, and done changes it"
        )

    def opens(self, held: str) -> None:
        """Opens the list of places for one of the two.

        Args:
          held: Which of them.
        """
        self._chooses(held)

    @work
    async def _chooses(self, held: str) -> None:
        """Asks which place, and moves on to what is still to be answered.

        Args:
          held: Which of the two places.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        fails = self._typed_in[_FAILS]
        try:
            chosen = await showing.push_screen_wait(
                Places(
                    self._offered,
                    "Select the place that fails"
                    if held == _FAILS
                    else f"Select where {fails or 'it'} falls back to",
                    self._typed_in[held],
                    leaving=fails if held == _GOES else "",
                    nowhere=held == _GOES,
                )
            )
        finally:
            self.opened()
        if chosen is None:
            return
        if chosen != self._typed_in[held]:
            self._typed_in[held], self._wrong = chosen, ""
            if held == _FAILS:
                self._takes_up(chosen)
            self.changed()
        self.kept(held)
        self._fill()

    def _ask(self) -> None:
        """Says which place this is about, and what a step is."""
        self.query_one("#asked", Label).update(
            "Add a step" if self._unwritten else escape(self._typed_in[_FAILS])
        )
        self.query_one("#about", Label).update(
            "What happens when a turn at a place cannot be taken: tried again there as many "
            "times as this says, then taken where it falls back to, in a conversation of "
            "its own."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with the step, once it says something and does not point at itself."""
        from hmz.coganchor.fallbacks import Falls

        fails, goes = self._typed_in[_FAILS], self._typed_in[_GOES]
        tries = next(
            (one for one in _TRIES if _tried(one) == self._typed_in[_HOW_MANY]), 0
        )
        if not fails:
            self._wrong = "a step is written against the place that fails; choose it"
        elif fails == goes:
            self._wrong = "a place cannot fall back to itself"
        elif not goes and not tries:
            self._wrong = "falling back nowhere and trying nothing again says nothing"
        if self._wrong:
            self._fill()
            return
        self.dismiss(
            Falls(
                fails,
                goes,
                tries,
                self._typed_in[_POLICY],
                next(
                    (one for one in _FOR if _lasting(one) == self._typed_in[_HOW_LONG]),
                    0.0,
                ),
            )
        )


class Fallbacks(Pages):
    """The fallback page of `/settings`: where a turn goes when its place cannot take it.

    A place is three things and no more: the CLI, the account it runs as, and the model it
    runs. That is what a turn can fail for having named -- a model retired, a CLI that will
    not start, a region gone dark, a rate limit on the whole account rather than one request
    -- and it is what a step is written between. How hard the agent thinks and what it may
    reach for are what that agent *is*, settled where it was made, and they come across the
    step unchanged.

    A row also says how many times over a failed turn is taken again before the step happens.
    Both are answers to the one thing that went wrong, so both are here.

    An account falling back to another account of the same CLI is not this. That happens
    inside the conversation that was running, so it is a thing about the account, and it is
    said on the accounts page where the accounts are.
    """

    #: What the page says it is.
    STEPS_ABOUT = (
        "Where a turn goes when the place taking it cannot take it at all. A place is a "
        "CLI, an account and a model. Saved, it is what the next failed turn walks."
    )

    def __init__(self) -> None:
        """Holds no steps until the menu reads them."""
        super().__init__()
        #: The backends offered here, and what each of them says it runs, which is what
        #: choosing a place is offered out of.
        self._offered: dict[str, tuple[Model, ...]] = {}
        #: The steps, held until the menu is saved.
        self._steps: list[Step] = []

    def _step_rows(self) -> list[tuple[str, str, str]]:
        """Every row: its id, the place that fails, and what happens when it does.

        Returns:
          One `(id, what fails, what happens)` apiece.
        """
        return [(one.spec, one.spec, _falling(one)) for one in self._steps]

    def _fill_steps(self) -> None:
        """Puts the steps up under the rows about them, each saying what fails and what next."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = [row for row in self._step_rows() if self.fits(row[1], row[2])]
        self._counting = len(str(max(len(rows), 1)))
        atop = [(_ADD, "add a step", "a place that fails, and where it goes"), _SEEK]
        landing = self._lands([held for held, _, _ in atop], [row[0] for row in rows])
        self._put(
            listing,
            [
                *self._atop(atop, here=landing),
                *(
                    Option(
                        self._row(
                            seen, said, goes, here=named == landing, inforce=True
                        ),
                        id=f"={named}",
                    )
                    for seen, (named, said, goes) in enumerate(rows)
                ),
                self._saving(here=landing == _SAVE),
            ],
            landing,
        )
        self._drawn = listing.highlighted
        said = self._said or ("" if rows else "nothing falls back anywhere yet")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "what happens"), Key("esc", "close"))

    def _drops_step(self, said: str) -> None:
        """Holds one place having nothing written about it, until the menu is saved.

        Held rather than done, as everything on this menu is: the row goes from the list at
        once so that what is read is what is held, and the cursor lands on the first of what
        is left rather than on a place that is no longer one of the rows.

        Args:
          said: The place, as it is written down.
        """
        self._steps = [one for one in self._steps if one.spec != said]
        self._said = iffy(f"{escape(said)} falls back nowhere when this menu is saved")
        self.changed()
        self._fill()

    def _took_step(self, named: str) -> None:
        """Opens the form a step is written on, for the step chosen or for a new one.

        Args:
          named: The row chosen, by its id.
        """
        if named == _ADD:
            self._writes_step(None)
        elif named:
            self._writes_step(self._step_of(named))

    @work
    async def _writes_step(self, step: Step | None) -> None:
        """Asks what one step is to say, on one form, and holds what it says.

        Args:
          step: The step as it is held now, or None for one being added.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            chosen = await showing.push_screen_wait(
                Failing(self._offered, step, steps=self._steps)
            )
        finally:
            self.opened()
        if chosen is None:
            return  # walked out, which changes nothing
        if chosen == _TAKES_AWAY:
            if step is not None:
                self._drops_step(step.spec)
            return
        if isinstance(chosen, str):
            return
        if chosen != step:
            self._holds_step(chosen)

    def _step_of(self, said: str) -> Step:
        """The step written against one place, or an empty one for a place with none."""
        from hmz.coganchor.fallbacks import Falls

        return next((one for one in self._steps if one.spec == said), Falls(said))

    def _holds_step(self, step: Step) -> None:
        """Puts one step in place of whatever was held against that place.

        Args:
          step: The step as it now stands.
        """
        self._steps = [one for one in self._steps if one.spec != step.spec] + [step]
        self._aim, self._said = step.spec, ""
        self.changed()
        self._fill()

    def _applies_steps(self, told: list[str]) -> None:
        """Writes down every step that was changed, and says what it did.

        Args:
          told: What the transcript is to say, which this adds to.
        """
        steps = _hmz().fallbacks
        # Against what is written down rather than over it: a menu somebody opened to change
        # one thing must not report the four it left alone as things it did.
        was = {one.spec: one for one in steps.all()}
        held = {one.spec: one for one in self._steps}
        for gone in was:
            if gone not in held:
                steps.clear(gone)
                told.append(f"[dim]{escape(gone)} falls back to nowhere[/dim]")
        for said, step in held.items():
            if was.get(said) == step:
                continue
            try:
                steps.points(said, step.to)
                steps.retrying(said, step.tries, step.policy, step.timeout)
            except ValueError as why:
                told.append(f"hmz: {escape(str(why))}")
            else:
                told.append(f"[dim]{escape(said)} {escape(_falling(step))}[/dim]")


def _falling(step: Step) -> str:
    """What happens when one place cannot take a turn, as the one line a row has room for.

    Args:
      step: The step.

    Returns:
      How often the turn is taken again there, and where it goes once those are spent.
    """
    goes = f"falls back to {step.to}" if step.to else "falls back nowhere"
    if not step.tries:
        return goes
    over = f", up to {_lasting(step.timeout)}" if step.timeout else ""
    return f"{step.tries} more tries, {step.policy}{over}{_DOT}{goes}"


#: What can be done to one account, which is what enter opens rather than what a row of
#: letter keys does. Each of these is a question about the account under the cursor, and a
#: menu of four is a menu; four keys nobody can see are four keys nobody presses. Being rid
#: of one is the fourth and is spelled with the rest of them -- see :data:`_TAKES_AWAY`.
_CORRECTS, _SIGNS_IN, _FALLS_BACK = "corrects", "signs-in", "falls"


class Account(Picks):
    """What to do with one account: correct it, sign it in, point it somewhere, be rid of it.

    Its own menu rather than a letter apiece on the list of accounts. They are four questions
    about the account under the cursor, and a sheet whose keys are `l` and `f` is a sheet
    whose keys have to be learned from a line at the bottom of it -- while enter, which every
    list already means, was doing one of the four.

    Taking it away is the last of them rather than a key on the list before this: the row
    that does it is read beside what the account is and what it is holding, which is what
    somebody deciding to be rid of it is deciding about.

    How many times over a failed turn is tried again is not among them. That is a thing about
    the place a turn runs at rather than about the credentials it runs with, and the
    fallback page of `/settings` is where it is said.
    """

    #: A few rows, read rather than narrowed.
    SEARCHES: ClassVar = False

    def __init__(self, cli: str, name: str, *, gone: bool = False) -> None:
        """Asks about one account.

        Args:
          cli: The backend it belongs to.
          name: What it is called, or "" for the account this machine is already signed into.
          gone: Whether the menu behind this is already holding it to be taken away, which is
            what makes the last row say the opposite. What is held may be taken back before
            it is saved, and a row that offered again to take away what is already going
            would be a row somebody pressed and got nothing from.
        """
        super().__init__()
        self._cli = cli
        self._name = name
        self._gone = gone
        self.asked = f"{cli}/{name}" if name else f"{cli}, as this machine is signed in"
        self.about = (
            "Correcting it, pointing it somewhere and taking it away land when /settings is "
            "saved; signing in happens as it is asked for."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The four, less the three there is nothing to do for this machine's own account."""
        held = [
            (
                _FALLS_BACK,
                "fails over to",
                "which account of it a failing turn carries on as, mid-conversation",
            ),
        ]
        if not self._name:
            return held
        return [
            (
                _CORRECTS,
                "correct what it holds",
                "the answers its way in was made with, asked again",
            ),
            (
                _SIGNS_IN,
                "sign in again",
                "run its own way in again; it owns the terminal while it does",
            ),
            *held,
            (
                _TAKES_AWAY,
                "keep it after all" if self._gone else "take it away",
                "it is held to go when /settings is saved"
                if self._gone
                else "the account and its credentials, when /settings is saved",
            ),
        ]

    def nothing(self) -> str:
        """Why three of them are not here.

        Returns:
          The line, or "" for any account humanize made. Why three of the four rows are not
          here is said rather than left to be noticed: a row somebody went looking for and
          did not find is a menu that has not answered them.
        """
        if self._name:
            return ""
        return (
            f"this is {escape(self._cli)} as this machine is already signed in: "
            "humanize keeps no credentials for it, so there is nothing to correct, "
            "sign in or take away"
        )


class Providers(Pages):
    """The accounts page of `/settings`: every account to run an agent as, per CLI.

    Read rather than chosen from: which account an agent runs as is asked where that agent is
    set up, so nothing here is being picked for anything. What it is for is what can happen to
    one -- made, set up again, signed in again, marked as where a turn goes when another
    account fails, taken away -- and all but the first of those are one menu, opened with
    enter on the account they are about.

    What is written down without running anything is held until the menu is saved: taking one
    away, marking one as a fallback, correcting what one holds. What cannot be held is what
    runs a command of its own -- making an account and signing one in own the terminal while
    they run, and something that has already happened is not a draft. Either way an agent
    reads the account it was configured with once, so what changes here is what its next
    session runs as, and the row says so while it is held.

    Each row is the name, the way it was made by and the variables it sets. Their names and
    never a value: this is drawn where somebody can read it.
    """

    #: What the page says it is.
    ACCOUNTS_ABOUT = (
        "One named set of credentials per account, kept apart from the CLI's own and from "
        "each other's. An agent is given one where it is set up. Making one and signing one "
        "in happen as they are asked for; the rest lands when this menu is saved, and an "
        "agent runs as it from its next session."
    )

    #: What a row says about an account whose change lands when the menu is saved, and when
    #: that change is felt: not by a session that is running, which read its account once.
    NEXT_SESSION = "from the next agent session"

    def __init__(self) -> None:
        """Holds nothing until the page is first read."""
        super().__init__()
        self._accounts: list[Provider] = []
        #: The ones to take away when this is saved, as `cli/name`.
        self._gone: set[str] = set()
        #: What each one is to fall back to when this is saved, by `cli/name`: the name of
        #: another account of that CLI, or "" for the end of the line.
        self._chains: dict[str, str] = {}
        #: What each corrected one is to hold, by `cli/name`.
        self._edits: dict[str, dict[str, str]] = {}
        #: Which other backends each corrected one is to be written down for as well, by
        #: `cli/name`: an account that several CLIs can be run as is corrected for all of
        #: them at once, which is the point of having copied it in the first place.
        self._alike: dict[str, tuple[str, ...]] = {}
        #: The ones whose CLI is being asked what it runs, which their rows say.
        self._asking: set[str] = set()

    def _read_accounts(self) -> None:
        """Reads every account off the disk, which is what the rows are drawn from.

        The account this machine is already signed into is one of them, under each CLI that
        has one of its own: it is what an agent nobody gave an account runs as, and it is
        where that agent's chain begins. Under a CLI with no accounts there is nothing for it
        to fall back to, so it is a row there only where something has already been said about
        it -- a chain that outlived the accounts it named -- which must not be a setting
        somebody believes in that nothing shows.

        Last in each CLI's group rather than first: what somebody came here to read is the
        accounts they made, and this is the one that was always there.
        """
        from hmz.coganchor.providers import LOCAL

        hmz = _hmz()
        accounts = hmz.accounts
        held = accounts.all()
        whose = {each.cli for each in held}
        mine = [
            one
            for profile in hmz.backends()
            if (one := accounts.find(profile.name, LOCAL)) is not None
            and (profile.name in whose or one.fallback)
        ]
        self._accounts = sorted(
            [*held, *mine], key=lambda one: (one.cli, not one.name, one.name)
        )

    @staticmethod
    def _named(one: Provider) -> str:
        """One account as it is keyed here, which is by the CLI it belongs to and its name."""
        return f"{one.cli}/{one.name}"

    def _account_about(self, one: Provider) -> str:
        """What a row says about one account, what is going to happen to it, and when."""
        named = self._named(one)
        said = (
            _sets(one) if one.name else "the CLI as this machine is already signed in"
        )
        if named in self._asking:
            said += f"{_DOT}asking what it runs…"
        if named in self._edits:
            said += f"{_DOT}corrected"
        falls = self._chains.get(named, one.fallback)
        if falls:
            said += f"{_DOT}fails over to {falls}"
        if named in self._gone:
            said += f"{_DOT}to be taken away"
        if named in self._edits or named in self._chains or named in self._gone:
            said += f"{_DOT}{self.NEXT_SESSION}"
        return said

    def _fill_accounts(self) -> None:
        """Puts the accounts up under a heading apiece, under the rows that add one."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._accounts if self.fits(one.name, one.cli, one.way)]
        self._counting = len(str(max(len(shown), 1)))
        atop = [
            (
                _ADD,
                "add an account",
                "a sign-in for one CLI: a key, a login, a gateway",
            ),
            (_SPEAKS, "add a CLI of your own", "one that speaks ACP"),
            _SEEK,
        ]
        landing = self._lands(
            [held for held, _, _ in atop], [self._named(one) for one in shown]
        )
        rows = self._atop(atop, here=landing)
        group = ""
        for seen, one in enumerate(shown):
            named = self._named(one)
            if one.cli != group:
                # A heading, and a blank line above it once there is a group above it.
                # Neither can be landed on, so the arrows walk the accounts and step over.
                if group:
                    rows.append(Option("", disabled=True))
                group = one.cli
                rows.append(
                    Option(f"{_INDENT}[$primary]{escape(group)}[/]", disabled=True)
                )
            rows.append(
                Option(
                    self._row(
                        seen,
                        one.name or _LOCAL,
                        self._account_about(one),
                        here=named == landing,
                        inforce=False,
                    ),
                    id=f"={named}",
                )
            )
        rows.append(self._saving(here=landing == _SAVE))
        self._put(listing, rows, landing)
        self._drawn = listing.highlighted
        said = self._said or ("" if self._accounts else "no accounts yet")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "what to do"), Key("esc", "close"))

    def _account_under(self) -> Provider | None:
        """The account the cursor is on, or None where the list has nothing in it."""
        return next(
            (one for one in self._accounts if self._named(one) == self._was), None
        )

    @staticmethod
    def _machines(cli: str, doing: str) -> str:
        """Why the account this machine is signed into is not one to do that to.

        Args:
          cli: The backend it is of.
          doing: What was asked for.

        Returns:
          The line to say under the list. humanize did not make that account and keeps no
          credentials for it -- it is the CLI as whoever is at this machine runs it -- so the
          only thing to say about it is what it fails over to, which is what enter offers.
        """
        telemetry.snag("key-does-nothing", sheet="Providers", doing=doing)
        return (
            f"there is nothing to {doing}: this is {escape(cli)} as this machine is already "
            "signed in. Enter says what it does take"
        )

    @work
    async def _falls_back(self, one: Provider) -> None:
        """Asks which account a turn under this one carries on as when it fails.

        Args:
          one: The account.
        """
        named = self._named(one)
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        was = {self._named(each) for each in self._accounts}
        chosen = await showing.push_screen_wait(
            Falls(one.cli, one.name, self._chains.get(named, one.fallback))
        )
        # An account may have been made on the way, which is one more row here, one more
        # line for the transcript, and one more CLI to ask what it runs as it.
        self._read_accounts()
        for made_ in [each for each in self._accounts if self._named(each) not in was]:
            self._told.append(
                f"[dim]{escape(self._named(made_))} is written down at "
                f"{escape(str(made_.at))}[/dim]"
            )
            self._probes(made_)
        if chosen is None:
            self._fill()
            return  # walked out, which changes nothing
        if chosen == one.fallback:
            self._chains.pop(named, None)
        else:
            self._chains[named] = chosen
        self._said = ""
        self.changed()
        self._fill()

    def _drops_account(self, one: Provider) -> None:
        """Holds one account to be taken away when this menu is saved, or takes that back.

        Held rather than done, as the rest of what this menu writes down is: credentials go
        with it, and a menu that deleted as it was read would be one where walking out had
        changed something nobody confirmed. The row stays where it is, saying what is going
        to happen to it, so the cursor is left on the thing it was on.

        Args:
          one: The account.
        """
        named = self._named(one)
        if named in self._gone:
            # Said and taken back, which is the other half of what that row offers.
            self._gone.discard(named)
            self._said = f"{escape(named)} stays"
        else:
            self._gone.add(named)
            self._said = f"{escape(named)} goes when this menu is saved"
        self.changed()
        self._fill()

    def _took_account(self, named: str) -> None:
        """Opens what there is to do with the account chosen, or makes one.

        Args:
          named: The row chosen, by its id.
        """
        if named == _ADD:
            self._adds_account()
            return
        if named == _SPEAKS:
            self._speaks()
            return
        one = next(
            (each for each in self._accounts if self._named(each) == named), None
        )
        if one is not None:
            self._doing_account(one)

    @work
    async def _doing_account(self, one: Provider) -> None:
        """Asks what to do with one account, and does it.

        Args:
          one: The account.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(
            Account(one.cli, one.name, gone=self._named(one) in self._gone)
        )
        if said is None:
            return  # walked out of it, which does nothing to the account
        if said == _CORRECTS:
            self._corrects(one)
        elif said == _SIGNS_IN:
            self._again(one)
        elif said == _FALLS_BACK:
            self._falls_back(one)
        elif said == _TAKES_AWAY:
            self._drops_account(one)

    @work
    async def _corrects(self, one: Provider) -> None:
        """Asks what one account is to hold, starting from what it holds now.

        A secret is never read back on to the screen, so one left blank keeps what it holds
        and one typed replaces it: a key is written once and read never. Which other backends
        hold it too is asked on the same form, so a rotated key is typed once.

        Args:
          one: The account.
        """
        if not one.name:
            self._said = self._machines(one.cli, "correct")
            self._fill()
            return
        way = _hmz().accounts.way(one.cli, one.way)
        if way is None:
            self._said = bad(f"{escape(one.way)} is not a way in {escape(one.cli)} has")
            self._fill()
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        signs = await showing.push_screen_wait(Signing(one.cli, way, one.name, one.env))
        if signs is None:
            return  # walked out, which corrects nothing
        named = self._named(one)
        self._edits[named] = signs.answers
        self._alike[named] = signs.also
        self._said = f"{escape(named)} is corrected when this menu is saved"
        if signs.also:
            self._said += f", for {escape(', '.join(signs.also))} as well"
        self.changed()
        self._fill()

    @work
    async def _adds_account(self) -> None:
        """Asks for an account on the one form that makes one, and writes it down.

        What comes of it has already happened by the time it lands -- a login owns the
        terminal while it runs -- so it is not one of the things this menu holds until it is
        saved. What it runs is asked afterwards, without holding the page up: see
        :meth:`_probes`.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            outcome = await made(showing)
        finally:
            self.opened()
        one = outcome.provider
        if one is None:  # walked out, or a name or a directory that will not do
            if outcome.why:
                self._said = bad(escape(outcome.why))
                self._fill()
            return
        self._told.append(
            f"[dim]{escape(one.cli)}/{escape(one.name)} is written down at "
            f"{escape(str(one.at))}[/dim]"
        )
        if outcome.way_runs and not outcome.status:
            # Said as well as written down: a way with a command of its own owned the
            # terminal while it ran, and whether it landed is the half worth reading.
            self._told.append(
                f"[dim]{escape(one.cli)}/{escape(one.name)} is signed in[/dim]"
            )
        elif outcome.status:
            self._told.append(
                f"hmz: {escape(outcome.why)}"
                if outcome.why
                else f"hmz: signing it in exited {outcome.status}"
            )
        if outcome.copied:
            self._told.append(
                f"[dim]{escape(one.name)} is written down for "
                f"{escape(', '.join(outcome.copied))} too[/dim]"
            )
        self._read_accounts()
        self._aim = self._named(one)
        if outcome.status:
            self._said = bad(
                escape(outcome.why)
                or f"signing {escape(one.name)} in exited {outcome.status}"
            )
            self._fill()
            return
        self._probes(one, copied=outcome.copied)

    @work
    async def _probes(self, one: Provider, *, copied: tuple[str, ...] = ()) -> None:
        """Asks a new account's CLI what it runs, saying so while it does and after.

        In the background: it is a coding agent starting up, some of which take the better
        part of a minute over it, and a page that could not be read or left while it did
        would be a page that looked as though it had hung. So the row says it is being asked
        and the line under the list says how it went -- and why, where the answer was none.

        Args:
          one: The account.
          copied: The other backends it was written down for as well, said alongside.
        """
        named = self._named(one)
        self._asking.add(named)
        self._tell(
            _ACCOUNTS, f"asking {escape(one.cli)} what it runs as {escape(one.name)}…"
        )
        self._fill()
        runs, why = await asks(one.cli, one.name)
        self._asking.discard(named)
        said = self._landed(one, 0, runs=runs, why=why)
        if copied:
            said = (
                f"{escape(one.name)} is written down for {escape(', '.join(copied))} "
                f"too\n{said}"
            )
        self._tell(_ACCOUNTS, said)
        self._fill()

    @staticmethod
    def _landed(one: Provider, status: int, *, runs: int, why: str = "") -> str:
        """What to say about an account that has just been made or signed in again.

        Args:
          one: The account.
          status: What its way in exited with, or 0 for one that ran nothing.
          runs: How many models its CLI then said it runs as it.
          why: Why it said none, where it would not say.

        Returns:
          The line to say under the list.
        """
        if status:
            return f"signing {escape(one.name)} in exited {status}"
        if runs:
            return f"{escape(one.cli)} says it runs {runs} models as {escape(one.name)}"
        return bad(
            f"{escape(one.cli)} did not say what it runs as {escape(one.name)}"
            + (f": {escape(why)}" if why else "")
            + "; ask it again from the model row of an agent run as it"
        )

    @work
    async def _again(self, one: Provider) -> None:
        """Runs one account's own way in again, asking for whatever it still needs.

        Args:
          one: The account.
        """
        accounts = _hmz().accounts
        if not one.name:
            self._said = self._machines(one.cli, "sign in")
            self._fill()
            return
        way = accounts.way(one.cli, one.way)
        if way is None or not way.argv:
            self._said = (
                f"{escape(one.name)} was made by {escape(one.way)}, which has nothing to "
                "run; correct what it holds instead"
            )
            self._fill()
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        # What it already holds answers what it can. A key the CLI keeps in its own store is
        # not among them -- it was never kept here -- so it is asked for again.
        answers = dict(one.env)
        if accounts.asks(way, answers):
            signs = await showing.push_screen_wait(
                Signing(one.cli, way, one.name, copies=False)
            )
            if signs is None:
                return  # walked out, which signs nothing in and changes nothing
            answers |= signs.answers
        try:
            with handed_over(showing):
                status = accounts.sign_in(one, way, answers)
        except OSError as why:  # the backend's own command is not on this machine
            self._said = bad(escape(f"{way.argv[0]}: {why}"))
            self._fill()
            return
        self._told.append(
            f"[dim]{escape(one.cli)}/{escape(one.name)} is signed in[/dim]"
            if not status
            else f"hmz: {escape(way.argv[0])} exited {status}"
        )
        if status:
            self._said = self._landed(one, status, runs=0)
            self._fill()
            return
        # Signed in again is possibly a different account, and certainly a fresh answer to
        # what it runs: an account that has just changed hands is one to ask again.
        self._probes(one)

    @work
    async def _speaks(self) -> None:
        """Asks for a CLI of your own that speaks ACP, and writes it down as a backend.

        A row of its own beside the one that adds an account: this is where somebody looks
        who cannot find their agent among the CLIs an account is made for, and what is
        written down is a backend rather than an account. It outlives the run, so it is a
        backend from the next prompt on, in this workspace and every other -- which is why it
        is not one of the things this menu holds until it is saved.
        """
        from hmz.coganchor import backends

        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            command = await showing.push_screen_wait(Speaks())
        finally:
            self.opened()
        if command is None:
            return
        try:
            # What it is called here is what the command is called, which is the one thing
            # this does not have to ask about: every backend answers to the command that CLI
            # registers, and the writing down is where that is settled.
            name = backends.remember("", shlex.split(command))
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        self._said = f"{escape(name)} is a backend from here on"
        self._told.append(
            f"[dim]{escape(name)} is written down: `{escape(command)}` starts it, "
            "and it is a backend from here on[/dim]"
        )
        self._fill()

    def _applies_accounts(self, told: list[str]) -> None:
        """Does everything the accounts page was holding, and says what became of each.

        Args:
          told: What the transcript is to say, which this adds to.
        """
        accounts = _hmz().accounts
        was = len(told)
        # Taken away first, and then everything that is left: a chain pointed at an account
        # that is going in the same save is a chain that goes nowhere, and one written before
        # the removal would be written and then quietly left dangling.
        for taken in sorted(self._gone):
            cli, _, name = taken.partition("/")
            try:
                gone = accounts.remove(cli, name)
            except ValueError as why:  # a name nothing could ever have been kept under
                told.append(f"hmz: {escape(str(why))}")
                continue
            told.append(
                f"[dim]{escape(taken)} is gone, credentials and all[/dim]"
                if gone
                else f"hmz: no provider {escape(taken)}"
            )
        for one in self._accounts:
            named = self._named(one)
            if named in self._gone:
                continue  # gone above, so there is nothing to correct or point anywhere
            if (answers := self._edits.get(named)) is not None:
                try:
                    corrected = accounts.write(one.cli, one.name, one.way, answers)
                except (OSError, ValueError) as why:
                    told.append(f"hmz: {escape(str(why))}")
                    continue
                told.append(f"[dim]{escape(named)} is corrected[/dim]")
                for cli in self._alike.get(named, ()):
                    try:
                        accounts.copies(corrected, cli)
                    except (OSError, ValueError) as why:
                        told.append(f"hmz: {escape(str(why))}")
                        continue
                    told.append(
                        f"[dim]{escape(cli)}/{escape(one.name)} is corrected with it[/dim]"
                    )
            if (falls := self._chains.get(named)) is not None:
                try:
                    accounts.points(one.cli, one.name, falls)
                except ValueError as why:
                    told.append(f"hmz: {escape(str(why))}")
                else:
                    told.append(
                        f"[dim]{escape(named)} fails over to {escape(falls)}[/dim]"
                        if falls
                        else f"[dim]{escape(named)} fails over to nowhere[/dim]"
                    )
        if len(told) > was:
            # When it is felt, said once rather than on every line: an agent reads the
            # account it was configured with once, so one running now carries on as it was.
            told.append(f"[dim]the accounts apply {self.NEXT_SESSION}[/dim]")


class Adjusted(NamedTuple):
    """What the settings menu answers with: what was changed, and what happened.

    Attributes:
      enable_sentry: Whether humanize reports its own failures from now on, or None where
        that was not touched.
      details: Whether the working of each turn is shown, or None where that was not touched.
      profile: Whether a run in this directory is profiled as well as traced, or None where
        that was not touched.
      forget: Whether to forget what this workspace was set up to run.
      told: What the pages that write for themselves -- the accounts, the fallbacks and the
        flowverses -- did, as lines for the transcript.
      placed: The last thing that happened to the flowverses, or "" for nothing.
      btw: The agent `/btw` asks about a whole flow, as `cli@provider/model:effort` or "" for
        the flow's first agent, or None where that was not touched.
    """

    enable_sentry: bool | None = None
    details: bool | None = None
    profile: bool | None = None
    forget: bool = False
    told: tuple[str, ...] = ()
    placed: str = ""
    btw: str | None = None


class Adjusts(Providers, Fallbacks, Flowverses):
    """Every setting humanize has: `/settings`, one menu of pages, opened on any by its name.

    Everywhere is what is true of this machine however many projects are driven from it;
    this directory is one directory's; the accounts, the fallbacks and the flowverses are
    the places agents run as, turns go when they cannot, and flows come from. One menu
    because they are one question -- what does humanize remember -- and a command apiece
    was five things to learn the names of.

    A menu rather than a file to edit, for the reason every other menu here is one: what is
    written down is written down in humanize's own words, and a person should not have to know
    the shape of a YAML file to turn a thing off. What is held lands together when the menu
    is left and saving is confirmed, and each setting takes effect at once where it can;
    where it cannot, the row says when it will while it is held and the transcript says so
    once it is saved. What runs a command of its own -- making an account, signing one in,
    fetching a flowverse -- happens as it is asked for, as it always did.
    """

    TABS: ClassVar = (
        "Everywhere",
        "This directory",
        "Accounts",
        "Fallback",
        "Flowverses",
    )

    class Settled(Message):
        """Says what the settings menu was answered with, to whoever applies it.

        Posted to the interface rather than only answered to whoever opened the menu: the
        flow menu opens it too, from the row below its flows, and what was changed there is
        the interface's to apply all the same -- the details it shows, the directory it remembers.
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
        page: int = _EVERYWHERE,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the menu on what is remembered now.

        What is written down rather than what is happening: the environment may answer the
        reporting question for one run, and a menu that showed that would be a menu offering
        to change a thing it cannot. The page says so under the list where the two differ.

        Args:
          agents: The backends offered here, and what each of them says it runs, which is
            what the fallback page chooses a place out of.
          page: Which page to open on.
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
        self._tab = page

    def _ask(self) -> None:
        """Says what the menu is, reads the pages that are lists, and puts one up."""
        self.query_one("#asked", Label).update("Settings")
        self._read_accounts()
        self._read_verses()
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _turn_page(self, by: int) -> None:
        """Turns the page, keeping what was said on the last one for when it is turned back to.

        What became of something done on a page -- an account whose CLI would not say what
        it runs, a fetch that failed -- is still true of that page after a look at another,
        and one that was gone on the way back would be one somebody never got to read.

        Args:
          by: One page forward or back.
        """
        self._saids[self._tab] = self._said
        self._said, self._was = "", ""
        # And the rows it was drawn with, which the next page would otherwise read the cursor
        # off: the row to add one more on the accounts is not a row of the fallbacks.
        self.query_one("#choices", OptionList).clear_options()
        super()._turn_page(by)
        if said := self._saids.pop(self._tab, ""):
            self._said = said
            self._fill()

    def _rows(self) -> list[tuple[str, str, str]]:
        """The rows of the first two pages: its id, what it says, and what it means."""
        if self._tab == _DIRECTORY:
            profile = "profile the programs a run here starts"
            if self._profile != self._profile_was:
                profile += f"{_DOT}{_NEXT_RUN}"
            forget = (
                f"forget what is remembered here, across {_many(self._flows, 'flow')}"
            )
            if self._forget:
                forget += f"{_DOT}{_NEXT_LAUNCH}"
            return [
                (
                    _WORKSPACE,
                    _shortly(self._workspace),
                    "the directory these are remembered for",
                ),
                (
                    _RUNS,
                    self._flow or "nothing yet",
                    f"the flow it opens on, set up with {_many(self._roles, 'agent')}",
                ),
                (_PROFILES, _YES if self._profile else _NO, profile),
                (_FORGET, _YES if self._forget else _NO, forget),
            ]
        rows = [
            (
                _SENTRY,
                {True: _YES, False: _NO, None: "not answered yet"}[self._sentry],
                "report what goes wrong to humanize",
            ),
            (_SENT, "", "what a report carries, and what it never does"),
            (
                _DETAILS,
                _YES if self._details else _NO,
                "show every tool call and all of the thinking",
            ),
        ]
        btw = "the agent /btw talks to outside a session"
        if self._btw != self._btw_was:
            btw += f"{_DOT}{_NEXT_BTW}"
        rows.append((_BTW, self._btw or "the flow's first agent", btw))
        if self._btw:
            rows.append((_BTW_FIRST, "", "back to the flow's first agent"))
        return rows

    def _fill(self) -> None:
        """Puts up whichever page is open, and the titles above it."""
        self.query_one("#about", Label).update(
            {
                _EVERYWHERE: "What humanize remembers about this machine.",
                _DIRECTORY: "What it remembers about this directory: the flow it opens "
                "on, and what that flow was last set up to run.",
                _ACCOUNTS: self.ACCOUNTS_ABOUT,
                _FALLBACK: self.STEPS_ABOUT,
                _VERSES: self.VERSES_ABOUT,
            }[self._tab]
        )
        self.tabbed(self._tab_line())
        if self._tab == _ACCOUNTS:
            self._fill_accounts()
        elif self._tab == _FALLBACK:
            self._fill_steps()
        elif self._tab == _VERSES:
            self._fill_verses()
        else:
            self._fill_own()

    def _fill_own(self) -> None:
        """Puts up the first or second page, which are settings rather than lists."""
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(len(rows)))
        at = min(listing.highlighted or 0, len(rows))
        listing.set_options(
            [
                Option(
                    self._row(
                        seen,
                        name,
                        self._says(name, value, about),
                        here=seen == at,
                        inforce=False,
                    ),
                    id=f"={name}",
                )
                for seen, (name, value, about) in enumerate(rows)
            ]
            + [self._saving(here=at == len(rows))]
        )
        listing.highlighted = at
        self._drawn = at
        said = self._said
        if (
            not said
            and self._tab == _EVERYWHERE
            and self._overridden
            and self._sentry == self._sentry_was
        ):
            said = f"{SAYS} is set, so this run does the opposite of what this says"
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._keys_for(rows[at][0] if at < len(rows) else _SAVE)

    @staticmethod
    def _says(name: str, value: str, about: str) -> str:
        """One row, less its name: what it is set to, whether it moves, and what it means.

        Args:
          name: The row, by id.
          value: What it is set to, or "" for a row that is not set to anything.
          about: What it means.

        Returns:
          The line, with the mark that says which of the three kinds of row it is -- turned
          round where it stands, opened onto something to read, or neither.
        """
        mark = _CYCLES if name in _SWITCHES else _OPENS if name in (_SENT, _BTW) else ""
        shown = f"{value} {mark}".strip()
        return f"{shown}   {about}" if shown else about

    def _keys_for(self, held: str) -> None:
        """Says what the keys do on the row under the cursor, which is not the same on each.

        Args:
          held: The row, by id.
        """
        close = Key("esc", "close")
        if held == _SENT:
            self._footed(Key("enter", "read"), close)
        elif held == _BTW:
            self._footed(Key("enter", "choose"), close)
        elif held == _BTW_FIRST:
            self._footed(Key("enter", "go back"), close)
        else:
            self._footed(close)

    def editable(self, row: str) -> bool:
        """Whether a row is a switch, turned round where it stands.

        Only on the first two pages: the others are lists, whose rows are things rather than
        settings, and one of them may be called whatever a switch is called.

        Args:
          row: The row, by id.

        Returns:
          True for the switches.
        """
        return self._tab not in _LISTS and row in _SWITCHES

    def held(self) -> object:
        """What every switch says now."""
        return (self._sentry, self._details, self._profile, self._forget)

    def put_back(self, was: object) -> None:
        """Puts every switch back as it was.

        Args:
          was: What :meth:`held` answered.
        """
        self._sentry, self._details, self._profile, self._forget = cast(
            "tuple[bool | None, bool, bool, bool]", was
        )

    def step(self, row: str, by: int) -> None:
        """Turns one switch round, whichever way the arrow points.

        Args:
          row: The switch.
          by: Which way, which a switch of two has no use for.
        """
        del by
        if row == _SENTRY:
            self._sentry = not self._sentry
        elif row == _DETAILS:
            self._details = not self._details
        elif row == _PROFILES:
            self._profile = not self._profile
        elif row == _FORGET:
            self._forget = not self._forget
        self._said = ""

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Does what enter does on the row chosen, which each page says for itself.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if held == _SAVE:
            self.applied()
        elif self._tab == _ACCOUNTS:
            self._took_account(held)
        elif self._tab == _FALLBACK:
            self._took_step(held)
        elif self._tab == _VERSES:
            self._took_verse(held)
        elif held == _SENT:
            sent, kept = "; ".join(SENT), "; ".join(KEPT)
            self._said = f"Sent: {sent}. Never: {kept}."
            self._fill()
        elif held == _BTW:
            self._chooses_btw()
        elif held == _BTW_FIRST:
            self._btw, self._said = "", ""
            self.changed()
            self._fill()

    @work
    async def _chooses_btw(self) -> None:
        """Sets up the btw agent on the sheet every agent is set up on, and holds it."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            chosen = await showing.push_screen_wait(
                Agent(
                    "the btw agent",
                    read_back(self._btw) or Runs(""),
                    self._offered,
                    unavailable=self._unavailable,
                )
            )
        finally:
            self.opened()
        if chosen is None or not _complete(chosen):
            return
        self._btw, self._said = written(chosen), ""
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

        Making an account and fetching a flowverse happen as they are asked for, so a menu
        walked out of without saving -- or with what it held thrown away -- still has
        something to say about them. And it is said to the interface as well as answered,
        since the interface is what applies the rest.

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


#: What can be done with a run that has already happened, once somebody is inside it: pick it
#: up where it stopped, for a flow that says it can be, and package the whole of it up --
#: trace and all -- to send to somebody who was not there. The first is answered outside this
#: module -- starting a flow is the interface's -- so it is named where it is read, and it is
#: named after the command it is, since a row and a command that did the same thing under two
#: names would be two things to learn.
RESUMES, _EXPORTS = "resume", "export"

#: What the trace an export gathers is filed as, inside the run's own `traces/`. Named for
#: what made it rather than for the moment it was made: a trace gathered by hand keeps both
#: when it is gathered twice, and this one is of a run that is over and will not read any
#: differently tomorrow.
EXPORTED = "export.trace.json"

#: How much of a task a row of the runs shows, before it is what a run is rather than a line.
_ENOUGH_TASK = 60


class Doing(NamedTuple):
    """What somebody asked to have done with one run that has already happened.

    Attributes:
      epic: The run, by the directory it is written in, or None where this is only what the
        sheet has to say on the way out.
      doing: What to do with it, which is what the menu under it answered, and "" where the
        sheet did it itself.
      said: What happened while the sheet was open, for the transcript: a menu that wrote an
        archive and said nothing afterwards is one nobody can read back.
    """

    epic: Path | None = None
    doing: str = ""
    said: tuple[str, ...] = ()


def _many(count: int, thing: str) -> str:
    """How many of something there were, said as English says it.

    Args:
      count: How many.
      thing: What they are, in the singular.

    Returns:
      The two words -- `1 session`, `3 sessions` -- since a sheet is prose and `1 sessions`
      is a sheet that reads as a template somebody forgot to finish.
    """
    return f"{count} {thing}" if count == 1 else f"{count} {thing}s"


def _asked_for(task: str) -> str:
    """What a run was asked to do, as much of it as a row has room for.

    Args:
      task: The whole of it, which is however long whoever started the run made it.

    Returns:
      Its first line's worth, on one line, cut with an ellipsis where it was cut.
    """
    said = " ".join(task.split())
    return said if len(said) <= _ENOUGH_TASK else f"{said[: _ENOUGH_TASK - 1]}…"


def _when(said: str) -> str:
    """One of the moments an epic writes down, as a row of a list says one.

    Args:
      said: The moment, as it was written -- `2026-08-16T03:04:05.123Z`.

    Returns:
      It, to the minute, and whatever was written where that is not what it is.
    """
    if len(said) < len("YYYY-MM-DDTHH:MM"):
        return said
    return said[:16].replace("T", " ")


class Does(Picks):
    """One run that has already happened, gone into: what it was, and what there is to do.

    Which is a second sheet rather than more keys on the first: a list of runs is a list
    somebody is reading, and what there is to do with one of them depends on the one under
    the cursor -- a flow that says it can be picked up is picked up, and one that says
    nothing is a run to read rather than a run to continue.

    Going into a run is how its directory is reached, so that is said here rather than
    fetched: where a run is written down was a row of its own that printed a path, which is
    an errand to send somebody on for something the sheet was already about.
    """

    #: A few rows, read rather than narrowed.
    SEARCHES: ClassVar = False

    def __init__(self, ran: Ran, *, resumable: bool) -> None:
        """Goes into one run.

        Args:
          ran: The run, as it was written down.
          resumable: Whether its flow says now that it can be picked up, which is asked of
            the flow rather than of the run: a flow may have been rewritten since.
        """
        super().__init__()
        self._ran = ran
        self._resumable = resumable
        self.asked = f"{_when(ran.began)}{_DOT}{ran.flow}"
        #: Where it is written first, on a line of its own: it is the long part and the part
        #: somebody copies, and a path wrapped into the middle of a sentence is one that has
        #: to be picked back out of it.
        self.about = (
            f"{escape(str(ran.at))}\nIt {_how(ran)}, driving "
            f"{_many(len(ran.agents), 'agent')} through "
            f"{_many(len(ran.sessions), 'session')}."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """Carrying on where it stopped, where that is a thing this flow can do, and sending it.

        Two rather than four. Gathering a trace wrote a file into the run that an export
        would have carried anyway, so exporting gathers one and packs it: a bundle read by
        somebody who was not there is a bundle with the timeline already in it.
        """
        held: list[tuple[str, str, str]] = []
        if self._resumable:
            held.append(
                (
                    RESUMES,
                    "resume this run",
                    "run the flow again on what this run left behind",
                )
            )
        held.append(
            (
                _EXPORTS,
                "export it",
                "the whole run as one archive, with a trace of it in",
            )
        )
        return held

    def nothing(self) -> str:
        """Why carrying on is not one of the things there are to do, where it is not."""
        if self._resumable:
            return ""
        return (
            f"{escape(self._ran.flow)} does not say it can be picked up, so there is "
            "nothing to carry on from"
        )


def _how(ran: Ran) -> str:
    """How one run ended, as a line about it reads.

    Args:
      ran: The run.

    Returns:
      What became of it, in words: a run with no end written down is one that was abandoned
      where it stood -- the machine it was on went, or the interface came down under it.
    """
    return {
        "done": "finished",
        "failed": "failed",
        "stopped": "was stopped",
    }.get(ran.how, "was left unfinished")


def exported(ran: Ran) -> tuple[Path, int, str]:
    """Gathers one run's trace, and packages the whole run up with it as one archive.

    One thing rather than two rows. A trace gathered here lands in the run's own `traces/`,
    which is part of what an export carries -- so the two were a row that wrote a file and a
    row that would have packed it anyway, and the one anybody sends is the archive. Whoever
    opens it can read the run as a timeline without gathering anything themselves, which is
    what a bundle sent to somebody who was not there has to be good for.

    The trace is of that run's own sessions and no others: a directory may have been run in a
    hundred times, and a trace filed under one of those runs while holding the other
    ninety-nine is a trace of nothing anybody asked about. They are asked for by the ids the
    run wrote down rather than by directory, so a flow that worked in a machine's mirror is
    in its own trace too.

    Beside the run rather than in this directory: an epic is what a run was, and the trace of
    that run belongs with the sessions it points at and the state it left. A trace of what a
    directory holds whoever opened it is `Hmz().epics.trace` with no sessions
    named, and a trace written somewhere else is its `output`: both are Python, there being no
    run here to hang either on.

    No screen goes in. What is drawn is the run that is going and this is a run out of the
    list, often one from last week, so a transcript here would be a bundle saying something
    about that run that is not true of it.

    Args:
      ran: The run.

    Returns:
      Where the archive was written, how big it came out, and a line saying what the trace
      inside it holds.
    """
    from hmz.runtime.epic import TRACES

    runs = _hmz().epics
    # Under a name of its own rather than the moment it was gathered, so that exporting one
    # run twice leaves one trace rather than a pile of identical ones -- a finished run does
    # not change, the archive replaces itself for the same reason, and an epic that grew a
    # trace every time somebody sent it would make every later archive bigger than the last.
    _, document = runs.traced(ran.at, output=ran.at / TRACES / EXPORTED)
    at, _ = runs.bundled(ran.at)
    said = document["otherData"]
    held = f"{_many(_counted(said, 'sessions'), 'session')}, "
    held += _many(_counted(said, "slices"), "slice")
    # Only where the run was profiled: a trace that reported nought programs on every run
    # would be one more thing to read past on the traces that are only ever sessions.
    if _counted(said, "programs"):
        held += f", {_many(_counted(said, 'programs'), 'program')}"
    return at, at.stat().st_size, held


def _counted(said: dict[str, Any], of: str) -> int:
    """How many of something a trace says it holds, out of the strings it says it in.

    Args:
      said: What the trace says about itself.
      of: Which count.

    Returns:
      It as a number, and nought for one that is missing or is not one -- a line about an
      export is not worth failing an export over.
    """
    try:
        return int(said.get(of, 0))
    except (TypeError, ValueError):
        return 0


class Epics(Sheet[Doing]):
    """Every run of a flow in this directory, newest first, and what to do with one.

    A run is written down as it happens -- which flow, on what, by which agents, and which
    sessions each of them opened -- and until now nothing showed them. What they are for is
    two things: reading one back afterwards, which is what the sessions kept in it are, and
    carrying one on, which is what a flow that says it can be picked up is for.

    Read rather than chosen from, so enter goes into the run under the cursor rather than
    doing anything to it: what there is to do is what that run is, and the sheet it opens is
    where the run says where it is written down.
    """

    SEARCHES: ClassVar = True

    def __init__(
        self,
        workspace: Path | None = None,
        *,
        running: Callable[[], bool] | None = None,
    ) -> None:
        """Reads every run of this directory.

        Args:
          workspace: Which directory's, defaulting to this one.
          running: Whether a flow is going, asked rather than answered once -- a list is
            read while a run goes and outlives it, and one that had taken the answer down
            as it opened would refuse to pick a run up in the name of a flow that has since
            finished. None for nothing to ask, which is nothing running.
        """
        super().__init__()
        from hmz.daemon import Hmz

        runs = Hmz(workspace).epics
        #: Newest first: what somebody opening this came to look at is the run that has just
        #: happened, and a list of a hundred is one nobody scrolls to the end of.
        self._ran = [
            one
            for one in (runs.read(at) for at in reversed(runs.all()))
            if one is not None
        ]
        self._underway = running or (lambda: False)
        #: Which run the cursor is on, by the directory it is written in: rows are narrowed
        #: by a search, so a row number is not a run.
        self._was = ""
        #: What is worth saying under the list.
        self._said = ""
        #: Whether each flow says now that it can be picked up, by flow: reading one means
        #: running its file, so it is asked once and only for the flows asked about.
        self._resumes: dict[str, bool] = {}
        #: What is worth saying in the transcript once this sheet is done with.
        self._told: list[str] = []

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Epics")
        self.query_one("#about", Label).update(
            "Every run of a flow in this directory, newest first: what it was, how it went, "
            "and how many sessions it opened."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _about(self, ran: Ran) -> str:
        """What a row says about one run: what it was asked to do, how it went, and its size.

        How it went only where it went some other way than finishing: a list of runs is
        mostly runs that finished, and a column saying so of nearly all of them is a column
        that says nothing while taking the room the ones that did not need.
        """
        said = _asked_for(ran.task) if ran.task else "no task"
        held = f"{said}{_DOT}{_many(len(ran.sessions), 'session')}"
        if ran.how != "done":
            held += f"{_DOT}{_how(ran)}"
        # Asked of the flow rather than read off the run, for the reason the menu asks it of
        # the flow: a flow is a directory on disk, and one marked resumable since that run is
        # one whose older runs can be picked up now.
        return f"{held}{_DOT}can be picked up" if self._carries_on(ran) else held

    def _fill(self) -> None:
        """Puts the runs up, marked where the cursor is."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        # The row that searches is not a run, so a cursor on it is on none of them.
        seeking = self.under() == _SEARCH
        shown = [one for one in self._ran if self.fits(one.flow, one.task, one.name)]
        self._counting = len(str(max(len(shown), 1)))
        if all(one.name != self._was for one in shown):
            self._was = shown[0].name if shown else ""
        listing.set_options(
            [
                Option(
                    self._row(
                        seen,
                        f"{_when(one.began)}{_DOT}{one.flow}",
                        _briefly(self._about(one), self.size.width),
                        here=not seeking and one.name == self._was,
                        inforce=False,
                    ),
                    id=f"={one.name}",
                )
                for seen, one in enumerate(shown)
            ]
            + [self._seeking(here=seeking or not shown)]
        )
        listing.highlighted = (
            len(shown)
            if seeking or not shown
            else next((at for at, one in enumerate(shown) if one.name == self._was), 0)
        )
        self._drawn = listing.highlighted
        said = self._said or ("" if self._ran else self._nothing())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "go into one"), Key("esc", "close"))

    def leaving(self) -> None:
        """Leaves, saying in the transcript whatever was gathered while this was open."""
        self.dismiss(Doing(said=tuple(self._told)) if self._told else None)

    def _nothing(self) -> str:
        """What an empty list says, which is that nothing has been run here yet."""
        return "no flow has been run in this directory yet"

    async def _exports(self, ran: Ran) -> None:
        """Gathers one run's trace and packages the whole run up around it, as one archive.

        Off the event loop: reading a run's sessions back is every log every backend wrote
        for it, and following and compressing them after that is seconds more on a long run
        -- and an interface that stopped redrawing while it ran would be one that looked as
        though it had gone away.

        Args:
          ran: The run.
        """
        import asyncio

        from hmz.runtime.exporting import sized

        self._said = f"exporting {escape(ran.name)}…"
        self._fill()
        try:
            at, size, held = await asyncio.to_thread(exported, ran)
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        said = f"{escape(str(at))}{_DOT}{sized(size)}{_DOT}{escape(held)}"
        self._said = said
        self._told.append(f"[dim]{said}[/dim]")
        self._fill()

    def _follows(self, listing: OptionList) -> None:
        """Takes which run the cursor is on off the list, by the directory it is written in."""
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named and named not in _APART:
                self._was = named

    def _under(self) -> Ran | None:
        """The run the cursor is on, or None where the list has nothing in it."""
        return next((one for one in self._ran if one.name == self._was), None)

    def _carries_on(self, ran: Ran) -> bool:
        """Whether one run can be carried on: its flow says so now, and it left a journal.

        Args:
          ran: The run.

        Returns:
          Whether picking it up would have anything to pick up from.
        """
        return self._picks_up(ran.flow) and _hmz().epics.picks_up(ran.at)

    def _picks_up(self, flow: str) -> bool:
        """Whether one flow says now that it can be picked up.

        Asked of the flow rather than of the run that recorded it: a flow is a directory on
        disk and may have been rewritten since, and what can happen next is what it says now.
        Asked once per flow, since reading one means importing it.

        Args:
          flow: The flow, as the run named it.

        Returns:
          Whether it is resumable, and False for one that will not load at all -- a flow that
          cannot be read cannot be run, which is what carrying on would come to.
        """
        if flow not in self._resumes:
            try:
                self._resumes[flow] = _hmz().flows.resumes(flow)
            except Exception:  # noqa: BLE001 -- a flow is a file, and reading one runs it
                self._resumes[flow] = False
        return self._resumes[flow]

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Goes into the run under the cursor.

        Args:
          event: What was chosen.
        """
        named = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._ran if each.name == named), None)
        if one is not None:
            self._doing(one)

    @work
    async def _doing(self, ran: Ran) -> None:
        """Goes into one run, and does what was asked there or answers with it.

        Args:
          ran: The run.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(
            Does(ran, resumable=self._picks_up(ran.flow))
        )
        if said is None:
            return  # walked out of it, which does nothing to the run
        if said == _EXPORTS:
            await self._exports(ran)
            return
        if said == RESUMES and self._underway():
            # Said here rather than on the way out: the question this sheet is asking is
            # still worth answering, and a flow is stopped with esc rather than from here.
            self._said = "a flow is running; ctrl+c twice stops it before another can be picked up"
            self._fill()
            return
        self.dismiss(Doing(ran.at, said, tuple(self._told)))


#: The transcript every agent's work appears on, which is what the first node of the monitor
#: reads and what the log opens on. Written down once, here, and read from `hmz.tui.app` and
#: `hmz.tui.monitoring` rather than said again there: two names for it are two that could come
#: apart.
#:
#: Nobody's, since it is not an agent's: an agent id is what every other transcript is kept
#: under, and no agent is called this.
EVERY = ""
