"""`hmz.coganchor.agents.pi`: one pi process in RPC mode, held open across turns."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import Failed, PiAgent, PiAgentConfig, PiSession, driver
from hmz.coganchor.fence import Fence

from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from hmz.coganchor.agents.event import Event, Question


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no `models.json` of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)


def _agent(**said: Any) -> PiAgent:
    return PiAgent(PiAgentConfig(**configured("anthropic/sonnet", said)))


def _part(**event: Any) -> str:
    return line({"type": "message_update", "assistantMessageEvent": event})


def _ended(*content: dict[str, Any], **more: Any) -> str:
    return line(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": list(content),
                "usage": {"input": 5, "output": 2, "cacheRead": 1},
                **more,
            },
        }
    )


_SETTLED = line({"type": "agent_settled"})

#: What pi says in RPC mode for one prompt.
_SAID = (
    line({"type": "response", "command": "prompt", "success": True}),
    _part(type="thinking_end", content="hmm"),
    _part(type="toolcall_start", contentIndex=1, id="c1", toolName="bash"),
    _part(type="toolcall_delta", contentIndex=1, delta='{"command": "ls -la"'),
    _part(
        type="toolcall_end",
        contentIndex=1,
        toolCall={"id": "c1", "name": "bash", "arguments": {"command": "ls -la"}},
    ),
    _part(type="text_end", content="done"),
    "plain words pi printed\n",
    _ended({"type": "text", "text": "done"}),
    _SETTLED,
)


def _rpc(*said: str) -> Callable[[str], Iterable[str]]:
    """Answers every prompt with `said`, and every other line with nothing."""

    def answers(told: str) -> Iterable[str]:
        return said if json.loads(told).get("type") == "prompt" else ()

    return answers


def _told(told: list[str]) -> list[dict[str, Any]]:
    return [json.loads(one) for one in told]


def _turn(session: PiSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_pi_is_driven_by_its_own_classes() -> None:
    assert driver("pi") == (PiAgent, PiAgentConfig)
    agent = _agent()
    assert agent.backend == "pi"
    assert isinstance(agent.new(), PiSession)
    assert PiAgent.counts == {"input", "output", "cache_read", "cache_write"}
    assert PiSession.steers


@pytest.mark.parametrize("field", ["append_system_prompt", "skill_paths"])
def test_one_entry_where_a_sequence_belongs_is_refused(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        PiAgentConfig(**configured("m", {field: "one entry"}))


@pytest.mark.parametrize("field", ["append_system_prompt", "skill_paths"])
def test_an_entry_saying_nothing_is_refused(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        PiAgentConfig(**configured("m", {field: ("fine", "  ")}))


def test_a_turn_is_a_prompt_line_and_what_pi_says_until_it_settles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)
    assert session.named is None

    events = _turn(session, "hello")

    (process,) = spawned
    argv = process.args
    assert argv[:5] == ["pi", "--mode", "rpc", "--model", "anthropic/sonnet"]
    assert "--thinking" not in argv
    assert _told(process.told) == [{"type": "prompt", "message": "hello"}]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "bash ls -la"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 5, "output": 2, "cache_read": 1}
    assert events[-1].tokens == {"anthropic/sonnet": 8}
    assert session.id == option(argv, "--session-id")
    assert session.named == session.id


def test_the_process_is_held_open_and_told_a_new_effort_in_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(effort="low")
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session, "one")
    session.effort = "high"
    _turn(session, "two")

    (process,) = spawned
    assert option(process.args, "--thinking") == "low"
    assert _told(process.told) == [
        {"type": "prompt", "message": "one"},
        {"type": "set_thinking_level", "level": "high"},
        {"type": "prompt", "message": "two"},
    ]


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"effort": "medium"}, ["--thinking", "medium"]),
        (
            {"permission": "read-only"},
            ["--exclude-tools", "bash,edit,write,powershell"],
        ),
        (
            {"append_system_prompt": ("be brief", "be kind")},
            ["--append-system-prompt", "be brief", "--append-system-prompt", "be kind"],
        ),
        ({"skill_paths": ("/skills",)}, ["--skill", "/skills"]),
        ({"context_files": False}, ["--no-context-files"]),
        ({"extensions": False}, ["--no-extensions"]),
        ({"offline": True}, ["--offline"]),
    ],
)
def test_what_the_agent_is_configured_with_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


def test_a_bare_agent_adds_nothing_to_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(compiled=False)
    heard(agent)

    _turn(agent.new(tmp_path))

    (process,) = spawned
    assert len(process.args) == 7  # pi --mode rpc --model M --session-id ID
    assert "NODE_COMPILE_CACHE" not in (process.env or {})


def test_a_prompt_pi_refuses_fails_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    refused = {
        "type": "response",
        "command": "prompt",
        "success": False,
        "error": "no model by that name",
    }
    spawning(monkeypatch, answers=_rpc(line(refused)))
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.output == "no model by that name"


def test_a_turn_that_errs_without_saying_anything_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(
        monkeypatch,
        answers=_rpc(_ended(errorMessage="the request was cut short"), _SETTLED),
    )
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.output == "the request was cut short"


def _asking(method: str, **asked: Any) -> str:
    return line(
        {"type": "extension_ui_request", "id": "ui-1", "method": method, **asked}
    )


@pytest.mark.parametrize(
    ("method", "answer", "replied"),
    [
        ("confirm", "no", {"confirmed": False}),
        ("confirm", "yes", {"confirmed": True}),
        ("select", "b", {"value": "b"}),
        ("input", "typed", {"value": "typed"}),
        ("confirm", None, {"cancelled": True}),
    ],
)
def test_what_an_extension_asks_mid_turn_is_put_to_whoever_drives_the_agent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    method: str,
    answer: str | None,
    replied: dict[str, Any],
) -> None:
    spawned = spawning(
        monkeypatch,
        answers=_rpc(_asking(method, title="go on?", options=["a", "b"]), *_SAID),
    )
    agent = _agent()
    heard(agent)
    questions: list[Question] = []

    def ask(question: Question) -> str | None:
        questions.append(question)
        return answer

    agent.ask = ask

    _turn(agent.new(tmp_path))

    assert questions[0].text == "go on?"
    replies = [
        one for one in _told(spawned[0].told) if one["type"] == "extension_ui_response"
    ]
    assert replies == [{"type": "extension_ui_response", "id": "ui-1", **replied}]


def test_a_notice_from_an_extension_is_not_answered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(
        monkeypatch, answers=_rpc(_asking("notify", message="fyi"), *_SAID)
    )
    agent = _agent()
    heard(agent)

    _turn(agent.new(tmp_path))

    assert [one["type"] for one in _told(spawned[0].told)] == ["prompt"]


def test_a_word_put_in_with_no_turn_running_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no turn"):
        _agent().new(tmp_path).interject("hold on")


def _declared(tmp_path: Path, providers: dict[str, Any]) -> None:
    home = tmp_path / "home/.pi/agent"
    home.mkdir(parents=True)
    (home / "models.json").write_text(json.dumps({"providers": providers}))


def test_a_fence_lets_through_the_hosts_models_json_declares_for_the_model(
    tmp_path: Path,
) -> None:
    _declared(
        tmp_path,
        {
            "mine": {
                "baseUrl": "https://gw.example:8443/v1",
                "models": [{"id": "m", "baseUrl": "http://[::1]:9000"}],
            },
            "theirs": {"baseUrl": "https://elsewhere.example"},
        },
    )

    fence = _agent(model="mine/m", fence=Fence(online=False)).fenced()
    plain = _agent(model="nobody/m", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert plain is not None
    assert set(fence.hosts) - set(plain.hosts) == {"gw.example:8443", "[::1]:9000"}


def test_a_bare_model_name_reaches_every_provider_declared(tmp_path: Path) -> None:
    _declared(
        tmp_path,
        {"a": {"baseUrl": "https://a.example"}, "b": {"baseUrl": "https://b.example"}},
    )

    fence = _agent(model="bare", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert {"a.example", "b.example"} <= set(fence.hosts)


def test_an_agent_without_a_fence_has_none() -> None:
    assert _agent().fenced() is None
