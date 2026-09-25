"""humanize as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way Claude Code is, and no wider: a transcript the width of the terminal, an
editor under it between two rules, and a status line under that. Nothing sits beside them --
how the run is going is on `/monitor`, and `/flow` both chooses the loop and, inside the one
it opens, sets what each of its agents runs.

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
import functools
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import traceback
import weakref
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, Protocol, cast

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

from .btw import AgentProgress, FlowSnapshot, Observation, compact, format_snapshot
from .complete import Command, hinted, offered
from .discover import installable, installed
from .history import History
from .monitor import Monitor, short, thousands
from .pick import (
    DETACHES,
    RESUMES,
    STOPS,
    Adjusted,
    Adjusts,
    Chosen,
    Declared,
    Drawn,
    Epics,
    Fallbacks,
    Flows,
    Flowverses,
    Held,
    Leaves,
    Monitoring,
    Providers,
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
from .tally import Tally

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pydantic import BaseModel

    from hmz.coganchor.agents import AgentBase, Board, Event, Question, SessionBase
    from hmz.daemon import Session
    from hmz.flows import Budget, Usage
    from hmz.runtime.flowing.harnesses import Listener


class _Running(Protocol):
    """A run of a flow, as the interface holds one: `hmz.runtime.Run`, named by its shape.

    Named here rather than imported, the runtime being reached through the daemon alone.
    """

    @property
    def budget(self) -> Budget:
        """What the run may spend."""
        ...

    @property
    def usage(self) -> Usage:
        """What it has spent so far."""
        ...

    @property
    def flow(self) -> str:
        """The flow, as it was named."""
        ...

    def watch(self, listener: Listener) -> None:
        """Has everything every session of the run says reach `listener`."""
        ...

    def opened(self, callback: Callable[[str, AgentBase, SessionBase], None]) -> None:
        """Has each session the run opens told to `callback` as it opens."""
        ...

    def run(self) -> object:
        """Runs the flow here, until it returns."""
        ...

    def stop(self) -> None:
        """Stops the flow, which unwinds in its own time."""
        ...

    def close(self) -> None:
        """Stops it and ends every conversation still open, without waiting."""
        ...


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

#: How many transcripts are kept, and how many lines of each. One per agent and one for all
#: of them together, so a flow of ten agents is eleven -- and the ones before that are the
#: agents of flows that have already ended, which are kept until there are this many newer.
#: Two thousand lines is more of one than anybody reads back through, and about what a long
#: turn's tools and thinking come to.
_KEPT = 16
_LINES = 2000

#: How long a second ctrl+c has to arrive in for the two to be one gesture. Long enough to
#: read the line that says what the next press does and then press it, and short enough that
#: a press minutes later is a first press rather than half of one nobody remembers making.
_AGAIN = 3.0

#: What a flow told to stop and not yet gone is doing, said wherever that state is the answer
#: -- to `/stop`, and to everything `_mid_run` turns down. One state reads as one state only
#: while it is said in one wording: two sentences for it are two states to whoever is at the
#: prompt, and each of them one somebody has to work out for themselves.
_UNWINDING = "it is closing out the turn it was in"

#: The flow the interface opens on, which is the one that is only talking to one agent.
_STARTS_ON = "chat"

#: What a `$` may name, which is a flow by the name it is offered under: a letter, then what
#: the directory holding a flow is called, `<where it came from>/<flow>` for one that says
#: which place it came from, and `:<inside>` for one of the several a file holds. Only a line
#: whose `$` is followed by that and then by whitespace or nothing is a flow being started --
#: anything else after the `$`, a space, a bracket, a figure, nothing at all, names no flow
#: there could be, and is a line somebody happened to begin with a `$`.
_NAMED = re.compile(r"[A-Za-z][\w.-]*(?:/[A-Za-z][\w.-]*)*(?::[\w.-]+)?")

#: How much live activity a side question may carry into its isolated context, and how many
#: side questions may have model turns open at once. Both are bounds on optional observation:
#: a day-long flow and a pasted row of questions must not grow the interface without limit.
_BTW_EVENTS = 80
_BTW_ACTIVE = 4


def _quiet_watch(
    _agent: AgentBase,
    _session: SessionBase | None,
    _event: Event,
) -> None:
    """Consumes a side agent's events so backend output stays out of the main transcript."""


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
        # How the run is going, which is where the flow is drawn. Not what stops a flow: a
        # key pressed to dismiss whatever is on the screen must not be the key that ends a
        # day's work, and esc is pressed to dismiss things everywhere else in this
        # interface. The editor takes it first while it is offering something.
        Binding("escape", "monitor", "monitor", show=False),
        # Round the transcripts: the one every agent is on, then whichever are working.
        # Priority, since tab and shift+tab are the screen's own way of moving the focus
        # about, and there is nowhere here for the focus to go.
        Binding("tab", "attach_next", "next agent", priority=True),
        Binding("shift+tab", "attach_previous", "previous agent", priority=True),
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
        # Every other one of ours is either the editor's, which a sheet has taken the focus
        # from, or means the same thing wherever it is pressed.
        if action not in ("attach_next", "attach_previous"):
            return True
        if len(self.screen_stack) > 1:
            return False
        # Asked of whatever is on the screen rather than of one widget, since a key may be
        # pressed before the offers themselves have been laid out.
        offering = any(offers.has_class("offering") for offers in self.query("#offers"))
        return not (action == "attach_next" and offering)

    def action_quit(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Leaves, having first stopped whatever was running.

        A flow is a loop and a turn can think for minutes, so leaving without stopping it
        would leave the interface gone and the work going -- which reads as a hang.
        """
        for run in (self._run, self._stopping):
            if run is not None:
                run.close()
        self._run, self._stopping, self._agents = None, None, []
        self._close_btw()
        self.exit()

    @work
    async def action_exit(self) -> None:
        """Closes the interface, having first asked what is to become of a running flow.

        Closing the interface and stopping the run are two things wherever the run is being
        held somewhere a terminal closing cannot reach: the flow goes on taking its turns and
        the next terminal to open it is drawn for from the top. So it is asked rather than
        assumed, and it is asked only where there is something to ask about -- with nothing
        running, `/exit` is a window being closed.

        The one way out, letting go of the terminal included. That was a command of its own
        and is an answer here instead: both were about the same running flow, and a person
        who has decided to leave should be asked what becomes of it once rather than having
        to know which of two words asks.
        """
        if self._run is None:
            self.action_quit()
            return
        said = await self.push_screen_wait(Leaves(held=self._session is not None))
        if said == STOPS:
            self.action_quit()
        elif said == DETACHES:
            self._detach()

    def _detach(self) -> None:
        """Lets go of the terminal reading this, leaving the flow running.

        The answer to `/exit` that closes the terminal rather than the run: what was running
        goes on running, and `hmz` in this directory opens it again. Only ever reached where
        something outside this terminal is holding the run -- where nothing is, the question
        offers staying here instead, an answer that cannot be carried out not being one.
        """
        session = self._session
        if session is None or not session.attached:
            # The reader went while the question was up, which is the run carrying on either
            # way: what would have been let go of has let go of itself.
            self.show("hmz: nothing is reading this run to let go of", "red")
            return
        session.detach()

    def reattached(self) -> None:
        """Draws the whole screen again, for a terminal that has just begun reading this.

        A terminal that has just arrived has none of what was drawn before it: it is in
        whatever modes the shell left it in, at whatever size it happens to be, showing
        whatever was on it. So the interface is stopped and started again on it, which is
        what puts the modes back and draws every row from the top.

        Called from whatever is holding the run, on a thread of its own.
        """
        with contextlib.suppress(Exception), self.suspend():
            pass

    def _close_btw(self) -> None:
        """Closes the optional side sessions without touching any flow session."""
        with self._btw_lock:
            self._btw_closed = True
            self._btw_generation += 1
            held = [session for _, session in self._btw_active.values()]
            self._btw_active.clear()
            self._btw_running.clear()
        for session in held:
            with contextlib.suppress(Exception):
                session.close()

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
        editor = self.query_one(Editor)
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
            self.show("[dim]— press ctrl+c again to leave —[/dim]")
        self._draw()

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
        run, self._stopping = self._stopping, None
        self._presses = 0
        if run is None:
            return
        closing = [
            session
            for agent in self._ran
            for session in agent.sessions
            if session in self._working
        ]
        if closing:
            self.show(
                f"[dim]— closing {len(closing)} conversation(s) under their turns —[/dim]"
            )
        # On this thread, as telling the flow to stop is: closing a conversation is closing
        # the process behind it, which is a second at the outside.
        run.close()
        for session in closing:
            self._working.discard(session)

    def __init__(
        self,
        flow: str = "",
        agents: Mapping[str, Runs] | None = None,
        params: BaseModel | None = None,
        session: Session | None = None,
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
          session: What is holding this run somewhere a terminal closing cannot reach, or
            None for one opened in the terminal it is drawn on -- where letting go of the
            terminal and stopping the run are the same thing, and `/exit` offers staying
            here rather than an answer that cannot be carried out.
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
        #: What is holding this run where a terminal closing cannot reach it, or None for one
        #: that is only in the terminal it was opened in. The whole of what the interface
        #: knows about that: how many terminals are reading, and how to let go of them.
        self._session = session
        #: The run going now, or None: which is what `a flow is running` means here.
        self._run: _Running | None = None
        #: Which run is the one going now, counted: what the person outside it is asked is
        #: answered only while the run asking is still the one going.
        self._generation = 0
        #: The agents behind the sessions the run going now has opened, which is who a typed
        #: line is said to. One per session, each named for the role it was opened for.
        self._agents: list[AgentBase] = []
        #: What the flow has done so far, which is what the right-hand column shows, and who
        #: reads the agents' own logs into it while it runs.
        self._monitor = Monitor()
        self._tally = Tally([], self._monitor)
        #: The task of the run in front of us and a bounded plain record of what its agent
        #: streams have said. `/btw` reads these once, as a snapshot; it never reaches into a
        #: flow's conversations for context, because doing that would make the side question a
        #: turn of the flow. The same lock holds the side sessions, since their threads add and
        #: remove them while the interface thread may close them on the way out.
        self._flow_task = ""
        self._btw_events: deque[Observation] = deque(maxlen=_BTW_EVENTS)
        self._btw_active: dict[int, tuple[AgentBase, SessionBase]] = {}
        self._btw_running: set[int] = set()
        self._btw_lock = threading.Lock()
        self._btw_serial = 0
        self._btw_generation = 0
        self._btw_closed = False
        #: Whether what a turn did on its way to an answer -- the tools it used, the thinking
        #: it did aloud, whatever it printed on its way past -- is shown, which `/details`
        #: toggles. Off, because a flow is watched to see where it has got to: what the
        #: agents said to each other and to you is that, and a tool row per file read is a
        #: transcript nobody is reading and the answer scrolled off the top of it.
        self._details = False
        #: Whether anybody is here to be asked, which `/afk` toggles. They are, until you say
        #: you are not: a flow that asks the person outside it and is answered by nobody is a
        #: flow that has stopped. Away, the outworlder answers what an away one answers.
        self._afk = False
        #: The question the flow has stopped on, if one has, and where its answer goes -- and
        #: which agent it was shown against, so that what it will take for an answer is shown
        #: under it rather than wherever the person is looking by the time it lands.
        self._asked_on: str | None = None
        self._asking: Question | None = None
        self._answer = ""
        self._answered = threading.Event()
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
        #: humanize, as the one object everything the interface does goes through: the
        #: flows there are, the agents and accounts they run as, the runs already made here
        #: and the run being started now. Reached through the daemon, which is the process a
        #: run of this workspace is held in and so where the interface asks for one. A
        #: command line holds the same object, reached the short way.
        self.hmz = Hmz()
        #: What this workspace was last set up to run, so that opening it again finds it
        #: that way rather than back at the default.
        self.settings = self.hmz.settings
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
        self._stopping: _Running | None = None
        #: The agents of the last run, which outlive it: their transcripts are still on the
        #: screen when the flow is over, so the diagram that reads one out is still about
        #: them. The run going now's are the same list, filled as its sessions open.
        self._ran: list[AgentBase] = []
        #: The conversations with a turn open, which are the only ones a typed line can go
        #: into: one written to a conversation between turns is answered on its own, outside
        #: the flow. Weakly held, for the reason the transcript is.
        self._working: weakref.WeakSet[SessionBase] = weakref.WeakSet()
        #: Said while no turn was open, for whichever turn starts next to take. Written from
        #: the event loop and drained from whichever thread a flow runs on, so it is held
        #: under a lock: `a running flow never drops a line` is only true if nothing races.
        self._queued: list[str] = []
        #: Said into a turn that was running, and not yet answered for: what a backend takes
        #: from us is not what the agent has heard, and every one of them says the second
        #: thing separately, as a `took`. Held under the same lock as `(agent, words)`, at
        #: most one per agent -- the next goes only once this one is answered for.
        self._given: list[tuple[str, str]] = []
        self._saying = threading.Lock()
        #: Whether the person has just been asked what to say next and answered out of the
        #: queue, in which case the turn that answer starts has its line already.
        self._handed = False
        #: Set when something is said, so a flow waiting to be told hears it at once rather
        #: than at the next tick, and whether a flow is waiting to be told at all.
        self._spoke = threading.Event()
        self._awaiting = False

    def said(self) -> dict[str, Any]:
        """What this interface says about the run it is holding, for the daemon's status.

        Called from the daemon's own thread, so it reads what the run keeps under its own
        locks and nothing of the screen. As JSON: a budget with no limit on its cost is
        written as the string `Infinity`, which reads back.

        Returns:
          The flow, what the run may spend and what it has spent -- the two as None with
          nothing running.
        """
        import json

        run = self._run
        return {
            "flow": run.flow if run is not None else self._flow_named,
            "budget": json.loads(run.budget.model_dump_json())
            if run is not None
            else None,
            "usage": json.loads(run.usage.model_dump_json())
            if run is not None
            else None,
        }

    @property
    def _named_by(self) -> tuple[str, ...]:
        """The agent roles somebody chooses an agent for, in the order the flow declares them.

        What a line about one says, and what every transcript but the shared one is named
        by. For a flow that will not load, the roles something was remembered for.
        """
        if self._declared is not None:
            return self._declared.roles
        return tuple(self._models)

    def _in_order(self) -> list[Runs]:
        """What each agent role runs, in the order the flow declares them."""
        return [self._models.get(role, Runs("")) for role in self._named_by]

    def compose(self) -> ComposeResult:
        """The transcript, the offers, the editor, the status. The width is the transcript's.

        Nothing sits beside it. What the flow is doing is on `/monitor`, which is opened when
        it is wanted: a column saying so the whole time costs a fifth of every line of every
        transcript, to say something that has usually not changed since it was last looked at.
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
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        self._asks_what_runs()
        self._asks_about_reports()
        self._freshens_flows()
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

    @work
    async def _asks_what_runs(self) -> None:
        """Asks each backend here what it runs, the once, for the account nobody chose.

        Only the ones that have never been asked: what a CLI runs is kept, and this is the
        first filling of it -- the moment before that, there is nothing to offer at any of the
        sheets and nothing to open talking to.

        In the background and one at a time, because asking means starting a coding agent,
        or reaching the endpoint an account points one at: a prompt cannot wait on either, and
        six at once is six of them. A backend that will not answer is left alone rather than
        retried -- `r` on the models is what asks again.
        """
        import asyncio

        accounts = self.hmz.accounts
        for backend in installed():
            if accounts.asked(backend):
                continue
            try:
                await asyncio.to_thread(accounts.ask, backend)
            except Exception as why:  # noqa: BLE001 -- a CLI that will not say what it runs
                # Not raised at whoever opened the interface: nobody asked for this, and a
                # backend that will not answer is one to ask again from the models.
                self.log(f"{backend} did not say what it runs: {why}")
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
        download nobody asked for -- `r` is still how somebody says they meant that.

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
                self.log(f"{one.name} was not fetched again: {why}")
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

        Output is barred rather than indented because that is what opencode does with it:
        a command and what it said are one block, set apart from the words around them.

        Only with `/details` on. What a backend writes on its way past is the working rather
        than the answer -- the same thing its tool rows and its thinking are -- and a flow
        watched to see where it has got to is one where all of that is in the way. The raw
        line is still retained in the bounded `/btw` snapshot when details are off.
        """
        if event.text.strip():
            # Flow-owned progress (for example, a Ralph round counter) is useful to `/btw`
            # even when `/details` keeps it out of the visible transcript.
            with self._btw_lock:
                self._btw_events.append(
                    Observation(
                        agent="",
                        kind="flow",
                        text=compact(event.text),
                        at=time.monotonic(),
                    )
                )
        if event.text.strip() and self._details:
            for line in escape(event.text.rstrip("\n")).splitlines():
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

    def _said_by_you(self, text: str, whose: str = "") -> None:
        """Puts something you said in the transcript, behind the `❯` Claude Code marks it with.

        Args:
          text: What was said.
          whose: The agent it was put to, where it went to one -- so that it lands on that
            agent's transcript and on the one they all appear on, as everything else that
            agent says does. A word put into a turn is part of that conversation, and would
            otherwise be on whichever screen happened to be up when the agent took it. "" for
            a line that went to nobody in particular: a command, the task that starts a flow,
            a line a flow that ended never took.
        """
        # What is read next starts its own part.
        self._keeping(whose or None).packed = False
        said = escape(text).splitlines() or [""]
        for line in (
            "",
            f"[dim]{_YOURS}[/] {said[0]}",
            *(f"  {one}" for one in said[1:]),
        ):
            self._into(whose or None, line)

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

    def _into(self, whose: str | None, content: object, *, shrink: bool = True) -> None:
        """Keeps something on the transcripts it belongs on, and draws it if one is read.

        An agent's line goes on two: that agent's own, and the one where every agent's work
        appears together. Which is what makes the second a place to watch a flow from rather
        than a copy of one agent -- and what makes stepping onto an agent a transcript of
        that agent rather than the screen carrying on.

        Args:
          whose: The agent it is from, or None for the interface's own -- which belongs to
            whichever transcript is being read, since that is the one it was said over.
          content: What to draw, as markup or as something Rich renders.
          shrink: Whether to draw it to fit.
        """
        where = [_EVERY, whose] if whose else [self._attached]
        for one in where:
            kept = self._keeping(one)
            if one == _EVERY and whose and kept.spoke != whose:
                # Two agents working at once are two agents whose lines land here in the
                # order they were said, so the one being read from has to be said. Once, as
                # it changes: a name against every line is a column nobody is reading.
                kept.spoke = whose
                self._writes(one, _Shown("", shrink=True))
                said = f"[dim]{_RULE * 2} {escape(short(whose))}[/]"
                self._writes(one, _Shown(said, shrink=True))
            self._writes(one, _Shown(content, shrink))

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
        # The oldest go first, and never the one being read, the one all of them are on, or
        # the one just opened: a machine that has run twenty flows would otherwise keep every
        # agent of all of them, and what is dropped this way is an agent no flow still holds.
        over = len(self._kept) - _KEPT
        dropping = [
            one for one in self._kept if one not in (_EVERY, key, self._attached)
        ]
        for gone in dropping[: max(over, 0)]:
            del self._kept[gone]
        return kept

    def _conversations(self) -> list[tuple[AgentBase, SessionBase]]:
        """Every conversation the flow has open, in the order the flow takes its agents.

        The person is not among them: they are an agent a flow talks to rather than one it
        drives, and the conversation with them is this prompt.

        Returns:
          The agent and the conversation, agents in the order the flow takes them and each of
          their conversations oldest first.
        """
        from hmz.coganchor.agents import HumanAgent

        return [
            (agent, session)
            for agent in self._agents
            if not isinstance(agent, HumanAgent)
            for session in agent.sessions
        ]

    def _driven(self) -> list[AgentBase]:
        """The agents there are transcripts of, which is the run's or the last run's.

        The last run's once it is over, because its transcripts are still on the screen and
        still worth reading back: a run that ended is the one somebody wants to look at.
        Nothing that asks this can mistake one for a flow that is running -- what is working
        is asked of the conversations, and there are none of those once a run is over.

        Returns:
          One per session opened, oldest first, each named for its role.
        """
        return list(self._agents or self._ran)

    def _of(self, role: str) -> list[AgentBase]:
        """The agents behind every session one role has opened, oldest first."""
        return [one for one in self._driven() if one.id == role]

    def _working_agents(self) -> list[str]:
        """Which of the flow's roles have a turn open, in the order they opened sessions.

        Returns:
          Their names. These are the ones tab steps between: with ten agents going, what
          somebody is stepping between is the ones thinking.
        """
        return list(
            dict.fromkeys(
                agent.id
                for agent in self._driven()
                if any(session in self._working for session in agent.sessions)
            )
        )

    def _reading(self) -> AgentBase | None:
        """The agent being read, where one role is rather than all of them.

        Returns:
          The newest agent of that role, or None on the transcript they all appear on and
          for one whose flow is over -- the transcript stays up either way, there being
          nothing to say to it.
        """
        held = self._of(self._attached) if self._attached != _EVERY else []
        return held[-1] if held else None

    def _says_to(self) -> SessionBase | None:
        """Which conversation a typed line goes into, which is the one on the screen.

        The agent being read is what is being said to; of its conversations, the one with a
        turn open, since a line written to one between turns is answered on its own outside
        the flow. Where all of them are being read there is no one agent to have meant, so it
        is whichever has a turn open -- which is what the transcript is showing.

        Returns:
          The conversation, or None where there is none open to say it to yet.
        """
        agent = self._reading()
        if agent is not None:
            return self._working_in(agent)
        working = [one for _, one in self._conversations() if one in self._working]
        return working[0] if working else None

    def _now_reading(self, whose: str, *, stepped: bool = True) -> None:
        """Reads one of the transcripts there are, drawing it from the top.

        From the top, and not by carrying on where the screen was: what an agent has done is
        that agent's transcript, and a screen that only appended would be every agent's lines
        shuffled into one another. Stepping between an agent's own conversations is not this
        -- they are all one transcript, so a loop that opens one a turn goes on down the same
        screen rather than replacing it.

        Args:
          whose: Which transcript, as `_keeping` names them.
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
        held = sum(len(one.sessions) for one in self._of(whose)) if whose else 0
        many = f"{_DOT}{held} conversations" if held > 1 else ""
        named = "every agent" if whose == _EVERY else f"{escape(short(whose))}{many}"
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
            agents = self._of(role)
            held.append(
                Held(
                    many=sum(len(agent.sessions) for agent in agents),
                    reading=role == self._attached,
                    unread=self._unread(role),
                    working=any(
                        one in self._working
                        for agent in agents
                        for one in agent.sessions
                    ),
                )
            )
        return held

    def action_attach_next(self) -> None:
        """Reads the next agent that is working, which is what tab is for."""
        self._attach_by(1)

    def action_attach_previous(self) -> None:
        """Reads the one before it, which is what shift+tab is for."""
        self._attach_by(-1)

    def _ring(self) -> list[str]:
        """What tab steps round: the transcript all of them are on, then the ones working.

        The ones working rather than every agent the flow drives: with ten agents going,
        what somebody is stepping between is the ones thinking. Every agent there is can
        still be read, from the diagram on `/monitor`, which is where an agent that has
        stopped is picked out by name rather than stepped past.

        Returns:
          The transcripts to step round, the one they are all on first -- so that there is
          always the way back to watching the flow rather than one agent of it.
        """
        return [_EVERY, *self._working_agents()]

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
    def _offer(self) -> None:
        """Offers whatever the line being typed could be finished with.

        Reconsidered when the cursor moves as well as when the text does: an offer made at
        the end of a line does not still stand once the cursor is back in the middle of it.
        """
        editor = self.query_one(Editor)
        typed = editor.text
        # At the end of what is being typed, and being typed rather than walked to.
        at_end = editor.cursor_location == editor.document.end and not editor.walking
        # And nothing against a `$` while an agent is waiting on an answer: the next line
        # typed is that answer, whatever it begins with, so a list that took the enter would
        # finish a flow's name over an answer nobody ever gave.
        answering = self._asking is not None and typed.startswith("$")
        offers = offered(typed, _COMMANDS) if at_end and not answering else []
        # Nothing left to finish, but a command still being written: its own line stays up,
        # since what it takes after its name is written there and is what is wanted just
        # then. Shown and not offered -- `offering` is what says a key is the list's.
        hint = hinted(typed, _COMMANDS) if at_end and not offers else ""
        listing = self.query_one("#offers", OptionList)
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
            listing.highlighted = 0

    @staticmethod
    def _offer_of(offer: str) -> Option:
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
        about = command.about if command else ""
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
        if self._run is not None and not working and self._awaiting:
            # A flow that has run out of things to do until it is told one. Spinning a bar at
            # it would read as a turn that has been thinking for as long as you have been
            # deciding what to say, which is the opposite of what is happening.
            left = f"[$text-muted]{_SPINNER[0]} waiting for you{_DOT}ctrl+c twice to stop[/]"
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
        if self._afk:
            left = f"[$warning]afk[/]{_DOT}{left}"
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
            "no agent installed" if self._named_by else "no agent to choose"
        ]
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
            " ▸ ".join(named_as(one.ref) for one in self.hmz.flows.running())
            or self._flow_named
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
        with self._saying:
            # What has gone to an agent went before anything still queued, the queue being
            # drained from the front, so it reads oldest first the same way the transcript does.
            held = list(self._given) + [("", said) for said in self._queued]
        if not held:
            return []
        # One line of the pin is one row of the screen: what is over is cut with an ellipsis
        # rather than wrapped, or a pasted paragraph would be five lines and fifty rows, and
        # the transcript, the editor and the status line would all go off the bottom.
        room = max(_NARROW, self.size.width - beside - len(_YOURS) - 5)
        lines: list[str] = []
        for at, (who, said) in enumerate(held):
            first, *rest = said.splitlines() or [""]
            # Who has it, for a word already put to somebody: a flow drives several agents,
            # and which of them is holding your line is the half of this worth knowing.
            with_it = f"{_DOT}with {short(who)}" if who else ""
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
            self.show(f"hmz: say on or off, not {argv[0]!r}", "red")
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
            return ["↑↓ move", "tab take", "esc dismiss"]
        keys: list[str] = []
        if self.query_one(Editor).text:
            # Enter does nothing with nothing typed, and a key that does nothing is not one
            # to offer: what it would do next is what it is called here.
            keys.append(
                "enter answer"
                if self._asking is not None
                else "enter say"
                if self._run is not None
                else "enter start"
            )
        if len(self._ring()) > 1:
            # Only with somewhere to step: with nothing working there is the one transcript
            # every agent is on, and a key that lands back where it started is not a key.
            keys.append("tab agent")
        keys.append("/ commands")
        keys.append("shift+enter newline")
        keys.append("esc monitor")
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
            keys.append("ctrl+c close them")
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
        if self._run is not None:
            self.show(
                f"hmz: {what} while a flow is running: ctrl+c twice stops it first",
                "red",
            )
            return True
        # Told to stop and not yet gone. A flow unwinds in its own time -- a loop sleeps off
        # its round, a turn is closed out -- and it writes down where it got to as it goes,
        # so a run picked up from a state that is still moving is a round done twice. And
        # `ctrl+c twice` is not the answer here: it has already been pressed.
        if self._stopping is not None:
            self.show(
                f"hmz: {what} while the flow is still stopping: {_UNWINDING}", "red"
            )
            return True
        return False

    @work
    async def action_monitor(self) -> None:
        """Opens the run, drawn, which is what esc is.

        Readable while a flow runs, unlike the two that choose something: it changes nothing
        about the run, so there is nothing for it to conflict with. The one thing it answers
        with is which transcript to read, the diagram being where an agent is picked out by
        name -- working or not, which is what tab is held to.
        """
        reading = await self.push_screen_wait(
            Monitoring(
                self._flow_named,
                self._named_by,
                self._in_order(),
                self._monitor,
                self._params,
                drawn=self._boxes,
                reading=self._attached,
                board=self._board,
            )
        )
        if reading is not None:
            self._now_reading(reading)
            self._draw()

    def _board(self) -> Board | None:
        """The board this run has, or None for one whose flow does not talk to the person.

        The person's rather than the flow's: a flow is a function that returns, and the board
        outlives any one turn of it -- so it is held by the one agent of a run that nobody
        chose and nothing takes a turn of.

        Returns:
          The board, or None where the flow being run declares no person.
        """
        from hmz.coganchor.agents import HumanAgent

        held = self._agents or self._ran
        return next(
            (one.board for one in held if isinstance(one, HumanAgent)),
            None,
        )

    def _boxes(self) -> list[Drawn]:
        """The roles that have worked, as the diagram draws them, in the flow's own order.

        The ones that have worked rather than the ones the flow declares. A flow may declare
        ten roles and reach three of them, and seven boxes that have never done anything are
        seven rows saying nothing -- the diagram is what the run *is doing*. Each appears as
        its first turn starts and stays for the rest of the run, which is what makes this a
        picture of the run growing rather than a list of what was configured.

        Returns:
          One per role that has taken a turn, in the order the flow declares them, and
          nothing at all before the first turn of a run -- which is a sheet about what is set
          up rather than about what it is doing.
        """
        shape = self._monitor.shape()
        named = self._named_by
        seen = list(dict.fromkeys(agent.id for agent in self._driven()))
        seen.sort(key=lambda who: named.index(who) if who in named else len(named))
        drawn: list[Drawn] = []
        for who in seen:
            working = any(
                one in self._working
                for agent in self._of(who)
                for one in agent.sessions
            )
            if not (working or shape.turns.get(who, 0)):
                continue
            drawn.append(
                Drawn(
                    who=who,
                    named=who,
                    runs=self._models[who].spec if who in self._models else "",
                    working=working,
                    reading=who == self._attached,
                    unread=self._unread(who),
                )
            )
        return drawn

    @on(Editor.Sent)
    def _sent(self, event: Editor.Sent) -> None:
        """Takes what was typed as a flow to start, as a command, or as something to say."""
        line = event.text
        # Written down whatever it turns out to be: a task, a word put into a running flow,
        # a command. All three were typed, and any of them may be worth typing again.
        self.history.add(line)
        # A `$` names the flow to run and, after it, what to run it on. Not while a question
        # is up: the next line typed is the answer to that, whatever it begins with, and an
        # agent left waiting on an answer that went off to start a flow is a stopped turn.
        if line.startswith("$") and self._asking is None:
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
        command.does(self, argv)

    def action_details(self, argv: Sequence[str] = ()) -> None:
        """Turns the working on or off, and says which way it went.

        Args:
          argv: What was written after the name, which is `on`, `off`, or nothing at all.
        """
        if (switched := self._switched(argv, now=self._details)) is None:
            return
        self._details = switched
        self.show(
            "[dim]showing the working: every tool call, all of the thinking, and "
            "whatever a backend prints on its way past[/dim]"
            if self._details
            else "[dim]showing what each turn said, and nothing of how it got there[/dim]"
        )
        self._draw()  # and the status line says which mode this is in from now on

    def action_afk(self, argv: Sequence[str] = ()) -> None:
        """Says whether anybody is here to be asked, and marks the status line with it.

        Args:
          argv: What was written after the name, which is `on`, `off`, or nothing at all.
        """
        if (switched := self._switched(argv, now=self._afk)) is None:
            return
        self._afk = switched
        self.show(
            "[dim]away: an agent that wants to ask is told nobody is here[/dim]"
            if self._afk
            else "[dim]here: an agent may stop and ask you[/dim]"
        )
        # Said once in the transcript and from now on in the status line: a line that has
        # scrolled away is not how somebody finds out that an agent may not reach them.
        self._draw()

    def action_btw(self, question: str = "") -> None:
        """Answers a side question from a frozen flow snapshot.

        A side question must never become a steer. It is answered by a short-lived clone of
        one of the flow's coding agents, with read-only permissions and no flow skills, while
        the primary sessions continue on their own threads. The prompt contains the runtime
        observations collected by :meth:`_heard`, so the clone does not need to inspect or
        lock the primary conversation.

        Args:
          question: What to ask, without the ``/btw`` command name.
        """
        question = " ".join(question.split())
        if not question:
            self.show("hmz: usage: /btw <question>", "red")
            return
        if self._run is None:
            self.show("hmz: /btw needs a flow that is running", "red")
            return
        candidates = self._btw_candidates()
        if not candidates:
            self.show(
                "hmz: /btw needs a coding agent that supports read-only turns", "red"
            )
            return
        with self._btw_lock:
            if self._btw_closed:
                return
            if len(self._btw_running) >= _BTW_ACTIVE:
                self.show(
                    f"hmz: /btw already has {_BTW_ACTIVE} questions in progress", "red"
                )
                return
            self._btw_serial += 1
            request = self._btw_serial
            generation = self._btw_generation
            self._btw_running.add(request)
        try:
            snapshot = self._btw_snapshot()
            prompt = format_snapshot(snapshot, question)
        except Exception as why:  # noqa: BLE001 -- an observation failure must not break the UI
            with self._btw_lock:
                self._btw_running.discard(request)
            self.show(f"hmz: /btw could not read flow progress: {why}", "red")
            return
        self.show(f"[dim]btw: checking the flow for {escape(question)}…[/dim]")
        worker = threading.Thread(
            target=self._run_btw,
            args=(request, question, prompt, tuple(candidates), generation),
            daemon=True,
            name=f"humanize-btw-{request}",
        )
        try:
            worker.start()
        except RuntimeError as why:
            with self._btw_lock:
                self._btw_running.discard(request)
            self.show(f"hmz: /btw could not start: {why}", "red")

    def _btw_snapshot(self) -> FlowSnapshot:
        """Copies the current run into a prompt-sized, immutable observation."""
        shape = self._monitor.shape()
        # One per role, however many sessions it opened: a role is what is watched, and each
        # of its sessions is an agent of its own named for it.
        driven = {agent.id: agent for agent in self._agents if agent.id}
        agents = tuple(
            AgentProgress(
                agent=who,
                model=agent.config.model,
                turns=shape.turns.get(who, 0),
                working=who in shape.working,
            )
            for who, agent in driven.items()
        )
        handovers = tuple(
            sorted(
                (
                    sender,
                    receiver,
                    count,
                )
                for (sender, receiver), count in shape.handovers.items()
                if count > 0
            )
        )
        with self._btw_lock:
            observations = tuple(self._btw_events)
        with self._saying:
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
        # The role beside the id the monitor and the handovers use, which is the same word.
        labelled = tuple(
            AgentProgress(
                agent=item.agent,
                model=item.model,
                turns=item.turns,
                working=item.working,
                role=item.agent,
            )
            for item in agents
        )
        return FlowSnapshot(
            flow=self._flowing(),
            task=self._flow_task,
            workspace=_where(),
            elapsed=elapsed,
            finished=ended is not None,
            agents=labelled,
            handovers=handovers,
            observations=observations,
            waiting=waiting,
            spent=spent,
            kinds=counted,
            waiting_for_input=self._awaiting,
        )

    def _btw_candidates(self) -> list[AgentBase]:
        """Orders usable coding agents for a side question, without including the person."""
        from hmz.coganchor.agents import HumanAgent

        reading = self._reading()
        ordered = ([reading] if reading is not None else []) + list(self._agents)
        candidates: list[AgentBase] = []
        for agent in ordered:
            if isinstance(agent, HumanAgent) or agent in candidates:
                continue
            candidates.append(agent)
        return candidates

    def _btw_clone(self, source: AgentBase, request: int) -> AgentBase:
        """Makes a read-only, skill-free agent that is invisible to the primary run."""
        from dataclasses import replace

        # `permission` is part of every AgentConfig, including backend-specific subclasses.
        # A backend that cannot express read-only raises here; the caller tries another agent
        # rather than silently running a side question with the flow's write permissions.
        settings: dict[str, object] = {"permission": "read-only", "goals": False}
        # Claude's optional allow-list can auto-approve a write even in a normal permission
        # mode. A side question has no reason to carry the flow's explicit tool grants.
        if hasattr(source.config, "allowed_tools"):
            settings["allowed_tools"] = ()
        # Cursor's is the same thing said about MCP servers: read-only is about edits, so a
        # side question would otherwise reach every server this workspace names on the flow's
        # say-so rather than on anybody's answer.
        if hasattr(source.config, "approve_mcps"):
            settings["approve_mcps"] = False
        config = replace(source.config, **settings)
        try:
            clone = source.clone(
                config=config,
                name=f"btw-{request}",
                skills=(),
            )
        except TypeError:
            # A third-party AgentBase written before the optional skills argument may still
            # implement clone(config=, name=). Clear its inherited skills after construction.
            clone = source.clone(config=config, name=f"btw-{request}")
            clone.loads(())
        # A watcher prevents command-backed backends from echoing the side answer to the
        # interface's captured stdout. It is intentionally not the primary app watcher.
        clone.watch(_quiet_watch)
        return clone

    def _btw_cwd(self, source: AgentBase) -> str | None:
        """Uses an already-open conversation's directory when one is available."""
        session = self._working_in(source)
        if session is None:
            return None
        try:
            return session.cwd
        except (OSError, RuntimeError, ValueError):
            return None

    def _run_btw(
        self,
        request: int,
        question: str,
        prompt: str,
        candidates: tuple[AgentBase, ...] = (),
        generation: int | None = None,
    ) -> None:
        """Runs one isolated side turn and posts only its final display event."""
        answer = ""
        failure = ""
        try:
            for source in candidates or tuple(self._btw_candidates()):
                with self._btw_lock:
                    if self._btw_closed or (
                        generation is not None and generation != self._btw_generation
                    ):
                        return
                side: AgentBase | None = None
                session: SessionBase | None = None
                try:
                    side = self._btw_clone(source, request)
                    cwd = self._btw_cwd(source)
                    session = side.new() if cwd is None else side.new(cwd)
                    with self._btw_lock:
                        if self._btw_closed or (
                            generation is not None
                            and generation != self._btw_generation
                        ):
                            session.close()
                            return
                        self._btw_active[request] = (side, session)
                    answered = session(prompt)
                    answer = str(answered or "").strip()
                    if answer:
                        break
                    failure = "the side agent returned no answer"
                except Exception as why:  # noqa: BLE001 -- a backend may fail independently
                    failure = str(why) or type(why).__name__
                finally:
                    if session is not None:
                        with contextlib.suppress(Exception):
                            session.close()
                    elif side is not None:
                        with contextlib.suppress(Exception):
                            side.stop()
                    with self._btw_lock:
                        held = self._btw_active.get(request)
                        if held is not None and held[1] is session:
                            self._btw_active.pop(request, None)
                if answer:
                    break
        finally:
            with self._btw_lock:
                self._btw_running.discard(request)
                closed = self._btw_closed or (
                    generation is not None and generation != self._btw_generation
                )
        if closed:
            return
        if answer:
            self._on_screen(self._btw_answer, question, answer)
        else:
            self._on_screen(
                self._btw_failed,
                question,
                failure or "no read-only coding agent is available",
            )

    def _btw_answer(self, question: str, answer: str) -> None:
        """Shows a completed side answer in the current transcript."""
        lines = escape(answer).splitlines() or [""]
        self._part(
            None,
            "\n".join(
                [
                    f"[cyan]{_SAID}[/] [dim]btw · {escape(question)}[/] {lines[0]}",
                    *(f"  {line}" for line in lines[1:]),
                ]
            ),
            packs=False,
        )
        self._draw()

    def _btw_failed(self, question: str, failure: str) -> None:
        """Reports a side-question failure without reporting it as a flow failure."""
        del question  # The command itself is already in the transcript.
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

        A flow already told to stop is said to be stopping rather than told again: stopping
        hands the agents it is holding on to the ones on their way out, and running it over an
        empty list would hand nothing on and drop the ones already there -- which is the third
        press losing its only way to the conversations still open under their turns.

        Nothing running at all is said as well. The key never says that, because with nothing
        running it is the key that leaves and what it says is about leaving; `/stop` has only
        the one thing to mean, and a command typed on purpose that answers with nothing reads
        as a command that did not work.

        Whatever it found, the count of presses goes back to nothing, which is what the second
        press does after it stops a flow. A `/stop` is not a press and must not be counted as
        one -- but neither may it leave a press made before it standing, or the press made
        after it would be the second of a gesture the command interrupted: with the flow by
        then unwound, that is the interface closing on one key after a line that said there
        was nothing to stop.
        """
        if self._run is not None:
            self.action_stop_flow()
        elif self._stopping is not None:
            self.show(f"hmz: the flow is already stopping: {_UNWINDING}", "red")
        else:
            self.show("hmz: no flow is running, so there is nothing to stop", "red")
        self._presses = 0
        self._draw()  # rather than at the next tick: it was just typed

    def action_stop_flow(self) -> None:
        """Stops the whole flow, not just the turn -- which is the second ctrl+c or `/stop`.

        The turn running now is interrupted and every call of the flow unwinds from where it
        stands, closing what it opened. The run is let go of here rather than when its own
        thread notices, so that the next thing said starts something instead of being put to
        a flow that is on its way out -- and kept as the one stopping, since a flow unwinds in
        its own time and the press after this one is the one that does not wait for it.

        Silent when nothing is running, every caller having its own answer for that: the key
        is mid-gesture and the press after it says what it does, a flow chosen while none runs
        has nothing to say about the one that was not there, and `/stop` looks before it calls
        this and says for itself that there was nothing to stop.
        """
        run = self._run
        if run is None:
            return
        run.stop()
        self.show("[dim]— stopping the flow —[/dim]")
        # Held by identity, so that the run's own thread can say when it has finished
        # unwinding and nothing says it of a run that started since.
        self._run, self._stopping, self._agents = None, run, []
        self._spoke.set()  # and a flow waiting to be told hears that it is over
        self._answered.set()  # as does one waiting on an answer
        self._never_sent("the flow stopped first")

    def on_unmount(self) -> None:
        """Stops whatever is running as the interface goes, however it goes.

        A flow waiting to be told something waits on this interface, and nothing else will
        release it: an interface that went away without saying so would leave a thread
        waiting on a prompt that is not there, holding a backend open behind it. Said to
        nobody rather than to the transcript, which has gone with everything else.
        """
        for run in (self._run, self._stopping):
            if run is not None:
                run.close()
        self._run, self._stopping, self._agents = None, None, []
        self._spoke.set()
        self._answered.set()
        self._close_btw()

    def _never_sent(self, because: str) -> None:
        """Puts whatever was still waiting into the transcript, nothing being left to take it.

        A flow ends two ways -- stopped by hand, or of its own accord -- and both leave the
        pin holding lines that are not on their way anywhere. They come off it and into the
        transcript as what they turned out to be: a line typed at a flow that is gone has to
        be somewhere, or the next thing typed would quietly take its place.

        Args:
          because: What to say about why it never went.
        """
        with self._saying:
            held, self._queued = self._queued, []
            given, self._given = [text for _, text in self._given], []
        if not (held or given):
            return
        # Lines typed at a flow that is no longer there to take them. Counted rather than
        # read: what they said is theirs, and how many of them there were is the signal.
        telemetry.snag("lines-never-sent", how_many=len(held) + len(given))
        for (
            said
        ) in given:  # oldest first: what went to an agent went before what is queued
            self._said_by_you(said)
        if given:
            # Put to an agent, which never said it had it: it may well have reached the
            # model, and saying it never went would be as wrong as saying it landed.
            self.show(f"[dim]   put to the agent, never taken back: {because}[/dim]")
        for said in held:
            self._said_by_you(said)
        if held:
            self.show(f"[dim]   never sent: {because}[/dim]")
        self._draw()

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
            self.show("hmz: a flow is running; no choosing a flow", "red")
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
            self.show("hmz: a flow is running; no choosing a flow", "red")
            return
        chosen = self._remembered_for(named)
        if chosen is None:
            chosen = await self._chooses(named, running=False)
            if chosen is None:
                # Walked out of the menu, so nothing was chosen and nothing runs. Said, or a
                # line that was typed to start something would have vanished without a word.
                self.show("[dim]nothing was set up, so nothing was started[/dim]")
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
            return Chosen(flow, agents, envs, budget=budget_of(flow))
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
        return Chosen(flow, agents, envs, params, budget)

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
        ) == (self._flow_named, self._models, self._envs, self._params, self._budget)
        if not running and not same:
            # A flow is chosen in order to be run, so whatever is running stops: the interface
            # opens on one already, and a choice that quietly went to the back of the queue
            # behind it would read as no choice at all. Answering the same way twice is not a
            # choice, though, and must not end the conversation.
            self.action_stop_flow()
        # Read again whether or not it is the same flow: a fetch or an edit since may have
        # given it roles the menu was just saved with.
        self._declared = declared_of(chosen.flow)
        self._flow_named = chosen.flow
        self._models, self._envs = dict(chosen.agents), dict(chosen.envs)
        self._params, self._budget = chosen.params, chosen.budget
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
        )
        if running:
            self._reconfigured()
        elif not same and not starting:
            self.show("[dim]say what to do, and the flow starts on it[/dim]")
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
            "[dim]the roles of the run going now stay as it started; what was changed is "
            "what the next run starts on[/dim]"
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
            "[dim]humanize reports what goes wrong; /settings turns it off[/dim]"
            if said == "on"
            else "[dim]humanize reports nothing; /settings turns it on[/dim]"
        )

    @work
    async def action_settings(self) -> None:
        """Opens what humanize remembers, which is what `/settings` is for.

        Two pages: what is true of this machine, and what is remembered about this directory.
        Not refused while a flow runs -- nothing on it changes what is running.
        """
        # What is written down rather than what is happening: the environment may answer for
        # one run, and a menu that showed that would be a menu offering to change a thing it
        # cannot. The sheet says so under the list where the two differ.
        #
        # Read again rather than off the interface's own `Settings`, which was made when it
        # opened: the first-start question writes through one of its own, so the long-lived
        # one would show a machine that has just answered as one nobody has asked.
        written = Hmz().settings.enable_sentry
        profiling = self.settings.profiling
        said = await self.push_screen_wait(
            Adjusts(
                enable_sentry=written,
                overridden=telemetry.enabled() is not written,
                workspace=str(Path.cwd()),
                flow=self.settings.flow,
                agents=len(self.settings.agents(self.settings.flow)),
                flows=len(self.settings.flows()),
                profile=profiling,
            )
        )
        if said is None:
            return
        self._took_settings(said, written=written, profiling=profiling)

    def _took_settings(
        self,
        said: Adjusted,
        *,
        written: bool | None = None,
        profiling: bool = False,
    ) -> None:
        """Does what the settings menu was holding.

        Args:
          said: What it answered with.
          written: What was written down when it opened, so that a setting nobody moved is
            not written again.
          profiling: Whether this directory was already being profiled, for the same reason.
        """
        if said.enable_sentry is not None and said.enable_sentry != written:
            # Through the same road the first-start question takes, so that the answer is
            # written down, what was read is forgotten, and reporting starts or stops now
            # rather than at the next start.
            telemetry.asked(enable_sentry=said.enable_sentry)
            self.show(
                "[dim]humanize reports what goes wrong[/dim]"
                if said.enable_sentry
                else "[dim]humanize reports nothing[/dim]"
            )
        if said.profile != profiling:
            self.settings.profiles(on=said.profile)
            self.show(
                "[dim]a run here profiles the programs it starts; /epics collects the "
                "trace[/dim]"
                if said.profile
                else "[dim]a run here is traced and not profiled[/dim]"
            )
        if said.forget and self.settings.forget():
            self.show(
                "[dim]what was remembered about this directory is forgotten[/dim]"
            )

    @work
    async def action_flowverses(self) -> None:
        """Opens the places flows come from, which is what `/flowverses` is for.

        Not which flow to run -- that is `/flow`, where the arrows step between these places
        and the list holds the one being read, and where `v` opens this same menu. A command
        as well, because that is the way in while a flow runs: choosing a flow is not offered
        then, so neither is the list `v` is a key of. Not refused while one is going either --
        a flowverse fetched now is a flowverse the next run may reach for, and nothing here
        touches the flow that is running.
        """
        for one in await self.push_screen_wait(Flowverses()) or ():
            self.show(f"[dim]{one}[/dim]")

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
                "hmz: /resume takes nothing: it carries the last run here on, and /epics "
                "is where another one is named",
                "red",
            )
            return
        epics = self.hmz.epics
        runs = epics.all()  # oldest first, so the last of them is the last run
        if not runs:
            self.show(
                "hmz: no flow has been run here, so there is nothing to carry on from",
                "red",
            )
            return
        # Past every run of a flow that neither was nor is one to pick up -- a conversation
        # had since -- and no further: a run of one that was or is, or a record that cannot
        # be read, is the one this settles on, and says for itself what stands in its way.
        for epic in reversed(runs):
            ran = epics.read(epic)
            if ran is None or ran.resumable or self._picks_up(ran.flow):
                break
        else:
            self.show(
                "hmz: no run here was of a flow that can be picked up, so there is nothing "
                "to carry on from",
                "red",
            )
            return
        # Which run is the whole of what this command settles. Why a run cannot be carried
        # on is settled in one place for both ways in, so that a run walked into on `/epics`
        # is turned down for the same reasons in the same words.
        self._carries_on(epic)

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

    def _carries_on(self, epic: Path) -> None:
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
        """
        # Before anything is read, since it is the one refusal that is about now rather than
        # about the record: a run picked up is a flow started, and there is one going.
        if self._mid_run("no picking a run up"):
            return
        ran = self.hmz.epics.read(epic)
        if ran is None:
            self.show(
                f"hmz: {escape(epic.name)} cannot be read back, so there is nothing to "
                "carry on from",
                "red",
            )
            return
        if not self._picks_up(ran.flow):
            self.show(
                f"hmz: {escape(ran.flow)} does not say it can be picked up, so there is "
                f"nothing to carry on from in {escape(ran.name)}",
                "red",
            )
            return
        # A journal with nothing in it is a run killed before it wrote down where it had got
        # to, and carrying it on would be a run starting from the top wearing a line that
        # says which run it came from -- a record of something that did not happen.
        if not self.hmz.epics.picks_up(epic):
            self.show(
                f"hmz: {escape(ran.name)} left nothing behind, so there is nothing to "
                "carry on from: say what to do and the flow starts from the top",
                "red",
            )
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
        self.show(
            f"[dim]carrying on from {escape(ran.name)}: {escape(ran.flow)} on what that "
            "run left behind[/dim]"
        )
        self._flow(ran.task, resume=epic)

    @work
    async def action_fallback(self) -> None:
        """Opens where a turn goes when the place taking it cannot, which is `/fallback`.

        Its own menu rather than a row of the accounts, because it is not about accounts: a
        place is a CLI, an account and a model, and a turn with nowhere left to run is taken
        at another place entirely -- written between the two rather than on either.

        Not refused while a flow runs, as the accounts are not: what is written down here is
        read by a turn that has failed, so a step added now is one the next failure walks.
        """
        agents = installed()
        agents.update(installable())
        for one in await self.push_screen_wait(Fallbacks(agents)) or ():
            self.show(one)

    @work
    async def action_providers(self) -> None:
        """Opens the accounts an agent may be run as, which is what `/providers` is for.

        Not refused while a flow runs. What it holds is not what is running: an agent reads
        the account it was configured with once, so one made or taken away now is one the next
        session sees. A login that takes the terminal does hold the rest of the interface up
        while it has it, which is what handing the terminal over means.
        """
        said = await self.push_screen_wait(Providers())
        for one in said or ():
            self.show(one)

    def _at_turn_start(self) -> list[str]:
        """What a turn starting folds into its prompt, which is one waiting line, or none.

        None when the person has just handed the flow the line it is starting this turn on:
        that line is this turn's, and taking the one behind it as well would put the two in
        front of the agent together and have them answered once -- which is the same thing
        going wrong from the other side.

        Returns:
          The one line to fold in, or nothing at all.
        """
        with self._saying:
            if self._handed:
                self._handed = False
                return []
        return self._take()

    def _take(self) -> list[str]:
        """Takes the oldest thing said while nobody was working, and leaves the rest.

        One line, not the queue: five lines typed in a row are five things said, and folding
        them into one prompt would have them answered once. The one behind this goes into
        the turn after, or into this one the moment it is running.

        The queue is the interface's rather than any one agent's: a line is typed at the flow
        and reaches whichever agent asks for it first, which is what "a typed line reaches
        whoever has the turn" means. Both hooks drain it, and both drain it destructively, so
        a line is delivered once however it is asked for.

        Returns:
          The oldest thing said, as the one-line list a turn folds into its prompt, which is
          nothing at all when nothing is waiting.
        """
        with self._saying:
            if not self._queued:
                return []
            held = [self._queued.pop(0)]
        self._on_screen(self._went, held)
        return held

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

    def _went(self, held: list[str]) -> None:
        """Puts what was waiting into the transcript, now that it has gone.

        Args:
          held: What was taken, oldest first.
        """
        for said in held:
            self._said_by_you(said)
        self._draw()

    def _flow(self, task: str, resume: Path | None = None) -> None:
        """Starts the flow that is set up, keeping the run so that a typed line reaches it.

        Args:
          task: What it is to do.
          resume: The run to pick up, for a flow that says it can be picked up, or None for
            a run from the top.
        """
        if self._run is not None:
            self.show("hmz: a flow is already running", "red")
            return
        from hmz.runtime.flowing import open_outworlder
        from hmz.runtime.kept import written

        self._generation += 1
        generation = self._generation
        try:
            # Whoever is outside the run is whoever is at this prompt: asked on a thread of
            # the run's own, and away while `/afk` says so -- which a run asks as it asks.
            run: _Running = self.hmz.run(
                self._flow_named,
                task,
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
                params=self._params.model_dump() if self._params is not None else None,
                budget=self._budget,
                resume=resume if resume is not None else False,
                outworlder=open_outworlder(
                    ask=functools.partial(self._outworlder_asks, generation),
                    away=lambda: self._afk,
                ),
            )
        except Exception as why:  # noqa: BLE001 -- a flow that will not start is a line to fix
            self.show(f"hmz: {why}", "red")
            return
        agents: list[AgentBase] = []
        self._run, self._agents, self._ran = run, agents, agents
        with self._btw_lock:
            old_side_sessions = [session for _, session in self._btw_active.values()]
            self._btw_active.clear()
            self._btw_running.clear()
            self._flow_task = task
            self._btw_events.clear()
            self._btw_generation += 1
        for session in old_side_sessions:
            with contextlib.suppress(Exception):
                session.close()
        # Nothing is left of the flow before this one to press a key about, and what is
        # being read is one of its agents unless it was the transcript they all appear on.
        # Which is where a run is watched from, so it is where a run starts.
        self._stopping = None
        if self._attached != _EVERY:
            self._now_reading(_EVERY, stepped=False)
        self._monitor = Monitor()
        # What the run costs is read from the logs the agents keep, which they write as they
        # go: a backend only says what a turn cost once the turn is over, and a turn is long.
        self._tally = Tally([], self._monitor)
        self._tally.watch()
        with self._saying:
            self._queued, self._given, self._handed = [], [], False
        watching, tally = self._monitor, self._tally
        run.watch(self._heard)
        run.opened(functools.partial(self._opened, agents, watching, tally))
        self._draw()

        def drive() -> int:
            from hmz.flows import BudgetExceeded, FlowException
            from hmz.runtime import Refused

            try:
                run.run()
            except asyncio.CancelledError:
                pass  # stopped by hand, which said so as it was stopped
            except Refused as why:
                self._on_screen(self.show, f"hmz: {why}", "red")
            except BudgetExceeded as why:
                # The ordinary end of a budgeted loop rather than a crash: what a run is
                # given a budget for.
                self._on_screen(self.show, f"hmz: stopped -- {why}", "yellow")
            except FlowException as why:
                # A failure the flow API has a name for -- a harness that would not take the
                # turn, a machine that went away, a flow that refused what it was handed --
                # which is said as what it is rather than as a traceback nobody can act on.
                self._on_screen(self.show, f"hmz: {type(why).__name__}: {why}", "red")
            finally:
                tally.stops()  # read once more, for what the last turn wrote on its way out
                watching.stops()  # the clock the rate is over is the run's, and it is over
                # Only this run's own, and only while it is still the one running. A flow
                # takes a while to unwind after it is stopped, and the next flow may have
                # started in the meantime. Clearing then would leave the running one
                # unreachable, and saying it was done would be saying it of the wrong flow.
                if self._stopping is run:
                    # Stopped by hand, and now finished unwinding: there is nothing left for
                    # the press that does not wait for it to reach.
                    self._stopping = None
                if self._run is run:
                    self._run, self._agents = None, []
                    self._spoke.set()
                    self._answered.set()
                    self._on_screen(self.show, "[dim]— the flow is done —[/dim]")
                    # And whatever it never got round to taking, which is now on its way
                    # nowhere: a flow that ends of its own accord strands the pin exactly as
                    # one that is stopped does.
                    self._on_screen(self._never_sent, "the flow ended first")
            return 0

        self._background(drive)

    def _opened(
        self,
        agents: list[AgentBase],
        monitor: Monitor,
        tally: Tally,
        role: str,
        agent: AgentBase,
        session: SessionBase,
    ) -> None:
        """Takes one session a run has just opened as one of the run's own.

        Told on the run's own thread, before the session's first turn, with the agent behind
        it already named for its role: its transcript is that role's, what its backend counts
        is said to the monitor, and whichever turn of it starts next takes the oldest line
        that was held.

        Args:
          agents: The run's agents, which this one joins.
          monitor: The run's monitor.
          tally: What reads the run's logs.
          role: The role it was opened for.
          agent: The agent behind it.
          session: Its conversation.
        """
        del role, session
        agent.waiting = self._at_turn_start
        agents.append(agent)
        # What its backend counts, said before its first turn: a kind nothing was spent on
        # this turn is missing from that turn's reckoning exactly as a kind the CLI never
        # counts is, and what is drawn of a run driving two backends has to tell the two
        # apart to say which of its figures are whole.
        monitor.reporting(agent.id, type(agent).counts)
        tally.add(agent)

    def _remember_btw(self, agent: AgentBase, event: Event) -> None:
        """Keeps a compact progress record for future side questions.

        Reasoning is intentionally omitted: a side question needs observable progress, not a
        second copy of private chain-of-thought. The event stream still reaches the ordinary
        transcript exactly as before.
        """
        # A stopped flow can take a moment to unwind while a new one is already up. Its old
        # watcher is still bound to this method, but its events must not become progress for
        # the new run.
        if self._run is not None and not any(agent is held for held in self._agents):
            return
        if event.kind not in {
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
            event.text.split("\n\n", 1)[0]
            if event.kind == "begins"
            else "turn ended"
            if event.kind == "ends"
            else event.text
        )
        text = compact(text)
        with self._btw_lock:
            self._btw_events.append(
                Observation(
                    agent=agent.id, kind=event.kind, text=text, at=time.monotonic()
                )
            )

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Shows what a turn said, on the transcript of the agent that said it.

        And takes what it cost into what `/monitor` shows, which is per agent: an agent is
        what is read, and the bill is the agent's too.

        What is shown of a turn is what the turn was for unless `/details` says otherwise:
        the agent starting, what it said, and the agent stopping. The tools it used and the
        thinking it did aloud are how it got there, and a screen of them is a screen where
        the answer went past between two file reads. `/details` is what asks for all of it.

        Called from whichever thread the turn is running on, which is why everything drawn
        from here goes through `_on_screen`.

        Args:
          agent: Whose turn said it.
          session: Which of that agent's conversations said it, or None for something the
            agent said rather than one of them -- a question put by a server that speaks for
            every conversation it holds. Either way it is shown against the agent, all of
            whose conversations are the one transcript.
          event: What was said.
        """
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
        whole = sum(event.tokens.values())
        for model, tokens in event.tokens.items():
            if not event.spent:
                broken = None
            elif len(event.tokens) == 1:
                broken = dict(event.spent)  # the whole turn, on the one model it named
            elif whole > 0:
                broken = {
                    kind: spent * tokens / whole for kind, spent in event.spent.items()
                }
            else:
                # Two models and nothing on either. There is nothing to divide by and
                # nothing to divide, and a turn whose accounting raised would lose the
                # line it was about: what a watcher raises is swallowed.
                broken = None
            self._monitor.spend(agent.id, tokens, model=model, kinds=broken)
        # Anything at all the agent did, token or not: a tool, a word, an answer. A turn
        # spends most of its minutes between the counts it reports, and a figure worked out
        # only when one arrives stands still through all of them.
        self._monitor.stirring()
        self._remember_btw(agent, event)
        if event.kind == "result":
            # Kept to tell a flow saying an agent's answer back to the person -- a
            # conversation asking what next -- from a question it asks them.
            self._last_answer = event.text
        elif event.kind == "asks":
            self._last_asked = event.text
        if event.kind == "took":
            # The agent saying a word put into its turn is now in front of it, which is the
            # one thing that makes a word said rather than posted.
            self._on_screen(self._took, agent.id, event.text)
            return
        whose = agent.id
        if event.kind == "begins":
            self._monitor.begins(agent.id, agent.config.model)
            self._began[agent.id] = time.monotonic()
            if session is not None:
                # Which is what makes it a conversation a typed line may go into: one written
                # to a conversation between turns is answered on its own, outside the flow.
                self._working.add(session)
            # A turn takes minutes and says nothing for most of them, so the line that says
            # one has started is the whole of what a flow looks like while it thinks. Which
            # of that agent's conversations, where it has more than one: a loop that opens
            # one a turn runs them all down the one transcript, and this is where each of
            # them begins.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_SAID} {escape(short(agent.id))} is working"
                f"{self._conversation(agent, session)}[/]",
                packs=False,
            )
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
            if session is not None:
                self._working.discard(session)
            # Whatever it was holding is not on its way anywhere now: the turn it was put
            # into is over, and it never said it had it.
            self._on_screen(self._ended_holding, agent.id)
            took = time.monotonic() - self._began.pop(agent.id, time.monotonic())
            # The line Claude Code closes a turn with, which says how long it worked.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_WORKED} Worked for {took:.0f}s"
                f"{_DOT}{escape(short(agent.id))}[/]",
                packs=False,
            )
        elif event.kind in ("subagent", "subagent-ends"):
            # An agent this one started of its own. Counted whether or not the details are
            # being shown, since `/monitor` draws the fleet under the agent that started it
            # and a fleet nobody counted would be an agent working with nothing under it.
            named, _, about = event.text.partition(" ")
            if event.kind == "subagent":
                self._monitor.started(agent.id, event.whose, about or named)
            else:
                self._monitor.finished(agent.id, event.whose, about or named)
            if self._details:
                self._on_screen(
                    self._part,
                    whose,
                    f"[$secondary]{_SAID}[/] {escape(named)}"
                    f"[dim]({escape(about)}) "
                    f"{'started' if event.kind == 'subagent' else 'done'}[/]",
                    packs=True,
                )
        elif event.kind == "notice":
            # Not the working, so `/details` does not hide it: this is humanize saying what it
            # is doing about a turn -- waiting out a rate limit, carrying on as another
            # account, cutting the turn off, taking it away from a backend that had stopped
            # saying anything. Hidden with the tool rows it reads as a hang, which is the one
            # thing the line exists to tell apart from a hang.
            self._on_screen(
                self._part,
                whose,
                f"[yellow]{_SAID}[/] [dim]{escape(event.text)}[/]",
                packs=False,
            )
        elif event.kind == "tool" and self._details:
            # The tool on the bullet, what it came back with under it -- Claude Code's shape.
            named, _, about = escape(event.text).partition(" ")
            self._on_screen(
                self._part,
                whose,
                f"[green]{_SAID}[/] {named}[dim]({about})[/]",
                packs=True,
            )
        elif event.kind == "reasoning" and self._details:
            self._on_screen(
                self._part,
                whose,
                "\n".join(
                    f"[dim italic]{line}[/]" for line in escape(event.text).splitlines()
                ),
                packs=False,
            )
        elif event.kind == "asks":
            self._on_screen(
                self._asked_by,
                agent,
                f"[yellow]{_SAID}[/] {escape(event.text)}",
            )
        elif event.kind == "failed":
            self._on_screen(
                self._part,
                whose,
                f"[red]hmz: {escape(event.text)}[/]",
                packs=False,
            )
        elif event.kind == "text":
            # The bullet on the first line, two spaces under it for the rest, which is how
            # Claude Code sets a message it has just written.
            said = escape(event.text).splitlines() or [""]
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

    def _conversation(self, agent: AgentBase, session: SessionBase | None) -> str:
        """Which of a role's conversations a turn is being taken in, where it has several.

        Args:
          agent: Whose turn it is -- one of the agents behind the role's sessions.
          session: The conversation it is in, or None where the agent said it.

        Returns:
          Which one, counting from one, and nothing at all for a role holding one -- there
          being nothing to tell it apart from.
        """
        held = [
            one for each in self._of(agent.id) for one in each.sessions
        ] or agent.sessions
        if session is None or len(held) < 2:  # noqa: PLR2004 -- one is none to tell apart
            return ""
        at = next(
            (one for one, held_one in enumerate(held) if held_one is session), None
        )
        return "" if at is None else f"{_DOT}conversation {at + 1} of {len(held)}"

    def _asked_by(self, agent: AgentBase, text: str) -> None:
        """Puts a question where whoever is at the prompt will come across it.

        On that agent's own transcript and on the one they all appear on, as everything else
        it says goes: it is that agent's question whichever of its conversations put it, and
        the server a codex or a kimi agent puts one through serves every conversation it
        holds and so names none of them.

        Args:
          agent: Who asked.
          text: The question, as markup.
        """
        # Written down so that what it will take for an answer goes under it rather than
        # wherever the person happens to be looking by then: the two are one question.
        self._asked_on = agent.id
        self._part(agent.id, text, packs=False)

    def _working_in(self, agent: AgentBase) -> SessionBase | None:
        """Which of one agent's conversations has a turn open, for a line said to it.

        Args:
          agent: The agent.

        Returns:
          The newest of its conversations that is working, or None where none of them is,
          which is a line that waits for whichever turn starts next. Only the conversations
          there are to read: the person's is this prompt, and is not one of them.
        """
        working = [
            session
            for who, session in self._conversations()
            if who is agent and session in self._working
        ]
        return working[-1] if working else None

    def _part(self, whose: str | None, text: str, *, packs: bool) -> None:
        """Puts one part of a turn in the transcript, spaced as opencode spaces its own.

        A blank line goes between the parts, except between two that pack -- one-line tool
        rows run together, and everything else is set apart. Spaced per transcript: two
        agents talking at once would otherwise run each other's lines together.

        Args:
          whose: The agent whose part it is, or None for one to show on whatever is read.
          text: The part, as markup.
          packs: Whether this part is one that runs on from the one before it.
        """
        kept = self._keeping(whose)
        if not (packs and kept.packed):
            self._into(whose, "")
        kept.packed = packs
        self._into(whose, text)

    def _background(self, work: Callable[[], int]) -> None:
        """Runs something off the event loop, showing what it says rather than dying of it.

        Args:
          work: What to do, answering with the status to report, if any.
        """

        def go() -> None:
            from hmz.coganchor.agents import Stopped

            try:
                status = work()
            except SystemExit as stopped:  # argparse rejecting the line, not a crash
                status = int(stopped.code or 0)
            except Stopped:
                return  # asked for: esc already said the flow was stopping
            except Exception as why:  # noqa: BLE001 -- a flow fails how it likes, and is shown
                telemetry.crash(why, doing="a flow")
                with contextlib.suppress(RuntimeError):  # or the interface has gone
                    self.call_from_thread(
                        self.show, traceback.format_exc().strip(), "red"
                    )
                return
            if status:
                with contextlib.suppress(RuntimeError):
                    self.call_from_thread(self.show, f"— exited {status} —", "red")

        # A thread of our own rather than a worker: a worker is joined on the way out, and a
        # turn that is still thinking would hold the interpreter open behind a closed screen.
        threading.Thread(target=go, daemon=True).start()

    def _said(self, text: str) -> None:
        """Takes a line that is not a command, which is a task, an answer, or a word put in.

        With a flow chosen and not yet running, it is the task that starts it -- the way a
        first message to opencode is the thing it is asked to do, and the reason the flow
        this opens on is one that takes anything as a task. With one running, it is the
        answer to whatever the flow stopped to ask, or goes to the agent taking its turn --
        into the turn under way, or to the flow waiting to be told the next one.

        Args:
          text: What was said.
        """
        if self._asking is not None:
            self._said_by_you(text)
            self._answer = text
            self._answered.set()  # and the turn waiting on it carries on
        elif self._run is not None:
            self._interject(text)
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
            self.show("hmz: no coding agent is installed here", "red")
            return
        self._flow(task)

    def _outworlder_asks(self, generation: int, question: Question) -> str | None:
        """Puts what a flow asks the person outside it to this prompt, and waits for them.

        Called from a thread of the run's own, which waits here. A question asked while a
        turn is open -- an agent that stopped to ask, put to the person by its flow -- or one
        with answers to choose from is shown and answered by the line typed after it, since a
        line typed into an open turn would otherwise go to the turn. Anything else is what to
        say next, answered by the next line typed, a line typed before it was asked included;
        what was asked is shown first, unless it is what an agent has just answered, which the
        transcript already shows -- a conversation saying back what was said. `/afk`, a run
        that has ended or been stopped, and an interface that has gone each answer nobody,
        which the flow hears as whoever is outside the run being away.

        Args:
          generation: Which run is asking, so that a run on its way out cannot take the
            answer meant for the run that replaced it.
          question: What it asks.

        Returns:
          What was typed, or None if nobody was there to type it.
        """
        if not self._live(generation):
            return None
        if question.options or len(self._working):
            return self._ask(generation, question)
        said = question.text.strip()
        if said and said != self._last_answer.strip():
            with contextlib.suppress(RuntimeError):  # or the interface has gone
                self.call_from_thread(self._show_question, question)
        return self._listen(generation)

    def _live(self, generation: int) -> bool:
        """Whether the run asking is still the one going, and somebody is here to answer."""
        return (
            not self._afk and generation == self._generation and self._run is not None
        )

    def _listen(self, generation: int) -> str | None:
        """Waits at the prompt for a flow that has nothing to do until it is told something.

        Nothing on the event loop is touched, so the interface goes on being an interface
        while a flow waits in it.

        Args:
          generation: Which run is waiting.

        Returns:
          What was said next, or None once this flow is over -- stopped by hand, or the
          interface going away, either of which has to release this rather than leave a
          thread waiting on a prompt that is not there.
        """
        self._awaiting = True
        try:
            while True:
                # Cleared before the queue is read, so that a line arriving between the two
                # sets it again and is not waited through.
                self._spoke.clear()
                if not self._live(generation):
                    return None
                if held := self._take():
                    # Whatever turn this answer starts is that line's turn, and takes
                    # nothing else out of the queue on the way in.
                    with self._saying:
                        self._handed = True
                    return "\n\n".join(held)
                self._spoke.wait(_REFRESH)
        finally:
            self._awaiting = False

    def _ask(self, generation: int, question: Question) -> str | None:
        """Puts a question the flow asks to whoever is at this prompt, and waits for them.

        Args:
          generation: Which run is asking.
          question: What it wants to know.

        Returns:
          What was typed, or None if nobody was there to type it.
        """
        # Cleared before the question goes up, so that an answer arriving between the two is
        # not cleared away with it.
        self._answered.clear()
        self._answer, self._asking = "", question
        with contextlib.suppress(RuntimeError):  # or the interface has gone
            self.call_from_thread(self._show_question, question)
        while not self._answered.wait(_REFRESH):
            # `/afk` while the question is up says so too, or saying you are away would
            # leave the flow waiting on the answer you had just declined to give.
            if not self._live(generation):
                break
        self._asking = None
        return self._answer or None

    def _show_question(self, question: Question) -> None:
        """Shows a question the flow asks, and what it will take for an answer.

        On whichever transcript is being read, the question being the flow's rather than any
        one agent's -- unless an agent has just stopped to ask the same thing, which is
        already on its own transcript and is not said twice.

        Args:
          question: What the flow wants to know.
        """
        asked = question.text.strip()
        repeated = bool(self._last_asked) and asked == self._last_asked.strip()
        self._asked_on = None if not repeated else self._asked_on
        if not repeated:
            self._part(None, f"[yellow]{_SAID}[/] {escape(asked)}", packs=False)
        for option in question.options:
            self._into(self._asked_on, f"      [dim]· {escape(option)}[/dim]")
        self._into(
            self._asked_on, "   [dim]type an answer, or /afk to stop being asked[/dim]"
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

    def _interject(self, text: str) -> None:
        """Puts something in the queue for the flow, and sends it if nothing is in the way.

        Everything typed joins one queue, whether or not a turn is running: a line is a
        thing said, and things said go one at a time and in order. It is pinned above the
        prompt rather than written into the transcript until it goes -- it has not been said
        to anybody yet, and a transcript is what happened, which is what Claude Code does
        with a queued line too.

        Args:
          text: What to say.
        """
        with self._saying:
            self._queued.append(text)
        self._spoke.set()  # a flow between turns is waiting to be told something
        self._draw()  # rather than at the next tick: it was just typed
        self._hand_over()

    def _hand_over(self) -> None:
        """Puts the oldest waiting line into the conversation on the screen, one at a time.

        Into the agent being read rather than into whichever happens to be working: a flow
        drives several, and a line said to the one that is not on the screen is a line said
        to the wrong agent. Of that agent's conversations it is the one with a turn open,
        since a line written to one between turns is answered on its own outside the flow.
        Where every agent is being read at once there is no one of them to have meant, so it
        is whichever has a turn open -- which is the one the screen is showing anyway.

        One at a time and never two: a backend given a second word while it is still
        swallowing the first runs the two together and answers once, so five lines typed in
        a row would come back as one reply. The next goes only once the turn has said it has
        this one, which is also the only point at which the two could not be run together.

        Nothing is sent between turns. A line has nowhere to go but the queue then -- writing
        it to a conversation that is not working would have it answered on its own, outside
        the flow -- so it waits for whichever turn starts next, and a running flow never
        drops one.
        """
        session = self._says_to()
        if session is None or session not in self._working:
            return
        # The agent alongside its conversation: a word put in is pinned against whoever has
        # it, and it is that agent's own stream that will say it has been taken in.
        agent = next(
            (who for who, one in self._conversations() if one is session), None
        )
        if agent is None:
            return
        with self._saying:
            if any(who == agent.id for who, _ in self._given):
                return  # it is holding one already, and holds one at a time
            if not self._queued:
                return
            text = self._queued.pop(0)
            self._given.append((agent.id, text))
        self._draw()

        def put_in() -> int:
            # Off the event loop: this writes to the agent, and a large paste into a pipe the
            # interface itself is draining would otherwise deadlock the two.
            try:
                session.interject(text)
            except (NotImplementedError, RuntimeError, OSError) as error:
                self._on_screen(self._unreached, agent.id, text, str(error))
            except subprocess.CalledProcessError as refused:
                # A backend that refused it: codex drops a steer that named a turn already
                # over, and kimi answers one inside a 200. Either way it never went.
                self._on_screen(
                    self._unreached,
                    agent.id,
                    text,
                    refused.stderr or "the agent refused it",
                )
            return 0

        self._background(put_in)

    def _unreached(self, who: str, text: str, because: str) -> None:
        """Puts a word back at the head of the queue, the agent never having taken it.

        At the head rather than the end, and without trying the next one behind it: it was
        said before everything still waiting, and sending that one now would be sending it
        to the agent that just refused this.

        Args:
          who: The agent it was put to.
          text: The word.
          because: What the backend said about it.
        """
        # How long the refusal was and nothing of what it said: `because` is a backend's own
        # stderr, which is the one thing a report may not carry.
        telemetry.snag("line-refused", said=len(because))
        with self._saying:
            if (who, text) in self._given:
                self._given.remove((who, text))
                self._queued.insert(0, text)
        self.show(f"hmz: {because}", "red")
        self._spoke.set()  # and whichever turn starts next takes it instead
        self._draw()

    def _took(self, who: str, text: str) -> None:
        """Takes a word off the pin, the agent having said it now has it.

        Args:
          who: The agent that said so.
          text: The word it said it has.
        """
        with self._saying:
            if (who, text) not in self._given:
                return  # somebody else's word, or one already written down
            self._given.remove((who, text))
        self._said_by_you(text, who)
        self._draw()
        self._hand_over()  # and the next one behind it goes now that this is through

    def _ended_holding(self, who: str) -> None:
        """Says what became of the words an agent was holding when its turn ended.

        The turn is over and it never said it had them, so they are neither waiting nor
        taken: they were put to it, and what it did with them is between it and the backend.
        Every backend but codex runs such a word as a turn of its own afterwards, and codex
        drops it -- which is more than this can tell from here, so it says what it knows.

        Args:
          who: The agent whose turn ended.
        """
        with self._saying:
            held = [text for agent, text in self._given if agent == who]
            self._given = [pair for pair in self._given if pair[0] != who]
        if not held:
            return
        for text in held:
            self._said_by_you(text)
        self.show(
            f"[dim]   put to {escape(short(who))}, which ended its turn without saying "
            f"it had {'them' if len(held) > 1 else 'it'}[/dim]"
        )
        self._draw()


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
    ),
    Command(
        "btw",
        "Ask a side question",
        lambda app, argv: app.action_btw(" ".join(argv).strip()),
        takes="<question>",
    ),
    Command(
        "flowverses",
        "Manage the places flows come from",
        lambda app, _: app.action_flowverses(),
    ),
    Command(
        "providers",
        "Manage the accounts agents run as",
        lambda app, _: app.action_providers(),
    ),
    Command(
        "fallback",
        "Where a turn goes when the place taking it cannot take it at all",
        lambda app, _: app.action_fallback(),
    ),
    Command(
        "epics",
        "The runs of this directory, and what to do with one",
        lambda app, _: app.action_epics(),
    ),
    Command(
        "resume",
        "Carry the last run here on from where it stopped",
        lambda app, argv: app.action_resume(argv),
    ),
    Command(
        "settings",
        "What humanize remembers, here and everywhere",
        lambda app, _: app.action_settings(),
    ),
    Command(
        "monitor",
        "Watch the run: the flow drawn, and the board",
        lambda app, _: app.action_monitor(),
    ),
    Command("clear", "Clear the screen", lambda app, _: app.action_clear()),
    Command(
        "details",
        "Toggle tool calls and thinking",
        lambda app, argv: app.action_details(argv),
        takes="[on|off]",
    ),
    Command(
        "afk",
        "Toggle whether an agent may ask you",
        lambda app, argv: app.action_afk(argv),
        takes="[on|off]",
    ),
    Command(
        "stop",
        "Stop the flow; typed out, so not asked twice",
        lambda app, _: app.action_stop(),
    ),
    Command(
        "exit",
        "Leave; a flow that is running can be left running",
        lambda app, _: app.action_exit(),
    ),
)

#: The same rows by name, for the two readers that have a name in hand rather than a line to
#: finish: the row drawn beside an offer, and the command a sent line turned out to be.
_BY_NAME = {one.name: one for one in _COMMANDS}
