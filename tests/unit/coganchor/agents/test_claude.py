"""Claude Code: one `claude --print` held open, spoken to in stream-json a line at a time.

The process is a scripted one that answers each user message the driver writes with the lines
a test hands it -- so what is checked is the command it was started as, what was written to
it, and the turn read back out of what it wrote.
"""

from __future__ import annotations

import json
import plistlib
import re
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from pydantic import BaseModel

from hmz.coganchor import AnchorConfig, gateway, models, prices, providers
from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    ClaudeCodeSession,
    Event,
    Failed,
    Moment,
    Question,
    Unserved,
    Verdict,
)
from hmz.coganchor.agents import claude as driver
from hmz.coganchor.agents.base import KEEPING, AgentBase
from hmz.coganchor.agents.hooks import WAITING
from hmz.coganchor.fence import Fence
from hmz.coganchor.machines import AnchoredConfig
from hmz.coganchor.providers import Provider
from tests.unit.coganchor.agents.doubles_u4 import Process, Spawner, offering

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from hmz.coganchor.agents import Occasion
    from hmz.coganchor.machines import MachineConfig


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "claude-x", "effort": ""}

#: A fence that writes nothing, and one that writes somewhere: the two grants a driver reads
#: off the fence, each with the network open so that the web tools stay out of it.
_READS = Fence(online=True)
_WRITES = Fence(write=("/w",), online=True)


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def _text(said: Any) -> str:
    """The words of a user message written to Claude."""
    return str(said["message"]["content"][0]["text"])


class _Claude:
    """What the scripted `claude` says: an answer per message, from a queue of answers."""

    def __init__(self, spawner: Spawner) -> None:
        self.answers: list[Callable[[Process, str], None]] = []
        self.model = "claude-x"
        self.mode = ""
        #: What its `system/init` lists as slash commands and as skills.
        self.commands: list[str] = []
        self.skills: list[str] = []
        #: The models `set_model` takes, by what each resolves to.
        self.models = {"claude-y": "claude-y", "sonnet": "claude-sonnet-9"}
        spawner.replying(self._heard)

    def _heard(self, proc: Process, said: Any) -> None:
        request: dict[str, Any] = said.get("request") or {}
        if (
            said.get("type") == "control_request"
            and request.get("subtype") == "set_model"
        ):
            asked = str(request.get("model"))
            answer: dict[str, Any] = (
                {"subtype": "success", "response": {"model": self.models[asked]}}
                if asked in self.models
                else {"subtype": "error", "error": f"Model '{asked}' not found"}
            )
            proc.say(
                {
                    "type": "control_response",
                    "response": {"request_id": said["request_id"], **answer},
                }
            )
            return
        if said.get("type") != "user" or _text(said) == "also this":
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
                "slash_commands": self.commands,
                "skills": self.skills,
            }
        )
        answering = self.answers.pop(0) if self.answers else _says("done")
        answering(proc, session)


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


