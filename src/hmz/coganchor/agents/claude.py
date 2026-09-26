"""Claude Code: one ``claude --print`` held open, spoken to in JSON a line at a time."""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Question, Usage
from .hooks import EVERYWHERE, SUBAGENTS, WAITING, Moment, about, arriving

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The tool Claude reaches for when it wants a person rather than a file. Its input is a list
#: of questions and its answer is that same input with the answers written into it, which is
#: what the permission prompt of an interactive Claude fills in.
_ASKS = "AskUserQuestion"

#: Noninteractive orchestration tools that can move work beyond the ordinary turn HMZ owns.
#: An agent whose goals are disabled remains able to use its ordinary permission-bound tools,
#: but cannot escape into a hidden goal, subagent, wakeup, or cron lifecycle.
#:
#: `Agent` is the name the subagent tool is registered under and `Task` is an alias of it, so
#: the name is the whole of what has to be said: a 2.1.272 given `--disallowedTools Agent`
#: reports neither spelling in the tool list of its `system/init`, which is the tool having
#: gone rather than one of its names. `Workflow` is the same escape arriving under a newer
#: one -- a script the model writes that Claude compiles and runs, forking agents of its own
#: in the background out of it -- so an agent refused the first is refused this too.
_CONTINUATION_TOOLS = (
    "Agent",
    "ScheduleWakeup",
    "CronCreate",
    "CronDelete",
    "CronList",
    "Workflow",
)

#: The tools that reach the web, by the names Claude calls them. Both, because searching and
#: fetching are one question here: an agent told not to search the web that went on reading
#: whatever page it liked would be answering the same question the other way.
#:
#: Withheld where the answer is no and nowhere else. Silence is not a no: an agent nobody said
#: anything about is one Claude ships these two to, so a rule written for it would be humanize
#: taking a tool away in the name of a question it was never asked.
_WEB_TOOLS = ("WebSearch", "WebFetch")

#: The tools Claude starts an agent of its own with. A turn that reaches for one of these has
#: agents under it rather than a tool running, which is worth saying as what it is: the id the
#: call was made under is what pairs the one that started with the result that ends it.
_FLEET = ("Task", "Agent")

#: What keeps a turn's work inside the turn. Claude sends a subagent or a command to the
#: background when it likes and ends the turn at once, saying it will wait for them -- and the
#: `result` that ends it is the turn humanize is holding over, so what the agent went on to
#: find would land after its flow had read the answer and moved on. Set, the same subagents
#: run, several to one message as before, and the turn ends when they have.
_FOREGROUND = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}

_ALLOWED_TOOLS_MAX = 32

#: How long a directory spelled as a name may be before Claude cuts it short and tells it
#: apart from others cut the same way by a hash of the whole.
_PROJECT_MAX = 200


def _project(where: str) -> str:
    """A directory as Claude names the folder its conversations there are kept in.

    Every character that is not an ASCII letter or digit is a dash -- counted as Claude counts
    them, in UTF-16 code units, so a character outside the basic plane is two -- and a name
    longer than :data:`_PROJECT_MAX` is cut there and given the base-36 of a 32-bit string
    hash of the whole path. Read off Claude Code 2.1.282, where it is the one function that
    names a project directory.

    Args:
      where: The directory, absolute.

    Returns:
      The folder's name.
    """
    units = where.encode("utf-16-le")
    codes = [
        int.from_bytes(units[at : at + 2], "little") for at in range(0, len(units), 2)
    ]
    said = "".join(
        chr(code) if chr(code).isascii() and chr(code).isalnum() else "-"
        for code in codes
    )
    if len(said) <= _PROJECT_MAX:
        return said
    hashed = 0
    for code in codes:
        hashed = (hashed * 31 + code) & 0xFFFFFFFF
    if hashed >= 1 << 31:
        hashed -= 1 << 32
    return f"{said[:_PROJECT_MAX]}-{_base36(abs(hashed))}"


def _base36(number: int) -> str:
    """A non-negative number written in base 36, as JavaScript's `toString(36)` writes it."""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    said = ""
    while True:
        number, digit = divmod(number, 36)
        said = digits[digit] + said
        if not number:
            return said


_ALLOWED_TOOL_RULE_MAX_CHARS = 4096

#: Reasons that leave an answer unfinished even when a broken intermediary labels the result
#: `success`. Claude normally keeps its own agent loop going for these rather than returning
#: them as the result of the whole turn.
_UNFINISHED = frozenset(
    {
        "max_tokens",
        "model_context_window_exceeded",
        "pause_turn",
        "tool_deferred",
        "tool_use",
    }
)

#: What Claude calls each rung of the ladder, said on its own command line. Three line up with
#: a mode of Claude's own: `plan` is an agent that works everything out and changes nothing,
#: `acceptEdits` is one that may change what it is working on without asking, and Claude's own
#: `auto` is one whose requests are answered for it. `bypass` is the fourth, and it is `manual`
#: -- the mode where Claude asks before every tool that would change something -- rather than
#: `bypassPermissions`, the mode that skips the asking. It is not that Claude cannot be told to
#: skip it: it is that an account can be given managed settings, and one carrying
#: `disableBypassPermissionsMode` does not refuse `--dangerously-skip-permissions` the way a
#: Codex given requirements refuses such a call -- it starts the turn at a mode where every
#: edit is declined and the turn ends successfully having changed nothing. So humanize takes
#: the asking rather than skipping it: `bypass` runs at `manual` and answers every request
#: itself, which is a mode every account allows and which means the same thing on each of them.
#:
#: Four rows and no fifth. The silence above the ladder is not a mode of Claude's to be looked
#: up here but the flag left off altogether, so this stays the four rungs and
#: :meth:`ClaudeCodeSession._command` says `--permission-mode` only where there is a rung --
#: the way it says `--effort` only where there is an effort. A row spelled "" would be a flag
#: carrying nothing, which is a mode named badly rather than a mode unasked for.
_PERMITTED = {
    "read-only": "plan",
    "workspace-write": "acceptEdits",
    "auto": "auto",
    "bypass": "manual",
}

