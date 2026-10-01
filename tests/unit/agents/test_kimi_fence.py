"""How Kimi Code's daemon is put inside the fence its agent is held to.

Kimi holds no part of a fence itself, so the whole of it is the wrapper's; what is the
driver's is the daemon it is put around. That daemon is the agent's, started once and shared
by every session, so it is started inside the fence the agent has now -- a new one where the
fence moves -- and where the network is cut it is told the exact port it may listen on.
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import KimiCodeCLIAgent, KimiCodeCLIAgentConfig
from hmz.coganchor.agents import kimi as driver
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class _Started:
    """A daemon that was never started: the command it would have been, and nothing more."""

    def __init__(self, argv: list[str], env: Mapping[str, str] | None = None) -> None:
        del env
        self.argv = argv

    def stop(self) -> None:
        pass


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture(autouse=True)
def _enforceable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setattr("hmz.coganchor.fence.landlocked", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(driver, "_AppServer", _Started)


def _fence(tmp_path: Path, *, online: bool = False, user: str = READ) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=ALL,
            user=user,
            system=NONE,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
        ),
        tmp=str(tmp_path / "scratch"),
    )


def _agent(fence: Fence | None, **config: object) -> KimiCodeCLIAgent:
    return KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="m", effort="high", fence=fence, **config)  # pyright: ignore[reportArgumentType]
    )


def _argv(agent: KimiCodeCLIAgent) -> list[str]:
    started = agent.server
    assert isinstance(started, _Started)
    return started.argv


def _port(argv: list[str]) -> int:
    return int(argv[argv.index("--port") + 1])


def _policy(argv: list[str]) -> Fence:
    assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    return Fence.loads(argv[5].removeprefix("--policy="))


def test_kimi_holds_none_of_its_fence_itself(tmp_path: Path) -> None:
    fence = _fence(tmp_path)
    assert _agent(fence).natively(fence) == fence


def test_a_cut_network_tells_the_daemon_the_one_port_it_may_bind(
    tmp_path: Path,
) -> None:
    argv = _argv(_agent(_fence(tmp_path)))
    port = _port(argv)
    assert port != 0
    policy = _policy(argv)
    assert policy.listen == (port,)
    assert not policy.online
    assert argv[argv.index("--") + 1 : argv.index("--") + 3] == ["kimi", "web"]


def test_a_port_the_config_names_is_the_one_granted(tmp_path: Path) -> None:
    argv = _argv(_agent(_fence(tmp_path), port=45678))
    assert _port(argv) == 45678
    assert _policy(argv).listen == (45678,)


def test_a_network_left_alone_grants_no_port_and_asks_for_any(tmp_path: Path) -> None:
    argv = _argv(_agent(_fence(tmp_path, online=True)))
    assert _port(argv) == 0
    assert _policy(argv).listen == ()


def test_an_unfenced_agent_starts_its_daemon_bare() -> None:
    argv = _argv(_agent(None))
    assert argv[:2] == ["kimi", "web"]
    assert _port(argv) == 0


def test_a_daemon_is_not_shared_across_fences(tmp_path: Path) -> None:
    fence = _fence(tmp_path)
    agent = _agent(fence)
    first = agent.server
    assert agent.server is first
    agent.reconfigure(replace(agent.config, fence=fence))
    assert agent.server is first
    wider = _fence(tmp_path, online=True)
    agent.reconfigure(replace(agent.config, fence=wider))
    second = agent.server
    assert second is not first
    assert _policy(_argv(agent)).online
    agent.reconfigure(replace(agent.config, fence=None))
    assert _argv(agent)[:2] == ["kimi", "web"]


@pytest.mark.parametrize("searching", [None, True, False])
def test_a_cut_network_takes_the_web_tools_away_whatever_was_said(
    tmp_path: Path, searching: bool | None
) -> None:
    session = _agent(_fence(tmp_path), web_search=searching).new()
    assert session._told()[1]["disabled_tools"] == ["WebSearch", "FetchURL"]


def test_a_network_left_alone_leaves_the_web_as_it_was_said(tmp_path: Path) -> None:
    session = _agent(_fence(tmp_path, online=True), web_search=True).new()
    assert session._told()[1]["disabled_tools"] == []
