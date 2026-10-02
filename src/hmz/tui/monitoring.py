"""The monitor: the run drawn across the whole screen, and the screen every log is left for.

Two screens make up the interface. The log is the transcript -- every agent's, one agent's --
and the monitor is the run itself: a node per agent that has worked, opened out to its
sessions and the environments they work in, marked as each one works, the handovers between
them as the arrows joining them, and the board under them. Drawn as a graph, or as a list
that says nothing of who handed to whom and puts whatever is working at the top. It is the
parent of the two, which is why the log is reached from it by picking what to read and why
`←` on an empty prompt comes back to it.

It is drawn with the same prompt under it as the log, because it is the same interface with the
transcript swapped for the graph: every command works here, and what the log says in its status
line and above its prompt is said here by the graph and the line under it.
"""

# The sheets' own module, split along the one screen of it that is not a sheet: the monitor
# draws with the marks they draw with and opens their entry sheet, so it reads what they keep
# to themselves. Named `monitoring` for the screen, as `monitor` is named for what it reads.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import functools
import itertools
import time
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from rich.markup import escape
from textual import events, on, work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Label, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from hmz.coganchor.agents import ANYONE, FLOW
from hmz.coganchor.prices import money

from .monitor import Shape, lasting, short, thousands
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
    named_as,
    reads,
    setting,
)
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Mapping, MutableSet, Sequence

    from pydantic import BaseModel
    from textual.app import App, ComposeResult

    from hmz.runtime.flowing import EnvRole
    from hmz.runtime.kept import Runs

    from .monitor import Counted, Monitor, Under

__all__ = [
    "EVERY",
    "OUTWORLDER",
    "BoardSeen",
    "Drawn",
    "Entry",
    "Line",
    "Monitoring",
    "Place",
    "Placed",
    "declared_places",
    "needs",
    "place_key",
]

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

#: What an environment's node is put up under, ahead of its key: a character no role and no
#: key of a session is called by, as the board's is.
_PLACE = "\x03"

#: What stands between an environment's key and the session it hangs under on the graph,
#: where one environment hangs under every session that works in it and a row apiece needs an
#: id apiece.
_AT = "\x04"

#: The row naming the columns of the list, which nothing lands on.
_COLUMNS = "\x05"

#: What an agent wears in front of its name: shut, with its sessions folded into its box, and
#: open, with them hanging under it.
_SHUT, _OPEN = "▸", "▾"

#: What an environment is drawn with: a place rather than somebody, so not a dot.
_ENV = "▤"

#: How far across the graph a click opens or shuts an agent rather than only picking it out:
#: the gutter and the side of a box, which is where its `▸` is.
_FOLDS = 8

#: What the two ways of drawing the run are called, on the switch above it and the status line.
_VIEWS = {False: "graph", True: "list"}

#: The mark against a line of the board. One mark, one kind of thing: whose a line is is said
#: in words beside it and in the colour it is drawn, which is what a reader actually reads --
#: a second glyph would be a second thing to learn for the same fact.
_ON_IT = "◈"


def _flowing(started: str, calls: Sequence[Mapping[str, Any]]) -> list[str]:
    """Which flow is running, and inside which, for the row that names one.

    A flow may reach for another by name and run it, so the flow a run is in is not always
    the flow that was started -- and a sheet that named only the one somebody chose would be
    a sheet that stopped being true the moment a flow called another.

    Args:
      started: The flow that was chosen, which is what this says with nothing running.
      calls: The flow calls going, oldest first, as the run says them.

    Returns:
      One line apiece, the one that was started first and whatever it called under it, each
      with how long it has been going; and just the one that is set up to run where nothing
      is running.
    """
    if not calls:
        return [escape(started)]
    return [
        f"{'  ' * (one['depth'] - 1)}{'▸ ' if one['depth'] > 1 else ''}"
        f"{escape(named_as(one['ref']))}"
        f"   [$text-muted]{time.monotonic() - one['since']:.0f}s[/]"
        for one in calls
    ]


class Line(NamedTuple):
    """One line of the board a flow and a person share, as the runs say it.

    Attributes:
      key: What it is called.
      value: What it says, or "" for one that says only what it is about.
      about: What it is for, as whoever put it up said.
      whose: Who may change it: the flow's, the person's, or anybody's.
      by: Who put it up last.
      at: When, as the clock of the machine the runs are on reads.
    """

    key: str
    value: str = ""
    about: str = ""
    whose: str = ANYONE
    by: str = ""
    at: float = 0.0