#: What each kind of token is called on the total Claude states at the end of a turn, and what
#: it is called on the message each request answered with. The same kinds either way, under
#: the two spellings Claude uses for them.
_KINDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
}
_AS_IT_GOES = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}


@dataclass(slots=True)
class _Reaching:
    """A tool call the model is still writing the arguments of.

    Attributes:
      marked: Claude's own id for the call, which is what pairs an agent this one started
        with the result that ends it.
      named: What the tool is called, which Claude says in the first fragment of all.
      arriving: What of its arguments has come in.
      said: Whether the row has gone out, so that the fragments after it do not send it again.
    """

    marked: str
    named: str
    arriving: str = ""
    said: bool = False


def _result_failure(said: dict[str, Any]) -> str | None:
    """Explains why a Claude result did not finish its turn, or says that it did.

    A turn held to a shape ends the one way that otherwise reads as unfinished: the last
    thing the model did was call `StructuredOutput`, so the result says `stop_reason:
    tool_use` -- and says the object beside it, which is the answer. So a result carrying
    one is a turn that finished, however it stopped.
    """
    reason: str | None = None
    shaped = said.get("structured_output") is not None
    if said.get("is_error"):
        reason = "the turn failed"
    elif (subtype := said.get("subtype")) not in (None, "success"):
        reason = f"Claude ended the turn with {subtype}"
    elif (terminal := said.get("terminal_reason")) not in (None, "completed"):
        reason = f"Claude ended the turn with {terminal}"
    elif not shaped and (stopped := said.get("stop_reason")) in _UNFINISHED:
        reason = f"Claude stopped with {stopped} before completing the turn"
    if reason is None:
        return None

    if result := said.get("result"):
        return str(result)
    errors = cast("list[Any]", said.get("errors") or [])
    if errors:
        return "; ".join(str(error) for error in errors)
    return reason


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeAgentConfig(AgentConfig):
    """The common settings, plus what this CLI takes that humanize has no word for.

    Everything else on Claude's command line is left at what `claude` itself does when it is
    passed nothing, so an agent nobody has configured takes its turn as the bare CLI would
    take it. A few of those omissions are chosen rather than merely unwritten, and are worth
    saying so that nobody adds them back as an obvious improvement. `--fallback-model` would
    have the CLI answer quietly on another model when the one asked for is overloaded, and
    humanize already falls back by naming the whole place a turn moves to -- both at once is
    a turn that ran somewhere `agent.spec` does not say. `--max-budget-usd` counts dollars
    over the process, and this driver ends the process and resumes the conversation whenever
    the effort, the hook table or the offered callbacks move, so a cap spelled that way would
    start again in the middle of a session; what a turn may spend is :class:`Budget`, which is
    measured over the turn. `--no-session-persistence` would take away the resume and the fork
    this backend is written down as having, `--disable-slash-commands` would take away
    `/goal`, which is what :meth:`ClaudeCodeSession._pursue` runs on, and
    `--strict-mcp-config` would take the MCP servers of the person at this machine away for
    the length of a flow, which is not a flow's to do.

    Attributes:
      allowed_tools: Exact `--allowedTools` rules, in Claude's own spelling, for a bounded
        unattended flow. Empty for an agent held to nothing beyond what its permission rung
        says, which is the turn the CLI takes when it is passed no such flag.
      partial_messages: Whether a turn says what it is reaching for while the arguments are
        still being written, which is `--include-partial-messages`. On, and the one thing
        this driver asks of the CLI that the CLI does not do by itself: without it a tool call
        is announced only once the whole of what it was called with has arrived, and for a
        `Write` that is the file -- a minute of silence on a large edit, which reads from
        outside as a turn that has hung. Off is the flow's to choose, and the turn then says
        each reach once and whole, the way every backend with no such flag says it.
        `narrate` is the name a flow asks for it under before it is handed an agent.
    """

    allowed_tools: tuple[str, ...] = ()
    partial_messages: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            len(self.allowed_tools) > _ALLOWED_TOOLS_MAX
            or self.allowed_tools != tuple(sorted(set(self.allowed_tools)))
            or any(
                not rule or len(rule) > _ALLOWED_TOOL_RULE_MAX_CHARS or "," in rule
                for rule in self.allowed_tools
            )
        ):
            raise ValueError("allowed_tools must be unique sorted Claude tool rules")


