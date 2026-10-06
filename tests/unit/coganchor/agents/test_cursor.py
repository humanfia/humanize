"""Cursor Agent: the id a turn asks for, the command it runs, and the NDJSON read back.

Every turn is one `cursor-agent --print`, so a turn here is one scripted process: what the
driver asked to run is read off it, and what it printed is read back as the turn's events.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import fence, models
from hmz.coganchor.agents import (
    CursorAgent,
    CursorAgentConfig,
    CursorSession,
    Failed,
    Unfenced,
    Unserved,
)
from hmz.coganchor.agents.cursor import spelled
from hmz.coganchor.backends import Model
from hmz.coganchor.fence import Fence
from tests.unit.coganchor.agents.doubles_u4 import Spawner, fenceable, offering

if TYPE_CHECKING:
    from pathlib import Path

#: What `cursor-agent --list-models` last said this account runs.
_ACCOUNT = (
    "composer-2.5",
    "composer-2.5-fast",
    "gpt-5.2",
    "gpt-5.2-low",
    "gpt-5.2-high",
    "gpt-5.2-xhigh",
    "auto",
)


#: What every agent here is made with unless a test says otherwise.
_DEFAULTS: dict[str, Any] = {"model": "gpt-5.2", "effort": ""}


@pytest.fixture
def spawner(monkeypatch: pytest.MonkeyPatch) -> Spawner:
    """Every process a turn asks for, scripted rather than started."""
    return Spawner(monkeypatch)


@pytest.fixture(autouse=True)
def _catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """The account's catalogue, as humanize last kept it."""
    monkeypatch.setattr(
        models, "offered", offering(*(Model(name=one, efforts=()) for one in _ACCOUNT))
    )


def _cursor(**given: Any) -> CursorAgent:
    return CursorAgent(CursorAgentConfig(**_DEFAULTS | given))


def _turn(
    session_id: str = "chat-1", result: str = "done", **usage: int
) -> list[dict[str, Any]]:
    """What one plain turn prints: the chat named, a word, a read, and the result."""
    return [
        {"type": "system", "subtype": "init", "session_id": session_id},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
        {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "c1",
            "tool_call": {"readToolCall": {"args": {"path": "src/x.py"}}},
        },
        {"type": "result", "subtype": "success", "result": result, "usage": usage},
    ]


@pytest.mark.parametrize(
    ("model", "effort", "fast", "listed", "expected"),
    [
        ("gpt-5.2", "low", False, _ACCOUNT, "gpt-5.2-low"),
        ("gpt-5.2-low", "high", False, _ACCOUNT, "gpt-5.2-low"),
        ("claude-x[context=1m]", "high", True, _ACCOUNT, "claude-x[context=1m]"),
        ("composer-2.5", "", True, _ACCOUNT, "composer-2.5-fast"),
        ("composer-2.5-fast", "", True, _ACCOUNT, "composer-2.5-fast"),
        ("composer-2.5", "", False, _ACCOUNT, "composer-2.5"),
        ("vendor/model-id", "", False, (), "vendor/model-id"),
        ("gpt-5.2", "medium", False, (), "gpt-5.2-medium"),
        ("gpt-5.9", "medium", False, _ACCOUNT, "gpt-5.9-medium"),
    ],
)
def test_spelled_writes_the_rung_and_the_tier_into_the_id(
    model: str, effort: str, fast: bool, listed: tuple[str, ...], expected: str
) -> None:
    assert spelled(model, effort, fast=fast, listed=listed) == expected


@pytest.mark.parametrize(
    ("model", "effort", "fast", "match"),
    [
        (
            "gpt-5.2",
            "medium",
            False,
            r"lists no gpt-5.2-medium.*gpt-5.2-low, gpt-5.2-high",
        ),
        ("gpt-5.2", "", True, r"lists no gpt-5.2-fast"),
        ("auto", "low", False, r"itself alone"),
    ],
)
def test_spelled_refuses_an_id_the_account_does_not_list(
    model: str, effort: str, fast: bool, match: str
) -> None:
    with pytest.raises(Unserved, match=match):
        spelled(model, effort, fast=fast, listed=_ACCOUNT)


def test_an_agent_at_a_rung_the_account_lacks_is_refused_where_it_is_made() -> None:
    with pytest.raises(Unserved, match=r"lists no gpt-5\.2-medium"):
        _cursor(effort="medium")
    assert isinstance(_cursor(effort="low"), CursorAgent)
    assert isinstance(_cursor(model="composer-2.5", service_tier="fast"), CursorAgent)


