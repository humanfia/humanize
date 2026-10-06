"""`hmz.coganchor.agents.dsh`: DeepSeek Harness, driven through its Python SDK."""

from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import pytest
import yaml

from hmz.coganchor.agents import (
    AgentBase,
    DshAgent,
    DshAgentConfig,
    DshSession,
    Failed,
    SessionBase,
    driver,
)
from hmz.coganchor.agents.dsh import native_ready
from hmz.coganchor.agents.event import Unrecoverable

from .doubles_u5 import configured, heard

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from hmz.coganchor.agents.event import Event


@dataclass(frozen=True)
class _Notice:
    """One notification the runtime sends a subscriber."""

    method: str
    payload: dict[str, Any]


def _event(session: str, kind: str, **data: Any) -> _Notice:
    return _Notice(
        "session.event", {"sessionId": session, "event": {"type": kind, "data": data}}
    )


def _completed(session: str) -> list[_Notice]:
    """What the runtime says for a turn that went well."""
    return [
        _event(
            session,
            "assistant/chunk",
            turn=1,
            step=1,
            chunk={"type": "reasoning-delta", "text": "hmm"},
        ),
        _event(session, "tool/call", name="read", arguments="a.py"),
        _event(
            session,
            "assistant/chunk",
            turn=1,
            step=2,
            chunk={"type": "text-delta", "text": "do"},
        ),
        _event(
            session,
            "assistant/chunk",
            turn=1,
            step=2,
            chunk={"type": "text-delta", "text": "ne"},
        ),
        _event(
            session,
            "assistant/message",
            turn=1,
            step=2,
            message={"content": [{"type": "text", "text": "done"}]},
            usage={"inputTokens": 5, "outputTokens": 2, "cacheReadTokens": 1},
        ),
        _event(session, "turn/end", reason={"kind": "completed"}),
    ]


@dataclass
class _Subscription:
    notices: Iterator[_Notice]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def next(self) -> object:
        return next(self.notices)


class _Client:
    def __init__(self, runtime: _Runtime) -> None:
        self._runtime = runtime

    def subscribe_session_notifications(self, session_id: str) -> _Subscription:
        receipt = _event(session_id, "agent/inbox/spliced", inserted=[{"id": "msg-1"}])
        idle = _Notice("session.status", {"sessionId": session_id, "status": "idle"})
        noise = _event("someone-else", "turn/end", reason={"kind": "failed"})
        said = [noise, receipt, *self._runtime.turn(session_id), idle]
        return _Subscription(iter(said))

    def session_prompt(
        self,
        session_id: str,
        content_blocks: list[dict[str, Any]],
        *,
        notification_subscription: _Subscription,
    ) -> str:
        del notification_subscription
        if self._runtime.refuses is not None:
            raise self._runtime.refuses
        self._runtime.prompts.append((session_id, content_blocks))
        return "msg-1"


class _Harness:
    def __init__(self, runtime: _Runtime, **made: Any) -> None:
        self.made = made
        written = Path(made["cordis"]).read_text(encoding="utf-8")
        self.cordis: list[dict[str, Any]] = yaml.safe_load(written.replace("!!js ", ""))
        self.client = _Client(runtime)
        self.started = self.closed = False
        runtime.harnesses.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


@dataclass
class _Runtime:
    """What the fake SDK was asked to do, and what it answers a turn with."""

    turn: Callable[[str], list[_Notice]] = _completed
    refuses: Exception | None = None
    harnesses: list[_Harness] = field(default_factory=list[_Harness])
    prompts: list[tuple[str, list[dict[str, Any]]]] = field(
        default_factory=list[tuple[str, list[dict[str, Any]]]]
    )


_BUNDLED: list[dict[str, Any]] = [
    {"id": "llm-deepseek", "name": "@deepseek-ai/dsh-llm-deepseek"},
    {
        "id": "agent-core",
        "name": "@deepseek-ai/dsh-agent-core",
        "config": {"goals": {}},
    },
    {
        "id": "sessions",
        "name": "@deepseek-ai/dsh-sessions",
        "config": {"compression": "zstd"},
    },
]


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Runtime:
    """The SDK and its bundled runtime, as modules that start nothing."""
    held = _Runtime()
    bundled = tmp_path / "cordis.yml"
    bundled.write_text(yaml.safe_dump(_BUNDLED))

    def make(**made: Any) -> _Harness:
        return _Harness(held, **made)

    harness = types.ModuleType("deepseek_harness")
    vars(harness)["DeepSeekHarness"] = make
    errors = types.ModuleType("deepseek_harness.errors")
    vars(errors)["TransportClosedError"] = type(
        "TransportClosedError", (Exception,), {}
    )
    bundle = types.ModuleType("deepseek_harness_runtime")
    vars(bundle)["resolve_bundled_launch_args"] = lambda: ("node", "/dsh/runtime.js")
    vars(bundle)["bundled_default_config_path"] = lambda: bundled
    monkeypatch.setitem(sys.modules, "deepseek_harness", harness)
    monkeypatch.setitem(sys.modules, "deepseek_harness.errors", errors)
    monkeypatch.setitem(sys.modules, "deepseek_harness_runtime", bundle)
    return held


