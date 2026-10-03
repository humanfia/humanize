"""The sheets: which flow, how it is set up, what each of its agents runs, and how it goes.

Drawn as Claude Code draws its own `/model`, which is the same question one step along: a rule
of `▔` across the top, the question and a line about it indented three, the choices numbered
with `❯` against the one under the cursor and a `✔` against the one already in force. A value
that is one of a few -- an effort, a switch, a backend -- is picked out of every value it can
take, dropped under its row (:mod:`hmz.tui.dropdown`), rather than stepped along with the
arrows across: a value nobody has seen listed is a value nobody knows is there.

Two things are said in one place for the whole file. The keys are said at the bottom and
nowhere else: :meth:`Sheet._footed` builds that row, so that `no key said twice on one sheet`
is a rule about the whole row rather than about any line of it -- a sheet that wrote its own
had no way of knowing it had said `esc` in the line about itself and `esc` again at the
bottom. And whatever is to be done about a list rather than picked out of it -- saving what
the menu holds, adding one more of what the list is of, being rid of what the sheet is about
-- is a row set apart from the choices and out of their numbering: numbered among them, saving
read as one more thing to pick, and a menu whose way out looks like one of its answers is a
menu nobody can see the way out of. `/settings` goes one further: each of its pages says what
it does about its list as a list of :class:`Action`, drawn as a bar of buttons under the list
(:mod:`hmz.tui.settings`), saving last, so that each page is laid out as the last one was.

A flow is set up by role: each agent role it declares is a CLI, an account, a model and an
effort (:class:`Agent`); each environment role is a backend, a machine and a directory there
(:class:`Placing`), which is what `-e` writes; and beside them are the flow's own params and
what a run of it may spend. The order of one agent's
rows is the order of what depends on what: an account belongs to a backend and a model belongs
to the CLI that runs it, so neither can be asked before the CLI has been. The backends are read
one at a time, a tab apiece: the ones installed here plus an optional one the sheet can teach
somebody to install. Every model of
every CLI in one list is a list that grows each time any of them ships a model. The effort is
picked from the ones the model takes, dropped under its row.

The run itself, drawn, is not a sheet: it is the monitor, a screen of its own in
:mod:`hmz.tui.monitoring`.
"""

from __future__ import annotations

import contextlib
import datetime
import re
import shlex
import sys
import textwrap
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
)

from pydantic import BaseModel, Field, field_validator, model_validator
from rich.markup import escape
from textual import events, on, work
from textual.await_complete import AwaitComplete
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Offset
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from hmz.coganchor import backends
from hmz.coganchor.agents import SWARM, driver
from hmz.coganchor.prices import money
from hmz.coganchor.spelling import parted
from hmz.flows import Budget
from hmz.runtime import telemetry
from hmz.runtime.kept import Runs
from hmz.runtime.telemetry import KEPT, SENT

from .discover import installed, ready_to_open
from .dropdown import Dropdown, Value, anchor
from .monitor import thousands
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from pydantic.fields import FieldInfo
    from textual.app import App, ComposeResult

    from hmz.coganchor.agents import AgentBase
    from hmz.coganchor.backends import Model, Way

    # Under another name, because that is what it is on these pages: one place's step, the
    # chain it falls back along and how it is tried again.
    from hmz.coganchor.fallbacks import Falls as Step
    from hmz.coganchor.machines.sshconfig import SSHHost
    from hmz.coganchor.machines.store import (
        DockerRuntime,
        Runtime,
        SSHRuntime,
        SwarmRuntime,
    )
    from hmz.coganchor.providers import Provider
    from hmz.daemon import Hmz
    from hmz.runtime.epic import Ran
    from hmz.runtime.flowing import AgentRole, EnvRole


