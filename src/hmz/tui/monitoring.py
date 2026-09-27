"""The monitor: the run drawn across the whole screen, and the screen every log is left for.

Two screens make up the interface. The log is the transcript -- every agent's, one agent's --
and the monitor is the run itself: a node per agent that has worked, or per session with
`ctrl+t`, marked as each one works, the handovers between them as the arrows joining them,
and the board under them. It is the parent of the two, which is why the log is reached from it
by picking what to read and why `←` on an empty prompt comes back to it.

It is drawn with the same prompt under it as the log, because it is the same interface with the
transcript swapped for the graph: every command works here, and what the log says in its status
line and above its prompt is said here by the graph and the line under it.
"""

# The sheets' own module, split along the one screen of it that is not a sheet: the monitor
# draws with the marks they draw with and opens their entry sheet, so it reads what they keep
# to themselves. Named `monitoring` for the screen, as `monitor` is named for what it reads.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from rich.markup import escape
from textual import events, on, work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from hmz.coganchor.agents import ANYONE, FLOW, USER
from hmz.coganchor.prices import money

from .monitor import lasting, short, thousands
from .pick import (
    _DOT,
    _FIELD,
    _HERE,
    _IDLE,
    _INDENT,
    _LABEL,
    _LIVE,
    _WORKING,
    EVERY,
    Key,
    Sheet,
    _hmz,
    bad,
    named_as,
    reads,
    setting,
)
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic import BaseModel
    from textual.app import App, ComposeResult

    from hmz.coganchor.agents import Board
    from hmz.runtime.kept import Runs

    from .monitor import Counted, Monitor, Shape, Under

__all__ = ["EVERY", "OUTWORLDER", "Drawn", "Entry", "Monitoring"]

#: What the node of an outworlder is read under, ahead of its role: the log a person reads
#: what the flow says to them in, and answers it from.
OUTWORLDER = "outworlder:"

#: What the diagram draws one agent's box with, and what it joins two of them by. Light
#: box-drawing, which is what a terminal has for a box that is a label rather than a frame.
_BOX = ("┌", "┐", "└", "┘", "─", "│")

#: What says a handover went down the diagram and what says it came back up it, and what
#: stands between two agents the flow never handed between directly.
_DOWN, _UP, _NEITHER = "↓", "↑", "┆"

#: How wide one agent's box is drawn, at most, and how narrow it is allowed to get. Wide
#: enough for what an agent runs beside how long it has been running it, and narrow enough
#: that the diagram still reads in a terminal somebody has left half the width of.
_WIDEST = 72
_NARROWEST = 24

#: What stands in front of the clock on an agent that is not working, so that the two halves
#: of a box are never read as the same kind of thing: one says how long a turn has been going
#: and the other how long ago the last one stopped.
_IDLED = "idle"

#: What an agent one of them started of its own is drawn with: no box of its own, a corner
#: hanging off the one above it, and a mark that is not the one a flow's agents wear. It is
#: not an agent of the flow -- nobody chose what it runs, nothing can be said to it, and it
#: has no transcript to read -- so it is drawn as a thing the agent above it is doing, and a
#: box would say it was another agent to attach to.
_UNDER, _LAST_UNDER = "├╴", "└╴"
_FLEET_WORKING, _FLEET_DONE = "◆", "◇"

#: How many of a fleet are drawn under one agent before the rest are counted rather than
#: listed. A turn that started forty is a turn nobody wants forty rows about.
_FLEET_SHOWN = 4

#: What a row of the board is put up under, so that a row about a line and a row about an
#: agent are told apart by their ids alone: an id is a name somebody chose, and a character
#: no name has is the one thing no agent can be called by accident.
_ON_BOARD = "\x00"

#: What the board's own heading is put up under, which is a row nothing lands on. Not one of
#: the ids a line is put up under either: a heading that read as a line would be a row
#: something could be pressed on.
_BOARDED = "\x01"

#: What the row saying nothing has worked yet is put up under, which is a row nothing lands
#: on either: the diagram is empty until a first turn starts, and one line says more about a
#: run that has not begun than a blank page does.
_NOTHING = "\x02"

#: The mark against a line of the board. One mark, one kind of thing: whose a line is is said
#: in words beside it and in the colour it is drawn, which is what a reader actually reads --
#: a second glyph would be a second thing to learn for the same fact.
_ON_IT = "◈"


def _flowing(started: str) -> list[str]:
    """Which flow is running, and inside which, for the row that names one.

    A flow may reach for another by name and run it, so the flow a run is in is not always
    the flow that was started -- and a sheet that named only the one somebody chose would be
    a sheet that stopped being true the moment a flow called another.

    Args:
      started: The flow that was chosen, which is what this says with nothing running.

    Returns:
      One line apiece, the one that was started first and whatever it called under it, each
      with how long it has been going; and just the one that is set up to run where nothing
      is running.
    """
    now = _hmz().flows.running()
    if not now:
        return [escape(started)]
    return [
        f"{'  ' * (one.depth - 1)}{'▸ ' if one.depth > 1 else ''}"
        f"{escape(named_as(one.ref))}"
        f"   [$text-muted]{time.monotonic() - one.since:.0f}s[/]"
        for one in now
    ]


