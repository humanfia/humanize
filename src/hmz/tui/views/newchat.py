"""New chat: the first message, the chips it starts with, and what waits on its person.

The web page's New chat page (`views/newchat.js`, Section 3.8.18 of [WEB]) as a page of the
terminal interface. A new chat takes one decision -- type and press enter -- so the page
opens on the box the first message is typed into, and over it the chips say what will apply
without being opened: the folder the chat is of, where it works, the model that answers it
and its effort, and what it may touch. A chip is opened only to change it. Under the box are
the chats of this directory that wait on their person, first, then the sessions its harnesses
had of their own, each opened by its row.

The one pink thing on the page is the start action.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, cast
from weakref import WeakKeyDictionary

from rich.markup import escape
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal
from textual.geometry import Offset
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from hmz.tui import humanfia
from hmz.tui.shell import Hints, View
from hmz.words import t

from . import harness
from .chips import (
    DEFAULT,
    Desk,
    Heading,
    Place,
    Start,
    desk,
    effort_name,
    effort_picked,
    env_said,
    folder_picked,
    harness_name,
    mode_of,
    mode_picked,
    nous_picked,
    parted,
    place_picked,
    spelled,
)

if TYPE_CHECKING:
    from textual import events
    from textual.app import App, ComposeResult

__all__ = ["VIEWS", "Chip", "NewChat", "opens"]

#: How often what waits is read again, in seconds: as often as the page reads it.
_EVERY: Final = 4.0
_FOLDER, _ENV, _MODEL, _EFFORT, _PERMISSION = (
    "folder",
    "environment",
    "model",
    "effort",
    "permission",
)

#: What marks, in the list, a chat and a session a harness had of its own.
_CHAT, _SESSION = "chat ", "session "


class Chip(Static, can_focus=True):
    """One chip: what it is of, in capitals, then the value that will apply.

    A flat plane, cyan while it has the keys. Enter, or a click, opens the list its value is
    picked out of.
    """

    DEFAULT_CSS = """
    Chip { width: auto; height: 1; padding: 0 1; margin: 0 1 0 0;
           background: $panel; color: $foreground; }
    Chip:focus { background: $primary; color: $background; text-style: bold; }
    """

    class Pressed(Message):
        """Says a chip was opened."""

        def __init__(self, chip: Chip) -> None:
            """Holds the chip.

            Args:
              chip: It.
            """
            super().__init__()
            self.chip = chip

    def __init__(self, name: str, label: str) -> None:
        """Makes a chip saying nothing yet.

        Args:
          name: What it is found by.
          label: What it is of, already in the language spoken.
        """
        super().__init__(id=name)
        self._label = label

    def says(self, value: str) -> None:
        """Says the value that will apply."""
        self.update(f"[b]{escape(self._label.upper())}[/] {escape(value)}")

    def on_key(self, event: events.Key) -> None:
        """Opens on enter."""
        if event.key == "enter":
            event.stop()
            self.post_message(self.Pressed(self))

    def on_click(self) -> None:
        """Opens on a click."""
        self.post_message(self.Pressed(self))


class NewChat(Screen[None]):
    """The New chat page: chips, the first message, and what waits on its person."""

    DEFAULT_CSS = """
    NewChat { background: $background; }
    NewChat #chips { height: auto; padding: 1 1 0 1; }
    NewChat #chips.-stacked { layout: vertical; }
    NewChat #chips.-stacked > Chip { margin: 0; }
    NewChat .rule { height: 1; color: $hmz-line-strong; }
    NewChat #start { height: 1; padding: 0 1; }
    NewChat #caret { width: 2; color: $primary; }
    NewChat #message { width: 1fr; height: 1; border: none; padding: 0;
                       background: $background; }
    NewChat #go { width: auto; padding: 0 0 0 2; color: $accent; text-style: bold; }
    NewChat #said { height: auto; padding: 0 1; color: $text-muted; }
    NewChat #waiting, NewChat #waiting:focus {
        height: 1fr; margin: 1 0 0 0; border: none; padding: 0;
        background: $background; background-tint: transparent;
    }
    NewChat #waiting > .option-list--option { padding: 0 1; }
    NewChat #waiting.-none { display: none; }
    NewChat Hints { dock: bottom; }
    """

    BINDINGS: ClassVar = [Binding("escape", "back", "Back", show=False)]

    #: The keys it takes, as the hint line says them.
    KEYS: ClassVar = (
        ("tab", "Next"),
        ("shift+tab", "Previous"),
        ("enter", "Start"),
        ("enter", "Choose"),
        ("enter", "Open"),
    )

    def __init__(self, at: Desk, *, folder: str = "") -> None:
        """Opens on a new chat of a folder.

        Args:
          at: The interface it is opened in.
          folder: The folder the chat is to be of, or "" for the directory the interface
            was opened in.
        """
        super().__init__()
        self._desk = at
        self._folder = folder or at.workspace
        self._place = Place()
        self._agent = ""
        self._permission = DEFAULT
        #: Whether the sessions each harness had of its own are listed, as the setting says.
        self._harnessed = True
        self._chats: list[dict[str, Any]] = []
        self._sessions: list[dict[str, Any]] = []
        self._starting = False
        #: Whether what the folder remembers has been read once.
        self._loaded = False
        #: Whether a listing is on its way, which the next one waits for.
        self._listing = False

    def compose(self) -> ComposeResult:
        """The heading; the chips; the box; what was said of it; what waits; the keys."""
        yield Heading(t("New chat"))
        with Horizontal(id="chips"):
            yield Chip(_FOLDER, t("Folder"))
            yield Chip(_ENV, t("Environment"))
            yield Chip(_MODEL, t("Model"))
            yield Chip(_EFFORT, t("Effort"))
            yield Chip(_PERMISSION, t("Permissions"))
        yield Static(classes="rule")
        with Horizontal(id="start"):
            yield Static(humanfia.BAR, id="caret")
            yield Input(placeholder=t("Message"), id="message")
            yield Static(f"{humanfia.SQUARE} {t('Start')}", id="go")
        yield Static(classes="rule")
        yield Static(id="said")
        yield OptionList(id="waiting", classes="-none")
        yield Hints()

    def on_mount(self) -> None:
        """Opens on the box, says the defaults, and reads what the folder remembers."""
        self.query_one("#message", Input).focus()
        self._draws()
        self._loads()
        self.set_interval(_EVERY, self._ticked)

    def _ticked(self) -> None:
        """Lists again, unless the last listing is still on its way."""
        if not self._listing:
            self._lists()

    def on_resize(self, event: events.Resize) -> None:
        """Rules the page across, and stacks the chips where a row of them would not fit."""
        for rule in self.query(".rule").results(Static):
            rule.update(humanfia.RULE * event.size.width)
        self._lays()

    def on_descendant_focus(self) -> None:
        """Has the hint line say the keys of what has them now."""
        self._hints()

    def _hints(self) -> None:
        held = self.focused
        enter = (
            "Choose"
            if isinstance(held, Chip)
            else "Open"
            if isinstance(held, OptionList)
            else "Start"
        )
        self.query_one(Hints).says(
            [
                ("tab", "Next"),
                ("shift+tab", "Previous"),
                ("enter", enter),
                ("esc", "Back"),
            ]
        )

    def _draws(self) -> None:
        """Has every chip say what will apply."""
        nous = parted(self._agent)

        def chip(name: str) -> Chip:
            return self.query_one(f"#{name}", Chip)

        chip(_FOLDER).says(_named(self._folder))
        chip(_ENV).says(env_said(self._place.env, worktree=self._place.worktree))
        chip(_MODEL).says(
            f"{harness_name(nous.cli)} {nous.model}" if nous.model else t("Pick a nous")
        )
        chip(_EFFORT).says(effort_name(nous.effort))
        chip(_PERMISSION).says(t(mode_of(self._permission).label))
        self.call_after_refresh(self._lays)

    def _lays(self) -> None:
        """Stacks the chips where a row of them would not fit the page."""
        row = self.query_one("#chips")
        asked = sum(len(str(one.render())) + 3 for one in row.query(Chip))
        row.set_class(asked + 2 > self.size.width, "-stacked")

    def _says(self, said: str = "", *, bad: bool = False) -> None:
        """Says one line under the box, in red where it is a failure."""
        self.query_one("#said", Static).update(
            f"[$error]{escape(said)}[/]" if bad else escape(said)
        )

    @work(group="newchat-loads", exclusive=True)
    async def _loads(self) -> None:
        """Reads the chat agent the folder remembers, else the first model there is."""
        asks, folder = self._desk.asks, self._folder
        agent = ""
        try:
            kept = await asyncio.to_thread(asks, "settings.get", workspace=folder)
            agent = str(kept.get("chat") or "")
            if not self._loaded:
                # The setting of the directory the interface was opened in, whose
                # sessions are the ones listed.
                self._harnessed = kept.get("harness_sessions") is not False
            if not agent:
                clis = (await asyncio.to_thread(asks, "flows.backends")).get("clis")
                agent = _first(cast("dict[str, Any]", clis or {}))
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._says(str(why), bad=True)
        if folder == self._folder and not self._agent:
            self._agent = agent
            self._draws()
        if not self._loaded:
            # Listed once the setting is known, which says whether harness sessions are.
            self._loaded = True
            self._lists()

    @work(group="newchat-lists", exclusive=True)
    async def _lists(self) -> None:
        """Reads the chats that wait on their person, and the harnesses' own sessions."""
        asks, here = self._desk.asks, self._desk.workspace
        if not self._loaded:
            return
        self._listing = True
        try:
            chats = await asyncio.to_thread(
                asks, "chat.list", workspace=here, limit=200
            )
            sessions: dict[str, Any] = {}
            if self._harnessed:
                sessions = await asyncio.to_thread(
                    asks, "chat.harness.list", workspace=here, limit=50
                )
        except Exception:  # noqa: BLE001 -- unread, the list stays as it was
            return
        finally:
            self._listing = False
        self._chats = [
            one
            for one in cast("list[dict[str, Any]]", chats.get("chats") or [])
            if one.get("state") == "asking" or one.get("asking")
        ]
        self._sessions = cast("list[dict[str, Any]]", sessions.get("sessions") or [])
        self._fills()

    def _fills(self) -> None:
        """Lists what waits, first, then the harness sessions, the cursor kept where it was."""
        listing = self.query_one("#waiting", OptionList)
        rows: list[Option] = []
        if self._chats:
            rows.append(_head(t("Waiting for you")))
            rows += [
                Option(
                    f"[$warning]{humanfia.POINT}[/] {escape(_titled(one))}  "
                    f"[$text-muted]{t('Asked a question')}[/]",
                    id=f"{_CHAT}{one.get('id')} {one.get('slot') or ''}",
                )
                for one in self._chats
            ]
        if self._sessions:
            rows.append(_head(t("Harness sessions")))
            rows += [
                Option(
                    f"  {escape(_titled(one))}  [$text-muted]"
                    + t("{harness} session", harness=harness_name(str(one["harness"])))
                    + "[/]",
                    id=f"{_SESSION}{one.get('harness')} {one.get('id')}",
                )
                for one in self._sessions
            ]
        ids = [one.id for one in rows]
        if ids == [one.id for one in listing.options]:
            return
        at = listing.highlighted
        was = listing.get_option_at_index(at).id if at is not None else None
        listing.clear_options()
        listing.add_options(rows)
        first = next((n for n, one in enumerate(rows) if not one.disabled), None)
        listing.highlighted = ids.index(was) if was and was in ids else first
        listing.set_class(not rows, "-none")
        if not rows and self.focused is listing:
            self.query_one("#message", Input).focus()

    def on_chip_pressed(self, event: Chip.Pressed) -> None:
        """Opens the list a chip's value is picked out of."""
        event.stop()
        self._picks(event.chip)

    @work(group="newchat-picks", exclusive=True)
    async def _picks(self, chip: Chip) -> None:
        """Changes one chip, and says the value picked."""
        app = cast("App[None]", self.app)  # pyright: ignore[reportUnknownMemberType]
        asks, at = self._desk.asks, Offset(chip.region.x, chip.region.y)
        self._says()
        try:
            if chip.id == _FOLDER:
                folder = await folder_picked(app, asks, self._folder, at=at)
                if folder and folder != self._folder:
                    # Another folder, another place to work in and another agent remembered.
                    self._folder, self._place, self._agent = folder, Place(), ""
                    self._loads()
            elif chip.id == _ENV:
                place = await place_picked(app, asks, self._folder, self._place, at=at)
                self._place = place or self._place
            elif chip.id == _MODEL:
                self._agent = (
                    await nous_picked(app, asks, self._agent, at=at) or self._agent
                )
            elif chip.id == _EFFORT and self._agent:
                self._agent = (
                    await effort_picked(app, asks, self._agent, at=at) or self._agent
                )
            elif chip.id == _PERMISSION:
                self._permission = (
                    await mode_picked(app, self._permission, at=at) or self._permission
                )
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._says(str(why), bad=True)
        self._draws()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Starts the chat on what was typed, with what the chips say."""
        event.stop()
        task = event.value.strip()
        if not task or self._starting:
            return
        if not spelled(parted(self._agent)):
            self._says(t("Pick a nous for the chat."), bad=True)
            self._picks(self.query_one(f"#{_MODEL}", Chip))
            return
        start = Start(
            task, self._agent, self._permission, self._place.env, self._place.worktree
        )
        if _same(self._folder, self._desk.workspace):
            # Through the interface, which goes to the chat's host and reads it from there.
            self._desk.starts(start)
            self.dismiss()
            return
        self._starts_there(start)

    @work(group="newchat-starts", exclusive=True)
    async def _starts_there(self, start: Start) -> None:
        """Starts a chat of another folder, which is read from an interface opened there."""
        self._starting = True
        self.query_one("#go", Static).update(t("Starting…"))
        try:
            await asyncio.to_thread(
                self._desk.asks,
                "chat.start",
                workspace=self._folder,
                agent=start.agent,
                task=start.task,
                permission=start.permission,
                worktree=start.worktree,
                env=start.env or None,
                remember=True,
            )
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._starting = False
            self.query_one("#go", Static).update(f"{humanfia.SQUARE} {t('Start')}")
            self._says(str(why), bad=True)
            return
        self._desk.says(
            t(
                "The chat was started in {folder}. Open hmz in that folder to read it.",
                folder=_homed(self._folder),
            )
        )
        self.dismiss()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Opens the chat or the harness session picked."""
        event.stop()
        picked = str(event.option.id or "")
        if picked.startswith(_CHAT):
            name, _, slot = picked.removeprefix(_CHAT).partition(" ")
            self._desk.follows(name, slot)
            self.dismiss()
        elif picked.startswith(_SESSION):
            named, _, session = picked.removeprefix(_SESSION).partition(" ")
            self._reads(named, session)

    @work(group="newchat-reads", exclusive=True)
    async def _reads(self, named: str, session: str) -> None:
        """Reads one harness session, and leaves with it where it is continued in a chat."""
        app = cast("App[None]", self.app)  # pyright: ignore[reportUnknownMemberType]
        chat = await app.push_screen_wait(
            harness.Session(self._desk, self._desk.workspace, named, session)
        )
        if chat:
            self.dismiss()

    def action_back(self) -> None:
        """Closes the page: one step back, to what was under it."""
        if not self._starting:  # a chat being started is waited for, and then it closes
            self.dismiss()


