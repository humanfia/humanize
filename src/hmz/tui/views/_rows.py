"""A chat, an epic and a harness session as the navigator and Search list them.

Each is read into one shape of row, as the page reads them (`chats.js`, `sidebar-rows.js`),
so that the two views draw them alike and open them alike: what a row is marked with, the
word that says how it stands, how long ago it was heard of, and what enter does with it.
Everything is asked of this machine's daemon, which is whose they are; nothing is read off
their files.
"""

# The views are part of one interface laid out over several files, and the one name borrowed
# here is what would be a private name within one of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol, cast

from rich.cells import cell_len, set_cell_size
from rich.markup import escape
from textual.content import Content
from textual.widgets.option_list import Option

from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual.app import App
    from textual.widgets import OptionList

    from hmz.tui.shell import Shell

__all__ = [
    "CHAT",
    "EPIC",
    "HARNESS",
    "Asks",
    "Interface",
    "Picked",
    "Row",
    "ago",
    "chat_row",
    "drawn",
    "epic_row",
    "folder_name",
    "harness_row",
    "here",
    "interface",
    "local",
    "opens",
    "said",
    "same",
    "stamp",
]

#: The three kinds a row is of.
CHAT: Final = "chat"
EPIC: Final = "flow"
HARNESS: Final = "harness"

#: The marks that wait on the person, which stand first in any list they are in.
WAITS: Final = frozenset({"asking", "waiting"})

#: The marks an epic or a chat is going by.
GOING: Final = frozenset({"running", "stopping", *WAITS})

#: What asks the daemon one thing: a method, and what it takes.
type Asks = Callable[..., dict[str, Any]]

#: The calls that change something, which carry an `idem` of their own.
_WRITES: Final = frozenset(
    {
        "chat.rename",
        "chat.fork",
        "chat.archive",
        "chat.delete",
        "chat.backup",
        "chat.harness.adopt",
        "runs.backup",
        "workspaces.forget",
    }
)

#: Stopping the epic a host goes with, which is asked of that host rather than of the daemon.
STOP: Final = "epic.stop"

#: How long a host is waited on to say it is stopping.
_PATIENCE: Final = 30.0


def local(method: str, **params: Any) -> dict[str, Any]:
    """Asks this machine's daemon one thing, and answers what it said.

    Args:
      method: The method; :data:`STOP` is asked of the host of `workspace` and `slot`.
      params: What it takes; one given None is left out.

    Raises:
      OSError: Where the daemon was not reached or refused it, saying why.
    """
    given = {name: value for name, value in params.items() if value is not None}
    if method == STOP:
        from hmz import daemon

        link = daemon.attach(
            "tui", workspace=str(given["workspace"]), slot=str(given.get("slot") or "")
        )
        try:
            return link.asked({"do": "stop"}, seconds=_PATIENCE)
        finally:
            link.close()
    from hmz.tui.pick import LOCAL_DAEMON, _rpc

    return dict(_rpc(LOCAL_DAEMON, method, given, writes=method in _WRITES) or {})


class Interface(Protocol):
    """What a view asks of the interface it is opened in."""

    shell: Shell

    def opens_chat(self, chat: str, slot: str | None = None) -> None:
        """Puts one chat of this directory on the log."""
        ...

    def opens_epic(
        self, epic: str, slot: str | None = None, *, here: bool = True
    ) -> None:
        """Puts one epic on the log, or goes into what is written of it."""
        ...

    def showing(self) -> str:
        """The chat or the epic on the log, by its id or its name."""
        ...

    def show(self, text: str, style: str = "") -> None:
        """Puts a line in the transcript."""
        ...

    def copied(self, text: str) -> None:
        """Puts something on the clipboard."""
        ...


def interface(app: App[Any]) -> Interface:
    """The interface a view is opened in, as what a view asks of it."""
    return cast("Interface", app)


def here() -> str:
    """The directory this interface is of."""
    return str(Path.cwd().resolve())


def same(one: str, other: str) -> bool:
    """Whether two paths name one directory, however each was spelled."""
    if one == other:
        return True
    if not one or not other:
        return False
    try:
        return Path(one).resolve() == Path(other).resolve()
    except OSError:
        return False


def folder_name(path: str) -> str:
    """What a folder is called: the last of its path."""
    return Path(path).name or path


@dataclass(frozen=True)
class Row:
    """One chat, epic or harness session, as a list says it."""

    name: str
    """What it is known by: a chat's id, an epic's name, `harness:<harness>:<id>`."""
    kind: str
    """:data:`CHAT`, :data:`EPIC` or :data:`HARNESS`."""
    title: str
    """What it is listed by: a chat's title, an epic's task, on one line."""
    workspace: str = ""
    folderless: bool = False
    how: str = ""
    """Its mark: how an epic stands, and of a chat `running`, `asking`, `failed` or ""."""
    began: str = ""
    ended: str = ""
    held: bool = False
    """Whether a host goes with it."""
    slot: str = ""
    flow: str = ""
    harness: str = ""
    session: str = ""
    continuable: bool = False

    @property
    def waits(self) -> bool:
        """Whether it waits on its person."""
        return self.how in WAITS

    @property
    def going(self) -> bool:
        """Whether an epic is going: a chat never is, whether or not a host holds it."""
        return self.kind == EPIC and (self.held or self.how in GOING)