class Drawn(NamedTuple):
    """One node of a run -- an agent, or one session of one -- as the monitor draws it.

    Attributes:
      who: The key the node is read under: the agent id for an agent, `<role>/<n>` for the
        n-th session of that role. What reading it names, and what the graph counts it under.
      named: What to call it on its box, or "" to call it by its id cut down.
      runs: What it runs, as the line that says what each agent is says it.
      working: Whether it has a turn open right now.
      reading: Whether its transcript is the one on the screen behind this sheet.
      unread: Whether it has said something since it was last looked at, which is the one
        thing on a box that says pressing enter on it is worth doing now.
    """

    who: str
    named: str = ""
    runs: str = ""
    working: bool = False
    reading: bool = False
    unread: bool = False


class _Said(NamedTuple):
    """One line inside a box: what it says on the left, and what it says on the right.

    Two halves rather than one line, because they are two kinds of fact read at two speeds:
    what an agent *is* stands still on the left, and what it is *doing now* moves on the
    right -- so the right is what a reader watching a run keeps coming back to, and it is
    kept in one column down the page for them to come back to.

    Attributes:
      colour: What to draw the left half in.
      said: The left half, in plain words.
      tail: The right half, in plain words, or "" for a line that has no right half.
      tailing: What to draw the right half in.
    """

    colour: str
    said: str
    tail: str = ""
    tailing: str = "$text-muted"


def _marked(*, here: bool) -> str:
    """The three columns in front of a row, holding the marker where the cursor is.

    Three, which is what every sheet indents by: the marker sits in the indent rather than
    pushing the row along, so the diagram does not shuffle sideways as the cursor walks it.

    Args:
      here: Whether the cursor is on this row.

    Returns:
      The gutter, as markup.
    """
    return f" [$primary]{_HERE}[/] " if here else _INDENT


def _boxed(said: Sequence[_Said], width: int, *, here: bool = False) -> list[str]:
    """One agent, drawn as a box the width of the diagram.

    Args:
      said: The lines to put in it, each as the colour to draw it in and the plain words to
        draw. Plain, so that what will not fit can be cut before any markup is put round it:
        a bracket an agent's name happens to hold is a bracket, and an escape of one is
        characters that are not columns.
      width: How wide to draw it, borders included.
      here: Whether the cursor is on this box, which is said in the colour of its sides. The
        rows of this list are pictures rather than lines of text, and a highlight that
        recoloured the row would be one the markup inside the picture painted straight over.

    Returns:
      The box, a line at a time, each exactly as wide as the last.
    """
    left, right, under_left, under_right, across, side = _BOX
    edge = "$primary" if here else "$text-muted"
    room = width - 4
    lines = [f"[{edge}]{left}{across * (width - 2)}{right}[/]"]
    for one in said:
        # The right half first and whole: it is the shorter of the two and the one that
        # moves, so the left is what gives where there is not room for both.
        tail = _fits(one.tail, room)
        head = _fits(one.said, room - len(tail) - (1 if tail else 0))
        pad = " " * max(0, room - len(head) - len(tail))
        lines.append(
            f"[{edge}]{side}[/] [{one.colour}]{escape(head)}[/]{pad}"
            + (f"[{one.tailing}]{escape(tail)}[/]" if tail else "")
            + f" [{edge}]{side}[/]"
        )
    lines.append(f"[{edge}]{under_left}{across * (width - 2)}{under_right}[/]")
    return lines


def _fits(said: str, room: int) -> str:
    """One line of a box, cut to the room there is for it rather than running past its side.

    Args:
      said: The words, as they are.
      room: How many columns there are between the two sides of the box.

    Returns:
      Them, or as much of them as fits with an ellipsis where the rest was, and nothing at
      all where there is no room for anything -- a box drawn in a terminal nobody could read
      it in still has two sides that line up.
    """
    if room <= 0:
        return ""
    return said if len(said) <= room else said[: room - 1] + "…"


def _joins(down: int, up: int, *, live: bool = False) -> list[str]:
    """The arrows between two boxes, saying which way the flow went, how often, and last.

    Args:
      down: How many times the agent above handed to the one below.
      up: How many times it came back the other way.
      live: Whether the handover the flow took most recently went along this arrow, which is
        drawn lit. With six boxes on the page, where the run just went is the first thing a
        reader looks for, and a picture that is not moving says it nowhere else.

    Returns:
      The one line between the two boxes.
    """
    ways = _DOT.join(
        said
        for said, often in ((f"{_DOWN} {down}", down), (f"{_UP} {up}", up))
        if often
    )
    # A spine down the left, so the boxes read as one run rather than as a stack of cards:
    # solid where the flow has gone between these two, dotted where it never has.
    spine = _BOX[5] if ways else _NEITHER
    return [f"[{'$secondary' if live else '$text-muted'}]{spine}   {ways}[/]"]


