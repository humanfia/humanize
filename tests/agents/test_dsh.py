from __future__ import annotations

import importlib
import subprocess
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import pytest
from pydantic import BaseModel

from hmz.agents import DRIVEN, DshAgent, DshAgentConfig, DshSession, dsh

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


_REAL_HARNESS_TYPE = dsh._harness_type


@dataclass(slots=True)
class Notice:
    method: str
    payload: dict[str, Any]


class Subscription:
    def __init__(self, client: Client, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self.notices: deque[Notice] = deque()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        pass

    def next(self) -> Notice:
        return self.notices.popleft()


class Client:
    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.prompts: list[tuple[str, str]] = []

    def subscribe_session_notifications(self, session_id: str) -> Subscription:
        return Subscription(self, session_id)

    def session_prompt(
        self,
        session_id: str,
        content_blocks: list[dict[str, Any]],
        *,
        notification_subscription: Subscription,
    ) -> str:
        prompt = str(content_blocks[0]["text"])
        self.prompts.append((session_id, prompt))
        message_id = f"message-{len(self.prompts)}"
        scripted = self.harness.scripts.popleft()
        notification_subscription.notices.extend(
            [
                event(
                    session_id,
                    "agent/inbox/spliced",
                    {"inserted": [{"id": message_id}]},
                ),
                *(event(session_id, kind, data) for kind, data in scripted),
                Notice("session.status", {"sessionId": session_id, "status": "idle"}),
            ]
        )
        return message_id


class Harness:
    made: ClassVar[list[Harness]] = []
    next_scripts: ClassVar[deque[list[tuple[str, dict[str, Any]]]]] = deque()

    def __init__(self, **config: object) -> None:
        self.config = config
        self.client = Client(self)
        self.scripts = type(self).next_scripts
        self.started = False
        self.closed = False
        type(self).made.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


def event(session_id: str, kind: str, data: dict[str, Any]) -> Notice:
    return Notice(
        "session.event",
        {"sessionId": session_id, "event": {"type": kind, "data": data}},
    )


def assistant(
    text: str,
    *,
    reasoning: str = "",
    usage: dict[str, int] | None = None,
    turn: int = 1,
) -> tuple[str, dict[str, Any]]:
    content = [
        *([{"type": "reasoning", "text": reasoning}] if reasoning else []),
        {"type": "text", "text": text},
    ]
    return (
        "assistant/message",
        {
            "turn": turn,
            "step": 1,
            "message": {"content": content},
            "usage": usage or {},
        },
    )


def completed(turn: int = 1) -> tuple[str, dict[str, Any]]:
    return "turn/end", {"turn": turn, "reason": {"kind": "completed"}}


@pytest.fixture(autouse=True)
def sdk(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    Harness.made.clear()
    Harness.next_scripts.clear()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(dsh, "_harness_type", lambda: Harness)
    monkeypatch.setattr(dsh, "_runtime_args", lambda: ("/opt/dsh-runtime",))
    yield
    for harness in Harness.made:
        harness.close()


def configured(
    *,
    permission: str = "bypass",
    skills: tuple[str, ...] | None = None,
    provider: str = "",
) -> DshAgentConfig:
    return DshAgentConfig(
        model="deepseek-v4-flash",
        effort="high",
        permission=permission,
        skills=skills,
        provider=provider,
    )


def test_dsh_is_a_public_driven_agent() -> None:
    assert DRIVEN["dsh"] == (DshAgent, DshAgentConfig)
    assert DshAgent(configured()).backend == "dsh"
    assert DshAgent.pursues
    assert isinstance(DshAgent(configured()).new(), DshSession)


def test_a_turn_streams_reasoning_text_tools_usage_and_one_result(
    tmp_path: Path,
) -> None:
    Harness.next_scripts.append(
        [
            (
                "assistant/chunk",
                {
                    "turn": 1,
                    "step": 1,
                    "chunk": {"type": "reasoning-delta", "text": "thinking"},
                },
            ),
            (
                "tool/call",
                {"turn": 1, "step": 1, "name": "bash", "arguments": '{"cmd":"pwd"}'},
            ),
            assistant(
                "done",
                reasoning="thinking",
                usage={
                    "inputTokens": 11,
                    "outputTokens": 7,
                    "cacheReadTokens": 3,
                    "cacheWriteTokens": 2,
                    "reasoningTokens": 5,
                },
            ),
            completed(),
        ]
    )
    session = DshAgent(configured()).new(tmp_path)

    events = list(session.stream("work"))

    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "thinking"),
        ("tool", 'bash {"cmd":"pwd"}'),
        ("text", "done"),
        ("result", "done"),
    ]
    result = events[-1]
    assert result.tokens == {"deepseek-v4-flash": 23}
    assert dict(result.spent) == {
        "input": 11,
        "output": 7,
        "cache_read": 3,
        "cache_write": 2,
    }
    assert result.spent.total == 23  # reasoning is already inside output
    assert session.spent().total == 23


