"""What was said to a running flow and has not been taken yet, and where it is shown.

A line typed at a running flow is said to the runs, which queue it and hand it to the agents
one at a time -- that half is the host's, and `tests/integration/runtime/test_hosting.py`
checks it. What is left here is the interface's half: which view a line is said to, and what
it draws of what the runs say back. Until a line goes it is pinned above the prompt rather
than written into the transcript -- it has not been said to anybody yet, which is what Claude
Code does with a queued message too -- and once the runs say an agent has it, it is written
down where it went, with who said it where that was another frontend.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import Static

from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from hmz.tui.app import _PINNED
from hmz.tui.monitor import short
from tests.stubs import written
from tests.tui.fixtures import (
    event,
    link,
    opened,
    running,
    set_up,
    snapshot,
    started,
    told,
    transcript,
    until,
)

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that runs until a file appears, so that a line can be typed while it is up and the
#: flow can then be let finish of its own accord.
FLOW = """
import asyncio
from pathlib import Path

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, flow


class Agents(AgentCollection):
    coder: Agent


@flow(agents=Agents, envs=EnvCollection, params=FlowParams, name="flow")
async def run(task: str, *, agents: Agents, envs: EnvCollection, params: FlowParams,
              ctx: FlowContext) -> None:
    while not Path("go.txt").exists():
        await asyncio.sleep(0.02)
"""


def _pinned(app: Humanize) -> str:
    """What is pinned above the prompt, as it reads, or "" with the pin not showing at all."""
    said = app.query_one("#queued", Static)
    return str(said.content) if said.has_class("waiting") else ""


def _line(
    text: str, *, to: str = "", by: str = "you@tui", client: str = "c1"
) -> dict[str, Any]:
    """One line the runs hold queued, as their `waiting` snapshot lists it."""
    return {"text": text, "by": by, "client": client, "to": to}


def _given(
    text: str, agent: str = "coder", *, by: str = "you@tui", client: str = "c1"
) -> dict[str, Any]:
    """One line the runs have put into an agent's turn, which it has not said it has."""
    return {"agent": agent, "text": text, "by": by, "client": client}


def _waiting(
    *queued: dict[str, Any], given: tuple[dict[str, Any], ...] = ()
) -> dict[str, Any]:
    """The `waiting` snapshot: what is given, and what is still queued behind it."""
    return snapshot("waiting", queued=list(queued), given=list(given))


def _said(
    text: str, key: str = "coder/1", *, by: str = "you@tui", client: str = "c1"
) -> dict[str, Any]:
    """The runs saying a line has reached an agent, and who said it."""
    return {
        "type": "said",
        "run": 0,
        "text": text,
        "key": key,
        "by": by,
        "client": client,
    }


async def _running(app: Humanize, driver: Pilot[None], *keys: str) -> None:
    """Puts the interface in front of a run of one agent role, `coder`, going.

    Args:
      app: The interface.
      driver: What is pumping it.
      keys: The conversations the run has opened, none by default.
    """
    record = started(roles=["coder"])
    told(app, record, running(record), *(opened(key) for key in keys))
    await driver.pause()


async def _types(driver: Pilot[None], line: str) -> None:
    """Types one line and sends it, as somebody at the prompt would."""
    await driver.press(*line)
    await driver.press("enter")
    await driver.pause()


@pytest.fixture
def waiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A flow that runs until it is let go, and a `claude` on PATH it never launches."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    written(tmp_path, "flow", FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(60)
async def test_a_line_typed_at_a_running_flow_is_said_to_the_view_being_read() -> None:
    """It is asked of the runs, and not written down: nothing has taken it yet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await _types(driver, "and fix the tests")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert link(app).asked_for("say") == [
            {"do": "say", "text": "and fix the tests", "to": ""}
        ]
        assert "and fix the tests" not in transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_with_nowhere_to_go_yet_is_pinned_rather_than_written_down() -> (
    None
):
    """It has not been said to anybody, and the transcript is what was said."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        told(app, _waiting(_line("and fix the tests")))
        await driver.pause()

        assert "and fix the tests" in _pinned(app)
        assert "and fix the tests" not in transcript(app)


