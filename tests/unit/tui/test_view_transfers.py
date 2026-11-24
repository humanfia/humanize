"""`hmz.tui.views.transfers`: Download, Import and Export, and a transfer that outlives its page."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from textual.app import App
from textual.widgets import OptionList, Static

import hmz.daemon
from hmz.tui import humanfia, shell, stored
from hmz.tui.shell import Hints
from hmz.tui.views.transfers import VIEWS, Download, Import, moves, moving

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class _Stands(App[None]):
    """An interface that is a transcript to say things in, and nothing else."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[str, str]] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def show(self, text: str, style: str = "") -> None:
        self.shown.append((text, style))


def _said(app: App[None], held: str) -> str:
    return str(app.screen.query_one(held, Static).render())


async def _landed(pilot: Any, app: App[None]) -> None:
    await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
    await pilot.pause()


def test_the_three_pages_are_views_with_no_key_of_their_own() -> None:
    assert [(one.name, one.zone, one.title, one.key) for one in VIEWS] == [
        ("download", "page", "Download", ""),
        ("import", "page", "Import", ""),
        ("export", "page", "Export", ""),
    ]
    assert all(shell.views()[one.name] is one for one in VIEWS)


async def test_a_transfer_goes_on_after_its_page_is_left_and_is_read_on_return() -> (
    None
):
    gate = threading.Event()

    def how() -> str:
        gate.wait(10)
        return "Imported into ~/work."

    app = _Stands()
    async with app.run_test(size=(100, 24)) as pilot:
        one = moves(app, "import", "Importing a.hmzepic…", how)
        await app.push_screen(Import())
        await pilot.pause()

        assert _said(app, "#title") == "IMPORT"
        assert "Importing a.hmzepic…" in _said(app, "#moving")
        assert _said(app, "#note") == "A transfer goes on when this page is closed."
        assert str(app.screen.query_one(Hints).render()) == "enter Import   esc Back"

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, Import)
        assert not one.done

        gate.set()
        await _landed(pilot, app)
        assert (one.done, one.failed, one.said) == (
            True,
            False,
            "Imported into ~/work.",
        )
        assert app.shown == [("[dim]Imported into ~/work.[/dim]", "")]

        await app.push_screen(Import())
        await pilot.pause()
        assert "Imported into ~/work." in _said(app, "#moving")
        assert _said(app, "#note") == ""
    assert moving(app) == [one]


async def test_a_transfer_that_fails_says_why_in_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def how() -> str:
        raise ValueError("c.txt is not a .hmzepic file")

    verses = SimpleNamespace(plain=str)
    monkeypatch.setattr(hmz.daemon, "Hmz", lambda: SimpleNamespace(verses=verses))
    app = _Stands()
    async with app.run_test(size=(100, 24)) as pilot:
        one = moves(app, "import", "Importing c.txt…", how)
        await _landed(pilot, app)

        assert (one.done, one.failed) == (True, True)
        assert app.shown == [("[dim]c.txt is not a .hmzepic file[/dim]", "red")]


def _held(key: str, task: str) -> Any:
    return SimpleNamespace(
        key=key,
        machine="lab",
        workspace="/work",
        epic=key,
        flow="goal",
        task=task,
        began="2026-11-24T10:00:00.000Z",
        how="done",
        chat=False,
    )


async def test_download_lists_a_target_and_brings_one_epic_here_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [SimpleNamespace(name="lab"), SimpleNamespace(name="attic")]
    backups = SimpleNamespace(targets=lambda: targets)
    monkeypatch.setattr(hmz.daemon, "Hmz", lambda: SimpleNamespace(backups=backups))
    read: list[str] = []
    pulled: list[tuple[str, str]] = []

    def held(target: str) -> tuple[list[Any], set[str]]:
        read.append(target)
        return [_held("one", "fix the build"), _held("two", "ship it")], {"two"}

    def pull(target: str, one: Any) -> str:
        pulled.append((target, one.key))
        return f"Downloaded {one.key} into /work; open it from /epics"

    monkeypatch.setattr(stored, "held", held)
    monkeypatch.setattr(stored, "pull", pull)
    app = _Stands()
    async with app.run_test(size=(100, 24)) as pilot:
        await app.push_screen(Download())
        await _landed(pilot, app)

        assert "Download from lab" in _said(app, "#about")
        listing = app.screen.query_one("#rows", OptionList)
        assert [str(one.id) for one in listing.options if one.id] == ["one", "two"]
        assert "ship it · done · Here" in str(listing.options[-1].prompt)
        assert str(app.screen.query_one(Hints).render()) == (
            "enter Download   F Fetch   T Target   esc Back"
        )

        await pilot.press("enter")
        await pilot.press("enter")
        await _landed(pilot, app)
        assert pulled == [("lab", "one")]
        assert "Downloaded one into /work" in _said(app, "#moving")

        await pilot.press("enter")
        await _landed(pilot, app)
        assert pulled == [("lab", "one")]
        assert "one is here already" in _said(app, "#said")

        await pilot.press("t")
        await _landed(pilot, app)
        assert read == ["lab", "attic"]
        assert "Download from attic" in _said(app, "#about")


async def test_download_with_no_target_says_where_one_is_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backups = SimpleNamespace(targets=list)
    monkeypatch.setattr(hmz.daemon, "Hmz", lambda: SimpleNamespace(backups=backups))
    app = _Stands()
    async with app.run_test(size=(100, 24)) as pilot:
        await app.push_screen(Download())
        await pilot.pause()

        assert _said(app, "#about") == (
            "No backup target. Add one, and the epics it holds are downloaded from here."
        )
        assert str(app.screen.query_one(Hints).render()) == "esc Back"
