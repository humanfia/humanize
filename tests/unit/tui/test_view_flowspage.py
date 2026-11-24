"""`hmz.tui.views.flowspage`: the Flows page, over a store that holds two flows and an index."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from textual.app import App
from textual.widgets import OptionList, Static

import hmz.daemon
from hmz.tui import flows, humanfia, shell
from hmz.tui.shell import Hints
from hmz.tui.views.flowspage import VIEWS, FlowsPage

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _Installed:
    verse: str
    listed: str
    version: str

    @property
    def called(self) -> str:
        return f"@{self.verse}/{self.listed}"


@dataclass
class _Verses:
    """The flowverses store: one index, `theirs`, with `kernel` installed behind it."""

    at: Path
    held: list[_Installed] = field(
        default_factory=lambda: [_Installed("theirs", "kernel", "1.0.0")]
    )
    did: list[tuple[str, ...]] = field(default_factory=list[tuple[str, ...]])

    def all(self) -> list[Any]:
        return [
            SimpleNamespace(
                name="theirs", url="https://x/y", at=self.at, fetched=True, fixed=False
            )
        ]

    def installed(self) -> list[_Installed]:
        return list(self.held)

    def updates(self) -> list[Any]:
        return [SimpleNamespace(installed=one, version="1.1.0") for one in self.held]

    def index(self, name: str) -> Any:
        return SimpleNamespace(flows=lambda: ["kernel"], skipped=(), verse=name)

    def whence(self, one: Any, nowhere: str) -> str:
        return one.url or nowhere

    def plain(self, url: str) -> str:
        return url

    def install(self, flow: str, version: str) -> list[_Installed]:
        self.did.append(("install", flow, version))
        self.held = [_Installed("theirs", "kernel", version)]
        return self.held

    def uninstall(self, flow: str) -> bool:
        self.did.append(("uninstall", flow))
        self.held = []
        return True


@dataclass
class _Hmz:
    verses: _Verses

    def __call__(self) -> _Hmz:
        return self

    @property
    def flows(self) -> Any:
        offers = [SimpleNamespace(whose="local", name="@local/mine", about="My own.")]
        offers += [
            SimpleNamespace(whose="theirs", name=one.called, about="A kernel.")
            for one in self.verses.held
        ]
        return SimpleNamespace(all=lambda: offers)


#: The views this module is about.
OWN = ("flows", "download", "import", "export")


@pytest.fixture(autouse=True)
def own_views(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only this module's views: what another view does beside them is its own test's."""
    found = {name: view for name, view in shell.views().items() if name in OWN}
    monkeypatch.setattr(shell, "views", lambda: found)
    # The page asks by the name it imported, which is its own to stand in for.
    monkeypatch.setattr("hmz.tui.views.flowspage.views", lambda: found)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Hmz:
    """The one store the page reaches, in place of Humanize's own."""
    held = _Hmz(_Verses(tmp_path))
    monkeypatch.setattr(hmz.daemon, "Hmz", held)
    return held


class _Stands(App[None]):
    """An interface that is the page and whether an epic is going, and nothing else."""

    going = False

    def __init__(self) -> None:
        super().__init__()
        self.told: list[str] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def flow_running(self) -> bool:
        return self.going

    def on_flows_told(self, event: flows.Flows.Told) -> None:
        self.told.extend(event.lines)


def _said(app: App[None], held: str) -> str:
    return str(app.screen.query_one(held, Static).render())


def _rows(app: App[None]) -> list[str]:
    return [str(one.id) for one in app.screen.query_one("#rows", OptionList).options]


async def _settled(pilot: Any, app: App[None]) -> None:
    await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
    await pilot.pause()


def test_the_page_is_the_flows_view_and_the_only_one_with_a_key() -> None:
    (view,) = VIEWS

    assert (view.name, view.zone, view.title) == ("flows", "page", "Flows")
    assert (view.key, view.hint) == ("ctrl+l", "Flows")
    assert shell.views()["flows"] is view


