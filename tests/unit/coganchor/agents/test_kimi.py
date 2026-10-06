"""`hmz.coganchor.agents.kimi`: turns submitted to the app server `kimi web` holds open."""

from __future__ import annotations

import io
import json
import os
import signal
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

import pytest
import websockets.sync.client

from hmz.coganchor.agents import (
    Failed,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    KimiCodeCLISession,
    driver,
)
from hmz.coganchor.agents.hooks import Moment
from hmz.coganchor.agents.kimi import LOG_LEVELS, READABLE
from hmz.coganchor.fence import Fence

from .doubles_u5 import UNREAL_PID, Process, configured, heard, spawning

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from hmz.coganchor.agents.event import Event, Question

_SESSION = "k-1"


@dataclass
class _Daemon:
    """The app server's HTTP API and its event socket, answering one session's turns."""

    messages: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "id": "a1",
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "tool_use", "tool_name": "Shell"},
                    {"type": "text", "text": "done"},
                ],
            },
            {
                "id": "u2",
                "role": "user",
                "content": [{"type": "text", "text": "a word put in"}],
            },
        ]
    )
    usage: dict[str, int] = field(
        default_factory=lambda: {"input_tokens": 9, "output_tokens": 4}
    )
    questions: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    approvals: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    ended: dict[str, Any] = field(default_factory=lambda: {"reason": "completed"})
    calls: list[tuple[str, str, Any]] = field(
        default_factory=list[tuple[str, str, Any]]
    )
    sent: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    headers: list[str] = field(default_factory=list[str])

    def answer(self, method: str, path: str) -> Any:
        route = path.removeprefix("/api/v1")
        at = f"/sessions/{_SESSION}"
        posts: dict[str, Any] = {
            "/sessions": {"id": _SESSION},
            f"{at}/prompts": {"user_message_id": "u1", "prompt_id": "p1"},
        }
        gets: dict[str, Any] = {
            at: {"usage": self.usage},
            f"{at}/status": {"busy": False},
            f"{at}/messages?after_id=u1": {"items": self.messages},
            f"{at}/questions?status=pending": {"items": self.questions},
            f"{at}/approvals?status=pending": {"items": self.approvals},
        }
        return (posts if method == "POST" else gets).get(route, {})

    def urlopen(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        del timeout
        url = request.full_url
        assert url.startswith("http://127.0.0.1:5494/api/v1/")
        self.headers.append(str(request.get_header("Authorization")))
        data = request.data
        body = json.loads(data) if isinstance(data, bytes) else None
        method = request.get_method()
        path = url.removeprefix("http://127.0.0.1:5494")
        self.calls.append((method, path.removeprefix("/api/v1"), body))
        return io.BytesIO(
            json.dumps({"code": 0, "data": self.answer(method, path)}).encode()
        )

    def connect(self, url: str, **_: Any) -> _Socket:
        assert url == "ws://127.0.0.1:5494/api/v1/ws"
        events: list[dict[str, Any]] = [
            {"type": "ack", "id": "hmz", "code": 0},
            {"type": "ping", "payload": {"nonce": "n1"}},
            {
                "type": "turn.step.completed",
                "session_id": _SESSION,
                "payload": {"usage": {"inputOther": 3, "output": 1}},
            },
            {"type": "turn.ended", "session_id": "someone-else", "payload": {}},
            {"type": "turn.ended", "session_id": _SESSION, "payload": self.ended},
        ]
        return _Socket(self, iter(events))

    def posted(self, path: str) -> list[Any]:
        return [
            body for method, at, body in self.calls if method == "POST" and at == path
        ]


@dataclass
class _Socket:
    daemon: _Daemon
    events: Iterator[dict[str, Any]]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def send(self, said: str) -> None:
        self.daemon.sent.append(json.loads(said))

    def recv(self, timeout: float) -> str:
        del timeout
        try:
            return json.dumps(next(self.events))
        except StopIteration:
            raise TimeoutError from None


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no configuration of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> _Daemon:
    held = _Daemon()
    monkeypatch.setattr(urllib.request, "urlopen", held.urlopen)
    monkeypatch.setattr(websockets.sync.client, "connect", held.connect)
    return held


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> list[Process]:
    """`kimi web`, which says where it listens and nothing else."""
    return spawning(
        monkeypatch,
        opening=["starting\n", "Kimi server: http://127.0.0.1:5494/#token=tok\n"],
    )


@pytest.fixture
def signalled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Every process group a server being stopped was signalled, rather than signalling it."""
    sent: list[tuple[int, int]] = []

    def killpg(pid: int, sign: int) -> None:
        sent.append((pid, sign))

    monkeypatch.setattr(os, "killpg", killpg)
    return sent


@pytest.fixture
def made(signalled: list[tuple[int, int]]) -> Iterator[Callable[..., KimiCodeCLIAgent]]:
    """Builds agents, and stops each of them -- and so its server -- at the end of the test."""
    del signalled
    agents: list[KimiCodeCLIAgent] = []

    def make(**said: Any) -> KimiCodeCLIAgent:
        agent = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(**configured("kimi-k2", said)))
        heard(agent)
        agents.append(agent)
        return agent

    yield make
    for one in agents:
        one.stop()


def _turn(session: KimiCodeCLISession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def test_kimi_is_driven_by_its_own_classes(
    made: Callable[..., KimiCodeCLIAgent],
) -> None:
    assert driver("kimi") == (KimiCodeCLIAgent, KimiCodeCLIAgentConfig)
    agent = made()
    assert agent.backend == "kimi"
    assert isinstance(agent.new(), KimiCodeCLISession)
    assert KimiCodeCLIAgent.counts == {"input", "output", "cache_read", "cache_write"}
    assert Moment.PERMISSION_REQUEST in KimiCodeCLIAgent.moments
    assert KimiCodeCLIAgent.pursues
    assert KimiCodeCLISession.steers


def test_every_log_level_but_the_silent_one_is_readable() -> None:
    assert "silent" in LOG_LEVELS
    assert set(READABLE) == set(LOG_LEVELS) - {"silent"}


@pytest.mark.parametrize(
    ("said", "named"),
    [
        ({"port": -1}, "port"),
        ({"port": 65536}, "port"),
        ({"log_level": "silent"}, "banner"),
        ({"log_level": "loud"}, "log_level"),
        ({"web_title": "  "}, "web_title"),
    ],
)
def test_a_config_the_server_cannot_run_at_is_refused(
    said: dict[str, Any], named: str
) -> None:
    with pytest.raises(ValueError, match=named):
        KimiCodeCLIAgentConfig(model="m", effort="", **said)


def test_a_fence_needs_nothing_while_no_server_is_starting(
    made: Callable[..., KimiCodeCLIAgent],
) -> None:
    fence = Fence(online=False)
    assert made().natively(fence) is fence


def test_a_turn_is_a_prompt_posted_and_the_messages_it_answers_with(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
) -> None:
    agent = made()
    session = agent.new(tmp_path)

    events = _turn(session, "hello")

    (process,) = server
    assert process.args == [
        "kimi",
        "web",
        "--no-open",
        "--port",
        "0",
        "--log-level",
        "error",
    ]
    assert set(daemon.headers) == {"Bearer tok"}
    assert daemon.posted("/sessions") == [{"metadata": {"cwd": str(tmp_path)}}]
    assert daemon.posted(f"/sessions/{_SESSION}/prompts") == [
        {
            "content": [{"type": "text", "text": "hello"}],
            "model": "kimi-k2",
            "swarm_mode": False,
        }
    ]
    assert {"type": "pong", "payload": {"nonce": "n1"}} in daemon.sent
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "Shell"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 9, "output": 4}
    assert events[-1].tokens == {"kimi-k2": 13}
    assert session.id == _SESSION


def test_one_server_serves_every_session_and_stops_with_the_agent(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    signalled: list[tuple[int, int]],
    tmp_path: Path,
) -> None:
    agent = made()

    _turn(agent.new(tmp_path))
    _turn(agent.new(tmp_path))
    agent.stop()

    assert len(server) == 1
    assert len(daemon.posted("/sessions")) == 2
    assert (UNREAL_PID, signal.SIGTERM) in signalled


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"open_browser": True}, ["kimi", "web", "--port"]),
        ({"port": 8123}, ["--port", "8123"]),
        ({"log_level": "debug"}, ["--log-level", "debug"]),
        ({"web_title": "mine"}, ["--web-title", "mine"]),
    ],
)
def test_the_server_is_started_as_the_config_says(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    del daemon
    _turn(made(**said).new(tmp_path))

    argv = server[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


@pytest.mark.parametrize(
    ("said", "told"),
    [
        ({"effort": "high"}, {"thinking": "high"}),
        ({"permission": "read-only"}, {"permission_mode": "manual", "plan_mode": True}),
        ({"permission": "auto"}, {"permission_mode": "yolo", "plan_mode": False}),
        (
            {"permission": "workspace-write"},
            {"permission_mode": "auto", "plan_mode": False},
        ),
    ],
)
def test_the_session_profile_carries_how_the_agent_is_configured(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
    said: dict[str, Any],
    told: dict[str, Any],
) -> None:
    del server
    _turn(made(**said).new(tmp_path))

    (profile,) = daemon.posted(f"/sessions/{_SESSION}/profile")
    assert profile["agent_config"] == {"model": "kimi-k2", "swarm_mode": False, **told}


@pytest.mark.parametrize(
    ("said", "disabled"),
    [({"web_search": False}, ["WebSearch", "FetchURL"]), ({"web_search": True}, [])],
)
def test_the_web_tools_are_said_on_the_prompt(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
    said: dict[str, Any],
    disabled: list[str],
) -> None:
    del server
    _turn(made(**said).new(tmp_path))

    (prompt,) = daemon.posted(f"/sessions/{_SESSION}/prompts")
    assert prompt["disabled_tools"] == disabled


@pytest.mark.parametrize(
    ("permission", "decision"),
    [("auto", "approved"), ("workspace-write", "approved"), ("read-only", "rejected")],
)
def test_an_approval_the_server_holds_is_answered_by_the_rung(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
    permission: str,
    decision: str,
) -> None:
    del server
    daemon.approvals = [
        {"approval_id": "ap1", "tool_name": "Shell", "action": "rm -rf"}
    ]

    _turn(made(permission=permission).new(tmp_path))

    (answer,) = daemon.posted(f"/sessions/{_SESSION}/approvals/ap1")
    assert answer["decision"] == decision


@pytest.mark.parametrize(
    ("answer", "chosen"),
    [
        ("b", {"kind": "single", "option_id": "o2"}),
        ("something else", {"kind": "other", "text": "something else"}),
        (None, {"kind": "skipped"}),
    ],
)
def test_a_question_the_server_holds_is_put_to_whoever_drives_the_agent(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
    answer: str | None,
    chosen: dict[str, Any],
) -> None:
    del server
    daemon.questions = [
        {
            "question_id": "q1",
            "questions": [
                {
                    "id": "x",
                    "question": "which one?",
                    "options": [{"id": "o1", "label": "A"}, {"id": "o2", "label": "B"}],
                }
            ],
        }
    ]
    agent = made()
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return answer

    agent.ask = ask

    _turn(agent.new(tmp_path))

    assert [(one.text, one.options) for one in asked] == [("which one?", ("A", "B"))]
    assert daemon.posted(f"/sessions/{_SESSION}/questions/q1") == [
        {"answers": {"x": chosen}}
    ]


def test_a_turn_the_server_says_failed_fails(
    made: Callable[..., KimiCodeCLIAgent],
    daemon: _Daemon,
    server: list[Process],
    tmp_path: Path,
) -> None:
    del server
    daemon.ended = {"reason": "failed", "error": {"message": "the model fell over"}}

    with pytest.raises(Failed) as failed:
        _turn(made().new(tmp_path))

    assert failed.value.stderr == "the model fell over"
    assert failed.value.output == "done"


def test_a_server_that_never_says_where_it_listens_fails_the_turn(
    made: Callable[..., KimiCodeCLIAgent],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    spawning(monkeypatch, opening=["no banner here\n"], status=1)

    with pytest.raises(Failed) as failed:
        _turn(made().new(tmp_path))

    assert "stopped without listening" in str(failed.value.stderr)


def test_a_word_put_in_with_no_turn_running_is_refused(
    made: Callable[..., KimiCodeCLIAgent], tmp_path: Path
) -> None:
    with pytest.raises(RuntimeError, match="no turn"):
        made().new(tmp_path).interject("hold on")
