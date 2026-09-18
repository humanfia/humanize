"""Any CLI that speaks the Agent Client Protocol, driven as one of these.

The protocol is the whole of what is known about such a backend: humanize is handed a command
to run and speaks JSON-RPC to it over its own stdin and stdout, one message a line. That is
enough to hold a conversation -- `session/new` opens one, `session/prompt` takes a turn, and
the agent says what it is doing in `session/update` notifications while the turn runs.

It is not enough to know what the agent runs. The protocol has since grown words for a model,
a reasoning effort and a mode -- `session/set_model`, `session/set_config_option`,
`session/set_mode`, each answered with what the agent is already holding -- but every one of
them is a setting whoever installed the CLI has already made, and none is sent from here: an
added CLI runs as it was configured to, which is what `as configured` means where a model and
an effort are asked for. What the protocol does say is that a client is asked to permit each
tool call, and nobody is at a prompt here -- so every request is granted, by the *kind* of the
option rather than by its id, which is the agent's own to name. That is the whole of the
permission there is: `bypass` and the silence of a config that settles no rung come to one
agent here -- the one whoever installed the CLI configured -- and a rung below them is refused
where the agent is made rather than promised here and not kept.

What a client offers the agent is the other half of the handshake, and this one offers nothing
it was not asked for: the agent has a machine of its own to read files and run commands on,
and a client that says it will do those things is a client the agent stops doing them for
itself. Each of the three the protocol names -- reading a file, writing one, holding a
terminal -- is a field on :class:`AcpAgentConfig` for the turn that wants it, and is served
here when it is asked for, since a client that declared a capability and refused it where it
was asked would be worse than one that never offered.
"""

# The teardown every driver shares is base's, and reaching for it is what grok, agy, qwen
# and the watchdog already do.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, SessionBase, _ended

# `UNSAID` is already taken here, by the word ACP has for what a backend runs, so the
# ladder's own word for a rung nobody settled comes in under the name it is described by.
from .config import UNSAID as NO_RUNG
from .config import AgentConfig, Unserved
from .event import Event, Failed, Saying
from .watchdog import Watchdog

if TYPE_CHECKING:
    from collections.abc import Iterator
    from io import BufferedReader

    from pydantic import BaseModel

#: The version of the protocol this speaks, as an integer. Sent on the way in and read back
#: out of the answer: an agent answers with the version it will actually speak, which is the
#: lower of the two, so one that answers higher than this is one speaking a protocol this
#: client was never taught -- and ACP says a client that cannot speak what it was answered
#: with closes the connection rather than carrying on in a language neither of them shares.
#: Every ACP server this was checked against -- kimi, opencode, qwen, grok -- answers 1 to a
#: client asking for 99, which is that negotiation working rather than a reason to send more.
_VERSION = 1

#: What a client offers an agent when nothing has asked it to offer anything, which is the
#: whole of what the protocol lets one offer and none of it. A client that says it reads files
#: or holds terminals is a client the agent will ask to do those things, and the agent already
#: has a machine of its own to do them on -- so saying nothing keeps the only inbound request
#: `session/request_permission`. Each of the three is a field of :class:`AcpAgentConfig` for
#: the turn that wants it, and `AcpSession._offering` is where what was asked for is said.
#: Read from here by grok too, which speaks this protocol under a name of its own.
_CAPABILITIES: dict[str, Any] = {
    "fs": {"readTextFile": False, "writeTextFile": False},
    "terminal": False,
}

#: How a tool call is permitted, best first. The kind rather than the id: an id is the agent's
#: own word -- one calls it `proceed_once`, another `allow-once` -- and a client that matched
#: on those would work with the agent it was written against and no other.
_GRANTS = ("allow_always", "allow_once")

#: What each thing said in a turn reads as, by the name ACP gives that kind of update. Two of
#: the many an agent sends: the rest say a state moved along rather than a thing said -- a
#: tool call's status, the commands the session offers, the mode it is in, what it has spent
#: so far -- and a reader shown those would be shown the same turn twice.
_SAYS = {"agent_message_chunk": "text", "agent_thought_chunk": "reasoning"}

#: How many bytes of a command's output this client keeps for the agent when the agent names
#: no limit of its own. A megabyte, because what a terminal is asked for is the tail of a
#: build log and holding the whole of one in memory is the client paying for the agent's `yes`.
_OUTPUT = 1 << 20

#: How much of a running command's output is taken at a time: whatever is there, up to this.
#: A read that waited for more than the pipe holds is a client showing nothing while the
#: command is saying something.
_PIECE = 1 << 16

#: What a request this client cannot answer comes back as: a method it never offered is not
#: there to be called, and a call naming something this client is not holding is a call whose
#: parameters are wrong. Both are JSON-RPC's own words, so that an agent reads them the way it
#: reads every other client's.
_UNOFFERED = -32601
_UNKNOWN = -32602
_FAILED = -32603

