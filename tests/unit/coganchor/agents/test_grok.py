"""`hmz.coganchor.agents.grok`: Grok Build over ACP held open, or one `--single` run a turn."""

from __future__ import annotations

import json
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import (
    Failed,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    GrokBuildSession,
    driver,
)
from hmz.coganchor.agents.config import Unfenced
from hmz.coganchor.agents.event import Unrecoverable
from hmz.coganchor.agents.hooks import Moment
from hmz.coganchor.fence import Fence

from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from hmz.coganchor.agents.event import Event

_GATEWAY = ("GROK_GATEWAY_API_BACKEND", "GROK_XAI_API_BASE_URL", "XAI_API_KEY")


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, and no gateway account of whoever runs it."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for one in (*_GATEWAY, "GROK_CONFIG", "GROK_HOME"):
        monkeypatch.delenv(one, raising=False)


def _agent(**said: Any) -> GrokBuildAgent:
    return GrokBuildAgent(GrokBuildAgentConfig(**configured("grok-4", said)))


def _update(**update: Any) -> str:
    return line(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": "g-1", "update": update},
        }
    )


def _chunk(kind: str, words: str) -> str:
    return _update(sessionUpdate=kind, content={"type": "text", "text": words})


#: What one prompt is answered with, before the answer to the prompt itself.
_SAID = (
    _chunk("agent_thought_chunk", "hmm"),
    _update(
        sessionUpdate="tool_call",
        toolCallId="t1",
        toolName="read_file",
        title="Read a.py",
        rawInput={"path": "a.py"},
    ),
    _chunk("agent_message_chunk", "do"),
    _chunk("agent_message_chunk", "ne"),
    _update(
        sessionUpdate="response_completed",
        usage={"input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 1},
    ),
)


def _acp(
    said: Iterable[str] = _SAID, stop: str = "end_turn"
) -> Callable[[str], Iterable[str]]:
    """Grok's ACP server: a handshake, a session, and every prompt answered with `said`."""

    def answers(told: str) -> Iterable[str]:
        asked: dict[str, Any] = json.loads(told)
        method, at = asked.get("method"), asked.get("id")
        if method == "initialize":
            return [
                line({"jsonrpc": "2.0", "id": at, "result": {"protocolVersion": 1}})
            ]
        if method == "session/new":
            return [line({"jsonrpc": "2.0", "id": at, "result": {"sessionId": "g-1"}})]
        if method == "session/prompt":
            ended = {"jsonrpc": "2.0", "id": at, "result": {"stopReason": stop}}
            return [*said, line(ended)]
        return ()  # an answer of ours to something it asked

    return answers


def _told(told: list[str]) -> list[dict[str, Any]]:
    return [json.loads(one) for one in told]


def _turn(session: GrokBuildSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_grok_is_driven_by_its_own_classes() -> None:
    assert driver("grok") == (GrokBuildAgent, GrokBuildAgentConfig)
    agent = _agent()
    assert agent.backend == "grok"
    assert isinstance(agent.new(), GrokBuildSession)
    assert GrokBuildAgent.counts == {"input", "output", "cache_read", "cache_write"}
    assert Moment.PERMISSION_REQUEST in GrokBuildAgent.moments


def test_a_negative_turn_cap_is_refused() -> None:
    with pytest.raises(ValueError, match="max_turns"):
        GrokBuildAgentConfig(model="m", effort="", max_turns=-1)


def test_a_fenced_agent_cannot_join_the_leader() -> None:
    with pytest.raises(Unfenced, match="leader"):
        _agent(leader=True, fence=Fence(online=False))


def test_a_turn_over_acp_is_a_handshake_a_session_and_a_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_acp())
    agent = _agent(effort="high")
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = spawned
    assert process.args == [
        "grok",
        "agent",
        "--model",
        "grok-4",
        "--effort",
        "high",
        "--no-leader",
        "stdio",
    ]
    told = _told(process.told)
    assert [one["method"] for one in told] == [
        "initialize",
        "session/new",
        "session/prompt",
    ]
    assert told[1]["params"]["cwd"] == str(tmp_path)
    assert told[2]["params"] == {
        "sessionId": "g-1",
        "prompt": [{"type": "text", "text": "hello"}],
    }
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "read_file Read a.py"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 7, "output": 3, "cache_read": 1}
    assert events[-1].tokens == {"grok-4": 11}
    assert session.id == "g-1"


def test_the_process_is_held_open_across_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_acp())
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    _turn(session, "again")

    (process,) = spawned
    prompts = [one for one in _told(process.told) if one["method"] == "session/prompt"]
    assert [one["params"]["prompt"][0]["text"] for one in prompts] == ["do it", "again"]


@pytest.mark.parametrize("leader", [True, None])
def test_the_leader_is_joined_only_where_the_config_says(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, leader: bool | None
) -> None:
    spawned = spawning(monkeypatch, answers=_acp())
    agent = _agent(leader=leader)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    assert "--no-leader" not in argv
    assert ("--leader" in argv) == bool(leader)


