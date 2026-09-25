"""One run written down, and what is read back off it -- shared by four test modules.

An epic and an export are one subject read twice: a run opens a session, the session's log is
linked into the run's directory, and a bundle is that directory with every link followed. Both
subjects split across tiers -- what a stand-in agent can show, and what only a turn taken as a
named account can, which needs a kernel that will hand over a tracee -- so the flow that opens
one session, the stand-in whose logs humanize knows where to find, and the three readers below
are wanted by `tests/{integration,system}/runtime/test_{epics,export}.py`.

Written once here rather than four times there because a bundle's layout is the thing these
read: a copy of `held` in a file CI never runs is one that goes on asserting last year's tar
long after the other was fixed, and nothing would say so.

Here rather than in a conftest for the reason `tests/stubs.py` gives -- a conftest is a pytest
plugin rather than a module to import from -- and nothing below is a fixture, so there is
nothing a conftest would have added.
"""

from __future__ import annotations

import json
import tarfile
from typing import TYPE_CHECKING, Any

from hmz.runtime.exporting import MANIFEST
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: A flow that drives one agent, and says its session is called what the log is named after.
ONE = """
from hmz.coganchor.agents import AgentBase
from hmz._legacy_flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()("echo the-session")
"""


class ClaudeAgent(ShellAgent):
    """A stand-in for a backend humanize knows where the logs of are."""


def claude_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, said: str = "{}"
) -> Path:
    """Points Claude Code's home somewhere temporary, with one session already logged.

    Args:
      tmp_path: The test's own directory, which the home goes under.
      monkeypatch: What sets the variable, and puts it back afterwards.
      said: The one line the logged session holds.

    Returns:
      The log that session was written to.
    """
    where = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(where))
    log = where / "projects" / "-tmp-project" / "the-session.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(f"{said}\n", encoding="utf-8")
    return log


def held(at: Path) -> dict[str, str]:
    """Everything one bundle holds, by the name it is under with the epic's own stripped off."""
    inside: dict[str, str] = {}
    with tarfile.open(at) as opened:
        for one in opened.getmembers():
            handle = opened.extractfile(one)
            said = handle.read().decode("utf-8") if handle is not None else ""
            inside[one.name.partition("/")[2]] = said
    return inside


def manifest(at: Path) -> dict[str, Any]:
    """What one bundle says about itself."""
    return json.loads(held(at)[MANIFEST])
