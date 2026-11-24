"""Download, Import and Export: an epic brought here, read back in, or written out as a file.

Three pages, each a way an epic crosses a machine's edge. **Download** lists what a backup
target holds and brings one epic or chat here; **Import** reads a `.hmzepic` somebody exported
back in; **Export** writes a recorded epic out as one. What lists and lands a download is the
Download sheet's own (:mod:`hmz.tui.stored`), and the two forms that ask for a path are
`/epics`'s (:class:`hmz.tui.pick.ImportingEpic`, :class:`hmz.tui.pick.Exporting`), so a path
is finished as it is typed here as it is there.

A transfer is the interface's rather than the page's: it is started off the event loop on
the interface itself, so `esc` leaves the page and the bytes go on moving, and any of the
three pages opened again shows it where it stands -- still going, with how long it has taken,
or what came of it. What came of it is said in the transcript too.
"""

# The rows are drawn with the pieces every list of epics is drawn with, which are `pick`'s.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, ClassVar, cast
from weakref import WeakKeyDictionary

from rich.markup import escape
from textual import on, work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from hmz.tui import humanfia, stored
from hmz.tui.pick import (
    Exporting,
    ImportingEpic,
    _asked_for,
    _homed,
    _when,
    chatting,
    exported,
)
from hmz.tui.shell import Hints, View
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from textual import events
    from textual.app import App, ComposeResult

    from hmz.runtime.epic import Ran

__all__ = ["VIEWS", "Download", "Export", "Import", "Moving", "moves", "moving"]

#: How many transfers a page shows, the newest first.
_SHOWN = 6

#: How wide the bar of a transfer still going is, and the plane that crosses it.
_BAR, _PLANE = 24, 6

#: How often a page draws its transfers again while it is open, in seconds.
_TICK = 0.2


@dataclass
class Moving:
    """One transfer: what it is, when it began, and what came of it once it ended."""

    kind: str
    """Which page started it: `download`, `import` or `export`."""
    doing: str
    """What is said of it while it goes."""
    began: float = field(default_factory=time.monotonic)
    """When it began, on the clock that only goes forward."""
    said: str = ""
    """What came of it, or why it failed; "" while it goes."""
    done: bool = False
    """Whether it has ended, either way."""
    failed: bool = False
    """Whether it ended by failing."""
    took: float = 0.0
    """How long it took, in seconds, once it ended."""


#: The transfers of each interface, oldest first: kept beside the interface rather than on
#: a page, since a page is left and opened again while one goes.
_MOVING: WeakKeyDictionary[App[None], list[Moving]] = WeakKeyDictionary()


def moving(app: App[None]) -> list[Moving]:
    """Every transfer an interface started, oldest first."""
    return _MOVING.setdefault(app, [])


def moves(
    app: App[None],
    kind: str,
    doing: str,
    how: Callable[[], str],
    then: Callable[[Moving], None] | None = None,
) -> Moving:
    """Starts one transfer off the event loop, on the interface rather than on a page.

    Args:
      app: The interface, which the transfer outlives every page of.
      kind: Which page started it.
      doing: What is said of it while it goes.
      how: What moves the bytes, answering with what to say once they have landed.
      then: What to do on the event loop once it has ended, either way.

    Returns:
      The transfer, which says where it stands whenever it is read.
    """
    one = Moving(kind, doing)
    moving(app).append(one)

    async def goes() -> None:
        from hmz.daemon import Hmz

        try:
            one.said = await asyncio.to_thread(how)
        except Exception as why:  # noqa: BLE001 -- whatever stopped it, it has stopped
            # Scrubbed, as everywhere git's own words are drawn: a target is added with a
            # token in its URL.
            one.said, one.failed = Hmz().verses.plain(str(why) or repr(why)), True
        one.took, one.done = time.monotonic() - one.began, True
        show = getattr(app, "show", None)
        if callable(show):
            show(f"[dim]{escape(one.said)}[/dim]", "red" if one.failed else "")
        if then is not None:
            then(one)

    app.run_worker(goes(), group="transfers", exit_on_error=False)
    return one