def _head(text: str) -> Option:
    """The heading of a group of the list, which the cursor passes over."""
    return Option(
        f"[b $text-muted]{humanfia.SQUARE} {escape(text.upper())}[/]", disabled=True
    )


def _titled(one: dict[str, Any]) -> str:
    """What a chat or a session is called on its row: its title on one line, or its id."""
    return " ".join(str(one.get("title") or "").split()) or str(one.get("id") or "")


def _named(path: str) -> str:
    """A folder as its chip names it: its own name, as the page's chip does."""
    return path.rstrip("/").rpartition("/")[2] or path


def _homed(path: str) -> str:
    """A path with the home directory written as `~`, as every shell shortens it."""
    home = str(Path.home())
    return (
        f"~{path[len(home) :]}" if path == home or path.startswith(f"{home}/") else path
    )


def _same(one: str, other: str) -> bool:
    """Whether two paths name one directory."""
    try:
        return Path(one).resolve() == Path(other).resolve()
    except OSError:
        return one == other


def _first(clis: dict[str, Any]) -> str:
    """The first model any harness here lists, as an agent spec, or "" for none."""
    for cli, held in clis.items():
        for account in held.get("accounts") or ():
            for model in account.get("models") or ():
                whose = f"{cli}@{account['name']}" if account.get("name") else cli
                return f"{whose}/{model['name']}:auto"
    return ""


#: The folder each interface's page is to open on the next time it is made.
_ON: WeakKeyDictionary[App[Any], str] = WeakKeyDictionary()


async def opens(app: App[Any], *, folder: str = "") -> None:
    """Opens the New chat page of an interface on a folder.

    Args:
      app: The interface, which has the shell the page is opened by.
      folder: The folder the chat is to be of, or "" for the one the interface is open in.
    """
    if folder:
        _ON[app] = folder
    await cast("Any", app).shell.opens("newchat")


def _made(app: App[None]) -> Screen[None]:
    return NewChat(desk(app), folder=_ON.pop(app, ""))


VIEWS = (
    View(
        "newchat",
        "page",
        "New chat",
        _made,
        key="ctrl+n",
        hint="New chat",
        keys=NewChat.KEYS,
    ),
)
