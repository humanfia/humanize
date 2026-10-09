"""Claude Code: one `claude --print` held open, spoken to in stream-json a line at a time.

The process is a scripted one that answers each user message the driver writes with the lines
a test hands it -- so what is checked is the command it was started as, what was written to
it, and the turn read back out of what it wrote.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor import models
from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    ClaudeCodeSession,
    Event,
    Failed,
    Moment,
    Question,
    Verdict,
)
from hmz.coganchor.agents.base import KEEPING
from hmz.coganchor.fence import Fence
from tests.unit.coganchor.agents.doubles_u4 import Process, Spawner, offering

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from hmz.coganchor.agents import Occasion


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "claude-x", "effort": ""}


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


class _Claude:
    """What the scripted `claude` says: an answer per message, from a queue of answers."""

    def __init__(self, spawner: Spawner) -> None:
        self.answers: list[Callable[[Process, str], None]] = []
        self.model = "claude-x"
        self.mode = ""
        spawner.replying(self._heard)

    def _heard(self, proc: Process, said: Any) -> None:
        if said.get("type") != "user" or "uuid" in said:
            return
        session = (
            _flag(proc.args, "--session-id")
            if "--session-id" in proc.args
            else _flag(proc.args, "--resume")
        )
        if "--fork-session" in proc.args:
            session = f"{session}-forked"
        proc.say(
            {
                "type": "system",
                "subtype": "init",
                "session_id": session,
                "model": self.model,
                "permissionMode": self.mode or "default",
            }
        )
        answer = self.answers.pop(0) if self.answers else _says("done")
        answer(proc, session)


def _result(text: str = "done", **more: Any) -> dict[str, Any]:
    return {"type": "result", "subtype": "success", "result": text} | more


def _says(*lines: dict[str, Any] | str) -> Callable[[Process, str], None]:
    """An answer: these lines, and a result carrying the last string among them."""

    def answer(proc: Process, session: str) -> None:
        del session
        text = "done"
        for one in lines:
            if isinstance(one, str):
                text = one
                proc.say(_assistant({"type": "text", "text": one}))
            else:
                proc.say(one)
        if not any(
            isinstance(one, dict) and one.get("type") == "result" for one in lines
        ):
            proc.say(_result(text))

    return answer


def _assistant(
    *parts: dict[str, Any], message: str = "m1", **usage: int
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {"id": message, "content": list(parts), "usage": usage},
    }


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch) -> Spawner:
    """Every process a turn asks for, scripted rather than started."""
    return Spawner(monkeypatch)


@pytest.fixture
def claude(spawner: Spawner, monkeypatch: pytest.MonkeyPatch) -> _Claude:
    """The scripted CLI, on an account whose catalogue lists nothing."""
    monkeypatch.setattr(models, "offered", offering())
    return _Claude(spawner)


def _agent(**given: Any) -> ClaudeCodeAgent:
    return ClaudeCodeAgent(ClaudeCodeAgentConfig(**_DEFAULTS | given))


@pytest.mark.parametrize(
    "rules",
    [
        ("b", "a"),
        ("a", "a"),
        ("",),
        ("a,b",),
        tuple(f"r{n:02}" for n in range(33)),
    ],
)
def test_allowed_tools_must_be_unique_sorted_rules(rules: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="allowed_tools"):
        ClaudeCodeAgentConfig(model="m", effort="", allowed_tools=rules)


def test_a_session_is_one_process_started_as_print_over_stream_json(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    assert isinstance(session, ClaudeCodeSession)
    assert session("first") == "done"
    assert session("second") == "done"
    (proc,) = spawner.started
    argv = proc.args
    assert argv[:7] == [
        "claude",
        "--print",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    assert "--include-partial-messages" in argv
    assert _flag(argv, "--model") == "claude-x"
    assert json.loads(_flag(argv, "--settings")) == {}
    for absent in (
        "--effort",
        "--permission-mode",
        "--disallowedTools",
        "--allowedTools",
    ):
        assert absent not in argv
    assert proc.cwd == str(tmp_path)
    assert proc.environ["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert proc.stdin is not None
    assert [one["message"]["content"][0]["text"] for one in proc.stdin.said] == [
        "first",
        "second",
    ]
    assert session.id == _flag(argv, "--session-id")


@pytest.mark.parametrize(
    ("permission", "mode"),
    [
        ("read-only", "plan"),
        ("workspace-write", "acceptEdits"),
        ("auto", "auto"),
        ("bypass", "bypassPermissions"),
    ],
)
def test_each_rung_is_a_permission_mode(
    spawner: Spawner, claude: _Claude, tmp_path: Path, permission: str, mode: str
) -> None:
    claude.mode = mode
    _agent(permission=permission).new(tmp_path)("go")
    argv = spawner.last.args
    assert _flag(argv, "--permission-mode") == mode
    assert ("--permission-prompt-tool" in argv) is (permission == "bypass")


def test_what_the_config_says_reaches_the_command_line(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    agent = _agent(
        effort="high",
        service_tier="fast",
        web_search=False,
        allowed_tools=("Bash(git:*)", "Read"),
        partial_messages=False,
    )
    agent.disable_goals()
    agent.new(tmp_path)("go")
    argv = spawner.last.args
    assert _flag(argv, "--effort") == "high"
    assert json.loads(_flag(argv, "--settings")) == {"fastMode": True}
    denied = _flag(argv, "--disallowedTools").split(",")
    assert {"Agent", "Workflow", "CronCreate", "WebSearch", "WebFetch"} <= set(denied)
    assert _flag(argv, "--allowedTools") == "Bash(git:*),Read"
    assert "--include-partial-messages" not in argv


class _Shape(BaseModel):
    ok: bool


def test_a_shaped_turn_is_a_process_told_the_schema(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.answers = [_says(_result('{"ok": true}'))]
    session = _agent().new(tmp_path)
    assert session("judge", schema=_Shape) == _Shape(ok=True)
    schema = json.loads(_flag(spawner.last.args, "--json-schema"))
    assert schema["properties"]["ok"]["type"] == "boolean"


def test_a_moved_effort_resumes_the_conversation_in_a_new_process(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("one")
    first = spawner.last
    session.effort = "low"
    session("two")
    second = spawner.last
    assert second is not first
    assert first.stdin is not None
    assert first.stdin.closed
    assert _flag(second.args, "--resume") == session.id
    assert _flag(second.args, "--effort") == "low"


def test_a_turn_says_what_the_agent_did(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.answers = [
        _says(
            _assistant(
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "looking"},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Read",
                    "input": {"file_path": "a.py"},
                },
                {
                    "type": "tool_use",
                    "id": "t2",
                    "name": "Task",
                    "input": {"description": "dig"},
                },
            ),
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "t2"}]},
            },
            "found it",
        )
    ]
    events = list(_agent().new(tmp_path).stream("go"))
    assert [(one.kind, one.text, one.whose) for one in events[:-1]] == [
        ("reasoning", "hmm", ""),
        ("text", "looking", ""),
        ("tool", "Read a.py", ""),
        ("subagent", "Task dig", "t2"),
        ("subagent-ends", "Task dig", "t2"),
        ("text", "found it", ""),
    ]
    assert (events[-1].kind, events[-1].text) == ("result", "found it")


def test_a_reach_is_said_once_as_it_starts(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def partial(event: dict[str, Any]) -> dict[str, Any]:
        return {"type": "stream_event", "event": event}

    claude.answers = [
        _says(
            partial(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "tool_use", "id": "w", "name": "Write"},
                }
            ),
            partial(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": '{"file_path": "big.txt", "content": "',
                    },
                }
            ),
            partial({"type": "content_block_stop", "index": 0}),
            _assistant(
                {
                    "type": "tool_use",
                    "id": "w",
                    "name": "Write",
                    "input": {"file_path": "big.txt"},
                }
            ),
        )
    ]
    events = list(_agent().new(tmp_path).stream("go"))
    assert [(one.kind, one.text) for one in events if one.kind == "tool"] == [
        ("tool", "Write big.txt")
    ]


def test_what_a_turn_cost_is_the_rise_in_the_running_total(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def totals(inputs: int, outputs: int) -> dict[str, Any]:
        return {
            "modelUsage": {"claude-x": {"inputTokens": inputs, "outputTokens": outputs}}
        }

    claude.answers = [
        _says(_result("a", **totals(100, 10))),
        _says(_result("b", **totals(150, 30))),
    ]
    session = _agent().new(tmp_path)
    first = list(session.stream("one"))[-1]
    second = list(session.stream("two"))[-1]
    assert first.tokens == {"claude-x": 110}
    assert dict(second.spent) == {"input": 50, "output": 20}
    assert second.tokens == {"claude-x": 70}
    assert session.spent().total == 180


def test_what_each_message_cost_is_counted_as_it_lands(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.answers = [
        _says(
            _assistant({"type": "text", "text": "x"}, input_tokens=40, output_tokens=5),
            _result(
                "x",
                modelUsage={"claude-x": {"inputTokens": 40, "outputTokens": 9}},
            ),
        )
    ]
    session = _agent().new(tmp_path)
    result = list(session.stream("go"))[-1]
    assert dict(result.spent) == {"input": 40, "output": 9}
    assert dict(session.spent()) == {"input": 40, "output": 9}


@pytest.mark.parametrize(
    ("ending", "match"),
    [
        (_result("the model refused", is_error=True), "the model refused"),
        ({"type": "result", "subtype": "error_max_turns"}, "error_max_turns"),
        (_result("", stop_reason="max_tokens"), "max_tokens"),
        (_result("", terminal_reason="aborted"), "aborted"),
        (
            {
                "type": "result",
                "subtype": "error_during_execution",
                "errors": ["e1", "e2"],
            },
            "e1; e2",
        ),
    ],
)
def test_a_result_that_did_not_finish_the_turn_fails_it(
    spawner: Spawner,
    claude: _Claude,
    tmp_path: Path,
    ending: dict[str, Any],
    match: str,
) -> None:
    def fails(proc: Process, session: str) -> None:
        _says(ending)(proc, session)
        # Its stderr ended as well, so the driver need not wait out its drain.
        proc.stderr.end()

    claude.answers = [fails]
    session = _agent().new(tmp_path)
    with pytest.raises(Failed, match=match):
        session("go")
    with pytest.raises(RuntimeError):
        _ = session.id


def test_a_process_that_goes_away_fails_the_turn_with_what_it_said(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def leaves(proc: Process, session: str) -> None:
        del session
        proc.complain("the account was signed out")
        proc.exit(2)

    claude.answers = [leaves]
    with pytest.raises(Failed, match="signed out") as failed:
        _agent().new(tmp_path)("go")
    assert failed.value.returncode == 2


def test_a_model_it_does_not_know_is_said_once(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.model = "claude-default"
    session = _agent().new(tmp_path)
    notices = [one.text for one in session.stream("one") if one.kind == "notice"]
    assert len(notices) == 1
    assert "does not know the model 'claude-x'" in notices[0]
    assert not [one for one in session.stream("two") if one.kind == "notice"]


@pytest.mark.parametrize("running", ["claude-x", "claude-x-20260101", "claude-x[1m]"])
def test_the_model_it_was_told_under_another_spelling_is_no_news(
    spawner: Spawner, claude: _Claude, tmp_path: Path, running: str
) -> None:
    claude.model = running
    assert not [
        one for one in _agent().new(tmp_path).stream("go") if one.kind == "notice"
    ]


def _asking(request: dict[str, Any]) -> Callable[[Process, str], None]:
    """An answer that first asks for something over the control protocol."""
    return _says({"type": "control_request", "request_id": "r1", "request": request})


def _replied(proc: Process) -> dict[str, Any]:
    assert proc.stdin is not None
    (reply,) = [one for one in proc.stdin.said if one["type"] == "control_response"]
    assert reply["response"]["request_id"] == "r1"
    return reply["response"]["response"]


@pytest.mark.parametrize(
    ("permission", "behavior"), [("bypass", "allow"), ("read-only", "deny")]
)
def test_a_permission_is_granted_unless_the_rung_changes_nothing(
    spawner: Spawner, claude: _Claude, tmp_path: Path, permission: str, behavior: str
) -> None:
    claude.mode = "bypassPermissions" if permission == "bypass" else "plan"
    claude.answers = [
        _asking(
            {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "ls"}}
        )
    ]
    _agent(permission=permission).new(tmp_path)("go")
    replied = _replied(spawner.last)
    assert replied["behavior"] == behavior
    if behavior == "allow":
        assert replied["updatedInput"] == {"command": "ls"}


def test_a_hook_on_permission_request_asks_and_may_refuse(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.mode = "manual"
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that")

    agent = _agent(permission="bypass")
    agent.hooks.on(Moment.PERMISSION_REQUEST, refuse)
    claude.answers = [
        _asking(
            {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "rm"}}
        )
    ]
    agent.new(tmp_path)("go")
    assert _flag(spawner.last.args, "--permission-mode") == "manual"
    assert _replied(spawner.last) == {"behavior": "deny", "message": "not that"}
    assert [(one.tool, one.about) for one in seen] == [("Bash", "rm")]


@pytest.mark.parametrize(("answer", "behavior"), [("blue", "allow"), (None, "deny")])
def test_a_question_for_its_user_is_put_to_whoever_is_driving(
    spawner: Spawner,
    claude: _Claude,
    tmp_path: Path,
    answer: str | None,
    behavior: str,
) -> None:
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return answer

    agent = _agent()
    agent.ask = ask
    question = {"question": "Which?", "options": [{"label": "blue"}, {"label": "red"}]}
    claude.answers = [
        _asking(
            {
                "subtype": "can_use_tool",
                "tool_name": "AskUserQuestion",
                "input": {"questions": [question]},
            }
        )
    ]
    agent.new(tmp_path)("go")
    assert [(one.text, one.options) for one in asked] == [("Which?", ("blue", "red"))]
    replied = _replied(spawner.last)
    assert replied["behavior"] == behavior
    if answer is not None:
        assert replied["updatedInput"]["answers"] == {"Which?": "blue"}


def test_an_account_that_forbids_bypass_is_moved_and_remembered(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    agent = _agent(permission="bypass")
    assert not agent.declines()
    events = list(agent.new(tmp_path).stream("go"))
    assert any("will not run an agent at bypass" in one.text for one in events)
    assert spawner.last.stdin is not None
    (moved,) = [
        one for one in spawner.last.stdin.said if one["type"] == "control_request"
    ]
    assert moved["request"] == {"subtype": "set_permission_mode", "mode": "acceptEdits"}
    assert agent.declines()
    agent.new(tmp_path)("again")
    assert _flag(spawner.last.args, "--permission-mode") == "acceptEdits"


def test_bypass_refused_as_root_is_taken_again_at_accept_edits(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def script(proc: Process) -> None:
        if _flag(proc.args, "--permission-mode") == "bypassPermissions":
            proc.complain(
                "--dangerously-skip-permissions cannot be used with root/sudo privileges"
            )
            proc.exit(1)

    spawner.script = script
    claude.mode = "acceptEdits"
    events = list(_agent(permission="bypass").new(tmp_path).stream("go"))
    assert events[-1].text == "done"
    assert [_flag(one.args, "--permission-mode") for one in spawner.started] == [
        "bypassPermissions",
        "acceptEdits",
    ]


def test_a_word_put_in_mid_turn_is_heard_and_answered_with_the_turn(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def steered(proc: Process, said: Any) -> None:
        if said.get("type") == "user" and "uuid" in said:
            proc.say(
                {
                    "type": "command_lifecycle",
                    "state": "started",
                    "command_uuid": said["uuid"],
                },
                _result("both done"),
            )

    def working(proc: Process, session: str) -> None:
        del session
        proc.say(_assistant({"type": "text", "text": "working"}))

    claude.answers = [working]
    heard = spawner.heard
    assert heard is not None

    def either(proc: Process, line: str) -> None:
        heard(proc, line)
        steered(proc, json.loads(line))

    spawner.heard = either
    session = _agent().new(tmp_path)
    events: list[Event] = []
    for event in session.stream("go"):
        events.append(event)
        if event.kind == "text":
            session.interject("also this")
    assert [(one.kind, one.text) for one in events] == [
        ("text", "working"),
        ("took", "also this"),
        ("result", "both done"),
    ]


def test_interjecting_with_nothing_running_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no turn is running"):
        _agent().new(tmp_path).interject("hello")


def test_close_ends_the_process(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    session = _agent().new(tmp_path)
    session("go")
    session.close()
    assert spawner.last.stdin is not None
    assert spawner.last.stdin.closed


def test_reconfiguring_starts_a_process_at_the_new_settings(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    agent.reconfigure(replace(agent.config, web_search=False))
    session("two")
    assert len(spawner.started) == 2
    assert "WebSearch" in _flag(spawner.last.args, "--disallowedTools")


def test_it_enforces_no_part_of_a_fence_itself() -> None:
    held = Fence(read=("/a",), write=("/b",), online=False)
    assert _agent().natively(held) is held


# -- a conversation kept elsewhere, carried on -----------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Claude's own home, which is where its sessions are kept by an agent no run keeps."""
    at = tmp_path / "home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(at))
    monkeypatch.setenv(KEEPING, "off")
    return at


