"""The navigator: every chat and epic there is to work on, and first what waits on you.

What the page's sidebar is (Section 3.5 of web.md), beside the log: every workspace's chats,
epics and -- where General lists them -- the sessions each harness had of its own, from the
same calls of the daemon. It answers two things at a glance: what needs me, and where was I.
So what waits on its person stands first, under a heading of its own, and is the only pink
there is; everything under it is quiet, grouped by folder, by date, or as one list.

The list does not move under the keys: while they are in it, what is read again from the
daemon is drawn into the rows where they stand, and the order is settled again only once
the keys have left or the person themself changed it. What is pinned, what is unread, how
the list is grouped and which groups are folded are one person's way of looking, kept
beside the prompt history and asked of no daemon.
"""

# The views are part of one interface laid out over several files, and the names borrowed
# from the sheets are what would be private names within one of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import datetime
import json
import time
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast
from weakref import WeakSet

from rich.cells import cell_len, set_cell_size
from rich.markup import escape
from textual import on, work
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import OptionList, Static

from hmz import state
from hmz.tui import humanfia
from hmz.tui.chats import Deletes, Renames
from hmz.tui.pick import Action, Acts, Popup, _popup
from hmz.tui.shell import View
from hmz.words import t

from . import _rows, newchat, newepic
from ._rows import CHAT, EPIC, HARNESS, Asks, Row

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from textual import events
    from textual.app import App, ComposeResult
    from textual.widget import Widget

__all__ = ["GROUPS", "VIEWS", "WIDE", "Group", "Kept", "Navigator", "arranged", "told"]

#: How the list is grouped, in the order the key steps through them, and what each is called.
GROUPS: Final = ("folder", "date", "none")
_GROUPED: Final = {"folder": "Folder", "date": "Date", "none": "None@@group"}

#: How wide a terminal is before the navigator is open as the interface opens.
WIDE: Final = 110

#: How often the list is read again with nothing told of, in seconds.
_EVERY: Final = 5.0

#: How many rows a group shows before `Show {n} more`, and how many of each the daemon is
#: asked for: the most it answers at once.
_GROUP_ROWS: Final = 20
_MOST: Final = 200

#: How many chats, and how many epics, are listed at the most.
_ROWS: Final = 2000

#: How many folders' harness sessions are asked for, and how many of each.
_HARNESSED_FOLDERS: Final = 8
_HARNESSED: Final = 50

#: How many names a list of one person's keeps.
_KEPT: Final = 200

#: How many times a list with no width yet is waited on before it is drawn as it is.
_LAYS: Final = 20

#: What tells the rows of the list apart by what they are: a heading, a chat or an epic, a
#: folder of `Folders`, and the row that shows the rest of a group.
_HEAD, _ROW, _PLACE, _MORE = "g:", "r:", "f:", "m:"

#: The marks beside a row: unread, as the page's sidebar marks one, and pinned.
_UNREAD: Final = "●"
_OPEN, _SHUT = "▾", humanfia.POINT

#: The groups `Date` makes, by how many days ago a row stands.
_DAYS: Final = (
    (0, "today", "Today"),
    (1, "yesterday", "Yesterday"),
    (7, "week", "Last 7 days"),
    (30, "month", "Last 30 days"),
    (10**9, "older", "Older"),
)