#: The reasons a turn can end. The first two are a turn that answered; the rest are one that
#: did not, and a flow told otherwise would be running on an answer nobody gave.
_ANSWERED = ("end_turn", "max_tokens")

#: What ACP says a backend runs and how hard it thinks, which is nothing at all. One of each
#: is offered so that an agent can be configured; both are the agent's own to know.
UNSAID = "as configured"


class _Stopped(Exception):  # noqa: N818 -- not an error of ours: the agent went away
    """The agent went away while something was waiting on it."""


def _counted(said: object) -> int | None:
    """One number an agent asked with, or None where it asked with something else.

    Everything in a request came off a pipe, so nothing in one is a number because the
    protocol says it is. What is not one is read as though it had not been sent: a client that
    raised on it would end the turn over a field it could have ignored.

    Args:
      said: What arrived.

    Returns:
      The number, and None for anything that is not one -- a boolean included, which is an
      integer to Python and a mistake to everybody else.
    """
    if isinstance(said, bool) or not isinstance(said, int):
        return None
    return said


@dataclass
class AcpConnection:
    """One ACP agent, running, and the conversation this client holds with it.

    A process rather than a command per turn: the protocol is a session opened once and
    prompted many times, and the agent is what holds the session.
    """

    argv: list[str]
    environ: dict[str, str] | None = None
    cwd: str | None = None
    proc: subprocess.Popen[str] | None = None
    #: What each request is waiting for, by the id it was sent under, and the lock that keeps
    #: two threads from writing half a line each.
    answers: dict[int, Any] = field(default_factory=dict[int, Any])
    landed: threading.Condition = field(default_factory=threading.Condition)
    writing: threading.Lock = field(default_factory=threading.Lock)
    said: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    at: int = 0

    def start(self) -> None:
        """Spawns the agent, if it is not already up."""
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            env=self.environ,
            cwd=self.cwd,
        )

    def send(self, method: str, params: dict[str, Any]) -> int:
        """Writes one request and answers with the id it went under.

        Args:
          method: What to ask for.
          params: What to ask it with.

        Returns:
          The id the answer will come back under.

        Raises:
          _Stopped: If the agent is not there to be told.
        """
        with self.writing:
            self.at += 1
            at = self.at
            self._write(
                {"jsonrpc": "2.0", "id": at, "method": method, "params": params}
            )
        return at

    def notify(self, method: str, params: dict[str, Any]) -> None:
        """Writes one notification, which is a message nothing answers."""
        with self.writing:
            self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def reply(self, at: object, result: dict[str, Any] | None = None) -> None:
        """Answers something the agent asked us.

        Args:
          at: The id it asked under.
          result: What to answer with, and None for the calls the protocol answers with
            nothing at all -- writing a file is one -- since an object where the agent's
            schema says null is an answer it may refuse to read.
        """
        with self.writing:
            self._write({"jsonrpc": "2.0", "id": at, "result": result})

    def refuse(self, at: object, why: str, code: int = _UNOFFERED) -> None:
        """Tells the agent this client will not do what it asked.

        Args:
          at: The id it asked under.
          why: What to say, which goes back as the message of the error.
          code: Which error it is, out of JSON-RPC's own: a method never offered by default,
            and one of the others for a call this client took and could not carry out.
        """
        with self.writing:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": at,
                    "error": {"code": code, "message": why},
                }
            )

    def _write(self, message: dict[str, Any]) -> None:
        """Puts one message on the agent's stdin, whole and on one line.

        Raises:
          _Stopped: If there is nothing listening.
        """
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise _Stopped("the agent is not running")
        try:
            # Compact and on one line: the framing is the newline, so a message written with
            # any in it would be read as several.
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as gone:
            raise _Stopped("the agent is no longer listening") from gone

    def read(self) -> dict[str, Any] | None:
        """The next message the agent wrote, or None once it has stopped writing."""
        proc = self.proc
        if proc is None or proc.stdout is None:
            return None
        for line in proc.stdout:
            if not line.strip():
                continue
            try:
                said: object = json.loads(line)
            except ValueError:
                continue  # a line of something else, which stdout should not carry
            if isinstance(said, dict):
                return cast("dict[str, Any]", said)
        return None

    def stop(self) -> None:
        """Ends the agent, which is what was holding the conversation open."""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        with contextlib.suppress(OSError, ValueError):
            if proc.stdin is not None:
                proc.stdin.close()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            # The tree, not the launcher: an ACP backend starts a runtime that inherits
            # stdout, and killing only what we spawned leaves the half that is actually
            # talking to the model still holding the pipe this session reads.
            _ended(proc)
        with contextlib.suppress(OSError, ValueError):
            if proc.stdout is not None:
                proc.stdout.close()
        with contextlib.suppress(OSError, ValueError):
            if proc.stderr is not None:
                proc.stderr.close()


