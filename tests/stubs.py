"""What more than one suite needs: the stand-in agents, and an anchor that stays here.

Four agents and their sessions, which is every stand-in this repo drives more than one test
file against. `ShellAgent` runs the prompt as a shell script, so each test spells what it is
standing in for; `ClaudeShellAgent` is that wearing Claude's name, which is what a provider is
looked up by; `EchoAgent` runs `cat`, which is a turn taken without anything installed. Each of
the last two is wanted by both halves of a file that split across tiers, and a stand-in written
down twice is a stand-in corrected in one copy.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from -- and because the agents, the epics and the
machines are three suites now, all of which drive a stand-in agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import AgentBase, CommandSessionBase
from hmz.runtime.epic import JOURNAL
from hmz.runtime.flowing import ENTRY
from hmz.runtime.flowing.skills import SKILLS

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping, Sequence
    from pathlib import Path


@dataclass(frozen=True, kw_only=True, slots=True)
class HereAnchor(AnchorConfig):
    """An anchor that runs the turn here after all, and keeps what it was handed.

    A real one would spawn coganchor, which needs a target and a machine to intercept on;
    what an agent owes it is the whole call the backend built, which is what this records --
    and, for an agent that is also run under a provider, the paths that session is to answer
    with others, since a process has one tracer and the anchor is the one that has it -- and
    the directory each session works in, which is the target's to hold.
    """

    seen: list[list[str]] = field(default_factory=list[list[str]])
    answered: list[list[tuple[str, str]]] = field(
        default_factory=list[list[tuple[str, str]]]
    )
    kept: list[list[str]] = field(default_factory=list[list[str]])
    into: list[str] = field(default_factory=list[str])

    def command(
        self,
        argv: Sequence[str],
        *,
        swaps: Sequence[tuple[str, str]] = (),
        private: Sequence[str] = (),
        chdir: str = "",
    ) -> list[str]:
        self.seen.append(list(argv))
        self.answered.append(list(swaps))
        self.kept.append(list(private))
        self.into.append(chdir)
        return list(argv)


class ShellSession(CommandSessionBase):
    """Runs the prompt as a shell script, so each test spells the agent it stands in for."""

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.reads = 0

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", prompt], None)

    def _read_session_id(self, transcript: str) -> str:
        self.reads += 1
        return transcript.strip()  # so a test can see exactly what the parser was given


class ShellAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> ShellSession:
        return ShellSession(self, cwd)


class ClaudeShellSession(ShellSession):
    """A shell session that says it is Claude's, so a provider's real paths are in play."""


class ClaudeShellAgent(ShellAgent):
    """A shell-backed agent wearing Claude's name, which is what a provider is looked up by.

    Which account a turn runs as is looked up by the backend the agent says it is, so a stub
    that answers `shell` is a stub no provider is ever found for. Wanted by both halves of the
    provider tests -- `tests/integration/agents/test_providers.py` reads the command line and
    the environment one of these would be spawned with, and `tests/system/agents/test_providers.py`
    actually takes the turn under a ptrace supervisor -- and so here rather than in either.
    """

    @property
    def backend(self) -> str:
        return "claude"

    def new(self, cwd: str | os.PathLike[str] | None = None) -> ClaudeShellSession:
        return ClaudeShellSession(self, cwd)


class EchoSession(CommandSessionBase):
    """Runs `cat`, echoing the prompt back on stdout -- the only fake on the stdin path.

    What the agent library's own tests are asked about: the object a backend hands out, rather
    than any CLI. `tests/unit/agents/test_agents.py` never lets one run at all, and
    `tests/integration/agents/test_agents.py` takes real turns on it through `cat` -- the one
    program a session can be driven against without anything being installed.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["cat"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "echo"


class EchoAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> EchoSession:
        return EchoSession(self, cwd)


def written(
    under: Path, name: str, source: str, skills: Mapping[str, str] | None = None
) -> Path:
    """Writes one flow out the way a flow is laid out: a directory, and what is in it.

    Args:
      under: Where the flows are kept -- a flowverse's `flows/`, a `.humanize/flows`, or a
        directory a test is pointing at outright.
      name: What the flow is called, which is the directory it goes in.
      source: The flow itself, which goes in its `__init__.py`.
      skills: The skills it brings, as one `SKILL.md` per skill by the name each goes under.

    Returns:
      The flow's own directory.
    """
    at = under / name
    at.mkdir(parents=True, exist_ok=True)
    (at / ENTRY).write_text(source)
    for called, said in (skills or {}).items():
        (at / SKILLS / called).mkdir(parents=True, exist_ok=True)
        (at / SKILLS / called / "SKILL.md").write_text(said)
    return at


def events(epic: Path) -> list[dict[str, Any]]:
    """Every line one record wrote, in the order it wrote them.

    An epic is a directory now -- the run's own record, a record per flow the run called, and
    a link per session any of them opened -- so what these suites want is one file inside it:
    the run's own where they are handed the directory, and the one they name where they name
    a record of a called flow.

    Args:
      epic: The epic's directory, or one record inside it.

    Returns:
      One record per line.
    """
    at = epic / JOURNAL if epic.is_dir() else epic
    return [json.loads(line) for line in at.read_text(encoding="utf-8").splitlines()]
