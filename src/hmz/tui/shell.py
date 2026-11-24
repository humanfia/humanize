"""Where things are in the terminal interface: three zones that stay put, and the keys to them.

The log -- the transcript and the prompt under it -- is the work, in the middle. To its left
is the navigator: what there is to work on. To its right is the context: more about the thing
being worked on. Neither is drawn until something is opened in it, and what is opened there is
a :class:`View`, written in a module of `hmz.tui.views` and found by name, as a command of
`hmz.cli.commands` is. A view that needs the whole screen is a page instead.

The rules a view is written to, which are what make the interface one place rather than a
set of screens (Section 3 of tui.md):

- A zone is always where it is. Opening a view never moves another.
- What waits on the person is first in any list it is in.
- One thing on a screen is pink: what is picked, or the one thing to press. What can be
  followed is cyan. Green stands only beside cyan.
- `esc` goes back one step: out of a zone to the prompt, out of a page to what was under it.
- Every key a view takes is on the hint line while the view has the keys. Nothing is done by
  a key that is not shown.
- Removing something asks first, and names what goes.
- Every text is one of :mod:`hmz.words`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, partial
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from hmz.words import t

from . import humanfia

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from textual import events
    from textual.app import App, ComposeResult
    from textual.widget import Widget

__all__ = ["Hints", "Shell", "View", "Zone", "bindings", "views"]

type Where = Literal["navigator", "context", "page"]


@dataclass(frozen=True)
class View:
    """One thing that can be opened beside the log, or over it."""

    name: str
    """What it is opened by, and what its module is called."""
    zone: Where
    """Where it opens: one of the two zones beside the log, or the whole screen."""
    title: str
    """What it is headed, in one text of :mod:`hmz.words`."""
    make: Callable[[App[None]], Widget]
    """Makes it for an interface: a widget for a zone, a `Screen` for a page."""
    key: str = ""
    """The key that opens it from anywhere, and closes it where it is a zone's; "" for none."""
    hint: str = ""
    """What that key is said to do on the hint line, in one text of :mod:`hmz.words`."""
    opens: bool = False
    """Whether it is open when the interface opens."""
    keys: tuple[tuple[str, str], ...] = ()
    """The keys it takes while it has them, each with what it does: the hint line's, in order."""


@cache
def views() -> dict[str, View]:
    """Every view of `hmz.tui.views`, by name, in the order of their modules' names."""
    import pkgutil
    from importlib import import_module

    from . import views as package

    found: dict[str, View] = {}
    for module in sorted(
        pkgutil.iter_modules(package.__path__), key=lambda one: one.name
    ):
        if module.name.startswith("_"):
            continue
        held: tuple[View, ...] = import_module(
            f"{package.__name__}.{module.name}"
        ).VIEWS
        for view in held:
            if view.name in found:
                raise RuntimeError(f"two views are called {view.name!r}")
            found[view.name] = view
    return found


def bindings() -> list[Binding]:
    """The key of every view that has one, bound over whatever has the keys."""
    return [
        Binding(
            view.key, f"view('{view.name}')", t(view.hint), show=False, priority=True
        )
        for view in views().values()
        if view.key
    ]