class ClaudeCodeSession(StreamSessionBase):
    """A Claude Code conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume.

    The process stands for the life of the session rather than the length of a turn, which is
    what streaming input buys: the turns of one conversation are lines written to a Claude that
    is already there, and so is anything said to it while a turn is running.
    """

    #: `--json-schema` is Claude's own: it validates the answer against the schema before it
    #: hands it back, so a turn asked for a shape answers in it or does not answer.
    shapes: ClassVar[bool] = True

    #: `--mcp-config` takes a server on the command line, so a flow's own callbacks reach
    #: this turn without anything of the person at this machine's being written.
    takes_tools: ClassVar[bool] = True

    #: The process stands for the life of the session, so a word typed at a turn already
    #: running reaches it: `interject` writes it on the stream Claude is reading, and the
    #: `command_lifecycle` `started` that comes back under its own uuid is the agent having
    #: heard rather than the pipe having taken it.
    steers: ClassVar[bool] = True

    #: `--include-partial-messages`, which this CLI takes and the rest here have no flag for:
    #: a tool call is said the moment the model reaches for it rather than once the whole of
    #: what it was called with has been written. What is said here is that it can be asked
    #: for; whether a given agent asks is `ClaudeCodeAgentConfig.partial_messages`, on unless
    #: a flow says otherwise. A fact about driving this CLI rather than one about the CLI
    #: itself -- it is this driver that asks for the fragments and :meth:`_streaming` that
    #: reads them -- which is why it is declared here rather than in `hmz.coganchor.backends`.
    narrates: ClassVar[bool] = True

    #: Claude keeps a conversation under the directory it was held in, and `--resume` looks
    #: for it under the directory it is run in. A fork opened elsewhere is carried there first,
    #: by :meth:`_carry`.
    forks_elsewhere: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has spent nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What each model has cost so far, by kind, as Claude counts it: a running total per
        #: process, so what a turn cost is the rise across it.
        self._counted: dict[str, Counter[str]] = {}
        #: What the turn now running has already been counted as spending, from the messages
        #: it answered with -- so that the total it states at the end adds only the rest --
        #: and what each of those messages last said it had cost.
        self._fed: Counter[str] = Counter()
        self._seen: dict[str, Counter[str]] = {}
        #: What the process now up was started to think at, so that a flow moving the effort
        #: mid-session is answered by starting one that thinks at the new one.
        self._at: str | None = None
        #: The id Claude says this session has, taken only once a turn has landed in it.
        self._named: str | None = None
        #: The agents this turn has started of its own, by the id of the call that started
        #: each: Claude ends one by answering that call, and what comes back names no tool,
        #: so what it was is remembered here until it does.
        self._fleet: dict[str, str] = {}
        #: Which of the flow's own callbacks the process now up was told about, by the names
        #: it was told them under, so that a session whose offer changes between two turns is
        #: answered by starting one that was told what this turn is offering.
        self._offering: tuple[str, ...] | None = None
        #: What the command line just built said they were, read once while it was built and
        #: kept for the process it starts. Read once rather than twice: an offer landing from
        #: a sibling session between the two reads would be written down as a name the process
        #: was told about when the process was told nothing at all, and never asked again.
        self._telling: tuple[str, ...] = ()
        #: Whether the process now up was given a hook table of its own, and whether the
        #: command line just built gave one -- the same pair, for the same reason: a hook hung
        #: or taken down between two turns is a process started under the wrong answer.
        self._gated: bool | None = None
        self._gating = False
        #: What of the config the process now up was built with, out of the settings only a
        #: command line can carry, or None while nothing is up. `reconfigure` says that every
        #: turn from then on runs at the new one, and these two are read when Claude starts.
        self._built: tuple[tuple[str, ...], bool] | None = None
        #: The tool calls whose arguments are still arriving, by the block of the message each
        #: is being written into. The index is Claude's own numbering of the blocks of one
        #: message, under the call the message belongs to: an agent this one started writes
        #: its messages on this same stream and numbers its own blocks from zero.
        self._reaching: dict[tuple[str, int], _Reaching] = {}
        #: The calls this turn has already said, by Claude's own id for each, so that the
        #: whole of one arriving a moment later as part of a message is not a second row.
        self._announced: set[str] = set()

    @property
    def named(self) -> str | None:
        """What Claude called this session, which it says on the first line it writes."""
        return self._id or self._named

    def _holding(self) -> list[str]:
        """Which conversation this process is to be holding: this one, or a fork of another.

        Three ways in, and the flag says which. A session with an id resumes it. A fork has
        no id of its own yet and the id of the one it was cut from: `--fork-session` is
        `--resume` told to mint a new id rather than reuse the one it was handed, so Claude
        loads the parent's turns and calls what follows a session of its own -- which it says
        on the first line it writes, and which this session then takes for good. Anything
        else is a conversation that does not exist yet, and is named up front.

        Returns:
          The flags, to go on the command line as they are.
        """
        if self._id is not None:
            return ["--resume", self._id]
        if self._forked_from is not None:
            return ["--resume", self._forked_from, "--fork-session"]
        # A fresh id per attempt: an opening turn that failed may still have left Claude
        # holding the id it was given, and retrying under that one would collide forever.
        return ["--session-id", str(uuid.uuid4())]

    def _environment(self) -> dict[str, str]:
        """What the turn runs with, plus :data:`_FOREGROUND`, which nothing else outranks."""
        return {**super()._environment(), **_FOREGROUND}

    def _command(self) -> list[str]:
        """Builds the ``claude --print`` that reads turns from stdin and says events on stdout.

        Opens the session while it is unopened and resumes it once it has an id, which is what
        an anchored session needs: its process ends with each turn, so the next one has a
        conversation to rejoin. An unanchored session opens once and stays open.
        """
        argv = [
            "claude",
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            *(
                # A message arrives whole when the block it is a part of has finished, and a
                # tool call's block is not finished until the whole of what it was called
                # with has been written -- which for a `Write` is the file. Without this the
                # turn says nothing from the moment the model reaches for something to the
                # moment it has finished saying what it reached with, which is a minute of
                # silence on a large edit and reads as a turn that has hung. With it the
                # reach is announced as it happens, and :meth:`_streaming` is what reads it.
                # The one thing this line asks for that the CLI would not do by itself, which
                # is why it is the config's to take back.
                ["--include-partial-messages"]
                if getattr(self._agent.config, "partial_messages", True)
                else []
            ),
            *self._holding(),
            *(
                # The mode the rung means, where there is a rung, said the way the effort
                # below is. An agent at no rung at all is one humanize says nothing to Claude
                # about, which leaves it at whatever mode `claude --print` would have run at
                # on this account. The flag carrying "" would not be that -- it would be a
                # mode named badly -- and Claude has no mode of its own meaning "whatever you
                # were going to do", so the two words go onto the line together or neither of
                # them does.
                ["--permission-mode", _PERMITTED[self._agent.config.permission]]
                if self._agent.config.permission
                else []
            ),
            *(
                # `bypass` is the rung where nothing is asked and nothing is checked, so
                # nobody is at a prompt to answer for it -- and rather than skip the asking
                # with the flag an account may forbid, humanize does the answering. An agent
                # at no rung at all is not that agent: what it stops to ask about is between
                # it and the account it runs on, and taking the deciding for one would be
                # humanize answering a question nobody put to it.
                #
                # `manual` mode routes every request to whoever the CLI is talking to, and
                # `stdio` is that being us: each one is read as a `control_request` and
                # answered `allow`, yes to whatever the account leaves decidable, with its own
                # hard `deny` list still the CLI's to enforce.
                #
                # Not in `claude --help` any more. What 2.1.272 documents is
                # `--permission-prompts <host|none>`, "who answers permission prompts with
                # --print", defaulting to `host` -- "the SDK host or --permission-prompt-tool"
                # -- which reads as though the routing were already the default and this the
                # legacy spelling of it. Tried, it is not: a 2.1.272 run at `--permission-mode
                # manual` without this flag sends no `control_request` at all, with or without
                # `--permission-prompts host` said outright. It denies the tool by itself and
                # names it in the result's `permission_denials`, and the turn ends having
                # asked for something and changed nothing. The host it means is one that
                # announced itself over the control protocol, and a reader of the stream is
                # not that. So the flag stays: without it `bypass` would be a rung that
                # decides nothing and a flow's `PERMISSION_REQUEST` hooks would see none of
                # what they are hung for.
                ["--permission-prompt-tool", "stdio"]
                if self._agent.config.permission == "bypass"
                else []
            ),
            "--settings",
            json.dumps(self._settings(), separators=(",", ":")),
            "--model",
            self._agent.config.model,
            # The rung, where there is one. An agent at no rung is one humanize says nothing
            # to Claude about, which leaves the model at whatever effort the account gives it
            # -- a flag carrying nothing would be read as a rung named badly, and 2.1.x warns
            # about an effort it does not know and then runs at its default anyway, which is
            # the same turn with a line of noise in front of it.
            *(["--effort", self.effort] if self.effort else []),
        ]
        if self._shaping is not None:
            # Claude validates the answer against this itself, so a turn that lands has
            # answered in the shape: what comes back is the object, and nothing else.
            argv += ["--json-schema", json.dumps(self._shaping.model_json_schema())]
        # A tool call is a tool call, and `--disallowedTools` is that call written as a rule.
        # Two things are said with it and the flag takes one list, so they are one list: an
        # agent whose goals were switched off is refused the tools that would carry work past
        # the turn humanize is holding -- a subagent of its own, a wakeup, anything on the
        # scheduler -- and one told not to search the web is refused the two that reach it.
        # Everything else it may reach for is what its permission rung says it may.
        denied: list[str] = []
        if not self._agent.goals_enabled:
            denied += _CONTINUATION_TOOLS
        # `is False` rather than falsy, because the answer has three states and the third is
        # nobody having been asked: a rule written for that one would take the two tools away
        # in the name of a question this flow never put.
        if self._agent.config.web_search is False:
            denied += _WEB_TOOLS
        if denied:
            argv += ["--disallowedTools", ",".join(denied)]
        allowed_tools = getattr(self._agent.config, "allowed_tools", ())
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools)]
        # Read once and kept, so that what the process is recorded as having been told is
        # what this line actually tells it.
        self._telling = self._offered()
        if self._telling:
            # The flow's own callbacks, as the one thing Claude takes a tool it was not
            # shipped with on: a server on the command line rather than a line written into
            # anybody's settings file. Added to whatever the person at this machine has
            # configured rather than replacing it -- `--strict-mcp-config` would take their
            # own servers away for the length of this flow, which is not this flow's to do.
            argv += [
                "--mcp-config",
                json.dumps(self._agent.toolbox.config(), separators=(",", ":")),
            ]
        return argv

    def _settings(self) -> dict[str, Any]:
        """What this process is to run under, as the settings named on its own command line.

        A JSON literal rather than a path, and never a file: `--settings` is how Claude Code
        is told something for the length of one run, and what is said here is this flow's for
        the length of this one. Nothing of the user's own settings is read, written or
        replaced -- what they have configured goes on being theirs, and what is here is added
        to it in the way Claude adds a command line to a file. Which is why nothing is said
        that this turn is not asking for: a key written here is the same key in their own
        settings answered over, so the hook table is here when something is hung on that
        moment and `fastMode` when the tier asked for is `fast`, and neither is here to say no
        on the turns that want neither.

        The hook table is the part that matters. Every other moment of a turn is read off the
        stream this session is already reading, and read there a `PreToolUse` arrives after
        Claude has announced the tool and is about to run it: a flow refusing one would be
        describing what already happened. Claude's own table is the one place it stops and
        waits to be told, so that is where humanize puts the moment -- pointed at
        `hmz internal hook --at <socket>`, which carries it back to the hooks hung on this agent.

        Said only where something is actually hung on that moment. A table is a program Claude
        starts and then waits for before every tool it runs, one call after another -- so a
        table written for hooks that are not there is a relay spawned per file read and a
        quarter of a second added to each, for nothing. A hook hung or taken down between two
        turns is answered the way a moved effort is, by ending this process and resuming the
        conversation in one started under the new answer; one hung while a turn is running is
        read off that turn's own stream instead, watching the tool rather than gating it,
        which is what `Hooks.gated` says and what every backend without a table does anyway.

        Not for an anchored turn, whose Claude runs on another machine: the relay is a program
        on this one talking to a socket on this one, and a table naming it over there would be
        a hook that failed to start before every tool call and a moment that then fired
        nowhere at all. Those turns go on reading `PreToolUse` off the stream, which is
        watching a tool rather than gating it, and which is what every backend did before.

        Returns:
          The settings, as the mapping the flag takes.
        """
        settings: dict[str, Any] = {}
        # Said where the tier asked for is `fast`, and left out otherwise. `--settings` is
        # layered over the settings the person at this machine keeps, so a key written here is
        # an answer of theirs overruled: `"fastMode": false` on every ordinary turn is their
        # own `fastMode` decided for them by a flow that was never asking about it. What the
        # CLI does with the key unsaid is its own business -- a 2.1.272 in print mode reports
        # `fast_mode_disabled_reason: sdk_opt_in_required` and runs at the ordinary tier --
        # and that is the answer to leave standing.
        if self._agent.config.service_tier == "fast":
            settings["fastMode"] = True
        # Read once and kept, so that what the process is recorded as having been told is what
        # this line actually tells it: a hook hung by a sibling session between two reads
        # would otherwise be written down as a table the process never got.
        self._gating = self._hooking()
        # Seconds, which is the unit Claude Code reads this number in. Nothing at all for a
        # gate that could not be served, which is a turn whose `PreToolUse` is read off the
        # stream again rather than one pointed at a socket nothing is listening on.
        if self._gating and (table := self._agent.hooks.gate().table(WAITING)):
            settings["hooks"] = table
        return settings

    def _asking(self, moment: Moment) -> bool:
        """Whether the Claude now running this conversation was given a table of its own.

        What the process was told rather than what is hung now: `--settings` is read when
        Claude starts, so a hook hung after that is one this process will never stop to ask
        about, and the moment has to go on being read off this turn's own stream until the
        turn after has started a Claude that was told.

        Args:
          moment: The moment.

        Returns:
          True where this process asks about it and waits to be told.
        """
        return bool(self._gated) and super()._asking(moment)

    def _hooking(self) -> bool:
        """Whether a Claude started now would be given a hook table of its own.

        Returns:
          True where this machine runs the turn and something is hung on the one moment a
          table is for. Asked as a question of its own because two places need the same
          answer: the line that builds the settings, and the one that says whether the
          process now up was built under a different one.
        """
        return self._agent.anchor is None and self._agent.hooks.hooked(
            Moment.PRE_TOOL_USE
        )

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one thing to say as the user message Claude reads it as.

        A word put into a turn carries a `uuid`, which is what Claude names it by in the
        `command_lifecycle` lines it answers with -- so a turn told three things says which
        of them it has taken in, one at a time. Without one it says nothing at all, and a
        word put in would only ever be as good as the write that sent it.

        Args:
          text: What to say.
          ticket: The uuid to name it by, or "" for a turn's own prompt: the turn beginning
            is what says that one landed.

        Returns:
          The line, newline included.
        """
        said: dict[str, Any] = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        }
        if ticket:
            said["uuid"] = ticket
        return json.dumps(said) + "\n"

    def _restarted(self) -> None:
        """Forgets what the last process had spent, which the new one has not counted."""
        self._counted, self._fed, self._seen = {}, Counter(), {}
        # And whatever was under the turn the last process was taking: it went with it.
        self._fleet = {}
        self._reaching, self._announced = {}, set()
        self._at = self.effort
        self._offering = self._telling
        self._gated = self._gating
        self._built = self._configured()

    def _configured(self) -> tuple[tuple[str, ...], bool]:
        """What of the config a Claude started now would be built with and cannot be told.

        Claude's own tool rules and whether it says a reach as it happens are arguments of the
        process, the way the effort is: read when it starts and held for its life. So they are
        read here, once, and compared against what the process up was built with.

        Returns:
          The allow rules and whether the fragments were asked for, as one value to compare.
        """
        config = self._agent.config
        return (
            tuple(getattr(config, "allowed_tools", ())),
            bool(getattr(config, "partial_messages", True)),
        )

    def _offered(self) -> tuple[str, ...]:
        """What a Claude started now would be told the flow's own callbacks are.

        Returns:
          The name of every callback in front of the agent, sorted, so that a flow which
          builds its list afresh before each turn is offering the same thing each time.
          Names rather than everything a tool says: a name is what a tool is here -- two
          conversations offering one name are offering one tool -- and building every
          argument schema again before every turn to catch a reworded sentence would cost
          each turn more than the sentence is worth.
        """
        return tuple(sorted(one.name for one in self._agent.toolbox.offered()))

    def _stale(self) -> bool:
        """Whether the process up was started for something this turn is no longer.

        `--effort` is an argument of the process, so a flow that moves it mid-session is
        answered by ending this one and resuming the conversation in a process started at the
        new one -- exactly as asking for a shape is. So is `--mcp-config`: Claude reads what
        an MCP server has when it starts it and holds that list for the life of the process,
        so a flow that changes which callbacks it offers between two turns is answered the
        same way. What is compared is the list the process was actually told, not whether it
        was told anything: a tool swapped for another is one the model has never heard of and
        one it can still reach for and be told is not there.

        And so is the hook table: `--settings` is read when Claude starts, so a hook hung
        after it started is one the CLI would never stop to ask about, and one taken down is a
        relay still being spawned before every tool for nobody. The first turn after either
        runs in a process told which it is.

        And so are the two settings of the config that only a command line carries -- the
        native allow rules and whether the reach is said as it happens. `reconfigure` is the
        one thing that changes a frozen config, and what it says is that every turn from then
        on runs at the new one; a process built under the old one would go on running at it
        until something else happened to end it.
        """
        if self._at is not None and self._at != self.effort:
            return True
        if self._gated is not None and self._gated != self._hooking():
            return True
        if self._built is not None and self._built != self._configured():
            return True
        return self._offering is not None and self._offering != self._offered()

    def _spent(self, said: dict[str, Any]) -> tuple[dict[str, int], Usage]:
        """What the turn just ending cost, per model and by the kind it went on.

        Claude reports each model's usage as a running total for the session, so what this
        turn cost is the rise since the last one. Every kind of token counts: what a rate is
        measuring is the traffic, and a cache read crosses the wire like anything else.

        Args:
          said: The `result` event, as read.

        Returns:
          Tokens spent per model since the previous turn, models that did not move omitted,
          and the same spending by kind.
        """
        spent: dict[str, int] = {}
        risen: Counter[str] = Counter()
        used: dict[str, Any] = said.get("modelUsage") or {}
        for model, usage in used.items():
            counted = Counter(
                {
                    kind: int(usage.get(named) or 0)
                    for kind, named in _KINDS.items()
                    if usage.get(named)
                }
            )
            before = self._counted.get(model) or Counter()
            moved = Counter(
                {
                    kind: tokens
                    for kind in set(counted) | set(before)
                    if (tokens := counted[kind] - before[kind]) > 0
                }
            )
            if total := sum(moved.values()):
                spent[model] = total
            risen.update(moved)
            self._counted[model] = counted
        return spent, Usage(risen)

    def _live(self, said: dict[str, Any]) -> None:
        """Takes what one request to the model came to, as its answer arrives.

        Claude says what each of them cost on the message it produced, which is where a rate
        read while the turn is still running comes from -- the `result` at the end of the turn
        is minutes away, and a rate that only moved there would stand still for all of them.
        What the result then states is the whole of the turn, so only the shortfall is added.

        Args:
          said: The `assistant` event, as read.
        """
        message: dict[str, Any] = said.get("message") or {}
        usage: dict[str, Any] = message.get("usage") or {}
        # Claude says the same message twice -- once for the thinking in it and once for the
        # words -- and states the whole of what that request cost both times. So what one of
        # these adds is the rise on the message it names, not the figure on it.
        named = str(message.get("id") or "")
        counted: Counter[str] = Counter(
            {
                kind: int(usage.get(spelled) or 0)
                for kind, spelled in _AS_IT_GOES.items()
                if usage.get(spelled)
            }
        )
        before = self._seen.get(named) or Counter()
        risen = Usage(
            {
                kind: tokens
                for kind in set(counted) | set(before)
                if (tokens := counted[kind] - before[kind]) > 0
            }
        )
        self._seen[named] = counted
        if risen.total:
            self._fed.update(risen)
            self._spends(risen)

    def _settle(self, risen: Usage) -> None:
        """Adds whatever the turn's own total says was spent beyond what was counted live.

        Args:
          risen: What the turn cost, by kind, as the `result` states it.
        """
        owed = Usage(
            {
                kind: tokens
                for kind in set(risen) | set(self._fed)
                if (tokens := risen.get(kind, 0.0) - self._fed[kind]) > 0
            }
        )
        self._fed, self._seen = Counter(), {}
        # Not a turn of the model: the requests it is settling up for have each been counted
        # already, and counting this as one more would put a turn in the average that never
        # happened.
        self._spends(owed, turn=False)

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one event Claude wrote, as the things it says the agent did.

        A message carries a list of parts, and thinking, speaking and reaching for a tool can
        all be in the same one -- so every part is read, not the first that says anything.
        What was thought and what was said are read there, whole: Claude closes each part with
        a message of its own, so the utterance is already the utterance rather than fragments
        of one. Only the reach for a tool is read out of the fragments, by `_streaming`, and
        only because the fragments of that one are the whole of what is being waited for.

        Args:
          line: The line, as written.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing: a tool's
          result coming back, a fragment of words still being written, or something a later
          Claude has added.
        """
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: Claude prints the odd plain line among the JSON
        if said.get("type") == "stream_event":
            yield from self._streaming(
                cast("dict[str, Any]", said.get("event") or {}),
                str(said.get("parent_tool_use_id") or ""),
            )
        elif said.get("type") == "control_request":
            # Claude waits on the answer, so one left unanswered is a turn that never ends.
            self._answer(said)
        elif said.get("type") == "command_lifecycle":
            # What Claude answers a word put into a turn with, under the uuid it was sent
            # with: `queued` the moment it has been read off stdin, `started` once it is in
            # front of the model, `completed` when its answer is done. Only `started` is the
            # agent having heard -- the other two are the pipe and the answer.
            if said.get("state") == "started":
                words = self.took(str(said.get("command_uuid") or ""))
                if words is not None:
                    yield Event(kind="took", text=words)
        elif said.get("type") == "system" and said.get("session_id"):
            # Noted, not taken: this is the first line out, said before anything can go
            # wrong, and a session is only opened by a turn that lands in it.
            self._named = str(said["session_id"])
        elif said.get("type") == "result":
            if failure := _result_failure(said):
                # Claude has emitted `subtype: success` with `is_error: true`, so neither
                # field is sufficient alone. The remaining reasons also guard a malformed
                # success result that arrives while Claude is still asking to use a tool.
                tokens, risen = self._spent(said)
                self._settle(risen)
                yield Event(
                    kind="failed",
                    text=failure,
                    tokens=tokens,
                    spent=risen,
                )
                return
            if self._named is not None:
                self._adopt(self._named)  # a turn has landed, so the session is open
            tokens, risen = self._spent(said)
            self._settle(risen)
            # The turn is over, so what it reached for is nothing the next one has to know
            # about: a session takes thousands of turns, and these would grow with all of them.
            self._reaching, self._announced = {}, set()
            yield Event(
                kind="result",
                text=str(said.get("result") or ""),
                tokens=tokens,
                spent=risen,
            )
        elif said.get("type") == "assistant":
            self._live(said)
            for part in said.get("message", {}).get("content", []):
                if part.get("type") == "text" and part.get("text", "").strip():
                    yield Event(kind="text", text=part["text"])
                elif (
                    part.get("type") == "thinking" and part.get("thinking", "").strip()
                ):
                    yield Event(kind="reasoning", text=part["thinking"])
                elif part.get("type") == "tool_use":
                    marked = str(part.get("id") or "")
                    if marked and marked in self._announced:
                        # Said as the model reached for it, rather than here where the whole
                        # of what it reached with has finally arrived. Saying it again would
                        # be two rows for one call.
                        continue
                    called: dict[str, Any] = part.get("input") or {}
                    yield from self._called(
                        marked, str(part.get("name") or "tool"), about(called)
                    )
        elif said.get("type") == "user":
            # A tool answering, which is the only thing said back to Claude on this stream
            # that is worth reading: one of them is an agent of its own having finished.
            for part in said.get("message", {}).get("content", []):
                if part.get("type") != "tool_result":
                    continue
                marked = str(part.get("tool_use_id") or "")
                if was := self._fleet.pop(marked, ""):
                    yield Event(kind="subagent-ends", text=was, whose=marked)

    def _streaming(self, event: dict[str, Any], under: str) -> Iterator[Event]:
        """Reads one piece of a message Claude is still writing.

        `--include-partial-messages` is on for one thing, and this is it. A tool call is
        announced here the moment the model reaches for it; in the message that carries the
        call it is announced only once the arguments have all arrived, and for a `Write` those
        arguments are the file. Between the two the turn says nothing whatever, which is a
        minute of silence on a large edit and reads from outside as an agent that has hung.

        Nothing else is read from here. What was thought and what was said arrive whole on the
        message Claude closes each part with, and that is the utterance rather than the
        fragments of one -- a row per fragment is a paragraph broken into fifty answers.

        Args:
          event: What the line carried, which is Anthropic's own streaming event.
          under: The tool call this message is being written under -- "" for the agent's own
            and the id of the call for an agent it started. Both are written on this one
            stream, and each numbers the blocks of its own messages from zero.

        Yields:
          The call, as soon as there is enough of its arguments to say what it is about.
        """
        at = (under, int(cast("int", event.get("index") or 0)))
        match event.get("type"):
            case "content_block_start":
                block = cast("dict[str, Any]", event.get("content_block") or {})
                if block.get("type") == "tool_use":
                    self._reaching[at] = _Reaching(
                        marked=str(block.get("id") or ""),
                        named=str(block.get("name") or "tool"),
                    )
            case "content_block_delta":
                delta = cast("dict[str, Any]", event.get("delta") or {})
                reaching = self._reaching.get(at)
                if (
                    reaching is None
                    or reaching.said
                    or delta.get("type") != "input_json_delta"
                ):
                    return
                reaching.arriving += str(delta.get("partial_json") or "")
                if words := arriving(reaching.arriving):
                    reaching.said = True
                    yield from self._called(reaching.marked, reaching.named, words)
            case "content_block_stop":
                reaching = self._reaching.pop(at, None)
                if (
                    reaching is None
                    or reaching.said
                    or reaching.marked in self._announced
                ):
                    # Said as the model reached for it, or said by the message that carries
                    # the call whole -- which lands a moment before this on a Claude that is
                    # keeping up. Either way this is the second time round.
                    return
                # Nothing among the arguments said anything early enough to say it with, and
                # no message has carried the call. They have all arrived now, so they are read
                # the way that message would have read them: one call reads as one row
                # whichever of the two got there first.
                reaching.said = True
                try:
                    whole = json.loads(reaching.arriving or "{}")
                except json.JSONDecodeError:
                    whole = {}
                yield from self._called(
                    reaching.marked,
                    reaching.named,
                    about(cast("dict[str, Any]", whole))
                    if isinstance(whole, dict)
                    else "",
                )
            case _:  # a message starting or ending, and the fragments of words
                pass

    def _called(self, marked: str, named: str, about_it: str) -> Iterator[Event]:
        """One tool call, as the row a transcript has room for.

        Args:
          marked: Claude's own id for the call, which is what pairs an agent this one started
            with the result that ends it.
          named: What the tool is called.
          about_it: What it was called on, as far as anybody knows it yet.

        Yields:
          The call: `Read src/x.py`, `Bash git status`. As a `subagent` where what it starts
          is an agent of its own, since a fleet under a turn is agents rather than tool calls.
        """
        if marked:
            self._announced.add(marked)
        said_as = f"{named} {about_it}".strip()[:120]
        if named in _FLEET:
            self._fleet[marked] = said_as
            yield Event(kind="subagent", text=said_as, whose=marked)
            return
        yield Event(kind="tool", text=said_as)

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers something Claude asked of us over the same stream the turn is read from.

        Two kinds arrive here. The tool Claude uses to ask a person a question is put to the
        person. Everything else is a permission -- and under `bypass`, where Claude runs at
        `manual` and asks before every tool that would change something, every one of those
        asks lands here, which is humanize taking the deciding rather than skipping it. A flow
        watches its agent rather than gating it, so those are allowed with the input they came
        with, unless something hung on `PermissionRequest` says otherwise -- a moment a refusal
        actually stops the agent at, because it is one the backend waits on. It is the second
        of the two here: Claude runs its own hook table first, which is where `PreToolUse` is
        served from and where a refusal means this is never asked at all.
        What the account itself will not allow at all -- the hard `deny` list an organisation
        ships -- the CLI refuses before it ever asks, so a yes here is a yes to what the
        account leaves decidable and nothing more. A question nobody is there to answer is
        refused, which Claude reads as the tool having been declined and carries on from,
        rather than waiting on a reply that is not coming.

        An agent that may change nothing is the exception: a permission is a request to do
        something, and granting one under `read-only` would be handing back the rung the flow
        asked for. Claude in plan mode asks rather than acts, and the answer here is no.

        Args:
          said: The `control_request`, as read.
        """
        asked: dict[str, Any] = said.get("request") or {}
        called: dict[str, Any] = asked.get("input") or {}
        answers: dict[str, str] = {}
        tool = str(asked.get("tool_name") or "")
        if tool != _ASKS:
            asking = self._fire(
                Moment.PERMISSION_REQUEST,
                tool=tool,
                about=about(called),
                called=called,
            )
            if self._agent.config.permission == "read-only":
                self._reply(
                    said,
                    {"behavior": "deny", "message": f"{tool} would change something"},
                )
                return
            if asking.refused:
                self._reply(
                    said,
                    {
                        "behavior": "deny",
                        "message": asking.because or f"{tool} was refused",
                    },
                )
                return
        else:
            for raw in cast("list[Any]", called.get("questions") or []):
                question = cast("dict[str, Any]", raw)
                wanted = str(question.get("question") or question.get("header") or "")
                offers: list[Any] = question.get("options") or []
                offered = tuple(
                    str(cast("dict[str, Any]", option)["label"])
                    for option in offers
                    if isinstance(option, dict)
                    and cast("dict[str, Any]", option).get("label")
                )
                answer = self._agent.asked(Question(text=wanted, options=offered))
                if answer is None:
                    self._reply(said, {"behavior": "deny", "message": "nobody to ask"})
                    return
                answers[wanted] = answer
        self._reply(
            said,
            {
                "behavior": "allow",
                "updatedInput": {**called, "answers": answers} if answers else called,
            },
        )

    def _reply(self, said: dict[str, Any], answer: dict[str, Any]) -> None:
        """Writes one answer back to Claude, against the request it answers.

        Args:
          said: The `control_request` being answered.
          answer: What to answer it with.
        """
        self._send(
            json.dumps(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": said.get("request_id"),
                        "response": answer,
                    },
                }
            )
            + "\n"
        )

    def _carry(self, cwd: str) -> None:
        """Copies this conversation to where a Claude run in another directory looks for it.

        Claude keeps a conversation as `projects/<the directory, spelled as a name>/<id>.jsonl`
        under its home, and `--resume <id> --fork-session` reads it from under the directory
        it is run in. So a fork opened elsewhere is given a copy there to be cut from; the
        copy is this conversation as it stands, which is what the fork carries on from.

        Args:
          cwd: The directory the fork is to work in.

        Raises:
          NotImplementedError: For an agent whose turns land on another machine, whose Claude
            keeps its conversations there rather than here.
          RuntimeError: If this conversation cannot be found where Claude keeps it.
        """
        import shutil

        from hmz.coganchor.backends import named

        if self._agent.config.machine is not None:
            raise NotImplementedError(
                "claude cannot carry a conversation into another directory on another machine"
            )
        profile = named("claude")
        assert profile is not None  # noqa: S101 -- the backend this driver is for
        projects = profile.directory(self._environ()) / "projects"
        # Where this conversation is held first: an earlier fork carried elsewhere left a
        # copy of it there, as it stood then, which is not where it stands now.
        held = os.path.abspath(self.cwd)  # noqa: PTH100
        found = next(
            (
                kept
                for spelled in dict.fromkeys((held, os.path.realpath(held)))
                if (kept := projects / _project(spelled) / f"{self.id}.jsonl").is_file()
            ),
            None,
        ) or next(projects.glob(f"*/{self.id}.jsonl"), None)
        if found is None:
            raise RuntimeError(f"claude: no conversation {self.id} under {projects}")
        where = os.path.abspath(cwd)  # noqa: PTH100
        for spelled in dict.fromkeys((where, os.path.realpath(where))):
            there = projects / _project(spelled)
            there.mkdir(parents=True, exist_ok=True)
            if (there / found.name) != found:
                shutil.copyfile(found, there / found.name)

    def _pursue(self, objective: str) -> str:
        """Runs the turn as Claude Code's own ``/goal``, which print mode expands like any other.

        Claude keeps the session going itself, by refusing to stop while the objective is
        unmet, so the turn is over only once it has been reached or given up on.
        """
        return self(f"/goal {objective}")


class ClaudeCodeAgent(AgentBase):
    """Claude Code, driven over its streaming JSON protocol so a turn can be talked to."""

    service_tiers = ("default", "fast")

    #: Every moment a turn passes through, and three more: Claude asks before it uses a tool,
    #: over the same stream the turn is read from, and waits for the answer -- so this is the
    #: one backend here where a hook can say no to something and have the agent hear it -- and
    #: it says on the same stream when it starts an agent of its own and when that one is done.
    moments: ClassVar[frozenset[Moment]] = (
        EVERYWHERE | SUBAGENTS | {Moment.PERMISSION_REQUEST}
    )

    #: Claude keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    #: What it counts, read off the same table its driver reads a usage with, so that
    #: what a run is told this backend reports is what its driver actually parses.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> ClaudeCodeSession:
        """Opens a new Claude Code session, in the directory it is given or in this one."""
        return ClaudeCodeSession(self, cwd)
