"""The runs of a workspace on another machine, followed from here: `/epics @<name>`'s own.

What another daemon's web page shows of an epic going there, as the terminal reads one: what
was asked, what each agent said and did, what the flow asks a person -- read off that machine's
interface, reached over ssh, as its page reads it -- and a line typed under it said to the run
or, where it is asking, its answer. Reached from that daemon's list of epics, on one going
there or one started from it; esc comes back to the list and leaves the run going there.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar

from rich.markup import escape
from textual import on, work
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, RichLog

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from hmz.daemon.link import Link

__all__ = ["Afar"]

#: What an agent's line and a person's are set on, as the terminal's own transcript sets them.
_SAID, _YOURS = "⏺", "❯"

#: What separates the parts of a line.
_DOT = " · "


class Afar(ModalScreen[None]):
    """One workspace's runs on another machine: its transcript, how it stands, and a line to say.

    Read through a link to that machine's interface (:func:`hmz.daemon.link.remote`), which
    this lets go of as it is left: the run goes on there for whoever else reads it.
    """

    DEFAULT_CSS = """
    Afar { background: $background; }
    Afar #sheet { width: 100%; height: 100%; padding: 1 2 0 2; }
    Afar #asked { width: 100%; text-style: bold; color: $primary; }
    Afar #about { width: 100%; padding: 0 0 1 0; color: $text-muted; }
    Afar #said { height: 1fr; background: $background; scrollbar-size: 1 1; }
    Afar #standing { width: 100%; height: 1; color: $text-muted; }
    Afar #line { border: round $primary; background: $background; }
    Afar #keys { width: 100%; height: 1; color: $text-muted; }
    """

    BINDINGS: ClassVar = [Binding("escape", "back", "back", show=False, priority=True)]

    def __init__(self, daemon: str, workspace: str, link: Link) -> None:
        """Follows one workspace's runs on another machine.

        Args:
          daemon: The daemon, by name.
          workspace: The workspace there.
          link: This end of its runs, which this lets go of as it is left.
        """
        super().__init__()
        self._daemon = daemon
        self._workspace = workspace
        self._link = link
        #: What the run asks and is not answered yet, oldest first: each by its id.
        self._pending: list[dict[str, Any]] = []
        #: How the run stands, as it last said: its state, and a chat's turn.
        self._run: dict[str, Any] = {}
        self._gone = ""

    def compose(self) -> ComposeResult:
        """Where this is, the transcript, how it stands, the line, and the keys."""
        with Vertical(id="sheet"):
            yield Label(id="asked")
            yield Label(id="about")
            yield RichLog(id="said", wrap=True, markup=True)
            yield Label(id="standing")
            yield Input(placeholder="say something to the run", id="line")
            yield Label("enter send   esc back", id="keys")

    def on_mount(self) -> None:
        """Says where this is, and follows the runs."""
        self.query_one("#asked", Label).update(
            f"{escape(self._workspace)}{_DOT}{escape(self._daemon)}"
        )
        self.query_one("#about", Label).update(
            f"The runs of this directory on {escape(self._daemon)}, as its own web page "
            "reads them. A line typed is said to the run, or answers what it asks."
        )
        self._stands()
        self._link.heard(self._told)
        self.query_one(Input).focus()

    def _told(self, message: dict[str, Any]) -> None:
        """Takes one message, on the link's thread, to the screen's."""
        self.app.call_from_thread(  # pyright: ignore[reportUnknownMemberType]
            self._takes, message
        )

    def _takes(self, message: dict[str, Any]) -> None:
        """Draws one message about the runs there."""
        kind = message.get("type")
        text = str(message.get("text") or "")
        if kind == "started":
            self._says(f"[dim]— {escape(str(message.get('flow') or ''))} started —[/]")
            if task := str(message.get("task") or ""):
                self._says(f"[b]{_YOURS}[/] {escape(task)}")
        elif kind == "said":
            self._says(f"[b]{_YOURS}[/] {escape(text)}")
        elif kind == "event":
            self._heard(message)
        elif kind == "asked":
            # Not what a flow listening says back, which is the answer drawn already.
            if text.strip() and message.get("mode") != "listen":
                self._says(f"[yellow]?[/] {escape(text)}")
        elif kind == "answered":
            asked = message.get("question")
            self._pending = [
                one for one in self._pending if one.get("question") != asked
            ]
            if text.strip():
                self._says(f"[b]{_YOURS}[/] {escape(text)}")
        elif kind == "ended":
            self._says(
                f"[dim]— the flow is {escape(str(message.get('how') or 'over'))} —[/]"
            )
        elif kind == "refused":
            self._says(f"[red]hmz: {escape(str(message.get('because') or ''))}[/]")
        elif kind == "run":
            self._run = message
        elif kind == "pending":
            self._pending = list(message.get("pending") or [])
        elif kind == "gone":
            self._gone = str(message.get("why") or "")
        self._stands()

    def _heard(self, record: dict[str, Any]) -> None:
        """Draws what one turn said: words, questions, failures, and when it began and ended."""
        agent, kind = str(record.get("agent") or ""), record.get("kind")
        text = escape(str(record.get("text") or ""))
        if kind == "text":
            self._says(f"[green]{_SAID}[/] {text}")
        elif kind == "asks":
            self._says(f"[yellow]{_SAID}[/] {text}")
        elif kind == "failed":
            self._says(f"[red]hmz: {text}[/]")
        elif kind == "notice":
            self._says(f"[yellow]{_SAID}[/] [dim]{text}[/]")
        elif kind == "begins":
            self._says(f"[dim]{_SAID} {escape(agent)} is working[/]")

    def _says(self, line: str) -> None:
        """Writes one line to the transcript."""
        self.query_one("#said", RichLog).write(line)

    def _stands(self) -> None:
        """Says how the runs there stand: going, waiting for somebody, done, or let go of."""
        state = str(self._run.get("state") or "")
        turn = str(self._run.get("turn") or "")
        said = (
            f"[red]{escape(self._gone)}[/]"
            if self._gone
            else "waiting for you"
            if any(one.get("mode") == "listen" for one in self._pending)
            else turn or state or "nothing running"
        )
        self.query_one("#standing", Label).update(said)

    @on(Input.Submitted, "#line")
    def _sends(self, event: Input.Submitted) -> None:
        """Says the line typed, or answers what the run asks with it."""
        text = event.value.strip()
        event.input.value = ""
        if text:
            self._carries(text)

    @work(group="afar")
    async def _carries(self, text: str) -> None:
        """Takes one line there, off the screen's thread, and says what refused it."""
        from hmz.daemon import Refused

        asking = next(
            (
                one
                for one in self._pending
                if one.get("owner") in (None, self._link.client)
            ),
            None,
        )
        try:
            if asking is not None:
                await asyncio.to_thread(
                    self._link.answer, str(asking["question"]), text
                )
            else:
                await asyncio.to_thread(self._link.say, text)
        except (Refused, OSError, TimeoutError) as why:
            self._says(f"[red]hmz: {escape(str(why))}[/]")

    def action_back(self) -> None:
        """Comes back, letting go of the runs there, which go on."""
        self._link.close()
        self.dismiss(None)
