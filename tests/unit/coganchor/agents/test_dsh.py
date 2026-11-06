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
from hmz.coganchor.agents.dsh_skills import configuration
from hmz.coganchor.agents.event import Unrecoverable
from hmz.coganchor.agents.skills import Loaded
from hmz.coganchor.providers import Provider

from .doubles_core import Run
from .doubles_u5 import configured, gatewayed, heard

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
        self.launch: tuple[str, ...] = made["_launch_args"]
        written = Path(_option(self.launch, "--patch")).read_text(encoding="utf-8")
        self.patch: list[dict[str, Any]] = (
            yaml.safe_load(written.replace("!!js ", "")) or []
        )
        self.client = _Client(runtime)
        self.started = self.closed = False
        runtime.harnesses.append(self)

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True


def _option(argv: tuple[str, ...], flag: str) -> str:
    return argv[argv.index(flag) + 1]


@dataclass
class _Runtime:
    """What the fake SDK was asked to do, and what it answers a turn with."""

    turn: Callable[[str], list[_Notice]] = _completed
    refuses: Exception | None = None
    harnesses: list[_Harness] = field(default_factory=list[_Harness])
    prompts: list[tuple[str, list[dict[str, Any]]]] = field(
        default_factory=list[tuple[str, list[dict[str, Any]]]]
    )


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch) -> _Runtime:
    """The SDK and its bundled runtime, as modules that start nothing."""
    held = _Runtime()

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


def _disabled(patch: list[dict[str, Any]]) -> set[str]:
    """The rows of the SDK's profile a patch switches off."""
    return {str(one["id"]) for one in patch if one.get("disabled") is True}


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
    assert started["reasoning_effort"] == "high"
    assert started["cwd"] == str(tmp_path)
    # The bundled runtime under the SDK's own profile, with Humanize's patch over it.
    assert harness.launch[-5:-1] == ("/dsh/runtime.js", "--profile", "sdk", "--patch")
    node = harness.launch[-6]
    # `node` by name, or by the path a machine that keeps it off `PATH` has it at.
    assert Path(node).name == "node"
    env = started["env"]
    assert env["DEEPSEEK_API_KEY"] == "test-key"
    assert env["DSH_PERMISSION_MODE"] == "danger-full-access"
    assert Path(env["DSH_HOME"]).is_absolute()


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