__all__ = [
    "DETACHES",
    "EVERY",
    "EXPORTED",
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
    "Held",
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
    "complete",
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

#: What says a row opens onto a sheet of its own, and what says its values are dropped under
#: it to be picked from, as a `<select>` says so on a web page. Two marks because they are the
#: two things a row of a menu can be besides one that is written, and a reader who has to press
#: a key to find out which one they are on is a reader the row did not tell.
_OPENS, _DROPS = "▸", "▾"

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
#: Answering a form with everything written into it: `done`, on every form.
_DONE = f"{_APART_MARK}done"
#: The row of the list a role's machine is chosen from that names an ssh host nobody saved,
#: and the row of the form a docker daemon is written on that asks the daemon what it has.
_UNSAVED = f"{_APART_MARK}unsaved"
_DETECTS = f"{_APART_MARK}detects"

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
    {
        _SAVE,
        _ADD,
        _SEARCH,
        _AGAIN,
        _DONE,
        _TAKES_AWAY,
        _BUDGET,
        _UNSAVED,
        _DETECTS,
    }
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
    _DONE: "done",
    _TAKES_AWAY: "remove",
    _BUDGET: "set",
    _UNSAVED: "type a host",
    _DETECTS: "detect",
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
Configures, Flows, Form {
    align: center middle; background: $background; }
#sheet { width: 100%; height: auto; padding: 0; }
#rule { height: 1; color: $primary; }
#asked { padding: 0 0 0 3; text-style: bold; color: $primary; }
#about { padding: 0 3 1 3; color: $text-muted; width: 1fr; }
/* The row above the list: the places a list of flows is one of. A sheet that is one list
   says nothing here, and a label with nothing in it is a row nobody paid for. */
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
#: arrows up and down walk the rows, these step between the lists a page is made of, enter
#: opens the row under the cursor, drops its values under it or begins writing it, and esc
#: steps back -- so nothing about working one has to be known before it is opened.
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


class Drop(NamedTuple):
    """What a row whose values are dropped under it drops: every one of them, and which is in force.

    Attributes:
      title: What the row is called, which the list is headed with.
      values: Every value it can take, in order.
      current: The one in force, which is ticked.
      cursor: Which value the list opens on where not the one in force: a switch opens on the
        other of its two, so that enter twice turns it round as a switch is turned.
    """

    title: str
    values: Sequence[Value]
    current: str
    cursor: str | None = None


#: What a switch reads as, on every sheet that has one: the two words its dropped list says.
_YES, _NO = "on", "off"


def switch(values: Sequence[str]) -> bool:
    """Whether a row's values are a switch's: `on` and `off`, in either order.

    Args:
      values: Every value the row can take.

    Returns:
      True for the two words of a switch and nothing else.
    """
    return len(values) == 2 and set(values) == {_YES, _NO}  # noqa: PLR2004 -- two sides


def switched(title: str, current: str, means: tuple[str, str] = ("", "")) -> Drop:
    """The two values of a switch, dropped under its row, opening on the one it is not.

    Args:
      title: What the row is called.
      current: `on` or `off`, as it is now.
      means: What each of the two means, said beside it.

    Returns:
      The list.
    """
    return Drop(
        title,
        (Value(_YES, _YES, means[0]), Value(_NO, _NO, means[1])),
        current,
        cursor=_NO if current == _YES else _YES,
    )


class Sheet[T](ModalScreen[T | None]):
    """One question drawn the way Claude Code draws one, answered by picking a line.

    What answering it comes to is the sheet's own: a flow is a name, an agent is what it runs
    and where, and walking out without answering is None wherever it is asked. What is reached
    by picking something is opened with enter on the thing it is about and left on esc, rather
    than being a tab beside the list it was picked from: a tab between a list and the thing
    picked out of it reads as a view that was there all along, which hides that anything was
    picked at all.

    Four keys and no more: the arrows up and down walk the rows, the arrows across step
    between the lists a page is made of where it has several, enter opens the row under the
    cursor and esc steps back. Everything else a sheet does is a row of it -- searching,
    adding, saving -- so that nothing has to be known before it is found. A row whose value is
    one of a few has every one of them dropped under it by enter or a click, as `/settings`
    has (:mod:`hmz.tui.dropdown`), and one is picked with enter or a click; a row that is
    written is written where it stands: enter begins, typing changes it, enter keeps what it
    now says and esc puts back what it said before.
    """

    CSS = _SHEET
    # All of them priority, so that they are taken in the order they were pressed: a key the
    # list under the cursor took for itself would be handled after one the sheet took, and
    # enter then an arrow pressed quickly would step to the next list before the row was begun
    # on.
    BINDINGS: ClassVar = [
        Binding("escape", "back", "back", show=False, priority=True),
        Binding("up", "walk(-1)", "up", show=False, priority=True),
        Binding("down", "walk(1)", "down", show=False, priority=True),
        Binding("enter", "enter", "open", show=False, priority=True),
        # Refused where they do nothing -- see :meth:`check_action` -- so that a sheet of one
        # list lets them fall through.
        Binding("left", "across(-1)", "back", show=False, priority=True),
        Binding("right", "across(1)", "next", show=False, priority=True),
    ]

    #: Which row the marker was last drawn against. Putting the rows up moves the cursor,
    #: which asks for them to be put up again -- and the message saying so is posted rather
    #: than called, so a flag set around the drawing is already clear by the time it arrives.
    #: What breaks the loop is having nothing to do: the marker is already where it goes.
    _drawn: int | None = None
    #: How many columns the numbering takes, so that every row starts in the same one.
    _counting = 1
    #: How far in the column of values starts, which a list dropped under a row is dropped
    #: under.
    _values_at = 0
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
    #: Which row is being written, by its id, or "" while none is. Writing one is begun on
    #: purpose, with enter, so that walking past a row can never change it.
    _editing = ""
    #: What the sheet held before that row was begun on, which esc puts back.
    _before: object = None
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
    #: several.
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

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002 -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of this sheet's own keys is live now.

        The arrows across only on a sheet whose one page is several lists, and not while a
        row is being written. Anywhere else they are refused, so that they fall through to
        whatever is under the sheet rather than being swallowed by it. And a key that is a
        letter is the sheet's only while nothing is being typed into a search.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it. A binding refused here is one the key falls through.
        """
        if action == "across":
            return self.ASIDE and not self._editing
        if action in ("walk", "enter"):
            return bool(self.query("#choices"))
        return not (self._searching and action in self.LETTERS)

    def action_walk(self, by: int) -> None:
        """Walks the cursor a row up or down, unless the row it is on is being written.

        Args:
          by: One row down, or one up.
        """
        listing = self.query_one("#choices", OptionList)
        if by < 0:
            listing.action_cursor_up()
        else:
            listing.action_cursor_down()

    def action_enter(self) -> None:
        """Opens the row under the cursor, or drops, begins or keeps it -- see :meth:`pressed`."""
        self.query_one("#choices", OptionList).action_select()

    def action_across(self, by: int) -> None:
        """Steps to the next of the lists this page is made of.

        Args:
          by: One on, or one back.
        """
        self.aside(by)

    def aside(self, by: int) -> None:
        """Steps to another of the lists this page is made of, for a sheet that has them.

        Args:
          by: One on, or one back.
        """

    def editable(self, row: str) -> bool:
        """Whether a row is written where it stands rather than opened, which each sheet says.

        Args:
          row: The row, by id.

        Returns:
          True for one that enter begins writing.
        """
        del row
        return False

    def drops(self, row: str) -> bool:
        """Whether a row's values are dropped under it to be picked from, which each sheet says.

        Args:
          row: The row, by id.

        Returns:
          True for one that enter or a click drops its values under -- see :meth:`dropping`.
        """
        del row
        return False

    def dropping(self, row: str) -> Drop:
        """What a row whose values are dropped under it drops, which each sheet with one says.

        Args:
          row: The row, by id, one :meth:`drops` said is one.

        Returns:
          Its values, and which is in force.
        """
        raise NotImplementedError

    def dropped(self, row: str, picked: str) -> None:
        """Holds the value picked for a row, which each sheet with one says how to.

        Args:
          row: The row, by id.
          picked: The value, which is not the one that was in force.
        """

    def writes(self, row: str, event: events.Key) -> bool:
        """Types one key into a row being written.

        Args:
          row: The row, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        del row, event
        return False

    def held(self) -> object:
        """Everything a row of this sheet can be written to, as esc would put it back.

        Returns:
          Something :meth:`put_back` takes back, and that compares equal while nothing moved.
        """
        return None

    def put_back(self, was: object) -> None:
        """Puts back what :meth:`held` answered, which is esc while a row is being written.

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
          True for a row written where it stands on a sheet whose letters begin writing.
        """
        return self.TYPES and self.editable(row)

    def pressed(self) -> bool:
        """Takes enter where it drops a row's values, begins or ends writing it, or searches.

        Asked by the list before it picks the row under the cursor, whether enter was pressed
        or the row was clicked: enter on a row whose values are dropped under it drops them,
        enter on a row that is written begins writing it and does not pick it, and enter
        while one is being written keeps what it now says.

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
        if row and self.drops(row):
            self._drops(row)
            return True
        if self.editable(row):
            self._editing, self._before = row, self.held()
            self._fill()
            return True
        return False

    def dropped_at(self) -> Offset:
        """Where the value of the row under the cursor starts, which its list drops under."""
        return anchor(self.query_one("#choices", OptionList)) + Offset(
            self._values_at, 0
        )

    @work
    async def _drops(self, row: str) -> None:
        """Drops every value a row can take under it, and holds the one picked.

        Esc, or a click off the list, picks nothing; picking the one in force changes nothing.

        Args:
          row: The row, by id.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            drop = self.dropping(row)
            picked = await showing.push_screen_wait(
                Dropdown(
                    drop.title,
                    drop.values,
                    drop.current,
                    at=self.dropped_at(),
                    cursor=drop.cursor,
                )
            )
        finally:
            self.opened()
        if picked is None or picked == drop.current:
            return
        # Said to be edited only where what is held moved, as a row written is: a form whose
        # edits throw away what was checked must not throw it away for nothing. A sheet that
        # holds nothing it can put back took a value other than the one in force, which is.
        before = self.held()
        self.dropped(row, picked)
        if before is None or self.held() != before:
            self.edited()
        self.kept(row)
        self._fill()

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

    def ranks(self, *fields: str) -> int:
        """How near a row that :meth:`fits` comes to what was typed, the nearest being least.

        A search finds by letters spread through a name, which is what makes a few of them
        enough -- and what makes a long name holding every letter of a short one a match for
        it. Left in the order the list came in, the model somebody typed out whole was found
        below one that merely held its letters: `claude-sonnet-5` under `claude-sonnet-4-5`.
        So what was typed is the name itself first, then the start of one, then a run of one,
        and only then letters spread through one; rows equally near keep the list's own order.

        Args:
          fields: Everything the row says, as :meth:`fits` was given it.

        Returns:
          0 for a field that is what was typed, 1 for one it opens, 2 for one it is inside of,
          and 3 for anything else -- which is every row, where nothing has been typed.
        """
        wanted = self._typed.lower()
        if not wanted:
            return 3
        looking = [field.lower() for field in fields]
        if wanted in looking:
            return 0
        if any(one.startswith(wanted) for one in looking):
            return 1
        if any(wanted in one for one in looking):
            return 2
        return 3

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

        Above rather than below: what is done about a list -- adding to it, searching it,
        bringing more into it -- is found in the same place on each sheet that has them, and
        on a list that is empty it is the whole of the sheet.

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

        The row says what the keys do *now*. While a row is being written that is writing it
        and nothing else. Otherwise enter is what the row under the cursor is, and esc comes
        out of a running search before it leaves the sheet.

        Args:
          keys: This sheet's keys, in the order they are reached for.
        """
        if self._editing:
            keys = (
                # The one chord, which only a row being written that takes a list has.
                *(one for one in keys if one.key == _CHORD),
                Key("enter", "keep"),
                Key("esc", "undo"),
            )
        else:
            # What enter does on the row under the cursor, while the list is where enter
            # goes: on a sheet with something else to focus, its keys are its own.
            focus = self.focused
            listed = focus is None or focus.id == "choices"
            under = self.under() if listed and self.query("#choices") else ""
            apart = under if under in _APART else ""
            said = (
                self.DONE
                if apart == _DONE
                else _ON_APART.get(apart)
                or (
                    "choose"
                    if under and self.drops(under)
                    else "change"
                    if under and self.editable(under)
                    else None
                )
            )
            if under and self.written(under):
                # Typing is what writes it, so typing is what the row of keys says: enter
                # begins it as well, which is the same thing done the long way round.
                keys = (
                    Key("type", "to edit"),
                    *(one for one in keys if one.key != "enter"),
                )
            elif said:
                keys = (
                    Key("enter", said),
                    *(one for one in keys if one.key != "enter"),
                )
            if self._searching:
                keys = (
                    *(one for one in keys if one.key != "esc"),
                    Key("esc", "cancel search"),
                )
        # Kept as well as drawn, so that `no key twice on one sheet` is a thing a test can
        # read off the sheet rather than pick back out of a line of markup.
        self._keyed = keys
        self.query_one("#keys", Label).update(self.keys_line(keys))

    def keys_line(self, keys: Sequence[Key]) -> str:
        """The row of keys as it is drawn, which is plain words on every sheet but one.

        Args:
          keys: The keys, as :meth:`_footed` settled them.

        Returns:
          The row, as markup.
        """
        return _said(*keys)

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
        """The rule, the question, the strip, what there is to choose, what is tuned, the keys.

        Every sheet is made of the same parts whether or not it uses them. The strip of lists
        above the choices is the one part that is taken away again where a sheet has none --
        see :meth:`tabbed` -- so that a sheet which is one list is drawn as one list and
        nothing moved down a row.
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
        # Gone rather than blank until a sheet says what its list is one of: a label with
        # nothing in it still takes the row it is padded to.
        self.tabbed("")
        self._ask()

    def tabbed(self, said: str) -> None:
        """Puts the row above the choices up, or takes it back where there is nothing for it.

        Args:
          said: What a sheet says the list is one of, as markup -- and "" for a sheet that is
            one list of one thing.
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

    Which is what makes several pages one menu: going to another applies nothing, so what is
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


#: The units a duration is written back in, largest first, in microseconds. Days and not
#: weeks: `12d` is read at a glance where `1w5d` has to be added up.
_WRITTEN_IN = (("d", 86_400_000_000), ("h", 3_600_000_000), ("m", 60_000_000))


def _units(duration: datetime.timedelta) -> str:
    """A duration, written the way `-b duration=` reads one.

    Counted in whole microseconds, which is all a duration holds, so that what is written is
    exactly what is read back however long it is: `12d`, `1h30m`, `1.5s`, `0s`.

    Args:
      duration: The duration. Not negative, which no budget's is.

    Returns:
      Each unit that is not nothing, largest first, and seconds to the microsecond.
    """
    left = duration // datetime.timedelta(microseconds=1)
    said = ""
    for unit, size in _WRITTEN_IN:
        whole, left = divmod(left, size)
        if whole:
            said += f"{whole}{unit}"
    seconds, micro = divmod(left, 1_000_000)
    if micro:
        said += f"{seconds}.{micro:06d}".rstrip("0") + "s"
    elif seconds or not said:
        said += f"{seconds}s"
    return said


def spent(budget: Budget) -> str:
    """What a budget caps, shortest first, as a row says it.

    Args:
      budget: The budget.

    Returns:
      Each limit it sets -- the time as the sheet it is set on writes it, the output tokens,
      the money -- and `no limit` for the one a conversation runs under, whose one cap is an
      infinite cost.
    """
    import math

    caps: list[str] = []
    if budget.duration is not None:
        caps.append(_units(budget.duration))
    if budget.output_tokens is not None:
        caps.append(f"{thousands(budget.output_tokens)} out")
    if budget.cost is not None and not math.isinf(budget.cost):
        caps.append(money(budget.cost))
    if not caps:
        return "no limit"
    return ", ".join(caps) + ("" if budget.graceful else ", even mid-turn")


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


def complete(runs: Runs) -> bool:
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
    may hold slashes and colons of its own, while a CLI and an effort never do.

    Args:
      runs: The agent.

    Returns:
      The model, or "" for an agent nobody has answered yet.
    """
    return parted(runs.spec.partition("/")[2])[0]


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


#: What separates the two halves of a row's id where it is made of two names -- a CLI and
#: an account of it. A byte no name has in it, since either half may hold anything.
_HALVES = "\x1f"


def _always() -> bool:
    """True, for an action that can always be taken."""
    return True


class Action(NamedTuple):
    """One thing done about a page's list rather than to one thing on it: a button under it.

    What a page of `/settings` does about its list -- adding to it, bringing more into it,
    searching it, saving -- is said by the page as a list of these, in the order they stand,
    and the bar under the list is drawn from that list and nothing else.

    Attributes:
      key: What it is known by, which its button's id is made of: `act-<key>`.
      label: What its button says.
      about: What it does, said when the button is pointed at.
      does: What pressing it does.
      able: Whether it can be pressed now: a save with nothing to save cannot.
    """

    key: str
    label: str
    about: str
    does: Callable[[], object]
    able: Callable[[], bool] = _always


#: What each button under a page of `/settings` is known by. Words rather than the ids of rows
#: set apart, because a button is not a row of the list and its id cannot be taken for a name
#: somebody chose.
_ACT_ADD, _ACT_SPEAKS, _ACT_IMPORTS = "add", "speaks", "imports"
_ACT_SEARCH, _ACT_SAVE = "search", "save"


class Pages(Drafts["Adjusted"]):
    """What every page of `/settings` shares: where the cursor is, and what has been said.

    One menu rather than six, so there is one line under the list and one account of what
    happened for the transcript however many pages it happened on. Each page after the first
    two is a class of its own that :class:`Adjusts` is made of -- what a list of accounts does
    is a good deal of code, and it reads better beside the sheets it opens than folded into
    one class five times as long -- and this is what they have in common.

    And each of those is put up the same way, so that a page is laid out as the last one was:
    the list, with the cursor landed by :meth:`_lands` and put there by :meth:`_put`, and what
    is done about the list -- `add …`, anything else that brings one in, search, and saving
    where the page holds anything until it is saved -- said as a list of :class:`Action`, which
    :class:`hmz.tui.settings.Adjusts` draws as the buttons under the list. Enter on something
    listed opens its own menu, taking it away last; adding one opens a :class:`Form`, answered
    from its `done` row.
    """

    def __init__(self) -> None:
        """Starts with the cursor nowhere and nothing said."""
        super().__init__()
        #: Which page is open, in the order `/settings` lists them.
        self._tab = 0
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

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named:
                self._was = named

    def _lands(self, items: Sequence[str]) -> str:
        """Which row the cursor goes on as a page is put up again, by its id.

        The first thing a search found while one is narrowing the list; else something just
        added; else the row it was on, where that is still there; else the first thing listed,
        since what is on a list is what somebody turning to it came to read.

        Args:
          items: The things listed, by id, as a search has narrowed them.

        Returns:
          The id, or "" for a list with nothing in it.
        """
        sought = self._sought(items)
        if sought is not None and sought in items:
            self._was = sought
            return sought
        if self._aim in items:
            # Something just made or written, which is what somebody wants to see next.
            self._was, self._aim = self._aim, ""
            return self._was
        if self._was not in items:
            self._was = items[0] if items else ""
        return self._was

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

    def _holding(self) -> bool:
        """Whether anything is held that saving would land."""
        return self._changed

    def _searches(self) -> Action:
        """The button a page's list is searched from."""
        return Action(
            _ACT_SEARCH,
            "search…",
            "narrow the list by what is typed",
            self.action_search,
        )

    def _saves_all(self) -> Action:
        """The button the whole menu is saved from, last on a page that holds anything."""
        return Action(
            _ACT_SAVE,
            "save",
            "save all changes" if self._holding() else "nothing to save yet",
            self.applied,
            self._holding,
        )

    def _put(self, listing: OptionList, rows: list[Option], landing: str) -> None:
        """Puts the rows up with the cursor on one of them, by its id.

        On the first thing listed where what it was to land on is not there.

        Args:
          listing: The list.
          rows: The rows.
          landing: The id of the row the cursor goes on.
        """
        listing.set_options(rows)
        listing.highlighted = next(
            (at for at, one in enumerate(rows) if one.id == f"={landing}"),
            next((at for at, one in enumerate(rows) if not one.disabled), None),
        )


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


#: The three kinds of row a form is made of: one written into, one whose values are dropped
#: under it to be picked from, and one that opens a sheet of its own to be answered on.
_WRITES, _STEPS, _OPENS_ONTO = "writes", "steps", "opens"


class Question(NamedTuple):
    """One row of a form: what the answer is kept under, what it is called, what it asks.

    Attributes:
      held: What the answer is kept under, which is also the row's id.
      named: What the row is called on the screen.
      about: What is asked, said quietly beside it.
      kind: Written into, picked from a list dropped under it, or opened -- see
        :data:`_WRITES`.
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
    an enter to keep it and an arrow to the next. A stepped row drops every value it can
    take under it on enter or a click, one picked with enter or a click and none with esc --
    see :meth:`Sheet.pressed` -- and moves on as a written row does; an opened row opens a
    sheet of its own. Esc puts back a row being written, and on a form holding something asks
    whether to keep it, as every menu holding changes does.

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
        """What a stepped row is picked from, which each form with one says for itself.

        Args:
          held: The row.

        Returns:
          Its values, in order: `on` and `off` for a switch.
        """
        del held
        return ()

    def means(self, held: str, value: str) -> str:
        """What one value of a stepped row means, said beside it on the list it is picked from.

        Args:
          held: The row.
          value: The value.

        Returns:
          A few words, or "" for a value that says itself.
        """
        del held, value
        return ""

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
        self._values_at = len(_INDENT) + 2 + self._counting + 2 + named
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
                (Key(_CHORD, "new line"),)
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
        # a key to find out whether a row opens or drops is a reader the row did not tell.
        moves = {_STEPS: f" {_DROPS}", _OPENS_ONTO: f" {_OPENS}"}.get(one.kind, "")
        # Padded on what is shown rather than on what is written: markup is not columns.
        label = escape(one.named) + " " * max(1, named - len(one.named))
        room = wide - len(value) - (1 if caret else 0) - len(moves)
        # Wrapped here rather than by the list, so that a second line starts under the first
        # rather than under the edge: the column of what each row asks stays a column.
        starts = len(_INDENT) + 2 + len(number) + 1 + named + wide - room + max(1, room)
        # The list has no width of its own before it is first laid out; the screen's is it.
        across = (
            self.query_one("#choices", OptionList).scrollable_content_region.width
            or self.size.width
        )
        lines = textwrap.wrap(one.about, max(across - starts, 20)) or [""]
        about = f"\n{' ' * starts}".join(
            f"[$text-muted]{escape(line)}[/]" for line in lines
        )
        return (
            f"{mark}[$text-muted]{number}[/] {label}"
            f"[$secondary]{escape(value)}[/]{caret}[$text-muted]{moves}[/]"
            f"{' ' * max(1, room)}{about}"
        )

    def _kind(self, row: str) -> str:
        """Which kind of row one is, or "" for one that is not a question."""
        rows = self._now if self._now is not None else self.asked()
        return next((one.kind for one in rows if one.held == row), "")

    def editable(self, row: str) -> bool:
        """A written row is written where it stands; the others drop or open.

        Args:
          row: The row, by id.

        Returns:
          True for a question that is written.
        """
        return self._kind(row) == _WRITES

    def drops(self, row: str) -> bool:
        """A stepped row drops its values under it, where it has any.

        Args:
          row: The row, by id.

        Returns:
          True for a stepped row with something to pick from: one whose values are not
          known yet -- the ways into a CLI nothing knows -- has nothing to drop.
        """
        return self._kind(row) == _STEPS and bool(self.choices(row))

    def dropping(self, row: str) -> Drop:
        """Every value a stepped row can take, and the one it holds.

        A switch -- a row of `on` and `off` -- opens on the other of its two answers, so that
        enter twice turns it round as a switch is turned.

        Args:
          row: The row, by id.

        Returns:
          The list.
        """
        rows = self._now if self._now is not None else self.asked()
        question = next(one for one in rows if one.held == row)
        now = self.shown(question)
        values = list(self.choices(row))
        if switch(values):
            return switched(question.named, now)
        return Drop(
            question.named,
            [Value(one, one, self.means(row, one)) for one in values],
            now,
        )

    def dropped(self, row: str, picked: str) -> None:
        """Holds the value picked, and lets whatever follows from it follow.

        Args:
          row: The row, by id.
          picked: The value.
        """
        self._typed_in[row] = picked
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
            # An answer nobody typed is replaced by the first letter that is, and corrected by
            # a backspace: `gateway` backspaced is `gatewa`, not nothing, which is somebody
            # trimming a name rather than starting another.
            self._fresh.discard(row)
            if event.key != "backspace":
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
                "command to run the agent, e.g. my-agent --acp",
                needed=not self._typed_in.get("command", "").strip(),
            )
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "saves it as a backend"

    def _ask(self) -> None:
        """Says what one of these is."""
        self.query_one("#asked", Label).update("Add a CLI that speaks ACP")
        self.query_one("#about", Label).update(
            "Any coding agent that supports the Agent Client Protocol, "
            "communicating over stdin and stdout using the command you "
            "provide. The protocol does not configure models or effort, so it "
            "runs with its own configuration."
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
            self._wrong = "command is required"
            self._fill()
            return
        self.dismiss(said)


#: How many times over a turn may be tried again, and how long the retrying may be given.
#: Values to pick from rather than a number to type: a list says what is sensible, and a text
#: box for an integer is a text box to validate.
_TRIES = (0, 1, 2, 3, 5, 8, 13, 21)
_FOR = (0.0, 30.0, 60.0, 300.0, 900.0, 3600.0)

#: The rows a step is tried again by, on the sheet a step is written on.
_HOW_MANY = "tries"
_POLICY = "policy"
_HOW_LONG = "for"


def _lasting(seconds: float) -> str:
    """How long something may go on for, as a row of a sheet says it."""
    if not seconds:
        return "no limit"
    if seconds < 60:  # noqa: PLR2004 -- a minute, in the units the number is in
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.0f}m"


#: How wide the column of setting names is, and the column of their values, so that a sheet
#: of settings reads down three columns: what it is called, what it is, and what it is for.
#: Wide enough for the longest name any flow here has, since a column that a name overruns
#: is one the three of them stop lining up in.
_SETTING = 34
_VALUE = 13


class Budgeted(BaseModel):
    """What a run of a flow may spend, as the menu asks it.

    A model rather than four rows written by hand, so that the budget is asked with the same
    sheet a flow's own params are asked with: one place that knows how a number is typed
    and read back, and a description apiece saying what each limit means. What comes
    out of it is a :class:`hmz.flows.Budget`, which is where "at least one limit" is settled.

    Not a turn's budget, which is a flow's to give. This is the run's.
    """

    duration: str = Field(
        default="",
        description="maximum run duration: 1h30m, 90s, PT2H; empty for no limit",
    )
    cost: float = Field(
        default=0.0, ge=0, description="maximum cost in US dollars, 0 for no limit"
    )
    output_tokens: int = Field(
        default=0, ge=0, description="maximum output tokens, 0 for no limit"
    )
    graceful: bool = Field(
        default=True,
        description="finish the current turn when a limit is reached",
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
        """A budget, as the sheet shows it.

        Built rather than validated: this is what the sheet opens on, and the sheet is where
        a budget is checked, when it is set. A budget that was valid when it was written --
        one whose only limit is a cost of nothing, say -- is shown so that it can be changed,
        rather than refused before anybody sees it.
        """
        import math

        return cls.model_construct(
            duration=_units(budget.duration) if budget.duration is not None else "",
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
      A switch as `on` or `off` -- words pydantic takes back as a boolean, so what is shown is
      also what is validated -- anything else as it is written, and something unset as the
      empty string rather than as `None` -- a setting nobody has given a value is blank.
    """
    if isinstance(value, bool):
        return _YES if value else _NO
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
        #: The setting just begun on whose whole value is still selected, or "" for none:
        #: the first letter typed replaces it and backspace clears it, as a form's pre-filled
        #: answer is replaced. Without it `5` typed into a cost of `0.0` is `0.05`.
        self._whole = ""
        #: Which setting the cursor was last on, counting settings rather than rows: the
        #: headings between them are rows nothing can land on, so a row number is not one.
        #: One past the last for the row that sets them all.
        self._was = 0

    def _ask(self) -> None:
        """Says what is being set up."""
        self.query_one("#asked", Label).update(self._asked or f"Set up {self._flow}")
        self.query_one("#about", Label).update(
            self._about
            or (
                "Configure how this flow runs. Options and validation are defined "
                "by the flow itself."
            )
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the settings up, grouped, with the marker beside the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at(listing.highlighted)
        self._values_at = len(_INDENT) + 2 + self._counting + 2 + _SETTING
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
                self._apart(
                    self.DONE, "all of the above", here=at == len(self._fields)
                ),
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
        # A value still selected whole is drawn reversed, as a selection is, and the next
        # letter replaces it rather than landing after it; there is no caret beside it.
        whole = bool(value) and self._editing == name and self._whole == name
        shown = (
            f"[reverse]{escape(value)}[/reverse]"
            if whole
            else f"[$secondary]{escape(value)}[/]"
        )
        # A block where the next letter goes, drawn by reversing what is already there --
        # the one thing a list in the terminal's own colours can show without naming one.
        caret = "[reverse] [/reverse]" if self._editing == name and not whole else ""
        # And the mark that says which rows drop their values under them, which is the other
        # half of the same thing the caret is: a switch and a word look the same until you
        # try one.
        drops = f" {_DROPS}" if self._values(name) else ""
        # Padded on what is shown rather than on what is written: markup is not columns,
        # and the caret is one of them.
        named = escape(name) + " " * max(1, _SETTING - len(name))
        room = _VALUE - len(value) - (1 if caret else 0) - len(drops)
        return (
            f"{mark}[$text-muted]{number}[/] {named}"
            f"{shown}{caret}[$text-muted]{drops}[/]"
            f"{' ' * max(1, room)}[$text-muted]{escape(about)}[/]"
        )

    def _values(self, name: str) -> tuple[str, ...]:
        """What a setting is picked from, where it is one of a fixed few.

        Args:
          name: The field.

        Returns:
          Every value it takes, in the order the flow wrote them -- the two words of a
          switch, or the words of a literal -- and nothing at all for one that is written.
        """
        kind = dict(self._fields)[name].annotation
        # `Literal["a", "b"] | None` and `Literal["a", "b"]` are the same few words to pick
        # from, so the union is unwrapped before the literal is read off it.
        for said in (kind, *get_args(kind)):
            if get_origin(said) is Literal:
                return tuple(str(one) for one in get_args(said))
        if kind is bool:
            return (_YES, _NO)
        return ()

    def editable(self, row: str) -> bool:
        """Whether a setting is written where it stands, which one of a fixed few is not.

        Args:
          row: The row, by id.

        Returns:
          True for a setting that is written -- a word or a number -- and False for one
          picked from a list, and for the row that sets them all.
        """
        return row in dict(self._fields) and not self._values(row)

    def drops(self, row: str) -> bool:
        """Whether a setting's values are dropped under it: a switch's, and a literal's.

        Args:
          row: The row, by id.

        Returns:
          True for a setting that is one of a fixed few.
        """
        return row in dict(self._fields) and bool(self._values(row))

    def dropping(self, row: str) -> Drop:
        """Every value a setting can take, and the one it is set to.

        Args:
          row: The setting.

        Returns:
          The list: a switch's opening on the other of its two.
        """
        values = self._values(row)
        now = self._typed_in[row]
        if switch(values):
            return switched(row, now)
        return Drop(row, [Value(one, one) for one in values], now)

    def dropped(self, row: str, picked: str) -> None:
        """Sets a setting to the value picked for it.

        Args:
          row: The setting.
          picked: The value.
        """
        self._typed_in[row] = picked
        self._wrong = ""

    def held(self) -> object:
        """Every setting as it is written now."""
        return dict(self._typed_in)

    def put_back(self, was: object) -> None:
        """Puts every setting back as it was written before.

        Args:
          was: What :meth:`held` answered.
        """
        self._typed_in = dict(cast("dict[str, str]", was))

    def pressed(self) -> bool:
        """Takes enter as :meth:`Sheet.pressed` does, selecting a written value it begins on.

        Returns:
          Whether enter was taken, as there.
        """
        begun = not self._editing
        taken = super().pressed()
        self._whole = ""
        if begun and self._editing:
            self._whole = self._editing
            self._fill()
        return taken

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter as writing the setting being changed.

        Args:
          row: The setting.
          event: The key.

        Returns:
          Whether it was taken.
        """
        typed = event.key == "backspace" or (event.is_printable and event.character)
        if typed and self._whole == row:
            # A value selected whole is replaced by the first thing typed.
            self._whole = ""
            self._typed_in[row] = ""
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

    #: Whether the rows about the list go above it, as they do on everything a page of
    #: `/settings` opens, rather than below it -- in which case the cursor opens on the
    #: choice in force.
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
        shown = sorted(
            (row for row in self._rows if self.fits(row[1], row[2])),
            key=lambda row: self.ranks(row[1], row[2]),
        )
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

    def above(self) -> list[tuple[str, str, str]]:
        """The rows about the list, for one whose rows go above it: add, ask again, search.

        Returns:
          One `(id, what it is called, the line about it)` apiece, in order.
        """
        return [
            *(((_ADD, f"add {self.adds}", ""),) if self.adds else ()),
            *(((_AGAIN, self.again, ""),) if self.again else ()),
            *((_SEEK,) if self.SEARCHES else ()),
        ]

    def _fill_atop(
        self, listing: OptionList, shown: list[tuple[str, str, str]]
    ) -> None:
        """Puts the rows up under the rows about them, the cursor opening on the one in force.

        Args:
          listing: The list.
          shown: The choices, as a search has narrowed them.
        """
        atop = self.above()
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
        "Kimi Code is installed, but the websockets package is not",
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
        return Made(
            why=f"{signs.way} is not a supported sign-in method for {signs.cli}"
        )
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
_TYPED_ABOUT = "environment variables, as NAME=VALUE, one per line"
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
                    "account name",
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
                    f"{one.about}; leave blank to keep current value"
                    if keeps
                    else one.about,
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
                about += f"{_DOT}overwrites {other}/{name}"
            rows.append(Question(f"{_ALSO}{other}", f"also for {other}", about, _STEPS))
        return rows

    def shown(self, one: Question) -> str:
        """What a row holds, and on or off for whether it is written down elsewhere too."""
        if one.held.startswith(_ALSO):
            return _YES if self._also(one.held.removeprefix(_ALSO)) else _NO
        return super().shown(one)

    def choices(self, held: str) -> Sequence[str]:
        """The CLIs there are, the ways into the one chosen, and a switch apiece for the rest."""
        if held == _CLI:
            return self._clis
        if held == _BY:
            return [one.name for one in _hmz().accounts.ways(self._cli())]
        if held.startswith(_ALSO):
            return (_YES, _NO)
        return ()

    def stepped(self, held: str) -> None:
        """Lets go of what belonged to the CLI or the way in before it moved.

        Args:
          held: The row that moved: a switch for another backend moves nothing else.
        """
        if held.startswith(_ALSO):
            return
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
            said = f"updates {named} once /settings is saved"
        else:
            said = f"signs {named} in again"
        if way is not None and way.argv:
            said += ", running its login in the terminal"
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
            return (
                f"{escape(cli)} is not installed, and this sign-in method requires "
                "running its login"
            )
        return f"{escape(cli)} is not installed; install it to use this account"

    def _ask(self) -> None:
        """Says what is being made, corrected or signed in, and puts the questions up."""
        cli = escape(self._cli())
        named = f"{cli}/{escape(self._name)}"
        self.query_one("#asked", Label).update(
            (f"Add a {cli} account" if self._fixed else "Add an account")
            if self._making
            else f"Edit {named}"
            if self._copies
            else f"Sign {named} in again"
        )
        self.query_one("#about", Label).update(
            (
                "A saved sign-in for one CLI, kept separate from the CLI's default "
                "and other accounts. Secrets are masked and never shown."
            )
            if self._making
            else (
                "Edit account settings. Secrets are never displayed, so leave "
                "blank to keep current values."
            )
            if self._copies
            else "Required settings for this sign-in method."
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
            self._wrong = (
                f"{cli} has no sign-in method named {self._typed_in.get(_BY, '')}"
            )
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
                f"{cli} already has an account named {name}; edit it from its "
                "row, or choose a different name"
            )
            self._fill()
            return
        if still := accounts.asks(way, answers):
            self._wrong = f"{still[0]} is required"
            self._fill()
            return
        if not answers and not way.argv:
            self._wrong = "fill in credentials to sign in"
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
            (STOPS, "stop the flow and exit", ""),
            # The one line worth a word: that the run outlives this interface is the whole of
            # what makes letting go of it an answer rather than a way of abandoning it.
            (DETACHES, "detach and exit", "run `hmz` here to reattach")
            if self._held
            else (STAYS, "cancel", ""),
        ]

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here."""
        super()._fill()
        self._footed(Key("enter", "choose"), Key("esc", "stay"))


#: The two answers to the question humanize asks about itself on a first start.
_REPORTS, _QUIET = "on", "off"

#: The pages of `/settings`, in the order they are listed on its first screen: from the
#: broadest to the nearest. The fallbacks are beside the accounts, since what a turn falls
#: back to is another account or model; the machines a flow's environments go on follow; this
#: directory's own come last. Where flows come from is `/flow`'s (:mod:`hmz.tui.flows`). The
#: menu itself is :mod:`hmz.tui.settings`; the pages are counted here because each page that
#: is a list of things is a class of this module, and says which page it is when it says
#: something.
_EVERYWHERE, _ACCOUNTS, _FALLBACK, _MACHINES, _DIRECTORY = range(5)


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

    asked = "Report errors to humanize?"

    def __init__(self) -> None:
        """Initializes the question on its default answer, which is yes."""
        super().__init__()
        sent, kept = "; ".join(SENT), "; ".join(KEPT)
        # What goes and what does not, where the question is asked rather than somewhere to
        # go and read: this is the whole of what anybody has to decide on, so it stays.
        self.about = (
            f"Send error reports to help fix bugs. Sent: {sent}. Never sent: "
            f"{kept}. You can change this later in /settings."
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

#: Which of them have their values dropped under them rather than being opened. One is a
#: switch -- whether the turn runs as a fleet -- and it is a thing about the model rather than
#: about what the agent is allowed.
_DROPPED = (_EFFORT, _SWARM)


class Agent(Drafts[Runs]):
    """Everything one agent is, on one sheet, each row opened or picked from under it.

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
        model, effort = parted(rest)
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
            "Configure this agent: select its CLI, account, model, and "
            "reasoning effort."
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
            (_CLI, self._cli or "—", "coding agent CLI to use"),
            (_ACCOUNT, self._provider or _LOCAL, "account to run as"),
            (_MODEL, self._model or "—", "model to use"),
            (_EFFORT, self._effort or "—", "reasoning effort"),
        ]
        if self._swarms():
            rows.append((_SWARM, _YES if self._swarm else _NO, "run turns as a swarm"))
        return rows

    def _fill(self) -> None:
        """Puts the rows up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(max(len(rows), 1)))
        self._values_at = len(_INDENT) + 2 + self._counting + 2 + _ASPECT
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
        # own and one drops its values under it, and a reader who has to press a key to find
        # out which is a reader the row did not tell.
        moves = (
            f" {_DROPS}"
            if self.drops(held)
            else ""
            if held in _DROPPED
            else f" {_OPENS}"
        )
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

    def drops(self, row: str) -> bool:
        """Whether a row's values are dropped under it rather than opened.

        Args:
          row: The row, by id.

        Returns:
          True for how hard it thinks, once there is a model to say what it takes, and for
          whether a turn is run as a fleet.
        """
        return row == _SWARM or (row == _EFFORT and bool(self._efforts()))

    def dropping(self, row: str) -> Drop:
        """The efforts the model takes, hardest first, or the two sides of the switch.

        Args:
          row: The row, by id.

        Returns:
          The list.
        """
        if row == _SWARM:
            return switched(
                "swarm",
                _YES if self._swarm else _NO,
                ("run turns as a swarm", "run turns as one agent"),
            )
        return Drop(
            "effort", [Value(one, one) for one in self._efforts()], self._effort
        )

    def dropped(self, row: str, picked: str) -> None:
        """Holds the effort or the switch picked.

        Args:
          row: The row, by id.
          picked: The value.
        """
        if row == _EFFORT:
            self._effort = picked
        else:
            self._swarm = picked == _YES
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
        elif held == _EFFORT:
            # Not dropped, so there is no model yet to say which efforts it takes.
            self._said = "choose a model first; efforts belong to the model"
            self._fill()

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
            self._said = "choose a coding agent first; accounts belong to the CLI"
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
        self._said = f"checking models for {escape(cli)} as {escape(provider)}…"
        self._fill()
        runs, why = await asks(cli, provider)
        if (self._cli, self._provider) != (cli, provider):
            return  # chosen away from while it was asked, which is somebody else's answer
        self._catalogue, self._read_for = None, ("", "")
        self._said = (
            ""
            if runs
            else bad(
                f"could not get models for {escape(cli)} as {escape(provider)}"
                + (f": {escape(why)}" if why else "")
            )
        )
        self._fill()

    async def _chose_model(self, showing: App[None]) -> None:
        """Asks which of that CLI's models it runs, and starts it at the hardest effort."""
        if not self._cli:
            self._said = "choose a coding agent first; models belong to the CLI"
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

    asked = "Select a coding agent"
    about = (
        "The CLI for this agent. Accounts and models belong to the CLI, so "
        "choosing another resets them."
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
                    else _many(len(self._agents[backend]), "model")
                    if self._agents[backend]
                    else "no models reported yet",
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
        return "no coding agent installed here can run this agent"


class Accounts(Picks):
    """Which account one agent's turns run as, out of one CLI's own.

    The machine's own is always the first of them: an agent nobody has been asked about runs
    as whoever signed the CLI in, and that is a row rather than a blank. Making one is a row
    here, this being the moment somebody finds out they have none for this CLI.
    """

    asked = "Select the account to run as"
    about = (
        "Accounts belong to a specific CLI; each CLI has its own sign-ins. "
        "Sessions, settings, and skills belong to the CLI regardless of which "
        "account it runs as."
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
                (
                    "use credentials and the base URL saved by dsh, or environment "
                    "variables"
                )
                if self._backend == "dsh"
                else "use the account signed in on this machine",
            ),
            *((one.name, one.name, _sets(one)) for one in found),
        ]

    def nothing(self) -> str:
        """Says what came of making one, or where they come from for a CLI that has none."""
        if self._said:
            return self._said
        if self._backend == "dsh" and len(self._rows or []) < 2:  # noqa: PLR2004
            return (
                "DeepSeek Harness needs an API key; add an account to save "
                "one, or set DEEPSEEK_API_KEY and reopen hmz"
            )
        if len(self._rows or []) > 1:
            return ""
        return f"{escape(self._backend)} has no saved accounts yet"

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
                f"{escape(outcome.provider.name)} was saved, but sign-in "
                f"failed with exit code {outcome.status}"
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

    again = "check again"

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
        self.asked = f"Select a model for {backend}"
        self.about = (
            f"The model {backend} uses for this agent's turns, and its "
            "reasoning effort. These are the models last reported for this "
            "account."
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
            return f"checking {escape(self._backend)} for models…"
        if self._said:
            return self._said
        if self._models:
            return ""  # narrowed away by what was typed, which the search itself says
        whose = f" as {escape(self._provider)}" if self._provider else ""
        return (
            f"{escape(self._backend)} has not reported any models{whose} yet; "
            "select check again to query them"
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
        self._said = "" if found else f"no models found for {escape(self._backend)}"
        self._rows = None
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()


#: The place a chain is written against, and the places it falls back to, by the id each is put
#: up under on its form: the second is followed by where on the chain the row is, counting from
#: zero, so that a chain of three is three rows and one more to add a fourth on.
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
            "Here an agent is a CLI, an account and a model: what a turn can fail "
            "on. Search by any of the three."
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
                    "no fallback; fail the turn when retries are exhausted",
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
                            "models not reported yet; select to query them",
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
            return f"checking {escape(self._asking)} for models…"
        if self._said:
            return self._said
        return "" if self._rows else "no installed coding agent has a model to offer"

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the place, or asks an account that has not said what it runs.

        Args:
          event: What was chosen.
        """
        # All of it answered here: the list's own would answer an account asked with its row.
        event.prevent_default()
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
        self._said = bad(escape(why)) if why else "" if runs else "no models found"
        self._rows = None
        self._fill()


def _tried(tries: int) -> str:
    """How many times over a failed turn is tried again, as its row says it."""
    return str(tries) if tries else "none"


class Failing(Form["Step | str"]):
    """Everything about one chain, on one form: where it fails, where it goes, how it retries.

    One form rather than a walk. Adding a step used to be the three questions a place is,
    asked twice over on six sheets, and how it is tried again a menu of its own opened from
    another: here every place is a row apiece, each opening the one list of places, and the
    three that say how a failed turn is tried again are stepped where they stand beside them
    -- the tries first, since they are spent before the chain is walked.

    Where it falls back to is a list, in the order its places are tried, and is edited the way
    the rest of the form is -- by opening a row. The row after the last opens onto a place to
    add; a row already holding one opens onto the same list with `nowhere` at its head, which
    takes that place off the chain; and choosing a place that is already further along swaps
    the two, which is how a chain is put in another order without a key of its own to learn.
    The place that fails is never offered, and no place can be on the chain twice.

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
        #: Where it falls back to, in order, which is a list rather than one row's answer.
        self._chain: list[str] = list(held.to)
        self._typed_in = {
            _FAILS: held.spec,
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
                        "fails on",
                        "the agent whose turns cannot run",
                        _OPENS_ONTO,
                        needed=not self._typed_in[_FAILS],
                    ),
                )
                if self._unwritten
                else ()
            ),
            *(
                Question(
                    f"{_GOES}{at}",
                    "then" if at else "falls back to",
                    "if that fails too, in a new conversation"
                    if at
                    else "fallback agent for failed turns, in a new conversation",
                    _OPENS_ONTO,
                )
                for at in range(len(self._chain))
            ),
            Question(
                f"{_GOES}{len(self._chain)}",
                "then" if self._chain else "falls back to",
                "add an agent to try after the ones above"
                if self._chain
                else "fallback agent for failed turns, in a new conversation",
                _OPENS_ONTO,
                needed=self._unwritten and not self._chain,
            ),
            Question(
                _HOW_MANY,
                "tries",
                "how many times to retry a failed turn before falling back",
                _STEPS,
            ),
            Question(
                _POLICY,
                "policy",
                said.about if said is not None else "how long to wait between retries",
                _STEPS,
            ),
            Question(_HOW_LONG, "for", "maximum time to keep retrying", _STEPS),
        ]

    def shown(self, one: Question) -> str:
        """What a row holds, and what an empty place means."""
        if (at := self._slot(one.held)) is not None:
            if at < len(self._chain):
                return self._chain[at]
            return "+ add" if self._chain else "nowhere"
        value = self._typed_in.get(one.held, "")
        if one.held == _FAILS and not value:
            return "—"
        return value

    @staticmethod
    def _slot(held: str) -> int | None:
        """Where on the chain one row is, or None for a row that is not one of the chain's."""
        said = held.removeprefix(_GOES)
        return int(said) if said != held and said.isdigit() else None

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
        return [(_TAKES_AWAY, "remove", "removes this fallback rule when saved")]

    def besides(self, held: str) -> None:
        """Answers that it is to go.

        Args:
          held: The row, which is the one that takes it away.
        """
        if held == _TAKES_AWAY:
            self.dismiss(_TAKES_AWAY)

    def done_about(self) -> str:
        """What answering it does, which is hold it."""
        return "applies this fallback rule when /settings is saved"

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
        if not self._chain:
            self._chain = [one for one in was.to if one != place]
        for held, theirs, unset in (
            (_HOW_MANY, _tried(was.tries), _tried(fresh.tries)),
            (_POLICY, was.policy, fresh.policy),
            (_HOW_LONG, _lasting(was.timeout), _lasting(fresh.timeout)),
        ):
            if self._typed_in[held] == unset:
                self._typed_in[held] = theirs
        self._noted = (
            f"{escape(place)} already has a fallback rule; done will update it"
        )

    def opens(self, held: str) -> None:
        """Opens the list of places for the place that fails or for one on its chain.

        Args:
          held: Which of them.
        """
        self._chooses(held)

    @work
    async def _chooses(self, held: str) -> None:
        """Asks which place, and moves on to what is still to be answered.

        Args:
          held: The place that fails, or a row of its chain.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        fails = self._typed_in[_FAILS]
        at = self._slot(held)
        now = (
            self._typed_in[held]
            if at is None
            else self._chain[at]
            if at < len(self._chain)
            else ""
        )
        try:
            chosen = await showing.push_screen_wait(
                Places(
                    self._offered,
                    "Select the agent that fails"
                    if at is None
                    else f"Select the fallback agent for {fails or 'it'}",
                    now,
                    leaving=fails if at is not None else "",
                    nowhere=at is not None,
                )
            )
        finally:
            self.opened()
        if chosen is None:
            return
        if at is not None:
            if self._chains(at, chosen):
                self._wrong = ""
                self.changed()
            # Put up first, so that the cursor moved on to is counted among rows that are
            # there: a chain one longer is a form one row longer.
            self._fill()
            self.kept(f"{_GOES}{min(at, len(self._chain))}")
            self._fill()
            return
        if chosen != now:
            self._typed_in[held], self._wrong = chosen, ""
            # The place that fails cannot be on its own chain: chosen as the one that fails,
            # it comes off the chain rather than leaving a chain that points at itself.
            self._chain = [one for one in self._chain if one != chosen]
            self._takes_up(chosen)
            self.changed()
        self.kept(held)
        self._fill()

    def _chains(self, at: int, chosen: str) -> bool:
        """Puts one place at one position of the chain, which is three things by what it was.

        `nowhere` takes the place at that position off; a place already elsewhere on the
        chain changes places with the one there, which is how the chain is put in another
        order; and any other place takes that position, or is added at the end of the chain
        from the row after it.

        Args:
          at: The position, counting from zero; the length of the chain is the row after it.
          chosen: The place, or "" for nowhere.

        Returns:
          Whether the chain changed.
        """
        was = list(self._chain)
        if not chosen:
            del self._chain[at : at + 1]
        elif chosen in self._chain:
            there = self._chain.index(chosen)
            if at < len(self._chain):
                self._chain[at], self._chain[there] = chosen, self._chain[at]
        elif at < len(self._chain):
            self._chain[at] = chosen
        else:
            self._chain.append(chosen)
        return self._chain != was

    def _ask(self) -> None:
        """Says which place this is about, and what a step is."""
        self.query_one("#asked", Label).update(
            "Add fallback rule" if self._unwritten else escape(self._typed_in[_FAILS])
        )
        self.query_one("#about", Label).update(
            "What happens when an agent cannot take a turn: retry as "
            "configured, then fall back to another agent in a new conversation."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with the step, once it says something and does not point at itself."""
        from hmz.coganchor.fallbacks import Falls

        fails, goes = self._typed_in[_FAILS], tuple(self._chain)
        tries = next(
            (one for one in _TRIES if _tried(one) == self._typed_in[_HOW_MANY]), 0
        )
        if not fails:
            self._wrong = "select the agent that fails"
        elif fails in goes:
            self._wrong = "an agent cannot fall back to itself"
        elif len(set(goes)) != len(goes):
            self._wrong = "an agent can be on the chain only once"
        elif not goes and not tries:
            self._wrong = "choose a fallback agent or set retries"
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

    A row says where a turn goes as a chain, in the order its places are tried, and how many
    times over a failed turn is taken again before the chain is walked. Both are answers to
    the one thing that went wrong, so both are here. A chain is started only from the place it
    is written against: a place that is only some chain's fallback has none of its own, and one
    reached as a fallback carries on along the chain it was reached by.
    """

    #: What the page says it is.
    STEPS_ABOUT = (
        "Where a turn falls back when an agent fails, tried in order. An agent "
        "is a CLI, an account and a model. A chain starts only from the agent "
        "it is written for. Saved rules apply from the next failed turn."
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

    def _step_actions(self) -> list[Action]:
        """What is done about the steps: adding one, searching them, and saving."""
        return [
            Action(
                _ACT_ADD,
                "add fallback rule",
                "an agent that fails, and its fallback",
                lambda: self._writes_step(None),
            ),
            self._searches(),
            self._saves_all(),
        ]

    def _fill_steps(self) -> None:
        """Puts the steps up, each saying what fails and what happens next."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        rows = [row for row in self._step_rows() if self.fits(row[1], row[2])]
        landing = self._lands([row[0] for row in rows])
        self._put(
            listing,
            [
                Option(
                    self._row(seen, said, goes, here=named == landing, inforce=True),
                    id=f"={named}",
                )
                for seen, (named, said, goes) in enumerate(rows)
            ],
            landing,
        )
        self._drawn = listing.highlighted
        said = self._said or ("" if rows else "no fallback rules configured yet")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "edit"), Key("esc", "close"))

    def _drops_step(self, said: str) -> None:
        """Holds one place having nothing written about it, until the menu is saved.

        Held rather than done, as everything on this menu is: the row goes from the list at
        once so that what is read is what is held, and the cursor lands on the first of what
        is left rather than on a place that is no longer one of the rows.

        Args:
          said: The place, as it is written down.
        """
        self._steps = [one for one in self._steps if one.spec != said]
        self._said = iffy(f"{escape(said)} has no fallback when this menu is saved")
        self.changed()
        self._fill()

    def _took_step(self, named: str) -> None:
        """Opens the form a step is written on, for the step chosen.

        Args:
          named: The row chosen, by its id.
        """
        if named:
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
                told.append(f"[dim]{escape(gone)} has no fallback[/dim]")
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
    goes = f"falls back to {', then '.join(step.to)}" if step.to else "no fallback"
    if not step.tries:
        return goes
    over = f", up to {_lasting(step.timeout)}" if step.timeout else ""
    tries = "retry" if step.tries == 1 else "retries"
    return f"{step.tries} {tries}, {step.policy}{over}{_DOT}{goes}"


