"""A flow's Claude Code session, settled by the runtime and run against a stand-in `claude`.

The stand-in routes a request over the stream only where it was told
`--permission-prompt-tool stdio`, as the real CLI does; told nothing, it denies the tool by
itself. So what is checked is what the runtime makes of a grant and the hooks hung on it, and
whether a question the agent asks then reaches the hook hung for it.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Question,
)
from hmz.flows import HarnessKind, HookKind, Permission, PermissionKind
from hmz.runtime.flowing.harnesses import settled
from tests.integration.doubles_agents import Standins, standins

if TYPE_CHECKING:
    from pathlib import Path

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
READ = Permission(local=PermissionKind.READ)


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
        ClaudeCodeAgent,
        permission,
        hung,
        tellable=True,
        workdir=str(workdir),
    )
    assert isinstance(config, ClaudeCodeAgentConfig)
    return config


@pytest.mark.parametrize(
    ("permission", "hung", "rung", "asks"),
    [
        (READ, frozenset({HookKind.ASK_USER}), "read-only", False),
        (Permission(), frozenset[HookKind](), "bypass", False),
        (Permission(), frozenset({HookKind.PERMISSION_REQUEST}), "bypass", True),
    ],
)
def test_the_runtime_settles_the_rung_and_asks_from_the_hooks_hung(
    tmp_path: Path,
    permission: Permission,
    hung: frozenset[HookKind],
    rung: str,
    asks: bool,
) -> None:
    config = _settled(permission, hung, tmp_path)

    assert (config.permission, config.asks) == (rung, asks)


def test_a_question_asked_at_read_only_reaches_the_ask_user_hook(
    claude: Standins, tmp_path: Path
) -> None:
    config = _settled(READ, frozenset({HookKind.ASK_USER}), tmp_path)
    # Without the read-only wall, which would keep the stand-in from writing down its calls:
    # what is checked here is the rung and where its questions go.
    agent = ClaudeCodeAgent(dataclasses.replace(config, fence=None))
    asked: list[Question] = []

    def ask(question: Question) -> str | None:
        asked.append(question)
        return "blue"

    agent.ask = ask

    assert agent.new(tmp_path)("go") == "allow:{'Which?': 'blue'}"
    assert [(one.text, one.options) for one in asked] == [("Which?", ("blue",))]
    (launch,) = (one for one in claude.calls() if not one.stdin)
    assert launch.flag("--permission-mode") == "plan"
    assert launch.flag("--permission-prompt-tool") == "stdio"