@pytest.mark.timeout(60)
async def test_it_goes_into_the_transcript_at_the_moment_it_is_taken() -> None:
    """In front of the turn that took it, which is where it belongs -- and off the pin."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver, "coder/1")
        told(app, _waiting(_line("and fix the tests")))
        await driver.pause()
        assert "and fix the tests" in _pinned(app)

        told(app, _said("and fix the tests"), _waiting())
        await driver.pause()

        assert _pinned(app) == ""
        assert "and fix the tests" in transcript(app)
        # On that conversation's own, as well as the one every agent is on.
        app._now_reading("coder/1")
        await driver.pause()
        assert "and fix the tests" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_into_a_turn_that_is_open_is_pinned_until_the_agent_has_it() -> (
    None
):
    """What the backend takes from us is not what the agent has heard.

    Every one of them answers a word put into a turn twice: once to say it has been taken
    from us, and again -- a whole answer or a tool call later -- to say it is in front of the
    model. Only the runs saying the second writes it down.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver, "coder/1")
        told(app, event("coder/1", "begins"), _waiting(given=(_given("and this"),)))
        await driver.pause()

        # Handed over, and not said: it is pinned against the agent that has it.
        assert "and this" not in transcript(app)
        assert f"with {short('coder')}" in _pinned(app)

        told(app, _said("and this"), _waiting())
        await driver.pause()

        assert _pinned(app) == ""
        assert "and this" in transcript(app)


@pytest.mark.timeout(60)
async def test_an_agent_saying_it_took_a_word_is_not_the_word_written_down() -> None:
    """The runs say who took what, and once: the agent's own `took` draws nothing."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver, "coder/1")
        told(
            app, event("coder/1", "begins"), _waiting(given=(_given("for the coder"),))
        )
        told(app, event("coder/1", "took", "for the coder"))
        await driver.pause()

        assert "for the coder" not in transcript(app)
        assert "for the coder" in _pinned(app)


@pytest.mark.timeout(60)
async def test_a_turn_that_ended_without_saying_it_had_it_says_that_instead() -> None:
    """Neither waiting nor taken: it was put to an agent whose turn is over.

    Nothing may stay pinned against a turn that has ended -- the pin would be claiming a word
    is still on its way to something that is not running.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver, "coder/1")
        told(app, event("coder/1", "begins"), _waiting(given=(_given("take this"),)))
        await driver.pause()

        told(
            app,
            event("coder/1", "ends"),
            {"type": "unheld", "run": 0, "agent": "coder", "texts": ["take this"]},
            _waiting(),
        )
        await driver.pause()

        assert _pinned(app) == ""
        assert "take this" in transcript(app)
        assert "without saying it had it" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_word_the_backend_would_not_take_is_said_and_stays_pinned() -> None:
    """A steer codex drops or kimi refuses never went: the runs say why, and keep it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        told(
            app,
            {
                "type": "refused",
                "run": 0,
                "agent": "coder",
                "text": "never went",
                "because": "no active turn to steer",
            },
            _waiting(_line("never went"), _line("typed after it")),
        )
        await driver.pause()

        # Still on its way, and still in front of what followed it.
        first, second = _pinned(app).splitlines()
        assert "never went" in first
        assert "typed after it" in second
        assert "hmz: no active turn to steer" in transcript(app)


@pytest.mark.timeout(60)
async def test_another_frontend_s_lines_are_pinned_and_written_down_as_theirs() -> None:
    """Several may be saying things to one run, and which of them said a line is half of it."""
    app = Humanize()
    async with app.run_test(size=(120, 24)) as driver:
        await _running(app, driver, "coder/1")
        told(
            app,
            _waiting(
                _line("mine"),
                _line("theirs", by="bob@tui", client="c2"),
            ),
        )
        await driver.pause()

        mine, theirs = _pinned(app).splitlines()
        assert "by" not in mine
        assert theirs.endswith("theirs · by bob@tui")

        told(
            app,
            _said("mine"),
            _said("theirs", by="bob@tui", client="c2"),
            _waiting(),
        )
        await driver.pause()

        shown = transcript(app)
        assert "mine · by" not in shown
        assert "theirs · by bob@tui" in shown


@pytest.mark.timeout(60)
async def test_more_than_a_few_are_counted_rather_than_all_pinned() -> None:
    """A pin that grew without limit would push the transcript off the screen to say so."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        told(app, _waiting(*(_line(f"line {at}") for at in range(_PINNED + 3))))
        await driver.pause()

        shown = _pinned(app)
        assert "line 0" in shown  # oldest first, since that is the order they go in
        assert len(shown.splitlines()) <= _PINNED + 1
        assert "3 more waiting" in shown


@pytest.mark.timeout(60)
async def test_a_line_of_several_is_pinned_as_it_was_typed() -> None:
    """As the transcript sets one: the first behind the marker, the rest lined up under it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await driver.press(*"first")
        await driver.press("ctrl+j")
        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: bool(link(app).asked_for("say")), driver)
        (said,) = link(app).asked_for("say")
        assert said["text"] == "first\nsecond"

        told(app, _waiting(_line(said["text"])))
        await driver.pause()

        first, second = _pinned(app).splitlines()
        assert first.strip().startswith("❯")
        assert first.strip().endswith("first")
        assert second.strip() == "second"


@pytest.mark.timeout(60)
async def test_what_the_stopped_flow_never_took_is_said_to_have_been_dropped() -> None:
    """A line pinned against a flow that has gone would read as one still on its way."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        told(app, _waiting(_line("too late")))
        await driver.pause()

        app.action_stop_flow()
        await until(lambda: bool(link(app).asked_for("stop")), driver)
        told(
            app,
            {
                "type": "dropped",
                "run": 0,
                "given": [],
                "queued": [_line("too late")],
                "because": "stopped",
            },
            _waiting(),
        )
        await driver.pause()

        assert _pinned(app) == ""
        assert "too late" in transcript(app)
        assert "never sent: the flow stopped first" in transcript(app)