def test_a_new_effort_is_refused_once_the_conversation_has_taken_a_turn(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    """A new runtime cannot resume the conversation, so the turn is refused up front."""
    agent = made(effort="low")
    session = agent.new(tmp_path)

    _turn(session)
    session.effort = "high"
    with pytest.raises(Unrecoverable, match="cannot carry") as refused:
        _turn(session)

    (kept,) = runtime.harnesses
    assert not kept.closed
    assert len(runtime.prompts) == 1
    assert session.id in str(refused.value.stderr)
    # Put back as it was, the session carries on in the runtime it took its turn in.
    session.effort = "low"
    _turn(session)
    assert len(runtime.harnesses) == 1


def test_a_closed_runtime_is_not_restarted_under_a_conversation(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    session = made().new(tmp_path)

    _turn(session)
    session.cut(why="stop")
    with pytest.raises(Unrecoverable, match="cannot carry"):
        _turn(session)

    assert len(runtime.harnesses) == 1


def test_a_new_effort_before_the_first_turn_starts_a_runtime_at_it(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    session = made(effort="low").new(tmp_path)

    session.effort = "high"
    _turn(session)

    (harness,) = runtime.harnesses
    assert harness.made["reasoning_effort"] == "high"


def test_an_agent_at_no_effort_leaves_the_adapter_at_its_own_default(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    _turn(made().new(tmp_path))

    assert runtime.harnesses[0].made["reasoning_effort"] is None


def test_closing_the_session_closes_its_runtime(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    agent = made()
    session = agent.new(tmp_path)

    _turn(session)
    session.close()

    assert runtime.harnesses[0].closed


@pytest.mark.parametrize(
    ("said", "off"),
    [
        ({}, set[str]()),
        ({"compaction": False}, {"compaction-basic", "command-compact"}),
        (
            {"goals": False},
            {"goal", "goal-round-driver", "command-goal", "tool-goal"},
        ),
        (
            {"web_search": False},
            {"web", "web-search-deepseek", "web-fetch-http", "tool-web"},
        ),
        ({"web_search": True}, set[str]()),
    ],
)
def test_the_patch_switches_off_what_the_config_turns_down(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    said: dict[str, Any],
    off: set[str],
) -> None:
    agent = made(**said)

    _turn(agent.new(tmp_path))

    assert _disabled(runtime.harnesses[0].patch) == off


@pytest.mark.parametrize(
    ("compression", "patch"),
    [
        (
            "none",
            [
                {
                    "id": "session-persistence-jsonl",
                    "config": {
                        "root": "dshHomePath('sessions')",
                        "compression": "none",
                    },
                }
            ],
        ),
        ("zstd", []),
    ],
)
def test_only_a_compression_other_than_the_sdks_own_is_patched_in(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    compression: str,
    patch: list[dict[str, Any]],
) -> None:
    """An agent at every one of the SDK's own settings is told nothing over its profile."""
    agent = made(session_compression=compression)

    _turn(agent.new(tmp_path))

    assert runtime.harnesses[0].patch == patch


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


@pytest.mark.parametrize("goal", [False, True])
@pytest.mark.parametrize("taken", [False, True])
def test_a_session_is_the_runs_once_its_runtime_has_taken_the_prompt_and_not_before(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    goal: bool,
    taken: bool,
) -> None:
    if taken:
        runtime.turn = lambda session: [
            _event(session, "turn/end", reason={"kind": "failed"})
        ]
    else:
        runtime.refuses = RuntimeError("the runtime would not take it")
    agent = made()
    agent.epic = run = Run(tmp_path)
    session = agent.new(tmp_path)
    asked = (
        (lambda: session.pursue("the objective"))
        if goal
        else (lambda: session("the prompt"))
    )

    for _ in range(2):
        with pytest.raises(Failed):
            asked()

    # Each session a runtime took a prompt into is the run's, though no turn landed in it, and
    # none that a runtime never took is: there is no such session to be anybody's.
    assert run.said == [(one, "") for one, _ in runtime.prompts]
    assert len(run.said) == (2 if taken else 0)
    assert agent.opened == []


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


def test_a_turn_through_a_gateway_runs_on_the_route_it_is_pointed_at_it_by(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gatewayed(
        monkeypatch,
        Provider(
            cli="dsh",
            name="gw",
            way="litellm-openai-key",
            env={"OPENAI_API_KEY": "upstream-secret"},
        ),
    )

    _turn(made(provider="gw", effort="high").new(tmp_path))

    (harness,) = runtime.harnesses
    assert harness.made["provider"] == "gateway"
    assert harness.made["reasoning_effort"] is None
    env = harness.made["env"]
    assert env["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:4321"
    assert env["DEEPSEEK_API_KEY"] == "sk-master"
    assert env["DSH_GATEWAY_API"] == "openai-completions"
    assert "upstream-secret" not in env.values()
    (route,) = [one for one in harness.patch if one["id"] == "llm-pi-ai"]
    assert route["config"]["providers"]["gateway"]["models"] == [{"id": "deepseek-v4"}]
    assert "settings" in _disabled(harness.patch)


def test_a_gateway_started_again_is_a_new_runtime_a_conversation_cannot_carry_on_in(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = gatewayed(
        monkeypatch, Provider(cli="dsh", name="gw", way="litellm-openai-key")
    )
    agent = made(provider="gw")
    session = agent.new(tmp_path)

    _turn(session)
    started[0].running = False
    with pytest.raises(Unrecoverable, match="cannot carry"):
        _turn(session)
    _turn(agent.new(tmp_path))

    assert len(started) == 2
    assert len(runtime.harnesses) == 2
    assert len(runtime.prompts) == 2


def _skill(at: Path, name: str, *resources: str) -> Loaded:
    """One skill of a flow's, with whatever else its directory holds."""
    (at / name).mkdir(parents=True)
    (at / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: The {name} skill.\n---\nDo {name}.\n",
        encoding="utf-8",
    )
    for one in resources:
        (at / name / one).write_text(one, encoding="utf-8")
    return Loaded(name, at / name, "flow")


def _inserted(harness: _Harness, row: str) -> dict[str, Any] | None:
    """One row the patch inserts, by its id, where it inserts it."""
    rows = [
        one
        for held in harness.patch
        for one in held.get("insert", [])
        if one["id"] == row
    ]
    return rows[0] if rows else None


def _provided(harness: _Harness) -> dict[str, Any] | None:
    """The config of humanize's own skill provider, where the patch mounts one."""
    row = _inserted(harness, "humanize-skills")
    if row is None:
        return None
    assert Path(row["name"]).name == "humanize-skills.mjs"
    return row["config"]["provider"]


def _stock(harness: _Harness) -> list[dict[str, Any]]:
    """What the patch says to the stock skill provider's row."""
    return [one for one in harness.patch if one.get("id") == "skill-filesystem"]


def _lodged(harness: _Harness) -> dict[str, list[str]]:
    """Each flow skill put down for a runtime, by what its directory holds."""
    config = _provided(harness)
    assert config is not None
    root = Path(config["customSkillDirs"][0])
    return {
        one.name: sorted(entry.name for entry in one.iterdir())
        for one in sorted(root.iterdir())
    }


def test_flow_skills_are_a_provider_of_their_own_beside_the_stock_one(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    """The stock row is left as the profile has it, and the flow's go in a root apiece."""
    flow = tmp_path / "flow" / "skills"
    workspace = tmp_path / "work"
    workspace.mkdir()
    agent = made()
    agent.loads([_skill(flow, "review", "notes.txt"), _skill(flow, "write")])

    _turn(agent.new(workspace))

    (harness,) = runtime.harnesses
    # The runtime's home is the user's, which the stock row reads as it always does.
    assert _stock(harness) == []
    beside = Path(_option(harness.launch, "--patch")).parent
    assert _provided(harness) == {
        "providerName": f"humanize-{beside.name}",
        "includeDefaultRoots": False,
        "customSkillDirs": [str(beside / "skills")],
        "watch": False,
    }
    # And what tells the catalog it changed, read before every step.
    told = _inserted(harness, "humanize-skills")
    assert told is not None
    assert Path(told["name"]).parent == beside
    assert "agent/pre-step" in Path(told["name"]).read_text(encoding="utf-8")
    assert Path(told["config"]["generation"]).read_text(encoding="utf-8")
    assert _lodged(harness) == {
        "review": ["SKILL.md", "notes.txt"],
        "write": ["SKILL.md"],
    }
    assert list(workspace.iterdir()) == []


def test_an_agent_given_no_flow_skills_is_patched_with_no_provider(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    _turn(made().new(tmp_path))

    assert _provided(runtime.harnesses[0]) is None


def test_a_runtime_given_the_epics_home_still_reads_the_users_own_skills(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path, dsh_home: Path
) -> None:
    """The stock row told the user's home and nothing else; the flow's in a row of its own."""
    agent = made()
    agent.keeps = tmp_path / "epic" / "sessions"
    agent.loads([_skill(tmp_path / "flow", "review")])

    _turn(agent.new(tmp_path))

    (harness,) = runtime.harnesses
    assert harness.made["env"]["DSH_HOME"] == str(tmp_path / "epic/sessions/dsh")
    assert _stock(harness) == [
        {"id": "skill-filesystem", "config": {"dshHome": str(dsh_home)}}
    ]
    config = _provided(harness)
    assert config is not None
    assert len(config["customSkillDirs"]) == 1


def test_an_agent_with_no_flow_skills_kept_in_an_epic_reads_the_users_alone(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path, dsh_home: Path
) -> None:
    agent = made()
    agent.keeps = tmp_path / "epic" / "sessions"

    _turn(agent.new(tmp_path))

    (harness,) = runtime.harnesses
    assert _stock(harness) == [
        {"id": "skill-filesystem", "config": {"dshHome": str(dsh_home)}}
    ]
    assert _provided(harness) is None


@pytest.mark.parametrize("name", ["../escape", "/abs", "a/b", "..", ""])
def test_a_flow_skill_named_as_anything_but_a_directory_is_refused_touching_nothing(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path, name: str
) -> None:
    outside = tmp_path / "escape"
    outside.mkdir()
    (outside / "kept").write_text("kept", encoding="utf-8")
    at = _skill(tmp_path / "flow", "real").at
    agent = made()
    agent.loads([Loaded(name, at, "flow")])

    with pytest.raises(ValueError, match="unsupported skill name"):
        _turn(agent.new(tmp_path / "flow"))

    assert runtime.harnesses == []
    assert [one.name for one in outside.iterdir()] == ["kept"]
    assert sorted(one.name for one in (tmp_path / "flow").iterdir()) == ["real"]


def test_two_sessions_carry_their_own_subsets_and_take_them_away_when_closed(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    flow = tmp_path / "flow"
    agent = made()
    agent.loads([_skill(flow, "review"), _skill(flow, "write")])
    reading, writing = agent.new(tmp_path), agent.new(tmp_path)
    reading.loads(["review", "nothing-the-flow-brings"])
    writing.loads(["write"])

    _turn(reading)
    _turn(writing)

    first, second = runtime.harnesses
    assert _lodged(first) == {"review": ["SKILL.md"]}
    assert _lodged(second) == {"write": ["SKILL.md"]}
    held = Path(_option(first.launch, "--patch")).parent
    reading.close()
    assert not held.exists()
    assert _lodged(second) == {"write": ["SKILL.md"]}
    assert (flow / "review" / "SKILL.md").is_file()


def test_skills_changed_between_turns_reach_the_same_runtime(
    made: Callable[..., DshAgent], runtime: _Runtime, tmp_path: Path
) -> None:
    """The conversation goes on in the runtime it started in, carrying what it now carries."""
    flow = tmp_path / "flow"
    agent = made()
    agent.loads([_skill(flow, "review"), _skill(flow, "write")])
    session = agent.new(tmp_path)
    session.loads(["review"])

    _turn(session)
    (harness,) = runtime.harnesses
    told = _inserted(harness, "humanize-skills")
    assert told is not None
    generation = Path(told["config"]["generation"])
    said = [generation.read_text(encoding="utf-8")]
    assert _lodged(harness) == {"review": ["SKILL.md"]}
    session.loads(["write"])
    _turn(session)
    said.append(generation.read_text(encoding="utf-8"))
    assert _lodged(harness) == {"write": ["SKILL.md"]}
    _turn(session)
    said.append(generation.read_text(encoding="utf-8"))
    session.loads(None)
    _turn(session)
    said.append(generation.read_text(encoding="utf-8"))
    # Said anew where the skills changed, and only there.
    assert said[0] != said[1] == said[2] != said[3]

    assert len(runtime.harnesses) == 1
    assert not harness.closed
    assert len({asked for asked, _ in runtime.prompts}) == 1
    assert _lodged(harness) == {"review": ["SKILL.md"], "write": ["SKILL.md"]}


def _user_patch(home: Path, text: str, *, profile: bool = False) -> Path:
    at = home / "profiles" / "sdk" if profile else home
    at.mkdir(parents=True, exist_ok=True)
    path = at / "cordis.patch.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_skill_configuration_applies_profile_then_home_by_native_replacement(
    dsh_home: Path,
) -> None:
    assert configuration(dsh_home) == {}
    _user_patch(
        dsh_home,
        "- id: skill-filesystem\n  config:\n    watch: false\n    dshHome: old-home\n",
        profile=True,
    )
    _user_patch(
        dsh_home,
        "- id: skill-filesystem\n  config:\n    includeDefaultRoots: false\n"
        "    customSkillDirs: [relative, yes]\n"
        "- id: skill-filesystem\n  name: other-package\n  disabled: true\n",
    )
    assert configuration(dsh_home) == {
        "includeDefaultRoots": False,
        "customSkillDirs": ["relative", "yes"],
    }


def test_a_user_can_disable_the_stock_skill_provider(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    dsh_home: Path,
    tmp_path: Path,
) -> None:
    _user_patch(dsh_home, "- id: skill-filesystem\n  disabled: true\n")
    assert configuration(dsh_home) is None
    agent = made()
    agent.keeps = tmp_path / "epic"
    agent.loads([_skill(tmp_path / "flow", "review")])
    _turn(agent.new(tmp_path))
    assert _stock(runtime.harnesses[0]) == [
        {"id": "skill-filesystem", "disabled": True}
    ]
    assert _lodged(runtime.harnesses[0]) == {"review": ["SKILL.md"]}


def test_a_later_layer_can_enable_the_stock_skill_provider(dsh_home: Path) -> None:
    _user_patch(dsh_home, "- id: skill-filesystem\n  disabled: true\n", profile=True)
    _user_patch(dsh_home, "- id: skill-filesystem\n  disabled: false\n")
    assert configuration(dsh_home) == {}


def test_only_skill_configuration_is_carried_to_an_epic(
    made: Callable[..., DshAgent], runtime: _Runtime, dsh_home: Path, tmp_path: Path
) -> None:
    _user_patch(
        dsh_home,
        "- id: unrelated\n  config: !!js dangerous()\n"
        "- id: another\n  config: {separator: =}\n"
        "- id: skill-filesystem\n  config:\n    dshHome: configured-dsh\n"
        "    agentsHome: configured-agents\n    watch: false\n"
        "    customSkillDirs: [custom]\n    includeDefaultRoots: false\n",
    )
    agent = made()
    agent.keeps = tmp_path / "epic"
    _turn(agent.new(tmp_path))
    assert _stock(runtime.harnesses[0]) == [
        {"id": "skill-filesystem", "config": configuration(dsh_home)}
    ]
    assert all(row.get("id") != "unrelated" for row in runtime.harnesses[0].patch)


@pytest.mark.parametrize(
    "setting",
    [
        "disabled: !!js process.env.DISABLE_SKILLS",
        "config: !!js chooseSkills()",
        "config: {customSkillDirs: [!!js 'process.env.SKILLS']}",
        "config: {includeDefaultRoots: no}",
        "config: {customSkillDirs: {__jsExpr: chooseSkills()}}",
        "intercept: {skills: custom}",
        "group: true\n  config: []",
        "remove: true",
    ],
)
def test_unsupported_skill_configuration_is_refused_without_enabling_defaults(
    made: Callable[..., DshAgent],
    runtime: _Runtime,
    dsh_home: Path,
    tmp_path: Path,
    setting: str,
) -> None:
    _user_patch(dsh_home, f"- id: skill-filesystem\n  {setting}\n")
    agent = made()
    agent.keeps = tmp_path / "epic"
    with pytest.raises(ValueError, match="dsh skill provider"):
        _turn(agent.new(tmp_path))
    assert runtime.harnesses == []
