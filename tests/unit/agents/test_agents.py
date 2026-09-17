"""The agent library where nothing is launched: identity, bookkeeping, and what is read back.

Every test here makes an agent, and none of them lets one run. What is asked about is the
object the driving library is -- the codename an agent answers to, the sessions it remembers,
the call a backend would build, the events one line of a backend's protocol becomes, and the
refusals that land before a process would -- so each is imports, a call and an assert, with no
process, no socket and nothing to install.

The same classes taking real turns against a fake CLI on PATH are next door, in
`tests/integration/agents/test_agents.py`, which is where that pattern is documented.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    ClaudeCodeSession,
    CommandSessionBase,
    Event,
    Question,
    Stopped,
)
from hmz.coganchor.agents.codenames import SAID

if TYPE_CHECKING:
    import os

CONFIG = AgentConfig(model="m", effort="high")

#: What a turn held to a shape answers with, which is the object and nothing else.
SHAPED = '{"capital":"Bern","landlocked":true}'


@pytest.fixture(autouse=True)
def _nothing_to_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leaves nothing on PATH for this file to find, which is what it says it does not do.

    Two of the tests below reach the line that would take a turn and are refused before it --
    a backend with no goal feature, and an agent stopped before its session was opened. They
    are here because they raise rather than run; if a regression ever moved either check past
    the spawn, an emptied PATH is a `claude` that was not found rather than a real turn taken
    on the machine running the suite.
    """
    monkeypatch.setenv("PATH", "")


