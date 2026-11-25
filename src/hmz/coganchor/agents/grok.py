"""grok: one `grok agent stdio` held open per conversation, and a run per shaped turn.

Grok Build serves the Agent Client Protocol on its own stdin and stdout -- `grok agent stdio`
-- and that is one process for the whole conversation rather than one per turn: `session/new`
opens it, `session/prompt` takes a turn on it, and what the agent is doing arrives as
`session/update` notifications while the turn runs. A turn is a line written to a process that
is already up, so a turn no longer pays for a CLI starting.

Not every turn can go that way. The protocol's process is configured by its command line, and
what `grok agent` carries of an agent is a short list: a model, an effort, an approval, a
profile, a plugin directory and the leader, beside the debugging and the endpoints. It has no
`--tools`, no `--disable-web-search`, no `--json-schema`, no `--sandbox`, no `--max-turns`, no
`--no-subagents` and no `--rules` -- each of those seven refused outright, `error: unexpected
argument` -- so a fence that writes nothing, whose tools are an allowlist, an agent told not to
search the web or fenced off the network, a turn held to a shape and four of the five settings
on `GrokBuildAgentConfig` are settings only `grok -p` carries. Those run the command they
always did, resuming the same conversation with `--resume` -- the id is Grok Build's own either
way, and each transport picks up what the other opened. Nothing is served looser for the
transport's sake: what moves is which of the two a turn is taken on.

The prompt goes on the command line for that run because that is the only way in: Grok Build
does not read a piped stdin as the prompt, and the two other ways it offers are a JSON literal
and a file. `--prompt-file` is the one that would put a long prompt out of argv's way, and it
is worth knowing exactly how long: Linux takes 2MB of argv in total but caps any *single*
element at 32 pages, which measures here as 131062 bytes once `--single=` and the terminator
are off it. A prompt past that is an `OSError` raised where the process would have started,
before Grok Build has seen anything. That is about 32 thousand tokens of prompt -- far more
than a turn of a flow writes, and far less than a context window holds -- so it is a ceiling
rather than a comfort. It stays on the command line because the alternative is a file to
write, to keep for the length of the turn and to clear up after a turn that may have been cut
off, and this transport has nowhere to hang that clearing up: a turn is `_turn` returning an
argv and nothing runs after the process ends.

A fence is held from outside, whole, and never by Grok Build's own sandbox -- which is the
finding :meth:`GrokBuildAgent.natively` is left at its default for. The sandbox is real and
reaches both transports: `GROK_SANDBOX` is read by `grok agent stdio` though `--sandbox` is
refused there, and it confines the whole process with Landlock rather than its commands
alone. But it cannot say a fence. Its network setting blocks the *commands'* network with
seccomp and leaves the process's own untouched, `web_fetch` included, so a cut network is
never Grok Build's to hold. What it is told instead, wherever a fence cuts the network, is
`--disable-web-search`, whatever `web_search` says: its `web_search` may be xAI's own search,
run at the model's host, which the fence's proxy lets through, and `web_fetch` would be one
more thing refused by the proxy rather than never tried. `grok agent` refuses that flag, and
has no other switch for it -- `GROK_DISABLE_WEB_FETCH` takes the fetch and leaves the search --
so an offline conversation takes every turn with `grok -p`. Every profile it has -- the four
built in, and a custom one, which only extends one of those -- lets `/tmp` and `/var/tmp` be
written and the working directory too, so none is as narrow as a fence that grants neither. A
custom profile is read only out of the person's `~/.grok/sandbox.toml` or a `.grok/sandbox.toml`
in the directory worked in, which are theirs, not Humanize's, to write. And on a machine whose
kernel gives unprivileged users no user namespace, 1.0.24 does not start under any profile at
all, built-ins included: `bwrap: setting up uid map: Permission denied`.

What a fence does change here is the leader. Grok Build hands a conversation to a shared
leader process where it is told to, and that process is whoever started it -- outside the
fence, reached over a Unix socket the fence does not govern -- so a fenced conversation that
joined it would run its tools unfenced. Grok Build's own sandbox refuses the leader for the
same reason; a fenced conversation here is always started with `--no-leader`, and one told to
join the leader is refused (:meth:`GrokBuildAgent._serves`).

In a chat every line is said as text, there being no catalog of native input: Grok Build is
driven over the Agent Client Protocol, a turn being a text block of `session/prompt` (or the
prompt of a `grok -p` for a turn that needs a flag), and a harness spoken to that way has none.
Its own `/` commands, `@` file picker and `!` shell mode are its terminal interface's, which
neither transport goes through.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz.coganchor.homes import merged, merger

# What the protocol says a thing is, what a client may do, how a tool call is permitted and
# what ends a turn having answered are the protocol's rather than Grok Build's, so they are
# taken from the ACP client every such CLI here is driven through rather than said again.
from .acp import _ALWAYS, _ANSWERED, _CAPABILITIES, _GRANTS, _VERSION, _bridged
from .acp import _SAYS as _TOLD
from .base import (
    _IN_SHAPE,
    AgentBase,
    CommandSessionBase,
    SessionBase,
    StreamSessionBase,
    _ended,
)
from .config import AgentConfig, Unfenced, Unserved
from .event import Event, Failed, Saying, Unrecoverable, Usage

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    import tomlkit
    from pydantic import BaseModel

#: What the CLI is installed as.
_COMMAND = "grok"

#: Everything is approved without being asked, wherever there is a fence: nobody is at a
#: prompt here, and a turn waiting on an approval is a flow that stopped. `--always-approve`
#: rather than `--yolo`, which is a hidden alias for it that `grok agent` still takes and
#: neither command documents: a spelling the help does not list is one release away from
#: disappearing, and this one is the same flag under the name Grok Build actually publishes.
_APPROVAL = "--always-approve"

#: The one flag on that list a turn told not to search the web is given, which Grok Build
#: documents as exactly that -- `Disable web search and web fetch tools`. It says what
#: `--disallowed-tools web_search,web_fetch` said before it and says it in one word: run
#: against 1.0.24 the two leave the same 25 tools in the process, the whole list less those
#: two, so the general flag was spelling out what the CLI has a name for.
_NO_WEB = "--disable-web-search"

#: The tools an agent whose fence writes nothing is started with, as `--tools` takes them: the
#: three that read and `run_terminal_cmd`, Grok Build's shell. An allowlist rather than a list
#: of what to take away, since a tool the process was not started with cannot run at all and a
#: tool a later release adds is one this list never let in -- `--tools read_file,grep,list_dir`
#: leaves those three and the two by which an MCP server is looked up, and a turn asked to
#: write a file under it reaches for a writer that is not there and writes nothing.
#:
#: The shell by its tool id and not by the name a tool call is reported under. Over ACP the
#: shell's calls are titled `run_terminal_command`; but `--tools` takes ids, and run against
#: 1.0.62 an allowlist naming `run_terminal_command` warns `--tools "run_terminal_command"
#: names no tool, so other tools stay available` and starts with the whole toolset, writers
#: included -- one wrong name and the allowlist is no allowlist at all. `run_terminal_cmd` is
#: the id its own help gives the shell, and the one 1.0.62 takes without a word.
#: The shell is kept: a `git log` or a test run is most of what an agent that may change
#: nothing is for, and a write it attempts is refused by the fence around the process rather
#: than by anything Grok Build is told.
#:
#: Grok Build's own `--permission-mode` is deliberately not how this is said, and that is the
#: finding this list is written around. It has six modes -- `default`, `acceptEdits`, `auto`,
#: `dontAsk`, `bypassPermissions`, `plan` -- and on 1.0.24 a headless `grok -p` run at every
#: one of them, `plan` included, ran the same `echo`, wrote the same file into the workspace
#: and wrote the same file outside it. A mode governs how the permission *rules* this machine
#: has are applied, and a machine with no rules -- which is what `grok inspect` reports of a
#: fresh one -- has nothing for a mode to apply; headless has nobody to ask, so what is left
#: is approved. A mode is a grant that looks held and holds nothing, and the fence is what
#: holds it in any case: what the CLI is told is only which tools it has.
_READERS = ("read_file", "grep", "list_dir", "run_terminal_cmd")

#: The web tools by their `--tools` ids, added to :data:`_READERS` where the agent may search the
#: web (:func:`_searches`). An allowlist leaves out what it does not name, so a fence that writes
#: nothing would otherwise take web search away from an agent whose grant is online -- and
#: Section 4.6.3.1 of the protocol has a grant on the network switch its web search on, whatever
#: it may write. 1.0.62 takes both ids without a word, as it does not a name that is no tool.
_SEARCHERS = ("web_search", "web_fetch")


#: What `grok inspect --json` lists, under `permissions.enforced`, for an administrator's lock on
#: always-approve: `[ui] disable_bypass_permissions_mode = true`, or the legacy `[ui] yolo =
#: false`, in a `requirements.toml` or the macOS MDM domain `ai.x.grok`. 1.0.62 reports it as
#: `{"setting": "alwaysApprove", "enabled": false, "source": <the file>}`, and under it takes
#: `--always-approve` with a warning and runs at its ask mode: over the protocol every tool call
#: comes to the client as `session/request_permission`, and on `grok -p`, which has no client,
#: a call that needs approval is refused -- `permission required: ... was not run` -- in a turn
#: that still exits 0. The same lock in Claude Code's `managed-settings.json` is one Grok Build
#: reads as advisory (`claudeBypassLockAdvisory`) and does not enforce, so it is not looked for.
_LOCK = "alwaysApprove"

#: What `grok -p` says on stderr of a tool call it refused for want of anyone to approve it: the
#: backstop for a lock the probe did not see -- a run on another machine is one it does not look
#: at -- and for an administrator's `ask` rule, which 1.0.62 holds even under always-approve.
_LOCKED = "a headless run cannot ask for approval"

#: How long `grok inspect` is given to say, which takes a fifth of a second.
_INSPECTING = 10.0

#: What each `grok` this process has run, under each `GROK_HOME`, was found locked by: the source
#: of the lock, or "" for none. A machine's requirements are not a flow's to move, so one probe
#: is the whole cost of finding out.
_PROBED: dict[tuple[str, str], str] = {}
_PROBING = threading.Lock()


def _locked() -> str:
    """Where always-approve is locked off for the `grok` this machine runs, asked of `grok` itself.

    `grok inspect --json` rather than the files: it reads every layer the lock can come from --
    the signed `$GROK_HOME/requirements.toml`, `/etc/grok/requirements.toml` and the MDM domain --
    as the CLI that enforces it reads them, runs no model and writes nothing of the user's, and
    takes a fifth of a second. A `grok` that cannot say -- missing, older than the field, its
    answer unreadable -- is taken as unlocked, the turn's own stderr (:data:`_LOCKED`) being the
    backstop.

    Returns:
      The source of the lock, or "" where there is none.
    """
    found = shutil.which(_COMMAND) or ""
    key = (found, os.environ.get("GROK_HOME", ""))
    with _PROBING:
        if key not in _PROBED:
            _PROBED[key] = _inspected(found) if found else ""
        return _PROBED[key]


def _inspected(found: str) -> str:
    """What one `grok inspect --json` says locks always-approve off, as :func:`_locked` says it.

    Args:
      found: The `grok` to ask.

    Returns:
      The source of the lock, or "" where it names none or cannot be read.
    """
    try:
        ran = subprocess.run(
            [found, "inspect", "--json"],
            capture_output=True,
            text=True,
            timeout=_INSPECTING,
            check=False,
        )
        said = json.loads(ran.stdout)
        enforced = said["permissions"]["enforced"]
        return next(
            (
                str(one.get("source") or "requirements.toml")
                for one in enforced
                if one.get("setting") == _LOCK and one.get("enabled") is False
            ),
            "",
        )
    # An answer of another shape is one that names no lock this can read.
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        LookupError,
        TypeError,
        AttributeError,
    ):
        return ""


def _granted(config: AgentConfig, *, locked: bool = False) -> tuple[str, ...]:
    """What a turn at this config is run as, said as the command line says it.

    Read off the fence and nothing else. A fence that writes nothing is approved its tools and
    started with :data:`_READERS` only, and :data:`_SEARCHERS` beside them where the agent may
    search the web; one that writes somewhere is approved every tool, the
    fence deciding where its writes land. And an agent with no fence -- one driven by hand --
    is told nothing whatever: no approval, no allowlist. It is one `grok` decides for itself
    -- its own prompting, the permission rules this machine carries, the tools it starts with
    -- which is exactly what `grok -p` does when nobody hands it a flag.

    Where always-approve is locked off (:data:`_LOCK`), nothing either: the conversation is held
    open on the protocol, every tool comes to the client to be granted, and the allowlist goes
    with the command line that alone carries it -- confinement refusing the writes.

    Args:
      config: What the agent is to run at.
      locked: Whether always-approve is locked off where the agent runs.

    Returns:
      The flags, to go on the command line as they are.
    """
    if config.fence is None or locked:
        return ()
    if config.fence.writes:
        return (_APPROVAL,)
    allowed = _READERS + (_SEARCHERS if _searches(config) else ())
    return (_APPROVAL, "--tools", ",".join(allowed))


#: How a tool call is refused, as `_GRANTS` is how one is permitted: the kind rather than the
#: id, for the reason ACP gives that field. One kind rather than the two the protocol has,
#: because the other one is not the same refusal. Run against 1.0.24, `reject_always` writes
#: the refusal into that project's own configuration -- `User rejected the execution and
#: excluded 'echo hello-from-grok' from future runs in this project` -- which is one refused
#: turn leaving a rule behind it on somebody's machine -- where a refusal is reached for an
#: agent driven by hand, whose whole meaning is that Humanize settles nothing about this
#: machine. So a request
#: offering no `reject_once` falls through to `cancelled` instead of to that: refusing without
#: writing anything down is worth more than refusing in the agent's preferred words.
#:
#: What either comes to is the same turn anyway: 1.0.24 fails the tool call with `User
#: rejected the execution for tool run_terminal_command` and answers `session/prompt` with
#: `stopReason: cancelled`, which :meth:`_answered` reads as a turn that did not answer. So a
#: refusal here is a failed turn a flow can read, not a turn left hanging on a client that
#: said nothing.
_REFUSES = ("reject_once",)

#: What each answer to the leader question is said with, and why there are three of them.
#: A leader is one backend process shared by every client that asks for it, and which a
#: `grok agent` joins is not its own choice: it follows `[cli] use_leader` in the
#: `~/.grok/config.toml` of whoever is at this machine. So `--no-leader` is the answer
#: Humanize has always given, and goes on giving unless it is told otherwise -- a flow whose
#: sessions all landed on one backend because of a line in somebody's config file would be
#: running something other than what it was measured as. `--leader` is the opposite answer
#: said out loud, and None is the question left to that config file, which is the bare CLI's
#: own behaviour. The two flags refuse each other -- `the argument '--leader' cannot be used
#: with '--no-leader'` -- which is why this is one setting with three answers rather than two
#: settings that could contradict.
_LEADING: dict[bool | None, tuple[str, ...]] = {
    False: ("--no-leader",),
    True: ("--leader",),
    None: (),
}

#: What each kind of line reads as. A tool call that is only being updated is not shown
#: again: it was shown when it started, and a row per status is a transcript of statuses.
_SAYS = {"text": "text", "thought": "reasoning"}

#: What each kind of token is called in the counts Grok Build states, and what each of them
#: is here. Humanize's own names rather than the CLI's, as everywhere else a kind is
#: counted: the prices are per kind, so a usage written down under a spelling nothing else
#: knows is a lump nobody can put a figure on -- which is what these were until this table.
#: The input count is the uncached part alone, which is why the two cache counts stand beside
#: it rather than being folded into it, so the four added up are the whole of what crossed
#: the wire.
#:
#: Its `reasoning_tokens` is deliberately not among them. It is counted *inside* the output
#: rather than beside it -- a turn asked to think at length and answer in one word came back
#: with `output_tokens: 1141` and `reasoning_tokens: 1140` -- so a kind of its own here would
#: count those tokens twice and, the prices billing reasoning as output, charge for them
#: twice as well.
_KINDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}

#: `grok -p` writes the protocol's own `session/update` with `sessionUpdate` flattened onto
#: `type` and the words moved onto `data`: the two transports are one stream said twice, which
#: is why a turn reads the same on either and why `_TOLD` above is the protocol's own table.

#: How long a new process has to say what protocol it speaks and open the session. Generous,
#: because a machine holding twenty of these is a machine where starting one is slow; finite,
#: because a process that fills the pipe nobody is draining yet before it answers is a process
#: nothing will ever hear from, and a turn waiting on that one never ends at all.
_HANDSHAKE = 120.0

#: And how long to wait for what a process that has stopped said on its way out. Short, and on
#: a thread of its own: a stream is spent when every holder of its write end has let go, and
#: Grok Build has a leader of its own that would be handed one.
_WAITING = 5.0

#: The variable a gateway account says which API its endpoint speaks in, and the three answers
#: Grok Build has a word for -- spelled as its `api_backend` spells them. Humanize's variable
#: rather than the CLI's: 1.0.46 reads no variable for it at all, only an `api_backend` on a
#: `[model.*]` entry of `$GROK_HOME/config.toml`. The `GROK_CONFIG` overlay that would have
#: carried one without a file is allowlisted to a few soft tables and drops `model`, which was
#: run against it -- an entry said there was posted to `/chat/completions` all the same.
_SPEAKS = "GROK_GATEWAY_API_BACKEND"
_APIS = frozenset({"responses", "chat_completions", "messages"})

#: Where the endpoint is and what it is paid with, as the gateway ways keep them: the variables
#: 1.0.46 itself reads for an endpoint's catalogue and for the bearer it sends there.
_AT = "GROK_XAI_API_BASE_URL"
_KEY = "XAI_API_KEY"

#: The version an Anthropic-shaped endpoint refuses to answer without, which 1.0.46 does not
#: send of its own accord -- its own guide's Anthropic example adds it by hand, as this does.
_DATED = "2023-06-01"


class GrokBuildSession(StreamSessionBase):
    """A Grok Build conversation, held open on the process that opened it.

    The id is minted by `grok` as the session opens -- answered by `session/new` on the
    protocol, and reported on the line a run ends on -- so it is read back out of whichever
    turn opened it and given to every turn after. That is what keeps the conversation one
    conversation rather than a new one per turn, and what lets a shaped turn resume on the
    command line what the held-open process opened. Asked for rather than chosen: `-s` takes
    an id but refuses one already in use, and a flow that reopened a session it had already
    run would fail on its second turn.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking, on the
    #: protocol and on the command line alike.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the answer comes back validated by the agent
    #: itself rather than asked for in the prompt.
    shapes: ClassVar[bool] = True

    #: The protocol's `session/new` and `session/load` carry `mcpServers`, so the flow's own
    #: callbacks reach a held-open conversation as one more server, written into no
    #: `config.toml`. `grok -p` has no flag for one, so a turn that has to go there while
    #: callbacks are offered is refused rather than taken without them: :meth:`_stream`.
    takes_tools: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the agent has said so far in the turn now running, and what went wrong with it
        #: if anything did. The text arrives in chunks, so the answer is what they come to.
        self._said: list[str] = []
        self._failed: str | None = None
        #: Why this client refused a tool call of the turn now running, or None where it
        #: refused none. Kept because Grok Build answers a refused prompt with `stopReason:
        #: cancelled` and says nothing about who cancelled it, and a turn that reads as the
        #: CLI giving up is a turn whose flow cannot tell a refusal from a fault.
        self._refused: str | None = None
        #: What a run of `grok -p` said of an always-approve lock it found, which no probe
        #: here saw: a fenced turn under it is one whose tool calls nobody approved.
        self._locked_out = ""
        #: Those same chunks, gathered into the answers they are pieces of: a response is one
        #: paragraph and is worth one row of a transcript rather than one row a word.
        self._saying = Saying()
        #: What the turn now running has cost, added up as each response of it comes back, and
        #: the tool calls already shown -- a call is shown as it starts and updated after.
        self._costing = Usage()
        self._shown: set[str] = set()
        #: What the process now up was started for, and what this turn wants: they differ
        #: exactly when something the command line carries has moved, which is a restart.
        self._launched: tuple[object, ...] | None = None
        self._requested: tuple[object, ...] = ()
        #: The last id sent on this process, and the id of the turn's own request. Numbered
        #: per process because the process is where the protocol's conversation lives.
        self._at = 0
        self._asked: int | None = None

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Keeps ordinary turns warm, and runs the rest as the command that carries them.

        A shape, a fence that writes nothing and everything :func:`_extras` writes are
        settings of `grok -p` and of nothing else: `grok agent` has a flag for none of them,
        so a turn that needs one is a run of the command line rather than a line written to
        the process. The conversation is not ended by that -- the run resumes it, and the
        process the next ordinary turn starts loads it back.

        So is the first turn of a conversation cut from another. The protocol opens a session
        or loads one by id and has no third call; `--fork-session` is the command line's, and
        it is what mints the id this conversation is from then on. One turn that way, and the
        turns after it are ordinary ones on the process that loads what it minted.

        Where always-approve is locked off, every turn stays on the protocol, whose client is
        asked and grants: a shape is asked for in the prompt (:meth:`_shaped_ask`), a fence
        that writes nothing is held by confinement alone, and what only `grok -p` can say is
        refused before a session opens (:meth:`GrokBuildAgent._admits`). Said once per agent.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, or None to take what the agent says.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          Unrecoverable: For a turn the command line has to take while the flow's own
            callbacks are offered: `grok -p` takes no MCP server, and a turn whose model was
            never told of them reads as a model that would not use them.
        """
        agent = self._agent
        if isinstance(agent, GrokBuildAgent):
            agent._admits()  # noqa: SLF001 -- the session is the agent's own
        locked = _locks(agent)
        if (schema is not None and not locked) or self._commanded() or self._forking():
            if self._agent.toolbox.offered():
                said = (
                    f"{_COMMAND} -p, which this turn needs, takes no MCP server, so it "
                    "cannot be offered the flow's own callbacks"
                )
                raise Unrecoverable(1, [_COMMAND], "", said)
            with self._lock:
                self._shut()
                # The finite command transport checks the process's exit status after its
                # result too. Reuse it on this same session state: a helper session would
                # register a second conversation and count its opening twice.
                yield from CommandSessionBase._stream(  # noqa: SLF001 -- shared turn transport
                    cast("CommandSessionBase", self), prompt, schema=schema
                )
            return
        # Only a grok agent is ever locked, and the session is its own.
        if locked and cast("GrokBuildAgent", agent)._first_locked():  # noqa: SLF001
            yield Event(
                kind="notice",
                text=f"{_COMMAND}: always-approve is locked off by {locked}, so this agent "
                "runs asking, and every tool call it asks about is granted",
            )
        with self._lock:
            self._requested = self._settings()
            self._said, self._failed, self._shown = [], None, set()
            self._costing, self._saying, self._refused = Usage(), Saying(), None
            try:
                yield from super()._stream(prompt)
            except BaseException:
                # A process that failed a turn is a process whose state nobody here can
                # account for. The conversation survives it: the next turn loads the session
                # back onto a process started afresh.
                self._shut()
                raise

    def _shaped_ask(self, prompt: str, schema: type[BaseModel] | None) -> str:
        """The prompt, with the shape under it where always-approve is locked off.

        `--json-schema` is `grok -p`'s, which has nobody to grant a tool call under the lock,
        so a shaped turn is asked for its shape and taken on the protocol like any other.

        Args:
          prompt: What the flow is asking.
          schema: The shape it wants back, or None.

        Returns:
          The prompt as this turn is to be given it.
        """
        if schema is None or not _locks(self._agent):
            return prompt
        return prompt + _IN_SHAPE.format(
            schema=json.dumps(schema.model_json_schema(), indent=2)
        )

    @property
    def forks(self) -> bool:
        """Whether this conversation can be cut into a second one.

        Not where always-approve is locked off: `--fork-session` is `grok -p`'s, where nothing
        can grant a tool call.
        """
        return super().forks and not _locks(self._agent)

    def fork(
        self,
        *,
        into: AgentBase | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> SessionBase:
        """Cuts a second conversation from this one, as :meth:`SessionBase.fork` does.

        Raises:
          NotImplementedError: Where always-approve is locked off, said as the session is cut
            rather than as its first turn runs with nobody to grant what it asks.
        """
        if locked := _locks(self._agent) or _locks(into or self._agent):
            raise NotImplementedError(
                f"{_COMMAND}: always-approve is locked off by {locked}, and a fork is cut "
                f"only by `{_COMMAND} -p`, where nothing can grant a tool call"
            )
        return super().fork(into=into, cwd=cwd)

    def _forking(self) -> bool:
        """Whether this turn is the one that cuts this conversation from the one it came from.

        Returns:
          Whether a fork is still to be made: the protocol has no call for one, so it is made
          on the command line, once, and never again once the fork has an id of its own.
        """
        return self._id is None and self._forked_from is not None

    def _commanded(self) -> bool:
        """Whether this turn carries something only the top-level command line can say.

        The one place that question is asked, so that a setting added to
        :class:`GrokBuildAgentConfig` is a line here and a line in :meth:`_turn` rather than
        an option that quietly applied to some turns of a conversation and not others. A turn
        that needs one of these is a run of `grok -p` resuming the same session; the rest stay
        on the process already up.

        Returns:
          Whether the fence writes nothing, its tools an allowlist, the agent is told not to
          search the web -- or is fenced off the network, which says the same whatever it was
          told -- or any of the settings only the top-level command has been asked for -- a
          sandbox profile, a cap on the turns under this one, subagents switched off, rules to
          append. Every one of them is refused by `grok agent` with `error: unexpected
          argument`, and an agent given one that the transport could not carry would be a
          setting that lies.
        """
        config = self._agent.config
        # `is False` rather than `not`: the web is three answers, and None is the agent nobody
        # was asked about, which is said with no flag at all. `not None` is true, so the
        # shorter test would send every turn of every such conversation to the command line
        # for a flag it was never going to write.
        return bool(
            (
                config.fence is not None
                and not config.fence.writes
                and not _locks(self._agent)
            )
            or not _searches(config)
            or _extras(config)
        )

    def _settings(self) -> tuple[object, ...]:
        """What the held-open process was started with, and so what going stale means.

        Returns:
          Everything a flow can move that the process reads once, as it starts: what the
          agent is configured as, how hard this conversation thinks, the skills it carries
          and the environment its provider hands it. What the person at this machine has in
          their own `~/.grok` is not among them -- a flow does not move it, and proving each
          turn that it did not is a cost every turn would pay for an edit nobody made.
        """
        return (
            self._agent.config,
            self.effort,
            self._carrying(),
            # The whole environment rather than what the provider adds to it: an agent whose
            # provider adds nothing is handed this process's own, and a flow that moved one of
            # the twelve variables Grok Build reads would otherwise move nothing at all.
            self._environ() or dict(os.environ),
            # And the callbacks it was handed, which it lists once, as the session opens.
            self._agent.toolbox.names(),
        )

    def _model(self) -> str:
        """What this conversation asks Grok Build for its model by.

        The model itself for every account but one behind a gateway, which is asked for by
        the entry :func:`_routed` keeps for it -- the one place the API that gateway speaks
        can be said. Read off the environment a turn runs under, which is the account's.

        Not for a turn on another machine, where the API cannot be said both truly and
        privately: the entry is written into the `config.toml` of a virtual home this machine
        builds, which a target's own `grok` never reads, and the headers an Anthropic-shaped
        endpoint wants travel in a variable holding the key, which every command the agent
        runs on a target would inherit. Refused there rather than run in whatever API the CLI
        picks by the model's name, which would be the account's answer quietly not given.

        Returns:
          The name `--model` takes.

        Raises:
          Unrecoverable: For a gateway account on a target whose own CLI takes the turn, or
            under a harness on another machine -- neither is started in a virtual home this
            machine builds -- or on any target for one speaking Anthropic's API.
        """
        from hmz.coganchor.elsewhere import elsewhere

        environ = self._environ() or os.environ
        speaks = environ.get(_SPEAKS, "").strip()
        if self._agent.config.machine is not None and speaks and environ.get(_AT):
            anchor = self._agent.anchor
            if anchor is not None and (
                anchor.native or elsewhere(anchor) or speaks == "messages"
            ):
                said = f"a grok account speaking {speaks} to a gateway runs on this machine"
                raise Unrecoverable(1, [_COMMAND], "", said)
        return _routed(self._agent.config.model, environ)[0]

    def _stale(self) -> bool:
        """Restarts before settings or mounted flow resources change."""
        return self._launched is not None and self._launched != self._requested

    def _merges(self) -> tuple[tuple[str, str], ...]:
        """The `[model.*]` entry a gateway account is asked for by, for the home's `config.toml`.

        The home is the user's own as :mod:`hmz.coganchor.homes` builds it -- a copy of their
        `config.toml`, links to everything else, the flow's skills beside theirs -- and the
        entry (:func:`_routed`) is put into that copy (:func:`_entered`), which goes with the
        process: the user's own is never written. Nothing for an account no gateway holds.
        """
        named, entry = _routed(self._agent.config.model, self._environ() or os.environ)
        if entry is None:
            return ()
        return (merged(_entered, {"named": named, "entry": entry}),)

    def _command(self) -> list[str]:
        """The `grok agent stdio` this conversation is held open on.

        What the fence grants goes on whole rather than as the approval alone: of what
        :func:`_granted` says, only `--always-approve` is a flag `grok agent` takes --
        `--tools` is refused there outright, `error: unexpected argument` -- and a turn that
        needs anything else never reaches this transport at all: :meth:`_stream` has already
        sent it to the command line. So whatever is said here is a flag this process takes,
        and a fence that writes somewhere is held open as well as one that is not there.

        Returns:
          The command, carrying what the protocol's process is configured by: the model, how
          hard to think, the approval a flow watching its agent gives once rather than per
          tool call, and what it was told about the leader.
        """
        return [
            _COMMAND,
            "agent",
            "--model",
            self._model(),
            # Where there is a rung. `grok agent` takes any word at all here and says nothing
            # until the first shaped turn goes out on the command line, so an agent at no rung
            # is better off saying nothing than saying "".
            *(["--effort", self.effort] if self.effort else []),
            *_granted(
                self._agent.config,
                locked=bool(_locks(self._agent)),
            ),
            *_LEADING.get(_leads(self._agent), ()),
            "stdio",
        ]

    def _restarted(self) -> None:
        """Opens the conversation on the process that has just come up.

        A new process knows nothing yet: it is told what protocol this is, and then either
        opens the session or is handed the one this conversation already has. Done here,
        before the turn writes anything, because `session/prompt` names the session it is a
        turn of -- there is nothing to write until there is one.

        Raises:
          subprocess.CalledProcessError: If the process will not speak the protocol or
            refuses the session, which is a turn that never started.
        """
        self._launched = self._requested
        self._at, self._asked = 0, None
        proc = self._proc
        if proc is None:  # pragma: no cover -- a process is up whenever this is called
            return
        # Nothing is draining the process's other stream yet -- that reader starts once this
        # returns -- so a process that fills that pipe before it answers is one this would
        # wait on forever. Ended instead, which makes it a failed turn rather than a flow
        # that stopped: stdout ends with the process, and stdout is what is read below. The
        # tree rather than the one process, which is what `_ended` is: a launcher killed over
        # a runtime still holding the inherited stdout leaves this read exactly as blocked.
        watchdog = threading.Timer(_HANDSHAKE, _ended, args=(proc,))
        watchdog.daemon = True
        watchdog.start()
        try:
            self._settle(
                proc,
                self._ask(
                    "initialize",
                    {
                        "protocolVersion": _VERSION,
                        "clientCapabilities": _CAPABILITIES,
                        "clientInfo": {"name": "humanize", "version": "1"},
                    },
                ),
            )
            # Absolute, which the protocol requires, and the one the session works in. Loaded
            # rather than opened once this conversation has an id: a process is a transport,
            # and starting another must not start another conversation. A load the agent
            # refuses is refused again on the next try -- the conversation is not there under
            # that id -- so it is said once rather than tried down the whole chain.
            where: dict[str, Any] = {
                "cwd": self._workspace(),
                "mcpServers": [one.sent() for one in _bridged(self._agent)],
            }
            if self._id is not None:
                loaded = self._settle(
                    proc,
                    self._ask("session/load", {"sessionId": self._id, **where}),
                    refused=Unrecoverable,
                )
                self._chooses(proc, self._id, loaded)
                return
            opened = self._settle(proc, self._ask("session/new", where))
            if not (named := str(opened.get("sessionId") or "")):
                raise Failed(1, self._command(), "", f"{_COMMAND} named no session")
            # Taken before the model is chosen, so that a session refused one is loaded by
            # the next try rather than opened again beside it.
            self._adopt(named)
            self._chooses(proc, named, opened)
        finally:
            watchdog.cancel()

    def _chooses(
        self, proc: subprocess.Popen[str], session: str, opened: dict[str, Any]
    ) -> None:
        """Puts the session on a gateway's entry, where it opened on another model.

        `grok agent` 1.0.50 takes `--model` only for a model in the catalogue it fetched from
        the endpoint, and opens on the first of that catalogue otherwise -- which the entry
        :func:`_routed` keeps for a gateway account never is, being hidden. Unseen behind an
        endpoint serving the one model, whose first is that model; traced behind a LiteLLM
        gateway, whose catalogue is every model of its provider, as a session opened on
        whichever of four hundred came first. `session/set_model` takes the entry. Only for
        an entry: a model of the catalogue is one `--model` was taken for, under whatever id
        the session reports it by.

        Args:
          proc: The process now up.
          session: The session it opened or loaded.
          opened: What it answered with, which names the model the session is on.
        """
        models = opened.get("models")
        wanted = self._model()
        if not isinstance(models, dict) or wanted == self._agent.config.model:
            return
        if cast("dict[str, Any]", models).get("currentModelId") in (None, wanted):
            return
        self._settle(
            proc,
            self._ask("session/set_model", {"sessionId": session, "modelId": wanted}),
        )

    def _ask(self, method: str, params: dict[str, Any]) -> int:
        """Writes one request of the protocol's own, which is not a thing said to the agent.

        Args:
          method: What to ask for.
          params: What to ask it with.

        Returns:
          The id the answer will come back under.
        """
        self._at += 1
        self._send(
            json.dumps(
                {"jsonrpc": "2.0", "id": self._at, "method": method, "params": params}
            )
            + "\n"
        )
        return self._at

    def _settle(
        self,
        proc: subprocess.Popen[str],
        at: int,
        *,
        refused: type[Failed] = Failed,
    ) -> dict[str, Any]:
        """Reads until one request is answered, and answers what is asked on the way.

        Args:
          proc: The process now up, whose stdout the answer is coming down.
          at: The id the request went under.
          refused: What to raise where this asking is one whose refusal another try would
            only be refused again.

        Returns:
          What it answered with.

        Raises:
          subprocess.CalledProcessError: If it refused, or stopped writing instead.
        """
        for line in proc.stdout or ():
            said = _parsed(line)
            if said is None:
                continue
            if (method := said.get("method")) is not None:
                if (asked := said.get("id")) is not None:
                    self._answers(
                        asked,
                        str(method),
                        cast("dict[str, Any]", said.get("params") or {}),
                    )
                continue  # everything the turn is told is read by the turn, not here
            if said.get("id") != at:
                continue
            if (why := said.get("error")) is not None:
                raise refused(1, self._command(), "", _why(why))
            return cast("dict[str, Any]", said.get("result") or {})
        # stdout ended instead, so the process is going, and what it said on its way out is
        # the diagnostic. Nobody is draining that stream yet, so it is read here -- briefly,
        # and on a thread, since whatever the agent left holding the write end holds it open.
        raise refused(
            proc.poll() or 1, self._command(), "", _left(proc, self._complaints)
        )

    def _answers(self, at: object, method: str, params: dict[str, Any]) -> None:
        """Answers something the agent asked us, rather than leaving it waiting on us.

        A tool call it asks permission for is answered by whether there is a fence. Under one
        the answer is yes, whatever the fence lets it write: `--always-approve` has already
        approved every tool the process was started with, a request arriving anyway is one a
        hook of Grok Build's own put in front of the client, and the fence is what holds the
        grant. With no fence the flag is not sent, so
        the asking is `grok`'s own and the answer is no -- Humanize, told nothing about this
        agent, does not grant on its behalf: a machine whose `[ui] permission_mode` is left at
        `default` asks tool call by tool call, and answering yes there would be Humanize
        settling what it exists not to settle. Answered either way by the *kind* of the option
        rather than by its id, which is the agent's own word for it.

        No hook is told. The asking is not a moment a flow could be written against: under a
        fence `--always-approve` has settled every tool before one is asked about -- or, where an
        administrator locks it off, every tool is asked about and granted alike -- and a turn
        that falls to `grok -p` has no client to ask at all, so a hook hung on it would be one
        that looked held and was never called (Section 4.9.1.3 of the protocol).

        Args:
          at: The id it asked under.
          method: What it asked for.
          params: What it asked with, which carries the options for a permission.
        """
        if method == "session/request_permission":
            granted = self._agent.config.fence is not None
            self._send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": at,
                        "result": {"outcome": _permits(params, granted=granted)},
                    }
                )
                + "\n"
            )
            if not granted:
                # Remembered so that the turn this ends says who ended it. Grok answers a
                # refused prompt with `stopReason: cancelled` and nothing about why, and a
                # flow told only that is a flow reading a refusal as the CLI misbehaving.
                self._refused = "Humanize did not permit a tool call"
            return
        # Everything else is something this client said it could not do, and an agent asking
        # anyway is told so in the protocol's own words rather than left waiting.
        self._send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": at,
                    "error": {
                        "code": -32601,
                        "message": f"Humanize offers no {method}",
                    },
                }
            )
            + "\n"
        )

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one turn as the `session/prompt` that takes it.

        Args:
          text: The prompt for this turn.
          ticket: Unused: nothing is put into a turn already running here, so there is
            nothing for the agent to name what it was told by.

        Returns:
          The request, as the line to write.
        """
        del ticket
        self._at += 1
        self._asked = self._at
        return (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self._at,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": self._id,
                        "prompt": [{"type": "text", "text": text}],
                    },
                }
            )
            + "\n"
        )

    def interject(self, text: str) -> None:
        """Says nothing to a turn already running: the protocol queues it as another turn.

        Args:
          text: What would have been said.

        Raises:
          NotImplementedError: Always. A second `session/prompt` is a second turn, answered
            on its own once this one is over, and a flow told that was a word put into the
            turn it is watching would be watching the wrong thing.
        """
        SessionBase.interject(self, text)

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one line Grok Build wrote on the protocol, as what it says the agent did.

        Args:
          line: The line, as written.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        said = _parsed(line)
        if said is None:
            return
        if (method := said.get("method")) is not None:
            # Both the protocol's own `session/update` and the notifications Grok Build adds
            # beside it carry the same update, so what is in it is what this reads rather
            # than which of the two it came under.
            yield from self._told(cast("dict[str, Any]", said.get("params") or {}))
            if (asked := said.get("id")) is not None:
                self._answers(
                    asked, str(method), cast("dict[str, Any]", said.get("params") or {})
                )
            return
        if said.get("id") != self._asked:
            return  # an answer to something else, which this turn is not waiting on
        self._asked = None
        # And whatever the last response held back: nothing follows it to close it, the thing
        # that ends it being the turn's own answer, and words held back for a boundary that
        # never came are words the turn would swallow.
        yield from self._saying.rest()
        yield self._answered(said)

    def _told(self, params: dict[str, Any]) -> Iterator[Event]:
        """Reads one update of a running turn.

        Args:
          params: What the notification carried.

        Yields:
          What it said, which is nothing for an update saying nothing worth showing.
        """
        update = cast("dict[str, Any]", params.get("update") or {})
        kind = str(update.get("sessionUpdate") or "")
        if kind == "tool_call":
            # A call the agent gave no id is shown as it comes: there is nothing to tell it
            # from the next one, and folding them all onto one blank id would show the first
            # and silently drop every call after it.
            marked = str(update.get("toolCallId") or "")
            if not marked or marked not in self._shown:
                self._shown.add(marked)
                # What it said before reaching for something is what says why it reached.
                yield from self._saying.upto()
                yield Event(kind="tool", text=_called(update))
        elif kind == "response_completed":
            # Told as each response lands rather than once the run is over, which is what a
            # rate read while the turn is still running is made of. The answer the turn ends
            # on carries the same spending added up, so only these are counted.
            self._costing = self._costing + self._cost(
                cast("dict[str, Any]", update.get("usage") or {})
            )
            # And a response that has been counted is a response that has finished saying
            # what it had to say, so this is where its words are whole.
            yield from self._saying.ended()
        elif (says := _TOLD.get(kind)) is not None:
            words = str(
                cast("dict[str, Any]", update.get("content") or {}).get("text") or ""
            )
            if words:
                if says == "text":
                    self._said.append(words)
                # Gathered rather than said: the protocol sends an answer a fragment at a
                # time, and a fragment shown on its own is one row of a transcript a word.
                self._saying.delta(says, words)

    def _answered(self, said: dict[str, Any]) -> Event:
        """The turn's answer, out of what `session/prompt` came back with.

        Args:
          said: The answer, as read.

        Returns:
          The `result` the turn ends on, or the `failed` that says it did not answer -- which
          a turn that returned it as its text would be running on as the work of the turn.
        """
        if (why := said.get("error")) is not None:
            return Event(kind="failed", text=_why(why))
        result = cast("dict[str, Any]", said.get("result") or {})
        if (why := str(result.get("stopReason") or "")) not in _ANSWERED:
            # Whose refusal it was, where it was this client's. 1.0.24 ends a turn whose tool
            # call was refused on `cancelled` and says nothing about who refused it, which
            # reads exactly like the CLI giving up -- so what this client said no to and why
            # is put back into the diagnostic the flow actually sees.
            because = f": {self._refused}" if self._refused else ""
            return Event(
                kind="failed", text=f"{_COMMAND} ended the turn on {why}{because}"
            )
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text="".join(self._said).strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `grok -p` a shaped turn, a fork or a turn the process cannot carry is.

        `streaming-json` rather than the `plain` the CLI defaults to, and rather than the
        `streaming-messages-json` beside it: `plain` is the answer with nothing said about
        how it was arrived at, and the Anthropic-shaped one is somebody else's wire format
        wrapped round the same turn. `streaming-json` is what the help calls `the agent's
        native format` -- the protocol's own `session/update` with `sessionUpdate` flattened
        onto `type` and the words moved onto `data` -- so the two transports here are one
        stream said twice, which is why :meth:`_reads` and :meth:`_told` read the same turn.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and None because the prompt is inside it: Grok Build does not read a
          piped stdin as the prompt.
        """
        self._said, self._failed, self._shown = [], None, set()
        self._costing, self._saying, self._refused = Usage(), Saying(), None
        self._locked_out = ""
        config = self._agent.config
        argv = [
            _COMMAND,
            "--output-format",
            "streaming-json",
            "--model",
            self._model(),
            "--effort",
            self.effort,
            *_granted(config),
        ]
        # Decided by the network alone, whatever the fence lets the agent write. `is False`
        # rather than `not`, inside `_searches`, since None is the agent nobody was asked
        # about and `not None` is true: an agent nothing was said about would otherwise be
        # told not to search the web, which is Humanize settling the one thing it was meant to
        # leave alone.
        if not _searches(config):
            argv.append(_NO_WEB)
        argv += _extras(config)
        if (schema := self._shaping) is not None:
            # Held as Codex's models hold one, closed and every property required: a grok
            # account behind a gateway runs a model that refuses a structured output that is
            # not, and every model takes one that is.
            from .codex import strict

            argv += ["--json-schema", json.dumps(strict(schema.model_json_schema()))]
        if self._id is not None:
            argv += ["--resume", self._id]
        elif self._forked_from is not None:
            # A resume told to mint an id rather than reuse the one it was handed: the turns
            # of the conversation this one was cut from come with it, and what follows is its.
            argv += ["--resume", self._forked_from, "--fork-session"]
        # Written onto the flag rather than after it: a prompt is a paragraph and may open
        # with a dash, and a value given with an `=` is a value whatever it starts with.
        return [*argv, f"--single={prompt}"], None

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line a run of Grok Build wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is its own log rather than the turn --
            kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            if _LOCKED in line and self._agent.config.fence is not None:
                self._locked_out = line.strip()
            return
        said = _parsed(line)
        if said is None:
            return
        if self._id is None and (named := said.get("sessionId")):
            # Named on the line a run ends on, and on no earlier one: the run's from there,
            # whether or not the turn lands.
            self._tells(str(named))
        kind = str(said.get("type") or "")
        if kind == "error":
            self._failed = str(said.get("message") or "") or json.dumps(said)
        elif kind == "tool_call":
            marked = str(said.get("toolCallId") or "")
            if not marked or marked not in self._shown:
                self._shown.add(marked)
                # What it said before reaching for something is what says why it reached.
                yield from self._saying.upto()
                yield Event(kind="tool", text=_called(said))
        elif kind == "usage":
            self._costing = self._costing + self._cost(
                cast("dict[str, Any]", said.get("usage") or {})
            )
            # And a response that has been counted is a response that has finished saying
            # what it had to say, so this is where its words are whole.
            yield from self._saying.ended()
        elif kind == "end":
            # A turn that ended without a count for its last response still said it.
            yield from self._saying.rest()
        elif (says := _SAYS.get(kind)) is not None:
            words = str(said.get("data") or "")
            if words:
                if says == "text":
                    self._said.append(words)
                self._saying.delta(says, words)

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What one response cost, by the kind each token went on.

        Every kind counts: what a rate is measuring is the traffic, and a cache read crosses
        the wire like anything else. The input count is the uncached part alone here, which is
        why the two cache counts are added rather than folded into it.

        Args:
          counted: A `usage`, as read.

        Returns:
          What it spent.
        """
        return Usage(
            {
                kind: float(counted.get(named) or 0)
                for kind, named in _KINDS.items()
                if counted.get(named)
            }
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the lines a run wrote.

        Args:
          transcript: The whole of stdout, already read line by line.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. Grok Build says so on a line of
            its own as well as in its exit status, and a loop fed that as an answer would be
            running on it as the work of the turn.
        """
        said = "".join(self._said)
        if self._locked_out:
            raise Unrecoverable(
                1,
                [_COMMAND],
                said,
                f"{self._locked_out}: a fenced `{_COMMAND} -p` turn had nobody to grant "
                "what it asked, which a policy on this machine put to approval",
            )
        if self._failed is not None:
            raise Failed(1, [_COMMAND], said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text=said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session a run of Grok Build opened, which the line it ends on names.

        Only that line: the stream has no preamble, so the id is not there to be read until
        the turn is over.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The session's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            said = _parsed(line)
            if said is not None and (named := said.get("sessionId")):
                return str(named)
        raise ValueError(f"{_COMMAND} named no session")


def _left(proc: subprocess.Popen[str], held: list[str]) -> str:
    """What a process that has stopped writing said on its way out.

    Read on a thread and waited on only briefly: a stream is spent when every holder of its
    write end has let go of it, and a backend that started a daemon of its own handed that
    end to the daemon -- so reading to the end of it is a wait on that rather than on this.

    Args:
      proc: The process, whose stderr nobody is draining yet.
      held: What it has complained of so far, which this adds to.

    Returns:
      The whole of it, as the diagnostic of a turn that never started.
    """

    def reading() -> None:
        with contextlib.suppress(OSError, ValueError):
            if proc.stderr is not None:
                held.append(proc.stderr.read())

    reader = threading.Thread(target=reading, daemon=True)
    reader.start()
    reader.join(timeout=_WAITING)
    return "".join(held).strip()


def _permits(params: dict[str, Any], *, granted: bool) -> dict[str, Any]:
    """Answers a tool call, by the kind of the option rather than by its name.

    Args:
      params: What was asked, which carries the options the agent offers.
      granted: Whether Humanize says yes: under a fence. Where it does not, the asking is
        the CLI's own, and so is the tool that does not run.

    Returns:
      The outcome to answer with: the best option of the kind called for, and a
      cancellation where the agent offered nothing of that kind. Answered either way, and
      never left, because a `session/request_permission` nobody answers is a turn that waits
      until the watchdog puts the process down -- which is a worse outcome than a refusal,
      a refused tool being something a flow can read and a wedge being nothing at all.
    """
    offered = [
        cast("dict[str, Any]", one)
        for one in cast("list[Any]", params.get("options") or [])
        if isinstance(one, dict)
    ]
    chosen = next(
        (
            one
            for kind in (_GRANTS if granted else _REFUSES)
            for one in offered
            if one.get("kind") == kind
        ),
        None,
    )
    if chosen is None and granted:
        # Whatever was offered, an agent that named no kind this client knows being better
        # answered with one of its own options than with none. Only where it is granted:
        # the first option of a list is the agent's own best answer, which every 1.0.24
        # request starts with an `allow_always`, and a refusal that fell through to it would
        # be a no said as a yes. Never an `always` either way, which is a rule written down.
        chosen = next(
            (one for one in offered if not str(one.get("kind", "")).endswith(_ALWAYS)),
            None,
        )
    if chosen is None:
        return {"outcome": "cancelled"}
    return {"outcome": "selected", "optionId": str(chosen.get("optionId"))}


def _parsed(line: str) -> dict[str, Any] | None:
    """One line of either stream as the object it carries, or None for one that is not ours.

    Args:
      line: The line, as written.

    Returns:
      What it says, or None for the odd plain line among the JSON.
    """
    try:
        said: object = json.loads(line)
    except ValueError:
        return None
    return cast("dict[str, Any]", said) if isinstance(said, dict) else None


def _why(error: object) -> str:
    """What a refusal on the protocol says, as the diagnostic of a turn that never ran.

    Args:
      error: The `error` member, as read.

    Returns:
      Its message, or the whole of it where it carries none.
    """
    if isinstance(error, dict):
        message = cast("dict[str, Any]", error).get("message")
        if message:
            return str(message)
    return json.dumps(error)


def _called(said: dict[str, Any]) -> str:
    """One tool call as the one line a row of a transcript has room for.

    Named by the tool, and said by whatever else the call carries: the protocol writes the
    name as the call's title and a run of the command line writes it twice, so a title that
    is only the name again is not the thing it was called with.

    Args:
      said: The `tool_call`, as read on either transport.

    Returns:
      What it reached for and what with.
    """
    # What a call was given is the agent's own to shape, and a turn must not fail on the
    # shape of a line it was only going to show: anything but an object carries no names.
    raw: object = said.get("rawInput")
    given = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    named = str(said.get("toolName") or said.get("title") or said.get("kind") or "tool")
    about = next(
        (
            str(value)
            for value in (said.get("title"), *given.values())
            if isinstance(value, str) and value.strip() and value != named
        ),
        "",
    )
    return f"{named} {about}".strip()[:120]


def _fenced(agent: AgentBase, config: AgentConfig) -> bool:
    """Whether an agent at this config is put inside ``hmz internal fence`` as it is spawned.

    Args:
      agent: The agent, which says what of a fence its CLI holds itself.
      config: What it is to run at.

    Returns:
      Whether there is a fence and something of it is left for the wrapper to hold.
    """
    return config.fence is not None and not agent.natively(config.fence).open


def _locks(agent: AgentBase) -> str:
    """Where always-approve is locked off for this agent, or "" for one it is not or no grok.

    Args:
      agent: The agent a conversation is of.

    Returns:
      What :meth:`GrokBuildAgent.locks` says.
    """
    return agent.locks() if isinstance(agent, GrokBuildAgent) else ""


def _searches(config: AgentConfig) -> bool:
    """Whether a turn at this config is let keep its web tools, rather than told to drop them.

    Not where the agent was told not to search -- `is False` rather than `not`, the web being
    three answers and None the agent nobody was asked about, which is said with no flag at all
    -- and not where the fence it was given cuts the network, whatever `web_search` says. Its
    `web_search` may be xAI's own search, run at the model's host rather than from this
    machine, which is a host the fence leaves open: the proxy would let the search through, so
    the tool is taken away instead. Asked of the fence as it was written, before the hosts the
    CLI needs are let through, since those are exactly where such a search would go.

    Args:
      config: What the agent is to run at.

    Returns:
      Whether nothing says to disable its web tools.
    """
    offline = config.fence is not None and not config.fence.online
    return config.web_search is not False and not offline


def _leads(agent: AgentBase) -> bool | None:
    """What the held-open process is told about the leader.

    What the agent was set up with, except that a fenced one is never left to the person's
    `[cli] use_leader`: a leader is a process started outside the fence, and a conversation
    that joined it would run its tools there. One set up to join it outright never gets this
    far, :meth:`GrokBuildAgent._serves` having refused it.

    Args:
      agent: The agent whose conversation this is.

    Returns:
      The key into :data:`_LEADING`.
    """
    config = agent.config
    leader: bool | None = getattr(config, "leader", False)
    return False if _fenced(agent, config) else leader


#: The flags :func:`_extras` writes, without what each is given.
_EXTRAS = ("--sandbox", "--max-turns", "--no-subagents", "--rules")


def _extras(config: AgentConfig) -> list[str]:
    """What this agent was set up with that only the top-level command line carries.

    The one place those four are turned into flags, so that :meth:`GrokBuildSession._turn`
    writes them and :meth:`GrokBuildSession._commanded` can ask whether there are any without
    the two answers ever drifting apart.

    Read with `getattr` rather than off the class, since an agent may be built from the common
    config rather than from Grok Build's own -- and every one of these is absent by default,
    which is the bare CLI's own behaviour: an install that sets nothing adds no flag.

    Args:
      config: What the agent's turns run at.

    Returns:
      The flags to add, in the order the help lists them, and nothing at all for an agent
      that was asked for none of them.
    """
    argv: list[str] = []
    if profile := str(getattr(config, "sandbox", "") or ""):
        argv += ["--sandbox", profile]
    if turns := int(getattr(config, "max_turns", 0) or 0):
        argv += ["--max-turns", str(turns)]
    if not getattr(config, "subagents", True):
        argv.append("--no-subagents")
    if rules := str(getattr(config, "rules", "") or ""):
        argv += ["--rules", rules]
    return argv


def _routed(
    model: str, environ: Mapping[str, str]
) -> tuple[str, dict[str, Any] | None]:
    """The name a turn asks for `model` by, under an account's environment, and its entry.

    An account behind a gateway is told which API to speak by a `[model.*]` entry, there
    being nowhere else 1.0.46 reads an `api_backend` from -- so the entry is written, into
    the `config.toml` of the virtual home this turn's CLI is started in
    (:meth:`GrokBuildSession._spawning`), and the turn asks for it rather than for the model.
    The entry names the variable the key is in rather than the key, which is what keeps a
    secret off a disk it was never meant for. The headers Anthropic's API wants
    besides are not the entry's to carry: :meth:`GrokBuildAgent.environment` says why.

    Named for what it holds, so that the same endpoint, model and API are always the same
    entry, and a process started again asks for the one it asked for before. Hidden, being
    Humanize's rather than something the person at this machine picked: `-m` still reaches
    it, and the picker does not show it.

    Args:
      model: The model, as the endpoint names it.
      environ: The environment the turn runs under.

    Returns:
      The entry's name and the entry, or `model` itself and None for an account that is not
      behind a gateway.

    Raises:
      Unrecoverable: If the account names an API Grok Build has no word for, which it would
        otherwise drop the entry over and refuse the model as one it does not know -- and a
        sentence `signs` reads as a busy catalogue, waited on and tried again for nothing.
    """
    speaks = environ.get(_SPEAKS, "").strip()
    base = environ.get(_AT, "").strip()
    if not speaks or not base:
        return model, None
    if speaks not in _APIS:
        said = f"{_SPEAKS} is {speaks!r}, which is none of {', '.join(sorted(_APIS))}"
        raise Unrecoverable(1, [_COMMAND], "", said)
    entry: dict[str, Any] = {
        "model": model,
        "base_url": base,
        "api_backend": speaks,
        "env_key": _KEY,
        "hidden": True,
    }
    said = json.dumps(entry, sort_keys=True).encode()
    return f"hmz-{hashlib.sha256(said).hexdigest()[:12]}/{model}", entry


@merger
def _entered(home: Path, said: dict[str, Any]) -> None:
    """Puts one `[model.*]` entry into a virtual home's copy of a Grok Build `config.toml`.

    The copy is the process's own, so it is written outright; what the user wrote in their
    file -- their comments and their order among it -- is kept in it all the same.

    Args:
      home: The virtual home, whose copy is not there for a user with no file of their own.
      said: `named`, the entry's name, and `entry`, what it holds.

    Raises:
      Unrecoverable: If the file is there and is not TOML, which Grok Build would refuse
        too: it is somebody's to correct.
    """
    import tomlkit

    at = home / "config.toml"
    doc = _reading(at)
    if "model" not in doc:
        doc["model"] = tomlkit.table(is_super_table=True)
    cast("dict[str, Any]", doc["model"])[said["named"]] = said["entry"]
    at.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _reading(at: Path) -> tomlkit.TOMLDocument:
    """A Grok Build `config.toml` as TOML that keeps its comments, and an empty one if none.

    Raises:
      Unrecoverable: If the file is there and is not TOML: see :func:`_entered`.
    """
    import tomlkit
    from tomlkit.exceptions import TOMLKitError

    try:
        return tomlkit.parse(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return tomlkit.document()
    except (TOMLKitError, UnicodeDecodeError) as error:
        said = f"{at} cannot be read as TOML ({error}): correct it"
        raise Unrecoverable(1, [_COMMAND], "", said) from error


def _overlaid(theirs: str, headers: Mapping[str, str]) -> str:
    """A `GROK_CONFIG` overlay sending `headers` with every request, over one already set.

    Args:
      theirs: The overlay the environment already holds, or "" for none. One that is not a
        JSON object is one Grok Build would ignore with a warning, and is replaced here.
      headers: What to send.

    Returns:
      The overlay, as the JSON object `GROK_CONFIG` takes: theirs, with `[models]
      extra_headers` holding these over whatever it held.
    """
    try:
        held: object = json.loads(theirs) if theirs.strip() else {}
    except ValueError:
        held = {}
    overlay = cast("dict[str, Any]", held) if isinstance(held, dict) else {}
    models = overlay.get("models")
    models = cast("dict[str, Any]", models) if isinstance(models, dict) else {}
    sent = models.get("extra_headers")
    sent = cast("dict[str, Any]", sent) if isinstance(sent, dict) else {}
    overlay["models"] = models | {"extra_headers": sent | dict(headers)}
    return json.dumps(overlay)


@dataclass(frozen=True, kw_only=True)
class GrokBuildAgentConfig(AgentConfig):
    """What Grok Build is configured with: the common model and effort, and five of its own.

    The model is written as Grok Build writes it, which is a name out of its own catalogue --
    `grok models` is what lists them.

    Every one of the five is off by default, and off means the flag is not written at all: an
    install that says nothing here runs exactly the command line the bare CLI runs. Four of
    them are the top-level command's, which is the transport a shaped turn, a fork and a fence
    that writes nothing already go to -- so naming one of them sends *every* turn of the
    conversation that way rather than applying to some turns and not others. That is the
    whole reason they are gathered in :func:`_extras` and asked about in `_commanded`.

    Three more of Grok Build's own are deliberately not here. `--include-partial-messages` says
    of itself that it `Only affects --output-format streaming-messages-json`, and these turns
    are read as `streaming-json`, so it is a switch that would do nothing whichever way it was
    set. `--agent-profile` and `--plugin-dir` are the mirror of the four below: they exist on
    `grok agent` and not on the top-level command, so an agent given one would keep it for its
    ordinary turns and silently lose it for every shaped, forked or tool-withheld one -- and a
    setting that holds for some turns of a conversation and not others is worse than one that
    was never offered.

    Attributes:
      leader: Whether this conversation's held-open process joins the leader -- one backend
        shared by every client that asks for it -- or starts one of its own. False starts its
        own, which is what Humanize has always done and what keeps a run reproducible: a
        `use_leader = true` in the `~/.grok/config.toml` of whoever is at this machine would
        otherwise put every session of a flow on one backend. True joins it, and None leaves
        the question to that config file, which is the bare CLI's own answer. It is a setting
        of the process the protocol is held open on, so a conversation every turn of which
        falls to the command line never reaches it.
      sandbox: The sandbox profile a turn's filesystem and network access is confined by, by
        the name `--sandbox` takes, or "" for the CLI's own -- which is none. Grok Build has
        no built-in ladder of profiles to pick from: `workspace` is a base to extend, and a
        profile is otherwise a `[profiles.<name>]` in the `sandbox.toml` of whoever is at this
        machine. So it is named here rather than being what a grant is made of: writing a
        profile to hold a grant would be Humanize writing the CLI's own settings, and the
        fence holds it in any case.
      max_turns: How many turns of its own one run may take under this turn, or 0 for as many
        as it takes, which is the CLI's own answer. Its own setting rather than anything
        :class:`~hmz.coganchor.agents.config.Budget` reaches: a budget is per turn of *this*
        conversation and is held to here, off the meter every backend feeds, rather than
        handed to a CLI at all -- and rerouting it onto a flag only some backends have would
        make a cap that read the same and counted something else.
      subagents: Whether the agent may start agents of its own. True is the CLI's own answer;
        False is `--no-subagents`, for a flow that wants the work done by the one agent it is
        watching rather than by a fleet under it.
      rules: Extra rules appended to the system prompt, as `--rules` takes them, or "" for the
        prompt Grok Build builds itself. Appended rather than replacing: `--system-prompt-
        override` is the other flag and is not this one.
    """

    leader: bool | None = False
    sandbox: str = ""
    max_turns: int = 0
    subagents: bool = True
    rules: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        # Said where it is written rather than by a CLI refusing the argv minutes later, which
        # is a turn that never started for a number nobody looked at.
        if self.max_turns < 0:
            raise ValueError("max_turns cannot be less than nothing")


class GrokBuildAgent(AgentBase):
    """Grok Build, driven through the protocol it serves, one process per conversation."""

    #: What it counts, read off the same table its driver reads a usage with, so that what
    #: a run is told this backend reports is what its driver actually parses.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    # No moment beyond every backend's. `grok agent` can put a tool call to its client as
    # `session/request_permission`, and that is answered (`GrokBuildSession._answers`) but is
    # not a moment: a fenced conversation is started with `--always-approve`, which settles
    # every tool before one is asked about, and a turn taken with `grok -p` has no client to
    # ask. A hook there would be one a flow could hang and never hear from. Where an
    # administrator locks always-approve off, every request does come to the client, and is
    # granted as `--always-approve` would have granted it.

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent that has said nothing yet of a lock on always-approve.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        #: Whether it has been said that this agent runs asking (Section 4.6.2 of the protocol
        #: has that said once per agent).
        self._noted = False
        self._noting = threading.Lock()
        #: What locks always-approve off on this machine, once asked (:meth:`locks`).
        self._probed: str | None = None

    def environment(self) -> Mapping[str, str]:
        """The provider's variables, and the one that has Grok Build read a project's skills.

        Grok Build 1.0.46 reads a project's skills only out of a folder it was told to trust,
        which a workspace a flow runs in has never been: the skills the workspace keeps under
        `.grok/skills` or `.agents/skills` were there and never seen. `GROK_FOLDER_TRUST=0`
        takes the question away, as a workspace Humanize was told to work in is trusted
        already. The flow's own skills need no trust: they are at the user level, in the
        virtual home each process is started in.

        And for an account behind an Anthropic-shaped gateway, the two headers that API asks
        for: the key as `x-api-key` and the version it answers in. Said in the `GROK_CONFIG`
        overlay rather than on the account's `[model.*]` entry, because 1.0.46 applies a
        model's own `extra_headers` and `env_http_headers` to a `grok -p` run and drops both on
        `grok agent stdio` -- traced against a recording endpoint, where the held-open
        process sent neither and the command line both. The overlay's `[models]
        extra_headers` reaches both transports. It holds the key itself, which is where that
        table takes a value from, and is a variable rather than a file: the key is in this
        process's environment as `XAI_API_KEY` already, and nothing here writes it down. A
        `GROK_CONFIG` the turn would have had anyway is kept, with these laid over it -- which
        under an account is none, the overlay being hushed like anything else that can carry
        one. Never for an agent on another machine, whose commands there would inherit it:
        :meth:`GrokBuildSession._model` refuses that turn instead.

        And for an account a local LiteLLM gateway holds, the gateway as an endpoint speaking
        chat completions: the one protocol it speaks to every provider behind it, where
        `responses`, the gateway way's own answer, is one it speaks to some.

        Returns:
          The variables to add.
        """
        added = {**super().environment(), "GROK_FOLDER_TRUST": "0"}
        if self.gateway is not None:
            added[_SPEAKS] = "chat_completions"
        hushed = self.hushed()
        said = {k: v for k, v in os.environ.items() if k not in hushed} | added
        key = said.get(_KEY, "")
        speaks = said.get(_SPEAKS, "").strip()
        if (
            self.config.machine is None
            and speaks == "messages"
            and said.get(_AT)
            and key
        ):
            added["GROK_CONFIG"] = _overlaid(
                said.get("GROK_CONFIG", ""),
                {"x-api-key": key, "anthropic-version": _DATED},
            )
        return added

    def _serves(self, config: AgentConfig) -> None:
        """Refuses what the base class refuses, and a fenced agent set up to join the leader.

        The leader is one backend process shared by every client that joins it, started by
        whichever came first and reached over a Unix socket, which the fence does not govern.
        A conversation that joined it would be a fenced client handing its tools to a process
        outside the fence. Left unsaid, the question is answered `--no-leader` for a fenced
        agent (:func:`_leads`); said outright, it is refused rather than overruled.

        Args:
          config: What the agent is to run at.

        Raises:
          Unserved: For whatever the base class refuses.
          Unfenced: If the agent is fenced and set up to join the leader.
        """
        super()._serves(config)
        if getattr(config, "leader", False) is True and _fenced(self, config):
            raise Unfenced(
                f"{type(self).__name__}: a fenced conversation cannot join the leader, "
                "which runs its tools outside the fence; set leader to False or None"
            )

    def locks(self) -> str:
        """Where always-approve is locked off for this agent, if anything locks it.

        Asked only for an agent hmz fences, which is the one it would approve, and only on this
        machine, whose `grok` is the one asked (:func:`_locked`); a `grok` on another machine
        says so on the run instead (:data:`_LOCKED`).

        Returns:
          The source of the lock, or "" where there is none.
        """
        if self.config.fence is None or self.config.machine is not None:
            return ""
        if self._probed is None:
            self._probed = _locked()
        return self._probed

    def _admits(self) -> None:
        """Refuses a fenced agent that only `grok -p` can run, where always-approve is locked.

        `grok -p` has no client to ask, so under the lock a tool call it would ask about is
        refused in a turn that still answers. A fence that writes nothing and a shape move to
        the protocol; a fork is refused as it is cut (:meth:`GrokBuildSession.fork`); web
        search switched off and the settings :func:`_extras` writes are said nowhere else, and
        an agent set up with them is refused here, before a session opens.

        Raises:
          Unserved: If the lock is there and the agent needs `grok -p` for every turn.
        """
        config = self.config
        needs = ([] if _searches(config) else [_NO_WEB]) + [
            flag for flag in _extras(config) if flag in _EXTRAS
        ]
        if needs and (locked := self.locks()):
            raise Unserved(
                f"{type(self).__name__}: always-approve is locked off by {locked}, and "
                f"{', '.join(needs)} is said only on `{_COMMAND} -p`, where nothing can "
                "grant a tool call"
            )

    def _first_locked(self) -> bool:
        """Notes that this agent has been told it runs asking, under the lock.

        Returns:
          Whether this is the first time, and so something to say.
        """
        with self._noting:
            first, self._noted = not self._noted, True
            return first

    def new(self, cwd: str | os.PathLike[str] | None = None) -> GrokBuildSession:
        """Opens a new Grok Build session, in the directory it is given or in this one.

        Raises:
          Unserved: For an agent that cannot run where always-approve is locked off
            (:meth:`_admits`).
        """
        self._admits()
        return GrokBuildSession(self, cwd)
