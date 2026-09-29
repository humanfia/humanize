"""Claude Code under a fence: held from outside, and told only what the wall cannot say.

Claude's own sandbox holds the commands its Bash tool runs and nothing else, so none of a fence
is claimed as held natively and the whole of it is put around the CLI. What Claude is told is
the one thing the wall cannot do: its web search runs at the model API, the one host a cut
network still reaches, so a fence that cuts the network takes the web tools away by rule.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.fence import ALL, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture(autouse=True)
def enforceable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Takes this machine to be one that can fence a process, with a home of the test's own."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def _fence(tmp_path: Path, *, online: bool) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=READ,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
            hosts=["api.anthropic.com"],
        ),
        tmp=str(tmp_path / "scratch"),
    )


def _agent(fence: Fence | None, **config: object) -> ClaudeCodeAgent:
    return ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", fence=fence, **config)  # pyright: ignore[reportArgumentType]
    )


def _denied(agent: ClaudeCodeAgent) -> list[str]:
    argv = agent.new()._command()
    if "--disallowedTools" not in argv:
        return []
    return argv[argv.index("--disallowedTools") + 1].split(",")


@pytest.mark.parametrize("online", [True, False])
def test_claude_holds_none_of_its_fence_itself(tmp_path: Path, online: bool) -> None:
    fence = _fence(tmp_path, online=online)
    agent = _agent(fence)

    assert agent.natively(fence) is fence
    widened = agent.fenced()
    assert widened is not None
    assert agent.natively(widened) is widened


@pytest.mark.parametrize("online", [True, False])
def test_the_whole_fence_is_put_around_claude(tmp_path: Path, online: bool) -> None:
    argv = _agent(_fence(tmp_path, online=online)).spawned(["claude", "--print"])

    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert policy.online is online
    assert not policy.allows(tmp_path / "home" / "x", write=True)
    assert policy.allows(tmp_path / "work" / "x", write=True)


@pytest.mark.parametrize("web_search", [None, True, False])
def test_a_cut_network_takes_the_web_tools_away_whatever_web_search_says(
    tmp_path: Path, web_search: bool | None
) -> None:
    """The search runs at the model API, which the wall still lets through."""
    denied = _denied(_agent(_fence(tmp_path, online=False), web_search=web_search))

    assert denied == ["WebSearch", "WebFetch"]


def test_a_fence_that_leaves_the_network_leaves_the_web_tools(tmp_path: Path) -> None:
    assert _denied(_agent(_fence(tmp_path, online=True))) == []
    assert _denied(_agent(None)) == []


def test_a_fence_moved_offline_ends_the_process_that_was_told_otherwise(
    tmp_path: Path,
) -> None:
    """`--disallowedTools` is read when Claude starts, so the next turn needs a new one."""
    agent = _agent(_fence(tmp_path, online=True))
    session = agent.new()
    session._command()
    session._restarted()
    assert not session._stale()

    agent.reconfigure(
        dataclasses.replace(agent.config, fence=_fence(tmp_path, online=False))
    )

    assert session._stale()


def test_a_reconfigure_that_fails_other_than_by_refusal_keeps_the_config_it_had(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = _agent(_fence(tmp_path, online=True))
    was = agent.config

    def broken(fence: Fence) -> Fence:
        raise OSError(fence.tmp)

    monkeypatch.setattr(agent, "natively", broken)
    with pytest.raises(OSError):  # noqa: PT011
        agent.reconfigure(
            dataclasses.replace(was, fence=_fence(tmp_path, online=False))
        )

    assert agent.config is was
