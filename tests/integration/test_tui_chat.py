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

import threading
from typing import TYPE_CHECKING

import pytest

from hmz import daemon as daemons
from hmz.daemon.reach import Conversations
from hmz.runtime.epic import Ran, chats, epics, read
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.monitoring import Monitoring
from tests.integration.doubles_tui import (
    OWN,
    PRINTED,
    RUNS,
    SIZE,
    Chats,
    folds_fast,
    heard,
    leaves,
    on,
    opened,
    opens,
    own_flow,
    rows,
    screen,
    set_up_own_flow,
    shows,
    stand_in,
    started,
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
        assert "stop" not in drawn.splitlines()[-1]
        assert "monitor" not in drawn.splitlines()[-1]

        await typed(pilot, "now")

        drawn = await shows(pilot, "heard wait for it then now", "◉ done")
        assert "waiting for you" not in drawn
        assert "outworlder" not in drawn
    assert heard(workspace) == ["wait for it", "now"]


async def test_tool_rows_shown_in_detail_are_drawn_as_written_and_again_on_a_resize(
    workspace: Path, tmp_path: Path
) -> None:
    home = tmp_path / "humanize-home"
    home.mkdir(exist_ok=True)
    (home / "settings.yaml").write_text("details: true\n")
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
        assert "starting…" in drawn.splitlines()[-1]
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
        await shows(pilot, "Resume a chat", "wait for it")
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
        first, _ = chats(workspace)
        # The first is hers, kept; and stays hers once her conversation is forgotten.
        kept = Conversations()
        made = kept.made({"slot": "ai:1"})
        kept.changed(made["id"], record=first.name)

        for forgotten in (False, True):
            if forgotten:
                assert kept.forgot(made["id"]) is not None
            said = screen(app).count("no other chat has been had here")
            await typed(pilot, "/resume")
            await until(
                pilot,
                lambda said=said: (
                    screen(app).count("no other chat has been had here") == said + 1
                ),
                "none to resume",
            )


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

        # Listed by the daemon, by its title, and not among the epics.
        await typed(pilot, "/resume")
        await shows(pilot, "Resume a chat", "hello")
        await opens(pilot, chat.name)
        await shows(pilot, "say something to continue")

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
        await shows(pilot, "Resume a chat", "first")
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
        await shows(pilot, "Resume a chat", "first")
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
        await shows(pilot, "Resume a chat", "first")
        first, second = chats(workspace)
        # The earlier one alone: the one on the screen is the one already had.
        assert rows(app) == [first.name]
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
        await shows(pilot, "Resume a chat", "one")
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