def _drawn(one: Moving) -> str:
    """One transfer as a line: a plane crossing a heavy rule while it goes, then what came."""
    if one.done:
        mark = humanfia.SQUARE
        if one.failed:
            return f"[$error]{mark} {escape(one.said)}[/]"
        return f"[$primary]{mark}[/] {escape(one.said)}"
    spent = time.monotonic() - one.began
    # There and back along the rule, so that it reads as moving rather than as filling:
    # nothing here knows how much there is to move.
    reach = _BAR - _PLANE
    at = int(spent / _TICK) % (2 * reach)
    at = at if at <= reach else 2 * reach - at
    bar = (
        f"[$hmz-line-strong]{humanfia.RULE * at}[/]"
        f"[$primary]{humanfia.BLOCK * _PLANE}[/]"
        f"[$hmz-line-strong]{humanfia.RULE * (reach - at)}[/]"
    )
    seconds = t("{n} s", n=int(spent))
    return f"[$primary]{humanfia.POINT}[/] {escape(one.doing)}  {bar}  {seconds}"


class Transfer(Screen[None]):
    """A page a transfer is started from, and every transfer the interface has is read on."""

    DEFAULT_CSS = """
    Transfer { background: $background; }
    Transfer > #title { height: 1; padding: 0 2; color: $primary; text-style: bold; }
    Transfer > #rule { height: 1; color: $primary; }
    Transfer > #about { height: auto; padding: 0 2; margin: 1 0 0 0; color: $text-muted; }
    Transfer > #rows { height: 1fr; margin: 1 0 0 0; padding: 0 1; border: none;
                       background: $background; }
    Transfer > #rows:focus { border: none; }
    Transfer > #space { height: 1fr; }
    Transfer > #said { height: auto; padding: 0 2; }
    Transfer > #moving { height: auto; padding: 0 2; margin: 1 0 0 0; }
    Transfer > #note { height: auto; padding: 0 2; color: $text-muted; }
    Transfer > Hints { padding: 0 2; }
    """

    #: What the page is headed, and which transfers are its own.
    TITLE_SAID: ClassVar[str] = ""
    KIND: ClassVar[str] = ""

    #: Whether the page lists anything to pick from.
    LISTS: ClassVar[bool] = True

    #: Every key any of the three takes; which a page takes is what :meth:`keys` says.
    BINDINGS: ClassVar = [
        Binding(key, f"key('{key}')", show=False)
        for key in ("escape", "enter", "f", "t")
    ]

    def __init__(self) -> None:
        """Holds nothing said yet."""
        super().__init__()
        self._said = ""
        #: The row drawn as the cursor's, by id.
        self._shaded = ""

    def compose(self) -> ComposeResult:
        """A title over a heavy rule, what the page is, its list, the transfers, the keys."""
        yield Static(t(self.TITLE_SAID).upper(), id="title")
        yield Static(id="rule")
        yield Static(id="about")
        if self.LISTS:
            yield OptionList(id="rows")
        else:
            yield Static(id="space")
        yield Static(id="said")
        yield Static(id="moving")
        yield Static(id="note")
        yield Hints()

    def on_mount(self) -> None:
        """Draws the page, and goes on drawing its transfers while it is open."""
        self._draws()
        self.set_interval(_TICK, self._ticks)
        if self.LISTS:
            self.query_one("#rows", OptionList).focus()

    def on_resize(self, event: events.Resize) -> None:
        """Rules the title across however wide the screen is now."""
        self.query_one("#rule", Static).update(humanfia.RULE * event.size.width)

    def _interface(self) -> App[None]:
        """The interface this page is drawn over."""
        return cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )

    def crumb(self) -> str:
        """What the page is called on the way across the top of a form opened over it."""
        return t(self.TITLE_SAID)

    def crumbs(self) -> list[str]:
        """Nothing: the page is one step."""
        return []

    def about(self) -> str:
        """What the page is for, in a line or two, as markup."""
        return ""

    def keys(self) -> Sequence[tuple[str, str]]:
        """The keys the page takes now, each with what it does, but for `esc`."""
        return ()

    def _draws(self) -> None:
        """Draws what the page is, what it last said, its transfers and its keys."""
        self.query_one("#about", Static).update(self.about())
        self.query_one("#said", Static).update(self._said)
        self.query_one(Hints).says([*self.keys(), ("esc", "Back")])
        self._ticks()

    def _ticks(self) -> None:
        """Draws every transfer where it stands now, the newest first."""
        held = moving(self._interface())
        self.query_one("#moving", Static).update(
            "\n".join(_drawn(one) for one in held[: -_SHOWN - 1 : -1])
            if held
            else f"[$text-muted]{t('No transfer yet.')}[/]"
        )
        going = any(not one.done for one in held)
        self.query_one("#note", Static).update(
            t("A transfer goes on when this page is closed.") if going else ""
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Whether a key does anything here: only the ones the hint line says."""
        if action != "key":
            return True
        return parameters[0] == "escape" or parameters[0] in {
            held for held, _ in self.keys()
        }

    def action_key(self, key: str) -> None:
        """Does what the hint line says the key does."""
        if key == "escape":
            self.dismiss()
        else:
            self.pressed(key)

    def pressed(self, key: str) -> None:
        """Does what one of the page's own keys does."""

    def _row(self) -> str:
        """The row under the cursor, by id, or "" for none."""
        listing = self.query_one("#rows", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "")

    def _fill(self) -> None:
        """Puts the page's rows up, where it lists any."""

    @on(OptionList.OptionHighlighted, "#rows")
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Draws the list again with the cursor's row as one plane, once it has moved."""
        held = str(event.option.id or "")
        if held != self._shaded:
            self._shaded = held
            self._fill()

    def _put(self, options: list[Option]) -> None:
        """Puts the rows up with the cursor on the row it was on, else the first to pick."""
        listing = self.query_one("#rows", OptionList)
        was = self._row()
        listing.set_options(options)
        listing.highlighted = next(
            (at for at, one in enumerate(options) if was and one.id == was),
            next((at for at, one in enumerate(options) if not one.disabled), None),
        )


class Download(Transfer):
    """What a backup target holds, and one epic or chat of it brought here."""

    TITLE_SAID: ClassVar = "Download"
    KIND: ClassVar = "download"

    def __init__(self) -> None:
        """Opens on the first backup target there is."""
        super().__init__()
        from hmz.daemon import Hmz

        self._targets = [one.name for one in Hmz().backups.targets()]
        self._target = self._targets[0] if self._targets else ""
        #: What the target holds, newest first, or None while it is fetched.
        self._held: list[stored.Held] | None = None
        #: The keys of the ones this machine has.
        self._here: set[str] = set()
        #: The keys of the ones being downloaded now, each asked for once.
        self._asked: set[str] = set()

    def on_mount(self) -> None:
        """Fetches the target, where there is one."""
        super().on_mount()
        if self._target:
            self._fetches()

    def about(self) -> str:
        """Which target is read, and what the list is."""
        if not self._target:
            return t("No backup target.") + t(
                " Add one, and the epics it holds are downloaded from here."
            )
        heading = t("Download from {target}", target=escape(self._target))
        return f"[b $foreground]{heading}[/]\n" + t(
            "Every epic and chat the backup target holds, by machine and folder, "
            "newest first. Enter downloads one here, as an import does."
        )

    def keys(self) -> Sequence[tuple[str, str]]:
        """Downloading, fetching again, and the next target where there is another."""
        if not self._target:
            return ()
        held = [("enter", "Download"), ("f", "Fetch")]
        return [*held, ("t", "Target")] if len(self._targets) > 1 else held

    def pressed(self, key: str) -> None:
        """Fetches the target again, or turns to the next one."""
        if key == "t":
            at = self._targets.index(self._target)
            self._target = self._targets[(at + 1) % len(self._targets)]
        if key in ("f", "t"):
            self._fetches()
        elif key == "enter":
            self._downloads(self._row())

    @on(OptionList.OptionSelected, "#rows")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Downloads the row chosen."""
        self._downloads(str(event.option.id or ""))

    @work(group="held", exclusive=True)
    async def _fetches(self) -> None:
        """Reads what the target holds off the event loop, which is a `git fetch`."""
        from hmz.daemon import Hmz

        target, self._held = self._target, None
        self._said = escape(t("Fetching {target}…", target=target))
        self._fill()
        try:
            self._held, self._here = await asyncio.to_thread(stored.held, target)
        except (OSError, ValueError) as why:
            said = Hmz().verses.plain(str(why))
            self._held, self._said = [], f"[$error]{escape(f'{target}: {said}')}[/]"
        else:
            self._said = ""
            if not self._held:
                self._said = t("No epic here yet.") + escape(
                    t(
                        " {target} holds none: an epic is backed up to it as its "
                        "policies say, or by Upload.",
                        target=target,
                    )
                )
        self._fill()

    def _fill(self) -> None:
        """Puts each machine up, each folder under it, and each epic under that."""
        options: list[Option] = []
        place = ("", "")
        at = self._shaded = self._row()
        for one in self._held or []:
            if (one.machine, one.workspace) != place:
                if one.machine != place[0]:
                    options.append(
                        Option(f"[b $primary]{escape(one.machine)}[/]", disabled=True)
                    )
                folder = escape(_homed(one.workspace))
                options.append(Option(f"  [$text-muted]{folder}[/]", disabled=True))
                place = (one.machine, one.workspace)
            here = one.key in self._here
            said = escape(stored.about(one, here=here))
            if one.key != at:
                said = f"[$text-muted]{said}[/]"
            options.append(
                Option(f"    [b]{escape(stored.named(one))}[/]  {said}", id=one.key)
            )
        self._put(options)
        self._draws()

    def _downloads(self, key: str) -> None:
        """Starts one download, unless what it would bring is here already."""
        one = next((each for each in self._held or [] if each.key == key), None)
        if one is None:
            return
        if one.key in self._asked:
            return  # on its way: asked for once, however often enter is pressed
        if one.key in self._here:
            self._said = t(
                "{name} is here already; {then}",
                name=escape(one.epic),
                then=stored.then(one),
            )
            self._draws()
            return
        self._asked.add(one.key)

        def landed(moved: Moving) -> None:
            self._asked.discard(one.key)
            if not moved.failed:
                self._here.add(one.key)
            if self.is_attached:
                self._fill()

        moves(
            self._interface(),
            self.KIND,
            t("Downloading {name}…", name=one.epic),
            partial(stored.pull, self._target, one),
            landed,
        )
        self._said = ""
        self._fill()


class Import(Transfer):
    """A `.hmzepic` read back in, as an epic of the folder it says it ran in."""

    TITLE_SAID: ClassVar = "Import"
    KIND: ClassVar = "import"
    LISTS: ClassVar = False

    def on_mount(self) -> None:
        """Asks for the file at once, unless an import is what there is to look at."""
        super().on_mount()
        if not any(one.kind == self.KIND for one in moving(self._interface())):
            self._asks()

    def about(self) -> str:
        """What an import is."""
        return t(
            "An epic somebody exported, a .hmzepic file, is read back in under the "
            "folder it ran in."
        )

    def keys(self) -> Sequence[tuple[str, str]]:
        """Asking for a file."""
        return (("enter", "Import"),)

    def pressed(self, key: str) -> None:
        """Asks which file to import."""
        del key
        self._asks()

    @work
    async def _asks(self) -> None:
        """Asks which file, its path finished as it is typed, and starts reading it in."""
        from pathlib import Path

        from hmz.daemon import Hmz

        source = await self._interface().push_screen_wait(ImportingEpic())
        if source is None:
            return

        def importing() -> str:
            epics = Hmz().epics
            landed = epics.imported(source)
            ran = epics.read(landed)
            where = ran.workspace if ran and ran.workspace else str(landed.parent)
            return t("Imported into {folder}.", folder=_homed(where))

        moves(
            self._interface(),
            self.KIND,
            t("Importing {name}…", name=Path(source).name),
            importing,
        )
        self._draws()


class Export(Transfer):
    """A recorded epic written out as one `.hmzepic`, where somebody says it goes."""

    TITLE_SAID: ClassVar = "Export"
    KIND: ClassVar = "export"

    def __init__(self, epic: Path | None = None) -> None:
        """Opens on every epic recorded here, or straight on where one of them goes.

        Args:
          epic: The epic to export, by the directory it is written in, for a page opened
            from that epic's own menu; None to pick one.
        """
        super().__init__()
        self._epic = epic
        #: Every epic recorded on this machine, newest first, or None while they are read.
        self._ran: list[Ran] | None = None

    def on_mount(self) -> None:
        """Reads the epics, and asks where the one named goes."""
        super().on_mount()
        self._reads()

    def about(self) -> str:
        """What an export is."""
        return t(
            "Pick an epic; the whole of it is written as one .hmzepic archive, with "
            "its trace, credentials struck out."
        )

    def keys(self) -> Sequence[tuple[str, str]]:
        """Exporting the epic under the cursor."""
        return (("enter", "Export"),) if self._ran else ()

    def pressed(self, key: str) -> None:
        """Asks where the epic under the cursor goes."""
        del key
        self._exports(self._row())

    @on(OptionList.OptionSelected, "#rows")
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Asks where the epic chosen goes."""
        self._exports(str(event.option.id or ""))

    @work(group="ran", exclusive=True)
    async def _reads(self) -> None:
        """Reads every epic recorded on this machine off the event loop, newest first."""
        from hmz.daemon import Hmz

        def read() -> list[Ran]:
            epics = Hmz().epics
            found = [epics.read(at) for at in epics.every()]
            return sorted(
                (one for one in found if one is not None),
                key=lambda one: one.began,
                reverse=True,
            )

        self._said = t("Loading…")
        self._draws()
        self._ran = await asyncio.to_thread(read)
        self._said = "" if self._ran else t("No epic to export yet.")
        self._fill()
        if self._epic is not None:
            named, self._epic = self._epic.name, None
            self._exports(named)

    def _fill(self) -> None:
        """Puts each epic up: when it began and what ran, then its task and where it ran."""
        at = self._shaded = self._row()
        options: list[Option] = []
        for one in self._ran or []:
            named = f"{_when(one.began)} · {t('chat') if chatting(one) else one.flow}"
            said = _asked_for(one.task) if one.task else t("no task")
            said = escape(
                f"{said} · {one.how or t('unfinished')} · {_homed(one.workspace)}"
            )
            if one.name != at:
                said = f"[$text-muted]{said}[/]"
            options.append(Option(f"  [b]{escape(named)}[/]  {said}", id=one.name))
        self._put(options)
        self._draws()

    @work
    async def _exports(self, name: str) -> None:
        """Asks where one epic's archive goes, and starts writing it there."""
        from hmz.runtime.exporting import sized

        ran = next((one for one in self._ran or [] if one.name == name), None)
        if ran is None:
            return
        to = await self._interface().push_screen_wait(Exporting(ran.name))
        if to is None:
            return

        def exporting() -> str:
            landed, size, _ = exported(ran, to)
            return t(
                "Exported {name} to {path} ({size}).",
                name=ran.name,
                path=_homed(str(landed)),
                size=sized(size),
            )

        moves(
            self._interface(),
            self.KIND,
            t("Exporting {name}…", name=ran.name),
            exporting,
        )
        self._draws()


def _download(_app: App[None]) -> Download:
    return Download()


def _import(_app: App[None]) -> Import:
    return Import()


def _export(_app: App[None]) -> Export:
    return Export()


VIEWS = (
    View("download", "page", "Download", _download),
    View("import", "page", "Import", _import),
    View("export", "page", "Export", _export),
)
