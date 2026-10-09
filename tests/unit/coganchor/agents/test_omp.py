"""`hmz.coganchor.agents.omp`: pi's driver speaking to omp, and the places the two part company.

What is checked is what differs from pi -- the command line, the session asked for rather
than given, the turn ending on a terminal `agent_end`, the tool named off the message so far,
the rungs as omp's approval modes, and the providers declared in YAML -- each through a turn
of a scripted process. What omp says to a turn is pi's protocol, which `test_pi` checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence
from hmz.coganchor.agents import (
    OhMyPiAgent,
    OhMyPiAgentConfig,
    OhMyPiSession,
    driver,
)
from hmz.coganchor.fence import Fence

from .doubles_u4 import fenceable
from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from hmz.coganchor.agents.event import Event, Question

_MODEL = "deepseek/deepseek-v4-flash"

#: How every omp here is started, after the command and before anything a config adds.
_BARE = ["--mode", "rpc", "--model", _MODEL]


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no `models.yml` of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    monkeypatch.delenv("NODE_COMPILE_CACHE", raising=False)


def _agent(**said: Any) -> OhMyPiAgent:
    return OhMyPiAgent(OhMyPiAgentConfig(**configured(_MODEL, said)))


def _part(**event: Any) -> str:
    return line({"type": "message_update", "assistantMessageEvent": event})


def _ended(text: str) -> str:
    return line(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "usage": {"input": 5, "output": 2, "cacheRead": 1, "cacheWrite": 3},
                "stopReason": "stop",
            },
        }
    )


def _stopped(**more: Any) -> str:
    return line({"type": "agent_end", "messages": [], **more})


_PROMPTED = line({"type": "response", "command": "prompt", "success": True})

#: What omp 18.2.8 says in RPC mode for one prompt that ran one command.
_SAID = (
    _PROMPTED,
    line({"type": "agent_start"}),
    _part(type="thinking_end", contentIndex=0, content="hmm"),
    _part(
        type="toolcall_start",
        contentIndex=1,
        partial={
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "toolCall", "id": "call_1", "name": "bash", "arguments": {}},
            ],
        },
    ),
    _part(type="toolcall_delta", contentIndex=1, delta='{"command": "echo hi"'),
    _part(type="toolcall_delta", contentIndex=1, delta="}"),
    _part(
        type="toolcall_end",
        contentIndex=1,
        toolCall={
            "type": "toolCall",
            "id": "call_1",
            "name": "bash",
            "arguments": {"command": "echo hi"},
        },
    ),
    _part(type="text_end", contentIndex=0, content="done"),
    _ended("done"),
    _stopped(isTerminal=True),
)


def _rpc(
    *said: str, opened: Iterable[str] = ("s-1", "s-2")
) -> Callable[[str], Iterable[str]]:
    """Answers every prompt with `said`, and each `get_state` with the next session opened."""
    ids = iter(opened)

    def answers(told: str) -> Iterable[str]:
        asked = json.loads(told)
        if asked["type"] == "get_state":
            data = {"sessionId": next(ids)}
            return (
                line(
                    {
                        "type": "response",
                        "command": "get_state",
                        "id": asked["id"],
                        "success": True,
                        "data": data,
                    }
                ),
            )
        return said if asked["type"] == "prompt" else ()

    return answers


def _told(told: list[str]) -> list[dict[str, Any]]:
    return [json.loads(one) for one in told]


def _turn(session: OhMyPiSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_omp_is_driven_by_its_own_classes() -> None:
    assert driver("omp") == (OhMyPiAgent, OhMyPiAgentConfig)
    agent = _agent()
    assert agent.backend == "omp"
    assert isinstance(agent.new(), OhMyPiSession)
    assert OhMyPiSession.steers


def test_a_fresh_session_asks_omp_which_one_it_opened_and_ends_on_agent_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = spawned
    assert Path(process.args[0]).name == "omp"
    assert process.args[1:] == _BARE
    assert "NODE_COMPILE_CACHE" not in (process.env or {})
    assert _told(process.told) == [
        {"type": "get_state", "id": "hmz-session"},
        {"type": "prompt", "message": "hello"},
    ]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "bash echo hi"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {
        "input": 5,
        "output": 2,
        "cache_read": 1,
        "cache_write": 3,
    }
    assert session.id == "s-1"


def test_the_next_process_resumes_the_session_omp_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session, "one")
    session.close()
    _turn(session, "two")

    first, second = spawned
    assert option(first.args, "--resume") is None
    assert second.args[1:] == [*_BARE, "--resume", "s-1"]
    assert _told(second.told) == [{"type": "prompt", "message": "two"}]
    assert session.id == "s-1"


def test_a_fork_opens_on_top_of_its_parent_and_learns_its_own_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent()
    heard(agent)
    parent = agent.new(tmp_path)
    _turn(parent, "one")

    child = parent.fork()
    list(child.stream("two"))

    forked = spawned[-1]
    assert forked.args[1:] == [*_BARE, "--fork", "s-1"]
    assert _told(forked.told)[0] == {"type": "get_state", "id": "hmz-session"}
    assert (parent.id, child.id) == ("s-1", "s-2")


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({}, []),
        ({"effort": "high"}, ["--thinking", "high"]),
        ({"permission": "read-only"}, ["--approval-mode", "always-ask"]),
        ({"permission": "workspace-write"}, ["--approval-mode", "yolo"]),
        ({"permission": "auto"}, ["--approval-mode", "yolo"]),
        ({"permission": "bypass"}, ["--approval-mode", "yolo"]),
    ],
)
def test_the_command_line_is_the_model_its_effort_and_omps_approval_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert spawned[0].args[1:] == [*_BARE, *flags]


@pytest.mark.parametrize("unfinished", [{"isTerminal": False}, {"yielded": False}])
def test_an_agent_end_omp_says_is_not_the_last_does_not_end_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, unfinished: dict[str, bool]
) -> None:
    spawning(
        monkeypatch,
        answers=_rpc(
            _PROMPTED,
            _ended("retrying"),
            _stopped(**unfinished),
            _ended("the answer"),
            _stopped(isTerminal=True),
        ),
    )
    agent = _agent()
    heard(agent)

    events = _turn(agent.new(tmp_path))

    assert [(one.kind, one.text) for one in events] == [("result", "the answer")]


def test_a_prompt_omp_answers_itself_ends_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = {
        "type": "response",
        "command": "prompt",
        "success": True,
        "data": {"agentInvoked": False},
    }
    spawning(monkeypatch, answers=_rpc(line(local)))
    agent = _agent()
    heard(agent)

    events = _turn(agent.new(tmp_path), "/session")

    assert [(one.kind, one.text) for one in events] == [("result", "")]


@pytest.mark.parametrize(
    ("permission", "options", "replied"),
    [
        ("read-only", ["Approve", "Deny"], None),
        ("read-only", ["a", "b"], "a"),
        ("", ["Approve", "Deny"], "Approve"),
    ],
)
def test_an_approval_at_read_only_is_refused_and_anything_else_goes_to_the_person(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    permission: str,
    options: list[str],
    replied: str | None,
) -> None:
    asking = line(
        {
            "type": "extension_ui_request",
            "id": "ui-1",
            "method": "select",
            "title": "Allow tool: write",
            "options": options,
        }
    )
    spawned = spawning(monkeypatch, answers=_rpc(asking, *_SAID))
    agent = _agent(permission=permission)
    heard(agent)
    questions: list[Question] = []

    def ask(question: Question) -> str | None:
        questions.append(question)
        return question.options[0]

    agent.ask = ask

    _turn(agent.new(tmp_path))

    replies = [
        one for one in _told(spawned[0].told) if one["type"] == "extension_ui_response"
    ]
    value = "Deny" if replied is None else replied
    assert replies == [{"type": "extension_ui_response", "id": "ui-1", "value": value}]
    assert [one.options for one in questions] == (
        [] if replied is None else [tuple(options)]
    )


@pytest.mark.parametrize("named", ["models.yml", "models.yaml"])
def test_a_fence_lets_through_the_hosts_models_yml_declares_for_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, named: str
) -> None:
    home = tmp_path / "omp"
    home.mkdir()
    (home / named).write_text(
        "providers:\n"
        "  mine:\n"
        "    baseUrl: https://gw.example:8443/v1\n"
        "    models:\n"
        "      - id: m\n"
        "        baseUrl: http://[::1]:9000\n"
        "  theirs:\n"
        "    baseUrl: https://elsewhere.example\n"
    )
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home))

    mine = _agent(model="mine/m", fence=Fence(online=False)).fenced()
    plain = _agent(model="nobody/m", fence=Fence(online=False)).fenced()

    assert mine is not None
    assert plain is not None
    assert set(mine.hosts) - set(plain.hosts) == {"gw.example:8443", "[::1]:9000"}


def test_a_fence_that_cuts_the_network_is_not_said_to_omp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    spawned = spawning(monkeypatch, answers=_rpc(*_SAID))
    work = tmp_path / "work"
    work.mkdir()
    agent = _agent(fence=Fence(read=("/",), write=(str(work),), online=False))
    heard(agent)

    _turn(agent.new(work))

    argv = spawned[0].args
    assert argv[argv.index("--") + 2 :] == _BARE  # pi's would end `--offline`
