"""A chat, read as Claude Code reads one: one conversation, running or done, never stopped.

And as many of them as there are: each is an epic of its own, on a host of its own, which goes
on while another is had and folds away once nobody has looked at it for a while -- and is
carried on, in the same epic, from `/epics`. A flow started from it goes on the workspace's
own host, and `/chat` comes back to it. What its harness takes at its own prompt -- a command,
a skill, a shell command -- it takes too, and `/prefer` says which a `$` name that is both a
skill and a flow starts. The daemon's chats are stood in for (:class:`Chats`).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from hmz import daemon as daemons
from hmz.daemon.reach import Conversations
from hmz.runtime.epic import Ran, epics, read
from hmz.tui import Humanize
from hmz.tui.flows import Flows
from hmz.tui.monitoring import Monitoring
from hmz.tui.pick import Does, Epics
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


async def test_a_chat_offers_no_stop_monitor_or_views(workspace: Path) -> None:
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
        await pilot.pause()
        assert "/stop" not in screen(app)
        await pilot.press("ctrl+c")
        await typed(pilot, "/stop")

        await shows(pilot, "a chat is not stopped: /clear starts another")
        await typed(pilot, "go on")
        await shows(pilot, "heard wait for it then go on")


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

        # Both going, each an epic of its own.
        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await shows(pilot, "wait for it · ", "again · ")
        first, _ = epics(workspace)
        await opens(pilot, first.name)
        await on(pilot, Does)
        await opens(pilot, "continue")

        # Back in the first, as it stands, and talking to it.
        await shows(pilot, "still on it")
        await typed(pilot, "now")
        await shows(pilot, "heard wait for it then now")
    assert heard(workspace) == ["wait for it", "again", "now"]


async def test_the_epic_of_an_ai_chan_conversation_is_not_among_the_epics(
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
        first, _ = epics(workspace)
        # The first is hers, kept; and stays hers once her conversation is forgotten.
        kept = Conversations()
        made = kept.made({"slot": "ai:1"})
        kept.changed(made["id"], record=first.name)

        for forgotten in (False, True):
            if forgotten:
                assert kept.forgot(made["id"]) is not None
            await typed(pilot, "/epics")
            await on(pilot, Epics)
            await shows(pilot, "again · ")
            assert "wait for it · " not in screen(app)
            await leaves(pilot)


async def test_a_chat_folded_away_is_continued_from_epics_in_the_same_epic(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folds_fast(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello")
        await shows(pilot, "heard hello", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(epics(workspace)) == 1, "the epic")
        (epic,) = epics(workspace)
        await until(pilot, lambda: bool((read(epic) or Ran(epic)).ended), "it to fold")

        await typed(pilot, "/epics")
        await on(pilot, Epics)
        await opens(pilot, epic.name)
        await on(pilot, Does)
        await opens(pilot, "continue")
        await shows(pilot, "say something to continue")

        await typed(pilot, "more")
        await shows(pilot, "heard more", "◉ done")
        assert "could not be carried on" not in screen(app)

    # One conversation, so one epic, and the agent's session carried on.
    assert epics(workspace) == [epic]
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
    chats = Chats().install(monkeypatch)
    app = Humanize()
    async with app.run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "first")
        await shows(pilot, "heard first", "◉ done")
        await typed(pilot, "/clear")
        await until(pilot, lambda: len(epics(workspace)) == 1, "the epic")
        (first,) = epics(workspace)
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

    starts = [said for method, said in chats.asked if method == "chat.start"]
    assert [one["prefer"] for one in starts] == [None, "flow", None]
    assert starts[-1]["resume"] == str(first)
    assert (read(first) or Ran(first)).prefer == ""


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
        first, _ = epics(workspace)
        await opens(pilot, first.name)

        await shows(pilot, "heard first")
        await typed(pilot, "more")
        await shows(pilot, "heard more")
    # Carried on in its own epic: no third.
    assert len(epics(workspace)) == 2


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
        first, _ = epics(workspace)
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