@dataclass
class _Terminal:
    """One command this client is running because the agent asked it to.

    Held by the conversation that was asked, and let go of when the agent releases it or when
    the conversation ends. What it says is gathered on a thread of its own: the agent asks for
    the output whenever it likes, and a pipe nobody is reading is a command that stops as soon
    as the pipe is full.

    In bytes, which is what the protocol counts a limit in, and in whatever sized pieces the
    pipe has rather than a line at a time: a command drawing a progress bar says nothing that
    ends in a newline, and a client that waited for one would show nothing at all while the
    only thing worth watching was happening.
    """

    proc: subprocess.Popen[bytes]
    limit: int
    said: bytes = b""
    lock: threading.Lock = field(default_factory=threading.Lock)
    cut: bool = False
    #: Set once everything the command said has been read, which is after it has exited. The
    #: agent is told how the command ended only from here on: an exit status handed over while
    #: the pipe still held the last of a build log would be a log the agent read as complete.
    done: threading.Event = field(default_factory=threading.Event)

    def gather(self) -> None:
        """Reads what the command says until it says no more, keeping the last of it."""
        out = self.proc.stdout
        try:
            if out is not None:
                # Whatever is in the pipe now, which is what `read1` is for -- a read of a
                # fixed size waits for that size. Cast because a process's stdout is spelled
                # as the interface every stream shares rather than as the buffered one it is.
                reading = cast("BufferedReader", out)
                with contextlib.suppress(OSError, ValueError):
                    for piece in iter(lambda: reading.read1(_PIECE), b""):
                        with self.lock:
                            self.said += piece
                            if len(self.said) > self.limit:
                                # The tail rather than the head: what a command is asked for
                                # is how it went, and how it went is at the end.
                                self.said = self.said[-self.limit :]
                                self.cut = True
        finally:
            with contextlib.suppress(OSError, ValueError):
                self.proc.wait()
            self.done.set()

    def output(self) -> dict[str, Any]:
        """What it has said so far, and how it ended for one that has."""
        with self.lock:
            held: dict[str, Any] = {
                # Replacing what will not decode, because this goes into JSON: a command that
                # wrote a byte of something else is not a turn to fail.
                "output": self.said.decode("utf-8", "replace"),
                "truncated": self.cut,
            }
        if self.done.is_set() and (ended := self.ended()) is not None:
            held["exitStatus"] = ended
        return held

    def ended(self) -> dict[str, Any] | None:
        """How the command ended, or None while it is still running."""
        status = self.proc.poll()
        if status is None:
            return None
        if status >= 0:
            return {"exitCode": status, "signal": None}
        # A process that died on a signal has no exit status, and the signal is what there is
        # to say about it -- by its name, which is what the protocol asks for.
        named = next(
            (one.name for one in signal.Signals if one.value == -status), str(-status)
        )
        return {"exitCode": None, "signal": named}

    def waited(self) -> dict[str, Any]:
        """Waits for the command to end and for the last of what it said, and says how."""
        self.done.wait()
        return self.ended() or {"exitCode": None, "signal": None}

    def stop(self) -> None:
        """Ends the command, and the tree under it, if it has not ended already."""
        if self.proc.poll() is None:
            # Asking a process to stop and then making it is the same call whichever way its
            # streams were opened, which is the whole of what the cast says.
            _ended(cast("subprocess.Popen[str]", self.proc))