@pytest.mark.timeout(60)
async def test_what_was_put_to_an_agent_and_dropped_says_it_may_have_reached_it() -> (
    None
):
    """Put to an agent that never said it had it: neither sent nor never sent."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        told(
            app,
            {
                "type": "dropped",
                "run": 0,
                "given": [_given("half way")],
                "queued": [_line("from bob", by="bob@tui", client="c2")],
                "because": "ended",
            },
        )
        await driver.pause()

        shown = transcript(app)
        assert "half way" in shown
        assert "put to the agent, never taken back: the flow ended first" in shown
        assert "from bob · by bob@tui" in shown
        assert "never sent: the flow ended first" in shown
        assert shown.index("half way") < shown.index("from bob")


@pytest.mark.timeout(60)
async def test_nothing_is_pinned_with_no_flow_running() -> None:
    """The first thing said to a flow that is not running is the task, and it starts it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _types(driver, "the task")

        assert _pinned(app) == ""
        assert not link(app).asked_for("say")


@pytest.mark.timeout(60)
async def test_one_that_will_not_fit_whole_is_counted_rather_than_shown_in_half() -> (
    None
):
    """A message cut across the middle reads as a message that says something it does not."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        # A long one, which cannot follow the short one whole.
        told(
            app,
            _waiting(_line("short"), _line("\n".join(["long"] * _PINNED + ["end"]))),
        )
        await driver.pause()

        shown = _pinned(app)
        assert "short" in shown
        assert "long" not in shown  # not the half of it that would have fitted
        assert "1 more waiting" in shown


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "typed", ["try [red]this", "fix the [TODO] item", "[$text-muted] and [ ]"]
)
async def test_what_was_typed_is_pinned_as_text_rather_than_as_markup(
    typed: str,
) -> None:
    """A bracket somebody typed is a bracket, whatever it happens to look like.

    Neither escaper is safe here: each only escapes a bracket that already looks like a tag
    to it, and Rich and Textual disagree about which do -- `[TODO]` is a word to one and a
    tag to the other. So the pin is drawn as content rather than as markup, and there is
    nothing to escape.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await _types(driver, typed)
        await until(lambda: bool(link(app).asked_for("say")), driver)
        assert link(app).asked_for("say")[0]["text"] == typed
        told(app, _waiting(_line(typed)))
        await driver.pause()

        assert typed in _pinned(app)


@pytest.mark.timeout(60)
async def test_clearing_the_screen_leaves_what_is_waiting_where_it_is() -> None:
    """`/clear` clears the transcript, and what is waiting has not reached it yet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        told(app, _waiting(_line("still coming")))
        await driver.pause()

        await _types(driver, "/clear")

        assert "still coming" in _pinned(app)


@pytest.mark.timeout(90)
async def test_what_a_flow_that_ended_never_took_is_said_to_have_been_dropped(
    waiting: Path, hosting: None
) -> None:
    """A flow ends two ways, and both leave the pin holding a line on its way nowhere.

    Stopped by hand is the other test; this is the one that ends of its own accord, which is
    how every flow that finishes ends -- run for real, in this process, so that what the runs
    say at the end is what they say rather than what a test told the interface.
    """
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "flow")
        await _types(driver, "the task")
        await until(lambda: app._run is not None, driver)

        await _types(driver, "and this too")
        await until(lambda: bool(_pinned(app)), driver)

        (waiting / "go.txt").write_text("")  # and the flow runs out of things to do
        await until(lambda: app._run is None, driver)
        await until(lambda: "never sent" in transcript(app), driver)

        assert _pinned(app) == ""
        assert "and this too" in transcript(app)
        assert "the flow ended first" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_pasted_paragraph_is_one_row_rather_than_twenty() -> None:
    """A pin capped in lines and not in rows would push the editor off the bottom."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        told(app, _waiting(_line("please " * 200)))  # one line, and far more than a row
        await driver.pause()

        assert len(_pinned(app).splitlines()) == 1
        assert app.query_one("#queued", Static).size.height == 1
        assert _pinned(app).endswith("…")


