"""humanize as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way Claude Code is, and no wider: a transcript the width of the terminal, an
editor under it between two rules, and a status line under that. Nothing sits beside them --
how the run is going is the monitor, the screen `←` goes up to, and `/flow` both chooses the
loop and, inside the one it opens, sets what each of its agents runs.

The transcript is a tab per agent, and one more where all of them appear together. A flow
drives several agents and each of them holds as many conversations as it likes; every agent's
lines interleaved is none of them readable, and a screen wiped every time a loop opened its
next conversation is a screen nobody can read back through. So each agent keeps a transcript
of its own, all of its conversations running on down it, and the tab this opens on is the one
that shows the lot -- which is where somebody watches a flow rather than an agent. tab and
shift+tab step between that one and whichever agents are working.

It opens on the flow that is only talking to one agent, so that saying something is all it
takes to start. A flow is what you reach for once talking to one agent is not the shape of
the work, and nobody knows that before they have said anything.

The editor means three things at once: a line starting with `/` is a command, a line starting
with `$` names a flow to start and what to start it on, and any other line is the task if
nothing is running yet, or is said to the conversation being read.

Drawn in the terminal's own colours: every surface is the terminal's background and every
colour is one of the sixteen it already has a setting for, so nothing is read from it and
nothing is imposed on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import queue
import re
import shlex
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

import pyfiglet
from rich.box import ROUNDED
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.content import Content
from textual.message import Message
from textual.theme import Theme
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

from hmz.coganchor.prices import money, refresh
from hmz.daemon import Hmz
from hmz.runtime import telemetry
from hmz.runtime.kept import read_back

from .btw import (
    HOPS,
    AgentProgress,
    FlowSnapshot,
    Observation,
    asked,
    compact,
    format_answers,
    format_forked,
    format_snapshot,
    format_turn,
)
from .complete import VIEWS, Command, hinted, offered
from .discover import installable, installed
from .history import History
from .keyboard import reads_long_reports
from .monitor import Monitor, short, thousands
from .monitoring import (
    BoardSeen,
    Drawn,
    Monitoring,
    Placed,
    declared_places,
    needs,
    place_key,
)
from .pick import (
    DETACHES,
    RESUMES,
    STOPS,
    Chosen,
    Declared,
    Epics,
    Flows,
    Held,
    Leaves,
    Reports,
    Runs,
    budget_of,
    declared_of,
    named_as,
    params_model,
    params_of,
    reads,
    settled,
)
from .pick import EVERY as _EVERY
from .selecting import Choices, Transcript
from .settings import PAGES as _PAGES
from .settings import Adjusts, page_of
from .tally import Seen, Tally

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic import BaseModel

    from hmz.daemon import Host, Link
    from hmz.flows import Budget
    from hmz.runtime.epic import Ran

# Once, and before any terminal is read: an input method commits what was composed as one key
# report, and Textual types out any longer than 32 characters as though it were keys.
reads_long_reports()


@dataclass(frozen=True)
class _RunSeen:
    """A run of a flow, as the frontends of the runs here are told of one.

    What `started` said of it and the `run` snapshot says again: which run it is, which flow,
    on what, and what each of its roles was given -- another frontend may have started a
    flow this one never set up, so while it goes it is read off this rather than off what
    is set up here.

    Attributes:
      number: Which run of the host it is.
      flow: The flow, as it was named.
      ref: The flow's canonical ref.
      task: What it was started on.
      by: Who started it, as that frontend is named.
      roles: Its agent roles, in the order the flow declares them.
      outworlders: Its `Outworlder` roles, likewise.
      agents: What each agent role runs, as `-a` spells it after `<role>=`.
      envs: What each environment role was given, as `-e` spells it after `<role>=`.
      harness: Where its agents' harnesses were put, as `-H` spells it, or "" for a run
        whose host did not say.
    """

    number: int
    flow: str = ""
    ref: str = ""
    task: str = ""
    by: str = ""
    roles: tuple[str, ...] = ()
    outworlders: tuple[str, ...] = ()
    agents: Mapping[str, str] = field(default_factory=dict[str, str])
    envs: Mapping[str, str] = field(default_factory=dict[str, str])
    harness: str = ""

    @classmethod
    def of(cls, said: Mapping[str, Any]) -> _RunSeen:
        """A run as a `started` record or a `run` snapshot says it."""
        return cls(
            int(said.get("run") or 0),
            str(said.get("flow") or ""),
            str(said.get("ref") or ""),
            str(said.get("task") or ""),
            str(said.get("by") or ""),
            tuple(said.get("roles") or ()),
            tuple(said.get("outworlders") or ()),
            dict(said.get("agents") or {}),
            dict(said.get("envs") or {}),
            str(said.get("harness") or ""),
        )


#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

#: How long the status line says that something was copied, in seconds. Long enough to be
#: read after a drag that ended somewhere else on the screen, and gone before it is mistaken
#: for a thing about the run.
_COPIED = 2.0

#: How many lines of what is waiting to be said are pinned above the prompt before the rest
#: is counted instead. A pin that grew without limit would push the transcript off the screen
#: to say that a lot is queued, which one line says. The stylesheet holds it to one row more
#: than this, for the line that does the counting.
_PINNED = 5

#: How narrow a terminal a pinned line is still given room in, so that the arithmetic below
#: cannot ask for a negative number of columns.
_NARROW = 20

#: How many transcripts are kept, and how many lines of each. One per agent, one per
#: conversation, one per outworlder and one for all of them together -- and the ones before
#: that are of flows that have already ended, which are kept until there are this many newer.
#: Two thousand lines is more of one than anybody reads back through, and about what a long
#: turn's tools and thinking come to.
_KEPT = 32
_LINES = 2000

#: What the transcript of one outworlder is kept under, ahead of the role: an outworlder is
#: no agent, and what it asks is not an agent's transcript.
_OUTWORLDER = "outworlder:"

#: How each view is said where a command is refused in it, which is saying where it works.
_VIEWED = {
    "monitor": "the monitor",
    "aggregate": "the all-agents transcript",
    "session": "one agent's transcript",
    "outworlder": "an outworlder's transcript",
}

#: How long a second ctrl+c has to arrive in for the two to be one gesture. Long enough to
#: read the line that says what the next press does and then press it, and short enough that
#: a press minutes later is a first press rather than half of one nobody remembers making.
_AGAIN = 3.0

#: What a flow told to stop and not yet gone is doing, said wherever that state is the answer
#: -- to `/stop`, and to everything `_mid_run` turns down. One state reads as one state only
#: while it is said in one wording: two sentences for it are two states to whoever is at the
#: prompt, and each of them one somebody has to work out for themselves.
_UNWINDING = "it is finishing the turn it was in"

#: The flow the interface opens on, which is the one that is only talking to one agent.
_STARTS_ON = "chat"

#: What a `$` may name, which is a flow by the name it is offered under: a letter, then what
#: the directory holding a flow is called, `<where it came from>/<flow>` for one that says
#: which place it came from, and `:<inside>` for one of the several a file holds. Only a line
#: whose `$` is followed by that and then by whitespace or nothing is a flow being started --
#: anything else after the `$`, a space, a bracket, a figure, nothing at all, names no flow
#: there could be, and is a line somebody happened to begin with a `$`.
_NAMED = re.compile(r"[A-Za-z][\w.-]*(?:/[A-Za-z][\w.-]*)*(?::[\w.-]+)?")

#: How long a request made on the way out is given to be answered: the interface is going,
#: and a host that will not answer is not one to be left behind a frozen screen for.
_PATIENCE = 10.0

#: What a line left waiting when a run went is said to have been stopped by, as the host says
#: why it let go of it.
_FIRST = {"stopped": "the flow stopped", "ended": "the flow ended"}

#: How much live activity a side question may carry into its isolated context: a bound on
#: optional observation, since a day-long flow must not grow the interface without limit.
_BTW_EVENTS = 80


@dataclass
class _Btw:
    """Btw mode: who a typed line goes to, and the side conversations opened so far.

    Attributes:
      target: The session asked, as `<role>/<n>`, or "" for the btw agent.
      sides: Each side conversation opened, as the host numbers it, by the session it is
        about -- "" for the btw agent's own.
      busy: Whether a question is being answered.
    """

    target: str
    sides: dict[str, str] = field(default_factory=dict[str, str])
    busy: bool = False


class _BtwLeft(Exception):  # noqa: N818 -- a way out rather than a failure
    """Btw mode was left while a side conversation was being opened."""


def _where() -> str:
    """The directory this is working in, as somebody reading a status line wants it.

    Read each time rather than kept: a flow is a Python file and may change directory under
    the interface, and the one thing this line must not do is name the wrong one.

    Returns:
      The path, with a home directory written as `~` -- the shortening every shell does, and
      the only one that shortens without losing anything.
    """
    here = Path.cwd()
    try:
        home = Path.home()
    except RuntimeError:
        return str(here)  # nobody's home directory, so nothing to shorten it against
    return str("~" / here.relative_to(home)) if here.is_relative_to(home) else str(here)


def _clipped(said: str, room: int) -> str:
    """One line of what is waiting, cut to a row rather than wrapped over several.

    Args:
      said: The line.
      room: How many columns there are for it.

    Returns:
      It, or as much of it as fits with an ellipsis where the rest was.
    """
    return said if len(said) <= room else said[: room - 1] + "…"


#: How many cells the bar opencode spins in its status line is wide. Blocks, not braille --
#: watching it run is what says so.
_BLOCKS = 8

#: What Claude Code marks each thing on screen with, taken from its own source and its own
#: screen: `⏺` where it can and `●` everywhere else for anything the agent said or did, `❯`
#: for a line you typed and for the prompt itself, `⎿` under a tool for what it came back
#: with, and `✻` for the line that closes a turn.
_SAID = "⏺" if sys.platform == "darwin" else "●"
_YOURS = "❯"
_CAME_BACK = "⎿"
_WORKED = "✻"

#: What it rules the prompt with, above and below, and what it rules a sheet with.
_RULE = "─"

#: The dot Claude Code separates the parts of a line with.
_DOT = " · "

#: The frames Claude Code spins while a turn is running, and the words it spins them beside.
_SPINNER = ("·|·", "·/·", "·—·", "·\\·")

#: The terminal's own colours, named so that the stylesheet can ask for them.
#:
#: Every surface is `ansi_default` -- the terminal's background, whatever it has been set to --
#: and everything the interface has to draw is one of the sixteen colours that terminal already
#: has a setting for. So it is not that the colours are read and matched: there is nothing to
#: read, because none of the colours are ours. A theme that named even one of them would be a
#: guess about the background it lands on, and that guess is what a black interface in a white
#: terminal is.
#:
#: `dark` is nearly inert here. It picks the palette Textual would convert ANSI colours through,
#: and `ansi` says not to convert them at all -- they go to the terminal as the terminal's own.
_TERMINAL = Theme(
    name="terminal",
    primary="ansi_blue",
    secondary="ansi_cyan",
    accent="ansi_bright_black",
    warning="ansi_yellow",
    error="ansi_red",
    success="ansi_green",
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    dark=True,
    ansi=True,
    variables={
        # The two Textual's own stylesheet asks an ANSI theme for. Default, like the rest:
        # they end up as the border of an inline app, and that border is the terminal's.
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
        # Where the cursor is. Both ends of the pair are named, because a highlight is the
        # one thing that must not be left to the terminal: against `ansi_default` on
        # `ansi_default` there is nothing to see, and a row that says which one is under the
        # cursor by being a shade of the background says it to nobody. Blue with white on it
        # carries its own contrast, so it reads the same whatever it is drawn over.
        "block-cursor-background": "ansi_blue",
        "block-cursor-foreground": "ansi_bright_white",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "ansi_bright_black",
        "block-cursor-blurred-foreground": "ansi_bright_white",
        "block-cursor-blurred-text-style": "none",
        "input-cursor-background": "ansi_blue",
        "input-cursor-foreground": "ansi_bright_white",
        "input-cursor-text-style": "none",
        # What is selected, in the editor and anywhere on the screen: the same pair either
        # way, since it is one gesture and means one thing. Both ends named, for the reason
        # the cursor's are -- a selection drawn as a shade of the background is one nobody
        # can see the edges of, and the edges are what somebody dragging is watching.
        "input-selection-background": "ansi_bright_black",
        "input-selection-foreground": "ansi_bright_white",
        "screen-selection-background": "ansi_bright_black",
        "screen-selection-foreground": "ansi_bright_white",
        "block-hover-background": "ansi_default",
        # Chrome and anything said quietly, at the one slot every scheme keeps a grey in.
        # Not the foreground at half strength: half of `ansi_default` is `ansi_default`,
        # since there is nothing to blend it against until it reaches the terminal.
        "text-muted": "ansi_bright_black",
        "text-disabled": "ansi_bright_black",
        "border-blurred": "ansi_bright_black",
        "scrollbar": "ansi_bright_black",
        "scrollbar-background": "ansi_default",
        "scrollbar-hover": "ansi_bright_black",
        "scrollbar-active": "ansi_blue",
    },
)


class _Shown(NamedTuple):
    """One thing that has been put in the transcript, kept so that it can be drawn again.

    Attributes:
      content: What was drawn -- markup for a line, and the box this opens with as itself.
      shrink: Whether it is drawn to fit. The box is not: it is measured against the width it
        is rendered at, and one drawn to fit comes out split down its right-hand edge.
    """

    content: object
    shrink: bool


@dataclass
class _Kept:
    """What one transcript has to show, held against it rather than against the screen.

    One per agent, and one more for all of them together. Held rather than drawn once and
    forgotten because stepping to another agent draws that agent's from the top: a transcript
    is what that agent has done, and a screen that only ever appended would be every agent's
    lines shuffled into one another with no way of reading any of them back.

    Attributes:
      lines: What has been put in it, oldest first and held to the last `_LINES` of them, the
        ones before that falling off the front.
      unread: Whether it has said something since it was last read, which is what the line
        above the prompt marks an agent with.
      packed: Whether the last part shown was one the next may run on from. A thing about the
        transcript rather than about the screen: two agents talking at once would otherwise
        space each other's lines.
      spoke: Which agent said the last thing on it, so that the one where all of them appear
        together says who a line is from when that changes. "" on an agent's own, where
        there is only ever the one answer to it.
    """

    lines: deque[_Shown] = field(
        default_factory=lambda: deque[_Shown](maxlen=_LINES),
    )
    unread: bool = False
    packed: bool = False
    spoke: str = ""


class Editor(TextArea):
    """The prompt: multi-line, but enter sends rather than breaking the line."""

    BINDINGS: ClassVar = [
        Binding("enter", "send", "send", priority=True),
        # Both, because only one of them always arrives. A terminal reports shift+enter as
        # itself only where it speaks the keyboard protocol that has a way to say so, and
        # sends a bare carriage return where it does not -- which is enter, and would send
        # the line. `ctrl+j` is a line feed, so it reaches here from any terminal there is.
        Binding("shift+enter", "newline", "newline", priority=True),
        Binding("ctrl+j", "newline", "newline", priority=True),
    ]

    class Sent(Message):
        """What was typed, now that it has been sent."""

        def __init__(self, text: str) -> None:
            """Initializes the message.

            Args:
              text: What was typed.
            """
            super().__init__()
            self.text = text

    class Enters(Message, bubble=False):
        """The enter, on its way back to the queue the keys pressed with it are in.

        The editor's own and nobody else's: what came of it is `Sent`, and this is only how
        it waits its turn behind them.
        """

    class Breaks(Message, bubble=False):
        """The line break, waiting its turn behind the keys that arrived with it.

        The same queue and for the same reason as `Enters`: a break applied ahead of the
        characters typed before it would put the line's end in the wrong place, and the enter
        that follows would send the two lines joined.
        """

    def action_send(self) -> None:
        """Puts the enter behind whatever else arrived in the same read of the terminal.

        Bound with priority, so Textual matches it on the application's pump -- which is
        ahead of the characters of that read, still queued at this editor. A terminal hands
        over everything that has arrived since it was last read, so a pasted line, or one a
        proxy writes in a single go, reaches here with the whole line still behind it. Acting
        now would act on an editor nothing has been typed into: the line would land in the
        prompt a moment later and the enter would be gone, which is a keypress to make again
        for a person and a command that silently did nothing for anything driving this.
        Posted rather than done, so what the handler reads is the characters of that read.
        Only those: a key a binding resolves -- backspace, delete -- is resolved on the
        application's pump too, so it lands ahead of this whatever order it was typed in.
        """
        self.post_message(self.Enters())

    @on(Enters)
    def _sends(self) -> None:
        """Takes what is offered, if anything is, and otherwise sends what is in the editor.

        Enter means over the offers what it means over any list: take the one under the
        cursor. What was typed goes when the offers are gone -- which is a line they have
        nothing more to add to, or esc, which puts them away. The line left showing about a
        finished command is not one of them: it is read, and enter sends what it is about.
        """
        listing = self.screen.query_one("#offers", OptionList)
        if listing.has_class("offering") and listing.highlighted is not None:
            whole = str(listing.get_option_at_index(listing.highlighted).id)
            # The list is filled from a message the application handles, so it can be a
            # keystroke behind the editor. An offer that no longer finishes what is typed is
            # not the one enter was pressed over, and the line goes as it stands instead.
            if whole in offered(self.text, _COMMANDS):
                self.take(whole)
                return
        said, self.text = self.text.strip(), ""
        if said:
            self.post_message(self.Sent(said))

    def action_newline(self) -> None:
        """Breaks the line, which is what enter would do anywhere else.

        Behind the keys that arrived with it, exactly as `action_send` is: bound with
        priority and so matched ahead of them, and a break put in ahead of the characters
        typed before it is a line broken in the wrong place -- which the enter after it would
        then send.
        """
        self.post_message(self.Breaks())

    @on(Breaks)
    def _breaks(self) -> None:
        """Puts the break in, now that what was typed before it is in."""
        self.insert("\n")

    #: Whether what is in the editor was put there by walking what was typed here before,
    #: rather than typed. Nothing is offered against it while that is so: a line walked to
    #: is a line that already exists, and a list opening over it would take the arrows that
    #: are walking it -- one step back through a command, and there is no step forward.
    #: Sticky, because the message saying the text changed is posted rather than called: a
    #: flag held only around the assignment is clear again by the time it arrives. The next
    #: key that is not an arrow is a key that is typing, and clears it.
    walking = False

    def check_consume_key(self, key: str, character: str | None = None) -> bool:
        """Whether a key is typing, which a space on an empty prompt under the monitor is not.

        There it opens the node under the cursor out, as the arrows walk the nodes: nothing
        has been typed for it to be the next character of. Anywhere else, and once anything
        is typed, it is a space.

        Args:
          key: The key.
          character: What it types, if anything.

        Returns:
          Whether this editor takes it, which keeps any binding of it from being matched.
        """
        if key == "space" and not self.text and isinstance(self.screen, Monitoring):
            return False
        return super().check_consume_key(key, character)

    #: Whether the offers were put away with esc and nothing has been typed since, which is
    #: a list not to bring back when what it offers changes under it.
    dismissed = False

    async def _on_key(self, event: events.Key) -> None:
        """Gives tab and the arrows to the offers, but only while there are any.

        Bound here rather than on the application, and only when the list is showing: a key
        the offers are not using is the editor's, and a prompt of more than one line needs
        its arrows back. With nothing offered they walk what was typed here before, and only
        from the ends of what is being typed now -- up off the first line, down off the last
        -- so that a prompt of several lines is still moved around in. Tab reaches here only
        while there are offers to take: with none it is the interface's, which attaches to
        the next conversation with it.
        """
        if event.key not in ("up", "down"):
            self.walking = False
        listing = self.screen.query_one("#offers", OptionList)
        if not listing.has_class("offering"):
            # Out of btw mode, which is the one thing esc means while it is on.
            if (
                event.key == "escape"
                and cast(
                    "Humanize",
                    self.app,  # pyright: ignore[reportUnknownMemberType]
                ).leaves_btw()
            ):
                event.prevent_default()
                event.stop()
                return
            if event.key in ("up", "down"):
                # textual types the property off the bare generic, so what it hands
                # back is an `App` of nothing in particular.
                history = cast(
                    "Humanize",
                    self.app,  # pyright: ignore[reportUnknownMemberType]
                ).history
                row, _ = self.cursor_location
                if event.key == "up" and row == 0:
                    said = history.back(self.text)
                elif event.key == "down" and row == self.document.line_count - 1:
                    said = history.forward()
                else:
                    return  # inside a prompt of more than one line, which is the editor's
                if said is None:
                    return  # nothing that way, so the key is the editor's as it always was
                event.prevent_default()
                event.stop()
                self.walking = True
                self.text = said
                self.move_cursor(self.document.end)
            return
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            if listing.highlighted is not None:
                self.take(str(listing.get_option_at_index(listing.highlighted).id))
        elif event.key in ("up", "down"):
            event.prevent_default()
            event.stop()
            listing.action_cursor_down() if event.key == "down" else (
                listing.action_cursor_up()
            )
        elif event.key == "escape":
            event.prevent_default()
            event.stop()
            # Positional because textual's is: the class names follow it as *args.
            listing.set_class(False, "offering")  # noqa: FBT003
            self.dismissed = True

    def on_mouse_up(self) -> None:
        """Copies what was just dragged across in the editor, as everywhere else does.

        The editor selects for itself rather than letting the screen do it -- it holds a
        selection so that what is typed can be changed, not only read -- so the screen has
        nothing to copy after a drag in here, and this is the only place that knows there was
        one. A click rather than a drag leaves nothing selected, and copies nothing.
        """
        # textual types the property off the bare generic, so what it hands back is an
        # `App` of nothing in particular.
        cast(
            "Humanize",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        ).copied(self.selected_text)

    def take(self, whole: str) -> None:
        """Replaces the part being finished with what was offered for it.

        Args:
          whole: The offer, in full.
        """
        typed = self.text
        self.text = typed[: len(typed) - len(typed.split(" ")[-1])] + whole + " "
        self.move_cursor(self.document.end)


class Humanize(App[None]):
    """A transcript, an editor under it, and a status line under that."""

    CSS = """
    /* Nothing here names a colour of its own. Every surface is the terminal's, and what has
       to stand out is either one of the sixteen colours the terminal already has a setting
       for or a reversal of it -- so the interface reads as part of whatever it was opened
       in, without asking the terminal a single question about itself. */
    Screen { background: $surface; }
    /* An ANSI surface is transparent, and Textual paints a modal over what is behind it by
       blending -- which over a transparent screen blends with nothing. Named, so a sheet is
       a sheet rather than something the transcript reads through. */
    ModalScreen { background: $background; }
    #transcript { width: 1fr; height: 1fr; padding: 0; }

    /* What was said to a flow and has not been taken yet, pinned above the prompt rather
       than written into the transcript: it has not happened, and a transcript is what has.
       Claude Code holds a queued message here too, and for the same reason -- it is still
       yours to see go, rather than something to scroll back for.

       On the left of the block that sits on the editor, beside what the run is running as:
       one thing above the prompt rather than two, so that neither pushes the other up the
       screen. As wide as what is in it, the right-hand side taking the rest. */
    #pinned { height: auto; }
    #queued { display: none; width: auto; height: auto; max-height: 6; padding: 0 2;
              color: $text-muted; }
    #queued.waiting { display: block; }

    /* Above the prompt and unbordered, at most ten rows: what Claude Code offers a
       half-typed command in. The row under the cursor is coloured, not filled. */
    #offers { display: none; max-height: 10; padding: 0 2; background: $background;
              border: none; scrollbar-size: 0 0; }
    #offers.offering, #offers.hinting { display: block; }
    #offers > .option-list--option-highlighted {
        background: $background; color: $primary; text-style: none; }

    /* The prompt: a rule across, what you are typing behind a `❯`, a rule across. Which is
       how Claude Code draws its own -- no box, no bar, no shadow. */
    #above { width: 1fr; height: auto; padding: 0 1; color: $text-muted;
             text-align: right; }
    .rule { height: 1; color: $text-muted; }
    #prompt { height: auto; background: $background; }
    #caret { width: 2; color: $text-muted; }
    #editor { height: auto; max-height: 10; border: none; padding: 0;
              background: $background; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    """

    #: Off, and its key given back. Nothing here is chosen from a dialog -- a `/` offers the
    #: commands and a flag offers whatever it is for -- so a palette of them over the top is a
    #: second way to say the same things, and one nothing else in this interface leads to.
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar = [
        Binding("ctrl+c", "interrupt", "interrupt", priority=True),
        # Textual's own is bound to leaving outright, which on a run being held apart from
        # the terminal would end a day's work on one keypress and without the question
        # `/exit` asks. It is not taken away -- a key somebody's fingers know is a key they
        # will press -- but it means what `/exit` means.
        Binding("ctrl+q", "exit", "exit", show=False, priority=True),
        # Up to the monitor, the screen the log is read from, as Claude Code goes up a level
        # with the same key. Only off an empty prompt, which `check_action` says: anywhere
        # else it is the editor's, moving back along what is being typed.
        Binding("left", "monitor", "monitor", show=False, priority=True),
        # Round the views: the one every agent is on, the conversations running, then the
        # outworlders -- forward on shift+tab, as Claude Code rounds its modes, and back on
        # tab. Priority, since tab and shift+tab are the screen's own way of moving the
        # focus about, and there is nowhere here for the focus to go.
        Binding("shift+tab", "attach_next", "next view", priority=True),
        Binding("tab", "attach_previous", "previous view", priority=True),
    ]

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002  -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of the interface's own keys is live, with something up over it.

        Attaching to a conversation is not, twice over: a sheet is open in order to be
        answered, and both keys are its own while it is there, and the offers are open to be
        taken from, which is what tab does over them. A binding that is refused here is one
        the sheet or the editor is then offered rather than one that is swallowed, since the
        interface's own are priority bindings and would otherwise be matched first wherever
        the cursor was.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it.
        """
        if action == "monitor":
            # From the log alone, and only with nothing typed or offered: the monitor is up
            # already over anything else, and a sheet has its own use for the arrows.
            return (
                len(self.screen_stack) == 1
                and not self.query_one(Editor).text
                and not self.query_one("#offers", OptionList).has_class("offering")
            )
        # Every other one of ours is either the editor's, which a sheet has taken the focus
        # from, or means the same thing wherever it is pressed.
        if action not in ("attach_next", "attach_previous"):
            return True
        if len(self.screen_stack) > 1:
            return False
        # Asked of whatever is on the screen rather than of one widget, since a key may be
        # pressed before the offers themselves have been laid out.
        offering = any(offers.has_class("offering") for offers in self.query("#offers"))
        return not (action == "attach_previous" and offering)

    def action_quit(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Leaves, having first stopped whatever was running.

        A flow is a loop and a turn can think for minutes, so leaving without stopping it
        would leave the interface gone and the work going -- which reads as a hang. Runs held
        in this process go with it; runs a host holds are forced to a stop for everybody,
        which is what `stop it, then leave` asks for, and are otherwise left alone.
        """
        self._quitting = True
        if self._host is not None:
            # This process is where they are, so closing them is the only way they end.
            self._host.close()
        elif self._run is not None or self._stopping is not None:
            # Asked here rather than in the background: this process is about to go, and a
            # request on a thread of its own would go with it before it was sent.
            with contextlib.suppress(Exception):
                self._link.asked({"do": "force"}, seconds=_PATIENCE)
        self._close_btw()
        self.exit()

    @work
    async def action_exit(self) -> None:
        """Closes the interface, having first asked what is to become of a running flow.

        Closing the interface and stopping the run are two things wherever the runs are held
        somewhere this interface closing cannot reach: the flow goes on taking its turns for
        whoever else is reading it, and the next `hmz` here reads it from the top. So it is
        asked rather than assumed, and it is asked only where there is something to ask about
        -- with nothing running, `/exit` is a window being closed.

        What it lets go of is this interface and nothing else: another reading the same runs
        goes on reading them, and whatever this one held for a role is anybody's again.
        """
        if self._run is None:
            self.action_quit()
            return
        said = await self.push_screen_wait(Leaves(held=self._host is None))
        if said == STOPS:
            self.action_quit()
        elif said == DETACHES:
            self._quitting = True
            self._close_btw()
            self._link.close()
            self.exit()

    def action_interrupt(self) -> None:
        """Takes back the nearest thing there is to take back, on a press or two or three.

        The half-written line first, if there is one, which is what ctrl+c does in every
        terminal there is and what nobody presses it twice for.

        With nothing typed it is the run, and it is asked twice: a flow is a day's work
        behind a key that is also pressed by mistake, so the first press says what the next
        one does and the second one does it. Every agent is told to take no further turn, so
        the turn running now is closed out and the loop ends rather than handing on.

        A third press does not wait for it. A flow that has been told to stop unwinds in its
        own time -- a loop sleeps off its round, a server is given its seconds -- and a third
        press closes every conversation still open under whatever turn it is in, which is the
        backend's process going. That is the last thing a key can do about a flow.

        With nothing running it is the interface, asked the same way: twice, because leaving
        is not what ctrl+c means anywhere else and a first press that left would be a run
        somebody ended while reaching to clear a line.
        """
        editor = self._prompt()
        if editor.text:
            editor.text = ""
            self._presses = 0
            return
        now = time.monotonic()
        # A press long enough after the last is the first of its own gesture: nobody
        # remembers pressing this two minutes ago, and the line that said what the next one
        # would do has been gone for most of that.
        self._presses = self._presses + 1 if now - self._pressed < _AGAIN else 1
        self._pressed = now
        if self._run is not None:
            self._interrupts()
        elif self._stopping is not None:
            # A flow told to stop and not yet gone. However long ago it was told: this is
            # the one thing left that a key can do about it, and asking for it twice over
            # would be asking twice about a run that is already over.
            self._forces()
        elif self._presses > 1:
            self.action_quit()
        else:
            self.show("[dim]— press ctrl+c again to exit —[/dim]")
        self._draw()

    def _prompt(self) -> Editor:
        """The prompt on the screen: the monitor's while it is up, the log's otherwise.

        Returns:
          The editor being typed at. The log's where a sheet is up over either, as it was
          before the sheet opened.
        """
        held = self.screen.query(Editor)
        return held.first() if held else self.query_one(Editor)

    def _interrupts(self) -> None:
        """The first two presses at a flow that is running: say so, then stop it."""
        if self._presses < 2:  # noqa: PLR2004 -- the second press is what stops it
            self.show("[dim]— press ctrl+c again to stop the flow —[/dim]")
            return
        self.action_stop_flow()
        # Counted from nothing again, so that the press after this one is the one that does
        # not wait for the flow to unwind rather than the one that leaves.
        self._presses = 0

    def _forces(self) -> None:
        """The press after the one that stopped a flow, which does not wait for it to go.

        Stopping a flow interrupts the turn it was in and lets it unwind, and a backend that
        took no notice of that is the reason there is a third press: every conversation still
        open is closed, which is the backend's process going. What the flow gets back is a
        turn that failed, the same thing it would have got had the agent fallen over by itself.

        And the run reads as over from here, whatever is still unwinding behind it: nothing
        is left that a turn could still be running in, so nothing is left spinning at the
        person who has just asked twice for it to stop.
        """
        self._stopping = None
        self._presses = 0
        self._asks("force", then=self._forced)

    def _forced(self, answer: dict[str, Any]) -> None:
        """Says how many conversations forcing a run closed under their turns.

        Args:
          answer: What the host answered, which says how many as `closed`.
        """
        closed = answer.get("closed")
        if closed:
            self.show(f"[dim]— closed {closed} conversation(s) mid-turn —[/dim]")

    def __init__(
        self,
        flow: str = "",
        agents: Mapping[str, Runs] | None = None,
        params: BaseModel | None = None,
        link: Link | None = None,
    ) -> None:
        """Initializes an interface holding no agents, because nothing is running yet.

        Args:
          flow: The flow to open on, which is what a run being picked up names -- or "" to
            open on what this workspace was last set up to run, and on the one that only
            talks to one agent where it has run nothing.
          agents: What each of that flow's agent roles runs, by role, or None to open on
            what was remembered.
          params: What that flow is set up with, or None to open on what was remembered.
            Checked by whatever read the line: an interface is opened set up, not corrected.
          link: This interface's end of the runs a host holds apart from it, or None to
            hold them here, in this process -- where closing the interface and stopping the
            run are the same thing, and `/exit` offers staying here rather than an answer
            that cannot be carried out.
        """
        # `ansi_color` up front rather than left to the theme: Textual picks the filter it
        # runs every colour through inside `App.__init__`, before a theme set below could
        # have said anything, and under `NO_COLOR` the wrong one there turns the whole
        # interface a single shade of black.
        super().__init__(ansi_color=True)
        # Drawn in the terminal's own colours rather than a scheme of ours. `TEXTUAL_THEME`
        # still wins, for anyone who would rather have one -- read here rather than left to
        # Textual, whose own default for it was settled when this module was imported. One
        # naming a theme that is not there falls back rather than refusing to start.
        self.register_theme(_TERMINAL)
        asked = os.environ.get("TEXTUAL_THEME", "")
        self.theme = asked if asked in self.available_themes else _TERMINAL.name
        #: This interface's end of the runs: everything it draws is a message told through
        #: it, and everything it does to a run is a request asked through it. Made as it
        #: mounts where none was handed over, on runs held in this process.
        self._linked: Link | None = link
        #: The runs, where they are held in this process rather than by a host apart from it:
        #: what closing the interface closes. None where a host holds them.
        self._host: Host | None = None
        #: Who this interface is to the runs, as they named it: its client id and its name.
        self._me = ""
        self._named = ""
        #: Every frontend reading the runs, this one included, by client id: their names.
        self._frontends: dict[str, str] = {}
        #: Which `Outworlder` role is held by which frontend, as the runs last said.
        self._claims: dict[str, str] = {}
        #: The questions the runs are waiting on, oldest first, each saying whose it is.
        self._pending: list[dict[str, Any]] = []
        #: What has been said to the run and not taken yet, as the runs last said: the lines
        #: queued, and the ones put into a turn that the agent has not said it has.
        self._queued: list[dict[str, Any]] = []
        self._given: list[dict[str, Any]] = []
        #: The board a flow and a person share, as the runs last said it, or None for a run
        #: whose flow talks to nobody.
        self._boarded: BoardSeen | None = None
        #: Whether what the runs held when this arrived has all been told, so that what is
        #: told after it is happening now rather than being read back.
        self._live = False
        #: What the runs have said and the screen has not taken yet, oldest first, and
        #: whether the screen has been asked to take it.
        self._arriving = threading.Lock()
        self._arrived: deque[dict[str, Any]] = deque()
        self._draining = False
        #: Whether this interface is on its way out, so that the runs letting it go is not
        #: news to say.
        self._quitting = False
        #: Requests waiting to be asked, in order, on the one thread that asks them: a line
        #: typed twice is two lines in the order they were typed.
        self._requests: queue.SimpleQueue[
            tuple[
                dict[str, Any],
                Callable[[dict[str, Any]], object] | None,
                Callable[[], object] | None,
                bool,
            ]
            | None
        ] = queue.SimpleQueue()
        #: The run going now, or None: which is what `a flow is running` means here.
        self._run: _RunSeen | None = None
        #: And the last one that went, kept once it is over: its sessions are still drawn on
        #: the monitor, and what their environments are is what that run was given.
        self._seen_last: _RunSeen | None = None
        #: Which run is the one in front of us, as the runs number them: a record of a run
        #: that has since been replaced is one about a run nobody is watching.
        self._generation = 0
        #: The runs somebody told to stop, which have said so already and are not `done`.
        self._halted: set[int] = set()
        #: Whether this interface has asked for a run to start and not yet heard it has, or
        #: that it was refused: what is typed meanwhile is said to the run it is starting.
        self._starting = False
        #: The questions this interface has answered and not yet heard were taken, which
        #: a line typed next does not answer again.
        self._answering: set[str] = set()
        #: The run going now, or the last, as the records it tells: each session it opened by
        #: the key it is read under, in the order it opened them, each named for its role.
        #: Kept once the run is over, since its transcripts are still on the screen and
        #: still worth reading back.
        self._seen: dict[str, Seen] = {}
        #: Where each of those sessions works, as the run said as it opened it: the
        #: environment role it fills, the kind of machine, which one, and where on it.
        self._placed: dict[str, dict[str, Any]] = {}
        #: What the flow has done so far, which is what the right-hand column shows, and who
        #: reads the agents' own logs into it while it runs.
        self._monitor = Monitor()
        self._tally = Tally([], self._monitor)
        #: The same pair for each run still going, by run: a run told to stop unwinds in its
        #: own time, and the next may have started by the time it has.
        self._followed: dict[int, tuple[Monitor, Tally]] = {}
        #: The flow calls going, as last told: the flow started and whatever it called.
        self._called: list[dict[str, Any]] = []
        #: The task of the run in front of us and a bounded plain record of what its agent
        #: streams have said. `/btw` reads these once, as a snapshot; it never reaches into a
        #: flow's conversations for context, because doing that would make the side question a
        #: turn of the flow. The same lock holds the side sessions, since their threads add and
        #: remove them while the interface thread may close them on the way out.
        self._flow_task = ""
        self._btw_events: deque[Observation] = deque(maxlen=_BTW_EVENTS)
        self._btw_lock = threading.Lock()
        #: Btw mode, while it is on: who it talks to and the side conversations it opened.
        self._btw: _Btw | None = None
        #: Whether what a turn did on its way to an answer -- the tools it used, the thinking
        #: it did aloud, whatever it printed on its way past -- is shown, which the details
        #: switch on the first page of `/settings` turns, and which is read from what is
        #: remembered once that has been read. Off until somebody says otherwise, because a
        #: flow is watched to see where it has got to: what the agents said to each other and
        #: to you is that, and a tool row per file read is a transcript nobody is reading and
        #: the answer scrolled off the top of it.
        self._details = False
        #: Whether anybody is there to be asked, as the runs last said: `/afk` asks them to
        #: change it, and it outlives this interface. The first is every outworlder; the
        #: second is one outworlder set apart from it.
        self._afk = False
        self._afk_of: dict[str, bool] = {}
        #: The `Outworlder` roles of the run, in the order the flow declares them and then as
        #: any other first asks: one transcript apiece, and a stop on the ring each.
        self._outworlders: list[str] = []
        #: The last thing a turn answered with, and the last thing an agent stopped to ask:
        #: what the flow puts to the person is often exactly that -- a conversation says the
        #: agent's answer back to you to ask what next -- and a line already on the screen is
        #: not put there twice.
        self._last_answer = ""
        self._last_asked = ""
        #: When something was last copied off the screen, so that the status line can say so
        #: for a moment: a clipboard is written to silently, and a gesture that says nothing
        #: is one nobody knows worked.
        self._copied = 0.0
        #: humanize, as the one object what the interface reads and writes on this machine
        #: goes through: the flows there are, the agents and accounts they run as, the runs
        #: already made here. Reached through the daemon, as the interface reaches everything
        #: of the runtime; the runs themselves are asked of through the link instead. A
        #: command line holds the same object, reached the short way.
        self.hmz = Hmz()
        #: What this workspace was last set up to run, so that opening it again finds it
        #: that way rather than back at the default.
        self.settings = self.hmz.settings
        self._details = self.settings.details
        #: The flow to run and what each of its roles is given, which start out as the flow
        #: that is only talking to one agent and the first agent there is to talk to. So the
        #: first thing you say starts something rather than being told to pick a flow first:
        #: a flow is what you reach for once talking to one agent is not the shape of the
        #: work, and nobody knows that before they have said anything.
        self._flow_named = flow or self.settings.flow or _STARTS_ON
        #: What the flow declares, kept rather than read off the flow each time the line
        #: above the prompt is drawn: that means importing the flow, and this is drawn twice
        #: a second. None for a flow that will not load.
        self._declared: Declared | None = declared_of(self._flow_named)
        # What is installed here and what each of them says it runs, which is what a role
        # nothing was remembered for falls back on. Nothing at all until some backend here
        # has said what it runs, which is asked for in the background as this opens.
        remembered = (
            dict(agents)
            if agents is not None
            else self.settings.agents(self._flow_named)
        )
        self._models: dict[str, Runs] = (
            settled(remembered, self._declared.agents, installed())
            if self._declared is not None
            else remembered
        )
        #: Where each environment role is, as `-e` says it.
        self._envs: dict[str, str] = self.settings.envs(self._flow_named)
        #: What the flow itself is set up with, for a flow that takes params at all: an
        #: instance of its model, or None. Read back from what this workspace last ran, so a
        #: flow of many params opens the way it was left.
        self._params: BaseModel | None = params or params_of(
            self._flow_named, self.settings.params(self._flow_named)
        )
        #: What a run of it here may spend, or None for none yet -- which only a flow
        #: humanize ships runs with. Beside the params and not inside them: it is a setting
        #: of the run rather than one of the flow's own.
        self._budget: Budget | None = budget_of(self._flow_named)
        #: Where its agents' harnesses run, as `-H` spells it: "" for adaptive. A setting of
        #: the run beside the budget, and for the same reason.
        self._harness: str = self.settings.harness(self._flow_named)
        #: Where each role's harness went the last time the flow in force ran, by role: what
        #: adaptive came to, which only the machine could say.
        self._harnessed: dict[str, str] = {}
        #: What has been typed here before, which the arrows walk. Read now rather than each
        #: time it is asked for: a run started here writes this project's own history into
        #: being, and what is being walked must not change under whoever is walking it.
        self.history = History()
        #: When each agent's turn started, for the line that closes it.
        self._began: dict[str, float] = {}
        #: What each transcript has to show: one per role, under the role, and one under
        #: `_EVERY` where all of them appear together. Kept by name rather than by the
        #: object, since a role's sessions come and go under it -- a Ralph loop opens one a
        #: turn -- and what is read is the role rather than whichever of them is open.
        self._kept: dict[str, _Kept] = {}
        #: Which transcript is being read: what the screen shows, and which agent a typed
        #: line is said to. The one they all appear on until somebody steps off it, that
        #: being where a flow is watched rather than one agent of it.
        self._attached: str = _EVERY
        #: When ctrl+c was last pressed, and how many times it has been pressed in a row, so
        #: that the second and third mean more than the first. `_AGAIN` is how long a press
        #: counts for.
        self._pressed = 0.0
        self._presses = 0
        #: A run that has been told to stop and has not finished unwinding. A third ctrl+c
        #: closes its conversations under whatever turn is still open, which is the only
        #: thing left that a key can do about a flow already on its way out.
        self._stopping: int | None = None
        #: The conversations with a turn open, by key, which are the only ones a typed line
        #: can go into: one written to a conversation between turns is answered on its own,
        #: outside the flow.
        self._working: set[str] = set()
        #: Whether the monitor draws the run as a list rather than as a graph, as `ctrl+t`
        #: last left it, and which agents it has opened out to their sessions.
        self._monitor_listed = False
        self._monitor_opened: set[str] = set()
        #: Why there is no run here for `/resume` to carry on, as it was last looked for, or
        #: "" where there is one or it has not been looked for yet. What the list goes by, and
        #: how many times it has been looked for, so that a slow look lands only if no later
        #: one has.
        self._no_resume = ""
        self._resume_looks = 0
        #: The commands the list was last worked out against, and what each was said to be
        #: for, with whether a flow could be chosen: what the offers and the keys are drawn
        #: from, compared at every redraw so that both change the moment what they are drawn
        #: from does, rather than at the next keystroke.
        self._standing: tuple[object, ...] = ()

    @property
    def _named_by(self) -> tuple[str, ...]:
        """The agent roles somebody chooses an agent for, in the order the flow declares them.

        What a line about one says, and what every transcript but the shared one is named
        by. While a run goes, its own: another frontend may have started a flow this one
        never set up. For a flow that will not load, the roles something was remembered for.
        """
        if self._run is not None:
            return self._run.roles
        if self._declared is not None:
            return self._declared.roles
        return tuple(self._models)

    def _runs_of(self, role: str) -> Runs:
        """What one agent role runs: as the run going was started with, or as set up here."""
        if self._run is not None:
            said = self._run.agents.get(role, "")
            return read_back(said) or Runs(said)
        return self._models.get(role, Runs(""))

    def _in_order(self) -> list[Runs]:
        """What each agent role runs, in the order the flow declares them."""
        return [self._runs_of(role) for role in self._named_by]

    def compose(self) -> ComposeResult:
        """The transcript, the offers, the editor, the status. The width is the transcript's.

        Nothing sits beside it. What the flow is doing is on the monitor, which is gone up to
        when it is wanted: a column saying so the whole time costs a fifth of every line of
        every transcript, to say something that has usually not changed since it was last
        looked at.
        """
        yield Transcript(id="transcript")
        yield Choices(id="offers")
        # Both sides of the same block, right on top of the editor: what is waiting to go on
        # the left, what it would be going to on the right. Read from the bottom up -- the
        # last thing typed and the running total sit on the row above the rule.
        with Horizontal(id="pinned"):
            yield Static(id="queued")
            yield Static(id="above")
        yield Static(id="rule-above", classes="rule")
        with Horizontal(id="prompt"):
            yield Static(_YOURS, id="caret")
            yield Editor(id="editor", show_line_numbers=False)
        yield Static(id="rule-below", classes="rule")
        yield Static(id="status")

    def on_mount(self) -> None:
        """Says what this understands, then waits to be told something."""
        # Everything printed anywhere under this process lands in the transcript, which is what
        # makes a flow watchable: a session tees each agent's streams to ours as they arrive.
        self.begin_capture_print(self)
        self._welcome()
        # Reached now rather than as this was made, so that nothing the runs say arrives
        # before there is a screen to say it on: runs held in this process where no host was
        # handed over, and the run so far first however they are held.
        if self._linked is None:
            self._host = self.hmz.host()
            self._linked = self._links(self._host)
        self._me = self._linked.client
        self._linked.heard(self._told)
        threading.Thread(
            target=self._requested, daemon=True, name="humanize-requests"
        ).start()
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        self._asks_what_runs()
        self._asks_about_reports()
        self._freshens_flows()
        self._looks_for_resume()
        # What a token costs in money, fetched here and nowhere else: this is the one part of
        # humanize that shows a bill, and it is asked for once on a thread of its own so that
        # nothing drawn afterwards ever waits on a network. What is already kept is served
        # throughout, including while this is still in the air and including if it never lands.
        refresh()
        # The editor is the only thing to type at, so it is the only thing that takes focus:
        # a transcript or a list that could hold it would swallow the keystrokes meant for it.
        for elsewhere in self.query("#transcript, #offers"):
            elsewhere.can_focus = False
        self.query_one(Editor).focus()

    @property
    def _link(self) -> Link:
        """This interface's end of the runs, which it holds from the moment it is mounted.

        Raises:
          RuntimeError: If it is asked for before then.
        """
        if self._linked is None:
            raise RuntimeError("cannot access runs before the interface is mounted")
        return self._linked

    def _links(self, host: Host) -> Link:
        """This interface's end of runs held in this process, rather than by a host apart.

        Args:
          host: The runs.

        Returns:
          The link, attached as an interface.
        """
        from hmz.daemon import linked

        return linked(host, kind="tui")

    @work
    async def _asks_what_runs(self) -> None:
        """Asks each backend here what it runs, for the account nobody chose, where it is due.

        Only the ones never asked or asked too long ago: what a CLI runs is kept, and this is
        the first filling of it -- the moment before that, there is nothing to offer at any
        of the sheets and nothing to open talking to -- and the refilling of one a vendor has
        since moved under.

        In the background and one at a time, because asking means starting a coding agent,
        or reaching the endpoint an account points one at: a prompt cannot wait on either, and
        six at once is six of them. A backend that will not answer is left alone rather than
        retried -- the `check again` row under its models is what asks again.
        """
        import asyncio

        accounts = self.hmz.accounts
        for backend in installed():
            if not accounts.stale(backend):
                continue
            try:
                await asyncio.to_thread(accounts.ask, backend)
            except Exception as why:  # noqa: BLE001 -- a CLI that will not say what it runs
                # Not raised at whoever opened the interface: nobody asked for this, and a
                # backend that will not answer is one to ask again from the models.
                self.log(f"{backend} failed to report available models: {why}")
                continue
            # Which may be the first model there is to open on, for an interface that opened
            # with nothing installed to talk to.
            if self._declared is not None:
                self._models = settled(self._models, self._declared.agents, installed())
            self._draw()

    @work
    async def _freshens_flows(self) -> None:
        """Takes what each flowverse already here says now, quietly, as the interface opens.

        A flowverse is a copy of somebody else's repository, and one only ever fetched again
        when somebody thinks to press a key is one that is months behind by the time anybody
        notices. Every start is the moment to do it: it is the one moment nothing is running,
        and it is often enough that the flows offered are the flows there are.

        In the background and one at a time, the way the backends are asked what they run: a
        fetch is a network round trip, and a prompt that waited on one would open late on a
        slow connection and not at all on a machine with no network. Nothing is drawn about it
        either -- whoever opened the interface asked for a prompt, not for a download -- so one
        that failed goes to the log, and what is already here goes on being what is offered.

        Every one with somewhere to fetch from, whether or not it has ever been fetched. The
        one nobody has fetched is the one most worth getting rather than the one to leave for
        somebody to ask for: its flows are the flows nobody can run at all, so `official` on a
        machine humanize was installed on this morning is the handful in the package and
        nothing else until this lands. Nothing is lost by doing it quietly, either -- the flow
        menu fetches what has never been fetched as it opens and says how that went, so
        whoever goes looking for the flows a failure here would have brought is told, at the
        moment they go looking, rather than left with an empty list and no explanation.

        And not one somebody has written into. A fetch resets the clone to what the repository
        says now, so a weaver editing a flow in a flowverse of their own would lose it to a
        download nobody asked for -- the flowverse's `fetch again` row is still how somebody
        says they meant that.

        Nor under a flow that is running, for the same reason read the other way round: the
        clone reset under a running flow is its own source swapped out from beneath it, and
        what it imports next and the skills it brings would be somebody else's edit halfway
        through a run. Nothing is running when the interface opens, and this stops rather than
        goes on to the next if something starts while it is still going. What is left is the
        one fetch already in the air when a run starts, which is seconds at the opening of the
        interface and the reason this is done then rather than on a timer.
        """
        import asyncio

        verses = self.hmz.verses
        for one in await asyncio.to_thread(verses.all):
            # Whether or not it has ever been fetched. One that never has is the one whose
            # flows nobody can run at all, so it is the one most worth getting: `official`
            # on a machine that has just been installed holds nothing but the `chat` in the
            # package until this lands.
            if not one.url:
                continue
            if self._run is not None or self._stopping is not None:
                return
            if one.fetched and await asyncio.to_thread(verses.edited, one):
                continue
            was = await asyncio.to_thread(verses.standing, one)
            try:
                await asyncio.to_thread(verses.fetch, one.name)
            except Exception as why:  # noqa: BLE001 -- a flowverse that would not fetch again
                # Not raised at whoever opened the interface: nobody asked for this, and the
                # flows that came down last time are still there to run.
                self.log(f"failed to update flowverse {one.name}: {why}")
            else:
                # And only where something came down with it. Most of these bring nothing --
                # the repository has not moved since the last start -- and reading a flow
                # means running it, so telling the menus to read again after one of those is
                # every flow on the disk imported, in force, to arrive at the list that is
                # already drawn. What that costs is somebody else's code run for nothing, on
                # a machine where it had already been run once.
                if await asyncio.to_thread(verses.standing, one) != was:
                    # What is on the disk is something else now, so what anything has read off
                    # it is out of date. A fetch that landed behind a menu already holding the
                    # list from before it is a flow that will not load until the interface is
                    # closed and opened again -- which is the fetch working and nobody being
                    # able to tell.
                    self._flows_changed()
        # And once they have all landed, whether or not anything came down: the look as the
        # interface opened may have read a flow out of a clone halfway through being reset.
        self._looks_for_resume()

    def _flows_changed(self) -> None:
        """Tells whatever is drawn that the flows on the disk are not the ones it read.

        A sheet that lists flows reads them once and holds the list, reading one being running
        it. That is right while nothing underneath changes and wrong the moment a fetch lands:
        the held list is from before the download, so a flow that arrived in it is one the menu
        does not offer and a flow whose file changed is one it will not load. Both look like a
        fetch that did nothing, and both come right on a restart -- which is the interface
        asking to be closed and opened to pick up what it already has.

        Every sheet on the stack rather than the one on top: a fetch lands where it lands, and
        the menu underneath is the one somebody comes back to.
        """
        from hmz.tui.pick import Lists

        for screen in self.screen_stack:
            if isinstance(screen, Lists):
                screen.reread()
        # And whether the last run here is of a flow that can be picked up, which is a
        # question about a flow.
        self._looks_for_resume()

    def _welcome(self) -> None:
        """The box this opens with: what this is, and how to begin.

        The description is the one the package was built with rather than a second copy of
        it, so the sentence this answers to is the sentence it was published under.

        What is set up to run is not in it, nor is where it would run. Those are on the lines
        round the editor, where they are redrawn twice a second, and a second copy of either
        here could only be the copy that was true when the interface opened -- the transcript
        is append-only, so a line written into it is a line about the moment it was written.

        Its title rides in the top border and its corners are round, which is the one boxed
        thing on the screen: everything after it is text down the terminal. Drawn as a panel
        rather than as lines of rules, so that every side of it is measured against the same
        width at the moment it is rendered -- lines written to a width guessed before the
        screen was laid out come out of the transcript split down the right-hand edge. And
        it is only as wide as what is in it: a box ruled the whole way across an empty screen
        is mostly rule, and nothing in it is wider than the name drawn across the top.
        """
        from importlib.metadata import metadata, version

        self._into(
            None,
            Panel(
                Group(
                    Text(self._banner(), style="blue", no_wrap=True),
                    Text(""),
                    Text(str(metadata("hmz")["Summary"] or "")),
                ),
                # Room around it, above and below and at both ends: the name drawn large is
                # the first thing on the screen and reads as cramped without any.
                padding=(1, 4),
                box=ROUNDED,
                border_style="dim",
                title=f"[dim]humanize v{version('hmz')}[/dim]",
                title_align="left",
                expand=False,
            ),
            shrink=False,
        )

    def _banner(self) -> str:
        """The name, drawn large.

        Returns:
          The word as block letters where the terminal is wide enough to hold them, and as
          the small face where it is not. Two of them and no more: a banner that wrapped
          would be worse than no banner, and one that is picked from a dozen faces by width
          is a dozen ways for it to be wrong.
        """
        for face in ("ansi_shadow", "small"):
            art = pyfiglet.figlet_format("humanize", font=face).rstrip("\n")
            drawn = [line for line in art.splitlines() if line.strip()]
            # Against what is left after the box: a border and four columns of room a side.
            if max(len(line) for line in drawn) <= self.size.width - 10:
                return "\n".join(drawn)
        return "\n".join(drawn)

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript, as a barred block.

        Where the runs are held in this process, which is where what a flow prints lands; a
        host apart from it says what is printed there as a `printed` message instead, which
        lands in the same place.

        Args:
          event: What was printed.
        """
        self._prints(event.text)

    def _prints(self, text: str) -> None:
        """Puts something printed where the runs are into the transcript, as a barred block.

        Output is barred rather than indented because that is what opencode does with it:
        a command and what it said are one block, set apart from the words around them.

        Only with details on. What a backend writes on its way past is the working rather
        than the answer -- the same thing its tool rows and its thinking are -- and a flow
        watched to see where it has got to is one where all of that is in the way. The raw
        line is still retained in the bounded `/btw` snapshot when details are off.

        Args:
          text: What was printed.
        """
        if text.strip():
            # Flow-owned progress (for example, a Ralph round counter) is useful to `/btw`
            # even when details keep it out of the visible transcript.
            with self._btw_lock:
                self._btw_events.append(
                    Observation(
                        agent="",
                        kind="flow",
                        text=compact(text),
                        at=time.monotonic(),
                    )
                )
        if text.strip() and self._details:
            for line in escape(text.rstrip("\n")).splitlines():
                self.show(f"[dim]  {_CAME_BACK}  {line}[/]")

    def on_text_selected(self) -> None:
        """Puts what was just selected with the mouse on the clipboard.

        Letting go of a selection is the whole gesture. The interface has the mouse -- it is
        drawing the highlight itself, the terminal never having been told a drag was going on
        -- so a selection nobody copied is one that goes nowhere.

        What is copied is the text the transcript was written as rather than the screen: a
        line that took four rows comes back as the line, without the breaks the width put in
        it and without the spaces that padded each row out to the edge.
        """
        self.copied(self.screen.get_selected_text() or "")

    def copied(self, text: str) -> None:
        """Puts something on the clipboard, and says on the status line that it went.

        By the escape a terminal takes for its clipboard, which is the only way to reach the
        clipboard of the machine somebody is sitting at while the interface runs on another
        one. Nothing else about it is ours: a terminal that will not take the escape is one to
        turn it on in, and holding shift while dragging is what every terminal keeps for
        itself.

        Args:
          text: What to copy, and "" for a gesture that came to nothing -- a click that
            landed on no text, an empty selection -- which is not a thing to say happened.
        """
        if not text:
            return
        self.copy_to_clipboard(text)
        self._copied = time.monotonic()
        self._draw()

    def _said_by_you(self, text: str, whose: str = "", by: str = "") -> None:
        """Puts something you said in the transcript, behind the `❯` Claude Code marks it with.

        Args:
          text: What was said.
          whose: The agent it was put to, where it went to one -- so that it lands on that
            agent's transcript and on the one they all appear on, as everything else that
            agent says does. A word put into a turn is part of that conversation, and would
            otherwise be on whichever screen happened to be up when the agent took it. "" for
            a line that went to nobody in particular: a command, the task that starts a flow,
            a line a flow that ended never took.
          by: Who said it, as `_by` says it, where it was another frontend rather than you.
        """
        # What is read next starts its own part.
        self._keeping(whose or None).packed = False
        said = escape(text).splitlines() or [""]
        for line in (
            "",
            f"[dim]{_YOURS}[/] {said[0]}" + (f"[dim]{escape(by)}[/]" if by else ""),
            *(f"  {one}" for one in said[1:]),
        ):
            self._into(whose or None, line)

    def _by(self, said: Mapping[str, Any]) -> str:
        """Who said something the runs were told, where it was not this interface.

        Args:
          said: What the runs said of it, naming the frontend by `client` and `by`.

        Returns:
          ` · by <name>`, or "" for this interface's own and for one nobody said.
        """
        client = str(said.get("client") or "")
        if not client or client == self._me:
            return ""
        return f"{_DOT}by {said.get('by') or self._frontends.get(client, client)}"

    def show(self, text: str, style: str = "") -> None:
        """Puts a line in the transcript, on whichever one is being read.

        The interface's own lines go where you are looking: what you typed, what a command
        came back with, what went wrong. They are nobody's transcript in particular, and one
        that dropped them would be a screen where half of what you did never happened.

        Args:
          text: What to show, taken as markup when no style is given and as plain text
            otherwise -- so that a bracket an agent wrote stays a bracket.
          style: How to show it, as a Rich style, or "" to show it as it is.
        """
        body = text if style == "" else f"[{style}]{escape(text)}[/{style}]"
        self._into(None, body)
        # And under the graph, where the monitor is what is on the screen: a command typed
        # there answers there, rather than on a log nobody is looking at.
        for up in self.screen_stack:
            if isinstance(up, Monitoring):
                up.says(body)

    def _into(
        self,
        whose: str | None,
        content: object,
        *,
        shrink: bool = True,
        shared: bool = True,
    ) -> None:
        """Keeps something on the transcripts it belongs on, and draws it if one is read.

        A conversation's line goes on three: that conversation's own, its agent's, and the one
        where every agent's work appears together. Which is what makes the last a place to
        watch a flow from rather than a copy of one agent -- and what makes stepping onto a
        conversation a transcript of it rather than the screen carrying on. An outworlder's
        goes on its own and on that last one, which hosts whatever any of them asks.

        Args:
          whose: The transcript it is from -- a conversation, an agent, an outworlder, as
            `_now_reading` names them -- or None for the interface's own, which belongs to
            whichever transcript is being read, since that is the one it was said over.
          content: What to draw, as markup or as something Rich renders.
          shrink: Whether to draw it to fit.
          shared: Whether it goes on the one every agent is on as well, which it does unless
            that one already shows it.
        """
        if not whose:
            where = [self._attached]
        else:
            role = self._role_of(whose)
            where = [
                *([_EVERY] if shared else []),
                *([role] if role and role != whose else []),
                whose,
            ]
        speaker = self._role_of(whose or "") or whose
        for one in where:
            kept = self._keeping(one)
            if one == _EVERY and speaker and kept.spoke != speaker:
                # Two agents working at once are two agents whose lines land here in the
                # order they were said, so the one being read from has to be said. Once, as
                # it changes: a name against every line is a column nobody is reading.
                kept.spoke = speaker
                self._writes(one, _Shown("", shrink=True))
                said = f"[dim]{_RULE * 2} {escape(self._titled(speaker))}[/]"
                self._writes(one, _Shown(said, shrink=True))
            self._writes(one, _Shown(content, shrink))

    @staticmethod
    def _role_of(key: str) -> str:
        """The agent role a transcript is of: its own for a conversation's, "" for the rest.

        Args:
          key: The transcript, as `_now_reading` names them.

        Returns:
          The role for an agent's or a conversation's, and "" for the one every agent is on
          and for an outworlder's, neither of which is any agent's.
        """
        if key.startswith(_OUTWORLDER):
            return ""
        return key.partition("/")[0]

    @staticmethod
    def _titled(key: str) -> str:
        """What a transcript is called where it is named: an agent, a conversation, and so on.

        Args:
          key: The transcript, as `_now_reading` names them.

        Returns:
          Its name as it is read.
        """
        if key == _EVERY:
            return "all agents"
        if key.startswith(_OUTWORLDER):
            return f"outworlder {key.removeprefix(_OUTWORLDER)}"
        role, _, count = key.partition("/")
        return f"{short(role)}{_DOT}conversation {count}" if count else short(role)

    def _view_kind(self) -> str:
        """Which kind of view is in front of the person, which is what a command works in.

        Returns:
          `monitor` where the run is drawn, `aggregate` on the transcript every agent is on,
          `outworlder` on what one outworlder asks, and `session` on one agent's or one of its
          conversations'.
        """
        screen = self.screen
        if screen.id == "monitor" or type(screen).__name__.startswith("Monitor"):
            return "monitor"
        if self._attached == _EVERY:
            return "aggregate"
        if self._attached.startswith(_OUTWORLDER):
            return "outworlder"
        return "session"

    def _writes(self, whose: str, shown: _Shown) -> None:
        """Puts one line on one transcript, and on the screen where that one is read.

        Args:
          whose: Which transcript, as `_keeping` names them.
          shown: The line.
        """
        kept = self._keeping(whose)
        kept.lines.append(shown)
        if whose == self._attached:
            self.query_one("#transcript", Transcript).write(
                shown.content, shrink=shown.shrink
            )
        elif _EVERY not in (whose, self._attached):
            # Nothing is unread while every agent is being read: it went onto that transcript
            # too, and it was read there. Marking it would be marking every agent of the flow
            # as having something nobody has looked at, on the one screen that shows the lot.
            kept.unread = True  # and the line above the prompt says so until it is read

    def _keeping(self, whose: str | None) -> _Kept:
        """What is kept of one transcript, opening one the first time.

        Args:
          whose: The agent it is of, or `_EVERY` for the one they all appear on. None means
            the one being read, which is what the interface's own lines are said over.

        Returns:
          What it has to show, which is what stepping onto it draws.
        """
        key = self._attached if whose is None else whose
        if (kept := self._kept.get(key)) is not None:
            return kept
        kept = self._kept[key] = _Kept()
        # The oldest go first, a conversation's before an agent's, and never the one being
        # read, the one all of them are on, or the one just opened: a machine that has run
        # twenty flows would otherwise keep every agent of all of them, and a loop that opens
        # a conversation a turn would otherwise push its own agent's transcript out.
        over = len(self._kept) - _KEPT
        dropping = sorted(
            (one for one in self._kept if one not in (_EVERY, key, self._attached)),
            key=lambda one: "/" not in one,
        )
        for gone in dropping[: max(over, 0)]:
            del self._kept[gone]
        return kept

    def _conversations(self) -> list[str]:
        """Every conversation the flow has open, in the order the flow takes its agents.

        The person is not among them: they are an agent a flow talks to rather than one it
        drives, and the conversation with them is this prompt.

        Returns:
          Their keys, agents in the order the flow takes them and each of their conversations
          oldest first -- and none once the run is over, there being nothing left to say to.
        """
        return self._driven() if self._run is not None else []

    def _driven(self) -> list[str]:
        """The conversations there are transcripts of, which are the run's or the last run's.

        The last run's once it is over, because its transcripts are still on the screen and
        still worth reading back: a run that ended is the one somebody wants to look at.
        Nothing that asks this can mistake one for a flow that is running -- what is working
        is asked of the conversations, and there are none of those once a run is over.

        Returns:
          One key per session opened, oldest first.
        """
        return list(self._seen)

    def _of(self, role: str) -> list[str]:
        """Every session one role has opened, oldest first."""
        return [key for key, seen in list(self._seen.items()) if seen.id == role]

    def _working_agents(self) -> list[str]:
        """Which of the flow's roles have a turn open, in the order they opened sessions.

        Returns:
          Their names. These are the ones tab steps between: with ten agents going, what
          somebody is stepping between is the ones thinking.
        """
        return list(
            dict.fromkeys(
                seen.id
                for key, seen in list(self._seen.items())
                if key in self._working
            )
        )

    def _reading(self) -> str | None:
        """The conversation being read, where one role is rather than all of them.

        Returns:
          The conversation read, the newest of the role read, or None on the transcript they
          all appear on, on an outworlder's, and for one whose flow is over -- the transcript
          stays up either way, there being nothing to say to it.
        """
        if "/" in self._attached:
            return self._attached if self._attached in self._seen else None
        held = self._of(self._role_of(self._attached)) if self._attached else []
        return held[-1] if held else None

    def _says_to(self) -> str | None:
        """Which conversation a typed line goes into, which is the one on the screen.

        The agent being read is what is being said to; of its conversations, the one with a
        turn open, since a line written to one between turns is answered on its own outside
        the flow. Where all of them are being read there is no one agent to have meant, so it
        is whichever has a turn open -- which is what the transcript is showing.

        Returns:
          The conversation's key, or None where there is none open to say it to yet -- and on
          an outworlder's transcript, which is no agent's to say anything to.
        """
        if "/" in self._attached:
            return self._reading()
        if self._attached.startswith(_OUTWORLDER):
            return None
        working = [key for key in self._conversations() if key in self._working]
        key = self._reading()
        if key is not None:
            return key if key in working else None
        return working[0] if working else None

    def _now_reading(self, whose: str, *, stepped: bool = True) -> None:
        """Reads one of the transcripts there are, drawing it from the top.

        From the top, and not by carrying on where the screen was: what an agent has done is
        that agent's transcript, and a screen that only appended would be every agent's lines
        shuffled into one another. Stepping between an agent's own conversations is not this
        -- they are all one transcript, so a loop that opens one a turn goes on down the same
        screen rather than replacing it.

        Args:
          whose: Which transcript: `""` for the one every agent is on, `<role>` for one agent
            and all of its conversations, `<role>/<n>` for the n-th conversation that role
            opened, counting from one, and `outworlder:<role>` for what one outworlder asks.
          stepped: Whether somebody asked for this, rather than what was being read having
            gone with the flow that held it.
        """
        if whose == self._attached:
            return  # already the one on the screen, so nothing has happened
        self._attached = whose
        kept = self._keeping(whose)
        kept.unread = False
        if whose == _EVERY:
            # Everything every agent has said is on this one, so reading it is reading all of
            # them: an agent left marked unread here would be marked for what is on the screen.
            for one in self._kept.values():
                one.unread = False
        shown = self.query_one("#transcript", Transcript)
        shown.clear()
        held = len(self._of(whose)) if self._role_of(whose) == whose else 0
        many = f"{_DOT}{held} conversations" if held > 1 else ""
        named = f"{escape(self._titled(whose))}{many}"
        shown.write(
            f"[dim]{_RULE} {'' if stepped else 'that flow has gone, now '}"
            f"reading {named} {_RULE}[/]"
        )
        for line in kept.lines:
            shown.write(line.content, shrink=line.shrink)

    def _unread(self, whose: str) -> bool:
        """Whether one transcript has something on it nobody has looked at.

        Args:
          whose: Which one, as `_keeping` names them.

        Returns:
          True if it has said something since it was last read.
        """
        kept = self._kept.get(whose)
        return kept is not None and kept.unread

    def _held(self) -> list[Held]:
        """How many conversations each of the flow's roles has, and which one is being read.

        Returns:
          One per agent role, in the order the flow declares them -- and nothing at all with
          no flow run, which is a line about what is set up rather than about what it is
          doing.
        """
        if not self._driven():
            return []
        held: list[Held] = []
        for role in self._named_by:
            keys = self._of(role)
            held.append(
                Held(
                    many=len(keys),
                    reading=role == self._role_of(self._attached),
                    unread=self._unread(role),
                    working=any(key in self._working for key in keys),
                )
            )
        return held

    def action_attach_next(self) -> None:
        """Reads the next view round the ring, which is what shift+tab is for."""
        self._attach_by(1)

    def action_attach_previous(self) -> None:
        """Reads the one before it, which is what tab is for."""
        self._attach_by(-1)

    def _ring(self) -> list[str]:
        """What shift+tab steps round: all of them, the conversations running, outworlders.

        The conversations with a turn open rather than every one the flow has opened: with
        ten agents going, what somebody is stepping between is the ones thinking. One that
        has ended can still be read, from the monitor, which is where it is picked out by
        name rather than stepped past. An outworlder is one stop however many conversations
        it is asked in, for as long as its run is going.

        Returns:
          The transcripts to step round, the one they are all on first -- so that there is
          always the way back to watching the flow rather than one agent of it.
        """
        running = [key for key in self._conversations() if key in self._working]
        asked = (
            [f"{_OUTWORLDER}{one}" for one in self._outworlders]
            if self._run is not None
            else []
        )
        return [_EVERY, *running, *asked]

    def _attach_by(self, step: int) -> None:
        """Moves what is being read one step round the ring, either way.

        Args:
          step: How far, and which way.
        """
        ring = self._ring()
        # From where the one being read stands, and from the start where it is not on the
        # ring at all -- an agent that has stopped since it was stepped onto, which is left
        # up until somebody asks for something else.
        at = ring.index(self._attached) if self._attached in ring else 0
        self._now_reading(ring[(at + step) % len(ring)])
        self._draw()

    @on(TextArea.Changed)
    @on(TextArea.SelectionChanged)
    def _offer(self, event: TextArea.Changed | TextArea.SelectionChanged) -> None:
        """Offers whatever the line being typed could be finished with.

        Reconsidered when the cursor moves as well as when the text does: an offer made at
        the end of a line does not still stand once the cursor is back in the middle of it.
        Over whichever prompt it was typed at -- the log's or the monitor's, each of which
        has its offers above it.

        Args:
          event: What changed, which says which prompt it was.
        """
        if isinstance(editor := event.text_area, Editor):
            editor.dismissed = (
                False  # typed at since, so what esc put away is asked again
            )
            self._offers_on(editor)

    def _offers_on(self, editor: Editor, *, keeping: bool = False) -> None:
        """Works out what one prompt's line could be finished with, and lists it above it.

        Args:
          editor: The prompt.
          keeping: Whether to keep the cursor on the offer it was on, where that is still
            offered: for a list worked out again under somebody who has not typed anything.
        """
        listing = editor.screen.query_one("#offers", OptionList)
        was = (
            listing.get_option_at_index(listing.highlighted).id
            if keeping and listing.highlighted is not None and listing.option_count
            else None
        )
        typed = editor.text
        # At the end of what is being typed, and being typed rather than walked to.
        at_end = editor.cursor_location == editor.document.end and not editor.walking
        # And nothing against a `$` while an agent is waiting on an answer: the next line
        # typed is that answer, whatever it begins with, so a list that took the enter would
        # finish a flow's name over an answer nobody ever gave.
        answering = self._answers_to() is not None and typed.startswith("$")
        # Only what works in the view in front of the person, and as things stand: a command
        # offered where it is refused is one offered to be told off for. The flows likewise,
        # which are offered to be chosen, and are not while one runs.
        here = self._commands_here()
        offers = (
            offered(typed, here, flows=self._run is None)
            if at_end and not answering
            else []
        )
        # Nothing left to finish, but a command still being written: its own line stays up,
        # since what it takes after its name is written there and is what is wanted just
        # then. Shown and not offered -- `offering` is what says a key is the list's.
        hint = hinted(typed, here) if at_end and not offers else ""
        listing.clear_options()
        listing.set_class(bool(offers), "offering")
        listing.set_class(bool(hint), "hinting")
        if hint:
            listing.add_option(self._offer_of(f"/{hint}"))
        if offers:
            # Name on the left and what it is for on the right, as opencode lists its own.
            # The bare name is kept as the option's id, since that is what replaces the text.
            # The name and what it takes on the left, what it is for on the right. The bare
            # name is the option's id, since that is what replaces the text: taking an offer
            # must not type the arguments in as well.
            listing.add_options([self._offer_of(offer) for offer in offers])
            listing.highlighted = offers.index(was) if was in offers else 0

    def _commands_here(self) -> tuple[Command, ...]:
        """The commands that work in the view in front of the person, and would do so now."""
        kind = self._view_kind()
        return tuple(
            one
            for one in _COMMANDS
            if kind in one.where
            and not (one.refuses is not None and one.refuses(self))
            and not (one.unlisted is not None and one.unlisted(self))
        )

    def _about(self, command: Command) -> str:
        """What one command is said to be for, as things stand.

        Args:
          command: The command.

        Returns:
          What its row says beside its name.
        """
        return (command.now(self) if command.now is not None else "") or command.about

    def _reconsiders(self) -> None:
        """Offers and binds again where what either is worked out from has moved.

        Asked at every redraw, which is twice a second and after anything the runs say: a run
        starting, stopping or ending, a view stepped to, btw mode entered or left. A list that
        went on offering `/stop` after the flow ended, or not offering it once one started,
        would be a list true as of the last key pressed rather than as of now -- so it is
        worked out again the moment it differs, and left alone, cursor and all, while not.
        """
        here = self._commands_here()
        standing = (
            self._run is None,
            self._answers_to() is None,
            self.screen,
            *((one.name, self._about(one)) for one in here),
        )
        if standing == self._standing:
            return
        self._standing = standing
        # Not one somebody put away with esc since they last typed: a list that came back
        # of its own accord would take the enter that was meant to send the line. Nor an
        # empty prompt, which has nothing to finish and so nothing listed to change.
        for editor in self.screen.query(Editor):
            if editor.text and not editor.dismissed:
                self._offers_on(editor, keeping=True)
        self.refresh_bindings()

    def _offer_of(self, offer: str) -> Option:
        """One row of the list: what would be typed, and what it is for.

        Args:
          offer: What taking it would leave in the editor, in full.

        Returns:
          The row. The bare name is its id, since that is what replaces the text -- taking
          an offer must not type the arguments in as well.
        """
        # A flow is the other thing offered here, and it says nothing about itself: only a
        # `/` names a command, so a flow that happens to be called `monitor` is not one.
        command = _BY_NAME.get(offer[1:]) if offer.startswith("/") else None
        takes = command.takes if command else ""
        about = self._about(command) if command else ""
        # Escaped: what a command takes is written in brackets, and a bracket left as it is
        # would be read as markup and swallowed -- which is what `[path]` did. Padded first,
        # since the escaping adds characters that are not columns.
        return Option(
            escape(f"{f'{offer} {takes}'.rstrip():<19}")
            + f"[dim]{escape(about)}[/dim]",
            id=offer,
        )

    def _draw(self) -> None:
        """Redraws the lines around the editor: what is above it, the rules, the status.

        Called on a timer, which keeps ticking while the interface is being taken down -- so
        there may be nothing left to draw on.
        """
        if not self.is_running:
            return
        # First, since the keys drawn below are read off whether anything is offered.
        self._reconsiders()
        spending = self._monitor.spending()
        spent = sum(spend.tokens for spend in spending)
        rate = sum(spend.rate for spend in spending)
        # What went on each kind of token, which is the reading anybody has a use for: an
        # input token, an output token and a cached read are three different things bought at
        # three different prices, and one number over the lot of them answers no question.
        # Marked where a figure is short of what an agent of this run spends without counting.
        counted = self._monitor.reckoning()
        # What the run has cost in money, and whether that is the whole of it: a model
        # nobody prices adds tokens to the count and nothing to the bill, so the figure is
        # marked as a floor rather than quietly reported as the total.
        billed = [spend.dollars for spend in spending if spend.dollars is not None]
        bill = sum(billed) if billed else None
        floor = "+" if billed and len(billed) < len(spending) else ""
        # Left, first match wins, as opencode's status line resolves it: what is running if
        # anything is, else where this is. Right, the usage. The two ends are pushed apart.
        working = self._monitor.now_working()
        if self._run is not None and not working and (waits := self._waits_on()):
            # A flow that has run out of things to do until it is told one. Spinning a bar at
            # it would read as a turn that has been thinking for as long as you have been
            # deciding what to say, which is the opposite of what is happening.
            left = (
                f"[$text-muted]{_SPINNER[0]} waiting for {escape(waits)}"
                f"{_DOT}ctrl+c twice to stop[/]"
            )
        elif working or self._run is not None:
            bar = _SPINNER[int(time.monotonic() / _REFRESH) % len(_SPINNER)]
            # Whoever is talking and how long their turn has been going, or -- between two
            # turns -- the flow itself and how long the run has. A flow sleeps off a round,
            # commits, reads what the last turn wrote, and none of that is a flow that has
            # stopped: a clock still moving is what says so.
            since = min(
                (self._began[who] for who in working if who in self._began),
                default=self._monitor.began,
            )
            named = ", ".join(short(who) for who in working) or self._flowing()
            left = (
                f"[$secondary]{bar}[/] {escape(named)}… "
                f"[$text-muted]({time.monotonic() - since:.0f}s{_DOT}ctrl+c twice to stop)[/]"
            )
        else:
            # The flow that is set up to run, and the directory it would run in. Only with
            # nothing running: the two lines above are about a run once there is one, and
            # where it is working has not changed since it started.
            left = (
                f"[$secondary]◉[/] {escape(self._flowing())}"
                f"[$text-muted]{_DOT}{escape(_where())}[/]"
            )
        # The modes this is in, ahead of everything else on the line. Both change what the
        # interface does without changing anything drawn on it, and a mode nobody can see
        # they are in is one they find out about from what did not happen -- an agent that
        # wanted a person and was told there is none. In front rather than beside, since
        # that is the one place on this row that survives a narrow terminal: the keys are
        # clipped from their end and the flow and the directory can fill a small screen on
        # their own, so a marker anywhere else is one that is there until it is needed.
        # `afk` in the colour of a warning, being the one that decides whether an agent may
        # reach you at all.
        if self._details:
            left = f"[$text-muted]details[/]{_DOT}{left}"
        if away := self._away_marker():
            left = f"[$warning]{escape(away)}[/]{_DOT}{left}"
        # And btw mode, in the colour its answers are in: every line typed goes to a side
        # conversation rather than to the flow while it is on.
        if (mode := self._btw) is not None:
            left = f"[cyan]btw{_DOT}{escape(mode.target or 'btw agent')}[/]{_DOT}{left}"
        # For a moment after it happens, beside whatever else the line says: writing to a
        # clipboard is silent, and a person who has just dragged across half a screen is
        # owed the one word that says it went somewhere.
        if time.monotonic() - self._copied < _COPIED:
            left += f"[$text-muted]{_DOT}copied[/]"
        # Above the prompt on the right, where Claude Code says what it is running as. One
        # agent to a line rather than a row of them separated by commas: a flow drives several
        # and they are read one at a time, against the name the flow calls each one by -- and
        # with the conversations each of them is holding, since one of those is what is being
        # read and what a typed line goes to.
        lines = reads(self._named_by, self._in_order(), self._held()) or [
            "no agent installed" if self._named_by else "no agent available"
        ]
        lines.extend(self._outworlder_lines())
        if spent:
            costing = f"{money(bill)}{floor}{_DOT}" if bill is not None else ""
            # Two lines rather than one: five kinds, a bill and a rate on one row come to a
            # row wider than the terminal, and what sits above the editor is read at a glance.
            lines.append(
                _DOT.join(
                    f"{one.kind} {thousands(one.tokens)}{'' if one.whole else '+'}"
                    for one in counted
                )
                or f"{thousands(spent)} tokens"
            )
            # Output alone, and said so: the input of a turn is the conversation so far, sent
            # again at every request and mostly served out of a cache, so a rate counting it
            # says how long the transcript has got rather than how fast the model is writing.
            lines.append(f"{costing}{rate:.0f} out/s")
        # Beside it, and cut to what it leaves: the two are one block, and a pinned line
        # the width of the screen would push what the run is running as off the side of it.
        waiting = self._waiting_lines(max(len(line) for line in lines) + 2)
        if waiting:
            # Bottom up, both sides ending on the row above the rule: the last thing typed
            # and the running total are the two halves of where the run has got to, and one
            # of them hanging a row above the other reads as two things rather than one.
            rows = max(len(waiting), len(lines))
            lines = [""] * (rows - len(lines)) + lines
            waiting = [""] * (rows - len(waiting)) + waiting
        self.query_one("#above", Static).update(
            "[$text-muted]" + "\n".join(lines) + "[/]"
        )
        pinned = self.query_one("#queued", Static)
        pinned.set_class(bool(waiting), "waiting")
        # As content rather than as markup: this is what somebody typed, and a `[TODO]` in it
        # is a word rather than a tag. Neither escaper is safe here -- both only escape a
        # bracket that already looks like a tag to them, and the two disagree about which do.
        pinned.update(Content("\n".join(waiting)))
        for ruled in self.query(".rule").results(Static):
            ruled.update(_RULE * self.size.width)
        # Measured as drawn rather than as written: markup is not what takes up columns.
        # Textual's own, since these are Textual's markup and name its colours.
        room = self.size.width - 4 - Content.from_markup(left).cell_length
        keys = self._keys()
        while len(keys) > 1 and len(_DOT.join(keys)) > room:
            # The row is drawn against the right-hand edge, so what will not fit falls off
            # that end -- which is where the keys that change are. The ones at the front are
            # the ones that mean the same thing whenever they are pressed, so they are what
            # gives: a row that clipped `ctrl+c` to say `shift+enter newline` would be a row
            # holding the one key nobody has to be told about and losing the one they do.
            keys.pop(0)
        right = f"[$text-muted]{_DOT.join(keys)}[/]"
        gap = room - len(_DOT.join(keys))
        self.query_one("#status", Static).update(
            left + " " * max(2, gap) + right, layout=False
        )

    def _away(self, role: str) -> bool:
        """Whether one outworlder is away: as `/afk` set it, or as every one was set."""
        return self._afk_of.get(role, self._afk)

    def _away_marker(self) -> str:
        """What the status line says of being away: `afk`, the ones away, or nothing."""
        if self._afk and all(self._afk_of.values()):
            return "afk"
        away = [role for role, off in self._afk_of.items() if off]
        if self._afk:
            away = [one for one in self._outworlders if self._away(one)]
        return f"afk {', '.join(away)}" if away else ""

    def _whose(self, role: str) -> str:
        """Who holds one outworlder role: `yours`, `<name>'s`, or "" for nobody yet."""
        owner = self._claims.get(role)
        if owner is None:
            return ""
        if owner == self._me:
            return "yours"
        return f"{self._frontends.get(owner, owner)}'s"

    def _waits_on(self) -> str:
        """Who the run is waiting on to say what next, or "" where it is not waiting.

        Returns:
          `you` where this interface may answer what it waits on, the name of whoever holds
          the role asking otherwise.
        """
        listening = [one for one in self._pending if one.get("mode") == "listen"]
        if not listening:
            return ""
        if any(one.get("owner") in (None, self._me) for one in listening):
            return "you"
        owner = str(listening[0].get("owner"))
        return self._frontends.get(owner, owner)

    def _outworlder_lines(self) -> list[str]:
        """One line per outworlder of the run going, under the agents above the prompt.

        Each says it is an outworlder, whose it is to answer where somebody has claimed it,
        whether it is asking something now, and -- as an agent's does -- whether it is the
        one being read or has something unread, since what it asks is on a transcript of its
        own.
        """
        if self._run is None:
            return []
        asking = {one.get("role") for one in self._pending}
        lines: list[str] = []
        for role in self._outworlders:
            key = f"{_OUTWORLDER}{role}"
            marks = [
                role,
                "outworlder",
                *([whose] if (whose := self._whose(role)) else []),
                *(["away"] if self._away(role) else []),
                *(["asking"] if role in asking else []),
                *(
                    ["reading"]
                    if key == self._attached
                    else ["unread"]
                    if self._unread(key)
                    else []
                ),
            ]
            lines.append(escape(_DOT.join(marks)))
        return lines

    def _flowing(self) -> str:
        """What is running now, flow inside flow, for the line that names one.

        A flow may reach for another by ref and run it, so what is running is a list rather
        than a name: the one that was started, and whatever it called, innermost last. Read
        from the running tree rather than asked of the flow -- a flow may branch any way it
        likes, so what it is doing is only ever visible where it is being run.

        Returns:
          The flows, innermost last, and the one that is set up to run where none is running --
          which is what this line says with nothing going on.
        """
        return (
            " ▸ ".join(named_as(one["ref"]) for one in self._called) or self._flow_named
        )

    def _waiting_lines(self, beside: int = 0) -> list[str]:
        """What has been said to the flow and not taken yet, as the pin above the prompt.

        Behind the same `❯` the transcript marks what you said with, and dim: it is yours,
        and it has not gone anywhere yet. Held to a few lines, with the rest counted -- a pin
        that grew without limit would push the transcript off the screen to say that a lot
        was queued, which the count says in one line.

        Args:
          beside: How many columns the block to the right of it takes, which are not the
            pin's to draw in.

        Returns:
          The lines to draw, oldest first, as text rather than as markup -- a bracket
          somebody typed is a bracket, and nothing here is drawn in a colour of its own.
          Nothing at all with nothing waiting.
        """
        # What has gone to an agent went before anything still queued, the queue being
        # drained from the front, so it reads oldest first the same way the transcript does.
        held = [
            (str(one.get("agent") or ""), str(one.get("text")), self._by(one))
            for one in [*self._given, *self._queued]
        ]
        if not held:
            return []
        # One line of the pin is one row of the screen: what is over is cut with an ellipsis
        # rather than wrapped, or a pasted paragraph would be five lines and fifty rows, and
        # the transcript, the editor and the status line would all go off the bottom.
        room = max(_NARROW, self.size.width - beside - len(_YOURS) - 5)
        lines: list[str] = []
        for at, (who, said, by) in enumerate(held):
            first, *rest = said.splitlines() or [""]
            # Who has it, for a word already put to somebody: a flow drives several agents,
            # and which of them is holding your line is the half of this worth knowing. And
            # who said it, where it was not this interface: several may be saying things.
            with_it = f"{_DOT}with {short(who)}" if who else ""
            with_it += by
            # As the transcript sets one: the first line behind the marker, the rest lined
            # up under it.
            shown = [
                f"{_YOURS} {_clipped(first, room - len(with_it))}{with_it}",
                *(f"  {_clipped(line, room)}" for line in rest),
            ]
            if lines and len(lines) + len(shown) > _PINNED:
                # This one will not fit whole, so it is counted with the ones after it
                # rather than shown in half.
                lines.append(f"  … {len(held) - at} more waiting")
                return lines
            if len(shown) > _PINNED:
                # The first, and longer on its own than there is room for: what is left of
                # it is counted too, so that half a message never reads as the whole of one.
                lines.extend(shown[: _PINNED - 1])
                left = f"… {len(shown) - _PINNED + 1} more lines"
                if at + 1 < len(held):
                    left += f" and {len(held) - at - 1} more waiting"
                lines.append(f"  {left}")
                return lines
            lines.extend(shown)
            if len(lines) >= _PINNED and at + 1 < len(held):
                lines.append(f"  … {len(held) - at - 1} more waiting")
                return lines
        return lines

    def _switched(self, argv: Sequence[str], *, now: bool) -> bool | None:
        """What a switch becomes: what was asked for, or the other of what it is.

        A toggle is what you reach for at a prompt and the wrong thing to write down: a line
        that says `on` means on whichever way the switch was left, which is what anything
        replaying a session needs.

        Args:
          argv: What followed the command, which is nothing, `on`, or `off`.
          now: How the switch is set.

        Returns:
          How to set it, or None for a line that named something else -- which is said and
          left alone rather than guessed at.
        """
        said = argv[0].lower() if argv else ""
        if said in ("on", "off"):
            return said == "on"
        if said:
            self.show(f"hmz: expected 'on' or 'off', not {argv[0]!r}", "red")
            return None
        return not now

    def _keys(self) -> list[str]:
        """The keys that do something right now, said in the order they are reached for.

        Only the ones that work: a shortcut listed in a state it does nothing in is worse
        than one that is not listed at all, and there is nowhere else to look them up. What
        ctrl+c would do next is what it is called by, since it is the one key here that
        means something different for having just been pressed.
        """
        if self.query_one("#offers", OptionList).has_class("offering"):
            return ["↑↓ move", "tab select", "esc cancel"]
        keys: list[str] = []
        typed = self.query_one(Editor).text
        named = _BY_NAME.get(typed[1:].partition(" ")[0]) if typed[:1] == "/" else None
        if typed.startswith("/"):
            # A command is run whatever else is going on -- and only one that would be: a
            # line naming one that is turned down here, or none at all, is only told off.
            if (
                named is not None
                and self._view_kind() in named.where
                and not (named.refuses is not None and named.refuses(self))
            ):
                keys.append("enter run")
        elif typed:
            # Enter does nothing with nothing typed, and a key that does nothing is not one
            # to offer: what it would do next is what it is called here. In btw mode every
            # line is a side question.
            keys.append(
                "enter ask"
                if self._btw is not None
                else "enter answer"
                if self._answers_to() is not None
                else "enter send"
                if self._run is not None
                else "enter start"
            )
        if len(self._ring()) > 1:
            # Only with somewhere to step: with nothing working there is the one transcript
            # every agent is on, and a key that lands back where it started is not a key.
            keys.append("shift+tab switch view")
        keys.append("/ commands")
        keys.append("shift+enter newline")
        if not self.query_one(Editor).text:
            keys.append("← monitor")
        if self.query_one(Editor).text:
            keys.append("ctrl+c clear")
        elif self._counting():
            keys.append(
                "ctrl+c again to stop"
                if self._run is not None
                else "ctrl+c again to exit"
            )
        elif self._run is not None:
            keys.append("ctrl+c stop")
        elif self._stopping is not None:
            keys.append("ctrl+c force stop")
        else:
            keys.append("ctrl+c exit")
        return keys

    def _counting(self) -> bool:
        """Whether a ctrl+c has been pressed and the next one is still the second of it.

        Read where the keys are drawn, which is twice a second, so this is also where a
        gesture nobody finished is forgotten: a line saying what the next press does is
        wrong the moment that press would be a first press again.

        Returns:
          Whether the last press still stands.
        """
        if not self._presses:
            return False
        if time.monotonic() - self._pressed < _AGAIN:
            return True
        self._presses = 0
        return False

    def _mid_run(self, what: str) -> bool:
        """Whether a flow is still going, and says so where that is why nothing happened.

        Which is the answer for anything that would change what is running while it runs.
        A flow holds the agents it was handed and drives them by its own control flow: swapped
        underneath it, the run carries on against the ones it already has, and the interface
        starts saying it is running something it is not. Stop it, then choose.

        Still going means told to stop and not yet gone as well as running: those are two
        answers rather than one, since what to do about them differs.

        Args:
          what: The command being turned down, so that the line says which one.

        Returns:
          True if a flow is running or on its way out, having said which.
        """
        if why := self._mid_run_why(what):
            self.show(f"hmz: {why}", "red")
            return True
        return False

    def _mid_run_why(self, what: str) -> str:
        """What `_mid_run` would say, without saying it: "" with nothing going.

        Args:
          what: The command being turned down, so that the line says which one.

        Returns:
          Why it is turned down, or "" where it is not.
        """
        if self._run is not None:
            return (
                f"{what} while a flow is running: press ctrl+c twice to stop it first"
            )
        # Told to stop and not yet gone. A flow unwinds in its own time -- a loop sleeps off
        # its round, a turn is closed out -- and it writes down where it got to as it goes,
        # so a run picked up from a state that is still moving is a round done twice. And
        # `ctrl+c twice` is not the answer here: it has already been pressed.
        if self._stopping is not None:
            return f"{what} while the flow is still stopping: {_UNWINDING}"
        return ""

    def flow_running(self) -> bool:
        """Whether a flow is running, as the rows of the command table read it."""
        return self._run is not None

    def held_apart(self) -> bool:
        """Whether the runs are held by a host this interface closing leaves running."""
        return self._host is None

    def refused_stop(self) -> str:
        """Why `/stop` has nothing to do now, or "" while a flow runs for it to stop.

        A flow already told to stop is said to be stopping rather than told again: stopping
        hands the agents it is holding on to the ones on their way out, and running it over an
        empty list would hand nothing on and drop the ones already there -- which is the third
        press losing its only way to the conversations still open under their turns.

        Nothing running at all is said as well. The key never says that, because with nothing
        running it is the key that leaves and what it says is about leaving; `/stop` has only
        the one thing to mean, and a command typed on purpose that answers with nothing reads
        as a command that did not work.
        """
        if self._run is not None:
            return ""
        if self._stopping is not None:
            return f"the flow is already stopping: {_UNWINDING}"
        return "no flow is running"

    def refused_resume(self) -> str:
        """Why `/resume` cannot run now, which is a flow still going, or "" where it can."""
        return self._mid_run_why("cannot resume a run")

    def nothing_to_resume(self) -> bool:
        """Whether there was no run here to carry on, as it was last looked for.

        As it was last looked for, which is off the screen and not as the list is drawn:
        finding the run means reading the flow it was of, and reading a flow is running it.
        Looked for again whenever what it depends on may have moved -- as the interface opens,
        as a run ends, as a menu closes, as a fetch lands -- and by `/resume` itself, which is
        why this leaves it out of the list and does not turn it down: a run another terminal
        left here since is one it finds.
        """
        return bool(self._no_resume)

    def held_elsewhere(self, doing: str) -> str:
        """Why the outworlder being read is not this interface's to do something about.

        Args:
          doing: What would be done about it, said after `cannot`.

        Returns:
          Whose it is where another frontend holds it -- the runs refuse both `/claim` and
          `/afk` on a role somebody else holds -- or "" where it is this one's or nobody's,
          and anywhere but on an outworlder's transcript.
        """
        if self._view_kind() != "outworlder":
            return ""
        role = self._attached.removeprefix(_OUTWORLDER)
        whose = self._whose(role)
        if whose in ("", "yours"):
            return ""
        return f"{role} is {whose}: cannot {doing}"

    def action_monitor(self) -> None:
        """Goes up to the monitor, the run drawn, which is what `←` off an empty prompt is.

        Never refused while a flow runs: it changes nothing about the run, so there is nothing
        for it to conflict with. It answers with the view to read -- a node picked out by
        name, working or not, which is what tab is held to -- or with nothing for `→`, which
        comes back to the one that was being read.
        """
        if any(isinstance(up, Monitoring) for up in self.screen_stack):
            return  # up already, under whatever is over it
        self.push_screen(
            Monitoring(
                monitor=lambda: self._monitor,
                drawn=self._boxes,
                sessions=self._branches,
                places=self._places,
                setup=lambda: (
                    self._run.flow if self._run is not None else self._flow_named,
                    self._named_by,
                    self._in_order(),
                    self._params,
                ),
                reading=lambda: self._attached,
                board=self._board,
                outworlders=self._outworlding,
                calls=lambda: self._called,
                whose=self._whose,
                frontends=self._reading_too,
                listed=self._monitor_listed,
                opened=self._monitor_opened,
                turned=self._turns_monitor,
            ),
            self._back_from_monitor,
        )

    def _turns_monitor(self, listed: bool) -> None:  # noqa: FBT001 -- what it was turned to
        """Remembers whether the monitor draws a list, for the next time it opens.

        Args:
          listed: Whether it does.
        """
        self._monitor_listed = listed

    def _back_from_monitor(self, key: str | None) -> None:
        """Reads what was picked on the monitor, or the log that was being read.

        Args:
          key: The view picked, or None for the one that was up before.
        """
        if key is not None:
            self._now_reading(key)
        self._draw()

    def _outworlding(self) -> list[str]:
        """The outworlders of the run, each a node of the monitor of its own.

        Returns:
          Their roles, in the order the flow declares them and then as they first asked.
        """
        return list(self._outworlders)

    def _board(self) -> BoardSeen | None:
        """The board this run has, or None for one whose flow does not talk to the person.

        The person's rather than the flow's: a flow is a function that returns, and the board
        outlives any one turn of it. As the runs last said it, what is written on it put and
        taken off by asking them.

        Returns:
          The board, or None where the flow being run declares no person.
        """
        return self._boarded

    def _reading_too(self) -> list[str]:
        """Every frontend reading the runs, this one first and said to be this one.

        Returns:
          Their names, in the order they arrived, and `you` beside this interface's own.
        """
        return [
            f"{name}{_DOT}you" if client == self._me else name
            for client, name in sorted(
                self._frontends.items(), key=lambda one: one[0] != self._me
            )
        ]

    def _boxes(self) -> list[Drawn]:
        """The agents that have worked, as the monitor draws them, in the flow's own order.

        The ones that have worked rather than the ones the flow declares. A flow may declare
        ten roles and reach three of them, and seven boxes that have never done anything are
        seven rows saying nothing -- the monitor is what the run *is doing*. Each appears as
        its first turn starts and stays for the rest of the run, which is what makes this a
        picture of the run growing rather than a list of what was configured.

        Returns:
          One per agent that has taken a turn, in the order the flow declares its roles, and
          nothing at all before the first turn of a run -- which is a monitor about what is
          set up rather than about what it is doing.
        """
        shape = self._monitor.shape()
        drawn: list[Drawn] = []
        for who in self._roles_seen():
            working = any(key in self._working for key in self._of(who))
            if not (working or shape.turns.get(who, 0)):
                continue
            drawn.append(
                Drawn(
                    who=who,
                    named=who,
                    runs=self._runs_of(who).spec,
                    working=working,
                    reading=who == self._attached,
                    unread=self._unread(who),
                )
            )
        return drawn

    def _branches(self) -> list[Drawn]:
        """The sessions that have worked, as the monitor hangs them under their agents.

        Returns:
          One per session that has taken a turn, keyed `<role>/<n>`, its role's in the order
          the flow declares its roles and each role's in the order they were opened -- each
          saying which agent it is of and which environment it works in.
        """
        shape = self._monitor.shape(sessions=True)
        seen = self._roles_seen()
        return [
            Drawn(
                who=key,
                named=f"{role}{_DOT}session {at}",
                runs=self._runs_of(role).spec,
                working=key in shape.working,
                # A session read on its own where it has a log of its own, and on its role's
                # where it does not: that is the log reading it opens.
                reading=self._attached in (key, role),
                unread=self._unread(key if key in self._kept else role),
                of=role,
                env=place_key(placed) if (placed := self._placed.get(key)) else "",
            )
            for key in sorted(
                shape.turns,
                key=lambda key: (
                    seen.index(key.partition("/")[0])
                    if key.partition("/")[0] in seen
                    else len(seen),
                    int(key.partition("/")[2] or 0),
                ),
            )
            for role, _, at in [key.partition("/")]
        ]

    def _roles_seen(self) -> list[str]:
        """The roles the run has opened sessions for, in the order the flow declares them."""
        named = self._named_by
        seen = list(dict.fromkeys(one.id for one in list(self._seen.values())))
        seen.sort(key=lambda who: named.index(who) if who in named else len(named))
        return seen

    def _places(self) -> list[Placed]:
        """The environments the run's sessions work in, as the monitor hangs them under them.

        What the run said of each as it opened a session there, and what the flow declares of
        the role it fills: what it may do there and what it asks of the machine.

        Returns:
          One per environment, in the order a session first worked in it.
        """
        # The run's own, while there is one to read it off: another frontend may have started
        # a flow this one never set up, and the menu may have set up another since.
        ran = self._run or self._seen_last
        declared = {
            one.name: one
            for one in declared_places(ran.flow if ran else self._flow_named)
        }
        given = ran.envs if ran is not None else self._envs
        held: dict[str, Placed] = {}
        for key, placed in list(self._placed.items()):
            known = place_key(placed)
            was = held.get(known)
            went = str(placed.get("harness") or "")
            if was is not None:
                held[known] = was._replace(
                    sessions=(*was.sessions, key), harnesses=(*was.harnesses, went)
                )
                continue
            role = str(placed.get("role") or "")
            of = declared.get(role)
            held[known] = Placed(
                key=known,
                role=role,
                kind=str(placed.get("kind") or ""),
                target=str(placed.get("target") or ""),
                workdir=str(placed.get("workdir") or ""),
                given=given.get(role, ""),
                anchored=bool(placed.get("anchored")),
                grants=tuple(
                    sorted(
                        one.__name__.removesuffix("EnvMixin") for one in of.capabilities
                    )
                )
                if of is not None
                else (),
                needs=needs(of) if of is not None else (),
                image=of.image if of is not None else "",
                sessions=(key,),
                harness=ran.harness if ran is not None else "",
                harnesses=(went,),
            )
        return list(held.values())

    @on(Editor.Sent)
    def _sent(self, event: Editor.Sent) -> None:
        """Takes what was typed as a flow to start, as a command, or as something to say."""
        line = event.text
        # Written down whatever it turns out to be: a task, a word put into a running flow,
        # a command. All three were typed, and any of them may be worth typing again.
        self.history.add(line)
        # In btw mode every line that is not a command is one more side question: that is
        # what the mode is, and the flow is not told any of it.
        if self._btw is not None and not line.startswith("/"):
            self._said_by_you(line)
            self._btw_ask(self._btw, line)
            return
        # A `$` names the flow to run and, after it, what to run it on. Not while a question
        # is up: the next line typed is the answer to that, whatever it begins with, and an
        # agent left waiting on an answer that went off to start a flow is a stopped turn.
        if line.startswith("$") and self._answers_to() is None:
            named = _NAMED.match(line[1:])
            # The name, and then whitespace or the end of the line. Matched rather than split
            # on, so that the space after `$` is not eaten the way splitting on runs of it
            # would eat it -- `$ ls -la` names nothing -- and so that a prompt written on the
            # line under the name is the prompt rather than part of it.
            at = 1 + named.end() if named else 0
            if named and (at == len(line) or line[at].isspace()):
                # Written down as it was typed, not as its halves go back together: a prompt
                # broken under the name is two lines, and one space is not what that was.
                self._said_by_you(line)
                self._quick_flow(named.group(), line[at:].strip())
                return
        if not line.startswith("/"):
            self._said(line)
            return
        self._said_by_you(line)
        name, _, rest = line[1:].partition(" ")
        try:
            argv = shlex.split(rest)
        except (
            ValueError
        ) as error:  # an unbalanced quote is a line to correct, not a crash
            self.show(f"hmz: {error}", "red")
            return
        command = _BY_NAME.get(name)
        if command is None:
            telemetry.snag("unknown-command", length=len(name))
            self.show(f"hmz: no such command: /{name}", "red")
            return
        if (kind := self._view_kind()) not in command.where:
            named = [_VIEWED[one] for one in _VIEWED if one in command.where]
            works = " and ".join(
                [", ".join(named[:-1]), named[-1]] if len(named) > 1 else named
            )
            self.show(
                f"hmz: /{name} is only available on {works}, not on {_VIEWED[kind]}",
                "red",
            )
            return
        # And only while there is something for it to do, which is when it is offered. Said
        # rather than done, and in the words the command would have used: a command typed out
        # while it is not offered is somebody asking why not.
        if command.refuses is not None and (why := command.refuses(self)):
            self.show(f"hmz: {why}", "red")
            # Nor is a press made before it left standing: a line typed in between is two
            # gestures, and the press after it is a first press -- not one that leaves.
            self._presses = 0
            self._draw()
            return
        command.does(self, argv)

    def action_afk(self, argv: Sequence[str] = ()) -> None:
        """Says whether anybody is here to be asked, and marks the status line with it.

        On an outworlder's own transcript it is that outworlder alone; anywhere else it is
        every one of them this interface may answer for, as one switch -- the ones set apart
        from it included, and the ones another frontend holds left as that one left them. It
        is the runs' to hold rather than this interface's, so it outlives this interface.

        Args:
          argv: What was written after the name, which is `on`, `off`, or nothing at all.
        """
        if self._view_kind() == "outworlder":
            role = self._attached.removeprefix(_OUTWORLDER)
            if (switched := self._switched(argv, now=self._away(role))) is None:
                return
            said = (
                f"away as {role}: agents that ask are told nobody is here"
                if switched
                else f"here as {role}: agents may stop and ask you"
            )
            self._asks("afk", then=lambda _: self._says(said), on=switched, role=role)
            return
        now = self._afk and all(self._afk_of.values())
        if (switched := self._switched(argv, now=now)) is None:
            return
        said = (
            "away: agents that ask are told nobody is here"
            if switched
            else "here: an agent may stop and ask you"
        )
        # Said once in the transcript and from then on in the status line: a line that has
        # scrolled away is not how somebody finds out that an agent may not reach them.
        self._asks("afk", then=lambda _: self._says(said), on=switched)

    def action_claim(self, argv: Sequence[str] = ()) -> None:
        """Holds the outworlder being read for this interface alone, or gives it back.

        A role claimed is answered here and nowhere else: what it asks is this interface's to
        answer, and another reading the same runs is refused it until this one gives it back
        or goes. Claiming is about answering and nothing else -- anybody may still say
        anything to the agents.

        Args:
          argv: What was written after the name, which is `on`, `off`, or nothing at all.
        """
        role = self._attached.removeprefix(_OUTWORLDER)
        mine = self._claims.get(role) == self._me
        if (switched := self._switched(argv, now=mine)) is None:
            return
        if switched:
            said = f"only you can answer for {role}"
            self._asks("claim", then=lambda _: self._says(said), role=role)
        else:
            said = f"anyone can answer for {role}"
            self._asks("release", then=lambda _: self._says(said), role=role)

    def _says(self, said: str) -> None:
        """Says something that happened, quietly, and redraws what it changed."""
        self.show(f"[dim]{escape(said)}[/dim]")
        self._draw()

    def action_btw(self, question: str = "") -> None:
        """Enters btw mode, asks in it, or leaves it, which is what `/btw` is.

        A side question must never become a steer. In a session's view it goes to a
        read-only fork of that session where its CLI can fork one, and otherwise to a
        read-only, skill-free copy of the same agent seeded from a snapshot -- ended sessions
        included. In the transcript every agent is on, or on the monitor, it goes to the btw
        agent, which may ask any session's side conversation in turn. Either way the flow's
        own sessions carry on untouched on their own threads.

        Once in, every line typed is one more turn of the same side conversation, until
        `/btw` on its own or esc leaves it and closes what it opened.

        Args:
          question: What to ask, without the ``/btw`` command name, or "" to enter or leave.
        """
        question = " ".join(question.split())
        mode = self._btw
        if mode is None:
            mode = self._enter_btw()
            if mode is None:
                return
        elif not question:
            self._leave_btw()
            return
        if question:
            self._btw_ask(mode, question)

    def _btw_target(self) -> str:
        """Who a side question here goes to: a session's view key, or "" for the btw agent.

        Returns:
          `<role>/<n>` for a session, the newest of a role's where the view is the role's
          own, and "" for the aggregate, the monitor and an outworlder's view.
        """
        if self._view_kind() != "session":
            return ""
        key = self._attached
        if "/" in key:
            return key
        keys = [held for held in self._btw_sessions() if held.startswith(f"{key}/")]
        return keys[-1] if keys else ""

    def _btw_sessions(self) -> list[str]:
        """Every conversation of this run or the last, keyed as the views name them.

        The key its transcript and its node go by, so that a side question asked of
        `builder/2` is asked of the conversation `builder/2` shows.

        Returns:
          `<role>/<n>` apiece, `n` counting a role's from 1, and the person's left out --
          theirs is this prompt.
        """
        return list(self._seen)

    def in_btw(self) -> bool:
        """Whether btw mode is on, as the rows of the command table read it."""
        return self._btw is not None

    def refused_btw(self) -> str:
        """Why btw mode cannot be entered here, or "" where it can -- and always to leave it.

        Returns:
          Why there is nobody to ask: the conversation on the screen gone, or no agent to
          ask at all.
        """
        if self._btw is not None:
            return ""
        target = self._btw_target()
        if target:
            if target not in self._btw_sessions():
                return f"/btw: no conversation found for {target}"
        elif not (self.settings.btw or self._btw_sessions() or self._models):
            return "/btw requires a coding agent"
        return ""

    def _enter_btw(self) -> _Btw | None:
        """Starts btw mode against whatever is on the screen, saying so."""
        if why := self.refused_btw():
            self.show(f"hmz: {why}", "red")
            return None
        target = self._btw_target()
        mode = _Btw(target)
        with self._btw_lock:
            self._btw = mode
        self.show(
            f"[cyan]btw · {escape(target or 'btw agent')}[/] [dim]each line is "
            "a question; /btw or esc to exit[/dim]"
        )
        self._draw()
        return mode

    def leaves_btw(self) -> bool:
        """Leaves btw mode, for esc, answering whether there was one to leave."""
        if self._btw is None:
            return False
        self._leave_btw()
        return True

    def _leave_btw(self, because: str = "") -> None:
        """Leaves btw mode, closing every side conversation it opened.

        Args:
          because: Why, where it was not asked for, or "" for `/btw` or esc.
        """
        self._close_btw()
        self.show(f"[dim]btw: exited{f' -- {because}' if because else ''}[/dim]")
        self._draw()

    def _close_btw(self) -> None:
        """Closes the side conversations without touching any flow session."""
        with self._btw_lock:
            mode, self._btw = self._btw, None
            held = list(mode.sides.values()) if mode is not None else []
            if mode is not None:
                mode.sides.clear()
        # Asked of the runs, which hold them; and nothing to ask on the way out, since this
        # interface going is every side conversation it opened going with it.
        if not self._quitting:
            for side in held:
                self._asks("unaside", quiet=True, side=side)

    def _btw_ask(self, mode: _Btw, question: str) -> None:
        """Puts one more question to btw mode's side conversation, on a thread of its own.

        Args:
          mode: The btw mode it is asked in.
          question: What was asked.
        """
        if mode.busy:
            self.show("hmz: btw is still answering the last question", "red")
            return
        try:
            snapshot = self._btw_snapshot()
        except Exception as why:  # noqa: BLE001 -- an observation failure must not break the UI
            self.show(f"hmz: /btw could not read flow progress: {why}", "red")
            return
        mode.busy = True
        worker = threading.Thread(
            target=self._run_btw,
            args=(mode, question, snapshot),
            daemon=True,
            name="humanize-btw",
        )
        try:
            worker.start()
        except RuntimeError as why:
            mode.busy = False
            self.show(f"hmz: /btw could not start: {why}", "red")

    def _btw_snapshot(self) -> FlowSnapshot:
        """Copies the current run into a prompt-sized, immutable observation."""
        shape = self._monitor.shape()
        # One per role, however many sessions it opened: a role is what is watched, and each
        # of its sessions is an agent of its own named for it.
        driven = {seen.id: seen for seen in list(self._seen.values()) if seen.id}
        agents = tuple(
            AgentProgress(
                agent=who,
                model=seen.model,
                turns=shape.turns.get(who, 0),
                working=who in shape.working,
                role=who,
            )
            for who, seen in driven.items()
        )
        handovers = tuple(
            sorted(
                (sender, receiver, count)
                for (sender, receiver), count in shape.handovers.items()
                if count > 0
            )
        )
        with self._btw_lock:
            observations = tuple(self._btw_events)
        waiting = len(self._queued) + len(self._given)
        moment = time.monotonic()
        ended = self._monitor.until
        elapsed = (ended if ended is not None else moment) - self._monitor.began
        spent = tuple(
            (entry.model, entry.tokens, entry.rate, entry.dollars)
            for entry in self._monitor.spending(now=ended or moment)
        )
        # Beside it rather than inside it: the kinds are the run's rather than any one
        # model's, a bill being made of them whichever model bought them, and each says
        # whether the figure is the whole of what went on that kind or a floor under it.
        counted = tuple(
            (one.kind, one.tokens, one.whole)
            for one in self._monitor.reckoning(now=ended or moment)
        )
        # What the btw agent may ask by key: each conversation, and whether it is going.
        sessions = tuple(
            (
                key,
                (
                    "working"
                    if key in self._working
                    else "idle"
                    if self._run
                    else "ended"
                )
                + f", model={seen.model or '(default)'}",
            )
            for key, seen in list(self._seen.items())
        )
        return FlowSnapshot(
            flow=self._flowing(),
            task=self._flow_task,
            workspace=_where(),
            elapsed=elapsed,
            finished=self._run is None,
            agents=agents,
            handovers=handovers,
            observations=observations,
            waiting=waiting,
            spent=spent,
            kinds=counted,
            waiting_for_input=bool(self._waits_on()),
            sessions=sessions,
        )

    def _btw_source(self) -> dict[str, str] | None:
        """What the btw agent is opened as: the one `/settings` names, or the flow's first.

        Returns:
          What to open a side conversation with -- `runs`, an agent as `-a` spells one, or
          `key`, one of the run's conversations to copy the agent of -- or None where there
          is nothing set up to open one as.
        """
        from hmz.runtime.kept import written

        said = read_back(self.settings.btw) if self.settings.btw else None
        if said is not None:
            return {"runs": written(said)}
        # The first the flow declares, as it is running where it has run.
        ran = self._btw_sessions()
        for role in self._named_by:
            if held := [key for key in self._of(role) if key in ran]:
                return {"key": held[0]}
            if (runs := self._runs_of(role)).spec:
                return {"runs": written(runs)}
        return {"key": ran[0]} if ran else None

    def _btw_kept(self, mode: _Btw, key: str, side: str) -> str:
        """Holds a side conversation on btw mode, or closes it for a mode that has gone.

        Args:
          mode: The btw mode it was opened for.
          key: The session it is about, or "" for the btw agent's own.
          side: The side conversation, as the runs number it.

        Returns:
          The side conversation, held.

        Raises:
          _BtwLeft: If btw mode was left while it was being opened.
        """
        with self._btw_lock:
            if self._btw is mode:
                mode.sides[key] = side
                return side
        self._asks("unaside", quiet=True, side=side)
        raise _BtwLeft

    def _aside(self, side: str, prompt: str) -> str:
        """One turn of a side conversation: what it answered to a prompt.

        Args:
          side: The side conversation, as the runs number it.
          prompt: What to say to it.

        Returns:
          Its answer.
        """
        return str(self._link.aside(side=side, prompt=prompt).get("answer") or "")

    def _btw_turn(
        self, mode: _Btw, key: str, question: str, snapshot: FlowSnapshot
    ) -> str:
        """One turn of one session's side conversation, opening it the first time.

        A fork of the session where its CLI forks, carrying its history, and a copy of its
        agent seeded from the snapshot where it cannot, or where the fork will not open --
        which of the two the runs opened is what they say back.

        Args:
          mode: The btw mode it is asked in.
          key: The session, as `<role>/<n>`.
          question: What was asked.
          snapshot: The flow, frozen when the question was.

        Returns:
          What the side conversation answered.
        """
        side = mode.sides.get(key)
        if side is not None:
            return self._aside(side, format_turn(question))
        if key not in self._btw_sessions():
            return f"(session {key} not found)"
        opened = self._link.aside(key=key, fork=True)
        side = self._btw_kept(mode, key, str(opened["side"]))
        if opened.get("forked"):
            try:
                if answer := self._aside(side, format_forked(key, question)):
                    return answer
            except Exception:  # noqa: BLE001, S110 -- the copy below is what is left to try
                pass
            # A fork that opened and would not answer: a copy of its agent is asked instead.
            with self._btw_lock:
                if mode.sides.get(key) == side:
                    del mode.sides[key]
            self._asks("unaside", quiet=True, side=side)
            side = self._btw_kept(mode, key, str(self._link.aside(key=key)["side"]))
        role = key.rpartition("/")[0]
        about = replace(
            snapshot,
            observations=tuple(
                one for one in snapshot.observations if one.agent in (role, "")
            ),
            sessions=(),
        )
        return self._aside(side, format_snapshot(about, question, about=key))

    def _btw_agent_turn(self, mode: _Btw, question: str, snapshot: FlowSnapshot) -> str:
        """One turn of the btw agent, carrying out whatever it asks of the sessions.

        Args:
          mode: The btw mode it is asked in.
          question: What was asked.
          snapshot: The flow, frozen when the question was.

        Returns:
          Its answer to the person, with no `@ask` left in it.
        """
        side = mode.sides.get("")
        if side is None:
            source = self._btw_source()
            if source is None:
                return ""
            side = self._btw_kept(mode, "", str(self._link.aside(**source)["side"]))
            prompt = format_snapshot(snapshot, question)
        else:
            prompt = format_turn(question)
        hops = 0
        while True:
            asks, answer = asked(self._aside(side, prompt))
            if not asks or hops >= HOPS:
                return answer
            answers: list[tuple[str, str]] = []
            for key, asking in asks[: HOPS - hops]:
                hops += 1
                self._on_screen(
                    self.show,
                    f"[dim]btw · asking {escape(key)}: "
                    f"{escape(compact(asking, 120))}[/dim]",
                )
                try:
                    said = self._btw_turn(mode, key, asking, snapshot)
                except _BtwLeft:
                    raise
                except Exception as why:  # noqa: BLE001 -- told back rather than raised
                    said = f"(could not ask: {why})"
                answers.append((key, said or "(no answer)"))
            prompt = format_answers(answers, more=hops < HOPS)

    def _run_btw(self, mode: _Btw, question: str, snapshot: FlowSnapshot) -> None:
        """Runs one side turn and posts only its final display event."""
        answer = failure = ""
        try:
            if mode.target:
                answer = self._btw_turn(mode, mode.target, question, snapshot)
            else:
                answer = self._btw_agent_turn(mode, question, snapshot)
            failure = "" if answer else "the agent returned no answer"
        except _BtwLeft:
            pass
        except Exception as why:  # noqa: BLE001 -- a backend may fail independently
            failure = str(why) or type(why).__name__
        finally:
            mode.busy = False
        with self._btw_lock:
            if self._btw is not mode:
                return
        if answer:
            self._on_screen(self._btw_answer, question, answer)
        else:
            self._on_screen(self._btw_failed, question, failure)

    def _btw_answer(self, question: str, answer: str) -> None:
        """Shows a completed side answer, in cyan, in the current transcript."""
        lines = escape(answer).splitlines() or [""]
        self._part(
            None,
            "\n".join(
                [
                    (
                        f"[cyan]{_SAID}[/] [dim]btw · {escape(question)}[/] "
                        f"[cyan]{lines[0]}[/]"
                    ),
                    *(f"  [cyan]{line}[/]" for line in lines[1:]),
                ]
            ),
            packs=False,
        )
        self._draw()

    def _btw_failed(self, question: str, failure: str) -> None:
        """Reports a side-question failure without reporting it as a flow failure."""
        del question  # The question itself is already in the transcript.
        self.show(f"hmz: /btw: {failure}", "red")

    def action_clear(self) -> None:
        """Clears the screen, and nothing else.

        There is nothing else for it to clear. A turn carries no context across an epic: a
        flow is handed agents that were made for that run and drops them at the end of it, so
        what is on screen is the whole of what starting over would have thrown away. What is
        running is left running, and what it has done so far is still beside it.

        The screen is one transcript, so what is cleared is that one: clearing every agent's
        would be `/clear` reaching into ones nobody was looking at.
        """
        kept = self._keeping(self._attached)
        kept.lines.clear()
        # And what it was in the middle of saying, which is gone with the lines it was said
        # against: the next part opens its own, and the next agent to speak on the one they
        # all appear on says which agent it is rather than running on from a name nobody can
        # see any more.
        kept.packed, kept.spoke = False, ""
        self.query_one("#transcript", Transcript).clear()
        self._welcome()  # a cleared screen is a screen just opened, and one opens with this
        self._draw()

    def action_stop(self) -> None:
        """Stops the flow on a line typed rather than a key pressed, and asks once for it.

        The key asks twice because a day's work is behind a key that a finger also lands on
        by mistake. Nothing is typed by mistake: writing `/stop` out and sending it is the
        deliberation the second press stands in for, so asking again would be a question with
        one answer.

        Reached only while a flow runs: with none, or with one already stopping, the command
        is not offered and a line naming it is turned down saying which (`refused_stop`).

        The count of presses goes back to nothing, which is what the second press does after
        it stops a flow. A `/stop` is not a press and must not be counted as one -- but
        neither may it leave a press made before it standing, or the press made after it
        would be the second of a gesture the command interrupted.
        """
        self.action_stop_flow()
        self._presses = 0
        self._draw()  # rather than at the next tick: it was just typed

    def action_stop_flow(self) -> None:
        """Stops the whole flow, not just the turn -- which is the second ctrl+c or `/stop`.

        The turn running now is interrupted and every call of the flow unwinds from where it
        stands, closing what it opened -- for every frontend reading it, since there is one
        run however many are reading. It is let go of here rather than when the runs say so,
        so that the press after this one is the one that does not wait for it to unwind.

        Silent when nothing is running, every caller having its own answer for that: the key
        is mid-gesture and the press after it says what it does, a flow chosen while none runs
        has nothing to say about the one that was not there, and `/stop` looks before it calls
        this and says for itself that there was nothing to stop.
        """
        run = self._run
        if run is None:
            return
        self._run, self._stopping = None, run.number
        self._asks("stop")

    def on_unmount(self) -> None:
        """Lets go of the runs as the interface goes, however it goes.

        Runs held in this process go with it -- nothing else would ever close them -- and
        runs a host holds are left to it and whoever else is reading them. Said to nobody
        rather than to the transcript, which has gone with everything else.
        """
        self._quitting = True
        self._close_btw()
        if self._linked is not None:
            self._linked.close()
        if self._host is not None:
            self._host.close()
        self._requests.put(None)

    def _asks(
        self,
        do: str,
        then: Callable[[dict[str, Any]], object] | None = None,
        *,
        refused: Callable[[], object] | None = None,
        quiet: bool = False,
        **said: Any,
    ) -> None:
        """Asks the runs one thing, off the event loop, in the order things were asked.

        One thread asks every request in turn: a request may take as long as what it asks
        does -- a flow is imported to start it -- and two lines typed one after the other
        must reach the run in that order. What it answers is drawn once it has; a refusal is
        said in red, in the words the runs refused it in.

        Args:
          do: What to ask.
          then: What to do with the answer once it has come, on the screen, or None.
          refused: What to do once it has been refused, on the screen, or None.
          quiet: Whether a refusal is to go unsaid, for one that only says it was already so.
          said: What that takes.
        """
        self._requests.put(({"do": do, **said}, then, refused, quiet))

    def _requested(self) -> None:
        """Asks every request put in, in order, until the interface goes: the one thread."""
        while (asked := self._requests.get()) is not None:
            request, answered, refused, hushed = asked
            try:
                answer = self._link.asked(request)
            except Exception as why:  # noqa: BLE001 -- a refusal, or runs gone: said either way
                if not hushed:
                    self._on_screen(self.show, f"hmz: {why}", "red")
                if refused is not None:
                    self._on_screen(cast("Callable[..., None]", refused))
                continue
            if answered is not None:
                self._on_screen(cast("Callable[..., None]", answered), answer)

    @work
    async def action_flow(self, named: str = "") -> None:
        """Opens the flow menu: which flow runs, and what each of its agents is.

        One menu walked into rather than a sheet per question: the flows, and the agents of
        the one that is opened. Nothing in it is applied until it is saved on the way out, so
        opening it to look at the flows and walking back out again leaves the interface
        exactly as ready to be typed at as it was.

        Not refused while a flow runs. Choosing one is not offered then -- a flow is chosen in
        order to be started, and there is one going -- so it opens inside the agents of the
        flow that is going, that being where somebody halfway through a run finds out that an
        agent is thinking too little or is allowed too much.

        Args:
          named: A flow of your own, as a path, to open the menu already holding.
        """
        running = self._run is not None
        if named and running:
            self.show("hmz: cannot choose a flow while one is running", "red")
            return
        chosen = await self._chooses(named, running=running)
        if chosen is None:
            return  # walked out without saving, which changes nothing at all
        self._took_flow(chosen, running=running)

    async def _chooses(self, named: str, *, running: bool) -> Chosen | None:
        """Puts the flow menu up and answers with whatever it was saved holding.

        Called from a worker, since it waits on a sheet: `/flow` opens it to be answered, and
        a `$` naming a flow this workspace has never set up opens it for the same reason --
        one menu either way, so that a flow is set up in one place however it was reached for.

        Args:
          named: A flow to open the menu already holding, or "" for the one in force.
          running: Whether a flow is running, which is what takes the flows away.

        Returns:
          The flow, what its roles are given and how the flow itself is set up, or None for a
          menu walked out of -- which changes nothing at all.
        """
        # Opened whether or not there is a backend to run one on: which flow to run is worth
        # reading either way, and the sheet an agent is set up on says for itself that there
        # is nothing installed to set it up as.
        agents = installed()
        unavailable = installable()
        agents.update(unavailable)
        # What is in hand is what is in hand for the flow the interface is set up on. A menu
        # opened straight into another flow is handed none, and reads what that one was last
        # set up with here -- which is what turning to it would have read.
        holding = not named or named == self._flow_named
        return await self.push_screen_wait(
            Flows(
                named or self._flow_named,
                self._models if holding else {},
                self._params if holding else None,
                agents,
                self.settings.flows(),
                envs=self._envs if holding else None,
                budget=self._budget if holding else None,
                harness=self._harness if holding else None,
                # What the run going found, while it is a run of this flow: its record says
                # nothing until each session's first turn, and the menu reads the record else.
                harnessed=self._harnessed
                if holding
                and self._run is not None
                and self._run.flow == self._flow_named
                else None,
                unavailable=frozenset(unavailable),
                running=running,
                # A flow that was named has been chosen, so what is left to answer is what
                # drives it -- and one named as a path is not in the list to choose from at
                # all, so a menu that opened on that list would be offering to undo it.
                inside=bool(named),
            )
        )

    @work
    async def _quick_flow(self, named: str, task: str) -> None:
        """Starts one flow on what was typed after its name, setting it up first if it needs to.

        The whole of what `$ralph_loop fix the build` is: that flow, said that. A
        flow this workspace has already set up runs on the spot -- the menu would be answers
        already given -- and one it has not opens that menu inside it, holding the line that
        was typed until it is saved, since a flow nobody has answered for is a flow with no
        agents to run on.

        Args:
          named: The flow, by the name it is offered under.
          task: What to start it on, or "" for a `$` that named a flow and said nothing after
            it -- which is choosing that flow and no more, there being nothing to start on.

        Note:
          The line is already in the transcript: it went down as it was typed, before this.
        """
        if not any(one.name == named for one in self.hmz.flows.all()):
            # Said the way `/nosuchcommand` is: the sigil was meant, and the name after it is
            # the half to correct. A path is not one of the answers -- it would swallow the
            # prose after it -- so `/flow` is where a flow of your own by path is reached.
            telemetry.snag("unknown-flow", length=len(named))
            self.show(f"hmz: no such flow: {named}", "red")
            return
        if self._run is not None:
            # The same answer `/flow <name>` gives while one runs, since it is the same thing
            # being asked for: two ways of choosing a flow that did opposite things would be
            # one of them ending a day's work on a line meant to queue the next one up.
            self.show("hmz: cannot choose a flow while one is running", "red")
            return
        chosen = self._remembered_for(named)
        if chosen is None:
            chosen = await self._chooses(named, running=False)
            if chosen is None:
                # Walked out of the menu, so nothing was chosen and nothing runs. Said, or a
                # line that was typed to start something would have vanished without a word.
                self.show("[dim]flow not set up; nothing started[/dim]")
                return
        self._took_flow(chosen, running=False, starting=task)

    def _remembered_for(self, flow: str) -> Chosen | None:
        """What one flow would run as here, or None for one this workspace must be asked about.

        Args:
          flow: The flow, by the name it is offered under.

        Returns:
          The flow, what its roles are given and how it is set up -- exactly what the menu
          would have been saved holding -- or None for a flow to put that menu up about: one
          this workspace has never set up, one that has grown, lost or renamed a role since
          it last was, one whose kept params no longer read back through the model it
          declares now, and one given no budget that needs one. A settings file is a
          convenience, and one that no longer fits the flow is a question to ask again rather
          than a run to start on half an answer.
        """
        declared = declared_of(flow)
        agents = self.settings.agents(flow)
        envs = self.settings.envs(flow)
        if declared is None:
            # A flow that will not load says nothing about what it declares, so nothing here
            # can tell whether it is set up. Running it is where that is said, exactly as it
            # is for the flow already in force.
            return Chosen(
                flow,
                agents,
                envs,
                budget=budget_of(flow),
                harness=self.settings.harness(flow),
            )
        if set(agents) != set(declared.roles):
            return None
        if any(role.required and role.name not in envs for role in declared.envs):
            return None
        written_ = self.settings.params(flow)
        params = params_of(flow, written_)
        if written_ and params is None and params_model(flow) is not None:
            # Set up with params this flow no longer accepts, which is one that has dropped,
            # renamed or retyped a param since. Nothing here can guess what the answer that no
            # longer reads was meant to say, so it is asked where it is asked.
            return None
        budget = budget_of(flow)
        if budget is None and not declared.unbounded:
            return None
        return Chosen(flow, agents, envs, params, budget, self.settings.harness(flow))

    def _took_flow(self, chosen: Chosen, *, running: bool, starting: str = "") -> None:
        """Applies what the flow menu was saved with, and writes it down.

        Args:
          chosen: The flow, what its roles are given, and how the flow itself is set up.
          running: Whether a flow was running when the menu opened, which is what decides
            between starting fresh and changing the agents under a run.
          starting: What to start the flow on now that it is set up, for a `$` line that
            named the flow and said what to do in one go, or "" to leave it waiting to be
            told -- which is what every other way of choosing a flow leaves it doing.
        """
        import json

        same = (
            chosen.flow,
            chosen.agents,
            chosen.envs,
            chosen.params,
            chosen.budget,
            chosen.harness,
        ) == (
            self._flow_named,
            self._models,
            self._envs,
            self._params,
            self._budget,
            self._harness,
        )
        if chosen.flow != self._flow_named:
            self._harnessed = {}
        # Nothing running is stopped for it: a run another frontend started while the menu
        # was up is theirs as much as anybody's, and starting this one is refused while it
        # goes rather than ending it. Read again whether or not it is the same flow: a fetch
        # or an edit since may have given it roles the menu was just saved with.
        self._declared = declared_of(chosen.flow)
        self._flow_named = chosen.flow
        self._models, self._envs = dict(chosen.agents), dict(chosen.envs)
        self._params, self._budget = chosen.params, chosen.budget
        self._harness = chosen.harness
        self.settings.remember(
            chosen.flow,
            self._models,
            self._envs,
            # As JSON, which is what a settings file holds and reads back through the model.
            json.loads(chosen.params.model_dump_json())
            if chosen.params is not None
            else None,
            # And a budget of nothing written down as nothing, which is how a flow that
            # needs none is told apart from one that was given one.
            json.loads(chosen.budget.model_dump_json())
            if chosen.budget is not None
            else {},
            chosen.harness,
        )
        if running:
            self._reconfigured()
        elif not same and not starting:
            self.show("[dim]enter a task to start the flow[/dim]")
        self._draw()
        if starting:
            # Said already, `$` and all, so it starts rather than being written down twice.
            self._starts(starting)

    def _reconfigured(self) -> None:
        """Says what becomes of agents changed under a run that is going.

        A run is handed a driver per role as it starts -- the CLI, the account, the model and
        the effort -- and every session of that role is opened on it for as long as the run
        goes. Nothing under a running flow can be swapped for another without the flow
        noticing, so what was changed is written down and is what the next run starts on.
        """
        self.show(
            "[dim]the current run keeps its original roles; changes will apply "
            "to the next run[/dim]"
        )

    @work
    async def _asks_about_reports(self) -> None:
        """Asks, once, whether humanize reports its own failures.

        Only where nobody has been asked yet, and only here: the interface is the one thing
        humanize has that has somebody at it. A headless run reports if this was answered yes
        and is silent otherwise -- silence is not consent, and a question nobody is there to
        answer is a run that has stopped.

        Left unanswered by esc, which is asked again next time rather than taken as a no. And
        what the interface knows about the machine is said here either way, so that a report
        made later carries it: registered rather than gathered, so nothing is looked at on a
        machine that reports nothing.
        """
        telemetry.about("machine", _machine)
        if telemetry.enabled() is not None:
            telemetry.start()
            return
        said = await self.push_screen_wait(Reports())
        if said is None:
            return  # asked again next time: walking away is not an answer
        telemetry.asked(enable_sentry=said == "on")
        self.show(
            "[dim]error reporting enabled; use /settings to turn it off[/dim]"
            if said == "on"
            else "[dim]error reporting disabled; use /settings to turn it on[/dim]"
        )

    def action_settings(self, page: str = "") -> None:
        """Opens every setting humanize has, which is what `/settings` is for.

        Six pages: what is true of this machine, what is remembered about this workspace,
        the accounts agents run as, the machines environments go on, where a turn goes when
        it cannot run, and where flows come from -- opened on the screen of them all, or
        inside the one named, so that the page somebody came for is not a walk away. Not
        refused while a flow runs -- what lands at once does not touch what is running, and
        what does not says when it will. What it was answered with comes back as a message
        rather than to here, since the flow menu opens it too.

        Args:
          page: Which page to open inside, by its name, or "" for none of them.
        """
        opens = page_of(page) if page else None
        if page and opens is None:
            self.show(
                f"hmz: /settings has no page {page!r}: choose "
                f"{', '.join(_PAGES[:-1])} or {_PAGES[-1]}",
                "red",
            )
            return
        agents = installed()
        unavailable = installable()
        agents.update(unavailable)
        self.push_screen(
            Adjusts(agents, page=opens, unavailable=frozenset(unavailable))
        )

    @on(Adjusts.Settled)
    def _took_settings(self, event: Adjusts.Settled) -> None:
        """Does what the settings menu was holding, at once wherever it can be done at once.

        Args:
          event: What it answered with: only what was changed, and what the pages that
            write for themselves did.
        """
        said = event.said
        for one in said.told:
            self.show(one)
        if said.enable_sentry is not None:
            # Through the same road the first-start question takes, so that the answer is
            # written down, what was read is forgotten, and reporting starts or stops now
            # rather than at the next start.
            telemetry.asked(enable_sentry=said.enable_sentry)
            self.show(
                "[dim]error reporting enabled[/dim]"
                if said.enable_sentry
                else "[dim]error reporting disabled[/dim]"
            )
        if said.details is not None:
            self.settings.detailing(on=said.details)
            self._details = said.details
            self.show(
                "[dim]showing details: tool calls, thinking, and backend output[/dim]"
                if said.details
                else "[dim]showing turn responses only, without details[/dim]"
            )
            self._draw()  # and the status line says which mode this is in from now on
        if said.profile is not None:
            self.settings.profiles(on=said.profile)
            # Read as a run starts, so one running now carries on as it started.
            self.show(
                (
                    "[dim]runs will profile started programs from the next flow "
                    "run; /epics collects the trace[/dim]"
                )
                if said.profile
                else (
                    "[dim]runs will be traced and not profiled from the next flow "
                    "run[/dim]"
                )
            )
        if said.btw is not None:
            self.settings.btw = said.btw
            # Not the one open now: a side conversation is one agent from its first turn on.
            self.show(
                "[dim]/btw will ask "
                f"{escape(said.btw or "the flow's first agent")} about the "
                "whole flow next time you enter btw mode[/dim]"
            )
        if said.forget and self.settings.forget():
            # What this interface opened on is already in hand, so it is the next one that
            # opens without it.
            self.show(
                "[dim]cleared saved settings for this directory; humanize will "
                "open without them on next launch[/dim]"
            )

    @work
    async def action_epics(self) -> None:
        """Opens the runs of this directory, which is what `/epics` is for.

        Every run of a flow here, newest first: what it was and how it went, with enter
        going into one. Read while a flow runs -- what has already happened does not change
        under one -- but a run picked up is a flow started, so that half is refused while one
        is going, on the sheet where it was asked for. Whether one is going is asked there
        rather than handed over, since this list outlives the run it was opened during.
        """
        said = await self.push_screen_wait(Epics(running=lambda: self._run is not None))
        # Whatever was done there -- a run taken away, a run exported -- the last run here
        # may be another one now.
        self._looks_for_resume()
        if said is None:
            return
        for one in said.said:
            self.show(one)
        if said.doing == RESUMES and said.epic is not None:
            self._carries_on(said.epic)

    def action_resume(self, argv: Sequence[str] = ()) -> None:
        """Carries the last run here of a flow that can be picked up on: what `/resume` is for.

        `/epics` already offers this of whichever run you go into, and needing to find that
        row is the whole of what is wrong with it: a loop is left running overnight, the
        machine goes down, and what somebody who comes back to a stopped one wants is the
        work carried on rather than a list to look for it in. So this is the last run here of
        a resumable flow and no other -- a conversation had since is not a run to carry on,
        and there is nothing to choose, which is why it is a command rather than a row -- and
        a run that cannot be carried on says why rather than quietly handing the one before
        it over: a loop resumed from the day before yesterday because yesterday's died early
        is a day's work thrown away without anybody being told.

        Args:
          argv: Whatever was typed after the command, which is nothing: said back rather
            than dropped, since a run named here and quietly ignored would be somebody
            watching a different run start than the one they asked for.
        """
        if argv:
            self.show(
                "hmz: /resume takes no arguments: it resumes the last run "
                "here; use /epics to choose another run",
                "red",
            )
            return
        # Looked for again rather than taken from what the list was drawn from: that is as
        # it was, and this is somebody asking about now.
        # And what it finds is what the list goes by from now, over anything still looking.
        self._resume_looks += 1
        epic, ran, self._no_resume = self._last_run()
        if epic is None:
            self.show(f"hmz: {self._no_resume}", "red")
            return
        self._carries_on(epic, ran)

    def _last_run(self) -> tuple[Path | None, Ran | None, str]:
        """The last run here that `/resume` would carry on, or why there is none.

        Past every run of a flow that neither was nor is one to pick up -- a conversation had
        since -- and no further: a run of one that was or is, or a record that cannot be
        read, is the one this settles on, and says for itself what stands in its way.

        Returns:
          The run, by the directory it is written in, what it was, and "" -- or None, None
          and why not, in the words `/resume` says it in.
        """
        epics = self.hmz.epics
        runs = epics.all()  # oldest first, so the last of them is the last run
        if not runs:
            return (
                None,
                None,
                "no flow has been run here, so there is nothing to resume",
            )
        for epic in reversed(runs):
            ran = epics.read(epic)
            if ran is None or ran.resumable or self._picks_up(ran.flow):
                break
        else:
            return (
                None,
                None,
                (
                    "no run here was of a flow that can be resumed, so there is nothing "
                    "to resume"
                ),
            )
        # Why a run cannot be carried on is settled in one place for both ways in, so that a
        # run walked into on `/epics` is turned down for the same reasons in the same words.
        ran, why = self._unresumable(epic)
        return (None, None, why) if why else (epic, ran, "")

    @work(group="resume", exclusive=True)
    async def _looks_for_resume(self) -> None:
        """Looks for the run `/resume` would carry on, off the screen, for the list to offer it.

        Off the screen because finding it reads the flow it was of, and reading a flow is
        running it. Whatever it finds is what the list goes by until it is looked for again.
        Only the list: a line naming the command looks again for itself, since what this
        found may be from before a run somebody else started here.

        And only if nothing looked since it began: a look that took longer than a later one
        found out less.
        """
        self._resume_looks += 1
        looking = self._resume_looks
        try:
            *_, why = await asyncio.to_thread(self._last_run)
        except Exception as failed:  # noqa: BLE001 -- a store that cannot be read is said on use
            self.log(f"failed to look for a run to resume: {failed}")
            why = ""
        if looking == self._resume_looks:
            self._no_resume = why
            self._draw()

    def _picks_up(self, flow: str) -> bool:
        """Whether one flow says now that it can be picked up.

        Asked of the flow rather than read off the run, as it is wherever it is said: a flow
        is a file on disk, and one marked resumable since that run is one whose older runs
        can be carried on now. The same question the runs sheet asks of every row it draws
        (:meth:`hmz.tui.pick.Epics._picks_up`), which caches it because it asks it of a list;
        one run is one flow, so this asks it once and keeps nothing.

        Args:
          flow: The flow, as the run named it.

        Returns:
          Whether it is resumable, and False for one that will not load at all -- a flow that
          cannot be read cannot be run, which is what carrying on would come to.
        """
        try:
            return self.hmz.flows.resumes(flow)
        except Exception:  # noqa: BLE001 -- a flow is a file, and reading one runs it
            return False

    def _unresumable(self, epic: Path) -> tuple[Ran | None, str]:
        """What one run was, and what stands in the way of carrying it on, if anything does.

        Args:
          epic: The run, by the directory it is written in.

        Returns:
          The run as it was written down, or None where it cannot be read, and why it cannot
          be carried on, or "" where it can.
        """
        ran = self.hmz.epics.read(epic)
        if ran is None:
            return None, f"{epic.name} cannot be read, so there is nothing to resume"
        if not self._picks_up(ran.flow):
            return ran, (
                f"{ran.flow} does not support resuming, so {ran.name} cannot be resumed"
            )
        # A journal with nothing in it is a run killed before it wrote down where it had got
        # to, and carrying it on would be a run starting from the top wearing a line that
        # says which run it came from -- a record of something that did not happen.
        if not self.hmz.epics.picks_up(epic):
            return ran, (
                f"{ran.name} has no saved state to resume: enter a task to start the "
                "flow from the beginning"
            )
        return ran, ""

    def _carries_on(self, epic: Path, ran: Ran | None = None) -> None:
        """Runs the flow of one run again, picking up what that run left behind.

        Which is a run of its own: an epic is one run and is never reopened, so this is the
        flow started again from the journal of the run being picked up, writing into an epic
        of its own that says which one it came from.

        The flow, what its roles were given, its params, its budget and what it was asked to
        do all come from the run rather than from what the interface happens to be set up
        on: picking up a run means running what ran, and an agent swapped under it would be
        a different run wearing its name -- and one the journal would not pick up from.

        What stands in the way of carrying one on is read here and nowhere else, whether the
        run was named by `/resume` or walked into on `/epics`: two ways in that turned the
        same run down for different reasons would be two answers to one question.

        Args:
          epic: The run to pick up, by the directory it is written in.
          ran: What it was, where `_unresumable` has just said nothing stands in its way --
            reading it again would be running its flow again -- or None to find out.
        """
        # Before anything is read, since it is the one refusal that is about now rather than
        # about the record: a run picked up is a flow started, and there is one going.
        if self._mid_run("cannot resume a run"):
            return
        if ran is None:
            ran, why = self._unresumable(epic)
            if ran is None or why:
                self.show(f"hmz: {why}", "red")
                return
        # Named here rather than at the top of the file: `backends` is a local elsewhere in
        # this class, and an agent at no rung has to be written back out as `auto` or the
        # spec it goes into is `MODEL:`, which nothing can read again.
        from hmz.coganchor import backends
        from hmz.flows import Budget

        self._flow_named = ran.flow
        self._declared = declared_of(ran.flow)
        self._models = {
            one.agent: Runs(
                f"{one.backend}/{one.model}:{backends.written(one.effort)}",
                one.provider,
            )
            for one in ran.agents
        }
        self._envs = {
            role: spec
            for role, _, spec in (one.partition("=") for one in ran.envs)
            if spec
        }
        self._params = params_of(ran.flow, ran.params)
        try:
            self._budget = Budget.model_validate(ran.budget) if ran.budget else None
        except ValueError:
            self._budget = None
        self._harness = ran.harness
        self.show(
            f"[dim]resuming {escape(ran.name)}: running {escape(ran.flow)} "
            "from saved state[/dim]"
        )
        self._flow(ran.task, resume=epic)

    def _on_screen(
        self, doing: Callable[..., None], *said: object, **and_so: object
    ) -> None:
        """Draws something from whichever thread is asking, which is not always the same one.

        A turn asks for what is waiting from its own thread; a flow between turns asks from
        the flow's; and a test drives the interface from the event loop itself. Only the
        first two can go through `call_from_thread`; the loop itself may just draw.

        Args:
          doing: What to draw with.
          said: What to draw.
          and_so: The rest of what to draw with.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # no loop here, so this is a thread of somebody's own
            if not self.is_running:
                return  # and one that has gone has nothing left to draw on
            with contextlib.suppress(RuntimeError):  # or it went just now
                self.call_from_thread(lambda: doing(*said, **and_so))
            return
        if self.is_running:  # and one that has gone has nothing left to draw on
            doing(*said, **and_so)

    def _flow(self, task: str, resume: Path | None = None) -> None:
        """Asks the runs to start the flow that is set up, on what was said.

        Every frontend reading the runs reads the run it starts, as it happens: that is where
        what it says comes back from, this one included, so nothing about it is drawn here.

        Args:
          task: What it is to do.
          resume: The run to pick up, for a flow that says it can be picked up, or None for
            a run from the top.
        """
        if self._run is not None or self._starting:
            self.show("hmz: a flow is already running", "red")
            return
        import json

        from hmz.runtime.kept import written

        self._starting = True
        self._asks(
            "start",
            refused=self._not_started,
            flow=self._flow_named,
            task=task,
            agents={
                role: written(runs)
                for role, runs in self._models.items()
                if role in self._named_by
            },
            envs={
                role: spec
                for role, spec in self._envs.items()
                if self._declared is None or role in self._declared.places
            },
            params=self._params.model_dump(mode="json")
            if self._params is not None
            else None,
            # As JSON, which is what a budget crosses a socket as and reads back from.
            budget=json.loads(self._budget.model_dump_json())
            if self._budget is not None
            else None,
            resume=str(resume) if resume is not None else False,
            harness=self._harness,
        )

    def _not_started(self) -> None:
        """Takes a start that was refused as nothing starting, which the refusal has said."""
        self._starting = False
        self._draw()

    def _told(self, message: dict[str, Any]) -> None:
        """Takes one message about the runs, which is everything the interface draws them from.

        Called on the link's own thread, and taken on the screen's: what is drawn and what it
        is drawn from are then only ever touched in one place. Handed over without waiting on
        the screen, and taken there as many at a time as have arrived -- a frontend arriving
        late to a long run is told thousands at once, and a round trip and a redraw apiece
        would be it reading the run back for as long as the run took to say it.

        Args:
          message: What was told, as JSON; see `hmz.runtime.doing.hosting`.
        """
        with self._arriving:
            self._arrived.append(message)
            if self._draining:
                return
            self._draining = True
        try:
            asyncio.get_running_loop()
        except (
            RuntimeError
        ):  # the link's own thread, which is not to wait on the screen
            if not self.call_later(self._drains):
                with (
                    self._arriving
                ):  # the screen has gone, and nothing is left to take it
                    self._arrived.clear()
                    self._draining = False
            return
        self._drains()

    def _drains(self) -> None:
        """Takes every message that has arrived, in order, and redraws once for all of them."""
        while True:
            with self._arriving:
                taking = list(self._arrived)
                self._arrived.clear()
                if not taking or not self.is_running:
                    self._draining = False
                    break
            for message in taking:
                try:
                    self._takes(message)
                except Exception as why:  # noqa: BLE001 -- one message is not all of them
                    self.log(
                        f"a {message.get('type')} message could not be drawn: {why}"
                    )
        self._draw()

    def _takes(self, message: dict[str, Any]) -> None:
        """Takes one message, on the screen's own thread.

        Args:
          message: What was told.
        """
        kind = message.get("type")
        if kind == "event":
            self._heard(message)
        elif kind == "opened":
            self._opened(message)
        elif kind == "started":
            self._started(message)
        elif kind == "stopping":
            self._stopped(message)
        elif kind == "ended":
            self._ended(message)
        elif kind == "asked":
            self._show_question(message)
        elif kind == "answered":
            self._answered(message)
        elif kind == "said":
            self._said_by_you(
                str(message.get("text") or ""),
                str(message.get("key") or ""),
                self._by(message),
            )
        elif kind == "refused":
            self.show(f"hmz: {message['because']}", "red")
        elif kind == "unheld":
            self._unheld(message)
        elif kind == "dropped":
            self._never_sent(message)
        elif kind == "printed":
            self._prints(str(message.get("text") or ""))
        elif kind == "welcome":
            self._me, self._named = message["client"], message["name"]
        elif kind == "live":
            self._live = True
        elif kind == "gone":
            self._gone(str(message.get("why") or ""))
        else:
            self._stands(message)

    def _stands(self, message: dict[str, Any]) -> None:
        """Takes how one thing stands now, as the runs say it whenever it changes.

        Args:
          message: The snapshot: which thing, and how it stands.
        """
        kind = message.get("type")
        if kind == "run":
            self._ran(message)
        elif kind == "sessions":
            # How things stand wins over what was read back of how they came to: a turn
            # that began before this interface arrived is working whether or not the record
            # of it beginning was kept.
            if message.get("run") == self._generation:
                self._working = set(message.get("working") or ())
        elif kind == "calls":
            self._called = list(message.get("calls") or ())
        elif kind == "clients":
            self._frontends = {
                one["client"]: one["name"] for one in message.get("clients") or ()
            }
        elif kind == "claims":
            self._claimed(dict(message.get("claims") or {}))
        elif kind == "away":
            self._afk = bool(message.get("all"))
            self._afk_of = dict(message.get("of") or {})
        elif kind == "waiting":
            self._queued = list(message.get("queued") or ())
            self._given = list(message.get("given") or ())
        elif kind == "pending":
            self._pending = list(message.get("pending") or ())
        elif kind == "board":
            items = message.get("items")
            self._boarded = (
                None
                if items is None
                else BoardSeen(
                    items, lambda key, value: self._asks("board", key=key, value=value)
                )
            )

    def _ran(self, message: dict[str, Any]) -> None:
        """Takes which run is going and which is stopping, as the runs say it now.

        Args:
          message: The `run` snapshot: the state, and what the run in front of us started as.
        """
        if (
            message.get("state") == "running"
            and message.get("run", 0) > self._generation
        ):
            # A run whose start was not kept for this interface to read back, which is one
            # older than the most that is kept: it starts here instead.
            self._started(message)
        self._run = _RunSeen.of(message) if message.get("state") == "running" else None
        if self._run is not None:
            self._starting = False
            self._seen_last = self._run
        stopping = message.get("stopping")
        self._stopping = stopping if isinstance(stopping, int) else None

    def _claimed(self, claims: dict[str, str]) -> None:
        """Takes who holds which role now, saying so where one this interface held has gone.

        Args:
          claims: Each role held, and the client holding it.
        """
        was, self._claims = self._claims, claims
        if not self._live:
            return
        for role, owner in was.items():
            if owner == self._me and claims.get(role) != self._me:
                now = self._whose(role) or "anybody's"
                self.show(f"[dim]{escape(role)} is {escape(now)} to answer now[/dim]")

    def _gone(self, why: str) -> None:
        """Takes the runs letting go of this interface, which is the end of it.

        Args:
          why: Why they let go of it.
        """
        if self._quitting:
            return  # asked for, on the way out
        self._quitting = True
        self.exit(return_code=1, message=f"hmz: {why or 'disconnected from the runs'}")

    def _started(self, record: dict[str, Any]) -> None:
        """Takes a run that has just started as the one in front of us.

        Args:
          record: The run, as it started.
        """
        self._generation = int(record["run"])
        # A side conversation is about the run it was opened on, and that run has gone.
        if self._btw is not None:
            self._leave_btw("a new flow started")
        with self._btw_lock:
            self._flow_task = record["task"]
            self._btw_events.clear()
        # Nothing is left of the flow before this one to press a key about, and what is
        # being read is one of its agents unless it was the transcript they all appear on.
        # Which is where a run is watched from, so it is where a run starts.
        if self._attached != _EVERY:
            self._now_reading(_EVERY, stepped=False)
        # The conversations of the run before this one went with it, and so do their numbers
        # and their transcripts: this run's first conversation is its role's first again.
        self._seen, self._working, self._placed = {}, set(), {}
        # And where their harnesses went, which this run settles for itself.
        self._harnessed = {}
        for gone in [key for key in self._kept if "/" in key]:
            del self._kept[gone]
        self._outworlders = list(record.get("outworlders") or ())
        # What it was started on, where somebody else started it: what they said is what
        # this run is doing, and it went down here as it was typed where it was typed here.
        if by := self._by(record):
            self._said_by_you(str(record.get("task") or ""), by=by)
        self._monitor = Monitor(began=record["began"])
        # What the run costs is read from the logs the agents keep, which they write as they
        # go: a backend only says what a turn cost once the turn is over, and a turn is long.
        self._tally = Tally([], self._monitor)
        self._followed[self._generation] = (self._monitor, self._tally)
        self._tally.watch()

    def _stopped(self, record: dict[str, Any]) -> None:
        """Says a run is on its way out, and who asked for it to be.

        Args:
          record: The run, as it was told to stop.
        """
        self._halted.add(int(record["run"]))
        if record["run"] == self._generation:
            client = str(record.get("client") or "")
            who = (
                "" if client in ("", self._me) else f"{record.get('by') or client} is "
            )
            self.show(f"[dim]— {escape(who)}stopping the flow —[/dim]")

    def _ended(self, record: dict[str, Any]) -> None:
        """Says how a run went.

        Args:
          record: The run, as it ended.
        """
        why = record["why"]
        if record["how"] in ("refused", "failed", "crashed"):
            self.show(f"hmz: {why}", "red")
        elif record["how"] == "budget":
            self.show(f"hmz: stopped -- {why}", "yellow")
        followed = self._followed.pop(record["run"], None)
        if followed is not None:
            monitor, tally = followed
            tally.stops()  # read once more, for what the last turn wrote on its way out
            monitor.stops()  # the clock the rate is over is the run's, and it is over
        # Only this run's own, and only one nobody stopped: a run stopped by hand has said
        # so already, and one still unwinding behind the next is no run anybody is watching.
        if record["run"] == self._generation and record["run"] not in self._halted:
            self.show("[dim]— the flow is done —[/dim]")
        # The run in front of us is the last run here, and may be the one to carry on now.
        # Only that one: a frontend arriving late is told of every run before it as well.
        if record["run"] == self._generation:
            self._looks_for_resume()

    def _opened(self, record: dict[str, Any]) -> None:
        """Takes one session a run has just opened as one of the run's own.

        Told on the run's own thread, before the session's first turn: its transcript is its
        role's, and what its backend counts is said to the monitor. A person holds no
        conversation, and the board is all there is of them.

        Args:
          record: The session, as it opened.
        """
        if record["person"]:
            return
        seen = Seen(
            record["agent"],
            record["cli"],
            record["model"],
            frozenset(record["counts"]),
            kept=record.get("kept", ""),
        )
        if record["run"] == self._generation:
            self._seen[record["key"]] = seen
            if placed := record.get("env"):
                # With where its harness went, which is the environment's page to say.
                self._placed[record["key"]] = {
                    **placed,
                    "harness": str(record.get("harness") or ""),
                }
            self._harnessed_at(str(record.get("role") or ""), record.get("harness"))
        followed = self._followed.get(record["run"])
        if followed is None:
            return
        monitor, tally = followed
        # What its backend counts, said before its first turn: a kind nothing was spent on
        # this turn is missing from that turn's reckoning exactly as a kind the CLI never
        # counts is, and what is drawn of a run driving two backends has to tell the two
        # apart to say which of its figures are whole.
        monitor.reporting(seen.id, seen.counts)
        tally.add(seen)

    def _harnessed_at(self, role: str, where: object) -> None:
        """Says where a role's harness went, the first time it goes somewhere this run.

        Only for work on another machine, which is the only work whose harness had anywhere
        else to be: a session that works here says nothing. And kept, for the flow menu to
        say what adaptive came to without anybody having to find it in the transcript.

        Args:
          role: The role, as the flow calls it.
          where: Where its harness runs, as the run said it, or nothing for work here.
        """
        if not role or not isinstance(where, str) or not where:
            return
        if self._harnessed.get(role) == where:
            return
        self._harnessed[role] = where
        kind, _, on = where.partition(":")
        said = {"local": "here", "env": "on its environment's machine"}.get(
            kind, f"on {on}"
        )
        self.show(f"[dim]{escape(role)}'s harness runs {escape(said)} ({kind})[/dim]")

    def _remember_btw(self, record: dict[str, Any]) -> None:
        """Keeps a compact progress record for future side questions.

        Reasoning is intentionally omitted: a side question needs observable progress, not a
        second copy of private chain-of-thought. The event stream still reaches the ordinary
        transcript exactly as before.
        """
        # A stopped flow can take a moment to unwind while a new one is already up. Its
        # events must not become progress for the new run.
        if self._run is not None and record["run"] != self._generation:
            return
        kind = record["kind"]
        if kind not in {
            "begins",
            "ends",
            "failed",
            "asks",
            "notice",
            "tool",
            "text",
            "result",
        }:
            return
        text = (
            record["text"].split("\n\n", 1)[0]
            if kind == "begins"
            else "turn ended"
            if kind == "ends"
            else record["text"]
        )
        text = compact(text)
        with self._btw_lock:
            self._btw_events.append(
                Observation(
                    agent=record["agent"], kind=kind, text=text, at=time.monotonic()
                )
            )

    def _heard(self, record: dict[str, Any]) -> None:
        """Shows what a turn said, on the transcript of the agent that said it.

        And takes what it cost into what the monitor shows, which is per agent: an agent is
        what is read, and the bill is the agent's too.

        What is shown of a turn is what the turn was for unless details say otherwise:
        the agent starting, what it said, and the agent stopping. The tools it used and the
        thinking it did aloud are how it got there, and a screen of them is a screen where
        the answer went past between two file reads. Details are what ask for all of it.

        Called from whichever thread the turn is running on, which is why everything drawn
        from here goes through `_on_screen`.

        Args:
          record: What was said, by whose turn and in which of its conversations -- or in
            none, for something the agent said rather than one of them: a question put by a
            server that speaks for every conversation it holds. Either way it is shown
            against the agent, all of whose conversations are the one transcript.
        """
        agent, kind, text = record["agent"], record["kind"], record["text"]
        now: float = record["mono"]
        # First, whatever else happens: showing a line raises once the interface has gone, and
        # what a watcher raises is swallowed, so accounting after it would be lost.
        # The kinds go with the tokens where a turn spent them all on one model, which is the
        # ordinary turn: `spent` is that whole turn's cost by kind. A turn that named two --
        # an agent that reached for a cheaper model for a sub-turn -- says what each of them
        # cost and says the kinds of the pair together, and nothing in it says which of the
        # two a cached read was made against. So they are divided by what each model took,
        # rather than dropped: a turn whose kinds are dropped is a turn counted as tokens of
        # no kind at all, which is a turn missing from every per-kind figure and priced at
        # nothing. Where the CLI's own log is read as well, the exact split is in it, and the
        # fullest reckoning is the one the money and the kinds are both read off.
        tokens: dict[str, int] = record["tokens"]
        spent: dict[str, float] = record["spent"]
        whole = sum(tokens.values())
        # And the node the monitor draws that conversation as, which is the key of the
        # conversation it stands for -- only while the run it is of is the one in front of
        # us. A run stopped and still unwinding behind the next numbers its conversations
        # from one as that one does, so what it says goes on its agent's transcript instead.
        ours = record["run"] == self._generation
        numbered: str | None = (record["session"] or None) if ours else None
        for model, count in tokens.items():
            if not spent:
                broken = None
            elif len(tokens) == 1:
                broken = dict(spent)  # the whole turn, on the one model it named
            elif whole > 0:
                broken = {kind: one * count / whole for kind, one in spent.items()}
            else:
                # Two models and nothing on either. There is nothing to divide by and
                # nothing to divide, and a turn whose accounting raised would lose the
                # line it was about: what a watcher raises is swallowed.
                broken = None
            self._monitor.spend(
                agent, count, model=model, now=now, kinds=broken, session=numbered
            )
        # Anything at all the agent did, token or not: a tool, a word, an answer. A turn
        # spends most of its minutes between the counts it reports, and a figure worked out
        # only when one arrives stands still through all of them.
        self._monitor.stirring()
        self._remember_btw(record)
        if kind == "result":
            # Kept to tell a flow saying an agent's answer back to the person -- a
            # conversation asking what next -- from a question it asks them.
            self._last_answer = text
        elif kind == "asks":
            self._last_asked = text
        seen = self._seen.get(record["session"]) if numbered is not None else None
        if seen is not None and record["ident"] not in ("", *seen.idents):
            # What the backend calls it, which is the name its log is kept under.
            seen.idents = seen.idents | {record["ident"]}
        # The conversation's own transcript, which is its agent's too and every agent's.
        whose: str = record["key"] if ours else agent
        if kind == "took":
            # The agent saying a word put into its turn is now in front of it, which the runs
            # say as the word being said, with who said it.
            return
        if kind == "begins":
            self._monitor.begins(agent, record["model"], now=now, session=numbered)
            self._began[agent] = now
            if numbered is not None:
                # Which is what makes it a conversation a typed line may go into: one written
                # to a conversation between turns is answered on its own, outside the flow.
                self._working.add(numbered)
            # A turn takes minutes and says nothing for most of them, so the line that says
            # one has started is the whole of what a flow looks like while it thinks. Which
            # of that agent's conversations, where it has more than one: a loop that opens
            # one a turn runs them all down the one transcript, and this is where each of
            # them begins.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_SAID} {escape(short(agent))} is working"
                f"{self._conversation(numbered or '')}[/]",
                packs=False,
            )
        elif kind == "ends":
            self._monitor.ends(agent, now=now, session=numbered)
            if numbered is not None:
                self._working.discard(numbered)
            took = now - self._began.pop(agent, now)
            # The line Claude Code closes a turn with, which says how long it worked.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_WORKED} Worked for {took:.0f}s{_DOT}{escape(short(agent))}[/]",
                packs=False,
            )
        elif kind in ("subagent", "subagent-ends"):
            # An agent this one started of its own. Counted whether or not the details are
            # being shown, since the monitor draws the fleet under the agent that started it
            # and a fleet nobody counted would be an agent working with nothing under it.
            named, _, about = text.partition(" ")
            if kind == "subagent":
                self._monitor.started(
                    agent, record["whose"], about or named, session=numbered
                )
            else:
                self._monitor.finished(
                    agent, record["whose"], about or named, session=numbered
                )
            if self._details:
                self._on_screen(
                    self._part,
                    whose,
                    f"[$secondary]{_SAID}[/] {escape(named)}"
                    f"[dim]({escape(about)}) "
                    f"{'started' if kind == 'subagent' else 'done'}[/]",
                    packs=True,
                )
        elif kind == "notice":
            # Not the working, so details do not hide it: this is humanize saying what it
            # is doing about a turn -- waiting out a rate limit, carrying on as another
            # account, cutting the turn off, taking it away from a backend that had stopped
            # saying anything. Hidden with the tool rows it reads as a hang, which is the one
            # thing the line exists to tell apart from a hang.
            self._on_screen(
                self._part,
                whose,
                f"[yellow]{_SAID}[/] [dim]{escape(text)}[/]",
                packs=False,
            )
        elif kind == "tool" and self._details:
            # The tool on the bullet, what it came back with under it -- Claude Code's shape.
            named, _, about = escape(text).partition(" ")
            self._on_screen(
                self._part,
                whose,
                f"[green]{_SAID}[/] {named}[dim]({about})[/]",
                packs=True,
            )
        elif kind == "reasoning" and self._details:
            self._on_screen(
                self._part,
                whose,
                "\n".join(
                    f"[dim italic]{line}[/]" for line in escape(text).splitlines()
                ),
                packs=False,
            )
        elif kind == "asks":
            self._on_screen(
                self._part,
                whose,
                f"[yellow]{_SAID}[/] {escape(text)}",
                packs=False,
            )
        elif kind == "failed":
            self._on_screen(
                self._part,
                whose,
                f"[red]hmz: {escape(text)}[/]",
                packs=False,
            )
        elif kind == "text":
            # The bullet on the first line, two spaces under it for the rest, which is how
            # Claude Code sets a message it has just written.
            said = escape(text).splitlines() or [""]
            self._on_screen(
                self._part,
                whose,
                "\n".join(
                    [
                        f"[green]{_SAID}[/] {said[0]}",
                        *(f"  {line}" for line in said[1:]),
                    ]
                ),
                packs=False,
            )

    def _conversation(self, key: str) -> str:
        """Which of a role's conversations a turn is being taken in, where it has several.

        Args:
          key: The conversation, or "" where the agent said it rather than one of them.

        Returns:
          Which one, counting from one, and nothing at all for a role holding one -- there
          being nothing to tell it apart from.
        """
        role, _, at = key.partition("/")
        if not at:
            return ""
        opened = len(self._of(role))
        if opened < 2:  # noqa: PLR2004 -- one is none to tell apart
            return ""
        return f"{_DOT}conversation {at} of {opened}"

    def _part(
        self, whose: str | None, text: str, *, packs: bool, shared: bool = True
    ) -> None:
        """Puts one part of a turn in the transcript, spaced as opencode spaces its own.

        A blank line goes between the parts, except between two that pack -- one-line tool
        rows run together, and everything else is set apart. Spaced per transcript: two
        agents talking at once would otherwise run each other's lines together.

        Args:
          whose: The agent whose part it is, or None for one to show on whatever is read.
          text: The part, as markup.
          packs: Whether this part is one that runs on from the one before it.
          shared: Whether it goes on the one every agent is on as well; see `_into`.
        """
        kept = self._keeping(whose)
        if not (packs and kept.packed):
            self._into(whose, "", shared=shared)
        kept.packed = packs
        self._into(whose, text, shared=shared)

    def _said(self, text: str) -> None:
        """Takes a line that is not a command, which is a task, an answer, or a word put in.

        With a flow chosen and not yet running, it is the task that starts it -- the way a
        first message to opencode is the thing it is asked to do, and the reason the flow
        this opens on is one that takes anything as a task. With one running, it is the
        answer to whatever the flow stopped to ask that is this interface's to answer, or it
        goes to the agent taking its turn -- into the turn under way, or to the flow waiting
        to be told the next one.

        Args:
          text: What was said.
        """
        if (asked := self._answers_to()) is not None:
            # Set aside here rather than when the runs say it was answered, so that a second
            # line typed before they do answers the next question -- and put back where it
            # is refused, since the question is still waiting.
            question = str(asked["question"])
            self._answering.add(question)
            self._asks(
                "answer",
                refused=lambda: self._answering.discard(question),
                question=question,
                text=text,
            )
            self._draw()
        elif self._run is not None and self._view_kind() == "outworlder":
            # Nothing of its own is up, and a line typed here is for this outworlder alone:
            # left in the queue, whichever other outworlder asked next would take it.
            role = self._attached.removeprefix(_OUTWORLDER)
            whose = self._whose(role)
            self.show(
                f"hmz: {role} is {whose} to answer, not yours"
                if whose not in ("", "yours")
                else f"hmz: {role} is not asking anything now; read another transcript "
                "to say it to an agent",
                "red",
            )
        elif self._run is not None or self._starting:
            # Into the turn on the view being read, or the next one to start there: the runs
            # pin it above the prompt until it goes, and say who said it once it has. Asked
            # after the start before it, so a run still starting is the one it is said to.
            self._asks("say", text=text, to=self._attached)
        else:
            self._said_by_you(text)
            self._starts(text)

    def _starts(self, task: str) -> None:
        """Starts the flow that is chosen on what was said, which is what saying it does.

        Written down here rather than in :meth:`_said` because a `$` line reaches it the other
        way round -- the flow first and what to do with it after -- and two places starting a
        flow on different command lines is two things to drift apart.

        Args:
          task: What to start it on, which is already in the transcript.
        """
        if not self._set_up:
            # Typed a task and nothing at all happened, which is the worst of these: it is
            # somebody meeting humanize for the first time and getting a red line for it.
            telemetry.snag("nothing-started", because="no coding agent installed")
            self.show("hmz: no coding agent is installed", "red")
            return
        self._flow(task)

    def _answers_to(self) -> dict[str, Any] | None:
        """The question a line typed now would answer, if it would answer one.

        On an outworlder's own transcript, the oldest that outworlder asks; on the one every
        agent is on, and on the monitor, the oldest any of them asks, those being where every
        one of them is answered. On an agent's own, none: what is typed there is said to it.
        And only one this interface may answer: a role another holds is theirs.

        Returns:
          The question, as the runs said it, or None where a typed line goes elsewhere.
        """
        kind = self._view_kind()
        if kind == "session":
            return None
        role = self._attached.removeprefix(_OUTWORLDER) if kind == "outworlder" else ""
        return next(
            (
                one
                for one in self._pending
                if (not role or one.get("role") == role)
                and one.get("owner") in (None, self._me)
                and one.get("question") not in self._answering
            ),
            None,
        )

    def _show_question(self, record: dict[str, Any]) -> None:
        """Shows a question the flow asks, and what it will take for an answer.

        On the transcript of the outworlder asking, and on the one every agent is on --
        unless an agent has just stopped to ask the same thing, or has just said it, which
        is already there and is not said twice. The answers it offers are numbered, so that
        one is chosen by its number as well as by its words. What to say next, with nothing
        asked in words, is shown as nothing: the prompt is what asks it.

        Args:
          record: What the flow wants to know, and which outworlder wants it.
        """
        role = str(record.get("role") or "outworlder")
        if role not in self._outworlders:
            self._outworlders.append(role)
        asked = str(record.get("text") or "").strip()
        listening = record.get("mode") == "listen"
        if listening and not asked:
            return
        key = f"{_OUTWORLDER}{role}"
        repeated = bool(self._last_asked) and asked == self._last_asked.strip()
        # A conversation saying back what its agent answered, to ask what next: on the
        # one every agent is on already.
        said_back = listening and asked == self._last_answer.strip()
        self._part(
            key,
            f"[yellow]{_SAID}[/] {escape(asked)}",
            packs=False,
            shared=not (repeated or said_back),
        )
        for at, option in enumerate(record.get("options") or (), 1):
            self._into(key, f"      [dim]{at}. {escape(option)}[/dim]")
        whose = self._whose(role)
        self._into(
            key,
            f"   [dim]{escape(whose)} to answer[/dim]"
            if whose not in ("", "yours")
            else f"   [dim]{'yours to answer: ' if whose else ''}type an answer, or /afk "
            "to stop being asked[/dim]",
        )

    def _answered(self, record: dict[str, Any]) -> None:
        """Shows a question answered, on its outworlder's transcript and the shared one.

        Args:
          record: What was answered, by whom, to which question.
        """
        asked = record.get("question")
        self._pending = [one for one in self._pending if one.get("question") != asked]
        self._said_by_you(
            str(record.get("text") or ""),
            f"{_OUTWORLDER}{record.get('role') or 'outworlder'}",
            self._by(record),
        )

    @property
    def _set_up(self) -> bool:
        """Whether there is an agent for each of the flow's agent roles.

        There is always a flow -- the interface opens on one -- so this is only ever short of
        an agent, which is a machine with no coding agent installed on it. A flow with no
        agent role is not short of anything: whoever is outside it is at this prompt.
        """
        return all(
            role in self._models and self._models[role].spec for role in self._named_by
        )

    def _unheld(self, record: dict[str, Any]) -> None:
        """Says what became of the words an agent was holding when its turn ended.

        The turn is over and it never said it had them, so they are neither waiting nor
        taken: they were put to it, and what it did with them is between it and the backend.
        Every backend but codex runs such a word as a turn of its own afterwards, and codex
        drops it -- which is more than this can tell from here, so it says what it knows.

        Args:
          record: The agent whose turn ended, and what it was holding.
        """
        held = [str(one) for one in record.get("texts") or ()]
        if not held:
            return
        for text in held:
            self._said_by_you(text)
        self.show(
            f"[dim]   sent to {escape(short(str(record.get('agent'))))}, which "
            "ended its turn without acknowledging "
            f"{'them' if len(held) > 1 else 'it'}[/dim]"
        )

    def _never_sent(self, record: dict[str, Any]) -> None:
        """Puts whatever was still waiting into the transcript, nothing being left to take it.

        A flow ends two ways -- stopped by hand, or of its own accord -- and both leave the
        pin holding lines that are not on their way anywhere. They come off it and into the
        transcript as what they turned out to be: a line typed at a flow that is gone has to
        be somewhere, or the next thing typed would quietly take its place.

        Args:
          record: What was waiting -- put to an agent, or queued -- and why it never went.
        """
        because = str(record.get("because") or "")
        because = _FIRST.get(because, because)
        given: list[dict[str, Any]] = list(record.get("given") or ())
        queued: list[dict[str, Any]] = list(record.get("queued") or ())
        # Oldest first: what went to an agent went before what is queued.
        for one in given:
            self._said_by_you(str(one.get("text")), by=self._by(one))
        if given:
            # Put to an agent, which never said it had it: it may well have reached the
            # model, and saying it never went would be as wrong as saying it landed.
            self.show(f"[dim]   sent to the agent, not acknowledged: {because}[/dim]")
        for one in queued:
            self._said_by_you(str(one.get("text")), by=self._by(one))
        if queued:
            self.show(f"[dim]   never sent: {because}[/dim]")


def _machine() -> dict[str, object]:
    """What the interface knows about this machine, for a report of something going wrong.

    Which coding agents are installed, which accounts exist and how each was signed in, what
    each backend would load as skills, and where flows come from. Names and counts only: an
    account's variables are named nowhere and its values are read nowhere, and a skill is its
    name and the CLI that would load it.

    Returns:
      The description, as plain values something can write out as YAML.
    """
    import platform

    from hmz.coganchor.agents.skills import skills

    held = Hmz()
    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "clis": sorted(installed()),
        "accounts": [
            {"cli": one.cli, "name": one.name or "as local", "way": one.way or "-"}
            for one in held.accounts.all()
        ],
        "skills": {
            cli: [one.name for one in skills(cli)]
            for cli in sorted(installed())
            if skills(cli)
        },
        "flowverses": [
            {"name": one.name, "fetched": one.fetched} for one in held.verses.all()
        ],
    }


#: What the editor understands, named as opencode names them, one step along: what answers
#: here is a flow rather than an agent, so opencode's `/agents` is `/flow`, and what a flow
#: runs on is an agent apiece rather than one model, so its `/models` is the page along from
#: it. There is no command for an agent on its own: an agent belongs to the flow that drives
#: it, and is set up on the page of `/flow` its agents are on. `hmz internal anchor` is not here
#: either: it is not a thing to do to a flow that is running, and it is a command line of its
#: own. What a run left behind is `/epics`, which is where the runs of this directory are --
#: and packaging one up to send is one of the things offered about the run under the cursor
#: there, rather than a command of its own about whichever run this screen happens to show.
#:
#: One table, read by everything that has anything to do with a command: the list offers what
#: is in it, the line under the editor says what each takes, and a line that was sent is
#: carried out by the row it names. Adding one is one row here rather than an entry in three
#: files that only a test kept in step.
#:
#: Written down here rather than beside the class, since a row names the method that carries
#: it out and the class has to exist first.
_COMMANDS: tuple[Command, ...] = (
    Command(
        "flow",
        "Switch flow",
        lambda app, argv: app.action_flow(argv[0] if argv else ""),
        takes="[flow]",
        # Never refused -- the agents of a run are set up whatever is happening -- but only
        # that while one runs: no flow is offered after it, and one named is turned down.
        now=lambda app: (
            "Set up the running flow's agents" if app.flow_running() else ""
        ),
    ),
    Command(
        "btw",
        "Ask side questions; press esc or /btw to stop",
        lambda app, argv: app.action_btw(" ".join(argv).strip()),
        takes="[question]",
        refuses=lambda app: app.refused_btw(),
        now=lambda app: (
            "Ask one more; alone, leave btw mode (esc too)" if app.in_btw() else ""
        ),
    ),
    Command(
        "epics",
        "View and manage runs in this directory",
        lambda app, _: app.action_epics(),
    ),
    Command(
        "resume",
        "Resume the last run in this directory",
        lambda app, argv: app.action_resume(argv),
        # Turned down with a flow going. And left out of the list with nothing here to carry
        # on, which is looked for off the screen, reading a flow being running it -- and so
        # only left out: typed, it looks again for itself, and says what it found.
        refuses=lambda app: app.refused_resume(),
        unlisted=lambda app: app.nothing_to_resume(),
    ),
    Command(
        "settings",
        "Every setting: settings, workspace, accounts, environments, fallback, "
        "flowverses",
        lambda app, argv: app.action_settings(argv[0] if argv else ""),
        takes="[page]",
        offers=_PAGES,
    ),
    Command("clear", "Clear the screen", lambda app, _: app.action_clear()),
    Command(
        "afk",
        "Toggle whether an agent may ask you",
        lambda app, argv: app.action_afk(argv),
        takes="[on|off]",
        # Every outworlder from where all of them are, one from its own transcript, and
        # nothing from an agent's, which asks nobody anything.
        where=VIEWS - {"session"},
        refuses=lambda app: app.held_elsewhere("say whether it is away"),
    ),
    Command(
        "claim",
        "Answer for this outworlder exclusively; off releases it",
        lambda app, argv: app.action_claim(argv),
        takes="[on|off]",
        # On the transcript of the one outworlder it holds, and nowhere else: which role is
        # meant is the one being read.
        where=frozenset({"outworlder"}),
        refuses=lambda app: app.held_elsewhere("claim it"),
    ),
    Command(
        "stop",
        "Stop the flow without confirmation",
        lambda app, _: app.action_stop(),
        # From where the whole run is watched, and not from one agent's transcript, where
        # stopping reads as stopping that agent.
        where=frozenset({"monitor", "aggregate"}),
        refuses=lambda app: app.refused_stop(),
    ),
    Command(
        "exit",
        "Exit",
        lambda app, _: app.action_exit(),
        # What becomes of the run is asked, and which answers there are is where it is held.
        now=lambda app: (
            ""
            if not app.flow_running()
            else "Exit; a running flow can be left running"
            if app.held_apart()
            else "Exit; asks before stopping the running flow"
        ),
    ),
)

#: The same rows by name, for the two readers that have a name in hand rather than a line to
#: finish: the row drawn beside an offer, and the command a sent line turned out to be.
_BY_NAME = {one.name: one for one in _COMMANDS}
