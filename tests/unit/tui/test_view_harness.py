"""`hmz.tui.views.harness`: one harness session read, and continued in a chat."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, Static

from hmz import words
from hmz.tui import humanfia
from hmz.tui.selecting import Transcript
from hmz.tui.shell import Hints
from hmz.tui.views import harness
from hmz.tui.views.chips import Desk
from hmz.tui.views.harness import Session

HERE = "/w/project"

SESSION: dict[str, Any] = {
    "id": "s1",
    "harness": "codex",
    "title": "tidy the  parser",
    "workspace": HERE,
    "continuable": True,
    "trace": [
        {
            "key": "codex:s1",
            "actions": [
                {"category": "turn", "name": "turn", "args": {"prompt": "tidy it"}},
                {"category": "tool", "name": "Bash", "args": {}},
                {"category": "message", "name": "said", "args": {"text": "tidied"}},
            ],
        },
        {"key": "codex:empty", "actions": []},
    ],
}


class Daemon:
    """What stands in for the daemon: answers by method, and keeps every call."""

    def __init__(self, **answers: Any) -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.answers: dict[str, Any] = {
            "chat.harness.get": SESSION,
            "chat.harness.adopt": {"chat": "c7"},
            **answers,
        }

    def __call__(self, method: str, **said: Any) -> dict[str, Any]:
        self.asked.append((method, said))
        answer = self.answers.get(method, {})
        if isinstance(answer, Exception):
            raise answer
        return dict(answer)

    def calls(self, method: str) -> list[dict[str, Any]]:
        return [said for name, said in self.asked if name == method]


class _Stands(App[None]):
    """An interface that is a prompt, with the page put over it."""

    def __init__(self, page: Session) -> None:
        super().__init__()
        self._page = page
        self.answered: list[str | None] = []

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Input(id="editor")

    async def on_mount(self) -> None:
        await self.push_screen(self._page, self.answered.append)


async def _settled(pilot: Any) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def _note(app: App[Any]) -> str:
    return str(app.screen.query_one("#note", Static).render())


async def test_the_page_draws_what_was_said_and_offers_continue_in_chat() -> None:
    daemon = Daemon()
    page = Session(Desk(asks=daemon, workspace=HERE), HERE, "codex", "s1")
    async with _Stands(page).run_test(size=(120, 30)) as pilot:
        await _settled(pilot)
        said = pilot.app.screen.query_one(Transcript).text

        assert said.splitlines() == ["❯ tidy it", "  ▸ Bash", "tidied"]
        sub = str(pilot.app.screen.query_one("#sub", Static).render())
        assert "tidy the parser" in sub
        assert "Codex" in sub
        assert _note(pilot.app) == (
            "Read-only. Continuing copies it into a chat here; the Codex session "
            "stays as it is.  ■ Continue in chat"
        )
        assert str(pilot.app.screen.query_one(Hints).render()) == (
            "↑↓ Scroll   enter Continue in chat   esc Back"
        )
    assert daemon.calls("chat.harness.get") == [
        {"workspace": HERE, "harness": "codex", "session": "s1", "trace": True}
    ]


async def test_enter_continues_it_in_a_chat_and_goes_to_that_chat() -> None:
    went: list[tuple[str, str]] = []
    daemon = Daemon()
    at = Desk(
        asks=daemon,
        workspace=HERE,
        follows=lambda chat, slot: went.append((chat, slot)),
    )
    app = _Stands(Session(at, HERE, "codex", "s1"))
    async with app.run_test(size=(120, 30)) as pilot:
        await _settled(pilot)
        await pilot.press("enter")
        await _settled(pilot)

        assert not isinstance(app.screen, Session)
    assert daemon.calls("chat.harness.adopt") == [
        {"workspace": HERE, "harness": "codex", "session": "s1"}
    ]
    assert went == [("c7", "")]
    assert app.answered == ["c7"]


async def test_a_session_that_cannot_be_continued_says_so_and_enter_does_nothing() -> (
    None
):
    daemon = Daemon(
        **{"chat.harness.get": {**SESSION, "harness": "kimi", "continuable": False}}
    )
    page = Session(Desk(asks=daemon, workspace=HERE), HERE, "kimi", "s1")
    async with _Stands(page).run_test(size=(120, 30)) as pilot:
        await _settled(pilot)
        await pilot.press("enter")
        await _settled(pilot)

        assert isinstance(pilot.app.screen, Session)
        assert _note(pilot.app) == (
            "Read-only. A session of Kimi Code cannot be continued in a chat."
        )
    assert daemon.calls("chat.harness.adopt") == []


async def test_a_refusal_to_continue_is_said_and_the_page_stays() -> None:
    daemon = Daemon(**{"chat.harness.adopt": OSError("its files cannot be copied")})
    page = Session(Desk(asks=daemon, workspace=HERE), HERE, "codex", "s1")
    async with _Stands(page).run_test(size=(120, 30)) as pilot:
        await _settled(pilot)
        await pilot.press("enter")
        await _settled(pilot)

        assert isinstance(pilot.app.screen, Session)
        assert _note(pilot.app) == "its files cannot be copied"


async def test_a_session_whose_logs_hold_nothing_says_so() -> None:
    daemon = Daemon(**{"chat.harness.get": {**SESSION, "trace": []}})
    page = Session(Desk(asks=daemon, workspace=HERE), HERE, "codex", "s1")
    async with _Stands(page).run_test(size=(120, 30)) as pilot:
        await _settled(pilot)

        assert pilot.app.screen.query_one(Transcript).text == (
            "Its logs held nothing said."
        )


async def test_opened_on_no_session_it_reads_the_newest_of_the_folder() -> None:
    daemon = Daemon(
        **{"chat.harness.list": {"sessions": [{"id": "s9", "harness": "claude"}]}}
    )
    async with _Stands(Session(Desk(asks=daemon, workspace=HERE))).run_test(
        size=(120, 30)
    ) as pilot:
        await _settled(pilot)

    assert daemon.calls("chat.harness.list") == [{"workspace": HERE, "limit": 1}]
    assert daemon.calls("chat.harness.get")[0]["session"] == "s9"


async def test_a_folder_with_no_session_says_so() -> None:
    daemon = Daemon(**{"chat.harness.list": {"sessions": []}})
    async with _Stands(Session(Desk(asks=daemon, workspace=HERE))).run_test(
        size=(120, 30)
    ) as pilot:
        await _settled(pilot)

        assert _note(pilot.app) == "No harness session in this folder."
    assert daemon.calls("chat.harness.get") == []


async def test_esc_closes_the_page_with_nothing_continued() -> None:
    app = _Stands(Session(Desk(asks=Daemon(), workspace=HERE), HERE, "codex", "s1"))
    async with app.run_test(size=(120, 30)) as pilot:
        await _settled(pilot)
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, Session)
    assert app.answered == [None]


async def test_the_module_opens_the_page_for_one_session() -> None:
    class Bare(App[None]):
        def get_css_variables(self) -> dict[str, str]:
            return {**humanfia.FALLBACK, **super().get_css_variables()}

    app = Bare()
    async with app.run_test(size=(120, 30)) as pilot:
        await harness.opens(app, HERE, "codex", "s1")
        await pilot.pause()

        assert isinstance(app.screen, Session)


def test_the_view_is_a_page_opened_by_name_and_aimed_at_a_session() -> None:
    (view,) = harness.VIEWS

    assert (view.name, view.zone, view.title, view.key) == (
        "harness",
        "page",
        "Harness session",
        "",
    )
    assert all(words.known(does) for _, does in view.keys)
    harness.aim(HERE, "codex", "s1")
    assert isinstance(view.make(App()), Session)
