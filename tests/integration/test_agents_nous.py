"""Where a turn goes when the nous taking it cannot: tries again, then its `then`, or a graph.

A concrete nous is `CLI[@ACCOUNT]/MODEL[:EFFORT]`, and what is written down about one with
`nous.then`, `nous.retrying` and `nous.put` -- into the test's own Humanize home -- is what a
failed turn reads.
Each place here is a stand-in CLI on PATH: an `opencode run` that fails as many times as the
file `fails` beside it says before it answers, and a `claude` that is either absent or exits.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import nous
from hmz.coganchor.agents import (
    AgentBase,
    Budget,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Event,
    Failed,
    Moment,
    Occasion,
    OpencodeAgent,
    OpencodeAgentConfig,
    Question,
    SessionBase,
    Unrecoverable,
    Verdict,
)
from hmz.coganchor.fence import Fence
from hmz.coganchor.nous import Graph, Node, Nous
from tests.integration.doubles_agents import (
    CODEX,
    Standins,
    kinds,
    serving,
    standins,
)
from tests.integration.test_agents_claude import CLAUDE as CLAUDE_RUN
from tests.integration.test_agents_opencode import OPENCODE as OPENCODE_REACHING

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
    nous.then("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    agent = ClaudeCodeAgent(CLAUDE)

    assert agent("hello") == "from opencode: hello"

    stood_in = agent.stand_in("opencode/opencode/stand-in")
    assert isinstance(stood_in, OpencodeAgent)
    assert stood_in.spec == "opencode/opencode/stand-in:high"
    assert places.said("opencode") == ["hello"]


def test_a_place_whose_turn_fails_falls_back_along_its_chain(
    places: Standins,
) -> None:
    places.install("claude", CLAUDE_CRASHING)
    nous.then("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    said: list[Event] = []
    agent = ClaudeCodeAgent(CLAUDE)
    agent.watch(lambda _agent, _session, event: said.append(event))

    assert agent.new()("hello") == "from opencode: hello"

    assert len(places.calls("claude")) == 1
    assert kinds(said) == ["begins", "notice", "text", "result", "ends"]
    assert "carrying on as opencode/opencode/stand-in" in said[1].text


def test_a_hook_is_told_of_the_tool_a_stand_in_reached_for(places: Standins) -> None:
    places.install("claude", CLAUDE_CRASHING)
    places.install("opencode", OPENCODE_REACHING)
    nous.then("claude/claude-stand-in", ["opencode/opencode/stand-in"])
    agent = ClaudeCodeAgent(CLAUDE)
    seen: list[tuple[str, str]] = []
    agent.hooks.on(
        Moment.PRE_TOOL_USE,
        lambda occasion: seen.append((occasion.tool, occasion.about)),
    )

    assert agent.new()("hello") == "hello"

    assert seen == [("bash", "echo hello")]


def test_a_hook_gates_the_tool_a_stand_in_of_the_same_harness_reaches_for(
    places: Standins,
) -> None:
    # The original model's CLI is down; the one fallen back to asks its own hook table.
    places.install(
        "claude",
        CLAUDE_RUN.replace(
            "note()\n",
            'note()\nif flags.get("--model") == "claude-stand-in":\n    sys.exit(3)\n',
            1,
        ),
    )
    nous.then("claude/claude-stand-in", ["claude/claude-elsewhere"])
    agent = ClaudeCodeAgent(CLAUDE)
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="never that")

    agent.hooks.on(Moment.PRE_TOOL_USE, refuse, tool="Bash")

    decided = json.loads(agent.new()("gate"))["hookSpecificOutput"]

    assert decided["permissionDecisionReason"] == "never that"
    assert [(one.agent, one.about) for one in seen] == [(agent.id, "rm -rf /")]


def test_a_permission_a_stand_in_asks_for_is_put_to_the_hook_as_its_agents(
    places: Standins, monkeypatch: pytest.MonkeyPatch
) -> None:
    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        del fence
        return []

    # A fence is what routes requests over the stream; the wall itself is not put up.
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    places.install(
        "claude",
        CLAUDE_RUN.replace(
            "note()\n",
            'note()\nif flags.get("--model") == "claude-stand-in":\n    sys.exit(3)\n',
            1,
        ),
    )
    nous.then("claude/claude-stand-in", ["claude/claude-elsewhere"])
    agent = ClaudeCodeAgent(
        dataclasses.replace(CLAUDE, fence=Fence(write=("/w",), online=True))
    )
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that file")

    agent.hooks.on(Moment.PERMISSION_REQUEST, refuse)

    assert agent.new()("ask") == "deny:not that file"
    assert [(one.agent, one.tool) for one in seen] == [(agent.id, "Write")]


def test_a_question_a_stand_in_stops_to_ask_is_put_to_whoever_answers_for_the_agent(
    places: Standins,
) -> None:
    del places
    agent = ClaudeCodeAgent(CLAUDE)
    stood_in = agent.stand_in("opencode/opencode/stand-in")
    assert stood_in is not None
    told: list[str] = []
    agent.hooks.on(Moment.NOTIFICATION, lambda occasion: told.append(occasion.said))
    # Set after the stand-in was made, as a run sets it.
    agent.ask = lambda question: f"answered {question.text}"

    assert stood_in.asked(Question(text="Which?")) == "answered Which?"
    assert told == ["Which?"]


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
    nous.then("claude/claude-stand-in", ["litellm/openai/stand-in"])
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
    nous.then("claude/claude-stand-in", ["codex/gpt-stand-in"])
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
    nous.then("claude/claude-stand-in", ["opencode/opencode/stand-in"])
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
    nous.then("claude/claude-stand-in", ["opencode/opencode/stand-in"])
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
    nous.retrying("opencode/opencode/stand-in", 1, "constant", 0)
    _failing(places, 1)

    assert OpencodeAgent(OPENCODE).new()("hello") == "from opencode: hello"

    assert places.said("opencode") == ["hello", "hello"]


def test_a_place_out_of_tries_and_places_raises_the_last_failure(
    places: Standins,
) -> None:
    nous.retrying("opencode/opencode/stand-in", 1, "constant", 0)
    _failing(places, 5)

    with pytest.raises(Failed) as failed:
        OpencodeAgent(OPENCODE).new()("hello")

    assert failed.value.returncode == 3
    assert len(places.calls("opencode")) == 2


def test_a_turn_no_try_could_change_is_neither_tried_again_nor_moved(
    places: Standins,
) -> None:
    nous.retrying("opencode/opencode/stand-in", 3, "constant", 0)
    nous.then("opencode/opencode/stand-in", ["claude/claude-stand-in"])
    places.install("claude", CLAUDE_CRASHING)
    session = OpencodeAgent(OPENCODE).new()
    # Long enough for the stand-in to have started and said so under a loaded runner.
    session.budget = Budget(seconds=3, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("hang")

    assert len(places.calls("opencode")) == 1
    assert places.calls("claude") == []


def test_a_virtual_nous_is_an_agent_like_any_other(places: Standins) -> None:
    # Configured at `smart`, the agent is built where `smart` starts and its turns are walked
    # through it: claude is not installed, and the edge for that fault goes to opencode.
    nous.put(
        Nous(
            "smart",
            graph=Graph(
                "first",
                (
                    Node(
                        "first", use="claude/claude-stand-in", on=(("missing", "then"),)
                    ),
                    Node("then", use="opencode/opencode/stand-in:low"),
                ),
            ),
        )
    )
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-stand-in", effort="high", nous="smart")
    )

    assert agent.nous == "smart"
    assert agent("hello") == "from opencode: hello"
    stood_in = agent.stand_in("opencode/opencode/stand-in:low")
    assert stood_in is not None
    assert stood_in.effort == "low"


def test_a_fault_with_no_edge_fails_the_graph(places: Standins) -> None:
    nous.put(
        Nous(
            "smart",
            graph=Graph(
                "first",
                (
                    Node(
                        "first",
                        use="claude/claude-stand-in",
                        on=(("throttled", "then"),),
                    ),
                    Node("then", use="opencode/opencode/stand-in"),
                ),
            ),
        )
    )
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-stand-in", effort="high", nous="smart")
    )

    with pytest.raises(Failed) as failed:
        agent.new()("hello")

    assert failed.value.returncode == 127
    assert places.calls("opencode") == []


def test_a_graph_none_of_whose_nous_can_take_the_turn_fails_as_missing(
    places: Standins,
) -> None:
    # opencode has no effort `zzz`, so the only nous the graph reaches names no stand-in and
    # nothing runs: a failure of the `missing` kind that names it, not a bug.
    nous.put(
        Nous(
            "one",
            graph=Graph("only", (Node("only", use="opencode/opencode/stand-in:zzz"),)),
        )
    )
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-stand-in", effort="high", nous="one")
    )

    with pytest.raises(Failed) as failed:
        agent.new()("hello")

    assert failed.value.fault == "missing"
    assert failed.value.returncode != 127
    assert "opencode/opencode/stand-in:zzz" in str(failed.value)
    assert places.calls("opencode") == []
    assert places.calls("claude") == []


def test_a_balance_node_carries_on_to_another_member_and_keeps_it(
    places: Standins,
) -> None:
    # Two accounts' worth of one model, as two members: the one picked first is not installed
    # and the turn goes on to the other, which the conversation then starts at.
    places.install("claude", CLAUDE_CRASHING)
    nous.put(
        Nous(
            "pool",
            graph=Graph(
                "p",
                (
                    Node(
                        "p",
                        balance="least-busy",
                        among=(
                            ("claude/claude-stand-in", 2),
                            ("opencode/opencode/stand-in", 1),
                        ),
                    ),
                ),
            ),
        )
    )
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-stand-in", effort="high", nous="pool")
    ).new()

    assert session("hello") == "from opencode: hello"
    assert session("again") == "from opencode: again"

    assert len(places.calls("claude")) == 1
    assert places.said("opencode") == ["hello", "again"]


OPENCODE_FORKING = r"""
said = sys.stdin.read()
note(said)
session = flags.get("--session") or "ses_" + flags["--model"].rpartition("/")[2]
if "--fork" in argv:
    session += "_forked"