@pytest.fixture(autouse=True)
def managed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This machine's managed settings, kept in a folder of the test's and empty until said."""
    folder = tmp_path / "managed"
    (folder / "managed-settings.d").mkdir(parents=True)
    monkeypatch.setattr(driver, "MANAGED", (tmp_path / "device.plist", folder))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home"))
    return folder


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


def test_a_turn_never_lets_claude_fall_back_to_another_model(
    spawner: Spawner,
    claude: _Claude,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_NO_MODEL_FALLBACK", "0")

    _agent().new(tmp_path)("hi")

    assert spawner.last.environ["CLAUDE_CODE_NO_MODEL_FALLBACK"] == "1"


def test_an_agent_with_no_fence_is_told_nothing_of_a_grant(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    _agent().new(tmp_path)("go")
    argv = spawner.last.args
    for absent in (
        "--permission-mode",
        "--tools",
        "--permission-prompt-tool",
        "--disallowedTools",
    ):
        assert absent not in argv


def test_a_fence_that_writes_nothing_withholds_the_writing_tools_and_keeps_the_shell(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.mode = "bypassPermissions"
    _agent(fence=_READS).new(tmp_path)("go")
    argv = spawner.last.args
    assert _flag(argv, "--permission-mode") == "bypassPermissions"
    assert _flag(argv, "--tools") == "default"
    denied = _flag(argv, "--disallowedTools").split(",")
    assert denied == ["Edit", "Write", "NotebookEdit"]
    assert _flag(argv, "--permission-prompt-tool") == "stdio"
    assert "plan" not in argv


def test_a_fence_that_writes_somewhere_gives_every_tool(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.mode = "bypassPermissions"
    _agent(fence=_WRITES).new(tmp_path)("go")
    argv = spawner.last.args
    assert _flag(argv, "--permission-mode") == "bypassPermissions"
    assert _flag(argv, "--permission-prompt-tool") == "stdio"
    assert "--tools" not in argv
    assert "--disallowedTools" not in argv


def test_the_writing_tools_withheld_join_the_others_on_one_list(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.mode = "bypassPermissions"
    agent = _agent(fence=Fence(online=False))
    agent.disable_goals()
    agent.new(tmp_path)("go")
    argv = spawner.last.args
    assert argv.count("--disallowedTools") == 1
    denied = set(_flag(argv, "--disallowedTools").split(","))
    assert {"Edit", "Write", "NotebookEdit", "WebSearch", "WebFetch", "Agent"} <= denied
    assert "Bash" not in denied


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


def test_a_user_message_of_plain_text_is_read_past(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    # What Claude says back in the user's place after a `/compact`: text, not tool answers.
    claude.answers = [
        _says(
            {"type": "user", "message": {"content": "This session is being continued"}},
            "compacted",
        )
    ]

    events = list(_agent().new(tmp_path).stream("/compact", native=True))

    assert (events[-1].kind, events[-1].text) == ("result", "compacted")


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


def _hourly(split: bool) -> dict[str, Any]:
    """A turn total of 100,000 cache writes, all to the one-hour cache where it says so."""
    usage: dict[str, int] = {
        "inputTokens": 6,
        "outputTokens": 500,
        "cacheCreationInputTokens": 100_000,
    }
    if split:
        usage["cacheCreationEphemeral5mInputTokens"] = 0
        usage["cacheCreationEphemeral1hInputTokens"] = 100_000
    return {"modelUsage": {"claude-x": usage}}


@pytest.mark.parametrize("split", [True, False])
def test_one_hour_cache_writes_are_counted_beside_the_kinds_once(
    spawner: Spawner, claude: _Claude, tmp_path: Path, split: bool
) -> None:
    message = _assistant({"type": "text", "text": "x"})
    message["message"]["usage"] = {
        "input_tokens": 6,
        "output_tokens": 1,
        "cache_creation_input_tokens": 100_000,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 0,
            "ephemeral_1h_input_tokens": 100_000,
        },
    }

    def partial(event: dict[str, Any]) -> dict[str, Any]:
        return {"type": "stream_event", "event": event}

    claude.answers = [
        _says(
            partial({"type": "message_start", "message": {"id": "m1"}}),
            message,
            # What closes the message repeats the writes and leaves the split out.
            partial(
                {
                    "type": "message_delta",
                    "usage": {
                        "output_tokens": 500,
                        "cache_creation_input_tokens": 100_000,
                    },
                }
            ),
            _result("x", **_hourly(split)),
        )
    ]
    session = _agent().new(tmp_path)
    result = list(session.stream("go"))[-1]
    spent = session.spent()
    assert dict(spent) == {"input": 6, "output": 500, "cache_write": 100_000}
    assert spent.hour == 100_000
    assert dict(result.spent) == dict(spent)
    assert result.spent.hour == (100_000 if split else 0)


def test_a_message_past_a_long_context_line_is_counted_beside_the_kinds_once(
    spawner: Spawner,
    claude: _Claude,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def tiered(
        request: Mapping[str, float], model: str, *, hour: float = 0.0
    ) -> dict[str, float]:
        prompt = request.get("input", 0.0) + request.get("cache_read", 0.0)
        if model != "claude-long" or prompt <= 1000:
            return {}
        marked = {f"{kind}>1000": tokens for kind, tokens in request.items()}
        return marked | ({"cache_write_1h>1000": hour} if hour else {})

    monkeypatch.setattr(prices, "tiered", tiered)
    message = _assistant(
        {"type": "text", "text": "x"},
        input_tokens=6,
        cache_read_input_tokens=2000,
        cache_creation_input_tokens=40,
    )
    message["message"]["model"] = "claude-long"
    message["message"]["usage"]["cache_creation"] = {"ephemeral_1h_input_tokens": 40}

    def partial(event: dict[str, Any]) -> dict[str, Any]:
        return {"type": "stream_event", "event": event}

    used = {
        "inputTokens": 6,
        "outputTokens": 500,
        "cacheReadInputTokens": 2000,
        "cacheCreationInputTokens": 40,
    }
    claude.answers = [
        _says(
            partial(
                {
                    "type": "message_start",
                    "message": {"id": "m1", "model": "claude-long"},
                }
            ),
            message,
            message,
            # What closes the message names neither it nor the model that wrote it.
            partial({"type": "message_delta", "usage": {"output_tokens": 500}}),
            _result("x", modelUsage={"claude-long": used}),
        )
    ]
    session = _agent().new(tmp_path)
    result = list(session.stream("go"))[-1]
    spent = session.spent()
    marked = {
        "input>1000": 6,
        "cache_read>1000": 2000,
        "cache_write>1000": 40,
        "cache_write_1h>1000": 40,
        "output>1000": 500,
    }
    assert dict(spent) == {
        "input": 6,
        "output": 500,
        "cache_read": 2000,
        "cache_write": 40,
    }
    assert spent.tiered == marked
    assert dict(result.spent) == dict(spent)
    assert result.spent.tiered == marked


def test_one_hour_cache_writes_only_the_turn_total_names_are_counted(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.answers = [_says(_result("x", **_hourly(split=True)))]
    session = _agent().new(tmp_path)
    list(session.stream("go"))
    assert session.spent()["cache_write"] == 100_000
    assert session.spent().hour == 100_000


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


def test_a_session_claude_names_is_the_runs_even_where_the_process_goes_away(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    said: list[str] = []

    class Run:
        @property
        def keeps(self) -> Path:
            return tmp_path

        def opened(self, agent: AgentBase, session: str, parent: str = "") -> None:
            del agent, parent
            said.append(session)

    def leaves(proc: Process, session: str) -> None:
        del session
        proc.exit(2)

    claude.answers = [leaves]
    agent = _agent()
    agent.epic = Run()
    session = agent.new(tmp_path)
    with pytest.raises(Failed):
        session("go")
    # Named on its first line, which is all it said: written down, and not opened.
    (named,) = said
    assert session.named == named
    assert agent.opened == []


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
    """An answer that first asks for something over the control protocol.

    As the CLI does: only a process told `--permission-prompt-tool stdio` routes the request
    to its reader. Any other denies the tool by itself and names it in the result.
    """

    def answer(proc: Process, session: str) -> None:
        if "--permission-prompt-tool" in proc.args:
            asked = {"type": "control_request", "request_id": "r1", "request": request}
            _says(asked)(proc, session)
        else:
            denied = [{"tool_name": request["tool_name"]}]
            _says(_result(permission_denials=denied))(proc, session)

    return answer


def _replied(proc: Process) -> dict[str, Any]:
    assert proc.stdin is not None
    (reply,) = [one for one in proc.stdin.said if one["type"] == "control_response"]
    assert reply["response"]["request_id"] == "r1"
    return reply["response"]["response"]


@pytest.mark.parametrize("fence", [_READS, _WRITES])
def test_a_permission_is_granted_whatever_the_fence_writes(
    spawner: Spawner, claude: _Claude, tmp_path: Path, fence: Fence
) -> None:
    claude.mode = "acceptEdits"
    seen: list[Occasion] = []

    def watch(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict()

    agent = _agent(fence=fence, asks=False)
    agent.hooks.on(Moment.PERMISSION_REQUEST, watch)
    claude.answers = [
        _asking(
            {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "ls"}}
        )
    ]
    agent.new(tmp_path)("go")
    replied = _replied(spawner.last)
    assert replied == {"behavior": "allow", "updatedInput": {"command": "ls"}}
    assert [(one.tool, one.about) for one in seen] == [("Bash", "ls")]


@pytest.mark.parametrize("fence", [_READS, _WRITES])
def test_a_hook_on_permission_request_asks_and_may_refuse(
    spawner: Spawner, claude: _Claude, tmp_path: Path, fence: Fence
) -> None:
    claude.mode = "manual"
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that")

    agent = _agent(fence=fence)
    agent.hooks.on(Moment.PERMISSION_REQUEST, refuse)
    claude.answers = [
        _asking(
            {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "rm"}}
        )
    ]
    agent.new(tmp_path)("go")
    assert _flag(spawner.last.args, "--permission-mode") == "manual"
    assert ("--tools" in spawner.last.args) is (fence is _READS)
    assert _replied(spawner.last) == {"behavior": "deny", "message": "not that"}
    assert [(one.tool, one.about) for one in seen] == [("Bash", "rm")]


@pytest.mark.parametrize("fence", [_READS, _WRITES])
@pytest.mark.parametrize(("answer", "behavior"), [("blue", "allow"), (None, "deny")])
def test_a_question_for_its_user_is_put_to_whoever_is_driving(
    spawner: Spawner,
    claude: _Claude,
    tmp_path: Path,
    fence: Fence,
    answer: str | None,
    behavior: str,
) -> None:
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return answer

    claude.mode = "bypassPermissions"
    agent = _agent(fence=fence)
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


def test_an_agent_with_no_fence_routes_nothing(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return "blue"

    agent = _agent()
    agent.ask = ask
    question = {"question": "Which?", "options": [{"label": "blue"}]}
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
    assert "--permission-prompt-tool" not in spawner.last.args
    assert asked == []


@pytest.mark.parametrize("web_search", [True, None])
def test_web_search_not_switched_off_leaves_the_web_tools_alone(
    spawner: Spawner, claude: _Claude, tmp_path: Path, web_search: bool | None
) -> None:
    _agent(fence=_READS, web_search=web_search).new(tmp_path)("go")
    argv = spawner.last.args
    if "--disallowedTools" in argv:
        denied = set(_flag(argv, "--disallowedTools").split(","))
        assert not {"WebSearch", "WebFetch"} & denied


def test_an_account_that_forbids_bypass_is_moved_and_remembered(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    agent = _agent(fence=_WRITES)
    assert not agent.declines()
    events = list(agent.new(tmp_path).stream("go"))
    assert any(
        "will not run an agent at bypassPermissions" in one.text for one in events
    )
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
    events = list(_agent(fence=_READS).new(tmp_path).stream("go"))
    assert events[-1].text == "done"
    assert [_flag(one.args, "--permission-mode") for one in spawner.started] == [
        "bypassPermissions",
        "acceptEdits",
    ]


def _forbid(where: Path, settings: dict[str, Any]) -> None:
    """Writes managed settings, as JSON or as the plist an MDM profile installs."""
    where.parent.mkdir(parents=True, exist_ok=True)
    if where.suffix == ".plist":
        where.write_bytes(plistlib.dumps(settings))
    else:
        where.write_text(json.dumps(settings))


_NO_BYPASS = {"permissions": {"disableBypassPermissionsMode": "disable"}}


@pytest.mark.parametrize(
    "where",
    [
        "managed/managed-settings.json",
        "managed/managed-settings.d/20-security.json",
        "device.plist",
        "home/remote-settings.json",
    ],
)
def test_bypass_forbidden_by_managed_settings_is_never_launched(
    spawner: Spawner, claude: _Claude, tmp_path: Path, where: str
) -> None:
    _forbid(tmp_path / where, _NO_BYPASS)
    claude.mode = "acceptEdits"
    agent = _agent(fence=_WRITES)
    events = list(agent.new(tmp_path).stream("go"))
    said = [one.text for one in events if one.kind == "notice"]
    assert len(said) == 1
    assert "disableBypassPermissionsMode" in said[0]
    assert str(tmp_path / where) in said[0]
    assert [_flag(one.args, "--permission-mode") for one in spawner.started] == [
        "acceptEdits"
    ]
    assert spawner.last.stdin is not None
    assert not [one for one in spawner.last.stdin.said if one["type"] != "user"]
    events = list(agent.new(tmp_path).stream("again"))
    assert not [one for one in events if one.kind == "notice"]
    assert _flag(spawner.last.args, "--permission-mode") == "acceptEdits"


def test_a_permission_request_hook_runs_at_manual_whatever_the_policy(
    spawner: Spawner, claude: _Claude, managed: Path, tmp_path: Path
) -> None:
    _forbid(managed / "managed-settings.json", _NO_BYPASS)
    claude.mode = "manual"
    agent = _agent(fence=_WRITES)
    agent.hooks.on(Moment.PERMISSION_REQUEST, lambda occasion: Verdict())
    agent.new(tmp_path)("go")
    assert _flag(spawner.last.args, "--permission-mode") == "manual"


def test_a_setting_that_forbids_nothing_here_changes_nothing(
    spawner: Spawner, claude: _Claude, managed: Path, tmp_path: Path
) -> None:
    _forbid(managed / "managed-settings.json", {"model": "opus"})
    _forbid(managed / "managed-settings.d/.hidden.json", _NO_BYPASS)
    _forbid(managed / "managed-settings.d/notes.txt", _NO_BYPASS)
    claude.mode = "bypassPermissions"
    _agent(fence=_WRITES).new(tmp_path)("go")
    assert _flag(spawner.last.args, "--permission-mode") == "bypassPermissions"


@pytest.mark.parametrize(
    "policy",
    [
        {"allowManagedHooksOnly": True},
        {"disableAllHooks": True},
        {"strictPluginOnlyCustomization": ["hooks"]},
    ],
)
def test_a_gate_the_policy_drops_from_settings_is_served_over_the_stream(
    spawner: Spawner,
    claude: _Claude,
    managed: Path,
    tmp_path: Path,
    policy: dict[str, Any],
) -> None:
    _forbid(managed / "managed-settings.json", policy)
    claude.mode = "bypassPermissions"
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that")

    agent = _agent(fence=_WRITES)
    agent.hooks.on(Moment.PRE_TOOL_USE, refuse)
    called = {
        "subtype": "hook_callback",
        "callback_id": "hmz-gate",
        "input": {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "rm"},
        },
    }
    use = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "rm"}}
    claude.answers = [
        _says(
            {"type": "control_request", "request_id": "r1", "request": called},
            _assistant(use),
        )
    ]
    agent.new(tmp_path)("go")
    assert "hooks" not in json.loads(_flag(spawner.last.args, "--settings"))
    assert spawner.last.stdin is not None
    first = spawner.last.stdin.said[0]
    assert first["request"]["subtype"] == "initialize"
    assert first["request"]["hooks"] == {
        "PreToolUse": [
            {"matcher": None, "hookCallbackIds": ["hmz-gate"], "timeout": WAITING}
        ]
    }
    assert _replied(spawner.last) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "not that",
        }
    }
    # Once, from the callback: the tool the stream then announces is not fired again.
    assert [(one.tool, one.about) for one in seen] == [("Bash", "rm")]


def test_with_no_policy_the_gate_is_a_table_and_nothing_is_registered(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    claude.mode = "bypassPermissions"
    agent = _agent(fence=_WRITES)
    agent.hooks.on(Moment.PRE_TOOL_USE, lambda occasion: Verdict())
    agent.new(tmp_path)("go")
    assert "PreToolUse" in json.loads(_flag(spawner.last.args, "--settings"))["hooks"]
    assert spawner.last.stdin is not None
    assert not [one for one in spawner.last.stdin.said if one["type"] != "user"]


@pytest.mark.parametrize("where", ["managed-settings.json", "managed-mcp.json"])
def test_callbacks_the_policy_drops_are_refused_before_anything_starts(
    spawner: Spawner,
    claude: _Claude,
    managed: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    where: str,
) -> None:
    _forbid(managed / where, {"disableSideloadFlags": True, "mcpServers": {}})
    agent = _agent(fence=_WRITES)
    monkeypatch.setattr(agent.toolbox, "names", lambda: ("answer",))
    with pytest.raises(Unserved, match=re.escape(str(managed / where))):
        agent.new(tmp_path)("go")
    assert spawner.started == []


@pytest.mark.parametrize(("fence", "refused"), [(None, True), (_WRITES, False)])
def test_allow_rules_the_policy_drops_are_refused_only_where_they_are_the_grant(
    spawner: Spawner,
    claude: _Claude,
    managed: Path,
    tmp_path: Path,
    fence: Fence | None,
    refused: bool,
) -> None:
    _forbid(
        managed / "managed-settings.json", {"allowManagedPermissionRulesOnly": True}
    )
    agent = _agent(fence=fence, allowed_tools=("Read",))
    if refused:
        with pytest.raises(Unserved, match="allowManagedPermissionRulesOnly"):
            agent.new(tmp_path)("go")
        assert spawner.started == []
    else:
        agent.new(tmp_path)("go")
        assert len(spawner.started) == 1


def test_a_word_put_in_mid_turn_is_heard_and_answered_with_the_turn(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    def steered(proc: Process, said: Any) -> None:
        if said.get("type") == "user" and _text(said) == "also this":
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


def _shadowed(
    tmp_path: Path, *, native: bool = False, harness: str = "local"
) -> tuple[ClaudeCodeAgent, Path]:
    """An agent whose work is on another machine, at `/far/desk` as that machine names it.

    Its Claude runs here, in this machine's mirror of the far workspace under `tmp_path` --
    unless it is that machine's own (`native`), or under a harness on a third (`harness`).

    Returns:
      The agent, and this machine's mirror of where it works.
    """
    mirror = tmp_path / "mirror"
    (mirror / "desk").mkdir(parents=True)
    here = not native and harness == "local"
    anchor = AnchorConfig(
        target="ssh://box",
        workspace="/far",
        shadow=str(mirror) if here else None,
        native=native,
        harness=harness,
    )
    return _agent(machine=AnchoredConfig(anchor=anchor)), mirror / "desk"


def test_a_recalled_conversation_is_carried_into_the_mirror_claude_runs_in_here(
    spawner: Spawner, claude: _Claude, home: Path, tmp_path: Path
) -> None:
    """Where Claude, run here for work on another machine, looks: the mirror of where it works.

    From the copy brought in -- the longest, where it has more than one -- and never from one
    an earlier fork left there, nor into the far path, where no Claude here looks.
    """
    agent, mirrored = _shadowed(tmp_path)
    snapshot = _kept(tmp_path / "snapshot", tmp_path / "mirror" / "had", "the word\n")
    _kept(snapshot, tmp_path / "mirror" / "before", "the word is papaya\n")
    _kept(home, mirrored, "an older copy\n")

    agent.recall("told", snapshot, "/far/desk").fork()("what was the word?")

    argv = spawner.last.args
    assert (_flag(argv, "--resume"), "--fork-session" in argv) == ("told", True)
    assert _transcript(home, mirrored).read_text() == "the word is papaya\n"
    assert not list(home.glob("projects/-far*"))


def test_a_conversation_already_where_claude_runs_is_not_written_again(
    spawner: Spawner, claude: _Claude, home: Path, tmp_path: Path
) -> None:
    agent, mirrored = _shadowed(tmp_path)
    snapshot = _kept(tmp_path / "snapshot", tmp_path / "mirror" / "had", "one\n")
    agent.recall("told", snapshot, "/far/desk").fork()("go on")
    copy = _transcript(home, mirrored)
    first = copy.stat().st_ino

    agent.recall("told", snapshot, "/far/desk").fork()("go on again")

    assert len(spawner.started) == 2
    assert copy.stat().st_ino == first, "the same file, left as it was"
    assert copy.read_text() == "one\n"


def test_a_live_conversation_is_forked_from_the_mirror_it_was_had_in(
    spawner: Spawner, claude: _Claude, home: Path, tmp_path: Path
) -> None:
    """Its own transcript is the mirror's, not a copy left under the far path's name."""
    agent, mirrored = _shadowed(tmp_path)
    (tmp_path / "mirror" / "other").mkdir()
    session = agent.new("/far/desk")
    session("the word is papaya")
    name = f"{session.id}.jsonl"
    had = _transcript(home, mirrored).with_name(name)
    had.parent.mkdir(parents=True)
    had.write_text("the word is papaya\n")
    stale = home / "projects" / "-far-desk" / name
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n")

    session.fork(cwd="/far/other")("what was the word?")

    moved = _transcript(home, tmp_path / "mirror" / "other").with_name(name)
    assert moved.read_text() == "the word is papaya\n"
    assert not (home / "projects" / "-far-other").exists()


@pytest.mark.parametrize(
    ("native", "harness"),
    [(True, "local"), (False, "ssh://gpu")],
    ids=["native", "afar"],
)
def test_a_conversation_is_not_carried_for_a_claude_run_on_another_machine(
    spawner: Spawner,
    claude: _Claude,
    home: Path,
    tmp_path: Path,
    native: bool,
    harness: str,
) -> None:
    agent, _ = _shadowed(tmp_path, native=native, harness=harness)
    snapshot = _kept(tmp_path / "snapshot", tmp_path / "far" / "had", "one\n")

    with pytest.raises(NotImplementedError, match="on another machine"):
        agent.recall("told", snapshot, "/far/desk").fork()("go on")
    assert spawner.started == []


# --------------------------------------------------------------- through a LiteLLM gateway


class _Gateway:
    """A gateway that starts nothing: where it would be, and whether it was taken down."""

    started: ClassVar[list[_Gateway]] = []

    def __init__(self, provider: Provider) -> None:
        self.account = provider
        self.port = 4321
        self.url = "http://127.0.0.1:4321"
        self.key = "sk-master"
        self.running = True
        _Gateway.started.append(self)

    def stop(self) -> None:
        self.running = False


_ROUTED = Provider(
    cli="claude",
    name="gw",
    way="litellm-openai-key",
    env={"OPENAI_API_KEY": "upstream-secret"},
)


@pytest.fixture
def routed(monkeypatch: pytest.MonkeyPatch) -> list[_Gateway]:
    """An account litellm holds, and a gateway that is only pretended."""

    def find(cli: str, name: str) -> Provider | None:
        return _ROUTED if name == "gw" else Provider(cli, name, way="")

    monkeypatch.setattr(providers, "find", find)
    monkeypatch.setattr(gateway, "Gateway", _Gateway)
    monkeypatch.setenv("OPENAI_API_KEY", "lying-about")
    _Gateway.started = []
    return _Gateway.started


def test_a_turn_through_a_gateway_is_pointed_at_it_and_given_none_of_the_account(
    routed: list[_Gateway],
) -> None:
    agent = _agent(provider="gw")

    env = agent.environment()
    hushed = agent.hushed()

    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4321"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-master"
    assert "127.0.0.1" in env["NO_PROXY"].split(",")
    assert "OPENAI_API_KEY" in hushed
    assert "upstream-secret" not in env.values()
    assert len(routed) == 1
    assert agent.gateway is routed[0]


def test_claude_reaches_for_no_model_of_its_own_through_a_gateway(
    routed: list[_Gateway], spawner: Spawner, claude: _Claude
) -> None:
    _agent(provider="gw", model="gpt-5").new()("hi")

    env = spawner.last.environ
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "gpt-5"
    assert env["ANTHROPIC_SMALL_FAST_MODEL"] == "gpt-5"
    assert "OPENAI_API_KEY" not in env


def test_an_account_not_through_a_gateway_starts_none(routed: list[_Gateway]) -> None:
    agent = _agent()

    assert agent.gateway is None
    assert routed == []


def test_a_fenced_turn_through_a_gateway_may_reach_it_on_loopback(
    routed: list[_Gateway],
) -> None:
    fence = _agent(provider="gw", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert "127.0.0.1:4321" in fence.hosts


def test_a_stopped_agent_takes_its_gateway_down(routed: list[_Gateway]) -> None:
    agent = _agent(provider="gw")
    assert agent.gateway is not None

    agent.stop()

    assert not routed[0].running


def test_a_gateway_that_went_away_is_started_again(routed: list[_Gateway]) -> None:
    agent = _agent(provider="gw")
    first = cast("_Gateway", agent.gateway)
    first.running = False

    assert agent.gateway is not first
    assert len(routed) == 2


def test_a_cli_run_on_another_machine_is_refused_an_account_through_a_gateway(
    routed: list[_Gateway],
) -> None:
    machine = cast("MachineConfig", SimpleNamespace(anchor=AnchorConfig(native=True)))

    with pytest.raises(Unserved, match="local LiteLLM gateway"):
        _agent(provider="gw", machine=machine)
    assert routed == []


def _natively(session: ClaudeCodeSession, line: str) -> str:
    """Takes a turn of `line` as a person's native input, answering with its result."""
    (answer,) = [
        one.text for one in session.stream(line, native=True) if one.kind == "result"
    ]
    return answer