@pytest.mark.timeout(60)
async def test_the_pin_never_takes_more_than_its_share_of_the_screen() -> None:
    """Five long pastes are five rows, and the editor and the status line stay where they are."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        told(app, _waiting(*(_line(f"{at} " + "x" * 900) for at in range(_PINNED + 2))))
        await driver.pause()

        assert "more waiting" in _pinned(app)
        assert app.query_one("#queued", Static).size.height <= _PINNED + 1
        # The status line is still on the screen, which is what the cap is for.
        assert app.query_one("#status", Static).region.y < 24


@pytest.mark.timeout(60)
async def test_a_message_too_long_to_show_whole_says_how_much_was_cut() -> None:
    """Half a message must never read as the whole of one -- not even the first."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        told(app, _waiting(_line("\n".join(f"line {at}" for at in range(10)))))
        await driver.pause()

        shown = _pinned(app)
        assert "line 0" in shown
        assert len(shown.splitlines()) == _PINNED
        assert "6 more lines" in shown  # ten of them, four shown


@pytest.mark.timeout(60)
async def test_what_is_cut_off_counts_the_lines_and_the_messages_apart() -> None:
    """One number for what is left of this message, another for the messages after it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        told(
            app,
            _waiting(
                _line("\n".join(f"line {at}" for at in range(10))),
                _line("and another"),
            ),
        )
        await driver.pause()

        shown = _pinned(app)
        assert "6 more lines" in shown
        assert "1 more waiting" in shown


@pytest.mark.timeout(60)
async def test_it_reaches_the_transcript_from_the_thread_the_runs_tell_it_on() -> None:
    """Which is the path every message takes: a link hands them over on a thread of its own."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver, "coder/1")

        telling = threading.Thread(target=lambda: app._told(_said("from a turn")))
        telling.start()
        await until(lambda: "from a turn" in transcript(app), driver)
        telling.join(5)

        assert "from a turn" in transcript(app)


@pytest.mark.timeout(60)
async def test_lines_typed_in_a_row_are_said_in_the_order_they_were_typed() -> None:
    """Each is asked of the runs in turn, on the one thread that asks them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        for said in ("hi", "hi again", "hi once more"):
            await _types(driver, said)
        await until(lambda: len(link(app).asked_for("say")) == 3, driver)

        assert [one["text"] for one in link(app).asked_for("say")] == [
            "hi",
            "hi again",
            "hi once more",
        ]


@pytest.mark.timeout(60)
async def test_a_line_typed_while_a_run_starts_is_said_to_it_rather_than_starting_one() -> (
    None
):
    """The run asked for is the one it goes to, once the runs have started it."""
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "chat", {"assistant": Runs("claude/m:high")})
        await _types(driver, "the task")
        await _types(driver, "and this")
        await until(lambda: bool(link(app).asked_for("say")), driver)

        assert [one["do"] for one in link(app).requests] == ["start", "say"]
        assert link(app).asked_for("say")[0]["text"] == "and this"


@pytest.mark.timeout(60)
async def test_what_went_to_an_agent_is_pinned_in_front_of_what_is_still_queued() -> (
    None
):
    """The pin reads oldest first, as the transcript does -- and what went, went first."""
    app = Humanize()
    async with app.run_test(size=(120, 24)) as driver:
        await _running(app, driver, "coder/1")
        told(
            app,
            event("coder/1", "begins"),
            _waiting(_line("behind"), given=(_given("gone"),)),
        )
        await driver.pause()

        first, second = _pinned(app).splitlines()
        assert "gone" in first
        assert f"with {short('coder')}" in first  # since that is the one it is holding
        assert "behind" in second


@pytest.mark.timeout(60)
async def test_the_pin_sits_on_the_editor_beside_what_the_run_is_running_as() -> None:
    """One block above the prompt rather than two, read from the bottom up.

    The last line typed and the running total are two halves of where the run has got to,
    and the pin standing above them in a column of its own reads as two things.
    """
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)
        app._monitor.spend("coder", 12345, model="m")
        told(app, _waiting(_line("hi"), _line("hi again")))
        await driver.pause()

        pin = app.query_one("#queued", Static).region
        beside = app.query_one("#above", Static).region
        rule = app.query_one("#rule-above", Static).region

        assert pin.bottom == beside.bottom  # the last line typed, and the running total
        assert pin.bottom == rule.y  # with nothing between the block and the editor
        assert pin.right <= beside.x  # side by side, rather than one above the other
        assert "12.3k tokens" in str(app.query_one("#above", Static).content)


@pytest.mark.timeout(60)
async def test_a_pinned_line_is_cut_to_what_is_left_beside_it() -> None:
    """The block to the right of it is not the pin's to draw in."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        told(app, _waiting(_line("x" * 200)))
        await driver.pause()

        pin = app.query_one("#queued", Static).region
        beside = app.query_one("#above", Static).region
        assert _pinned(app).endswith("…")
        assert pin.right <= beside.x  # cut short of it rather than over it
        assert beside.width >= len("coder · claude/m:high")  # which still fits whole
