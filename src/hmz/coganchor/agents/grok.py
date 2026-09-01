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
argument` -- so a rung that takes tools away, an agent told not to search the web, a turn held
to a shape and four of the five settings on `GrokBuildAgentConfig` are settings only `grok -p`
carries. Those run the command they always did, resuming the same conversation with
`--resume` -- the id is Grok Build's own either way, and each transport picks up what the
other opened. Nothing is served looser for the transport's sake: what moves is which of the
two a turn is taken on.

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
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import json
import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

# What the protocol says a thing is, what a client may do, how a tool call is permitted and
# what ends a turn having answered are the protocol's rather than Grok Build's, so they are
# taken from the ACP client every such CLI here is driven through rather than said again.
from .acp import _ANSWERED, _CAPABILITIES, _GRANTS, _VERSION
from .acp import _SAYS as _TOLD
from .base import (
    AgentBase,
    CommandSessionBase,
    SessionBase,
    StreamSessionBase,
    _ended,
)
from .config import AgentConfig
from .event import Event, Failed, Saying, Unrecoverable, Usage

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Iterator

    from pydantic import BaseModel

#: What the CLI is installed as.
_COMMAND = "grok"

#: Everything is approved without being asked, at every rung: nobody is at a prompt here, and
#: a turn waiting on an approval is a flow that stopped. `--always-approve` rather than
#: `--yolo`, which is a hidden alias for it that `grok agent` still takes and neither command
#: documents: a spelling the help does not list is one release away from disappearing, and
#: this one is the same flag under the name Grok Build actually publishes.
_APPROVAL = "--always-approve"

#: The one flag on that list a turn told not to search the web is given, which Grok Build
#: documents as exactly that -- `Disable web search and web fetch tools`. It says what
#: `--disallowed-tools web_search,web_fetch` said before it and says it in one word: run
#: against 1.0.24 the two leave the same 25 tools in the process, the whole list less those
#: two, so the general flag was spelling out what the CLI has a name for.
_NO_WEB = "--disable-web-search"

#: What a turn at each rung of the ladder is run as, said as the command line says it.
#:
#: Grok Build's own `--permission-mode` is deliberately not among them, and that is the
#: finding this table is written around. It has six modes -- `default`, `acceptEdits`,
#: `auto`, `dontAsk`, `bypassPermissions`, `plan` -- and on 1.0.24 a headless `grok -p` run
#: at every one of them, `plan` included, ran the same `echo`, wrote the same file into the
#: workspace and wrote the same file outside it. A mode governs how the permission *rules*
#: this machine has are applied, and a machine with no rules -- which is what `grok inspect`
#: reports of a fresh one -- has nothing for a mode to apply; headless has nobody to ask, so
#: what is left is approved. Naming a mode would be a rung that looks enforced and enforces
#: nothing, which is the one way a rung must not fail.
#:
#: So a rung here is made of what actually bites: the tools the process is started with. An
#: allowlist for the rung that may change nothing, since a tool the process was not started
#: with cannot run at all -- `--tools read_file,grep,list_dir` leaves five tools in the
#: process, those three and the two by which an MCP server is looked up, and a turn asked to
#: write a file under it reaches four times and writes nothing. `--disable-web-search` above
#: it, where what is taken away is the reaching outside the workspace, Grok Build having no
#: sandbox of its own until somebody writes a profile for it.
_PERMITTED = {
    "read-only": (_APPROVAL, "--tools", "read_file,grep,list_dir"),
    "workspace-write": (_APPROVAL, _NO_WEB),
    "auto": (_APPROVAL,),
    "bypass": (_APPROVAL,),
}

#: The rungs the held-open transport can serve, which is every rung whose whole saying is a
#: flag `grok agent` takes -- and of the three above only `--always-approve` is: `--tools` and
#: `--disable-web-search` are both refused there outright, `error: unexpected argument`.
#:
#: A rung outside this set is not refused, though, the way a backend with no way of saying it
#: at all refuses one. It falls to the command line, which says it exactly and resumes the
#: same conversation, so what moves is which transport the turn is taken on rather than what
#: the agent is allowed. Nothing here is a rung quietly served a rung looser.
_HELD_OPEN = frozenset(
    rung for rung, said in _PERMITTED.items() if set(said) <= {_APPROVAL}
)

#: What each answer to the leader question is said with, and why there are three of them.
#: A leader is one backend process shared by every client that asks for it, and which a
#: `grok agent` joins is not its own choice: it follows `[cli] use_leader` in the
#: `~/.grok/config.toml` of whoever is at this machine. So `--no-leader` is the answer
#: humanize has always given, and goes on giving unless it is told otherwise -- a flow whose
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

        A shape, a rung that takes tools away and everything :func:`_extras` writes are
        settings of `grok -p` and of nothing else: `grok agent` has a flag for none of them,
        so a turn that needs one is a run of the command line rather than a line written to
        the process. The conversation is not ended by that -- the run resumes it, and the
        process the next ordinary turn starts loads it back.

        So is the first turn of a conversation cut from another. The protocol opens a session
        or loads one by id and has no third call; `--fork-session` is the command line's, and
        it is what mints the id this conversation is from then on. One turn that way, and the
        turns after it are ordinary ones on the process that loads what it minted.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, or None to take what the agent says.

        Yields:
          What the agent said, and the answer it ended on.
        """
        if schema is not None or self._commanded() or self._forking():
            with self._lock:
                self._shut()
                # The finite command transport checks the process's exit status after its
                # result too. Reuse it on this same session state: a helper session would
                # register a second conversation and count its opening twice.
                yield from CommandSessionBase._stream(  # noqa: SLF001 -- shared turn transport
                    cast("CommandSessionBase", self), prompt, schema=schema
                )
            return
        with self._lock:
            self._requested = self._settings()
            self._said, self._failed, self._shown = [], None, set()
            self._costing, self._saying = Usage(), Saying()
            try:
                yield from super()._stream(prompt)
            except BaseException:
                # A process that failed a turn is a process whose state nobody here can
                # account for. The conversation survives it: the next turn loads the session
                # back onto a process started afresh.
                self._shut()
                raise

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
          Whether the rung takes a tool away, the agent is told not to search the web, or any
          of the settings only the top-level command has been asked for -- a sandbox profile,
          a cap on the turns under this one, subagents switched off, rules to append. Every
          one of them is refused by `grok agent` with `error: unexpected argument`, and an
          agent given one that the transport could not carry would be a setting that lies.
        """
        config = self._agent.config
        return bool(
            config.permission not in _HELD_OPEN
            or not config.web_search
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
        )

    def _stale(self) -> bool:
        """Restarts before settings or mounted flow resources change."""
        return self._launched is not None and self._launched != self._requested

    def _command(self) -> list[str]:
        """The `grok agent stdio` this conversation is held open on.

        The rung goes on whole rather than as the approval alone: `_HELD_OPEN` is derived
        from which rungs say nothing `grok agent` would refuse, and a turn at any other one
        never reaches this transport at all -- :meth:`_stream` has already sent it to the
        command line. So whatever the rung says here is a flag this process takes.

        Returns:
          The command, carrying what the protocol's process is configured by: the model, how
          hard to think, the approval a flow watching its agent gives once rather than per
          tool call, and what it was told about the leader.
        """
        return [
            _COMMAND,
            "agent",
            "--model",
            self._agent.config.model,
            # Where there is a rung. `grok agent` takes any word at all here and says nothing
            # until the first shaped turn goes out on the command line, so an agent at no rung
            # is better off saying nothing than saying "".
            *(["--effort", self.effort] if self.effort else []),
            *_PERMITTED[self._agent.config.permission],
            *_LEADING.get(getattr(self._agent.config, "leader", False), ()),
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
            where: dict[str, Any] = {"cwd": self._workspace(), "mcpServers": []}
            if self._id is not None:
                self._settle(
                    proc,
                    self._ask("session/load", {"sessionId": self._id, **where}),
                    refused=Unrecoverable,
                )
                return
            opened = self._settle(proc, self._ask("session/new", where))
        finally:
            watchdog.cancel()
        if not (named := str(opened.get("sessionId") or "")):
            raise Failed(1, self._command(), "", f"{_COMMAND} named no session")
        self._adopt(named)

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

        A tool call it asks permission for is granted: `--always-approve` approves what a rung
        leaves, but a hook of Grok Build's own can put a call in front of the client anyway,
        and a flow watches its agent rather than gating it. Granted by the *kind* of the
        option rather than by its id, which is the agent's own word for it.

        Args:
          at: The id it asked under.
          method: What it asked for.
          params: What it asked with, which carries the options for a permission.
        """
        if method == "session/request_permission":
            self._send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": at,
                        "result": {"outcome": _permits(params)},
                    }
                )
                + "\n"
            )
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
                        "message": f"humanize offers no {method}",
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
            return Event(kind="failed", text=f"{_COMMAND} ended the turn on {why}")
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
        self._costing, self._saying = Usage(), Saying()
        config = self._agent.config
        argv = [
            _COMMAND,
            "--output-format",
            "streaming-json",
            "--model",
            config.model,
            "--effort",
            self.effort,
            *_PERMITTED[config.permission],
        ]
        # Said once however it was asked for: a rung that already takes the reaching outside
        # the workspace away has said it, and the flag is a switch rather than a list.
        if not config.web_search and _NO_WEB not in argv:
            argv.append(_NO_WEB)
        argv += _extras(config)
        if (schema := self._shaping) is not None:
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
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
            return
        said = _parsed(line)
        if said is None:
            return
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


def _permits(params: dict[str, Any]) -> dict[str, Any]:
    """Grants a tool call, by the kind of the option rather than by its name.

    Args:
      params: What was asked, which carries the options the agent offers.

    Returns:
      The outcome to answer with: the first option that grants it, whatever was offered
      where none of them does, and a cancellation where nothing was offered at all. Answered
      either way, because the turn is not this client's to leave hanging.
    """
    offered = [
        cast("dict[str, Any]", one)
        for one in cast("list[Any]", params.get("options") or [])
        if isinstance(one, dict)
    ]
    chosen = next(
        (one for kind in _GRANTS for one in offered if one.get("kind") == kind),
        next(iter(offered), None),
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


@dataclass(frozen=True, kw_only=True)
class GrokBuildAgentConfig(AgentConfig):
    """What Grok Build is configured with: the common model and effort, and five of its own.

    The model is written as Grok Build writes it, which is a name out of its own catalogue --
    `grok models` is what lists them.

    Every one of the five is off by default, and off means the flag is not written at all: an
    install that says nothing here runs exactly the command line the bare CLI runs. Four of
    them are the top-level command's, which is the transport a shaped turn, a fork and a rung
    that takes tools away already go to -- so naming one of them sends *every* turn of the
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
        own, which is what humanize has always done and what keeps a run reproducible: a
        `use_leader = true` in the `~/.grok/config.toml` of whoever is at this machine would
        otherwise put every session of a flow on one backend. True joins it, and None leaves
        the question to that config file, which is the bare CLI's own answer. It is a setting
        of the process the protocol is held open on, so a conversation every turn of which
        falls to the command line never reaches it.
      sandbox: The sandbox profile a turn's filesystem and network access is confined by, by
        the name `--sandbox` takes, or "" for the CLI's own -- which is none. Grok Build has
        no built-in ladder of profiles to pick from: `workspace` is a base to extend, and a
        profile is otherwise a `[profiles.<name>]` in the `sandbox.toml` of whoever is at this
        machine. So it is named here rather than being what a rung is made of: writing a
        profile to enforce a rung would be humanize writing the CLI's own settings.
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

    def new(self, cwd: str | os.PathLike[str] | None = None) -> GrokBuildSession:
        """Opens a new Grok Build session, in the directory it is given or in this one."""
        return GrokBuildSession(self, cwd)