def _transcript(kept: Path, cwd: Path) -> Path:
    """Where Claude keeps conversation `told` had in `cwd`, under `kept`."""
    return kept / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", str(cwd)) / "told.jsonl"


def _kept(at: Path, cwd: Path, said: str) -> Path:
    """A copy of conversation `told`, had in `cwd`, as Claude lays out its home."""
    transcript = _transcript(at, cwd)
    transcript.parent.mkdir(parents=True)
    transcript.write_text(said)
    return at


def test_a_recalled_conversation_is_forked_as_carried_on_in_another_directory(
    spawner: Spawner, claude: _Claude, home: Path, tmp_path: Path
) -> None:
    """From the copy brought in, and never from one an earlier fork left there."""
    had, there = tmp_path / "had", tmp_path / "there"
    there.mkdir()
    snapshot = _kept(tmp_path / "snapshot", had, "the word is papaya\n")
    _kept(home, there, "an older copy\n")

    _agent().recall("told", snapshot, there).fork()("what was the word?")

    argv = spawner.last.args
    assert (_flag(argv, "--resume"), "--fork-session" in argv) == ("told", True)
    assert spawner.last.cwd == str(there)
    assert _transcript(home, had).read_text() == "the word is papaya\n"
    assert _transcript(home, there).read_text() == "the word is papaya\n"
    assert _transcript(snapshot, had).read_text() == "the word is papaya\n"


def test_a_second_copy_of_a_conversation_is_refused_where_the_first_was_brought_in(
    spawner: Spawner, claude: _Claude, home: Path, tmp_path: Path
) -> None:
    had, there = tmp_path / "had", tmp_path / "there"
    there.mkdir()
    early = _kept(tmp_path / "early", had, "one\n")
    late = _kept(tmp_path / "late", had, "one\ntwo\n")
    agent = _agent()
    agent.recall("told", early, there).fork()("go on")

    with pytest.raises(RuntimeError, match="another copy of conversation told"):
        agent.recall("told", late, there).fork()("go on")

    assert len(spawner.started) == 1
    assert _transcript(home, had).read_text() == "one\n"
    assert _transcript(home, there).read_text() == "one\n"
