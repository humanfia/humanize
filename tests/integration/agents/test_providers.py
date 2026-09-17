"""Which account an agent's turns run as, and what that does to the turn.

Two things reach a backend from a provider: the variables it was made with, which is how a key
or an endpoint gets in, and the paths its credentials are answered by, which is how a login
does. What is checked here is the seam both arrive through -- what an agent under a provider
says its environment is, which variables it hushes, what command it would spawn, and what it
tells an anchor to answer -- read off objects in this process. Nothing here supervises anything,
so CI runs the lot.

The other half is `tests/system/agents/test_providers.py`, where the turn is actually taken: a
login is answered by a seccomp filter and a `ptrace` supervisor swapping the paths a CLI opens,
and a command line says nothing about whether a kernel will hand over a tracee. Those carry
`@traced`, which is a question only running one answers -- a container without `CAP_SYS_PTRACE`
would skip every one of them and read as green, so they are not CI's to run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import AgentConfig, ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.coganchor.backends import named
from hmz.coganchor.machines import MachineBase, MachineConfig
from tests.stubs import HereAnchor, ShellAgent, ShellSession

if TYPE_CHECKING:
    import os
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


class _ClaudeShellSession(ShellSession):
    """A shell session that says it is Claude's, so a provider's real paths are in play."""


class _ClaudeShellAgent(ShellAgent):
    """A shell-backed agent wearing Claude's name, which is what a provider is looked up by."""

    @property
    def backend(self) -> str:
        return "claude"

    def new(self, cwd: str | os.PathLike[str] | None = None) -> _ClaudeShellSession:
        return _ClaudeShellSession(self, cwd)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts this user's home somewhere temporary, so nothing here can read the real one."""
    house = tmp_path / "home"
    (house / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # What the machine itself is signed in as, which a turn under a provider must never see.
    (house / ".claude.json").write_text('{"account": "the one at this machine"}')
    (house / ".claude" / ".credentials.json").write_text('{"token": "this machine"}')
    return house


def test_an_agent_with_no_provider_is_run_exactly_as_it_was() -> None:
    agent = ShellAgent(CONFIG)

    assert agent.provider is None
    assert agent.environment() == {}
    assert agent.spawned(["sh", "-c", "echo hi"]) == ["sh", "-c", "echo hi"]
    assert agent.new()("echo hi") == "hi"


def test_an_agent_with_no_provider_is_run_with_the_environment_it_was_started_in(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is taken away from an agent nobody said anything about."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high"))

    assert agent.hushed() == frozenset()
    assert agent.new()('printf %s "$ANTHROPIC_API_KEY"') == "the one in the shell"


def test_an_agent_told_of_an_account_there_is_none_of_says_so(home: Path) -> None:
    """Rather than quietly running as whoever is signed in here, which is the wrong account."""
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="nowhere"))

    with pytest.raises(ValueError, match="no claude provider called 'nowhere'"):
        _ = agent.provider


def test_what_a_provider_adds_to_the_command_line_is_added_to_the_backends(
    home: Path,
) -> None:
    """Codex takes a provider as settings rather than variables, so a way may carry arguments."""
    providers.add(
        "claude", "mine", way="gateway", env={"X": "1"}, args=("--flag", "value")
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    spawned = agent.spawned(["claude", "--print"])

    assert spawned[:5] == [sys.executable, "-m", "hmz", "internal", "cred"]
    # The backend's own line, the provider's arguments at the end of it.
    assert spawned[spawned.index("--") + 1 :] == [
        "claude",
        "--print",
        "--flag",
        "value",
    ]


@dataclass(frozen=True, kw_only=True)
class _StubMachineConfig(MachineConfig):
    """A machine that is only ever said to be started, holding the anchor it hands back."""

    anchor: HereAnchor

    def create(self) -> _StubMachine:
        return _StubMachine(self)


class _StubMachine(MachineBase):
    def __init__(self, config: _StubMachineConfig) -> None:
        super().__init__(config)
        self._anchor = config.anchor

    def start(self) -> HereAnchor:
        return self._anchor

    def stop(self) -> None:
        """Nothing was started, so there is nothing to take down."""


def test_a_turn_that_is_anchored_and_under_a_provider_is_supervised_once(
    home: Path,
) -> None:
    """A process has one tracer, so the anchor is told what to answer rather than wrapped."""
    providers.add("claude", "mine", way="login")
    anchor = HereAnchor(target="tcp://stub:0")
    agent = _ClaudeShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            provider="mine",
            machine=_StubMachineConfig(anchor=anchor),
        )
    )

    spawned = agent.spawned(["claude", "--print"])

    # Nothing of ours around it: the anchor's own supervisor is the one that will run it.
    assert spawned == ["claude", "--print"]
    assert anchor.seen == [["claude", "--print"]]
    assert anchor.kept == [[]]  # a login carries no variables, so none are held back
    (answered,) = anchor.answered
    assert (
        str(home / ".claude" / ".credentials.json"),
        str(providers.where("claude", "mine") / "home" / ".credentials.json"),
    ) in answered


def test_an_anchored_turn_keeps_its_providers_variables_off_the_target(
    home: Path,
) -> None:
    """A key crossing to another machine is a key on that machine, so it does not cross.

    Everything an agent exports is inherited by every command it runs on the target, so the
    variables a provider hands it are named as the agent's own and dropped on the way over.
    """
    providers.add(
        "claude", "gateway", way="gateway", env={"ANTHROPIC_AUTH_TOKEN": "not-a-token"}
    )
    anchor = HereAnchor(target="tcp://stub:0")
    agent = _ClaudeShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            provider="gateway",
            machine=_StubMachineConfig(anchor=anchor),
        )
    )

    agent.spawned(["claude", "--print"])

    assert anchor.kept == [["ANTHROPIC_AUTH_TOKEN"]]


def test_a_provider_of_a_backend_with_no_credentials_named_is_only_variables() -> None:
    """A stand-in backend has no paths written down, so there is nothing to supervise."""
    agent = ShellAgent(CONFIG)

    assert named(agent.backend) is None
    assert agent.spawned(["sh", "-c", "true"]) == ["sh", "-c", "true"]


def test_a_provider_reaches_the_command_a_real_backend_builds(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the real driver rather than a stand-in: the seam is on the agent, not the CLI."""
    providers.add("claude", "mine", way="key", env={"ANTHROPIC_API_KEY": "not-real"})
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", provider="mine")
    )

    assert agent.environment() == {"ANTHROPIC_API_KEY": "not-real"}
    spawned = agent.spawned(["claude", "--print"])
    assert spawned[:5] == [sys.executable, "-m", "hmz", "internal", "cred"]
    assert any(f"--map={home}/.claude/.credentials.json=" in one for one in spawned), (
        spawned
    )