def _line(text: object) -> str:
    return " ".join(str(text or "").split())


def chat_row(chat: Mapping[str, Any]) -> Row:
    """A chat as `chat.list` rows it."""
    state = str(chat.get("state") or "")
    how = {"turn": "running", "asking": "asking", "failed": "failed"}.get(state, "")
    name = str(chat.get("id") or "")
    return Row(
        name=name,
        kind=CHAT,
        title=_line(chat.get("title")) or name,
        workspace=str(chat.get("workspace") or ""),
        folderless=chat.get("folderless") is True,
        how=how,
        began=str(chat.get("began") or ""),
        ended=str(chat.get("updated") or ""),
        held=bool(chat.get("slot")),
        slot=str(chat.get("slot") or ""),
    )


def epic_row(run: Mapping[str, Any], running: Sequence[Mapping[str, Any]] = ()) -> Row:
    """An epic as `runs.list` rows it, marked as its host says where one is stopping it.

    One going that asked its person something is asking: a question comes before the
    stopping of the epic that asks it.
    """
    how = str(run.get("how") or "")
    held = run.get("held") is True
    workspace, slot = str(run.get("workspace") or ""), str(run.get("slot") or "")
    if held and any(
        one.get("state") == "stopping"
        and one.get("workspace") == workspace
        and str(one.get("slot") or "") == slot
        for one in running
    ):
        how = "stopping"
    if how in ("running", "stopping") and run.get("asking"):
        how = "asking"
    name = str(run.get("name") or "")
    return Row(
        name=name,
        kind=EPIC,
        title=_line(run.get("task")) or name,
        workspace=workspace,
        folderless=run.get("folderless") is True,
        how=how,
        began=str(run.get("began") or ""),
        ended=str(run.get("ended") or ""),
        held=held,
        slot=slot,
        flow=str(run.get("flow") or ""),
    )


def harness_row(one: Mapping[str, Any]) -> Row:
    """A session a harness had of its own, as `chat.harness.list` rows it: only read."""
    harness, session = str(one.get("harness") or ""), str(one.get("id") or "")
    return Row(
        name=f"{HARNESS}:{harness}:{session}",
        kind=HARNESS,
        title=_line(one.get("title")) or session,
        workspace=str(one.get("workspace") or ""),
        began=str(one.get("began") or ""),
        ended=str(one.get("updated") or ""),
        harness=harness,
        session=session,
        continuable=one.get("continuable") is True,
    )


def _moment(written: str) -> datetime.datetime | None:
    try:
        at = datetime.datetime.fromisoformat(written)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.UTC)


def stamp(written: str) -> float:
    """A moment an epic or a chat wrote down, in seconds, or 0 where it wrote none."""
    at = _moment(written)
    return at.timestamp() if at else 0.0


def ago(written: str, now: float) -> str:
    """How long ago something happened, as the page says it."""
    at = _moment(written)
    if at is None:
        return ""
    seconds = max(0.0, now - at.timestamp())
    if seconds < 45:  # noqa: PLR2004 -- the page's own
        return t("just now")
    if seconds < 3600:  # noqa: PLR2004
        return t("{n}m ago", n=round(seconds / 60))
    if seconds < 86400:  # noqa: PLR2004
        return t("{n}h ago", n=round(seconds / 3600))
    local_ = at.astimezone()
    return f"{local_:%b} {local_.day}"


#: A chat's state in words, as a chat app says it, and an epic's mark as a word.
_CHAT_SAID: Final = {
    "running": "Running",
    "asking": "Awaiting input",
    "failed": "Failed",
}
_EPIC_SAID: Final = {
    "running": "Running",
    "asking": "Asking",
    "waiting": "Waiting",
    "stopping": "Stopping",
    "done": "Done",
    "failed": "Failed",
    "refused": "Refused",
    "crashed": "Crashed",
    "stopped": "Stopped",
    "budget": "Budget spent",
    "unfinished": "Unfinished",
    "unknown": "Unknown",
}


def said(row: Row) -> str:
    """How a row stands, in the words the page's lists say it in; "" for a chat at rest."""
    if row.kind == HARNESS:
        return t("Read-only")
    if row.kind == CHAT:
        return t(_CHAT_SAID[row.how]) if row.how in _CHAT_SAID else ""
    known = _EPIC_SAID.get(row.how)
    return t(known) if known else row.how.capitalize()


def _colour(row: Row) -> str:
    """What a row's mark is drawn in: pink waits on the person, cyan is going."""
    if row.waits:
        return "$hmz-pink"
    if row.how in ("running", "stopping"):
        return "$primary"
    if row.how == "done":
        return "$success"
    if row.how in ("failed", "refused", "crashed"):
        return "$error"
    return "$hmz-ink-3"


