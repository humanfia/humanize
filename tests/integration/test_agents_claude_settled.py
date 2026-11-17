"""A flow's Claude Code session, settled by the runtime and run against a stand-in `claude`.

The stand-in routes a request over the stream only where it was told
`--permission-prompt-tool stdio`, as the real CLI does; told nothing, it denies the tool by
itself. So what is checked is what the runtime makes of a grant and the hooks hung on it, and
whether a question the agent asks then reaches the hook hung for it: routed for every fenced
agent, whatever its fence writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    KimiCodeCLIAgentConfig,
    Question,
)
from hmz.flows import HarnessKind, HookKind, Permission
from hmz.runtime.flowing.harnesses import settled
from tests.integration.doubles_agents import Standins, standins

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.fence import Fence

CLAUDE = r"""
note()
session = flags.get("--session-id") or flags.get("--resume") or "s-none"
out({"type": "system", "subtype": "init", "session_id": session,
     "model": flags.get("--model"),
     "permissionMode": flags.get("--permission-mode", "default")})


def result(text):
    out({"type": "result", "subtype": "success", "session_id": session, "result": text})


for line in sys.stdin:
    note(json.loads(line)["message"]["content"][0]["text"])
    if flags.get("--permission-prompt-tool") != "stdio":
        result("denied by itself")
        continue
    out({"type": "control_request", "request_id": "r1", "request": {
        "subtype": "can_use_tool", "tool_name": "AskUserQuestion",
        "input": {"questions": [{"question": "Which?", "options": [{"label": "blue"}]}]}}})
    answer = json.loads(sys.stdin.readline())["response"]["response"]
    result(answer["behavior"] + ":" + str(answer.get("updatedInput", {}).get("answers")))
"""

#: What the flow grants: the workdir read-only, nothing else written.
READ = Permission(preset="read-only")


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Standins:
    held = standins(tmp_path, monkeypatch)
    held.install("claude", CLAUDE)
    return held


def _settled(
    permission: Permission, hung: frozenset[HookKind], workdir: Path
) -> ClaudeCodeAgentConfig:
    config = settled(
        ClaudeCodeAgentConfig(model="claude-stand-in", effort=""),
        HarnessKind.CLAUDE,
        permission,
        hung,
        tellable=True,
        workdir=str(workdir),
    )
    assert isinstance(config, ClaudeCodeAgentConfig)
    return config


@pytest.mark.parametrize(
    ("permission", "hung", "writes", "asks"),
    [
        (READ, frozenset({HookKind.ASK_USER}), False, False),
        (Permission(), frozenset[HookKind](), True, False),
        (Permission(), frozenset({HookKind.PERMISSION_REQUEST}), True, True),
    ],
)
def test_the_runtime_settles_the_fence_and_asks_from_the_hooks_hung(
    tmp_path: Path,
    permission: Permission,
    hung: frozenset[HookKind],
    writes: bool,
    asks: bool,
) -> None:
    config = _settled(permission, hung, tmp_path)

    assert config.fence is not None
    assert (config.fence.writes, config.asks) == (writes, asks)
    assert not hasattr(config, "permission")


@pytest.mark.parametrize(
    ("hung", "asks"),
    [
        (frozenset[HookKind](), False),
        (frozenset({HookKind.STOP, HookKind.PRE_TOOL_USE}), False),
        (frozenset({HookKind.PERMISSION_REQUEST}), True),
        (frozenset({HookKind.ASK_USER}), True),
    ],
)
def test_kimi_is_settled_to_ask_only_for_the_hooks_the_flow_hung(
    tmp_path: Path, hung: frozenset[HookKind], asks: bool
) -> None:
    """Said outright, so the driver's own hook and `agent.ask` are not read as the flow's."""
    config = settled(
        KimiCodeCLIAgentConfig(model="kimi-stand-in", effort=""),
        HarnessKind.KIMI,
        Permission(),
        hung,
        tellable=True,
        workdir=str(tmp_path),
    )

    assert isinstance(config, KimiCodeCLIAgentConfig)
    assert config.asks is asks


def test_a_question_asked_under_a_fence_that_writes_nothing_reaches_the_ask_user_hook(
    claude: Standins, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def enforceable(*, net: bool) -> bool:
        del net
        return True

    def wrapper(fence: Fence) -> list[str]:
        del fence
        return []

    # The fence the runtime drew is kept, for the driver to read the grant off; the wall itself
    # is not put up, since it would keep the stand-in from writing down its calls, and what
    # is checked here is what Claude is told and where its questions go.
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", enforceable)
    monkeypatch.setattr("hmz.coganchor.fence.wrapper", wrapper)
    config = _settled(READ, frozenset({HookKind.ASK_USER}), tmp_path)
    assert config.fence is not None
    assert not config.fence.writes
    agent = ClaudeCodeAgent(config)
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return "blue"

    agent.ask = ask

    assert agent.new(tmp_path)("go") == "allow:{'Which?': 'blue'}"
    assert [(one.text, one.options) for one in asked] == [("Which?", ("blue",))]
    (launch,) = (one for one in claude.calls() if not one.stdin)
    assert launch.flag("--permission-mode") == "bypassPermissions"
    assert launch.flag("--tools") == "default"
    assert (launch.flag("--disallowedTools") or "").split(",")[:3] == [
        "Edit",
        "Write",
        "NotebookEdit",
    ]
    assert launch.flag("--permission-prompt-tool") == "stdio"
