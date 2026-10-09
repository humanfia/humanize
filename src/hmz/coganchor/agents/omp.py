"""omp: Oh My Pi, pi's fork, held open as pi is and spoken to in pi's protocol as omp spells it.

`omp --mode rpc` is pi's RPC mode carried on: one process for the session, a turn a `prompt`
written to its stdin, a word put in mid-turn a `steer`, and what the agent did the same
`message_update`s pi says it with. So what drives it is pi's driver, and what is here is where
the two part company -- most of a command line, and three things about the protocol:

- A turn ends on the `agent_end` that is terminal. There is no `agent_settled`: omp's own
  reference says so, and a reader waiting for one waits for ever.
- A session cannot be given its id up front -- there is no `--session-id` -- so the id is asked
  for, as `get_state`, ahead of the first prompt, and `--resume` takes it back after that.
- A `toolcall_start` names neither the call nor the tool. Both are on the message so far that
  comes with it, which pi stopped sending at 0.84.0 and omp still sends.

Here rather than as a second dialect in :mod:`hmz.coganchor.agents.pi` because it is a second
backend: it has its own home, its own models and its own place at a prompt, and a reader
looking for what drives `omp` should find a file called that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .config import AgentConfig
from .pi import PiAgent, PiSession

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from .event import Event

#: The command omp is installed as.
_COMMAND = "omp"

#: Each rung, in omp's own approval modes. omp has no sandbox, so nothing here keeps an edit
#: inside the workspace or a command off the network -- but it has a gate, and every tool it
#: runs, extensions' and MCP servers' included, says which tier of it it is: a read, a write,
#: or something it executes. `read-only` is the mode that asks before anything but a read, with
#: every one of those askings answered no (:meth:`OhMyPiSession._answer`), so what the agent
#: may do is what omp itself counts as looking. The other three rungs are one agent, the one
#: that is asked nothing: there is no sandbox to tell `workspace-write` from `auto` with, and a
#: turn waiting on an approval nobody is there to give is a flow that has stopped. The silence
#: above them says no mode at all, leaving omp wherever its own configuration leaves it.
_APPROVING = {
    "read-only": "always-ask",
    "workspace-write": "yolo",
    "auto": "yolo",
    "bypass": "yolo",
}

#: What omp offers on a tool it wants approved, in the order it offers them -- which is what
#: tells an approval from a question the agent or an extension has put to the person.
_APPROVAL = ("Approve", "Deny")

#: What the `get_state` asking a new process which session it opened is sent under, so that
#: its answer is told from one to a command somebody else sent.
_NAMING = "hmz-session"

#: The files omp declares providers of its own in, under its home, in the order it reads them.
_MODELS = ("models.yml", "models.yaml")


class OhMyPiSession(PiSession):
    """An omp conversation: pi's, opened and resumed as omp opens and resumes one."""

    def _command(self) -> list[str]:
        """Builds the ``omp --mode rpc`` that reads commands on stdin and says events on stdout.

        A session that has an id resumes it, and one forked from another forks it; one that
        has neither is opened fresh, and is named by what omp says it opened -- asked as its
        first prompt is written, which is the moment there is a process to ask.
        """
        config = self._agent.config
        argv = [
            _COMMAND,
            "--mode",
            "rpc",
            "--model",
            config.model,
            # Out of pi's ladder, which omp's is. An agent at no rung says nothing, and omp
            # leaves the model at its own thinking level.
            *(["--thinking", self.effort] if self.effort else []),
        ]
        if self._id is not None:
            argv += ["--resume", self._id]
        else:
            # Whatever the process before this one opened is not this one's: a turn that
            # never landed may have left one, and resuming it would resume a turn that never
            # happened.
            self._named = None
            if self._forked_from is not None:
                argv += ["--fork", self._forked_from]
        if mode := _APPROVING.get(config.permission):
            argv += ["--approval-mode", mode]
        return argv

    def _environment(self) -> Mapping[str, str]:
        """What a turn is run with, which is the provider's and nothing of pi's.

        Neither the compile cache nor the preload pi's driver puts in `NODE_OPTIONS`: omp
        reads neither, and what would read them is the programs a turn of it starts, which are
        the agent's tools rather than the agent.
        """
        return super(PiSession, self)._environment()

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one thing to say as pi's driver does, asking which session it is first.

        Asked once per process that has not said: ahead of the prompt that opens the session,
        since omp runs commands in the order they arrive and so answers this before the turn
        has done anything at all.
        """
        line = super()._write(text, ticket)
        if ticket or self.named is not None:
            return line
        return json.dumps({"type": "get_state", "id": _NAMING}) + "\n" + line

    def _event(self, said: dict[str, Any]) -> Iterator[Event]:
        """Reads the events omp spells its own way, and hands pi's driver the rest.

        Args:
          said: The event, as read.

        Yields:
          The turn's answer once omp has stopped, and whatever pi's driver makes of any other
          event.
        """
        match said.get("type"):
            case "response" if said.get("id") == _NAMING:
                data = said.get("data")
                if isinstance(data, dict) and (
                    named := cast("dict[str, Any]", data).get("sessionId")
                ):
                    self._named = str(named)
            case "agent_end":
                # Terminal unless it says it is not: retrying, compacting or answering a
                # reminder of its own is omp still at work on the turn, and `yielded` -- which
                # a release older than it does not send -- says the same thing.
                if (
                    said.get("isTerminal") is not False
                    and said.get("yielded") is not False
                ):
                    self._aborted.set()  # a run told to stop has, whatever comes after
                    yield self._answered()
            case "response" if (
                said.get("command") == "prompt"
                and cast("dict[str, Any]", said.get("data") or {}).get("agentInvoked")
                is False
            ):
                yield self._answered()  # finished where it was said: a command of omp's own
            case "prompt_result" if said.get("agentInvoked") is False:
                yield self._answered()  # the same, said once it had run
            case _:
                yield from super()._event(said)

    def _reaches(self, event: dict[str, Any]) -> Iterator[Event]:
        """Says what the agent reached for, naming the call off the message omp sends with it.

        Args:
          event: The `assistantMessageEvent`, as read.

        Yields:
          What pi's driver says of the call, which it can say as early as pi's does once the
          start names it.
        """
        if event.get("type") == "toolcall_start" and "toolName" not in event:
            content = cast("dict[str, Any]", event.get("partial") or {}).get("content")
            at = event.get("contentIndex")
            if isinstance(content, list) and isinstance(at, int):
                parts = cast("list[Any]", content)
                if 0 <= at < len(parts) and isinstance(parts[at], dict):
                    call = cast("dict[str, Any]", parts[at])
                    event = {
                        **event,
                        "id": call.get("id"),
                        "toolName": call.get("name"),
                    }
        yield from super()._reaches(event)

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers what omp stopped the turn to ask, refusing every approval at `read-only`.

        Args:
          said: The `extension_ui_request`, as read.
        """
        offered = tuple(cast("list[Any]", said.get("options") or []))
        if self._agent.config.permission == "read-only" and offered == _APPROVAL:
            denied = {"type": "extension_ui_response", "id": said.get("id")}
            self._send(json.dumps(denied | {"value": _APPROVAL[1]}) + "\n")
            return
        super()._answer(said)


