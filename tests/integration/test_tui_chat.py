"""A chat, read as Claude Code reads one: one conversation, running or done, never ended.

And as many of them as there are: each is a chat of its own and no epic, on a host of its own,
which goes on while another is had and folds away once nobody has looked at it for a while --
and is carried on, the same chat, from `/resume`. `/stop` interrupts its open turn. A flow
started from it goes on the workspace's own host, and `/chat` comes back to it. What its
harness takes at its own prompt -- a command, a skill, a shell command -- it takes too, and
`/prefer` says which a `$` name that is both a skill and a flow starts. The daemon's chats
are stood in for (:class:`Chats`).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz import config
from hmz import daemon as daemons
from hmz.daemon.reach import Conversations
from hmz.runtime.epic import Ran, chats, epics, read
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.chats import Resumes
from hmz.tui.envs import Envs
from hmz.tui.flows import Flows
from hmz.tui.monitoring import Monitoring
from tests.integration.doubles_tui import (
    MODEL,
    OWN,
    PRINTED,
    RUNS,
    SIZE,
    Chats,
    claude_logged,
    folds_fast,
    heard,
    leaves,
    on,
    onto,
    opened,
    opens,
    own_flow,
    rows,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
    status,
    typed,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = pytest.mark.usefixtures("daemon", "loops")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Path:
    """The stand-in `claude` on `PATH`, really asked what it runs as the interface opens."""
    del asking
    return stand_in(tmp_path, monkeypatch)


async def test_a_chat_is_running_while_the_assistant_answers_and_done_after(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")

        drawn = await shows(pilot, "still on it", "running…")
        assert "stop" not in status(drawn)
        assert "monitor" not in status(drawn)

        await typed(pilot, "now")

        drawn = await shows(pilot, "heard wait for it then now", "◉ done")
        assert "waiting for you" not in drawn
        assert "outworlder" not in drawn
    assert heard(workspace) == ["wait for it", "now"]


async def test_tool_rows_shown_in_detail_are_drawn_as_written_and_again_on_a_resize(
    workspace: Path, tmp_path: Path
) -> None:
    home = config()
    home.mkdir(parents=True, exist_ok=True)
    (home / "settings.toml").write_text("details = true\n")
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "tools")
        rows = ("Agent(look around) started", "Bash(foo\\ bar)", "heard tools")
        await shows(pilot, *rows)

        # Drawn again from what was kept, at the new width: what a row was written with is
        # read a second time, and a row that was not markup would fail every redraw after.
        await pilot.resize_terminal(SIZE[0] - 10, SIZE[1])

        await shows(pilot, *rows)


def holds_the_start(
    monkeypatch: pytest.MonkeyPatch, *, refusing: bool = False
) -> threading.Event:
    """Holds every `chat.start` until the event answered is set, refused if `refusing`."""
    chats = Chats().install(monkeypatch)
    chats.starting = threading.Event()
    chats.refusing = refusing
    return chats.starting


async def test_a_chat_says_it_is_starting_until_it_has_started(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    let_go = holds_the_start(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")

        drawn = await shows(pilot, "starting…")
        assert "starting…" in status(drawn)
        assert f"◉ {RUNS}" not in drawn

        let_go.set()
        drawn = await shows(pilot, "heard hello", "◉ done")
        assert "starting…" not in drawn
    del workspace


async def test_a_refused_start_puts_the_status_line_back_at_rest(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    let_go = holds_the_start(monkeypatch, refusing=True)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "starting…")

        let_go.set()
        drawn = await shows(pilot, "no room to start", f"◉ {RUNS}")
        assert "starting…" not in drawn
    del workspace


async def test_ctrl_c_never_stops_a_chat_and_twice_leaves(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await pilot.press(*"half")
        await pilot.press("ctrl+c")
        await until(pilot, lambda: "❯ half" not in screen(app), "the line to clear")
        await pilot.press("ctrl+c")
        await shows(pilot, "press ctrl+c again to exit", "ctrl+c again to exit")
        assert "stopping" not in screen(app)
        await typed(pilot, "still here")
        await shows(pilot, "heard wait for it then still here")

        await pilot.press("ctrl+c", "ctrl+c")

        await until(pilot, lambda: not app.is_running, "the interface to close")


async def test_a_chat_offers_no_monitor_or_views_and_stop_interrupts_its_turn(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await pilot.press("left")
        await pilot.press("tab")
        await pilot.press("shift+tab")
        await pilot.pause()
        assert not any(isinstance(one, Monitoring) for one in app.screen_stack)
        assert "reading" not in screen(app)

        await pilot.press(*"/st")
        await shows(pilot, "/stop", "Stop the turn, and go on with the chat")
        await pilot.press("ctrl+c")
        await typed(pilot, "/stop")

        # The turn alone: the chat is between turns, on its host, and goes on.
        await shows(pilot, "That turn was stopped.", "◉ done")
        assert "stopping the flow" not in screen(app)
        await typed(pilot, "/stop")
        await shows(pilot, "no turn is open, so there is nothing to stop")
        await typed(pilot, "go on")
        await shows(pilot, "go on", "◉ done")
    assert [method for method, _ in asked].count("chat.stop") == 1
    assert len(chats(workspace)) == 1


async def test_clear_starts_another_chat_and_the_first_goes_on_to_go_back_to(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await typed(pilot, "/clear")
        await shows(pilot, f"◉ {RUNS}")
        assert "still on it" not in screen(app)
        assert "stopping" not in screen(app)

        await typed(pilot, "again")
        await shows(pilot, "heard again")
        assert len(started(workspace)) == 2  # a conversation of its own

        # Both going, each a chat of its own and neither an epic.
        first, _ = chats(workspace)
        assert epics(workspace) == []
        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "wait for it")
        await opens(pilot, first.name)

        # Back in the first, as it stands, and talking to it.
        await shows(pilot, "still on it")
        await typed(pilot, "now")
        await shows(pilot, "heard wait for it then now")
    assert heard(workspace) == ["wait for it", "again", "now"]


async def test_an_ai_chan_conversation_is_not_among_the_chats_to_resume(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")
        await typed(pilot, "/clear")
        await shows(pilot, f"◉ {RUNS}")
        await typed(pilot, "again")
        await shows(pilot, "heard again")
        first, second = chats(workspace)
        # The first is hers, kept; and stays hers once her conversation is forgotten.
        kept = Conversations()
        made = kept.made({"slot": "ai:1"})
        kept.changed(made["id"], record=first.name)

        for forgotten in (False, True):
            if forgotten:
                assert kept.forgot(made["id"]) is not None
            await typed(pilot, "/resume")
            await on(pilot, Resumes)
            # The chat on the screen alone: hers is no chat to carry on from here.
            assert rows(app) == [second.name]
            await pilot.press("escape")
            await until(pilot, lambda: len(app.screen_stack) == 1, "the list to close")


async def test_an_env_asked_of_a_chat_that_is_refused_opens_over_nothing_later(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    held = Chats().install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
        (chat,) = chats(workspace)
        await until(pilot, lambda: bool((read(chat) or Ran(chat)).ended), "it to fold")
        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "hello")
        await opens(pilot, chat.name)
        await shows(pilot, "say something to continue")

        # Bringing it up for its environment is refused, and said so.
        held.starting, held.refusing = threading.Event(), True
        held.starting.set()
        await typed(pilot, "/env")
        await shows(pilot, "no room to start")

        # The next line still carries that chat on, and no sheet opens over it uninvited.
        held.starting = None
        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        await pilot.pause(0.5)
        assert not isinstance(app.screen, Envs)
    assert [one["resume"] for one in held.started()] == [None, chat.name, chat.name]


async def test_a_chat_folded_away_is_carried_on_by_resume_as_the_same_chat(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
        (chat,) = chats(workspace)
        await until(pilot, lambda: bool((read(chat) or Ran(chat)).ended), "it to fold")
        # Its session as Claude Code logs one, which the stand-in writes only the half of.
        (session,) = (read(chat) or Ran(chat)).sessions
        claude_logged(chat / "sessions" / "claude", workspace, session.ident, 0)

        # Listed by the daemon, by its title, and not among the epics.
        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "hello")
        await opens(pilot, chat.name)
        await shows(pilot, "say something to continue")
        # Drawn with what was said in it, above what carries it on (Section 8.7.4 of [CORE]).
        drawn = screen(app)
        assert (
            drawn.index("❯ fix the bug")
            < drawn.index("⏺ fixed" if sys.platform == "darwin" else "● fixed")
            < drawn.index("say something to continue")
        )

        # Its environment opens with nothing said: no host holding it is no reason not to.
        await typed(pilot, "/env")
        await on(pilot, Envs)
        await shows(pilot, "Environments", "workspace")
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the sheet to close")
        assert (read(chat) or Ran(chat)).reopened == ""

        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        assert "could not be carried on" not in screen(app)

    # One conversation, so one chat and no epic, carried on by its id, and the agent's
    # session carried on.
    assert chats(workspace) == [chat]
    assert epics(workspace) == []
    listed = [said for method, said in asked if method == "chat.list"]
    assert listed == [{"offset": 0, "limit": 200}]
    starts = [said for method, said in asked if method == "chat.start"]
    assert [one["resume"] for one in starts] == [None, chat.name]
    # Carried on with nothing said, for its environment; what was said then was said to it.
    assert starts[1]["task"] == ""
    began, carried = started(workspace)
    session = began[began.index("--session-id") + 1]
    assert carried[carried.index("--resume") + 1] == session
    assert "--fork-session" in carried


async def test_exit_leaves_a_chat_without_asking(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "wait for it")
        await shows(pilot, "still on it")

        await typed(pilot, "/exit")

        await until(pilot, lambda: not app.is_running, "the interface to close")


async def chatting(pilot: Pilot[None], said: str = "hello") -> None:
    """Starts a chat on one line, and waits for its turn to be done."""
    await opened(pilot)
    await typed(pilot, said)
    await shows(pilot, f"heard {said}", "◉ done")


async def test_quit_leaves_a_chat_as_exit_does(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "/quit")

        await until(pilot, lambda: not app.is_running, "the interface to close")


async def test_a_flow_started_from_a_chat_leaves_it_going_and_chat_brings_it_back(
    workspace: Path,
) -> None:
    own_flow(workspace)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await chatting(pilot)

        await typed(pilot, f"${OWN} do it")

        # The flow on the screen, on the workspace's own host, and run to its end.
        await until(pilot, (workspace / "said.txt").exists, "the flow to write")
        await shows(pilot, "the flow is done")
        assert "heard hello" not in screen(app)

        await typed(pilot, "/chat")

        await shows(pilot, "heard hello", "◉ done")
        await typed(pilot, "/chat")
        await shows(pilot, "the chat is already on the screen")
        await typed(pilot, "more")
        await shows(pilot, "heard more")
    assert (workspace / "said.txt").read_text() == "started: heard do it\n"


async def test_a_line_said_after_a_flow_ends_goes_back_to_the_chat(
    workspace: Path,
) -> None:
    own_flow(workspace)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)
        await chatting(pilot)
        await typed(pilot, f"/flow {OWN} do it")
        await shows(pilot, "the flow is done")

        await typed(pilot, "and now")

        await shows(pilot, "heard and now")
    # One flow, one chat: nothing said after the flow started another of either.
    assert heard(workspace) == ["hello", "do it", "and now"]


async def test_flow_with_a_task_starts_a_flow_set_up_at_once(workspace: Path) -> None:
    own_flow(workspace)
    async with Humanize().run_test(size=SIZE) as pilot:
        await set_up_own_flow(pilot)

        await typed(pilot, f"/flow {OWN} do it")

        await until(pilot, (workspace / "said.txt").exists, "the flow to write")
    assert heard(workspace) == ["do it"]


async def test_a_dollar_skill_is_said_to_the_chat_as_its_harness_takes_it(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "$review the diff")

        await shows(pilot, "heard $review the diff")
    assert heard(workspace)[-1] == "$review the diff"


async def test_a_name_both_a_skill_and_a_flow_goes_by_the_chats_preference(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chats = Chats().install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot)
        await typed(pilot, "/prefer")
        await shows(pilot, "native, from the settings file")

        # The skill, as the settings prefer.
        await typed(pilot, "$rlar go")
        await shows(pilot, "heard $rlar go")

        await typed(pilot, "/prefer flow")
        await shows(pilot, "runs the flow where it names both, in this chat")
        # Recorded by the chat's host, for the chat on the screen.
        (set_,) = [said for method, said in chats.asked if method == "chat.set"]
        assert set_["prefer"] == "flow"
        assert str(set_["slot"]).startswith("chat:")

        # The flow now: not set up here, so its menu, holding the task.
        await typed(pilot, "$rlar go")
        await on(pilot, Flows)
        await leaves(pilot, saving=False)
        await shows(pilot, "flow not set up; nothing started")
        await typed(pilot, "/prefer")
        await shows(pilot, "flow, from this chat")
    assert heard(workspace).count("$rlar go") == 1


async def test_a_preference_set_for_one_chat_is_not_another_carried_on_after_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
        (first,) = chats(workspace)
        await until(
            pilot, lambda: bool((read(first) or Ran(first)).ended), "it to fold"
        )

        # Set before the second chat starts, so it is started with it.
        await typed(pilot, "/prefer flow")
        await shows(pilot, "runs the flow where it names both, in this chat")
        await typed(pilot, "second")
        await shows(pilot, "heard second", "◉ done")

        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "first")
        await opens(pilot, first.name)
        await shows(pilot, "say something to continue")
        # The first chat's, which was never given one of its own.
        await typed(pilot, "/prefer")
        await shows(pilot, "native, from the settings file")
        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")

    starts = [said for method, said in asked if method == "chat.start"]
    assert [one["prefer"] for one in starts] == [None, "flow", None]
    assert starts[-1]["resume"] == first.name
    assert (read(first) or Ran(first)).prefer == ""


async def test_a_chat_carried_on_keeps_the_preference_set_for_it(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    asked = Chats().install(monkeypatch).asked
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/prefer flow")
        await shows(pilot, "runs the flow where it names both, in this chat")
        await typed(pilot, "first")
        await shows(pilot, "heard first", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(chats(workspace)) == 1, "the chat")
        (first,) = chats(workspace)
        await until(
            pilot, lambda: bool((read(first) or Ran(first)).ended), "it to fold"
        )
        await typed(pilot, "/prefer")
        await shows(pilot, "native, from the settings file")

        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "first")
        await opens(pilot, first.name)
        await shows(pilot, "say something to continue")
        # Its own, as the chat records it, before a word carries it on and after.
        await typed(pilot, "/prefer")
        await shows(pilot, "flow, from this chat")
        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        said = screen(app).count("flow, from this chat")
        await typed(pilot, "/prefer")
        await until(
            pilot,
            lambda: screen(app).count("flow, from this chat") == said + 1,
            "its preference said again",
        )

    starts = [said for method, said in asked if method == "chat.start"]
    # Said once, to the chat it was set for: the chat keeps it from there on.
    assert [one["prefer"] for one in starts] == ["flow", None]
    assert (read(first) or Ran(first)).prefer == "flow"


def _harness_session(tmp_path: Path, workspace: Path, ident: str, said: str) -> Path:
    """A session the stand-in `claude` had of its own in the workspace, as it logs one."""
    workspace = workspace.resolve()
    plain = "".join(one if one.isalnum() else "-" for one in str(workspace))
    log = tmp_path / "claude-home" / "projects" / plain / f"{ident}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = [
        {
            "type": "user",
            "cwd": str(workspace),
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": said},
        },
        {
            "type": "assistant",
            "cwd": str(workspace),
            "timestamp": "2026-01-01T00:00:05+00:00",
            "message": {"model": MODEL, "role": "assistant", "content": []},
        },
    ]
    log.write_text("".join(json.dumps(one) + "\n" for one in rows))
    return log


async def test_a_harness_session_is_offered_on_resume_where_set_and_goes_on_as_a_chat(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    ident = "0b0b0b0b-1111-4222-8333-444444444444"
    log = _harness_session(tmp_path, workspace, ident, "the word is guava")
    before = log.read_bytes()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first", "◉ done")

        # Not listed until the setting says so: only the chats of Humanize's own are.
        await typed(pilot, "/resume")
        await on(pilot, Resumes)
        (mine,) = chats(workspace)
        assert rows(app) == [mine.name]
        await pilot.press("escape")
        await until(pilot, lambda: len(app.screen_stack) == 1, "the list to close")

        Settings().harness_sessions = True
        await typed(pilot, "/resume")
        await shows(
            pilot, "Resume chat", "the word is guava", "claude session, read-only"
        )
        # After the chats, and read-only: its row has no menu.
        listing = await on(pilot, Resumes)
        assert rows(app) == [mine.name, f"harness:claude:{ident}"]
        await onto(pilot, f"harness:claude:{ident}")
        assert listing.menu() is None
        await opens(pilot, f"harness:claude:{ident}")
        await shows(pilot, "say something to continue")
        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")

    made = [ran for at in chats(workspace) if (ran := read(at)) and ran.adopted]
    assert [(one.adopted, one.title) for one in made] == [
        (f"claude:{ident}", "the word is guava")
    ]
    assert log.read_bytes() == before
    assert heard(workspace) == ["first", "more"]


def _opencode_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace: Path
) -> Path:
    """A session of an `opencode` that is only a name on PATH, in the database it keeps."""
    stub = tmp_path / "bin" / "opencode"
    stub.write_text("#!/bin/sh\n")
    stub.chmod(0o755)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    store = tmp_path / "share" / "opencode" / "opencode.db"
    store.parent.mkdir(parents=True)
    with sqlite3.connect(store) as held:
        held.execute(
            "create table session (id, parent_id, directory, title, time_created, "
            "time_updated)"
        )
        held.execute(
            "insert into session values ('ses_1', null, ?, 'The word is plum', 1, 2)",
            (str(workspace.resolve()),),
        )
    held.close()
    return store


async def test_a_harness_session_that_cannot_be_continued_says_so_and_is_refused(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _opencode_session(tmp_path, monkeypatch, workspace)
    before = store.read_bytes()
    Settings().harness_sessions = True
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)

        await typed(pilot, "/resume")
        await shows(
            pilot,
            "The word is plum",
            "opencode session, read-only: cannot be continued in a chat",
        )
        await on(pilot, Resumes)
        assert rows(app) == ["harness:opencode:ses_1"]
        await opens(pilot, "harness:opencode:ses_1")

        await shows(pilot, "A session of opencode cannot be continued in a chat.")

    assert chats(workspace) == []
    assert store.read_bytes() == before


async def test_prefer_is_refused_an_argument_it_does_not_take(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)

        await typed(pilot, "/prefer neither")

        await shows(pilot, "/prefer takes native or flow")


async def test_a_shell_line_and_what_it_printed_are_drawn_as_a_shell_draws_them(
    workspace: Path,
) -> None:
    (workspace / PRINTED).touch()
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "!ls")

        drawn = await shows(pilot, "!ls", f"⎿  {PRINTED}")
        assert "❯ !ls" not in drawn
        assert drawn.count("!ls") == 1
    # Run for the chat rather than said to its assistant.
    assert "!ls" not in heard(workspace)


async def test_a_command_only_the_harness_interface_serves_is_refused(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "/config")

        await shows(
            pilot, "/config is served only by the harness's own interactive interface"
        )
        await typed(pilot, "/nonsense")
        await shows(pilot, "no such command: /nonsense")
    assert heard(workspace) == ["hello"]


async def test_a_slash_line_is_said_as_text_to_a_harness_with_no_catalogue(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Chats(catalog=()).install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "/nonsense please")

        await shows(pilot, "heard /nonsense please")
        assert "no such command" not in screen(app)
    assert heard(workspace) == ["hello", "/nonsense please"]


async def test_a_harness_command_is_said_to_the_chat(workspace: Path) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await typed(pilot, "/compact")

        await shows(pilot, "heard /compact")


async def test_the_chats_skills_and_the_flows_are_offered_and_told_apart(
    workspace: Path,
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await chatting(pilot)

        await pilot.press(*"$r")

        drawn = await shows(
            pilot,
            "skill · Review the change",
            "skill and flow: runs the skill; /flow rlar starts the flow",
        )
        assert drawn.index("$review") < drawn.index("$rlar")


async def test_resume_in_a_chat_carries_on_an_earlier_one(workspace: Path) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot, "first")
        await typed(pilot, "/clear")
        await chatting(pilot, "second")

        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "first")
        first, second = chats(workspace)
        # Newest first, the one on the screen among them as the one already had.
        assert rows(app) == [second.name, first.name]
        await opens(pilot, first.name)

        await shows(pilot, "heard first")
        await typed(pilot, "more")
        await shows(pilot, "heard more")
    # Carried on as the chat it is: no third.
    assert chats(workspace) == [first, second]


async def test_a_chat_gone_back_to_is_drawn_with_every_line_said_in_it(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot, "one")
        await typed(pilot, "two")
        await shows(pilot, "heard two", "◉ done")
        await typed(pilot, "/clear")
        await chatting(pilot, "other")

        await typed(pilot, "/resume")
        await shows(pilot, "Resume chat", "one")
        first, _ = chats(workspace)
        await opens(pilot, first.name)

        drawn = await shows(pilot, "heard one", "heard two")
    assert drawn.index("❯ one") < drawn.index("heard one") < drawn.index("❯ two")
    assert drawn.index("❯ two") < drawn.index("heard two")


async def test_a_line_another_frontend_says_in_a_chat_is_drawn_in_it(
    workspace: Path,
) -> None:
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await chatting(pilot, "one")
        (slot,) = [
            one.slot for one in daemons.daemons() if one.slot.startswith("chat:")
        ]
        link = daemons.attach("sdk", workspace=workspace, slot=slot)
        try:
            link.chat_say("from elsewhere")

            drawn = await shows(pilot, "heard from elsewhere")
        finally:
            link.close()
        assert drawn.index("❯ from elsewhere") < drawn.index("heard from elsewhere")
        # And one typed here is drawn once, as it was typed.
        await typed(pilot, "two")
        drawn = await shows(pilot, "heard two", "◉ done")
    assert drawn.count("❯ two") == 1
