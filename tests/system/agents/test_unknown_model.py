"""Claude Code handed a model it does not know, which it runs its own default in place of.

The integration tier's stand-in says what the real one says; this is the real one saying it, on
one turn of a word apiece. Only what a turn of it shows is checked: that a model nobody chose is
said to be running, and that one it knows is not.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of its own for the turn to work in, which is where it is run from."""
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed here")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _notices(model: str) -> list[str]:
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model=model, effort="low")).new()
    said = list(session.stream("Reply with exactly one word: hi"))
    assert said[-1].kind == "result", said
    return [one.text for one in said if one.kind == "notice"]


@pytest.mark.agent
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("workspace")
def test_a_model_claude_does_not_know_is_said_to_be_running_as_another() -> None:
    (said,) = _notices("claude-nonexistent-9")

    assert "claude-nonexistent-9" in said


@pytest.mark.agent
@pytest.mark.timeout(300)
@pytest.mark.usefixtures("workspace")
def test_a_model_claude_knows_says_nothing() -> None:
    assert _notices("claude-haiku-4-5-20251001") == []