class _EchoSession(CommandSessionBase):
    """Runs `cat`, echoing the prompt back on stdout -- and here, never asked to.

    A session is what an agent hands out and remembers, so these tests need a concrete one;
    what it would run is its own business, and nothing below takes a turn on it.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["cat"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "echo"


class _EchoAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> _EchoSession:
        return _EchoSession(self, cwd)


def test_every_driven_agent_names_the_backend_it_is_registered_under() -> None:
    """What an agent calls its backend is what its account, its skills and its cost are under.

    Read off the class name, so a class whose name spells its product rather than its backend
    -- `GrokBuildAgent` for `grok` -- would name a backend nothing answers to, and every one
    of those lookups would quietly answer with nothing.
    """
    from hmz.coganchor.agents import DRIVEN
    from hmz.coganchor.backends import named

    for backend, (driver, config) in DRIVEN.items():
        agent = driver(config(model="m", effort="high"))
        assert agent.backend == backend, driver.__name__
        assert named(agent.backend) is not None


def test_an_agent_is_one_agent_apart_from_its_configuration() -> None:
    # The rlar shape: an actor and the reviewer reading its work, at one model and one effort.
    actor, reviewer = _EchoAgent(CONFIG), _EchoAgent(CONFIG)
    assert actor.id != reviewer.id
    assert actor.config == reviewer.config
    # A flow that names its agents keeps those names across restarts; one left unnamed draws
    # a designation out of Amphoreus, so a trace of two of them still reads as two.
    assert _EchoAgent(CONFIG, name="actor").id == "actor"
    assert actor.id in SAID or re.fullmatch(
        r"[A-Z][a-z]+(?:[A-Z][a-z]+)+[0-9]{3}", actor.id
    )


def test_an_agent_keeps_the_sessions_it_launched() -> None:
    agent = _EchoAgent(CONFIG)
    first, second = agent.new(), agent.new()
    assert agent.sessions == [first, second]  # oldest first
    assert agent.config is CONFIG

    agent.sessions.clear()  # the list is a copy, so a caller cannot lose the agent its sessions
    assert agent.sessions == [first, second]


def test_launching_while_another_thread_reads_loses_no_session() -> None:
    agent = _EchoAgent(CONFIG)
    stop = threading.Event()

    def read() -> None:
        while not stop.is_set():
            len(agent.sessions)

    with ThreadPoolExecutor(max_workers=1) as pool:
        reader = pool.submit(read)
        held = [agent.new() for _ in range(2000)]
        stop.set()
        reader.result()
    assert agent.sessions == held


def test_claude_narrates_a_reach_by_default_and_takes_that_back_when_told_to() -> None:
    """`--include-partial-messages` is the one thing asked of that CLI beyond its own default.

    So it is the one thing with a field of its own to turn back off: with it the reach is
    said the moment the model makes it, and without it once the whole of what it was called
    with has arrived -- which for a `Write` is the file, and minutes of a turn saying nothing.
    """
    config = ClaudeCodeAgentConfig(model="m", effort="high")

    assert "--include-partial-messages" in ClaudeCodeAgent(config).new()._command()
    assert ClaudeCodeSession.narrates is True

    quiet = replace(config, partial_messages=False)

    assert "--include-partial-messages" not in ClaudeCodeAgent(quiet).new()._command()


def test_a_session_that_never_opened_cannot_be_talked_to() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()
    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")


def test_a_backend_without_a_goal_feature_says_so() -> None:
    with pytest.raises(NotImplementedError):
        _EchoAgent(CONFIG).new().pursue("the suite passes")


@pytest.mark.parametrize(
    ("result", "because"),
    [
        (
            {
                "subtype": "error_max_turns",
                "is_error": False,
                "terminal_reason": "max_turns",
                "stop_reason": "tool_use",
                "errors": ["turn limit reached"],
            },
            "turn limit reached",
        ),
        (
            {
                "subtype": "success",
                "is_error": False,
                "terminal_reason": "aborted_streaming",
                "stop_reason": "end_turn",
            },
            "aborted_streaming",
        ),
        (
            {
                "subtype": "success",
                "is_error": False,
                "terminal_reason": "completed",
                "stop_reason": "tool_use",
            },
            "tool_use",
        ),
    ],
)
def test_claude_does_not_accept_an_unfinished_result(
    result: dict[str, object], because: str
) -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(session._read(json.dumps({"type": "result", **result})))

    assert len(events) == 1
    assert events[0].kind == "failed"
    assert because in events[0].text


def test_a_turn_held_to_a_shape_ends_on_the_tool_that_answered_it() -> None:
    """Which reads as an unfinished turn everywhere else, and is how a shaped turn ends.

    The last thing the model does is call `StructuredOutput`, so the result says
    `stop_reason: tool_use` -- and says the object beside it, which is the answer.
    """
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(
        session._read(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "terminal_reason": "completed",
                    "stop_reason": "tool_use",
                    "result": SHAPED,
                    "structured_output": {"capital": "Bern", "landlocked": True},
                }
            )
        )
    )

    assert [one.kind for one in events] == ["result"]
    assert events[0].text == SHAPED


def test_claude_accepts_a_completed_result() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).new()

    events = list(
        session._read(
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "terminal_reason": "completed",
                    "stop_reason": "end_turn",
                    "result": "done",
                }
            )
        )
    )

    assert len(events) == 1
    assert events[0].kind == "result"
    assert events[0].text == "done"


def test_a_loop_that_swallows_a_failed_turn_does_not_swallow_being_stopped() -> None:
    """What `/stop` rests on: being stopped must not arrive as a failed turn.

    A flow is a loop, and a loop that catches a failed turn goes round again.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()

    agent.stop()

    with pytest.raises(Stopped):
        session("anything")
    # And it is not what a ralph loop suppresses, or the loop would never end.
    assert not issubclass(Stopped, subprocess.CalledProcessError)


def test_an_agent_takes_the_name_a_flow_calls_it_unless_it_has_one() -> None:
    """`builder` says what a codename does not, and a trace groups the sessions under it."""
    named = ClaudeCodeAgent(CONFIG, name="actor")
    unnamed = ClaudeCodeAgent(CONFIG)

    named.rename("builder")
    unnamed.rename("reviewer")

    assert named.id == "actor"  # a name given where the agent was made is the name
    assert unnamed.id == "reviewer"