class Zone(Vertical):
    """One of the two zones beside the log: closed until a view is opened in it."""

    DEFAULT_CSS = """
    Zone { display: none; width: 36; height: 1fr; background: $surface; }
    Zone.open { display: block; }
    Zone > .zone-title { height: 1; padding: 0 1; color: $text-muted; text-style: bold; }
    Zone:focus-within > .zone-title { color: $primary; }
    Zone > .zone-rule { height: 1; color: $hmz-line-strong; }
    Zone:focus-within > .zone-rule { color: $primary; }
    Zone#navigator { border-right: heavy $hmz-line; }
    Zone#context { border-left: heavy $hmz-line; width: 48; }
    Zone.wide, Zone#context.wide { width: 50%; }
    Zone.widest, Zone#context.widest { width: 80%; }
    """

    #: How wide a zone can be made, narrowest first: as it opens, half the screen, most of it.
    WIDTHS: ClassVar = ("", "wide", "widest")

    #: The view open here, or None.
    view: View | None = None
    #: What is told that the keys came to this zone or left it: the shell's, once it starts.
    told: Callable[[], None] | None = None

    def compose(self) -> ComposeResult:
        """A title, a heavy rule under it, and under that whatever is opened."""
        yield Static(classes="zone-title")
        yield Static(classes="zone-rule")

    def on_resize(self, event: events.Resize) -> None:
        """Rules the title across however wide the zone is now."""
        self.query_one(".zone-rule", Static).update(humanfia.RULE * event.size.width)

    async def shows(self, view: View, made: Widget, *, keys: bool = True) -> None:
        """Opens a view here, in place of whatever was, and gives it the keys unless told not to."""
        await self.empties()
        self.view = view
        self.query_one(".zone-title", Static).update(t(view.title).upper())
        await self.mount(made)
        self.add_class("open")
        if keys:
            made.focus()

    def on_descendant_focus(self, _: events.DescendantFocus) -> None:
        """Has the hint line say this view's keys, now that it has them."""
        self._hints()

    def on_descendant_blur(self, _: events.DescendantBlur) -> None:
        """Has the hint line stop saying them."""
        self.call_after_refresh(self._hints)

    def _hints(self) -> None:
        if self.told is not None:
            self.told()

    def on_key(self, event: events.Key) -> None:
        """Gives the keys back to the prompt on `esc`: one step back, the zone left open."""
        if event.key == "escape":
            event.stop()
            for prompt in self.screen.query(Shell.HOME):
                prompt.focus()

    def widens(self) -> str:
        """Makes the zone one step wider, and as narrow as it opens after the widest.

        Returns:
          How wide it is now: one of :attr:`WIDTHS`.
        """
        now = next((one for one in self.WIDTHS if one and self.has_class(one)), "")
        going = self.WIDTHS[(self.WIDTHS.index(now) + 1) % len(self.WIDTHS)]
        for one in self.WIDTHS:
            if one:
                self.set_class(one == going, one)
        return going

    async def empties(self) -> None:
        """Closes the zone, and lets go of what was in it."""
        self.view = None
        self.remove_class("open")
        for child in self.children[2:]:
            await child.remove()


class Hints(Static):
    """The line of keys: every key that does something where the keys are, and what it does."""

    DEFAULT_CSS = """
    /* As many lines as its keys take, so that none is cut off on a narrow terminal. */
    Hints { display: none; height: auto; max-height: 3; padding: 0 2;
            color: $text-muted; }
    Hints.hinting { display: block; }
    """

    #: The keys being shown, each with what it does.
    _pairs: Sequence[tuple[str, str]] = ()

    def says(self, pairs: Sequence[tuple[str, str]]) -> None:
        """Shows keys and what each does; nothing, and no line, where there are none."""
        self._pairs = tuple(pairs)
        self.set_class(bool(pairs), "hinting")
        self._draws()

    def on_resize(self, _: events.Resize) -> None:
        """Breaks the line again for however wide it is now."""
        self._draws()

    def _draws(self) -> None:
        """Writes the keys, a row breaking only between one key and the next.

        Left to wrap where it will, a row ends with a key and the next begins with what that
        key does, which reads as two things.
        """
        wide = self.size.width or 10**6
        rows: list[list[str]] = [[]]
        used = 0
        for key, does in self._pairs:
            plain = len(f"{_shown(key)} {t(does)}")
            if rows[-1] and used + 3 + plain > wide:
                rows.append([])
                used = 0
            used += plain + (3 if len(rows[-1]) else 0)
            rows[-1].append(f"[b $primary]{_shown(key)}[/] {t(does)}")
        self.update("\n".join("   ".join(row) for row in rows))


