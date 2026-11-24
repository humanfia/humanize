"""A session a harness had of its own, read and only read, with one way on.

Humanize did not run it (Section 8.11 of [CORE]): what was said in it is read by
`chat.harness.get` and drawn as a transcript, and the one thing to press is the page's
`Continue in chat`, which copies it into a chat of the folder by `chat.harness.adopt` and goes
to that chat -- offered for a session its row says is `continuable`, and otherwise said not to
be. Nothing is said to the session itself, and nothing of it is changed.

Opened from the list of the New chat page, and by anything else through :func:`opens`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.markup import escape
from textual import work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from hmz.tui import humanfia
from hmz.tui.selecting import Transcript
from hmz.tui.shell import Hints, View
from hmz.words import t

from .chips import Desk, Heading, desk, harness_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual import events
    from textual.app import App, ComposeResult

__all__ = ["VIEWS", "Session", "aim", "opens"]

#: The mark a line the person said is drawn behind, as the log draws one.
_YOURS = "❯"

#: The session the view opens on when it is opened by name: `(workspace, harness, session)`.
_aimed: tuple[str, str, str] | None = None


class Session(Screen[str | None]):
    """One harness session: what was said in it, and `Continue in chat`.

    Answered with the chat it was continued in, by its id, or None where it was only read.
    """

    DEFAULT_CSS = """
    Session { background: $background; }
    Session #sub { height: 1; padding: 0 1; color: $text-muted; }
    Session Transcript { height: 1fr; margin: 1 0 0 0; background: $background; }
    Session .rule { height: 1; color: $hmz-line-strong; }
    Session #note { height: auto; padding: 0 1; color: $text-muted; }
    Session Hints { dock: bottom; }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "back", "Back", show=False),
        Binding("enter", "adopt", "Continue in chat", show=False),
        Binding("up", "scroll(-1)", "scroll", show=False),
        Binding("down", "scroll(1)", "scroll", show=False),
        Binding("pageup", "page(-1)", "scroll", show=False),
        Binding("pagedown", "page(1)", "scroll", show=False),
    ]

    #: The keys it takes, as the hint line says them.
    KEYS: ClassVar = (("↑↓", "scroll"), ("enter", "Continue in chat"))

    def __init__(
        self, at: Desk, workspace: str = "", named: str = "", session: str = ""
    ) -> None:
        """Opens on one session, which is read as the page mounts.

        Args:
          at: The interface it is opened in.
          workspace: The folder the session worked in.
          named: The harness that had it.
          session: The id its harness gave it; "" for the folder's newest, of any harness.
        """
        super().__init__()
        self._desk = at
        self._workspace = workspace or at.workspace
        self._named, self._session = named, session
        #: The session as `chat.harness.get` answered it, or None before it has.
        self._row: dict[str, Any] | None = None
        self._copying = False

    def compose(self) -> ComposeResult:
        """The heading; what the session is; what was said in it; the way on; the keys."""
        yield Heading(t("Harness session"))
        yield Static(id="sub")
        yield Transcript(id="said")
        yield Static(classes="rule")
        yield Static(f"[$text-muted]{t('Reading its logs…')}[/]", id="note")
        yield Hints()

    def on_mount(self) -> None:
        """Says the keys, and reads the session."""
        self.query_one(Hints).says([*self.KEYS, ("esc", "Back")])
        self._reads()

    def on_resize(self, event: events.Resize) -> None:
        """Rules the page across however wide it is now."""
        self.query_one(".rule", Static).update(humanfia.RULE * event.size.width)

    def _notes(self, markup: str) -> None:
        self.query_one("#note", Static).update(markup)

    @work(group="harness-reads", exclusive=True)
    async def _reads(self) -> None:
        """Reads the session whole, and draws what was said in it."""
        asks = self._desk.asks
        try:
            if not self._session:
                newest = await asyncio.to_thread(
                    asks, "chat.harness.list", workspace=self._workspace, limit=1
                )
                found = cast("list[dict[str, Any]]", newest.get("sessions") or [])
                if not found:
                    self._notes(t("No harness session in this folder."))
                    return
                self._named, self._session = (
                    str(found[0].get("harness") or ""),
                    str(found[0].get("id") or ""),
                )
            one = await asyncio.to_thread(
                asks,
                "chat.harness.get",
                workspace=self._workspace,
                harness=self._named,
                session=self._session,
                trace=True,
            )
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._notes(f"[$error]{escape(str(why))}[/]")
            return
        self._row = one
        named = harness_name(str(one.get("harness") or self._named))
        title = " ".join(str(one.get("title") or "").split()) or str(one.get("id"))
        self.query_one("#sub", Static).update(
            f"[b $foreground]{escape(title)}[/]  {humanfia.POINT} {escape(named)}"
            f"  {humanfia.POINT} {escape(str(one.get('workspace') or self._workspace))}"
        )
        said = self.query_one(Transcript)
        read = [
            each
            for each in cast("list[dict[str, Any]]", one.get("trace") or [])
            if each.get("actions")
        ]
        for each in read:
            if len(read) > 1:
                said.write(f"[dim]{escape(str(each.get('key') or ''))}[/]")
            for action in cast("list[dict[str, Any]]", each["actions"]):
                said.write(_drawn(action))
        if not read:
            said.write(f"[dim]{t('Its logs held nothing said.')}[/]")
        if one.get("continuable"):
            note = t(
                "Read-only. Continuing copies it into a chat here; "
                "the {harness} session stays as it is.",
                harness=named,
            )
            self._notes(
                f"{escape(note)}  "
                f"[b $accent]{humanfia.SQUARE} {t('Continue in chat')}[/]"
            )
        else:
            self._notes(
                escape(
                    t(
                        "Read-only. A session of {harness} cannot be continued in a chat.",
                        harness=named,
                    )
                )
            )

    def action_scroll(self, by: int) -> None:
        """Scrolls what was said a line up or down."""
        said = self.query_one(Transcript)
        said.scroll_relative(y=by, animate=False)

    def action_page(self, by: int) -> None:
        """Scrolls what was said a page up or down."""
        said = self.query_one(Transcript)
        said.scroll_relative(y=by * max(1, said.size.height - 1), animate=False)

    def action_adopt(self) -> None:
        """Continues the session in a chat, where its harness carries a copy on."""
        if self._row is not None and self._row.get("continuable") and not self._copying:
            self._adopts()

    @work(group="harness-adopts", exclusive=True)
    async def _adopts(self) -> None:
        """Copies the session into a chat of the folder, and goes to that chat."""
        self._copying = True
        self._notes(f"[$text-muted]{t('Copying…')}[/]")
        try:
            made = await asyncio.to_thread(
                self._desk.asks,
                "chat.harness.adopt",
                workspace=self._workspace,
                harness=self._named,
                session=self._session,
            )
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._copying = False
            self._notes(f"[$error]{escape(str(why))}[/]")
            return
        chat = str(made.get("chat") or "")
        if chat:
            # A chat just made is on no host, and is carried on by the next line.
            self._desk.follows(chat, "")
        self.dismiss(chat or None)

    def action_back(self) -> None:
        """Closes the page: one step back, to what was under it."""
        if (
            not self._copying
        ):  # a session being copied is waited for, and then it closes
            self.dismiss(None)