def diagram(
    drawn: Sequence[Drawn], shape: Shape, width: int, here: str = ""
) -> list[list[str]]:
    """The agents of a run and the handovers between them, as one box apiece.

    The shape of a flow is not written anywhere: a flow is a Python file that may branch any
    way it likes, so what it did is read off the turns going past. Drawn down the page in the
    order the flow takes its agents, with the handovers between neighbours as the arrows that
    join them -- which is the shape of nearly every flow there is, since a flow is written as
    one agent after another. The rest are said under it rather than drawn as lines crossing
    the page, there being no way to draw those in a terminal that reads as anything.

    Each box says what its agent is on the left and what it is doing on the right: how long
    the turn it has open has been open, or how long it has been since it last worked. That is
    the half a reader comes back to, and the half nothing else on the screen carries -- the
    lines above the prompt say what an agent is, and the status line says only whose turn it
    is now.

    Args:
      drawn: The agents, in the order the flow takes them.
      shape: The run as a graph, which says who is working, who handed to whom, and how long
        each of them has been at it.
      width: How much room there is across.
      here: The agent whose box the cursor is on, or "" for a cursor that is somewhere else.

    Returns:
      One block of lines per agent, in the same order: the arrows above it and then its box,
      so that a list of blocks is the diagram from top to bottom.
    """
    across = max(_NARROWEST, min(_WIDEST, width - len(_INDENT) - 5))
    blocks: list[list[str]] = []
    for at, one in enumerate(drawn):
        before = drawn[at - 1].who if at else ""
        arrows = (
            []
            if at == 0
            else _joins(
                shape.handovers.get((before, one.who), 0),
                shape.handovers.get((one.who, before), 0),
                live=shape.latest in {(before, one.who), (one.who, before)},
            )
        )
        taken = shape.turns.get(one.who, 0)
        clock = lasting(shape.since.get(one.who, 0.0))
        tail, tailing = (
            ("reading", "$primary")
            if one.reading
            else ("unread", "$secondary")
            if one.unread
            else ("", "$text-muted")
        )
        block = (
            arrows
            + _boxed(
                [
                    _Said(
                        "$secondary" if one.working else "$foreground",
                        f"{_WORKING if one.working else _IDLE} "
                        # What the flow calls it, or the id cut down where it calls it
                        # nothing: one name, since two for the same thing is one said twice.
                        + (one.named or short(one.who)),
                        clock if one.working else f"{_IDLED} {clock}",
                        "$secondary" if one.working else "$text-muted",
                    ),
                    _Said(
                        "$text-muted",
                        _DOT.join(
                            part
                            for part in (
                                one.runs,
                                f"{taken} turn{'' if taken == 1 else 's'}"
                                if taken
                                else "",
                            )
                            if part
                        ),
                        tail,
                        tailing,
                    ),
                ],
                across,
                here=one.who == here,
            )
            + fleet(shape.under.get(one.who, ()), across)
        )
        # The marker goes beside the agent's name rather than against the top of its box: the
        # name is the line being read, and a marker on a border reads as part of the border.
        named = len(arrows) + 1
        blocks.append(
            [
                _marked(here=one.who == here and line == named) + said
                for line, said in enumerate(block)
            ]
        )
    return blocks


def fleet(under: Sequence[Under], width: int) -> list[str]:
    """The agents one agent started of its own, hanging off the bottom of its box.

    Drawn rather than listed elsewhere because that is where they are: a subagent is a thing
    the agent above it is doing, so it belongs under that agent and nowhere else. And drawn
    without a box of its own, for the reason it has no transcript: a box is what a flow's own
    agents wear, and one round a subagent would say it was another agent to attach to.

    Args:
      under: The fleet, oldest first.
      width: How wide the boxes are, so these sit under them rather than beside them.

    Returns:
      One line per subagent, and nothing at all for an agent that has started none. A fleet
      too long to draw is cut, with a line saying how many were left off: a turn that started
      forty is a turn nobody wants forty rows about.
    """
    if not under:
        return []
    shown = list(under[:_FLEET_SHOWN])
    rest = len(under) - len(shown)
    room = max(width - 6, 12)
    lines: list[str] = []
    for at, one in enumerate(shown):
        last = at == len(shown) - 1 and not rest
        mark = _FLEET_WORKING if one.working else _FLEET_DONE
        colour = "$secondary" if one.working else "$text-muted"
        lines.append(
            f"[$text-muted]{'  ' + (_LAST_UNDER if last else _UNDER)}[/]"
            f"[{colour}]{mark}[/] [$text-muted]{escape(_fits(one.about, room))}[/]"
        )
    if rest:
        lines.append(f"[$text-muted]  {_LAST_UNDER}{_FLEET_DONE} and {rest} more[/]")
    return lines


def elsewhere(drawn: Sequence[Drawn], shape: Shape) -> list[str]:
    """The handovers the diagram has no arrow for, said rather than drawn.

    Which are the ones between agents the boxes did not put next to each other: a line
    crossing the page from the first box to the fourth is a line nothing in a terminal draws
    readably, so it is a row under the diagram instead.

    Args:
      drawn: The agents, in the order the flow takes them.
      shape: The run as a graph.

    Returns:
      One line per handover the boxes have no arrow for, which is nothing at all for the
      flows that are one agent after another.
    """
    order = {one.who: at for at, one in enumerate(drawn)}
    return [
        f"{escape(short(sender))} → {escape(short(taker))}{_DOT}×{often}"
        for (sender, taker), often in sorted(shape.handovers.items())
        if abs(order.get(sender, -1) - order.get(taker, -1)) != 1
        or sender not in order
        or taker not in order
    ]


