"""pi held to a fence: all of it from outside, with its own model APIs let through.

pi has no sandbox, so every scope is the wrapper's; what the driver adds is the hosts of the
providers `models.json` declares, which no variable names, and ``--offline`` where the network
is cut. Read off the command lines built, with nothing spawned.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

from hmz.coganchor.agents import PiAgent, PiAgentConfig
from hmz.coganchor.fence import ALL, READ, Fence

GATEWAY = "nvgw/nvidia/minimaxai/minimax-m3"


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A home of the test's own, on a machine taken to be one that can fence a process."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    return tmp_path / "home"


def _models(home: Path, providers: object) -> None:
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "models.json").write_text(json.dumps({"providers": providers}))


def _agent(tmp_path: Path, model: str = GATEWAY, *, online: bool = False) -> PiAgent:
    fence = dataclasses.replace(
        Fence.of(
            local=ALL,
            user=READ,
            system=READ,
            online=online,
            workdir=tmp_path / "work",
            home=tmp_path / "home",
        ),
        tmp=str(tmp_path / "scratch"),
    )
    return PiAgent(PiAgentConfig(model=model, effort="low", fence=fence))


def _policy(argv: list[str]) -> Fence:
    assert argv[:5] == [sys.executable, "-m", "hmz", "internal", "fence"]
    return Fence.loads(argv[5].removeprefix("--policy="))


def test_pi_enforces_nothing_itself(home: Path, tmp_path: Path) -> None:
    del home
    agent = _agent(tmp_path)
    fence = agent.fenced()

    assert fence is not None
    assert agent.natively(fence) == fence
    policy = _policy(agent.spawned(["pi", "--mode", "rpc"]))
    assert not policy.online
    assert policy.allows(Path("~/.pi/agent/sessions/x.jsonl").expanduser(), write=True)
    assert not policy.allows(Path("~/.bashrc").expanduser(), write=True)


def test_the_gateway_models_json_declares_is_let_through(
    home: Path, tmp_path: Path
) -> None:
    _models(
        home,
        {
            "nvgw": {
                "baseUrl": "https://inference-api.nvidia.com/v1",
                "models": [{"id": "x", "baseUrl": "https://other.example:8443/v1"}],
            },
            "elsewhere": {"baseUrl": "https://elsewhere.example/v1"},
        },
    )

    hosts = _policy(_agent(tmp_path).spawned(["pi"])).hosts

    assert "inference-api.nvidia.com" in hosts
    assert "other.example:8443" in hosts
    # Only the provider the model is named under.
    assert "elsewhere.example" not in hosts
    # The backend's own, still.
    assert "api.anthropic.com" in hosts


def test_a_model_named_without_a_provider_lets_every_declared_one_through(
    home: Path, tmp_path: Path
) -> None:
    _models(
        home,
        {
            "a": {"baseUrl": "https://a.example/v1"},
            "b": {"baseUrl": "https://b.example"},
        },
    )

    hosts = _policy(_agent(tmp_path, "minimax-m3").spawned(["pi"])).hosts

    assert {"a.example", "b.example"} <= set(hosts)


@pytest.mark.parametrize("written", ["not json", '{"providers": []}', "{}"])
def test_a_models_json_pi_would_not_read_adds_nothing(
    home: Path, tmp_path: Path, written: str
) -> None:
    agent = home / ".pi" / "agent"
    agent.mkdir(parents=True)
    (agent / "models.json").write_text(written)
    agent = _agent(tmp_path)

    fenced = agent.fenced()

    assert fenced is not None
    assert fenced.hosts == super(PiAgent, agent).fenced().hosts  # pyright: ignore[reportOptionalMemberAccess]


def test_pi_is_started_offline_where_the_network_is_cut(
    home: Path, tmp_path: Path
) -> None:
    del home
    cut = _agent(tmp_path).new()._command()
    online = _agent(tmp_path, online=True).new()._command()

    assert "--offline" in cut
    assert "--offline" not in online


def test_a_model_under_a_provider_the_file_does_not_declare_lets_none_through(
    home: Path, tmp_path: Path
) -> None:
    _models(home, {"corpgw": {"baseUrl": "https://corp-gw.internal/v1"}})

    hosts = _policy(_agent(tmp_path, "openai/gpt-5").spawned(["pi"])).hosts

    assert "corp-gw.internal" not in hosts