def test_follow_up_turns_resume_the_same_durable_session() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two", turn=2), completed(2)])
    )
    agent = DshAgent(configured())
    session = agent.new()

    assert session("first") == "one"
    session_id = session.id
    assert session("second") == "two"

    assert Harness.made[0].client.prompts == [
        (session_id, "first"),
        (session_id, "second"),
    ]
    assert agent.opened == [session_id]


def test_a_goal_uses_the_official_same_session_goal_tools() -> None:
    Harness.next_scripts.append(
        [
            assistant("still working"),
            completed(),
            assistant("done", turn=2),
            completed(2),
        ]
    )
    session = DshAgent(configured()).new()

    assert session.pursue("the suite passes") == "done"
    prompt = Harness.made[0].client.prompts[0][1]
    assert "create_goal" in prompt
    assert prompt.endswith("the suite passes")


def test_the_opening_session_id_is_visible_while_its_turn_is_running() -> None:
    Harness.next_scripts.append(
        [
            (
                "assistant/chunk",
                {
                    "turn": 1,
                    "step": 1,
                    "chunk": {"type": "text-delta", "text": "working"},
                },
            ),
            assistant("done"),
            completed(),
        ]
    )
    agent = DshAgent(configured())
    session = agent.new()
    streamed = session.stream("work")

    assert next(streamed).text == "working"
    opening = session.named
    assert opening is not None
    assert opening.startswith("session-")
    assert agent.opened == []

    assert [event.text for event in streamed] == ["done"]
    assert session.id == opening
    assert agent.opened == [opening]


def test_two_sessions_get_two_ids() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two"), completed()])
    )
    agent = DshAgent(configured())
    first, second = agent.new(), agent.new()

    first("first")
    second("second")

    assert first.id != second.id
    assert agent.opened == [first.id, second.id]


def test_a_failed_turn_is_common_failure_and_does_not_open_the_session() -> None:
    Harness.next_scripts.append(
        [
            assistant("partial"),
            (
                "turn/end",
                {
                    "turn": 1,
                    "reason": {
                        "kind": "error",
                        "error": {"message": "provider busy", "code": "SERVER"},
                    },
                },
            ),
        ]
    )
    agent = DshAgent(configured())
    session = agent.new()

    with pytest.raises(subprocess.CalledProcessError, match="dsh") as raised:
        session("work")

    assert raised.value.stderr.endswith("provider busy")
    assert session.named is None
    assert agent.opened == []
    assert Harness.made[0].closed


@pytest.mark.parametrize("reason", ["max-tokens", "blocked", "aborted", "interrupted"])
def test_every_non_completed_turn_end_is_a_failure(reason: str) -> None:
    Harness.next_scripts.append([("turn/end", {"turn": 1, "reason": {"kind": reason}})])

    with pytest.raises(subprocess.CalledProcessError):
        DshAgent(configured())("work")


def test_effort_changes_restart_the_runtime_but_resume_the_session() -> None:
    Harness.next_scripts.extend(
        ([assistant("one"), completed()], [assistant("two", turn=2), completed(2)])
    )
    session = DshAgent(configured()).new()
    session("first")
    session_id = session.id

    session.effort = "max"
    session("second")

    assert len(Harness.made) == 2
    assert Harness.made[0].closed
    assert [
        cast("dict[str, str]", one.config["env"])["HMZ_DSH_EFFORT"]
        for one in Harness.made
    ] == [
        "high",
        "max",
    ]
    assert Harness.made[1].client.prompts == [(session_id, "second")]


