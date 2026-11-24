"""`hmz.tui.views.chips`: a chat's chips as plain values, and the Details view of one chat."""

from __future__ import annotations

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList

from hmz import words
from hmz.tui import humanfia
from hmz.tui.chats import Deletes
from hmz.tui.dropdown import Dropdown
from hmz.tui.views import chips
from hmz.tui.views.chips import Chips, Desk, Nous, Place

CLIS: dict[str, Any] = {
    "claude": {
        "accounts": [
            {
                "name": "",
                "asked": True,
                "models": [
                    {"name": "fable", "efforts": ["low", "high"]},
                    {"name": "haiku", "efforts": []},
                ],
            },
            {
                "name": "work",
                "asked": True,
                "models": [{"name": "opus", "efforts": ["max"]}],
            },
        ]
    },
    "codex": {"accounts": [{"name": "", "asked": False, "models": []}]},
    "grok": {"accounts": [{"name": "", "asked": True, "models": []}]},
}

CHAT = {
    "id": "c1",
    "title": "Fix the  parser",
    "workspace": "/w/project",
    "env": "local/w/project",
    "agent": "claude/fable:high",
    "state": "turn",
    "slot": "chat:ab12",
    "permission": "workspace-write",
    "prefer": "",
    "spent": {"money": "$0.12", "tokens": "1,200", "worked": "3s"},
}


class Daemon:
    """What stands in for the daemon: answers by method, and keeps every call."""

    def __init__(self, **answers: Any) -> None:
        self.asked: list[tuple[str, dict[str, Any]]] = []
        self.chat = dict(CHAT)
        self.answers: dict[str, Any] = {
            "flows.backends": {"clis": CLIS},
            "runs.usage": {"whole": {"money": "$1.50", "tokens": "9,000", "runs": 2}},
            "runtimes.list": {"runtimes": [{"backend": "ssh", "name": "box"}]},
            "paths.list": {"at": "~", "whole": "/home/me", "up": "", "entries": []},
            **answers,
        }

    def __call__(self, method: str, **said: Any) -> dict[str, Any]:
        self.asked.append((method, said))
        if method == "chat.get":
            return dict(self.chat)
        if method == "chat.agent":
            self.chat["agent"] = said["agent"]
            return dict(self.chat)
        if method == "chat.set":
            self.chat.update(
                {k: v for k, v in said.items() if k in ("permission", "prefer")}
            )
            return {}
        answer = self.answers.get(method, {})
        if isinstance(answer, Exception):
            raise answer
        return dict(answer)

    def calls(self, method: str) -> list[dict[str, Any]]:
        return [said for name, said in self.asked if name == method]


class _Stands(App[None]):
    """An interface that is the view and a prompt, and nothing else."""

    def __init__(self, at: Desk) -> None:
        super().__init__()
        self._at = at

    def get_css_variables(self) -> dict[str, str]:
        return {**humanfia.FALLBACK, **super().get_css_variables()}

    def compose(self) -> ComposeResult:
        yield Input(id="editor")
        yield Chips(self._at)


def _drawn(app: App[Any]) -> str:
    return "\n".join(str(one.prompt) for one in app.query_one(Chips).options)


async def _settled(pilot: Any) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def _picks(
    pilot: Any, value: str | None, *, more: bool = False
) -> tuple[str, list[str]]:
    """Takes one value of the list dropped; answers its title and the values it offered."""
    for _ in range(50):
        if isinstance(pilot.app.screen, Dropdown):
            break
        await pilot.pause(0.01)
    dropped = pilot.app.screen
    assert isinstance(dropped, Dropdown)
    listing = dropped.query_one(OptionList)
    offered = [str(one.id).removeprefix("=") for one in listing.options if one.id]
    title = str(listing.border_title)
    dropped.dismiss(value)
    await pilot.pause()
    if not more:  # another list is dropped next, which what changes the chip waits on
        await _settled(pilot)
    return title, offered


async def _onto(pilot: Any, row: str) -> None:
    listing = pilot.app.query_one(Chips)
    listing.focus()
    listing.highlighted = listing.get_option_index(row)
    await pilot.pause()


