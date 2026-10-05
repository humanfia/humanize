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
from pathlib import Path
from typing import ClassVar

from .opencode import OpencodeAgent, OpencodeAgentConfig, OpencodeSession
from .preload import preloaded

#: What a gateway way calls the provider it configures, the variable that says where it is --
#: which is how a turn knows its account is one -- and the one its model is named by. All three
#: are the gateway ways' own, in :data:`hmz.coganchor.backends.PROFILES`.
_GATEWAY, _URL, _MODEL = "humanize", "MIMO_GATEWAY_URL", "MIMO_GATEWAY_MODEL"


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

        And one thing opencode does not do: mimocode reads Claude Code's `~/.claude.json` as it
        starts, for the MCP servers configured there, and dies where it may not -- which a fence
        that keeps the home from being read is. That file is another CLI's, secrets and all, so
        it is not granted; mimocode is told to leave Claude Code's settings alone instead, which
        where the fence would have refused it reading them is nothing it could have had.

        And under a gateway account, the model this turn is of as the one its provider lists:
        see :meth:`_gateway`.
        """
        environment = preloaded(self._agent, super()._environment())
        fence = self._agent.config.fence
        if fence is not None and not fence.allows(Path.home() / ".claude.json"):
            environment["MIMOCODE_DISABLE_CLAUDE_CODE"] = "1"
        if served := self._gateway():
            environment[_MODEL] = served
        return environment

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Opencode's turn, with a gateway account's model spelled as mimocode is asked for it.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command and the prompt to write to it.
        """
        argv, stdin = super()._turn(prompt)
        if served := self._gateway():
            argv[argv.index("--model") + 1] = f"{_GATEWAY}/{served}"
        return argv, stdin

    def _gateway(self) -> str:
        """The id a gateway account's endpoint serves this turn's model under, if it is one.

        A gateway way configures one provider, `humanize`, with one model under it, named by a
        variable: mimocode refuses a model its provider does not list, and what the endpoint
        lists is far more than the one the account was made with. So the variable is set to
        this turn's model, which makes every id the endpoint serves one a turn may name. Either
        spelling of it is taken -- the bare id the endpoint lists, which is what the catalogue
        of such an account is, and `humanize/<id>`, which is what mimocode lists it as -- and
        nothing past the first `/` is read as a provider, an endpoint's own ids having those.
        Every model of such an account is the gateway's, then, even one spelled like a
        provider of mimocode's own: `anthropic/claude-x` is an id a router serves, and the
        account is the gateway rather than whatever else the CLI could reach.

        Returns:
          The id, or "" for an account that is not a gateway's, whose model is its own to
          spell.
        """
        if _URL not in self._agent.environment():
            return ""
        return self._agent.config.model.removeprefix(f"{_GATEWAY}/")

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

    configured: ClassVar[str] = "mimocode"

    def new(self, cwd: str | os.PathLike[str] | None = None) -> MimoCodeSession:
        """Opens a new mimocode session, in the directory it is given or in this one."""
        return MimoCodeSession(self, cwd)