@pytest.mark.usefixtures("store")
async def test_a_flow_with_a_newer_release_is_first_marked_and_counted() -> None:
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        await app.push_screen(FlowsPage())
        await pilot.pause()

        assert _said(app, "#title") == "FLOWS"
        assert _rows(app) == ["@theirs/kernel", "@local/mine"]
        assert "1 flow has a newer release" in _said(app, "#about")
        first = str(app.screen.query_one("#rows", OptionList).options[0].prompt)
        assert "1.0.0" in first
        assert "↑ 1.1.0" in first
        assert str(app.screen.query_one(Hints).render()) == (
            "enter Open   N New epic   U Update   S Switch   X Uninstall   "
            "tab Flowverses   esc Back"
        )


async def test_update_installs_the_newer_release_and_says_so(store: _Hmz) -> None:
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        await app.push_screen(FlowsPage())
        await pilot.pause()

        await pilot.press("u")
        await _settled(pilot, app)

        assert store.verses.did == [("install", "@theirs/kernel", "1.1.0")]
        assert _said(app, "#said") == "@theirs/kernel 1.1.0 is installed."
        assert app.told == ["[dim]@theirs/kernel 1.1.0 is installed.[/dim]"]


async def test_uninstall_asks_first_by_name_and_keeps_the_flow_on_cancel(
    store: _Hmz,
) -> None:
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        page = FlowsPage()
        await app.push_screen(page)
        await pilot.pause()

        await pilot.press("x")
        await pilot.pause()
        asked = app.screen
        assert isinstance(asked, flows.Uninstalls)
        assert asked.asked == "Uninstall @theirs/kernel?"
        await pilot.press("escape")
        await _settled(pilot, app)
        assert store.verses.did == []

        await pilot.press("x")
        await pilot.pause()
        cast("flows.Uninstalls", app.screen).dismiss("yes")
        await _settled(pilot, app)

        assert app.screen is page
        assert store.verses.did == [("uninstall", "@theirs/kernel")]
        assert _rows(app) == ["@local/mine"]


async def test_an_update_left_behind_still_lands_and_is_said(store: _Hmz) -> None:
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        page = FlowsPage()
        await app.push_screen(page)
        await pilot.pause()

        await pilot.press("u", "escape")
        await _settled(pilot, app)

        assert app.screen is not page
        assert store.verses.did == [("install", "@theirs/kernel", "1.1.0")]
        assert app.told == ["[dim]@theirs/kernel 1.1.0 is installed.[/dim]"]


async def test_new_epic_closes_the_page_and_sets_the_flow_up(
    store: _Hmz, monkeypatch: pytest.MonkeyPatch
) -> None:
    del store
    started: list[str] = []
    app = _Stands()
    monkeypatch.setattr(app, "action_flow", started.append, raising=False)
    async with app.run_test(size=(120, 30)) as pilot:
        page = FlowsPage()
        await app.push_screen(page)
        await pilot.pause()

        await pilot.press("n")
        await _settled(pilot, app)

        assert app.screen is not page
        assert started == ["@theirs/kernel"]


async def test_nothing_is_installed_or_uninstalled_while_an_epic_is_going(
    store: _Hmz,
) -> None:
    app = _Stands()
    app.going = True
    async with app.run_test(size=(120, 30)) as pilot:
        page = FlowsPage()
        await app.push_screen(page)
        await pilot.pause()
        why = "An epic is going; flows are installed, updated and uninstalled once it ends."
        assert _said(app, "#held") == why

        await pilot.press("u")
        await _settled(pilot, app)
        await pilot.press("x")
        await _settled(pilot, app)

        assert app.screen is page
        assert store.verses.did == []
        assert _said(app, "#said") == why


@pytest.mark.usefixtures("store")
async def test_tab_turns_to_the_flowverses_and_esc_goes_back_a_step_then_out() -> None:
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        page = FlowsPage()
        await app.push_screen(page)
        await pilot.pause()

        await pilot.press("tab")
        await pilot.pause()
        assert _rows(app) == ["theirs"]
        row = str(app.screen.query_one("#rows", OptionList).options[0].prompt)
        assert "1 flow" in row
        assert "1 installed" in row
        assert "↑ 1 update" in row
        assert "A Add flowverse" in str(app.screen.query_one(Hints).render())

        # A key the hint line does not say does nothing here.
        await pilot.press("u")
        await pilot.pause()
        assert _said(app, "#said") == ""

        await pilot.press("s")
        await pilot.pause()
        assert _rows(app) == ["theirs"]

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not page
