"""`hmz.tui.shell`: the zones beside the log, the views opened in them, and the line of keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Input, Static

from hmz.tui import humanfia, shell
from hmz.tui.shell import Hints, Shell, View, Zone

if TYPE_CHECKING:
    import pytest


class _Pane(Static, can_focus=True):
    pass


LEFT = View("left", "navigator", "Open", lambda _: _Pane("left"), key="f2", hint="Open")
RIGHT = View(
    "right", "context", "Search", lambda _: _Pane("right"), key="f3", hint="Search",
    keys=(("enter", "Open"),),
)  # fmt: skip
START = View("start", "navigator", "Close", lambda _: _Pane("start"), opens=True)


class _Stands(App[None]):
    """An interface that is the zones and a prompt, and nothing else."""

    def __init__(self) -> None:
        super().__init__()
        self.shell = Shell(self)

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Zone(id="navigator")
        yield Input(id="editor")
        yield Zone(id="context")
        yield Hints(id="hints")

    def on_mount(self) -> None:
        for bound in shell.bindings():
            self.bind(bound.key, bound.action)
        self.shell.starts()

    async def action_view(self, name: str) -> None:
        await self.shell.toggles(name)


def _with(monkeypatch: pytest.MonkeyPatch, *found: View) -> None:
    monkeypatch.setattr(shell, "views", lambda: {view.name: view for view in found})


def test_the_views_are_found_by_walking_the_package() -> None:
    found = shell.views()

    assert found["keys"].zone == "context"
    assert found["keys"].key == "f1"


def test_a_view_with_a_key_is_bound_over_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, LEFT, START)

    (bound,) = shell.bindings()
    assert (bound.key, bound.action, bound.priority) == ("f2", "view('left')", True)


async def test_a_zone_is_closed_until_a_view_is_opened_in_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, LEFT, RIGHT)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        app = pilot.app
        navigator, context = (
            app.query_one("#navigator", Zone),
            app.query_one("#context", Zone),
        )
        assert not navigator.has_class("open")
        assert not context.display

        await pilot.press("f3")
        await pilot.pause()

        assert context.has_class("open")
        assert context.view is RIGHT
        assert not navigator.has_class("open")
        assert isinstance(app.focused, _Pane)
        assert str(context.query_one(".zone-title", Static).render()) == "SEARCH"


async def test_a_views_key_goes_to_it_then_closes_it_and_esc_only_lets_go_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, LEFT, RIGHT)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        app = pilot.app
        context = app.query_one("#context", Zone)
        await pilot.press("f3")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()
        assert context.has_class("open")
        assert isinstance(app.focused, Input)

        await pilot.press("f3")
        await pilot.pause()
        assert context.has_class("open")
        assert isinstance(app.focused, _Pane)

        await pilot.press("f3")
        await pilot.pause()
        assert not context.has_class("open")
        assert context.view is None
        assert isinstance(app.focused, Input)


async def test_a_view_that_opens_with_the_interface_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, START)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        await pilot.pause()

        assert pilot.app.query_one("#navigator", Zone).view is START


async def test_the_hint_line_says_the_keys_of_what_has_the_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, LEFT, RIGHT)
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        hints = app.query_one(Hints)
        await pilot.pause()
        assert str(hints.render()) == "F2 Open   F3 Search"

        await pilot.press("f3")
        await pilot.pause()
        assert app.shell.held() is RIGHT
        assert str(hints.render()) == "enter Open   esc Back   F2 Open"


async def test_there_is_no_hint_line_where_there_is_nothing_to_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, START)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        await pilot.pause()

        assert not pilot.app.query_one(Hints).has_class("hinting")


async def test_a_zone_is_widened_a_step_at_a_time_and_is_narrow_again_after_the_widest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with(monkeypatch, LEFT, RIGHT)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        context = pilot.app.query_one("#context", Zone)
        await pilot.press("f3")
        await pilot.pause()
        assert context.outer_size.width == 48

        assert context.widens() == "wide"
        await pilot.pause()
        assert context.outer_size.width == 60

        assert context.widens() == "widest"
        await pilot.pause()
        assert context.outer_size.width == 96
        assert not context.has_class("wide")

        assert context.widens() == ""
        await pilot.pause()
        assert context.outer_size.width == 48


class _Turning(Static, can_focus=True):
    """A pane whose keys are other keys once it has been turned."""

    turned = False

    def hint_keys(self) -> list[tuple[str, str]]:
        return [("enter", "Close" if self.turned else "Open")]


async def test_a_view_that_says_its_own_keys_is_asked_for_them_as_the_line_is_drawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turning = View("turning", "context", "Search", lambda _: _Turning("x"), key="f3")
    _with(monkeypatch, turning)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        app = pilot.app
        await pilot.press("f3")
        await pilot.pause()
        assert str(app.query_one(Hints).render()) == "enter Open   esc Back"

        pane = app.query_one(_Turning)
        pane.turned = True
        shell.hinting(pane)
        await pilot.pause()

        assert str(app.query_one(Hints).render()) == "enter Close   esc Back"


class _Page(Screen[None]):
    """A page with a way out of its own, which counts the times it was taken."""

    left = 0

    def closes(self) -> None:
        type(self).left += 1
        self.dismiss(None)


async def test_a_pages_key_closes_it_by_its_own_way_out_while_it_is_on_top(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = View("page", "page", "Open", lambda _: _Page(), key="f4", hint="Open")
    _with(monkeypatch, page)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        app = pilot.app
        await pilot.press("f4")
        await pilot.pause()
        assert isinstance(app.screen, _Page)

        # Under another screen the key is not the page's to be closed by.
        await app.push_screen(Screen[None]())
        await pilot.press("f4")
        await pilot.pause()
        assert (len(app.screen_stack), _Page.left) == (3, 0)
        await app.pop_screen()

        await pilot.press("f4")
        await pilot.pause()

        # Left by its own way out, which is where a page keeps what it held.
        assert len(app.screen_stack) == 1
        assert _Page.left == 1