def test_a_watcher_that_raises_is_reported_rather_than_only_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A draw that failed is a thing the agent said that nobody will ever see.

    Swallowed in silence, a run whose rows all went that way reads as a turn sitting there
    doing nothing -- a hang to whoever is watching it and no trace at all afterwards. Once
    per kind, since a watcher that fails on one event fails on every one of them.
    """
    from hmz.runtime import telemetry

    agent = ClaudeCodeAgent(CONFIG)
    heard: list[str] = []
    reported: list[tuple[str, object]] = []

    def noted(name: str, **said: object) -> None:
        reported.append((name, said.get("kind")))

    monkeypatch.setattr(telemetry, "snag", noted)

    def broken(_agent: object, _session: object, event: Event) -> None:
        raise RuntimeError(event.kind)

    agent.watch(broken)
    agent.watch(lambda _agent, _session, event: heard.append(event.kind))

    for _ in range(3):
        agent._heard(Event(kind="tool", text="Read x.py"))
    agent._heard(Event(kind="text", text="hello"))

    # The turn is untouched, and so is every other watcher.
    assert heard == ["tool", "tool", "tool", "text"]
    assert reported == [("watcher-raised", "tool"), ("watcher-raised", "text")]


def test_a_report_that_will_not_be_made_is_not_a_turn_that_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The branch exists so a watcher cannot fail a flow; the reporting must not either."""
    from hmz.runtime import telemetry

    def unreportable(name: str, **said: object) -> None:
        del name, said
        raise OSError("no reporting from here")

    monkeypatch.setattr(telemetry, "snag", unreportable)
    agent = ClaudeCodeAgent(CONFIG)
    agent.watch(lambda _agent, _session, _event: (_ for _ in ()).throw(RuntimeError()))

    agent._heard(
        Event(kind="tool", text="Read x.py")
    )  # says nothing, and raises nothing


def test_a_question_reaches_whoever_is_driving_the_agent_and_nobody_otherwise() -> None:
    """A turn that stopped to ask must be answerable, and must not wait when it cannot be."""
    agent = ClaudeCodeAgent(CONFIG)
    heard: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            heard.append(event.kind) if event.kind == "asks" else None
        )
    )
    question = Question(text="Which way?", options=("left", "right"))

    assert agent.asked(question) is None  # nobody is driving it, so nobody answers

    agent.ask = lambda asked: asked.options[0]
    assert agent.asked(question) == "left"

    # Whatever is watching the agent is told what was asked, since the turns going past are
    # the one place a run is visible.
    assert heard == ["asks", "asks"]

    def raises(asked: Question) -> str:
        raise RuntimeError("the interface has gone")

    agent.ask = raises
    assert agent.asked(question) is None  # and a turn does not fail because asking did


def test_a_flow_waits_at_the_prompt_only_where_there_is_one() -> None:
    """A conversation needs somewhere to be told the next thing; a command line has nowhere."""
    agent = ClaudeCodeAgent(CONFIG)

    # Nobody is at a prompt, so a flow that is a conversation has had its conversation.
    assert agent.prompted() is None

    said = ["and then this", "this first"]
    agent.prompting = said.pop
    assert agent.prompted() == "this first"
    assert agent.prompted() == "and then this"

    def raises() -> str:
        raise RuntimeError("the interface has gone")

    agent.prompting = raises
    assert agent.prompted() is None  # and a flow ends rather than failing


def test_being_stopped_at_the_prompt_is_being_stopped() -> None:
    """A run ended by hand is written down as one, and `None` would write it down as done."""
    agent = ClaudeCodeAgent(CONFIG)

    def stops() -> str | None:
        agent.stop()  # as esc does, while the flow is waiting to be told something
        return None

    agent.prompting = stops
    with pytest.raises(Stopped):
        agent.prompted()
