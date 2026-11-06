"""Where a turn goes when the place taking it cannot: tries again, then the next place.

A place is `CLI[@ACCOUNT]/MODEL`, and what is written down about it with `fallbacks.points`
and `fallbacks.retrying` -- into the test's own Humanize home -- is what a failed turn reads.
Each place here is a stand-in CLI on PATH: an `opencode run` that fails as many times as the
file `fails` beside it says before it answers, and a `claude` that is either absent or exits.
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import fallbacks
from hmz.coganchor.agents import (
    AgentBase,
    Budget,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Event,
    Failed,
    OpencodeAgent,
    OpencodeAgentConfig,
    SessionBase,
    Unrecoverable,
)
from tests.integration.doubles_agents import (
    CODEX,
    Standins,
    kinds,
    serving,
    standins,
)

if TYPE_CHECKING:
    from pathlib import Path

CLAUDE = ClaudeCodeAgentConfig(model="claude-stand-in", effort="high")
OPENCODE = OpencodeAgentConfig(model="opencode/stand-in", effort="high")

OPENCODE_RUN = r"""
import pathlib, time

said = sys.stdin.read()
note(said)
fails = pathlib.Path(sys.argv[0]).with_name("fails")
left = int(fails.read_text()) if fails.exists() else 0
if left:
    fails.write_text(str(left - 1))
    print("opencode: something broke", file=sys.stderr, flush=True)
    sys.exit(3)
if said == "hang":
    time.sleep(600)
session = flags.get("--session", "ses_stand_in")
out({"type": "text", "sessionID": session, "part": {"id": "p1", "type": "text",
                                                    "text": "from opencode: " + said}})
if said == "busy":
    time.sleep(600)
out({"type": "step_finish", "sessionID": session,
     "part": {"id": "p2", "type": "step-finish", "reason": "stop",
              "tokens": {"total": 3, "input": 2, "output": 1, "reasoning": 0,
                         "cache": {"read": 0, "write": 0}}}})
