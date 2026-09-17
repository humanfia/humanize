"""A turn actually run as a named account, under a real ptrace supervisor.

The other half of this file is `tests/integration/agents/test_providers.py`, which reads the
seam: what an agent under a provider says its environment is, what it hushes, what command it
would spawn, and what it tells an anchor to answer. All of that is objects and argument lists in
this process, so CI runs it.

Everything below runs the turn instead. A provider's credentials reach a CLI by having the paths
it opens answered with somebody else's -- a seccomp filter and a `ptrace` supervisor doing the
answering -- so the thing under test is a kernel handing over a tracee, and there is no reading
it off a command line.

Which is why they are in this directory rather than in that one: the tier is the gate, and what
CI runs is chosen by it. `@traced` below is not that gate and never was -- it is a `skipif` on
whether this machine can supervise anything at all, so a container without `CAP_SYS_PTRACE`
would skip every one of these and read as green. A check that skips itself on every run looks
exactly like a check that passes, which is the failure the tiers are drawn against.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import providers
from hmz.coganchor.agents import AgentConfig
from tests.stubs import ShellAgent, ShellSession
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path


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


@traced
def test_a_provider_that_is_variables_is_what_the_turn_is_run_with(home: Path) -> None:
    """A key, an endpoint, an account on somebody's cloud: every CLI reads one as a variable."""
    providers.add(
        "claude",
        "gateway",
        way="gateway",
        env={
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="gateway"))

    assert agent.environment() == {
        "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
    }
    # The turn itself is run with them, on top of what it inherits.
    assert agent.new()('printf %s "$ANTHROPIC_BASE_URL"') == (
        "https://example.invalid/anthropic"
    )
    assert agent.new()('printf %s "$PATH"') == os.environ["PATH"]  # and keeps its own


@traced
@pytest.mark.timeout(120, method="thread")
def test_a_turn_under_a_provider_reads_that_providers_credentials(home: Path) -> None:
    """The whole errand: the CLI names its own path and is answered with the provider's."""
    provider = providers.add("claude", "mine", way="login")
    where = provider.at / "user" / ".claude.json"
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text('{"account": "the provider"}')
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    said = agent.new()('cat "$HOME/.claude.json"')

    assert json.loads(said) == {"account": "the provider"}
    # And what the machine itself is signed in as is untouched, both ways round.
    assert json.loads((home / ".claude.json").read_text()) == {
        "account": "the one at this machine"
    }


@traced
@pytest.mark.timeout(120, method="thread")
def test_what_a_turn_under_a_provider_writes_lands_in_that_provider(home: Path) -> None:
    """A token refreshed mid-run is written back where it was read from, which is the provider."""
    provider = providers.add("claude", "mine", way="login")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    assert agent.new()('printf refreshed > "$HOME/.claude/.credentials.json"; echo ok')

    assert (provider.at / "home" / ".credentials.json").read_text() == "refreshed"
    assert (
        home / ".claude" / ".credentials.json"
    ).read_text() == '{"token": "this machine"}'


@traced
@pytest.mark.timeout(180, method="thread")
def test_two_agents_of_one_cli_under_two_providers_are_two_accounts(home: Path) -> None:
    """The flame-chase case: one flow, one CLI, two accounts, at the same time."""
    for name in ("first", "second"):
        provider = providers.add("claude", name, way="login")
        where = provider.at / "user" / ".claude.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(json.dumps({"account": name}))
    agents = [
        _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider=name))
        for name in ("first", "second")
    ]

    said = [agent.new()('cat "$HOME/.claude.json"') for agent in agents]

    assert [json.loads(one)["account"] for one in said] == ["first", "second"]


@traced
@pytest.mark.timeout(180, method="thread")
def test_two_accounts_run_at_the_same_time_without_reading_each_others(
    home: Path,
) -> None:
    """At once rather than one after the other, which is how a flow would drive them."""
    import asyncio

    for name in ("first", "second"):
        provider = providers.add("claude", name, way="login")
        where = provider.at / "user" / ".claude.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(json.dumps({"account": name}))
    agents = [
        _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider=name))
        for name in ("first", "second")
    ]

    async def both() -> list[str]:
        return list(
            await asyncio.gather(
                *(
                    agent.aturn('sleep 0.2; cat "$HOME/.claude.json"')
                    for agent in agents
                )
            )
        )

    said = asyncio.run(both())

    assert [json.loads(one)["account"] for one in said] == ["first", "second"]


@traced
def test_a_key_left_lying_about_does_not_outrank_the_account_it_was_told(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These CLIs take a key from the environment over the one they were signed in with.

    So a turn under a provider is run without every variable its backend would read an
    account from -- an `ANTHROPIC_API_KEY` in somebody's shell profile would otherwise be the
    account the turn was taken as, and the bill the first thing to say so.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    providers.add("claude", "mine", way="login")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    assert "ANTHROPIC_API_KEY" in agent.hushed()
    assert (
        agent.new()('printf "[%s]" "$ANTHROPIC_API_KEY$CLAUDE_CODE_USE_BEDROCK"')
        == "[]"
    )
    # And what is none of the account's business is left exactly as it was found.
    assert agent.new()('printf %s "$PATH"') == os.environ["PATH"]


@traced
def test_a_provider_keeps_the_variables_it_set_itself(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    providers.add(
        "claude", "gateway", way="gateway", env={"ANTHROPIC_API_KEY": "its own"}
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="gateway"))

    assert "ANTHROPIC_API_KEY" not in agent.hushed()
    assert agent.new()('printf %s "$ANTHROPIC_API_KEY"') == "its own"