@pytest.mark.parametrize(
    ("given", "error", "match"),
    [
        ({"web_search": False}, Unserved, "no way of being told"),
        ({"service_tier": "flex"}, ValueError, "flex"),
    ],
)
def test_settings_it_cannot_express_are_refused(
    given: dict[str, Any], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        _cursor(**given)


def test_a_blank_extra_root_is_refused_in_the_config() -> None:
    with pytest.raises(ValueError, match="add_dirs"):
        CursorAgentConfig(model="gpt-5.2", effort="", add_dirs=("  ",))


def test_a_fence_that_cuts_the_network_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fence, "enforceable", fenceable)
    with pytest.raises(Unfenced, match="grant it online ALL"):
        _cursor(fence=Fence(read=("/",), write=("/tmp",), online=False))


def test_natively_grants_where_cursor_keeps_its_sign_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    granted = _cursor().natively(Fence(read=("/",), write=()))
    assert os.path.join(tmp_path, "cursor") in granted.write  # noqa: PTH118


def test_a_turn_runs_print_with_the_prompt_after_the_flags(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    _cursor().new(tmp_path)("-v is a prompt")
    proc = spawner.last
    assert proc.args == [
        "cursor-agent",
        "--print",
        "--output-format",
        "stream-json",
        "--model",
        "gpt-5.2",
        "--workspace",
        str(tmp_path),
        "--trust",
        "--",
        "-v is a prompt",
    ]
    assert proc.cwd == str(tmp_path)
    assert proc.stdin is None


@pytest.mark.parametrize(
    ("permission", "flags"),
    [
        ("read-only", ["--mode", "plan"]),
        ("workspace-write", ["--force", "--sandbox", "enabled"]),
        ("auto", ["--auto-review"]),
        ("bypass", ["--force", "--sandbox", "disabled"]),
        ("", []),
    ],
)
def test_each_rung_is_its_own_flags(
    spawner: Spawner, tmp_path: Path, permission: str, flags: list[str]
) -> None:
    spawner.answering(_turn())
    _cursor(permission=permission).new(tmp_path)("go")
    argv = spawner.last.args
    at = argv.index(str(tmp_path)) + 1
    assert argv[at : argv.index("--trust")] == flags


def test_its_own_settings_reach_the_command_line(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    _cursor(
        effort="low",
        trust=False,
        partial_output=True,
        approve_mcps=True,
        add_dirs=("/one", "/two"),
    ).new(tmp_path)("go")
    argv = spawner.last.args
    assert argv[argv.index("--model") + 1] == "gpt-5.2-low"
    assert "--trust" not in argv
    assert "--stream-partial-output" in argv
    assert "--approve-mcps" in argv
    assert argv[argv.index("--approve-mcps") + 1 :][:4] == [
        "--add-dir",
        "/one",
        "--add-dir",
        "/two",
    ]


def test_the_faster_service_is_the_fast_id(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(_turn())
    _cursor(model="composer-2.5", service_tier="fast").new(tmp_path)("go")
    argv = spawner.last.args
    assert argv[argv.index("--model") + 1] == "composer-2.5-fast"


def test_a_turn_reads_its_events_and_cost(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(
        _turn(
            result="the answer",
            inputTokens=100,
            outputTokens=20,
            cacheReadTokens=5,
            cacheWriteTokens=3,
        )
    )
    session = _cursor().new(tmp_path)
    events = list(session.stream("go"))
    said = [(one.kind, one.text) for one in events]
    assert ("text", "hi") in said
    assert ("tool", "read src/x.py") in said
    result = events[-1]
    assert (result.kind, result.text) == ("result", "the answer")
    assert result.tokens == {"gpt-5.2": 128}
    assert dict(result.spent) == {
        "input": 100,
        "output": 20,
        "cache_read": 5,
        "cache_write": 3,
    }
    assert session.id == "chat-1"
    assert session.spent().total == 128


def test_a_turn_that_said_nothing_about_tokens_costs_nothing(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    events = list(_cursor().new(tmp_path).stream("go"))
    assert events[-1].tokens == {}
    assert events[-1].spent.total == 0


def test_the_next_turn_resumes_the_chat_the_first_named(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn(session_id="chat-7"))
    session = _cursor().new(tmp_path)
    session("one")
    session("two")
    first, second = spawner.started
    assert not any(one.startswith("--resume") for one in first.args)
    assert "--resume=chat-7" in second.args
    assert second.args[-2:] == ["--", "two"]


def test_an_agent_of_its_own_is_a_subagent_bracketed_by_its_call(
    spawner: Spawner, tmp_path: Path
) -> None:
    task = {"taskToolCall": {"args": {"description": "read the tests"}}}
    spawner.answering(
        [
            {"type": "system", "session_id": "chat-1"},
            {
                "type": "tool_call",
                "subtype": "started",
                "call_id": "t",
                "tool_call": task,
            },
            {
                "type": "tool_call",
                "subtype": "started",
                "call_id": "t",
                "tool_call": task,
            },
            {
                "type": "tool_call",
                "subtype": "completed",
                "call_id": "t",
                "tool_call": task,
            },
            {"type": "result", "subtype": "success", "result": "ok"},
        ]
    )
    events = list(_cursor().new(tmp_path).stream("go"))
    fleet = [
        (one.kind, one.text, one.whose) for one in events if "subagent" in one.kind
    ]
    assert fleet == [
        ("subagent", "task read the tests", "t"),
        ("subagent-ends", "task read the tests", "t"),
    ]


def test_pieces_asked_for_are_not_said_again_when_gathered(
    spawner: Spawner, tmp_path: Path
) -> None:
    def says(text: str) -> dict[str, Any]:
        return {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": text}]},
        }

    spawner.answering(
        [
            {"type": "system", "session_id": "chat-1"},
            says("a"),
            says("\n\n"),
            says("b"),
            says("a\n\nb"),
            {"type": "result", "subtype": "success", "result": "a\n\nb"},
        ]
    )
    events = list(_cursor(partial_output=True).new(tmp_path).stream("go"))
    assert [one.text for one in events if one.kind == "text"] == ["a", "b"]
    assert events[-1].text == "a\n\nb"


def test_noise_and_stderr_are_not_events(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering(["not json", *_turn()], err="a warning")
    kinds = [one.kind for one in _cursor().new(tmp_path).stream("go")]
    assert kinds.count("text") == 1
    assert kinds[-1] == "result"


@pytest.mark.parametrize(
    ("lines", "code", "match"),
    [
        (
            [
                {"type": "system", "session_id": "c"},
                {
                    "type": "result",
                    "subtype": "error",
                    "is_error": True,
                    "result": "no",
                },
            ],
            0,
            "no",
        ),
        (
            [{"type": "system", "session_id": "c"}, {"type": "result", "subtype": "x"}],
            0,
            "x",
        ),
        ([], 0, "said nothing at all"),
        (_turn(), 3, "exit status 3"),
    ],
)
def test_a_failed_turn_raises_and_leaves_the_session_unopened(
    spawner: Spawner,
    tmp_path: Path,
    lines: list[dict[str, Any]],
    code: int,
    match: str,
) -> None:
    spawner.answering(lines, code=code)
    session = _cursor().new(tmp_path)
    with pytest.raises(Failed, match=match) as failed:
        session("go")
    assert failed.value.returncode != 0
    assert session.named is None or session.named == "c"
    with pytest.raises(RuntimeError, match="has not run a turn"):
        _ = session.id
    assert session("go", suppress=True) == ""


def test_a_turn_naming_no_chat_is_refused(spawner: Spawner, tmp_path: Path) -> None:
    spawner.answering([{"type": "result", "subtype": "success", "result": "ok"}])
    with pytest.raises(ValueError, match="named no chat"):
        _cursor().new(tmp_path)("go")


def test_new_opens_a_cursor_session_where_it_is_told(tmp_path: Path) -> None:
    session = _cursor().new(tmp_path)
    assert isinstance(session, CursorSession)
    assert session.cwd == str(tmp_path)


def test_reconfiguring_onto_another_rung_moves_the_id(
    spawner: Spawner, tmp_path: Path
) -> None:
    spawner.answering(_turn())
    agent = _cursor()
    agent.reconfigure(replace(agent.config, effort="xhigh"))
    agent.new(tmp_path)("go")
    argv = spawner.last.args
    assert argv[argv.index("--model") + 1] == "gpt-5.2-xhigh"
