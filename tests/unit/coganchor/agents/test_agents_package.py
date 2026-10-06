"""`hmz.coganchor.agents`: which class drives which backend, and what the package says."""

from __future__ import annotations

import pytest

from hmz.coganchor import agents, backends
from hmz.coganchor.agents import (
    DRIVEN,
    AcpAgent,
    AcpAgentConfig,
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    driver,
)


def test_every_driven_backend_is_a_known_cli_or_litellm() -> None:
    assert set(DRIVEN) == {
        "agy",
        "claude",
        "codex",
        "cursor-agent",
        "dsh",
        "grok",
        "kimi",
        "litellm",
        "mcode",
        "mimo",
        "opencode",
        "pi",
        "qwen",
    }
    for name, (agent, config) in DRIVEN.items():
        assert issubclass(agent, AgentBase), name
        assert issubclass(config, AgentConfig), name


def test_driven_classes_are_one_apiece() -> None:
    assert len({agent for agent, _ in DRIVEN.values()}) == len(DRIVEN)
    assert len({config for _, config in DRIVEN.values()}) == len(DRIVEN)


@pytest.mark.parametrize("name", sorted(DRIVEN))
def test_a_driven_backend_is_one_written_down_and_driven_by_its_entry(
    name: str,
) -> None:
    profile = backends.named(name)
    assert profile is not None
    assert profile.name == name
    assert driver(name) == DRIVEN[name]


def test_driver_of_claude() -> None:
    assert driver("claude") == (ClaudeCodeAgent, ClaudeCodeAgentConfig)


def test_driver_of_an_added_cli_is_the_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backends, "speaking", lambda: {"mycli": ("mycli", "--acp")})
    assert driver("mycli") == (AcpAgent, AcpAgentConfig)


def test_driver_of_nothing_anybody_drives(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backends, "speaking", dict)
    with pytest.raises(KeyError):
        driver("nobody")


def test_all_is_what_the_package_has() -> None:
    assert len(set(agents.__all__)) == len(agents.__all__)
    for name in agents.__all__:
        assert hasattr(agents, name), name
    assert "driver" not in agents.__all__
    assert agents.SWARM is backends.SWARM
