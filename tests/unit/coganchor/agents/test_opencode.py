"""`hmz.coganchor.agents.opencode`: one `opencode run` per turn, read back from its JSON."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import (
    Failed,
    OpencodeAgent,
    OpencodeAgentConfig,
    OpencodeSession,
    driver,
)
from hmz.coganchor.agents.config import Unserved
from hmz.coganchor.fence import Fence

from .doubles_u5 import configured, heard, line, option, spawning

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.agents.event import Event


@pytest.fixture(autouse=True)
def _home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A home of the test's own, so that no configuration of whoever runs it is read."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)


def _agent(**said: Any) -> OpencodeAgent:
    return OpencodeAgent(OpencodeAgentConfig(**configured("anthropic/sonnet", said)))


def _turn(session: OpencodeSession, prompt: str = "do it") -> list[Event]:
    return list(session.stream(prompt))


def _says(kind: str, **said: Any) -> str:
    return line({"type": kind, "sessionID": "ses_1", **said})


#: A turn as `opencode run --format json` writes one: a thought, a tool, the answer, the cost.
_TURN = [
    _says("reasoning", part={"id": "r1", "text": "thinking it over"}),
    _says(
        "tool_use",
        part={"id": "t1", "tool": "bash", "state": {"input": {"command": "ls -la"}}},
    ),
    _says("text", part={"id": "p1", "text": "all done"}),
    _says(
        "step_finish",
        part={
            "tokens": {
                "input": 10,
                "output": 5,
                "reasoning": 2,
                "cache": {"read": 3, "write": 1},
            }
        },
    ),
    "a plain line among the JSON\n",
]


def test_opencode_is_driven_by_its_own_classes() -> None:
    assert driver("opencode") == (OpencodeAgent, OpencodeAgentConfig)
    agent = _agent()
    assert agent.backend == "opencode"
    assert isinstance(agent.new(), OpencodeSession)
    assert OpencodeSession.protocol


def test_it_counts_every_kind_of_token_a_step_reports() -> None:
    assert OpencodeAgent.counts == {
        "input",
        "output",
        "reasoning",
        "cache_read",
        "cache_write",
    }


@pytest.mark.parametrize("named", ["two words", "tab\there", " "])
def test_a_cli_agent_name_with_a_space_is_refused(named: str) -> None:
    with pytest.raises(ValueError, match="cli_agent"):
        OpencodeAgentConfig(model="m", effort="", cli_agent=named)


@pytest.mark.parametrize(
    ("said", "named"),
    [
        ({"permission": "read-only"}, "permission="),
        ({"permission": "workspace-write"}, "permission="),
        ({"web_search": False}, "web_search=False"),
        ({"fence": Fence(online=False)}, "cuts the network"),
    ],
)
def test_turning_the_table_off_refuses_what_only_the_table_carries(
    said: dict[str, Any], named: str
) -> None:
    with pytest.raises(Unserved, match=named):
        OpencodeAgentConfig(model="m", effort="", permission_table=False, **said)


@pytest.mark.parametrize(
    "said",
    [{}, {"permission": "auto"}, {"permission": "bypass"}, {"web_search": True}],
)
def test_turning_the_table_off_is_fine_where_it_withholds_nothing(
    said: dict[str, Any],
) -> None:
    config = OpencodeAgentConfig(model="m", effort="", permission_table=False, **said)
    assert config.permission_table is False


def test_a_turn_is_one_run_reading_the_prompt_on_stdin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, opening=_TURN)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    events = _turn(session, "-- a prompt that starts with dashes")

    (process,) = spawned
    assert process.args == [
        "opencode",
        "run",
        "--format",
        "json",
        "--dir",
        str(tmp_path),
        "--model",
        "anthropic/sonnet",
    ]
    assert process.told == ["-- a prompt that starts with dashes"]
    assert [(one.kind, one.text) for one in events] == [
        ("reasoning", "thinking it over"),
        ("tool", "bash ls -la"),
        ("text", "all done"),
        ("result", "all done"),
    ]


def test_a_turn_reports_what_every_step_cost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch, opening=[*_TURN, *_TURN[-2:]])
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    result = _turn(session)[-1]

    assert result.tokens == {"anthropic/sonnet": 42}
    assert dict(result.spent) == {
        "input": 20,
        "output": 10,
        "reasoning": 4,
        "cache_read": 6,
        "cache_write": 2,
    }
    assert session.spent()["input"] == 20


def test_a_part_written_twice_is_said_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch, opening=[*_TURN, *_TURN])
    agent = _agent()
    heard(agent)

    kinds = [one.kind for one in _turn(agent.new(tmp_path))]

    assert kinds == ["reasoning", "tool", "text", "result"]


def test_the_next_turn_resumes_the_session_the_first_one_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = spawning(monkeypatch, opening=_TURN)
    agent = _agent()
    heard(agent)
    session = agent.new(tmp_path)

    _turn(session)
    _turn(session)

    assert session.id == "ses_1"
    assert "--session" not in spawned[0].args
    assert option(spawned[1].args, "--session") == "ses_1"


@pytest.mark.parametrize(
    ("said", "flags"),
    [
        ({"effort": "high"}, ["--variant", "high"]),
        ({"cli_agent": "plan"}, ["--agent", "plan"]),
        ({"thinking": True}, ["--thinking"]),
        ({"pure": True}, ["--pure"]),
        ({"permission": "auto"}, ["--auto"]),
        ({"unattended": True}, ["--auto"]),
    ],
)
def test_what_the_agent_is_configured_with_goes_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    flags: list[str],
) -> None:
    spawned = spawning(monkeypatch, opening=_TURN)
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    argv = spawned[0].args
    at = argv.index(flags[0])
    assert argv[at : at + len(flags)] == flags


@pytest.mark.parametrize("said", [{}, {"permission": "auto", "unattended": False}])
def test_a_bare_turn_carries_no_auto_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, said: dict[str, Any]
) -> None:
    spawned = spawning(monkeypatch, opening=_TURN)
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert "--auto" not in spawned[0].args


def _permitted(spawned_env: dict[str, str] | None) -> dict[str, Any] | None:
    said = (spawned_env or {}).get("OPENCODE_PERMISSION")
    return None if said is None else json.loads(said)


@pytest.mark.parametrize(
    ("said", "table"),
    [
        ({}, None),
        ({"permission_table": True}, None),
        (
            {"permission": "read-only"},
            {"edit": "deny", "bash": "deny", "webfetch": "allow", "websearch": "allow"},
        ),
        (
            {"permission": "workspace-write"},
            {"edit": "allow", "bash": "allow", "webfetch": "deny", "websearch": "deny"},
        ),
        (
            {"permission": "auto", "web_search": False},
            {"edit": "allow", "bash": "allow", "webfetch": "deny", "websearch": "deny"},
        ),
        ({"web_search": True}, {"webfetch": "allow", "websearch": "allow"}),
        ({"web_search": False}, {"webfetch": "deny", "websearch": "deny"}),
        ({"permission": "auto", "permission_table": False}, None),
    ],
)
def test_what_the_agent_may_do_is_a_table_in_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    said: dict[str, Any],
    table: dict[str, str] | None,
) -> None:
    monkeypatch.delenv("OPENCODE_PERMISSION", raising=False)
    spawned = spawning(monkeypatch, opening=_TURN)
    agent = _agent(**said)
    heard(agent)

    _turn(agent.new(tmp_path))

    assert _permitted(spawned[0].env) == table


def test_an_error_event_fails_the_turn_whatever_it_exited_with(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(
        monkeypatch,
        opening=[
            _says("text", part={"id": "p1", "text": "partial"}),
            _says("error", error={"name": "Oops", "data": {"message": "bad thing"}}),
        ],
    )
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert "bad thing" in str(failed.value.stderr)
    assert failed.value.output == "partial"


def test_a_turn_that_says_nothing_at_all_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch)
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert "said nothing at all" in str(failed.value.stderr)


def test_a_run_that_exits_nonzero_fails_with_what_it_said(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawning(monkeypatch, opening=_TURN[:1], status=3, stderr="crashed hard\n")
    agent = _agent()
    heard(agent)

    with pytest.raises(Failed) as failed:
        _turn(agent.new(tmp_path))

    assert failed.value.returncode == 3
    assert "crashed hard" in str(failed.value.stderr)


def test_a_fence_lets_through_the_host_its_provider_is_configured_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = tmp_path / "config" / "opencode"
    configured.mkdir(parents=True)
    (configured / "opencode.json").write_text(
        json.dumps(
            {
                "provider": {
                    "local": {"options": {"baseURL": "http://gw.example:8080/v1"}}
                }
            }
        )
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    agent = _agent(model="local/m1", fence=Fence(online=False))
    fence = agent.fenced()

    assert fence is not None
    assert "gw.example:8080" in fence.hosts


@pytest.mark.parametrize(
    "written", [None, "not json", json.dumps({"provider": {"other": {}}})]
)
def test_a_fence_is_left_alone_where_no_provider_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, written: str | None
) -> None:
    configured = tmp_path / "opencode"
    configured.mkdir()
    if written is not None:
        (configured / "opencode.json").write_text(written)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    fence = _agent(model="local/m1", fence=Fence(online=False)).fenced()
    plain = _agent(model="other/m1", fence=Fence(online=False)).fenced()

    assert fence is not None
    assert plain is not None
    assert fence.hosts == plain.hosts


def test_an_agent_without_a_fence_has_none() -> None:
    assert _agent().fenced() is None