"""

CLAUDE_CRASHING = r"""
note()
print("claude: something broke", file=sys.stderr, flush=True)
sys.exit(3)
"""


@pytest.fixture
def places(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("opencode", OPENCODE_RUN)
    return held


def _failing(places: Standins, times: int) -> None:
    (places.bin / "fails").write_text(str(times))


def test_a_cli_that_is_not_installed_falls_back_to_the_next_place(
    places: Standins,
) -> None:
    fallbacks.points("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    agent = ClaudeCodeAgent(CLAUDE)

    assert agent("hello") == "from opencode: hello"

    stood_in = agent.stands_in()
    assert isinstance(stood_in, OpencodeAgent)
    assert stood_in.spec == "opencode/opencode/stand-in"
    assert places.said("opencode") == ["hello"]


def test_a_place_whose_turn_fails_falls_back_along_its_chain(
    places: Standins,
) -> None:
    places.install("claude", CLAUDE_CRASHING)
    fallbacks.points("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    said: list[Event] = []
    agent = ClaudeCodeAgent(CLAUDE)
    agent.watch(lambda _agent, _session, event: said.append(event))

    assert agent.new()("hello") == "from opencode: hello"

    assert len(places.calls("claude")) == 1
    assert kinds(said) == ["begins", "notice", "text", "result", "ends"]
    assert "carrying on as opencode/opencode/stand-in" in said[1].text


def test_a_place_with_no_chain_fails_as_a_turn_always_has(places: Standins) -> None:
    places.install("claude", CLAUDE_CRASHING)

    with pytest.raises(Failed) as failed:
        ClaudeCodeAgent(CLAUDE).new()("hello")

    assert failed.value.returncode == 3
    assert places.calls("opencode") == []


# Short of the 600s the endpoint would hold the turn without the watchdog, and long enough
# for litellm's first import on a cold runner.
@pytest.mark.timeout(60)
def test_a_place_fallen_back_to_that_the_watchdog_gives_up_on_fails_the_turn(
    places: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The turn is taken in a session of the place fallen back to, as a turn of that session's
    # own: the watchdog over it gives up on an endpoint gone silent as it would on its own,
    # and the turn fails, rather than answering with what a cut-off leaves,
    # which is nothing.
    places.install("claude", CLAUDE_CRASHING)
    fallbacks.points("claude/claude-stand-in", ["litellm/openai/stand-in"])
    monkeypatch.setenv("HUMANIZE_WATCHDOG", "1")
    for endpoint in serving():
        monkeypatch.setenv("OPENAI_BASE_URL", endpoint.url)
        monkeypatch.setenv("OPENAI_API_BASE", endpoint.url)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-stand-in")
        with pytest.raises(Failed, match="the watchdog stopped this turn"):
            ClaudeCodeAgent(CLAUDE).new()("hang")


def _cut_after_first_words(session: SessionBase, prompt: str) -> list[str]:
    """Takes a turn on a thread, cuts it off once the agent has said anything, and waits."""
    speaking = threading.Event()
    said: list[str] = []

    def taking() -> None:
        for event in session.stream(prompt):
            if event.kind == "text":
                speaking.set()
            elif event.kind == "result":
                said.append(event.text)

    turn = threading.Thread(target=taking, daemon=True)
    turn.start()
    assert speaking.wait(15)
    session.cut(why="the flow cut the conversation off")
    turn.join(15)
    assert not turn.is_alive()
    return said


def test_a_cut_ends_the_turn_where_it_was_moved_on_what_it_had_said(
    places: Standins,
) -> None:
    # Claude is not installed, so the turn is taken by Codex, on an app server that hears an
    # interrupt only at its next answer -- and the turn sends none after its first words.
    places.install("codex", CODEX)
    fallbacks.points("claude/claude-stand-in", ["codex/gpt-stand-in"])
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()
    try:
        assert _cut_after_first_words(session, "long") == ["busy"]
        # And the thread the cut turn was taking is the one the next turn goes on in.
        assert session("again") == "again"
        assert [
            json.loads(said.removeprefix("thread/resume "))["threadId"]
            for said in places.said("codex")
            if said.startswith("thread/resume ")
        ] == ["t-1"]
    finally:
        agent.stop()


def test_a_turn_failed_where_it_was_moved_leaves_no_conversation_open_there(
    places: Standins,
) -> None:
    # The budget is the turn's own, and failing it fails the turn wherever the turn went: the
    # conversation opencode named is not one the next turn goes on in.
    fallbacks.points("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    session = ClaudeCodeAgent(CLAUDE).new()
    session.budget = Budget(seconds=3, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("busy")
    session.budget = None

    assert session("again") == "from opencode: again"
    assert places.calls("opencode")[-1].flag("--session") is None


def test_a_cut_as_the_turn_moves_ends_it_before_the_next_place_is_asked(
    places: Standins,
) -> None:
    fallbacks.points("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()

    def cutting(_agent: AgentBase, whose: SessionBase | None, event: Event) -> None:
        if whose is session and "carrying on as" in event.text:
            session.cut(why="the flow cut the conversation off")

    agent.watch(cutting)
    try:
        assert session("hello") == ""
        assert places.said("opencode") == []
    finally:
        agent.stop()


def test_a_place_told_to_try_again_does_so_before_falling_back(
    places: Standins,
) -> None:
    fallbacks.retrying("opencode/opencode/stand-in", 1, "constant", 0)
    _failing(places, 1)

    assert OpencodeAgent(OPENCODE).new()("hello") == "from opencode: hello"

    assert places.said("opencode") == ["hello", "hello"]


def test_a_place_out_of_tries_and_places_raises_the_last_failure(
    places: Standins,
) -> None:
    fallbacks.retrying("opencode/opencode/stand-in", 1, "constant", 0)
    _failing(places, 5)

    with pytest.raises(Failed) as failed:
        OpencodeAgent(OPENCODE).new()("hello")

    assert failed.value.returncode == 3
    assert len(places.calls("opencode")) == 2


def test_a_turn_no_try_could_change_is_neither_tried_again_nor_moved(
    places: Standins,
) -> None:
    fallbacks.retrying("opencode/opencode/stand-in", 3, "constant", 0)
    fallbacks.points("opencode/opencode/stand-in", ["claude/claude-stand-in"])
    places.install("claude", CLAUDE_CRASHING)
    session = OpencodeAgent(OPENCODE).new()
    # Long enough for the stand-in to have started and said so under a loaded runner.
    session.budget = Budget(seconds=3, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("hang")

    assert len(places.calls("opencode")) == 1
    assert places.calls("claude") == []