def _kinds(counted: Sequence[Counted]) -> list[str]:
    """What a run spent its tokens on, kind by kind, as the rows under the diagram say it.

    Args:
      counted: One entry per kind, as the monitor reckons them.

    Returns:
      A row per kind, and a last row saying what a `+` means where anything wears one. The
      mark rather than a column of its own: it is on the figure it is about, and a legend
      nobody has to read unless a figure has one.
    """
    if not counted:
        return ["[$text-muted]nothing spent yet[/]"]
    rows = [
        f"{escape(one.kind):<26}{thousands(one.tokens):>8}{'' if one.whole else '+'}"
        for one in counted
    ]
    if not all(one.whole for one in counted):
        rows.append("[$text-muted]+ a floor: not every agent here reports that kind[/]")
    return rows


class Entry(Sheet[tuple[str, str]]):
    """One line of the board, typed: what it is called, and then what it says.

    Typed rather than picked, because it is words: a line of a board is what somebody wants
    said, and a list has nothing to offer them. Two questions in one sheet, since a line
    nobody named is not a line and a name with nothing under it is a line that says nothing.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("enter", "onward", "next", priority=True),
    ]

    def __init__(self, key: str, value: str, board: Board) -> None:
        """Initializes the writing.

        Args:
          key: The line being changed, or "" for one being put up now -- which is what makes
            this ask for a name first.
          value: What it says now, which is what is offered to change.
          board: The board it goes on, so a name already taken can be said about here rather
            than found on the way out.
        """
        super().__init__()
        self._key = key
        self._value = value
        self._board = board
        #: Which of the two is being typed: a line already there is named, so it opens on
        #: what it says.
        self._naming = not key
        self._typed = key if self._naming else value
        self._said = ""

    def _ask(self) -> None:
        """Says what a line of the board is, and takes what is typed from here on."""
        self.query_one("#asked", Label).update(
            "A line of the board" if self._naming else f"{escape(self._key)}"
        )
        self.query_one("#about", Label).update(
            "What you and the flow both write on. Neither of you waits on the other."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts up what has been typed, which is the whole of what this sheet shows."""
        listing = self.query_one("#choices", OptionList)
        asked = "what to call it" if self._naming else "what it says"
        listing.set_options(
            [
                Option(
                    f"{_INDENT}[$text-muted]{asked}[/]  "
                    f"[$secondary]{escape(self._typed)}[/][reverse] [/reverse]",
                    id="=typed",
                )
            ]
        )
        listing.highlighted = 0
        self._drawn = 0
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said}[/]" if self._said else ""
        )
        self._footed(
            Key("type", "write"),
            Key("backspace", "rub out"),
            Key(
                "enter",
                "on to what it says"
                if self._naming
                else "write it down, or take it away if empty",
            ),
            Key("esc", "back"),
        )

    def on_key(self, event: events.Key) -> None:
        """Takes every printable key as what is being typed, which is what this sheet is.

        Not a search that has to be asked for, as it is on a sheet of choices: there is
        nothing here to choose between, so the letters have nowhere else to go.

        Args:
          event: The key.
        """
        if event.key == "backspace":
            self._typed = self._typed[:-1]
        elif event.is_printable and event.character:
            self._typed += event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self._said = ""
        self._fill()

    def action_onward(self) -> None:
        """Takes the name and asks what it says, or writes the line down."""
        if not self._naming:
            self.dismiss((self._key, self._typed))
            return
        named = self._typed.strip()
        if not named:
            self._said = "a line of the board is named"
            self._fill()
            return
        held = self._board.held(named)
        if held is not None and held.whose == FLOW:
            self._said = f"{escape(named)} is the flow's to change, not yours"
            self._fill()
            return
        self._key, self._naming = named, False
        self._typed = held.value if held is not None else self._value
        self._said = ""
        self.query_one("#asked", Label).update(escape(self._key))
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, _event: OptionList.OptionSelected) -> None:
        """A click on the one row means what enter means, there being one thing to do."""
        self.action_onward()


#: What the row that puts a new line on the board is put up under: the board's own mark with
#: no name after it, there being no line yet.
_NEW = _ON_BOARD

#: What the node mode is called on the status line, and what `ctrl+t` turns it to.
_BY = {False: "agent", True: "session"}


class _Row(NamedTuple):
    """One row of the graph: what it is about, what it draws, and whether it is landed on.

    A row here is a picture rather than a line of text -- a box with the arrows above it, a
    line of the board -- so it is built as markup and kept as markup: the markup is what is
    compared against the last redraw, and what is put back in place of it where they differ.

    Attributes:
      who: The node this is about -- a view key, as the log reads one -- or the board line,
        or one of the ids nothing lands on.
      said: The row, as markup.
      landing: Whether the cursor stops on it. A heading is not something to press enter on.
    """

    who: str
    said: str
    landing: bool = True