@pytest.mark.parametrize(
    ("permission", "chosen"), [("auto", "allow"), ("bypass", "allow"), ("", "reject")]
)
def test_a_permission_asked_mid_turn_is_answered_by_the_rung(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, permission: str, chosen: str
) -> None:
    asked = line(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "session/request_permission",
            "params": {
                "sessionId": "g-1",
                "toolCall": {"title": "rm -rf build"},
                "options": [
                    {"kind": "allow_once", "optionId": "allow"},
                    {"kind": "reject_once", "optionId": "reject"},
                ],
            },
        }
    )
    spawned = spawning(monkeypatch, answers=_acp([asked, *_SAID]))
    agent = _agent(permission=permission)
    heard(agent)

    _turn(agent.new(tmp_path))

    (answer,) = [one for one in _told(spawned[0].told) if one.get("id") == 99]
    assert answer["result"]["outcome"] == {"outcome": "selected", "optionId": chosen}


def test_a_turn_ended_on_anything_but_its_end_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch, answers=_acp(stop="refusal"))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert "ended the turn on refusal" in str(failed.value.output)


def test_a_session_grok_will_not_open_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def refuses(told: str) -> Iterable[str]:
        asked: dict[str, Any] = json.loads(told)
        if asked.get("method") == "session/new":
            refused = {"code": -1, "message": "no session for you"}
            return [line({"jsonrpc": "2.0", "id": asked["id"], "error": refused})]
        return _acp()(told)

    spawning(monkeypatch, answers=refuses)
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert "no session for you" in str(failed.value.stderr)


#: What `grok --single` writes with `--output-format streaming-json`.
_SINGLE = (
    line({"type": "thought", "data": "hmm"}),
    line({"type": "tool_call", "toolCallId": "t1", "toolName": "grep", "rawInput": {}}),
    line({"type": "text", "data": "all "}),
    line({"type": "text", "data": "done"}),
    line({"type": "usage", "usage": {"input_tokens": 4, "output_tokens": 2}}),
    line({"type": "end", "sessionId": "c-1"}),
)


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        (
            {"permission": "read-only"},
            ["--always-approve", "--tools", "read_file,grep,list_dir"],
        ),
        (
            {"permission": "workspace-write"},
            ["--always-approve", "--disable-web-search"],
        ),
        ({"web_search": False}, ["--disable-web-search"]),
        ({"sandbox": "strict"}, ["--sandbox", "strict"]),
        ({"max_turns": 3}, ["--max-turns", "3"]),
        ({"subagents": False}, ["--no-subagents"]),
        ({"rules": "be brief"}, ["--rules", "be brief"]),
    ],
)
def test_what_acp_cannot_carry_is_a_single_run_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, opening=_SINGLE)
    agent = _agent(effort="low", **said)
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = spawned
    argv = process.args
    assert argv[:7] == [
        "grok",
        "--output-format",
        "streaming-json",
        "--model",
        "grok-4",
        "--effort",
        "low",
    ]
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags
    assert argv[-1] == "--single=hello"
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "grep"),
        ("text", "all done"),
        ("result", "all done"),
    ]
    assert dict(events[-1].spent) == {"input": 4, "output": 2}
    assert session.id == "c-1"


def test_a_single_run_resumes_the_session_the_first_one_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, opening=_SINGLE)
    agent = _agent(permission="read-only")
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    _turn(session)

    assert option(spawned[0].args, "--resume") is None
    assert option(spawned[1].args, "--resume") == "c-1"


def test_an_error_line_fails_a_single_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(
        monkeypatch,
        opening=[line({"type": "error", "message": "it went sideways"})],
    )
    agent = _agent(permission="read-only")
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert str(failed.value.stderr) == "it went sideways"


def test_the_environment_never_trusts_the_folder() -> None:
    assert _agent().environment()["GROK_FOLDER_TRUST"] == "0"


def test_a_messages_gateway_is_sent_its_key_as_a_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_GATEWAY_API_BACKEND", "messages")
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "http://gw.example/v1")
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setenv("GROK_CONFIG", json.dumps({"theme": "dark"}))

    overlay = json.loads(_agent().environment()["GROK_CONFIG"])

    assert overlay["theme"] == "dark"
    assert overlay["models"]["extra_headers"] == {
        "x-api-key": "test-key",
        "anthropic-version": "2023-06-01",
    }


def test_a_gateway_model_is_declared_in_grok_config_and_run_by_its_own_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GROK_GATEWAY_API_BACKEND", "responses")
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "http://gw.example/v1")
    spawned = spawning(monkeypatch, answers=_acp())
    agent = _agent()
    heard(agent)

    _turn(agent.new(tmp_path))

    named = option(spawned[0].args, "--model") or ""
    assert named.startswith("hmz-")
    assert named.endswith("/grok-4")
    declared = tomllib.loads((tmp_path / "home/.grok/config.toml").read_text())
    assert declared["model"][named] == {
        "model": "grok-4",
        "base_url": "http://gw.example/v1",
        "api_backend": "responses",
        "env_key": "XAI_API_KEY",
        "hidden": True,
    }


def test_a_gateway_speaking_no_api_grok_knows_is_unrecoverable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GROK_GATEWAY_API_BACKEND", "carrier-pigeon")
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "http://gw.example/v1")
    spawned = spawning(monkeypatch, answers=_acp())
    agent = _agent()
    heard(agent)

    with pytest.raises(Unrecoverable, match="carrier-pigeon"):
        _turn(agent.new(tmp_path))

    assert not spawned
