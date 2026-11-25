"""Search: finding a chat or an epic, by what was said in it, its kind, and how it went.

What the page's Search is (Section 3.10 of web.md), as a page of the terminal interface:
one field at its top, under it the tabs -- everything, the chats, the epics -- and the
filters by how it went, by folder and by flow, then what was found, newest first, a line
apiece. The keys stay in the field: what is typed narrows the list as it is typed, the
arrows move along what was found, enter opens the one moved to and esc closes.

Asked of this machine's daemon as the page asks it: the chats of `chat.list` and the epics
of `runs.list`, each with what was typed as `q`, and on `All` both, as one list.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast
from weakref import WeakKeyDictionary

from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.content import Content
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from hmz.tui import humanfia
from hmz.tui.shell import Hints, View
from hmz.words import t

from . import _rows
from ._rows import CHAT, EPIC, Asks, Row

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from textual import events
    from textual.app import App, ComposeResult
    from textual.timer import Timer

__all__ = ["TABS", "VIEWS", "Chosen", "Search", "asked", "searches"]

#: The kinds Search lists, as its tabs name them, in their order: a chat is never an epic.
TABS: Final = (("", "All"), (CHAT, "Chats"), (EPIC, "Epics"))

#: How a run can have ended, in the order the filter steps through them; "" is any.
_ENDINGS: Final = ("", "running", "done", "failed", "stopped", "unfinished")
_ENDED: Final = {
    "": "All",
    "running": "Running",
    "done": "Done",
    "failed": "Failed",
    "stopped": "Stopped",
    "unfinished": "Unfinished",
}

#: How many rows a page of the list holds, and the most a daemon answers at once.
PAGE: Final = 50
_MOST: Final = 200

#: How long nothing is typed for before the daemon is asked, in seconds.
_SETTLES: Final = 0.2


@dataclass(frozen=True)
class Chosen:
    """What is searched for: the tab, what was typed, and the filters under the tabs."""

    kind: str = ""
    q: str = ""
    status: str = ""
    flow: str = ""
    workspace: str = ""
    offset: int = 0


def asked(chosen: Chosen) -> list[tuple[str, dict[str, Any]]]:
    """What the daemon is asked for one page of what is chosen: each a method and what it takes.

    The chats of `chat.list`, the epics of `runs.list`, and on `All` both -- from the first
    of each as far as the page shown, which is then cut out of the two as one list. A chat
    is of no flow and is not filtered by how it went: with either chosen on `All`, only
    epics are asked for.
    """
    said: dict[str, Any] = {}
    if chosen.workspace:
        said["workspace"] = chosen.workspace
    if chosen.q:
        said["q"] = chosen.q
    epics = dict(said)
    if chosen.status:
        epics["status"] = chosen.status
    if chosen.flow:
        epics["flow"] = chosen.flow
    page = {"offset": chosen.offset, "limit": PAGE}
    if chosen.kind == CHAT:
        return [("chat.list", {**said, **page})]
    if chosen.kind == EPIC or chosen.status or chosen.flow:
        return [("runs.list", {**epics, **page})]
    both = {"offset": 0, "limit": min(_MOST, chosen.offset + PAGE)}
    return [("chat.list", {**said, **both}), ("runs.list", {**epics, **both})]


@dataclass(frozen=True)
class _Found:
    """What was found: one page of rows, how many there are in all, and the flows there are."""

    rows: tuple[Row, ...] = ()
    total: int = 0
    flows: tuple[str, ...] = ()
    folders: tuple[str, ...] = ()


def _found(chosen: Chosen, answers: Sequence[Mapping[str, Any]]) -> _Found:
    """What each call answered, as one list, newest first, the page chosen cut out of it."""
    rows: list[Row] = []
    flows: tuple[str, ...] = ()
    for one in answers:
        if "chats" in one:
            rows += [
                _rows.chat_row(chat)
                for chat in cast("list[Mapping[str, Any]]", one.get("chats") or [])
            ]
        else:
            rows += [
                _rows.epic_row(run)
                for run in cast("list[Mapping[str, Any]]", one.get("runs") or [])
            ]
            flows = tuple(str(flow) for flow in one.get("flows") or ())
    total = sum(int(one.get("total") or 0) for one in answers)
    if len(answers) > 1:
        rows.sort(key=lambda row: -_rows.stamp(row.began))
        rows = rows[chosen.offset : chosen.offset + PAGE]
    return _Found(tuple(rows), total, flows)


#: The folder the next Search of an interface opens in, where one was asked for.
_WITHIN: WeakKeyDictionary[App[Any], str] = WeakKeyDictionary()

_KEYS: Final = (
    ("↑↓", "Move"),
    ("enter", "Open"),
    ("tab", "Change type"),
    ("f2", "How it went"),
    ("f3", "Folder"),
    ("f4", "Flow"),
    ("f5", "Clear filters"),
    ("pgdn", "Older"),
    ("pgup", "Newer"),
)


class Search(Screen[None]):
    """The field, the tabs and filters under it, what was found, and the keys."""

    DEFAULT_CSS = """
    Search { background: $background; }
    Search > #search-title { height: 1; padding: 0 2; color: $primary; text-style: bold; }
    Search > .search-rule { height: 1; color: $hmz-line-strong; }
    Search > #search-field { height: 1; padding: 0 2; }
    Search #search-caret { width: 2; color: $primary; }
    Search Input, Search Input:focus { border: none; padding: 0; height: 1;
                                       background: $background; }
    Search > #search-tabs, Search > #search-filters { height: 1; padding: 0 2; }
    Search > #search-heading { height: 1; padding: 0 2; color: $text-muted;
                               text-style: bold; }
    Search > OptionList, Search > OptionList:focus { height: 1fr; border: none; padding: 0 2;
                          background: $background; }
    Search > OptionList > .option-list--option-highlighted {
        background: $primary; color: $background; text-style: bold; }
    Search > #search-paged { height: 1; padding: 0 2; color: $text-muted; }
    Search > Hints { dock: bottom; }
    """

    BINDINGS: ClassVar = [
        Binding("escape", "close", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("down", "move(1)", show=False),
        Binding("pageup", "page(-1)", show=False),
        Binding("pagedown", "page(1)", show=False),
        Binding("tab", "tab(1)", show=False),
        Binding("shift+tab", "tab(-1)", show=False),
        Binding("f2", "status", show=False),
        Binding("f3", "folder", show=False),
        Binding("f4", "flow", show=False),
        Binding("f5", "clear", show=False),
    ]

    def __init__(self, asks: Asks = _rows.local, workspace: str = "") -> None:
        """Opens Search, on everything or on one folder.

        Args:
          asks: What asks the daemon one thing.
          workspace: The folder it is opened in, or "" for every folder.
        """
        super().__init__()
        self._asks = asks
        self.chosen = Chosen(workspace=workspace)
        self._data = _Found()
        self._folders: tuple[str, ...] = ()
        self._shown: list[Row] = []
        self._picked = _rows.Picked()
        #: What the list on the screen was found by, or None before anything was.
        self._filled: Chosen | None = None
        self._settling: Timer | None = None

    @property
    def _host(self) -> App[None]:
        """The interface this is part of."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    def compose(self) -> ComposeResult:
        """The title over a rule, the field, the tabs, the filters, the list, the keys."""
        yield Static(t("Search").upper(), id="search-title")
        yield Static(classes="search-rule")
        with Horizontal(id="search-field"):
            yield Static(humanfia.POINT, id="search-caret")
            yield Input(placeholder=t("Search"), id="search-input")
        yield Static(id="search-tabs")
        yield Static(id="search-filters")
        yield Static(classes="search-rule")
        yield Static(id="search-heading")
        yield OptionList(id="search-found")
        yield Static(id="search-paged")
        yield Hints(id="search-hints")

    def on_mount(self) -> None:
        """Keeps the keys in the field, says what they do, and reads the newest of everything."""
        self.query_one(OptionList).can_focus = False
        self.query_one(Input).focus()
        self.query_one(Hints).says([*_KEYS, ("esc", "Close")])
        self._heads()
        self.query_one("#search-paged", Static).update(t("Reading the list…"))
        self._finds()

    def on_resize(self, event: events.Resize) -> None:
        """Rules across however wide the screen is now, and draws the rows to it."""
        for rule in self.query(".search-rule").results(Static):
            rule.update(humanfia.RULE * event.size.width)
        self._fills()

    @on(OptionList.OptionHighlighted)
    def _moved(self, _: OptionList.OptionHighlighted) -> None:
        """Draws the row the cursor came to as the one it is on."""
        self._picked.moves(self.query_one(OptionList))

    # -- Asking --------------------------------------------------------------------------

    def _chooses(self, chosen: Chosen) -> None:
        """Takes what is searched for now, and asks for it."""
        self.chosen = chosen
        self._heads()
        self._finds()

    @on(Input.Changed)
    def _typed(self, event: Input.Changed) -> None:
        """Narrows the list by what is typed, once nothing more has been for a moment."""
        self.chosen = replace(self.chosen, q=event.value.strip(), offset=0)
        self._heads()
        if self._settling is not None:
            self._settling.stop()
        self._settling = self.set_timer(_SETTLES, self._finds)

    @work(group="search", exclusive=True)
    async def _finds(self) -> None:
        """Asks the daemon for what is chosen, off the screen's thread, and puts it up."""
        chosen = self.chosen
        try:
            found = await asyncio.to_thread(self._asked, chosen, not self._folders)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            if chosen == self.chosen and self.is_attached:
                self.query_one("#search-paged", Static).update(Content(str(why)))
            return
        # Something else was chosen while it was asked: what it answered is nobody's.
        if chosen != self.chosen or not self.is_attached:
            return
        if found.folders:
            self._folders = found.folders
        self._data = found
        self._heads()
        self._fills()

    def _asked(self, chosen: Chosen, folders: bool) -> _Found:  # noqa: FBT001 -- whether to
        answers = [self._asks(method, **params) for method, params in asked(chosen)]
        found = _found(chosen, answers)
        if not folders:
            return found
        listed = cast(
            "list[Mapping[str, Any]]",
            self._asks("workspaces.list").get("workspaces") or [],
        )
        paths = tuple(str(one.get("path") or "") for one in listed if one.get("path"))
        return replace(found, folders=paths)

    # -- Drawing -------------------------------------------------------------------------

    def _heads(self) -> None:
        """Draws the tabs and the filters as they are chosen: the one chosen is cyan."""
        chosen = self.chosen
        tabs = Content("   ").join(
            Content.styled(f"{humanfia.SQUARE} {t(name).upper()}", "bold $primary")
            if kind == chosen.kind
            else Content.styled(f"  {t(name).upper()}", "$text-muted")
            for kind, name in TABS
        )
        self.query_one("#search-tabs", Static).update(tabs)

        def one(label: str, value: str, *, chosen_: bool) -> Content:
            return Content.assemble(
                (t(label), "$text-muted"),
                " ",
                (value, "$primary" if chosen_ else "$foreground"),
            )

        went = t(_ENDED[chosen.status]) if chosen.status in _ENDED else chosen.status
        folder = (
            _rows.folder_name(chosen.workspace)
            if chosen.workspace
            else t("All folders")
        )
        self.query_one("#search-filters", Static).update(
            Content("   ").join(
                (
                    one("How it went", went, chosen_=bool(chosen.status)),
                    one("Folder", folder, chosen_=bool(chosen.workspace)),
                    one(
                        "Flow",
                        chosen.flow or t("All flows"),
                        chosen_=bool(chosen.flow),
                    ),
                )
            )
        )
        narrowed = chosen.kind or chosen.q or self._filtered()
        self.query_one("#search-heading", Static).update(
            (t("Results") if narrowed else t("Recents")).upper()
        )

    def _filtered(self) -> bool:
        chosen = self.chosen
        return bool(chosen.status or chosen.flow or chosen.workspace)

    def _nothing(self) -> str:
        """What is said where nothing was found: nothing like that, or none of the kind yet."""
        chosen = self.chosen
        if chosen.q or self._filtered():
            return t("Nothing is like that.") + t(
                " Clear the filters to see every chat and epic."
            )
        if chosen.kind == CHAT:
            return t("No chats yet.") + t(
                " Start a chat, and it is written down here as it goes."
            )
        if chosen.kind == EPIC:
            return t("No epics yet.") + t(
                " Start an epic, and it is written down here as it goes."
            )
        return t("Nothing here yet.") + t(
            " Start a chat or an epic, and it is written down here as it goes."
        )

    def _fills(self) -> None:
        """Puts what was found up, the cursor on its first row."""
        if not self.is_attached:
            return
        listing = self.query_one(OptionList)
        data, chosen = self._data, self.chosen
        room, now = max(listing.size.width - 4, 20), time.time()
        current = _rows.interface(self._host).showing()
        was = listing.highlighted
        self._shown = list(data.rows)
        lines = [
            (
                f"r:{row.name}",
                _rows.drawn(
                    row,
                    room,
                    now,
                    current=row.name == current,
                    about=" · ".join(
                        one
                        for one in (
                            ""
                            if chosen.workspace or row.folderless
                            else _rows.folder_name(row.workspace),
                            row.flow.rsplit("/", 1)[-1],
                        )
                        if one
                    ),
                ),
            )
            for row in data.rows
        ]
        if lines:
            self._picked.fills(listing, lines)
        else:
            nothing = Content.styled(self._nothing(), "$text-muted")
            self._picked.fills(listing, [])
            listing.set_options([Option(nothing, disabled=True)])
        if data.rows:
            # Where it was, only where the same list is drawn again; else its first row.
            at = (was or 0) if chosen == self._filled else 0
            listing.highlighted = min(at, len(data.rows) - 1)
        self._filled = chosen
        self._picked.moves(listing)
        self.query_one("#search-paged", Static).update(
            t(
                "{from}–{to} of {total}",  # noqa: RUF001 -- the page's own
                **{
                    "from": chosen.offset + 1,
                    "to": chosen.offset + len(data.rows),
                    "total": data.total,
                },
            )
            if data.total
            else ""
        )

    # -- Keys ----------------------------------------------------------------------------

    def action_close(self) -> None:
        """Closes Search: one step back, to what was under it."""
        self._host.pop_screen()

    def action_move(self, by: int) -> None:
        """Moves along what was found, round the ends."""
        listing = self.query_one(OptionList)
        if self._shown:
            at = listing.highlighted
            listing.highlighted = (
                (0 if by > 0 else len(self._shown) - 1)
                if at is None
                else (at + by) % len(self._shown)
            )

    def action_page(self, by: int) -> None:
        """Turns to an older page of what was found, or a newer one."""
        offset = self.chosen.offset + by * PAGE
        # On `All` the two lists are read from their first row, as far as a daemon answers
        # at once: no page past that is whole, so none is turned to.
        both = len(asked(self.chosen)) > 1
        if both and offset + PAGE > _MOST:
            return
        if 0 <= offset < max(self._data.total, 1) and offset != self.chosen.offset:
            self._chooses(replace(self.chosen, offset=offset))

    def action_tab(self, by: int) -> None:
        """Changes the tab, which stops at either end; `Chats` drops what no chat is found by."""
        kinds = [kind for kind, _ in TABS]
        kind = kinds[min(len(kinds) - 1, max(0, kinds.index(self.chosen.kind) + by))]
        if kind == self.chosen.kind:
            return
        self._chooses(
            replace(
                self.chosen,
                kind=kind,
                flow="" if kind == CHAT else self.chosen.flow,
                status="" if kind == CHAT else self.chosen.status,
                offset=0,
            )
        )

    def _epics(self) -> str:
        """The tab once an epic's filter is set: a flow's are epics, so `Chats` gives way."""
        return EPIC if self.chosen.kind == CHAT else self.chosen.kind

    def action_status(self) -> None:
        """Filters by how it went, the next way."""
        at = _ENDINGS.index(self.chosen.status) if self.chosen.status in _ENDINGS else 0
        status = _ENDINGS[(at + 1) % len(_ENDINGS)]
        kind = self._epics() if status else self.chosen.kind
        self._chooses(replace(self.chosen, status=status, kind=kind, offset=0))

    def action_folder(self) -> None:
        """Filters by folder, the next one; after the last, every folder again."""
        folders = ["", *self._folders]
        if self.chosen.workspace not in folders:
            folders.append(self.chosen.workspace)
        at = folders.index(self.chosen.workspace)
        self._chooses(
            replace(self.chosen, workspace=folders[(at + 1) % len(folders)], offset=0)
        )

    def action_flow(self) -> None:
        """Filters by flow, the next one; after the last, every flow again."""
        flows = ["", *self._data.flows]
        if self.chosen.flow not in flows:
            flows.append(self.chosen.flow)
        flow = flows[(flows.index(self.chosen.flow) + 1) % len(flows)]
        kind = self._epics() if flow else self.chosen.kind
        self._chooses(replace(self.chosen, flow=flow, kind=kind, offset=0))

    def action_clear(self) -> None:
        """Clears what was typed and filtered for: the tab stays, which is no filter."""
        self.query_one(Input).value = ""
        self._chooses(Chosen(kind=self.chosen.kind))

    @on(Input.Submitted)
    def _opens(self, _: Input.Submitted) -> None:
        """Enter: closes Search, and opens the one moved to in the log."""
        at = self.query_one(OptionList).highlighted
        if at is None or not 0 <= at < len(self._shown):
            return
        app, row = self._host, self._shown[at]
        app.pop_screen()
        app.run_worker(_goes(app, row, self._asks))


async def _goes(app: App[Any], row: Row, asks: Asks) -> None:
    """Opens one row found, and gives the prompt the keys to go on in it."""
    if await _rows.opens(app, row, asks):
        _rows.interface(app).shell.home()


async def searches(app: App[Any], workspace: str = "") -> None:
    """Opens Search in one folder: what `Search here` does.

    Args:
      app: The interface.
      workspace: The folder, or "" for every folder.
    """
    _WITHIN[app] = workspace
    await _rows.interface(app).shell.opens("search")


def _made(app: App[None]) -> Search:
    return Search(workspace=_WITHIN.pop(app, ""))


VIEWS = (
    View("search", "page", "Search", _made, key="ctrl+k", hint="Search", keys=_KEYS),
)
