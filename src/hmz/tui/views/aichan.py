"""Ai-chan: her conversations, listed beside the log, and opened in it.

What the web page's drawer lists, in the context zone: a new conversation first, then every
one the daemon holds -- the pinned first, then the latest said in -- each dotted where it was
said in since it was read here. Enter on one follows it in the log, as picking it from `/ai`
does; the rest of what the drawer's menu does is on a key apiece, each of them on the hint
line: renaming, pinning, marking read or unread, and deleting, which asks first.

Which are pinned and which unread is this person's way of looking at them, kept where the
navigator keeps its own (`navigator.json` of the state directory): read as the interface
opens, and written as it changes here and as the interface closes.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast
from weakref import WeakKeyDictionary

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

from .navigator import Kept

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual.app import App

    from hmz.tui.app import Humanize

__all__ = ["VIEWS", "Conversations", "keeps", "remembers"]

#: What the pinned, the unread, and up to when each was read are kept under.
_PINNED, _UNREAD, _SEEN = "ai-pinned", "ai-unread", "ai-seen"

#: What reaching the daemon may fail with, each of which is said rather than raised.
_REFUSED = (LookupError, OSError, RuntimeError, ValueError)

#: How often the list is asked for again while it is open, in seconds: a conversation made or
#: said in from the prompt beside it shows without the pane being opened again.
_EVERY = 3.0


type _Marked = tuple[frozenset[int], frozenset[int], dict[int, str]]

#: What each set of marks was when it was last read from the file or written to it.
_AS_KEPT: WeakKeyDictionary[AiMarks, _Marked] = WeakKeyDictionary()


def _ids(names: frozenset[str]) -> set[int]:
    return {int(name) for name in names if name.isdecimal()}


def _seen(names: frozenset[str]) -> dict[int, str]:
    return {
        int(number): updated
        for number, _, updated in (one.partition(" ") for one in names)
        if number.isdecimal()
    }


def _marked(marks: AiMarks) -> _Marked:
    return frozenset(marks.pinned), frozenset(marks.unread), dict(marks.seen)


def remembers(marks: AiMarks | None = None, kept: Kept | None = None) -> None:
    """Takes what was kept of her conversations as what is pinned, unread and read.

    Args:
      marks: What is told; this interface's own for None.
      kept: Where it was kept; the navigator's own file for None.
    """
    marks = AI_MARKS if marks is None else marks
    kept = Kept() if kept is None else kept
    marks.pinned, marks.unread = _ids(kept.all(_PINNED)), _ids(kept.all(_UNREAD))
    marks.seen = _seen(kept.all(_SEEN))
    _AS_KEPT[marks] = _marked(marks)


def keeps(marks: AiMarks | None = None, kept: Kept | None = None) -> None:
    """Keeps what is pinned, unread and read of her conversations, where it has changed.

    Only what changed here since it was last read or kept, put over what the file holds
    now: another interface of this person keeps its own there, and what it pinned is not
    let go of for this one never having heard of it.

    Args:
      marks: What is kept; this interface's own for None.
      kept: Where; the navigator's own file for None.
    """
    marks = AI_MARKS if marks is None else marks
    now = _marked(marks)
    was = _AS_KEPT.get(marks, (frozenset[int](), frozenset[int](), dict[int, str]()))
    if now == was:
        return
    kept = Kept() if kept is None else kept
    kept.reads()
    pinned = (_ids(kept.all(_PINNED)) | (now[0] - was[0])) - (was[0] - now[0])
    unread = (_ids(kept.all(_UNREAD)) | (now[1] - was[1])) - (was[1] - now[1])
    seen = _seen(kept.all(_SEEN))
    seen.update({one: at for one, at in now[2].items() if was[2].get(one) != at})
    kept.keeps(
        {
            _PINNED: [str(one) for one in sorted(pinned)],
            _UNREAD: [str(one) for one in sorted(unread)],
            _SEEN: [f"{one} {seen[one]}" for one in sorted(seen)],
        }
    )
    _AS_KEPT[marks] = now


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
        kept: Kept | None = None,
        followed: Callable[[], int | None] = lambda: None,
        forgot: Callable[[int], None] = lambda _: None,
    ) -> None:
        """Lists nothing until the daemon has answered.

        Args:
          follows: Follows one conversation in the log, as picking it from `/ai` does.
          news: Starts a new conversation, as **New** of `/ai` does.
          asks: One `aichan.*` call of the daemon, as :func:`hmz.tui.pick.ai_chan` makes it.
          marks: Which are pinned and which unread; this interface's own for None.
          kept: Where they are kept from one opening of the interface to the next; the
            navigator's own file for None.
          followed: The id of the conversation the log follows now, or None for none.
          forgot: Told the id of a conversation deleted from here, once it is.
        """
        super().__init__()
        self._follows, self._news, self._asks = follows, news, asks
        self._followed, self._forgot = followed, forgot
        self._marks = AI_MARKS if marks is None else marks
        self._kept = kept
        self._listed: list[dict[str, Any]] = []
        #: What is said in place of the conversations: that they are being read, or why not.
        self._said = t("Reading her conversations…")

    def on_mount(self) -> None:
        """Draws the one row there always is, and asks the daemon for the rest."""
        self._draws()
        self.reads()
        self.set_interval(_EVERY, self.reads)

    @work(group="aichan-view", exclusive=True)
    async def reads(self) -> None:
        """Asks the daemon for her conversations, and lists them."""
        self._marks.following = self._followed()
        try:
            listed = await asyncio.to_thread(self._asks, "list")
        except _REFUSED as why:
            self._listed = []
            self._said = t(
                "Ai-chan's conversations could not be loaded: {why}", why=str(why)
            )
        else:
            found = listed.get("conversations") or ()
            self._said = "" if found else t("No conversations yet")
            self._lists(found)
            return
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

    def _lists(self, listed: Sequence[Mapping[str, Any]]) -> None:
        """Lists these in their order, the cursor going with the conversation it was on."""
        under = self.under()
        self._listed = self._marks.ordered(listed)
        self._draws(None if under is None else int(under["id"]))

    def _draws(self, on: int | None = None) -> None:
        """Puts the rows up, the cursor on one conversation, or on the one it is on."""
        under = self.under()
        was = on if on is not None else None if under is None else int(under["id"])
        rows = [
            Option(f"[b]+ {t('New conversation')}[/]", id=AI_NEW),
            *(Option(self._row(one), id=str(one["id"])) for one in self._listed),
        ]
        if self._said:
            rows.append(Option(escape(self._said), disabled=True))
        self.set_options(rows)
        ids = [int(one["id"]) for one in self._listed]
        self.highlighted = ids.index(was) + 1 if was in ids else 0
        self._keeps()

    def _keeps(self) -> None:
        """Keeps the marks for the next time the interface opens, once they have changed."""
        keeps(self._marks, self._kept)

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
        self._marks.follows(one)
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
            self._lists(self._listed)

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
        self._forgot(number)
        self.reads()


def _made(app: App[None]) -> Conversations:
    """The view, opening a conversation the way `/ai` does in this interface."""
    host = cast("Humanize", app)

    def follows(one: dict[str, Any]) -> None:
        host.follows_ai(one)
        app.set_focus(None)
        for prompt in app.query("#editor"):
            prompt.focus()

    def news() -> None:
        app.run_worker(app.run_action("ai"), exclusive=False)

    def followed() -> int | None:
        one = host.ai_followed()
        return None if one is None or "id" not in one else int(one["id"])

    def forgot(number: int) -> None:
        # Gone with its host: this directory's own is followed again, as `/ai` leaves it.
        if followed() == number:
            host.follows_ai(None)

    return Conversations(follows=follows, news=news, followed=followed, forgot=forgot)


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
