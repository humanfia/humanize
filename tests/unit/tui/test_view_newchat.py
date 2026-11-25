"""`hmz.tui.views.newchat`: the New chat page -- chips, the first message, what waits."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static

from hmz import words
from hmz.tui import humanfia
from hmz.tui.dropdown import Dropdown
from hmz.tui.shell import Hints
from hmz.tui.views import newchat
from hmz.tui.views.chips import Desk, Start
from hmz.tui.views.harness import Session
from hmz.tui.views.newchat import Chip, NewChat

HERE = "/w/project"

CLIS = {
    "claude": {
        "accounts": [
            {
                "name": "",
                "asked": True,
                "models": [{"name": "fable", "efforts": ["low", "high"]}],
            }
        ]
    }
}


class Daemon:
    """What stands in for the daemon: answers by method, and keeps every call."""

    def __init__(self, **answers: Any) -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.answers: dict[str, Any] = {
            "settings.get": {"chat": "claude/fable:high", "harness_sessions": True},
            "flows.backends": {"clis": CLIS},
            "chat.list": {"chats": []},
            "chat.harness.list": {"sessions": []},
            "runtimes.list": {"runtimes": []},
            "workspaces.list": {
                "workspaces": [
                    {"path": HERE, "name": "project", "there": True},
                    {"path": "/w/other", "name": "other", "there": True},
                    {"path": "/w/gone", "name": "gone", "there": False},
                ]
            },
            "paths.list": {
                "at": HERE,
                "whole": HERE,
                "up": "/w",
                "entries": [{"name": ".git", "dir": True}],
            },
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

    def __init__(self, at: Desk) -> None:
        super().__init__()
        self._at = at

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Input(id="editor")

    async def on_mount(self) -> None:
        await self.push_screen(NewChat(self._at))


def _desk(daemon: Daemon, **more: Any) -> Desk:
    return Desk(asks=daemon, workspace=HERE, **more)


async def _settled(pilot: Any) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


def _chip(app: App[Any], name: str) -> str:
    return str(app.screen.query_one(f"#{name}", Chip).render())


async def _picks(pilot: Any, value: str | None, *, more: bool = False) -> list[str]:
    """Takes one value of the list dropped, and answers the values it offered."""
    for _ in range(50):
        if isinstance(pilot.app.screen, Dropdown):
            break
        await pilot.pause(0.01)
    dropped = pilot.app.screen
    assert isinstance(dropped, Dropdown)
    listing = dropped.query_one(OptionList)
    offered = [str(one.id).removeprefix("=") for one in listing.options if one.id]
    dropped.dismiss(value)
    await pilot.pause()
    if not more:
        await _settled(pilot)
    return offered


async def test_the_page_opens_on_the_message_with_the_defaults_said_on_its_chips() -> (
    None
):
    daemon = Daemon()
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        app = pilot.app

        assert isinstance(app.focused, Input)
        assert app.focused.id == "message"
        assert _chip(app, "folder") == "FOLDER project"
        assert _chip(app, "environment") == "ENVIRONMENT This computer"
        assert _chip(app, "model") == "MODEL Claude Code fable"
        assert _chip(app, "effort") == "EFFORT High"
        assert _chip(app, "permission") == "PERMISSIONS Edit this folder"
        assert str(app.screen.query_one("#go", Static).render()) == "■ Start"
        assert str(app.screen.query_one(Hints).render()) == (
            "tab Next   shift+tab Previous   enter Start   esc Back"
        )
        assert daemon.calls("settings.get") == [{"workspace": HERE}]


async def test_with_no_agent_remembered_the_first_model_listed_is_the_default() -> None:
    daemon = Daemon(**{"settings.get": {"chat": ""}})
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)

        assert _chip(pilot.app, "model") == "MODEL Claude Code fable"
        assert _chip(pilot.app, "effort") == "EFFORT Default"


async def test_tab_walks_the_chips_and_the_message_and_the_hint_says_what_enter_does() -> (
    None
):
    async with _Stands(_desk(Daemon())).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        app = pilot.app
        walked: list[str] = []
        for _ in range(6):
            await pilot.press("tab")
            walked.append(str(getattr(app.focused, "id", "")))

        assert walked == [
            "folder",
            "environment",
            "model",
            "effort",
            "permission",
            "message",
        ]
        await pilot.press("shift+tab")
        assert getattr(app.focused, "id", "") == "permission"
        assert "enter Choose" in str(app.screen.query_one(Hints).render())


async def test_enter_in_the_message_starts_the_chat_with_what_the_chips_say() -> None:
    started: list[Start] = []
    daemon = Daemon()
    at = _desk(daemon, starts=started.append)
    async with _Stands(at).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("shift+tab", "enter")
        offered = await _picks(pilot, "read-only")
        await pilot.press("shift+tab", "enter")
        await _picks(pilot, "low")
        assert _chip(pilot.app, "permission") == "PERMISSIONS Read only"

        pilot.app.screen.query_one("#message", Input).focus()
        await pilot.press(*"fix it", "enter")
        await pilot.pause()

        assert not isinstance(pilot.app.screen, NewChat)
    assert offered == ["read-only", "workspace-write", "danger-full-access"]
    assert started == [Start("fix it", "claude/fable:low", "read-only", "", False)]
    assert daemon.calls("chat.start") == []


async def test_nothing_typed_starts_nothing() -> None:
    started: list[Start] = []
    async with _Stands(_desk(Daemon(), starts=started.append)).run_test(
        size=(140, 40)
    ) as pilot:
        await _settled(pilot)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(pilot.app.screen, NewChat)
    assert started == []


async def test_a_new_worktree_is_offered_in_a_repository_and_started_with() -> None:
    started: list[Start] = []
    async with _Stands(_desk(Daemon(), starts=started.append)).run_test(
        size=(140, 40)
    ) as pilot:
        await _settled(pilot)
        await pilot.press("tab", "tab", "enter")
        offered = await _picks(pilot, "worktree")
        assert _chip(pilot.app, "environment") == "ENVIRONMENT New worktree"

        pilot.app.screen.query_one("#message", Input).focus()
        await pilot.press("x", "enter")
        await pilot.pause()

    assert offered == ["local", "worktree"]
    assert started == [Start("x", "claude/fable:high", "workspace-write", "", True)]


async def test_a_folder_that_is_no_repository_is_offered_no_worktree() -> None:
    daemon = Daemon(
        **{"paths.list": {"at": HERE, "whole": HERE, "up": "", "entries": []}}
    )
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("tab", "tab", "enter")
        offered = await _picks(pilot, None)

        assert offered == ["local"]
        assert _chip(pilot.app, "environment") == "ENVIRONMENT This computer"


async def test_a_chat_of_another_folder_is_started_there_and_said_in_the_log() -> None:
    started: list[Start] = []
    said: list[str] = []
    daemon = Daemon(**{"chat.start": {"slot": "chat:1", "chat": "c9"}})
    at = _desk(daemon, starts=started.append, says=said.append)
    async with _Stands(at).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("tab", "enter")
        offered = await _picks(pilot, "/w/other")
        assert _chip(pilot.app, "folder") == "FOLDER other"
        # What that folder remembers is read for it.
        assert daemon.calls("settings.get")[-1] == {"workspace": "/w/other"}

        pilot.app.screen.query_one("#message", Input).focus()
        await pilot.press("x", "enter")
        await _settled(pilot)

        assert not isinstance(pilot.app.screen, NewChat)
    # A folder that is gone is not offered; browsing for another is.
    assert offered == [HERE, "/w/other", "…"]
    assert started == []
    assert daemon.calls("chat.start") == [
        {
            "workspace": "/w/other",
            "agent": "claude/fable:high",
            "task": "x",
            "permission": "workspace-write",
            "worktree": False,
            "env": None,
            "remember": True,
        }
    ]
    assert said == [
        "The chat was started in /w/other. Open hmz in that folder to read it."
    ]


async def test_a_start_refused_there_is_said_on_the_page_which_stays() -> None:
    daemon = Daemon(**{"chat.start": OSError("no room")})
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("tab", "enter")
        await _picks(pilot, "/w/other")
        pilot.app.screen.query_one("#message", Input).focus()
        await pilot.press("x", "enter")
        await _settled(pilot)

        assert isinstance(pilot.app.screen, NewChat)
        assert str(pilot.app.screen.query_one("#said", Static).render()) == "no room"


async def test_what_waits_on_its_person_is_listed_first_then_harness_sessions() -> None:
    went: list[tuple[str, str]] = []
    daemon = Daemon(
        **{
            "chat.list": {
                "chats": [
                    {"id": "c1", "title": "quiet", "state": "resting", "asking": []},
                    {
                        "id": "c2",
                        "title": "which colour",
                        "state": "asking",
                        "slot": "chat:7",
                        "asking": ["1:q"],
                    },
                ]
            },
            "chat.harness.list": {
                "sessions": [{"id": "s1", "harness": "codex", "title": "old work"}]
            },
        }
    )

    def follows(chat: str, slot: str) -> None:
        went.append((chat, slot))

    at = _desk(daemon, follows=follows)
    async with _Stands(at).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        listing = pilot.app.screen.query_one("#waiting", OptionList)
        drawn = [str(one.prompt) for one in listing.options]

        assert "WAITING FOR YOU" in drawn[0]
        assert "which colour" in drawn[1]
        assert "Asked a question" in drawn[1]
        assert "HARNESS SESSIONS" in drawn[2]
        assert "old work" in drawn[3]
        assert "Codex session" in drawn[3]
        assert not any("quiet" in one for one in drawn)
        assert daemon.calls("chat.list") == [{"workspace": HERE, "limit": 200}]

        # From the message, tab goes on to the list, and enter opens the chat that waits.
        await pilot.press("tab")
        assert pilot.app.focused is listing
        assert "enter Open" in str(pilot.app.screen.query_one(Hints).render())
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(pilot.app.screen, NewChat)
    assert went == [("c2", "chat:7")]


async def test_a_harness_session_picked_is_read_on_its_own_page() -> None:
    daemon = Daemon(
        **{
            "chat.harness.list": {
                "sessions": [{"id": "s1", "harness": "codex", "title": "old work"}]
            },
            "chat.harness.get": {"id": "s1", "harness": "codex", "trace": []},
        }
    )
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("tab", "enter")
        await pilot.pause()
        await pilot.pause()

        assert isinstance(pilot.app.screen, Session)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(pilot.app.screen, NewChat)
    assert daemon.calls("chat.harness.get") == [
        {"workspace": HERE, "harness": "codex", "session": "s1", "trace": True}
    ]


async def test_harness_sessions_are_not_listed_where_the_setting_says_not() -> None:
    daemon = Daemon(**{"settings.get": {"chat": "", "harness_sessions": False}})
    async with _Stands(_desk(daemon)).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)

    assert daemon.calls("chat.list") == [{"workspace": HERE, "limit": 200}]
    assert daemon.calls("chat.harness.list") == []


async def test_the_chips_are_stacked_where_a_row_of_them_would_not_fit() -> None:
    async with _Stands(_desk(Daemon())).run_test(size=(80, 24)) as pilot:
        await _settled(pilot)
        chips = pilot.app.screen.query_one("#chips")

        assert chips.has_class("-stacked")
        tops = [one.region.y for one in chips.query(Chip)]
        assert tops == sorted(set(tops))


async def test_esc_closes_the_page() -> None:
    async with _Stands(_desk(Daemon())).run_test(size=(140, 40)) as pilot:
        await _settled(pilot)
        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(pilot.app.screen, NewChat)


def test_the_view_is_a_page_on_ctrl_n_whose_texts_are_the_pages() -> None:
    (view,) = newchat.VIEWS

    assert (view.name, view.zone, view.title, view.key, view.hint) == (
        "newchat",
        "page",
        "New chat",
        "ctrl+n",
        "New chat",
    )
    assert all(words.known(does) for _, does in view.keys)