@pytest.mark.parametrize("effort", ["low", "ultra"])
def test_an_unsupported_effort_is_refused_before_startup(effort: str) -> None:
    agent = DshAgent(configured())
    agent.effort = effort

    with pytest.raises(ValueError, match="unsupported dsh effort"):
        agent("work")

    assert Harness.made == []


def test_permissions_the_sdk_cannot_enforce_are_refused() -> None:
    agent = DshAgent(configured(permission="read-only"))

    with pytest.raises(ValueError, match="permission must be 'bypass'"):
        agent("work")

    assert Harness.made == []


def test_an_explicit_skill_selection_the_sdk_cannot_enforce_is_refused() -> None:
    agent = DshAgent(configured(skills=("review",)))

    with pytest.raises(ValueError, match="does not support selecting skills"):
        agent("work")

    assert Harness.made == []


def test_a_missing_api_key_fails_before_runtime_start_and_reaches_watchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    agent = DshAgent(configured())
    heard: list[tuple[str, str]] = []
    agent.watch(lambda _agent, _session, event: heard.append((event.kind, event.text)))

    assert agent("hello", suppress=True) == ""

    failed = [text for kind, text in heard if kind == "failed"]
    assert len(failed) == 1
    assert "needs a DeepSeek API key" in failed[0]
    assert "ctrl+n" in failed[0]
    assert Harness.made == []


@pytest.mark.parametrize("way", ["env", "gateway", "login"])
def test_only_a_key_provider_can_authenticate_dsh(
    way: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz import providers

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    providers.add(
        "dsh",
        "legacy",
        way=way,
        env={"DEEPSEEK_API_KEY": "provider-key"},
    )
    agent = DshAgent(configured(provider="legacy"))
    heard: list[tuple[str, str]] = []
    agent.watch(lambda _agent, _session, event: heard.append((event.kind, event.text)))

    assert agent("hello", suppress=True) == ""

    assert [kind for kind, _text in heard].count("failed") == 1
    assert any("only supports API-key login" in text for _kind, text in heard)
    assert Harness.made == []


def test_shapes_are_asked_for_in_the_prompt() -> None:
    class Answer(BaseModel):
        done: bool

    Harness.next_scripts.append([assistant('{"done":true}'), completed()])
    session = DshAgent(configured()).new()

    assert session("decide", schema=Answer) == Answer(done=True)
    prompt = Harness.made[0].client.prompts[0][1]
    assert prompt.startswith("decide\n\nAnswer with JSON")
    assert '"done"' in prompt


def test_provider_environment_reaches_the_sdk_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz import providers

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    providers.add(
        "dsh",
        "mine",
        way="key",
        env={"DEEPSEEK_API_KEY": "provider-key"},
    )
    Harness.next_scripts.append([assistant("done"), completed()])

    DshAgent(configured(provider="mine")).new(tmp_path)("work")

    made = Harness.made[0].config
    assert made["env"] == {
        "DEEPSEEK_API_KEY": "provider-key",
        "HMZ_DSH_EFFORT": "high",
    }
    assert made["cwd"] == str(tmp_path)
    launch = cast("tuple[str, ...]", made["launch_args_override"])
    assert launch[0].endswith("/env")
    assert launch[1:] == ("-u", "DEEPSEEK_BASE_URL", "/opt/dsh-runtime")
    assert made["request_timeout_seconds"] == 180.0


def test_missing_sdk_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = importlib.import_module

    def missing(name: str) -> object:
        if name == "deepseek_harness":
            raise ModuleNotFoundError(name=name)
        return real_import(name)

    monkeypatch.setattr(dsh, "_harness_type", _REAL_HARNESS_TYPE)
    monkeypatch.setattr(importlib, "import_module", missing)

    with pytest.raises(ModuleNotFoundError, match=r"pip install 'hmz\[dsh\]'"):
        DshAgent(configured())("work")
