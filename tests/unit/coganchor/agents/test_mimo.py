"""mimocode: opencode's driver under the name `mimo`, and the places the two part company.

What is checked is what differs -- the command, the variable its permissions go in and the
third web tool among them, the flag that says nobody is there, a gateway account's model, and
Claude Code's settings left alone under a fence -- each through a turn of a scripted process.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence, providers
from hmz.coganchor.agents import (
    Failed,
    MimoCodeAgent,
    MimoCodeAgentConfig,
    MimoCodeSession,
    OpencodeAgent,
)
from hmz.coganchor.fence import Fence
from tests.unit.coganchor.agents.doubles_u4 import Spawner, fenceable

if TYPE_CHECKING:
    from pathlib import Path

_MODEL = "xiaomi/mimo-v2"


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": _MODEL, "effort": ""}


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Spawner:
    """Every process a turn asks for, scripted rather than started, under a home of its own."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for inherited in (
        "MIMOCODE_PERMISSION",
        "OPENCODE_PERMISSION",
        "MIMO_GATEWAY_MODEL",
        "MIMO_GATEWAY_URL",
        "MIMOCODE_DISABLE_CLAUDE_CODE",
    ):
        monkeypatch.delenv(inherited, raising=False)
    held = Spawner(monkeypatch)
    held.answering(_turn())
    return held


def _mimo(**given: Any) -> MimoCodeAgent:
    return MimoCodeAgent(MimoCodeAgentConfig(**_DEFAULTS | given))


def _turn(session_id: str = "ses-1", **tokens: Any) -> list[dict[str, Any]]:
    """What one plain `mimo run --format json` prints."""
    return [
        {"type": "step_start", "sessionID": session_id, "part": {}},
        {
            "type": "tool_use",
            "sessionID": session_id,
            "part": {"id": "p1", "tool": "read", "state": {"input": {"path": "a.py"}}},
        },
        {
            "type": "text",
            "sessionID": session_id,
            "part": {"id": "p2", "text": "the answer"},
        },
        {"type": "step_finish", "sessionID": session_id, "part": {"tokens": tokens}},
    ]


def _gateway(provider: object) -> dict[str, str]:
    """`hmz.coganchor.providers.environ` for an account made by a gateway way."""
    del provider
    return {"MIMO_GATEWAY_URL": "http://gw"}


def _permitted(env: dict[str, str]) -> dict[str, Any]:
    return json.loads(env["MIMOCODE_PERMISSION"])


def test_it_is_opencode_answering_to_its_own_name(tmp_path: Path) -> None:
    agent = _mimo()
    assert isinstance(agent, OpencodeAgent)
    session = agent.new(tmp_path)
    assert isinstance(session, MimoCodeSession)
    assert session.cwd == str(tmp_path)


def test_a_turn_is_mimo_run_with_the_prompt_on_stdin(
    spawner: Spawner, tmp_path: Path
) -> None:
    session = _mimo(effort="high").new(tmp_path)
    assert session("go") == "the answer"
    proc = spawner.last
    assert proc.args[:2] == ["mimo", "run"]
    assert proc.args[proc.args.index("--dir") + 1] == str(tmp_path)
    assert proc.args[proc.args.index("--model") + 1] == _MODEL
    assert proc.args[proc.args.index("--variant") + 1] == "high"
    assert proc.stdin is not None
    assert proc.stdin.lines == ["go"]


def test_the_next_turn_resumes_the_session_it_was_given(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn(session_id="ses-9"))
    session = _mimo().new(tmp_path)
    session("one")
    session("two")
    assert "--session" not in spawner.started[0].args
    assert spawner.last.args[-2:] == ["--session", "ses-9"]
    assert session.id == "ses-9"


def test_a_rung_is_its_own_table_and_its_own_flag(
    spawner: Spawner, tmp_path: Path
) -> None:
    _mimo(permission="bypass").new(tmp_path)("go")
    proc = spawner.last
    assert proc.args[-1] == "--dangerously-skip-permissions"
    assert "--auto" not in proc.args
    assert _permitted(proc.environ) == {
        "edit": "allow",
        "bash": "allow",
        "webfetch": "allow",
        "websearch": "allow",
        "codesearch": "allow",
    }
    assert "OPENCODE_PERMISSION" not in (proc.env or {})


def test_no_web_takes_its_code_search_too(spawner: Spawner, tmp_path: Path) -> None:
    _mimo(web_search=False).new(tmp_path)("go")
    proc = spawner.last
    assert _permitted(proc.environ) == dict.fromkeys(
        ("webfetch", "websearch", "codesearch"), "deny"
    )
    assert "--dangerously-skip-permissions" not in proc.args


def test_an_agent_nobody_set_a_rung_for_is_told_nothing(
    spawner: Spawner, tmp_path: Path
) -> None:
    _mimo().new(tmp_path)("go")
    proc = spawner.last
    assert "MIMOCODE_PERMISSION" not in proc.environ
    assert "--dangerously-skip-permissions" not in proc.args


@pytest.mark.parametrize(
    ("model", "served"),
    [
        ("mimo-v2-pro", "mimo-v2-pro"),
        ("humanize/mimo-v2-pro", "mimo-v2-pro"),
        ("anthropic/claude-x", "anthropic/claude-x"),
    ],
)
def test_a_gateway_account_asks_for_its_model_under_the_gateway(
    spawner: Spawner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    served: str,
) -> None:
    monkeypatch.setattr(providers, "environ", _gateway)
    _mimo(model=model).new(tmp_path)("go")
    proc = spawner.last
    assert proc.args[proc.args.index("--model") + 1] == f"humanize/{served}"
    assert proc.environ["MIMO_GATEWAY_MODEL"] == served
    assert proc.environ["MIMO_GATEWAY_URL"] == "http://gw"


def test_any_other_account_names_its_model_as_it_is(
    spawner: Spawner, tmp_path: Path
) -> None:
    _mimo(model="humanize/x").new(tmp_path)("go")
    proc = spawner.last
    assert proc.args[proc.args.index("--model") + 1] == "humanize/x"
    assert "MIMO_GATEWAY_MODEL" not in proc.environ


@pytest.mark.parametrize(("reads_home", "told"), [(False, "1"), (True, None)])
def test_a_fence_that_keeps_the_home_leaves_claude_codes_settings_alone(
    spawner: Spawner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reads_home: bool,
    told: str | None,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    work = tmp_path / "work"
    work.mkdir()
    read = ("/",) if reads_home else (str(work),)
    _mimo(fence=Fence(read=read, write=(str(work),))).new(work)("go")
    assert spawner.last.environ.get("MIMOCODE_DISABLE_CLAUDE_CODE") == told


def test_a_turn_reads_its_events_and_cost(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(
        _turn(input=10, output=3, reasoning=2, cache={"read": 4, "write": 1})
    )
    events = list(_mimo().new(tmp_path).stream("go"))
    assert [(one.kind, one.text) for one in events[:-1]] == [
        ("tool", "read a.py"),
        ("text", "the answer"),
    ]
    assert events[-1].tokens == {_MODEL: 20}
    assert dict(events[-1].spent) == {
        "input": 10,
        "output": 3,
        "reasoning": 2,
        "cache_read": 4,
        "cache_write": 1,
    }


def test_an_error_line_fails_the_turn(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(
        [{"type": "error", "sessionID": "s", "error": {"name": "the model refused"}}]
    )
    with pytest.raises(Failed, match="the model refused"):
        _mimo().new(tmp_path)("go")
