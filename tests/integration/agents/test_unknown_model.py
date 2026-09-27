"""A model Claude Code does not know, which it runs its own default in place of without a word.

A stand-in `claude` on `PATH` that does what the real one does with a `--model` it has never
heard of: says in its `system/init` that it is running its default instead, and answers the
turn all the same. What is checked is that the turn says so rather than landing quietly on a
model nobody chose.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from tests.agents import standins

if TYPE_CHECKING:
    from pathlib import Path

#: A `claude` whose own default is `claude-opus-5-5`, and which knows the haiku by its id.
_CLAUDE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
model = flags.get("--model", "")
known = model.startswith("claude-haiku-4-5")
running = model if known else "claude-opus-5-5"
print(json.dumps({"type": "system", "subtype": "init", "model": running,
                  "session_id": flags.get("--session-id") or flags["--resume"]}),
      flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""


@pytest.fixture(autouse=True)
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{standins.refusing('claude')}{_CLAUDE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")


def _notices(model: str) -> list[str]:
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model=model, effort="high")).new()
    said = [(one.kind, one.text) for one in session.stream("hi")]
    assert said[-1] == ("result", "hi")
    return [text for kind, text in said if kind == "notice"]


@pytest.mark.parametrize("model", ["claude-nonexistent-9", "claude-opus-5"])
def test_a_model_claude_does_not_know_is_said_to_be_running_as_its_default(
    model: str,
) -> None:
    """Its default read as the model only where it is that model, or that model dated."""
    (said,) = _notices(model)

    assert model in said
    assert "claude-opus-5-5" in said


@pytest.mark.parametrize(
    "model", ["claude-haiku-4-5", "claude-haiku-4-5-20251001", "opus", "opus[1m]"]
)
def test_a_model_claude_runs_by_that_name_or_resolves_says_nothing(model: str) -> None:
    """An id, the id it dates, or one of Claude's own aliases, which name the model run."""
    assert _notices(model) == []
