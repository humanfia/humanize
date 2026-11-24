"""Ai-chan: her conversations, listed beside the log, and opened in it.

What the web page's drawer lists, in the context zone: a new conversation first, then every
one the daemon holds -- the pinned first, then the latest said in -- each dotted where it was
said in since it was read here. Enter on one follows it in the log, as picking it from `/ai`
does; the rest of what the drawer's menu does is on a key apiece, each of them on the hint
line: renaming, pinning, marking read or unread, and deleting, which asks first.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.markup import escape
from textual import work
from textual.binding import Binding
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from hmz.tui import humanfia
from hmz.tui.pick import (
    AI_MARKS,
    AI_NEW,
    AiForgets,
    AiMarks,
    AiRenames,
    ai_chan,
    ai_scope,
)
from hmz.tui.shell import View
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from textual.app import App

__all__ = ["VIEWS", "Conversations"]

#: What reaching the daemon may fail with, each of which is said rather than raised.
_REFUSED = (LookupError, OSError, RuntimeError, ValueError)


class Conversations(OptionList):
    """Her conversations, a row apiece under `New conversation`, in the context zone."""

    DEFAULT_CSS = """
    Conversations {
        height: 1fr; padding: 0; border: none; background: $surface;
        scrollbar-size: 1 1; }
    Conversations:focus { border: none; background-tint: $surface 0%; }
    Conversations > .option-list--option-highlighted {
        background: $block-cursor-blurred-background;
        color: $block-cursor-blurred-foreground; text-style: none; }
    Conversations:focus > .option-list--option-highlighted {
        background: $block-cursor-background; color: $block-cursor-foreground;
        text-style: bold; }
    """

    BINDINGS: ClassVar = [
        Binding("n", "fresh", show=False),
        Binding("r", "rename", show=False),
        Binding("p", "pin", show=False),
        Binding("u", "read", show=False),
        Binding("delete", "forget", show=False),
    ]

    def __init__(
        self,
        *,
        follows: Callable[[dict[str, Any]], None],
        news: Callable[[], None],
        asks: Callable[..., Any] = ai_chan,
        marks: AiMarks | None = None,
    ) -> None:
        """Lists nothing until the daemon has answered.

        Args:
          follows: Follows one conversation in the log, as picking it from `/ai` does.
          news: Starts a new conversation, as **New** of `/ai` does.
          asks: One `aichan.*` call of the daemon, as :func:`hmz.tui.pick.ai_chan` makes it.
          marks: Which are pinned and which unread; this interface's own for None.
        """
        super().__init__()
        self._follows, self._news, self._asks = follows, news, asks
        self._marks = AI_MARKS if marks is None else marks
        self._listed: list[dict[str, Any]] = []
        #: What is said in place of the conversations: that they are being read, or why not.
        self._said = t("Reading her conversations…")

    def on_mount(self) -> None:
        """Draws the one row there always is, and asks the daemon for the rest."""
        self._draws()
        self.reads()

    @work(group="aichan-view", exclusive=True)
    async def reads(self) -> None:
        """Asks the daemon for her conversations, and lists them."""
        try:
            listed = await asyncio.to_thread(self._asks, "list")
        except _REFUSED as why:
            self._listed = []
            self._said = t(
                "Ai-chan's conversations could not be loaded: {why}", why=str(why)
            )
        else:
            self._listed = self._marks.ordered(listed.get("conversations") or ())
            self._said = "" if self._listed else t("No conversations yet")
        self._draws()

    def _row(self, one: Mapping[str, Any]) -> str:
        """One conversation: its marks and title, and under them what she may reach."""
        number = int(one["id"])
        pinned = f"{humanfia.SQUARE} " if number in self._marks.pinned else ""
        unread = " ●" if self._marks.is_unread(one) else ""
        state = str(one.get("state") or "")
        about = " · ".join(
            part
            for part in (
                ai_scope(one, short=True),
                str(one.get("preset") or ""),
                t("typing…") if state == "running" else "",
            )
            if part
        )
        title = f"Ai-chan#{number} · {one.get('title') or ''}"
        return f"{pinned}[b]{escape(title)}[/]{unread}\n  {escape(about)}"

    def _draws(self) -> None:
        """Puts the rows up, the cursor on the row it was on."""
        was = self.highlighted or 0
        rows = [
            Option(f"[b]+ {t('New conversation')}[/]", id=AI_NEW),
            *(Option(self._row(one), id=str(one["id"])) for one in self._listed),
        ]
        if self._said:
            rows.append(Option(escape(self._said), disabled=True))
        self.set_options(rows)
        self.highlighted = min(was, len(self._listed))

    def under(self) -> dict[str, Any] | None:
        """The conversation under the cursor, or None on `New conversation`."""
        at = (self.highlighted or 0) - 1
        return self._listed[at] if 0 <= at < len(self._listed) else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Follows the conversation picked in the log, or starts a new one."""
        event.stop()
        one = self.under()
        if one is None:
            self._news()
            return
        self._marks.reads(one)
        self._draws()
        self._follows(one)

    def action_fresh(self) -> None:
        """Starts a new conversation."""
        self._news()

    def action_pin(self) -> None:
        """Pins the conversation under the cursor to the top, or lets it go."""
        if (one := self.under()) is not None:
            number = int(one["id"])
            pinned = self._marks.pinned
            (pinned.discard if number in pinned else pinned.add)(number)
            self._listed = self._marks.ordered(self._listed)
            self._draws()

    def action_read(self) -> None:
        """Marks the conversation under the cursor read, or unread until it is opened."""
        if (one := self.under()) is not None:
            if self._marks.is_unread(one):
                self._marks.reads(one)
            else:
                self._marks.unread.add(int(one["id"]))
            self._draws()

    def _showing(self) -> App[None]:
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    @work
    async def action_rename(self) -> None:
        """Asks what the conversation under the cursor is to be called, and renames it."""
        if (one := self.under()) is None:
            return
        title = await self._showing().push_screen_wait(
            AiRenames(str(one.get("title") or ""))
        )
        if not title:
            return
        try:
            await asyncio.to_thread(
                self._asks, "rename", id=int(one["id"]), title=title
            )
        except _REFUSED as why:
            self._said = str(why)
            self._draws()
            return
        self.reads()

    @work
    async def action_forget(self) -> None:
        """Asks whether to delete the conversation under the cursor, and deletes it."""
        if (one := self.under()) is None:
            return
        number = int(one["id"])
        if await self._showing().push_screen_wait(AiForgets(number)) != "yes":
            return
        try:
            await asyncio.to_thread(self._asks, "forget", id=number)
        except _REFUSED as why:
            self._said = str(why)
            self._draws()
            return
        self._marks.pinned.discard(number)
        self._marks.unread.discard(number)
        self.reads()


def _made(app: App[None]) -> Conversations:
    """The view, opening a conversation the way `/ai` does in this interface."""

    def follows(one: dict[str, Any]) -> None:
        # The log's own way onto a host, which `/ai` takes for a conversation picked there.
        host = cast("Any", app)
        host._moves(str(one["slot"]), None, ai=one)  # noqa: SLF001
        host._draw()  # noqa: SLF001
        app.set_focus(None)
        for prompt in app.query("#editor"):
            prompt.focus()

    def news() -> None:
        app.run_worker(app.run_action("ai"), exclusive=False)

    return Conversations(follows=follows, news=news)


VIEWS = (
    View(
        "aichan",
        "context",
        "Ai-chan",
        _made,
        key="f3",
        hint="Ai-chan",
        keys=(
            ("enter", "Open"),
            ("n", "New"),
            ("r", "Rename"),
            ("p", "Pin"),
            ("u", "Mark as unread"),
            ("delete", "Delete"),
        ),
    ),
)