class Monitoring(Screen[str | None]):
    """The run, drawn full screen: a node per agent or per session, and the board under it.

    The graph is the screen. What somebody comes here for is the shape of the run and where it
    has got to -- which agent is thinking, how long it has been thinking, which way the work
    went last -- and all of that is in the picture. So the picture takes the height, and what
    is written under it is only what a picture cannot say: the flows running, what this one
    was set up with, the handovers no arrow could be drawn for, and what has been spent.

    It is where a log is picked to be read. The first node is every agent's log, selected
    when this opens, so enter reads the run whole; each node under it reads its own; `→` goes
    back to whichever was read last. A node stays for the rest of the run, working or not.

    And the prompt is under it, the same prompt as the log's: every command works here, and a
    line typed goes where it would have gone from the log. The arrows and enter are the
    graph's only while nothing is typed, since a line being written needs them back.

    Redrawn twice a second, since what it is about moves without anybody touching it. Answers
    with the view to read, or None for the one that was being read.
    """

    DEFAULT_CSS = """
    #graph { height: 1fr; padding: 0 1; border: none; background: $surface; }
    #graph:focus { border: none; }
    #graph > .option-list--option-highlighted { background: $surface; text-style: none; }
    #graph > .option-list--option-hover { background: $surface; }
    #under { height: auto; padding: 0 2; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        # Priority, so they reach the graph ahead of the prompt -- and only while nothing is
        # typed, which `check_action` says: a line being written needs its arrows and its
        # enter, and walks what was typed before with them.
        Binding("up", "step(-1)", "previous node", show=False, priority=True),
        Binding("down", "step(1)", "next node", show=False, priority=True),
        Binding("enter", "open", "read it", show=False, priority=True),
        Binding("right", "back", "back to the log", show=False, priority=True),
        Binding("ctrl+t", "turn", "agents or sessions", show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        monitor: Callable[[], Monitor],
        drawn: Callable[[bool], Sequence[Drawn]],
        setup: Callable[[], tuple[str, tuple[str, ...], list[Runs], BaseModel | None]],
        reading: Callable[[], str] = lambda: EVERY,
        board: Callable[[], Board | None] = lambda: None,
        outworlders: Callable[[], Sequence[str]] = tuple,
        sessions: bool = False,
        turned: Callable[[bool], None] = lambda _: None,
    ) -> None:
        """Watches the run, asking about it afresh each time it is drawn.

        Asked rather than given, every one of them, because the answers move while this is
        up: an agent appears as its first turn starts, a run started from the prompt here is a
        new run with a new monitor, and a command typed here may change what is set up.

        Args:
          monitor: The run itself.
          drawn: The nodes there are, in the order the flow takes them: one per agent, or one
            per session where asked with True.
          setup: The flow set up to run, what it calls each agent it drives, what each of
            them runs, and what it was set up with.
          reading: Which view the log was on, so the graph can say so.
          board: What the flow and whoever is at the prompt both write on, or None on a run
            whose flow does not talk to the person.
          outworlders: The roles of the run that are the person, each of which is a view of
            its own.
          sessions: Whether to open on a node per session rather than per agent.
          turned: Told which of the two `ctrl+t` turned it to, so the next time the monitor
            opens it opens the way it was left.
        """
        super().__init__()
        self._monitoring = monitor
        self._boxing = drawn
        self._setup = setup
        self._reading = reading
        self._boarding = board
        self._outworlding = outworlders
        self._turned = turned
        self._boxes: list[Drawn] = []
        #: Whether a node is a session rather than an agent, which `ctrl+t` turns.
        self._sessions = sessions
        #: The last thing the interface said while this was up, where the log would have
        #: shown it: under the graph, until the next one.
        self._said = ""
        #: Which row the cursor is on, by node: the rows are put up again twice a second,
        #: and a row number would move under it as the flow opens and drops agents. The
        #: first node, which is every agent's log, to begin with.
        self._was = EVERY
        #: The rows as they were last drawn, by id and as markup. A clock in a box moves
        #: every second, so something changes on nearly every redraw -- and a list cleared
        #: and rebuilt that often is one that loses the click somebody is making on it and
        #: jumps back to the top under anybody scrolling. So the rows that changed are put
        #: back where they were, and the list is only built again when the run grows a node.
        self._ids: list[str] = []
        self._shown: list[str] = []

    def compose(self) -> ComposeResult:
        """The graph, what it cannot say, and the log's own prompt and status line under it."""
        # Here rather than at the top: the interface imports this screen to open it.
        from .app import _YOURS, Editor

        yield OptionList(id="graph")
        yield Static(id="under")
        yield Choices(id="offers")
        yield Static(id="rule-above", classes="rule")
        # Built whole rather than in a `with`: that reads the app composing from a context
        # the caller of `push_screen` may not have set, and an empty row is no prompt.
        yield Horizontal(
            Static(_YOURS, id="caret"),
            Editor(id="editor", show_line_numbers=False),
            id="prompt",
        )
        yield Static(id="rule-below", classes="rule")
        yield Static(id="status")

    def on_mount(self) -> None:
        """Draws the run, keeps drawing it, and gives the prompt the keys."""
        # The prompt is the only thing to type at, so it is the only thing that takes focus:
        # the graph is clicked and walked with the arrows without ever holding it.
        for elsewhere in self.query("#graph, #offers"):
            elsewhere.can_focus = False
        self._fill()
        self.set_interval(_LIVE, self._fill)
        # Once the prompt is there: what it sits in is mounted after this screen is.
        self.call_after_refresh(lambda: self.query_one("#editor", TextArea).focus())

    def _typed(self) -> str:
        """What is typed at the prompt under the graph, which is nothing before it is up."""
        held = self.query("#editor").results(TextArea)
        return next((one.text for one in held), "")

    def says(self, said: str) -> None:
        """Shows a line the interface said, where the log would have put it.

        Args:
          said: What it said, as markup. Its first line only: under the graph is not a
            transcript, and a paragraph there pushes the prompt off the screen.
        """
        self._said = said.split("\n", 1)[0]
        if self.is_mounted:
            self._fill()

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002 -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of the graph's keys is the graph's right now.

        Every one but `ctrl+t` is the prompt's while anything is typed or offered: an arrow
        walks a line or the offers, and enter sends it. Refused here, the key goes on to the
        prompt rather than being swallowed.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it.
        """
        if action == "turn":
            return True
        offering = any(
            one.has_class("offering") for one in self.query("#offers").results(OptionList)
        )
        return not (self._typed() or offering)

    def action_step(self, by: int) -> None:
        """Moves the cursor to the next node that way, past whatever is not one.

        Args:
          by: Which way: -1 up and 1 down.
        """
        listing = self.query_one("#graph", OptionList)
        if by < 0:
            listing.action_cursor_up()
        else:
            listing.action_cursor_down()
        self._fill()

    def action_open(self) -> None:
        """Reads the node under the cursor, or writes the line of the board it is on."""
        listing = self.query_one("#graph", OptionList)
        if listing.highlighted is not None:
            self._took(
                str(listing.get_option_at_index(listing.highlighted).id or EVERY)
            )

    def action_back(self) -> None:
        """Goes back to the log that was being read, which is what `→` is."""
        self.dismiss(None)

    def action_turn(self) -> None:
        """Draws a node per session where it drew one per agent, and the other way round."""
        self._sessions = not self._sessions
        self._turned(self._sessions)
        self._ids = []  # every node is another node now, so the list is put up again
        self._fill()

    def _fill(self) -> None:
        """Draws the run as it stands, keeping the cursor on the node it was on.

        Drawn again rather than adjusted, because everything in it moves: an agent starts a
        turn, a handover happens, a clock ticks. The cursor is held by node rather than by
        row so that it stays on the same box while that happens -- and, across `ctrl+t`, on
        the agent a session is of or the first session of the agent it was on.
        """
        listing = self.query_one("#graph", OptionList)
        at = listing.highlighted
        if self._ids and at is not None and 0 <= at < listing.option_count:
            self._was = str(listing.get_option_at_index(at).id or EVERY)
        self._boxes = list(self._boxing(self._sessions))
        monitor = self._monitoring()
        shape = monitor.shape(sessions=self._sessions)
        rows = self._rows(monitor, shape)
        ids = [one.who for one in rows]
        if ids != self._ids:
            role = self._was.partition("/")[0]
            landed = next(
                (one for one, who in enumerate(ids) if who == self._was),
                next(
                    (
                        one
                        for one, row in enumerate(rows)
                        if row.landing and row.who and row.who.partition("/")[0] == role
                    ),
                    0,
                ),
            )
            if ids[landed] != self._was:
                # Moved to another node, so the markers are drawn against that one.
                self._was = ids[landed]
                rows = self._rows(monitor, shape)
            self._ids, self._shown = ids, [one.said for one in rows]
            listing.clear_options()
            listing.add_options(
                [Option(one.said, id=one.who, disabled=not one.landing) for one in rows]
            )
            listing.highlighted = landed
        else:
            said = [one.said for one in rows]
            # The same rows saying something else, which is what a clock ticking comes to.
            # Put back one at a time so that the list itself never moves: a picture somebody
            # is watching must not scroll out from under them twice a second.
            for one, (was, now) in enumerate(zip(self._shown, said, strict=True)):
                if was != now:
                    listing.replace_option_prompt_at_index(one, now)
            self._shown = said
        self._says(monitor, shape)
        self._status()

    def _rows(self, monitor: Monitor, shape: Shape) -> list[_Row]:
        """Every row of the graph, top to bottom, drawn against where the cursor is now.

        Args:
          monitor: The run.
          shape: The run as a graph, taken at the same moment the boxes were.

        Returns:
          The first node, the outworlders, the diagram, and the board.
        """
        return [
            self._every(monitor, shape),
            *self._outworlders(),
            *self._agents(shape),
            *self._lines(),
        ]

    def _every(self, monitor: Monitor, shape: Shape) -> _Row:
        """The first node: the log every agent is on, and the run in one line beside it.

        Args:
          monitor: The run.
          shape: The run as a graph, taken at the same moment the boxes were.

        Returns:
          The node, with how far the run has got beside it -- how many of the nodes below
          are working, how many turns they have taken between them, and how long it has all
          been going.
        """
        working = sum(1 for one in self._boxes if one.working)
        over = (monitor.until or time.monotonic()) - monitor.began
        turns = sum(shape.turns.values())
        return _Row(
            EVERY,
            f"{_marked(here=self._was == EVERY)}"
            f"[{'$secondary' if working else '$text-muted'}]▣[/] all agents"
            f"{_DOT}[$text-muted]{working} of {len(self._boxes)} working"
            f"{_DOT}{turns} turn{'' if turns == 1 else 's'}"
            f"{_DOT}{lasting(over)}[/]"
            + (f"{_DOT}[$primary]reading[/]" if self._reading() == EVERY else ""),
        )

    def _outworlders(self) -> list[_Row]:
        """A node per outworlder: the person, as each role of the run that is them.

        Returns:
          One row apiece, under the first node and above the agents: a person is not an
          agent the flow drives, and reading what the flow says to them is where they answer.
        """
        return [
            _Row(
                key,
                f"{_marked(here=self._was == key)}[$primary]◉[/] {escape(role)}"
                f"{_DOT}[$text-muted]outworlder: what the flow says to you[/]"
                + (f"{_DOT}[$primary]reading[/]" if self._reading() == key else ""),
            )
            for role in self._outworlding()
            if (key := f"{OUTWORLDER}{role}")
        ]

    def _agents(self, shape: Shape) -> list[_Row]:
        """The diagram itself, one row per node that has worked.

        Args:
          shape: The run as a graph, taken at the same moment the boxes were.

        Returns:
          A row apiece, each holding the arrows above that node's box, the box, and whatever
          it started of its own hanging under it -- and one row saying so where none has
          worked yet, since a graph of a run that has not begun is a blank page otherwise.
        """
        if not self._boxes:
            return [
                _Row(
                    _NOTHING,
                    f"{_INDENT}  [$text-muted]no agent has taken a turn yet; a box appears "
                    f"as each one does[/]",
                    landing=False,
                )
            ]
        return [
            _Row(one.who, "\n".join(block))
            for one, block in zip(
                self._boxes,
                diagram(self._boxes, shape, self.size.width, self._was),
                strict=True,
            )
        ]

    def _says(self, monitor: Monitor, shape: Shape) -> None:
        """Puts what the graph cannot say under it, which is not much, and that is the point.

        Which flows are running, what this one was set up with, the handovers no arrow could
        be drawn for, and what has been spent. Who is working, how long each has been at it,
        what each of them runs and how many turns it has taken are all in the boxes, and
        saying them again here would be two places to keep in step and one more thing between
        the graph and the eye. What the agents are is said only while none of them has
        worked, there being no boxes yet to read it off.

        Args:
          monitor: The run.
          shape: The run as a graph, taken at the same moment the boxes were.
        """
        flow, named, models, config = self._setup()
        spending = monitor.spending()
        counted = monitor.reckoning()
        # Grouped as Claude Code groups its own: what is set up, what has happened that the
        # picture has no room for, what it has cost, a blank line between one and the next.
        groups: list[list[tuple[str, list[str]]]] = [
            [
                ("Flow", _flowing(flow)),
                (
                    "Agents",
                    (reads(named, models) or ["none installed"])
                    if not self._boxes
                    else [],
                ),
                # Only what was changed: a flow of forty settings says nothing by listing
                # the ones nobody touched, and this is read to see what this run is.
                ("Set", [escape(one) for one in setting(config)]),
            ],
            [
                # Only the ones the boxes have no arrow for: the rest are drawn above.
                ("Also", elsewhere(self._boxes, shape)),
            ],
            [
                (
                    "Tokens",
                    [
                        f"{escape(spend.model):<26}{thousands(spend.tokens):>8}"
                        # Blank rather than nought for a model nobody prices: a run whose
                        # bill is not known has still cost something, and `$0.00` would say
                        # it had not.
                        f"{money(spend.dollars) if spend.dollars is not None else '':>10}"
                        # Output alone: the input of a turn is the conversation so far, sent
                        # again at every request, so a rate counting it says how long the
                        # transcript has got rather than how fast the model is writing.
                        f"   [$text-muted]{spend.rate:.0f} out/s[/]"
                        for spend in spending
                    ]
                    or ["[$text-muted]nothing spent yet[/]"],
                ),
                # Under the models rather than beside them, because it is a different
                # question: what a model cost is per model, and what a run spent its tokens
                # *on* is the run's, a cached read being the same thing whichever model made
                # it. A `+` is a figure some agent of this run does not report and which is
                # therefore a floor.
                ("Kinds", _kinds(counted)),
            ],
        ]
        lines: list[str] = []
        for group in groups:
            written = False
            for field, values in group:
                for at, value in enumerate(values):
                    # The field is named against the first of its values and the rest are
                    # left to line up under it, which is how a list reads as one field.
                    head = f"{field}:" if at == 0 else ""
                    lines.append(f"[$text-muted]{head:<{_FIELD}}[/]{value}")
                    written = True
            if written:  # a group with nothing in it is not a blank line to read past
                lines.append("")
        if self._said:
            lines.append(self._said)
        elif lines:
            lines.pop()  # the prompt's own rule is the line under the last group
        self.query_one("#under", Static).update("\n".join(lines))

    def _status(self) -> None:
        """The status line under the prompt, which is the graph's where the log's would be.

        What the log's says about the run is on the first node here, so this says which
        screen this is and how its nodes are drawn, and the keys that do something now.
        """
        from .app import _RULE

        width = self.size.width
        for ruled in self.query(".rule").results(Static):
            ruled.update(_RULE * width)
        said = f"monitor{_DOT}a node per {_BY[self._sessions]}"
        left = (
            f"[$secondary]▣[/] monitor[$text-muted]{_DOT}a node per "
            f"{_BY[self._sessions]}[/]"
        )
        if self._typed():
            keys = ["enter send", "ctrl+c clear"]
        else:
            keys = [
                "↑↓ node",
                "enter read",
                "→ back",
                f"ctrl+t by {_BY[not self._sessions]}",
                "/ commands",
            ]
        # Measured as drawn: the mark and a space ahead of the words, and the padding.
        room = width - 4 - 2 - len(said)
        while len(keys) > 1 and len(_DOT.join(keys)) > room:
            keys.pop()
        gap = room - len(_DOT.join(keys))
        self.query_one("#status", Static).update(
            left + " " * max(2, gap) + f"[$text-muted]{_DOT.join(keys)}[/]",
            layout=False,
        )

    def _lines(self) -> list[_Row]:
        """The board, as the rows under the diagram.

        Returns:
          A heading, one row per line and the row that puts one up, or nothing at all for a
          run whose flow does not talk to the person -- there being no board on one nobody
          can write to.
        """
        board = self._boarding()
        if board is None:
            return []
        rows = [
            # A row of air between the diagram and the board: they are two things about the
            # run rather than one list, and a heading pressed against a box reads as part of
            # the diagram.
            _Row(f"{_BOARDED}{_NOTHING}", "", landing=False),
            _Row(
                _BOARDED,
                f"{_INDENT}[$primary]Board[/]"
                f"{_DOT}[$text-muted]what you and the flow both write on[/]",
                landing=False,
            ),
        ]
        room = max(
            _NARROWEST, min(_WIDEST, self.size.width - len(_INDENT) - 5) - _LABEL - 6
        )
        # Cut and padded before anything is put round it, for the reason a box's lines are:
        # a bracket a name happens to hold is a bracket, and an escape of one is characters
        # that are not columns.
        rows += [
            _Row(
                f"{_ON_BOARD}{one.key}",
                f"{_marked(here=self._was == f'{_ON_BOARD}{one.key}')}"
                f"[{'$text-muted' if one.whose == FLOW else '$secondary'}]"
                f"{_ON_IT}[/] {escape(named)}{' ' * max(0, _LABEL - len(named))}"
                f"[$text-muted]{escape(_fits(one.value or one.about, room))}[/]"
                + (
                    f"{_DOT}[$text-muted]{one.whose}'s[/]"
                    if one.whose != ANYONE
                    else ""
                ),
            )
            for one in board.items()
            if (named := _fits(one.key, _LABEL))
        ]
        # And the way to put one up, as the last line of the board: enter on it is a new
        # line, as enter on any other is that line.
        rows.append(
            _Row(
                _NEW,
                f"{_marked(here=self._was == _NEW)}[$primary]+[/] "
                f"[$text-muted]a new line[/]",
            )
        )
        return rows

    @on(OptionList.OptionSelected, "#graph")
    def _clicked(self, event: OptionList.OptionSelected) -> None:
        """A click on a node means what enter on it means.

        Args:
          event: The click, as the list says it.
        """
        self._took(str(event.option.id or EVERY))

    def _took(self, named: str) -> None:
        """Reads a node, or writes a line of the board: whichever row this was.

        Args:
          named: The row's id.
        """
        if not named.startswith(_ON_BOARD):
            self.dismiss(named)
            return
        key = named.removeprefix(_ON_BOARD)
        board = self._boarding()
        held = board.held(key) if board is not None and key else None
        if held is not None and held.whose == FLOW:
            self._said = f"{escape(key)} is the flow's to change, not yours"
            self._fill()
            return
        self._writes(key)

    @work
    async def _writes(self, key: str) -> None:
        """Asks what a line is to say, and writes it down -- or takes it away, left empty.

        Args:
          key: Which line, or "" for one being put up now.
        """
        board = self._boarding()
        if board is None:
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        held = board.held(key) if key else None
        said = await showing.push_screen_wait(
            Entry(key, held.value if held is not None else "", board)
        )
        if said is None:
            return  # walked out of it, which changes nothing
        named, value = said
        try:
            if value:
                board.put(named, value, by=USER)
                self._said = f"{escape(named)} is on the board"
            elif board.held(named) is not None:
                # Written down as nothing, which is a line with nothing to say: taken off
                # rather than left up empty, there being no key of its own that does it.
                board.drop(named, by=USER)
                self._said = f"{escape(named)} is off the board"
            else:
                self._said = "nothing was written, so nothing went up"
        except (PermissionError, ValueError) as why:
            self._said = bad(escape(str(why)))
        self._ids = []  # the rows have moved, so they are put up again
        self._fill()