class Kept:
    """What one person keeps of the list: its grouping, and the rows pinned, unread, folded.

    In Humanize's state directory, beside the prompt history: a way of looking, which is no
    loss to lose and nothing a daemon is asked to hold. Another view's lists of the same
    kind are kept beside the navigator's, each under a name of its own.
    """

    #: The lists kept: the navigator's, then Ai-chan's (`hmz.tui.views.aichan`).
    LISTS: ClassVar = ("pinned", "unread", "shut", "ai-pinned", "ai-unread", "ai-seen")

    def __init__(self, at: Path | None = None) -> None:
        """Reads what is kept.

        Args:
          at: The file, defaulting to `navigator.json` of the state directory.
        """
        self._at = at if at is not None else state() / "navigator.json"
        self._group: str = GROUPS[0]
        self._lists: dict[str, list[str]] = {}
        self.reads()

    def reads(self) -> None:
        """Reads what is kept again: another interface of this person may have written it."""
        held: dict[str, Any] = {}
        try:
            read = json.loads(self._at.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            read = None
        if isinstance(read, dict):
            held = cast("dict[str, Any]", read)
        group = held.get("group")
        self._group = group if isinstance(group, str) and group in GROUPS else GROUPS[0]
        for which in self.LISTS:
            listed = held.get(which)
            self._lists[which] = (
                [str(one) for one in cast("list[object]", listed)]
                if isinstance(listed, list)
                else []
            )

    @property
    def group(self) -> str:
        """How the list is grouped: one of :data:`GROUPS`."""
        return self._group

    @group.setter
    def group(self, group: str) -> None:
        self.reads()
        self._group = group if group in GROUPS else GROUPS[0]
        self._writes()

    def has(self, which: str, name: str) -> bool:
        """Whether a row is pinned, unread, or a group shut: `pinned`, `unread`, `shut`."""
        return name in self._lists[which]

    def all(self, which: str) -> frozenset[str]:
        """Every name of one of the lists."""
        return frozenset(self._lists[which])

    def marks(self, which: str, name: str, on: bool) -> None:  # noqa: FBT001 -- which way
        """Puts a name in one of the lists or takes it out, the newest last."""
        self.reads()
        rest = [one for one in self._lists[which] if one != name]
        self._lists[which] = ([*rest, name] if on else rest)[-_KEPT:]
        self._writes()

    def keeps(self, lists: Mapping[str, Sequence[str]]) -> None:
        """Keeps some of the lists as a whole, each in the order given, where one is another."""
        self.reads()
        now = {which: list(names)[-_KEPT:] for which, names in lists.items()}
        if any(self._lists[which] != names for which, names in now.items()):
            self._lists.update(now)
            self._writes()

    def _writes(self) -> None:
        try:
            self._at.parent.mkdir(parents=True, exist_ok=True)
            self._at.write_text(
                json.dumps({"group": self._group, **self._lists}), encoding="utf-8"
            )
        except OSError:
            return  # a way of looking nobody can write is not a list to lose


@dataclass(frozen=True)
class Group:
    """One group of the list: a heading, and the rows under it."""

    key: str
    kind: str
    """`waiting`, `pinned`, `folder`, `date`, `all` or `folders`."""
    label: str
    path: str = ""
    rows: tuple[Row, ...] = ()
    folders: tuple[tuple[str, int], ...] = ()
    """Of `folders`: each folder's path and how many rows it has."""
    missing: bool = False
    """Of a folder: whether its directory is gone."""
    empty: bool = False
    """Of a folder: whether nothing ran in it and nothing goes in it, as the daemon counts."""


def _last(row: Row) -> float:
    return _rows.stamp(row.ended) or _rows.stamp(row.began)


def _days_ago(at: float, now: float) -> int:
    day = datetime.datetime.fromtimestamp
    return max(0, (day(now).date() - day(at).date()).days)


def arranged(
    rows: Sequence[Row],
    folders: Sequence[Mapping[str, Any]] = (),
    *,
    group: str = "folder",
    pinned: frozenset[str] = frozenset(),
    now: float | None = None,
) -> list[Group]:
    """The list's groups, in their order, as the page's sidebar arranges them.

    What waits on its person first, under `Waiting for you`; then the rows pinned; then the
    rest by folder -- every workspace offered, those an epic is going in first, then by
    their latest, the rows of no folder last -- by date, or as one group. Grouped by
    anything but folder, the folders stand last as a group of their own.

    Args:
      rows: The chats and epics listed.
      folders: The workspaces, as `workspaces.list` answers them.
      group: One of :data:`GROUPS`.
      pinned: The names pinned.
      now: The moment, which one going was last updated at.
    """
    now = time.time() if now is None else now
    at = {row.name: (now if row.going else _last(row)) for row in rows}
    ordered = sorted(rows, key=lambda row: -at[row.name])
    waiting = tuple(row for row in ordered if row.waits)
    kept = tuple(row for row in ordered if not row.waits and row.name in pinned)
    rest = [row for row in ordered if not row.waits and row.name not in pinned]
    groups: list[Group] = []
    if waiting:
        groups.append(Group(":waiting", "waiting", t("Waiting for you"), rows=waiting))
    if kept:
        groups.append(Group(":pinned", "pinned", t("Pinned"), rows=kept))
    held: dict[str, list[Row]] = {}
    gone: set[str] = set()
    # The folders nothing ran in: by the daemon's own count, which is of every chat and
    # epic there, and not by the rows listed here -- one pinned or waiting stands elsewhere.
    bare: set[str] = set()
    for one in folders:
        path = str(one.get("path") or "")
        # One whose directory is gone and that holds nothing has nothing to show.
        there = one.get("there") is not False
        holds = bool(one.get("epics") or one.get("chats") or one.get("running"))
        if path and (there or holds):
            held.setdefault(path, [])
            if not there:
                gone.add(path)
            if not holds:
                bare.add(path)
    for row in rest:
        held.setdefault("" if row.folderless else row.workspace, []).append(row)
    for row in rows:
        bare.discard(row.workspace)

    def rank(path: str) -> tuple[bool, bool, float]:
        going = any(row.held and row.kind == EPIC for row in held[path])
        return (
            not path,
            not going,
            -max((_last(row) for row in held[path]), default=0),
        )

    by_folder = [
        Group(
            path or ":nowhere",
            "folder",
            _rows.folder_name(path) if path else t("No folder"),
            path,
            tuple(held[path]),
            missing=path in gone,
            empty=path in bare,
        )
        for path in sorted(held, key=rank)
    ]
    if group == "folder":
        return [*groups, *by_folder] or [Group(":nowhere", "folder", t("No folder"))]
    named = tuple((one.path, len(one.rows)) for one in by_folder if one.path)
    places = (
        [Group(":folders", "folders", t("Folders"), folders=named)] if named else []
    )
    if group == "none":
        return [*groups, Group(":all", "all", t("All"), rows=tuple(rest)), *places]
    days: dict[str, list[Row]] = {key: [] for _, key, _ in _DAYS}
    for row in rest:
        away = _days_ago(at[row.name], now)
        days[next(key for most, key, _ in _DAYS if away <= most)].append(row)
    dated = [
        Group(f":date:{key}", "date", t(label), rows=tuple(days[key]))
        for _, key, label in _DAYS
        if days[key]
    ]
    if not dated and not groups:
        dated = [Group(":date:today", "date", t("Today"))]
    return [*groups, *dated, *places]


class Forgets(Popup):
    """Whether to forget a folder nothing ran in, which takes it out of the list."""

    CSS = _popup("Forgets")

    def __init__(self, name: str) -> None:
        """Asks of one folder.

        Args:
          name: What the folder is called.
        """
        super().__init__()
        self.asked = t("Forget the folder {name}?", name=escape(name))
        self.about = t(
            "The folder leaves this list and what it was set up with is forgotten. "
            "Nothing in the folder itself is removed."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """Keeping it, which is first and so what enter answers, or forgetting it."""
        return [("no", t("Cancel"), ""), ("yes", t("Forget"), "")]


@dataclass(frozen=True)
class _Read:
    """What the daemon answered of the list, read at once."""

    rows: tuple[Row, ...] = ()
    folders: tuple[Mapping[str, Any], ...] = ()
    harnessed: Mapping[str, tuple[Row, ...]] | None = None


#: The interfaces a navigator was already made for: the first is the one that opens with it.
_MADE: WeakSet[App[Any]] = WeakSet()


class Navigator(Vertical):
    """The list, and one line under it for what was last done."""

    DEFAULT_CSS = """
    Navigator { height: 1fr; }
    Navigator > OptionList, Navigator > OptionList:focus {
        height: 1fr; border: none; padding: 0; background: $surface;
        scrollbar-size-vertical: 1; }
    /* The row the cursor is on is a cyan plane while the keys are in the list, and a
       quiet one once they have left. */
    Navigator > OptionList > .option-list--option-highlighted {
        background: $hmz-line-strong; color: $foreground; text-style: none; }
    Navigator > OptionList:focus > .option-list--option-highlighted {
        background: $primary; color: $background; text-style: bold; }
    Navigator > #navigator-said { height: 1; padding: 0 1; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        Binding("n", "new_chat", show=False),
        Binding("N", "new_epic", show=False),
        Binding("p", "pin", show=False),
        Binding("u", "unread", show=False),
        Binding("full_stop", "menu", show=False),
        Binding("g", "group", show=False),
    ]

    def __init__(
        self,
        asks: Asks = _rows.local,
        kept: Kept | None = None,
        *,
        starting: bool = False,
    ) -> None:
        """Makes the list, which is read as it is put up.

        Args:
          asks: What asks the daemon one thing.
          kept: What this person keeps of the list.
          starting: Whether it is opened by the interface opening, which a narrow terminal
            closes again.
        """
        super().__init__()
        self._asks = asks
        self.kept = kept if kept is not None else Kept()
        self._starting = starting
        self._read = _Read()
        #: Whether the daemon has answered once, and whether it is being asked now.
        self._answered = False
        self._reading = False
        #: The rows and groups drawn, by what each is put up under, and their order.
        self._drawn_rows: dict[str, Row] = {}
        self._groups: dict[str, Group] = {}
        self._order: list[str] = []
        #: The groups shown whole, past their first rows.
        self._whole: set[str] = set()
        self._said = ""
        self._picked = _rows.Picked()
        #: How many times running the list was to be drawn before it had a width.
        self._unlaid = 0

    def compose(self) -> ComposeResult:
        """The list, and the line under it."""
        yield OptionList(id="navigator-list")
        yield Static(id="navigator-said")

    def focus(self, scroll_visible: bool = True) -> Widget:  # noqa: FBT001, FBT002 -- Textual's
        """Gives the keys to the list, which is what takes them here."""
        self._list.focus(scroll_visible)
        return self

    @property
    def _host(self) -> App[None]:
        """The interface this is part of."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    @property
    def _list(self) -> OptionList:
        return self.query_one("#navigator-list", OptionList)

    def on_mount(self) -> None:
        """Reads the list, and goes on reading it; closed again on a narrow terminal."""
        if self._starting and self._host.size.width < WIDE:
            self._host.call_later(_rows.interface(self._host).shell.closes, "navigator")
            return
        self._says(t("Reading the list…"))
        self.reads()
        self.set_interval(_EVERY, self.reads)

    def on_resize(self, _: events.Resize) -> None:
        """Draws every row again to the width there is now."""
        self._draws(hold=True)

    def on_descendant_blur(self, _: events.DescendantBlur) -> None:
        """Settles the order again, now that the keys have left."""
        self.call_after_refresh(self._draws)

    # -- Reading -------------------------------------------------------------------------

    def reads(self) -> None:
        """Asks the daemon for the list again, off the screen's thread; once at a time."""
        if not self._reading and self.is_attached:
            self._reading = True
            self._rereads()

    @work(group="navigator-reads")
    async def _rereads(self) -> None:
        self.kept.reads()
        shut = self.kept.all("shut")
        try:
            read = await asyncio.to_thread(self._asked, shut, self.kept.group)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            if not self._answered:
                self._says(str(why), "$error")
            return
        finally:
            self._reading = False
        if not self._answered:
            self._says("")
        self._answered = True
        self._read = read
        self._draws(hold=self._keyed())

    def _every(self, method: str, held: str) -> list[Mapping[str, Any]]:
        """Every row of one of the daemon's lists, a page at a time, up to :data:`_ROWS`."""
        found: list[Mapping[str, Any]] = []
        while len(found) < _ROWS:
            said = self._asks(method, offset=len(found), limit=_MOST)
            page = cast("list[Mapping[str, Any]]", said.get(held) or [])
            found += page
            if not page or len(found) >= int(said.get("total") or 0):
                break
        return found

    def _asked(self, shut: frozenset[str], group: str) -> _Read:
        """Everything the list is made of, as the daemon answers it now."""
        asks = self._asks
        running = cast(
            "list[Mapping[str, Any]]", asks("hosts.running").get("running") or []
        )
        chats = self._every("chat.list", "chats")
        runs = self._every("runs.list", "runs")
        folders = cast(
            "list[Mapping[str, Any]]",
            asks("workspaces.list").get("workspaces") or [],
        )
        harnessed: dict[str, tuple[Row, ...]] = {}
        # Only where they are drawn: after the rows of a folder that is not folded.
        if group == "folder" and asks("settings.get").get("harness_sessions") is True:
            open_ = [
                str(one.get("path") or "")
                for one in folders
                if one.get("there") is not False and one.get("path") not in shut
            ]
            for path in open_[:_HARNESSED_FOLDERS]:
                try:
                    found = asks("chat.harness.list", workspace=path, limit=_HARNESSED)
                except Exception:  # noqa: BLE001, S112 -- one that cannot be read lists none
                    continue
                harnessed[path] = tuple(
                    _rows.harness_row(one)
                    for one in cast(
                        "list[Mapping[str, Any]]", found.get("sessions") or []
                    )
                )
        return _Read(
            (
                *(_rows.chat_row(one) for one in chats),
                *(_rows.epic_row(one, running) for one in runs),
            ),
            tuple(folders),
            harnessed,
        )

    def hears(self, name: str, *, unread: bool) -> None:
        """Takes that something was told of a chat or an epic: unread, and read again."""
        if name and unread:
            self.kept.marks("unread", name, on=True)
        self.reads()

    # -- Drawing -------------------------------------------------------------------------

    def _keyed(self) -> bool:
        """Whether the keys are in the list."""
        return self.is_attached and self._list.has_focus

    def _says(self, said: str, style: str = "") -> None:
        """Says one thing on the line under the list."""
        self._said = said
        if self.is_attached:
            self.query_one("#navigator-said", Static).update(
                Content.styled(said, style)
            )

    def _room(self) -> int:
        return max(self._list.size.width - 2, 16)

    def _lines(self) -> list[tuple[str, Content]]:
        """Every row of the list, by what it is put up under, as markup."""
        room, now = self._room(), time.time()
        current = _rows.interface(self._host).showing()
        groups = arranged(
            self._read.rows,
            self._read.folders,
            group=self.kept.group,
            pinned=self.kept.all("pinned"),
            now=now,
        )
        self._drawn_rows, self._groups = {}, {one.key: one for one in groups}
        lines: list[tuple[str, Content]] = []
        for group in groups:
            shut = self.kept.has("shut", group.key)
            rows = list(group.rows)
            if group.kind == "folder" and group.path and not shut:
                # After its chats and epics, the sessions each harness had of its own there.
                rows += (self._read.harnessed or {}).get(group.path, ())
            lines.append((f"{_HEAD}{group.key}", self._heading(group, rows, room)))
            if shut:
                continue
            shown = rows if group.key in self._whole else rows[:_GROUP_ROWS]
            for row in shown:
                self._drawn_rows[row.name] = row
                flag = (
                    (_UNREAD, "$primary")
                    if self.kept.has("unread", row.name)
                    else (humanfia.POINT, "$hmz-ink-3")
                    if self.kept.has("pinned", row.name)
                    else (" ", "")
                )
                lines.append(
                    (
                        f"{_ROW}{row.name}",
                        _rows.drawn(
                            row, room, now, flag=flag, current=row.name == current
                        ),
                    )
                )
            if len(rows) > len(shown):
                more = t("Show {n} more", n=len(rows) - len(shown))
                lines.append(
                    (f"{_MORE}{group.key}", Content.styled(f"   {more}", "$hmz-ink-3"))
                )
            for path, count in group.folders:
                name = set_cell_size(_rows.folder_name(path), room - 3 - 5)
                lines.append(
                    (
                        f"{_PLACE}{path}",
                        Content.assemble(f"   {name} ", (f"{count:>4}", "$hmz-ink-3")),
                    )
                )
        if self._answered and not self._read.rows and not self._read.folders:
            nothing = t("Nothing here yet.") + t(
                " Start a chat or an epic, and it is written down here as it goes."
            )
            lines.append((f"{_MORE}", Content.styled(nothing, "$hmz-ink-3")))
        return lines

    def _heading(self, group: Group, rows: Sequence[Row], room: int) -> Content:
        """A group's heading: its name, which way it is folded, and how many it holds."""
        shut = self.kept.has("shut", group.key)
        colour = "$hmz-pink" if group.kind == "waiting" else "$text-muted"
        fold = _SHUT if shut else _OPEN
        count = str(len(rows)) if rows else ""
        unseen = shut and any(self.kept.has("unread", row.name) for row in rows)
        gone = f" {t('missing')}" if group.missing else ""
        ends = f"{_UNREAD} {count}" if unseen else count
        name = f"{group.label.upper()}{gone}"
        wide = room - 2 - cell_len(ends) - 1
        if cell_len(name) > wide:
            name = set_cell_size(name, max(wide - 1, 1)) + "…"
        pad = " " * max(wide - cell_len(name), 0)
        return Content.assemble(
            (f"{fold} {name}", f"bold {colour}"), f"{pad} ", (ends, "$hmz-ink-3")
        )

    def _draws(self, *, hold: bool = False) -> None:
        """Puts the list up again, the cursor on the row it was on.

        Args:
          hold: Whether every row keeps its place: what is new goes in after what it
            follows, and nothing already there moves. For what the daemon said while the
            keys are in the list, which must not reorder under them.
        """
        if not self.is_attached:
            return
        listing = self._list
        if not listing.size.width and self._unlaid < _LAYS:
            # Not laid out yet, so there is no width to draw a row to: once it is.
            self._unlaid += 1
            self.set_timer(0.05, partial(self._draws, hold=hold))
            return
        self._unlaid = 0
        lines = self._lines()
        if hold and self._order:
            fresh = dict(lines)
            order = [one for one in self._order if one in fresh]
            placed = set(order)
            before = ""
            for name, _ in lines:
                if name not in placed:
                    order.insert(order.index(before) + 1 if before else 0, name)
                    placed.add(name)
                before = name
            lines = [(name, fresh[name]) for name in order]
        was = self.under()
        at, scrolled = listing.highlighted, listing.scroll_y
        self._order = [name for name, _ in lines]
        self._picked.fills(listing, lines)
        if was in self._order:
            listing.highlighted = self._order.index(was)
        elif self._order:
            first = next(
                (n for n, one in enumerate(self._order) if one.startswith(_ROW)), 0
            )
            listing.highlighted = first if at is None else min(at, len(self._order) - 1)
        self._picked.moves(listing)
        listing.scroll_to(y=scrolled, animate=False)

    @on(OptionList.OptionHighlighted)
    def _moved(self, _: OptionList.OptionHighlighted) -> None:
        """Draws the row the cursor came to as the one it is on."""
        self._picked.moves(self._list)

    def under(self) -> str:
        """What the cursor is on, by what the row is put up under; "" for nothing."""
        listing = self._list
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "")

    def _row(self) -> Row | None:
        """The chat, epic or session under the cursor."""
        under = self.under()
        return (
            self._drawn_rows.get(under.removeprefix(_ROW))
            if under.startswith(_ROW)
            else None
        )

    def _lands_on(self, name: str) -> None:
        """Draws the list as it now stands, and puts the cursor on one row of it."""
        self._draws()
        if name in self._order:
            self._list.highlighted = self._order.index(name)

    # -- Keys ----------------------------------------------------------------------------

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Enter: opens a chat or an epic, folds a group, shows the rest of one."""
        event.stop()
        under = str(event.option.id or "")
        if under.startswith(_ROW):
            row = self._drawn_rows.get(under.removeprefix(_ROW))
            if row is not None:
                self._opens(row)
        elif under.startswith(_HEAD):
            self._folds(under.removeprefix(_HEAD))
        elif under.startswith(_MORE) and under != _MORE:
            self._whole.add(under.removeprefix(_MORE))
            self._lands_on(under)
        elif under.startswith(_PLACE):
            self._folder_menu(under.removeprefix(_PLACE))

    def _folds(self, key: str) -> None:
        self.kept.marks("shut", key, on=not self.kept.has("shut", key))
        self._lands_on(f"{_HEAD}{key}")

    @work
    async def _opens(self, row: Row) -> None:
        """Opens one row in the log, and gives the prompt the keys to go on in it."""
        self.kept.marks("unread", row.name, on=False)
        if await _rows.opens(self._host, row, self._asks):
            _rows.interface(self._host).shell.home()
        self._draws()

    async def action_new_chat(self, folder: str = "") -> None:
        """A new chat, of a folder or of this interface's own: on the New chat page."""
        await newchat.opens(self._host, folder=folder)

    async def action_new_epic(self, folder: str = "") -> None:
        """A new epic, of a folder or of this interface's own: on the New epic page."""
        await newepic.opens(self._host, folder=folder)

    def action_pin(self) -> None:
        """Pins the row under the cursor, or takes its pin away."""
        row = self._row()
        if row is not None:
            self._pins(row)

    def _pins(self, row: Row) -> None:
        self.kept.marks("pinned", row.name, on=not self.kept.has("pinned", row.name))
        self._lands_on(f"{_ROW}{row.name}")

    def action_unread(self) -> None:
        """Marks the row under the cursor unread, or read."""
        row = self._row()
        if row is not None:
            self._marks(row)

    def _marks(self, row: Row) -> None:
        self.kept.marks("unread", row.name, on=not self.kept.has("unread", row.name))
        self._lands_on(f"{_ROW}{row.name}")

    def action_group(self) -> None:
        """Groups the list the next way: by folder, by date, as one list."""
        self.kept.group = GROUPS[(GROUPS.index(self.kept.group) + 1) % len(GROUPS)]
        self._says(f"{t('Group by')}: {t(_GROUPED[self.kept.group])}")
        self._lands_on(self.under())

    def action_menu(self) -> None:
        """Opens what the row under the cursor offers: a chat's, an epic's, a folder's."""
        under = self.under()
        row = self._row()
        if row is not None:
            self._menu(row.title, self._offers(row))
        elif under.startswith(_PLACE):
            self._folder_menu(under.removeprefix(_PLACE))
        elif under.startswith(_HEAD):
            group = self._groups.get(under.removeprefix(_HEAD))
            if group is not None and group.kind == "folder" and group.path:
                self._folder_menu(group.path, group)

    @work
    async def _menu(self, named: str, acts: Sequence[Action]) -> None:
        """Puts one row's menu up, and does the one taken."""
        offered = [one for one in acts if one.able()]
        taken = await self._host.push_screen_wait(Acts(named, offered))
        for one in offered:
            if one.key == taken:
                one.does()

    def _offers(self, row: Row) -> list[Action]:
        """What the page's menu of a row offers that the terminal interface does."""
        ours = _rows.same(row.workspace, _rows.here())
        pinned = self.kept.has("pinned", row.name)
        unread = self.kept.has("unread", row.name)
        chat = row.kind == CHAT
        acts = [
            Action("open", t("Open"), "", lambda: self._opens(row)),
            Action(
                "pin", t("Unpin") if pinned else t("Pin"), "", lambda: self._pins(row)
            ),
            Action(
                "unread",
                t("Mark as read") if unread else t("Mark as unread"),
                "",
                lambda: self._marks(row),
            ),
        ]
        if row.kind == HARNESS:
            return [
                *acts,
                Action(
                    "copy",
                    t("Copy session ID"),
                    row.session,
                    lambda: self._copies(row.session, t("Session ID copied")),
                ),
            ]
        if chat:
            acts += [
                Action("rename", t("Rename"), "", lambda: self._renames(row)),
                Action("fork", t("Fork"), "", lambda: self._forks(row), lambda: ours),
                Action(
                    "copy",
                    t("Copy ID"),
                    row.name,
                    lambda: self._copies(row.name, t("ID copied")),
                ),
            ]
        else:
            acts += [
                Action(
                    "task",
                    t("Copy task"),
                    "",
                    lambda: self._copies(row.title, t("Task copied")),
                ),
                Action(
                    "copy",
                    t("Copy name"),
                    row.name,
                    lambda: self._copies(row.name, t("Name copied")),
                ),
            ]
        acts.append(Action("upload", t("Upload"), "", lambda: self._uploads(row)))
        if chat:
            acts += [
                Action("archive", t("Archive"), "", lambda: self._archives(row)),
                Action(
                    "delete",
                    t("Delete"),
                    "",
                    lambda: self._deletes(row),
                    variant="error",
                ),
            ]
        elif row.held:
            acts.append(
                Action("stop", t("Stop"), "", lambda: self._stops(row), variant="error")
            )
        return acts

    def _folder_menu(self, path: str, group: Group | None = None) -> None:
        """What a folder offers: a new chat or epic in it, Search in it, forgetting it."""
        # A folder that is gone is one nothing is started in.
        there = group is None or not group.missing
        acts = [
            Action(
                "chat",
                t("New chat here"),
                "",
                lambda: self._host.run_worker(self.action_new_chat(path)),
                lambda: there,
            ),
            Action(
                "epic",
                t("New epic here"),
                "",
                lambda: self._host.run_worker(self.action_new_epic(path)),
                lambda: there,
            ),
            Action("search", t("Search here"), "", lambda: self._searches(path)),
            Action(
                "copy",
                t("Copy path"),
                path,
                lambda: self._copies(path, t("Path copied")),
            ),
        ]
        if group is not None:
            shut = self.kept.has("shut", group.key)
            acts.append(
                Action(
                    "fold",
                    t("Expand") if shut else t("Collapse"),
                    "",
                    lambda: self._folds(group.key),
                )
            )
            # Only one that holds nothing: what ran in a folder is not forgotten with it.
            acts.append(
                Action(
                    "forget",
                    t("Forget"),
                    "",
                    lambda: self._forgets(path),
                    lambda: group.empty,
                    variant="error",
                )
            )
        self._menu(path, acts)

    # -- What a menu does ----------------------------------------------------------------

    def _copies(self, what: str, said: str) -> None:
        _rows.interface(self._host).copied(what)
        self._says(said)

    async def _asking(self, method: str, **params: Any) -> dict[str, Any] | None:
        """Asks the daemon off the screen's thread; None, having said why, where refused."""
        try:
            return await asyncio.to_thread(self._asks, method, **params)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._says(str(why), "$error")
            return None

    @work
    async def _searches(self, path: str) -> None:
        from .search import searches

        await searches(self._host, path)

    @work
    async def _renames(self, row: Row) -> None:
        """Asks what the chat is to be called, and renames it."""
        title = await self._host.push_screen_wait(Renames(row.title))
        if title and await self._asking("chat.rename", chat=row.name, title=title):
            self._says(t("Renamed"))
            self.reads()

    @work
    async def _forks(self, row: Row) -> None:
        """Forks the chat, and goes on in the fork."""
        made = await self._asking("chat.fork", chat=row.name)
        if made is not None:
            to = _rows.interface(self._host)
            to.opens_chat(str(made.get("chat") or ""), "")
            to.shell.home()
            self.reads()

    @work
    async def _archives(self, row: Row) -> None:
        """Archives the chat, which leaves the list."""
        if await self._asking("chat.archive", chat=row.name) is not None:
            self._says(t("Archived"))
            self.reads()

    @work
    async def _deletes(self, row: Row) -> None:
        """Asks whether the chat is to go for good, and deletes it on a yes."""
        sure = await self._host.push_screen_wait(Deletes(row.title))
        if (
            sure == "yes"
            and await self._asking("chat.delete", chat=row.name) is not None
        ):
            self._says(t("Deleted"))
            self.reads()

    @work
    async def _uploads(self, row: Row) -> None:
        """Queues a backup of the chat or the epic, which is not waited on."""
        self._says(t("Uploading…"))
        said = (
            await self._asking("chat.backup", chat=row.name)
            if row.kind == CHAT
            else await self._asking("runs.backup", name=row.name)
        )
        if said is not None:
            queued = ", ".join(str(one) for one in said.get("queued") or ())
            self._says(t("Uploading to {targets}", targets=queued))

    @work
    async def _stops(self, row: Row) -> None:
        """Stops the epic a host goes with."""
        self._says(t("Stopping…"))
        stopped = await self._asking(_rows.STOP, workspace=row.workspace, slot=row.slot)
        if stopped is not None:
            self._says(t("Stopping"))
            self.reads()

    @work
    async def _forgets(self, path: str) -> None:
        """Asks whether a folder nothing ran in is to be forgotten, and forgets it on a yes."""
        sure = await self._host.push_screen_wait(Forgets(_rows.folder_name(path)))
        if sure != "yes":
            return
        self._says(t("Forgetting…"))
        if await self._asking("workspaces.forget", workspace=path) is not None:
            self._says(t("Forgotten"))
            self.reads()


def told(app: App[Any], notice: Mapping[str, Any], *, unread: bool) -> None:
    """Takes a notice the interface heard: its chat or epic is unread, and the list read again.

    Args:
      app: The interface.
      notice: The notice, as the interface heard it: its `epic` or its `chat`.
      unread: Whether it is news: not the one on the log.
    """
    name = str(notice.get("epic") or notice.get("chat") or "")
    # Never the one on the log, whatever it was told of.
    unread = unread and name != _rows.interface(app).showing()
    # On the log's own screen, whatever sheet or page is over it.
    listed = list(app.screen_stack[0].query(Navigator))
    for listing in listed:
        listing.hears(name, unread=unread)
    if not listed and name and unread:
        Kept().marks("unread", name, on=True)


def _made(app: App[None]) -> Navigator:
    starting = app not in _MADE
    _MADE.add(app)
    return Navigator(starting=starting)


VIEWS = (
    View(
        "navigator",
        "navigator",
        "Sidebar",
        _made,
        key="ctrl+b",
        hint="Sidebar",
        opens=True,
        keys=(
            ("↑↓", "Move"),
            ("enter", "Open"),
            ("n", "New chat"),
            ("shift+n", "New epic"),
            ("p", "Pin"),
            ("u", "Unread"),
            (".", "Actions"),
            ("g", "Group by"),
        ),
    ),
)
