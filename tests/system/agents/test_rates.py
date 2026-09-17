"""What a real turn of a real CLI says it spent, by kind.

The other half of this file is `tests/integration/agents/test_rates.py`, which holds the meter
itself -- what a reckoning is, what it adds up to, what a rate over a window comes to -- and
drives each backend's counting through a stand-in CLI written here. All of that is arithmetic
and a script on PATH, so CI runs it.

The two below take a turn of an actual model on an actual account, which is the one thing a
stand-in cannot settle: whether the kinds humanize reads are the kinds that CLI really emits,
under whichever spelling this release of it uses. That needs the CLI installed, an account
signed in, and tokens spent, so it is never CI's to run.
"""

from __future__ import annotations

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
)


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_claude_says_what_it_spent_by_kind_for_real() -> None:
    """The kinds are read off two spellings of the same usage, so a real turn settles both."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="low")
    ).new()
    (answered,) = [
        event
        for event in session.stream("Reply with exactly: OK")
        if event.kind == "result"
    ]

    assert "OK" in answered.text
    # What the turn states and what its messages said add up to the same spending.
    assert answered.spent.total == sum(answered.tokens.values())
    assert session.spent().total == answered.spent.total
    assert session.spent().output > 0
    assert session.rate(over=60).output > 0


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_codex_says_what_it_spent_by_kind_for_real() -> None:
    session = CodexAgent(CodexAgentConfig(model="gpt-5.5", effort="low")).new()
    (answered,) = [
        event
        for event in session.stream("Reply with exactly: OK")
        if event.kind == "result"
    ]

    assert "OK" in answered.text
    assert answered.spent.total == sum(answered.tokens.values())
    assert session.spent().input > 0
    assert session.spent().output > 0