@dataclass(frozen=True, kw_only=True)
class OhMyPiAgentConfig(AgentConfig):
    """What omp is configured with: the common model and effort, written as omp writes them.

    The model is `provider/id`, as pi's is. None of what pi's config adds: each of those is a
    flag of pi's that omp does not take.
    """


class OhMyPiAgent(PiAgent):
    """omp, driven over its RPC protocol so a turn can be talked to while it runs."""

    def _declared(self, home: Path) -> Any:
        """What this machine's omp declares of its own providers, read out of `models.yml`.

        Args:
          home: omp's home, as a turn will find it.

        Returns:
          The file, as read.

        Raises:
          OSError: If there is neither spelling of it, or it cannot be read.
          ValueError: If it is not YAML.
        """
        import yaml

        for name in _MODELS:
            try:
                text = (home / name).read_text(encoding="utf-8")
            except FileNotFoundError:
                continue
            try:
                return yaml.safe_load(text)
            except yaml.YAMLError as unread:
                raise ValueError(str(unread)) from unread
        raise FileNotFoundError(home / _MODELS[0])

    def new(self, cwd: str | os.PathLike[str] | None = None) -> OhMyPiSession:
        """Opens a new omp session, in the directory it is given or in this one."""
        return OhMyPiSession(self, cwd)
