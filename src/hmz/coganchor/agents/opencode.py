"""opencode: one ``opencode run`` per turn, reading the JSON it answers in.

Its command line says everything an agent is configured with -- the model, the variant that is
its reasoning effort, the session to carry on, the directory to work in -- so a turn is one run
of it rather than a conversation held open on a server. What it writes on stdout with
``--format json`` is a protocol rather than the agent talking: the events of the turn, one per
line, which is where the session it opened, what it reached for and what it spent all are.

mimocode is the same program under another name, and is driven from here: what differs is what
the command is called and which of its own variables it takes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig
from .event import Event, Failed, Usage

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: What each kind of event reads as. A step beginning or ending is the turn's own plumbing,
#: and is read for what it cost rather than shown. `reasoning` arrives only where the turn was
#: asked for it: a bare ``opencode run`` streams the thinking nowhere, and `--thinking` is what
#: turns those parts into events. Which changes what a turn *shows* and nothing about what it
#: *counts* -- the reasoning tokens are in every step's own totals either way.
_SAYS = {"text": "text", "reasoning": "reasoning"}

#: What the tokens of one step are called, and what each of them is here. `reasoning` is
#: counted beside the output rather than inside it, so it is a kind of its own; the cache
#: counts arrive under `cache` rather than beside these.
_COUNTED = ("input", "output", "reasoning")
_CACHED = ("read", "write")

#: What each rung of the ladder is, said the way opencode takes it: a permission apiece for
#: editing a file, running a command and reaching the web, each `allow`, `ask` or `deny`. A
#: `deny` here is the tool not being offered at all, which is what makes `read-only` real; there
#: is no sandbox, so `workspace-write` is the same agent with nothing outside the workspace to reach
#: for, and `auto` and `bypass` are that agent with the reaching allowed.
#:
#: `reach` is not a permission of the CLI's but the one answer every web-reaching tool of it
#: gets, since more than one of them is a way out and a rung that let one through while holding
#: the others would be a rung that means nothing. :attr:`OpencodeSession.reaches` names them,
#: and mimocode names one more than opencode does.
#:
#: `ask` is never emitted. It is answerable now -- a headless run answers one itself, `once`
#: where it was told nobody is there to and `reject` where it was not -- but those are the two
#: answers the ends of this table already give, so a rung written as `ask` would say nothing a
#: rung written outright does not.
_PERMITTED = {
    "read-only": {"edit": "deny", "bash": "deny", "reach": "allow"},
    "workspace-write": {"edit": "allow", "bash": "allow", "reach": "deny"},
    "auto": {"edit": "allow", "bash": "allow", "reach": "allow"},
    "bypass": {"edit": "allow", "bash": "allow", "reach": "allow"},
}

#: The rungs that withhold nothing, and so the only ones a turn run without a table of its own
#: can honestly be at: what decides then is whatever the person at this machine has configured,
#: which a narrower rung would have had to overrule and has no way left to.
_UNNARROWED = ("auto", "bypass")


class OpencodeSession(CommandSessionBase):
    """An opencode conversation, resumed by the id the first turn's events name it with.

    The id is minted by opencode as the session opens, so it is read back out of the turn that
    opened it and given to every turn after -- which is what keeps the conversation one
    conversation rather than a new one per run.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: The command this backend is installed as, and the variable it is told what the agent
    #: may do in -- the two things mimocode differs by on the way in.
    command: ClassVar[str] = "opencode"
    permits: ClassVar[str] = "OPENCODE_PERMISSION"

    #: Which permissions of that table are the ways out of the workspace, and so the ones
    #: `web_search` is said in. Two here -- the tool that fetches a page it is given, and the
    #: one that goes looking for pages it is not -- because either left allowed is an agent
    #: still reaching the web, and a switch that took only the first away would be one that
    #: lies. mimocode ships a third and says so on its own class.
    reaches: ClassVar[tuple[str, ...]] = ("webfetch", "websearch")

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the agent has said so far in the turn now running, and what went wrong with
        #: it if anything did.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, added up as each step of it comes back, and
        #: which parts of it have already been shown -- a part is written once here, but a
        #: turn that saw it twice would show it twice.
        self._spent = 0
        self._costing = Usage()
        self._shown: set[str] = set()

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the ``opencode run`` one turn is, and hands it the prompt on stdin.

        On stdin rather than as an argument: a prompt is a paragraph and may open with a dash,
        neither of which belongs on a command line.

        Two of these flags are not a bare ``opencode run``'s and are nobody's to turn off.
        ``--format json`` is what makes the turn a protocol rather than a formatted page, and
        ``--dir`` is what puts it in the directory the flow opened this session at rather than
        wherever the process happens to be standing -- a driver without either is a driver with
        nothing to read and nowhere to read it from. Everything after the model and the variant
        is the agent's own to say, and says by default what the CLI would have done unasked.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command and the prompt to write to it.
        """
        config = self._agent.config
        self._said, self._failed, self._spent, self._shown = "", None, 0, set()
        self._costing = Usage()
        argv = [
            type(self).command,
            "run",
            "--format",
            "json",
            "--dir",
            self._workspace(),
            "--model",
            config.model,
            # The variant is this backend's rung, and an agent at none leaves it unsaid: a
            # provider with no variants takes the flag and ignores it, but one that has them
            # would read "" as a variant it does not serve.
            *(["--variant", self.effort] if self.effort else []),
        ]
        if named := str(getattr(config, "cli_agent", "")):
            argv += ["--agent", named]
        if getattr(config, "thinking", False):
            argv.append("--thinking")
        if getattr(config, "pure", False):
            argv.append("--pure")
        if self._id is not None:
            argv += ["--session", self._id]
        elif self._forked_from is not None:
            # `--fork` forks the session it is given and carries on in the fork, so this run
            # lands in a conversation of its own that starts out knowing what that one knew.
            argv += ["--session", self._forked_from, "--fork"]
        if getattr(config, "unattended", True):
            argv += self._unattended()
        return argv, prompt

    def _unattended(self) -> list[str]:
        """What tells this backend that nobody is there to answer it.

        A flow watches its agent rather than gating it, as humanize' own flows do, and a turn
        waiting on an approval nobody is there to give is a flow that has stopped. It answers
        yes to everything that is not refused outright, which is why the rung below is said as
        refusals: what the agent may not do is denied, and the flag is what carries the rest.

        What the flag is called is all this says. Whether a turn carries it at all is the
        agent's `unattended`, and a turn that does not gets the CLI's own answer instead --
        a headless run refuses what it is asked rather than waiting to be told.
        """
        return ["--auto"]

    def _environment(self) -> dict[str, str]:
        """What the agent may do, which this backend takes as a variable rather than a flag.

        Set for this turn and for nothing else, rather than written into the settings file:
        two agents of one flow may be allowed different things, and neither is a reason to
        change what the person who started the flow has configured.

        A table the flow asked not to have written is not written at all, and the turn runs at
        whatever that person's own configuration says. `permission_table` is where that is
        said, and the config refuses it off beside a rung or a web switch this was the only way
        of carrying.
        """
        config = self._agent.config
        if not getattr(config, "permission_table", True):
            return dict(super()._environment())
        rung = _PERMITTED.get(config.permission, _PERMITTED["bypass"])
        # A rung that already withholds the web is not asked twice: it and `web_search` say
        # the same thing here, and either of them saying it is enough.
        reaching = rung["reach"] if config.web_search else "deny"
        allowed = {"edit": rung["edit"], "bash": rung["bash"]}
        allowed |= dict.fromkeys(type(self).reaches, reaching)
        return {
            **super()._environment(),
            type(self).permits: json.dumps(allowed),
        }

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one event opencode wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is opencode's own log rather than the
            turn -- kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the odd plain line among the JSON
        part: dict[str, Any] = said.get("part") or {}
        kind = str(said.get("type") or "")
        if kind == "error":
            failed: dict[str, Any] = said.get("error") or {}
            self._failed = json.dumps(failed) if failed else "the turn failed"
        elif kind == "step_finish":
            # Told as the step lands rather than once the run is over, which is what a rate
            # read while the turn is still running is made of.
            counted = self._cost(cast("dict[str, Any]", part.get("tokens") or {}))
            self._spent += int(counted.total)
            self._costing = self._costing + counted
            self._spends(counted)
        elif kind == "tool_use":
            yield from self._tool(part)
        elif (says := _SAYS.get(kind)) is not None:
            words = str(part.get("text") or "")
            marked = str(part.get("id") or "")
            if not words.strip() or (marked and marked in self._shown):
                return  # a part already shown is not the agent saying it twice
            self._shown.add(marked)
            if says == "text":
                # The last thing it says is what the turn answers with; the reasoning on the
                # way there is shown and nothing more.
                self._said = words
            yield Event(kind=says, text=words)

    def _tool(self, part: dict[str, Any]) -> Iterator[Event]:
        """Reads one tool call, as the one line a row of a transcript has room for.

        Args:
          part: The `tool` part, as read.

        Yields:
          What it reached for and what with, once per call.
        """
        marked = str(part.get("id") or "")
        if marked and marked in self._shown:
            return
        self._shown.add(marked)
        state: dict[str, Any] = part.get("state") or {}
        called: dict[str, Any] = state.get("input") or {}
        about = str(state.get("title") or "") or next(
            (
                str(value)
                for value in called.values()
                if isinstance(value, str) and value.strip()
            ),
            "",
        )
        yield Event(
            kind="tool", text=f"{part.get('tool') or 'tool'} {about}".strip()[:120]
        )

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What one step of a turn cost, by the kind each token went on.

        Every kind of token counts: what a rate is measuring is the traffic, and a cache read
        crosses the wire like anything else. Reasoning is counted beside the output here
        rather than inside it, which is why it is a kind of its own.

        Args:
          counted: The step's `tokens`, as read.

        Returns:
          What that step spent.
        """
        cached: dict[str, Any] = counted.get("cache") or {}
        return Usage(
            {
                name: float(counted.get(name) or 0)
                for name in _COUNTED
                if counted.get(name)
            }
            | {
                f"cache_{name}": float(cached.get(name) or 0)
                for name in _CACHED
                if cached.get(name)
            }
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the events it wrote.

        Args:
          transcript: The whole of stdout, already read event by event.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. opencode leaves nonzero for the
            times it could not start at all and says everything else in its events, so a
            model that refused and a turn that said nothing whatever both come back as an
            exit of zero -- and a loop fed either as an answer would be running on it as the
            work of the turn.
        """
        said, failed, spent = self._said, self._failed, self._spent
        if failed is not None:
            raise Failed(1, [type(self).command], said, failed)
        if not transcript.strip():
            raise Failed(
                1, [type(self).command], "", f"{type(self).command} said nothing at all"
            )
        return Event(
            kind="result",
            text=said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session opencode opened, which every event of the turn names.

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
            if not isinstance(said, dict):
                continue
            if named := cast("dict[str, Any]", said).get("sessionID"):
                return str(named)
        raise ValueError(f"{type(self).command} named no session")


@dataclass(frozen=True, kw_only=True)
class OpencodeAgentConfig(AgentConfig):
    """What opencode is configured with: the common model and effort, and what it adds.

    The model is written as opencode writes it, `provider/id`, since a model here belongs to
    the provider that serves it and opencode is asked for the pair.

    The rest is the way in to what a turn would otherwise decide for itself. Every one of them
    defaults to what a bare ``opencode run`` does, so an agent that says none of them is that
    command with a protocol to read and a directory to read it in and nothing else added.

    Attributes:
      cli_agent: Which of the CLI's own agents a turn runs as, by name, or "" for the one it
        starts with. Its agents carry a prompt, a model and a tool list apiece, so this is the
        CLI's own way of saying what kind of turn this is. `cli_agent` rather than `agent`
        because an agent here is the thing being configured: what this names is one of the
        several the CLI ships under that word, and the two would otherwise read as each other.
        A name it does not know it warns about and runs the default for, which is a setting
        that quietly did nothing, so a name with a space in it -- the way one gets misspelled
        -- is refused here instead.
      thinking: Whether the turn says the thinking on the way to its answer. Off, as the CLI
        is: the reasoning parts become events only where `--thinking` asked for them. What the
        turn spent on reasoning is counted either way, being part of every step's own totals,
        so this buys the words and not the figure.
      pure: Whether the turn runs without the plugins installed around the CLI rather than in
        it. Off, as the CLI is, and on for a run that has to be answerable for what was in it:
        somebody else's plugin is somebody else's code inside the turn.
      unattended: Whether the turn carries the CLI's own auto-approve flag, which answers yes
        to everything the permission table has not refused outright. On, because a flow
        watches its agent rather than gating it and a turn waiting on an approval nobody is
        there to give is a flow that has stopped. Off, the CLI answers its own asks by
        refusing them, which is a turn held to what it was allowed up front.
      permission_table: Whether `permission` and `web_search` reach the CLI at all, as a table
        written for this turn in the variable it reads one from. On, and off for a turn that
        is to run under whatever the person at this machine has configured -- their table,
        with `unattended` still deciding what becomes of anything that table leaves to be
        asked about. Off leaves this backend no way of saying either of the two, so a rung
        that withholds anything and web search switched off are both refused beside it: a
        setting the CLI never hears is a setting that lies.
    """

    cli_agent: str = ""
    thinking: bool = False
    pure: bool = False
    unattended: bool = True
    permission_table: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if any(letter.isspace() for letter in self.cli_agent):
            raise ValueError(
                f"cli_agent must be one of the CLI's own agent names, "
                f"not {self.cli_agent!r}"
            )
        if not self.permission_table:
            unsayable = [
                said
                for said, narrowed in (
                    (
                        f"permission={self.permission!r}",
                        self.permission not in _UNNARROWED,
                    ),
                    ("web_search=False", not self.web_search),
                )
                if narrowed
            ]
            if unsayable:
                raise ValueError(
                    "permission_table=False withholds the only table this backend hears "
                    f"{' and '.join(unsayable)} in"
                )


class OpencodeAgent(AgentBase):
    """opencode, driven through its own command line, one run per turn."""

    #: What it counts, read off the same tables its driver reads a step's usage with. Every
    #: kind there is: opencode counts its reasoning beside the output rather than inside it,
    #: and says what a cache read and a cache write came to on their own. All five of them
    #: whether or not the turn was asked to say its thinking -- a step reports what it spent
    #: on reasoning either way, and `thinking` only decides whether the words come too.
    counts: ClassVar[frozenset[str]] = frozenset(_COUNTED) | {
        f"cache_{named}" for named in _CACHED
    }

    def new(self, cwd: str | os.PathLike[str] | None = None) -> OpencodeSession:
        """Opens a new opencode session, in the directory it is given or in this one."""
        return OpencodeSession(self, cwd)