#: What can be done to one account, which is what enter opens rather than what a row of
#: letter keys does. Each of these is a question about the account under the cursor, and a
#: menu of four is a menu; four keys nobody can see are four keys nobody presses. Being rid
#: of one is the fourth and is spelled with the rest of them -- see :data:`_TAKES_AWAY`.
_CORRECTS, _SIGNS_IN = "corrects", "signs-in"


class Account(Picks):
    """What to do with one account: correct it, sign it in, be rid of it.

    Its own menu rather than a letter apiece on the list of accounts. They are three questions
    about the account under the cursor, and a sheet whose keys are `l` and `r` is a sheet
    whose keys have to be learned from a line at the bottom of it -- while enter, which every
    list already means, was doing one of the three.

    Taking it away is the last of them rather than a key on the list before this: the row
    that does it is read beside what the account is and what it is holding, which is what
    somebody deciding to be rid of it is deciding about.

    Where a failed turn goes and how many times over it is tried again are not among them.
    Those are things about the place a turn runs at rather than about the credentials it runs
    with, and the fallback page of `/settings` is where they are said.
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
        self.asked = f"{cli}/{name}" if name else f"{cli} as local"
        self.about = (
            "Editing and removal take effect when /settings is saved; signing in "
            "happens immediately."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The three, none of which there is anything to do about for this machine's own."""
        if not self._name:
            return []
        return [
            (
                _CORRECTS,
                "edit settings",
                "ask the setup questions again",
            ),
            (
                _SIGNS_IN,
                "sign in again",
                "run the CLI's sign-in again; takes over the terminal while running",
            ),
            (
                _TAKES_AWAY,
                "cancel removal" if self._gone else "remove",
                "will be removed when /settings is saved"
                if self._gone
                else "remove the account and its credentials when /settings is saved",
            ),
        ]

    def nothing(self) -> str:
        """Why none of them is here.

        Returns:
          The line, or "" for any account humanize made. Why the rows are not here is said
          rather than left to be noticed: a row somebody went looking for and did not find is
          a menu that has not answered them.
        """
        if self._name:
            return ""
        return (
            f"this is {escape(self._cli)} as local: humanize keeps no "
            "credentials for it, so you cannot edit, sign in, or remove it"
        )