def _shown(key: str) -> str:
    """A key as it is written for a person: `ctrl+k` is `^K`."""
    held, _, name = key.rpartition("+")
    name = name.upper() if len(name) == 1 or name.startswith("f") else name
    return f"^{name}" if held == "ctrl" else f"{held}+{name}" if held else name


class Shell:
    """The zones of one interface, and what is open in them."""

    #: Where the keys go when a zone lets go of them: the prompt.
    HOME: ClassVar = "#editor"

    def __init__(self, app: App[None]) -> None:
        """Holds the interface the zones are part of."""
        self._app = app
        #: The page each view that is one last opened, which its key closes while it is up.
        self._pages: dict[str, Widget] = {}

    def zone(self, where: Where) -> Zone:
        """One of the two zones."""
        return self._app.query_one(f"#{where}", Zone)

    def starts(self) -> None:
        """Opens what is open from the start, and draws the hint line."""
        for zone in self._app.query(Zone):
            zone.told = self.hints
        for view in views().values():
            if view.opens and view.zone != "page":
                # Open, and the keys still the prompt's: nothing typed goes astray.
                self._app.call_later(partial(self.opens, view.name, keys=False))
        self.hints()

    async def opens(self, name: str, *, keys: bool = True) -> None:
        """Opens a view by name: in its zone, or over the screen where it is a page.

        Args:
          name: The view.
          keys: Whether it is given the keys; a page always has them.
        """
        view = views()[name]
        made = view.make(self._app)
        if view.zone == "page":
            from textual.screen import Screen

            if not isinstance(made, Screen):
                raise TypeError(f"the page {name!r} is not a screen")
            # A page's key is bound over everything, the page itself included: pressed on
            # the page it opens, or on anything opened from it, it is not opened again.
            page = cast("Screen[None]", made)
            if not any(type(one) is type(page) for one in self._app.screen_stack):
                self._pages[name] = made
                await self._app.push_screen(page)
        else:
            await self.zone(view.zone).shows(view, made, keys=keys)
        self.hints()

    async def closes(self, where: Where) -> None:
        """Closes a zone, and gives the keys back to the prompt."""
        if where != "page":
            await self.zone(where).empties()
        self.home()
        self.hints()

    async def toggles(self, name: str) -> None:
        """What a view's key does: opens it, goes to it, or closes it where the keys are in it.

        The same key is the way in and the way out, so that there is one thing to remember:
        pressed from elsewhere it goes to the view, opening it if it is not open, and pressed
        from inside it closes it -- a page as well as a zone's.
        """
        view = views()[name]
        if view.zone == "page" and self._app.screen is self._pages.get(name):
            self._app.pop_screen()
        elif view.zone != "page" and not self._app.query(f"#{view.zone}"):
            # A sheet or a page is over the log: the zones are under it, and the key is its.
            return
        elif view.zone == "page" or self.zone(view.zone).view is not view:
            await self.opens(name)
        elif self.held() is view:
            await self.closes(view.zone)
        else:
            self.zone(view.zone).children[-1].focus()
            self.hints()

    def home(self) -> None:
        """Gives the keys to the prompt."""
        for prompt in self._app.query(self.HOME):
            prompt.focus()

    def held(self) -> View | None:
        """The view that has the keys, or None where the log does."""
        focused = self._app.focused
        for zone in self._app.query(Zone):
            if focused is not None and zone in focused.ancestors_with_self:
                return zone.view
        return None

    def hints(self) -> None:
        """Draws the hint line: the keys of what has the keys, then each view's own."""
        # The log's own, whatever page is over it: a page says its keys for itself.
        line = self._app.screen_stack[0].query(Hints) if self._app.screen_stack else ()
        if not line:
            return
        held = self.held()
        pairs = [*held.keys, ("esc", "Back")] if held is not None else []
        pairs += [
            (view.key, view.hint)
            for view in views().values()
            if view.key and view.hint and view is not held
        ]
        line.first(Hints).says(pairs)