def test_an_agent_is_taken_apart_and_put_back_as_a_command_line_spells_it() -> None:
    assert chips.parted("claude@work/opus:max") == Nous("claude", "work", "opus", "max")
    assert chips.parted("codex/llama3:8b:auto") == Nous(
        "codex", "", "llama3:8b", "auto"
    )
    assert chips.parted("nothing") == Nous()
    assert (
        chips.spelled(Nous("claude", "work", "opus", "max")) == "claude@work/opus:max"
    )
    assert chips.spelled(Nous("claude", "", "fable", "auto")) == "claude/fable:auto"
    assert chips.spelled(Nous("claude")) == ""


def test_every_text_a_chip_names_a_value_by_is_one_of_the_words() -> None:
    said = [
        *(one.label for one in chips.MODES),
        *(one.about for one in chips.MODES),
        *(pair[1] for pair in Chips.KEYS),
    ]

    assert [one for one in said if not words.known(one)] == []
    assert chips.effort_name("") == "Default"
    assert chips.effort_name("auto") == "Default"
    assert chips.effort_name("xhigh") == "Extra high"
    assert chips.effort_name("max") == "Max"
    assert chips.effort_name("turbo") == "turbo"
    assert chips.harness_name("claude") == "Claude Code"
    assert chips.harness_name("mine") == "mine"


def test_the_permissions_are_the_three_presets_narrowest_first() -> None:
    offered = chips.modes_offered()

    assert [one.value for one in offered[:3]] == [
        "read-only",
        "workspace-write",
        "danger-full-access",
    ]
    assert [one.label for one in offered[:3]] == [
        "Read only",
        "Edit this folder",
        "Full access",
    ]
    assert offered[3].inert
    assert chips.mode_of("").value == chips.DEFAULT == "workspace-write"
    assert chips.mode_of("read-only").label == "Read only"


def test_the_models_are_offered_a_group_a_harness_with_what_is_missing_said() -> None:
    offered = chips.nous_offered(CLIS, Nous("claude", "", "fable"))

    assert [(one.value, one.label, one.group) for one in offered[:2]] == [
        ("claude/fable:auto", "fable", "Claude Code"),
        ("claude/haiku:auto", "haiku", "Claude Code"),
    ]
    # One nobody has asked is asked by picking it; one that lists none says so.
    assert offered[2].value == f"{chips.UNASKED}codex@"
    assert (offered[2].label, offered[2].inert) == ("Not asked yet", False)
    assert (offered[3].label, offered[3].inert) == ("No models listed", True)


def test_a_chat_that_is_open_is_offered_only_its_own_harness_and_account() -> None:
    offered = chips.nous_offered(CLIS, Nous("claude", "work", "typed"), only=True)

    assert [one.value for one in offered] == [
        "claude@work/opus:auto",
        "claude@work/typed:auto",
    ]
    assert {one.group for one in offered} == {"Claude Code"}


def test_the_efforts_offered_are_those_the_model_takes_after_its_own() -> None:
    offered = chips.efforts_offered(CLIS, Nous("claude", "", "fable"))

    assert [(one.value, one.label) for one in offered] == [
        ("auto", "Default"),
        ("low", "Low"),
        ("high", "High"),
    ]
    assert [one.value for one in chips.efforts_offered(CLIS, Nous("x", "", "y"))] == [
        "auto"
    ]


def test_where_a_chat_works_is_said_and_offered_as_the_page_does() -> None:
    assert chips.env_said("") == "This computer"
    assert chips.env_said("local/w/project") == "This computer, project"
    assert chips.env_said("", worktree=True) == "New worktree"
    assert chips.env_said("ssh@box/srv") == "ssh@box/srv"

    runtimes = [{"backend": "ssh", "name": "box"}, {"backend": "docker", "name": ""}]
    fresh = chips.envs_offered(runtimes, "/w/project", worktree="")
    assert [(one.value, one.label, one.group) for one in fresh] == [
        ("local", "This computer", ""),
        ("worktree", "New worktree", ""),
        ("ssh@box", "box", "Runtimes"),
        ("docker", "Docker container", "Runtimes"),
    ]
    assert fresh[0].about == "In the folder project"
    refused = chips.envs_offered([], "/w/project", worktree="no git here")
    assert (refused[1].inert, refused[1].about) == (True, "no git here")
    # A chat that is open is moved, and a move makes no worktree.
    assert [one.value for one in chips.envs_offered([], "/w/project")] == ["local"]


