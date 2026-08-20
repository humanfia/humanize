"""mimocode: opencode under another name, and driven the same way.

The program is the same one, installed as `mimo` and serving models of its own, so what it is
driven by is opencode's driver with the command it answers to and the flags that differ. Here
rather than as a second name in `hmz.coganchor.agents.opencode` because it is a second backend: it
has its own home, its own models and its own place at a prompt, and a reader looking for what
drives `mimo` should find a file called that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os

from dataclasses import dataclass
from typing import ClassVar

from .opencode import OpencodeAgent, OpencodeAgentConfig, OpencodeSession
from .preload import preloaded


class MimoCodeSession(OpencodeSession):
    """A mimocode conversation, held and resumed exactly as an opencode one is."""

    command: ClassVar[str] = "mimo"
    permits: ClassVar[str] = "MIMOCODE_PERMISSION"

    #: Three ways out where opencode has two. It ships the same page-fetcher and web search,
    #: and a third tool that looks up the APIs and libraries a turn is working against -- which
    #: goes out over the same wire and is the same setting, so `web_search` off takes it too.
    reaches: ClassVar[tuple[str, ...]] = ("webfetch", "websearch", "codesearch")

    def _environment(self) -> dict[str, str]:
        """What opencode's driver runs a turn with, plus the preload where one is wanted.

        The one place the two part company: what mimocode is installed as is a Node script, where
        opencode is a single-file executable with its runtime compiled in and reads none of this.
        What that script starts is a binary of the same kind, so what is watched here is the
        launcher and the one spawn it makes -- which is the whole of what a runtime can be asked
        about a program that has none. :mod:`hmz.coganchor.agents.preload` decides whether one is
        wanted at all.
        """
        return preloaded(self._agent, super()._environment())

    def _unattended(self) -> list[str]:
        """What tells mimocode that nobody is there to answer it.

        Its own spelling of opencode's `--auto`: the same setting under the name this fork
        gives it, which is Claude Code's. Not to be confused with its top-level `--never-ask`,
        which is the other thing a session can be asked to stop stopping for and leaves the
        permissions exactly where they were.
        """
        return ["--dangerously-skip-permissions"]


@dataclass(frozen=True, kw_only=True)
class MimoCodeAgentConfig(OpencodeAgentConfig):
    """What mimocode is configured with: everything opencode is, being the same program.

    The model is written as mimocode writes it, `provider/id`, since a model here belongs to
    the provider that serves it and mimocode is asked for the pair.
    """


class MimoCodeAgent(OpencodeAgent):
    """mimocode, driven through its own command line, one run per turn."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> MimoCodeSession:
        """Opens a new mimocode session, in the directory it is given or in this one."""
        return MimoCodeSession(self, cwd)