class BoardSeen:
    """The board a flow and a person share, as the runs last said it.

    What is on it is read off what the runs say, since the board itself is theirs; what the
    person writes on it is asked of them, and comes back as the board they say next. A line
    the flow owns is refused here before it is asked, as it would be there.
    """

    def __init__(
        self,
        items: Sequence[Mapping[str, Any]],
        asks: Callable[[str, str], None],
    ) -> None:
        """Holds what is on the board, and how to ask for it to change.

        Args:
          items: Its lines, as the runs said them.
          asks: What asks the runs to put a line up -- or take it off, said as nothing.
        """
        self._lines = [
            Line(**{key: one[key] for key in Line._fields if key in one})
            for one in items
        ]
        self._asks = asks

    def items(self) -> list[Line]:
        """Every line on it, in the order the runs said them."""
        return list(self._lines)

    def held(self, key: str) -> Line | None:
        """The line of that name, or None where there is none."""
        return next((one for one in self._lines if one.key == key), None)

    def put(self, key: str, value: str) -> None:
        """Asks for a line to say something, putting it up where it is not there yet."""
        self._asks(key, value)

    def drop(self, key: str) -> None:
        """Asks for a line to come off."""
        self._asks(key, "")


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
      of: For a session, the agent it is one of, which is what it hangs under; "" for an
        agent.
      env: For a session, the key of the environment it works in, or "" where nothing said.
    """

    who: str
    named: str = ""
    runs: str = ""
    working: bool = False
    reading: bool = False
    unread: bool = False
    of: str = ""
    env: str = ""


class Placed(NamedTuple):
    """One environment of a run -- a workdir on a machine -- as the monitor draws it.

    Not somebody: nothing is said to one and it keeps no transcript. It hangs under the
    sessions that work in it, and is opened for what it is rather than read.

    Attributes:
      key: What it is known by: its role, and where it is.
      role: The environment role of the flow it fills, or "" where nothing said.
      kind: Which kind of machine: `local`, `ssh`, `docker` or `swarm`.
      target: Which one of that kind -- the ssh host, the docker runtime -- or "" for this
        machine.
      workdir: Where on it the sessions work.
      given: What it was set up as, as `-e` spells it, or "" for one nobody set up here.
      anchored: Whether the agents working in it run on this machine with what they run
        landing on that one -- which is how every agent reaches a machine that is not this.
      grants: The capabilities the flow declared for the role, by name.
      needs: What the flow asks of the machine, in words: CPUs, memory, GPUs.
      image: What a container for it is started from, or "" for the provider's own.
      sessions: The sessions working in it, by key, in the order they opened.
      harness: Where the run put its agents' harnesses, as `-H` spells it, or "" where the
        run did not say.
      harnesses: Where each of those sessions' harness went, in the same order, as the run
        said it as the session opened: `local`, `env`, `standalone:<target>`, or "" for one
        working here with nothing between.
    """

    key: str
    role: str
    kind: str
    target: str = ""
    workdir: str = ""
    given: str = ""
    anchored: bool = False
    grants: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    image: str = ""
    sessions: tuple[str, ...] = ()
    harness: str = ""
    harnesses: tuple[str, ...] = ()


def _where(place: Placed) -> str:
    """Where an environment is, on one line: what kind of machine, which one, where on it."""
    return _DOT.join(part for part in (place.kind, place.target, place.workdir) if part)


#: What `-H` calls a harness on this machine, which is where a session working here has one.
_LOCAL = "local"


def _harnessed(place: Placed) -> str:
    """Where the harnesses of an environment's sessions went, said as its page says it.

    As the run found it rather than as the environment's kind suggests: `-H` puts a harness
    here, on the environment's machine or on one of its own, and adaptive may put two roles'
    harnesses in two places. What `-H` was comes first, where the run said, and then what it
    came to -- once where every session went the same way, and session by session where not.

    Args:
      place: The environment.

    Returns:
      The row, as `adaptive → env: on this environment's machine, with the CLI there`.
    """
    # By what each went as, a session working here being one whose harness is here too.
    went: dict[str, list[str]] = {}
    for key, where in itertools.zip_longest(
        place.sessions, place.harnesses, fillvalue=""
    ):
        if key:
            went.setdefault(where or _LOCAL, []).append(key)
    set_to = f"{place.harness} → " if place.harness else ""
    if len(went) > 1:
        return set_to + _DOT.join(
            f"{where} for {', '.join(keys)}" for where, keys in went.items()
        )
    where = next(iter(went), _LOCAL)
    kind, _, on = where.partition(":")
    said = {
        _LOCAL: "on this machine; what it runs lands here"
        if place.anchored
        else "on this machine, in this workdir",
        "env": "on this environment's machine, with the CLI installed there",
    }.get(kind, f"on {on}, reaching this environment through the anchor")
    return f"{set_to}{kind}: {said}"


def place_key(placed: Mapping[str, Any]) -> str:
    """What one environment is known by, from what the run said of a session opened in it.

    Its role and where it is, rather than its role alone: a worktree derived from an
    environment fills the same role somewhere else, and it is somewhere else.

    Args:
      placed: What the run said: `role`, `kind`, `target` and `workdir`.

    Returns:
      The key, the same for every session working in the same place.
    """
    return "\x1f".join(
        str(placed.get(part) or "") for part in ("role", "kind", "target", "workdir")
    )


@functools.lru_cache(maxsize=8)
def declared_places(flow: str) -> tuple[EnvRole, ...]:
    """Every environment role a flow declares, the workspace it runs in among them.

    Read once per flow, since reading one means loading it, and this is asked each time the
    graph is drawn.

    Args:
      flow: The flow, as it was named.

    Returns:
      The roles, and none for a flow that will not load -- whose environments are drawn for
      where they are, with nothing said of what the flow declared of them.
    """
    from hmz.runtime.flowing import resolved

    try:
        return tuple(resolved(flow).describe().envs)
    except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
        return ()


#: Bytes in the unit memory is said in.
_GIB = 1 << 30


def needs(role: EnvRole) -> tuple[str, ...]:
    """What an environment role asks of its machine, in words, for the page it opens to.

    Args:
      role: The role, as the flow declares it.

    Returns:
      One phrase per thing it asks for, and nothing for a role that asks nothing beyond a CPU.
    """
    return tuple(
        said
        for said in (
            f"{role.cpu_count} CPUs" if role.cpu_count > 1 else "",
            f"{role.memory / _GIB:g} GiB memory" if role.memory else "",
            f"{role.gpu_count} GPU{'' if role.gpu_count == 1 else 's'}"
            if role.gpu_count
            else "",
            f"{role.gpu_memory / _GIB:g} GiB per GPU" if role.gpu_memory else "",
        )
        if said
    )


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


def _across(width: int) -> int:
    """How wide a box is drawn in a graph this wide, which is how wide the rows under it are."""
    return max(_NARROWEST, min(_WIDEST, width - len(_INDENT) - 5))


def _clock(shape: Shape, who: str, *, working: bool) -> str:
    """How long a node has been at what it is doing, as the right of its row says it."""
    clock = lasting(shape.since.get(who, 0.0))
    return clock if working else f"{_IDLED} {clock}"


def _flagged(one: Drawn) -> tuple[str, str]:
    """What a node says about being read -- `reading`, `unread` or nothing -- and its colour."""
    if one.reading:
        return "reading", "$primary"
    if one.unread:
        return "unread", "$secondary"
    return "", "$text-muted"


def _spent(shape: Shape, who: str) -> str:
    """How many tokens a node has spent, in words, or "" for none reported yet."""
    used = shape.used.get(who, 0)
    return f"{thousands(used)} tokens" if used else ""


def diagram(
    drawn: Sequence[Drawn],
    shape: Shape,
    width: int,
    here: str = "",
    *,
    opened: Collection[str] = (),
    sessions: Mapping[str, int] | None = None,
    places: Mapping[str, Sequence[Placed]] | None = None,
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
      opened: The agents opened out to their sessions, whose `▸` is turned down and whose
        subagents hang under their sessions rather than under the box.
      sessions: How many sessions each agent has worked in, said on its box where it is more
        than one -- which is what opening it out would show.
      places: The environments each agent's sessions work in, said on a line of the box.

    Returns:
      One block of lines per agent, in the same order: the arrows above it and then its box,
      so that a list of blocks is the diagram from top to bottom.
    """
    across = _across(width)
    sessions = sessions or {}
    places = places or {}
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
        held = sessions.get(one.who, 0)
        tail, tailing = _flagged(one)
        said = [
            _Said(
                "$secondary" if one.working else "$foreground",
                f"{_OPEN if one.who in opened else _SHUT} "
                f"{_WORKING if one.working else _IDLE} "
                # What the flow calls it, or the id cut down where it calls it nothing: one
                # name, since two for the same thing is one said twice.
                + (one.named or short(one.who)),
                _clock(shape, one.who, working=one.working),
                "$secondary" if one.working else "$text-muted",
            ),
            _Said(
                "$text-muted",
                _DOT.join(
                    part
                    for part in (
                        one.runs,
                        f"{taken} turn{'' if taken == 1 else 's'}" if taken else "",
                        f"{held} sessions" if held > 1 else "",
                        _spent(shape, one.who),
                    )
                    if part
                ),
                tail,
                tailing,
            ),
        ]
        if placed := places.get(one.who):
            # Where its sessions work, named rather than spelled out: the whole of where one
            # is -- the machine, the directory -- is on its own row, opened out.
            said.append(
                _Said(
                    "$text-muted",
                    _DOT.join(
                        f"{_ENV} {at.role} {at.kind}"
                        if at.role
                        else f"{_ENV} {at.kind}"
                        for at in placed
                    ),
                )
            )
        block = (
            arrows
            + _boxed(said, across, here=one.who == here)
            # Under the box, where its sessions do not hang under it: opened out, each
            # subagent is under the session that started it.
            + ([] if one.who in opened else fleet(shape.under.get(one.who, ()), across))
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


def session_row(
    one: Drawn, shape: Shape, width: int, *, here: bool = False, last: bool = False
) -> str:
    """One session of an agent opened out, hanging under its box, with its subagents under it.

    A row rather than a box: a session is one of the things its agent is doing, so it is drawn
    as a branch of that agent -- and it is still somebody, with a transcript to read and a
    turn that may be open, so it says so the way a box does, its clock down the same column.

    Args:
      one: The session.
      shape: The run a session at a time.
      width: How much room there is across.
      here: Whether the cursor is on it.
      last: Whether it is the last of its agent's, which ends the branch it hangs on.

    Returns:
      The row, as markup, with a line under it for each agent it started of its own.
    """
    across = _across(width)
    taken = shape.turns.get(one.who, 0)
    flag, flagging = _flagged(one)
    colour = "$secondary" if one.working else "$foreground"
    clock = _clock(shape, one.who, working=one.working)
    # The branch and the mark are six columns ahead of the words, and the clock ends where
    # the clock of the box above it does, a side and a space short of the box's width, so
    # the two read down one column.
    room = across - 8
    tail = _fits(clock, room)
    flagged = _fits(flag, room - len(tail) - 3) if flag else ""
    ahead = len(tail) + (len(flagged) + len(_DOT) if flagged else 0)
    head = _fits(
        _DOT.join(
            part
            for part in (
                one.named.rpartition(_DOT)[2] or short(one.who),
                f"{taken} turn{'' if taken == 1 else 's'}" if taken else "",
                _spent(shape, one.who),
            )
            if part
        ),
        room - ahead - 1,
    )
    pad = " " * max(1, room - len(head) - ahead)
    lines = [
        f"{_marked(here=here)}[$text-muted]  {_LAST_UNDER if last else _UNDER}[/]"
        f"[{colour}]{_WORKING if one.working else _IDLE}[/] [{colour}]{escape(head)}[/]"
        f"{pad}"
        + (f"[{flagging}]{escape(flagged)}[/][$text-muted]{_DOT}[/]" if flagged else "")
        + f"[{'$secondary' if one.working else '$text-muted'}]{escape(tail)}[/]"
    ]
    stem = f"{_INDENT}[$text-muted]  {' ' if last else _BOX[5]} [/]"
    lines += [stem + line for line in fleet(shape.under.get(one.who, ()), across - 4)]
    return "\n".join(lines)


def place_row(
    place: Placed, width: int, *, here: bool = False, last: bool = False
) -> str:
    """The environment a session works in, on the row under that session.

    Args:
      place: The environment.
      width: How much room there is across.
      here: Whether the cursor is on it.
      last: Whether the session above is the last of its agent's, so that the branch the
        sessions hang on stops rather than running on past it.

    Returns:
      The row, as markup: which role of the flow it fills, and where it is.
    """
    room = _across(width) - 6
    said = _fits(_DOT.join(part for part in (place.role, _where(place)) if part), room)
    return (
        f"{_marked(here=here)}[$text-muted]  {' ' if last else _BOX[5]}   {_ENV}[/] "
        f"[$text-muted]{escape(said)}[/]"
    )


#: How wide the columns of the list are: the name, the turns, the clock and the tokens. What
#: a node runs, or where an environment is, has whatever is left, since it is the one of
#: them that is only read when it is looked for.
_NAMED, _TURNS, _CLOCK, _TOKENS = 24, 11, 12, 10


def _what_room(width: int) -> int:
    """How wide the list's column of what a node runs is, which is what gives in a narrow one."""
    rest = len(_INDENT) + 4 + _NAMED + _TURNS + _CLOCK + _TOKENS + 4
    return max(0, min(30, width - rest))


def columns(width: int) -> str:
    """The row naming the columns of the list, which nothing lands on."""
    what = _what_room(width)
    return (
        f"{_INDENT}    [$text-muted]{'node':<{_NAMED}}{'runs · where':<{what}}"
        f"{'turns':>{_TURNS}}{'time':>{_CLOCK}}{'tokens':>{_TOKENS}}[/]"
    )


def listed_row(
    width: int,
    *,
    mark: str,
    named: str,
    what: str,
    turns: str,
    clock: str,
    tokens: str,
    working: bool,
    here: bool = False,
    fold: str = "",
    flag: tuple[str, str] = ("", "$text-muted"),
) -> str:
    """One node of the list, in its columns.

    Args:
      width: How much room there is across.
      mark: What it wears: `●` or `○` for somebody, `▤` for an environment.
      named: What it is called.
      what: What it runs, or where it is.
      turns: How many turns it has taken, or how many sessions work in it.
      clock: How long it has been at what it is doing.
      tokens: What it has spent.
      working: Whether it is working, which is what colours it.
      here: Whether the cursor is on it.
      fold: `▸` or `▾` for an agent that opens out, and "" for anything else.
      flag: `reading` or `unread`, and the colour to say it in, after the name.

    Returns:
      The row, as markup, its columns padded before anything is put round them.
    """
    room = _what_room(width)
    said, flagging = flag
    name = _fits(named, _NAMED - 1 - (len(said) + 1 if said else 0))
    colour = "$secondary" if working else "$foreground"
    lead = (
        f"[{colour}]{escape(name)}[/]"
        + (f" [{flagging}]{escape(said)}[/]" if said else "")
        + " " * max(1, _NAMED - len(name) - (len(said) + 1 if said else 0))
    )
    return (
        f"{_marked(here=here)}[$text-muted]{fold or ' '}[/] [{colour}]{mark}[/] {lead}"
        f"[$text-muted]{escape(f'{_fits(what, room - 1):<{room}}{turns:>{_TURNS}}')}[/]"
        f"[{'$secondary' if working else '$text-muted'}]"
        f"{escape(f'{clock:>{_CLOCK}}')}[/]"
        f"[$text-muted]{escape(f'{tokens:>{_TOKENS}}')}[/]"
    )


def floated[T](nodes: Sequence[tuple[bool, T]]) -> list[T]:
    """Nodes in the order the list puts them: whatever is working first, the rest after.

    Stable, so that nothing moves but what started or stopped: a list whose rows shuffled
    among themselves each time a clock ticked would be one nobody could keep their place in.

    Args:
      nodes: Each node, as whether it is working and the node, in the order they come.

    Returns:
      The nodes, the working ones first, each half in the order it was given in.
    """
    return [node for working, node in nodes if working] + [
        node for working, node in nodes if not working
    ]


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
        return ["[$text-muted]no tokens used yet[/]"]
    rows = [
        f"{escape(one.kind):<26}{thousands(one.tokens):>8}{'' if one.whole else '+'}"
        for one in counted
    ]
    if not all(one.whole for one in counted):
        rows.append("[$text-muted]+ is a minimum: not all agents report this kind[/]")
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

    def __init__(self, key: str, value: str, board: BoardSeen) -> None:
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
            "Board entry" if self._naming else f"{escape(self._key)}"
        )
        self.query_one("#about", Label).update(
            "Shared by you and the flow. Neither waits for the other."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts up what has been typed, which is the whole of what this sheet shows."""
        listing = self.query_one("#choices", OptionList)
        asked = "name" if self._naming else "value"
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
            Key("backspace", "delete"),
            Key(
                "enter",
                "continue to value" if self._naming else "save, or remove if empty",
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
            self._said = "a board entry needs a name"
            self._fill()
            return
        held = self._board.held(named)
        if held is not None and held.whose == FLOW:
            self._said = f"{escape(named)} can only be changed by the flow"
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


class Place(Sheet[str]):
    """One environment of a run, opened: what it is, what the flow may do in it, who works there.

    A reading rather than a question. An environment keeps no transcript and nothing is said
    to it, so what opening one is for is what the graph has no room for -- the whole of where
    it is, what the flow declared of it, and which sessions work in it -- and the one thing
    to do from here is read one of those. Kept live while it is up, as the graph under it is.
    """

    def __init__(
        self,
        key: str,
        places: Callable[[], Sequence[Placed]],
        sessions: Callable[[], Sequence[Drawn]],
    ) -> None:
        """Opens one environment.

        Args:
          key: Which, by its key.
          places: The environments of the run, asked afresh each time this is drawn.
          sessions: Every session of the run that has worked, asked afresh the same way.
        """
        super().__init__()
        self._key = key
        self._places = places
        self._sessions = sessions

    def _ask(self) -> None:
        """Says which environment this is, and keeps saying how it stands."""
        self._fill()
        self.set_interval(_LIVE, self._fill)
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts up what it is, and under that the sessions working in it."""
        place = next((one for one in self._places() if one.key == self._key), None)
        listing = self.query_one("#choices", OptionList)
        if place is None:
            # The run it was of has gone, and a new run's environments are not this one.
            self.query_one("#about", Label).update(
                "This environment is not in the run."
            )
            listing.set_options([])
            self._footed(Key("esc", "back"))
            return
        self.query_one("#asked", Label).update(escape(place.role or place.kind))
        self.query_one("#about", Label).update(
            "An environment of the run: where its sessions work."
        )
        by = {one.who: one for one in self._sessions()}
        using = [by.get(key, Drawn(key)) for key in place.sessions]
        working = sum(one.working for one in using)
        facts = [
            ("kind", place.kind.upper()),
            ("target", place.target or "this machine"),
            ("workdir", place.workdir),
            ("set up as", place.given),
            ("image", place.image),
            ("grants", ", ".join(place.grants) or "nothing beyond running in it"),
            ("needs", _DOT.join(place.needs)),
            ("harness", _harnessed(place)),
            (
                "status",
                (
                    f"{working} of {len(using)} session{'' if len(using) == 1 else 's'} "
                    "working"
                ),
            ),
        ]
        at = self.under()
        landing = at if at in place.sessions else next(iter(place.sessions), "")
        rows = [
            Option(
                f"{_INDENT}  [$text-muted]{field:<{_FIELD}}[/]{escape(value)}",
                disabled=True,
            )
            for field, value in facts
            if value
        ]
        rows.append(Option(f"{_INDENT}  [$primary]Sessions[/]", disabled=True))
        rows += [
            Option(
                f"{_marked(here=one.who == landing)}  "
                f"[{'$secondary' if one.working else '$text-muted'}]"
                f"{_WORKING if one.working else _IDLE}[/] "
                f"{escape(one.named or one.who)}"
                + (f"{_DOT}[$text-muted]{escape(one.runs)}[/]" if one.runs else ""),
                id=f"={one.who}",
            )
            for one in using
        ]
        listing.set_options(rows)
        if landing:
            listing.highlighted = len(rows) - len(using) + place.sessions.index(landing)
            self._drawn = listing.highlighted
        self._footed(Key("enter", "read session"), Key("esc", "back"))

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Reads the session picked, enter or a click, which leaves the monitor for its log.

        Args:
          event: What was picked.
        """
        self.dismiss(str(event.option.id or "").removeprefix("="))


#: What the row that puts a new line on the board is put up under: the board's own mark with
#: no name after it, there being no line yet.
_NEW = _ON_BOARD


class _Graph(OptionList):
    """The graph's list, which says where across it was clicked as well as on which row.

    Because a click on an agent means two things. On its left edge, where its `▸` is, or on
    one the cursor is already on, it opens the agent out to its sessions or shuts it again;
    anywhere else it picks the agent out, and a second click straight after reads it.
    """

    #: Where across the last click landed, how many clicks in a row it was, and which row
    #: the cursor was on before it, or None before any.
    clicked: tuple[int, int, int | None] | None = None

    async def _on_click(self, event: events.Click) -> None:
        """Notes where the click landed, before the list picks the row as it would.

        Only notes it: textual hands the click to the list's own handler after this one, as
        it hands every event to each class that has a handler for it, and a second pick of
        the row would be a second click.

        Args:
          event: The click.
        """
        at = event.get_content_offset(self)
        self.clicked = (at.x if at is not None else 0, event.chain, self.highlighted)


class _Switch(Static):
    """One half of the switch above the graph: the graph, or the list. Clicked, it is drawn."""

    def __init__(self, *, listed: bool) -> None:
        """Makes one half.

        Args:
          listed: Whether it is the list's half.
        """
        super().__init__(_VIEWS[listed], id=f"as-{_VIEWS[listed]}")
        self.listed = listed

    def on_click(self) -> None:
        """Draws the run the way this half says."""
        screen = self.screen
        if isinstance(screen, Monitoring):
            screen.view(listed=self.listed)


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
    """The run, drawn full screen: a node per agent, opened out to its sessions, and the board.

    The graph is the screen. What somebody comes here for is the shape of the run and where it
    has got to -- which agent is thinking, how long it has been thinking, which way the work
    went last -- and all of that is in the picture. So the picture takes the height, and what
    is written under it is only what a picture cannot say: the flows running, what this one
    was set up with, the handovers no arrow could be drawn for, and what has been spent.

    An agent is one node however many sessions it opens, and opens out to them with space or
    a click: each session a branch under its box, and under each the environment it works
    in, which opens for what it is. Or the run is drawn as a list, which says nothing of who
    handed to whom and puts whatever is working at the top -- the question a run of twelve
    agents is watched to answer, and one a picture of twelve boxes answers slowly.

    It is where a log is picked to be read. The first node is every agent's log, selected
    when this opens, so enter reads the run whole; each node under it reads its own; `→` goes
    back to whichever was read last. A node stays for the rest of the run, working or not.

    And the prompt is under it, the same prompt as the log's: every command works here, and a
    line typed goes where it would have gone from the log. The arrows, space and enter are
    the graph's only while nothing is typed, since a line being written needs them back.

    Redrawn twice a second, since what it is about moves without anybody touching it. Answers
    with the view to read, or None for the one that was being read.
    """

    DEFAULT_CSS = """
    #views { height: 1; padding: 0 2; background: $surface; }
    #views > Static { width: auto; padding: 0 1; color: $text-muted; }
    #views > Static.on { color: $primary; text-style: bold reverse; }
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
        Binding("enter", "open", "open", show=False, priority=True),
        Binding("space", "fold", "sessions", show=False, priority=True),
        Binding("right", "back", "back to the log", show=False, priority=True),
        Binding("ctrl+t", "turn", "graph or list", show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        monitor: Callable[[], Monitor],
        drawn: Callable[[], Sequence[Drawn]],
        setup: Callable[[], tuple[str, tuple[str, ...], list[Runs], BaseModel | None]],
        reading: Callable[[], str] = lambda: EVERY,
        board: Callable[[], BoardSeen | None] = lambda: None,
        outworlders: Callable[[], Sequence[str]] = tuple,
        calls: Callable[[], Sequence[Mapping[str, Any]]] = tuple,
        whose: Callable[[str], str] = lambda _: "",
        frontends: Callable[[], Sequence[str]] = tuple,
        sessions: Callable[[], Sequence[Drawn]] = tuple,
        places: Callable[[], Sequence[Placed]] = tuple,
        listed: bool = False,
        opened: MutableSet[str] | None = None,
        turned: Callable[[bool], None] = lambda _: None,
    ) -> None:
        """Watches the run, asking about it afresh each time it is drawn.

        Asked rather than given, every one of them, because the answers move while this is
        up: an agent appears as its first turn starts, a run started from the prompt here is a
        new run with a new monitor, and a command typed here may change what is set up.

        Args:
          monitor: The run itself.
          drawn: The agents there are, in the order the flow takes them.
          setup: The flow set up to run, what it calls each agent it drives, what each of
            them runs, and what it was set up with.
          reading: Which view the log was on, so the graph can say so.
          board: What the flow and whoever is at the prompt both write on, or None on a run
            whose flow does not talk to the person.
          outworlders: The roles of the run that are the person, each of which is a view of
            its own.
          calls: The flow calls going, oldest first: the flow started and whatever it called.
          whose: Who holds an outworlder role to answer: `yours`, `<name>'s`, or "".
          frontends: Every frontend reading the runs, by name, this one said to be.
          sessions: The sessions there are, each saying whose it is and where it works.
          places: The environments the run's sessions work in.
          listed: Whether to open drawn as a list rather than as a graph.
          opened: The agents opened out to their sessions. Held by whoever opens this and
            changed where it stands, so the monitor opens again the way it was left.
          turned: Told which of the two `ctrl+t` turned it to, for the same reason.
        """
        super().__init__()
        self._monitoring = monitor
        self._boxing = drawn
        self._setup = setup
        self._reading = reading
        self._boarding = board
        self._outworlding = outworlders
        self._calling = calls
        self._whose = whose
        self._frontends = frontends
        self._turned = turned
        self._placing = places
        self._branching = sessions
        self._boxes: list[Drawn] = []
        #: Every session that has worked, and by key, as the graph was last drawn.
        self._sessions: list[Drawn] = []
        self._keyed: dict[str, Drawn] = {}
        #: The environments, by key, as the graph was last drawn.
        self._places: dict[str, Placed] = {}
        #: The run a session at a time, taken where the run an agent at a time was.
        self._by_session = Shape({}, frozenset(), {})
        #: Whether this has answered already, and is on its way down to a log.
        self._left = False
        #: Whether the run is drawn as a list rather than as a graph, which `ctrl+t` turns.
        self._listed = listed
        #: The agents opened out, which space and a click change.
        self._opened: MutableSet[str] = set() if opened is None else opened
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

        # A switch across the top, the way it is drawn now lit: clicked, as `ctrl+t` turns it.
        yield Horizontal(_Switch(listed=False), _Switch(listed=True), id="views")
        yield _Graph(id="graph")
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
            one.has_class("offering")
            for one in self.query("#offers").results(OptionList)
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
        self._leaves(None)

    def _leaves(self, reading: str | None) -> None:
        """Goes down to a log, once however many times it is asked for.

        A double click is two clicks, and the second of them may land before the first has
        taken this screen away: a second answer to it would pop whatever is under it.

        Args:
          reading: The view to read, or None for the one that was being read.
        """
        if self._left:
            return
        self._left = True
        self.dismiss(reading)

    def action_turn(self) -> None:
        """Draws the run as a list where it was a graph, and the other way round."""
        self.view(listed=not self._listed)

    def view(self, *, listed: bool) -> None:
        """Draws the run as a list or as a graph, whichever it was not drawn as already.

        Args:
          listed: Whether as a list.
        """
        if listed == self._listed:
            return
        self._listed = listed
        self._turned(listed)
        self._ids = []  # every row is another row now, so the list is put up again
        self._fill()

    def action_fold(self) -> None:
        """Opens the agent under the cursor out to its sessions, or shuts it again.

        On one of its sessions, or the environment under one, it shuts the agent they hang
        under and puts the cursor back on it: the way back up from a branch is the key that
        went down it.
        """
        listing = self.query_one("#graph", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return
        who = str(listing.get_option_at_index(at).id or "")
        if any(one.who == who for one in self._boxes):
            self._folds(who)
            return
        owner = self._owner(who)
        if owner != who and owner in self._opened:
            self._was = owner
            self._folds(owner)

    def _folds(self, agent: str) -> None:
        """Opens one agent out, or shuts it, and draws it so.

        Args:
          agent: Which.
        """
        if agent in self._opened:
            self._opened.discard(agent)
        else:
            self._opened.add(agent)
        self._fill()

    def _owner(self, who: str) -> str:
        """The agent a row hangs under: a session's, an environment's session's, or itself.

        Args:
          who: The row's id.

        Returns:
          The agent, or the id as it was for a row that hangs under nobody.
        """
        if who.startswith(_PLACE):
            who = who.partition(_AT)[2] or who
        held = self._keyed.get(who)
        return held.of if held is not None and held.of else who

    def _fill(self) -> None:
        """Draws the run as it stands, keeping the cursor on the node it was on.

        Drawn again rather than adjusted, because everything in it moves: an agent starts a
        turn, a handover happens, a clock ticks. The cursor is held by node rather than by
        row so that it stays on the same box while that happens -- and, where the row it was
        on has gone, on the agent that row hung under.
        """
        listing = self.query_one("#graph", OptionList)
        at = listing.highlighted
        if self._ids and at is not None and 0 <= at < listing.option_count:
            self._was = str(listing.get_option_at_index(at).id or EVERY)
        self._boxes = list(self._boxing())
        self._sessions = list(self._branching())
        self._keyed = {one.who: one for one in self._sessions}
        self._places = {one.key: one for one in self._placing()}
        monitor = self._monitoring()
        shape = monitor.shape()
        self._by_session = monitor.shape(sessions=True)
        rows = self._rows(monitor, shape)
        ids = [one.who for one in rows]
        if ids != self._ids:
            owner = self._owner(self._was)
            landed = next(
                (one for one, who in enumerate(ids) if who == self._was),
                next(
                    (
                        one
                        for one, row in enumerate(rows)
                        if row.landing and row.who and self._owner(row.who) == owner
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
        for half in self.query(_Switch).results(_Switch):
            half.set_class(half.listed == self._listed, "on")
        self._says(monitor, shape)
        self._status()

    def _rows(self, monitor: Monitor, shape: Shape) -> list[_Row]:
        """Every row of the graph, top to bottom, drawn against where the cursor is now.

        Args:
          monitor: The run.
          shape: The run as a graph, taken at the same moment the boxes were.

        Returns:
          The first node, the outworlders, the diagram or the list, and the board.
        """
        return [
            self._every(monitor, shape),
            *self._outworlders(),
            *(self._list(shape) if self._listed else self._agents(shape)),
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
                (
                    f"{_marked(here=self._was == key)}[$primary]◉[/] "
                    f"{escape(role)}{_DOT}[$text-muted]outworlder: messages from "
                    "the flow to you[/]"
                )
                + (f"{_DOT}[$text-muted]{escape(whose)}[/]" if whose else "")
                + (f"{_DOT}[$primary]reading[/]" if self._reading() == key else ""),
            )
            for role in self._outworlding()
            if (key := f"{OUTWORLDER}{role}")
            for whose in [self._whose(role)]
        ]

    def _agents(self, shape: Shape) -> list[_Row]:
        """The diagram itself, one row per node that has worked.

        Args:
          shape: The run as a graph, taken at the same moment the boxes were.

        Returns:
          A row apiece, each holding the arrows above that node's box, the box, and whatever
          it started of its own hanging under it; under an agent opened out, a row per
          session and one for the environment each works in -- and one row saying so where
          none has worked yet, since a graph of a run that has not begun is a blank page
          otherwise.
        """
        if not self._boxes:
            return [
                _Row(
                    _NOTHING,
                    f"{_INDENT}  [$text-muted]no agent has taken a turn yet; "
                    "agents appear as they take turns[/]",
                    landing=False,
                )
            ]
        width = self.size.width
        held: dict[str, list[Drawn]] = {}
        for one in self._sessions:
            held.setdefault(one.of, []).append(one)
        placed = {
            agent: list(
                {
                    one.env: self._places[one.env]
                    for one in sessions
                    if one.env in self._places
                }.values()
            )
            for agent, sessions in held.items()
        }
        rows: list[_Row] = []
        for one, block in zip(
            self._boxes,
            diagram(
                self._boxes,
                shape,
                width,
                self._was,
                opened=self._opened,
                sessions={agent: len(sessions) for agent, sessions in held.items()},
                places=placed,
            ),
            strict=True,
        ):
            rows.append(_Row(one.who, "\n".join(block)))
            if one.who not in self._opened:
                continue
            sessions = held.get(one.who, [])
            if not sessions:
                rows.append(
                    _Row(
                        f"{_NOTHING}{one.who}",
                        f"{_INDENT}  [$text-muted]{_LAST_UNDER}no session has said "
                        "which it is[/]",
                        landing=False,
                    )
                )
            for at, session in enumerate(sessions):
                last = at == len(sessions) - 1
                rows.append(
                    _Row(
                        session.who,
                        session_row(
                            session,
                            self._by_session,
                            width,
                            here=self._was == session.who,
                            last=last,
                        ),
                    )
                )
                place = self._places.get(session.env)
                if place is not None:
                    key = f"{_PLACE}{place.key}{_AT}{session.who}"
                    rows.append(
                        _Row(
                            key,
                            place_row(place, width, here=self._was == key, last=last),
                        )
                    )
        return rows

    def _list(self, shape: Shape) -> list[_Row]:
        """The run as a list: every node, whatever is working at the top, and no arrows.

        What a run of a dozen agents is watched to find out -- who is doing something now --
        without the picture of how they are joined, which is what takes the room. Agents,
        the sessions of the ones opened out, and every environment, each a row of the same
        columns.

        Args:
          shape: The run an agent at a time, taken at the same moment the boxes were.

        Returns:
          A row naming the columns, and a row per node.
        """
        width = self.size.width
        nodes: list[tuple[bool, _Row]] = []
        for one in self._boxes:
            taken = shape.turns.get(one.who, 0)
            nodes.append(
                (
                    one.working,
                    _Row(
                        one.who,
                        listed_row(
                            width,
                            mark=_WORKING if one.working else _IDLE,
                            named=one.named or short(one.who),
                            what=one.runs,
                            turns=f"{taken} turn{'' if taken == 1 else 's'}",
                            clock=_clock(shape, one.who, working=one.working),
                            tokens=thousands(shape.used.get(one.who, 0)),
                            working=one.working,
                            here=self._was == one.who,
                            fold=_OPEN if one.who in self._opened else _SHUT,
                            flag=_flagged(one),
                        ),
                    ),
                )
            )
            if one.who not in self._opened:
                continue
            for session in self._sessions:
                if session.of != one.who:
                    continue
                taken = self._by_session.turns.get(session.who, 0)
                nodes.append(
                    (
                        session.working,
                        _Row(
                            session.who,
                            listed_row(
                                width,
                                mark=_WORKING if session.working else _IDLE,
                                named=session.named or session.who,
                                what=session.runs,
                                turns=f"{taken} turn{'' if taken == 1 else 's'}",
                                clock=_clock(
                                    self._by_session,
                                    session.who,
                                    working=session.working,
                                ),
                                tokens=thousands(
                                    self._by_session.used.get(session.who, 0)
                                ),
                                working=session.working,
                                here=self._was == session.who,
                                flag=_flagged(session),
                            ),
                        ),
                    )
                )
        for place in self._places.values():
            key = f"{_PLACE}{place.key}"
            working = any(
                self._keyed[one].working for one in place.sessions if one in self._keyed
            )
            count = len(place.sessions)
            nodes.append(
                (
                    working,
                    _Row(
                        key,
                        listed_row(
                            width,
                            mark=_ENV,
                            named=place.role or place.kind,
                            what=_where(place),
                            turns=f"{count} session{'' if count == 1 else 's'}",
                            clock="",
                            tokens="",
                            working=working,
                            here=self._was == key,
                        ),
                    ),
                )
            )
        if not nodes:
            return self._agents(shape)  # which says why there is nothing
        return [_Row(_COLUMNS, columns(width), landing=False), *floated(nodes)]

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
                ("Flow", _flowing(flow, self._calling())),
                (
                    "Agents",
                    (reads(named, models) or ["none installed"])
                    if not self._boxes
                    else [],
                ),
                # Only what was changed: a flow of forty settings says nothing by listing
                # the ones nobody touched, and this is read to see what this run is.
                ("Set", [escape(one) for one in setting(config)]),
                # Who else is reading, where anybody is: which of them holds which role is
                # on the outworlders' nodes, and who said what is on the log.
                (
                    "Reading",
                    [escape(one) for one in frontends]
                    if len(frontends := self._frontends()) > 1
                    else [],
                ),
            ],
            [
                # Only the ones the boxes have no arrow for: the rest are drawn above. And
                # none on the list, which is drawn to say nothing of who handed to whom.
                (
                    "Also",
                    [] if self._listed else elsewhere(self._boxes, shape),
                ),
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
                    or ["[$text-muted]no tokens used yet[/]"],
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
        screen this is and how its nodes are drawn, and the keys that do something now --
        space among them only where the cursor is on something it opens or shuts.
        """
        from .app import _RULE

        width = self.size.width
        for ruled in self.query(".rule").results(Static):
            ruled.update(_RULE * width)
        said = f"monitor{_DOT}{_VIEWS[self._listed]}"
        left = f"[$secondary]▣[/] monitor[$text-muted]{_DOT}{_VIEWS[self._listed]}[/]"
        if self._typed():
            keys = ["enter send", "ctrl+c clear"]
        else:
            under = self._was
            folding = (
                ["space shut" if under in self._opened else "space sessions"]
                if any(one.who == under for one in self._boxes)
                else ["space shut"]
                if self._owner(under) in self._opened and self._owner(under) != under
                else []
            )
            keys = [
                "↑↓ node",
                *folding,
                "enter open",
                "→ back",
                f"ctrl+t {_VIEWS[not self._listed]}",
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
                f"{_INDENT}[$primary]Board[/]{_DOT}[$text-muted]shared by you and "
                "the flow[/]",
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
                "[$text-muted]add entry[/]",
            )
        )
        return rows

    @on(OptionList.OptionSelected, "#graph")
    def _clicked(self, event: OptionList.OptionSelected) -> None:
        """A click on a node means what enter on it means -- but on an agent, what space does.

        An agent opens out on its left edge, where its `▸` is, or where the cursor is already
        on it; anywhere else a click only picks it out, and a second straight after reads it,
        which is how a log is reached with the mouse alone.

        Args:
          event: The click, as the list says it.
        """
        named = str(event.option.id or EVERY)
        clicked = self.query_one("#graph", _Graph).clicked
        if not any(one.who == named for one in self._boxes) or clicked is None:
            self._took(named)
            return
        across, chain, before = clicked
        if chain > 1:
            self._took(named)
        elif across < _FOLDS or before == event.option_index:
            self._folds(named)
        else:
            self._fill()  # picked out, which the marker says

    def _took(self, named: str) -> None:
        """Reads a node, opens an environment, or writes a line of the board.

        Args:
          named: The row's id.
        """
        if named.startswith(_PLACE):
            self._visits(named.removeprefix(_PLACE).partition(_AT)[0])
            return
        if not named.startswith(_ON_BOARD):
            self._leaves(named)
            return
        key = named.removeprefix(_ON_BOARD)
        board = self._boarding()
        held = board.held(key) if board is not None and key else None
        if held is not None and held.whose == FLOW:
            self._said = f"{escape(key)} can only be changed by the flow"
            self._fill()
            return
        self._writes(key)

    @work
    async def _visits(self, key: str) -> None:
        """Opens one environment, and reads the session picked on it, if one is.

        Args:
          key: Which environment.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        picked = await showing.push_screen_wait(
            Place(key, self._placing, self._branching)
        )
        if picked:
            self._leaves(picked)

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
        if value:
            board.put(named, value)
            self._said = f"{escape(named)} saved to the board"
        elif board.held(named) is not None:
            # Written down as nothing, which is a line with nothing to say: taken off rather
            # than left up empty, there being no key of its own that does it.
            board.drop(named)
            self._said = f"{escape(named)} removed from the board"
        else:
            self._said = "nothing was entered, so nothing was saved"
        self._ids = []  # the rows have moved, so they are put up again
        self._fill()