@pytest.fixture(autouse=True)
def dsh_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A dsh home of the test's own, and a key that is nobody's."""
    home = tmp_path / "dsh-home"
    home.mkdir()
    monkeypatch.setenv("DSH_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    return home


@pytest.fixture
def made() -> Iterator[Callable[..., DshAgent]]:
    """Builds agents, and closes every session they took a turn in at the end of the test.

    Held here until then: a session nobody holds is collected with its runtime still up.
    """
    sessions: list[SessionBase] = []

    def hold(agent: AgentBase, session: SessionBase | None, event: Event) -> None:
        del agent, event
        if session is not None and session not in sessions:
            sessions.append(session)

    def make(**said: Any) -> DshAgent:
        agent = DshAgent(DshAgentConfig(**configured("deepseek-v4", said)))
        agent.watch(hold)
        return agent

    yield make
    for one in sessions:
        one.close()


def _turn(session: DshSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def _ids(cordis: list[dict[str, Any]]) -> list[str]:
    return [one["id"] for one in cordis]


def test_dsh_is_driven_by_its_own_classes(
    made: Callable[..., DshAgent],
) -> None:
    assert driver("dsh") == (DshAgent, DshAgentConfig)
    agent = made()
    assert agent.backend == "dsh"
    assert isinstance(agent.new(), DshSession)
    assert DshAgent.counts == {"input", "output", "cache_read", "cache_write"}
    assert DshAgent.rungs == ("bypass",)
    assert DshAgent.pursues


def test_a_session_compression_dsh_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="session_compression"):
        DshAgentConfig(model="m", effort="", session_compression="gzip")


def test_a_turn_is_one_prompt_and_the_events_the_session_is_told(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made()
    session = agent.new(tmp_path)
    assert session.named is None

    events = _turn(session, "hello")

    ((asked, blocks),) = runtime.prompts
    assert blocks == [{"type": "text", "text": "hello"}]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "hmm"),
        ("tool", "read a.py"),
        ("text", "done"),
        ("result", "done"),
    ]
    assert dict(events[-1].spent) == {"input": 5, "output": 2, "cache_read": 1}
    assert events[-1].tokens == {"deepseek-v4": 8}
    assert session.id == asked
    assert asked.startswith("session-")


def test_the_runtime_is_started_where_the_session_works_with_its_key(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made(effort="high")

    _turn(agent.new(tmp_path))

    (harness,) = runtime.harnesses
    started = harness.made
    assert harness.started
    assert started["provider"] == "deepseek-official"
    assert started["model"] == "deepseek-v4"
    assert started["cwd"] == str(tmp_path)
    # `node` by name, or by the path a machine that keeps it off `PATH` has it at.
    node, script = started["launch_args_override"]
    assert Path(node).name == "node"
    assert script == "/dsh/runtime.js"
    assert started["env"]["DEEPSEEK_API_KEY"] == "test-key"
    assert started["env"]["HMZ_DSH_EFFORT"] == "high"


def test_a_session_keeps_its_runtime_across_turns_and_resumes_its_conversation(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made()
    session = agent.new(tmp_path)

    _turn(session)
    _turn(session)

    assert len(runtime.harnesses) == 1
    first, second = (asked for asked, _ in runtime.prompts)
    assert first == second


def test_a_new_effort_starts_a_new_runtime(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made(effort="low")
    session = agent.new(tmp_path)

    _turn(session)
    session.effort = "high"
    _turn(session)

    old, new = runtime.harnesses
    assert old.closed
    assert new.made["env"]["HMZ_DSH_EFFORT"] == "high"


def test_closing_the_session_closes_its_runtime(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made()
    session = agent.new(tmp_path)

    _turn(session)
    session.close()

    assert runtime.harnesses[0].closed


@pytest.mark.parametrize(
    ("said", "present", "absent"),
    [
        ({}, {"token-meter", "compaction-basic"}, {"web", "llm-pi-ai"}),
        ({"compaction": False}, set[str](), {"token-meter", "compaction-basic"}),
        (
            {"web_search": True},
            {"web", "web-search", "web-fetch", "tool-web"},
            set[str](),
        ),
    ],
)
def test_the_composition_mounts_what_the_config_asks_for(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    said: dict[str, Any],
    present: set[str],
    absent: set[str],
) -> None:
    agent = made(**said)

    _turn(agent.new(tmp_path))

    ids = set(_ids(runtime.harnesses[0].cordis))
    assert present <= ids
    assert not absent & ids


@pytest.mark.parametrize(
    ("said", "goals", "compression"),
    [
        ({}, True, "none"),
        ({"goals": False}, False, "none"),
        ({"session_compression": "zstd"}, True, None),
    ],
)
def test_the_composition_carries_goals_and_compression_as_configured(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    said: dict[str, Any],
    goals: bool,
    compression: str | None,
) -> None:
    agent = made(**said)

    _turn(agent.new(tmp_path))

    cordis = {one["id"]: one.get("config", {}) for one in runtime.harnesses[0].cordis}
    assert ("goals" in cordis["agent-core"]) == goals
    assert cordis["sessions"].get("compression") == compression
    assert cordis["llm-deepseek"]["reasoningEffort"] == "process.env.HMZ_DSH_EFFORT"


@pytest.mark.parametrize(
    ("reason", "kind", "why"),
    [
        (
            {"kind": "failed", "error": {"message": "the model fell over"}},
            Failed,
            "the model fell over",
        ),
        (
            {"kind": "failed", "error": {"code": "MISSING_CREDENTIAL"}},
            Failed,
            "API key",
        ),
        (
            {"kind": "failed", "error": {"message": "maximum context length is 64k"}},
            Unrecoverable,
            "maximum context length",
        ),
    ],
)
def test_a_turn_that_does_not_complete_fails_saying_why(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    reason: dict[str, Any],
    kind: type[Failed],
    why: str,
) -> None:
    def fails(session: str) -> list[_Notice]:
        return [
            _event(
                session,
                "assistant/chunk",
                turn=1,
                step=1,
                chunk={"type": "text-delta", "text": "partly"},
            ),
            _event(session, "turn/end", reason=reason),
        ]

    runtime.turn = fails
    agent = made()
    told = heard(agent)

    with pytest.raises(kind) as failed:
        _turn(agent.new(tmp_path))

    assert why in str(failed.value.stderr)
    assert ("failed", str(failed.value.stderr)) in [
        (one.kind, one.text) for one in told
    ]


def test_a_runtime_that_refuses_the_prompt_fails_the_turn(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    runtime.refuses = RuntimeError("an id collision in the session store")
    agent = made()

    with pytest.raises(Unrecoverable) as failed:
        _turn(agent.new(tmp_path))

    assert "id collision" in str(failed.value.stderr)


def test_without_the_sdk_a_turn_says_which_extra_to_install(
    made: Callable[..., DshAgent], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "deepseek_harness", None)
    monkeypatch.setitem(sys.modules, "deepseek_harness_runtime", None)
    agent = made()

    with pytest.raises(ModuleNotFoundError, match=r"\[dsh\] extra"):
        _turn(agent.new(tmp_path))


def test_a_key_in_the_environment_is_ready(tmp_path: Path) -> None:
    assert native_ready(tmp_path)


def test_no_key_anywhere_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    assert not native_ready(tmp_path)


def test_a_key_in_the_project_env_file_is_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-the-project\n")
    assert native_ready(tmp_path)


def test_a_key_in_the_dsh_home_env_file_is_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dsh_home: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    (dsh_home / ".env").write_text("DEEPSEEK_API_KEY=from-the-home\n")
    assert native_ready(tmp_path / "elsewhere")


def test_a_key_saved_in_private_credentials_is_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dsh_home: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    saved = dsh_home / ".credentials.yaml"
    saved.write_text("DEEPSEEK_API_KEY: saved\n")
    saved.chmod(0o600)
    assert native_ready(tmp_path)


def test_credentials_others_can_read_are_not_trusted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dsh_home: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    saved = dsh_home / ".credentials.yaml"
    saved.write_text("DEEPSEEK_API_KEY: saved\n")
    os.chmod(saved, 0o644)  # noqa: PTH101 -- the mode is the point
    assert not native_ready(tmp_path)


def test_a_key_read_from_the_variable_settings_name_is_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dsh_home: Path
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    monkeypatch.setenv("MY_DEEPSEEK", "mine")
    (dsh_home / "settings.yaml").write_text("llm-deepseek:\n  apiKeyEnv: MY_DEEPSEEK\n")
    assert native_ready(tmp_path)


@pytest.mark.parametrize(
    "settings",
    [
        "llm-deepseek: [not, a, mapping]\n",
        "llm-deepseek:\n  apiKeyEnv: 'not a name'\n",
        "llm-deepseek:\n  baseURL: 3\n",
        "a: 1\na: 2\n",
        "- a list\n",
        "{unclosed\n",
    ],
)
def test_settings_dsh_cannot_read_are_not_ready(
    tmp_path: Path, dsh_home: Path, settings: str
) -> None:
    (dsh_home / "settings.yaml").write_text(settings)
    assert not native_ready(tmp_path)


def test_the_base_url_settings_name_reaches_the_runtime(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path, dsh_home: Path
) -> None:
    (dsh_home / "settings.yaml").write_text(
        "llm-deepseek:\n  baseURL: https://api.example/v1\n"
    )
    agent = made()

    _turn(agent.new(tmp_path))

    env = runtime.harnesses[0].made["env"]
    assert env["DEEPSEEK_BASE_URL"] == "https://api.example/v1"