async def test_the_view_says_there_is_no_chat_where_none_is_on_the_screen() -> None:
    daemon = Daemon()
    async with _Stands(Desk(asks=daemon)).run_test(size=(60, 30)) as pilot:
        await _settled(pilot)

        assert "No chat here" in _drawn(pilot.app)
        assert daemon.asked == []


async def test_the_view_draws_the_chat_its_chips_and_what_it_has_used() -> None:
    daemon = Daemon()
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        drawn = _drawn(pilot.app)
        listing = pilot.app.query_one(Chips)
        # The cursor opens on the first chip, and the arrows walk the chips.
        assert listing.get_option_at_index(listing.highlighted or 0).id == "model"
        listing.focus()
        await pilot.press("down")
        assert listing.get_option_at_index(listing.highlighted or 0).id == "effort"

    assert "Fix the parser" in drawn
    for said in (
        "Claude Code",
        "fable",
        "High",
        "Edit this folder",
        "This computer",
        "$0.12",
        "1,200",
        "$1.50",
        "Rename…",
        "Fork",
        "Archive",
        "Delete chat",
    ):
        assert said in drawn, said
    assert daemon.calls("chat.get") == [{"chat": "c1"}]
    assert daemon.calls("runs.usage") == [{"days": 7, "workspace": "/w/project"}]


async def test_an_effort_picked_is_asked_of_the_daemon_as_the_chats_agent() -> None:
    daemon = Daemon()
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        await _onto(pilot, "effort")
        await pilot.press("enter")
        title, offered = await _picks(pilot, "low")

        assert (title, offered) == ("EFFORT", ["auto", "low", "high"])
        assert daemon.calls("chat.agent") == [
            {"chat": "c1", "agent": "claude/fable:low"}
        ]
        assert "Low" in _drawn(pilot.app)


async def test_a_model_picked_keeps_the_effort_only_where_the_model_takes_it() -> None:
    daemon = Daemon()
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        await _onto(pilot, "model")
        await pilot.press("enter")
        await _picks(pilot, "claude/haiku:auto")

    assert daemon.calls("chat.agent") == [{"chat": "c1", "agent": "claude/haiku:auto"}]


async def test_a_permission_picked_is_set_on_the_host_holding_the_chat() -> None:
    daemon = Daemon()
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        await _onto(pilot, "permission")
        await pilot.press("enter")
        await _picks(pilot, "read-only")

        assert daemon.calls("chat.set") == [
            {"workspace": "/w/project", "slot": "chat:ab12", "permission": "read-only"}
        ]
        assert "Read only" in _drawn(pilot.app)


async def test_a_chat_no_host_holds_is_carried_on_with_nothing_said_to_be_set() -> None:
    went: list[tuple[str, str]] = []
    daemon = Daemon(**{"chat.start": {"slot": "chat:new", "chat": "c1"}})
    daemon.chat["slot"] = ""
    at = Desk(
        asks=daemon,
        chat=lambda: "c1",
        follows=lambda chat, slot: went.append((chat, slot)),
    )
    async with _Stands(at).run_test(size=(60, 40)) as pilot:
        await _settled(pilot)
        await _onto(pilot, "prefer")
        await pilot.press("enter")
        await _picks(pilot, "flow")

    assert daemon.calls("chat.start") == [
        {"workspace": "/w/project", "resume": "c1", "task": ""}
    ]
    assert went == [("c1", "chat:new")]
    assert daemon.calls("chat.set") == [
        {"workspace": "/w/project", "slot": "chat:new", "prefer": "flow"}
    ]


async def test_a_chat_is_moved_to_the_runtime_picked() -> None:
    daemon = Daemon(**{"chat.move": {"env": "ssh@box"}})
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        await _onto(pilot, "env")
        await pilot.press("enter")
        _, listed = await _picks(pilot, "ssh@box", more=True)
        # Then the directory there: none picked is the runtime's own.
        await _picks(pilot, None)

    assert listed == ["local", "ssh@box"]
    assert daemon.calls("paths.list") == [{"at": "~", "env": "ssh@box"}]
    assert daemon.calls("chat.move") == [
        {"workspace": "/w/project", "slot": "chat:ab12", "env": "ssh@box"}
    ]


