"""One run written down, and what is read back off it -- shared by the runtime's test modules.

An epic and an export are one subject read twice: a run opens a session, the session's log is
linked into the run's directory, and a bundle is that directory with every link followed. Both
subjects split across tiers -- what a stand-in CLI can show, and what only a turn taken as a
named account can, which needs a kernel that will hand over a tracee -- so the flow that opens
one session, the stand-in whose logs humanize knows where to find, and the readers below are
wanted by `tests/{integration,system}/runtime/test_{epics,export}.py`.

The stand-in is :data:`tests.flows.standins.CLAUDE` -- a `claude` on PATH that speaks the real
CLI's stream JSON, takes the session id it is handed, and keeps each conversation where Claude
Code keeps one, which is where humanize links it from.

Written once here rather than four times there because a bundle's layout is the thing these
read: a copy of `held` in a file CI never runs is one that goes on asserting last year's tar
long after the other was fixed, and nothing would say so.

Here rather than in a conftest for the reason `tests/stubs.py` gives -- a conftest is a pytest
plugin rather than a module to import from -- and nothing below is a fixture, so there is
nothing a conftest would have added.
"""

from __future__ import annotations

import json
import re
import tarfile
from typing import TYPE_CHECKING, Any

from hmz.runtime.exporting import MANIFEST
from tests.flows import standins

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: A flow that drives one agent, `builder`, through one session in the workspace.
ONE = '''"""Opens one session, and says the task in it."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def one(task, *, agents, envs, params, ctx):
    session = await agents["builder"].spawn(env=envs["here"])
    return await agents["builder"].run(task, session=session)
'''

#: What the stand-in is driven as, after `builder=`.
AGENT = "claude/claude-haiku-4-5:low"

#: What is run on it: a turn the stand-in answers with the word.
TASK = "Reply with the single word: done"


def standing_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the stand-in `claude` on PATH, with a home and a config directory of its own.

    Args:
      tmp_path: The test's own directory, which all of it goes under.
      monkeypatch: What sets the variables, and puts them back afterwards.

    Returns:
      Where it keeps its conversations: `projects/<the directory as a name>/<id>.jsonl`.
    """
    standins.install(tmp_path / "bin", "claude", standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return config


def logged(config: Path, workspace: Path, session: str) -> Path:
    """Where the stand-in keeps one conversation, as Claude Code keeps one."""
    return (
        config
        / "projects"
        / re.sub(r"[^a-zA-Z0-9]", "-", str(workspace))
        / (f"{session}.jsonl")
    )


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
