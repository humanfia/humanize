"""What the flow engine's tests are written with: role types, collections, and flowverses.

A helper rather than a test module, imported by path from any tier. The role types here are
the ones a flow author writes; a flowverse is written out under a test's own temporary
directory, one flow directory apiece.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, NotRequired

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

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = [
    "Agents",
    "Coder",
    "Envs",
    "Everything",
    "Pair",
    "Params",
    "Workspace",
    "flowverse",
]


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