async def test_a_refusal_is_said_in_the_view_and_nothing_else_changes() -> None:
    daemon = Daemon(**{"chat.fork": OSError("a turn is open")})
    went: list[tuple[str, str]] = []
    at = Desk(
        asks=daemon,
        chat=lambda: "c1",
        follows=lambda chat, slot: went.append((chat, slot)),
    )
    async with _Stands(at).run_test(size=(60, 40)) as pilot:
        await _settled(pilot)
        await _onto(pilot, "fork")
        await pilot.press("enter")
        await _settled(pilot)

        assert "a turn is open" in _drawn(pilot.app)
    assert went == []


async def test_a_fork_is_gone_to_and_an_archived_chat_is_left_for_a_new_one() -> None:
    daemon = Daemon(**{"chat.fork": {"chat": "c2"}, "chat.archive": dict(CHAT)})
    went: list[tuple[str, str]] = []
    cleared: list[bool] = []
    at = Desk(
        asks=daemon,
        chat=lambda: "c1",
        follows=lambda chat, slot: went.append((chat, slot)),
        clears=lambda: cleared.append(True),
    )
    async with _Stands(at).run_test(size=(60, 40)) as pilot:
        await _settled(pilot)
        await _onto(pilot, "fork")
        await pilot.press("enter")
        await _settled(pilot)
        await _onto(pilot, "archive")
        await pilot.press("enter")
        await _settled(pilot)

    assert went == [("c2", "")]
    assert daemon.calls("chat.archive") == [{"chat": "c1"}]
    assert cleared == [True]


@pytest.mark.parametrize(("answer", "deleted"), [("no", False), ("yes", True)])
async def test_deleting_asks_first_and_names_the_chat(
    answer: str,
    deleted: bool,
) -> None:
    daemon = Daemon()
    cleared: list[bool] = []
    at = Desk(asks=daemon, chat=lambda: "c1", clears=lambda: cleared.append(True))
    async with _Stands(at).run_test(size=(80, 40)) as pilot:
        await _settled(pilot)
        await _onto(pilot, "delete")
        await pilot.press("enter")
        for _ in range(50):
            if isinstance(pilot.app.screen, Deletes):
                break
            await pilot.pause(0.01)
        sheet = pilot.app.screen
        assert isinstance(sheet, Deletes)
        assert sheet.asked == "Delete Fix the parser?"
        assert daemon.calls("chat.delete") == []
        sheet.dismiss(answer)
        await pilot.pause()
        await _settled(pilot)

    assert daemon.calls("chat.delete") == ([{"chat": "c1"}] if deleted else [])
    assert cleared == ([True] if deleted else [])


def test_the_view_is_details_in_the_context_on_ctrl_g() -> None:
    (view,) = chips.VIEWS

    assert (view.name, view.zone, view.title, view.key) == (
        "chips",
        "context",
        "Details",
        "ctrl+g",
    )
    assert view.keys == (("↑↓", "move"), ("enter", "choose"))
    assert isinstance(Place(), tuple)


async def test_this_computer_picked_for_a_chat_already_on_it_moves_nothing() -> None:
    daemon = Daemon()
    daemon.chat["env"] = "local/w/project/.worktrees/one"
    async with _Stands(Desk(asks=daemon, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        await _onto(pilot, "env")
        await pilot.press("enter")
        await _picks(pilot, "local")

    assert daemon.calls("chat.move") == []
    assert daemon.calls("chat.start") == []


async def test_a_failure_to_read_the_chat_is_unsaid_once_it_is_read_again() -> None:
    daemon = Daemon()
    real, failing = daemon.__call__, [True]

    def asks(method: str, **said: Any) -> dict[str, Any]:
        if method == "chat.get" and failing[0]:
            raise OSError("the daemon went away")
        return real(method, **said)

    async with _Stands(Desk(asks=asks, chat=lambda: "c1")).run_test(
        size=(60, 40)
    ) as pilot:
        await _settled(pilot)
        assert "the daemon went away" in _drawn(pilot.app)

        failing[0] = False
        await pilot.pause(4.2)
        await _settled(pilot)
        assert "the daemon went away" not in _drawn(pilot.app)
        assert "Fix the parser" in _drawn(pilot.app)