def _drawn(action: dict[str, Any]) -> str:
    """One thing a session did, as markup: a line said to it, what it said, or what it ran."""
    args = cast("dict[str, Any]", action.get("args") or {})
    name = str(action.get("name") or "")
    if action.get("category") == "turn":
        return f"[cyan]{_YOURS}[/] [b]{escape(str(args.get('prompt') or name))}[/]"
    if action.get("category") == "message":
        return escape(str(args.get("text") or name))
    return f"[dim]  {humanfia.POINT} {escape(name)}[/]"


def aim(workspace: str, named: str, session: str) -> None:
    """Says which session the view opens on the next time it is opened by name.

    Args:
      workspace: The folder the session worked in.
      named: The harness that had it.
      session: The id its harness gave it.
    """
    global _aimed  # noqa: PLW0603 -- one session aimed at, taken by the page that opens
    _aimed = (workspace, named, session)


async def opens(
    app: App[None],
    workspace: str,
    named: str,
    session: str,
    *,
    then: Callable[[str | None], None] | None = None,
) -> None:
    """Opens the page on one harness session.

    Args:
      app: The interface to open it on.
      workspace: The folder the session worked in.
      named: The harness that had it.
      session: The id its harness gave it.
      then: What is told the chat it was continued in, or None where it was only read.
    """
    await app.push_screen(Session(desk(app), workspace, named, session), then)


def _made(app: App[None]) -> Session:
    global _aimed
    aimed, _aimed = _aimed, None
    return Session(desk(app), *(aimed or ()))


VIEWS = (View("harness", "page", "Harness session", _made, keys=Session.KEYS),)
