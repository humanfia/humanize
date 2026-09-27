"""A run held here, told as the records the interface draws every run from.

The records are what a run held anywhere else will be read by, so their shape is the contract:
each one plain JSON, the same keys every time, and nothing in one that only this process could
make sense of. What turns a run held here into them numbers its conversations the way their
transcripts are named, and keeps what is behind each key for the three things that still
reach past a record.
"""

from __future__ import annotations

import gc
import json
import time
from typing import TYPE_CHECKING, Any

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Event,
    HumanAgent,
    Usage,
)
from hmz.flows import Budget
from hmz.runtime.flowing import LiveCall
from hmz.tui.records import Following, called, ended, opened, record, started

if TYPE_CHECKING:
    import pytest

#: Every key an event record has, and nothing else.
EVENT = {
    "type",
    "run",
    "key",
    "session",
    "agent",
    "cli",
    "model",
    "ident",
    "kind",
    "text",
    "whose",
    "tokens",
    "spent",
    "at",
    "mono",
}


def _builder() -> ClaudeCodeAgent:
    """An agent named for the role it fills, as a run names the one behind each session."""
    return ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"), name="builder"
    )


def test_an_event_says_whose_it_is_and_nothing_only_this_process_can_read() -> None:
    agent = _builder()
    session = agent.new()
    session._adopt("s1")

    said = record(
        agent,
        session,
        Event(
            kind="result",
            text="done",
            tokens={"claude-opus-5": 40},
            spent=Usage(input=30, output=10),
        ),
        key="builder/2",
        run=3,
    )

    assert set(said) == EVENT
    assert said["type"] == "event"
    assert (said["run"], said["key"], said["session"]) == (3, "builder/2", "builder/2")
    assert (said["agent"], said["cli"], said["model"]) == (
        "builder",
        "claude",
        "claude-opus-5",
    )
    assert (
        said["ident"] == "s1"
    )  # what the backend calls it, which is how its log is found
    assert said["tokens"] == {"claude-opus-5": 40}
    assert said["spent"] == {"input": 30, "output": 10}
    assert json.loads(json.dumps(said)) == said  # JSON through and through


def test_what_an_agent_says_for_all_of_its_conversations_names_none() -> None:
    agent = _builder()

    said = record(agent, None, Event(kind="asks", text="which way?"), key="builder/1")

    assert said["key"] == "builder/1"  # the transcript it goes on
    assert said["session"] == ""  # which is not a conversation it was said in
    assert said["ident"] == ""


def test_a_session_opened_says_what_its_backend_counts() -> None:
    agent = _builder()
    session = agent.new()

    said = opened(4, "builder", "builder/1", agent, session)

    assert set(said) == {
        "type",
        "run",
        "role",
        "key",
        "agent",
        "cli",
        "model",
        "counts",
        "forks",
        "person",
        "kept",
        "mono",
    }
    assert said["counts"] == sorted(ClaudeCodeAgent.counts)
    assert said["forks"] is session.forks
    assert said["person"] is False
    assert said["kept"] == str(agent.kept())
    person = opened(4, "human", "human", HumanAgent(), None)
    assert person["person"] is True
    assert person["kept"] == ""


def test_a_run_starting_and_ending_are_records_too() -> None:
    before = time.monotonic()

    said = started(
        2,
        flow="chat",
        task="fix it",
        roles=("assistant",),
        outworlders=("human",),
        agents={"assistant": "claude/m:high"},
        budget=Budget(cost=1),
    )

    assert said["type"] == "started"
    assert said["roles"] == ["assistant"]
    assert said["outworlders"] == ["human"]
    assert said["budget"]["cost"] == 1
    assert (
        said["began"] >= before
    )  # on the clock every clock of the run is read against
    assert set(said) >= {"flow", "ref", "task", "by", "client", "envs", "params", "at"}
    assert ended(2, "budget", "spent")["how"] == "budget"


def test_the_flow_calls_name_the_call_that_made_each_by_its_place() -> None:
    outer = LiveCall("chat:chat", "chat", 1, 1.0, 1, None)
    inner = LiveCall("rlar:review", "review", 2, 2.0, 2, outer)

    said = called((outer, inner))

    assert said["type"] == "calls"
    assert [one["parent"] for one in said["calls"]] == [None, 0]
    assert said["calls"][1]["since"] == 2.0


def _following() -> tuple[Following, list[dict[str, Any]]]:
    """A run followed, and everything it has told."""
    told: list[dict[str, Any]] = []
    return Following(7, told.append, waiting=list), told


def test_conversations_are_numbered_per_role_in_the_order_the_run_opens_them() -> None:
    following, told = _following()
    one, two = _builder(), _builder()
    first, second = one.new(), two.new()

    following.opens("builder", one, first)
    following.opens("builder", two, second)
    following.hears(two, second, Event(kind="begins", text=""))

    assert [said["key"] for said in told] == ["builder/1", "builder/2", "builder/2"]
    assert all(said["run"] == 7 for said in told)
    assert one.waiting is not None  # the turn that starts next folds in what was held
    # And what is behind each key, for what still reaches past a record.
    assert [(key, session) for key, _, session in following.behind()] == [
        ("builder/1", first),
        ("builder/2", second),
    ]


def test_a_conversation_still_held_is_reached_however_many_opened_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What is kept past its run is bounded; what the run still holds is not.

    A planner opened first and talked to all day is still where a typed line goes after a
    loop beside it has opened a thousand sessions -- and one nothing holds any more is gone.
    """
    monkeypatch.setattr("hmz.tui.records._KEPT", 1)
    following, _ = _following()
    planner, worker, other = _builder(), _builder(), _builder()
    held, dropped = planner.new(), worker.new()
    following.opens("builder", planner, held)
    following.opens("builder", worker, dropped)
    following.opens("builder", other, other.new())  # and the one kept past its run

    assert following.at("builder/1") == (planner, held)  # held by the run, so reached
    del dropped
    gc.collect()
    assert following.at("builder/2") == (worker, None)  # held by nobody, so gone


def test_what_an_agent_says_for_all_of_them_goes_on_the_one_working() -> None:
    following, told = _following()
    agent = _builder()
    first, second = agent.new(), agent.new()
    following.opens("builder", agent, first)
    following.opens("builder", agent, second)
    following.hears(agent, first, Event(kind="begins", text=""))

    following.hears(agent, None, Event(kind="asks", text="which way?"))
    following.hears(agent, first, Event(kind="ends", text=""))
    following.hears(agent, None, Event(kind="asks", text="and now?"))

    working, newest = told[-3], told[-1]
    assert (working["key"], working["session"]) == ("builder/1", "")
    assert (newest["key"], newest["session"]) == ("builder/2", "")  # none working


def test_a_run_ends_having_said_the_calls_it_leaves_going() -> None:
    following, told = _following()

    following.ends("failed", "HarnessError: no")

    assert [said["type"] for said in told] == ["calls", "ended"]
    assert told[-1] == {
        "type": "ended",
        "run": 7,
        "how": "failed",
        "why": "HarnessError: no",
        "mono": told[-1]["mono"],
    }