def _users(proc: Process) -> list[str]:
    """The user messages written to a process, in order."""
    assert proc.stdin is not None
    return [_text(one) for one in proc.stdin.said if one.get("type") == "user"]


def _controls(proc: Process) -> list[dict[str, Any]]:
    """The control requests written to a process, in order."""
    assert proc.stdin is not None
    return [
        one["request"]
        for one in proc.stdin.said
        if one.get("type") == "control_request"
    ]


def test_the_catalog_is_what_init_listed_less_what_hmz_keeps(
    claude: _Claude, tmp_path: Path
) -> None:
    claude.commands = [
        "compact",
        "context",
        "clear",
        "resume",
        "model",
        "effort",
        "config",
        "mcp",
        "__remote-workflow",
        "code-review",
    ]
    claude.skills = ["code-review", "anthropic-skills:pdf"]
    session = _agent().new(tmp_path)
    # Before its init, what it passes under `/` is not known: a chat passes such a line as
    # text. What is called and what is refused is, and is listed from the start.
    before = session.natives()
    assert {(one.sigil, one.how) for one in before if one.sigil != "/"} == {
        ("!", "emulate"),
        ("@", "pass"),
    }
    slashed = {one.name: one.how for one in before if one.sigil == "/"}
    assert "pass" not in slashed.values()
    assert {name for name, how in slashed.items() if how == "call"} == {
        "model",
        "effort",
    }
    assert {"config", "mcp", "agents", "login", "permissions", "doctor"} <= {
        name for name, how in slashed.items() if how == "refuse"
    }
    session("one")
    natives = session.natives()
    passed = {
        one.name: one for one in natives if one.how == "pass" and one.sigil == "/"
    }
    assert list(passed) == ["compact", "context", "code-review", "anthropic-skills:pdf"]
    assert passed["code-review"].about == "a skill"
    assert passed["compact"].about == "a Claude Code command"
    assert {one.name for one in natives if one.how == "call"} == {"model", "effort"}
    refused = {one.name: one.about for one in natives if one.how == "refuse"}
    assert {"config", "mcp", "agents", "login", "permissions", "doctor"} <= set(refused)
    assert set(refused.values()) == {
        "served only by Claude Code's own interactive interface"
    }
    assert {(one.sigil, one.how) for one in natives if one.sigil in "!@"} == {
        ("!", "emulate"),
        ("@", "pass"),
    }
    named = [one.name for one in natives if one.sigil == "/"]
    assert len(named) == len(set(named))
    for kept in ("clear", "resume", "__remote-workflow"):
        assert kept not in named


