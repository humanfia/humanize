"""Grok Build held to a fence: all of it from outside, and never on the shared leader.

Read off the commands the driver builds, with nothing spawned: Grok Build's own sandbox cannot
say a fence (its network setting leaves the process's own egress alone, and every profile
writes `/tmp`), so the whole fence goes to ``hmz internal fence`` -- and the leader, a process
started outside that wall, is kept out of a fenced conversation.
"""

from __future__ import annotations

import dataclasses
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import GrokBuildAgent, GrokBuildAgentConfig, Unfenced
from hmz.coganchor.fence import ALL, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture
def enforceable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A host that can hold any fence, with a home of the test's own."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def _fence(tmp_path: Path, *, everything: bool = False, online: bool = False) -> Fence:
    level = ALL if everything else READ
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=level,
            system=level,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
        ),
        tmp=str(tmp_path / "scratch"),
    )


def _agent(fence: Fence | None, **config: object) -> GrokBuildAgent:
    return GrokBuildAgent(
        GrokBuildAgentConfig(model="grok-build", effort="high", fence=fence, **config)  # pyright: ignore[reportArgumentType]
    )


def test_grok_enforces_none_of_its_fence_itself(tmp_path: Path) -> None:
    fence = _fence(tmp_path)
    assert _agent(None).natively(fence) is fence


@pytest.mark.usefixtures("enforceable")
@pytest.mark.parametrize("online", [False, True])
def test_a_fenced_turn_is_held_whole_from_outside(tmp_path: Path, online: bool) -> None:
    agent = _agent(_fence(tmp_path, online=online))
    session = agent.new(tmp_path / "work")

    argv = agent.spawned(session._command())

    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    policy = Fence.loads(argv[5].removeprefix("--policy="))
    assert policy.online is online
    assert not policy.allows("/tmp/x", write=True)
    assert policy.allows(tmp_path / "home" / ".grok" / "sessions", write=True)
    inner = argv[argv.index("--") + 1 :]
    # Grok Build's own sandbox is not asked for on either transport.
    assert "--sandbox" not in inner
    assert "--sandbox" not in session._turn("hi")[0]


@pytest.mark.usefixtures("enforceable")
@pytest.mark.parametrize("leader", [None, False])
def test_a_fenced_conversation_never_joins_the_leader(
    tmp_path: Path, leader: bool | None
) -> None:
    argv = _agent(_fence(tmp_path), leader=leader).new()._command()

    assert "--no-leader" in argv
    assert "--leader" not in argv


@pytest.mark.usefixtures("enforceable")
def test_a_fenced_agent_told_to_join_the_leader_is_refused(tmp_path: Path) -> None:
    with pytest.raises(Unfenced, match="leader"):
        _agent(_fence(tmp_path), leader=True)


@pytest.mark.usefixtures("enforceable")
def test_a_fence_that_fences_nothing_leaves_the_leader_as_it_was_said(
    tmp_path: Path,
) -> None:
    fence = _fence(tmp_path, everything=True, online=True)
    assert fence.open

    agent = _agent(fence, leader=True)

    assert "--leader" in agent.new()._command()
    assert agent.spawned(["grok"])[:1] != [sys.executable]
    assert "--no-leader" not in _agent(fence, leader=None).new()._command()


@pytest.mark.usefixtures("enforceable")
@pytest.mark.parametrize("web_search", [None, True, False])
def test_a_fence_that_cuts_the_network_takes_the_web_tools_away(
    tmp_path: Path, web_search: bool | None
) -> None:
    """Its search may run at xAI's own host, which the proxy lets through, so it is not given.

    Whatever `web_search` says: the one flag that says it is refused by `grok agent`, so every
    turn of such a conversation is taken with `grok -p`, which takes it.
    """
    session = _agent(_fence(tmp_path), web_search=web_search).new(tmp_path / "work")

    assert session._commanded()
    argv = session._turn("hi")[0]
    assert argv.count("--disable-web-search") == 1
    assert "--disable-web-search" not in session._command()


@pytest.mark.usefixtures("enforceable")
@pytest.mark.parametrize("web_search", [None, True])
def test_a_fence_that_leaves_the_network_leaves_the_web_tools(
    tmp_path: Path, web_search: bool | None
) -> None:
    """Granted the network, a conversation searches as it was told and stays held open."""
    agent = _agent(_fence(tmp_path, online=True), web_search=web_search)
    session = agent.new(tmp_path / "work")

    assert not session._commanded()
    assert "--disable-web-search" not in session._turn("hi")[0]