class AcpSession(SessionBase):
    """One ACP conversation, held open on the agent this client spawned.

    The process is the session: ACP opens one with `session/new` and takes as many turns on it
    as it is asked for, so the agent stays up between them rather than being run again.
    """

    #: The protocol has no way of holding a turn to a shape, so one asked for is asked for in
    #: the prompt, as it is for every other backend without a setting for it.
    shapes: ClassVar[bool] = False

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session with no agent running yet.

        Args:
          agent: The agent whose command every turn of this session is run against.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        self._link: AcpConnection | None = None
        #: The chunks a turn arrives in, gathered into the messages they are chunks of: ACP
        #: says an agent's words a fragment at a time, and a fragment is not a thing to show.
        self._saying = Saying()
        #: What this client offers the agent, read off the settings the agent was made with
        #: rather than off each request as it arrives: what was declared at the handshake is
        #: what the agent may ask for, and a client that served more than it declared would be
        #: a handshake that lied.
        self._reads_files = bool(getattr(agent.config, "reads_files", False))
        self._writes_files = bool(getattr(agent.config, "writes_files", False))
        self._terminals = bool(getattr(agent.config, "terminals", False))
        #: Which of the protocol's two ways of picking a conversation back up this agent said
        #: it serves, read off the handshake. Neither, until it has been asked.
        self._resumes = False
        self._loads = False
        #: The commands this client is running for the agent, by the name it knows each by,
        #: and what the next one is to be called.
        self._running: dict[str, _Terminal] = {}
        self._held = 0

    def _connection(self) -> AcpConnection:
        """The agent, started and initialized and holding a session, made on first use.

        Returns:
          The connection, with the conversation already opened on it -- a new one, one cut
          from another, or the one this session was holding before its last agent went.

        Raises:
          subprocess.CalledProcessError: If the agent will not start, speaks a protocol this
            client does not, refuses to open a session, or cannot pick one back up.
        """
        if self._link is not None and self.elsewhere():
            # Started as an account this agent has since left: ended here, on the thread that
            # holds it, so that the next turn opens one as whoever the agent now is.
            self._shut()
        if self._link is not None:
            return self._link
        agent = cast("AcpAgent", self._agent)
        argv = self._agent.spawned(list(agent.command), self.cwd)
        anchor = self._agent.anchor
        offered = self._reads_files or self._writes_files or self._terminals
        if offered and anchor is not None and anchor.native:
            # The CLI is the target's own, so a file this client read and a command it ran
            # would be this machine's -- which is not where the work lands. Refused where the
            # conversation opens rather than answered from the wrong machine.
            raise Failed(
                1,
                argv,
                "",
                f"this agent's CLI runs on {anchor.target}, whose files and commands are "
                "that machine's; reads_files, writes_files and terminals offer it this "
                "one, and must be off for a turn that lands there",
            )
        link = AcpConnection(
            argv=argv,
            environ=self._environ(),
            cwd=None if self._agent.anchor is not None else self._workspace(),
        )
        self._as = self._agent.node().name
        try:
            link.start()
            self._agreed(
                self._settle(
                    link,
                    link.send(
                        "initialize",
                        {
                            "protocolVersion": _VERSION,
                            "clientCapabilities": self._offering(),
                            "clientInfo": {"name": "humanize", "version": "1"},
                        },
                    ),
                )
            )
            asked, params = self._opening()
            opened = self._settle(link, link.send(asked, params))
        except _Stopped as gone:
            link.stop()
            raise Failed(1, argv, "", str(gone)) from gone
        except ValueError as refused:
            link.stop()
            raise Failed(1, argv, "", str(refused)) from refused
        self._adopt(str(opened.get("sessionId") or ""))
        self._link = link
        return link

    def _offering(self) -> dict[str, Any]:
        """What this client says it can do, which is nothing it was not asked for.

        Returns:
          The `clientCapabilities` of the handshake: :data:`_CAPABILITIES` where nothing was
          asked for, and what was asked for where something was.
        """
        return {
            "fs": {
                "readTextFile": self._reads_files,
                "writeTextFile": self._writes_files,
            },
            "terminal": self._terminals,
        }

    def _agreed(self, hello: dict[str, Any]) -> None:
        """Reads the handshake back: what is being spoken, and what the agent can be asked.

        Args:
          hello: What `initialize` answered with.

        Raises:
          ValueError: If the agent answered with a version of the protocol this client has
            never been taught. An agent answers with the lower of the two versions, so a
            higher one is one that cannot go down to this -- and a client carrying on there
            would be sending messages nobody has agreed the shape of.
        """
        spoken = hello.get("protocolVersion")
        if (
            isinstance(spoken, int)
            and not isinstance(spoken, bool)
            and spoken > _VERSION
        ):
            raise ValueError(
                f"the agent speaks version {spoken} of the agent client protocol and "
                f"this client speaks {_VERSION}"
            )
        able = cast("dict[str, Any]", hello.get("agentCapabilities") or {})
        held = cast("dict[str, Any]", able.get("sessionCapabilities") or {})
        self._resumes = "resume" in held
        self._loads = bool(able.get("loadSession"))

    def _opening(self) -> tuple[str, dict[str, Any]]:
        """Which of the protocol's ways into a conversation this one takes, and with what.

        Returns:
          The call and its parameters.

        Raises:
          ValueError: If this conversation has an id to pick back up and the agent said at the
            handshake that it serves neither of the calls that would. Said here rather than
            quietly opening a new session under the old one's id: a turn taken from nothing is
            a flow going round again on a conversation that has forgotten it.
        """
        params: dict[str, Any] = {
            # Absolute, which the protocol requires, and the one the session works in.
            "cwd": self._workspace(),
            # What this client is handing the agent on top of whatever the CLI is already
            # configured with, which is nothing unless the agent was made carrying some. An
            # empty list is the protocol's own default rather than humanize declining
            # anything: the servers the person who installed the CLI wrote down are the CLI's
            # own and are loaded whatever a client sends.
            "mcpServers": [one.sent() for one in self._servers()],
        }
        # `session/fork` for a conversation cut from another and not yet opened: the
        # protocol's own call for it, answering with a session id of its own that holds what
        # the named one had got to. An agent that has not implemented it answers with an
        # error, which is a refusal read where it was asked -- and not two conversations that
        # are quietly one. Only while this session has no id: a child that has taken turns of
        # its own is a conversation, and forking the parent again would throw those away.
        if self._id is None and self._forked_from is not None:
            return "session/fork", {**params, "sessionId": self._forked_from}
        if self._id is None:
            return "session/new", params
        # An id already, so this is the same conversation on a second process -- the agent was
        # put down by a watchdog, or ended because the account it was running as changed.
        # `session/resume` restores it without saying it all again; `session/load` replays the
        # whole of it as updates nobody here shows. The first where the agent offers it, since
        # a replay of an hour's work is an hour's words across a pipe.
        if self._resumes:
            return "session/resume", {**params, "sessionId": self._id}
        if self._loads:
            return "session/load", {**params, "sessionId": self._id}
        raise ValueError(
            f"this agent cannot pick {self._id} back up: it offers neither "
            "session/resume nor session/load"
        )

    def _servers(self) -> tuple[McpServer, ...]:
        """The MCP servers this agent's conversations are to be given, on top of the CLI's."""
        return cast(
            "tuple[McpServer, ...]",
            tuple(getattr(self._agent.config, "mcp_servers", ())),
        )

    def _settle(self, link: AcpConnection, at: int) -> dict[str, Any]:
        """Waits for one request to be answered, serving whatever is asked on the way.

        The client has to keep answering while its own request is outstanding: an agent asks
        for permission in the middle of the turn it was told to take, and a client that only
        read its own answer would deadlock against it.

        Args:
          link: The agent.
          at: The id the request went under.

        Returns:
          What it answered with.

        Raises:
          _Stopped: If the agent stopped before answering.
          ValueError: If it answered with an error.
        """
        for event in self._serving(link, at):
            del event  # nothing is shown from here: the turn is what is watched
        answered = link.answers.pop(at)
        if isinstance(answered, Exception):
            raise answered
        return cast("dict[str, Any]", answered)

    def _serving(self, link: AcpConnection, at: int) -> Iterator[Event]:
        """Reads until one request is answered, saying what the agent says on the way.

        Args:
          link: The agent.
          at: The id being waited for.

        Yields:
          What the agent said while it worked.

        Raises:
          _Stopped: If the agent stopped before answering.
        """
        while True:
            message = link.read()
            if message is None:
                link.answers[at] = _Stopped("the agent stopped before it answered")
                raise cast("_Stopped", link.answers[at])
            if "method" in message:
                yield from self._asked(link, message)
                continue
            if message.get("id") != at:
                continue  # an answer to something else, which nothing here is waiting on
            if (failed := message.get("error")) is not None:
                link.answers[at] = ValueError(json.dumps(failed))
            else:
                link.answers[at] = message.get("result") or {}
            return

    def _asked(self, link: AcpConnection, message: dict[str, Any]) -> Iterator[Event]:
        """Answers something the agent said or asked, and says what is worth showing.

        Args:
          link: The agent.
          message: What it sent.

        Yields:
          What it said, for a notification that is the agent talking.
        """
        method = str(message.get("method") or "")
        params = cast("dict[str, Any]", message.get("params") or {})
        if method == "session/update":
            yield from self._told(cast("dict[str, Any]", params.get("update") or {}))
            return
        if "id" not in message:
            return  # a notification of some other kind: nothing to answer, nothing to show
        at = message["id"]
        if method == "session/request_permission":
            link.reply(at, {"outcome": self._permits(params)})
            return
        if method == "fs/read_text_file" and self._reads_files:
            self._reads(link, at, params)
            return
        if method == "fs/write_text_file" and self._writes_files:
            self._writes(link, at, params)
            return
        if method.startswith("terminal/") and self._terminals:
            self._terminal(link, method, at, params)
            return
        # Everything else is a thing this client said it could not do, and an agent asking
        # anyway is told so in the protocol's own words rather than left waiting.
        link.refuse(at, f"{method} is not offered")

    def _reads(self, link: AcpConnection, at: object, params: dict[str, Any]) -> None:
        """Reads a file for the agent, which is a thing this client said it would do.

        Args:
          link: The agent.
          at: The id it asked under.
          params: What it asked for: the path, and the run of lines it wants where it wants
            part of the file rather than all of it.
        """
        path = str(params.get("path") or "")
        try:
            held = Path(path).read_text(encoding="utf-8")
        except (OSError, ValueError) as why:
            # A file that is not there, and one that is not text: this call is for text, and
            # what cannot be read is answered where it was asked rather than raised into the
            # turn's own reader, which would end a turn over one bad path.
            link.refuse(at, f"{path}: {why}", _FAILED)
            return
        line, limit = _counted(params.get("line")), _counted(params.get("limit"))
        if line is not None or limit is not None:
            # One-based, which is how the protocol counts and how a person reading an error
            # message counts; a limit is how many lines rather than which last one.
            lines = held.splitlines(keepends=True)
            first = max(line - 1, 0) if line is not None else 0
            last = first + limit if limit is not None else len(lines)
            held = "".join(lines[first:last])
        link.reply(at, {"content": held})

    def _writes(self, link: AcpConnection, at: object, params: dict[str, Any]) -> None:
        """Writes a file for the agent, making the directories it is under if it must.

        Args:
          link: The agent.
          at: The id it asked under.
          params: What it asked for: the path, and the whole of what is to be in it.
        """
        path = Path(str(params.get("path") or ""))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(params.get("content") or ""), encoding="utf-8")
        except OSError as why:
            link.refuse(at, f"{path}: {why}", _FAILED)
            return
        link.reply(at)  # the protocol answers this one with nothing at all

    def _terminal(
        self, link: AcpConnection, method: str, at: object, params: dict[str, Any]
    ) -> None:
        """Holds a command for the agent, which is the third thing a client can offer.

        Args:
          link: The agent.
          method: Which of the terminal calls it made.
          at: The id it asked under.
          params: What it asked with, which names the terminal for all but the first.
        """
        if method == "terminal/create":
            self._opens(link, at, params)
            return
        named = str(params.get("terminalId") or "")
        held = self._running.get(named)
        if held is None:
            link.refuse(
                at, f"{named} is not a terminal this client is holding", _UNKNOWN
            )
            return
        if method == "terminal/output":
            link.reply(at, held.output())
        elif method == "terminal/wait_for_exit":
            # Answered from a thread of its own, because the answer is however long the
            # command takes: this one is the turn's reader, and a reader waiting on a build
            # is a reader not reading what the agent says while the build runs.
            threading.Thread(
                target=self._exited, args=(link, at, held), daemon=True
            ).start()
        elif method == "terminal/kill":
            held.stop()
            link.reply(at, {})
        elif method == "terminal/release":
            held.stop()
            del self._running[named]
            link.reply(at, {})
        else:
            link.refuse(at, f"{method} is not offered")

    def _opens(self, link: AcpConnection, at: object, params: dict[str, Any]) -> None:
        """Starts one command for the agent, and answers with the name it is to be asked for.

        Args:
          link: The agent.
          at: The id it asked under.
          params: The command, its arguments, and whatever it is to be run with.
        """
        argv = [
            str(params.get("command") or ""),
            *(str(one) for one in cast("list[Any]", params.get("args") or [])),
        ]
        # The environment the agent itself runs under, plus what it named for this command:
        # a command run beside the agent is one run as the agent, which is what an account
        # signed in for these turns has to reach.
        environ = dict(self._environ() or os.environ)
        for one in cast("list[Any]", params.get("env") or []):
            if isinstance(one, dict):
                held = cast("dict[str, Any]", one)
                environ[str(held.get("name") or "")] = str(held.get("value") or "")
        # Nothing and nothing at all are the same answer: a client holding none of what a
        # command said is a client the agent asked for output it cannot use.
        limit = _counted(params.get("outputByteLimit")) or _OUTPUT
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                # Together, because a terminal is one screen: a command's complaints belong
                # where its output does, in the order it said them.
                stderr=subprocess.STDOUT,
                # Bytes, because the limit the agent names is in bytes and because a command
                # that wrote something that is not text is not a turn to fail.
                env=environ,
                cwd=str(params.get("cwd") or self._workspace()),
            )
        except OSError as why:
            link.refuse(at, f"{argv[0]}: {why}", _FAILED)
            return
        self._held += 1
        named = f"term-{self._held}"
        running = _Terminal(proc=proc, limit=limit)
        self._running[named] = running
        threading.Thread(target=running.gather, daemon=True).start()
        link.reply(at, {"terminalId": named})

    def _exited(self, link: AcpConnection, at: object, held: _Terminal) -> None:
        """Waits for one command to end and says how it did, on a thread of its own."""
        ended = held.waited()
        # The agent may be gone by the time the command is: a conversation that ended took
        # its terminals with it, and there is nobody left to tell.
        with contextlib.suppress(_Stopped):
            link.reply(at, ended)

    def _permits(self, params: dict[str, Any]) -> dict[str, Any]:
        """Grants a tool call, by the kind of the option rather than by its name.

        Args:
          params: What was asked, which carries the options the agent offers.

        Returns:
          The outcome to answer with, which is the chosen option or a refusal where the agent
          offered nothing that would allow it.
        """
        offered = [
            cast("dict[str, Any]", one)
            for one in cast("list[Any]", params.get("options") or [])
            if isinstance(one, dict)
        ]
        for kind in _GRANTS:
            for one in offered:
                if one.get("kind") == kind:
                    return {"outcome": "selected", "optionId": str(one.get("optionId"))}
        # Nothing that grants it: the turn is not ours to hang, so it is answered rather than
        # left, and the agent decides what a refusal means to it.
        if offered:
            return {"outcome": "selected", "optionId": str(offered[0].get("optionId"))}
        return {"outcome": "cancelled"}

    def _told(self, update: dict[str, Any]) -> Iterator[Event]:
        """Reads one `session/update`, whose variant names itself and is flattened beside it.

        Args:
          update: The update, as read.

        Yields:
          What it said, which is nothing for one that moved a state along.
        """
        kind = str(update.get("sessionUpdate") or "")
        if kind == "tool_call":
            # What it said before reaching for something is what says why it reached.
            yield from self._saying.upto()
            named = str(update.get("title") or update.get("kind") or "tool")
            yield Event(kind="tool", text=named[:120])
        elif (says := _SAYS.get(kind)) is not None:
            content = cast("dict[str, Any]", update.get("content") or {})
            if words := str(content.get("text") or ""):
                self._saying.delta(says, words)

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Takes one turn on the session, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.
          schema: Unused here: the protocol has no way of holding a turn to a shape, so one
            was asked for in the prompt before this was called.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the agent went away, refused, or ended the turn
            on a reason that is not an answer.
        """
        del schema
        link = self._connection()
        self._saying = Saying()
        said: list[str] = []
        # Under a clock: reading the agent is reading its stdout, and an agent still
        # holding that pipe open and never writing to it again is neither an answer nor
        # an exit. The process is this session's own, so the watchdog signals it; the
        # conversation does not survive -- the protocol's only way to open a session
        # opens a new one -- which is what it says before it does it.
        with Watchdog(self, riding=lambda: link.proc) as watch:
            try:
                at = link.send(
                    "session/prompt",
                    {
                        "sessionId": self.id,
                        "prompt": [{"type": "text", "text": prompt}],
                    },
                )
                if self._cutting():
                    # Cut off while the turn was still being said, when there was nothing yet
                    # to cancel: an agent cancelled before it was prompted is an agent that
                    # goes on to take the turn anyway, so what arrived a moment early is done
                    # a moment late.
                    self._cuts()
                for event in self._serving(link, at):
                    watch.saw()
                    if event.kind == "text":
                        said.append(event.text)
                    with (
                        watch.held()
                    ):  # a reader that pauses is not the agent's silence
                        yield event
                # And whatever the last message of the turn held back: nothing follows it to
                # close it, the thing that ends it being the turn's own answer.
                for event in self._saying.rest():
                    if event.kind == "text":
                        said.append(event.text)
                    yield event
                answered = link.answers.pop(at)
            except _Stopped as gone:
                # Everything this conversation was holding, the commands it was running for
                # the agent included: an agent that went away mid-build is not a reason for
                # the build to outlive it.
                self._shut()
                # What it had said before it went is what says how far it got, and is the
                # whole of the diagnostic for an agent that stopped mid-sentence.
                said += [one.text for one in self._saying.rest() if one.kind == "text"]
                raise Failed(
                    1,
                    list(cast("AcpAgent", self._agent).command),
                    "\n".join(said),
                    str(gone),
                ) from gone
            if isinstance(answered, Exception):
                raise Failed(
                    1,
                    list(cast("AcpAgent", self._agent).command),
                    "\n".join(said),
                    str(answered),
                )
            why = str(cast("dict[str, Any]", answered).get("stopReason") or "")
            if why not in _ANSWERED:
                raise Failed(
                    1,
                    list(cast("AcpAgent", self._agent).command),
                    "\n".join(said),
                    f"the turn ended on {why}",
                )
        yield Event(kind="result", text="\n".join(said).strip())

    def interject(self, text: str) -> None:
        """Says something to the turn already running, which ACP has no way of doing.

        Args:
          text: What would have been said.

        Raises:
          NotImplementedError: Always. Steering is an extension each agent spells its own
            way, and a client that guessed at one would be talking to itself.
        """
        del text
        raise NotImplementedError(
            "the agent client protocol has no way to steer a turn"
        )

    def _cuts(self) -> None:
        """Stops the turn now running, by the protocol's own word for it.

        `session/cancel` rather than the process: the protocol says an agent told to cancel
        ends what it is doing and answers the prompt it was given with `cancelled`, which is a
        turn that stops where it stands and a conversation still there to take the next one --
        and this conversation can be picked back up, so throwing the agent away would throw
        away the session too. An agent that ignores it is left to the watchdog, which is what
        ends a turn nothing else will.
        """
        super()._cuts()
        link = self._link
        if link is None or self._id is None:
            return  # nothing has opened a session yet, so there is no turn to cancel
        with contextlib.suppress(_Stopped):
            link.notify("session/cancel", {"sessionId": self._id})

    def _shut(self) -> None:
        """Ends the agent, which is what was holding the conversation open."""
        # And the commands it was given: a terminal is this client's own process, and one
        # left running would outlive the conversation that asked for it.
        running, self._running = self._running, {}
        for held in running.values():
            held.stop()
        link, self._link = self._link, None
        if link is not None:
            link.stop()


@dataclass(frozen=True, kw_only=True)
class McpServer:
    """One MCP server an added CLI is to be given, as `session/new` carries it.

    A server of the flow's rather than of the CLI's: what the person who installed the CLI
    wrote down is loaded whatever a client sends, and this is what a turn adds to it for as
    long as the conversation lasts. Over stdio, which is the one transport every ACP agent
    reads -- an agent may also take HTTP and SSE and says at the handshake whether it does,
    and a flow that wants one of those wants a server this machine is not holding.

    Attributes:
      name: What the agent is to call it, which is what its tools are prefixed with.
      command: The program that serves it.
      args: What to run that with.
      env: What to run it under, as pairs, and nothing at all for the environment the agent
        itself was started in.
    """

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()

    def sent(self) -> dict[str, Any]:
        """This server as the handshake spells it."""
        return {
            "name": self.name,
            "command": self.command,
            "args": list(self.args),
            "env": [{"name": one, "value": value} for one, value in self.env],
        }


@dataclass(frozen=True, kw_only=True)
class AcpAgentConfig(AgentConfig):
    """What an ACP agent is configured with, which is which CLI it is and little else.

    Everything below `command` is something the protocol lets a *client* offer, and each of
    them is off: the agent has a machine of its own to read files and run commands on, and a
    client that says otherwise is a client the agent hands that work to. Off is also what the
    bare CLI does when anything else drives it, which is the whole reason it is the default --
    a turn that wants one says so here, and gets a client that actually serves it.

    Attributes:
      cli: The name the CLI was added under, which is what an `-a` calls it.
      command: What to run to start it, or nothing to look it up by name.
      reads_files: Whether the agent may have this client read a file for it, rather than
        reading it itself. Worth having where the agent's own reads would miss what a flow
        has in hand -- an editor's unsaved buffer is what the protocol names it for.
      writes_files: Whether the agent may have this client write one.
      terminals: Whether the agent may have this client run a command and hold it: it starts
        one, reads what it says while it runs, waits for it, kills it and lets it go. The
        command runs where humanize runs.
      mcp_servers: The MCP servers each conversation of this agent is opened with, on top of
        whatever the CLI is already configured with. Nothing at all by default, which is what
        a client hands over when it has none of its own to add.
    """

    cli: str = ""
    command: tuple[str, ...] = ()
    reads_files: bool = False
    writes_files: bool = False
    terminals: bool = False
    mcp_servers: tuple[McpServer, ...] = ()

    def __post_init__(self) -> None:
        """Refuses a server that could not be started.

        Raises:
          ValueError: If one was named with nothing to run, or run with no name. Both are
            said here rather than by an agent refusing a session hours later, and neither is
            the agent's to explain: what it would answer is that the handshake was malformed.
        """
        super().__post_init__()
        for one in self.mcp_servers:
            if not one.name.strip() or not one.command.strip():
                raise ValueError(
                    "an MCP server needs a name and a command to start it with, "
                    f"not {one.name!r} and {one.command!r}"
                )


class AcpAgent(AgentBase):
    """A CLI of your own that speaks the Agent Client Protocol."""

    @property
    def backend(self) -> str:
        """The name this CLI was added under, rather than one read off the class.

        Every other backend here is one class apiece, so the class says which it drives. This
        one class drives every CLI anybody adds, so the name is a setting instead.
        """
        held = getattr(self.config, "cli", "") or "acp"
        return str(held)

    @property
    def command(self) -> tuple[str, ...]:
        """What to run to start this agent.

        Returns:
          The command, as it was given when the CLI was added.

        Raises:
          ValueError: If nothing says how to start it, which is a CLI that was never added.
        """
        from hmz.coganchor import backends

        given = tuple(getattr(self.config, "command", ()) or ())
        if given:
            return given
        found = backends.speaking().get(self.backend)
        if not found:
            raise ValueError(
                f"{self.backend}: no command to start it with; /providers, then a, "
                "then `a CLI of your own` is where one is written down"
            )
        return found

    def _serves(self, config: AgentConfig) -> None:
        """Refuses a config the protocol has no way of carrying.

        Args:
          config: What the agent is to run at.

        Raises:
          ValueError: If it was allowed less than everything. ACP's only word about permission
            is `session/request_permission`, which asks a client to allow one tool call at a
            time -- and nobody is at a prompt here, so every request is granted and the agent
            goes on doing what whoever installed it allowed it to do.

            Which is why the silence is the one other answer this backend can honestly give:
            a config that settles no rung asks for nothing to be said about what the agent may
            do, and an added CLI doing what whoever installed it allowed it to do is exactly
            that. `bypass` is the flow saying it wants the same thing out loud. Neither is
            humanize allowing anything, because there is nothing here to allow it with.

            An agent that never asks is an agent nothing was given the chance to refuse, so a
            rung below those two is said where the agent is made rather than quietly run as
            the rung above it.
        """
        super()._serves(config)
        if config.permission not in (NO_RUNG, "bypass"):
            raise Unserved(
                "the agent client protocol has no way of allowing an agent less than "
                "everything; permission must be 'bypass', or left unsaid for the agent as "
                f"whoever installed the CLI configured it, not {config.permission!r}",
                "permission",
            )

    def new(self, cwd: str | os.PathLike[str] | None = None) -> AcpSession:
        """Opens a new conversation, in the directory it is given or in this one."""
        return AcpSession(self, cwd)
