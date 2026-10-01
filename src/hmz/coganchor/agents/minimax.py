"""MiniMax Code: one run of `mcode exec` per turn, read as the JSON lines it answers in.

`mcode exec` is the whole of a turn without its interface: a prompt in, the Runtime its
terminal interface runs on taking the turn, and the answer out. Its command line says
everything an agent here is configured with -- which model, how hard it thinks, how much it
may do unasked, which session to carry on -- so a turn is one run of it, and the session it
opened is carried on with `--session` and the id it was given.

What `--output-format stream-json` writes is a protocol rather than the agent talking: a JSON
object a line, each stamped with the run, the session and the turn, and tagged by `type`. The
turn opens on `exec.started`, says what it does as `item.*` -- a message, a piece of reasoning,
a tool call -- and ends on `turn.completed` or `turn.failed` and then `exec.completed`, which
carries the whole result. The session's id is on every one of them, including the first, so
it is known before anything can go wrong. What the turn cost is on `turn.completed`, once, as
four figures: the input already net of what the cache answered, the output with the reasoning
inside it, and the cache read and written beside them -- the same reckoning as everywhere else
here. Nothing is said about tokens while a turn is running; the log it keeps is where the tally
reads them as they are spent.

How hard it thinks is `--effort`, and a model is asked for one only where its own table says
it takes one: MiniMax Code refuses a turn given a rung its model has not got rather than run it
at some other strength, so a rung this account's catalogue says the model lacks is refused here
before a turn is spent finding out.

Its permission ladder is three words on its command line, and none of them is read-only:
`smart`, where its own reviewer decides what is safe and anything it would have asked about
fails the turn, there being nobody at a headless run to ask; `full`, where nothing is asked;
and `off`, where nothing is even reviewed. It has no sandbox of its own that holds a turn to a
directory, so `workspace-write` is `full` held by a fence from outside, and `read-only` is a
rung it will not take -- a flow wanting one gets its agent run at `bypass` inside a fence that
writes nothing, which is the one read-only it can honestly be held to.

Nor can it be told to leave the web alone. Its `web_search` is not run here: the model asks for
it and MiniMax's own service answers, on the very hosts a turn cannot be taken without -- so a
proxy letting the model through lets the search through too, and nothing a driver owns takes
the tool away. A fence that cuts the network would be one it reaches the web around, so it is
refused, and the permission is to grant online ALL.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz.coganchor import models
from hmz.coganchor.backends import AUTO

from .base import AgentBase, CommandSessionBase
from .config import UNSAID, AgentConfig, Unfenced, Unserved
from .event import Event, Failed, Usage
from .hooks import EVERYWHERE, SUBAGENTS, Moment

if TYPE_CHECKING:
    from collections.abc import Iterator

#: What the CLI is installed as.
_COMMAND = "mcode"

#: What a turn is run at for each rung it takes, as `--permission`. `workspace-write` and
#: `bypass` are one agent here, since nothing of MiniMax Code's own stops a write at the edge of
#: the workspace: the fence around it is what does, and `full` is the rung that leaves the fence
#: to do it rather than failing a turn on a question nobody is there to answer. `auto` is its
#: own reviewer, `smart`, which is what it runs at when it is told nothing -- and the silence is
#: no flag at all, leaving the turn wherever `mcode exec` itself would have put it.
_PERMITTED = {
    "workspace-write": ("--permission", "full"),
    "auto": ("--permission", "smart"),
    "bypass": ("--permission", "full"),
    UNSAID: (),
}

#: The tool it starts an agent of its own with, by the name its stream calls it. A turn that
#: reaches for it is a turn with an agent under it, which is worth showing as that.
_SUBAGENTS = ("task",)

#: How much of a tool call fits on a row of a transcript.
_ROOM = 120

#: What each kind of token is called on the `usage` a turn ends on. The input is already net of
#: the cache, so these are four figures which together are the traffic; the reasoning is inside
#: the output, as it is on every answer the model gave.
_KINDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadTokens",
    "cache_write": "cacheWriteTokens",
}

#: The status a tool call is stated at once it has finished, as the CLI numbers them: `2` for
#: one that succeeded and `3` for one that failed. The earlier ones are the call being written,
#: queued and running.
_DONE = (2, 3)


def _about(given: object) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      given: The tool call's input, as MiniMax Code stated it.

    Returns:
      The first thing in it that is words -- the command, the path, the description -- or "".
    """
    if not isinstance(given, dict):
        return ""
    return next(
        (
            str(value)
            for value in cast("dict[str, Any]", given).values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )


def _offered(model: str, account: str) -> tuple[str, ...] | None:
    """The rungs one model is offered at on this account, as its catalogue last said.

    Args:
      model: The model, as `provider/id`.
      account: The account, by the name its provider was made under, or "" for the CLI as
        whoever is at this machine already runs it.

    Returns:
      Its rungs, hardest first, and None for a model the catalogue says nothing about -- one
      nobody has asked this account about yet, or one kept where it cannot be read -- which is
      a turn MiniMax Code answers for itself rather than one to refuse here.
    """
    try:
        listed = models.offered(_COMMAND, account)
    except (OSError, ValueError):
        return None
    return next((one.efforts for one in listed if one.name == model), None)


def taken(model: str, effort: str, account: str) -> None:
    """Refuses a rung this account's catalogue says the model has not got.

    Args:
      model: The model, as `provider/id`.
      effort: The rung, or "" for none.
      account: The account the turn runs as.

    Raises:
      Unserved: If the catalogue lists the model and not at that rung. A model listed at no
        rung at all is one MiniMax Code refuses any `--effort` for, which is most of its own.
    """
    if not effort or effort == AUTO or not model:
        return
    rungs = _offered(model, account)
    if rungs is None or effort in rungs:
        return
    runs = (
        ", ".join(rungs) if rungs else "at no rung at all: its effort is written `auto`"
    )
    raise Unserved(f"{_COMMAND} runs {model} {runs}, not at {effort!r}")


class MiniMaxCodeSession(CommandSessionBase):
    """A MiniMax Code session, carried on by the id its first turn was given.

    The id is minted as `mcode exec` opens the session and stated on the first line it writes,
    so it is read back out of the turn that opened it and handed to every turn after.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--output-schema` holds the answer to a shape, and fails the turn where it does not
    #: fit, rather than asking the model nicely in the prompt.
    shapes: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The id the turn now opening this session was given, stated on the first line it
        #: writes and taken as the session's own once that turn has landed.
        self._named: str | None = None
        #: What the agent has said so far in the turn now running, and what went wrong with it
        #: if anything did. Each message is stated whole once it is done.
        self._said: list[str] = []
        self._failed: str | None = None
        #: The answer as a shape, where one was asked for: the result carries it parsed, and
        #: it is what the turn answers with rather than the words it came in.
        self._shaped: str | None = None
        #: Which tool calls have been shown, a call being stated at every status it passes
        #: through and a row per status being a transcript of statuses.
        self._shown: set[str] = set()
        #: What the turn now running has cost, and which model it says it ran on. Stated once,
        #: on the line the turn ends on.
        self._spent = 0
        self._costing = Usage()
        self._ran = ""

    @property
    def named(self) -> str | None:
        """What MiniMax Code calls this session, which the first line of its first turn says."""
        return self._id or self._named

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `mcode exec` one turn is.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and the prompt to write to its stdin: `--input -` reads it from
          there, which keeps a prompt that opens with a dash a prompt and one longer than a
          command line may be a prompt at all.
        """
        self._said, self._failed, self._shaped, self._shown = [], None, None, set()
        self._spent, self._costing, self._ran = 0, Usage(), ""
        configured = self._agent.config
        taken(configured.model, self.effort, self._agent.node().name)
        argv = [
            _COMMAND,
            "exec",
            "--output-format",
            "stream-json",
            "--input",
            "-",
            # The workspace is a session's rather than a run's, and a session carried on is
            # refused one it was not opened in -- so it is said, not left to the directory
            # the command happens to start in.
            "--cwd",
            self.cwd,
            *_PERMITTED[configured.permission],
        ]
        if configured.model:
            argv += ["--model", configured.model]
        if self.effort:
            argv += ["--effort", self.effort]
        if (schema := self._shaping) is not None:
            # Held closed and with every property required, as the strict structured output
            # it asks its models for has to be.
            from .codex import strict

            argv += [
                "--output-schema",
                json.dumps(strict(schema.model_json_schema())),
            ]
        if self._id is not None:
            argv += ["--session", self._id]
        return argv, prompt

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line `mcode exec` wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is where it says why a run failed --
            kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            loaded: object = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the protocol is JSON and nothing else
        if not isinstance(loaded, dict):
            return
        said = cast("dict[str, Any]", loaded)
        kind = str(said.get("type") or "")
        if kind == "exec.started" and said.get("sessionId"):
            # Noted, not taken: this is the first line out, said before anything can go
            # wrong, and a session is only opened by a turn that lands in it.
            self._named = str(said["sessionId"])
        elif kind in ("item.started", "item.updated", "item.completed"):
            item = cast("dict[str, Any]", said.get("item") or {})
            yield from self._item(item, done=kind == "item.completed")
        elif kind == "turn.completed":
            self._counts(cast("dict[str, Any]", said.get("usage") or {}))
            ran = cast("dict[str, Any]", said.get("model") or {})
            if ran.get("providerId") and ran.get("modelId"):
                self._ran = f"{ran['providerId']}/{ran['modelId']}"
        elif kind == "turn.failed":
            error_ = cast("dict[str, Any]", said.get("error") or {})
            self._failed = str(error_.get("message") or said.get("status") or "failed")
        elif kind == "exec.completed":
            result = cast("dict[str, Any]", said.get("result") or {})
            if result.get("status") != "succeeded":
                error_ = cast("dict[str, Any]", result.get("error") or {})
                self._failed = self._failed or str(
                    error_.get("message") or result.get("status") or "failed"
                )
            elif (output := result.get("output")) is not None and self._shaping:
                # A shape, parsed already: what the turn answers with is the object, and
                # the words it was written in are the same object as text.
                self._shaped = output if isinstance(output, str) else json.dumps(output)

    def _item(self, item: dict[str, Any], *, done: bool) -> Iterator[Event]:
        """One thing a turn did, said once and whole.

        A message and a piece of reasoning are stated a piece at a time as they are written
        and then whole when they are done, so only the whole is said: a watcher is told
        utterances, not the fragments they arrived in. A tool call is stated at each status
        it passes through, and is said once, as soon as what it was called with is known.

        Args:
          item: The item, as stated.
          done: Whether this is the line saying it is finished.

        Yields:
          What it comes to, which is nothing for a statement that says nothing new.
        """
        kind = item.get("type")
        if kind in ("agent_message", "reasoning"):
            words = str(item.get("content") or "")
            if not done or not words.strip():
                return
            if kind == "agent_message":
                self._said.append(words)
                yield Event(kind="text", text=words)
            else:
                yield Event(kind="reasoning", text=words)
            return
        if kind != "tool_call":
            return
        call = cast("dict[str, Any]", item.get("toolCall") or {})
        marked = str(call.get("id") or item.get("id") or "")
        named = str(call.get("name") or "tool")
        about = _about(call.get("input"))
        ending = done or call.get("status") in _DONE
        if marked not in self._shown and ("input" in call or ending):
            self._shown.add(marked)
            if named.lower() in _SUBAGENTS:
                # A fleet of its own rather than another tool: what is under this turn is
                # agents, and whatever is watching draws them as agents.
                yield Event(
                    kind="subagent",
                    text=f"{named} {about}".strip()[:_ROOM],
                    whose=marked,
                )
            else:
                yield Event(kind="tool", text=f"{named} {about}".strip()[:_ROOM])
        if done and named.lower() in _SUBAGENTS:
            yield Event(
                kind="subagent-ends",
                text=f"{named} {about}".strip()[:_ROOM],
                whose=marked,
            )

    def _counts(self, usage: dict[str, Any]) -> None:
        """Takes what the turn cost, off the line it ends on.

        Args:
          usage: The `usage` object, as read, which is empty for a turn whose model said
            nothing about what it spent.
        """
        counted = Usage(
            {
                kind: float(usage.get(named) or 0)
                for kind, named in _KINDS.items()
                if usage.get(named)
            }
        )
        if not counted.total:
            return
        self._spent += int(counted.total)
        self._costing = self._costing + counted
        self._spends(counted)

    def _result(self, transcript: str) -> Event:
        """The turn's answer, out of the lines it wrote.

        Args:
          transcript: The whole of stdout, already read line by line.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. It says so on the lines it ends
            on as well as in its exit status, and a loop fed that as an answer would be
            running on it as the work of the turn.
        """
        said = "".join(self._said) if self._shaped is None else self._shaped
        if self._failed is not None:
            raise Failed(1, [_COMMAND], said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        model = self._ran or self._agent.config.model
        return Event(
            kind="result",
            text=said.strip(),
            tokens={model: self._spent} if self._spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session `mcode exec` opened, which every line it wrote names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The session's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            try:
                said: object = json.loads(line)
            except ValueError:
                continue
            if isinstance(said, dict) and (
                named := cast("dict[str, Any]", said).get("sessionId")
            ):
                return str(named)
        raise ValueError(f"{_COMMAND} named no session")


@dataclass(frozen=True, kw_only=True)
class MiniMaxCodeAgentConfig(AgentConfig):
    """What MiniMax Code is configured with: the common settings, and nothing of its own.

    The model is written as MiniMax Code writes it, `provider/id` -- `minimax/MiniMax-M3` for
    its own, `custom_provider:NAME/ID` for one added to it -- and left empty for whichever model
    its configuration makes the default. The effort is a rung its catalogue lists for that
    model, or `auto` for the many that take none.
    """


class MiniMaxCodeAgent(AgentBase):
    """MiniMax Code, driven through its own command line, one run per turn."""

    #: Three of the four: it has no rung that changes nothing, so `read-only` is held by a
    #: fence around it rather than said to it. See the module.
    rungs: ClassVar[tuple[str, ...]] = ("workspace-write", "auto", "bypass")

    #: What the `usage` on the line a turn ends on counts: the input, the output, and the cache
    #: read and written to -- four figures, the input already net of the other two.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    #: Every moment a turn passes through, and the two about a fleet: its stream says when a
    #: turn starts an agent of its own and when that one has come back.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | SUBAGENTS

    def _serves(self, config: AgentConfig) -> None:
        """Refuses a config this backend cannot express, this account's catalogue too.

        Args:
          config: What the agent is to run at.

        Raises:
          Unserved: For what the base class refuses, and for a rung the catalogue this
            account last gave says the model has not got.
        """
        super()._serves(config)
        taken(config.model, config.effort, config.provider)

    def _fences(self, config: AgentConfig) -> None:
        """Refuses a fence as the base class does, and every one that cuts the network.

        Asked of the fence as it was written, because the hosts a cut network still lets
        through are where its web search runs: see the module.

        Args:
          config: What the agent is to run at.

        Raises:
          Unfenced: If the base class refuses it, or if it cuts the network.
        """
        super()._fences(config)
        if config.fence is not None and not config.fence.online:
            raise Unfenced(
                f"{_COMMAND}: this permission cuts the network, and {_COMMAND}'s web search "
                "runs on MiniMax's own service, through the same hosts as its model, where "
                "nothing here can take it away; grant it online ALL to use "
                f"{_COMMAND}"
            )

    def _keeping_swaps(self) -> tuple[tuple[str, str], ...]:
        """Where its sessions are kept, and where a fenced turn takes the lock beside its home.

        MiniMax Code locks its whole data directory as it starts, by making a directory of the
        same name with `.lock` on the end -- beside the home rather than inside it, which is a
        directory of the user's home and not one a fence lets be written unless the whole home
        may be. Landlock cannot grant one name inside a directory without granting the
        directory, so the lock is answered by a supervisor from beside where this agent's
        sessions are kept, which every fence of it lets be written: every fenced turn of it
        takes the same lock. So too where no session is kept -- `HUMANIZE_SESSIONS=off` --
        since the directory is made before a fenced turn is spawned whether or not a session
        is kept in it, and the lock is then all that is ever in it, the CLI taking it away
        again as it exits.

        Returns:
          The kept sessions' pairs, and for a fenced turn the lock's under both spellings of
          the home where it is reached through a link -- unless the turn is run here, keeps
          no session, and this machine cannot supervise one, where it is left to the CLI.
        """
        kept = super()._keeping_swaps()
        fence = self._config.fence
        if fence is None or fence.open:
            return kept
        from hmz.coganchor.backends import named
        from hmz.coganchor.providers.redirect import supervises

        if not kept and self._config.machine is None and not supervises():
            return kept
        profile = named(self.backend)
        assert profile is not None  # noqa: S101 -- mcode's profile is always there
        home = profile.directory(self._environ())
        instead = str(self.keeps / profile.name / f"{home.name}.lock")
        spellings = {str(home), os.path.realpath(home)}
        return (*kept, *((f"{one}.lock", instead) for one in sorted(spellings)))

    def new(self, cwd: str | os.PathLike[str] | None = None) -> MiniMaxCodeSession:
        """Opens a new MiniMax Code session, in the directory it is given or in this one."""
        return MiniMaxCodeSession(self, cwd)
