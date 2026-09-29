"""Codex held to a fence: all of it from outside, and its web search off from inside."""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor.agents import CodexAgent, CodexAgentConfig
from hmz.coganchor.agents.codex import unattended
from hmz.coganchor.agents.config import anchored
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture(autouse=True)
def enforceable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Takes this machine to be one that can fence a process, with a home of the test's."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)


def _fence(tmp_path: Path) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system="none",
            online=False,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
            hosts=("chatgpt.com",),
        ),
        tmp=str(tmp_path / "scratch"),
    )


def test_codex_enforces_none_of_its_fence_itself(tmp_path: Path) -> None:
    """Its sandbox holds its commands and not itself, its MCP servers or its hooks."""
    fence = _fence(tmp_path)
    agent = CodexAgent(CodexAgentConfig(model="m", effort="high", fence=fence))

    assert agent.natively(fence) is fence


def test_a_fenced_codex_offline_is_wrapped_and_told_not_to_search(
    tmp_path: Path,
) -> None:
    """The wrapper holds the paths and the hosts; only Codex can switch its search off."""
    agent = CodexAgent(
        CodexAgentConfig(
            model="m", effort="high", fence=_fence(tmp_path), web_search=False
        )
    )

    argv = agent.spawned(agent._argv(()))

    assert argv[:7] == [
        sys.executable,
        "-Pm",
        "hmz",
        "internal",
        "fence",
        argv[5],
        "--",
    ]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert not policy.online
    assert "chatgpt.com" in policy.hosts
    assert policy.allows(tmp_path / "home" / ".codex" / "auth.json", write=True)
    assert not policy.allows(tmp_path / "home" / "elsewhere", write=True)
    assert not policy.allows("/etc/machine-id")
    rest = argv[argv.index("--") + 1 :]
    assert rest[rest.index("-c") + 1] == 'web_search="disabled"'


@pytest.mark.parametrize("searching", [True, None, False])
def test_a_cut_network_turns_off_what_openai_runs_whatever_web_search_says(
    tmp_path: Path, *, searching: bool | None
) -> None:
    """Its web search and its apps run at OpenAI, where the proxy the fence leaves is."""
    agent = CodexAgent(
        CodexAgentConfig(
            model="m",
            effort="high",
            fence=_fence(tmp_path),
            web_search=searching,
            features=(("apps", True),),
        )
    )

    argv = agent._argv(())

    assert argv[argv.index("-c") + 1] == 'web_search="disabled"'
    assert argv[argv.index("apps") - 1 : argv.index("apps") + 1] == [
        "--disable",
        "apps",
    ]
    assert argv.count("apps") == 1


def test_an_open_network_leaves_both_as_the_flow_said(tmp_path: Path) -> None:
    fence = dataclasses.replace(_fence(tmp_path), online=True)
    agent = CodexAgent(
        CodexAgentConfig(model="m", effort="high", fence=fence, web_search=True)
    )

    argv = agent._argv(())

    assert argv[argv.index("-c") + 1] == 'web_search="live"'
    assert "apps" not in argv


class _Server:
    """The one thing a turn asks of its server about the rung: what it runs it at."""

    @staticmethod
    def permitted(permission: str, service_tier: str) -> dict[str, Any]:
        return unattended(permission, service_tier)


@pytest.mark.parametrize(
    ("permission", "scopes", "online", "policy"),
    [
        ("read-only", (READ, READ, READ), True, "enabled"),
        ("read-only", (READ, NONE, NONE), False, "restricted"),
        ("workspace-write", (ALL, READ, NONE), True, "enabled"),
        # A fence wider than the rung leaves the rung to Codex's own sandbox.
        ("read-only", (ALL, READ, READ), True, None),
        ("workspace-write", (ALL, ALL, READ), True, None),
        # And a rung with no sandbox has none to leave out.
        ("bypass", (ALL, READ, READ), True, None),
    ],
)
def test_an_anchored_turn_leaves_its_sandbox_to_the_anchors_fence(
    tmp_path: Path,
    *,
    permission: str,
    scopes: tuple[str, str, str],
    online: bool,
    policy: str | None,
) -> None:
    """Codex's sandbox wraps a command in a helper, which an anchor would run on the target.

    Where the fence the anchor holds on both machines is the rung, the turn is told its
    commands are sandboxed from outside instead, with the network the fence leaves them.
    """
    local, user, system = scopes
    fence = Fence.of(
        local=local,
        user=user,
        system=system,
        online=online,
        workdir=tmp_path / "work",
        home=tmp_path / "home",
    )
    agent = CodexAgent(
        CodexAgentConfig(
            model="m",
            effort="high",
            permission=permission,
            fence=fence,
            machine=anchored("ssh://box"),
        )
    )

    said = agent.new()._turned(cast("Any", _Server()))

    if policy is None:
        assert said.get("sandboxPolicy", {}).get("type") != "externalSandbox"
    else:
        assert said["sandboxPolicy"] == {
            "type": "externalSandbox",
            "networkAccess": policy,
        }
    # Nor is Landlock asked for, which would be this machine's sandbox and not the target's.
    assert "use_legacy_landlock" not in agent._argv(())


def test_a_turn_on_this_machine_keeps_its_own_sandbox(tmp_path: Path) -> None:
    fence = dataclasses.replace(_fence(tmp_path), online=True)
    agent = CodexAgent(
        CodexAgentConfig(model="m", effort="high", permission="read-only", fence=fence)
    )

    said = agent.new()._turned(cast("Any", _Server()))

    assert said["sandboxPolicy"] == {"type": "readOnly", "networkAccess": True}
