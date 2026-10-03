"""What the flow engine's tests are written with: role types, collections, and flowverses.

A helper rather than a test module, imported by path from any tier. The role types here are
the ones a flow author writes; a flowverse is written out under a test's own temporary
directory, one flow directory apiece. And the flows humanize ships, loaded from the package,
with what a resumable one of them kept read back out of its journal.
"""

from __future__ import annotations

import json
import textwrap
from typing import TYPE_CHECKING, Any, NotRequired

from hmz.flows import (
    Agent,
    AgentCollection,
    BashEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    GitWorktreeEnvMixin,
    GoalCommandAgentMixin,
    LocalEnv,
    Outworlder,
    ScratchDirEnvMixin,
    ShellEnvMixin,
    TemporaryClonedDirEnvMixin,
)
from hmz.runtime.flowing import BUILTIN_AT, resolved

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from types import ModuleType

    from hmz.runtime.flowing import FlowImpl

__all__ = [
    "SHIPPED",
    "Agents",
    "Coder",
    "Envs",
    "Everything",
    "Pair",
    "Params",
    "Workspace",
    "flowverse",
    "kept",
    "module",
    "shipped",
]

#: The flows humanize ships in the package, by the name each is offered under, alphabetically:
#: `chat`, and the loops beside it. Every list of humanize's own flows starts with these,
#: whatever has been fetched.
SHIPPED = (
    "chat",
    "continue_loop",
    "flame_chase",
    "goal",
    "ralph_loop",
    "rlar",
    "stateful_ralph",
)


class Coder(Agent, GoalCommandAgentMixin):
    """An agent that may run `/goal`."""


class Everything(
    Env,
    BashEnvMixin,
    FilesEnvMixin,
    GitWorktreeEnvMixin,
    TemporaryClonedDirEnvMixin,
    ScratchDirEnvMixin,
):
    """An environment that may do everything."""


class Workspace(LocalEnv, ShellEnvMixin, FilesEnvMixin):
    """The run's own directory, with commands and files."""


class Agents(AgentCollection):
    coder: Coder
    reviewer: Agent
    human: NotRequired[Outworlder]


class Pair(AgentCollection):
    a: Agent
    b: Agent


class Envs(EnvCollection):
    repo: Everything


class Params(FlowParams):
    depth: int = 0
    fanout: int = 1
    note: str = ""


def flowverse(at: Path, flows: Mapping[str, str | Mapping[str, str]]) -> Path:
    """Writes a directory of flows.

    Args:
      at: Where the flowverse goes; its `flows/` is made under it.
      flows: By flow name, the source of its `__init__.py`, or of every file in its
        directory by path relative to it.

    Returns:
      The `flows/` directory.
    """
    under = at / "flows"
    for name, said in flows.items():
        files = {"__init__.py": said} if isinstance(said, str) else said
        for path, source in files.items():
            where = under / name / path
            where.parent.mkdir(parents=True, exist_ok=True)
            where.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    return under


def shipped(name: str) -> FlowImpl:
    """One of the flows humanize ships, loaded from the package as `-f` would load it.

    Named by its path rather than by its name, so that no flow of anybody's own -- in the
    directory the suite runs in, or in the home directory of whoever runs it -- can stand in for
    the one being tested.

    Args:
      name: The flow's directory under `hmz/flows/builtin`.

    Returns:
      The flow.
    """
    return resolved(str(BUILTIN_AT / name))


def module(flow: FlowImpl) -> ModuleType:
    """The module a flow was loaded as, which is where its pauses and limits are set."""
    assert flow.home is not None
    return flow.home.module


def kept(journal: Path) -> dict[str, Any]:
    """What the flow at the top of a resumable run keeps, replayed from its journal.

    Args:
      journal: The run's journal.

    Returns:
      The state of the last call at the top of it, as the run that wrote it left it.
    """
    state: dict[str, Any] = {}
    top = None
    for line in journal.read_text().splitlines():
        record = json.loads(line)
        if record["t"] == "call" and record["parent"] == 0:
            top = record["id"]
        elif record["t"] == "set" and record["id"] == top:
            state[record["key"]] = record["value"]
        elif record["t"] == "del" and record["id"] == top:
            state.pop(record["key"], None)
    return state