@pytest.mark.parametrize(
    "line", ["/compact keep the tests", "@notes.txt what is in it?", "/code-review"]
)
def test_a_native_line_claude_expands_goes_into_the_message_unchanged(
    spawner: Spawner, claude: _Claude, tmp_path: Path, line: str
) -> None:
    del claude
    session = _agent().new(tmp_path)
    assert _natively(session, line) == "done"
    assert _users(spawner.last) == [line]


def test_a_native_model_moves_the_conversation_without_a_turn(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    said = _natively(session, "/model sonnet")
    assert said == "Set model to sonnet (claude-sonnet-9)"
    assert agent.config.model == "sonnet"
    session("two")
    (proc,) = spawner.started  # moved over the control protocol, not by a restart
    assert _controls(proc) == [{"subtype": "set_model", "model": "sonnet"}]
    assert _users(proc) == ["one", "two"]


def test_a_native_model_before_any_turn_is_the_model_the_first_turn_starts_on(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    assert _natively(session, "/model claude-y") == "Set model to claude-y"
    assert spawner.started == []
    session("one")
    (proc,) = spawner.started
    assert _flag(proc.args, "--model") == "claude-y"
    assert _users(proc) == ["one"]
    assert _controls(proc) == []
    assert agent.config.model == "claude-y"


def test_a_model_moved_by_hand_starts_the_next_turn_on_it(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    agent.reconfigure(replace(agent.config, model="claude-y"))
    session("two")
    first, second = spawner.started
    assert _flag(first.args, "--model") == "claude-x"
    assert _flag(second.args, "--model") == "claude-y"
    assert _flag(second.args, "--resume") == session.id


def test_a_model_claude_does_not_know_is_refused_and_nothing_moves(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    assert _natively(session, "/model nonsense") == "Model 'nonsense' not found"
    assert _natively(session, "/model") == "Model: claude-x"
    assert agent.config.model == "claude-x"
    session("two")
    (proc,) = spawner.started
    assert _users(proc) == ["one", "two"]


def test_a_native_effort_resumes_the_conversation_at_the_new_rung(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    session("one")
    first = spawner.last
    assert _natively(session, "/effort low") == "Set effort to low"
    assert agent.config.effort == "low"
    assert _natively(session, "/effort") == "Effort: low"
    session("two")
    second = spawner.last
    assert second is not first
    assert _users(first) == ["one"]
    assert _flag(second.args, "--effort") == "low"
    assert _flag(second.args, "--resume") == session.id


def test_a_native_effort_outranks_a_rung_a_flow_set_on_the_agent(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent(effort="high")
    agent.effort = "low"
    session = agent.new(tmp_path)
    assert _natively(session, "/effort max") == "Set effort to max"
    session("one")
    assert _flag(spawner.last.args, "--effort") == "max"


def test_a_rung_claude_has_no_word_for_is_refused(
    claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent(effort="high")
    session = agent.new(tmp_path)
    assert "warp" in _natively(session, "/effort warp")
    assert agent.config.effort == "high"


@pytest.mark.parametrize("line", ["/model sonnet", "/effort low"])
def test_a_flow_s_prompt_is_text_whatever_it_starts_with(
    spawner: Spawner, claude: _Claude, tmp_path: Path, line: str
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    assert session(line) == "done"
    assert _users(spawner.last) == [line]
    assert _controls(spawner.last) == []
    assert (agent.config.model, agent.config.effort) == ("claude-x", "")


def test_a_native_model_line_saying_more_is_passed_as_it_was(
    spawner: Spawner, claude: _Claude, tmp_path: Path
) -> None:
    del claude
    agent = _agent()
    session = agent.new(tmp_path)
    line = "/model sonnet\nand then fix the bug"
    assert _natively(session, line) == "done"
    assert _users(spawner.last) == [line]
    assert agent.config.model == "claude-x"