class Providers(Pages):
    """The accounts page of `/settings`: every account to run an agent as, per CLI.

    Read rather than chosen from: which account an agent runs as is asked where that agent is
    set up, so nothing here is being picked for anything. What it is for is what can happen to
    one -- made, set up again, signed in again, taken away -- and all but the first of those
    are one menu, opened with enter on the account they are about.

    What is written down without running anything is held until the menu is saved: taking one
    away, correcting what one holds. What cannot be held is what
    runs a command of its own -- making an account and signing one in own the terminal while
    they run, and something that has already happened is not a draft. Either way an agent
    reads the account it was configured with once, so what changes here is what its next
    session runs as, and the row says so while it is held.

    Each row is the name, the way it was made by and the variables it sets. Their names and
    never a value: this is drawn where somebody can read it.
    """

    #: What the page says it is.
    ACCOUNTS_ABOUT = (
        "Each account is a named set of credentials, kept separate from the CLI's own "
        "and from each other. You assign an account to an agent when setting "
        "it up. Creating and signing in happen immediately; other changes take "
        "effect when this menu is saved, and apply from an agent's next "
        "session."
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
        #: What each corrected one is to hold, by `cli/name`.
        self._edits: dict[str, dict[str, str]] = {}
        #: The accounts saving corrected, whose models the interface asks for again.
        self._corrected: list[tuple[str, str]] = []
        #: Which other backends each corrected one is to be written down for as well, by
        #: `cli/name`: an account that several CLIs can be run as is corrected for all of
        #: them at once, which is the point of having copied it in the first place.
        self._alike: dict[str, tuple[str, ...]] = {}
        #: The ones whose CLI is being asked what it runs, which their rows say.
        self._asking: set[str] = set()

    def _read_accounts(self) -> None:
        """Reads every account off the disk, which is what the rows are drawn from.

        The account this machine is already signed into is one of them, under each CLI that
        has one of its own: it is what an agent nobody gave an account runs as, and a group of
        accounts is read beside it.

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
            and profile.name in whose
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
        said = _sets(one) if one.name else "the account signed in on this machine"
        if named in self._asking:
            said += f"{_DOT}checking models…"
        if named in self._edits:
            said += f"{_DOT}edited"
        if named in self._gone:
            said += f"{_DOT}will be removed"
        if named in self._edits or named in self._gone:
            said += f"{_DOT}{self.NEXT_SESSION}"
        return said

    def _account_actions(self) -> list[Action]:
        """What is done about the accounts: adding one, adding a CLI, searching, saving."""
        return [
            Action(
                _ACT_ADD,
                "add an account",
                "a sign-in for one CLI: API key, login, or gateway",
                self._adds_account,
            ),
            Action(_ACT_SPEAKS, "add a custom CLI", "supports ACP", self._speaks),
            self._searches(),
            self._saves_all(),
        ]

    def _fill_accounts(self) -> None:
        """Puts the accounts up under a heading per CLI."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._accounts if self.fits(one.name, one.cli, one.way)]
        landing = self._lands([self._named(one) for one in shown])
        rows: list[Option] = []
        group = ""
        for seen, one in enumerate(shown):
            named = self._named(one)
            if one.cli != group:
                # A heading, and a blank line above it once there is a group above it.
                # Neither can be landed on, so the arrows walk the accounts and step over.
                if group:
                    rows.append(Option("", disabled=True))
                group = one.cli
                rows.append(Option(f" [$primary]{escape(group)}[/]", disabled=True))
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
        self._put(listing, rows, landing)
        self._drawn = listing.highlighted
        said = self._said or ("" if self._accounts else "no accounts yet")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "open"), Key("esc", "close"))

    @staticmethod
    def _machines(cli: str, doing: str) -> str:
        """Why the account this machine is signed into is not one to do that to.

        Args:
          cli: The backend it is of.
          doing: What was asked for.

        Returns:
          The line to say under the list. humanize did not make that account and keeps no
          credentials for it -- it is the CLI as whoever is at this machine runs it -- so
          there is nothing here to do to it.
        """
        telemetry.snag("key-does-nothing", sheet="Providers", doing=doing)
        return (
            f"cannot {doing} {escape(cli)} as local: humanize keeps no credentials "
            "for it"
        )

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
            self._said = f"{escape(named)} will be removed when this menu is saved"
        self.changed()
        self._fill()

    def _took_account(self, named: str) -> None:
        """Opens what there is to do with the account chosen.

        Args:
          named: The row chosen, by its id.
        """
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
            self._said = self._machines(one.cli, "edit")
            self._fill()
            return
        way = _hmz().accounts.way(one.cli, one.way)
        if way is None:
            self._said = bad(
                f"{escape(one.way)} is not a sign-in method for {escape(one.cli)}"
            )
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
        self._said = f"{escape(named)} will be updated when this menu is saved"
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
            f"[dim]{escape(one.cli)}/{escape(one.name)} saved to "
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
                else f"hmz: sign-in failed with exit code {outcome.status}"
            )
        if outcome.copied:
            self._told.append(
                f"[dim]{escape(one.name)} also saved for "
                f"{escape(', '.join(outcome.copied))}[/dim]"
            )
        self._read_accounts()
        self._aim = self._named(one)
        if outcome.status:
            self._said = bad(
                escape(outcome.why)
                or (
                    f"sign-in for {escape(one.name)} failed with exit code "
                    f"{outcome.status}"
                )
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
            _ACCOUNTS,
            f"checking available models for {escape(one.cli)} as {escape(one.name)}…",
        )
        self._fill()
        runs, why = await asks(one.cli, one.name)
        self._asking.discard(named)
        said = self._landed(one, 0, runs=runs, why=why)
        if copied:
            said = (
                f"{escape(one.name)} is also saved for "
                f"{escape(', '.join(copied))}\n{said}"
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
            return f"sign-in for {escape(one.name)} failed with exit code {status}"
        if runs:
            return (
                f"{escape(one.cli)} supports {_many(runs, 'model')} as "
                f"{escape(one.name)}"
            )
        return bad(
            f"could not get models for {escape(one.cli)} as {escape(one.name)}"
            + (f": {escape(why)}" if why else "")
            + "; retry from the model row of an agent using this account"
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
                f"{escape(one.name)} uses {escape(one.way)}, which has no "
                "command to run; edit its settings instead"
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
        self._said = f"{escape(name)} added as a backend"
        self._told.append(
            f"[dim]{escape(name)} is saved as a backend: `{escape(command)}` "
            "starts it[/dim]"
        )
        self._fill()

    def _applies_accounts(self, told: list[str]) -> None:
        """Does everything the accounts page was holding, and says what became of each.

        Args:
          told: What the transcript is to say, which this adds to.
        """
        accounts = _hmz().accounts
        was = len(told)
        # Taken away first, and then everything that is left: an account corrected and taken
        # away in the same save is an account taken away.
        for taken in sorted(self._gone):
            cli, _, name = taken.partition("/")
            try:
                gone = accounts.remove(cli, name)
            except ValueError as why:  # a name nothing could ever have been kept under
                told.append(f"hmz: {escape(str(why))}")
                continue
            told.append(
                f"[dim]{escape(taken)} and its credentials were removed[/dim]"
                if gone
                else f"hmz: no account {escape(taken)}"
            )
        for one in self._accounts:
            named = self._named(one)
            if named in self._gone:
                continue  # gone above, so there is nothing to correct
            if (answers := self._edits.get(named)) is not None:
                try:
                    corrected = accounts.write(one.cli, one.name, one.way, answers)
                except (OSError, ValueError) as why:
                    told.append(f"hmz: {escape(str(why))}")
                    continue
                told.append(f"[dim]{escape(named)} is updated[/dim]")
                self._corrected.append((one.cli, one.name))
                for cli in self._alike.get(named, ()):
                    try:
                        accounts.copies(corrected, cli)
                    except (OSError, ValueError) as why:
                        told.append(f"hmz: {escape(str(why))}")
                        continue
                    told.append(
                        f"[dim]{escape(cli)}/{escape(one.name)} is updated "
                        "with it[/dim]"
                    )
        if len(told) > was:
            # When it is felt, said once rather than on every line: an agent reads the
            # account it was configured with once, so one running now carries on as it was.
            told.append(f"[dim]account changes take effect {self.NEXT_SESSION}[/dim]")


# -------------------------------------------------------------------------------- runtimes

#: The backends a runtime is saved for, as `-e` and the store name them. A swarm's is not
#: `_SWARM`, which is the row an agent's turns are run as a fleet on: the same word, for
#: another thing.
_SSH, _DOCKER, _DOCKER_SWARM = "ssh", "docker", "swarm"

#: What one runtime of each is called on the form that adds one.
_KINDS = {
    _SSH: "an ssh host",
    _DOCKER: "a docker host",
    _DOCKER_SWARM: "a docker swarm",
}

#: The kinds the one button that adds a runtime drops, in its order, each with what it is.
_ADDING = (
    Value(_SSH, "ssh host", "a machine reached over ssh"),
    Value(_DOCKER, "docker host", "a local or remote docker daemon"),
    Value(_DOCKER_SWARM, "docker swarm", "a docker swarm, through one of its managers"),
)

#: How many of a swarm's nodes a check names before it only counts the rest: a cluster's
#: hundred names are no line anybody reads.
_NAMED_NODES = 8

#: The ssh config an import reads unless it is told another, as the row says it.
_OWN_CONFIG = "~/.ssh/config"

#: What checking one runtime answers with, on its own menu.
_CHECKS = "checks"

#: What memory is written as on a form: a number and a unit, in docker's units of 1024.
_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:([KMGTP])(?:I?B)?|B)", re.IGNORECASE)
_UNITS = "KMGTP"


class _Had(Protocol):
    """What a runtime said it has when it was checked, as the runtime answers it."""

    @property
    def reached(self) -> bool: ...
    @property
    def said(self) -> str: ...
    @property
    def home(self) -> str: ...
    @property
    def cpus(self) -> float: ...
    @property
    def memory(self) -> int: ...
    @property
    def gpus(self) -> tuple[str, ...]: ...
    @property
    def usable(self) -> tuple[str, ...] | None: ...
    @property
    def gpu_memory(self) -> int: ...
    @property
    def runtimes(self) -> tuple[str, ...]: ...
    @property
    def version(self) -> str: ...
    @property
    def short(self) -> tuple[str, ...]: ...
    @property
    def nodes(self) -> tuple[str, ...]: ...


def _sized(amount: int, *, exact: bool = False) -> str:
    """Bytes as a row says them and a form takes them back: `64G`, `512M`.

    Whole: the largest unit of a megabyte or more that divides it, else what it comes to in
    whole G -- or M, under one -- rounded down. A daemon's memory is not a round number, and
    one written in rounded up would be more than it has.

    Args:
      amount: The bytes.
      exact: Whether it is to be read back as the very same amount -- a form correcting what
        was saved, which must not change what nobody touched -- in the largest unit that
        divides it, bytes and all.
    """
    for at in range(len(_UNITS), 0 if exact else 1, -1):
        if amount and not amount % 1024**at:
            return f"{amount // 1024**at}{_UNITS[at - 1]}"
    if exact:
        return f"{amount}B"
    for at in (3, 2, 1):
        if amount >= 1024**at:
            return f"{amount // 1024**at}{_UNITS[at - 1]}"
    return str(amount)


def _bytes(said: str) -> int:
    """An amount of memory as a form was given it, in bytes.

    Raises:
      ValueError: For one that is not a number and a unit: a bare number is bytes to docker
        and gigabytes to whoever typed it.
    """
    read = _SIZE.fullmatch(said.strip())
    if read is None:
        raise ValueError(
            f"memory: {said!r} must be a number and unit, such as 64G or 512M"
        )
    unit = read[2] or ""
    return int(float(read[1]) * 1024 ** (_UNITS.index(unit.upper()) + 1 if unit else 0))


def _number(said: str, what: str) -> float:
    """A number a form was given, or 0 for none.

    Raises:
      ValueError: For one that is not a number, `nan` and `inf` among them.
    """
    import math

    if not said:
        return 0.0
    try:
        value = float(said)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise ValueError(f"{what}: {said!r} is not a number")
    return value


#: Where one option ends and the next begins: a comma before a keyword, and not every comma --
#: a value may be a list of its own, as `Ciphers=aes128-ctr,aes256-ctr` is.
_OPTION = re.compile(r",\s*(?=[A-Za-z][A-Za-z0-9]*\s*[=\s])")


def _options(said: str) -> dict[str, str]:
    """What else `ssh` is told, as a form was given it: `KEYWORD=VALUE`, a comma apart.

    Raises:
      ValueError: For one that says no value.
    """
    held: dict[str, str] = {}
    for one in (part.strip() for part in _OPTION.split(said)):
        if not one:
            continue
        key, _, value = one.partition("=") if "=" in one else one.partition(" ")
        if not key.strip() or not value.strip():
            raise ValueError(f"options: {one!r} is not KEYWORD=VALUE")
        held[key.strip()] = value.strip()
    return held


def _unique(base: str, taken: frozenset[str]) -> str:
    """A name nothing is called yet: the base, or the base with `-2`, `-3` after it."""
    count = 1
    while (named := base if count == 1 else f"{base}-{count}") in taken:
        count += 1
    return named


def _called_after(host: str, fallback: str) -> str:
    """What a runtime reached at a host is called until somebody says: the host's first label.

    An address is called what it is, and anything a runtime's name cannot hold is a dash.
    """
    host = host.rpartition("@")[2].partition(":")[0].strip()
    if not re.fullmatch(r"[\d.]+", host):
        host = host.partition(".")[0]
    return re.sub(r"[^A-Za-z0-9._-]", "-", host).lstrip("._-") or fallback


def _config_named(config: str) -> str:
    """An ssh config as a row says it: the user's own as `~/.ssh/config`, another shortly."""
    if not config:
        return _OWN_CONFIG
    said = str(Path(config).expanduser())
    home = str(Path.home())
    if said.startswith(f"{home}/"):
        said = f"~{said[len(home) :]}"
    return said if len(said) <= _LABEL else f"…/{_shortly(said)}"


def _hands_out(cpus: float, memory: int, gpus: Sequence[str] = ()) -> str:
    """What a docker daemon may hand out, or a swarm's tasks reserve, as a row says it."""
    held = [
        *((f"{cpus:g} CPUs",) if cpus else ()),
        *((_sized(memory),) if memory else ()),
        *((f"GPUs {', '.join(gpus)}",) if gpus else ()),
    ]
    return ", ".join(held) or "no limits"


def _swarm_line(one: SwarmRuntime) -> list[str]:
    """What a row says about a swarm: its manager, where its tasks go, and what they may have.

    Not its nodes: how each is reached is a thing for when one is, and a swarm of a hundred
    is no row.
    """
    return [
        one.endpoint,
        *((one.image,) if one.image else ()),
        *((f"on {', '.join(one.constraints)}",) if one.constraints else ()),
        _hands_out(one.cpus, one.memory),
        *((f"GPUs as {one.gpu_resource}",) if one.gpu_resource else ()),
        *((f"max {one.max_tasks} tasks",) if one.max_tasks else ()),
    ]


def _machine_line(one: Runtime) -> str:
    """What a row says about one runtime: how it is reached, and what it has.

    A key by its path and never by what is in it, as everywhere here: `ssh` reads a key.
    """
    if one.backend == _SSH:
        host = cast("SSHRuntime", one)
        reach = host.login() + (f":{host.port}" if host.port else "")
        if host.alias:
            config = _config_named(host.config)
            reach = (
                f"from {config}"
                if reach == host.name and not host.host
                else f"{reach}, from {config}"
            )
        said = [
            reach,
            *((f"key {host.identity_file}",) if host.identity_file else ()),
            *((f"through {host.proxy_jump}",) if host.proxy_jump else ()),
            *((f"-o {', '.join(host.options)}",) if host.options else ()),
        ]
    elif one.backend == _DOCKER_SWARM:
        said = _swarm_line(cast("SwarmRuntime", one))
    else:
        daemon = cast("DockerRuntime", one)
        said = [
            daemon.endpoint,
            *((daemon.image,) if daemon.image else ()),
            *((f"OCI runtime {daemon.runtime}",) if daemon.runtime else ()),
            _hands_out(daemon.cpus, daemon.memory, daemon.gpus),
            *(
                (f"max {daemon.max_containers} containers",)
                if daemon.max_containers
                else ()
            ),
        ]
    if one.workdir:
        said.append(f"working directory: {one.workdir}")
    if one.fallback:
        said.append(f"falls back to {', '.join(one.fallback)}")
    return _DOT.join(said)


def _answered(one: Runtime, said: _Had) -> str:
    """What to say once a runtime has been asked what it has, as markup.

    What it has, and in yellow what it was saved as handing out and has not got: a resource
    the daemon does not have is a run refused later, so it is said now. A swarm says it is
    one, and which of its nodes may be given a task -- all told, for a swarm's.
    """
    named = f"{one.backend}/{one.name}"
    if not said.reached:
        return bad(escape(f"{named} could not be reached: {said.said}"))
    swarm = one.backend == _DOCKER_SWARM
    lead = (
        f": {'swarm' if swarm else 'docker'} {said.version}"
        if said.version
        else f": home {said.home}"
        if said.home
        else ""
    )
    has = f"{_nodes(said.nodes)}; {_has(said)} all told" if swarm else _has(said)
    line = escape(f"{named} answers{lead}; {has}")
    if failed := _failed(said):
        line += "\n" + iffy(escape(failed))
    if said.short:
        line += "\n" + iffy(
            escape(f"lacks configured resources: {'; '.join(said.short)}")
        )
    return line


def _nodes(names: Sequence[str]) -> str:
    """A swarm's nodes that may take a task, as a line says them: counted, the first named.

    Args:
      names: Their host names.
    """
    if not names:
        return "no node may take a task"
    count = f"{len(names)} node{'' if len(names) == 1 else 's'}"
    shown = ", ".join(names[:_NAMED_NODES])
    more = len(names) - _NAMED_NODES
    return f"{count}: {shown}" + (f" and {more} more" if more > 0 else "")


def _through(one: Runtime, host: str) -> bool:
    """Whether a runtime is reached through a saved ssh host, which taking that away strands.

    A docker daemon is where its endpoint is `ssh:<host>`; a swarm is as well, and where one
    of its nodes is reached through it.

    Args:
      one: The runtime.
      host: The ssh host, by the name it is saved under.
    """
    if one.backend == _DOCKER_SWARM:
        swarm = cast("SwarmRuntime", one)
        return swarm.endpoint == f"ssh:{host}" or host in swarm.nodes.values()
    return (
        one.backend == _DOCKER and cast("DockerRuntime", one).endpoint == f"ssh:{host}"
    )


async def _checked(one: Runtime) -> _Had | str:
    """Asks a runtime what it has, off the loop: what it said, or why asking went wrong.

    Returns:
      What it has, or -- where asking raised rather than answering, as a TLS directory under
      a `~somebody` nobody is does -- why, in words.
    """
    import asyncio

    envs = _hmz().runtimes
    try:
        return await asyncio.to_thread(envs.check, one)
    except (OSError, ValueError, RuntimeError) as why:
        return f"{one.backend}/{one.name} could not be checked: {why}"


def _failed(said: _Had) -> str:
    """How many of the GPUs a daemon lists answer, where one does not, or "".

    A GPU the driver is bound to but that has failed since the daemon's CDI specs were written
    is listed still, and no container is handed it: said beside what it lists, so that what
    it lists is not taken for what a run may have.
    """
    if said.usable is None or len(said.usable) >= len(said.gpus):
        return ""
    gone = [one for one in said.gpus if one not in said.usable]
    return (
        f"{len(said.usable)} of {len(said.gpus)} GPUs answer; GPU {', '.join(gone)} "
        + ("does not" if len(gone) == 1 else "do not")
    )


def _has(said: _Had) -> str:
    """What a runtime said it has, as one line: its CPUs, memory, GPUs and OCI runtimes."""
    has = [f"{said.cpus:g} CPUs", _sized(said.memory)]
    if said.gpus:
        gpus = f"GPUs {', '.join(said.gpus)}"
        has.append(
            f"{gpus}, {_sized(said.gpu_memory)} each" if said.gpu_memory else gpus
        )
    runs = f"; OCI runtimes {', '.join(said.runtimes)}" if said.runtimes else ""
    return f"{', '.join(has)}{runs}"


async def provided(host: App[None], backend: str) -> tuple[Runtime | None, str]:
    """Asks for a runtime on the one form that makes one, and saves it.

    Here rather than beside either place that asks: the runtimes page of `/settings`,
    and the list a role's machine is chosen from on `/flow` -- which is where somebody finds
    out the one they want is not saved yet.

    Args:
      host: The interface, which the form is pushed onto.
      backend: `ssh`, `docker` or `swarm`.

    Returns:
      The runtime, saved -- or None, and why not: "" for a form walked out of.
    """
    form: Form[Runtime] = (
        Hosting()
        if backend == _SSH
        else Swarming()
        if backend == _DOCKER_SWARM
        else Docking()
    )
    one = await host.push_screen_wait(form)
    if one is None:
        return None, ""
    try:
        return _hmz().runtimes.add(one), ""
    except (
        OSError,
        ValueError,
    ) as why:  # saved meanwhile, or a directory that will not do
        return None, str(why)


#: The rows of the form an ssh host is written on, by the field each answers.
_ALIAS, _HOST, _USER, _PORT, _KEY, _JUMP, _OPTIONS, _WORKDIR = (
    "alias",
    "host",
    "user",
    "port",
    "identity_file",
    "proxy_jump",
    "options",
    "workdir",
)

#: The row of either form a runtime's fallback list is written on.
_FALLEN_TO = "fallback"


def _fallback_row() -> Question:
    """The row a runtime's fallback list is written on, which both forms ask last."""
    return Question(
        _FALLEN_TO,
        "falls back to",
        "runtimes to try in order if this one cannot: docker:box, ssh:gpu2",
    )


def _fallback(said: str) -> list[str]:
    """A fallback list as its row has it written: entries apart by commas, in order."""
    return [one.strip() for one in said.split(",") if one.strip()]


#: The row of either form a harness's runtimes are written on, and what it says.
_AFFINITY = "affinity"
_AFFINITY_ABOUT = (
    "where an agent's harness runs, in order, the next only when one has no room: "
    "self, local, ssh:<name>, docker:<name>, swarm:<name>; blank for self where the "
    "CLI is there, else local"
)


def _affinity(typed: str) -> list[str]:
    """A runtime's affinity, as its row has it written: entries apart by commas."""
    return [one.strip() for one in typed.split(",") if one.strip()]


class Hosting(Form["Runtime"]):
    """An ssh host, on one form: what reaches it, what it is called, where it works.

    The host first, it being the one thing there is to type: the name is written in after it
    -- its first label, unless a host is already saved as that -- and follows it until
    somebody types over it. The rest is what `ssh` is told on top of the user's own config,
    each blank for what that config says, so a host the config already knows is one row.

    Correcting one asks the same less the name it is saved under; one imported from an ssh
    config is asked its `Host` as well, which is what `ssh` resolves it through.
    """

    def __init__(self, one: SSHRuntime | None = None) -> None:
        """Initializes the form on a host, or on nothing for one being added.

        Args:
          one: The host being corrected, or None to add one.
        """
        super().__init__()
        self._one = one
        #: What ssh hosts are saved as, read once: the name is written in per keystroke.
        self._taken = frozenset(each.name for each in _hmz().runtimes.all(_SSH))
        if one is None:
            self._typed_in = {_HOST: ""}
            self._names()
            return
        self._typed_in = {
            _ALIAS: one.alias,
            _HOST: one.host,
            _USER: one.user,
            _PORT: str(one.port) if one.port else "",
            _KEY: one.identity_file,
            _JUMP: one.proxy_jump,
            _OPTIONS: ", ".join(f"{key}={value}" for key, value in one.options.items()),
            _WORKDIR: one.workdir,
            _FALLEN_TO: ", ".join(one.fallback),
            _AFFINITY: ", ".join(one.affinity),
        }

    def _names(self) -> None:
        """Calls it after its host, until somebody has typed a name of their own."""
        if self._one is not None:
            return
        if self._typed_in.get(_CALLED) and _CALLED not in self._fresh:
            return
        self._typed_in[_CALLED] = _unique(
            _called_after(self._typed_in.get(_HOST, ""), _SSH), self._taken
        )
        self._fresh.add(_CALLED)

    def asked(self) -> list[Question]:
        """The host, its name, and what ssh is told on top of your own config."""
        typed = self._typed_in
        one = self._one
        aliased = one is not None and bool(one.alias)
        rows: list[Question] = []
        if one is not None and aliased:
            rows.append(
                Question(
                    _ALIAS,
                    "alias",
                    f"the Host entry in {_config_named(one.config)}",
                    needed=not typed.get(_ALIAS, "").strip()
                    and not typed.get(_HOST, "").strip(),
                )
            )
        rows.append(
            Question(
                _HOST,
                "host",
                "override host; leave blank to use the config"
                if aliased
                else "hostname, IP address, or user@host:port",
                needed=not aliased and not typed.get(_HOST, "").strip(),
            )
        )
        if one is None:
            rows.append(
                Question(
                    _CALLED,
                    "name",
                    "name used in -e and /flow",
                    needed=not typed.get(_CALLED, "").strip(),
                )
            )
        rows.extend(
            [
                Question(_USER, "user", "username; leave blank to use your ssh config"),
                Question(_PORT, "port", "leave blank to use your ssh config, or 22"),
                Question(_KEY, "identity file", "path to private key"),
                Question(_JUMP, "proxy jump", "jump host to connect through, if any"),
                Question(
                    _OPTIONS, "options", "additional ssh options: KEYWORD=VALUE, …"
                ),
                Question(
                    _WORKDIR,
                    "workdir",
                    "default working directory when -e specifies none: /abs or ~/path",
                ),
                _fallback_row(),
                Question(_AFFINITY, "harness runs on", _AFFINITY_ABOUT),
            ]
        )
        return rows

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter, and calls it after the host being typed, where it is.

        Args:
          row: The question, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        taken = super().writes(row, event)
        if taken and row == _HOST:
            self._names()
        return taken

    def edited(self) -> None:
        """Takes a host written as ssh takes one -- `user@host:port` -- apart into its rows.

        Into the rows for the login and the port where nothing is written in them yet: one
        somebody typed is theirs. And the name follows what is left.
        """
        super().edited()
        typed = self._typed_in
        host = typed.get(_HOST, "").strip()
        user, at, rest = host.rpartition("@")
        if at and user and not typed.get(_USER, "").strip():
            typed[_USER], host = user, rest
        named, colon, port = host.rpartition(":")
        if colon and named and port.isdigit() and not typed.get(_PORT, "").strip():
            typed[_PORT], host = port, named
        typed[_HOST] = host
        self._names()

    def done_about(self) -> str:
        """What answering it does: saves it, and asks it what it has."""
        name = self._one.name if self._one else self._typed_in.get(_CALLED, "").strip()
        doing = "updates" if self._one else "adds"
        return f"{doing} ssh/{name}, and checks its resources"

    def _ask(self) -> None:
        """Says what is being added or corrected, and puts the questions up."""
        self.query_one("#asked", Label).update(
            escape(f"Edit ssh/{self._one.name}") if self._one else "Add an ssh host"
        )
        self.query_one("#about", Label).update(
            "A machine where flow environments run. Connects using your ssh "
            "config plus settings configured here. Keys are specified by path "
            "and never read."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fields(self, typed: Mapping[str, str]) -> dict[str, Any]:
        """Everything the form says of the host besides its name, as the store takes it.

        Raises:
          ValueError: For a port that is not one, or an option with no value.
        """
        port = typed.get(_PORT, "")
        if port and not port.isdigit():
            raise ValueError(f"port: {port!r} must be a number")
        fields: dict[str, Any] = {
            "host": typed.get(_HOST, ""),
            "user": typed.get(_USER, ""),
            "port": int(port or 0),
            "identity_file": typed.get(_KEY, ""),
            "proxy_jump": typed.get(_JUMP, ""),
            "options": _options(typed.get(_OPTIONS, "")),
            "workdir": typed.get(_WORKDIR, ""),
            "fallback": _fallback(typed.get(_FALLEN_TO, "")),
            "affinity": _affinity(typed.get(_AFFINITY, "")),
        }
        if self._one is not None:
            fields |= {
                "alias": typed.get(_ALIAS, ""),
                "config": self._one.config,
                "made": self._one.made,
            }
        return fields

    def action_done(self) -> None:
        """Answers with the host, once `ssh` could be told everything it says."""
        envs = _hmz().runtimes
        typed = {key: value.strip() for key, value in self._typed_in.items()}
        name = self._one.name if self._one is not None else typed.get(_CALLED, "")
        if self._one is None and envs.find(_SSH, name) is not None:
            self._wrong = (
                f"an ssh host named {name} already exists; edit it from its "
                "row, or choose a different name"
            )
            self._fill()
            return
        try:
            made = envs.new(_SSH, name, **self._fields(typed))
        except ValueError as why:
            self._wrong = str(why)
            self._fill()
            return
        self.dismiss(made)


#: The rows of the forms a docker daemon and a docker swarm are written on, by the field or
#: the part of its endpoint each answers.
_ENDPOINT, _SOCKET, _ADDRESS, _TLS, _VIA, _CONTEXT = (
    "endpoint",
    "socket",
    "address",
    "tls_dir",
    "via",
    "context",
)
_IMAGE, _RUNTIME, _ARGS, _CPUS, _MEMORY, _GPUS, _AT_ONCE = (
    "image",
    "runtime",
    "run_args",
    "cpus",
    "memory",
    "gpus",
    "max_containers",
)
_CONSTRAINTS, _TASKS, _RESOURCE, _NODES = (
    "constraints",
    "max_tasks",
    "gpu_resource",
    "nodes",
)

#: The ways a docker daemon is reached, as its form steps through them, and what each is.
_ENDPOINTS = {
    "local": "the default docker daemon on this machine",
    "socket": "a daemon's unix socket on this machine",
    "tcp": "a daemon listening at an address",
    "saved ssh host": "the daemon on a saved ssh host",
    "ssh address": "the daemon on any host via ssh",
    "context": "an existing docker context",
}

#: What each of them but `local` is spelled with, and the row the rest of it is written on.
_REACHED = {
    "ssh address": ("ssh://", _ADDRESS),
    "socket": ("unix://", _SOCKET),
    "tcp": ("tcp://", _ADDRESS),
    "saved ssh host": ("ssh:", _VIA),
    "context": ("context:", _CONTEXT),
}


class _Daemon[T: (DockerRuntime, SwarmRuntime)](Form["Runtime"]):
    """What is reached through a docker daemon, on one form: where, what it is, what it holds.

    The part a docker host and a docker swarm have in common, which is most of either: where
    the daemon is is a row stepped through the ways one is reached, and the rows under it are
    the one that way asks -- a socket, an address, a saved ssh host, a context. Then the name,
    the image, what else docker is told, where it works, and how much of the CPUs and memory
    it may have, each blank for all of it; `detect` asks the daemon and writes what it has in,
    for somebody to type less over. What else each asks is its own form's to say.

    Correcting one asks the same, less the name it is saved under.
    """

    #: The backend it is saved for.
    BACKEND: ClassVar[str] = _DOCKER
    #: What one is called on the form, after `a`.
    KIND: ClassVar[str] = "docker host"
    #: What the form says it is, under its title.
    ABOUT: ClassVar[str] = ""
    #: What answering it does besides saving it.
    CHECKS: ClassVar[str] = "detects host resources"
    #: The rows detecting writes into, in the order it walks through them.
    DETECTED: ClassVar[tuple[str, ...]] = (_CPUS, _MEMORY)

    def __init__(self, one: T | None = None) -> None:
        """Initializes the form on one, or on nothing for one being added.

        Args:
          one: The one being corrected, or None to add one.
        """
        super().__init__()
        self._one = one
        self._taken = frozenset(each.name for each in _hmz().runtimes.all(self.BACKEND))
        #: What to say under the form, as markup: what detecting found, or that it is asking.
        self._noted = ""
        self._detecting = False
        #: The ssh hosts the `on` row has named, read once apiece: it is redrawn per key.
        self._vias: dict[str, Runtime | None] = {}
        if one is None:
            self._typed_in = {_ENDPOINT: "local"}
            self._names()
            return
        self._typed_in = {
            _ENDPOINT: "local",
            _TLS: one.tls_dir,
            _IMAGE: one.image,
            _ARGS: shlex.join(one.run_args),
            _CPUS: f"{one.cpus:g}" if one.cpus else "",
            _MEMORY: _sized(one.memory, exact=True) if one.memory else "",
            _WORKDIR: one.workdir,
            _FALLEN_TO: ", ".join(one.fallback),
            _AFFINITY: ", ".join(one.affinity),
            **self._held(one),
        }
        for kind, (spelled, row) in _REACHED.items():
            if one.endpoint.startswith(spelled):
                self._typed_in |= {_ENDPOINT: kind, row: one.endpoint[len(spelled) :]}
                break

    def _held(self, one: T) -> dict[str, str]:
        """What the rows only this form asks hold, for one being corrected.

        Args:
          one: The one.
        """
        raise NotImplementedError

    def _holds(self) -> list[Question]:
        """The rows under the name, what it may hand out last."""
        raise NotImplementedError

    def _more(self, typed: Mapping[str, str]) -> dict[str, Any]:
        """What the rows only this form asks come to, as the store takes it.

        Args:
          typed: The rows, stripped.

        Raises:
          ValueError: For one that does not read.
        """
        raise NotImplementedError

    def _names(self) -> None:
        """Calls it after where it is, until somebody has typed a name of their own."""
        typed = self._typed_in
        if self._one is not None or (typed.get(_CALLED) and _CALLED not in self._fresh):
            return
        kind = typed.get(_ENDPOINT, "local")
        base = (
            kind
            if kind == "local"
            else _called_after(typed.get(_ADDRESS, ""), self.BACKEND)
            if kind in ("tcp", "ssh address")
            else typed.get(_VIA, "") or self.BACKEND
            if kind == "saved ssh host"
            else typed.get(_CONTEXT, "").strip() or self.BACKEND
            if kind == "context"
            else self.BACKEND
        )
        typed[_CALLED] = _unique(base, self._taken)
        self._fresh.add(_CALLED)

    def _via_host(self) -> Runtime | None:
        """The saved ssh host the `on` row names, or None where it names none."""
        via = self._typed_in.get(_VIA, "")
        if via not in self._vias:
            self._vias[via] = _hmz().runtimes.find(_SSH, via) if via else None
        return self._vias[via]

    def _endpoint(self) -> str:
        """Where the daemon is, spelled as a runtime spells it."""
        kind = self._typed_in.get(_ENDPOINT, "local")
        if kind not in _REACHED:
            return "local"
        spelled, row = _REACHED[kind]
        return spelled + self._typed_in.get(row, "").strip()

    def asked(self) -> list[Question]:
        """Where it is, its name, and what it may hand out."""
        typed = self._typed_in
        kind = typed.get(_ENDPOINT, "local")
        rows = [Question(_ENDPOINT, "endpoint", _ENDPOINTS.get(kind, ""), _STEPS)]
        if kind == "socket":
            rows.append(
                Question(
                    _SOCKET,
                    "socket",
                    "socket path: /run/docker.sock",
                    needed=not typed.get(_SOCKET, "").strip(),
                )
            )
        elif kind in ("tcp", "ssh address"):
            rows.append(
                Question(
                    _ADDRESS,
                    "address",
                    "host:port to connect to"
                    if kind == "tcp"
                    else "[user@]host[:port]",
                    needed=not typed.get(_ADDRESS, "").strip(),
                )
            )
            if kind == "tcp":
                rows.append(
                    Question(
                        _TLS,
                        "tls",
                        "directory containing ca.pem, cert.pem and key.pem; "
                        "blank for none",
                    )
                )
        elif kind == "saved ssh host":
            via = self._via_host()
            rows.append(
                Question(
                    _VIA,
                    "on",
                    _machine_line(via)
                    if via is not None
                    else "saved ssh host running the docker daemon",
                    _OPENS_ONTO,
                    needed=via is None,
                )
            )
        elif kind == "context":
            rows.append(
                Question(
                    _CONTEXT,
                    "context",
                    "docker context name",
                    needed=not typed.get(_CONTEXT, "").strip(),
                )
            )
        if self._one is None:
            rows.append(
                Question(
                    _CALLED,
                    "name",
                    "name used in -e and /flow",
                    needed=not typed.get(_CALLED, "").strip(),
                )
            )
        rows.append(Question(_AFFINITY, "harness runs on", _AFFINITY_ABOUT))
        # What it may hand out last, over the row that asks the daemon what it has: what is
        # written in there is walked through and typed over, and then the form is done.
        rows.extend(self._holds())
        return rows

    def choices(self, held: str) -> Sequence[str]:
        """The ways a daemon is reached."""
        return list(_ENDPOINTS) if held == _ENDPOINT else ()

    def stepped(self, held: str) -> None:
        """Calls it after where it now is, where nobody has named it.

        Args:
          held: The row that moved.
        """
        del held
        self._names()

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter, and calls it after where it is as that is typed.

        Args:
          row: The question, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        taken = super().writes(row, event)
        if taken and row in (_ADDRESS, _CONTEXT):
            self._names()
        return taken

    def edited(self) -> None:
        """Takes a row kept, pasted into or walked off, which the name may follow."""
        super().edited()
        self._names()

    def opens(self, held: str) -> None:
        """Opens the ssh hosts saved here, for the one its daemon is on.

        Args:
          held: The row, which is that one.
        """
        if held == _VIA:
            self._via()

    @work
    async def _via(self) -> None:
        """Asks which saved ssh host the daemon is on, and moves on."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            chosen = await showing.push_screen_wait(
                Hosts(_SSH, self._typed_in.get(_VIA, ""))
            )
        finally:
            self.opened()
        if chosen is None:
            return
        if chosen != self._typed_in.get(_VIA):
            self._typed_in[_VIA], self._wrong = chosen, ""
            self._vias.clear()  # one may have been added on the way
            self._names()
            self.changed()
        self.kept(_VIA)
        self._fill()

    def beside(self) -> list[tuple[str, str, str]]:
        """Asking the daemon what it has, above the row that answers the form."""
        return [(_DETECTS, "detect", "detect host resources and fill them in")]

    def besides(self, held: str) -> None:
        """Asks the daemon what it has.

        Args:
          held: The row, which is the one that detects.
        """
        if held == _DETECTS:
            self._detects()

    def _detected(self, said: _Had) -> dict[str, str]:
        """What detecting writes into each row it fills, by the row: "" for nothing.

        Args:
          said: What the daemon has.
        """
        return {
            _CPUS: f"{said.cpus:g}" if said.cpus else "",
            _MEMORY: _sized(said.memory) if said.memory else "",
        }

    @work
    async def _detects(self) -> None:
        """Asks the daemon what it has, off the loop, and writes it in to be typed over.

        Written in as what the form guessed, so the first letter typed into one replaces it:
        what somebody wants is usually less than all of it, and now they can see how much all
        of it is.
        """
        if self._detecting:
            return
        envs = _hmz().runtimes
        try:
            probe = envs.new(
                self.BACKEND,
                self.BACKEND,
                endpoint=self._endpoint(),
                tls_dir=self._typed_in.get(_TLS, "").strip()
                if self._typed_in.get(_ENDPOINT) == "tcp"
                else "",
            )
        except ValueError as why:
            self._wrong = str(why)
            self._fill()
            return
        self._detecting, self._wrong = True, ""
        self._noted = f"detecting resources on {escape(self._endpoint())}…"
        self._fill()
        said = await _checked(probe)
        self._detecting, self._noted = False, ""
        if isinstance(said, str) or not said.reached:
            self._wrong = (
                said
                if isinstance(said, str)
                else f"the daemon did not respond: {said.said}"
            )
            self._fill()
            return
        for held, value in self._detected(said).items():
            if value:
                self._typed_in[held] = value
                self._fresh.add(held)
        failed = _failed(said)
        self._noted = escape(f"detected {_has(said)}: auto-filled") + (
            f"\n{iffy(escape(failed))}" if failed else ""
        )
        self.changed()
        self._fill()
        # On the first of them, for the typing over.
        rows = [one.held for one in self._now or []]
        if _CPUS in rows:
            self.query_one("#choices", OptionList).highlighted = rows.index(_CPUS)
            self._fill()

    def kept(self, row: str) -> None:
        """Moves on to the next of what detecting wrote in, while there is one to type over.

        Args:
          row: The row, by id.
        """
        rows = [one.held for one in self.asked()]
        detected = self.DETECTED
        if row in detected and row in rows:
            onward = [
                at
                for at, held in enumerate(rows)
                if at > rows.index(row) and held in detected and held in self._fresh
            ]
            if onward:
                self.query_one("#choices", OptionList).highlighted = onward[0]
                return
        super().kept(row)

    def note(self) -> str:
        """What detecting found, or that it is asking."""
        return self._noted

    def done_about(self) -> str:
        """What answering it does: saves it, and asks the daemon what it has."""
        name = self._one.name if self._one else self._typed_in.get(_CALLED, "").strip()
        doing = "updates" if self._one else "adds"
        return f"{doing} {self.BACKEND}/{name} and {self.CHECKS}"

    def _ask(self) -> None:
        """Says what is being added or corrected, and puts the questions up."""
        self.query_one("#asked", Label).update(
            escape(f"Edit {self.BACKEND}/{self._one.name}")
            if self._one
            else f"Add a {self.KIND}"
        )
        self.query_one("#about", Label).update(self.ABOUT)
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fields(self, typed: Mapping[str, str]) -> dict[str, Any]:
        """Everything the form says of it besides its name, as the store takes it.

        Raises:
          ValueError: For an amount that is not one, or run args that do not split.
        """
        tls = typed.get(_TLS, "")
        try:
            Path(tls).expanduser()
        except (
            RuntimeError
        ):  # `~somebody` nobody is, which would crash whatever reads it
            raise ValueError(
                f"tls: home directory does not exist for {tls!r}"
            ) from None
        try:
            argv = shlex.split(typed.get(_ARGS, ""))
        except ValueError as why:
            raise ValueError(f"run args: {why}") from None
        return {
            "endpoint": self._endpoint(),
            "tls_dir": tls if typed.get(_ENDPOINT) == "tcp" else "",
            "image": typed.get(_IMAGE, ""),
            "run_args": argv,
            "cpus": _number(typed.get(_CPUS, ""), "cpus"),
            "memory": _bytes(typed[_MEMORY]) if typed.get(_MEMORY) else 0,
            "workdir": typed.get(_WORKDIR, ""),
            "fallback": _fallback(typed.get(_FALLEN_TO, "")),
            "affinity": _affinity(typed.get(_AFFINITY, "")),
            **self._more(typed),
        }

    def action_done(self) -> None:
        """Answers with it, once everything said of it reads."""
        envs = _hmz().runtimes
        typed = {key: value.strip() for key, value in self._typed_in.items()}
        name = self._one.name if self._one is not None else typed.get(_CALLED, "")
        if self._one is None and envs.find(self.BACKEND, name) is not None:
            self._wrong = (
                f"a {self.KIND} named {name} already exists; edit it from its "
                "row, or choose a different name"
            )
            self._fill()
            return
        try:
            made = envs.new(self.BACKEND, name, **self._fields(typed))
        except ValueError as why:
            self._wrong = str(why)
            self._fill()
            return
        self.dismiss(made)


def _how_many(said: str, what: str) -> int:
    """A count a form was given, or 0 for none.

    Raises:
      ValueError: For one that is not a whole number.
    """
    if said and not said.isdigit():
        raise ValueError(f"{what}: {said!r} must be a number")
    return int(said or 0)


class Docking(_Daemon["DockerRuntime"]):
    """A docker daemon, on one form: where it is, what it is called, what it may hand out.

    Where it is is a row stepped through the ways a daemon is reached, and the rows under it
    are the one that way asks: a socket, an address, a saved ssh host, a context. What it may
    hand out -- CPUs, memory, GPUs -- is each blank for all it has, and `detect` asks the
    daemon and writes what it has in, for somebody to type less over.

    Correcting one asks the same, less the name it is saved under.
    """

    BACKEND: ClassVar[str] = _DOCKER
    KIND: ClassVar[str] = "docker host"
    ABOUT: ClassVar[str] = (
        "A docker daemon where flow environments run in containers: on "
        "this machine, over ssh, or at an address. Flows running on it are "
        "limited to the resources configured here."
    )
    DETECTED: ClassVar[tuple[str, ...]] = (_CPUS, _MEMORY, _GPUS)

    def _held(self, one: DockerRuntime) -> dict[str, str]:
        """Its OCI runtime, its GPUs and how many containers it may run.

        Args:
          one: The daemon.
        """
        return {
            _RUNTIME: one.runtime,
            _GPUS: ", ".join(one.gpus),
            _AT_ONCE: str(one.max_containers) if one.max_containers else "",
        }

    def _holds(self) -> list[Question]:
        """The image, how a container is run, where it works, and what it may hand out."""
        return [
            Question(
                _IMAGE,
                "image",
                "default image, unless specified by the flow",
            ),
            Question(_RUNTIME, "OCI runtime", "e.g. nvidia; blank for daemon default"),
            Question(_ARGS, "run args", "extra arguments for docker run"),
            Question(
                _AT_ONCE,
                "max containers",
                "max concurrent containers; blank for no limit",
            ),
            Question(
                _WORKDIR,
                "workdir",
                "default working directory when -e specifies no directory",
            ),
            _fallback_row(),
            Question(_CPUS, "cpus", "max CPUs; blank to use all host CPUs"),
            Question(_MEMORY, "memory", "e.g. 64G; blank to use all host memory"),
            Question(_GPUS, "gpus", "GPU IDs, e.g. 0, 1; blank to use all host GPUs"),
        ]

    def _detected(self, said: _Had) -> dict[str, str]:
        """Its CPUs and memory, and the GPUs that answer.

        Args:
          said: What the daemon has.
        """
        # Those that answer, where it could say: a GPU listed but failed is one no container
        # is handed, and one saved to be handed out is one a check says lacks.
        return super()._detected(said) | {
            _GPUS: ", ".join(said.gpus if said.usable is None else said.usable)
        }

    def _more(self, typed: Mapping[str, str]) -> dict[str, Any]:
        """Its OCI runtime, its GPUs and how many containers it may run.

        Raises:
          ValueError: For a count that is not one.
        """
        return {
            "runtime": typed.get(_RUNTIME, ""),
            "gpus": [one for one in re.split(r"[,\s]+", typed.get(_GPUS, "")) if one],
            "max_containers": _how_many(typed.get(_AT_ONCE, ""), "max containers"),
            "gpu_memory": self._one.gpu_memory if self._one is not None else 0,
        }


def _pairs(said: str) -> dict[str, str]:
    """A swarm's nodes as a form was given them: `HOSTNAME=SSH-HOST`, a comma apart.

    Raises:
      ValueError: For one that says no ssh host.
    """
    held: dict[str, str] = {}
    for one in (part.strip() for part in said.split(",")):
        if not one:
            continue
        node, _, via = one.partition("=")
        if not node.strip() or not via.strip():
            raise ValueError(f"nodes: {one!r} is not HOSTNAME=SSH-HOST")
        held[node.strip()] = via.strip()
    return held


class Swarming(_Daemon["SwarmRuntime"]):
    """A docker swarm, on one form: where its manager is, what its tasks may have, and where.

    The manager is reached every way a docker daemon is, on the rows a docker host's form
    has -- `local` being the swarm this machine manages. Under it, where a task may be put:
    the constraints `docker service create` is told, and which generic resource the nodes
    advertise their GPUs as. What all of its tasks together may reserve -- CPUs, memory -- is
    a quota rather than a host's size, each blank for none, and `detect` writes in what the
    nodes that may take a task have all told. No OCI runtime and no GPU ids: a service is
    told neither.

    The nodes row is for a node not reached at `ssh://<its address>`: its host name and the
    saved ssh host or the destination that does reach it, which is how what a task does gets
    to the node the swarm put it on.

    Correcting one asks the same, less the name it is saved under.
    """

    BACKEND: ClassVar[str] = _DOCKER_SWARM
    KIND: ClassVar[str] = "docker swarm"
    ABOUT: ClassVar[str] = (
        "A docker swarm where flow environments run as services of one task, "
        "placed on whichever node has room. Reached through a manager's "
        "daemon: on this machine, over ssh, or at an address. Flows on it are "
        "limited to the quota configured here."
    )
    CHECKS: ClassVar[str] = "checks its nodes"

    def _held(self, one: SwarmRuntime) -> dict[str, str]:
        """Its constraints, GPU resource, nodes and how many tasks it may run.

        Args:
          one: The swarm.
        """
        return {
            _CONSTRAINTS: ", ".join(one.constraints),
            _TASKS: str(one.max_tasks) if one.max_tasks else "",
            _RESOURCE: one.gpu_resource,
            _NODES: ", ".join(f"{node}={via}" for node, via in one.nodes.items()),
        }

    def _holds(self) -> list[Question]:
        """The image, where a task is put and reached, and what its tasks may reserve."""
        return [
            Question(
                _IMAGE,
                "image",
                "default image, unless specified by the flow; every node pulls it",
            ),
            Question(_ARGS, "run args", "extra arguments for docker service create"),
            Question(
                _CONSTRAINTS,
                "constraints",
                "placement constraints, e.g. node.labels.gpu==true, …",
            ),
            Question(_TASKS, "max tasks", "max concurrent tasks; blank for no limit"),
            Question(
                _NODES,
                "nodes",
                "HOSTNAME=SSH-HOST, …; blank to reach each at ssh://its address",
            ),
            Question(
                _WORKDIR,
                "workdir",
                "default working directory, on every node, when -e specifies none",
            ),
            _fallback_row(),
            Question(
                _RESOURCE,
                "gpu resource",
                "generic resource nodes advertise GPUs as, e.g. NVIDIA-GPU",
            ),
            Question(_CPUS, "cpus", "CPUs all tasks may reserve; blank for no quota"),
            Question(_MEMORY, "memory", "e.g. 64G for all tasks; blank for no quota"),
        ]

    def _more(self, typed: Mapping[str, str]) -> dict[str, Any]:
        """Its constraints, GPU resource, nodes and how many tasks it may run.

        Raises:
          ValueError: For a count that is not one, or a node with no ssh host.
        """
        return {
            "constraints": [
                one.strip()
                for one in typed.get(_CONSTRAINTS, "").split(",")
                if one.strip()
            ],
            "max_tasks": _how_many(typed.get(_TASKS, ""), "max tasks"),
            "gpu_resource": typed.get(_RESOURCE, ""),
            "nodes": _pairs(typed.get(_NODES, "")),
        }


class Imported(NamedTuple):
    """Which hosts of an ssh config to save, as the form they are switched on in answers.

    Attributes:
      config: The config, or None for the user's own.
      names: The hosts to save, by their `Host`.
      again: The ones saved already to save again, over what an import left.
      left: The ones switched off.
    """

    config: str | None
    names: tuple[str, ...] = ()
    again: tuple[str, ...] = ()
    left: tuple[str, ...] = ()


#: The row an import is told which ssh config to read on, and what each host's switch is put
#: up under, in front of its `Host`.
_CONFIG = "config"
_HOSTED = "host:"


class Importing(Form[Imported]):
    """The hosts an ssh config names, each switched on or off, saved from the row that answers.

    Read as `ssh -G` reads them -- the machine, the login, the port, the key, the jump host,
    `Include` and `Match` and all -- off the drawing path: it is a program. Each is switched
    on unless it is saved already, so bringing in a config's new hosts is the one row. The
    config is the user's own unless the first row says another, and nothing here writes to
    it: a host imported goes on reading it, so the config stays the one place it is written.
    """

    def __init__(self) -> None:
        """Initializes the form on the user's own config, read once it is up."""
        super().__init__()
        # Written in as a guess, so that a path typed over it replaces it.
        self._typed_in = {_CONFIG: _OWN_CONFIG}
        self._fresh.add(_CONFIG)
        self._hosts: list[SSHHost] = []
        #: What the hosts were last read from, as the row said it, or None before they were.
        self._read: str | None = None
        self._reading = False
        #: The ssh hosts saved already, by name: what an import would write over.
        self._saved = {one.name: one for one in _hmz().runtimes.all(_SSH)}
        #: Why a host starts switched off, by its `Host`, for the ones that do.
        self._off: dict[str, str] = {}

    def _config(self) -> str | None:
        """The config to read, or None for the user's own -- which ssh reads with the system's."""
        said = self._typed_in.get(_CONFIG, "").strip()
        try:
            own = not said or Path(said).expanduser() == Path(_OWN_CONFIG).expanduser()
        except (
            RuntimeError
        ):  # `~somebody` nobody is: a path that reads nothing, said so
            own = False
        return None if own else said

    def _standing(self, found: Sequence[SSHHost]) -> dict[str, str]:
        """Why each host that starts switched off does, by its `Host`.

        Read as the store names an imported host -- its `Host`, anything a name cannot hold
        made a dash -- since that name is what it would be saved under: a host saved under it
        already, one typed in under it, and one an earlier host takes it from.
        """
        from hmz.coganchor.machines.store import IMPORTED

        off: dict[str, str] = {}
        taken: dict[str, str] = {}
        for one in found:
            name = re.sub(r"[^A-Za-z0-9._-]", "-", one.alias).lstrip("._-")
            saved = self._saved.get(name)
            if not name:
                off[one.alias] = "invalid host name"
            elif name in taken:
                off[one.alias] = f"{taken[name]} already uses the name {name}"
            elif saved is not None and saved.made != IMPORTED:
                off[one.alias] = f"a manually added host is already saved as {name}"
            elif saved is not None:
                off[one.alias] = "already imported"
            taken.setdefault(name, one.alias)
        return off

    def _on(self, alias: str) -> bool:
        """Whether one host is switched on to be imported."""
        return self._typed_in.get(f"{_HOSTED}{alias}") == _YES

    def asked(self) -> list[Question]:
        """The config, and a switch per host it names."""
        rows = [
            Question(
                _CONFIG,
                "from",
                "the ssh config to read: default, or another file",
                needed=not self._typed_in.get(_CONFIG, "").strip(),
            )
        ]
        rows.extend(
            Question(f"{_HOSTED}{one.alias}", one.alias, self._about_host(one), _STEPS)
            for one in self._hosts
        )
        return rows

    def _about_host(self, one: SSHHost) -> str:
        """What a host's row says: where it reaches, as whom, with what, and if it is saved."""
        said = [
            f"{one.user}@{one.host}:{one.port}"
            if one.user
            else f"{one.host}:{one.port}",
            *((f"key {', '.join(one.identity_files)}",) if one.identity_files else ()),
            *((f"through {one.proxy_jump}",) if one.proxy_jump else ()),
            *((self._off[one.alias],) if one.alias in self._off else ()),
        ]
        return _DOT.join(said)

    def choices(self, held: str) -> Sequence[str]:
        """On and off, for a host."""
        return (_YES, _NO) if held.startswith(_HOSTED) else ()

    def note(self) -> str:
        """That the config is being read, or that it names nothing."""
        if self._reading:
            return f"reading {escape(self._typed_in.get(_CONFIG, ''))}…"
        if self._read is not None and not self._hosts and not self._wrong:
            return f"{escape(self._read)} contains no hosts to import"
        return ""

    def done_about(self) -> str:
        """What answering it does: which hosts it saves."""
        on = [one.alias for one in self._hosts if self._on(one.alias)]
        if not on:
            return "imports nothing until a host is selected"
        # Three by name, which a row has room for, and a count past that.
        return (
            f"imports {', '.join(on)}"
            if len(on) <= 3  # noqa: PLR2004
            else f"imports {len(on)} hosts"
        )

    def edited(self) -> None:
        """Reads the hosts again once the config the first row names has changed."""
        super().edited()
        if self._typed_in.get(_CONFIG, "").strip() != self._read:
            self._reads()

    def _ask(self) -> None:
        """Says what an import is, puts the form up, and reads the config."""
        self.query_one("#asked", Label).update("Import ssh hosts")
        self.query_one("#about", Label).update(
            "Hosts from an ssh config, as read by ssh. Each is saved under its "
            "Host name and continues reading the config, which is never "
            "modified."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()
        self._reads()

    @work(exclusive=True)
    async def _reads(self) -> None:
        """Reads the hosts the config names, off the loop, and lands on the row that imports.

        Exclusive, so that a config typed while another is being read is the one read.
        """
        import asyncio

        said = self._typed_in.get(_CONFIG, "").strip()
        self._reading, self._wrong = True, ""
        self._fill()
        envs = _hmz().runtimes
        try:
            found = await asyncio.to_thread(envs.hosts, self._config())
        except (
            OSError,
            RuntimeError,
        ) as why:  # no ssh, or a config nobody's home holds
            found, self._wrong = [], f"{said}: {why}"
        self._reading, self._read, self._hosts = False, said, found
        self._off = self._standing(found)
        for one in found:
            self._typed_in.setdefault(
                f"{_HOSTED}{one.alias}", _NO if one.alias in self._off else _YES
            )
        self._fill()
        if any(self._on(one.alias) for one in found):
            # On the row that imports them, now that there are rows for it to be below.
            self.query_one("#choices", OptionList).highlighted = len(found) + 1
            self._fill()

    def action_done(self) -> None:
        """Answers with the hosts switched on, once there are any."""
        if self._reading:
            self._wrong = "the config is still being read"
        elif not any(self._on(one.alias) for one in self._hosts):
            self._wrong = "select at least one host to import"
        if self._wrong:
            self._fill()
            return
        on = [one.alias for one in self._hosts if self._on(one.alias)]
        # Switched on over one saved already is saving it again, which the store is told.
        again = {alias for alias in on if alias in self._off}
        self.dismiss(
            Imported(
                self._config(),
                tuple(alias for alias in on if alias not in again),
                tuple(alias for alias in on if alias in again),
                tuple(one.alias for one in self._hosts if not self._on(one.alias)),
            )
        )


class Machine(Picks):
    """What to do with one runtime: correct it, check it, or take it away.

    Its own menu, as an account's is: three questions about the one under the cursor, taking
    it away last. Each happens at once -- checking one runs `ssh` or `docker`, one corrected
    is checked as it lands, and one taken away is a directory gone; a run already on it keeps
    what it read as it started.
    """

    SEARCHES: ClassVar = False

    def __init__(self, one: Runtime) -> None:
        """Asks about one runtime.

        Args:
          one: The runtime.
        """
        super().__init__()
        self._one = one
        self.asked = escape(f"{one.backend}/{one.name}")
        self.about = escape(_machine_line(one))

    def rows(self) -> list[tuple[str, str, str]]:
        """Correcting it, checking it, and taking it away."""
        return [
            (_CORRECTS, "edit", "edit saved settings"),
            (
                _CHECKS,
                "check",
                "check host resources: home directory, CPUs, memory, and GPUs"
                if self._one.backend == _SSH
                else "check the swarm's nodes against its quota"
                if self._one.backend == _DOCKER_SWARM
                else "check daemon resources against its limits",
            ),
            (_TAKES_AWAY, "remove", "remove this host immediately"),
        ]


class Hosts(Picks):
    """Which saved runtime of one backend a role's machine is -- or one more, added here.

    The runtimes saved on the runtimes page of `/settings`, each with what reaches it.
    Adding one is the row above them, on the form that page opens, and it comes back chosen.
    For a role on ssh a host nobody saved is a row as well: `-e` takes any host `ssh`
    reaches, and saving one under a name is a convenience rather than a condition.
    """

    ATOP: ClassVar = True

    def __init__(
        self, backend: str, current: str = "", *, unsaved: bool = False
    ) -> None:
        """Initializes the choosing.

        Args:
          backend: The backend whose runtimes these are.
          current: The one chosen now, which the tick goes against.
          unsaved: Whether a host nobody saved may be named instead.
        """
        super().__init__(current)
        self._backend = backend
        self._unsaved = unsaved
        self._said = ""
        self.adds = _KINDS.get(backend, "")
        self.asked = {
            _SSH: "Select the ssh host to use",
            _DOCKER: "Select the docker host to use",
            _DOCKER_SWARM: "Select the docker swarm to use",
        }.get(backend, f"Select the {backend} host to use")
        self.about = (
            "Saved on the runtimes page of /settings; any host you add here is "
            "saved there."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """Every runtime of the backend saved here, each with what reaches it."""
        return [
            (one.name, one.name, _machine_line(one))
            for one in _hmz().runtimes.all(self._backend)
        ]

    def above(self) -> list[tuple[str, str, str]]:
        """Adding one, naming one nobody saved, and searching."""
        rows = super().above()
        if self._unsaved:
            at = 1 if self.adds else 0
            rows.insert(
                at,
                (_UNSAVED, "unsaved host", "type any host ssh can reach"),
            )
        return rows

    def nothing(self) -> str:
        """What came of adding one, or that there is none saved yet."""
        if self._said:
            return self._said
        return "" if self._rows else f"no {escape(self._backend)} host is saved yet"

    def added(self) -> None:
        """Adds one, which is then the one chosen."""
        self._new()

    @work
    async def _new(self) -> None:
        """Adds a runtime of this backend without leaving the question, and chooses it."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            one, why = await provided(showing, self._backend)
        finally:
            self.opened()
        if one is None:
            if why:
                self._said = bad(escape(why))
                self._fill()
            return
        self.dismiss(one.name)

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Asks for a host nobody saved, where that is the row chosen.

        Args:
          event: What was chosen.
        """
        if str(event.option.id or "").removeprefix("=") != _UNSAVED:
            return  # the list's own, which answers it
        # Taken here and nowhere else: the list's own would answer with the row's id.
        event.prevent_default()
        self._types()

    @work
    async def _types(self) -> None:
        """Asks which host, and answers with it as it was typed."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        saved = any(one[0] == self._current for one in self._rows or [])
        try:
            said = await showing.push_screen_wait(
                Unsaved("" if saved else self._current)
            )
        finally:
            self.opened()
        if said:
            self.dismiss(said)


class Unsaved(Form[str]):
    """An ssh host nobody saved, named as `ssh` takes one: for one role, and nowhere else."""

    def __init__(self, host: str = "") -> None:
        """Initializes the form on a host already named, or on none.

        Args:
          host: The host named now, or "".
        """
        super().__init__()
        self._typed_in = {_HOST: host}

    def asked(self) -> list[Question]:
        """The host."""
        return [
            Question(
                _HOST,
                "host",
                "[user@]host[:port], or an alias in your ssh config",
                needed=not self._typed_in.get(_HOST, "").strip(),
            )
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "assigns the role to this host without saving it"

    def _ask(self) -> None:
        """Says what a host not saved is."""
        self.query_one("#asked", Label).update("Unsaved ssh host")
        self.query_one("#about", Label).update(
            "Connects using your ssh config with no extra settings. To save a "
            "host with a name, go to the runtimes page of /settings."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with the host, once it is one."""
        said = self._typed_in.get(_HOST, "").strip()
        if not said:
            self._wrong = "host is required"
        elif re.search(r"[\s/]", said):
            self._wrong = (
                f"{said!r} is not a valid host: cannot contain spaces or slashes"
            )
        if self._wrong:
            self._fill()
            return
        self.dismiss(said)


def _spelled(role: str, spec: str) -> tuple[str, str, str] | None:
    """What an `-e` spec comes to -- its backend, its machine, its directory -- read as `-e` is.

    Args:
      role: The role it is for.
      spec: What follows `<role>=`.

    Returns:
      The three, or None for a spec that does not read.
    """
    from hmz.runtime.flowing import SpecError, parse_envs

    try:
        (one,) = parse_envs([f"{role}={spec}"])
    except (SpecError, ValueError):
        return None
    # A directory the spec leaves out is its runtime's, followed rather than copied: `-e`
    # fills it in from the runtime, and a spec read back must not have it written in.
    kept = "/" in spec.partition("@")[2]
    return one.backend.value, one.provider, str(one.workdir) if kept else ""


#: The rows of the form an environment role is placed on, besides its workdir.
_BACKEND, _PROVIDER, _SPELLED = "backend", "provider", "spelled"

#: What each backend is, said beside its row and beside it on the list it is picked from.
_BACKENDS_ABOUT = {
    "local": "this machine",
    _SSH: "a machine reached over ssh",
    _DOCKER: "a container on a docker daemon",
    _DOCKER_SWARM: "a container on whichever node of a docker swarm has room",
}

#: What the machine is called on the row it is chosen on.
_ON_ROW = {_SSH: "host", _DOCKER: "daemon", _DOCKER_SWARM: "swarm"}


class Placing(Form[str]):
    """Where one environment role works: the backend, the machine, and the directory there.

    In the order they depend on each other, which is the order `-e` spells them in: the
    backend -- every one `-e` takes -- settles which machines there are to choose from, and a
    saved one brings where it works unless somebody says otherwise. What the rows come to is
    the last row, spelled as `-e` spells it; typing a whole one there sets the rows above,
    because a spec copied off a command line is a spec, and somebody holding one should not
    have to take it apart to say it here.
    """

    def __init__(self, role: str, spec: str = "") -> None:
        """Initializes the form on where the role is now.

        Args:
          role: The environment role.
          spec: Where it is now, as `-e` spells it after `<role>=`, or "" for nowhere yet --
            which starts on the first backend anything is saved for.
        """
        from hmz.flows import EnvBackendKind

        super().__init__()
        self._role = role
        self._local = EnvBackendKind.LOCAL.value
        self._kinds = [kind.value for kind in EnvBackendKind]
        envs = _hmz().runtimes
        read = _spelled(role, spec) if spec else None
        # One that does not read is kept as it was written, for somebody to correct.
        raw = spec if read is None else ""
        if read is None:
            backend = next(
                (one for one in self._kinds if one in _KINDS and envs.all(one)),
                self._kinds[0],
            )
            read = (backend, "", "")
        #: The runtimes looked up by the rows, by backend and name, read once apiece: the
        #: form is redrawn per keystroke, and which one the rows name is read off them.
        self._finds: dict[tuple[str, str], Runtime | None] = {}
        self._reads_in(read)
        if raw:
            self._typed_in[_SPELLED] = raw
        else:
            self._spells()

    def _reads_in(self, read: tuple[str, str, str]) -> None:
        """Puts a backend, a machine and a directory in the rows, the runtime's own if none.

        Args:
          read: The three, the directory "" for the one the runtime is saved with.
        """
        self._typed_in |= dict(zip((_BACKEND, _PROVIDER, _WORKDIR), read, strict=True))
        self._fresh.discard(_WORKDIR)
        found = self._machine()
        if not read[2] and found is not None and found.workdir:
            self._typed_in[_WORKDIR] = found.workdir
            self._fresh.add(_WORKDIR)

    def _machine(self) -> Runtime | None:
        """The runtime the rows name, where one is saved under that name."""
        key = (self._typed_in.get(_BACKEND, ""), self._typed_in.get(_PROVIDER, ""))
        if key not in self._finds:
            self._finds[key] = _hmz().runtimes.find(*key) if key[1] else None
        return self._finds[key]

    def _composed(self) -> str:
        """The rows, as `-e` spells them after `<role>=`, or "" where they say too little.

        Where the directory is still the one the runtime is saved with, it is left out, so
        that the role goes on working wherever that runtime is saved to.
        """
        backend, provider, workdir = (
            self._typed_in.get(one, "").strip()
            for one in (_BACKEND, _PROVIDER, _WORKDIR)
        )
        if backend == self._local:
            return f"{backend}@{workdir}" if workdir else ""
        if not provider:
            return ""
        head = f"{backend}@{provider}"
        found = self._machine()
        if _WORKDIR in self._fresh and found is not None and workdir == found.workdir:
            workdir = ""
        if not workdir:
            return head
        return head + (workdir if workdir.startswith("/") else f"/{workdir}")

    def _spells(self) -> None:
        """Spells the last row out of the rows above it, to be typed over."""
        self._typed_in[_SPELLED] = self._composed()
        self._fresh.add(_SPELLED)

    def asked(self) -> list[Question]:
        """The backend, the machine where it has one, the directory, and all of it spelled."""
        typed = self._typed_in
        backend = typed.get(_BACKEND, "")
        rows = [
            Question(
                _BACKEND,
                "backend",
                _BACKENDS_ABOUT.get(backend, "where the environment runs"),
                _STEPS,
            )
        ]
        found = self._machine()
        saved = found.workdir if found is not None else ""
        if backend != self._local:
            provider = typed.get(_PROVIDER, "").strip()
            rows.append(
                Question(
                    _PROVIDER,
                    _ON_ROW.get(backend, "provider"),
                    _machine_line(found)
                    if found is not None
                    else "not saved: connects via ssh as entered"
                    if provider and backend == _SSH
                    else "not saved in settings"
                    if provider
                    else "choose a saved host, or add one",
                    _OPENS_ONTO if backend in _KINDS else _WRITES,
                    needed=not provider,
                )
            )
        rows.append(
            Question(
                _WORKDIR,
                "workdir",
                "absolute path on this machine"
                if backend == self._local
                else f"leave blank to use saved default: {saved}"
                if saved
                else "remote working directory: /path or ~/path under home",
                needed=not typed.get(_WORKDIR, "").strip() and not saved,
            )
        )
        rows.append(
            Question(_SPELLED, "as -e", "full -e spec: typing one sets the rows above")
        )
        return rows

    def choices(self, held: str) -> Sequence[str]:
        """Every backend `-e` takes."""
        return self._kinds if held == _BACKEND else ()

    def means(self, held: str, value: str) -> str:
        """What each backend is, on the list it is picked from.

        Args:
          held: The row.
          value: The backend.

        Returns:
          A few words.
        """
        del held
        return _BACKENDS_ABOUT.get(value, "")

    def stepped(self, held: str) -> None:
        """Lets go of the machine and the directory, which were the last backend's.

        Args:
          held: The row that moved.
        """
        del held
        self._typed_in[_PROVIDER] = self._typed_in[_WORKDIR] = ""
        self._fresh.discard(_WORKDIR)
        self._spells()

    def _takes(self, provider: str) -> None:
        """Puts the role on a machine, working where it is saved to unless somebody said.

        Args:
          provider: The machine, by the name it is saved under or as it was typed.
        """
        self._typed_in[_PROVIDER] = provider
        if not self._typed_in.get(_WORKDIR) or _WORKDIR in self._fresh:
            found = self._machine()
            saved = found.workdir if found is not None else ""
            self._typed_in[_WORKDIR] = saved
            if saved:
                self._fresh.add(_WORKDIR)
            else:
                self._fresh.discard(_WORKDIR)
        self._spells()

    def opens(self, held: str) -> None:
        """Opens the machines of the backend chosen.

        Args:
          held: The row, which is the machine's.
        """
        if held == _PROVIDER:
            self._chooses()

    @work
    async def _chooses(self) -> None:
        """Asks which machine, and moves on to what is still to be answered."""
        if self.opening():
            return
        backend = self._typed_in.get(_BACKEND, "")
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            chosen = await showing.push_screen_wait(
                Hosts(
                    backend, self._typed_in.get(_PROVIDER, ""), unsaved=backend == _SSH
                )
            )
        finally:
            self.opened()
        if chosen is None:
            return
        if chosen != self._typed_in.get(_PROVIDER):
            self._finds.clear()  # one may have been added on the way
            self._takes(chosen)
            self._wrong = ""
            self.changed()
        self.kept(_PROVIDER)
        self._fill()

    def writes(self, row: str, event: events.Key) -> bool:
        """Takes a letter, and spells the last row again out of what it changed.

        Args:
          row: The question, by id.
          event: The key.

        Returns:
          Whether it was taken.
        """
        taken = super().writes(row, event)
        if taken and row == _PROVIDER:
            self._takes(self._typed_in[_PROVIDER])
        elif taken and row == _WORKDIR:
            self._spells()
        return taken

    def edited(self) -> None:
        """Takes a spec typed whole into the last row as the rows above, where it reads."""
        super().edited()
        if _SPELLED in self._fresh:
            self._spells()  # something above it moved, pasted in or walked off
            return
        read = _spelled(self._role, self._typed_in.get(_SPELLED, "").strip())
        if read is None:
            return  # kept as written, and said what is wrong with it once it is answered
        self._reads_in(read)
        self._spells()

    def done_about(self) -> str:
        """What answering it does: holds where the role is until the flow is saved."""
        spec = self._typed_in.get(_SPELLED, "").strip()
        if not spec:
            return f"leaves {self._role} unset"
        return f"sets {self._role} to {spec} when the flow is saved"

    def _ask(self) -> None:
        """Says which role this is, and lands on the first thing still to be answered."""
        self.query_one("#asked", Label).update(escape(f"Environment for {self._role}"))
        self.query_one("#about", Label).update(
            "The machine and working directory for this environment role. "
            "Choosing a machine saved on the runtimes page of /settings by "
            "name includes its saved working directory."
        )
        self._fill()
        first = next((at for at, one in enumerate(self._now or []) if one.needed), None)
        if first is not None:
            self.query_one("#choices", OptionList).highlighted = first
            self._fill()
        self.query_one("#choices", OptionList).focus()

    def action_done(self) -> None:
        """Answers with where the role is, read as `-e` reads it, or with nowhere at all."""
        typed = self._typed_in
        spec = typed.get(_SPELLED, "").strip()
        if not spec and any(
            typed.get(one, "").strip() for one in (_PROVIDER, _WORKDIR)
        ):
            missing = next((one for one in self.asked() if one.needed), None)
            self._wrong = (
                f"fill in the {missing.named} as well"
                if missing
                else "specify an environment"
            )
        elif spec:
            self._wrong = placed(self._role, spec)
        if self._wrong:
            self._fill()
            return
        self.dismiss(spec)


class Machines(Pages):
    """The runtimes page of `/settings`: every saved machine a flow's environments may go on.

    What a role's machine is chosen out of on `/flow` -- ssh hosts, docker daemons with what
    each may hand out, and docker swarms with what their tasks may reserve all told -- under a
    heading per backend, over the buttons that bring one in: adding any of them on one form,
    and importing the hosts an ssh config names. Enter on one opens what can be done to it:
    correcting it, checking it, taking it away.

    Nothing here is held until the menu is saved, so the page has no button to save from. What
    is added or corrected is asked what it has as it lands -- `ssh` into the host, `docker
    info` of the daemon, `docker node ls` of the swarm's manager -- and an import runs `ssh
    -G`: each is a command run, and something that has already run is not a draft. Taking one
    away goes with them, as a flowverse's does, on a page that holds nothing.
    """

    #: What the page says it is.
    MACHINES_ABOUT = (
        "Saved ssh hosts, docker daemons with the resources each may hand "
        "out, and docker swarms with what their tasks may reserve, used by "
        "name as flow environments in -e and /flow. "
        "Changes take effect immediately."
    )

    def __init__(self) -> None:
        """Holds nothing until the page is first read."""
        super().__init__()
        self._saved_machines: list[Runtime] = []
        #: The ones being asked what they have, as `backend/name`, which their rows say.
        self._checking: dict[str, object] = {}

    def _read_machines(self) -> None:
        """Reads every runtime off the disk, which is what the rows are drawn from."""
        self._saved_machines = _hmz().runtimes.all()

    @staticmethod
    def _machine_key(one: Runtime) -> str:
        """One runtime as it is keyed here: by its backend and its name."""
        return f"{one.backend}/{one.name}"

    def _machine_actions(self) -> list[Action]:
        """What is done about the machines: adding one of any kind, importing, and searching.

        One button adds every kind, dropping the kinds over it, as one `+` does in an editor's
        panel: a button per kind was a bar wider than a terminal, and three ways of saying
        add. No saving: nothing on this page is held.
        """
        return [
            Action(
                _ACT_ADD,
                "add a runtime…",
                "an ssh host, a docker host or a docker swarm",
                self._picks_kind,
            ),
            Action(
                _ACT_IMPORTS,
                f"import {_OWN_CONFIG}",
                "hosts from this or another config file",
                self._imports_hosts,
            ),
            self._searches(),
        ]

    def _fill_machines(self) -> None:
        """Puts the runtimes up under a heading per backend."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        lined = [(one, _machine_line(one)) for one in self._saved_machines]
        shown = [
            (one, line) for one, line in lined if self.fits(one.name, one.backend, line)
        ]
        landing = self._lands([self._machine_key(one) for one, _ in shown])
        rows: list[Option] = []
        group = ""
        for seen, (one, line) in enumerate(shown):
            keyed = self._machine_key(one)
            if one.backend != group:
                # A heading, with a blank line above it once there is a group above it.
                if group:
                    rows.append(Option("", disabled=True))
                group = one.backend
                rows.append(Option(f" [$primary]{escape(group)}[/]", disabled=True))
            about = f"{line}{_DOT}checking…" if keyed in self._checking else line
            rows.append(
                Option(
                    self._row(
                        seen, one.name, about, here=keyed == landing, inforce=False
                    ),
                    id=f"={keyed}",
                )
            )
        self._put(listing, rows, landing)
        self._drawn = listing.highlighted
        said = self._said or (
            ""
            if self._saved_machines
            else "no machines saved yet; a role can still name one directly"
        )
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self._footed(Key("enter", "open"), Key("esc", "close"))

    def _took_machine(self, named: str) -> None:
        """Opens what there is to do with the runtime chosen.

        Args:
          named: The row chosen, by its id.
        """
        one = next(
            (each for each in self._saved_machines if self._machine_key(each) == named),
            None,
        )
        if one is not None:
            self._doing_machine(one)

    @work
    async def _doing_machine(self, one: Runtime) -> None:
        """Asks what to do with one runtime, and does it.

        Args:
          one: The runtime.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            said = await showing.push_screen_wait(Machine(one))
        finally:
            self.opened()
        if said == _CORRECTS:
            self._corrects_machine(one)
        elif said == _CHECKS:
            self._checks(one)
        elif said == _TAKES_AWAY:
            self._drops_machine(one)

    @work
    async def _picks_kind(self) -> None:
        """Drops the kinds of runtime over the button that adds one, and adds the one picked.

        Esc, or a click off the list, adds nothing.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        button = self.query_one(f"#act-{_ACT_ADD}")
        try:
            picked = await showing.push_screen_wait(
                Dropdown("add a runtime", _ADDING, "", at=button.region.offset)
            )
        finally:
            self.opened()
        if picked:
            self._adds_machine(picked)

    @work
    async def _adds_machine(self, backend: str) -> None:
        """Asks for a runtime on the form that makes one, saves it, and asks what it has.

        Args:
          backend: `ssh`, `docker` or `swarm`.
        """
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            one, why = await provided(showing, backend)
        finally:
            self.opened()
        if one is None:
            if why:
                self._said = bad(escape(why))
                self._fill()
            return
        self._told.append(
            f"[dim]{escape(self._machine_key(one))} saved to "
            f"{escape(str(one.at))}[/dim]"
        )
        self._read_machines()
        self._aim = self._machine_key(one)
        self._checks(one)

    @work
    async def _corrects_machine(self, one: Runtime) -> None:
        """Asks what one runtime is to say, starting from what it says, and saves it.

        Args:
          one: The runtime.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        form: Form[Runtime] = (
            Hosting(cast("SSHRuntime", one))
            if one.backend == _SSH
            else Swarming(cast("SwarmRuntime", one))
            if one.backend == _DOCKER_SWARM
            else Docking(cast("DockerRuntime", one))
        )
        fixed = await showing.push_screen_wait(form)
        if fixed is None or fixed == one:
            return  # walked out, or nothing changed
        try:
            _hmz().runtimes.write(fixed)
        except OSError as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        self._told.append(f"[dim]{escape(self._machine_key(fixed))} updated[/dim]")
        self._read_machines()
        self._aim = self._machine_key(fixed)
        self._checks(fixed)

    def _drops_machine(self, one: Runtime) -> None:
        """Takes one runtime away, and says what that leaves reaching nothing.

        Args:
          one: The runtime.
        """
        keyed = self._machine_key(one)
        try:
            _hmz().runtimes.remove(one.backend, one.name)
        except (OSError, ValueError) as why:
            self._said = bad(escape(str(why)))
            self._fill()
            return
        self._told.append(f"[dim]{escape(keyed)} removed[/dim]")
        self._said = f"{escape(keyed)} removed"
        # A docker daemon reached through the host that went is reached through nothing, and
        # so is a swarm whose manager was, or one of whose nodes was.
        if one.backend == _SSH:
            for backend, what in ((_DOCKER, "docker"), (_DOCKER_SWARM, "a swarm")):
                stranded = [
                    each.name
                    for each in self._saved_machines
                    if each.backend == backend and _through(each, one.name)
                ]
                if stranded:
                    self._said += "\n" + iffy(
                        escape(
                            f"{', '.join(stranded)} reached {what} through this host; "
                            "edit them"
                        )
                    )
        self._was = ""
        self._read_machines()
        self._fill()

    @work
    async def _imports_hosts(self) -> None:
        """Asks which hosts of an ssh config to save, and saves them."""
        if self.opening():
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        try:
            chosen = await showing.push_screen_wait(Importing())
        finally:
            self.opened()
        if chosen is None:
            return
        envs = _hmz().runtimes
        try:
            # The ones imported again first: the one that is refused -- a host somebody typed
            # in under that name -- is then refused before anything is written.
            made = [
                *(
                    envs.import_ssh(chosen.config, chosen.again, update=True)
                    if chosen.again
                    else ()
                ),
                *envs.import_ssh(chosen.config, chosen.names),
            ]
        except (OSError, ValueError, RuntimeError) as why:
            self._said = bad(escape(str(why)))
            self._read_machines()
            self._fill()
            return
        names = ", ".join(one.name for one in made)
        whence = _config_named(chosen.config or "")
        if made:
            self._told.append(
                f"[dim]{escape(names)} imported from {escape(whence)}[/dim]"
            )
        said = f"imported {names or 'nothing'} from {whence}"
        if chosen.left:
            said += f"; left {', '.join(chosen.left)}"
        self._said = escape(f"{said}. Open a host to check it.")
        self._read_machines()
        if made:
            self._aim = self._machine_key(made[0])
        self._fill()

    @work
    async def _checks(self, one: Runtime) -> None:
        """Asks one runtime what it has, saying so while it does and after.

        In the background: it is `ssh` reaching a machine or `docker` reaching a daemon, and
        either may take the better part of a minute to give up -- a page that could not be
        read or left meanwhile would be a page that looked as though it had hung.

        Args:
          one: The runtime.
        """
        keyed = self._machine_key(one)
        # This one's own, so that the answer to one asked before it was corrected is not
        # taken for the answer to what it is now: the last asked is the one said.
        turn = self._checking[keyed] = object()
        self._tell(_MACHINES, f"checking {escape(keyed)}…")
        self._fill()
        said = await _checked(one)
        if self._checking.get(keyed) is not turn:
            return
        del self._checking[keyed]
        self._tell(
            _MACHINES,
            bad(escape(said)) if isinstance(said, str) else _answered(one, said),
        )
        self._fill()


class Adjusted(NamedTuple):
    """What the settings menu answers with: what was changed, and what happened.

    Attributes:
      enable_sentry: Whether humanize reports its own failures from now on, or None where
        that was not touched.
      details: Whether the working of each turn is shown, or None where that was not touched.
      profile: Whether a run in this directory is profiled as well as traced, or None where
        that was not touched.
      forget: Whether to forget what this workspace was set up to run.
      told: What the pages that write for themselves -- the accounts, the runtimes and the
        fallbacks -- did, as lines for the transcript.
      btw: The agent `/btw` asks about a whole flow, as `cli@provider/model:effort` or "" for
        the flow's first agent, or None where that was not touched.
      corrected: The accounts corrected, as `(cli, name)`, whose models are to be asked for
        again: what an account runs follows from where it signs in, and a gateway moved is a
        list of models from the one it left.
    """

    enable_sentry: bool | None = None
    details: bool | None = None
    profile: bool | None = None
    forget: bool = False
    told: tuple[str, ...] = ()
    btw: str | None = None
    corrected: tuple[tuple[str, str], ...] = ()


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
            f"{escape(str(ran.at))}\nIt {_how(ran)} with "
            f"{_many(len(ran.agents), 'agent')} in "
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
                    "resume run",
                    "resume the flow from this run",
                )
            )
        held.append(
            (
                _EXPORTS,
                "export run",
                "the entire run as an archive, with its trace",
            )
        )
        return held

    def nothing(self) -> str:
        """Why carrying on is not one of the things there are to do, where it is not."""
        if self._resumable:
            return ""
        return (
            f"{escape(self._ran.flow)} is not resumable, so this run cannot be resumed"
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
        "stopped": "stopped",
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
            "Every run of a flow in this directory, newest first: task, "
            "status, and session count."
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
        return f"{held}{_DOT}resumable" if self._carries_on(ran) else held

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
        self._footed(Key("enter", "open"), Key("esc", "close"))

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
            self._said = (
                "a flow is running; press ctrl+c twice to stop it before resuming "
                "another"
            )
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