def _cut(text: str, room: int) -> str:
    """A text in exactly so many cells: cut with an ellipsis, or padded."""
    if room <= 0:
        return ""
    if cell_len(text) > room:
        return set_cell_size(text, room - 1) + "…"
    return set_cell_size(text, room)


def drawn(
    row: Row,
    room: int,
    now: float,
    *,
    flag: tuple[str, str] = (" ", ""),
    current: bool = False,
    about: str = "",
) -> Content:
    """One row as a line, exactly `room` cells wide.

    Its mark, a flag beside it, its title, and at the far end how it stands -- or, of one at
    rest, how long ago it was heard of.

    Args:
      row: The row.
      room: How many cells there are.
      now: The moment it is drawn.
      flag: One cell beside the mark and what it is drawn in: unread, or pinned.
      current: Whether it is the one on the log, which is cyan.
      about: More to say before how it stands: its folder, its flow.
    """
    from hmz.tui import humanfia

    colour = _colour(row)
    stands = said(row) if row.how in GOING or row.kind == HARNESS else ""
    last = stands or ago(row.ended or row.began, now) or said(row)
    end = " · ".join(one for one in (about, last) if one)
    end = _cut(end, min(cell_len(end), max(room // 2, 8)))
    title = _cut(row.title, room - 3 - cell_len(end) - 1)
    mark = humanfia.SQUARE if row.how or row.kind == EPIC else " "
    return Content.assemble(
        (mark, colour),
        flag,
        " ",
        (title, "$primary" if current else ""),
        " ",
        (end, colour if stands else "$hmz-ink-3"),
    )


class Picked:
    """A list whose row under the cursor is drawn plainly, in the colours of the cursor.

    Every row is drawn in colours of its own -- its mark, its title, how it stands -- and a
    colour of its own stays what it is on the plane the cursor fills, where it may be the
    plane's own. So the row the cursor is on is put up as its text alone, and takes the
    cursor's colours whole.
    """

    def __init__(self) -> None:
        """Holds no rows yet."""
        self._lines: dict[str, Content] = {}
        self._on = ""

    def fills(self, listing: OptionList, lines: Sequence[tuple[str, Content]]) -> None:
        """Puts the rows up, each by what it is put up under; none is under the cursor yet."""
        self._lines, self._on = dict(lines), ""
        listing.set_options([Option(line, id=name) for name, line in lines])

    def moves(self, listing: OptionList) -> None:
        """Draws the row the cursor is on now plainly, and the one it left in its colours."""
        at = listing.highlighted
        name = (
            str(listing.get_option_at_index(at).id or "")
            if at is not None and 0 <= at < listing.option_count
            else ""
        )
        if name == self._on:
            return
        if self._on in self._lines:
            listing.replace_option_prompt(self._on, self._lines[self._on])
        if name in self._lines:
            listing.replace_option_prompt(name, Content(self._lines[name].plain))
        self._on = name


async def opens(app: App[Any], row: Row, asks: Asks = local) -> bool:
    """Opens one row in the log, by what `/resume` and `/epics` open one with.

    A chat of this directory goes on the log, as one picked on `/resume` does, and so does a
    harness's own session where its harness carries a copy on: the copy is a chat. An epic a
    host of this directory goes with goes on the log too; any other is gone into as `/epics`
    goes into one, wherever it ran. A chat of another directory is not this interface's to
    carry on, which is said.

    Args:
      app: The interface.
      row: The row.
      asks: What asks the daemon one thing.

    Returns:
      Whether it was opened.
    """
    to = interface(app)
    ours = same(row.workspace, here())
    if row.kind == EPIC:
        to.opens_epic(row.name, row.slot if row.held and ours else None, here=ours)
        return True
    if row.folderless:
        to.show(t("This chat has no folder. Open it in the browser."))
        return False
    if not ours:
        to.show(
            t(
                "This is in the folder {name}. Run `hmz` in that folder to open it.",
                name=escape(folder_name(row.workspace)),
            )
        )
        return False
    if row.kind == CHAT:
        # Already on the log, it is gone to and no more. Otherwise the host that holds it is
        # the one the list last said, and where it said none the hosts are asked: a list is
        # as old as it was last read, and a chat carried on since has a host by now.
        if row.name != to.showing():
            to.opens_chat(row.name, row.slot or None)
        return True
    if not row.continuable:
        to.show(
            t(
                "Read-only. A session of {harness} cannot be continued in a chat.",
                harness=escape(row.harness),
            )
        )
        return False
    try:
        made = await asyncio.to_thread(
            asks,
            "chat.harness.adopt",
            workspace=row.workspace,
            harness=row.harness,
            session=row.session,
        )
    except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
        to.show(escape(str(why)), "red")
        return False
    to.opens_chat(str(made.get("chat") or ""), "")
    return True
