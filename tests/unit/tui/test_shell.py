"""`hmz.tui.shell`: the zones beside the log, the views opened in them, and the line of keys."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
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
