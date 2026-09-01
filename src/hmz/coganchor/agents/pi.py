"""pi: one ``pi --mode rpc`` held open, spoken to in JSON a line at a time.

``pi -p`` runs a turn and stops, which leaves nowhere to put a later word and no way to move
the thinking level once a session is going. ``pi --mode rpc`` is the same binary headless: the
session stands, turns are commands written to its stdin, and what it says comes back as the
same events its print mode writes. Steering a running turn, changing the effort mid-session
and asking what the session has spent are all commands there, and none of them is a flag.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz import home

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Question, Usage
from .hooks import arriving
from .preload import preloaded

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

#: What each kind of thing pi says a turn did reads as. A message is a list of parts and pi
#: says each of them three times -- as it starts, once per fragment, and once with the whole
#: of it -- and for words the end is the only one worth reading: a row per fragment is one
#: paragraph broken into fifty answers of a word each. Tool calls are not in here: all three
#: of theirs are read, in :meth:`PiSession._reaches`, because for those the end is too late.
_PARTS = {"text_end": "text", "thinking_end": "reasoning"}

#: The three pi says a tool call under, and all three are read. A call's end is the moment its
#: arguments have all arrived, and its arguments are what it was called with -- so for a
#: `write` that end is the whole of the file, and a row held for it is a minute in which the
#: agent has reached for something and the turn has said nothing at all. pi hands over the
#: fragments as they came, so the row goes out at the first one there is anything to say it
#: about.
_REACHING = ("toolcall_start", "toolcall_delta", "toolcall_end")

#: How much of a tool call fits on a row of a transcript.
_ROOM = 120

#: How much of a call's arguments is worth holding on to while they are still arriving, which
#: is exactly as much of them as :func:`hmz.coganchor.agents.hooks.arriving` ever reads. Anything
#: past it cannot change what a row says, and a `write` is five megabytes of it. Written here
#: rather than imported, that being a private of another module's; `tests/agents/test_reaching.py`
#: is what holds the two to each other.
_SCANNED = 4096

#: The ways an extension may stop a turn to ask the person at the prompt something. The rest
#: of what one may put on the screen -- a notice, a status, a widget -- is told rather than
#: asked, and pi waits on none of it.
_ASKS = ("select", "confirm", "input", "editor")

#: What pi offers for a question that is a yes or a no, so that it reads as a question
#: wherever it is shown rather than as one with nothing to answer it with.
_YES_NO = ("yes", "no")

#: What each kind of token is called in the usage pi reports on every message. Reasoning is
#: counted inside the output rather than beside it, which is why it is not a kind of its own.
_KINDS = {
    "input": "input",
    "output": "output",
    "cache_read": "cacheRead",
    "cache_write": "cacheWrite",
}

#: Where node is told to keep what it compiled of pi, and so what a second pi reads back
#: instead of compiling again. A quarter of a pi start is that compiling -- the CLI is one
#: bundle of some twenty megabytes -- and a session here is a process of its own, so eight
#: sessions at once on four cores spend their first second compiling the same file eight
#: times. Node's own cache and none of ours: it keys every entry on the file it came from and
#: on the node reading it, so an upgrade of either compiles once more and writes the entry
#: again, and a directory it cannot write leaves the saving unmade and nothing else.
#:
#: The one thing on this command line that is humanize's idea rather than pi's, and so the one
#: with a way out: `PiAgentConfig(compiled=False)` leaves the variable alone and a turn starts
#: exactly as a bare `pi` would. It stays on by default because the saving is real and the
#: cache is node's own -- but a flow timing a cold start, or one that must leave nothing on
#: this machine, is asking a fair question and gets an answer rather than a monkeypatch.
_COMPILED = "NODE_COMPILE_CACHE"

#: Where that cache goes, under humanize's own home: it outlives one run of one flow, which is
#: the whole point of it, and it is not the CLI's own directory to put anything in.
_CACHE = ("compiled", "pi")

#: The tools of pi's own that change something rather than look at something, which is the
#: whole of what an agent that may change nothing is refused. `powershell` is in here for the
#: same reason `bash` is: it is the same tool on Windows, and pi ignores a name on this list
#: that it did not load, so naming it costs a turn on Linux nothing.
#:
#: Checked again against 0.85.1, because `--approve`/`--no-approve` arrived recently and looks
#: like the beginning of a gate. It is not one, and it was made to say so rather than read: a
#: turn run under `--no-approve`, which is the stricter of the pair, ran `bash` to completion
#: and was never asked anything. pi's own security notes say why -- there is no sandbox, and
#: project trust is "only an input-loading guard" over settings, extensions, skills and
#: prompts that "does not restrict what the model can ask tools to do". So there is still
#: nothing to map the four rungs onto and no `_PERMITTED` table to write, and writing one
#: would be the failure this is here to avoid: a rung that reads as enforced and enforces
#: nothing. `read-only` is tools withheld, and `workspace-write`, `auto` and `bypass` are one
#: and the same agent.
#: A denylist rather than the `--tools read,grep,find,ls` allowlist pi documents for the same
#: job, because that one also switches off every extension tool and turns on three built-ins
#: pi ships disabled -- which is a different agent, not a stricter one.
_CHANGING = ("bash", "edit", "write", "powershell")


def _about(called: dict[str, Any]) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      called: The tool's arguments, as pi sent them.

    Returns:
      The first thing in it that is words -- the command, the path, the query -- or "".
    """
    return next(
        (
            str(value)
            for value in called.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )


@dataclass(frozen=True, kw_only=True)
class PiAgentConfig(AgentConfig):
    """What pi is configured with: the common model and effort, and what pi alone takes.

    The model is written as pi writes it, `provider/id`, since a model here belongs to the
    provider that serves it and pi is asked for the pair. Written that way rather than as a
    bare id and a `--provider` beside it, because pi's `--provider` defaults to `google` and a
    turn that named only the id would run on whichever Gemini that account has.

    Every field here is defaulted to what a bare `pi` already does, so an agent that sets none
    of them starts the CLI as it ships, and each is a capability a flow may ask for before it
    is handed an agent -- `hmz.flows.checking.catalogue` reads this class and names them
    `settings:<field>`. Three things humanize imposes whatever this says, and
    each is written down where it is imposed: ``--mode rpc``, which is the transport this
    driver is -- a turn is a line written to a process that is already up, and steering and
    moving the effort mid-session are commands there rather than flags; ``--session-id``,
    because the alternative is ``--continue`` picking whichever session in this directory is
    newest and a second agent working alongside stealing the resume; and ``--exclude-tools``
    at the `read-only` rung, which is the only thing that rung can be made of on a CLI with no
    permission gate.

    Attributes:
      compiled: Whether node may keep what it compiled of pi under humanize's home, which is
        what makes the second session on a machine start in three quarters of the time. True,
        which is humanize's choice rather than pi's: the CLI sets no `NODE_COMPILE_CACHE`
        itself. False leaves the variable exactly as it was found. Either way one already set
        -- by a provider, or by whoever started this process -- is left alone, and a turn that
        lands on another machine is given none.
      context_files: Whether pi discovers `AGENTS.md` and `CLAUDE.md` where the turn works.
        True, as pi ships. False is ``--no-context-files``: a run that has to answer the same
        way tomorrow, or on a machine whose checkout carries somebody else's instructions.
      extensions: Whether pi discovers the extensions installed on this machine. True, as pi
        ships. False is ``--no-extensions`` -- and worth knowing that an extension is what
        registers a flag of its own and what stops a turn to ask the person at the prompt, so
        switching them off is switching off the only thing that ever asks.
      offline: Whether pi is started with its startup network work switched off -- the model
        catalogue refresh and the update check, not the turn itself. False, as pi ships. True
        is ``--offline``, the same as `PI_OFFLINE=1`.
      append_system_prompt: Text -- or the path of a file holding it -- added to pi's own
        coding-assistant prompt, once per entry, as ``--append-system-prompt``. Empty, as pi
        ships. This adds to that prompt rather than replacing it: humanize does not hand a
        backend a system prompt of its own, and a flow that means to say something to every
        turn of one agent says it here.
      skill_paths: Skill files or directories for pi to load by path, once per entry, as
        ``--skill``. Empty, as pi ships. This is pi's only road for a skill that is not
        already installed on the machine: the two directories it discovers under the workspace
        -- `.pi/skills` and `.agents/skills` -- are gated on the project having been trusted,
        which a headless run has nobody to press, so a flow's own skills mounted into one of
        them would be read by nothing. ``--skill`` is not gated and is additive even under
        ``--no-skills``, so a path named here is loaded.
    """

    compiled: bool = True
    context_files: bool = True
    extensions: bool = True
    offline: bool = False
    append_system_prompt: tuple[str, ...] = ()
    skill_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Checks that what is to go on the command line is something pi can be given.

        Raises:
          TypeError: If either repeatable option was written as one entry rather than as a
            sequence of them.
          ValueError: If either carries an empty entry. pi would take the flag and the blank
            after it and load nothing, which is a skill the turn was meant to have and
            silently has not.
        """
        super().__post_init__()
        for field, held in (
            ("append_system_prompt", self.append_system_prompt),
            ("skill_paths", self.skill_paths),
        ):
            # A string is a sequence of strings, so this one slip is the one that would not
            # be caught anywhere: `skill_paths="/x"` is a `--skill` per character, and pi
            # takes every one of them.
            if isinstance(held, str):
                raise TypeError(
                    f"{field} must be a sequence of entries rather than one entry: "
                    f"{field}=({held!r},)"
                )
            if any(not one.strip() for one in held):
                raise ValueError(f"{field} entries must each say something")


class PiSession(StreamSessionBase):
    """A pi conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume. The process stands for the life
    of the session rather than the length of a turn, which is what the RPC mode buys: the
    turns of one conversation are commands written to a pi that is already there, and so is
    anything said to it while a turn is running.
    """

    #: `pi --mode rpc` takes a prompt as a command on the stdin of the process holding the
    #: session, so one written while a turn is running is spliced into that turn -- and the
    #: user message pi answers with is the model having it.
    steers: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has spent nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The id this session was opened under, noted as the command line is built and taken
        #: as the session's own only once a turn has landed in it. Ours rather than pi's: an
        #: RPC pi announces nothing when it comes up. `--mode json` writes the session file's
        #: own header as its first line and that line says the id; `--mode rpc` writes only
        #: what the session emits, which begins with the answer to the first command, and the
        #: id is there for the asking as `get_state` and nowhere else. It does not have to
        #: say it: `--session-id` is the exact id, pi creates it where there is none, and a
        #: `--fork` given one alongside forks into that id or exits rather than choosing
        #: another -- so the id asked for is the id there is.
        self._named: str | None = None
        #: What the agent has said so far in the turn now running, and what went wrong with
        #: it if anything did. Both are cleared as the turn's answer is given.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, added up as pi reports each request: as one
        #: number for the model it ran on, and by the kind each token went on.
        self._spent = 0
        self._costing = Usage()
        #: What the process now up was last told to think at, so that a flow moving the
        #: effort mid-session is told to pi rather than left on the flag it was started with.
        self._at: str | None = None
        #: The calls this turn has already said, by pi's own id for each, so that the row goes
        #: out at the first fragment of the arguments that says anything and not again at
        #: every fragment after it.
        self._reaching: set[str] = set()
        #: The calls being written now, by the place in the message pi is numbering them at:
        #: each is the call's id, what it is called, and as much of the JSON its arguments are
        #: written as has arrived. Kept because 0.85.1 sends those three things on three
        #: different events -- the id and the name once at the start, the arguments as bare
        #: fragments after it -- and a row needs the name and the arguments together.
        self._calling: dict[int, tuple[str, str, str]] = {}

    @property
    def named(self) -> str | None:
        """What pi calls this conversation, which is the id it was opened with."""
        return self._id or self._named

    def _command(self) -> list[str]:
        """Builds the ``pi --mode rpc`` that reads commands on stdin and says events on stdout.

        Opens the session while it is unopened and resumes it once it has an id -- pi takes
        the same flag for both, making the session it is given when there is none. Which is
        what an anchored session needs: its process ends with each turn, so the next one has a
        conversation to rejoin.

        Everything after the first four flags is a flow's own doing and defaults to absent, so
        an agent nobody has configured is started as a bare `pi` would be.
        """
        config = self._agent.config
        # A fresh id per attempt: an opening turn that failed may still have left pi holding
        # the session it was given, and retrying under that one would resume a turn that never
        # happened.
        pinned = self._id or str(uuid.uuid4())
        self._named = pinned
        argv = [
            "pi",
            "--mode",
            "rpc",
            "--model",
            config.model,
            # Out of pi's own ladder, so it is a rung pi has a word for. One it has not is a
            # warning on stderr and a turn that runs at the default anyway, which is why the
            # ladder is written down rather than passed through: pi never refuses this. An
            # agent at no rung says nothing, and pi leaves the model at its own thinking
            # level -- the flag carrying "" would be that same warning for no reason.
            *(["--thinking", self.effort] if self.effort else []),
            "--session-id",
            pinned,
        ]
        if self._id is None and self._forked_from is not None:
            # `--fork` opens this session on top of the one it names, so the turns of that
            # conversation are here and what follows them is not written into it. The id
            # asked for above is the one it opens under -- pi takes the two flags together
            # and refuses only where a session of that id is already there, which a freshly
            # minted one is not.
            argv += ["--fork", self._forked_from]
        if config.permission == "read-only":
            # Not a mode it is put in but tools it is not given: an agent without the ones
            # that change anything is one that can only look, which is the rung asked for.
            argv += ["--exclude-tools", ",".join(_CHANGING)]
        for said in getattr(config, "append_system_prompt", ()):
            argv += ["--append-system-prompt", said]
        for path in getattr(config, "skill_paths", ()):
            argv += ["--skill", path]
        if not getattr(config, "context_files", True):
            argv.append("--no-context-files")
        if not getattr(config, "extensions", True):
            argv.append("--no-extensions")
        if getattr(config, "offline", False):
            argv.append("--offline")
        return argv

    def _environment(self) -> Mapping[str, str]:
        """What a turn is run with: the provider's, where node may cache pi, and the preload.

        Returns:
          Those variables. `NODE_COMPILE_CACHE` is left exactly as it was found where somebody has
          set one already -- whether the provider names it or this process was started with it,
          theirs is the cache they meant -- is not set at all for a turn that lands somewhere
          else, since the path would name a directory on this machine rather than on the one the
          turn runs on, and is not set for an agent configured `compiled=False`, which is the
          way out of the one thing here humanize decided rather than read off pi. The preload is
          there for an agent something is listening to and absent otherwise, which
          :mod:`hmz.coganchor.agents.preload` decides: pi runs on Node, so what a turn of it runs,
          reads, writes and opens can be read from inside the process taking it.
        """
        added = dict(super()._environment())
        chosen = added.get(_COMPILED) or os.environ.get(_COMPILED)
        if (
            not chosen
            and self._agent.anchor is None
            and getattr(self._agent.config, "compiled", True)
        ):
            added[_COMPILED] = str(home().joinpath(*_CACHE))
        return preloaded(self._agent, added)

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one thing to say as the `prompt` command pi reads it as.

        Args:
          text: What to say.
          ticket: What to name the command by, or "" to leave it unnamed -- pi answers a
            command under the name it was sent with, and the turn's own prompt needs none:
            the turn beginning is what says that one landed.

        Returns:
          The line, newline included.
        """
        said: dict[str, Any] = {"type": "prompt", "message": text}
        if ticket:
            said["id"] = ticket
        line = json.dumps(said) + "\n"
        if self._at is not None and self._at != self.effort and self.effort:
            # How hard to think is a command here rather than a flag to restart under: pi
            # takes it on the session it is already holding, so a flow that moves the effort
            # is answered by telling it, ahead of the prompt the new effort is for.
            self._at = self.effort
            line = (
                json.dumps({"type": "set_thinking_level", "level": self._at})
                + "\n"
                + line
            )
        return line

    def interject(self, text: str) -> None:
        """Steers the turn under way, which pi takes into the turn it is running.

        Written rather than said: pi answers a whole agent run with one `agent_settled`,
        however many things it was told along the way, so a word put in is not a turn owed an
        answer of its own. What says the model has it is the user message pi splices into the
        conversation as it takes it in, which is a `took` event.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no process is up to hear it, which is a session no turn has opened.
        """
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("no turn is running to be talked to")
        # Named by its own words: pi splices a steered message into the conversation as the
        # user saying it, and the words are what both ends have to go on.
        self.steering(text, ticket=text)
        try:
            self._send(json.dumps({"type": "steer", "message": text}) + "\n")
        except BaseException:
            self.unsteered(text)  # nothing is coming back for a word that never went in
            raise

    def _restarted(self) -> None:
        """Forgets the turn the last process was in the middle of, which this one is not."""
        self._said, self._failed, self._spent, self._costing = "", None, 0, Usage()
        self._reaching, self._calling = set(), {}
        self._at = self.effort

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one event pi wrote, as the things it says the agent did.

        Args:
          line: The line, as written.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing: a fragment
          of a message still being written, a tool's result coming back, or an answer to a
          command nobody is waiting on.
        """
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: pi prints the odd plain line among the JSON
        match said.get("type"):
            case "response" if said.get("success") is False:
                # A command pi would not take. The one that matters is the prompt: a turn that
                # was never started is a failed turn, and there is no `agent_settled` coming.
                if said.get("command") == "prompt":
                    yield Event(
                        kind="failed", text=str(said.get("error") or "the turn failed")
                    )
            case "extension_ui_request":
                self._answer(said)
            case "message_update":
                yield from self._part(
                    cast("dict[str, Any]", said.get("assistantMessageEvent") or {})
                )
            case "message_start":
                # A word put into the turn, come back around: pi splices it into the
                # conversation at the step that takes it in, and that splice is the agent
                # saying it has it. The turn's own prompt arrives the same way and was never
                # put into anything, so it is not on the book and says nothing here.
                message: dict[str, Any] = said.get("message") or {}
                if message.get("role") == "user":
                    words = "".join(
                        str(cast("dict[str, Any]", part).get("text") or "")
                        for part in cast("list[Any]", message.get("content") or [])
                        if isinstance(part, dict)
                    )
                    if self.took(words) is not None:
                        yield Event(kind="took", text=words)
            case "message_end":
                self._message(cast("dict[str, Any]", said.get("message") or {}))
            case "agent_settled":
                # The whole of the run pi was told to make, the words put into it included:
                # it says this once it has stopped and has nothing queued behind.
                yield self._answered()
            case _:  # every other event is a step of a turn already read another way
                pass

    def _part(self, event: dict[str, Any]) -> Iterator[Event]:
        """Reads one part of a message pi is writing.

        Args:
          event: The `assistantMessageEvent`, as read.

        Yields:
          What the agent said, once its part is written, and what it reached for, as soon as
          there is enough of the call to say what it is about.
        """
        named = str(event.get("type") or "")
        if named in _REACHING:
            yield from self._reaches(event)
            return
        kind = _PARTS.get(named)
        if kind is None:
            return
        if (words := str(event.get("content") or "")).strip():
            yield Event(kind=kind, text=words)

    def _reaches(self, event: dict[str, Any]) -> Iterator[Event]:
        """Says that the agent has reached for something, once, as early as it can be said.

        The row goes out at the first fragment that finishes a value in the arguments rather
        than at the end, because the end is where the arguments stop arriving and the
        arguments are the file: for a `write` that is minutes in which the agent has reached
        for something and the turn has said nothing at all.

        Which takes assembling, because 0.85.1 hands the call over in three pieces and no one
        of them is the call. The start carries its id and what it is called and no arguments;
        each fragment after it carries the next piece of the JSON those arguments are written
        as and nothing else, not even the id; and only the end carries the call whole. Until
        0.84.0 every one of them also carried the message so far, which is what this used to
        read the name off -- that field was taken out, for the good reason that resending the
        whole of a message on every fragment of it is quadratic in the length of the answer.

        Read off those fragments as they came rather than off the `arguments` pi parses them
        into, which is what :func:`hmz.coganchor.agents.hooks.arriving` is for: the parse repairs
        what is half-written, so a value still arriving would read as a whole one and the row
        would say `write /tmp/se`.

        Args:
          event: The `assistantMessageEvent`, which is a `toolcall_start`, a `toolcall_delta`
            or a `toolcall_end`.

        Yields:
          The call: `bash echo hi`, `write src/x.py`. Only what will fit on a row, and nothing
          at all for a call already said or one whose arguments have said nothing yet.
        """
        named = str(event.get("type"))
        # Which part of the message this is about, which is what the fragments carry instead
        # of the call's id and so is the only thing there is to hold the pieces together by.
        at = int(cast("int", event.get("contentIndex") or 0))
        if named == "toolcall_start":
            self._calling[at] = (
                str(event.get("id") or ""),
                str(event.get("toolName") or "tool"),
                "",
            )
            return  # nothing to say yet: a row of `bash` and no command says nothing
        if named == "toolcall_delta":
            held = self._calling.get(at)
            if held is None:
                return  # fragments of a call whose start was never seen
            marked, calls, sofar = held
            if marked and marked in self._reaching:
                return  # said already: the rest of these is the file being written
            # Only ever as much as `arriving` reads. The rest of a `write` is the file, and
            # keeping it would put five megabytes through a string join once per fragment of
            # itself -- which is the quadratic pi took its own cumulative message out of
            # `message_update` to be rid of, put back on this side of the pipe.
            sofar = (sofar + str(event.get("delta") or ""))[:_SCANNED]
            self._calling[at] = (marked, calls, sofar)
            if not (words := arriving(sofar)):
                return  # nothing among the arguments has finished arriving to say it about
        else:
            called: dict[str, Any] = event.get("toolCall") or {}
            self._calling.pop(at, None)
            if not called:
                return  # an end carrying no call at all is nothing to say a row about
            marked = str(called.get("id") or "")
            calls = str(called.get("name") or "tool")
            words = _about(cast("dict[str, Any]", called.get("arguments") or {}))
        if not marked:
            # A call pi gave no id is said where it always was, at the end: there is nothing
            # to tell it from the next one, and folding every unnamed call onto one blank id
            # would say the first and silently drop every call after it.
            if named != "toolcall_end":
                return
        elif marked in self._reaching:
            return  # said already, as the model reached for it
        else:
            self._reaching.add(marked)
        yield Event(kind="tool", text=f"{calls} {words}".strip()[:_ROOM])

    def _message(self, message: dict[str, Any]) -> None:
        """Takes what one request to the model came to, as it comes back.

        pi answers a prompt with as many requests as the work takes, and says what each of
        them cost as it lands -- so a turn's spending is known while the turn is still
        running rather than once it is over. What it said last is the answer the turn ends
        on, and what it complained of last is why it did not.

        Args:
          message: The message just finished, as read.
        """
        if message.get("role") != "assistant":
            return
        usage: dict[str, Any] = message.get("usage") or {}
        # Every kind of token counts: what a rate is measuring is the traffic, and a cache
        # read crosses the wire like anything else. Told as it lands rather than once the run
        # is over, since that is what a rate read while the turn runs is made of.
        counted = Usage(
            {
                kind: float(usage.get(named) or 0)
                for kind, named in _KINDS.items()
                if usage.get(named)
            }
        )
        self._spent += int(counted.total)
        self._costing = self._costing + counted
        self._spends(counted)
        self._failed = (
            str(message["errorMessage"]) if message.get("errorMessage") else None
        )
        words = "".join(
            str(cast("dict[str, Any]", part).get("text") or "")
            for part in cast("list[Any]", message.get("content") or [])
            if isinstance(part, dict)
            and cast("dict[str, Any]", part).get("type") == "text"
        )
        if words.strip():
            self._said = words

    def _answered(self) -> Event:
        """The turn's answer, and what it cost, once pi has gone quiet.

        Returns:
          The `result` the turn ends on, or the `failed` that closes it the other way: a run
          whose last request came back as an error and left nothing to answer with did not
          land, and a loop fed that error would be running on it as the work of the turn.
        """
        said, failed, spent, turn = self._said, self._failed, self._spent, self._costing
        self._said, self._failed, self._spent, self._costing = "", None, 0, Usage()
        # The turn is over, so what it reached for is nothing the next one has to know about:
        # a session takes thousands of turns, and this would grow with all of them.
        self._reaching, self._calling = set(), {}
        tokens = {self._agent.config.model: spent} if spent > 0 else {}
        if failed is not None and not said:
            return Event(kind="failed", text=failed, tokens=tokens, spent=turn)
        if self._named is not None:
            self._adopt(self._named)  # a turn has landed, so the session is open
        return Event(kind="result", text=said.strip(), tokens=tokens, spent=turn)

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers something an extension of pi's stopped the turn to ask.

        pi waits on the answer, so one left unanswered is a turn that never ends. A question
        nobody is there to answer is cancelled, which pi reads as the person having walked
        away from it and carries on from.

        Args:
          said: The `extension_ui_request`, as read.
        """
        method = str(said.get("method") or "")
        if method not in _ASKS:
            return  # told rather than asked: a notice, a status, a widget, a title
        offers: list[Any] = said.get("options") or []
        answer = self._agent.asked(
            Question(
                text=str(said.get("title") or said.get("message") or ""),
                options=tuple(str(one) for one in offers)
                if method == "select"
                else (_YES_NO if method == "confirm" else ()),
            )
        )
        if answer is None:
            self._send(
                json.dumps(
                    {
                        "type": "extension_ui_response",
                        "id": said.get("id"),
                        "cancelled": True,
                    }
                )
                + "\n"
            )
            return
        answered: dict[str, Any] = {
            "type": "extension_ui_response",
            "id": said.get("id"),
        }
        if method == "confirm":
            answered["confirmed"] = answer.strip().lower() not in ("no", "n", "false")
        else:
            answered["value"] = answer
        self._send(json.dumps(answered) + "\n")


class PiAgent(AgentBase):
    """pi, driven over its RPC protocol so a turn can be talked to while it runs.

    Every moment here is one read off the turn itself: pi asks nothing of a client before it
    reaches for a tool, so there is no permission for a hook to be hung on.
    """

    #: What it counts, read off the same table its driver reads a usage with. Its reasoning
    #: is counted inside the output rather than beside it, so it is not a kind of its own.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> PiSession:
        """Opens a new pi session, in the directory it is given or in this one."""
        return PiSession(self, cwd)
