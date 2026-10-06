"""`hmz.coganchor.agents.qwen`: one Qwen Code process held open, spoken to in stream-json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz.coganchor.agents import (
    Failed,
    QwenCodeAgent,
    QwenCodeAgentConfig,
    QwenCodeSession,
    driver,
)
from hmz.coganchor.fence import Fence

from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from hmz.coganchor.agents.event import Event

_SETTINGS = "QWEN_CODE_SYSTEM_SETTINGS_PATH"


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no configuration of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for one in (_SETTINGS, "QWEN_CODE_SYSTEM_DEFAULTS_PATH", "QWEN_HOME"):
        monkeypatch.delenv(one, raising=False)


def _agent(**said: Any) -> QwenCodeAgent:
    return QwenCodeAgent(QwenCodeAgentConfig(**configured("qwen3-coder", said)))


def _message(*content: dict[str, Any], marked: str = "m1") -> str:
    return line(
        {
            "type": "assistant",
            "session_id": "qs-1",
            "message": {
                "id": marked,
                "content": list(content),
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        }
    )


def _result(said: str = "done", **more: Any) -> str:
    return line(
        {
            "type": "result",
            "session_id": "qs-1",
            "result": said,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "cache_read_input_tokens": 2,
            },
            **more,
        }
    )


#: A turn as `qwen --output-format stream-json` writes one.
_TURN = (
    line({"type": "system", "subtype": "init", "session_id": "qs-1"}),
    _message(
        {"type": "thinking", "thinking": "hmm"},
        {"type": "tool_use", "name": "read_file", "input": {"path": "a.py"}},
        {"type": "text", "text": "done"},
    ),
    "not json at all\n",
    _result(),
)


def _answering(*said: str) -> Callable[[str], Iterable[str]]:
    """Answers every turn written to it with the same lines."""

    def answers(told: str) -> Iterable[str]:
        del told
        return said

    return answers


def _turn(session: QwenCodeSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_qwen_is_driven_by_its_own_classes() -> None:
    assert driver("qwen") == (QwenCodeAgent, QwenCodeAgentConfig)
    agent = _agent()
    assert agent.backend == "qwen"
    assert isinstance(agent.new(), QwenCodeSession)
    assert QwenCodeAgent.counts == {"input", "output", "cache_read", "cache_write"}


def test_the_config_runs_the_cli_as_it_runs_itself_but_for_what_it_says() -> None:
    config = QwenCodeAgentConfig(model="m", effort="")
    assert config.headless_defaults
    assert config.compile_cache
    assert not config.partial_messages


def test_a_turn_is_a_user_line_and_the_events_it_answers_with(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello there")

    (process,) = spawned
    assert process.args[:5] == [
        "qwen",
        "--output-format",
        "stream-json",
        "--model",
        "qwen3-coder",
    ]
    assert process.args[-2:] == ["--input-format", "stream-json"]
    assert process.cwd == str(tmp_path)
    assert [json.loads(one) for one in process.told] == [
        {"type": "user", "message": {"role": "user", "content": "hello there"}}
    ]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "read_file a.py"),
        ("text", "done"),
        ("result", "done"),
    ]
    result = events[-1]
    assert dict(result.spent) == {"input": 10, "output": 4, "cache_read": 2}
    assert result.tokens == {"qwen3-coder": 16}
    assert session.id == "qs-1"


def test_the_process_is_held_open_across_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session, "one")
    _turn(session, "two")

    (process,) = spawned
    assert [json.loads(one)["message"]["content"] for one in process.told] == [
        "one",
        "two",
    ]
    assert "--session-id" in process.args
    session.close()
    assert process.poll() is not None


def test_a_message_said_twice_is_shown_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    said = _message({"type": "text", "text": "once"})
    spawning(monkeypatch, answers=_answering(said, said, _result("once")))
    agent = _agent()
    heard(agent)

    events = _turn(agent.new(tmp_path))

    assert [(one.kind, one.text) for one in events] == [
        ("text", "once"),
        ("result", "once"),
    ]


def test_partial_messages_stream_their_deltas_rather_than_the_whole(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def delta(kind: str, field: str, words: str) -> str:
        return line(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "delta": {"type": kind, field: words},
                },
            }
        )

    spawned = spawning(
        monkeypatch,
        answers=_answering(
            delta("thinking_delta", "thinking", "pondering"),
            delta("text_delta", "text", "do"),
            delta("text_delta", "text", "ne"),
            line({"type": "stream_event", "event": {"type": "message_stop"}}),
            _message({"type": "text", "text": "done"}),
            _result(),
        ),
    )
    agent = _agent(partial_messages=True)
    heard(agent)

    events = _turn(agent.new(tmp_path))

    assert "--include-partial-messages" in spawned[0].args
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "pondering"),
        ("text", "do"),
        ("text", "ne"),
        ("result", "done"),
    ]


@pytest.mark.parametrize(
    ("said", "approval", "excluded"),
    [
        ({}, None, None),
        (
            {"permission": "read-only"},
            "yolo",
            "edit,monitor,notebook_edit,run_shell_command,write_file",
        ),
        ({"permission": "workspace-write"}, "yolo", "web_fetch"),
        ({"permission": "auto"}, "yolo", None),
        ({"permission": "bypass", "web_search": False}, "yolo", "web_search,web_fetch"),
        (
            {"permission": "workspace-write", "web_search": False},
            "yolo",
            "web_fetch,web_search",
        ),
    ],
)
def test_what_the_agent_may_do_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    approval: str | None,
    excluded: str | None,
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    assert option(argv, "--approval-mode") == approval
    assert option(argv, "--exclude-tools") == excluded


def test_the_effort_is_written_into_a_settings_file_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent(effort="high")
    heard(agent)

    _turn(agent.new(tmp_path))

    env = spawned[0].env
    assert env is not None
    settings = Path(env[_SETTINGS])
    assert json.loads(settings.read_text())["model"] == {"reasoningEffort": "high"}
    defaults = json.loads((settings.parent / "system-defaults.json").read_text())
    assert defaults["general"] == {
        "preventSystemSleep": False,
        "enableAutoUpdate": False,
    }


def test_without_headless_defaults_no_defaults_layer_is_pointed_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent(effort="low", headless_defaults=False, compile_cache=False)
    heard(agent)

    _turn(agent.new(tmp_path))

    env = spawned[0].env
    assert env is not None
    assert not (Path(env[_SETTINGS]).parent / "system-defaults.json").exists()
    assert "NODE_COMPILE_CACHE" not in env


def test_a_new_effort_restarts_the_process_and_resumes_the_conversation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_answering(*_TURN))
    agent = _agent(effort="low")
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    session.effort = "high"
    _turn(session)

    assert len(spawned) == 2
    assert option(spawned[1].args, "--resume") == "qs-1"


def test_an_error_result_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(
        monkeypatch,
        answers=_answering(
            _result("", is_error=True, error={"message": "the turn could not finish"})
        ),
    )
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert "the turn could not finish" in str(failed.value.stderr)


def test_an_api_error_said_as_the_answer_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch, answers=_answering(_result("[API Error: the model is gone]")))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert str(failed.value.stderr) == "the model is gone"


def test_a_process_that_exits_without_answering_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def leaves(told: str) -> None:
        del told

    spawning(monkeypatch, answers=leaves, status=2, stderr="no way in\n")
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.returncode == 2
    assert "no way in" in str(failed.value.stderr)


class _Verdict(BaseModel):
    done: bool


def test_a_shaped_turn_is_a_command_of_its_own_holding_the_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(
        monkeypatch,
        answers=_answering(
            line({"type": "system", "session_id": "qs-1"}),
            _result('{"done": true}'),
        ),
    )
    agent = _agent()
    heard(agent)

    verdict = agent.new(tmp_path)("is it done?", schema=_Verdict)

    assert verdict == _Verdict(done=True)
    (process,) = spawned
    assert "--input-format" not in process.args
    assert json.loads(option(process.args, "--json-schema") or "")["properties"] == {
        "done": {"title": "Done", "type": "boolean"}
    }
    assert "".join(process.told).startswith("is it done?")


def test_an_open_fence_is_left_as_it_is() -> None:
    fence = Fence(write=("/",))
    assert _agent().natively(fence) is fence


def test_a_closed_fence_lets_the_settings_qwen_is_pointed_at_be_read(
    tmp_path: Path,
) -> None:
    fence = Fence(write=(str(tmp_path),), online=False)

    granted = _agent().natively(fence)

    assert len(granted.read) == len(fence.read) + 1
    assert granted.write == fence.write
