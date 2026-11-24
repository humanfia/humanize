"""`hmz.tui.views.search`: one field, the tabs and filters under it, and what was found."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static

from hmz.tui import humanfia
from hmz.tui.shell import Hints, Shell, Zone
from hmz.tui.views import search
from hmz.tui.views.search import Chosen, Search, asked

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest
    from textual.pilot import Pilot


class Daemon:
    """A daemon that finds chats and epics by what a test gave it."""

    def __init__(self, here: str) -> None:
        self.here = here
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, method: str, **params: Any) -> dict[str, Any]:
        self.asked.append((method, params))
        q = str(params.get("q") or "")
        if method == "chat.list":
            chats = [
                {
                    "id": name,
                    "title": title,
                    "workspace": self.here,
                    "began": began,
                    "updated": began,
                    "state": "resting",
                    "slot": "",
                }
                for name, title, began in (
                    ("c-parser", "refactor the parser", "2026-01-03T10:00:00Z"),
                    ("c-docs", "write the docs", "2026-01-01T10:00:00Z"),
                )
                if q in title
            ]
            return {"chats": chats, "total": len(chats)}
        if method == "runs.list":
            runs = [
                {
                    "name": "e-parser",
                    "workspace": self.here,
                    "flow": "@local/writes",
                    "task": "fuzz the parser",
                    "began": "2026-01-02T10:00:00Z",
                    "ended": "2026-01-02T11:00:00Z",
                    "how": "done",
                    "held": False,
                    "slot": "",
                }
            ]
            runs = [
                one
                for one in runs
                if q in one["task"] and params.get("status", "done") == one["how"]
            ]
            return {"runs": runs, "total": len(runs), "flows": ["@local/writes"]}
        if method == "workspaces.list":
            return {"workspaces": [{"path": self.here}, {"path": "/far/other"}]}
        return {}


class _Stands(App[None]):
    """An interface that is a prompt, and keeps what Search asked of it."""

    def __init__(self) -> None:
        super().__init__()
        self.shell = Shell(self)
        self.opened: list[tuple[Any, ...]] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Zone(id="navigator")
        yield Input(id="editor")
        yield Hints(id="hints")

    def opens_chat(self, chat: str, slot: str | None = None) -> None:
        self.opened.append(("chat", chat, slot))

    def opens_epic(
        self, epic: str, slot: str | None = None, *, here: bool = True
    ) -> None:
        self.opened.append(("epic", epic, slot, here))

    def showing(self) -> str:
        return ""

    def show(self, text: str, style: str = "") -> None:
        del text, style

    def copied(self, text: str) -> None:
        del text


def _found(page: Search) -> list[str]:
    return [str(one.id) for one in page.query_one(OptionList).options]


async def _until(pilot: Pilot[None], ready: Callable[[], bool]) -> None:
    for _ in range(300):
        await pilot.pause(0.01)
        if ready():
            return
    raise AssertionError("gave up waiting")


async def _opened(pilot: Pilot[None], daemon: Daemon, workspace: str = "") -> Search:
    page = Search(daemon, workspace)
    await pilot.app.push_screen(page)
    await _until(pilot, lambda: len(_found(page)) > 1 or bool(workspace))
    return page


def test_what_the_daemon_is_asked_follows_the_tab_and_the_filters() -> None:
    page = {"offset": 0, "limit": 50}

    assert asked(Chosen()) == [("chat.list", page), ("runs.list", page)]
    assert asked(Chosen(kind="chat", q="parser")) == [
        ("chat.list", {"q": "parser", **page})
    ]
    assert asked(Chosen(kind="flow", status="failed", flow="talk", workspace="/w")) == [
        ("runs.list", {"workspace": "/w", "status": "failed", "flow": "talk", **page})
    ]
    # A chat is of no flow and is not filtered by how it went: only epics are asked for.
    assert [method for method, _ in asked(Chosen(status="failed"))] == ["runs.list"]
    assert [method for method, _ in asked(Chosen(flow="talk"))] == ["runs.list"]
    # On `All`, a later page is cut out of both lists read from their first row.
    (_, chats), (_, epics) = asked(Chosen(offset=100))
    assert (chats["offset"], chats["limit"]) == (0, 150)
    assert (epics["offset"], epics["limit"]) == (0, 150)


async def test_it_lists_the_newest_of_everything_and_narrows_as_it_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        page = await _opened(pilot, daemon)

        # Chats and epics as one list, newest first, and the keys in the field.
        assert _found(page) == ["r:c-parser", "r:e-parser", "r:c-docs"]
        assert isinstance(app.focused, Input)
        assert str(page.query_one("#search-heading", Static).render()) == "RECENTS"
        assert str(page.query_one("#search-paged", Static).render()) == "1–3 of 3"  # noqa: RUF001
        hints = str(page.query_one(Hints).render())
        assert hints.startswith(
            "↑↓ Move   enter Open   tab Change type   F2 How it went"
        )
        assert hints.endswith("esc Close")

        await pilot.press(*"parser")
        await _until(pilot, lambda: _found(page) == ["r:c-parser", "r:e-parser"])
        assert str(page.query_one("#search-heading", Static).render()) == "RESULTS"
        # Asked once what was typed had settled, not a letter at a time.
        typed = [
            said.get("q") for method, said in daemon.asked if method == "chat.list"
        ]
        assert typed[-1] == "parser"
        assert "pars" not in typed


async def test_the_tabs_and_the_filters_choose_what_is_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    async with _Stands().run_test(size=(120, 30)) as pilot:
        page = await _opened(pilot, Daemon(str(tmp_path)))

        await pilot.press("tab")
        await _until(pilot, lambda: _found(page) == ["r:c-parser", "r:c-docs"])
        assert page.chosen.kind == "chat"
        assert "■ CHATS" in str(page.query_one("#search-tabs", Static).render())

        # How it went is an epic's: `Chats` gives way to `Epics`.
        await pilot.press("f2")
        assert page.chosen == Chosen(kind="flow", status="running")
        await _until(
            pilot, lambda: len(_found(page)) == 1 and "r:" not in _found(page)[0]
        )
        nothing = str(page.query_one(OptionList).get_option_at_index(0).prompt)
        assert nothing == (
            "Nothing is like that. Clear the filters to see every chat and epic."
        )

        await pilot.press("f3")
        assert page.chosen.workspace == str(tmp_path)
        await pilot.press("f4")
        assert page.chosen.flow == "@local/writes"
        filters = str(page.query_one("#search-filters", Static).render())
        assert filters == (
            f"How it went Running   Folder {tmp_path.name}   Flow @local/writes"
        )

        # Cleared, the tab stays, which is no filter.
        await pilot.press("f5")
        assert page.chosen == Chosen(kind="flow")
        await _until(pilot, lambda: _found(page) == ["r:e-parser"])
        await pilot.press("shift+tab", "shift+tab", "shift+tab")
        assert page.chosen == Chosen()


async def test_enter_opens_the_one_moved_to_and_esc_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = _Stands()
    async with app.run_test(size=(120, 30)) as pilot:
        page = await _opened(pilot, Daemon(str(tmp_path)))

        await pilot.press("down", "enter")
        await _until(pilot, lambda: bool(app.opened))
        # An epic that ended is gone into, as `/epics` goes into one.
        assert app.opened == [("epic", "e-parser", None, True)]
        assert app.screen is not page
        assert getattr(app.focused, "id", "") == "editor"

        again = await _opened(pilot, Daemon(str(tmp_path)))
        # The arrows go round the ends.
        await pilot.press("up", "enter")
        await _until(pilot, lambda: len(app.opened) == 2)
        assert app.opened[1] == ("chat", "c-docs", None)

        last = await _opened(pilot, Daemon(str(tmp_path)))
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is not last
        assert app.screen is not again
        assert len(app.opened) == 2


async def test_search_here_opens_it_in_one_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    daemon = Daemon(str(tmp_path))
    app = _Stands()
    made: list[Search] = []

    def makes(_: App[None]) -> Search:
        made.append(Search(daemon, search.VIEWS[0].make(app).chosen.workspace))  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]
        return made[-1]

    from dataclasses import replace

    from hmz.tui import shell

    view = replace(search.VIEWS[0], make=makes)
    monkeypatch.setattr(shell, "views", lambda: {"search": view})
    async with app.run_test(size=(120, 30)) as pilot:
        await search.searches(app, "/far/other")
        await pilot.pause()

        (page,) = made
        assert app.screen is page
        assert page.chosen == Chosen(workspace="/far/other")
        await _until(pilot, lambda: any(m == "chat.list" for m, _ in daemon.asked))
        assert all(
            said["workspace"] == "/far/other"
            for method, said in daemon.asked
            if method in ("chat.list", "runs.list")
        )
        # The key that opened it is the way out of it too.
        await app.shell.toggles("search")
        await pilot.pause()
        assert app.screen is not page
