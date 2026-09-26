"""That a real Claude's turn ends once the subagents it started have, and not before.

Claude may send a subagent to the background and end its turn at once, saying it will wait.
Which a stand-in cannot show: whether this release of the CLI still has a background to send
one to, and whether what keeps it in the foreground still does. So a real turn is asked to
send one there, and what only that subagent could have read has to be in its answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

if TYPE_CHECKING:
    from pathlib import Path

#: What only the subagent reads, so that it being in the answer is the subagent having finished.
TOKEN = "PELICAN-4417"


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_claude_answers_with_what_the_subagent_it_started_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secret.txt").write_text(f"{TOKEN}\n")
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-sonnet-5", effort="low")
    ).new()

    said = session(
        "Do not read any file yourself. Start one subagent with the Agent tool, with "
        "run_in_background set to true if the tool takes it, and have it read secret.txt in "
        "the current directory and report its contents. Then answer with exactly what it "
        "reported."
    )

    assert TOKEN in said
