"""The chats written down, on the sheets they are gone back to and tidied from.

A chat is no epic (Section 8 of [CORE]) and `/epics` lists none: the chats of this directory
are on `/resume` in a chat, each with a menu of what `chat.*` does to one that is written down
-- renaming it, forking it, archiving it, backing it up, deleting it (Section 7.12.5 of [TUI])
-- and the ones archived are on the Workspace page of `/settings`, where one picked is put back
(Section 19.11 of [TUI]). Everything here is asked of this machine's daemon, whose chats they
are (Section 4.25 of [DAEMON]); nothing is read off a chat's files.
"""

# The sheets are one piece of code laid out over several files, and the names one borrows
# from another are what would be a private name within one of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rich.markup import escape
from textual import on, work
from textual.widgets import Label, OptionList

from .pick import (
    _COPY_NAME,
    LOCAL_DAEMON,
    Action,
    Form,
    Picks,
    Popup,
    Question,
    _hmz,
    _popup,
    _rpc,
    bad,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual.app import App

__all__ = ["Archived", "Deletes", "Renames", "Resumes", "calls"]

#: How much of a chat's title a row shows.
_TITLE = 60

#: What a row of `/resume` offers, each by the key its row of the menu answers with.
_RENAMES, _FORKS, _ARCHIVES, _UPLOADS, _DELETES = (
    "rename",
    "fork",
    "archive",
    "upload",
    "delete",
)

#: The methods of `chat.*` that write nothing, which carry no `idem`.
_READS = frozenset({"chat.list", "chat.get"})

#: Where an archived chat is put back from, said wherever one is archived.
PUT_BACK = "/settings workspace puts it back"


def calls(method: str, **said: Any) -> dict[str, Any]:
    """Asks this machine's daemon one thing of its chats, and answers what it said.

    Args:
      method: A method of `chat.*` that names a chat as it is written down, or `chat.list`.
      said: What it takes.

    Raises:
      OSError: Where the daemon was not reached or refused it, saying why.
    """
    return dict(_rpc(LOCAL_DAEMON, method, said, writes=method not in _READS) or {})


def _titled(chat: Mapping[str, Any]) -> str:
    """What a chat is called on a row: its title on one line, cut, or its id for none."""
    title = " ".join(str(chat.get("title") or "").split())
    return (title if len(title) <= _TITLE else f"{title[: _TITLE - 1]}…") or str(
        chat.get("id") or ""
    )


class Renames(Form[str]):
    """What a chat is to be called from now on: one written row, opening on its title."""

    def __init__(self, title: str) -> None:
        """Opens on the title the chat has.

        Args:
          title: It.
        """
        super().__init__()
        self._typed_in = {"title": title}
        self._fresh = {"title"}

    def asked(self) -> list[Question]:
        """The title."""
        return [
            Question(
                "title",
                "title",
                "what the chat is listed by",
                needed=not self._typed_in.get("title", "").strip(),
            )
        ]

    def done_about(self) -> str:
        """What answering it does."""
        return "renames the chat"

    def _ask(self) -> None:
        """Says what this is for."""
        self.query_one("#asked", Label).update("Rename the chat")
        self.query_one("#about", Label).update(
            "A chat is listed by its title: the first line said in it, until it is given "
            "another."
        )
        self._fill()

    def action_done(self) -> None:
        """Answers with the title, once it says something."""
        title = " ".join(self._typed_in.get("title", "").split())
        if not title:
            self._wrong = "a chat's title says something"
            self._fill()
            return
        self.dismiss(title)


class Deletes(Popup):
    """Whether to delete a chat, which cannot be brought back."""

    CSS = _popup("Deletes")

    def __init__(self, title: str) -> None:
        """Initializes the question.

        Args:
          title: What the chat is called.
        """
        super().__init__()
        self.asked = f"Delete {escape(title)}?"
        self.about = (
            "Permanent: the chat and the conversation kept with it are removed, and "
            "cannot be brought back."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """Keeping it, which is first and so what enter answers, or deleting it."""
        return [("no", "keep", "keep it"), ("yes", "delete", "delete it for good")]


class _Listed(Picks):
    """A list of chats that changes under what is done to them, and says how each went."""

    def __init__(
        self,
        chats: Sequence[Mapping[str, Any]],
        asks: Callable[..., dict[str, Any]] = calls,
        current: str = "",
    ) -> None:
        """Holds the chats.

        Args:
          chats: Each as a chat row of `chat.list`, newest first.
          asks: What asks the daemon one thing of its chats, as :func:`calls` does.
          current: The chat already had, by its id, which is ticked, or "" for none.
        """
        super().__init__(current)
        self._chats = [dict(one) for one in chats]
        self._asks = asks
        #: The chats that left the list, by id: archived, put back or deleted.
        self.gone: set[str] = set()
        #: What became of the last thing done, already markup.
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """Each chat, by its id, with its title."""
        return [
            (str(one.get("id") or ""), _titled(one), str(one.get("id") or ""))
            for one in self._chats
        ]

    def nothing(self) -> str:
        """What became of the last thing done."""
        return self._said

    def _showing(self) -> App[None]:
        """The interface, which a sheet over this one is put up on."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    def _chat(self) -> dict[str, Any] | None:
        """The chat under the cursor."""
        return next((one for one in self._chats if one.get("id") == self.under()), None)

    def _redrawn(self, said: str, gone: str = "") -> None:
        """Says what happened, and puts the list up again without a chat that left it."""
        self._chats = [one for one in self._chats if one.get("id") != gone]
        if gone:
            self.gone.add(gone)
        self._said, self._rows = said, None
        self._fill()

    async def _asked(self, method: str, **said: Any) -> dict[str, Any] | None:
        """Asks the daemon off the screen's thread; None, having said why, where refused."""
        try:
            return await asyncio.to_thread(self._asks, method, **said)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._redrawn(bad(escape(str(why))))
            return None


class Resumes(_Listed):
    """The earlier chats of this directory, newest first, to carry one on: `/resume` in a chat.

    What the harness's own `/resume` is at its prompt: a list of the conversations had here,
    one of which is picked up where it was left (Section 8.9.8 of [CORE]). And where each is
    renamed, forked, archived, backed up and deleted, on its menu.
    """

    asked = "Resume a chat"
    about = "The chats of this directory, newest first: the one picked goes on."

    def menu(self) -> tuple[str, list[Action]] | None:
        """What is done to the chat under the cursor as it is written down."""
        chat = self._chat()
        if chat is None:
            return None
        name = str(chat.get("id") or "")
        acts = [
            Action(
                _RENAMES,
                "rename",
                "give it another title",
                lambda: self._renames(chat),
            ),
            Action(
                _FORKS,
                "fork",
                "a new chat that goes on from this one, and go to it",
                lambda: self._forks(name),
            ),
            Action(
                _ARCHIVES,
                "archive",
                f"take it out of this list; {PUT_BACK}",
                lambda: self._archives(chat),
            ),
            Action(
                _UPLOADS,
                "upload",
                "back the chat up to its targets, or the defaults",
                lambda: self._uploads(name),
                lambda: bool(_hmz().backups.targets()),
            ),
            Action(
                _DELETES,
                "delete",
                "remove it for good, after asking",
                lambda: self._deletes(chat),
            ),
            Action(_COPY_NAME, "copy id", name, lambda: self._copies(name)),
        ]
        return _titled(chat), acts

    def _copies(self, name: str) -> None:
        self.copies(name)
        self._redrawn("id copied")

    @work
    async def _renames(self, chat: dict[str, Any]) -> None:
        """Asks what the chat is to be called, and renames it."""
        if self.opening():
            return
        try:
            title = await self._showing().push_screen_wait(
                Renames(str(chat.get("title") or ""))
            )
        finally:
            self.opened()
        if not title:
            return
        row = await self._asked("chat.rename", chat=chat.get("id"), title=title)
        if row is not None:
            chat["title"] = row.get("title", title)
            self._redrawn(f"renamed {escape(_titled(chat))}")

    @work
    async def _forks(self, name: str) -> None:
        """Forks the chat, and answers with the fork, which is the chat gone on with."""
        said = await self._asked("chat.fork", chat=name)
        if said is not None:
            self.dismiss(str(said.get("chat") or ""))

    @work
    async def _archives(self, chat: dict[str, Any]) -> None:
        """Archives the chat, which leaves this list."""
        name = str(chat.get("id") or "")
        if await self._asked("chat.archive", chat=name) is not None:
            self._redrawn(f"archived {escape(_titled(chat))}; {PUT_BACK}", name)

    @work
    async def _uploads(self, name: str) -> None:
        """Queues a backup of the chat, which is not waited on."""
        said = await self._asked("chat.backup", chat=name)
        if said is not None:
            queued = ", ".join(str(one) for one in said.get("queued") or ())
            self._redrawn(f"backing up to {escape(queued)}")

    @work
    async def _deletes(self, chat: dict[str, Any]) -> None:
        """Asks whether the chat is to go for good, and deletes it on a yes."""
        if self.opening():
            return
        try:
            sure = await self._showing().push_screen_wait(Deletes(_titled(chat)))
        finally:
            self.opened()
        name = str(chat.get("id") or "")
        if sure == "yes" and await self._asked("chat.delete", chat=name) is not None:
            self._redrawn(f"deleted {escape(_titled(chat))}", name)


class Archived(_Listed):
    """The archived chats of this directory, one of which is put back among the others."""

    SEARCHES: ClassVar = True

    asked = "Archived chats"
    about = (
        "The chats of this directory that were archived, newest first: the one picked is "
        "put back among the others, on /resume in a chat."
    )

    def __init__(
        self, workspace: str, asks: Callable[..., dict[str, Any]] = calls
    ) -> None:
        """Opens on the archived chats of one directory, which are asked for as it opens.

        Args:
          workspace: The directory.
          asks: What asks the daemon one thing of its chats, as :func:`calls` does.
        """
        super().__init__([], asks)
        self._workspace = workspace
        self._said = "reading the archived chats…"

    def _ask(self) -> None:
        """Says what this is, and asks for the chats."""
        super()._ask()
        self._reads()

    @work
    async def _reads(self) -> None:
        """Reads every archived chat of the directory, a page at a time."""
        found: list[dict[str, Any]] = []
        while True:
            said = await self._asked(
                "chat.list",
                workspace=self._workspace,
                archived=True,
                offset=len(found),
                limit=200,
            )
            if said is None:
                return
            page = cast("list[dict[str, Any]]", said.get("chats") or [])
            found += page
            if not page or len(found) >= int(said.get("total") or 0):
                break
        self._chats = found
        self._redrawn("" if found else "no chat of this directory is archived")
        if found:
            # The list was empty as the sheet opened, so the focus went to a button under it.
            self.query_one("#choices", OptionList).focus()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Puts the chat picked back among the others, and stays on the list."""
        # All of it answered here: the list's own would answer with the row and leave.
        event.prevent_default()
        chat = self._chat()
        if chat is not None:
            self._puts_back(chat)

    @work
    async def _puts_back(self, chat: dict[str, Any]) -> None:
        name = str(chat.get("id") or "")
        if await self._asked("chat.unarchive", chat=name) is not None:
            self._redrawn(f"put back {escape(_titled(chat))}", name)