out({"type": "text", "sessionID": session, "part": {"id": "p1", "type": "text",
                                                    "text": session + ": " + said}})
out({"type": "step_finish", "sessionID": session,
     "part": {"id": "p2", "type": "step-finish", "reason": "stop",
              "tokens": {"total": 3, "input": 2, "output": 1, "reasoning": 0,
                         "cache": {"read": 0, "write": 0}}}})
"""


def test_a_session_answered_at_a_stand_in_is_forked_and_kept_as_that_conversation(
    places: Standins, tmp_path: Path
) -> None:
    # Two models dealt in turn: the second session's turns are all the other member's, in a
    # conversation of the stand-in's, and that conversation is the one a fork carries on.
    places.install("opencode", OPENCODE_FORKING)
    nous.put(
        Nous(
            "pool",
            graph=Graph(
                "p",
                (
                    Node(
                        "p",
                        balance="round-robin",
                        among=(
                            ("opencode/opencode/stand-in", 1),
                            ("opencode/opencode/other", 1),
                        ),
                    ),
                ),
            ),
        )
    )
    agent = OpencodeAgent(dataclasses.replace(OPENCODE, nous="pool"))
    first, second = agent.new(), agent.new()
    assert first("one") == "ses_stand-in: one"
    assert second("two") == "ses_other: two"

    assert second.id == second.named == "ses_other"
    assert second.forks
    child = second.fork()
    assert child("three") == "ses_other_forked: three"
    assert child.id == "ses_other_forked"
    assert child("four") == "ses_other_forked: four"
    # And by another agent at the same nous, which is how a flow's fork is taken.
    another = OpencodeAgent(dataclasses.replace(OPENCODE, nous="pool"))
    assert second.fork(into=another)("there") == "ses_other_forked: there"
    # The conversation forked goes on where it was, and a fork of it is cut where it was asked.
    late = second.fork()
    assert second("five") == "ses_other: five"
    with pytest.raises(RuntimeError, match="taken a turn since"):
        late("too late")

    # Kept as that conversation too: its files, where the agent's sessions are.
    kept = agent.kept()
    assert kept is not None
    (kept / "storage").mkdir(parents=True, exist_ok=True)
    (kept / "storage" / "ses_other.json").write_text("{}")
    second.keep(tmp_path / "copy")
    assert (tmp_path / "copy" / "storage" / "ses_other.json").read_text() == "{}"
